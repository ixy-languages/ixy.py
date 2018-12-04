import time
import logging as log

from ixypy.ixy import IxyDevice
from ixypy.register import MmapRegister

from ixypy.ixgbe.types import *


class IxgbeDevice(IxyDevice):
    MAX_QUEUES = 64

    def __init__(self, pci_device, num_rx_queues, num_tx_queues):
        self.resource = None
        self.tx_queues = None
        self.rx_queues = None
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
        self.reg = MmapRegister(self.pci_device.map_resource())
        self.reset_and_init()

    def reset_and_init(self):
        log.info('Resetting device %s', self.pci_device.address)
        self.disable_interrupts()
        self.global_reset()
        self.disable_interrupts()

        log.info('Initializing device %s', self.pci_device.address)
        self._wait_for_eeprom()
        self._wait_for_dma_init()

    def init_link(self):
        """Sec 4.6.4."""
        self.reg.set(IXGBE_AUTOC, )

    def disable_interrupts(self):
        """Sec 4.6.3.1 - Disable all interrupts."""
        self.reg.set(IXGBE_EIMC, 0x7FFFFFFF)

    def global_reset(self):
        """Sec 4.6.3.2 - Global reset (software + link)."""
        self.reg.set(IXGBE_CTRL, IXGBE_CTRL_RST_MASK)
        self.reg.wait_clear(IXGBE_CTRL, IXGBE_CTRL_RST_MASK)
        time.sleep(0.01)

    def _wait_for_eeprom(self):
        """Sec 4.6.3.1 - Wait for EEPROM auto read completion."""
        self.reg.wait_set(IXGBE_EEC, IXGBE_EEC_ARD)

    def _wait_for_dma_init(self):
        """Sec 4.6.3 - Wait for DMA initialization to complete."""
        self.reg.wait_set(IXGBE_RDRXCTL, IXGBE_RDRXCTL_DMAIDONE)
