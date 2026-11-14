#!/usr/bin/env python3
"""EXP-007 correctness gates: AVX-512 16-way multi-buffer
SHA-256d (src/avx512_mb.c, libbal_v512.so). Standard gate
set plus lane-semantics checks: backend accounting on
partial final groups (dummy lanes computed, never counted
as coverage) and group-edge nonce boundaries."""
import ctypes
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gates import FAILS, check, ref, run_gates, GENESIS, MAX_LE  # noqa: E402

SRC = os.path.join(HERE, "..", "src")


def main():
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
    backend_seen = []

    def batch(hdr, start, count, threads, target):
        h = ctypes.create_string_buffer(32 * max(count, 1))
        f = ctypes.create_string_buffer(max(count, 1))
        a = ctypes.c_uint64(0)
        b = ctypes.c_uint64(0)
        rc = bfn(hdr, start, count, threads, target, h, f,
                 ctypes.byref(a), ctypes.byref(b))
        backend_seen.append((count, threads, b.value))
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

    rng = random.Random(7031)
    # Group-atomic early exit: winner offset 50000 is lane 0
    # of group 3125; attempted == 3126 * 16 == 50016.
    run_gates("v512", batch, search, rng, wave_exact=50016)

    # Partial-group accounting, single thread: backend is
    # padded to whole groups, coverage is exact.
    rc, att, raw, _f = batch(GENESIS, 0, 100003, 1, MAX_LE)
    cnt, _t, be = backend_seen[-1]
    check("v512 partial group accounting",
          rc == 0 and att == 100003 and be == 100016,
          f"att={att} backend={be}")
    ok = all(raw[32 * i:32 * i + 32] == ref(GENESIS, i)
             for i in (0, 15, 16, 99999, 100002))
    check("v512 partial group spot digests", ok)
    # count below one group
    rc, att, raw, _f = batch(GENESIS, 100, 5, 1, MAX_LE)
    cnt, _t, be = backend_seen[-1]
    check("v512 sub-group accounting",
          rc == 0 and att == 5 and be == 16,
          f"att={att} backend={be}")
    ok = all(raw[32 * i:32 * i + 32] == ref(GENESIS, 100 + i)
             for i in range(5))
    check("v512 sub-group digests", ok)
    # group-edge boundary: nonces straddling 2^32 - 16
    rc, att, raw, _f = batch(GENESIS, 0xFFFFFFF0, 16, 1, MAX_LE)
    ok = rc == 0 and att == 16 and all(
        raw[32 * i:32 * i + 32] == ref(GENESIS, 0xFFFFFFF0 + i)
        for i in range(16))
    check("v512 group-edge at 2^32", ok)

    print()
    if FAILS:
        print("FAILED:", FAILS)
        return 1
    print("ALL EXP-007 AVX-512 GATES PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
