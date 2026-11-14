#!/usr/bin/env python3
"""EXP-017 paired benchmark driver (Y-101, Y-102, Y-103).

One invocation is one independent session for one named
comparison. It alternates the two arms at 65,536-hash
block granularity in randomised AB or BA order, samples
steal and runnable-load covariates around every counted
call, and asserts that attempted and backend accounting
equal the intended block size on every call. Raw output
is append-only: every session writes a new file under
benchmarks/exp017/ and never overwrites an old one.

The statistic computed from these files is the one
predeclared in phase6/EXPERIMENT_RESULTS.md, EXP-017:
paired log-ratios of equal-size counted batches, with
an OLS covariate adjustment and a pairs bootstrap.
This driver records data only; it makes no verdict.
"""
import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import random
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
EO_SRC = os.path.join(ROOT, "research/sha256d/extreme_optimization/src")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "exp017")
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import load_lib, GENESIS, DIFF1_LE  # noqa: E402

BLOCK = 65_536
THREADS = 2


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sample_env():
    with open("/proc/stat") as fh:
        fields = fh.readline().split()
    values = [int(x) for x in fields[1:]]
    with open("/proc/loadavg") as fh:
        load = fh.read().split()
    return {
        "cpu_total_jiffies": sum(values),
        "cpu_steal_jiffies": values[7],
        "load1": float(load[0]),
        "runnable": int(load[3].split("/")[0]),
    }


def env_interval(first, second, elapsed):
    total_delta = second["cpu_total_jiffies"] - first["cpu_total_jiffies"]
    steal_delta = second["cpu_steal_jiffies"] - first["cpu_steal_jiffies"]
    return {
        "steal_fraction": (steal_delta / total_delta
                           if total_delta > 0 else 0.0),
        "steal_jiffies_delta": steal_delta,
        "total_jiffies_delta": total_delta,
        "runnable_mean": 0.5 * (first["runnable"] + second["runnable"]),
        "load1_mean": 0.5 * (first["load1"] + second["load1"]),
        "elapsed_s": elapsed,
    }


def node_info():
    cli = os.path.join(
        ROOT, "../bitcoin-core-dist/bitcoin-core-28.1/bin/bitcoin-cli")
    cli = os.path.normpath(cli)
    datadir = os.path.join(ROOT, ".local/mainnet")
    try:
        out = subprocess.run(
            [cli, f"-datadir={datadir}", "getblockchaininfo"],
            capture_output=True, text=True, timeout=8)
        if out.returncode != 0:
            return {"rpc_status": "error",
                    "detail": (out.stderr or out.stdout).strip()[:200]}
        info = json.loads(out.stdout)
        return {"rpc_status": "ok", "blocks": info["blocks"],
                "headers": info["headers"],
                "initialblockdownload": info["initialblockdownload"],
                "verificationprogress": info["verificationprogress"]}
    except Exception as exc:  # timeout or parse failure: record, do not hang
        return {"rpc_status": "unavailable",
                "detail": f"{type(exc).__name__}: {exc}"[:200]}


class Arms:
    """Counted batch calls for the three gated implementations.

    Each call allocates its output buffers before the timed
    region, mirroring bench_harness.run_batch, so the elapsed
    time is the counted library call itself.
    """

    def __init__(self):
        _lib, self.prod_fn, _s = load_lib(
            os.path.join(ROOT, ".local/cpu/libbal_batch.so"), "bal_c")
        geo = ctypes.CDLL(os.path.join(EO_SRC, "libbal_geo.so"))
        self.geo_fn = geo.bal_m_batch2m
        self.geo_fn.restype = ctypes.c_int
        self.geo_fn.argtypes = [
            ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
            ctypes.c_uint, ctypes.c_int, ctypes.c_int,
            ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint64)]
        v512 = ctypes.CDLL(os.path.join(EO_SRC, "libbal_v512.so"))
        self.mb_fn = v512.bal_v_batch2
        self.mb_fn.restype = ctypes.c_int
        self.mb_fn.argtypes = [
            ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
            ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
            ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64)]

    def production(self, start, count, threads):
        hashes = ctypes.create_string_buffer(32 * count)
        flags = ctypes.create_string_buffer(count)
        attempted = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = self.prod_fn(GENESIS, start, count, threads, DIFF1_LE,
                          hashes, flags, ctypes.byref(attempted))
        dt = time.perf_counter() - t0
        return rc, attempted.value, attempted.value, dt

    def geo_s4_strided(self, start, count, threads):
        hashes = ctypes.create_string_buffer(32 * count)
        flags = ctypes.create_string_buffer(count)
        attempted = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = self.geo_fn(GENESIS, start, count, threads, 4, 1,
                         DIFF1_LE, hashes, flags,
                         ctypes.byref(attempted))
        dt = time.perf_counter() - t0
        return rc, attempted.value, attempted.value, dt

    def avx512_mb(self, start, count, threads):
        hashes = ctypes.create_string_buffer(32 * count)
        flags = ctypes.create_string_buffer(count)
        attempted = ctypes.c_uint64(0)
        backend = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = self.mb_fn(GENESIS, start, count, threads, DIFF1_LE,
                        hashes, flags, ctypes.byref(attempted),
                        ctypes.byref(backend))
        dt = time.perf_counter() - t0
        return rc, attempted.value, backend.value, dt


