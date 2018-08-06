
import time
from os import pwrite, pread

from struct import calcsize

from memory import DmaMemory

from ixypy.ixy import IxyDevice
from ixypy.virtio_type import *


class VStructure(object):
    def __init__(self, fmt):
        self.format = fmt

    def size(self):
        return calcsize(self.format)


class VRingDescriptor(VStructure):
    def __init__(self, address=None, length=None, flags=None, next_descriptor=None):
        super().__init__('Q I H H')
        self.address = address
        self.length = length
        self.flags = flags
        self.next_descriptor = next_descriptor


class VRingAvailable(VStructure):
    def __init__(self, flags=None, idx=None, ring=None):
        super().__init__('3H')


class VRingUsedElement(VStructure):
    def __init__(self):
        super().__init__('2I')


class VRingUsed(VStructure):
    def __init__(self):
        super().__init__('H H {}'.format(VRingUsedElement().format))


class VQueue(VStructure):
    def __init__(self):
        super().__init__('{} Q H Q')


class VirtIo(IxyDevice):
    def __init__(self, pci_device):
        super().__init__(pci_device, 'Ixy VirtIo driver')

    def _initialize_device(self):
        # TODO: Check if running as ROOT
        if self.pci_device.has_driver():
            self.pci_device.unbind_driver()
        self.pci_device.enable_dma()

        self.resource, self.resource_size = self.pci_device.resource()
        self._reset_devices()
        self._ack_device()
        self._set_driver_status()
        host_features = self._host_features()
        required_features = self._required_features()
        if host_features & 1 << VIRTIO_F_VERSION_1:
            raise ValueError('Not a legacy device')
        print(hex(host_features))
        print(hex(self._required_features()))
        if (host_features & required_features) != required_features:
            raise ValueError("Device doesn't support required features")
        self._set_features()
        self._setup_rx_queue()
        self._signal_ok()

    def get_link_speed(self):
        pass

    def get_stats(self):
        pass

    def set_promisc(self):
        pass

    def rx_batch(self):
        pass

    def tx_batch(self):
        pass

    @classmethod
    def _byte_str(cls, num, size=1):
        return num.to_bytes(size, 'little')

    def _vring_size(self, number, align):
        size = number * VRingDescriptor().size()
        size = size + VRingAvailable().size() + number * calcsize('H')
        # ceiling
        size = size + VRingUsed().size() + number * VRingUsedElement().size()
        return size

    def _setup_rx_queue(self, idx=0):
        # Create virt queue
        self._create_virt_queue(idx)

        max_queue_size = int.from_bytes(pread(self.resource.fileno(), 4, VIRTIO_PCI_QUEUE_NUM), 'little')
        notify_offset = int.from_bytes(pread(self.resource.fileno(), 2, VIRTIO_PCI_QUEUE_NOTIFY), 'little')
        virt_queue_mem_size = self._vring_size(max_queue_size, 4096)
        mem = DmaMemory(virt_queue_mem_size)
        #mem.set_to(0xab, virt_queue_mem_size)
        self._set_physical_address(mem.phy())

    def _set_physical_address(self, phy_address):
        address = phy_address >> VIRTIO_PCI_QUEUE_ADDR_SHIFT
        pwrite(self.resource.fileno(), self._byte_str(address, 4), VIRTIO_PCI_QUEUE_SEL)

    def _create_virt_queue(self, idx):
        pwrite(self.resource.fileno(), self._byte_str(idx, 2), VIRTIO_PCI_QUEUE_SEL)

    def _signal_ok(self):
        pwrite(self.resource.fileno(), self._byte_str(
            VIRTIO_CONFIG_STATUS_DRIVER_OK), VIRTIO_PCI_STATUS)

    def _host_features(self):
        host_features_bytes = pread(self.resource.fileno(), 4, VIRTIO_PCI_HOST_FEATURES)
        return int.from_bytes(host_features_bytes, 'little')

    def _required_features(self):
        return (1 << VIRTIO_NET_F_CSUM) | (1 << VIRTIO_NET_F_GUEST_CSUM)    \
            | (1 << VIRTIO_NET_F_CTRL_VQ) \
            | (1 << VIRTIO_NET_F_CTRL_RX)

    def _set_features(self):
        pwrite(self.resource.fileno(), self._byte_str(self._required_features(), 4), VIRTIO_PCI_GUEST_FEATURES)

    def _set_driver_status(self):
        pwrite(self.resource.fileno(), self._byte_str(VIRTIO_CONFIG_STATUS_DRIVER), VIRTIO_PCI_STATUS)

    def _ack_device(self):
        pwrite(self.resource.fileno(), self._byte_str(VIRTIO_CONFIG_STATUS_ACK), VIRTIO_PCI_STATUS)

    def _reset_devices(self):
        pwrite(self.resource.fileno(), self._byte_str(VIRTIO_CONFIG_STATUS_RESET), VIRTIO_PCI_STATUS)
        while pread(self.resource.fileno(), 1, VIRTIO_PCI_STATUS) != self._byte_str(VIRTIO_CONFIG_STATUS_RESET):
            time.sleep(0.1)
