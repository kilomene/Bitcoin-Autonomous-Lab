#!/usr/bin/env python3
"""EXP-054 sizing probe: production arm only.

300 self-paired production dual-search calls at the
EXP-017 block size (65,536), threads 2, genesis header,
target integer 1 (never met). Both arms of every pair
are the shipped production entry bal_vd_search2 of
.local/cpu/libbal_v512dual.so; no research-library
entry is loaded or timed by this probe, so no
candidate rate is observed before the predeclaration
is written. Output: RAW_RESULTS/sizing_probe.json with
the per-pair log-ratio standard deviation and the pair
counts the predeclaration's session design is derived
from, in the EXP-053 probe's format, extended with the
Bonferroni-corrected (family of 3 candidate
comparisons, per-comparison alpha 0.05/3, two-sided
z = 2.394) sizing rows the EXP-054 design uses.
"""
import ctypes
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import GENESIS  # noqa: E402

BLOCK = 65_536
THREADS = 2
PAIRS = 300
NO_HIT_TARGET_LE = (1).to_bytes(32, "little")
Z95 = 1.959964
Z_BONF = 2.393980  # two-sided alpha 0.05/3


def main():
    lib = ctypes.CDLL(os.path.join(ROOT, ".local/cpu/libbal_v512dual.so"))
    fn = lib.bal_vd_search2
    fn.restype = ctypes.c_int
    fn.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]

    def call(start):
        nonce = ctypes.c_uint32(0)
        digest = ctypes.create_string_buffer(32)
        attempted = ctypes.c_uint64(0)
        backend = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = fn(GENESIS, start, BLOCK, THREADS, NO_HIT_TARGET_LE,
                ctypes.byref(nonce), digest,
                ctypes.byref(attempted), ctypes.byref(backend))
        dt = time.perf_counter() - t0
        assert rc == 0 and attempted.value == BLOCK \
            and backend.value == BLOCK, (rc, attempted.value,
                                          backend.value)
        return BLOCK / dt

    for i in range(16):  # warmup, untimed shape only
        call(i * BLOCK)
    ratios = []
    walls = []
    t_all = time.perf_counter()
    for i in range(PAIRS):
        start = (16 + i) * BLOCK
        t0 = time.perf_counter()
        ra = call(start)
        rb = call(start)
        walls.append(time.perf_counter() - t0)
        ratios.append(math.log(rb / ra))
    total = time.perf_counter() - t_all
    sd = statistics.stdev(ratios)

    def pairs_for(z, halfwidth):
        return math.ceil((z * sd / halfwidth) ** 2)

    out = {
        "probe": "EXP-054 sizing probe, production arm only",
        "utc": datetime.now(timezone.utc).isoformat(),
        "block": BLOCK,
        "threads": THREADS,
        "pairs": PAIRS,
        "loadavg_at_probe": open("/proc/loadavg").read().split()[:3],
        "self_pair_log_ratio_mean": statistics.mean(ratios),
        "self_pair_log_ratio_sd": sd,
        "mean_pair_wall_s": statistics.mean(walls),
        "median_pair_wall_s": statistics.median(walls),
        "total_wall_s": total,
        "sizing": {
            "pairs_for_pooled_halfwidth_0.006_z95":
                pairs_for(Z95, 0.006),
            "pairs_for_session_halfwidth_0.008_z95":
                pairs_for(Z95, 0.008),
            "pairs_for_pooled_halfwidth_0.008_bonferroni_z2.394":
                pairs_for(Z_BONF, 0.008),
            "pairs_for_pooled_halfwidth_0.0075_bonferroni_z2.394":
                pairs_for(Z_BONF, 0.0075),
            "pairs_for_pooled_halfwidth_0.007_bonferroni_z2.394":
                pairs_for(Z_BONF, 0.007),
        },
    }
    path = os.path.join(HERE, "RAW_RESULTS", "sizing_probe.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)
    print(json.dumps(out, indent=2))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
