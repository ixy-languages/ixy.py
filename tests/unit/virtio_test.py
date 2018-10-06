import pytest

from ixypy.virtio.virtio_device import VirtIo, VCommand, VNetCtrlHdr
from ixypy.pci import PCIDevice, PCIAddress


def test_virtio():
    address = PCIAddress.from_address_string('0000:00:08.0')
    device = PCIDevice(address)
    pci_config = device.config()

    configuration = 'vendor_id={:02X} device_id={:02X}'.format(pci_config.vendor_id, pci_config.device_id)
    print('\n' + str(pci_config))
    vr = VirtIo(device)


@pytest.mark.parametrize('class_, cmd', [
    (0, 0),
    (1, 0),
    (1, 1)
])
def test_vnet_ctrl_hdr_to_bytes(class_, cmd):
    hdr = VNetCtrlHdr(class_, cmd)

    assert hdr.to_bytes() == bytes([class_, cmd])


@pytest.mark.parametrize('on', [0, 1])
def test_command_to_bytes(on):
    hdr = VNetCtrlHdr(1, 1)

    cmd = VCommand(hdr, on)

    assert cmd.to_bytes() == bytes([0x01, 0x01, on, 0x00])
