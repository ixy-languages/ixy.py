import re
import time
import logging as log
from struct import pack_into, unpack_from


class Register(object):
    def write(self, value, offset, length):
        """
        Args:
            value: the value to be written
            length: length in bytes of the value
            offset: register offset
        """
        pass

    def read(self, offset, length):
        """
        Args:
            length: length in bytes of the value
            offset: register offset
        """
        pass

    def __getattr__(self, name):
        op = re.match(r"(?P<operation>(write|read))(?P<length>\d+)", name)

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


class MmapRegister(object):

    def __init__(self, mem_buffer):
        self.mem_buffer = mem_buffer

    def set(self, offset, value):
        # log.debug('Setting value=%d offset=%d', value, offset)
        pack_into('I', self.mem_buffer, offset, value & 0xFFFFFFFF)

    def set_flags(self, offset, flags):
        new_value = self.get(offset) | flags
        self.set(offset, new_value)

    def clear_flags(self, offset, flags):
        self.set_flags(offset, ~flags)

    def get(self, offset):
        return unpack_from('I', self.mem_buffer, offset)[0]

    def wait_clear(self, offset, mask):
        self._wait_until_set(offset, mask, 0)

    def wait_set(self, offset, value):
        self._wait_until_set(offset, value, value)

    def _wait_until_set(self, offset, mask, value=0):
        current = self.get(offset)
        while current & value != value:
            log.debug('Waiting for flags 0x%02X in register 0x%02X to clear, current value 0x%02X', value, offset, current)
            time.sleep(0.01)
            current = self.get(offset)
