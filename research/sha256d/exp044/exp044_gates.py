#!/usr/bin/env python3
"""EXP-044 correctness gates. Run BEFORE any timing; any
failure stops that variant as a correctness failure (a
variant that fails is excluded from the benchmark arms
and the failure is the result for that variant).

Arms under test (all the same kernel source,
mining/cpu/bal_avx512_mb.c, exports bal_v_batch2 and
bal_v_search2):
  base    .local/cpu/libbal_v512.so, today's production
          library (sha256 6dfd8d42...; the EXP-044
          replica build is byte-identical to it).
  znver3  research build, kernel TU + -mtune=znver3.
  znver4  research build, kernel TU + -mtune=znver4.

Gates (the EXP-046 gate set, unchanged):
  G1 differentials: each library's counted batch form
     over 4 x 65,536 = 262,144 digests per library
     (786,432 total, above the 100,000-per-variant
     floor), byte-identical to hashlib: genesis at
     starts 0 and 65,536 (2 threads), a random header
     at the unaligned start 12,345 (2 threads), and
     genesis on the span ending exactly at 2^32
     (start 2^32-65,536, 1 thread). attempted == count
     asserted per call.
  G2 candidate-set equivalence at 1 thread, all three
     search entries against a hashlib recount, at
     target densities 0, about 2^-16, about 2^-8 and 1
     (target ints 0, 2^240, 2^248, 2^256-1): on a hit
     the returned nonce must be the recount's first
     qualifying nonce with its exact digest; on a miss
     rc must be 0 with attempted == count. Spans
     include starts 0 and 1, unaligned starts, the
     single last nonce 2^32-1, and spans ending
     exactly at 2^32.
  G3 multi-thread checks: density-0 accounting at 2
     threads on an unaligned start and on the span
     ending at 2^32; the genesis nonce re-found at 2
     threads by all three with the exact hashlib
     digest; density-1 at 2 threads returns a hit
     whose digest matches hashlib for the returned
     nonce.
  G4 boundary refusals: spans with start + count >
     2^32 and spans with start == 2^32 are refused
     with rc == -2 and zero accounting by all three.

Gate truth for digests and candidates is hashlib alone.
"""
import ctypes
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "RAW_RESULTS")
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import GENESIS, GENESIS_NONCE, DIFF1_LE  # noqa: E402

CPU_DIR = os.path.join(ROOT, ".local/cpu")
SRC_DIR = os.path.join(HERE, "src")
BASE_LIB = os.path.join(CPU_DIR, "libbal_v512.so")
Z3_LIB = os.path.join(SRC_DIR, "libbal_v512_exp044_znver3.so")
Z4_LIB = os.path.join(SRC_DIR, "libbal_v512_exp044_znver4.so")
KERNEL_SRC = os.path.join(ROOT, "mining/cpu/bal_avx512_mb.c")

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
MAX_LE = ((1 << 256) - 1).to_bytes(32, "little")
BLOCK = 65_536
M32 = 1 << 32


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest_of(header, nonce32):
    return hashlib.sha256(hashlib.sha256(
        header[:76] + nonce32.to_bytes(4, "little")).digest()).digest()


def load():
    blib = ctypes.CDLL(BASE_LIB)
    z3lib = ctypes.CDLL(Z3_LIB)
    z4lib = ctypes.CDLL(Z4_LIB)
    arms = {
        "base": (blib.bal_v_search2, blib.bal_v_batch2),
        "znver3": (z3lib.bal_v_search2, z3lib.bal_v_batch2),
        "znver4": (z4lib.bal_v_search2, z4lib.bal_v_batch2),
    }
    for search, batch in arms.values():
        search.restype = ctypes.c_int
        search.argtypes = SEARCH_SIG
        batch.restype = ctypes.c_int
        batch.argtypes = BATCH_SIG
    return arms


def run_search(fn, header, start, count, threads, target):
    nonce = ctypes.c_uint32(0)
    dig = ctypes.create_string_buffer(32)
    att = ctypes.c_uint64(0)
    back = ctypes.c_uint64(0)
    rc = fn(header, start, count, threads, target,
            ctypes.byref(nonce), dig, ctypes.byref(att),
            ctypes.byref(back))
    return rc, nonce.value, dig.raw, att.value, back.value


