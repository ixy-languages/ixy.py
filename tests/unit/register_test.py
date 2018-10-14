from unittest.mock import Mock

import pytest

from ixypy.register import Register


class MockRegister(Register):

    def __init__(self):
        self.mock = Mock()

    def write(self, value, offset, length):
        self.mock.write(value, offset, length)

    def read(self, length, offset):
        return self.mock.read(offset, length)


@pytest.mark.parametrize("length", [0, 8, 16, 32])
def test_write(length):
    # given
    register = MockRegister()

    # when
    getattr(register, 'write{}'.format(length))(value=5, offset=5)

    # then
    register.mock.write.assert_called_with(5, 5, length//8)


@pytest.mark.parametrize("length", [0, 8, 16, 32])
def test_read(length):
    # given
    register = MockRegister()
    mock_attrs = {'read.return_value': 55}
    register.mock.configure_mock(**mock_attrs)

    # when
    result = getattr(register, 'read{}'.format(length))(offset=5)

    # then
    register.mock.read.assert_called_with(5, length//8)
    assert result == 55


def test_invalid_length():
    register = MockRegister()

    with pytest.raises(ValueError):
        register.write15(value=5, offset=5)


def test_invalid_operation():
    register = MockRegister()

    with pytest.raises(AttributeError):
        register.append16(value=5, offset=3)
