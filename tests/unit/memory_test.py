from memory import DmaMemory


def test_memory():
    mem = DmaMemory()
    addr = buff.virt()
    # buff.memory[:5] = b'Hello'
    print(buff.phy())
    # ptr = pointer(addr)
    # for index, byte in enumerate(b'Hello'):
        # print(ptr[index])
