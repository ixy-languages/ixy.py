from ixypy.virtio import VirtIo
from ixypy.pci import PCIDevice, PCIAddress


def test_virtio():
    address = PCIAddress.from_address_string('0000:00:15.0')
    device = PCIDevice(address)
    vr = VirtIo(device)
