#!/usr/bin/env python3
"""EXP-024 correctness gates for the AVX-512 mask-based
early-exit search (designs B, C and the D/E scan arm).

All gates must pass before any benchmark timing. Ground
truth is hashlib SHA256d and the production kernel
bal_v_search2 / bal_v_batch2 from the unmodified EXP-007
research source (byte-identical kernel logic to
production mining/cpu/bal_avx512_mb.c). Both libraries
are built on this host with the restricted flag set
(-O3 -mavx512f -mavx512bw, never -march=native).

Arms under test, all from avx512_mb_mask_search.c:
  B  bal_v_msearch2   mask search, all-flagged extraction
  C  bal_v_msearcha2  mask search, lowest-lane extraction
  S  bal_v_msearchs2  span-complete scan, deferred extract
  MB bal_v_mbatch2    batch form of the new group code

Gates (numbering follows EXP024_MASK_SEARCH.md):
  G1 differential digests of the new group code (MB)
     vs hashlib, >= 108,000 nonces, several headers,
     starts and thread counts; accounting == production.
  G2 candidate-set equivalence: search arms vs a
     hashlib recount and vs production search. At
     1 thread the returned (nonce, digest) must equal
     the recount minimum exactly for every arm. At
     2 and 3 threads the returned candidate must be a
     true recount member with an exact digest (cross-
     worker first-publisher is a concurrency outcome,
     as in production). Densities about 0, 2^-16,
     2^-8 and 1.
  G3 target boundaries: target == digest(n) finds n,
     target == digest(n) - 1 misses, +1 finds.
  G4 nonce boundaries: starts 0 and 0xFFFFFFC0, ranges
     ending exactly at 2^32, the final nonce alone,
     unaligned starts, counts 1, 5, 15, 16, 17, 31, 33.
  G5 exact accounting at 1 thread: miss attempted ==
     count and backend == 16 * ceil(count / 16); hit
     attempted == min(16 * (hit_group + 1), count) and
     backend == 16 * (hit_group + 1), with the hit
     group derived from an independent recount; the
     genesis probe (winner 3 nonces into the range)
     reports attempted 16 and backend 16 on every arm.
     Scan arm: attempted == count always, backend ==
     full backend plus 16 on a hit.
  G6 genesis: every search arm re-finds nonce
     2083236893 with the exact hashlib digest.
  G7 invalid arguments: null pointers, zero count,
     zero or 17 threads, inverted and overflowing
     ranges return the production codes (-1 / -2)
     with no crash.
  G8 multiple candidates in one group: at density 1 a
     16-nonce span returns the span start (the lowest
     qualifying lane) on every arm at 1 thread.

The sanitizer gate (G9 in the run record) is a separate
C driver, exp024_san_driver.c, built with ASan/UBSan.
"""
import ctypes
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
EO_SRC = os.path.join(ROOT, "research/sha256d/extreme_optimization/src")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "exp024")
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import GENESIS, GENESIS_NONCE, DIFF1_LE  # noqa: E402

SEARCH_SIG = [
    ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
    ctypes.c_uint, ctypes.c_char_p,
    ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
    ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_uint64)]
BATCH_SIG = [
    ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
    ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
    ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_uint64)]

base = ctypes.CDLL(os.path.join(EO_SRC, "libbal_v512_exp022base.so"))
prod_search = base.bal_v_search2
prod_search.restype = ctypes.c_int
prod_search.argtypes = SEARCH_SIG
prod_batch = base.bal_v_batch2
prod_batch.restype = ctypes.c_int
prod_batch.argtypes = BATCH_SIG

mlib = ctypes.CDLL(os.path.join(EO_SRC, "libbal_m512.so"))
ARMS = {}
for name, sym in (("B", "bal_v_msearch2"), ("C", "bal_v_msearcha2"),
                  ("S", "bal_v_msearchs2")):
    fn = getattr(mlib, sym)
    fn.restype = ctypes.c_int
    fn.argtypes = SEARCH_SIG
    ARMS[name] = fn
