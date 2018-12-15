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


class RxWbHsRss(object):
    def __init__(self, pkt_info, hdr_info):
        self.pkt_info = pkt_info
        self.hdr_info = hdr_info


class RxDescriptorWritebackLower(IxgbeStruct):
    # Low dword
    hs_rss_fmt = 'H H'
    lo_dword_fmt = 'I {}'.format(hs_rss_fmt)
    # High dword
    csum_ip = 'H H'
    hi_dword_fmt = 'I {}'.format(csum_ip)

    def __init__(self, buffer):
        super().__init__(buffer, '{} {}'.format(self.lo_dword_fmt, self.hi_dword_fmt))
        self.lo_dword = Struct(self.lo_dword_fmt)
        self.hi_dword = Struct(self.hi_dword_fmt)

    def unpack_lo_dword(self):
        return self.lo_dword.unpack_from(self.buffer, 0)

    @property
    def data(self):
        return self.unpack_lo_dword()[0]

    @data.setter
    def data(self, data):
        self._pack_into(data, 'Q')

    @property
    def hs_rss(self):
        lo_dword = self.unpack_lo_dword()
        return RxWbHsRss(lo_dword[1], lo_dword[2])

    @hs_rss.setter
    def hs_rss(self, hs_rss):
        offset = calcsize('Q')
        pack_into(self.hs_rss_fmt, self.buffer, offset, hs_rss.pkt_info, hs_rss.hdr_info)


class RxDescriptorWritebackUpper(object):
    def __init__(self, buffer):
        pass
