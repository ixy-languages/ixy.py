import time
import logging as log

from functools import reduce

from memory import DmaMemory
from ixypy.mempool import Mempool
from ixypy.virtio.structures import VRing, VQueue, VirtioNetworkControl, PromiscuousModeCommand, VirtioNetworkHeader
from ixypy.ixy import IxyDevice
from ixypy.virtio import types
from ixypy.register import VirtioRegister
from ixypy.virtio.exception import VirtioException


class VirtioLegacyDevice(IxyDevice):
    net_hdr = VirtioNetworkHeader(flags=0, gso_type=types.VIRTIO_NET_HDR_GSO_NONE, header_len=14 + 20 + 8)

    def __init__(self, pci_device):
        self.rx_pkt_count = 0
        self.tx_pkt_count  = 0
        # Supporting at most 1 tx/rx queue
        super().__init__(pci_device, 'ixypy-virtio')
        self._verify_is_legacy()
        self.tx_pkts = 0
        self.tx_bytes = 0
        self.rx_pkts = 0
        self.rx_bytes = 0

    def _initialize_device(self):
        """Section 3.1"""
        log.debug('Configuring bar0')
        self.ctrl_queues = []
        self.resource, self.resource_size = self.pci_device.resource()
        self.reg = VirtioRegister(self.resource)
        self._reset_devices()
        self._ack_device()
        self._drive_device()
        self._setup_features()
        self._setup_rx_queue()
        self._setup_tx_queue()
        self._setup_ctrl_queue()
        self.signal_ok()
        self.verify_device()
        log.debug('Setting promisc mode')
        self.set_promisc()

    def _verify_is_legacy(self):
        legacy_device_id = 0x1000
        if self.pci_device.config().device_id != legacy_device_id:
            raise VirtioException('Device with id 0x{:02X} not supported'.format(self.pci_device.config().device_id))

    def set_promisc(self, on=True):
        command = VirtioNetworkControl(PromiscuousModeCommand(on=True))
        self.send_cmd(command)

    def read_stats(self, stats):
        stats.rx_packets += self.rx_pkts
        stats.tx_packets += self.tx_pkts
        stats.rx_bytes += self.rx_bytes
        stats.tx_bytes += self.tx_bytes
        self.rx_pkts, self.tx_pkts, self.rx_bytes, self.tx_bytes = 0, 0, 0, 0

    def get_link_speed(self):
        return 1000

    def rx_batch(self, queue_id, batch_size):
        vq = self.rx_queues[0]
        buffs = []
        vring_last_used_index = vq.vring.used.index
        # Read buffers from rx queue
        for _ in range(batch_size):
            if vq.used_last_index == vring_last_used_index:
                break
            used_element = vq.vring.used.rings[vq.used_last_index % vq.vring.size]
            used_element_id = used_element.id
            desc = vq.vring.descriptors[used_element_id]
            vq.used_last_index += 1
            self.rx_pkt_count += 1
            if desc.flags != types.VRING_DESC_F_WRITE:
                log.error("Unsupported rx flags on descriptor: %x", desc.flags)
                with open('log.txt', 'a+') as f:
                    f.write('{:d}\n'.format(self.rx_pkt_count))
                # desc.dump()
                vq.buffers[used_element.id].dump()
            desc.reset()
            buf = vq.buffers[used_element_id]
            buffs.append(buf)
            buff_size = used_element.length
            buf.size = buff_size
            self.rx_bytes += buff_size
            self.rx_pkts += 1

        for index, desc in vq.free_descriptors():
            pkt_buf = vq.mempool.get_buffer()
            pkt_buf.size = vq.mempool.buffer_size
            self.net_hdr.to_buffer(pkt_buf.head_room_buffer[-len(self.net_hdr):])
            desc.length = pkt_buf.size + len(self.net_hdr)
            desc.address = pkt_buf.data_addr - len(self.net_hdr)
            desc.flags = types.VRING_DESC_F_WRITE
            desc.next = 0
            vq.buffers[index] = pkt_buf
            vq.vring.available.rings[vq.vring.available.index % vq.vring.size] = index
            vq.vring.available.index += 1
            self._notify_queue(0)
        return buffs

    def _free_sent_buffers(self, vq):
        mempool = None
        while vq.used_last_index != vq.vring.used.index:
            used_element = vq.vring.used.rings[vq.used_last_index % vq.vring.size]
            idx = used_element.id
            buff = vq.buffers[idx]
            if buff:
                vq.buffers[idx] = None
            else:
                break
            desc = vq.vring.descriptors[idx]
            desc.address = 0
            desc.length = 0
            if not mempool:
                mempool = Mempool.pools[buff.mempool_id]
            mempool.free_buffer(buff)
            vq.used_last_index += 1

    def tx_batch(self, buffers, queue_id=0):
        vq = self.tx_queues[0]
        self._free_sent_buffers(vq)
        buffer_index = 0
        free_descriptors = vq.free_descriptors()
        for buffer in buffers:
            try:
                index, desc = next(free_descriptors)
            except StopIteration:
                break
            else:
                vq.buffers[index] = buffer
                buffer_size = buffer.size
                self.net_hdr.to_buffer(buffer.head_room_buffer[-len(self.net_hdr):])
                desc.length = buffer_size + len(self.net_hdr)
                offset = buffer.data_offset - len(self.net_hdr)
                desc.address = buffer.physical_address + offset
                desc.flags = 0
                desc.next_descriptor = 0
                vq.vring.available.rings[index] = index
                buffer_index += 1
                self.tx_bytes += buffer_size
                self.tx_pkts += 1
        vq.vring.available.index += buffer_index
        self._notify_queue(vq.identifier)
        return buffer_index

    def verify_device(self):
        if self.get_pci_status() == types.VIRTIO_CONFIG_STATUS_FAILED:
            raise VirtioException('Failed to initialize device')

    def signal_ok(self):
        self.reg.set(types.VIRTIO_PCI_STATUS, types.VIRTIO_CONFIG_STATUS_DRIVER_OK)

    def get_pci_status(self):
        return self.reg.get16(types.VIRTIO_PCI_STATUS)

    def send_cmd(self, net_ctrl):
        if net_ctrl.command_class != types.VIRTIO_NET_CTRL_RX:
            raise VirtioException('Command class[{}] is not supported'.format(net_ctrl.command_class))
        vq = self.ctrl_queues[0]
        vring = vq.vring
        index, header_descriptor = vq.get_free_descriptor()
        log.debug('Found descriptor slot at {:d} ({:d})'.format(index, vring.size))
        log.debug('Packet buffer allocation')
        pkt_buf = vq.mempool.get_buffer()
        net_ctrl.to_buffer(pkt_buf.data_buffer)
        vq.buffers[index] = pkt_buf

        log.debug('Writing to descriptor {:d}'.format(index))
        # Device-readable head: cmd header
        header_descriptor.length = 2
        header_descriptor.address = pkt_buf.data_addr
        header_descriptor.flags = types.VRING_DESC_F_NEXT
        header_descriptor.next_descriptor, payload_dscr = vq.get_free_descriptor()

        log.debug('Writing to descriptor {:d}'.format(header_descriptor.next_descriptor))
        # Device-readable payload: data
        payload_dscr.length = len(net_ctrl) - 2 - 1
        payload_dscr.address = pkt_buf.data_addr + 2
        payload_dscr.flags = types.VRING_DESC_F_NEXT
        payload_dscr.next_descriptor, ack_flag = vq.get_free_descriptor()

        log.debug('Writing to descriptor {:d}'.format(payload_dscr.next_descriptor))
        # Device-writable tail: ack flag
        ack_flag.length = 1
        ack_flag.address = pkt_buf.data_addr + len(net_ctrl) - 1
        ack_flag.flags = types.VRING_DESC_F_WRITE
        ack_flag.next_descriptor = 0

        log.debug('Avail index %d', vring.available.index)
        log.debug('Ring index = %d', vring.available.index % vring.size)
        vring.available.rings[vring.available.index % vring.size] = index
        vring.available.index += 1

        log.debug('Notifying queue')
        self._notify_queue(vq.identifier)
        # wait until buffer processed
        while vq.used_last_index == vring.used.index:
            time.sleep(1)
        vq.used_last_index += 1
        log.debug('Retrieved used element')
        log.debug('Used buff index => %d', vring.used.index)
        used_element = vring.used.rings[vring.used.index]
        log.debug('UE: %s', used_element)
        if used_element.id != index:
            log.error('Used buffer has different index as sent one')
        log.debug('Freeing buffer')

        vq.mempool.free_buffer(pkt_buf)
        for descriptor in [header_descriptor, payload_dscr, ack_flag]:
            descriptor.reset()

    def _notify_queue(self, index):
        self.reg.set16(types.VIRTIO_PCI_QUEUE_NOTIFY, index)

    def _notify_offset(self):
        return self.reg.get16(types.VIRTIO_PCI_QUEUE_NOTIFY)

    def _setup_rx_queue(self):
        self.rx_queues.append(self._setup_queue(index=0))

    def _setup_tx_queue(self):
        self.tx_queues.append(self._setup_queue(index=1, is_mempool_required=False))

    def _setup_ctrl_queue(self):
        self.ctrl_queues.append(self._setup_queue(index=2))

    def _setup_queue(self, index, is_mempool_required=True):
        """Section 5.1.2"""
        log.debug('Setting up queue %d', index)
        self._create_virt_queue(index)
        max_queue_size = self._max_queue_size()
        virt_queue_mem_size = VRing.byte_size(max_queue_size, 4096)
        log.debug('max queue size: %d', max_queue_size)
        log.debug('queue size in bytes: %d', virt_queue_mem_size)
        dma = DmaMemory(virt_queue_mem_size)
        log.debug('Allocated %s', dma)
        self._set_physical_address(dma.physical_address)
        # virtual queue initialization
        mempool_size = self._mempool_size(index, max_queue_size) if is_mempool_required else 0
        notify_offset = self._notify_offset()
        vqueue = self._build_queue(dma, max_queue_size, index, notify_offset, mempool_size) 
        log.debug('notify offset: %d', notify_offset)
        vqueue.disable_interrupts()
        return vqueue

    @staticmethod
    def _build_queue(dma, size, index, notify_offset, mempool_size):
        mem = memoryview(dma)
        if mempool_size > 0:
            mempool = Mempool.allocate(mempool_size)
            return VQueue(mem, size, index, notify_offset, mempool)
        else:
            return VQueue(mem, size, index, notify_offset)

    @staticmethod
    def _mempool_size(index, max_queue_size):
        return max_queue_size if index == 2 else max_queue_size * 4

    def _create_virt_queue(self, idx):
        self.reg.set16(types.VIRTIO_PCI_QUEUE_SEL, idx)

    def _set_physical_address(self, phy_address):
        address = phy_address >> types.VIRTIO_PCI_QUEUE_ADDR_SHIFT
        log.debug('Setting VQueue address to: 0x%02X', address)
        self.reg.set32(types.VIRTIO_PCI_QUEUE_PFN, address)

    def _max_queue_size(self):
        return self.reg.get32(types.VIRTIO_PCI_QUEUE_NUM)

    def _set_features(self):
        self.reg.set32(types.VIRTIO_PCI_GUEST_FEATURES, self._required_features())

    def _drive_device(self):
        log.debug('Setting the driver status')
        self.reg.set(types.VIRTIO_PCI_STATUS,
                     types.VIRTIO_CONFIG_STATUS_DRIVER)

    def _ack_device(self):
        log.debug('Acknowledge device')
        self.reg.set(types.VIRTIO_PCI_STATUS, types.VIRTIO_CONFIG_STATUS_ACK)

    def _reset_devices(self):
        log.debug('Resetting device')
        self.reg.set(types.VIRTIO_PCI_STATUS, types.VIRTIO_CONFIG_STATUS_RESET)
        self.reg.wait_set(types.VIRTIO_PCI_STATUS,
                          types.VIRTIO_CONFIG_STATUS_RESET)

    def _setup_features(self):
        host_features = self._host_features()
        required_features = self._required_features()
        log.debug('Host features: 0x%02X', host_features)
        log.debug('Required features: 0x%02X', required_features)
        if not host_features & types.VIRTIO_F_VERSION_1:
            raise VirtioException('In legacy mode but, not a legacy device')
        if (host_features & required_features) != required_features:
            raise VirtioException("Device doesn't support required features")
        log.debug('Guest features before negotiation: 0x%02X', self.reg.get32(types.VIRTIO_PCI_GUEST_FEATURES))
        self._set_features()
        log.debug('Guest features after negotiation: 0x%02X', self.reg.get32(types.VIRTIO_PCI_GUEST_FEATURES))

    def _host_features(self):
        return self.reg.get32(types.VIRTIO_PCI_HOST_FEATURES)

    @staticmethod
    def _required_features():
        features = [types.VIRTIO_NET_F_CSUM,
                    types.VIRTIO_NET_F_GUEST_CSUM,
                    types.VIRTIO_NET_F_CTRL_VQ,
                    types.VIRTIO_F_ANY_LAYOUT,
                    types.VIRTIO_NET_F_CTRL_RX]
        return reduce(lambda x, y: x | y, map(lambda x: 1 << x, features), 0)
