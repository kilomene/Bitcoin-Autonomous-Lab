#!/usr/bin/env python3
"""EXP-022 (Y-084) paired batch benchmark driver.

One invocation is one independent session for one named
comparison. Arm A is the production batch kernel
bal_v_batch2 (32 digest bytes plus one flag byte stored per
hash). Arm B is the flags-only variant bal_v_batchf2 from
avx512_mb_flags.c, either with flagged-digest extraction
(flagsx) or in pure flags mode with digests NULL (flagspure).
Both libraries are built on this host from the EXP-007
research source (byte-identical kernel logic to production)
and from the variant source, with the restricted flag set
-O3 -mavx512f -mavx512bw (never -march=native).

Blocks are 65,536 hashes per call, both arms covering the
same nonce range per pair, in randomised AB or BA order,
following the adopted EXP-017 protocol. Steal and
runnable-load covariates are sampled around every call and
attempted/backend are asserted against the call plan on
every timed call. Raw output is append-only under
benchmarks/exp022/.

Candidate density is set by the target in the v_meets
convention (flag iff int.from_bytes(digest, 'little') <=
target_int; argument bytes are target_int little-endian):
  d0    target_int 0        (approx 0 candidates)
  d256  target_int 2^248    (approx 2^-8 of hashes)
  dall  target_int 2^256-1  (every hash a candidate)

Predeclared verdict rule (recorded before benchmarking):
VERIFIED IMPROVEMENT (batch scope) iff the primary
comparison flagsx_vs_production_d0 at 2 threads is
significant (adjusted CI entirely above 0) in every
session and pooled under the EXP-017 statistic. Other
densities, the pure-flags arm and the 1-thread primary are
scope evidence. Gates (exp022_gates.py, all PASS) precede
any timing.
"""
import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import random
import sys
import time
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
EO_SRC = os.path.join(ROOT, "research/sha256d/extreme_optimization/src")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "exp022")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import GENESIS  # noqa: E402
from exp017_paired_bench import (  # noqa: E402
    node_info, sample_env, env_interval, sha256_file)

BLOCK = 65_536

BATCH_SIG = [
    ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
    ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
    ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_uint64)]

TARGETS = {
    "d0": (0).to_bytes(32, "little"),
    "d256": (1 << 248).to_bytes(32, "little"),
    "dall": ((1 << 256) - 1).to_bytes(32, "little"),
}

# comparison name -> (threads, density, arm B mode)
COMPARISONS = {
    "flagsx_vs_production_d0": (2, "d0", "flagsx"),
    "flagsx_vs_production_d256": (2, "d256", "flagsx"),
    "flagsx_vs_production_dall": (2, "dall", "flagsx"),
    "flagspure_vs_production_d0": (2, "d0", "flagspure"),
    "flagsx_vs_production_d0_t1": (1, "d0", "flagsx"),
}

MANIFEST_FILES = {
    "production_source":
        "research/sha256d/extreme_optimization/src/avx512_mb.c",
    "production_binary":
        "research/sha256d/extreme_optimization/src/"
        "libbal_v512_exp022base.so",
    "variant_source":
        "research/sha256d/extreme_optimization/src/avx512_mb_flags.c",
    "variant_binary":
        "research/sha256d/extreme_optimization/src/libbal_f512.so",
}

BUILD_CMD = ("gcc -O3 -mavx512f -mavx512bw -shared -fPIC "
             "-Wall -Wextra <src> -lpthread")


def cpu_model():
    try:
        with open("/proc/cpuinfo") as fh:
            for line in fh:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "unknown"


