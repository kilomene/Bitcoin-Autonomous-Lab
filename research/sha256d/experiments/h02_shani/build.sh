#!/bin/bash
# Build the H-02 / H-01 research libraries. Separate from the
# production build; outputs land in this directory.
set -e
cd "$(dirname "$0")"
CC=${CC:-gcc}
BASE="-O3 -march=native -msha -shared -fPIC -Wall -Wextra"
$CC $BASE -o libbal_h02.so h02_shani.c -lpthread
$CC $BASE -DBAL_H_SCALAR_SCHED -o libbal_h02_scalar.so h02_shani.c -lpthread
$CC $BASE -o libbal_h01.so h01_multistream.c -lpthread
echo "built libbal_h02.so libbal_h02_scalar.so libbal_h01.so"
