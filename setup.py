import io
from os.path import dirname
from os.path import join

from setuptools import setup, Extension, find_packages
from Cython.Build import cythonize


def read(*names, **kwargs):
    return io.open(
        join(dirname(__file__), *names),
        encoding=kwargs.get('encoding', 'utf8')
    ).read()


extentions = [
    Extension("memory", sources=['src/cython/memory/memory.pyx', 'src/cython/memory/mem.c']),
    Extension("vring", sources=['src/cython/virtio/virtio.pyx']),
    Extension("buff", sources=['src/cython/buff/buff.pyx'])]


setup(
    name="ixypy",
    version="0.0.1",
    author="Alexandru Obada",
    author_email="alexandru.obad@gmail.com",
    description="Some description",
    long_description=read('README.md'),
    license="MIT",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Topic :: Utilities",
        "License :: OSI Approved :: BSD License",
    ],
    include_package_data=True,
    install_requires=[],
    setup_requires=[],
    packages=find_packages('src'),
    package_dir={'': 'src'},
    ext_modules=cythonize(extentions, annotate=True))
