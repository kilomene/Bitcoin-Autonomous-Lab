#!/bin/bash
# EXP-032 research builds. Separate from the production
# build (mining/cpu/build.py); outputs land in this
# directory. Restricted flag sets throughout, never
# -march=native, so each binary is portable across hosts
# carrying the named extension set.
set -e
cd "$(dirname "$0")"
ROOT="$(cd ../../.. && pwd)"
CC=${CC:-gcc}

# AVX2 multi-buffer kernel (EXP-032 new work).
$CC -O3 -mavx2 -shared -fPIC -Wall -Wextra \
  -I "$ROOT/mining/cpu" \
  -o libbal_avx2.so src/avx2_mb.c -lpthread

# H-01 multi-stream SHA-NI kernel (Stage 5 research source,
# copied unchanged into src/; the copy is byte-identical to
# research/sha256d/experiments/h02_shani/h01_multistream.c).
$CC -O3 -msha -mssse3 -shared -fPIC -Wall -Wextra \
  -o libbal_h01.so src/h01_multistream.c -lpthread

# Flags-form search prototype: production flags kernel copy
# plus the EXP-032 bal_v_searchf2 addition. Built with the
# production restricted AVX-512 flag set.
$CC -O3 -mavx512f -mavx512bw -shared -fPIC -Wall -Wextra \
  -I "$ROOT/mining/cpu" \
  -o libbal_v512fsearch.so src/avx512_flags_search.c -lpthread

echo "built libbal_avx2.so libbal_h01.so libbal_v512fsearch.so"
