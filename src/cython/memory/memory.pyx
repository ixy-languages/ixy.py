from libc.stdint cimport uintptr_t


cdef extern from "stdbool.h":
        ctypedef bint bool

cdef extern from "mem.h":
    struct dma_memory:
        void* virt
        uintptr_t phy

    dma_memory memory_allocate_dma(size_t size, bool require_contiguous)

cdef class DmaMemory:
    cdef dma_memory _c_dma_memory

    def __cinit__(self):
        self._c_dma_memory = memory_allocate_dma(32, True)

    def phy(self):
        return self._c_dma_memory.phy

    def virt(self):
        return <uintptr_t> self._c_dma_memory.virt