def run_batch(fn, header, start, count, threads):
    hashes = ctypes.create_string_buffer(32 * count)
    flags = ctypes.create_string_buffer(count)
    att = ctypes.c_uint64(0)
    back = ctypes.c_uint64(0)
    rc = fn(header, start, count, threads, MAX_LE, hashes, flags,
            ctypes.byref(att), ctypes.byref(back))
    return rc, hashes.raw, flags.raw, att.value, back.value


def recount_first(header, target_int, start, count):
    for i in range(count):
        d = digest_of(header, (start + i) & 0xFFFFFFFF)
        if int.from_bytes(d, "little") <= target_int:
            return (start + i) & 0xFFFFFFFF, d
    return None


def cpu_model():
    with open("/proc/cpuinfo") as fh:
        for line in fh:
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return "unknown"


def main():
    rng = random.Random(44044)
    arms = load()
    report = {
        "experiment": "EXP-044",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "host": {"hostname": os.uname().nodename,
                 "cpu_model": cpu_model(),
                 "os_cpu_count": os.cpu_count()},
        "libraries": {
            "base": {"path": BASE_LIB,
                     "sha256": sha256_file(BASE_LIB),
                     "source": "mining/cpu/bal_avx512_mb.c",
                     "source_sha256": sha256_file(KERNEL_SRC)},
            "znver3": {"path": Z3_LIB,
                       "sha256": sha256_file(Z3_LIB),
                       "source": "mining/cpu/bal_avx512_mb.c",
                       "source_sha256": sha256_file(KERNEL_SRC),
                       "extra_kernel_flags": ["-mtune=znver3"]},
            "znver4": {"path": Z4_LIB,
                       "sha256": sha256_file(Z4_LIB),
                       "source": "mining/cpu/bal_avx512_mb.c",
                       "source_sha256": sha256_file(KERNEL_SRC),
                       "extra_kernel_flags": ["-mtune=znver4"]},
        },
        "gates": {},
    }
    failures = []

    def gate(name, ok, detail):
        report["gates"][name] = {"pass": bool(ok), "detail": detail}
        print(f"{name}: {'PASS' if ok else 'FAIL'} {detail}",
              flush=True)
        if not ok:
            failures.append(name)

    rand_header = bytes(rng.getrandbits(8) for _ in range(80))

    # ---- G1: differentials per library batch form ----
    g1_total = 0
    g1_ok = True
    g1_detail = ""
    blocks = [
        (GENESIS, 0, 2),
        (GENESIS, BLOCK, 2),
        (rand_header, 12_345, 2),
        (GENESIS, M32 - BLOCK, 1),
    ]
    for name, (_s, batch) in arms.items():
        checked = 0
        for header, start, threads in blocks:
            rc, raw, _fl, att, _back = run_batch(
                batch, header, start, BLOCK, threads)
            if rc != 0 or att != BLOCK:
                g1_ok = False
                g1_detail = (f"{name} batch rc {rc} att {att} "
                             f"start {start}")
                break
            for i in range(BLOCK):
                if raw[32 * i:32 * i + 32] != digest_of(
                        header, (start + i) & 0xFFFFFFFF):
                    g1_ok = False
                    g1_detail = (f"{name} digest mismatch start "
                                 f"{start} offset {i}")
                    break
            if not g1_ok:
                break
            checked += BLOCK
        if not g1_ok:
            break
        g1_total += checked
        print(f"  G1 {name}: {checked} digests OK", flush=True)
    gate("G1_differentials", g1_ok and g1_total >= 300_000,
         g1_detail or f"{g1_total} digests byte-identical to "
                      f"hashlib across the three batch forms "
                      f"(262,144 per library)")

    # ---- G2: candidate-set equivalence at 1 thread ----
    headers = [GENESIS, rand_header]
    spans = {
        0: [(0, 8192), (1, 4096), (12_345, 4096), (999, 1000),
            (M32 - 8192, 8192), (M32 - 1, 1)],
        1 << 240: [(rng.randrange(0, 1 << 24), BLOCK)
                   for _ in range(6)]
                  + [(rng.randrange(0, 1 << 24), 8192)
                     for _ in range(6)],
        1 << 248: [(rng.randrange(0, 1 << 24), c)
                   for c in (1000, 4096, 8192, 4096, 1000, 8192,
                             2048, 4096, 8192, 1000, 4096, 2048)],
        (1 << 256) - 1: [(0, 37), (1, 100), (12_345, 4096),
                         (M32 - 1, 1), (M32 - 4096, 4096),
                         (999, 1000)],
    }
    g2_ok = True
    g2_detail = ""
    g2_spans = 0
    g2_hits = 0
    for dval, span_list in spans.items():
        target = dval.to_bytes(32, "little")
        for si, (start, count) in enumerate(span_list):
            header = headers[si % len(headers)]
            want = recount_first(header, dval, start, count)
            for name, (search, _b) in arms.items():
                rc, nonce, dig, att, _back = run_search(
                    search, header, start, count, 1, target)
                if want is not None:
                    if rc != 1 or nonce != want[0] or dig != want[1]:
                        g2_ok = False
                        g2_detail = (f"{name} density {dval} span "
                                     f"{si}: rc {rc} nonce {nonce} "
                                     f"want {want[0]}")
                else:
                    if rc != 0 or att != count:
                        g2_ok = False
                        g2_detail = (f"{name} density {dval} span "
                                     f"{si}: miss rc {rc} att "
                                     f"{att} count {count}")
                if not g2_ok:
                    break
            if not g2_ok:
                break
            g2_spans += 1
            if want is not None:
                g2_hits += 1
        if not g2_ok:
            break
    gate("G2_candidate_equivalence_t1", g2_ok,
         g2_detail or f"{g2_spans} spans x 3 kernels at densities "
                      f"0, 2^-16, 2^-8, 1 ({g2_hits} spans with a "
                      f"recount hit): returned nonce and digest "
                      f"identical to the hashlib recount")

    # ---- G3: multi-thread checks ----
    g3_ok = True
    g3_detail = ""
    gwant = digest_of(GENESIS, GENESIS_NONCE)
    for name, (search, _b) in arms.items():
        for start, count in ((12_345, BLOCK), (M32 - BLOCK, BLOCK)):
            rc, _n, _d, att, _bk = run_search(
                search, GENESIS, start, count, 2,
                (0).to_bytes(32, "little"))
            if rc != 0 or att != count:
                g3_ok = False
                g3_detail = (f"{name} d0 t2 start {start}: rc {rc} "
                             f"att {att}")
        rc, nonce, dig, _a, _b = run_search(
            search, GENESIS, GENESIS_NONCE - 1000, 2000, 2, DIFF1_LE)
        if rc != 1 or nonce != GENESIS_NONCE or dig != gwant:
            g3_ok = False
            g3_detail = (f"{name} genesis t2: rc {rc} nonce {nonce} "
                         f"digest exact {dig == gwant}")
        rc, nonce, dig, _a, _b = run_search(
            search, GENESIS, 12_345, 4096, 2, MAX_LE)
        if rc != 1 or not (12_345 <= nonce < 12_345 + 4096) or \
                dig != digest_of(GENESIS, nonce):
            g3_ok = False
            g3_detail = (f"{name} density-1 t2: rc {rc} nonce "
                         f"{nonce} digest valid "
                         f"{dig == digest_of(GENESIS, nonce)}")
        if not g3_ok:
            break
    gate("G3_multithread", g3_ok,
         g3_detail or "d0 accounting exact at 2 threads on plain "
                      "and boundary spans; genesis re-found at 2 "
                      "threads by all three; density-1 hits at 2 "
                      "threads carry exact digests")

    # ---- G4: boundary refusals ----
    g4_ok = True
    g4_detail = ""
    for name, (search, _b) in arms.items():
        for start, count in ((M32 - 10, 64), (M32 - 2048, 4096),
                             (M32, 64)):
            rc, _n, _d, att, back = run_search(
                search, GENESIS, start, count, 1,
                (0).to_bytes(32, "little"))
            if rc != -2 or att != 0 or back != 0:
                g4_ok = False
                g4_detail = (f"{name} start {start} count {count}: "
                             f"rc {rc} att {att} back {back}")
        if not g4_ok:
            break
    gate("G4_boundary_refusals", g4_ok,
         g4_detail or "spans crossing or starting at 2^32 refused "
                      "with rc -2 and zero accounting by all three "
                      "kernels")

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
