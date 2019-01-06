from struct import Struct, calcsize, pack, pack_into, unpack_from
from collections import OrderedDict
from ixypy.virtio.types import VRING_AVAIL_F_NO_INTERRUPT, VIRTIO_NET_CTRL_RX, VIRTIO_NET_CTRL_RX_PROMISC
from ixypy.virtio.exception import VirtioException, BufferSizeException

from ixypy.ixy import IxyStruct, IxyQueue


MAX_QUEUE_SIZE = 32768


def align(offset, alignment=4096):
    return (offset + (alignment-1)) & -alignment


class VQueue(IxyQueue):
    def __init__(self, memory, size, identifier, notification_offset, mempool=None):
        super().__init__(memory, size, identifier, mempool)
        self.vring = VRing(memory, size) 
        self.notification_offset = notification_offset
        self.used_last_index = 0

    def disable_interrupts(self):
        self.vring.available.flags = VRING_AVAIL_F_NO_INTERRUPT
        self.vring.used.flags = 0

    def get_free_descriptor(self, index=0):
        for i in range(index, len(self.vring.descriptors)):
            desc = self.vring.descriptors[i]
            if desc.address == 0:
                return i, desc
        # for index, descriptor in enumerate(self.vring.descriptors):
            # if descriptor.address == 0:
                # return index, descriptor
        raise VirtioException('Queue overflow')


class VirtioNetworkHeader(object):
    data_format = 'B B H H H H'

    def __init__(self, flags=0, gso_type=0, header_len=0, gso_size=0, csum_start=0, csum_offset=0):
        self.flags = flags
        self.gso_type = gso_type
        self.header_len = header_len
        self.gso_size = gso_size
        self.csum_start = csum_start
        self.csum_offset = csum_offset
        self.struct = Struct(self.data_format)

    def to_buffer(self, buffer, offset=0):
        self.struct.pack_into(buffer, offset, *self._fields())

    def _fields(self):
        return [
            self.flags,
            self.gso_type,
            self.header_len,
            self.gso_size,
            self.csum_start,
            self.csum_offset]

    def __len__(self):
        return self.struct.size

    @staticmethod
    def byte_size():
        return calcsize(VirtioNetworkHeader.data_format)


class VCommand(object):
    def __init__(self, class_, id_):
        self.class_ = class_
        self.id = id_

    def bytes(self):
        pass


class PromiscuousModeCommand(VCommand):
    def __init__(self, on=True):
        self.on = on
        super().__init__(VIRTIO_NET_CTRL_RX, VIRTIO_NET_CTRL_RX_PROMISC)

    def bytes(self):
        return pack('B', self.on)

    def __len__(self):
        return 1


class VirtioNetworkControl(object):
    """
    u8 class
    u8 command
    u8 command-specific-data[]
    u8 ack
    """
    data_format = 'B B {:d}B B'

    def __init__(self, command, ack=0):
        self.command = command
        self.ack = ack

    def to_buffer(self, buffer, offset=0):
        fmt = self.data_format.format(len(self.command))
        pack_into(fmt, buffer, offset, self.command.class_, self.command.id, *self.command.bytes(), self.ack)

    @staticmethod
    def from_bytes(byte_sequence):
        pass

    @property
    def command_class(self):
        return self.command.class_

    @property
    def command_id(self):
        return self.command.id

    def __len__(self):
        return calcsize(self.data_format.format(len(self.command)))


class VRing(object):
    dump_count = 0
    def __init__(self, buffer, size, alignment=4096):
        if size > MAX_QUEUE_SIZE:
            raise VirtioException("Size[{}] exceeded maximum size[{}]".format(size, MAX_QUEUE_SIZE))
        if len(buffer) < self.byte_size(size, alignment):
            raise BufferSizeException("Required: {}, Received: {}".format(len(buffer), self.byte_size(size, alignment)))
        self.size = size
        self.buffer = buffer
        self.alignment = alignment
        self.descriptors = self._descriptors()
        self.available = self._available()
        self.used = self._used()

    def _descriptors(self):
        item_size = VRingDescriptor.byte_size()
        descriptor_tbl_size = VRing.descriptor_table_size(self.size)
        sub_buff = self.buffer[:descriptor_tbl_size]
        descriptor_buffers = [sub_buff[i*item_size:item_size*(i+1)] for i in range(self.size)]
        return [VRingDescriptor.create_descriptor(dsc_buff) for dsc_buff in descriptor_buffers]

    def _available(self):
        descriptor_tbl_size = VRing.descriptor_table_size(self.size)
        available_queue_size = VRing.available_queue_size(self.size)
        sub_buff = self.buffer[descriptor_tbl_size:(descriptor_tbl_size + available_queue_size)]
        avail = Available(sub_buff, self.size)
        avail.index = 0
        for i in range(len(avail.rings)):
            avail.rings[i] = 0
        return Available(sub_buff, self.size)

    def _used(self):
        buffer_start = len(self) - VRing.used_queue_size(self.size)
        sub_buff = self.buffer[buffer_start:len(self)]
        used = VRingUsed(sub_buff, self.size)
        used.index = 0
        for ring in used.rings:
            ring.id = 0
            ring.len = 0
        return used

    def __len__(self):
        return VRing.byte_size(self.size, self.alignment)

    def dump(self):
        with open('dumps/vring/vring_{:d}'.format(self.dump_count), 'wb') as f:
            f.write(self.buffer)
            self.dump_count += 1

    @staticmethod
    def used_queue_size(queue_size):
        return VRingUsed.byte_size(queue_size)

    @staticmethod
    def descriptor_table_size(queue_size):
        return VRingDescriptor.byte_size() * queue_size

    @staticmethod
    def available_queue_size(queue_size):
        return Available.byte_size(queue_size)

    @staticmethod
    def padding(queue_size, alignment=4096):
        dsc_tbl_sz = VRing.descriptor_table_size(queue_size)
        avail_sz = VRing.available_queue_size(queue_size)
        offset = dsc_tbl_sz + avail_sz
        return -offset & (alignment - 1)

    @staticmethod
    def byte_size(queue_size, alignment=4096):
        # see 2.4.2
        dsc_tbl_sz = VRing.descriptor_table_size(queue_size)
        avail_qsz = VRing.available_queue_size(queue_size)
        used_qsz = VRing.used_queue_size(queue_size)
        return align(dsc_tbl_sz + avail_qsz, alignment) + used_qsz