mbatch = mlib.bal_v_mbatch2
mbatch.restype = ctypes.c_int
mbatch.argtypes = BATCH_SIG

MAX_TARGET = b"\xff" * 32
NONCE_SPACE = 1 << 32


def sha256d(header_with_nonce):
    return hashlib.sha256(
        hashlib.sha256(header_with_nonce).digest()).digest()


def digest_of(header, nonce):
    return sha256d(header[:76] + nonce.to_bytes(4, "little"))


def run_search(fn, header, start, count, threads, target):
    nonce = ctypes.c_uint32(0)
    dig = ctypes.create_string_buffer(32)
    att = ctypes.c_uint64(0)
    back = ctypes.c_uint64(0)
    rc = fn(header, start, count, threads, target,
            ctypes.byref(nonce), dig, ctypes.byref(att),
            ctypes.byref(back))
    return rc, nonce.value, dig.raw, att.value, back.value


def run_batch(fn, header, start, count, threads, target):
    hashes = ctypes.create_string_buffer(32 * count)
    flags = ctypes.create_string_buffer(count)
    att = ctypes.c_uint64(0)
    back = ctypes.c_uint64(0)
    rc = fn(header, start, count, threads, target, hashes, flags,
            ctypes.byref(att), ctypes.byref(back))
    return rc, hashes.raw, flags.raw, att.value, back.value


def recount(header, target_int, start, count):
    out = {}
    for i in range(count):
        d = digest_of(header, start + i)
        if int.from_bytes(d, "little") <= target_int:
            out[start + i] = d
    return out


