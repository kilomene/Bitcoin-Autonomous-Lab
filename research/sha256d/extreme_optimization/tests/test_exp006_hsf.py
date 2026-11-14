#!/usr/bin/env python3
"""EXP-006 correctness gates: schedule-first hand-scheduled
variant (src/h01_hsf.c, libbal_hsf.so), same mode ABI as
EXP-005. Gates run for streams 2, 3, 4 (blocked)."""
import ctypes
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gates import FAILS, check, run_gates  # noqa: E402

SRC = os.path.join(HERE, "..", "src")


def main():
    lib = ctypes.CDLL(os.path.join(SRC, "libbal_hsf.so"))
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

    def mk(streams):
        def batch(hdr, start, count, threads, target):
            h = ctypes.create_string_buffer(32 * max(count, 1))
            f = ctypes.create_string_buffer(max(count, 1))
            a = ctypes.c_uint64(0)
            rc = bfn(hdr, start, count, threads, streams, 0,
                     target, h, f, ctypes.byref(a))
            return rc, a.value, h.raw, f.raw

        def search(hdr, start, count, threads, target):
            n = ctypes.c_uint32(0)
            d = ctypes.create_string_buffer(32)
            a = ctypes.c_uint64(0)
            rc = sfn(hdr, start, count, threads, streams, 0,
                     target, ctypes.byref(n), d, ctypes.byref(a))
            return rc, n.value, d.raw, a.value
        return batch, search

    rng = random.Random(6006)
    wave_exact = {2: 2, 3: 50001, 4: 4}
    for streams in (2, 3, 4):
        batch, search = mk(streams)
        run_gates(f"hsf s={streams}", batch, search, rng,
                  wave_exact=wave_exact[streams])

    print()
    if FAILS:
        print("FAILED:", FAILS)
        return 1
    print("ALL EXP-006 SCHEDULE-FIRST GATES PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
