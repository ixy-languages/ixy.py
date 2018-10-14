
import time
import logging as log

from functools import reduce
from os import pwrite, pread, getuid
from struct import calcsize, unpack, pack

from memory import DmaMemory, Mempool, PktBuf

from ixypy.virtio.structures import VRing, Queue, VNetworkControlHeader, VCommand
from ixypy.ixy import IxyDevice
from ixypy.virtio_type import *
from ixypy.register import Register


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
        self.set_promisc()

    def set_promisc(self, on=True):
        header = VNetworkControlHeader(VIRTIO_NET_CTRL_RX, VIRTIO_NET_CTRL_RX_PROMISC)
        command = VCommand(header, on)
        self.send_cmd(command)

    def get_link_speed(self):
        return 1000

    def get_stats(self):
        pass

    def rx_batch(self):
        pass

    def tx_batch(self):
        pass

    def verify_device(self):
        if self.get_pci_status() == VIRTIO_CONFIG_STATUS_FAILED:
            raise ValueError('Failed to initialize device')

    def signal_ok(self):
        self.register.write(VIRTIO_CONFIG_STATUS_DRIVER_OK, VIRTIO_PCI_QUEUE_SEL)

    def get_pci_status(self):
        return self.register.read16(VIRTIO_PCI_STATUS)

    def send_cmd(self, cmd):
        if cmd.header.class_ != VIRTIO_NET_CTRL_RX:
            raise ValueError('Command class is not supported')
        # find free descriptor slot
        vq = self.ctrl_queue.vqueue
        index, header_dscr = self.ctrl_queue.get_free_descriptor()
        buf = PktBuf(self.ctrl_queue.mempool)
        # TODO implement buffer protocol
        buf.to_buff(cmd.to_bytes())
        self.ctrl_queue.virtual_addresses[index] = buf

        # Device-readable head: cmd header
        header_dscr.write(len(cmd.header), buf.data_physical_address(), VRING_DESC_F_NEXT, index + 1)

        # Device-readable payload: data
        payload_dscr = vq.descriptors[index+1]
        payload_dscr.write(len(cmd), buf.data_physical_address() + 2, VRING_DESC_F_NEXT, index + 2)

        # Device-writable tail: ack flag
        ack_dscr = vq.descriptors[index+2]
        ack_dscr.write(1, buf.data_physical_address() + len(cmd) - 1, VRING_DESC_F_WRITE, 0)
        available_queue_index = vq.available_queues.idx % vq.size
        vq.available_queues.set_ring(index, available_queue_index)
        vq.available_queues.idx += 1

        # wait until buffer processed
        # while self.ctrl_queue.used_last_index == vq.used_queues.idx:
        #     print("Waiting...")
        #     time.sleep(1)
        self.ctrl_queue.used_last_index += 1
        # Check status and free buffer
        vq_used = vq.used_queues.used_elements[vq.used_queues.idx]
        if vq_used.id() != index:
            print("Used buffer has different index as sent one")

        if self.ctrl_queue.virtual_addresses[index] != buf:
            print("Buffer differ")

        buf.free()
        self.ctrl_queue.used_last_index += 1
        vq.descriptors[index].reset()
        vq.descriptors[index+1].reset()
        vq.descriptors[index+2].reset()

    def _notify_offset(self):
        return self.register.read16(VIRTIO_PCI_QUEUE_NOTIFY)

    def _setup_rx_queue(self):
        self.rx_queue = self._build_queue(index=0)

    def _setup_tx_queue(self):
        self.tx_queue = self._build_queue(1)

    def _setup_ctrl_queue(self):
        self.ctrl_queue = self._build_queue(2)

    def _build_queue(self, index, mempool=True):
        log.debug('Setting up queue %d', index)
        self._create_virt_queue(index)
        max_queue_size = self._max_queue_size()
        notify_offset = self._notify_offset()
        virt_queue_mem_size = VRing.byte_size(max_queue_size, 4096)
        log.debug('max queue size: %d', max_queue_size)
        log.debug('notify offset: %d', notify_offset)
        log.debug('queue size in bytes: %d', virt_queue_mem_size)
        mem = DmaMemory(virt_queue_mem_size)
        log.debug(mem)
        self._set_physical_address(mem.physical_address)
        # virtual queue initialization
        vq = VRing(max_queue_size, memoryview(mem))
        queue = Queue(vq, notify_offset, Mempool(max_queue_size * 4, 2048)) if mempool else Queue(vq, notify_offset)
        queue.disable_interrupts()
        return queue

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
                    VIRTIO_F_ANY_LAYOUT,
                    VIRTIO_NET_F_CTRL_RX]
        return reduce(lambda x, y: x | y, map(lambda x: 1 << x, features), 0)
