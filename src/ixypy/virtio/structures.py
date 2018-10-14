import logging as log
from struct import Struct, calcsize, pack, pack_into, unpack_from
from collections import OrderedDict
from ixypy.virtio_type import VRING_AVAIL_F_NO_INTERRUPT

MAX_QUEUE_SIZE = 32768


class Queue(object):
    def __init__(self, vqueue, notification_offset, mempool=None, used_last_index=0):
        self.mempool = mempool
        self.vqueue = vqueue
        self.notification_offset = notification_offset
        self.used_last_index = used_last_index
        self.virtual_addresses = [0]*vqueue.size

    def disable_interrupts(self):
        self.vqueue.available.flags = VRING_AVAIL_F_NO_INTERRUPT
        self.vqueue.used.flags = 0

    def get_free_descriptor(self):
        for index, descriptor in enumerate(self.vqueue.descriptors):
            if descriptor.address() == 0:
                return index, descriptor
        raise ValueError('Queue is full')


class VNetworkControlHeader(object):
    fmt = 'B B'

    def __init__(self, class_, cmd):
        self.struct = Struct(self.fmt)
        self.class_ = class_
        self.cmd = cmd

    def __len__(self):
        return calcsize(self.fmt)


class VCommand(object):
    def __init__(self, header, on):
        self.header = header
        self.on = on

    def to_bytes(self):
        return pack('{} B'.format(self.header.fmt), self.header.class_, self.header.cmd, self.on)

    def __len__(self):
        return calcsize('{} B'.format(self.header.fmt))


class VRing(object):
    def __init__(self, size, buffer, alignment=4096):
        if size > MAX_QUEUE_SIZE:
            raise ValueError("Size exceeded maximum size")
        self.size = size
        self.buffer = buffer
        self.alignment = alignment
        self.descriptors = self._descriptors()
        self.available = self._available()
        self.used = self._used()

    def _descriptors(self):
        item_size = VQueueDescriptor.byte_size()
        descriptor_tbl_size = VRing.descriptor_table_size(self.size)
        sub_buff = self.buffer[:descriptor_tbl_size]
        return [VQueueDescriptor(sub_buff[i*item_size:item_size*(i+1)]) for i in range(len(self))]

    def _available(self):
        descriptor_tbl_size = VRing.descriptor_table_size(self.size)
        available_queue_size = VRing.available_queue_size(self.size)
        sub_buff = self.buffer[descriptor_tbl_size:(descriptor_tbl_size + available_queue_size)]
        return VQueueAvailable(sub_buff, self.size)

    def _used(self):
        buffer_start = len(self) - VRing.used_queue_size(self.size)
        sub_buff = self.buffer[buffer_start:len(self)]
        return VQueueUsed(sub_buff, self.size)

    def __len__(self):
        return VRing.byte_size(self.size, self.alignment)

    @staticmethod
    def used_queue_size(size):
        return 6 + VQueueUsedElement.byte_size() * size

    @staticmethod
    def descriptor_table_size(size):
        return VQueueDescriptor.byte_size() * size

    @staticmethod
    def available_queue_size(size):
        return 6 + 2 * size

    @staticmethod
    def padding(size, alignment):
        total_qsz = VRing.byte_size(size, alignment)
        dsc_tbl_sz = VRing.descriptor_table_size(size)
        avail_qsz = VRing.available_queue_size(size)
        used_qsz = VRing.used_queue_size(size)
        return total_qsz - (dsc_tbl_sz + avail_qsz + used_qsz)

    @staticmethod
    def align(val, alignment):
        return (val + alignment) & ~alignment

    @staticmethod
    def byte_size(max_queue_size, alignment=4096):
        dsc_tbl_sz = VRing.descriptor_table_size(max_queue_size)
        avail_qsz = VRing.available_queue_size(max_queue_size)
        used_qsz = VRing.used_queue_size(max_queue_size)
        return VRing.align(dsc_tbl_sz + avail_qsz, alignment)+VRing.align(used_qsz, alignment)


