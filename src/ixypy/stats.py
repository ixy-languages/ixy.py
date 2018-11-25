class StatsDiff(object):
    def __init__(self, packets, bytes_, interval, channel, address):
        self.packets = packets
        self.bytes_ = bytes_
        self.channel = channel
        self.address = address
        self.interval = interval

    def _mpps(self, packets):
        return packets / 1000000.0 / self.interval / 1000000000.0

    def _mbit(self, bytes_, packets):
        return (bytes_ / 1000000.0 / self.interval / 1000000000.0) * 8 + self._mpps(packets) * 20 * 8

    def __str__(self):
        return '[{0}] {1}: {2:.2f} Mbit/s {3:.2f} Mpps'.format(self.address,
                                                               self.channel,
                                                               self.bytes,
                                                               self.packets)


class Stats(object):
    def __init__(self, pci_address, rx_pkts=0, tx_pkts=0, rx_bytes=0, tx_bytes=0):
        self.pci_address = pci_address
        self.rx_pkts = rx_pkts
        self.tx_pkts = tx_pkts
        self.rx_bytes = rx_bytes
        self.tx_bytes = tx_bytes

    def __str__(self):
        rx = '[{0}] RX: {1} bytes {2} packets'.format(self.pci_address, self.rx_pkts, self.rx_bytes)
        tx = '[{0}] TX: {1} bytes {2} packets'.format(self.pci_address, self.tx_pkts, self.tx_bytes)
        return '{}\n{}'.format(rx, tx)

    def diff(self, other, interval):
        tx_pkts_diff, rx_pkts_diff = self.tx_pkts - other.tx_pkts, self.rx_pkts - other.rx_pkts
        tx_bytes_diff, rx_bytes_diff = self.tx_bytes - other.tx_bytes, self.rx_bytes - other.rx_bytes
        tx_diff = StatsDiff(tx_pkts_diff, tx_bytes_diff, interval, 'TX', self.address)
        rx_diff = StatsDiff(rx_pkts_diff, rx_bytes_diff, interval, 'RX', self.address)
        return tx_diff, rx_diff
