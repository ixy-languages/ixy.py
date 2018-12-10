from struct import Struct, calcsize, pack_into, unpack_from


class Queue(object):
    def __init__(self, num_entries, identifier):
        self.num_entries = num_entries
        self.identifier = identifier


class RxQueue(Queue):
    def __init__(self, num_entries, identifier, memory):
        super().__init__(num_entries, identifier)
        self.memory = memory
        self.virtual_addresses = []


class TxQueue(Queue):
    def __init__(self, num_entries, identifier, memory):
        super().__init__(num_entries, identifier)


class IxgbeStruct(object):
    def __init__(self, buffer, fmt):
        self.buffer = buffer
        self.struct = Struct(fmt)

    def _pack_into(self, value, field_format, prefix=''):
        offset = calcsize(prefix)
        pack_into(field_format, self.buffer, offset, value)

    def _unpack(self):
        return self.struct.unpack(self.buffer)

    def byte_size(self):
        return self.struct.size


class RxDescriptor(object):
    """Advanced Receive Descriptor Sec. 7.1.6"""
    def __init__(self, buffer):
        self.buffer = buffer


class RxDescriptorRead(IxgbeStruct):
    """ Advanced Descriptor Read Sec. 7.1.6.1"""
    data_format = 'Q Q'

    def __init__(self, buffer):
        super().__init__(buffer, self.data_format)

    @property
    def pkt_addr(self):
        self._unpack()[0]

    @pkt_addr.setter
    def pkt_addr(self, address):
        self._pack_into(address, 'Q')

    @property
    def hdr_addr(self):
        self._unpack()[1]

    @hdr_addr.setter
    def hdr_addr(self, address):
        self._pack_into(address, 'Q', 'Q')

    @staticmethod
    def byte_size():
        return calcsize(RxDescriptorRead.data_format)


class RxDescriptorWriteback(object):
    """ Advanced Descriptor writeback Sec. 7.1.6.2 """
    def __init__(self, buffer):
        self.buffer = buffer


class RxDescriptorWritebackLower(object):
    def __init__(self, buffer):
        self.lo_dword = Struct('')


class RxDescriptorWritebackUpper(object):
    def __init__(self, buffer):
        pass
