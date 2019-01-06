from ixypy.mempool import Mempool
from ixypy.stats import Stats
from ixypy import init_device


import copy
import argparse
import logging as log
import time

log.basicConfig(level=log.DEBUG,
                format='%(asctime)s %(levelname)-8s %(message)s',
                datefmt='%a, %d %b %Y %H:%M:%S')


BATCH_SIZE = 32 

pkt_counter = 1 


def forward(rx_dev, rx_queue, tx_dev, tx_queue):
    global pkt_counter
    rx_buffers = rx_dev.rx_batch(rx_queue, BATCH_SIZE)

    if rx_buffers:
        for buff in rx_buffers:
            buff.touch()

        tx_buffer_count = tx_dev.tx_batch(rx_buffers, tx_queue)
        pkt_counter += tx_buffer_count

        """
        there are two ways to handle the case that packets are not being sent
        out: either wait on tx or drop them; in this case it's better to drop
        them, otherwise we accumulate latency
        """
        for buff in rx_buffers[tx_buffer_count:len(rx_buffers)]:
            mempool = Mempool.pools[buff.mempool_id]
            mempool.free_buffer(buff)


def run_packet_forwarding(args):
    dev_1 = init_device(args.pci_1)
    dev_2 = init_device(args.pci_2)

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
                log.info('Pkt counter = %d', pkt_counter)
        counter += 1


def main():
    parser = argparse.ArgumentParser()
    pci_address_eg = '0000:00:08.0'
    parser.add_argument('pci_2', help='Pci bus id2 e.g. {}'.format(pci_address_eg), type=str)
    parser.add_argument('pci_1', help='Pci bus id1 e.g. {}'.format(pci_address_eg), type=str)
    args = parser.parse_args()
    try:
        run_packet_forwarding(args)
    except KeyboardInterrupt:
        log.info('Packet forwarding has been stopped')


if __name__ == "__main__":
    main()
