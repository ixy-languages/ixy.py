def dump(buff, path):
    with open('dumps/{}'.format(path), 'wb') as f:
        f.write(buff)
