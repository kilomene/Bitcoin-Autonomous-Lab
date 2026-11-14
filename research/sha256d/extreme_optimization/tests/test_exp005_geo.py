#!/usr/bin/env python3
"""EXP-005 correctness gates: stream geometry extension of
the H-01 kernel (streams 1, 2, 3, 4, 6; blocked and strided
assignment), via libbal_geo.so (src/h01_geo.c)."""
import ctypes
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gates import FAILS, check, run_gates  # noqa: E402

SRC = os.path.join(HERE, "..", "src")


def main():
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

    def mk(streams, mode):
        def batch(hdr, start, count, threads, target):
            h = ctypes.create_string_buffer(32 * max(count, 1))
            f = ctypes.create_string_buffer(max(count, 1))
            a = ctypes.c_uint64(0)
            rc = bfn(hdr, start, count, threads, streams, mode,
                     target, h, f, ctypes.byref(a))
            return rc, a.value, h.raw, f.raw

        def search(hdr, start, count, threads, target):
            n = ctypes.c_uint32(0)
            d = ctypes.create_string_buffer(32)
            a = ctypes.c_uint64(0)
            rc = sfn(hdr, start, count, threads, streams, mode,
                     target, ctypes.byref(n), d, ctypes.byref(a))
            return rc, n.value, d.raw, a.value
        return batch, search

    rng = random.Random(5150)
    # Wave-exact early exit (threads=1, start=GN-50000,
    # count=100000), derived from bal_partition's ceil
    # chunks. Blocked: s=2, 4 put the winner at a chunk
    # head (attempted == s). s=1: the single stream walks
    # offsets in order, so the winner is examined 50,001st
    # (attempted == 50001). s=3: winner is chunk 1 element
    # 16666, all streams live: 3 * 16667 = 50001. s=6: the
    # winner is the last element of chunk 2 and the short
    # final chunk drains first: attempted == 100000 exactly.
    # Strided s=4: winner offset 50000 is stream 0's element
    # 12500, all streams live: 4 * 12501 = 50004.
    wave_exact = {(1, 0): 50001, (2, 0): 2, (3, 0): 50001,
                  (4, 0): 4, (6, 0): 100000, (4, 1): 50004}
    for streams in (1, 2, 3, 4, 6):
        for mode in (0, 1):
            batch, search = mk(streams, mode)
            run_gates(f"geo s={streams} mode={mode}", batch, search,
                      rng, wave_exact=wave_exact.get((streams, mode)))

    batch, search = mk(5, 0)
    rc, _a, _r, _f = batch(b"\x00" * 80, 0, 10, 1,
                           ((1 << 256) - 1).to_bytes(32, "little"))
    check("geo streams=5 rejected", rc == -1, f"rc={rc}")
    batch, search = mk(4, 2)
    rc, _a, _r, _f = batch(b"\x00" * 80, 0, 10, 1,
                           ((1 << 256) - 1).to_bytes(32, "little"))
    check("geo mode=2 rejected", rc == -1, f"rc={rc}")

    print()
    if FAILS:
        print("FAILED:", FAILS)
        return 1
    print("ALL EXP-005 GEOMETRY GATES PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
