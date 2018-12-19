#!/bin/bash

# Fail on first error
set -e

HOST=$1

if [[ $HOST ]]; then
    echo "Requested allocation of node $HOST"
else
    echo "Host not specified"
    exit 1
fi
IMAGE=debian-stretch

echo "Freeing node $HOST"
pos allocations free -f $HOST
echo "Allocating node $NODE"
pos allocations allocate $HOST
echo "Installing image<$IMAGE>"
pos node image $HOST $IMAGE
echo "Resetting"
pos node reset $HOST
echo "Node ready for operations"
