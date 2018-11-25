
import time
import logging as log

from functools import reduce
from os import pwrite, pread, getuid
from struct import calcsize, unpack, pack

from memory import DmaMemory

from ixypy.mempool import Mempool, PacketBuffer
from ixypy.virtio.structures import VRing, VQueue, VirtioNetworkControl, PromiscuousModeCommand, VirtioNetworkHeader
from ixypy.ixy import IxyDevice
from ixypy.virtio.types import *
from ixypy.register import Register
from ixypy.virtio.exception import VirtioException


def is_running_as_root():
    return getuid() == 0


class VirtioRegister(Register):

    def __init__(self, fd):
        self.fd = fd

    def write(self, value, offset, length=1):
        pwrite(self.fd.fileno(), value.to_bytes(length, 'little'), offset)

    def read(self, offset, length=1):
        return int.from_bytes(pread(self.fd.fileno(), length, offset), 'little')


class VirtIo(IxyDevice):
    net_hdr = VirtioNetworkHeader(flags=0, gso_type=VIRTIO_NET_HDR_GSO_NONE, header_len=14+20+8)
    legacy_device_id = 0x1000

    def __init__(self, pci_device):
        self.rx_queue = None
        self.ctrl_queue = None
        self.tx_queue = None
        super().__init__(pci_device, 'ixypy-virtio')

    def _initialize_device(self):
        if not is_running_as_root():
            log.warning('Not running as root')
        if self.pci_device.has_driver():
            log.info('Unbinding driver')
            self.pci_device.unbind_driver()
        if self.pci_device.config().device_id != self.legacy_device_id:
            raise ValueError('Device with id 0x{:02X} not supported'.format(self.pci_device.config().device_id))
        self.pci_device.enable_dma()
        log.debug('Configuring bar0')
        self.resource, self.resource_size = self.pci_device.resource()
        self.register = VirtioRegister(self.resource)
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

    def set_promisc(self, on=True):
        command = VirtioNetworkControl(PromiscuousModeCommand(on=True))
        self.send_cmd(command)

    def get_link_speed(self):
        return 1000

    def rx_batch(self, buffs):
        vq = self.rx_queue
        buff_indx = 0
        for i in range(len(buffs)):
            buff_indx = i
            if vq.used_last_index == vq.vring.used.index:
                break
            used_element = vq.vring.used.rings[vq.used_last_idx % vq.vring.size]
            log.debug('UE: %s', used_element)
            desc = vq.vring.descriptors[used_element.id]
            vq.used_last_index += 1
            if desc.flags != VRING_DESC_F_WRITE:
                log.error("Unsupported rx flags on descriptor: %x", desc.flags)
            desc.reset()
            buf = vq.virtual_addresses[used_element.id]
            buf.size = used_element.length
            buffs[i] = buf
            self.stats.rx_bytes += buf.size
            self.stats.rx_pkts += 1
        for index, desc in vq.vring.descriptors:
            if desc.address != 0:
                continue
            pkt_buf = vq.mempool.allocate_buffer()
            if not pkt_buf:
                log.error('Failed to allocate rx buffer')
            pkt_buf.size = vq.mempool.buffer_size
            self.net_hdr.to_buffer(pkt_buf.head_room_buffer[-len(self.net_hdr):])
            desc.length = pkt_buf.size + len(self.net_hdr)
            offset = pkt_buf.data_offset - len(self.net_hdr)
            desc.address = pkt_buf.physical_address + offset
            desc.flags = VRING_DESC_F_WRITE
            desc.next = 0
            vq.virtual_addresses[index] = pkt_buf
            vq.vring.available.rings[vq.vring.available.index % vq.vring.size] = index
            vq.vring.available.index += 1
            self._notify_queue(0)
        return buff_indx

    def tx_batch(self, buffers, queue_id=1):
        vq = self.tx_queue
        while vq.used_last_index != vq.vring.used.index:
            log.debug('Freeing sent buffers')
            used_element = vq.vring.used.rings[vq.used_last_index % vq.vring.size]
            desc = vq.vring.descriptors[used_element.id]
            desc.address = 0
            desc.length = 0
            log.debug('Freeing buffer %d', used_element.id)
            vq.mempool.free_buffer(vq.virtual_addresses[used_element.id])
            vq.used_last_index += 1
        # log.debug('Sending buffers')
        buffer_index = 0
        index = 0
        for buffer in buffers:
            try:
                index, desc = vq.get_free_descriptor()
            except VirtioException:
                # log.exception('no free descriptor')
                # raise ValueError()
                break
            else:
                self.stats.tx_bytes += buffer.size
                self.stats.tx_pkts += 1
                vq.virtual_addresses[index] = buffer
                self.net_hdr.to_buffer(buffer.head_room_buffer[-len(self.net_hdr):])

                desc.length = buffer.size + len(self.net_hdr)
                offset = buffer.data_offset - len(self.net_hdr)
                desc.address = buffer.physical_address + offset
                desc.flags = 0
                desc.next_descriptor = 0
                vq.vring.available.rings[index] = index
                buffer_index += 1
        log.debug("Available index %d", vq.vring.available.index)
        vq.vring.available.index = vq.vring.available.index + buffer_index
        self._notify_queue(1)
        return buffer_index

    def verify_device(self):
        if self.get_pci_status() == VIRTIO_CONFIG_STATUS_FAILED:
            raise ValueError('Failed to initialize device')

    def signal_ok(self):
        self.register.write(VIRTIO_CONFIG_STATUS_DRIVER_OK, VIRTIO_PCI_QUEUE_SEL)

    def get_pci_status(self):
        return self.register.read16(VIRTIO_PCI_STATUS)

    def send_cmd(self, net_ctrl):
        if net_ctrl.command_class != VIRTIO_NET_CTRL_RX:
            raise ValueError('Command class[{}] is not supported'.format(net_ctrl.command_class))

        send_queue = self.ctrl_queue.vring
        index, header_descriptor = self.ctrl_queue.get_free_descriptor()
        log.debug('Found descriptor slot at {:d} ({:d})'.format(index, send_queue.size))
        log.debug('Packet buffer allocation')
        pkt_buf = self.ctrl_queue.mempool.get_buffer()
        net_ctrl.to_buffer(pkt_buf.data_buffer)
        self.ctrl_queue.virtual_addresses[index] = pkt_buf

        log.debug('Writing to descriptor {:d}'.format(index))
        offset = pkt_buf.data_offset
        # Device-readable head: cmd header
        header_descriptor.length = 2
        header_descriptor.address = pkt_buf.physical_address + offset
        header_descriptor.flags = VRING_DESC_F_NEXT
        header_descriptor.next_descriptor, payload_dscr = self.ctrl_queue.get_free_descriptor()

        log.debug('Writing to descriptor {:d}'.format(header_descriptor.next_descriptor))
        # Device-readable payload: data
        payload_dscr.length = len(net_ctrl) - 2 - 1
        payload_dscr.address = pkt_buf.physical_address + offset + 2
        payload_dscr.flags = VRING_DESC_F_NEXT
        payload_dscr.next_descriptor, ack_flag = self.ctrl_queue.get_free_descriptor()

        log.debug('Writing to descriptor {:d}'.format(payload_dscr.next_descriptor))
        # Device-writable tail: ack flag
        ack_flag.length = 1
        ack_flag.address = pkt_buf.physical_address + offset + len(net_ctrl) - 1
        ack_flag.flags = VRING_DESC_F_WRITE
        ack_flag.next_descriptor = 0

        log.debug('Avail index %d', send_queue.available.index)
        log.debug('Ring index = %d', send_queue.available.index % send_queue.size)
        send_queue.available.rings[send_queue.available.index % send_queue.size] = index
        send_queue.available.index += 1

        log.debug('Notifying queue')
        self._notify_queue(2)
        # wait until buffer processed
        while self.ctrl_queue.used_last_index == send_queue.used.index:
            time.sleep(1)
        log.debug('Retrieved used element')
        log.debug('Used buff index => %d', send_queue.used.index)
        used_element = send_queue.used.rings[send_queue.used.index]
        log.debug('UE: %s', used_element)
        if used_element.id != index:
            log.error('Used buffer has different index as sent one')
        log.debug('Freeing buffer')
        self.ctrl_queue.mempool.free_buffer(pkt_buf)
        for descriptor in [header_descriptor, payload_dscr, ack_flag]:
            descriptor.reset()

    def _notify_queue(self, index):
        self.register.write16(index, VIRTIO_PCI_QUEUE_NOTIFY)

    def _notify_offset(self):
        return self.register.read16(VIRTIO_PCI_QUEUE_NOTIFY)

    def _setup_rx_queue(self):
        log.debug('Setting up rx queue')
        self.rx_queue = self._build_queue(index=0)

    def _setup_tx_queue(self):
        log.debug('Setting up tx queue')
        self.tx_queue = self._build_queue(index=1, mempool=False)

    def _setup_ctrl_queue(self):
        log.debug('Setting up control queue')
        self.ctrl_queue = self._build_queue(index=2)

    def _build_queue(self, index, mempool=True):
        log.debug('Setting up queue %d', index)
        self._create_virt_queue(index)
        max_queue_size = self._max_queue_size()
        virt_queue_mem_size = VRing.byte_size(max_queue_size, 4096)
        log.debug('max queue size: %d', max_queue_size)
        log.debug('queue size in bytes: %d', virt_queue_mem_size)
        mem = DmaMemory(virt_queue_mem_size)
        log.debug('Allocated %s', mem)
        self._set_physical_address(mem.physical_address)
        notify_offset = self._notify_offset()
        log.debug('notify offset: %d', notify_offset)

        # virtual queue initialization
        vring = VRing(memoryview(mem), max_queue_size)
        mempool_size = max_queue_size if index == 2 else max_queue_size * 4
        vqueue = VQueue(vring, notify_offset, Mempool.allocate(mempool_size, 2048)) if mempool else VQueue(vring, notify_offset)
        vqueue.disable_interrupts()
        return vqueue

    def _create_virt_queue(self, idx):
        self.register.write16(idx, VIRTIO_PCI_QUEUE_SEL)

    def _set_physical_address(self, phy_address):
        address = phy_address >> VIRTIO_PCI_QUEUE_ADDR_SHIFT
        log.debug('Setting VQueue address to: 0x%02X', address)
        self.register.write32(address, VIRTIO_PCI_QUEUE_PFN)

    def _max_queue_size(self):
        return self.register.read32(VIRTIO_PCI_QUEUE_NUM)

    def _set_features(self):
        self.register.write32(self._required_features(), VIRTIO_PCI_GUEST_FEATURES)

    def _drive_device(self):
        log.debug('Setting the driver status')
        self.register.write(VIRTIO_CONFIG_STATUS_DRIVER, VIRTIO_PCI_STATUS)

    def _ack_device(self):
        log.debug('Acknowledge device')
        self.register.write(VIRTIO_CONFIG_STATUS_ACK, VIRTIO_PCI_STATUS)

    def _reset_devices(self):
        log.debug('Resetting device')
        self.register.write(VIRTIO_CONFIG_STATUS_RESET, VIRTIO_PCI_STATUS)
        while self.register.read(VIRTIO_PCI_STATUS) != VIRTIO_CONFIG_STATUS_RESET:
            time.sleep(0.1)

    def _setup_features(self):
        host_features = self._host_features()
        required_features = self._required_features()
        log.debug('Host features: 0x%02X', host_features)
        log.debug('Required features: 0x%02X', required_features)
        if not host_features & VIRTIO_F_VERSION_1:
            raise ValueError('Not a legacy device')
        if (host_features & required_features) != required_features:
            raise ValueError("Device doesn't support required features")
        log.debug('Guest features before negotiation: 0x%02X', self.register.read32(VIRTIO_PCI_GUEST_FEATURES))
        self._set_features()
        log.debug('Guest features after negotiation: 0x%02X', self.register.read32(VIRTIO_PCI_GUEST_FEATURES))

    def _host_features(self):
        return self.register.read32(VIRTIO_PCI_HOST_FEATURES)

    @staticmethod
    def _required_features():
        features = [VIRTIO_NET_F_CSUM,
                    VIRTIO_NET_F_GUEST_CSUM,
                    VIRTIO_NET_F_CTRL_VQ,
                    # VIRTIO_F_ANY_LAYOUT,
                    VIRTIO_NET_F_CTRL_RX]
        return reduce(lambda x, y: x | y, map(lambda x: 1 << x, features), 0)
