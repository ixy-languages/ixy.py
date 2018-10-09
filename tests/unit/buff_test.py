from buff import Buff


def test_buff():
    buf = Buff(5)
    mem_view = memoryview(buf)
    mem_view[-1] = 0x0F
    print(buf)
