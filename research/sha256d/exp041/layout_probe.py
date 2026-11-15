#!/usr/bin/env python3
"""Diagnostic (NOT an EXP-017 verdict): does the rebuild
control effect follow the library file or the load order?

Usage: layout_probe.py <mode>
  mode solo_prod / solo_base: load only that library.
  mode both_prod_first / both_base_first: load both,
    time both.
Times 120 alternating counted batch calls of 65,536
hashes at 2 threads per library after 10 warmups, in
one process, and prints median rates.
"""
import ctypes
import os
import statistics
import sys
import time

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import GENESIS, DIFF1_LE  # noqa: E402

PROD = os.path.join(ROOT, ".local/cpu/libbal_v512.so")
BASE = os.path.join(ROOT, "research/sha256d/exp041/src/libbal_e41base.so")
COUNT = 65_536


def bind(path, prefix):
    lib = ctypes.CDLL(path)
    fn = getattr(lib, f"bal_{prefix}_batch2")
    fn.restype = ctypes.c_int
    fn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                   ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
                   ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
                   ctypes.POINTER(ctypes.c_uint64)]
    return fn


def call(fn, start):
    hashes = ctypes.create_string_buffer(32 * COUNT)
    flags = ctypes.create_string_buffer(COUNT)
    a = ctypes.c_uint64(0)
    b = ctypes.c_uint64(0)
    t0 = time.perf_counter()
    rc = fn(GENESIS, start, COUNT, 2, DIFF1_LE, hashes, flags,
            ctypes.byref(a), ctypes.byref(b))
    dt = time.perf_counter() - t0
    assert rc == 0 and a.value == COUNT
    return COUNT / dt


def timed(fn, label, reps=120):
    for i in range(10):
        call(fn, i * COUNT)
    rates = [call(fn, (1000 + i) * COUNT) for i in range(reps)]
    print(f"{label}: median {statistics.median(rates)/1e6:.3f} MH/s "
          f"min {min(rates)/1e6:.3f} max {max(rates)/1e6:.3f}")
    return statistics.median(rates)


def main():
    mode = sys.argv[1]
    if mode == "solo_prod":
        timed(bind(PROD, "v"), "prod")
    elif mode == "solo_base":
        timed(bind(BASE, "e41base"), "base")
    elif mode == "both_prod_first":
        fp = bind(PROD, "v")
        fb = bind(BASE, "e41base")
        timed(fp, "prod")
        timed(fb, "base")
    elif mode == "both_base_first":
        fb = bind(BASE, "e41base")
        fp = bind(PROD, "v")
        timed(fb, "base")
        timed(fp, "prod")
    else:
        raise SystemExit(mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
