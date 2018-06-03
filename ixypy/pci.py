import re
from struct import unpack, calcsize


class InvalidPCIAddressException(Exception):
    """Invalid pci address string."""

    pass


class PCIConfig(object):
    def __init__(self,
                 vendor_id,
                 device_id,
                 status_register,
                 control_register,
                 class_code,
                 revision_id,
                 header_type,
                 latency_timer,
                 cache_line_size,
                 base_address_registers,
                 card_bus_cis_pointer,
                 subsystem_id,
                 subsystem_vendor_id,
                 expansion_rom_base_address,
                 cap_pointer,
                 max_latency,
                 min_grant,
                 interrupt_pin,
                 interrupt_line):
        self.vendor_id = vendor_id
        self.device_id = device_id
        self.control_register = control_register
        self.status_register = status_register
        self.revision_id = revision_id
        self.class_code = class_code
        self.cache_line_size = cache_line_size
        self.latency_timer = latency_timer
        self.header_type = header_type
        self.base_address_registers = base_address_registers
        self.card_bus_cis_pointer = card_bus_cis_pointer
        self.subsystem_vendor_id = subsystem_vendor_id
        self.subsystem_id = subsystem_id
        self.expansion_rom_base_address = expansion_rom_base_address
        self.cap_pointer = cap_pointer
        self.interrupt_line = interrupt_line
        self.interrupt_pin = interrupt_pin
        self.min_grant = min_grant
        self.max_latency = max_latency


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
                                                   byteorder='little', signed=False),
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


class PCIDevice(object):
    def __init__(self, device, domain=0, bus=0, function=0, address=None):
        if address is None:
            self.address = PCIAddress(device, domain, bus, function)
        else:
            self.address = address