class VRingDescriptor(IxyStruct):
    data_format = 'Q I H H'

    def __init__(self, mem):
        super().__init__(mem)

    @staticmethod
    def create_descriptor(mem):
        """
        Creates a new descriptor around a buffer
        and sets all the fields to zero
        """
        descriptor = VRingDescriptor(mem)
        descriptor.length = 0
        descriptor.address = 0
        descriptor.flags = 0
        descriptor.next_descriptor = 0
        return descriptor

    @property
    def address(self):
        return self._unpack()[0]

    @address.setter
    def address(self, address):
        self._pack_into(address, 'Q')

    @property
    def length(self):
        return self._unpack()[1]

    @length.setter
    def length(self, length):
        self._pack_into(length, 'I', 'Q')

    @property
    def flags(self):
        return self._unpack()[2]

    @flags.setter
    def flags(self, flags):
        self._pack_into(flags, 'H', 'Q I')

    @property
    def next_descriptor(self):
        return self._unpack()[3]

    @next_descriptor.setter
    def next_descriptor(self, next_descriptor):
        self._pack_into(next_descriptor, 'H', 'Q I H')

    def reset(self):
        self.write(0, 0, 0, 0)

    def write(self, length, addr, flags, next_descriptor):
        self.data_struct.pack_into(self.mem, 0, length, addr, flags, next_descriptor)


class Available(object):
    data_format = 'H H'

    def __init__(self, buffer, size):
        self.size = size
        self.struct = Struct(Available.data_format.format(size))
        self.buffer = buffer[:self.struct.size]
        self.rings = RingList(buffer[self.struct.size:], size)

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
        return calcsize('H H {:d}H H'.format(queue_size))

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

    def __len__(self):
        return self.size

    def __iter__(self):
        return RingListIterator(self)

    @staticmethod
    def _get_offset(index):
        return calcsize('{:d}H'.format(index))


class RingListIterator(object):
    def __init__(self, ring_list):
        self.i = 0
        self.ring_list = ring_list

    def __iter__(self):
        return self

    def __next__(self):
        if self.i < len(self.ring_list):
            ring = self.ring_list[self.i]
            self.i += 1
            return ring
        else:
            raise StopIteration()


class VRingUsedElement(object):
    format = 'I I'

    def __init__(self, buffer):
        self.buffer = buffer
        self.struct = Struct(VRingUsedElement.format)

    @staticmethod
    def create_used_element(buff):
        used_element = VRingUsedElement(buff)
        used_element.id = 0
        used_element.length = 0
        return used_element

    @property
    def id(self):
        return self._unpack()[0]

    @id.setter
    def id(self, _id):
        self._pack_into_buffer(_id, 'I')

    @property
    def length(self):
        return self._unpack()[1]

    @length.setter
    def length(self, length):
        self._pack_into_buffer(length, 'I', 'I')

    @staticmethod
    def byte_size():
        return calcsize(VRingUsedElement.format)

    def _unpack(self):
        return self.struct.unpack(self.buffer)

    def _pack_into_buffer(self, value, field_format, prefix=''):
        offset = calcsize(prefix)
        pack_into(field_format, self.buffer, offset, value)

    def __str__(self):
        return 'id={}, length={}'.format(self.id, self.length)


class VRingUsed(object):
    data_format = 'H H {:d}x'

    def __init__(self, buffer, size):
        self.buffer = buffer
        self.size = size
        used_elem_size = VRingUsedElement.byte_size()
        self.struct = Struct(VRingUsed.data_format.format(used_elem_size*size))
        elem_buff = buffer[4:]
        self.rings = [VRingUsedElement.create_used_element(elem_buff[i*used_elem_size:used_elem_size*(i + 1)]) for i in range(size)]

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

    def _pack_into_buffer(self, value, field_format, prefix=''):
        offset = calcsize(prefix)
        pack_into(field_format, self.buffer, offset, value)

    def __str__(self):
        return 'size={} buffer_size={} format={}'.format(self.size, len(self.buffer), self.struct.format)

    def _unpack(self):
        return self.struct.unpack(self.buffer)

    @staticmethod
    def byte_size(queue_size):
        return calcsize(VRingUsed.data_format.format(VRingUsedElement.byte_size()*queue_size))
