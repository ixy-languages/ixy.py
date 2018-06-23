from memory import DmaMemory


def test_memory():
    mem = DmaMemory()
    addr = mem.virt()
    # buff.memory[:5] = b'Hello'
    print(mem.phy())
    # ptr = pointer(addr)
    # for index, byte in enumerate(b'Hello'):
        # print(ptr[index])
