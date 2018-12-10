class Queue(object):
    def __init__(self, num_entries, identifier):
        self.num_entries = num_entries
        self.identifier = identifier


class RxQueue(Queue):
    def __init__(self, num_entries, identifier, memory):
        super().__init__(num_entries, identifier)


class TxQueue(Queue):
    def __init__(self, num_entries, identifier, memory):
        super().__init__(num_entries, identifier)
