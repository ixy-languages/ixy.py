from distutils.core import setup, Extension
from Cython.Build import cythonize

setup(
    packages=["ixypy"],
    ext_modules=cythonize([Extension("memory", sources=["memory.pyx", "mem.c"])])
)
