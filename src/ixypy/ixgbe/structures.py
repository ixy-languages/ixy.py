from struct import Struct, calcsize, pack_into, unpack_from


class Queue(object):
    def __init__(self, memory, num_descriptors, identifier):
        self.memory = memory
        self.num_descriptors = num_descriptors
        self.buffers = [None]*num_descriptors
        self.identifier = identifier
        self.index = 0

    def _get_descriptors(self, descriptor_class):
        desc_size = descriptor_class.byte_size()
        return [descriptor_class(self.memory[i*desc_size:desc_size*(i+1)]) for i in range(self.num_descriptors)]


class RxQueue(Queue):
    def __init__(self, num_descriptors, identifier, memory):
        super().__init__(memory, num_descriptors, identifier)
        self.descriptors = self._get_descriptors(RxDescriptor)


class TxQueue(Queue):
    def __init__(self, memory, num_descriptors, identifier):
        super().__init__(memory, num_descriptors, identifier)
        self.clean_index = 0
        self.descriptors = self._get_descriptors(TxDescriptor)


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
        self._pack_into(cmd_type_len, 'I', 'Q')

    @property
    def olinfo_status(self):
        return self._unpack()[2]

    @olinfo_status.setter
    def olinfo_status(self, olinfo_status):
        self._pack_into(olinfo_status, 'I', 'Q I')


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
        return self._unpack()[2]

    @status.setter
    def status(self, status):
        self._pack_into(status, 'H', 'Q H')


class TxDescriptor(IxgbeStruct):
    def __init__(self, buffer):
        self.read = TxDescriptorRead(buffer)
        self.writeback = TxDescriptorWriteback(buffer)

    @staticmethod
    def byte_size():
        return 16


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


class RxDescWbLoDwordHsRss(IxgbeStruct):
    data_format = 'H H'

    def __init__(self, buffer):
        super().__init__(buffer, self.data_format)

    @property
    def pkt_info(self):
        return self._unpack()[0]

    @pkt_info.setter
    def pkt_info(self, pkt_info):
        self._pack_into(pkt_info, 'H')

    @property
    def hdr_info(self):
        return self._unpack()[1]

    @hdr_info.setter
    def hdr_info(self, hdr_info):
        self._pack_into(hdr_info, 'H', 'H')


class RxDescWbLoDwordData(IxgbeStruct):
    data_format = 'I'

    def __init__(self, buffer):
        super().__init__(buffer, self.data_format)

    @property
    def data(self):
        return self._unpack()[0]

    @data.setter
    def data(self, data):
        self._pack_into(data, self.data_format)


class RxDescWbLoDword(object):
    def __init__(self, buffer):
        self.data = RxDescWbLoDwordData(buffer)
        self.hs_rss = RxDescWbLoDwordHsRss(buffer)

    @staticmethod
    def byte_size():
        return 4


class RxDescWbHiDwordRss(IxgbeStruct):
    data_format = 'I'

    def __init__(self, buffer):
        super().__init__(buffer, self.data_format)

    @property
    def rss(self):
        return self._unpack()[0]

    @rss.setter
    def rss(self, rss):
        self._pack_into(rss, self.data_format)


class RxDescWbHiDwordCsumIp(IxgbeStruct):
    data_format = 'H H'

    def __init__(self, buffer):
        super().__init__(buffer, self.data_format)

    @property
    def ip_id(self):
        return self._unpack()[0]

    @ip_id.setter
    def ip_id(self, ip_id):
        self._pack_into(ip_id, 'H')

    @property
    def csum(self):
        return self._unpack()[1]

    @csum.setter
    def csum(self, csum):
        self._pack_into(csum, 'H', 'H')


class RxDescWbHiDword(object):
    def __init__(self, buffer):
        self.rss = RxDescWbHiDwordRss(buffer)
        self.csum_ip = RxDescWbHiDwordCsumIp(buffer)

    @staticmethod
    def byte_size():
        return 4


class RxDescriptorWritebackLower(object):
    def __init__(self, buffer):
        self.lo_dword = RxDescWbLoDword(buffer[:RxDescWbLoDword.byte_size()])
        self.hi_dword = RxDescWbHiDword(buffer[RxDescWbLoDword.byte_size():])

    @staticmethod
    def byte_size():
        return RxDescWbLoDword.byte_size()


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


class RxDescriptorWriteback(object):
    """ Advanced Descriptor writeback Sec. 7.1.6.2 """
    def __init__(self, buffer):
        self.lower = RxDescriptorWritebackLower(buffer[:RxDescriptorWritebackLower.byte_size()])
        self.upper = RxDescriptorWritebackUpper(buffer[RxDescriptorWritebackLower.byte_size():RxDescriptorWritebackUpper.byte_size()])


class RxDescriptor(object):
    """Advanced Receive Descriptor Sec. 7.1.6"""
    def __init__(self, buffer):
        self.read = RxDescriptorRead(buffer)
        self.writeback = RxDescriptorWriteback(buffer)

    @staticmethod
    def byte_size():
        return 16
