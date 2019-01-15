from ixypy.virtio.device import VirtioLegacyDevice 
from ixypy.ixgbe.device import IxgbeDevice
from ixypy.pci import PCIDevice, PCIAddress, PCIVendor

import logging as log

def init_device(pci_address):
    address = PCIAddress.from_address_string(pci_address)
    device = PCIDevice(address)
    return IxgbeDevice(device)

# def init_device(pci_address):
    # address = PCIAddress.from_address_string(pci_address)
    # device = PCIDevice(address)
    # log.info("Vendor = %s", device.vendor())
    # if device.vendor() == PCIVendor.virt_io:
        # return VirtioLegacyDevice(device)
    # elif device.vendor() == PCIVendor.intel:
        # return IxgbeDevice(device)
    # else:
        # raise ValueError('Device <{}> not supported'.format(pci_address))
