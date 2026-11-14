#!/usr/bin/env python3
"""EXP-003 (H-01) correctness gates for the multi-stream kernel.

Per stream count (1, 2, 4):
  - >= 100,000 randomized SHA-256d differentials vs hashlib.
  - Genesis digest and search.
  - Boundary nonces and ranges (max-only, ending at 2^32,
    crossing rejected, empty rejected, invalid streams rejected).
  - Odd counts not divisible by stream count or block size.
  - Accounting: batch attempted == count; search miss ==
    range; early exit reports true examined count under wave
    semantics (demonstrated exactly: a winner at scan position
    50,001 is found in ONE 4-stream wave, attempted == 4).
"""
import ctypes
import hashlib
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GENESIS = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GN = 2083236893
MAX_LE = ((1 << 256) - 1).to_bytes(32, "little")
DIFF1_LE = (0xFFFF << 208).to_bytes(32, "little")
FAILS = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")
    if not cond:
        FAILS.append(name)


def ref(hdr, n):
    return hashlib.sha256(hashlib.sha256(
        hdr[:76] + n.to_bytes(4, "little")).digest()).digest()


def main():
    lib = ctypes.CDLL(os.path.join(HERE, "libbal_h01.so"))
    bfn = lib.bal_m_batch2
    bfn.restype = ctypes.c_int
    bfn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                    ctypes.c_uint, ctypes.c_int, ctypes.c_char_p,
                    ctypes.c_char_p, ctypes.c_char_p,
                    ctypes.POINTER(ctypes.c_uint64)]
    sfn = lib.bal_m_search2
    sfn.restype = ctypes.c_int
    sfn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                    ctypes.c_uint, ctypes.c_int, ctypes.c_char_p,
                    ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
                    ctypes.POINTER(ctypes.c_uint64)]

    def mbatch(hdr, start, count, threads, streams, target):
        h = ctypes.create_string_buffer(32 * max(count, 1))
        f = ctypes.create_string_buffer(max(count, 1))
        a = ctypes.c_uint64(0)
        rc = bfn(hdr, start, count, threads, streams, target, h, f,
                 ctypes.byref(a))
        return rc, a.value, h.raw, f.raw

    def msearch(hdr, start, count, threads, streams, target):
        n = ctypes.c_uint32(0)
        d = ctypes.create_string_buffer(32)
        a = ctypes.c_uint64(0)
        rc = sfn(hdr, start, count, threads, streams, target,
                 ctypes.byref(n), d, ctypes.byref(a))
        return rc, n.value, d.raw, a.value

    rng = random.Random(424242)
    for streams in (1, 2, 4):
        total = 0
        bad = 0
        for _trial in range(9):
            hdr = bytes(rng.randbytes(80))
            start = rng.randrange(0, 2**31)
            count = 12000
            rc, att, raw, _f = mbatch(hdr, start, count, 2, streams,
                                      MAX_LE)
            if rc != 0 or att != count:
                bad += 1
                continue
            for i in range(count):
                if raw[32 * i:32 * i + 32] != ref(hdr, start + i):
                    bad += 1
                    break
            total += count
        check(f"streams={streams} randomized >=100k",
              bad == 0 and total >= 100_000,
              f"checked={total} bad={bad}")

        rc, att, raw, _f = mbatch(GENESIS, GN, 1, 1, streams, MAX_LE)
        check(f"streams={streams} genesis",
              rc == 0 and raw == ref(GENESIS, GN))
        rc, n, _d, _a = msearch(GENESIS, GN - 3, 10, 1, streams,
                                DIFF1_LE)
        check(f"streams={streams} genesis search",
              rc == 1 and n == GN, f"rc={rc} nonce={n}")

        ok = True
        for start, count in ((0xFFFFFFFE, 2), (0xFFFFFFFF, 1),
                             (0xFFFFF000, 0x1000), (0, 999), (5, 1)):
            rc, att, raw, _f = mbatch(GENESIS, start, count, 1,
                                      streams, MAX_LE)
            if rc != 0 or att != count:
                ok = False
                break
            for i in range(count):
                if raw[32 * i:32 * i + 32] != ref(GENESIS, start + i):
                    ok = False
                    break
        check(f"streams={streams} boundaries and odd counts", ok)
        rc, _a, _r, _f = mbatch(GENESIS, 0xFFFFFFFF, 2, 1, streams,
                                MAX_LE)
        check(f"streams={streams} crossing rejected", rc == -2)
        rc, _a, _r, _f = mbatch(GENESIS, 0, 0, 1, streams, MAX_LE)
        check(f"streams={streams} empty rejected", rc == -1)
        rc, _a, _r, _f = mbatch(GENESIS, 0, 10, 1, 3, MAX_LE)
        check(f"streams={streams} streams=3 rejected", rc == -1)

        rc, _n, _d, att = msearch(GENESIS, 0, 5000, 1, streams,
                                  DIFF1_LE)
        check(f"streams={streams} miss accounting",
              rc == 0 and att == 5000, f"att={att}")

    # Wave-semantics accounting, exact: streams=4, threads=1,
    # winner at offset 50,000 (first position of chunk 2) is
    # found in the first wave; attempted counts the whole wave.
    rc, n, dig, att = msearch(GENESIS, GN - 50000, 100000, 1, 4,
                              DIFF1_LE)
    check("wave accounting: winner at 50001st position, att == 4",
          rc == 1 and n == GN and att == 4,
          f"rc={rc} nonce={n} att={att}")
    want = ref(GENESIS, GN)
    check("wave accounting: winner digest verified", dig == want)

    print()
    if FAILS:
        print("FAILED:", FAILS)
        return 1
    print("ALL H-01 CORRECTNESS GATES PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
