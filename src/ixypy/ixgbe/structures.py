from struct import Struct, calcsize, pack_into, unpack_from


class Queue(object):
    def __init__(self, num_descriptors, identifier):
        self.num_descriptors = num_descriptors
        self.identifier = identifier
        self.index = 0


class RxQueue(Queue):
    def __init__(self, num_descriptors, identifier, memory):
        super().__init__(num_descriptors, identifier)
        self.memory = memory
        self.buffers = []
        self.descriptors = self._get_descriptors()

    def _get_descriptors(self):
        desc_size = RxDescriptor.byte_size
        return [RxDescriptor(self.memory[i*desc_size:desc_size*(i+1)]) for i in range(self.num_descriptors)]


class TxQueue(Queue):
    def __init__(self, num_descriptors, identifier, memory):
        super().__init__(num_descriptors, identifier)
        self.clean_index = 0


class IxgbeStruct(object):
    def __init__(self, buffer, fmt):
        self.buffer = buffer
        self.data_struct = Struct(fmt)

    def _pack_into(self, value, field_format, prefix=''):
        offset = calcsize(prefix)
        pack_into(field_format, self.buffer, offset, value)

    def _unpack(self):
        return self.data_struct.unpack(self.buffer)

    def __len__(self):
        return self.data_struct.size

    @classmethod
    def byte_size(cls):
        return calcsize(cls.data_format)


class TxDescriptorRead(IxgbeStruct):
    data_format = 'Q I I'

    def __init__(self, buffer):
        super().__init__(buffer, self.data_format)

    @property
    def buffer_addr(self):
        return self._unpack()[0]

    @buffer_addr.setter
    def buffer_addr(self, buffer_addr):
        self._pack_into(buffer_addr, 'Q')

    @property
    def cmd_type_len(self):
        return self._unpack()[1]

    @cmd_type_len.setter
    def cmd_type_len(self, cmd_type_len):
        self._pack_into(cmd_type_len, 'H', 'Q')

    @property
    def olinfo_status(self):
        return self._unpack()[2]

    @olinfo_status.setter
    def olinfo_status(self, olinfo_status):
        self._pack_into(olinfo_status, 'H', 'Q H')


class TxDescriptorWriteback(IxgbeStruct):
    data_format = 'Q I I'

    def __init__(self, buffer):
        super().__init__(buffer, self.data_format)

    @property
    def rsvd(self):
        return self._unpack()[0]

    @rsvd.setter
    def rsvd(self, rsvd):
        self._pack_into(rsvd, 'Q')

    @property
    def nextseq_seed(self):
        return self._unpack()[1]

    @nextseq_seed.setter
    def nextseq_seed(self, nextseq_seed):
        self._pack_into(nextseq_seed, 'H', 'Q')

    @property
    def status(self):
        self._unpack()[2]

    @status.setter
    def status(self, status):
        self._pack_into(status, 'H', 'Q H')


class TxDescriptor(IxgbeStruct):
    data_format = '{} {}'.format(TxDescriptorRead.data_format, TxDescriptorWriteback.data_format)

    def __init__(self, buffer):
        super().__init__(buffer, self.data_format)
        self.read = TxDescriptorRead(buffer[:TxDescriptorRead.byte_size()])
        self.writeback = TxDescriptorWriteback(buffer[TxDescriptorRead.byte_size():TxDescriptorWriteback.byte_size()])


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


class RxWbHsRss(object):
    def __init__(self, pkt_info, hdr_info):
        self.pkt_info = pkt_info
        self.hdr_info = hdr_info


class RxWbCsumIp(object):
    def __init_(self, ip_id, csum):
        self.ip_id = ip_id
        self.csum = csum


