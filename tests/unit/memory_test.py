import pytest

from memory2 import DmaMemory, Mempool, PktBuf


# def test_should_fail_when_no_contiguous_memory_available():
#     with pytest.raises(MemoryError):
#         DmaMemory(9999999, True)
#
#
# def test_mempool():
#     mem = Mempool(5)
#
#     PktBuf(mem)
