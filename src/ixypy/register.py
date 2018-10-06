import re


class Register(object):
    def write(self, value, length, offset):
        """
        Args:
            value: the value to be written
            length: length in bytes of the value
            offset: register offset
        """
        pass

    def read(self, length, offset):
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
            kwargs['length'] = int(op['length'])
            return rw(*args, **kwargs)

        if op:
            return wrapper
        else:
            raise AttributeError('No attribute {} found'.format(name))
