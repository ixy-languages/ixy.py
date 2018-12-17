class Stats(object):
    def __init__(self, device, rxp=0, txp=0, rxb=0, txb=0):
        self.device = device
        self.rx_packets = rxp
        self.tx_packets = txp
        self.rx_bytes = rxb
        self.tx_bytes = txb

    def reset(self):
        self.rx_packets = 0
        self.tx_packets = 0
        self.rx_bytes = 0
        self.tx_bytes = 0

    def print_stats(self):
        print('{0} RX: {1} bytes {2} packets\n'.format(self.device.address, self.rx_bytes, self.rx_packets))
        print('{0} TX: {1} bytes {2} packets\n'.format(self.device.address, self.tx_bytes, self.tx_packets))

    @staticmethod
    def _diff_mpps(pkt_new, pkt_old, interval):
        return (pkt_new - pkt_old)/ 1000000.0 / (interval/1000000000.0)

    @staticmethod
    def _diff_mbit(bytes_new, bytes_old, pkt_new, pkt_old, interval):
        mpps = Stats._diff_mpps(pkt_new, pkt_old, interval) * 20 * 8
        # 10000 mbit/s + preamble
        return ((bytes_new - bytes_old) / 1000000.0 / (interval / 1000000000.0)) * 8 + mpps

    def print_diff(self, other, interval):
        rx_diff_mbit = self._diff_mbit(self.rx_bytes, other.rx_bytes, self.rx_packets, other.rx_packets, interval)
        rx_diff_mpps = self._diff_mpps(self.rx_packets, other.rx_packets, interval)
        tx_diff_mbit = self._diff_mbit(self.tx_bytes, other.tx_bytes, self.tx_packets, other.tx_packets, interval)
        tx_diff_mpps = self._diff_mpps(self.tx_packets, other.tx_packets, interval)
        print('{0} RX: {1} Mbit/s {2} Mpps\n'.format(self.device.address, rx_diff_mbit, rx_diff_mpps))
        print('{0} TX: {1} Mbit/s {2} Mpps\n'.format(self.device.address, tx_diff_mbit, tx_diff_mpps))
