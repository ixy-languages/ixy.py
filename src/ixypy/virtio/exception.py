from ixypy.ixy import IxyException


class VirtioException(IxyException):
    pass


class BufferSizeException(VirtioException):
    pass
