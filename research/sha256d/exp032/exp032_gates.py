#!/usr/bin/env python3
"""EXP-032 correctness gates.

Every candidate kernel is checked digest by digest against
hashlib (the exact SHA-256d reference) before any benchmark
number is allowed to exist:

- batch differentials over the genesis header and random
  headers, at counts that are and are not multiples of the
  lane width, and at range starts near the 2^32 boundary;
- flag agreement: every batch flag byte must equal the
  hashlib meets decision at several target densities;
- search gates: the genesis nonce must be found with the
  exact genesis digest; a planted easy target must return
  a nonce whose hashlib digest truly meets it; a no-hit
  range must return 0 with attempted == count;
- the flags-search prototype must additionally agree with
  the production flags batch: for random ranges and
  densities, the nonce it returns must be a genuinely
  meeting nonce (hashlib), and when the flags batch says
  the range has no meeting nonce it must return 0.

Output: a JSON record under RAW_RESULTS/ plus a PASS/FAIL
summary on stdout. Exit code 0 only if every gate passes.
"""
import ctypes
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import GENESIS, GENESIS_NONCE, DIFF1_LE, MAX_LE  # noqa: E402

CPU_LIB = os.path.join(ROOT, ".local/cpu")


def dsha(header, nonce):
    return hashlib.sha256(hashlib.sha256(
        header[:76] + nonce.to_bytes(4, "little")).digest()).digest()


def meets_le(digest, target_le):
    return int.from_bytes(digest, "little") <= int.from_bytes(
        target_le, "little")


def counted_batch(fn, extra=()):
    fn.restype = ctypes.c_int
    fn.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, *extra, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]
    return fn


def counted_search(fn, extra=()):
    fn.restype = ctypes.c_int
    fn.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, *extra, ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]
    return fn


def plain_batch(fn):
    """bal_c_batch2 / bal_i_batch2 shape: no backend out."""
    fn.restype = ctypes.c_int
    fn.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)]
    return fn


class Batch:
    """Uniform wrapper: batch(header, start, count, threads,
    target_le) -> (rc, attempted, backend, hashes, flags)."""

    def __init__(self, kind, fn, streams=None):
        self.kind = kind
        self.fn = fn
        self.streams = streams

    def __call__(self, header, start, count, threads, target_le):
        hashes = ctypes.create_string_buffer(32 * count)
        flags = ctypes.create_string_buffer(count)
        attempted = ctypes.c_uint64(0)
        backend = ctypes.c_uint64(0)
        if self.kind == "counted":
            rc = self.fn(header, start, count, threads, target_le,
                         hashes, flags, ctypes.byref(attempted),
                         ctypes.byref(backend))
            return rc, attempted.value, backend.value, hashes.raw, \
                flags.raw
        if self.kind == "streams":
            rc = self.fn(header, start, count, threads, self.streams,
                         target_le, hashes, flags,
                         ctypes.byref(attempted),
                         ctypes.byref(backend))
            return rc, attempted.value, backend.value, hashes.raw, \
                flags.raw
        rc = self.fn(header, start, count, threads, target_le,
                     hashes, flags, ctypes.byref(attempted))
        return rc, attempted.value, attempted.value, hashes.raw, \
            flags.raw


class Search:
    """Uniform wrapper: search(header, start, count, threads,
    target_le) -> (rc, nonce, digest, attempted, backend)."""

    def __init__(self, kind, fn, streams=None):
        self.kind = kind
        self.fn = fn
        self.streams = streams

    def __call__(self, header, start, count, threads, target_le):
        nonce = ctypes.c_uint32(0)
        digest = ctypes.create_string_buffer(32)
        attempted = ctypes.c_uint64(0)
        backend = ctypes.c_uint64(0)
        if self.kind == "counted":
            rc = self.fn(header, start, count, threads, target_le,
                         ctypes.byref(nonce), digest,
                         ctypes.byref(attempted),
                         ctypes.byref(backend))
            return rc, nonce.value, digest.raw, attempted.value, \
                backend.value
        if self.kind == "streams":
            rc = self.fn(header, start, count, threads, self.streams,
                         target_le, ctypes.byref(nonce), digest,
                         ctypes.byref(attempted),
                         ctypes.byref(backend))
            return rc, nonce.value, digest.raw, attempted.value, \
                backend.value
        rc = self.fn(header, start, count, threads, target_le,
                     ctypes.byref(nonce), digest,
                     ctypes.byref(attempted))
        return rc, nonce.value, digest.raw, attempted.value, \
            attempted.value


