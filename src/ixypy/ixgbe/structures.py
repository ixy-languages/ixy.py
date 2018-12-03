class Queue(object):

    def __init__(self, count):
        self.count = count
        self.index = 0

class RxQueue(Queue):
    def __init__(self, count):
        super().__init__(count)
