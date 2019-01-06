from ixypy.mempool import Mempool
from ixypy.stats import Stats
from ixypy import init_device

import copy
import argparse
import logging as log
import struct
import time

log.basicConfig(level=log.DEBUG,
                format='%(filename)s:%(funcName)s:%(lineno)d %(levelname)-15s %(message)s',
                datefmt='%a, %d %b %Y %H:%M:%S')


PKT_SIZE = 60
BATCH_SIZE = 64

pkt_data = bytearray([
    # dst MAC
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06,
    # src MAC
    0x11, 0x12, 0x13, 0x14, 0x15, 0x16,
    # ether type: IPv4
    0x08, 0x00,
    # Version, IHL, TOS
    0x45, 0x00,
    # ip len excluding ethernet, high byte
    (PKT_SIZE - 14) >> 8,
    # ip len exlucding ethernet, low byte
    (PKT_SIZE - 14) & 0xFF,
    # id, flags, fragmentation
    0x00, 0x00, 0x00, 0x00,
    # TTL (64), protocol (UDP), checksum
    0x40, 0x11, 0x00, 0x00,
    # src ip (10.0.0.1)
    0x0A, 0x00, 0x00, 0x01,
    # dst ip (10.0.0.2)
    0x0A, 0x00, 0x00, 0x02,
    # src and dst ports (42 -> 1337)
    0x00, 0x2A, 0x05, 0x39,
    # udp len excluding ip & ethernet, high byte
    (PKT_SIZE - 20 - 14) >> 8,
    # udp len exlucding ip & ethernet, low byte
    (PKT_SIZE - 20 - 14) & 0xFF,
    # udp checksum, optional
    0x00, 0x00,
    # payload
    ord('i'), ord('x'), ord('y')
    # 1, 2, 3
    # rest of the payload is zero-filled because mempools guarantee empty bufs
])


def carry_around_add(a, b):
    c = a + b
    return (c & 0xffff) + (c >> 16)


def calc_ip_checksum(msg):
    s = 0
    for i in range(0, len(msg), 2):
        w = msg[i] + (msg[i+1] << 8)
        s = carry_around_add(s, w)
    return ~s & 0xffff


def init_mempool():
    NUM_BUFS = 2048
    mempool = Mempool.allocate(NUM_BUFS)
    # mempool.preallocate_buffers()
    buffs = []
    for _ in range(NUM_BUFS):
        buff = mempool.get_buffer()
        buff.size = PKT_SIZE
        buff.data_buffer[:len(pkt_data)] = memoryview(pkt_data)
        cs = calc_ip_checksum(buff.data_buffer[14:34])
        struct.pack_into('H', buff.data_buffer, 24, cs)
        buffs.append(buff)
    for buff in buffs:
        mempool.free_buffer(buff)
    return mempool


def run_packet_generator(args):
    mempool = init_mempool()
    dev = init_device(args.address)

    stats_old = Stats(dev.pci_device)
    stats_new = Stats(dev.pci_device)
    counter = 0
    last_stats_printed = time.perf_counter()

    seq_num = 0
    while True:
        buffers = mempool.get_buffers(BATCH_SIZE)
        for buffer in buffers:
            data_buffer = buffer.data_buffer
            struct.pack_into('I', data_buffer, PKT_SIZE-4, seq_num)
            seq_num += 1

        dev.tx_batch_busy_wait(buffers)

        if (counter & 0xFF) == 0:
            current_time = time.perf_counter()
            if current_time - last_stats_printed > 1:
                dev.read_stats(stats_new)
                stats_new.print_diff(stats_old, current_time - last_stats_printed)
                last_stats_printed = current_time
                stats_old = copy.copy(stats_new)
        counter += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('address', help='NIC Pci address e.g. 0000:00:08.0', type=str)
    args = parser.parse_args()
    try:
        run_packet_generator(args)
    except KeyboardInterrupt:
        log.info("Packet generator has been stopped")


if __name__ == '__main__':
    main()
