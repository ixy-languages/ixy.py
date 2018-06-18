# import os
# from mmap import mmap, ACCESS_WRITE, PAGESIZE
#
# from ctypes import c_void_p, c_uint, sizeof, POINTER, cast, pointer
#
#
# class Buffer(object):
#     def __init__(self, memory):
#         self.memory = memory
#
#     def virtual_address(self):
#         return cast(pointer(c_uint.from_buffer(self.memory, 0)), c_void_p)
#
#     def physical_address(self):
#         with open('/proc/self/pagemap', 'r+b') as fd:
#             # lseek(fd, (uintptr_t) virt / pagesize * sizeof(uintptr_t), SEEK_SET)
#             print(self.virtual_address().value / PAGESIZE * sizeof(c_void_p))
#             fd.seek(int(self.virtual_address().value / PAGESIZE * sizeof(c_void_p)))
#             bytes_ = fd.read(sizeof(c_void_p))
#             print(bytes_)
#             phy = cast(pointer(c_uint.from_buffer(bytearray(bytes_), 0)), c_void_p)
#             return phy
#
#
# class Memory(object):
#     HUGE_PAGE_BITS = 21
#     HUGE_PAGE_SIZE = 1 << HUGE_PAGE_BITS
#     huge_pg_id = 0
#
#     def allocate_dma(self, mem_size, contiguous=True):
#         size = mem_size
#         if size % self.HUGE_PAGE_SIZE:
#             size = ((size >> self.HUGE_PAGE_BITS) + 1) << self.HUGE_PAGE_BITS
#         if contiguous and size > self.HUGE_PAGE_SIZE:
#             raise RuntimeError('could not map physically contiguous memory')
#         self.huge_pg_id += 1
#         huge_page_path = '/mnt/huge/ixy-{}-{}'.format(os.getpid(), self.huge_pg_id)
#         huge_page_fd = os.open(huge_page_path, os.O_RDWR | os.O_CREAT)
#         os.ftruncate(huge_page_fd, size)
#         return Buffer(mmap(huge_page_fd, os.stat(huge_page_path).st_size, access=ACCESS_WRITE))
#         # mlock necessary to prevent swaping NO Python support
