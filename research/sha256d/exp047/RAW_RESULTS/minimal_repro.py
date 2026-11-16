#!/usr/bin/env python3
"""Minimal repro for the EXP-047 critical finding.

The predeclared campaign criterion S-C required
search_first_counted to return the span minimum, identically
on every backend. On the exact campaign case S_FULL-00
(genesis header, target 2^256 - 1, start 2083204125, count
65536) the v512 engine returned nonce 2083236893 instead
(mismatch.json). Mechanism, from production source:
mining/cpu/bal_search.h bal_ctx_publish is
first-publisher-wins over per-thread spans (bal_partition);
every native search ABI uses it, so when several thread spans
hold hits, which genuine hit is returned is
scheduling-dependent. At density 1 every span holds hits, so
the divergence reproduces within a few calls on a
multithreaded engine. The returned hit is always genuine
(digest verifies, meets target); only its identity as the
minimum is not guaranteed. Single-threaded, the same call
returns the minimum deterministically.

Run from the repo root. Exit 0 if the divergence reproduces
within MAX_TRIES calls, 1 if it does not (possible on an
idle single run; rerun under load), 2 on a false miss, 3 on
a wrong digest.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..")))

from gpu.engine import ComputeEngine, cpu_digest  # noqa: E402

GENESIS = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
START = 2083236893 - 32768
COUNT = 65536
TARGET = (1 << 256) - 1
MAX_TRIES = 500

eng = ComputeEngine(requested="v512")
print(f"v512 engine, threads {eng.c_threads}; span minimum "
      f"is {START}")
for i in range(MAX_TRIES):
    hit, _a, _s = eng.search_first_counted(
        GENESIS, TARGET, START, COUNT)
    if hit is None:
        print("call", i, "returned NO hit at density 1: "
              "false miss")
        sys.exit(2)
    if hit[1] != cpu_digest(GENESIS, hit[0]):
        print("call", i, "returned a WRONG digest for nonce",
              hit[0])
        sys.exit(3)
    if hit[0] != START:
        print(f"call {i}: returned genuine hit {hit[0]} "
              f"(offset +{hit[0] - START}), not the span "
              f"minimum {START}: DIVERGENCE REPRODUCED")
        sys.exit(0)
print(f"no divergence in {MAX_TRIES} calls (the minimum won "
      "every race this run); the campaign observation stands "
      "in mismatch.json")
sys.exit(1)
