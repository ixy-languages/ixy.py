import time
import logging as log
from functools import reduce

from memory import DmaMemory
from ixypy.mempool import Mempool
from ixypy.ixgbe.structures import RxQueue, TxQueue
from ixypy.ixy import IxyDevice
from ixypy.register import MmapRegister
from ixypy.ixgbe import types


def to_hex(val):
    return '{:02X}'.format(val)


class IxgbeDevice(IxyDevice):
    MAX_QUEUES = 64
    MAX_RX_QUEUE_ENTRIES = 4096
    MAX_TX_QUEUE_ENTRIES = 4096
    NUM_TX_QUEUE_ENTRIES = 512
    NUM_RX_QUEUE_ENTRIES = 512
    RX_DESCRIPTOR_SIZE = 16
    TX_DESCRIPTOR_SIZE = 16
    TX_CLEAN_BATCH = 32

    def __init__(self, pci_device, num_rx_queues=1, num_tx_queues=1):
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
        self.reg = MmapRegister(memoryview(self.pci_device.map_resource()))
        self.reset_and_init()

    def reset_and_init(self):
        log.info('Resetting device %s', self.pci_device.address)
        self.disable_interrupts()
        self.global_reset()
        self.disable_interrupts()

        log.info('Initializing device %s', self.pci_device.address)
        self._wait_for_eeprom()
        self._wait_for_dma_init()

        import pdb; pdb.set_trace()
        self.init_link()
        self.init_statistict()
        self.init_rx()
        self.init_tx()
        for queue in self.rx_queues:
            self.start_rx_queue(queue)
        for queue in self.tx_queues:
            self.start_tx_queue(queue)
        self.set_promisc()
        self.wait_for_link()

    def set_promisc(self, enabled=True):
        if enabled:
            log.info('Enabling promisc mode')
            self.reg.set_flags(types.IXGBE_FCTRL, types.IXGBE_FCTRL_MPE | types.IXGBE_FCTRL_UPE)
        else:
            log.info('Disabling promisc mode')
            self.reg.clear_flags(types.IXGBE_FCTRL, types.IXGBE_FCTRL_MPE | types.IXGBE_FCTRL_UPE)

    def wait_for_link(self):
        log.info('Waiting for link')
        waiting_time = 0
        link_speed = self.get_link_speed()
        while waiting_time < 10 and link_speed == 0:
            time.sleep(0.01)
            waiting_time += 0.01
            link_speed = self.get_link_speed()
        if link_speed != 0:
            log.info('Link established - speed %d Mbit/s', link_speed)
        else:
            log.warning('Timed out while waiting for link')

    def get_link_speed(self):
        links = self.reg.get(types.IXGBE_LINKS)
        if links & types.IXGBE_LINKS_UP:
            return 0
        speed = links & types.IXGBE_LINKS_SPEED_82599
        if speed == types.IXGBE_LINKS_SPEED_100_82599:
            return 100
        elif speed == types.IXGBE_LINKS_SPEED_1G_82599:
            return 1000
        elif speed == types.IXGBE_LINKS_SPEED_10G_82599:
            return 10000
        else:
            log.warning('Unknown link speed: %d', speed)
            return 0

    def start_rx_queue(self, queue):
        import pdb; pdb.set_trace()
        log.info('Starting RX queue %d', queue.identifier)
        # Mempool should be >= number of rx and tx descriptors
        mempool_size = self.NUM_RX_QUEUE_ENTRIES + self.NUM_TX_QUEUE_ENTRIES
        mempool = Mempool.allocate(4096 if mempool_size < 4096 else mempool_size)
        queue.mempool = mempool
        if queue.num_descriptors & (queue.num_descriptors - 1) != 0:
            raise ValueError('Number of queue entries must be a power of 2, actual {}'.format(queue.num_descriptors))
        for descriptor in queue.descriptors:
            pkt_buf = mempool.get_buffer()
            if not pkt_buf:
                raise ValueError('Could not allocate packet buffer')
            descriptor.read.pkt_addr = pkt_buf.physical_address + pkt_buf.data_offset
            descriptor.read.hdr_addr = 0
            queue.buffers.append(pkt_buf)
        # Enable queue and wait if necessary
        self.reg.set_flags(types.IXGBE_RXDCTL(queue.identifier), types.IXGBE_RXDCTL_ENABLE)
        self.reg.wait_set(types.IXGBE_RXDCTL(queue.identifier), types.IXGBE_RXDCTL_ENABLE)

        # Rx queue starts out full
        self.reg.set(types.IXGBE_RDH(queue.identifier), 0)

        # was set to 0 before in the init function
        self.reg.set(types.IXGBE_RDT(queue.identifier), queue.num_descriptors - 1)

    def init_rx(self):
        """Sec 4.6.7"""
        # disable RX while configuring
        # The datasheet also wants us to disable some crypto-offloading related rx paths (but we don't care about them)
        self.reg.clear_flags(types.IXGBE_RXCTRL, types.IXGBE_RXCTRL_RXEN)
        # self.reg.set(types.IXGBE_RXCTRL, types.IXGBE_RXCTRL_RXEN)

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
        """
        this flag probably refers to a broken feature: it's reserved and initialized as
        '1' but it must be set to '0'
        there isn't even a constant in ixgbe_types.h for this flag
        """
        for index, _ in enumerate(self.rx_queues):
            self.reg.clear_flags(types.IXGBE_DCA_RXCTRL(index), 1 << 12)

        # Start RX
        self.reg.set_flags(types.IXGBE_RXCTRL, types.IXGBE_RXCTRL_RXEN)

    def init_rx_queue(self, index):
        log.info('Initializing rx queue %d', index)
        # Enable advanced rx descriptors
        srrctl = types.IXGBE_SRRCTL(index)
        srrctl_masked = self.reg.get(srrctl) & ~types.IXGBE_SRRCTL_DESCTYPE_MASK
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
        log.info('RX ring %d using %s', index, mem)

        # Set ring to empty
        self.reg.set(types.IXGBE_RDH(index), 0)
        self.reg.set(types.IXGBE_RDT(index), 0)
        queue = RxQueue(self.NUM_RX_QUEUE_ENTRIES, index, memoryview(mem))
        return queue

    def start_tx_queue(self, queue):
        log.info('Starting tx queue %d', queue.identifier)
        if queue.num_descriptors & (queue.num_descriptors - 1) != 0:
            raise ValueError('Numberof queue entries must be a power of 2')
        # tx queue starts out empty
        self.reg.set(types.IXGBE_TDH(queue.identifier), 0)
        self.reg.set(types.IXGBE_TDT(queue.identifier), 0)

        # enable queue and wait if necessary
        self.reg.set_flags(types.IXGBE_TXDCTL(queue.identifier), types.IXGBE_TXDCTL_ENABLE)
        self.reg.wait_set(types.IXGBE_TXDCTL(queue.identifier), types.IXGBE_TXDCTL_ENABLE)

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
        queue = TxQueue(memoryview(mem), self.NUM_TX_QUEUE_ENTRIES, index)
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
        self.reg.clear_flags(types.IXGBE_RTTDCS, types.IXGBE_RTTDCS_ARBDIS)

        self.tx_queues = [
            self.init_tx_queue(index) for index in range(self.num_tx_queues)
        ]
        self.enable_dma()

    def rx_batch(self, queue_id, buffer_count):
        """
        Sec 1.8.2 and 7.1
        try to receive a single packet if one is available, non-blocking
        see datashet section 7.1.9 for an explanation of the rx ring structure
        tl;dr; we control the tail of the queue, the hardware the head
        """
        if not 0 <= queue_id < len(self.rx_queues):
            raise IndexError('Queue id<{}> not in [0, {}]'.format(queue_id, len(self.rx_queues)))
        buffers = []
        queue = self.rx_queues[queue_id]
        rx_index = queue.index
        last_rx_index = rx_index
        for buf_index in range(buffer_count):
            descriptor = queue.descriptors[rx_index]
            status = descriptor.writeback.upper.status_error
            # status done
            if (status & types.IXGBE_RXDADV_STAT_DD) != 0:
                # status end of packet
                if (status & types.IXGBE_RXDADV_STAT_EOP) == 0:
                    raise RuntimeError('Multisegment packets are not supported - increase buffer size or decrease MTU')

                # We got a packet - read and copy the whole descriptor
                packet_buffer = queue.buffers[rx_index]
                packet_buffer.size = descriptor.writeback.upper.length

                # This would be the plaace to implement RX offloading by translating the device-specific
                # flags to an independent representation in that buffer (similar to how DPDK works)
                new_buf = queue.mempool.get_buffer()
                if not new_buf:
                    raise MemoryError('Failed to allocate new buffer for rx')
                descriptor.read.pkt_addr = new_buf.physical_address + new_buf.data_offset
                # This resets the flags
                descriptor.read.hdr_addr = 0
                queue.buffers[rx_index] = new_buf
                buffers[buf_index] = packet_buffer

                # want to read the next one in the next iteration but we still need the current one to update RDT later
                last_rx_index = rx_index
                rx_index = self.wrap_ring(rx_index, queue.num_descriptors)
            else:
                break
        if rx_index != last_rx_index:
            """
            Tell the hardware that we are done. This is intentionally off by one, otherwise
            we'd set RDT=RDH if we are receiving faster than packets are coming in, which would mean queue is full
            """
            self.reg.set(types.IXGBE_RDT(queue_id), last_rx_index)
            queue.index = rx_index
        return buffers

    def tx_batch(self, buffers, queue_id):
        if not 0 <= queue_id < len(self.rx_queues):
            raise IndexError('Queue id<{}> not in [0, {}]'.format(queue_id, len(self.rx_queues)))
        queue = self.tx_queues[queue_id]
        clean_index = queue.clean_index
        current_index = queue.index
        flags = [
            types.IXGBE_ADVTXD_DCMD_EOP,
            types.IXGBE_ADVTXD_DCMD_RS,
            types.IXGBE_ADVTXD_DCMD_IFCS,
            types.IXGBE_ADVTXD_DCMD_DEXT,
            types.IXGBE_ADVTXD_DTYP_DATA
        ]
        cmd_type_flags = reduce(lambda x, y: x | y, flags, 0)
        # all packet buffers  handled here will belong to the same mempool
        mempool = None
        """
        Step1: Clen up descriptors sent out by the hardware and return them to the mempool
        Start by reading step 2 which is done first for each packet
        Cleaning up must be done in batches for performance reasons, so this is unfortunately somewhat complicated
        """
        while True:
            # current index is always ahead of clean (invariant of our queue)
            cleanable = current_index - clean_index
            if cleanable < 0:
                cleanable = queue.num_descriptors + cleanable
            if cleanable < self.TX_CLEAN_BATCH:
                break

            # Calculate the index of the last transcriptor in the clean batch
            # We can't check all descriptors for performance reasons
            cleanup_to = clean_index + self.TX_CLEAN_BATCH - 1
            if cleanup_to >= queue.num_descriptors:
                cleanup_to -= queue.num_descriptors
            descriptor = queue.descriptors[cleanup_to]
            status = descriptor.writeback.status

            # Hardware sets this flag as soon as it's sent out, we can give back all bufs in the batch back to the mempool
            if (status & types.IXGBE_ADVTXD_STAT_DD) != 0:
                i = clean_index
                while True:
                    pkt_buffer = queue.buffers[i]
                    if mempool is None:
                        mempool = Mempool.pools[pkt_buffer.mempool_id]
                        if mempool is None:
                            raise ValueError('Could not find mempool with id {}'.format(pkt_buffer.mempool_id))
                    mempool.free_buffer(pkt_buffer)
                    if i == cleanup_to:
                        break
                    i = self.wrap_ring(i, queue.num_descriptors)
                # Next descriptor to be cleaned up is one after the one we just cleaned
                clean_index = self.wrap_ring(cleanup_to, queue.num_descriptors)
            else:
                """
                Clean the whole batch or nothing. This will leave some packets in the queue forever
                if you stop transmitting but tha's not a real concern
                """
                break
            queue.clean_index = clean_index

        # Step 2: Send out as many of our packets as possible
        sent = 0
        for index, buff in enumerate(buffers):
            sent += 1
            descriptor = queue.descriptors[current_index]
            next_index = self.wrap_ring(current_index, queue.num_descriptors)
            # We are full if the next index is the one we are trying to reclaim
            if clean_index == next_index:
                break
            # Remember virual address to clean it up later
            queue.buffers[current_index] = buff
            queue.index = self.wrap_ring(queue.index, queue.num_descriptors)
            # NIC reads from here
            descriptor.read.buffer_address = buff.physical_address + buff.data_offset
            # Alaways the same flags: One buffer (EOP), advanced data descriptor, CRC offload, data length
            buff_size = buff.size
            descriptor.read.cmd_type_len = cmd_type_flags | buff_size
            """
            No fancy offloading - only the total payload length
            implement offloading flags here:
                * ip checksum offloading is trivial: just set the offset
                * tcp/udp checksum offloading is more annoying, you have to precalculate the pseudo-header checksum
            """
            descriptor.read.olinfo_status = buff_size << types.IXGBE_ADVTXD_PAYLEN_SHIFT
            current_index = next_index
        # Send out by advancing tail, i.e. pass control of the bus to the NIC
        self.reg.set(types.IXGBE_TDT(queue_id), queue.index)
        return sent

    def wrap_ring(self, index, ring_size):
        return (index + 1) & (ring_size -1)

    def enable_dma(self):
        self.reg.set(types.IXGBE_DMATXCTL, types.IXGBE_DMATXCTL_TE)

    def read_stats(self, stats):
        rx_packets = self.reg.get(types.IXGBE_GPRC)
        tx_packets = self.reg.get(types.IXGBE_GPTC)
        rx_bytes = self.reg.get(types.IXGBE_GORCL) + (self.reg.get(types.IXGBE_GORCH) << 32)
        tx_bytes = self.reg.get(types.IXGBE_GOTCL) + (self.reg.get(types.IXGBE_GOTCH) << 32)
        stats.rx_packets += rx_packets
        stats.tx_packets += tx_packets
        stats.rx_bytes += rx_bytes
        stats.tx_bytes += tx_bytes

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
        # the datasheet suggests waiting here, we will wait at a later point

    def init_statistict(self):
        """
        Sec. 4.6.7 - init rx
        reset on read registers, just read them once
        """
        self._reset_stats()

    def _reset_stats(self):
        self.reg.get(types.IXGBE_GPRC)
        self.reg.get(types.IXGBE_GPTC)
        self.reg.get(types.IXGBE_GORCL)
        self.reg.get(types.IXGBE_GORCH)
        self.reg.get(types.IXGBE_GOTCL)
        self.reg.get(types.IXGBE_GOTCH)

    def disable_interrupts(self):
        """Sec 4.6.3.1 - Disable all interrupts."""
        self.reg.set(types.IXGBE_EIMC, 0x7FFFFFFF)

    def global_reset(self):
        """Sec 4.6.3.2 - Global reset (software + link)."""
        self.reg.set(types.IXGBE_CTRL, types.IXGBE_CTRL_RST_MASK)
        self.reg.wait_clear(types.IXGBE_CTRL, types.IXGBE_CTRL_RST_MASK)
        time.sleep(0.1)

    def _wait_for_eeprom(self):
        """Sec 4.6.3.1 - Wait for EEPROM auto read completion."""
        self.reg.wait_set(types.IXGBE_EEC, types.IXGBE_EEC_ARD)

    def _wait_for_dma_init(self):
        """Sec 4.6.3 - Wait for DMA initialization to complete."""
        self.reg.wait_set(types.IXGBE_RDRXCTL, types.IXGBE_RDRXCTL_DMAIDONE)