class VQueueDescriptor(object):
    data_format = OrderedDict({
        'address': 'Q',
        'length': 'I',
        'flags': 'H',
        'next': 'H'
    })

    def __init__(self, buffer):
        self.struct = Struct(self.format())
        self.buffer = buffer

    @property
    def address(self):
        return self._unpack()[0]

    @address.setter
    def address(self, address):
        self._pack_into_buffer(value=address, field='address')

    @property
    def length(self):
        return self._unpack()[1]

    @length.setter
    def length(self, length):
        self._pack_into_buffer(length, prefix='Q', field='length')

    @property
    def flags(self):
        return self._unpack()[2]

    @flags.setter
    def flags(self, flags):
        self._pack_into_buffer(value=flags, prefix='Q I', field='flags')

    @property
    def next_descriptor(self):
        return self._unpack()[3]

    @next_descriptor.setter
    def next_descriptor(self, next_descriptor):
        self._pack_into_buffer(value=next_descriptor, prefix='Q I H', field='next')

    def reset(self):
        self.write(0, 0, 0, 0)

    def write(self, length, addr, flags, next_descriptor):
        self.struct.pack_into(self.buffer, 0, length, addr, flags, next_descriptor)

    def _pack_into_buffer(self, value, field, prefix=''):
        field_format = self.data_format[field]
        offset = calcsize(prefix)
        pack_into(field_format, self.buffer, offset, value)

    @staticmethod
    def format():
        return ' '.join([item for _, item in VQueueDescriptor.data_format.items()])

    @staticmethod
    def byte_size():
        return calcsize(VQueueDescriptor.format())

    def _unpack(self):
        return self.struct.unpack(self.buffer)


class VQueueAvailable(object):
    format = 'H H'

    def __init__(self, buffer, size):
        self.size = size
        self.struct = Struct(VQueueAvailable.format.format(size))
        self.buffer = buffer[:self.struct.size]
        self.rings = RingList(buffer[self.struct.size:-2], size)

    @property
    def flags(self):
        return self._unpack()[0]

    @flags.setter
    def flags(self, flags):
        self._pack_into_buffer(flags, 'H')

    @property
    def index(self):
        return self._unpack()[1]

    @index.setter
    def index(self, index):
        self._pack_into_buffer(index, 'H', 'H')

    @staticmethod
    def byte_size(queue_size):
        """
         H H + queue_sizeH(RingList) + xx
         uint16_t avail_flags;
         uint16_t avail_idx;
         uint16_t available[num];
         uint16_t used_event_idx;
        """
        return calcsize(VQueueAvailable.format.format(queue_size)) + queue_size * 2 + 2

    def __str__(self):
        return 'size={} buffer_size={}'.format(self.size, len(self.buffer))

    def _unpack(self):
        return self.struct.unpack(self.buffer)

    def _pack_into_buffer(self, value, field_format, prefix=''):
        offset = calcsize(prefix)
        pack_into(field_format, self.buffer, offset, value)


class RingList(object):
    def __init__(self, buffer, size):
        self.struct = Struct('{:d}H'.format(size))
        self.buffer = buffer
        self.size = size

    def __getitem__(self, index):
        return unpack_from('H', self.buffer, self._get_offset(index))[0]

    def __setitem__(self, index, value):
        pack_into('H', self.buffer, self._get_offset(index), value)

    @staticmethod
    def _get_offset(index):
        return calcsize('{:d}H'.format(index))


class VQueueUsedElement(object):
    format = 'H x x I'

    def __init__(self, buffer):
        self.buffer = buffer
        self.struct = Struct(VQueueUsedElement.format)

    @property
    def id(self):
        return self._unpack()[0]

    @id.setter
    def id(self, _id):
        self._pack_into_buffer(_id, 'H')

    @property
    def length(self):
        return self._unpack()[1]

    @length.setter
    def length(self, length):
        self._pack_into_buffer(length, 'I', 'H x x')

    @staticmethod
    def byte_size():
        return calcsize(VQueueUsedElement.format)

    def _unpack(self):
        return self.struct.unpack(self.buffer)

    def _pack_into_buffer(self, value, field_format, prefix=''):
        offset = calcsize(prefix)
        pack_into(field_format, self.buffer, offset, value)


class VQueueUsed(object):
    format = 'H H {0:d}x H'

    def __init__(self, buffer, size):
        self.buffer = buffer
        self.size = size
        used_elem_size = VQueueUsedElement.byte_size()
        self.struct = Struct(VQueueUsed.format.format(used_elem_size*size))
        elem_buff = buffer[4:-2]
        self.used_elements = [VQueueUsedElement(elem_buff[i*used_elem_size:used_elem_size*(i + 1)]) for i in range(size)]

    def flags(self):
        return self._unpack()[0]

    @property
    def idx(self):
        return self._unpack()[1]

    def __str__(self):
        return 'size={} buffer_size={} format={}'.format(self.size, len(self.buffer), self.struct.format)

    def _unpack(self):
        return self.struct.unpack(self.buffer)
