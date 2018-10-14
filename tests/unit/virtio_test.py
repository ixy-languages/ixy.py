import pytest

from ixypy.virtio.virtio_device import VirtIo
from ixypy.pci import PCIDevice, PCIAddress


def test_virtio():
    address = PCIAddress.from_address_string('0000:00:13.0')

    device = PCIDevice(address)
    pci_config = device.config()

    configuration = 'vendor_id={:02X} device_id={:02X}'.format(pci_config.vendor_id, pci_config.device_id)
    print('\n' + str(pci_config))
    vr = VirtIo(device)
