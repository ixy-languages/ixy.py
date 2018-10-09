from libc.stdint cimport uintptr_t, uint32_t, uint8_t, uint16_t, uint64_t
from libc.string cimport memset, memcpy
from libc.stdlib cimport malloc, free
from posix.unistd cimport close, read, off_t
from cpython cimport Py_buffer

import os
import stat
import resource

DEF HUGE_PAGE_BITS = 21
DEF HUGE_PAGE_SIZE = 1 << HUGE_PAGE_BITS
DEF SIZE_PKT_BUF_HEADROOM = 40


cdef extern from "mem.h":
    uintptr_t virt_to_phys(void* virt_addr)

# static fields not supported in cython, therefore module lvl variable is used
cdef uint32_t huge_pg_id = 0


cdef extern from "sys/mman.h":
    void *mmap(void *addr, size_t len, int prot, int flags, int fd, off_t offset)
    enum:
        PROT_READ
        PROT_WRITE
        MAP_SHARED
        MAP_HUGETLB

cdef class DmaMemory:
  cdef void* virtual_address
  cdef readonly uintptr_t physical_address
  cdef Py_ssize_t size
  cdef Py_ssize_t shape[1]
  cdef Py_ssize_t strides[1]



  def __cinit__(self, uint32_t size, bint aligned=True):
    self.size = <Py_ssize_t>size
    actual_size = DmaMemory._round_size(size)
    if aligned and actual_size > HUGE_PAGE_SIZE:
      raise MemoryError()
    global huge_pg_id
    # This is atomic thanks to the GIL
    huge_pg_id += 1
    page_id = huge_pg_id
    path = "/mnt/huge/ixypy-{:d}-{:d}".format(page_id, os.getpid())
    fd = os.open(path, os.O_CREAT | os.O_RDWR, stat.S_IRWXU)
    # check error
    self.virtual_address = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_HUGETLB, fd, 0)
    os.close(fd)
    os.unlink(path)
    self.physical_address = virt_to_phys(self.virtual_address)

  def __getbuffer__(self, Py_buffer *buffer, int flags):
    cdef Py_ssize_t itemsize = 1
    self.shape[0] = self.size
    self.strides[0] = 1
    buffer.buf = <char *>self.virtual_address
    buffer.format = 'B'                     # float
    buffer.internal = NULL                  # see References
    buffer.itemsize = itemsize
    buffer.len = self.size  # product(shape) * itemsize
    buffer.ndim = 1
    buffer.obj = self
    buffer.readonly = 0
    buffer.shape = self.shape
    buffer.strides = self.strides
    buffer.suboffsets = NULL

  def __str__(self):
    return 'VAddr={} PAddr={} size={}'.format(<uintptr_t>self.virtual_address, self.physical_address, self.size)

  def set_to(self, int value):
    memset(self.virtual_address, value, self.size)

  @staticmethod
  cdef uintptr_t virt_to_phys(void* virt):
    cdef uintptr_t* phy = NULL
    cdef long pagesize = <long>resource.getpagesize()
    # check error
    fd = os.open("/proc/self/pagemap", os.O_RDONLY)
    cdef uintptr_t offset = <uintptr_t> virt / pagesize * sizeof(uintptr_t)
    # check error
    os.lseek(fd, offset, os.SEEK_SET)
    # check error
    cdef bytearray data = bytearray(os.read(fd, sizeof(phy)))
    os.close(fd)
    phy = <uintptr_t *>&data[0]
    return (phy[0]&0x7fffffffffffffULL) * pagesize + (<uintptr_t>virt) % pagesize

  @staticmethod
  cdef uint32_t _round_size(uint32_t size):
    """
    round up to multiples of 2 MB if necessary, this is the wasteful part
    """
    if size % HUGE_PAGE_SIZE != 0:
      return ((size >> HUGE_PAGE_BITS) + 1) << HUGE_PAGE_BITS
    return size

  # cdef buf(self):
  #   return <char[:self.size]>self.virtual_address


# everything here contains virtual addresses, the mapping to physical addresses are in the pkt_buf
cdef struct mempool:
  void* base_addr
  uint32_t buff_size
  uint32_t num_entries
  # memory is managed via a simple stack
  # replacing this with a lock-free queue (or stack) makes this thread-safe
  uint32_t free_stack_top
  uint32_t* free_stack

cdef struct pkt_buf:
  uintptr_t buf_addr_phy
  mempool* mempool
  uint32_t mempool_idx
  uint32_t size
  uint8_t head_room[SIZE_PKT_BUF_HEADROOM]
  uint8_t* data


cdef class PktBuf:
  cdef pkt_buf* buf

  def __cinit__(self, Mempool mempool):
    self.buf = mempool.allocate_buffer()

  def to_buff(self, char* data):
    memcpy(self.buf.data, data, len(data))


cdef class Mempool:
  cdef mempool* mempool

  def __cinit__(self, uint32_t num_entries, uint32_t entry_size=2048):
    # cdef pkt_buf* buf = NULL
    # cdef mempool* pool = NULL
    if HUGE_PAGE_SIZE % entry_size:
      raise MemoryError('Entry size must be a divisor of the huge page size ({})'.format(HUGE_PAGE_SIZE))
    self.mempool = <mempool*>malloc(sizeof(mempool))
    self.mempool.free_stack = <uint32_t*>malloc(num_entries * sizeof(uint32_t))
    if not self.mempool:
      raise MemoryError()
    cdef DmaMemory dma = DmaMemory(num_entries * entry_size, False)
    self.mempool.num_entries = num_entries
    self.mempool.buff_size = entry_size
    self.mempool.base_addr = dma.virtual_address
    self.mempool.free_stack_top = num_entries
    for i in range(num_entries):
      self.mempool.free_stack[i] = i
      # buffer allocation
      buf_address = <uint8_t*>self.mempool.base_addr
      buf = <pkt_buf*>&buf_address[i * entry_size]
      buf.buf_addr_phy = DmaMemory.virt_to_phys(buf)
      buf.mempool_idx = i
      buf.mempool = self.mempool
      buf.size = 0

  def __dealloc__(self):
    free(self.mempool)

  cdef pkt_buf* allocate_buffers(self, num_buffers):
    cdef pkt_buf* buffs
    for i in range(num_buffers):
      buf = &buffs[i]
      buf = self.allocate_buffer()
    return buffs

  cdef pkt_buf* allocate_buffer(self):
    if self.mempool.free_stack_top == 0:
      raise MemoryError('No space available on the mempool')
    entry_id = self.mempool.free_stack[self.mempool.free_stack_top]
    self.mempool.free_stack_top = self.mempool.free_stack_top - 1
    pool = <uint8_t*>self.mempool.base_addr
    return <pkt_buf*>&pool[entry_id * self.mempool.buff_size]
