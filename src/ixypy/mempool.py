import logging as log

from struct import Struct, calcsize, unpack_from, pack_into

from itertools import count
from memory import DmaMemory

HUGE_PAGE_BITS = 21
HUGE_PAGE_SIZE = 1 << HUGE_PAGE_BITS
SIZE_PKT_BUF_HEADROOM = 40


class Mempool(object):
    pools = {}

    def __init__(self, dma, buffer_size, num_entries):
        self.dma = dma
        self.buffer_size = buffer_size
        self.num_entries = num_entries
        self.identifier = None
        self._buffers = []
        self.add_pool(self)

    @property
    def id(self):
        return self.identifier

    @id.setter
    def id(self, identifier):
        if identifier in Mempool.pools:
            raise ValueError('The id: {} already assigned'.format(identifier))
        self.identifier = identifier

    def free(self):
        del Mempool.pools[self.identifier]

    def preallocate_buffers(self):
        mem = memoryview(self.dma)
        for i in range(self.num_entries):
            offset = i*self.buffer_size
            physical_address = self.dma.get_physical_address(offset)
            buffer = PacketBuffer(mem[offset:offset + self.buffer_size])
            buffer.memopool_id = self.identifier
            buffer.physical_address = physical_address
            buffer.size = 0
            self._buffers.append(buffer)

    def get_buffer(self):
        if not self._buffers:
            log.warning('No memory buffers left')
        return self._buffers.pop()

    def free_buffer(self, buffer):
        self._buffers.append(buffer)

    @staticmethod
    def add_pool(mempool):
        mempool.id = Mempool.get_identifier()
        Mempool.pools[mempool.id] = mempool

    @staticmethod
    def get_identifier():
        for i in count(1):
            if i not in Mempool.pools:
                return i

    @staticmethod
    def allocate(num_entries, entry_size=2048):
        if HUGE_PAGE_SIZE % entry_size != 0:
            raise ValueError('entry size[{}] must be a divisor of the huge page size[{}]'.format(entry_size, HUGE_PAGE_SIZE))
        dma = DmaMemory(num_entries*entry_size, False)
        mempool = Mempool(dma, entry_size, num_entries)
        mempool.preallocate_buffers()
        return mempool


class PacketBuffer(object):
    data_format = 'Q 8x I I 40x'

    def __init__(self, buffer):
        self.buffer = buffer
        self.struct = Struct(self.data_format)
        self.data_buffer = buffer[self.struct.size:]
        self.head_room_buffer = buffer[calcsize('Q 8x I I'):self.struct.size]

    @property
    def physical_address(self):
        return unpack_from('Q', self.buffer, 0)[0]

    @physical_address.setter
    def physical_address(self, phyaddr):
        pack_into('Q', self.buffer, 0, phyaddr)

    @property
    def memopool_id(self):
        return unpack_from('I', self.buffer, calcsize('Q 8x'))[0]

    @memopool_id.setter
    def memopool_id(self, mempool_id):
        pack_into('I', self.buffer, calcsize('Q 8x'), mempool_id)

    @property
    def size(self):
        return unpack_from('I', self.buffer, calcsize('Q 8x I'))[0]

    @size.setter
    def size(self, size):
        pack_into('I', self.buffer, calcsize('Q 8x I'), size)

    @property
    def data_offset(self):
        return calcsize(self.data_format)