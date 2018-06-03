import mmap


def test_write_to_mmap_file(tmpdir):
    # GIVEN
    tmp_file = tmpdir.join('mmap_file.txt')
    tmp_file.write('This is the content')
    fd = tmp_file.open(mode='r+b')

    # WHEN
    mm = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_WRITE)
    mm[:5] = b'That '

    # THAN
    assert tmp_file.read() == 'That is the content'
