from ixypy.memory import Memory
from ctypes import *


def test_memory():
    mem = Memory()
    buff = mem.allocate_dma(5)
    addr = buff.virtual_address()
    buff.memory[:5] = b'Hello'
    print(buff.physical_address())
    ptr = pointer(addr)
    for index, byte in enumerate(b'Hello'):
        print(ptr[index])
