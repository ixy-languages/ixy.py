from struct import Struct, calcsize, pack

from ixypy.virtio_type import VRING_AVAIL_F_NO_INTERRUPT

MAX_QUEUE_SIZE = 32768


class Queue(object):
    def __init__(self, vqueue, notification_offset, mempool, used_last_index=0):
        self.mempool = mempool
        self.vqueue = vqueue
        self.notification_offset = notification_offset
        self.used_last_index = used_last_index
        self.virtual_addresses = []

    def disable_interrupts(self):
        self.vqueue.available_queues.flags = VRING_AVAIL_F_NO_INTERRUPT
        self.vqueue.used_queues.flags = 0

    def get_free_descriptor(self):
        for index, descriptor in enumerate(self.vqueue.descriptors):
            if descriptor.address == 0:
                return index, descriptor
        raise ValueError('Queue is full')


class VNetworkControlHeader(object):
    fmt = 'B B'

    def __init__(self):
        self.struct = Struct(self.fmt)


class VCommand(object):
    def __init__(self, hdr, on):
        self.hdr = hdr
        self.on = on


class VQueue(object):
    def __init__(self, size, buffer, alignment=4096):
        if size > MAX_QUEUE_SIZE:
            raise ValueError("Size exceeded maximum size")
        self.size = size
        self.buffer = buffer
        self.alignment = alignment
        self.descriptors = self._descriptors()
        self.available_queues = self._available_queues()
        self.used_queues = self._used_queues()

    def _descriptors(self):
        item_size = VQueueDescriptor.byte_size()
        descriptor_tbl_size = VQueue.descriptor_table_size(self.size)
        sub_buff = self.buffer[:descriptor_tbl_size]
        return [VQueueDescriptor(sub_buff[i*item_size:item_size*(i+1)]) for i in range(len(self))]

    def _available_queues(self):
        descriptor_tbl_size = VQueue.descriptor_table_size(self.size)
        available_queue_size = VQueue.available_queue_size(self.size)
        sub_buff = self.buffer[descriptor_tbl_size:(descriptor_tbl_size + available_queue_size)]
        return VQueueAvailable(sub_buff, self.size)

    def _used_queues(self):
        buffer_start = len(self) - VQueue.used_queue_size(self.size)
        sub_buff = self.buffer[buffer_start:len(self)]
        return VQueueUsed(sub_buff, self.size)

    def __len__(self):
        return VQueue.byte_size(self.size, self.alignment)

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
        total_qsz = VQueue.byte_size(size, alignment)
        dsc_tbl_sz = VQueue.descriptor_table_size(size)
        avail_qsz = VQueue.available_queue_size(size)
        used_qsz = VQueue.used_queue_size(size)
        return total_qsz - (dsc_tbl_sz + avail_qsz + used_qsz)

    @staticmethod
    def align(val, alignment):
        return (val + alignment) & ~alignment

    @staticmethod
    def byte_size(max_queue_size, alignment=4096):
        dsc_tbl_sz = VQueue.descriptor_table_size(max_queue_size)
        avail_qsz = VQueue.available_queue_size(max_queue_size)
        used_qsz = VQueue.used_queue_size(max_queue_size)
        return VQueue.align(dsc_tbl_sz + avail_qsz, alignment)+VQueue.align(used_qsz, alignment)


class VQueueDescriptor(object):
    format = 'Q I H H'

    def __init__(self, buffer):
        self.struct = Struct(VQueueDescriptor.format)
        self.buffer = buffer

    def address(self):
        return self._unpack()[0]

    def len(self):
        return self._unpack()[1]

    def flags(self):
        return self._unpack()[2]

    def next(self):
        return self._unpack()[3]

    def write(self, len, addr, flags, next):
        self.struct.pack_into(self.buffer, len, addr, flags, next)

    @staticmethod
    def byte_size():
        return calcsize(VQueueDescriptor.format)

    def _unpack(self):
        return self.struct.unpack(self.buffer)


class VQueueAvailable(object):
    format = 'H H {:d}H'

    def __init__(self, buffer, size):
        self.buffer = buffer
        self.size = size
        self.struct = Struct(VQueueAvailable.format.format(size))

    def flags(self):
        return self._unpack()[0]

    def idx(self):
        return self._unpack()[1]

    def ring(self, index=0):
        return self._unpack()[2 + index]

    @staticmethod
    def byte_size(queue_size):
        return calcsize(VQueueAvailable.format.format(queue_size))

    def _unpack(self):
        return self.struct.unpack(self.buffer)


class VQueueUsedElement(object):
    format = 'H x x I'

    def __init__(self, buffer):
        self.buffer = buffer
        self.struct = Struct(VQueueUsedElement.format)

    def id(self):
        return self._unpack()[0]

    def len(self):
        return self._unpack()[1]

    @staticmethod
    def byte_size():
        return calcsize(VQueueUsedElement.format)

    def _unpack(self):
        return self.struct.unpack(self.buffer)


class VQueueUsed(object):
    format = 'H H {0:d}x'

    def __init__(self, buffer, size):
        self.buffer = buffer
        self.size = size
        used_elem_size = VQueueUsedElement.byte_size()
        self.format = VQueueUsed.format.format(used_elem_size)
        elem_buff = buffer[2::]
        self.used_elements = [VQueueUsedElement(elem_buff[i*used_elem_size:used_elem_size*(i + 1)]) for i in range(size)]

    def flags(self):
        return self._unpack()[0]

    def idx(self):
        return self._unpack()[1]

    def _unpack(self):
        return self.struct.unpack(self.buffer)
