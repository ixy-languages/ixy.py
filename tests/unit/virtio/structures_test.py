import struct

from ixypy.virtio.structures import VQueueDescriptor, VQueueAvailable, RingList, \
                                    VQueueUsedElement, VQueueUsed


class TestVQueueDescriptor(object):
    data_format = 'Q I H H'
    length = 120
    address = 1233
    flags = 99
    next_descriptor = 123

    def test_queue_descriptor_read(self):
        data = bytearray(struct.pack(self.data_format,
                                     self.address,
                                     self.length,
                                     self.flags,
                                     self.next_descriptor))

        descriptor = VQueueDescriptor(memoryview(data))

        assert descriptor.length == self.length
        assert descriptor.address == self.address
        assert descriptor.flags == self.flags
        assert descriptor.next_descriptor == self.next_descriptor

    def test_queue_descriptor_write(self):
        data = bytearray(struct.pack(self.data_format, 0, 0, 0, 0))

        descriptor = VQueueDescriptor(memoryview(data))
        descriptor.address = self.address
        descriptor.length = self.length
        descriptor.flags = self.flags
        descriptor.next_descriptor = self.next_descriptor

        values = struct.unpack(self.data_format, data)
        assert values[0] == self.address
        assert values[1] == self.length
        assert values[2] == self.flags
        assert values[3] == self.next_descriptor


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
            print(struct.unpack_from('10H', data, 0))
            assert struct.unpack_from('H', data, self._offset(i))[0] == reversed_ring_values[i]

    @staticmethod
    def _offset(index):
        return struct.calcsize('{:d}H'.format(index))


class TestVQueueAvailable(object):
    size = 10
    data_format = 'H H {:d}H xx'.format(size)
    flags = 99
    index = 13
    rings = [i for i in range(size)]

    def test_queue_available_read(self):
        data = bytearray(struct.pack(self.data_format, self.flags, self.index, *self.rings))

        queue_available = VQueueAvailable(memoryview(data), self.size)

        assert queue_available.flags == self.flags
        assert queue_available.index == self.index
        for i, ring in enumerate(self.rings):
            assert queue_available.rings[i] == ring

    def test_queue_available_write(self):
        data = bytearray(struct.pack(self.data_format, 0, 0, *[0]*self.size))

        queue_available = VQueueAvailable(memoryview(data), self.size)

        queue_available.flags = self.flags
        queue_available.index = self.index
        for i in range(self.size):
            queue_available.rings[i] = self.rings[i]

        actual_values = struct.unpack(self.data_format, data)

        assert actual_values[0] == self.flags
        assert actual_values[1] == self.index
        for i, value in enumerate(actual_values[2:]):
            assert value == self.rings[i]


class TestVUsedElementTest(object):
    data_format = 'H xx I'
    id = 15
    length = 55

    def test_used_element_read(self):
        data = bytearray(struct.pack(self.data_format, self.id, self.length))

        used_element = VQueueUsedElement(memoryview(data))

        assert used_element.id == self.id
        assert used_element.length == self.length

    def test_used_element_write(self):
        data = bytearray(struct.pack(self.data_format, 0, 0))

        used_element = VQueueUsedElement(memoryview(data))
        used_element.id = self.id
        used_element.length = self.length

        actual_values = struct.unpack(self.data_format, data)

        assert actual_values[0] == self.id
        assert actual_values[1] == self.length


class TestVQueueUsed(object):
    pass
