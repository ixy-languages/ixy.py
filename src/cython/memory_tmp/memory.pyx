from libc.stdint cimport uintptr_t, uint32_t
from libc.string cimport memset


cdef extern from "stdbool.h":
        ctypedef bint bool

cdef extern from "mem.h":
    struct dma_memory:
        void* virt
        uintptr_t phy

    struct mempool:
        void* base_addr
        uint32_t buff_size
        uint32_t num_entries
        uint32_t free_stack_top
        uint32_t* free_stack

    mempool* memory_allocate_mempool(uint32_t num_entries, uint32_t entry_size)
    dma_memory memory_allocate_dma(size_t size, bool require_contiguous)
    uintptr_t virt_to_phys(void* virt_addr)

cdef class Mempool:
    cdef mempool* _mempool

    def __cinit__(self, num_entries, entry_size):
        self._mempool = memory_allocate_mempool(num_entries, entry_size)

    def size(self):
        sizeof(mempool)


cdef class DmaMemory:
    cdef dma_memory _c_dma_memory

    def __cinit__(self, size, aligned=True):
        self._c_dma_memory = memory_allocate_dma(size, aligned)

    def phy(self):
        return self._c_dma_memory.phy

    def virt(self):
        return <uintptr_t> self._c_dma_memory.virt

    def set_to(self, value, int size):
      memset(self._c_dma_memory.virt, 0, size)



# def write_to_mem(char[::1] buff):
#   buff[50] = 44
#   print("{0:x}".format(<uintptr_t>&buff[0]))
#   print_address(&buff[0])