def check_batch(name, batch, rng, results):
    cases = []
    total = 0
    # Genesis sweep, odd and even counts, several threadings.
    for count, threads in ((100_000, 2), (65_537, 1), (9_999, 4),
                           (8, 2), (1, 1)):
        rc, att, back, raw, flags = batch(
            GENESIS, 0, count, threads, MAX_LE)
        ok = rc == 0 and att == count
        detail = f"rc={rc} attempted={att}"
        if ok:
            for n in range(count):
                if raw[32 * n:32 * n + 32] != dsha(GENESIS, n):
                    ok = False
                    detail = f"digest mismatch at nonce {n}"
                    break
                if flags[n] != 1:
                    ok = False
                    detail = f"flag not set at nonce {n} (MAX target)"
                    break
        cases.append({"case": f"genesis count={count} threads={threads}",
                      "pass": bool(ok), "detail": detail})
        total += count if ok else 0
    # Random headers, random starts, flag agreement at density.
    for trial in range(6):
        header = bytes(rng.randrange(256) for _ in range(80))
        start = rng.randrange(0, 1 << 20)
        count = rng.choice([5_000, 12_345, 40_000])
        bits = rng.choice([8, 12, 16])
        target = ((1 << bits) - 1) << (256 - bits)
        target_le = target.to_bytes(32, "little")
        rc, att, back, raw, flags = batch(
            header, start, count, 2, target_le)
        ok = rc == 0 and att == count
        detail = f"rc={rc} attempted={att}"
        hits = 0
        if ok:
            for i in range(count):
                want = dsha(header, start + i)
                if raw[32 * i:32 * i + 32] != want:
                    ok = False
                    detail = f"digest mismatch at nonce {start + i}"
                    break
                m = meets_le(want, target_le)
                hits += m
                if flags[i] != (1 if m else 0):
                    ok = False
                    detail = f"flag mismatch at nonce {start + i}"
                    break
        cases.append({"case": f"random trial={trial} count={count} "
                              f"density_bits={bits} hits={hits}",
                      "pass": bool(ok), "detail": detail})
        total += count if ok else 0
    # Boundary: range ending exactly at 2^32.
    start = (1 << 32) - 5_000
    rc, att, back, raw, flags = batch(GENESIS, start, 5_000, 2, MAX_LE)
    ok = rc == 0 and att == 5_000
    detail = f"rc={rc} attempted={att}"
    if ok:
        for i in range(5_000):
            if raw[32 * i:32 * i + 32] != dsha(GENESIS, start + i):
                ok = False
                detail = f"digest mismatch at nonce {start + i}"
                break
    cases.append({"case": "boundary end at 2^32 count=5000",
                  "pass": bool(ok), "detail": detail})
    total += 5_000 if ok else 0
    passed = all(c["pass"] for c in cases)
    results[name] = {"pass": passed, "digests_verified": total,
                     "cases": cases}
    return passed


