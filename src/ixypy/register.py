import re
import time
from os import pwrite, pread
from struct import pack_into, unpack_from


class Register(object):
    def set(self, reg, value, length):
        """
        Args:
            reg: register offset
            value: the value to be written
            length: length in bytes of the value
        """
        pass

    def get(self, reg, length):
        """
        Args:
            reg: register offset
            length: length in bytes of the value
        """
        pass

    def wait_set(self, reg, mask, length=1):
        """
        Args:
            reg: register offset
            mask: bitmask to be set
            length: length in bytes of the mask
        """
        current = self.get(reg, length)
        while (current & mask) != mask:
            time.sleep(0.01)
            current = self.get(reg, length)

    def __getattr__(self, name):
        op = re.match(r"(?P<operation>(get|set|wait_set))(?P<length>\d+)", name)

        def wrapper(*args, **kwargs):
            length = int(op['length'])
            if length % 8 != 0:
                raise ValueError('Invalid length {}'.format(length))
            rw = getattr(self, op['operation'])
            kwargs['length'] = length//8
            return rw(*args, **kwargs)

        if op:
            return wrapper
        else:
            raise AttributeError('No attribute {} found'.format(name))


class VirtioRegister(Register):
    def __init__(self, fd):
        self.fd = fd

    def set(self, offset, value, length=1):
        if pwrite(self.fd.fileno(), value.to_bytes(length, 'little'), offset) != length:
            raise RuntimeError('Failed to write to register')

    def get(self, offset, length=1):
        return int.from_bytes(pread(self.fd.fileno(), length, offset), 'little')


class MmapRegister(object):
    def __init__(self, mem_buffer):
        self.mem_buffer = mem_buffer

    def set(self, offset, value):
        pack_into('I', self.mem_buffer, offset, value & 0xFFFFFFFF)

    def set_flags(self, offset, flags):
        new_value = self.get(offset) | flags
        self.set(offset, new_value)

    def clear_flags(self, offset, flags):
        self.set(offset, self.get(offset) & ~flags)

    def get(self, offset):
        return unpack_from('I', self.mem_buffer, offset)[0]

    def print_reg(self, offset):
        print('{:02x}'.format(self.get(offset)))

    def wait_clear(self, offset, mask):
        current = self.get(offset)
        while (current & mask) != 0:
            time.sleep(0.01)
            current = self.get(offset)

    def wait_set(self, offset, mask):
        current = self.get(offset)
        while (current & mask) != mask:
            time.sleep(0.01)
            current = self.get(offset)
