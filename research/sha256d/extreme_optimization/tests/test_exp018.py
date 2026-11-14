#!/usr/bin/env python3
"""Correctness gates for EXP-018 (Y-023):
register-resident dual-batch AVX-512 (libbal_r512).
Standard gate set from gates.py plus per-variant
group accounting checks.

Wave semantics: the variant is 32-group atomic with
the genesis winner (offset 50,000 from the probe
start) landing in the group that ends at 50,016, so
the exact early-exit attempted count is 50,016.
"""
import ctypes
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gates import FAILS, check, ref, run_gates, GENESIS, MAX_LE  # noqa: E402

SRC = os.path.join(HERE, "..", "src")

VARIANTS = [
  ("avx512_mb_reg", "libbal_r512.so", "r", 100016, 16),
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
    for label, libname, prefix, pbe, sbe in VARIANTS:
        if only and only != label:
            continue
        lib = ctypes.CDLL(os.path.join(SRC, libname))
        batch, search, seen = bind(lib, prefix)
        rng = random.Random(hash(label) & 0xFFFF)
        run_gates(label, batch, search, rng, wave_exact=50016)
        rc, att, raw, _f = batch(GENESIS, 0, 100003, 1, MAX_LE)
        check(f"{label} partial group accounting",
              rc == 0 and att == 100003 and seen[-1] == pbe,
              f"att={att} backend={seen[-1]} want={pbe}")
        ok = all(raw[32 * i:32 * i + 32] == ref(GENESIS, i)
                 for i in (0, 15, 16, 99999, 100002))
        check(f"{label} partial group spot digests", ok)
        rc, att, raw, _f = batch(GENESIS, 100, 5, 1, MAX_LE)
        check(f"{label} sub-group accounting",
              rc == 0 and att == 5 and seen[-1] == sbe,
              f"att={att} backend={seen[-1]} want={sbe}")
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
    print("ALL EXP-018 GATES PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
