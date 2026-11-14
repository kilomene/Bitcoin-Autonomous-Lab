#!/usr/bin/env python3
"""NOVA SHA-X shared benchmark harness.

This is the single harness used by the baseline (EXP-000) and by
every later experiment, so numbers stay comparable. It drives the
counted batch entry points (bal_c_batch2 / bal_i_batch2) through
ctypes and reports ACTUAL attempts returned by the library, per
the Task 003.9 accounting definitions: a batch call hashes its
whole range, so attempted == count is verified, never assumed.

Reported per configuration: repeats, median/min/max hashes per
second, and the spread. Single-candidate latency is measured as
the median wall time of count=1 batch calls (this includes the
ctypes crossing and thread setup, and is labelled as such; the
amortized per-hash time from throughput runs is reported too).

The live mainnet pool miner and pruned node run on this VM and
contend every measurement. Any consumer of these numbers must
carry that caveat.

Usage:
  python3 bench_harness.py            baseline run, JSON + summary
  python3 bench_harness.py --quick    smaller counts for smoke use
"""
import argparse
import ctypes
import hashlib
import json
import statistics
import sys
import time

GENESIS = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GENESIS_NONCE = 2083236893
DIFF1_LE = (0xFFFF << 208).to_bytes(32, "little")
MAX_LE = ((1 << 256) - 1).to_bytes(32, "little")


def load_lib(path, prefix):
    lib = ctypes.CDLL(path)
    batch2 = getattr(lib, f"{prefix}_batch2")
    batch2.restype = ctypes.c_int
    batch2.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint,
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint64)]
    search2 = getattr(lib, f"{prefix}_search2")
    search2.restype = ctypes.c_int
    search2.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint,
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)]
    return lib, batch2, search2


def run_batch(batch2, header, target_le, start, count, threads):
    hashes = ctypes.create_string_buffer(32 * count)
    flags = ctypes.create_string_buffer(count)
    attempted = ctypes.c_uint64(0)
    t0 = time.perf_counter()
    rc = batch2(header, start, count, threads, target_le, hashes, flags,
                ctypes.byref(attempted))
    dt = time.perf_counter() - t0
    return rc, attempted.value, dt, hashes.raw


def verify_batch(batch2, count=100_000, threads=2):
    """Differential check: every digest in a batch vs hashlib."""
    rc, attempted, _dt, raw = run_batch(batch2, GENESIS, MAX_LE, 0,
                                        count, threads)
    if rc != 0 or attempted != count:
        return False, f"rc={rc} attempted={attempted} count={count}"
    for n in range(count):
        want = hashlib.sha256(hashlib.sha256(
            GENESIS[:76] + n.to_bytes(4, "little")).digest()).digest()
        if raw[32 * n:32 * n + 32] != want:
            return False, f"digest mismatch at nonce {n}"
    return True, f"{count} digests match hashlib"


def verify_genesis_search(search2, threads=2):
    nonce = ctypes.c_uint32(0)
    attempted = ctypes.c_uint64(0)
    digest = ctypes.create_string_buffer(32)
    rc = search2(GENESIS, GENESIS_NONCE - 3, 10, threads, DIFF1_LE,
                 ctypes.byref(nonce), digest, ctypes.byref(attempted))
    want = bytes.fromhex(
        "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f")
    ok = (rc == 1 and nonce.value == GENESIS_NONCE
          and digest.raw[::-1] == want)
    return ok, f"rc={rc} nonce={nonce.value} attempted={attempted.value}"


def measure(batch2, count, threads, repeats):
    rates = []
    for _ in range(repeats):
        rc, attempted, dt, _raw = run_batch(
            batch2, GENESIS, DIFF1_LE, 0, count, threads)
        assert rc == 0 and attempted == count, (rc, attempted, count)
        rates.append(count / dt)
    return {
        "count_per_run": count, "threads": threads, "repeats": repeats,
        "rates_hs": [round(r) for r in rates],
        "median_hs": round(statistics.median(rates)),
        "min_hs": round(min(rates)), "max_hs": round(max(rates)),
        "spread_pct": round(100.0 * (max(rates) - min(rates))
                            / statistics.median(rates), 1),
    }


def measure_latency(batch2, calls=3000):
    times = []
    for _ in range(calls):
        _rc, _att, dt, _raw = run_batch(batch2, GENESIS, DIFF1_LE, 0, 1, 1)
        times.append(dt)
    times.sort()
    return {
        "calls": calls,
        "median_us_per_single_nonce_batch_call": round(
            statistics.median(times) * 1e6, 2),
        "p10_us": round(times[len(times) // 10] * 1e6, 2),
        "p90_us": round(times[9 * len(times) // 10] * 1e6, 2),
        "note": ("count=1 batch call through ctypes with thread setup; "
                 "an upper bound on pure single-hash latency"),
    }


def python_fallback(count, repeats):
    rates = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        for n in range(count):
            hashlib.sha256(hashlib.sha256(
                GENESIS[:76] + n.to_bytes(4, "little")).digest()).digest()
        rates.append(count / (time.perf_counter() - t0))
    return {
        "count_per_run": count, "threads": 1, "repeats": repeats,
        "median_hs": round(statistics.median(rates)),
        "min_hs": round(min(rates)), "max_hs": round(max(rates)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()
    count = 200_000 if args.quick else 1_000_000
    root = "/home/hatch/workspace/bitcoin-autonomous-lab"
    out = {"contention": ("live mainnet pool miner and pruned node "
                          "running; shared VM capped near 1.5 CPUs")}
    for name, path, prefix in (
            ("c_openssl_midstate", f"{root}/.local/cpu/libbal_batch.so",
             "bal_c"),
            ("intrinsics_scalar_schedule",
             f"{root}/.local/cpu/libbal_intrin.so", "bal_i")):
        _lib, batch2, search2 = load_lib(path, prefix)
        ok_b, msg_b = verify_batch(batch2, 20_000)
        ok_s, msg_s = verify_genesis_search(search2)
        entry = {"verify_batch_20000": f"{ok_b}: {msg_b}",
                 "verify_genesis_search": f"{ok_s}: {msg_s}",
                 "threads": {}}
        for threads in (1, 2, 4):
            entry["threads"][str(threads)] = measure(
                batch2, count, threads, args.repeats)
        entry["latency"] = measure_latency(batch2)
        out[name] = entry
    out["python_hashlib"] = python_fallback(
        20_000 if args.quick else 50_000, args.repeats)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
