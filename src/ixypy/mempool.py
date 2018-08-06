class Mempool(object):
    mempools = {}

    def __init__(self, base_address, buffer_size, num_entries, pool_id=None):
        self.pool_id = self._next_id() if pool_id is None else pool_id
        self.base_addr = base_address
        self.buffer_size = buffer_size
        self.num_entries = num_entries

    def __hash__(self):
        return self.pool_id

    @staticmethod
    def _next_id():
        return 1
