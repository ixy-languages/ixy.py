#!/bin/bash

git clone --recursive https://github.com/emmericp/MoonGen
git clone https://github.com/ixy-languages/benchmark-scripts.git
cd MoonGen
./build.sh
./setup-hugetlbfs.sh
./bind-interfaces.sh
# ./build/MoonGen <path-to-this-repo>/ixy-bench.lua --help
