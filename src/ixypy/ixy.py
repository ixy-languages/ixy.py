from abc import ABC, abstractmethod
import logging as log
from ixypy.stats import Stats


class IxyDevice(ABC):
    def __init__(self, pci_device, driver_name, num_rx_queues=1, num_tx_queues=1):
        self.pci_device = pci_device
        self.driver_name = driver_name
        self.num_rx_queues = num_rx_queues
        self.num_tx_queues = num_tx_queues
        self.stats = Stats(pci_address=pci_device.address)
        self._initialize_device()

    @abstractmethod
    def _initialize_device(self):
        pass

    @abstractmethod
    def get_link_speed(self):
        pass

    @abstractmethod
    def set_promisc(self):
        pass

    def get_stats(self):
        return self.stats

    @abstractmethod
    def tx_batch(self, buffers, queue_id=0):
        pass

    @abstractmethod
    def rx_batch(self):
        pass

    def tx_batch_busy_wait(self, pkt_buffs, queue_id=0):
        num_sent = 0
        while num_sent != len(pkt_buffs):
            # log.debug('Sending %d out of %d', num_sent, len(pkt_buffs))
            num_sent += self.tx_batch(pkt_buffs[num_sent:], queue_id)
