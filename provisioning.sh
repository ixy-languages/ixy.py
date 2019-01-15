#!/bin/bash


echo "System update ============>"
apt-get update


echo "Dev tool installation ============>"
# Install development tools
apt-get install -q -y make cmake build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev gdb
apt-get install -q -y wget curl llvm libncurses5-dev libncursesw5-dev xz-utils tk-dev pciutils vim git


# Install Python 3
PYTHON_VERSION=3.7.2
PYTHON_DIR="Python-$PYTHON_VERSION"
echo "Python $PYTHON_VERSION installation ============>"
wget "https://www.python.org/ftp/python/$PYTHON_VERSION/$PYTHON_DIR.tgz"
tar xvf "$PYTHON_DIR.tgz"
rm "$PYTHON_DIR.tgz"
cd $PYTHON_DIR
./configure --enable-optimizations
make -j8
make altinstall
cd ..
rm -fr $PYTHON_DIR


echo "pip installation ============>"
wget https://bootstrap.pypa.io/get-pip.py
python3.7 get-pip.py
rm -f get-pip.py


echo "pypy installation ============>"
wget -q -P /tmp https://bitbucket.org/pypy/pypy/downloads/pypy3-v6.0.0-linux64.tar.bz2
tar -x -C /opt -f /tmp/pypy3-v6.0.0-linux64.tar.bz2
rm /tmp/pypy3-v6.0.0-linux64.tar.bz2
mv /opt/pypy3-v6.0.0-linux64 /opt/pypy3
ln -fs /opt/pypy3/bin/pypy3 /usr/bin/pypy3


echo "Install necessary python dependencies"
pip3 install tox pytest cython ipython

