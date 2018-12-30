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
            buffer.mempool_id = self.identifier
            buffer.physical_address = physical_address
            buffer.size = 0
            self._buffers.append(buffer)

    def get_buffer(self):
        if not self._buffers:
            log.warning('No memory buffers left')
        return self._buffers.pop()

    def get_buffers(self, num_buffers):
        num = num_buffers if num_buffers <= len(self._buffers) else len(self._buffers)
        return [self.get_buffer() for _ in range(num)]

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
    data_offset = 64

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
    def mempool_id(self):
        # offset: Q 8x => 16
        return unpack_from('I', self.buffer, 16)[0]

    @mempool_id.setter
    def mempool_id(self, mempool_id):
        # offset: Q 8x => 16
        pack_into('I', self.buffer, 16, mempool_id)

    @property
    def size(self):
        # offset: Q 8x I => 20
        return unpack_from('I', self.buffer, 20)[0]

    @size.setter
    def size(self, size):
        # offset: Q 8x I => 20
        pack_into('I', self.buffer, 20, size)

#     @property
    # def data_offset(self):
        # # return calcsize(self.data_format)
        # return 64

    def __str__(self):
        return 'PktBuff(phy_addr={:02X}, mempool_id={:d}, size={:d})'.format(
            self.physical_address,
            self.mempool_id,
            self.size)
