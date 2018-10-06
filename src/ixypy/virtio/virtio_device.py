
import time
from os import pwrite, pread

from struct import calcsize, unpack, pack

from memory2 import DmaMemory, Mempool, PktBuf

from ixypy.ixy import IxyDevice
from ixypy.virtio_type import *
from ixypy.register import Register


class VirtioRegister(Register):
    def __init__(self, fd):
        self.fd = fd

    def write(self, value, length, offset):
        pwrite(self.fd.fileno(), self._byte_str(value, length//8), offset)

    @classmethod
    def _byte_str(cls, num, size=1):
        return num.to_bytes(size, 'little')


class VQueue(object):
    def __init__(self, vring, notification_offset, used_last_index, mempool):
        self.vring = vring
        self.notification_offset = notification_offset
        self.used_last_index = used_last_index
        self.mempool = mempool
        # virtual addresses


class VRing(object):
    def __init__(self, num):
        pass


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


class VNetCtrlHdr(object):
    fmt = 'B B'

    def __init__(self, class_, cmd):
        self.class_ = class_
        self.cmd = cmd

    def to_bytes(self):
        return pack(self.fmt, self.class_, self.cmd)

    @classmethod
    def size(cls):
        return calcsize(cls.fmt)


class VCommand(object):
    def __init__(self, hdr, on):
        self.hdr = hdr
        self.on = on

    def to_bytes(self):
        hdr_bytes = self.hdr.to_bytes()
        return pack(self.fmt, *hdr_bytes, self.on, 0)

    @property
    def fmt(self):
        return '{}B ? B'.format(self.hdr.size())


class VirtIo(IxyDevice):
    def __init__(self, pci_device):
        self.rx_queue = None
        self.ctrl_queue = None
        self.tx_queue = None
        super().__init__(pci_device, 'Ixy VirtIo driver')

    def _initialize_device(self):
        # TODO: Check if running as ROOT
        if self.pci_device.has_driver():
            self.pci_device.unbind_driver()
        self.pci_device.enable_dma()

        self.resource, self.resource_size = self.pci_device.resource()
        self.register = VirtioRegister(self.resource)
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
        self._setup_rx_queue(0)
        self._setup_tx_queue(1)
        self._setup_tx_queue(2)
        # memfence
        self._signal_ok()
        # check device
        self.check_device()
        # set promiscuous
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

    def check_device(self):
        if self.get_pci_status() == VIRTIO_CONFIG_STATUS_FAILED:
            raise ValueError('Failed to initialize device')

    def get_pci_status(self):
        return int.from_bytes(pread(self.resource.fileno(), 2, VIRTIO_PCI_STATUS), 'little')

    def set_promiscuous(self):
        pass

    def send_cmd(self, cmd):
        if len(cmd) < VNetCtrlHdr.size():
            raise ValueError('Cmd can\'t be shorter than control header')
        if cmd[0] != VIRTIO_NET_F_CTRL_RX:
            raise ValueError('Command class is not supported')
        # find free descriptor slot
        buf = PktBuf(self.ctrl_queue.mempool)
        buf.to_buff(cmd)
        # to be continued

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

        max_queue_size = self._max_queue_size()
        notify_offset = int.from_bytes(pread(self.resource.fileno(), 2, VIRTIO_PCI_QUEUE_NOTIFY), 'little')
        virt_queue_mem_size = self._vring_size(max_queue_size, 4096)
        print('max queue size rx {}, notify_offset = {}'.format(max_queue_size, notify_offset))
        mem = DmaMemory(virt_queue_mem_size)
        mem.set_to(0xab)
        self._set_physical_address(mem.physical_address)
        # virtual queue initialization
        vring = VRing(max_queue_size)
        mempool = Mempool(max_queue_size * 4, 2048)
        vqueue = VQueue(vring=vring, notification_offset=notify_offset, used_last_index=0, mempool=mempool)
        self.rx_queue = vqueue

    def _setup_tx_queue(self, idx=1):
        self._create_virt_queue(idx)
        max_queue_size = self._max_queue_size()
        virt_queue_mem_size = self._vring_size(max_queue_size, 4096)
        mem = DmaMemory(virt_queue_mem_size)
        mem.set_to(0xab)
        self._set_physical_address(mem.physical_address)
        notify_offset = int.from_bytes(pread(self.resource.fileno(), 2, VIRTIO_PCI_QUEUE_NOTIFY), 'little')
        vring = VRing(max_queue_size)
        # This is not needed for tx queue
        mempool = Mempool(max_queue_size * 4, 2048)
        vqueue = VQueue(vring=vring, notification_offset=notify_offset, used_last_index=0, mempool=mempool)
        if idx == 1:
            self.tx_queue = vqueue
        else:
            self.ctrl_queue = vqueue

    def _set_physical_address(self, phy_address):
        print('Adress {}'.format(phy_address))
        address = phy_address >> VIRTIO_PCI_QUEUE_ADDR_SHIFT
        print('Adress shifted {}'.format(address))
        pwrite(self.resource.fileno(), self._byte_str(address, 4), VIRTIO_PCI_QUEUE_PFN)

    def _max_queue_size(self):
        return int.from_bytes(pread(self.resource.fileno(), 4, VIRTIO_PCI_QUEUE_NUM), 'little')

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