IMPLEMENTATIONS = {
    "production": "production",
    "geo_s4_strided": "geo_s4_strided",
    "avx512_mb": "avx512_mb",
}

COMPARISONS = {
    "control_production": ("production", "production"),
    "control_avx512_mb": ("avx512_mb", "avx512_mb"),
    "production_vs_avx512_mb": ("production", "avx512_mb"),
    "production_vs_geo_s4_strided": ("production", "geo_s4_strided"),
}

MANIFEST_FILES = {
    "production_source": "mining/cpu/bal_batch.c",
    "production_binary": ".local/cpu/libbal_batch.so",
    "geo_source": "research/sha256d/extreme_optimization/src/h01_geo.c",
    "geo_binary": "research/sha256d/extreme_optimization/src/libbal_geo.so",
    "avx512_mb_source": "research/sha256d/extreme_optimization/src/avx512_mb.c",
    "avx512_mb_binary": "research/sha256d/extreme_optimization/src/libbal_v512.so",
}


def run_call(arms, impl, start, count):
    first = sample_env()
    rc, attempted, backend, dt = getattr(arms, impl)(start, count, THREADS)
    second = sample_env()
    assert rc == 0, (impl, rc)
    assert attempted == count, (impl, attempted, count)
    assert backend == count, (impl, backend, count)
    return {
        "implementation": impl,
        "start": start,
        "count": count,
        "threads": THREADS,
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
    ap.add_argument("--pairs", type=int, default=160)
    ap.add_argument("--warmup-pairs", type=int, default=8)
    ap.add_argument("--block-size", type=int, default=BLOCK)
    args = ap.parse_args()
    assert args.block_size == BLOCK, "EXP-017 protocol fixes 65,536"
    assert args.pairs >= 100, "a session needs at least 100 pairs"

    impl_a, impl_b = COMPARISONS[args.comparison]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_id = f"{stamp}_{args.comparison}"
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
    manifest["build_commands"] = {
        "geo": "gcc -O3 -march=native -msha -shared -fPIC "
               "-Wall -Wextra h01_geo.c -lpthread",
        "avx512_mb": "gcc -O3 -march=native -shared -fPIC "
                     "-Wall -Wextra avx512_mb.c -lpthread",
        "production": "prebuilt gated library, source and binary "
                      "hashes recorded above",
    }

    record = {
        "experiment": "EXP-017",
        "session_id": session_id,
        "comparison": args.comparison,
        "arm_a_reference": impl_a,
        "arm_b_candidate": impl_b,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "block_size": args.block_size,
        "threads": THREADS,
        "pairs_planned": args.pairs,
        "warmup_pairs": args.warmup_pairs,
        "order_seed": seed,
        "environment_at_start": sample_env(),
        "load_average_at_start": open("/proc/loadavg").read().split()[:3],
        "node_at_start": node_info(),
        "host": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "os_cpu_count": os.cpu_count(),
        },
        "manifest": manifest,
        "correctness_basis": (
            "production library verified on 100,000 digests vs "
            "hashlib in this EXP-017 run-up; geo s=4 strided and "
            "avx512_mb rebuilt from unchanged sources and passed "
            "the full extreme_optimization gate set (108,000 "
            "randomized differentials each) in this run-up; the "
            "driver additionally asserts attempted and backend "
            "equal the block size on every timed call"),
        "pairs": [],
    }

    block_index = 0
    for _ in range(args.warmup_pairs):
        start = block_index * args.block_size
        run_call(arms, impl_a, start, args.block_size)
        run_call(arms, impl_b, start, args.block_size)
        block_index += 1

    for pair_index in range(args.pairs):
        start = block_index * args.block_size
        b_first = rng.random() < 0.5
        order = ("B", "A") if b_first else ("A", "B")
        results = {}
        for label in order:
            impl = impl_b if label == "B" else impl_a
            results[label] = run_call(arms, impl, start, args.block_size)
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
