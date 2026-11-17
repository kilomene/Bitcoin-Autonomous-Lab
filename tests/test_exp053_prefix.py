#!/usr/bin/env python3
"""EXP-053 Gate 2: correctness gates for the chunk-2
prefix-sharing dual walker (NOVA-ER-0013, Y-098, H-6).

Layers, in order:

  1. The shared extreme_optimization gate set
     (research/sha256d/extreme_optimization/tests/gates.py:
     >= 100,000 randomized SHA-256d differentials vs
     hashlib, genesis digest and search, boundaries,
     template variations, target equality and minus one,
     regtest-easy candidate set, exact accounting with
     the dual walker's wave semantics, wave_exact 50016)
     run on the variant's bal_vp_* entries.
  2. The same gate set run on the production library's
     bal_vd_* entries, as a harness control: the gate
     set itself must pass on the shipped kernel.
  3. Record-scale cross-backend differential:
     bal_vp_batch2 vs bal_vd_batch2 (production binary)
     byte-identical hashes and flags over 4,194,304
     digests across randomized headers, starts and
     thread counts, with attempted and backend
     accounting equal on every call. The prefix share
     is an exact identity, so any single differing byte
     is a defect.
  4. Search agreement under the EXP-047 corrected
     criterion: at threads=1 the variant returns the
     production nonce exactly on hit ranges; at threads
     2 and 4 the found flag agrees and every returned
     (nonce, digest) pair is genuine (digest equals the
     hashlib reference at that nonce and meets the
     target). First-publisher-wins across thread
     partitions is the documented production semantics
     (EXP-047), so cross-thread nonce equality is not
     asserted.

The variant library is built by
research/sha256d/exp053/build_variant.py; this suite
builds it if it is missing.
"""

import ctypes
import hashlib
import os
import random
import subprocess
import sys

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
EXP053 = os.path.join(ROOT, "research/sha256d/exp053")
VARIANT_LIB = os.path.join(EXP053, "src/libbal_e53prefix.so")
PROD_LIB = os.path.join(ROOT, ".local/cpu/libbal_v512dual.so")
sys.path.insert(0, os.path.join(
    ROOT, "research/sha256d/extreme_optimization/tests"))
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from gates import FAILS, check, ref, run_gates, GENESIS, MAX_LE  # noqa: E402
from bench_harness import DIFF1_LE  # noqa: E402

GN = 2083236893


def ensure_built():
    if not os.path.exists(VARIANT_LIB):
        proc = subprocess.run(
            [sys.executable,
             os.path.join(EXP053, "build_variant.py")],
            capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)
            raise SystemExit("variant build failed")


def bind(lib, prefix):
    bfn = getattr(lib, f"{prefix}_batch2")
    bfn.restype = ctypes.c_int
    bfn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                    ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
                    ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
                    ctypes.POINTER(ctypes.c_uint64)]
    sfn = getattr(lib, f"{prefix}_search2")
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

    def batch_full(hdr, start, count, threads, target):
        h = ctypes.create_string_buffer(32 * max(count, 1))
        f = ctypes.create_string_buffer(max(count, 1))
        a = ctypes.c_uint64(0)
        b = ctypes.c_uint64(0)
        rc = bfn(hdr, start, count, threads, target, h, f,
                 ctypes.byref(a), ctypes.byref(b))
        return rc, a.value, b.value, h.raw, f.raw

    def search(hdr, start, count, threads, target):
        n = ctypes.c_uint32(0)
        d = ctypes.create_string_buffer(32)
        a = ctypes.c_uint64(0)
        b = ctypes.c_uint64(0)
        rc = sfn(hdr, start, count, threads, target,
                 ctypes.byref(n), d, ctypes.byref(a),
                 ctypes.byref(b))
        return rc, n.value, d.raw, a.value

    return batch, batch_full, search


