#!/bin/bash
# Build the extreme_optimization experiment libraries.
# Separate from the production build; outputs land here.
set -e
cd "$(dirname "$0")"
CC=${CC:-gcc}
BASE="-O3 -march=native -msha -shared -fPIC -Wall -Wextra"
$CC $BASE -o libbal_geo.so h01_geo.c -lpthread
$CC $BASE -o libbal_hsf.so h01_hsf.c -lpthread
$CC $BASE -o libbal_phase.so h01_phase.c -lpthread
$CC -O3 -march=native -shared -fPIC -Wall -Wextra \
  -o libbal_v512.so avx512_mb.c -lpthread
$CC -O3 -march=native -Wall -Wextra -o freq_gate freq_gate.c
echo "built libbal_geo.so libbal_hsf.so libbal_phase.so libbal_v512.so freq_gate"
