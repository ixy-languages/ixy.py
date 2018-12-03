import logging as log

from ixypy.ixy import IxyDevice



class IxgbeDevice(IxyDevice):
    MAX_QUEUES = 64

    def __init__(self, pci_device, num_rx_queues, num_tx_queues):
        super().__init__(pci_device, 'ixy-ixgbe', num_rx_queues, num_tx_queues)

    def _initialize_device(self):
        if not 0 < self.num_rx_queues < self.MAX_QUEUES:
            raise ValueError('Invalid rx queue number {}'.format(self.num_rx_queues))
        if not 0 < self.num_tx_queues < self.MAX_QUEUES:
            raise ValueError('Invalid tx queue number {}'.format(self.num_tx_queues))
        if self.pci_device.has_driver():
            log.info('Unbinding driver')
            self.pci_device.unbind_driver()
        # self.rx_queues =
        # self.tx_queues =