class Arms:
    def __init__(self):
        base = ctypes.CDLL(os.path.join(
            EO_SRC, "libbal_v512_exp022base.so"))
        self.prod_fn = base.bal_v_batch2
        self.prod_fn.restype = ctypes.c_int
        self.prod_fn.argtypes = BATCH_SIG
        var_lib = ctypes.CDLL(os.path.join(EO_SRC, "libbal_f512.so"))
        self.var_fn = var_lib.bal_v_batchf2
        self.var_fn.restype = ctypes.c_int
        self.var_fn.argtypes = BATCH_SIG

    def production(self, start, count, threads, target):
        hashes = ctypes.create_string_buffer(32 * count)
        flags = ctypes.create_string_buffer(count)
        attempted = ctypes.c_uint64(0)
        backend = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = self.prod_fn(GENESIS, start, count, threads, target,
                          hashes, flags, ctypes.byref(attempted),
                          ctypes.byref(backend))
        dt = time.perf_counter() - t0
        return rc, attempted.value, backend.value, dt

    def flagsx(self, start, count, threads, target):
        flagbits = ctypes.create_string_buffer((count + 7) // 8)
        digests = ctypes.create_string_buffer(32 * count)
        attempted = ctypes.c_uint64(0)
        backend = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = self.var_fn(GENESIS, start, count, threads, target,
                         flagbits, digests, ctypes.byref(attempted),
                         ctypes.byref(backend))
        dt = time.perf_counter() - t0
        return rc, attempted.value, backend.value, dt

    def flagspure(self, start, count, threads, target):
        flagbits = ctypes.create_string_buffer((count + 7) // 8)
        attempted = ctypes.c_uint64(0)
        backend = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = self.var_fn(GENESIS, start, count, threads, target,
                         flagbits, None, ctypes.byref(attempted),
                         ctypes.byref(backend))
        dt = time.perf_counter() - t0
        return rc, attempted.value, backend.value, dt


def expected_backend(count, threads):
    chunk = (count + threads - 1) // threads
    total = 0
    begin = 0
    while begin < count:
        span = min(chunk, count - begin)
        total += ((span + 15) // 16) * 16
        begin += span
    return total


def run_call(arms, impl, start, count, threads, target):
    first = sample_env()
    rc, attempted, backend, dt = getattr(arms, impl)(
        start, count, threads, target)
    second = sample_env()
    assert rc == 0, (impl, rc)
    assert attempted == count, (impl, attempted, count)
    assert backend == expected_backend(count, threads), (
        impl, backend, expected_backend(count, threads))
    return {
        "implementation": impl,
        "start": start,
        "count": count,
        "threads": threads,
        "rc": rc,
        "attempted": attempted,
        "backend_attempted": backend,
        "elapsed_s": dt,
        "rate_hs": count / dt,
        "env": env_interval(first, second, dt),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comparison", required=True,
                    choices=sorted(COMPARISONS))
    ap.add_argument("--pairs", type=int, default=120)
    ap.add_argument("--warmup-pairs", type=int, default=8)
    ap.add_argument("--block-size", type=int, default=BLOCK)
    args = ap.parse_args()
    assert args.block_size == BLOCK, "EXP-017 protocol fixes 65,536"
    assert args.pairs >= 100, "a session needs at least 100 pairs"

    threads, density, mode_b = COMPARISONS[args.comparison]
    target = TARGETS[density]
    impl_a, impl_b = "production", mode_b

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_id = f"{stamp}_{args.comparison}"
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"session_{session_id}.json")
    suffix = 2
    while os.path.exists(path):  # append-only: never overwrite
        session_id = f"{stamp}_{args.comparison}_r{suffix}"
        path = os.path.join(OUT_DIR, f"session_{session_id}.json")
        suffix += 1
    seed = int.from_bytes(
        hashlib.sha256(session_id.encode()).digest()[:8], "little")
    rng = random.Random(seed)

    arms = Arms()
    manifest = {name: {"path": rel,
                       "sha256": sha256_file(os.path.join(ROOT, rel))}
                for name, rel in MANIFEST_FILES.items()}
    manifest["driver"] = {"path": os.path.relpath(
        os.path.abspath(__file__), ROOT), "sha256": sha256_file(
            os.path.abspath(__file__))}
    manifest["build_command"] = BUILD_CMD

    record = {
        "experiment": "EXP-022",
        "session_id": session_id,
        "comparison": args.comparison,
        "arm_a_reference": impl_a,
        "arm_b_candidate": impl_b,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "block_size": args.block_size,
        "threads": threads,
        "density": density,
        "pairs_planned": args.pairs,
        "warmup_pairs": args.warmup_pairs,
        "order_seed": seed,
        "environment_at_start": sample_env(),
        "load_average_at_start":
            open("/proc/loadavg").read().split()[:3],
        "node_at_start": node_info(),
        "host": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "os_cpu_count": os.cpu_count(),
            "cpu_model": cpu_model(),
            "note": ("Intel Xeon Platinum 8321HC guest: AVX-512F/BW/"
                     "VL/VNNI present, no SHA extensions, no VBMI; "
                     "both arms built with -mavx512f -mavx512bw only"),
        },
        "manifest": manifest,
        "correctness_basis": (
            "exp022_gates.py all PASS before timing: 154,316 "
            "density-1 differentials vs hashlib, candidate-set "
            "parity with production at four densities in both "
            "extract and pure modes, genesis nonce recovery, "
            "target equality and minus/plus-one boundaries, "
            "accounting parity on 32 (count, threads) pairs"),
        "pairs": [],
    }

    block_index = 0
    for _ in range(args.warmup_pairs):
        start = block_index * args.block_size
        run_call(arms, impl_a, start, args.block_size, threads, target)
        run_call(arms, impl_b, start, args.block_size, threads, target)
        block_index += 1

    for pair_index in range(args.pairs):
        start = block_index * args.block_size
        b_first = rng.random() < 0.5
        order = ("B", "A") if b_first else ("A", "B")
        results = {}
        for label in order:
            impl = impl_b if label == "B" else impl_a
            results[label] = run_call(
                arms, impl, start, args.block_size, threads, target)
        ra, rb = results["A"], results["B"]
        record["pairs"].append({
            "pair_index": pair_index,
            "start": start,
            "order": "".join(order),
            "b_first": b_first,
            "a": ra,
            "b": rb,
            "log_ratio_b_over_a": math.log(rb["rate_hs"] / ra["rate_hs"]),
        })
        block_index += 1
        if (pair_index + 1) % 40 == 0:
            print(f"{session_id}: {pair_index + 1}/{args.pairs} pairs",
                  flush=True)

    record["finished_utc"] = datetime.now(timezone.utc).isoformat()
    record["environment_at_end"] = sample_env()
    record["load_average_at_end"] = open("/proc/loadavg").read().split()[:3]
    record["node_at_end"] = node_info()
    total_a = sum(p["a"]["attempted"] for p in record["pairs"])
    total_b = sum(p["b"]["attempted"] for p in record["pairs"])
    assert total_a == args.pairs * args.block_size
    assert total_b == args.pairs * args.block_size
    record["coverage_assertion"] = {
        "attempted_a": total_a, "attempted_b": total_b,
        "expected_each": args.pairs * args.block_size}

    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
