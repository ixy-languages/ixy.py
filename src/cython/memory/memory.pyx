from libc.stdint cimport uintptr_t, uint32_t, uint8_t, uint16_t, uint64_t
from libc.string cimport memset, memcpy
from libc.stdlib cimport malloc, free
from posix.unistd cimport close, read, off_t
from cpython cimport Py_buffer

import os
import stat
import resource
import array

DEF HUGE_PAGE_BITS = 21
DEF HUGE_PAGE_SIZE = 1 << HUGE_PAGE_BITS
DEF SIZE_PKT_BUF_HEADROOM = 40


cdef uint32_t huge_pg_id = 0

cdef uintptr_t virt_to_phys(void* virt):
  cdef long pagesize = <long>resource.getpagesize()
  # check error
  fd = os.open("/proc/self/pagemap", os.O_RDONLY)

  cdef uintptr_t offset = <uintptr_t> virt / pagesize * sizeof(uintptr_t)
  # check error
  os.lseek(fd, offset, os.SEEK_SET)
  # check error
  cdef uintptr_t phy = <uintptr_t>(array.array('Q', os.read(fd, sizeof(phy)))[0])
  os.close(fd)
  return (phy & 0x7fffffffffffffULL) * pagesize + (<uintptr_t>virt) % pagesize


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
    self.shape[0] = self.size
    self.strides[0] = 1
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
    memset(self.virtual_address, 0xab, self.size)
    os.close(fd)
    os.unlink(path)
    self.physical_address = virt_to_phys(self.virtual_address)

  def __getbuffer__(self, Py_buffer *buffer, int flags):
    cdef Py_ssize_t itemsize = 1
    buffer.buf = <char *>self.virtual_address
    buffer.format = 'B'
    buffer.internal = NULL
    buffer.itemsize = itemsize
    buffer.len = self.size
    buffer.ndim = 1
    buffer.obj = self
    buffer.readonly = 0
    buffer.shape = self.shape
    buffer.strides = self.strides
    buffer.suboffsets = NULL

  def get_physical_address(self, uint64_t offset):
    return virt_to_phys(self.virtual_address + offset)

  def __str__(self):
    return 'DmaMemory(vaddr=0x{:02X}, phyaddr=0x{:02X}, size={:d})'.format(<uintptr_t>self.virtual_address, self.physical_address, self.size)

  @staticmethod
  cdef uint32_t _round_size(uint32_t size):
    """
    round up to multiples of 2 MB if necessary, this is the wasteful part
    """
    if size % HUGE_PAGE_SIZE != 0:
      return ((size >> HUGE_PAGE_BITS) + 1) << HUGE_PAGE_BITS
    return size
