import struct
from unittest.mock import Mock

from ixypy.virtio.structures import VRing, VRingDescriptor, Available, RingList,\
                                    VRingUsedElement, VRingUsed, VirtioNetworkControl,\
                                    PromiscuousModeCommand

from ixypy.virtio.exception import VirtioException, BufferSizeException

import pytest


class TestVirtioNetworkControl(object):
    def test_write_net_ctrl_to_buffer(self):
        buffer = memoryview(bytearray(100))
        command = Mock()
        command_bytes = b'\xFF\xFF'
        command.__len__ = Mock(return_value=len(command_bytes))
        command.bytes = Mock(return_value=command_bytes)
        command.id = 1
        command.class_ = 2

        net_ctrl = VirtioNetworkControl(command)

        net_ctrl.to_buffer(buffer, 0)

        values = struct.unpack_from('B B B B', buffer, 0)

        assert values[0] == 2
        assert values[1] == 1
        assert values[2] == command_bytes[0]
        assert values[3] == command_bytes[1]

    def test_promisc_command(self):
        command = PromiscuousModeCommand()

        net_ctrl = VirtioNetworkControl(command)

        assert len(net_ctrl) == 4


class TestVRing(object):
    size = 256

    def test_size_calculation(self):
        assert VRing.byte_size(self.size) == 10244
        assert VRing.descriptor_table_size(self.size) == 4096
        assert VRing.available_queue_size(self.size) == 516
        assert VRing.used_queue_size(self.size) == 2052
        assert VRing.padding(self.size) == 3580

    def test_descriptors_creation(self):
        buff = memoryview(bytearray(VRing.byte_size(self.size)))

        vq = VRing(buff, self.size)

        assert len(vq.descriptors) == self.size

    def test_buffer_too_small(self):
        buff = memoryview(bytearray(VRing.byte_size(self.size) - 1))

        with pytest.raises(BufferSizeException):
            VRing(buff, self.size)


class TestVRingDescriptor(object):
    data_format = 'Q I H H'
    length = 120
    address = 1233
    flags = 99
    next_descriptor = 123

    def test_ring_descriptor_read(self):
        data = bytearray(struct.pack(self.data_format,
                                     self.address,
                                     self.length,
                                     self.flags,
                                     self.next_descriptor))

        descriptor = VRingDescriptor(memoryview(data))

        assert descriptor.length == self.length
        assert descriptor.address == self.address
        assert descriptor.flags == self.flags
        assert descriptor.next_descriptor == self.next_descriptor

    def test_ring_descriptor_write(self):
        data = bytearray(struct.pack(self.data_format, 0, 0, 0, 0))

        descriptor = VRingDescriptor(memoryview(data))
        descriptor.address = self.address
        descriptor.length = self.length
        descriptor.flags = self.flags
        descriptor.next_descriptor = self.next_descriptor

        values = struct.unpack(self.data_format, data)
        assert values[0] == self.address
        assert values[1] == self.length
        assert values[2] == self.flags
        assert values[3] == self.next_descriptor

    def test_create_descriptor(self):
        data = bytearray(struct.pack(self.data_format, 1, 1, 1, 1))

        VRingDescriptor.create_descriptor(memoryview(data))

        assert all(item == 0 for item in struct.unpack(self.data_format, data))


class TestRingList(object):
    def test_ring_list(self):
        ring_list_size = 10
        fmt = '{:d}H'.format(ring_list_size)
        ring_values = range(10)
        reversed_ring_values = ring_values[::-1]
        data = bytearray(struct.pack(fmt, *range(10)))

        ring_list = RingList(memoryview(data), ring_list_size)

        for i in range(10):
            assert ring_list[i] == i
        for i in range(10):
            ring_list[i] = reversed_ring_values[i]
            assert struct.unpack_from('H', data, self._offset(i))[0] == reversed_ring_values[i]

    @staticmethod
    def _offset(index):
        return struct.calcsize('{:d}H'.format(index))


class TestAvailable(object):
    size = 10
    data_format = 'H H {:d}H xx'.format(size)
    flags = 99
    index = 13
    rings = [i for i in range(size)]

    def test_ring_available_read(self):
        data = memoryview(bytearray(struct.calcsize(self.data_format)))

        vring_available = Available(data, self.size)

        data = struct.pack_into(self.data_format, data, 0, self.flags, self.index, *self.rings)

        assert vring_available.flags == self.flags
        assert vring_available.index == self.index
        for i, ring in enumerate(self.rings):
            assert vring_available.rings[i] == ring

    def test_ring_available_write(self):
        data = bytearray(struct.pack(self.data_format, 0, 0, *[0]*self.size))

        vring_available = Available(memoryview(data), self.size)

        vring_available.flags = self.flags
        vring_available.index = self.index
        for i in range(self.size):
            vring_available.rings[i] = self.rings[i]

        actual_values = struct.unpack(self.data_format, data)

        assert actual_values[0] == self.flags
        assert actual_values[1] == self.index
        for i, value in enumerate(actual_values[2:]):
            assert value == self.rings[i]


class TestVRingElementTest(object):
    data_format = 'H xx I'
    id = 15
    length = 55

    def test_used_element_read(self):
        data = bytearray(struct.pack(self.data_format, self.id, self.length))

        used_element = VRingUsedElement(memoryview(data))

        assert used_element.id == self.id
        assert used_element.length == self.length

    def test_used_element_write(self):
        data = bytearray(struct.pack(self.data_format, 0, 0))

        used_element = VRingUsedElement(memoryview(data))
        used_element.id = self.id
        used_element.length = self.length

        actual_values = struct.unpack(self.data_format, data)

        assert actual_values[0] == self.id
        assert actual_values[1] == self.length


class TestVRingUsed(object):
    size = 10
    flags = 234
    index = 55
    rings = [[1, 2]]*size
    used_elem_data_format = 'H xx I'
    data_format = 'H H {}'.format(' '.join([used_elem_data_format]*size))

    def test_ring_used_read(self):
        data = memoryview(bytearray(struct.calcsize(self.data_format)))

        vring_used = VRingUsed(data, self.size)

        struct.pack_into(self.data_format, data, 0, self.flags, self.index, *sum(self.rings, []))

        assert vring_used.flags == self.flags
        assert vring_used.index == self.index
        for i in range(self.size):
            assert vring_used.rings[i].id == self.rings[i][0]
            assert vring_used.rings[i].length == self.rings[i][1]

    def test_ring_used_write(self):
        data = bytearray(struct.pack(self.data_format, 0, 0, *[0, 0]*self.size))

        vring_used = VRingUsed(memoryview(data), self.size)
        vring_used.flags = self.flags
        vring_used.index = self.index
        for i, ring in enumerate(self.rings):
            vring_used.rings[i].id = ring[0]
            vring_used.rings[i].length = ring[1]

        actual_values = struct.unpack(self.data_format, data)
        actual_used_elements = [ring for ring in zip(actual_values[2::2], actual_values[3::2])]

        assert actual_values[0] == self.flags
        assert actual_values[1] == self.index
        for i, ring in enumerate(self.rings):
            assert actual_used_elements[i][0] == ring[0]
            assert actual_used_elements[i][1] == ring[1]