def cross_backend_differential(vp, vd, rng):
    total = 0
    bad = 0
    detail = ""
    # 16 blocks of 262,144 digests = 4,194,304 digests.
    for blk in range(16):
        hdr = bytes(rng.randbytes(80))
        start = rng.randrange(0, 2**31)
        count = 262_144
        threads = (1, 2, 3, 4)[blk % 4]
        target = MAX_LE if blk % 2 == 0 else DIFF1_LE
        rc1, a1, b1, h1, f1 = vp(hdr, start, count, threads, target)
        rc2, a2, b2, h2, f2 = vd(hdr, start, count, threads, target)
        if (rc1, a1, b1) != (rc2, a2, b2) or h1 != h2 or f1 != f2:
            bad += 1
            detail = (f"block {blk}: rc {rc1}/{rc2} attempted "
                      f"{a1}/{a2} backend {b1}/{b2} hashes "
                      f"{'same' if h1 == h2 else 'DIFFER'} flags "
                      f"{'same' if f1 == f2 else 'DIFFER'}")
            break
        total += count
    check("vp vs vd record-scale batch differential",
          bad == 0 and total == 4_194_304,
          f"digests={total} bad={bad} {detail}")


def search_agreement(vp_s, vd_s, rng):
    easy = (1 << 252).to_bytes(32, "little")
    ok_exact = True
    ok_agree = True
    detail = ""
    # threads=1: exact nonce equality on hit ranges.
    for trial in range(24):
        hdr = bytes(rng.randbytes(80))
        start = rng.randrange(0, 2**31)
        count = 4096
        r1 = vp_s(hdr, start, count, 1, easy)
        r2 = vd_s(hdr, start, count, 1, easy)
        if r1[0] != r2[0] or (r1[0] == 1 and r1[1] != r2[1]):
            ok_exact = False
            detail = (f"trial {trial}: rc {r1[0]}/{r2[0]} "
                      f"nonce {r1[1]}/{r2[1]}")
            break
        if r1[0] == 1 and r1[2] != ref(hdr, r1[1]):
            ok_exact = False
            detail = f"trial {trial}: returned digest not genuine"
            break
    check("vp vs vd search exact at threads=1", ok_exact, detail)
    # threads 2 and 4: found-flag agreement + genuineness.
    hits = 0
    for trial in range(48):
        hdr = bytes(rng.randbytes(80))
        start = rng.randrange(0, 2**31)
        count = 8192
        threads = 2 if trial % 2 == 0 else 4
        r1 = vp_s(hdr, start, count, threads, easy)
        if r1[0] == 1:
            hits += 1
            genuine = (r1[2] == ref(hdr, r1[1])
                       and int.from_bytes(r1[2], "little") <= (1 << 252))
            if not genuine:
                ok_agree = False
                detail = f"trial {trial}: vp hit not genuine"
                break
        r2 = vd_s(hdr, start, count, threads, easy)
        if (r1[0] == 1) != (r2[0] == 1):
            ok_agree = False
            detail = (f"trial {trial}: found flag vp={r1[0]} "
                      f"vd={r2[0]}")
            break
    check("vp vs vd search agreement at threads 2/4",
          ok_agree, f"vp hits={hits} {detail}")


def main():
    ensure_built()
    variant = ctypes.CDLL(VARIANT_LIB)
    prod = ctypes.CDLL(PROD_LIB)
    vp_batch, vp_full, vp_search = bind(variant, "bal_vp")
    vd_batch, vd_full, vd_search = bind(prod, "bal_vd")
    rng = random.Random(53053)

    run_gates("e53prefix", vp_batch, vp_search, rng,
              wave_exact=50016)
    run_gates("prod-dual-control", vd_batch, vd_search, rng,
              wave_exact=50016)
    cross_backend_differential(vp_full, vd_full, rng)
    search_agreement(vp_search, vd_search, rng)

    if FAILS:
        print(f"EXP-053 Gate 2: FAILED ({len(FAILS)} checks): "
              + ", ".join(FAILS))
        return 1
    print("EXP-053 Gate 2 suite: ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
