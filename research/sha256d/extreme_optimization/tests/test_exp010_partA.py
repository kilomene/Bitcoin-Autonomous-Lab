#!/usr/bin/env python3
"""EXP-010 (Part A decision closure) correctness gates.

The three decision contenders must each pass the full
shared gate set (tests/gates.py) before any benchmark
number is taken:

  1. production C (trusted baseline, .local/cpu
     libbal_batch.so, bal_c_batch2 / bal_c_search2)
  2. H-01 streams=4 strided (src/h01_geo.c,
     libbal_geo.so, mode=1)
  3. AVX-512 16-way multi-buffer (src/avx512_mb.c,
     libbal_v512.so)

Wave-exact early-exit expectations are the ones already
established for these kernels: strided s=4 gives 50004,
the multi-buffer group-atomic semantics give 50016. For
production C the counted search walks a single span in
order at threads=1, so attempted == 50001.
"""
import ctypes
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gates import FAILS, run_gates  # noqa: E402

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
SRC = os.path.join(HERE, "..", "src")
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import load_lib  # noqa: E402


def production():
    _lib, b2, s2 = load_lib(f"{ROOT}/.local/cpu/libbal_batch.so",
                            "bal_c")

    def batch(hdr, start, count, threads, target):
        h = ctypes.create_string_buffer(32 * max(count, 1))
        f = ctypes.create_string_buffer(max(count, 1))
        a = ctypes.c_uint64(0)
        rc = b2(hdr, start, count, threads, target, h, f,
                ctypes.byref(a))
        return rc, a.value, h.raw, f.raw

    def search(hdr, start, count, threads, target):
        n = ctypes.c_uint32(0)
        d = ctypes.create_string_buffer(32)
        a = ctypes.c_uint64(0)
        rc = s2(hdr, start, count, threads, target,
                ctypes.byref(n), d, ctypes.byref(a))
        return rc, n.value, d.raw, a.value
    return batch, search


def geo_strided4():
    lib = ctypes.CDLL(os.path.join(SRC, "libbal_geo.so"))
    bfn = lib.bal_m_batch2m
    bfn.restype = ctypes.c_int
    bfn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                    ctypes.c_uint, ctypes.c_int, ctypes.c_int,
                    ctypes.c_char_p, ctypes.c_char_p,
                    ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)]
    sfn = lib.bal_m_search2m
    sfn.restype = ctypes.c_int
    sfn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                    ctypes.c_uint, ctypes.c_int, ctypes.c_int,
                    ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32),
                    ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)]

    def batch(hdr, start, count, threads, target):
        h = ctypes.create_string_buffer(32 * max(count, 1))
        f = ctypes.create_string_buffer(max(count, 1))
        a = ctypes.c_uint64(0)
        rc = bfn(hdr, start, count, threads, 4, 1,
                 target, h, f, ctypes.byref(a))
        return rc, a.value, h.raw, f.raw

    def search(hdr, start, count, threads, target):
        n = ctypes.c_uint32(0)
        d = ctypes.create_string_buffer(32)
        a = ctypes.c_uint64(0)
        rc = sfn(hdr, start, count, threads, 4, 1,
                 target, ctypes.byref(n), d, ctypes.byref(a))
        return rc, n.value, d.raw, a.value
    return batch, search


def v512():
    lib = ctypes.CDLL(os.path.join(SRC, "libbal_v512.so"))
    bfn = lib.bal_v_batch2
    bfn.restype = ctypes.c_int
    bfn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                    ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
                    ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
                    ctypes.POINTER(ctypes.c_uint64)]
    sfn = lib.bal_v_search2
    sfn.restype = ctypes.c_int
    sfn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                    ctypes.c_uint, ctypes.c_char_p,
                    ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
                    ctypes.POINTER(ctypes.c_uint64),
                    ctypes.POINTER(ctypes.c_uint64)]

    def batch(hdr, start, count, threads, target):
        h = ctypes.create_string_buffer(32 * max(count, 1))
        f = ctypes.create_string_buffer(max(count, 1))
        a = ctypes.c_uint64(0)
        b = ctypes.c_uint64(0)
        rc = bfn(hdr, start, count, threads, target, h, f,
                 ctypes.byref(a), ctypes.byref(b))
        return rc, a.value, h.raw, f.raw

    def search(hdr, start, count, threads, target):
        n = ctypes.c_uint32(0)
        d = ctypes.create_string_buffer(32)
        a = ctypes.c_uint64(0)
        b = ctypes.c_uint64(0)
        rc = sfn(hdr, start, count, threads, target,
                 ctypes.byref(n), d, ctypes.byref(a),
                 ctypes.byref(b))
        return rc, n.value, d.raw, a.value
    return batch, search


def main():
    rng = random.Random(1010)
    batch, search = production()
    run_gates("production_c", batch, search, rng,
              wave_exact=50001)
    batch, search = geo_strided4()
    run_gates("geo_s4_strided", batch, search, rng,
              wave_exact=50004)
    batch, search = v512()
    run_gates("v512_mb16", batch, search, rng,
              wave_exact=50016)

    print()
    if FAILS:
        print("FAILED:", FAILS)
        return 1
    print("ALL EXP-010 PART A GATES PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