def check_search(name, search, rng, results):
    cases = []
    # Genesis nonce: search a window containing it at DIFF1.
    start = GENESIS_NONCE - 1000
    rc, nonce, digest, att, back = search(
        GENESIS, start, 2000, 2, DIFF1_LE)
    want = dsha(GENESIS, GENESIS_NONCE)
    ok = rc == 1 and nonce == GENESIS_NONCE and digest == want
    cases.append({"case": "genesis nonce find",
                  "pass": bool(ok),
                  "detail": f"rc={rc} nonce={nonce} attempted={att}"})
    # Planted easy target over random headers.
    for trial in range(4):
        header = bytes(rng.randrange(256) for _ in range(80))
        start = rng.randrange(0, 1 << 20)
        count = 20_000
        # Density 2^-8 in the little-endian comparison the
        # kernels implement: about 78 expected hits per
        # 20,000 nonces, so a correct search finds one with
        # overwhelming probability, and the returned nonce
        # is then verified exactly against hashlib.
        target_le = ((1 << 248) - 1).to_bytes(32, "little")
        rc, nonce, digest, att, back = search(
            header, start, count, 2, target_le)
        ok = rc == 1 and start <= nonce < start + count \
            and digest == dsha(header, nonce) \
            and meets_le(digest, target_le)
        cases.append({"case": f"planted target trial={trial}",
                      "pass": bool(ok),
                      "detail": f"rc={rc} nonce={nonce} "
                                f"attempted={att}"})
    # No-hit range: impossible target, attempted must be exact.
    rc, nonce, digest, att, back = search(
        GENESIS, 0, 65_536, 2, (1).to_bytes(32, "little"))
    ok = rc == 0 and att == 65_536
    cases.append({"case": "no-hit full range attempted exact",
                  "pass": bool(ok),
                  "detail": f"rc={rc} attempted={att}"})
    passed = all(c["pass"] for c in cases)
    results[name] = {"pass": passed, "cases": cases}
    return passed


