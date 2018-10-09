
import time

from os import pwrite, pread
from struct import calcsize, unpack, pack

from memory import DmaMemory, Mempool, PktBuf

from ixypy.virtio.structures import VQueue, Queue
from ixypy.ixy import IxyDevice
from ixypy.virtio_type import *
from ixypy.register import Register


class VirtioRegister(Register):
    def __init__(self, fd):
        self.fd = fd

    def write(self, value, offset, length=1):
        pwrite(self.fd.fileno(), value.to_bytes(length, 'little'), offset)

    def read(self, offset, length=1):
        return int.from_bytes(pread(self.fd.fileno(), length, offset), 'little')


class VirtIo(IxyDevice):
    def __init__(self, pci_device):
        self.rx_queue = None
        self.ctrl_queue = None
        self.tx_queue = None
        super().__init__(pci_device, 'Ixy VirtIo driver')

    def _initialize_device(self):
        if self.pci_device.has_driver():
            self.pci_device.unbind_driver()
        self.pci_device.enable_dma()
        self.resource, self.resource_size = self.pci_device.resource()
        self.register = VirtioRegister(self.resource)
        self._reset_devices()
        self._ack_device()
        self._set_driver_status()
        self._setup_features()
        self._setup_rx_queue()
        self._setup_tx_queue()
        self._setup_ctrl_queue()
        self.signal_ok()
        self.verify_device()
        self.set_promisc()

    def get_link_speed(self):
        pass

    def get_stats(self):
        pass

    def set_promisc(self, on=True):
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

    def set_promiscuous(self):
        pass

    def send_cmd(self, cmd):
        if cmd[0] != VIRTIO_NET_F_CTRL_RX:
            raise ValueError('Command class is not supported')
        # find free descriptor slot
        index, descriptor = self.ctrl_queue.get_free_descriptor()
        buf = PktBuf(self.ctrl_queue.mempool)
        # TODO implement buffer protocol
        buf.to_buff(cmd)
        self.ctrl_queue.virtual_addresses[index] = buf
        descriptor.length
        # to be continued

    def _notify_offset(self):
        return self.register.read16(VIRTIO_PCI_QUEUE_NOTIFY)

    def _setup_rx_queue(self):
        self.rx_queue = self._build_queue(index=0)

    def _setup_tx_queue(self):
        self.tx_queue = self._build_tx_queue(1)

    def _setup_ctrl_queue(self):
        self.ctrl_queue = self._build_tx_queue(2)

    def _build_tx_queue(self, index):
        queue = self._build_queue(index)
        queue.disable_interrupts()
        return queue

    def _build_queue(self, index):
        self._create_virt_queue(index)
        max_queue_size = self._max_queue_size()
        notify_offset = self._notify_offset()
        virt_queue_mem_size = VQueue.byte_size(max_queue_size, 4096)
        print('Max queue size {}, notify_offset = {}'.format(max_queue_size, notify_offset))
        mem = DmaMemory(virt_queue_mem_size)
        mem.set_to(0xab)
        self._set_physical_address(mem.physical_address)
        # virtual queue initialization
        vq = VQueue(max_queue_size, memoryview(mem))
        print(len(vq))
        return Queue(vq, notify_offset, Mempool(max_queue_size * 4, 2048))

    def _set_physical_address(self, phy_address):
        print('Address {}'.format(phy_address))
        address = phy_address >> VIRTIO_PCI_QUEUE_ADDR_SHIFT
        print('Address shifted {}'.format(address))
        self.register.write32(address, VIRTIO_PCI_QUEUE_PFN)

    def _max_queue_size(self):
        return self.register.read32(VIRTIO_PCI_QUEUE_NUM)

    def _create_virt_queue(self, idx):
        self.register.write16(idx, VIRTIO_PCI_QUEUE_SEL)

    def _set_features(self):
        self.register.write32(self._required_features(), VIRTIO_PCI_GUEST_FEATURES)

    def _set_driver_status(self):
        self.register.write(VIRTIO_CONFIG_STATUS_DRIVER, VIRTIO_PCI_STATUS)

    def _ack_device(self):
        self.register.write(VIRTIO_CONFIG_STATUS_ACK, VIRTIO_PCI_STATUS)

    def _reset_devices(self):
        self.register.write(VIRTIO_CONFIG_STATUS_RESET, VIRTIO_PCI_STATUS)
        while self.register.read(VIRTIO_PCI_STATUS) != VIRTIO_CONFIG_STATUS_RESET:
            time.sleep(0.1)

    def _setup_features(self):
        host_features = self._host_features()
        required_features = self._required_features()
        if host_features & 1 << VIRTIO_F_VERSION_1:
            raise ValueError('Not a legacy device')
        print(hex(host_features))
        print(hex(self._required_features()))
        if (host_features & required_features) != required_features:
            raise ValueError("Device doesn't support required features")
        self._set_features()

    def _host_features(self):
        return self.register.read32(VIRTIO_PCI_HOST_FEATURES)

    def _required_features(self):
        return (1 << VIRTIO_NET_F_CSUM) | (1 << VIRTIO_NET_F_GUEST_CSUM)    \
            | (1 << VIRTIO_NET_F_CTRL_VQ) \
            | (1 << VIRTIO_NET_F_CTRL_RX)
