import logging as log

from struct import Struct, calcsize, unpack_from, pack_into

from itertools import count
from memory import DmaMemory

HUGE_PAGE_BITS = 21
HUGE_PAGE_SIZE = 1 << HUGE_PAGE_BITS
SIZE_PKT_BUF_HEADROOM = 40


class Stack(object):
    def __init__(self, size):
        self.size = size
        self.top = 0
        self.items = [None]*size

    def push(self, item):
        if self.top < self.size:
            self.items[self.top - 1] = item
            self.top += 1
        else:
            raise MemoryError('Stack overflow')

    def pop(self):
        if self.top == 0:
            raise MemoryError('Empty stack')
        self.top -= 1
        return self.items[self.top]

    def __len__(self):
        return self.top


class Mempool(object):
    pools = {}

    def __init__(self, dma, buffer_size, num_entries):
        self.dma = dma
        self.buffer_size = buffer_size
        self.num_entries = num_entries
        self.identifier = None
        self._buffers = Stack(num_entries)
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

    def _gen_buffers(self, mem):
        i = 0
        while i < self.num_entries:
            offset = i*self.buffer_size
            physical_address = self.dma.get_physical_address(offset)
            buff = PacketBuffer(mem[offset:offset + self.buffer_size])
            buff.mempool_id = self.identifier
            buff.physical_address = physical_address
            buff.size = 0
            yield buff
            i += 1

    def preallocate_buffers(self):
        mem = memoryview(self.dma)
        for i, _ in enumerate(mem):
            mem[i] = 0x00
        for buff in self._gen_buffers(mem):
            self._buffers.push(buff)

    def get_buffer(self):
        if len(self._buffers) == 0:
            log.warning('No memory buffers left in pool %d', self.identifier)
        else:
            return self._buffers.pop()

    def get_buffers(self, num_buffers):
        num = num_buffers if num_buffers <= len(self._buffers) else len(self._buffers)
        return [self._buffers.pop() for _ in range(num)]

    def free_buffer(self, buffer):
        self._buffers.push(buffer)

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

pkt_dump_count = 0
class PacketBuffer(object):
    data_format = 'Q 8x I I 40x'
    data_offset = calcsize(data_format)
    head_room_offset = calcsize('Q 8x I I')
    struct = Struct(data_format)

    def __init__(self, buffer):
        self.buffer = buffer
        self.data_buffer = buffer[self.struct.size:]
        # data: Q 8x I I ==> 24
        self.head_room_buffer = buffer[self.head_room_offset:self.struct.size]

    def dump(self):
        global pkt_dump_count
        with open('dumps/buffs/buff_{:d}'.format(pkt_dump_count), 'wb') as f:
            f.write(self.buffer)
            pkt_dump_count += 1

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
        # return unpack_from('I', self.buffer, calcsize('Q 8x'))[0]

    @mempool_id.setter
    def mempool_id(self, mempool_id):
        # offset: Q 8x => 16
        pack_into('I', self.buffer, 16, mempool_id)
        # pack_into('I', self.buffer, calcsize('Q 8x'), mempool_id)

    @property
    def size(self):
        # offset: Q 8x I => 20
        return unpack_from('I', self.buffer, 20)[0]
        # return unpack_from('I', self.buffer, calcsize('Q 8x I'))[0]

    @size.setter
    def size(self, size):
        # offset: Q 8x I => 20
        pack_into('I', self.buffer, 20, size)
        # pack_into('I', self.buffer, calcsize('Q 8x I'), size)

    @property
    def data_addr(self):
        return self.physical_address + self.data_offset

    def touch(self):
        current_val = self.buffer[self.data_offset + 1]
        self.buffer[self.data_offset + 1] = (current_val + 1) % 0xFF

    def __str__(self):
        return 'PktBuff(phy_addr={:02X}, mempool_id={:d}, size={:d}, data_addr=0x{:02X})'.format(
            self.physical_address,
            self.mempool_id,
            self.size,
            self.data_addr
        )
