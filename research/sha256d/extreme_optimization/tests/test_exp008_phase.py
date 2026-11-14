#!/usr/bin/env python3
"""EXP-008 correctness gates: cross-nonce phase pipelining
(src/h01_phase.c, libbal_phase.so). Standard gate set; the
declared early-exit semantics are attempted == winner
offset + 1 (digests completed), asserted exactly."""
import ctypes
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gates import FAILS, run_gates  # noqa: E402

SRC = os.path.join(HERE, "..", "src")


def main():
    lib = ctypes.CDLL(os.path.join(SRC, "libbal_phase.so"))
    bfn = lib.bal_p_batch2
    bfn.restype = ctypes.c_int
    bfn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                    ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
                    ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)]
    sfn = lib.bal_p_search2
    sfn.restype = ctypes.c_int
    sfn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                    ctypes.c_uint, ctypes.c_char_p,
                    ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
                    ctypes.POINTER(ctypes.c_uint64)]

    def batch(hdr, start, count, threads, target):
        h = ctypes.create_string_buffer(32 * max(count, 1))
        f = ctypes.create_string_buffer(max(count, 1))
        a = ctypes.c_uint64(0)
        rc = bfn(hdr, start, count, threads, target, h, f,
                 ctypes.byref(a))
        return rc, a.value, h.raw, f.raw

    def search(hdr, start, count, threads, target):
        n = ctypes.c_uint32(0)
        d = ctypes.create_string_buffer(32)
        a = ctypes.c_uint64(0)
        rc = sfn(hdr, start, count, threads, target,
                 ctypes.byref(n), d, ctypes.byref(a))
        return rc, n.value, d.raw, a.value

    rng = random.Random(8009)
    run_gates("phase", batch, search, rng, wave_exact=50001)

    print()
    if FAILS:
        print("FAILED:", FAILS)
        return 1
    print("ALL EXP-008 PHASE-PIPELINE GATES PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
