#!/usr/bin/env python3
"""Correctness gates for EXP-041 variants.

The standard gate set from extreme_optimization/tests/
gates.py (>= 100,000 randomized SHA-256d differentials
vs hashlib, genesis digest and search, boundaries,
template variations, target equality and minus-one,
candidate-set equality, accounting) plus the EXP-020
per-variant group accounting checks. Wave semantics
are identical to the production kernel (16-group
atomic), so the genesis early-exit attempted count is
exactly 50,016, partial-group backend is 100,016 at
count 100,003 and 16 at count 5.
"""
import ctypes
import os
import random
import sys

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(
    ROOT, "research/sha256d/extreme_optimization/tests"))
from gates import FAILS, check, ref, run_gates, GENESIS, MAX_LE  # noqa: E402

SRC = os.path.join(HERE, "src")

VARIANTS = [
    ("base", "libbal_e41base.so", "e41base"),
    ("alta", "libbal_e41alta.so", "e41alta"),
    ("altb", "libbal_e41altb.so", "e41altb"),
    ("altc", "libbal_e41altc.so", "e41altc"),
    ("tmaj", "libbal_e41tmaj.so", "e41tmaj"),
    ("tfull", "libbal_e41tfull.so", "e41tfull"),
]


def bind(lib, prefix):
    bfn = getattr(lib, f"bal_{prefix}_batch2")
    bfn.restype = ctypes.c_int
    bfn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                    ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
                    ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
                    ctypes.POINTER(ctypes.c_uint64)]
    sfn = getattr(lib, f"bal_{prefix}_search2")
    sfn.restype = ctypes.c_int
    sfn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                    ctypes.c_uint, ctypes.c_char_p,
                    ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
                    ctypes.POINTER(ctypes.c_uint64),
                    ctypes.POINTER(ctypes.c_uint64)]
    seen = []

    def batch(hdr, start, count, threads, target):
        h = ctypes.create_string_buffer(32 * max(count, 1))
        f = ctypes.create_string_buffer(max(count, 1))
        a = ctypes.c_uint64(0)
        b = ctypes.c_uint64(0)
        rc = bfn(hdr, start, count, threads, target, h, f,
                 ctypes.byref(a), ctypes.byref(b))
        seen.append(b.value)
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

    return batch, search, seen


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for idx, (label, libname, prefix) in enumerate(VARIANTS):
        if only and only != label:
            continue
        lib = ctypes.CDLL(os.path.join(SRC, libname))
        batch, search, seen = bind(lib, prefix)
        rng = random.Random(4100 + idx)
        run_gates(label, batch, search, rng, wave_exact=50016)
        rc, att, raw, _f = batch(GENESIS, 0, 100003, 1, MAX_LE)
        check(f"{label} partial group accounting",
              rc == 0 and att == 100003 and seen[-1] == 100016,
              f"att={att} backend={seen[-1]} want=100016")
        ok = all(raw[32 * i:32 * i + 32] == ref(GENESIS, i)
                 for i in (0, 15, 16, 99999, 100002))
        check(f"{label} partial group spot digests", ok)
        rc, att, raw, _f = batch(GENESIS, 100, 5, 1, MAX_LE)
        check(f"{label} sub-group accounting",
              rc == 0 and att == 5 and seen[-1] == 16,
              f"att={att} backend={seen[-1]} want=16")
        ok = all(raw[32 * i:32 * i + 32] == ref(GENESIS, 100 + i)
                 for i in range(5))
        check(f"{label} sub-group digests", ok)
        rc, att, raw, _f = batch(GENESIS, 0xFFFFFFF0, 16, 1, MAX_LE)
        ok = rc == 0 and att == 16 and all(
            raw[32 * i:32 * i + 32] == ref(GENESIS, 0xFFFFFFF0 + i)
            for i in range(16))
        check(f"{label} group-edge at 2^32", ok)
    print()
    if FAILS:
        print("FAILED:", FAILS)
        return 1
    print("ALL EXP-041 GATES PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