class RxDescriptorWritebackLower(IxgbeStruct):
    # Low dword
    hs_rss_fmt = 'H H'
    data_fmt = 'I'
    lo_dword_fmt = '{} {}'.format(data_fmt, hs_rss_fmt)
    # High dword
    csum_ip_fmt = 'H H'
    rss_fmt = 'I'
    hi_dword_fmt = '{} {}'.format(rss_fmt, csum_ip_fmt)
    data_format = '{} {}'.format(lo_dword_fmt, hi_dword_fmt)

    def __init__(self, buffer):
        super().__init__(buffer, '{} {}'.format(self.lo_dword_fmt, self.hi_dword_fmt))
        self.lo_dword = Struct(self.lo_dword_fmt)
        self.hi_dword = Struct(self.hi_dword_fmt)

    def unpack_lo_dword(self):
        return self.lo_dword.unpack_from(self.buffer, 0)

    def unpack_hi_dword(self):
        return self.hi_dword.unpack_from(self.buffer, self.lo_dword.size)

    @property
    def data(self):
        return self.unpack_lo_dword()[0]

    @data.setter
    def data(self, data):
        self._pack_into(data, self.data_fmt)

    @property
    def hs_rss(self):
        lo_dword = self.unpack_lo_dword()
        return RxWbHsRss(lo_dword[1], lo_dword[2])

    @hs_rss.setter
    def hs_rss(self, hs_rss):
        offset = calcsize(self.data_fmt)
        pack_into(self.hs_rss_fmt, self.buffer, offset, hs_rss.pkt_info, hs_rss.hdr_info)

    @property
    def rss(self):
        self.unpack_hi_dword()[0]

    @rss.setter
    def rss(self, rss):
        offset = self.lo_dword.size
        pack_into(self.rss_fmt, self.buffer, offset, rss)

    @property
    def csum_ip(self):
        hi_dword = self.unpack_hi_dword()
        return RxWbCsumIp(hi_dword[1], hi_dword[2])

    @csum_ip.setter
    def csum_ip(self, csum_ip):
        offset = calcsize('{} {}'.format(self.lo_dword.format, self.rss_fmt))
        pack_into(self.csum_ip_fmt, self.buffer, offset, csum_ip.ip_id, csum_ip.csum)


class RxDescriptorWritebackUpper(IxgbeStruct):
    data_format = 'I H H'

    def __init__(self, buffer):
        super().__init__(buffer, self.data_format)

    @property
    def status_error(self):
        return self._unpack()[0]

    @status_error.setter
    def status_error(self, status_error):
        self._pack_into(status_error, 'I')

    @property
    def length(self):
        self._unpack()[1]

    @length.setter
    def length(self, length):
        self._pack_into(length, 'H', 'I')

    @property
    def vlan(self):
        return self.unpack()[2]

    @vlan.setter
    def vlan(self, vlan):
        self._pack_into(vlan, 'H', 'I H')


class RxDescriptorWriteback(IxgbeStruct):
    """ Advanced Descriptor writeback Sec. 7.1.6.2 """
    data_format = '{} {}'.format(RxDescriptorWritebackLower.data_format, RxDescriptorWritebackUpper.data_format)

    def __init__(self, buffer):
        super().__init__(buffer, self.data_format)
        self.lower = RxDescriptorWritebackLower(buffer[:RxDescriptorWritebackLower.byte_size()])
        self.upper = RxDescriptorWritebackUpper(buffer[RxDescriptorWritebackLower.byte_size():RxDescriptorWritebackUpper.byte_size()])


class RxDescriptor(IxgbeStruct):
    """Advanced Receive Descriptor Sec. 7.1.6"""
    data_format = '{} {}'.format(RxDescriptorRead.data_format, RxDescriptorWriteback.data_format)

    def __init__(self, buffer):
        super().__init__(buffer, self.data_format)
        self.read = RxDescriptorRead(buffer[:RxDescriptorRead.byte_size()])
        self.writeback = RxDescriptorWriteback(buffer[RxDescriptorRead.byte_size():RxDescriptorWriteback.byte_size()])
