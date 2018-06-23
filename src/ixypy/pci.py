import re
import os


from enum import Enum

from mmap import mmap, ACCESS_WRITE
from struct import unpack, calcsize


class PCIException(Exception):
    pass


class MmapNotSupportedException(PCIException):
    pass


class InvalidPCIAddressException(PCIException):
    pass


class UnknownDeviceClassException(PCIException):
    pass


class UnknownVendorException(PCIException):
    pass


class PCIConfig(object):
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            self.__dict__[key] = value


class PCIConfigurationReader(object):
    config_format = '< 4H 7B x 7I 2H I B 7x 4B'

    def __init__(self, path):
        self.path = path

    def read(self):
        with open(self.path, 'rb') as fd:
            config_data = fd.read(calcsize(self.config_format))
        config_tuple = unpack(self.config_format, config_data)
        return PCIConfig(vendor_id=config_tuple[0],
                         device_id=config_tuple[1],
                         control_register=config_tuple[2],
                         status_register=config_tuple[3],
                         revision_id=config_tuple[4],
                         class_code=int.from_bytes(bytes(config_tuple[5:8]),
                                                   byteorder='big', signed=False),
                         cache_line_size=config_tuple[8],
                         latency_timer=config_tuple[9],
                         header_type=config_tuple[10],
                         base_address_registers=config_tuple[11:17],
                         card_bus_cis_pointer=config_tuple[17],
                         subsystem_vendor_id=config_tuple[18],
                         subsystem_id=config_tuple[19],
                         expansion_rom_base_address=config_tuple[20],
                         cap_pointer=config_tuple[21],
                         interrupt_line=config_tuple[22],
                         interrupt_pin=config_tuple[23],
                         min_grant=config_tuple[24],
                         max_latency=config_tuple[25])


class PCIAddress(object):
    MAX_VAL = {
        # 16 bit
        'domain': 2**16,
        # 8 bit
        'bus': 2**8,
        # 5 bit
        'device': 2**5,
        # 3 bit
        'function': 2**3
    }

    def __init__(self, domain=0, bus=0, device=0, function=0):
        self.bus = bus
        self.domain = domain
        self.device = device
        self.function = function
        for field, value in self.__dict__.items():
            if not self._is_valid(field, value):
                raise InvalidPCIAddressException(
                    '{} is not a valid value for {}'.format(value, field))

    @classmethod
    def from_address_string(cls, address_string):
        """
        PCIAddress instance from string

        Get an instance of PCIAddress from a string representation (e.g. 0000:af:15:3).
        If the domain is ommitted, it defaults to 0x0000


        :param address_string: string representation of the address
        :return: An equivalent PCIAddress instance
        :raises: InvalidPCIAddressException
        """
        if not PCIAddress._is_valid_address_string(address_string):
            raise InvalidPCIAddressException('Invalid PCI address <{}>'.format(address_string))
        address_prefix, function_str = address_string.split('.')
        address_items = address_prefix.split(':')
        address_items.append(function_str)
        address_items_hex = [int(item, 16) for item in address_items]
        if len(address_items) == 4:
            return PCIAddress(*address_items_hex)
        return PCIAddress(0x0000, *address_items_hex)

    def _is_valid(self, item, value):
        return 0 <= value < self.MAX_VAL[item]

    def __eq__(self, other):
        if isinstance(self, other.__class__):
            return self.__dict__ == other.__dict__
        return NotImplemented

    def __str__(self):
        return '{}:{}:{}.{}'.format(
            format(self.domain, '04x'),
            format(self.bus, '02x'),
            format(self.device, '02x'),
            format(self.function, '01x'))

    def __repr__(self):
        return '<{}(domain={}, bus={}, device={}, function={})>'.format(
            self.__class__.__name__,
            self.domain,
            self.bus,
            self.device,
            self.function
        )

    @staticmethod
    def _is_valid_address_string(address_string):
        pci_address_regex = "([0-9a-f]{4}:)?[0-9a-f]{2}:[0-9a-f]{2}\\.[0-9a-f]$"
        return re.match(pci_address_regex, address_string)


class PCIDeviceController(object):
    def __init__(self, device_path):
        self.device_path = device_path

    def config_path(self):
        return '{device_path}/config'.format(device_path=self.device_path)

    def enable_dma(self):
        mask = 1 << 2
        with open(self.config_path(), 'r+b') as config:
            config.seek(4)
            command_reg = bytearray(config.read(2))
            command_reg[0] |= mask
            config.seek(4)
            config.write(command_reg)

    def has_driver(self):
        return os.path.exists('{}/driver/unbind'.format(self.device_path))

    def unbind_driver(self, device_address):
        unbind_path = '{}/driver/unbind'.format(self.device_path)
        if os.path.exists(unbind_path):
            with open(unbind_path, 'w') as unbind:
                unbind.write(str(device_address))
        else:
            raise RuntimeError('No bound driver')

    def map_resource(self):
        resource_fd, size = self.resource()
        try:
            return mmap(resource_fd.fileno(), size, access=ACCESS_WRITE)
        except OSError:
            raise MmapNotSupportedException('Failed mapping device<{}>'.format(self.device_path))

    def resource(self):
        resource_path = '{}/resource0'.format(self.device_path)
        if os.path.exists(resource_path):
            size = os.stat(resource_path).st_size
            return open(resource_path, 'r+b'), size
        else:
            raise PCIException('No resource found at<{}>'.format(resource_path))


class PCIDevice(object):
    def __init__(self, address, pci_controller=None):
        self.address = address
        if pci_controller is None:
            self.pci_controller = PCIDeviceController(self.path())
        else:
            self.pci_controller = pci_controller

    def path(self):
        return '/sys/bus/pci/devices/{address}'.format(address=self.address)

    def has_driver(self):
        return self.pci_controller.has_driver()

    def unbind_driver(self):
        self.pci_controller.unbind_driver(self.address)

    def map_resource(self):
        return self.pci_controller.map_resource()

    def config(self):
        return PCIConfigurationReader(self.pci_controller.config_path()).read()

    def vendor(self):
        vendor_id = self.config().vendor_id
        try:
            return PCIVendor(self.config().vendor_id)
        except ValueError:
            raise UnknownVendorException('Unknown vendor with id<{}>'.format(hex(vendor_id)))

    def class_(self):
        class_code = self.config().class_code
        try:
            return PCIClass(self.config().class_code)
        except ValueError:
            raise UnknownDeviceClassException(
                'Unknown device class with code<{}>'.format(hex(class_code)))


class PCIVendor(Enum):
    virt_io = 0x1af4
    intel = 0x8086


class PCIClass(Enum):
    unclassified = 0x00
    storage_controller = 0x01
    network_controller = 0x02
    display_controller = 0x03
    multimedia_controller = 0x04
    memory_controller = 0x05
    bridge = 0x06
    communication_controller = 0x07
    generic_system_peripheral = 0x08
    docking_station = 0x0a
    processor = 0x0b
    serial_bus_controller = 0x0c
    wireless_controller = 0x0d
    intelligent_controller = 0x0e
    satellite_communication_controller = 0x0f
    encryption_controller = 0x10
    signal_processing_controller = 0x11
    processing_accelerator = 0x12
    non_essential_instrumentation = 0x13
    coprocessor = 0x40
