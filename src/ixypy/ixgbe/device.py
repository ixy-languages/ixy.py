import time
import logging as log

from memory import DmaMemory
from ixypy.mempool import Mempool
from ixypy.ixgbe.structures import RxQueue, TxQueue
from ixypy.ixy import IxyDevice
from ixypy.register import MmapRegister
from ixypy.ixgbe import types


class IxgbeDevice(IxyDevice):
    MAX_QUEUES = 64
    MAX_RX_QUEUE_ENTRIES = 4096
    MAX_TX_QUEUE_ENTRIES = 4096
    NUM_TX_QUEUE_ENTRIES = 512
    NUM_RX_QUEUE_ENTRIES = 512
    RX_DESCRIPTOR_SIZE = 16
    TX_DESCRIPTOR_SIZE = 16
    TX_CLEAN_BATCH = 32

    def __init__(self, pci_device, num_rx_queues, num_tx_queues):
        self.resource = None
        self.tx_queues = None
        self.rx_queues = None
        super().__init__(pci_device, 'ixy-ixgbe', num_rx_queues, num_tx_queues)

    def _initialize_device(self):
        if not 0 < self.num_rx_queues < self.MAX_QUEUES:
            raise ValueError('Invalid rx queue number {}'.format(
                self.num_rx_queues))
        if not 0 < self.num_tx_queues < self.MAX_QUEUES:
            raise ValueError('Invalid tx queue number {}'.format(
                self.num_tx_queues))
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

        self.init_link()
        self.init_statistict()
        self.init_rx()
        self.init_tx()
        for queue in self.rx_queues:
            self.start_rx_queue(queue)
        for queue in self.tx_queues:
            self.start_tx_queue(queue)

    def start_rx_queue(self, queue):
        log.info('Starting RX_DESCRIPTOR_SIZEX queue %d', queue.identifier)
        # Mempool should be >= number of rx and tx descriptors
        mempool_size = self.NUM_RX_QUEUE_ENTRIES + self.NUM_TX_QUEUE_ENTRIES
        mempool = Mempool.allocate(4096 if mempool_size < 4096 else mempool_size)
        queue.mempool = mempool
        if queue.num_entries & (queue.num_entries - 1) != 0:
            raise ValueError('Number of queue entries must be a power of 2, actual {}'.format(queue.num_entries))
        for entry in range(queue.num_entries):
            # TODO ALlocate buffers
            pass
        # Enable queue and wait if necessary
        self.reg.set_flags(types.IXGBE_RXDCTL(queue.identifier), types.IXGBE_RXDCTL_ENABLE)
        self.reg.wait_set(types.IXGBE_RXDCTL(queue.identifier), types.IXGBE_RXDCTL_ENABLE)

        # Rx queue starts out full
        self.reg.set(types.IXGBE_RDH(queue.identifier), 0)
        self.reg.set(types.IXGBE_RDT(queue.identifier), queue.num_entries - 1)



    def init_rx(self):
        """Sec 4.6.7"""
        # disable RX while configuring
        self.reg.clear_flags(types.IXGBE_RXCTRL, types.IXGBE_RXCTRL_RXEN)
        self.reg.set(types.IXGBE_RXCTRL, types.IXGBE_RXCTRL_RXEN)

        # NO DCB or VT, just a single 128kb packet buffer
        self.reg.set(types.IXGBE_RXPBSIZE(0), types.IXGBE_RXPBSIZE_128KB)
        for item in range(1, 8):
            self.reg.set(types.IXGBE_RXPBSIZE(item), 0)

        # Always enable CRC offloading
        self.reg.set_flags(types.IXGBE_HLREG0, types.IXGBE_HLREG0_RXCRCSTRP)
        self.reg.set_flags(types.IXGBE_RDRXCTL, types.IXGBE_RDRXCTL_CRCSTRIP)

        # Accept broadcast packets
        self.reg.set_flags(types.IXGBE_FCTRL, types.IXGBE_FCTRL_BAM)

        # Per queue config
        self.rx_queues = [
            self.init_rx_queue(index) for index in range(self.num_rx_queues)
        ]

        # Sec 4.6.7 - set magic bits
        self.reg.set_flags(types.IXGBE_CTRL_EXT, types.IXGBE_CTRL_EXT_NS_DIS)
        for index, _ in enumerate(self.rx_queues):
            self.reg.clear_flags(types.IXGBE_DCA_RXCTRL(index), 1 << 12)

        # Start RX
        self.reg.set_flags(types.IXGBE_RXCTRL, types.IXGBE_RXCTRL_RXEN)

    def init_rx_queue(self, index):
        log.info('Initializing rx queue %d', index)
        # Enable advanced rx descriptors
        srrctl = types.IXGBE_SRRCTL(index)
        srrctl_masked = self.reg.get(
            srrctl) & ~types.IXGBE_SRRCTL_DESCTYPE_MASK
        rx_descriptor_reg = srrctl_masked | types.IXGBE_SRRCTL_DESCTYPE_ADV_ONEBUF
        self.reg.set(srrctl, rx_descriptor_reg)
        """
        DROP_EN causes the NIC to drop packets if no descriptors are available
        instead of buffering them
        A single overflowing queue can fill up the whole buffer and impact
        operations if not setting this
        """
        self.reg.set_flags(srrctl, types.IXGBE_SRRCTL_DROP_EN)

        # Sec 7.1.9 - Set up descriptor ring
        ring_size = self.NUM_RX_QUEUE_ENTRIES * self.RX_DESCRIPTOR_SIZE
        mem = DmaMemory(ring_size)
        self.reg.set(types.IXGBE_RDBAL(index), mem.physical_address)
        self.reg.set(types.IXGBE_RDBAH(index), mem.physical_address >> 32)
        self.reg.set(types.IXGBE_RDLEN(index), ring_size)
        self.info('RX ring %d using %s', index, mem)

        # Set ring to empty
        self.reg.set(types.IXGBE_RDH(index), 0)
        self.reg.set(types.IXGBE_RDT(index), 0)
        queue = RxQueue(self.NUM_RX_QUEUE_ENTRIES, index, memoryview(mem))
        return queue

    def init_tx_queue(self, index):
        log.info('Initializing TX queue %d', index)
        # Sec 7.1.9 - Set up descriptor ring
        ring_size = self.NUM_TX_QUEUE_ENTRIES * self.TX_DESCRIPTOR_SIZE
        mem = DmaMemory(ring_size)
        self.reg.set(types.IXGBE_TDBAL(index), mem.physical_address)
        self.reg.set(types.IXGBE_TDBAH(index), mem.physical_address >> 32)
        self.reg.set(types.IXGBE_TDLEN(index), ring_size)
        log.info('TX ring %d using %s', index, mem)
        # Descriptor writeback magic values, important to get good performance and low PCIe overhead
        # Sec 7.2.3.4.1 and 7.2.3.5
        txdctl = self.reg.get(types.IXGBE_TXDCTL(index))
        txdctl = txdctl & ~(0x3F | (0x3F << 8) | (0x3F << 16))
        txdctl = txdctl | (36 | (8 << 8) | (4 << 16))
        self.reg.set(types.IXGBE_TXDCTL(index), txdctl)
        queue = TxQueue(self.NUM_TX_QUEUE_ENTRIES, index, memoryview(mem))
        return queue

    def init_tx(self):
        """ Sec 4.6.8 """
        # CRC offload and small packet padding
        self.reg.set_flags(types.IXGBE_HLREG0, types.IXGBE_HLREG0_TXCRCEN | types.IXGBE_HLREG0_TXPADEN)
        # set defaul buffer size allocations (sec 4.6.11.3.4)
        self.reg.set(types.IXGBE_TXPBSIZE(0), types.IXGBE_TXPBSIZE_40KB)
        for item in range(1, 8):
            self.reg.set(types.IXGBE_TXPBSIZE(item), 0)

        # Rquired when not using DCB/VTd
        self.reg.set(types.IXGBE_DTXMXSZRQ, 0xFFFF)
        self.reg.clear_flags()

        self.tx_queues = [
            self.init_tx_queue(index) for index in range(self.num_tx_queues)
        ]
        self.enable_dma()

    def enable_dma(self):
        self.reg.set(types.IXGBE_DMATXCTL, types.IXGBE_DMATXCTL_TE)

    def init_statistics(self):
        pass

    def init_link(self):
        """Sec 4.6.4."""
        # Should already be set by the eeprom config
        autoc_value = (
            self.reg.get(types.IXGBE_AUTOC) &
            ~types.IXGBE_AUTOC_LMS_MASK) | types.IXGBE_AUTOC_LMS_10G_SERIAL
        self.reg.set(types.IXGBE_AUTOC, autoc_value)
        autoc_10G_pma = (
            self.reg.get(types.IXGBE_AUTOC) &
            ~types.IXGBE_AUTOC_10G_PMA_PMD_MASK) | types.IXGBE_AUTOC_10G_XAUI
        self.reg.set(types.IXGBE_AUTOC, autoc_10G_pma)

        # Negotiate link
        self.reg.set_flags(types.IXGBE_AUTOC, types.IXGBE_AUTOC_AN_RESTART)

    def disable_interrupts(self):
        """Sec 4.6.3.1 - Disable all interrupts."""
        self.reg.set(types.IXGBE_EIMC, 0x7FFFFFFF)

    def global_reset(self):
        """Sec 4.6.3.2 - Global reset (software + link)."""
        self.reg.set(types.IXGBE_CTRL, types.IXGBE_CTRL_RST_MASK)
        self.reg.wait_clear(types.IXGBE_CTRL, types.IXGBE_CTRL_RST_MASK)
        time.sleep(0.01)

    def _wait_for_eeprom(self):
        """Sec 4.6.3.1 - Wait for EEPROM auto read completion."""
        self.reg.wait_set(types.IXGBE_EEC, types.IXGBE_EEC_ARD)

    def _wait_for_dma_init(self):
        """Sec 4.6.3 - Wait for DMA initialization to complete."""
        self.reg.wait_set(types.IXGBE_RDRXCTL, types.IXGBE_RDRXCTL_DMAIDONE)