def expected_backend(count, threads):
    if threads > count:
        threads = count
    chunk = (count + threads - 1) // threads
    total = 0
    begin = 0
    while begin < count:
        span = min(chunk, count - begin)
        total += ((span + 15) // 16) * 16
        begin += span
    return total


def main():
    rng = random.Random(20261115)
    report = {"experiment": "EXP-024", "gates": {},
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "libraries": {
                  "production": "libbal_v512_exp022base.so",
                  "mask": "libbal_m512.so"}}
    failures = []

    def gate(name, ok, detail):
        report["gates"][name] = {"pass": bool(ok), "detail": detail}
        print(f"{name}: {'PASS' if ok else 'FAIL'} {detail}",
              flush=True)
        if not ok:
            failures.append(name)

    # ---- G1: differential digests of the new group code ----
    total = 0
    ok = True
    detail = ""
    headers = [GENESIS]
    for _ in range(3):
        h = bytearray(GENESIS)
        for i in range(0, 76, 4):
            h[i:i + 4] = rng.getrandbits(32).to_bytes(4, "little")
        headers.append(bytes(h))
    for hi, header in enumerate(headers):
        for threads in (1, 2):
            start = rng.randrange(0, 1 << 20)
            count = 16384 + rng.randrange(0, 5000)
            rc, raw, flags, att, back = run_batch(
                mbatch, header, start, count, threads, MAX_TARGET)
            prc, praw, _pf, patt, pback = run_batch(
                prod_batch, header, start, count, threads,
                MAX_TARGET)
            if rc != 0 or prc != 0 or att != count or \
                    patt != count or back != pback:
                ok = False
                detail = f"accounting h{hi} t{threads}"
                break
            if raw != praw:
                ok = False
                detail = f"digest bytes differ from production h{hi}"
                break
            for i in range(count):
                want = digest_of(header, start + i)
                if raw[32 * i:32 * i + 32] != want:
                    ok = False
                    detail = f"hashlib mismatch h{hi} nonce {start+i}"
                    break
                if flags[i] != 1:
                    ok = False
                    detail = f"flag not set at density 1 h{hi}"
                    break
            if not ok:
                break
            total += count
        if not ok:
            break
    gate("G1_differential_new_group", ok and total >= 108_000,
         detail or f"{total} nonces, digests == hashlib and == "
                   f"production batch, flags all set at density 1")

    # ---- G2: candidate-set equivalence of the search arms ----
    ok = True
    detail = ""
    trials = 0
    densities = [(0, "0"), (1 << 240, "2^-16"),
                 (1 << 248, "2^-8"), ((1 << 256) - 1, "1")]
    for dval, dname in densities:
        target = dval.to_bytes(32, "little")
        for trial in range(10):
            header = headers[rng.randrange(len(headers))]
            start = rng.randrange(0, 1 << 24)
            count = rng.choice((257, 1000, 4096))
            want = recount(header, dval, start, count)
            for name, fn in list(ARMS.items()) + [("P", prod_search)]:
                rc, nonce, dig, att, back = run_search(
                    fn, header, start, count, 1, target)
                if want:
                    if rc != 1 or nonce != min(want) or \
                            dig != want[min(want)]:
                        ok = False
                        detail = (f"{name} d{dname} t{trial}: rc {rc} "
                                  f"nonce {nonce} want {min(want)}")
                else:
                    if rc != 0 or att != count:
                        ok = False
                        detail = f"{name} d{dname} t{trial}: miss rc {rc}"
                if not ok:
                    break
            if not ok:
                break
            # multi-thread: returned candidate must be a true
            # recount member with an exact digest
            for threads in (2, 3):
                for name, fn in ARMS.items():
                    rc, nonce, dig, att, back = run_search(
                        fn, header, start, count, threads, target)
                    if want:
                        if rc != 1 or nonce not in want or \
                                dig != want[nonce]:
                            ok = False
                            detail = (f"{name} mt{threads} d{dname} "
                                      f"t{trial}: nonce {nonce} not a "
                                      f"true candidate")
                    elif rc != 0 or att != count:
                        ok = False
                        detail = (f"{name} mt{threads} d{dname} "
                                  f"t{trial}: miss rc {rc} att {att}")
                    if not ok:
                        break
                if not ok:
                    break
            if not ok:
                break
            trials += 1
        if not ok:
            break
    gate("G2_candidate_set_equivalence", ok,
         detail or f"{trials} randomised spans x 4 densities: "
                   f"1-thread results identical to the recount "
                   f"minimum and to production; 2/3-thread results "
                   f"always true candidates with exact digests")

    # ---- G3: target boundaries ----
    ok = True
    detail = ""
    for trial in range(24):
        header = headers[rng.randrange(len(headers))]
        n = rng.randrange(0, 1 << 28)
        d = digest_of(header, n)
        dv = int.from_bytes(d, "little")
        for name, fn in list(ARMS.items()) + [("P", prod_search)]:
            rc, nonce, dig, att, back = run_search(
                fn, header, n, 1, 1, dv.to_bytes(32, "little"))
            if rc != 1 or nonce != n or dig != d:
                ok = False
                detail = f"{name} equality trial {trial}"
                break
            if dv > 0:
                rc, nonce, dig, att, back = run_search(
                    fn, header, n, 1, 1,
                    (dv - 1).to_bytes(32, "little"))
                if rc != 0:
                    ok = False
                    detail = f"{name} minus-one trial {trial}"
                    break
            if dv < (1 << 256) - 1:
                rc, nonce, dig, att, back = run_search(
                    fn, header, n, 1, 1,
                    (dv + 1).to_bytes(32, "little"))
                if rc != 1 or nonce != n:
                    ok = False
                    detail = f"{name} plus-one trial {trial}"
                    break
        if not ok:
            break
    gate("G3_target_boundaries", ok,
         detail or "24 sampled nonces x 4 implementations: "
                   "equality meets, minus one misses, plus one meets")

    # ---- G4: nonce boundaries ----
    ok = True
    detail = ""
    cases = [
        (0, 1), (0, 5), (0, 15), (0, 16), (0, 17), (0, 31),
        (0, 33), (7, 100), (12345, 999),
        (NONCE_SPACE - 64, 64), (NONCE_SPACE - 32, 32),
        (NONCE_SPACE - 1, 1), (NONCE_SPACE - 16, 16),
        (0xFFFFFFC0, 37),
    ]
    for start, count in cases:
        want0 = start  # density 1: lowest nonce wins at t1
        want_dig = digest_of(GENESIS, start)
        for name, fn in list(ARMS.items()) + [("P", prod_search)]:
            rc, nonce, dig, att, back = run_search(
                fn, GENESIS, start, count, 1, MAX_TARGET)
            if rc != 1 or nonce != want0 or dig != want_dig:
                ok = False
                detail = (f"{name} start {start} count {count}: "
                          f"rc {rc} nonce {nonce}")
                break
            exp_att = count if name == "S" else min(16, count)
            if att != exp_att:
                ok = False
                detail = (f"{name} accounting start {start} "
                          f"count {count}: att {att} want {exp_att}")
                break
        if not ok:
            break
    gate("G4_nonce_boundaries", ok,
         detail or "14 boundary spans incl. ranges ending "
                   "exactly at 2^32 and the final nonce alone: "
                   "lowest nonce and exact digest on every arm")

    # ---- G5: exact accounting at 1 thread ----
    ok = True
    detail = ""
    # miss accounting over a count table
    for count in (1, 5, 15, 16, 17, 31, 100, 1000, 65537):
        for name, fn in list(ARMS.items()) + [("P", prod_search)]:
            rc, nonce, dig, att, back = run_search(
                fn, GENESIS, 5000, count, 1,
                (0).to_bytes(32, "little"))
            exp_back = 16 * ((count + 15) // 16)
            if name == "S":
                exp_back_s = exp_back
                if rc != 0 or att != count or back != exp_back_s:
                    ok = False
                    detail = f"S miss count {count}: att {att} back {back}"
            elif rc != 0 or att != count or back != exp_back:
                ok = False
                detail = (f"{name} miss count {count}: att {att} "
                          f"back {back} want {exp_back}")
            if not ok:
                break
        if not ok:
            break
    # hit accounting: hit group derived from a recount
    if ok:
        for trial in range(12):
            header = headers[rng.randrange(len(headers))]
            start = rng.randrange(0, 1 << 20)
            count = rng.choice((100, 1000, 5000))
            dval = 1 << 248
            want = recount(header, dval, start, count)
            if not want:
                continue
            first = min(want)
            g = (first - start) // 16
            exp_att = min(16 * (g + 1), count)
            exp_back = 16 * (g + 1)
            target = dval.to_bytes(32, "little")
            for name, fn in ARMS.items():
                rc, nonce, dig, att, back = run_search(
                    fn, header, start, count, 1, target)
                if name == "S":
                    if rc != 1 or nonce != first or att != count or \
                            back != expected_backend(count, 1) + 16:
                        ok = False
                        detail = (f"S hit trial {trial}: att {att} "
                                  f"back {back}")
                elif rc != 1 or nonce != first or att != exp_att or \
                        back != exp_back:
                    ok = False
                    detail = (f"{name} hit trial {trial}: att {att} "
                              f"want {exp_att}, back {back} want "
                              f"{exp_back}")
                if not ok:
                    break
            if not ok:
                break
    # genesis probe: winner exactly 3 nonces into the range
    if ok:
        for name, fn in list(ARMS.items()) + [("P", prod_search)]:
            rc, nonce, dig, att, back = run_search(
                fn, GENESIS, GENESIS_NONCE - 3, 100000, 1, DIFF1_LE)
            if name == "S":
                if rc != 1 or nonce != GENESIS_NONCE or \
                        att != 100000:
                    ok = False
                    detail = f"S genesis probe att {att}"
            elif rc != 1 or nonce != GENESIS_NONCE or att != 16 or \
                    back != 16:
                ok = False
                detail = (f"{name} genesis probe: att {att} "
                          f"back {back} want 16/16")
            if not ok:
                break
    gate("G5_exact_accounting", ok,
         detail or "miss and hit accounting predicted exactly "
                   "by the wave rule at 1 thread over the count "
                   "table and 12 recounted hit spans; genesis "
                   "probe attempted 16 / backend 16 on B, C and "
                   "production; scan arm attempted == count with "
                   "the +16 recompute on hits")

    # ---- G6: genesis re-find with exact digest ----
    ok = True
    detail = ""
    gwant = digest_of(GENESIS, GENESIS_NONCE)
    for name, fn in ARMS.items():
        rc, nonce, dig, att, back = run_search(
            fn, GENESIS, GENESIS_NONCE - 1000, 2000, 2, DIFF1_LE)
        if rc != 1 or nonce != GENESIS_NONCE or dig != gwant:
            ok = False
            detail = f"{name}: rc {rc} nonce {nonce}"
            break
    gate("G6_genesis", ok,
         detail or "all three arms re-find nonce 2083236893 "
                   "with the exact hashlib digest at 2 threads")

    # ---- G7: invalid arguments ----
    ok = True
    detail = ""
    nonce = ctypes.c_uint32(0)
    digbuf = ctypes.create_string_buffer(32)
    att = ctypes.c_uint64(0)
    back = ctypes.c_uint64(0)
    for name, fn in ARMS.items():
        checks = []
        checks.append(fn(None, 0, 16, 1, MAX_TARGET,
                         ctypes.byref(nonce), digbuf,
                         ctypes.byref(att), ctypes.byref(back)))
        checks.append(fn(GENESIS, 0, 16, 1, None,
                         ctypes.byref(nonce), digbuf,
                         ctypes.byref(att), ctypes.byref(back)))
        checks.append(fn(GENESIS, 0, 16, 1, MAX_TARGET,
                         None, digbuf, ctypes.byref(att),
                         ctypes.byref(back)))
        checks.append(fn(GENESIS, 0, 16, 1, MAX_TARGET,
                         ctypes.byref(nonce), None,
                         ctypes.byref(att), ctypes.byref(back)))
        checks.append(fn(GENESIS, 0, 0, 1, MAX_TARGET,
                         ctypes.byref(nonce), digbuf,
                         ctypes.byref(att), ctypes.byref(back)))
        checks.append(fn(GENESIS, 0, 16, 0, MAX_TARGET,
                         ctypes.byref(nonce), digbuf,
                         ctypes.byref(att), ctypes.byref(back)))
        checks.append(fn(GENESIS, 0, 16, 17, MAX_TARGET,
                         ctypes.byref(nonce), digbuf,
                         ctypes.byref(att), ctypes.byref(back)))
        if checks != [-1] * 7:
            ok = False
            detail = f"{name} bad-arg codes {checks}"
            break
        rc_over = fn(GENESIS, NONCE_SPACE - 8, 16, 1, MAX_TARGET,
                     ctypes.byref(nonce), digbuf,
                     ctypes.byref(att), ctypes.byref(back))
        rc_far = fn(GENESIS, NONCE_SPACE, 1, 1, MAX_TARGET,
                    ctypes.byref(nonce), digbuf,
                    ctypes.byref(att), ctypes.byref(back))
        if rc_over != -2 or rc_far != -2:
            ok = False
            detail = f"{name} range codes {rc_over} {rc_far}"
            break
    gate("G7_invalid_arguments", ok,
         detail or "null header/target/outputs, zero count, "
                   "0 and 17 threads all return -1; ranges "
                   "crossing 2^32 return -2; no crashes")

    # ---- G8: multiple candidates in one group ----
    ok = True
    detail = ""
    for start in (0, 16, 100000, NONCE_SPACE - 16):
        for name, fn in ARMS.items():
            rc, nonce, dig, att, back = run_search(
                fn, GENESIS, start, 16, 1, MAX_TARGET)
            if rc != 1 or nonce != start or \
                    dig != digest_of(GENESIS, start):
                ok = False
                detail = f"{name} start {start}: nonce {nonce}"
                break
        if not ok:
            break
    gate("G8_multiple_candidates_one_group", ok,
         detail or "density-1 single-group spans return the "
                   "lowest qualifying lane on every arm")

    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["all_pass"] = not failures
    report["failures"] = failures
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(OUT_DIR, f"gates_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(OUT_DIR, f"gates_{stamp}_r{suffix}.json")
        suffix += 1
    with open(path, "x") as fh:
        json.dump(report, fh, indent=2)
    print(f"wrote {path}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