def main():
    rng = random.Random(32032)
    results = {}
    all_ok = True

    avx2 = ctypes.CDLL(os.path.join(HERE, "libbal_avx2.so"))
    a_batch = Batch("counted", counted_batch(avx2.bal_a_batch2))
    a_search = Search("counted", counted_search(avx2.bal_a_search2))
    all_ok &= check_batch("avx2_batch", a_batch, rng, results)
    print("avx2_batch:", results["avx2_batch"]["pass"],
          results["avx2_batch"]["digests_verified"], "digests")
    all_ok &= check_search("avx2_search", a_search, rng, results)
    print("avx2_search:", results["avx2_search"]["pass"])

    h01 = ctypes.CDLL(os.path.join(HERE, "libbal_h01.so"))
    m_batch_fn = h01.bal_m_batch2
    m_batch_fn.restype = ctypes.c_int
    m_batch_fn.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_int, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint64)]
    m_search_fn = h01.bal_m_search2
    m_search_fn.restype = ctypes.c_int
    m_search_fn.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_int, ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint64)]

    class H01Batch:
        def __call__(self, streams):
            outer = self

            class B:
                def __call__(self, header, start, count, threads,
                             target_le):
                    hashes = ctypes.create_string_buffer(32 * count)
                    flags = ctypes.create_string_buffer(count)
                    att = ctypes.c_uint64(0)
                    rc = m_batch_fn(header, start, count, threads,
                                    streams, target_le, hashes, flags,
                                    ctypes.byref(att))
                    return rc, att.value, att.value, hashes.raw, \
                        flags.raw
            return B()

    class H01Search:
        def __call__(self, streams):
            class S:
                def __call__(self, header, start, count, threads,
                             target_le):
                    nonce = ctypes.c_uint32(0)
                    digest = ctypes.create_string_buffer(32)
                    att = ctypes.c_uint64(0)
                    rc = m_search_fn(header, start, count, threads,
                                     streams, target_le,
                                     ctypes.byref(nonce), digest,
                                     ctypes.byref(att))
                    return rc, nonce.value, digest.raw, att.value, \
                        att.value
            return S()

    for streams in (1, 2, 4):
        nm = f"shani_m{streams}_batch"
        all_ok &= check_batch(nm, H01Batch()(streams), rng, results)
        print(nm, ":", results[nm]["pass"],
              results[nm]["digests_verified"], "digests")
    all_ok &= check_search("shani_m4_search", H01Search()(4), rng,
                           results)
    print("shani_m4_search:", results["shani_m4_search"]["pass"])
    all_ok &= check_search("shani_m1_search", H01Search()(1), rng,
                           results)
    print("shani_m1_search:", results["shani_m1_search"]["pass"])

    intrin = ctypes.CDLL(os.path.join(CPU_LIB, "libbal_intrin.so"))
    i_batch = Batch("plain", plain_batch(intrin.bal_i_batch2))
    is_fn = intrin.bal_i_search2
    is_fn.restype = ctypes.c_int
    is_fn.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint64)]

    class ISearch:
        def __call__(self, header, start, count, threads, target_le):
            nonce = ctypes.c_uint32(0)
            digest = ctypes.create_string_buffer(32)
            att = ctypes.c_uint64(0)
            rc = is_fn(header, start, count, threads, target_le,
                       ctypes.byref(nonce), digest, ctypes.byref(att))
            return rc, nonce.value, digest.raw, att.value, att.value

    all_ok &= check_batch("shani_intrin_batch", i_batch, rng, results)
    print("shani_intrin_batch:", results["shani_intrin_batch"]["pass"],
          results["shani_intrin_batch"]["digests_verified"], "digests")
    all_ok &= check_search("shani_intrin_search", ISearch(), rng,
                           results)
    print("shani_intrin_search:",
          results["shani_intrin_search"]["pass"])

    fsearch = ctypes.CDLL(os.path.join(HERE, "libbal_v512fsearch.so"))
    f_search = Search("counted",
                      counted_search(fsearch.bal_v_searchf2))
    all_ok &= check_search("flags_search", f_search, rng, results)
    print("flags_search:", results["flags_search"]["pass"])

    # Cross-check: flags-search vs production flags batch on
    # random ranges. If the batch flag bits contain no hit the
    # search must return 0; if they contain a hit the returned
    # nonce's bit must be set (winner semantics: any genuinely
    # meeting nonce is acceptable, not necessarily the first).
    prod_flags = ctypes.CDLL(os.path.join(CPU_LIB,
                                          "libbal_v512flags.so"))
    pf = prod_flags.bal_v_batchf2
    pf.restype = ctypes.c_int
    pf.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]
    xcases = []
    for trial in range(8):
        header = bytes(rng.randrange(256) for _ in range(80))
        start = rng.randrange(0, 1 << 20)
        count = 16_384
        bits = rng.choice([16, 20, 24, 256])
        target = ((1 << bits) - 1) << (256 - bits) \
            if bits < 256 else (1 << 256) - 1
        target_le = target.to_bytes(32, "little")
        flagbits = ctypes.create_string_buffer((count + 7) // 8)
        att = ctypes.c_uint64(0)
        back = ctypes.c_uint64(0)
        rc = pf(header, start, count, 2, target_le, flagbits, None,
                ctypes.byref(att), ctypes.byref(back))
        raw = flagbits.raw
        any_hit = any(raw)
        rc2, nonce, digest, att2, back2 = f_search(
            header, start, count, 2, target_le)
        if not any_hit:
            ok = rc == 0 and rc2 == 0
            detail = f"no-hit agreement rc2={rc2}"
        else:
            idx = nonce - start
            bit = (raw[idx >> 3] >> (idx & 7)) & 1 \
                if 0 <= idx < count else 0
            ok = rc2 == 1 and bit == 1 \
                and digest == dsha(header, nonce)
            detail = f"hit agreement rc2={rc2} bit={bit}"
        xcases.append({"case": f"cross trial={trial} bits={bits}",
                       "pass": bool(ok), "detail": detail})
    xpass = all(c["pass"] for c in xcases)
    results["flags_search_vs_flags_batch"] = {"pass": xpass,
                                              "cases": xcases}
    all_ok &= xpass
    print("flags_search_vs_flags_batch:", xpass)

    record = {
        "experiment": "EXP-032 gates",
        "utc": datetime.now(timezone.utc).isoformat(),
        "host": "AMD EPYC 9D25 (guest, htch-runtime)",
        "all_pass": bool(all_ok),
        "results": results,
    }
    out_dir = os.path.join(HERE, "RAW_RESULTS")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(out_dir, f"gates_{stamp}.json")
    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    print("wrote", path)
    print("ALL GATES PASS" if all_ok else "GATE FAILURE")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
