from os import getuid
import logging as log
from abc import ABC, abstractmethod
from struct import Struct, calcsize, pack_into


def is_running_as_root():
    return getuid() == 0


class IxyException(Exception):
    pass


class IxyQueueSizeException(IxyException):
    def __init__(self, given_queue_num):
        super().__init__('Cannot configure queue: limit is {:d}'
                         .format(given_queue_num))


class IxyQueue(object):
    def __init__(self, memory, size, identifier, mempool):
        self.memory = memory
        self.size = size
        self.buffers = [None]*size
        self.identifier = identifier
        self.index = 0
        self.mempool = mempool

    def _get_descriptors(self, descriptor_class):
        desc_size = descriptor_class.byte_size()
        return [descriptor_class(self.memory[i*desc_size:desc_size*(i+1)]) for i in range(self.size)]

    def __len__(self):
        return self.size


class IxyStruct(object):
    def __init__(self, mem):
        self.mem = mem
        self.data_struct = Struct(self.data_format)

    def _pack_into(self, value, field_format, prefix=''):
        offset = calcsize(prefix)
        pack_into(field_format, self.mem, offset, value)

    def _unpack(self):
        return self.data_struct.unpack(self.mem)

    def __len__(self):
        return self.data_struct.size

    @classmethod
    def byte_size(cls):
        return calcsize(cls.data_format)


class IxyDevice(ABC):
    def __init__(self,
                 pci_device,
                 driver_name,
                 max_rx_queues=1,
                 max_tx_queues=1,
                 num_rx_queues=1,
                 num_tx_queues=1):
        self._validate_queue_size(num_rx_queues, max_rx_queues)
        self._validate_queue_size(num_tx_queues, max_tx_queues)
        self.pci_device = pci_device
        self.driver_name = driver_name
        self.num_rx_queues = num_rx_queues
        self.num_tx_queues = num_tx_queues
        self.rx_queues = []
        self.tx_queues = []
        self._common_init()
        self._initialize_device()

    def _common_init(self):
        if not is_running_as_root():
            log.warning('Not running as root')
        if self.pci_device.has_driver():
            log.info('Unbinding driver')
            self.pci_device.unbind_driver()
        else:
            log.info("No driver loaded")
        self.pci_device.enable_dma()

    @staticmethod
    def _validate_queue_size(actual, maximum):
        if not 0 < actual <= maximum:
            raise IxyQueueSizeException(actual)

    @abstractmethod
    def _initialize_device(self):
        pass

    @abstractmethod
    def get_link_speed(self):
        pass

    @abstractmethod
    def set_promisc(self):
        pass

    @abstractmethod
    def read_stats(self, stats):
        pass

    @abstractmethod
    def tx_batch(self, buffers, queue_id=0):
        pass

    @abstractmethod
    def rx_batch(self, queue_id, batch_size):
        pass

    def tx_batch_busy_wait(self, pkt_buffs, queue_id=0):
        num_sent = 0
        while num_sent < len(pkt_buffs):
            num_sent += self.tx_batch(pkt_buffs[num_sent:], queue_id)
