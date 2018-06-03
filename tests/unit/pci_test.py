from struct import pack, calcsize
from collections import namedtuple

import pytest
from pytest import raises

from ixypy.pci import PCIAddress, PCIConfigurationReader, InvalidPCIAddressException


class TestPCIAddress(object):
    def test_pci_device_str(self):
        pci = PCIAddress(device=0x15)

        assert str(pci) == '0000:00:15.0'

    @pytest.mark.parametrize('address_string, expected_pci_address', [
        ('0000:00:15.0', PCIAddress(device=0x15)),
        ('0001:ff:00.1', PCIAddress(domain=0x1, bus=0xff, device=0x00, function=0x1)),
        ('00ff:11:03.7', PCIAddress(domain=0x00ff, bus=0x11, device=0x03, function=0x7)),
        ('11:03.7', PCIAddress(domain=0x0000, bus=0x11, device=0x03, function=0x7))
    ])
    def test_pci_address_from_string(self, address_string,
                                     expected_pci_address):
        actual_pci_address = PCIAddress.from_address_string(address_string)
        assert actual_pci_address == expected_pci_address

    @pytest.mark.parametrize('address_string', [
        ('0003.00:00.3'),
        ('0009.03.33.1'),
        ('00ff:ff:33:3'),
    ])
    def test_malformed_pci_address(self, address_string):
        with raises(InvalidPCIAddressException):
            PCIAddress.from_address_string(address_string)

    @pytest.mark.parametrize('domain, bus, device, function', [
        (0xffff1, 0x00, 0x00, 0x0),
        (0x0000, 0xFFF, 0x00, 0x0),
        (0x0000, 0x00, 0xFF, 0x0),
        (0x0000, 0x00, 0x00, 0x8)])
    def test_pci_invalid_param(self, domain, bus, device, function):
        with raises(InvalidPCIAddressException):
            PCIAddress(domain=domain,
                       bus=bus,
                       device=device,
                       function=function)


class TestPCIConfigurationReader(object):
    def test_fixture(self, pci_configuration):
        config_reader = PCIConfigurationReader(pci_configuration.config_path)
        config = config_reader.read()
        assert config.__dict__ == pci_configuration.config_dict

    def test_real_config(self):
        config_reader = PCIConfigurationReader('/sys/bus/pci/devices/0000:00:09.0/config')
        config = config_reader.read()
        print('{:02x}'.format(config.class_code))


def pack_config(fmt, config):
    config_tuple = (
        config['vendor_id'],
        config['device_id'],
        config['control_register'],
        config['status_register'],
        config['revision_id'],
        *config['class_code'].to_bytes(3, 'little'),
        config['cache_line_size'],
        config['latency_timer'],
        config['header_type'],
        *config['base_address_registers'],
        config['card_bus_cis_pointer'],
        config['subsystem_vendor_id'],
        config['subsystem_id'],
        config['expansion_rom_base_address'],
        config['cap_pointer'],
        config['interrupt_line'],
        config['interrupt_pin'],
        config['min_grant'],
        config['max_latency'],
    )
    return pack(fmt, *config_tuple)


@pytest.fixture()
def pci_configuration(tmpdir):
    pci_config = tmpdir.join('config')
    fmt = '< 4H 7B x 7I 2H I B 7x 4B'
    config = {
        'vendor_id': 0x1af4,
        'device_id': 0x1000,
        'control_register': 0x1,
        'status_register': 0x1,
        'revision_id': 0x1,
        'class_code': 0x2,
        'cache_line_size': 0x10,
        'latency_timer': 0x1,
        'header_type': 0x8,
        'base_address_registers': tuple(range(6)),
        'card_bus_cis_pointer': 0x0,
        'subsystem_vendor_id': 0x1000,
        'subsystem_id': 0x1af4,
        'expansion_rom_base_address': 0x1000,
        'cap_pointer': 0x40,
        'interrupt_line': 0x00,
        'interrupt_pin': 0x01,
        'min_grant': 0x00,
        'max_latency': 0x00,
    }
    packed_config = pack_config(fmt, config)
    with pci_config.open(mode='wb') as fd:
        fd.write(packed_config)
    PciConfig = namedtuple('PciConfig', ['config_dict', 'config_path'])
    return PciConfig(config, str(pci_config))
