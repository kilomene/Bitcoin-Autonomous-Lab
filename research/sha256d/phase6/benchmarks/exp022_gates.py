#!/usr/bin/env python3
"""EXP-022 (Y-084) correctness gates for bal_v_batchf2.

All gates must pass before any benchmark timing. Ground
truth is hashlib SHA256d and the production kernel
bal_v_batch2 from the unmodified EXP-007 research source
(byte-identical kernel logic to production), both libraries
built on this host with the restricted flag set
(-O3 -mavx512f -mavx512bw).

Gates:
  G1 density-1 full differential: at the maximum target
     every lane is flagged, so the flags path extracts
     every digest; >= 100,000 nonces across several
     headers, starts and thread counts must equal
     hashlib exactly, attempted == count, and backend
     must equal the production backend for the same call.
  G2 flag parity vs production at the three bench
     densities (approx 0, 2^-8, 1) plus 2^-16: the
     flagged offset set from the variant bit array must
     equal the production flag-byte set exactly, and
     every extracted digest must equal the production
     digest at that slot. Pure-flags mode (digests NULL)
     must produce identical bits.
  G3 genesis: over a window containing the genesis nonce
     under the genesis target, exactly one bit is set, at
     the genesis nonce offset, and the extracted digest
     equals hashlib of the genesis header.
  G4 target boundaries: for sampled nonces n, target ==
     digest(n) flags n, target == digest(n) - 1 does not,
     target == digest(n) + 1 does (values in the v_meets
     convention: flag(n) iff int.from_bytes(digest_n,
     'little') <= target_int, target argument bytes are
     target_int in little-endian).
  G5 accounting parity: for counts {1, 15, 16, 17, 31,
     100, 1000, 65537} x threads {1, 2, 3, 4}, variant
     attempted and backend equal production's exactly,
     including spans whose begin offset is not a multiple
     of 8 (exercises the flag-bit merge alignment).
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
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import GENESIS, GENESIS_NONCE  # noqa: E402

BATCH_SIG = [
    ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
    ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
    ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_uint64)]

base = ctypes.CDLL(os.path.join(EO_SRC, "libbal_v512_exp022base.so"))
prod = base.bal_v_batch2
prod.restype = ctypes.c_int
prod.argtypes = BATCH_SIG

var_lib = ctypes.CDLL(os.path.join(EO_SRC, "libbal_f512.so"))
var = var_lib.bal_v_batchf2
var.restype = ctypes.c_int
var.argtypes = BATCH_SIG

MAX_TARGET = b"\xff" * 32
ZERO_TARGET = b"\x00" * 32


def target_int_bytes(v):
    return v.to_bytes(32, "little")


def sha256d(header_with_nonce):
    return hashlib.sha256(
        hashlib.sha256(header_with_nonce).digest()).digest()


def run_prod(header, start, count, threads, target):
    hashes = ctypes.create_string_buffer(32 * count)
    flags = ctypes.create_string_buffer(count)
    att = ctypes.c_uint64(0)
    back = ctypes.c_uint64(0)
    rc = prod(header, start, count, threads, target, hashes, flags,
              ctypes.byref(att), ctypes.byref(back))
    assert rc == 0, ("prod rc", rc)
    return hashes.raw, flags.raw, att.value, back.value


def run_var(header, start, count, threads, target, extract=True):
    nbytes = (count + 7) // 8
    flagbits = ctypes.create_string_buffer(nbytes)
    digests = ctypes.create_string_buffer(32 * count) if extract else None
    att = ctypes.c_uint64(0)
    back = ctypes.c_uint64(0)
    rc = var(header, start, count, threads, target, flagbits,
             digests, ctypes.byref(att), ctypes.byref(back))
    assert rc == 0, ("var rc", rc)
    return (flagbits.raw,
            digests.raw if extract else None,
            att.value, back.value)


def bits_set(flagbits, count):
    out = []
    for i in range(count):
        if flagbits[i >> 3] >> (i & 7) & 1:
            out.append(i)
    return out


def main():
    rng = random.Random(20261114)
    report = {"experiment": "EXP-022", "gates": {},
              "started_utc": datetime.now(timezone.utc).isoformat()}
    failures = []

    def gate(name, ok, detail):
        report["gates"][name] = {"pass": bool(ok), "detail": detail}
        print(f"{name}: {'PASS' if ok else 'FAIL'} {detail}", flush=True)
        if not ok:
            failures.append(name)

    # ---- G1: density-1 full differential vs hashlib ----
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
            fb, dig, att, back = run_var(
                header, start, count, threads, MAX_TARGET)
            _ph, _pf, patt, pback = run_prod(
                header, start, count, threads, MAX_TARGET)
            if att != count or back != pback or patt != count:
                ok = False
                detail = f"accounting h{hi} t{threads}"
                break
            if bits_set(fb, count) != list(range(count)):
                ok = False
                detail = f"not all flagged h{hi} t{threads}"
                break
            for i in range(count):
                want = sha256d(header[:76] +
                               (start + i).to_bytes(4, "little"))
                if dig[32 * i:32 * i + 32] != want:
                    ok = False
                    detail = f"digest mismatch h{hi} off{i}"
                    break
            total += count
            if not ok:
                break
        if not ok:
            break
    gate("G1_density1_hashlib_differential", ok and total >= 100_000,
         f"{total} nonces, headers={len(headers)}, threads 1/2")

    # ---- G2: flag parity at densities, extract + pure ----
    ok = True
    detail = ""
    densities = {
        "zero": ZERO_TARGET,
        "2^-16": target_int_bytes(1 << 240),
        "2^-8": target_int_bytes(1 << 248),
        "all": MAX_TARGET,
    }
    cand_total = {}
    for dname, target in densities.items():
        count = 65536
        start = 12345
        for threads in (1, 2, 3):
            ph, pf, patt, pback = run_prod(
                GENESIS, start, count, threads, target)
            fb, dig, att, back = run_var(
                GENESIS, start, count, threads, target)
            fb2, _d2, att2, back2 = run_var(
                GENESIS, start, count, threads, target, extract=False)
            prod_set = [i for i in range(count) if pf[i]]
            var_set = bits_set(fb, count)
            if var_set != prod_set or fb2 != fb:
                ok = False
                detail = f"{dname} t{threads} set mismatch"
                break
            if (att, back) != (patt, pback) or (att2, back2) != (patt, pback):
                ok = False
                detail = f"{dname} t{threads} accounting"
                break
            for i in prod_set:
                if dig[32 * i:32 * i + 32] != ph[32 * i:32 * i + 32]:
                    ok = False
                    detail = f"{dname} t{threads} digest at {i}"
                    break
            cand_total[dname] = len(prod_set)
            if not ok:
                break
        if not ok:
            break
    gate("G2_density_candidate_sets", ok,
         f"candidates per 65536: {cand_total}")

    # ---- G3: genesis recovery ----
    gtarget = target_int_bytes(0xFFFF << 208)
    start = GENESIS_NONCE - 8
    count = 16
    fb, dig, att, back = run_var(GENESIS, start, count, 1, gtarget)
    got = bits_set(fb, count)
    want_digest = sha256d(GENESIS[:76] +
                          GENESIS_NONCE.to_bytes(4, "little"))
    off = GENESIS_NONCE - start
    ok = (got == [off] and att == count and
          dig[32 * off:32 * off + 32] == want_digest)
    gate("G3_genesis", ok, f"flagged offsets {got}, digest match")

    # ---- G4: target equality and minus/plus one ----
    ok = True
    detail = ""
    sample_offsets = [0, 1, 15, 16, 17, 255, 4097]
    base_start = 777
    count = 8192
    digests_all = {}
    ph, _pf, _a, _b = run_prod(GENESIS, base_start, count, 1, MAX_TARGET)
    for off in sample_offsets:
        d = ph[32 * off:32 * off + 32]
        digests_all[off] = int.from_bytes(d, "little")
    for off, val in digests_all.items():
        for delta, want in ((0, True), (-1, False), (1, True)):
            tv = val + delta
            if tv < 0 or tv >= 1 << 256:
                continue
            fb, _dig, _a, _b = run_var(
                GENESIS, base_start, count, 2, target_int_bytes(tv))
            got = (fb[off >> 3] >> (off & 7)) & 1
            if bool(got) != want:
                ok = False
                detail = f"off {off} delta {delta}: got {got}"
                break
        if not ok:
            break
    gate("G4_target_boundaries", ok,
         f"{len(digests_all)} nonces x eq/-1/+1 {detail}")

    # ---- G5: accounting parity incl. unaligned spans ----
    ok = True
    detail = ""
    checks = 0
    for count in (1, 15, 16, 17, 31, 100, 1000, 65537):
        for threads in (1, 2, 3, 4):
            _h, _f, patt, pback = run_prod(
                GENESIS, 999, count, threads, MAX_TARGET)
            _fb, _d, att, back = run_var(
                GENESIS, 999, count, threads, MAX_TARGET)
            checks += 1
            if (att, back) != (patt, pback) or att != count:
                ok = False
                detail = (f"count {count} threads {threads}: "
                          f"var {(att, back)} prod {(patt, pback)}")
                break
        if not ok:
            break
    gate("G5_accounting_parity", ok, f"{checks} (count, threads) pairs")

    report["all_pass"] = not failures
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    out_dir = os.path.join(HERE, "exp022")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(out_dir, f"gates_{stamp}.json")
    with open(path, "x") as fh:
        json.dump(report, fh, indent=2)
    print(f"wrote {path}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
