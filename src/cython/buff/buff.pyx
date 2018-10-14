from libc.stdlib cimport malloc, free
from cpython cimport Py_buffer

cdef class Buff:
  cdef void* buf
  cdef Py_ssize_t shape[1]
  cdef Py_ssize_t strides[1]
  cdef Py_ssize_t size

  def __cinit__(self, size_t size):
    self.size = size
    self.buf = <void*>malloc(size)

  def __getbuffer__(self, Py_buffer *buffer, int flags):
    cdef Py_ssize_t itemsize = 1
    self.shape[0] = self.size
    self.strides[0] = 1
    buffer.buf = <char *>self.buf
    buffer.format = 'B'                     # float
    buffer.internal = NULL                  # see References
    buffer.itemsize = itemsize
    buffer.len = self.size  # product(shape) * itemsize
    buffer.ndim = 1
    buffer.obj = self
    buffer.readonly = 0
    buffer.shape = self.shape
    buffer.strides = self.strides
    buffer.suboffsets = NULL                # for pointer arrays only


  def __str__(self):
    cdef char[:] mem = <char[:self.size]>self.buf
    return ' '.join(['0x{:02x}'.format(b) for b in mem])

  def __dealloc__(self):
    free(self.buf)
