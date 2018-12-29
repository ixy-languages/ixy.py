from ixypy.virtio.virtio_device import VirtIo
from ixypy.ixgbe.device import IxgbeDevice
from ixypy.pci import PCIDevice, PCIAddress, PCIVendor
from ixypy.mempool import Mempool
from ixypy.stats import Stats

import copy
import argparse
import logging as log
import time

log.basicConfig(level=log.DEBUG,
                format='%(asctime)s %(levelname)-8s %(message)s',
                datefmt='%a, %d %b %Y %H:%M:%S')


BATCH_SIZE = 32


def forward(rx_dev, rx_queue, tx_dev, tx_queue):
    rx_buffers = rx_dev.rx_batch(rx_queue, BATCH_SIZE)

    if rx_buffers:
        # TODO: touch all packets, otherwise it's a completely unrealistic workload if the packet just stays in L3
        tx_buffer_count = tx_dev.tx_batch(rx_buffers, tx_queue)

        """
        there are two ways to handle the case that packets are not being sent out:
        either wait on tx or drop them; in this case it's better to drop them, otherwise we accumulate latency
        """
        for i in range(tx_buffer_count):
            buff = rx_buffers[i]
            mempool = Mempool.pools[buff.mempool_id]
            if mempool:
                mempool.free_buffer(buff)


def device(address_string):
    address = PCIAddress.from_address_string(address_string)
    device = PCIDevice(address)
    log.info("Vendor = %s", device.vendor())
    if device.vendor() == PCIVendor.virt_io:
        return VirtIo(device)
    return IxgbeDevice(device)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    pci_address_eg = '0000:00:08.0'
    parser.add_argument('pci_2', help='Pci bus id2 e.g. {}'.format(pci_address_eg), type=str)
    parser.add_argument('pci_1', help='Pci bus id1 e.g. {}'.format(pci_address_eg), type=str)
    args = parser.parse_args()

    dev_1 = device(args.pci_1)
    dev_2 = device(args.pci_2)

    last_stats_printed = time.perf_counter()
    stats_1_new, stats_1_old = Stats(dev_1.pci_device), Stats(dev_1.pci_device)
    stats_2_new, stats_2_old = Stats(dev_2.pci_device), Stats(dev_2.pci_device)

    counter = 0
    while True:
        forward(dev_1, 0, dev_2, 0)
        forward(dev_2, 0, dev_1, 0)

        # Don't poll the time unnecessarily
        if (counter & 0xFF) == 0:
            current_time = time.perf_counter()
            interval = current_time - last_stats_printed
            if interval > 1:
                dev_1.read_stats(stats_1_new)
                stats_1_new.print_diff(stats_1_old, interval)
                stats_1_old = copy.copy(stats_1_new)
                if dev_1 != dev_2:
                    dev_2.read_stats(stats_2_new)
                    stats_2_new.print_diff(stats_2_old, interval)
                    stats_2_old = copy.copy(stats_2_new)
                last_stats_printed = current_time
        counter += 1
