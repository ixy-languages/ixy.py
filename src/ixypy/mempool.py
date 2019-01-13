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
        self.items[self.top] = item
        self.top += 1

    def pop(self):
        self.top -= 1
        return self.items[self.top]

    def __len__(self):
        return self.top


class Mempool(object):
    pools = {}

    def __init__(self, dma, buffer_size, num_entries):
        self.dma = dma
        self.mem = memoryview(self.dma)
        for i, _ in enumerate(self.mem):
            self.mem[i] = 0x0
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

    def _gen_buffers(self):
        base_phy_address = self.dma.physical_address
        for i in range(self.num_entries):
            offset = i*self.buffer_size
            buff = PacketBuffer(self.mem[offset:offset + self.buffer_size])
            buff.mempool_id = self.identifier
            buff.physical_address = base_phy_address + offset
            buff.size = 0
            yield buff

    def preallocate_buffers(self):
        for buff in self._gen_buffers():
            self._buffers.push(buff)

    def get_buffer(self):
        try:
            return self._buffers.pop()
        except IndexError:
            log.exception('No memory buffers left in pool %d', self.identifier)

    def get_buffers(self, num_buffers):
        num = num_buffers if num_buffers <= len(self._buffers) else len(self._buffers)
        return [self._buffers.pop() for _ in range(num)]

    def free_buffer(self, buff):
        self._buffers.push(buff)
    
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
    data_offset = calcsize(data_format)
    head_room_offset = calcsize('Q 8x I I')
    struct = Struct(data_format)

    def __init__(self, buffer):
        self.buffer = buffer
        self.data_buffer = buffer[self.struct.size:]
        # data: Q 8x I I ==> 24
        self.head_room_buffer = buffer[self.head_room_offset:self.struct.size]

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

    def unpack(self):
        """
        Unpacking the whole structure is faster than one by one
        physical address
        data address
        memory pool id
        size
        """
        unpacked = self.struct.unpack_from(self.buffer)
        return unpacked[0], unpacked[0] + self.data_offset, unpacked[1], unpacked[2]

    @property
    def data_addr(self):
        return self.physical_address + self.data_offset

    def touch(self):
        current_val = self.buffer[48]
        self.buffer[48] = (current_val + 1) % 0xFF

    def __repr__(self):
        return str(self)

    def __str__(self):
        return 'PktBuff(phy_addr={:02X}, mempool_id={:d}, size={:d}, data_addr=0x{:02X})'.format(
            self.physical_address,
            self.mempool_id,
            self.size,
            self.data_addr
        )
