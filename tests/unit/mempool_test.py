import pytest

from unittest.mock import Mock

from ixypy.mempool import Mempool


def test_mempool_instance_count():
    dma = Mock()

    mempool = Mempool(dma=dma, buffer_size=256, num_entries=50000)

    assert mempool.id in Mempool.pools
