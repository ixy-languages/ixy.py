import mmap
from unittest.mock import Mock
from struct import unpack_from, pack_into

import pytest

from ixypy.register import Register, MmapRegister


class MockRegister(Register):

    def __init__(self):
        self.mock = Mock()

    def set(self, offset, value, length):
        self.mock.set(offset, value, length)

    def get(self, length, offset):
        return self.mock.get(offset, length)


@pytest.mark.parametrize("length", [0, 8, 16, 32])
def test_set(length):
    # given
    register = MockRegister()

    # when
    getattr(register, 'set{}'.format(length))(value=5, offset=5)

    # then
    register.mock.set.assert_called_with(5, 5, length//8)


@pytest.mark.parametrize("length", [0, 8, 16, 32])
def test_get(length):
    # given
    register = MockRegister()
    mock_attrs = {'get.return_value': 55}
    register.mock.configure_mock(**mock_attrs)

    # when
    result = getattr(register, 'get{}'.format(length))(offset=5)

    # then
    register.mock.get.assert_called_with(5, length//8)
    assert result == 55


def test_invalid_length():
    register = MockRegister()

    with pytest.raises(ValueError):
        register.set15(value=5, offset=5)


def test_invalid_operation():
    register = MockRegister()

    with pytest.raises(AttributeError):
        register.append16(value=5, offset=3)


def get_mem(tmp_dir):
    tmp_file = tmp_dir.join('register')
    tmp_file.write('0'*100)
    fd = tmp_file.open(mode='r+b')
    mem = memoryview(mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_WRITE))
    mem[:] = bytearray(len(mem))
    return mem, fd


def read32(fd, offset):
    mem = memoryview(mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_WRITE))
    return unpack_from('I', mem, offset)[0]


def test_set_mmap_register(tmpdir):
    # given
    mem, fd = get_mem(tmpdir)
    reg = MmapRegister(mem)

    # when
    value = 0xFFACBEFF
    reg.set(0, value)
    reg.wait_set(0, value)

    # then
    assert read32(fd, 0) == value


def test_set_flags(tmpdir):
    # given
    mem, fd = get_mem(tmpdir)
    reg = MmapRegister(mem)
    already_set = 0xAAAABBBB
    pack_into('I', mem, 10, already_set)
    offset = 10

    # when
    reg.set_flags(offset, 0x0000FFFF)

    # then
    assert unpack_from('I', mem, offset)[0] == 0xAAAAFFFF


def test_clear_flags(tmpdir):
    # given
    mem, fd = get_mem(tmpdir)
    reg = MmapRegister(mem)
    offset = 25
    mask = 0x0000FFFF

    # when
    reg.clear_flags(offset, mask)
    reg.wait_clear(offset, mask)

    # then
    assert unpack_from('I', mem, offset)[0] & mask == 0
