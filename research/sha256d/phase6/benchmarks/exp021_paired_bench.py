#!/usr/bin/env python3
"""EXP-021 (Y-097) paired pool benchmark driver.

One invocation is one independent session for one named
comparison between two worker-pool configurations at
equal total thread count. The arms alternate at pool
block granularity (65,536 hashes per worker, so a block
is 131,072 hashes for the two-thread pools and 262,144
for the four-thread pools) in randomised AB or BA
order, both arms covering the same nonce range per
pair. Steal and runnable-load covariates are sampled
around every pool call, and per-worker attempted from
the kernels' own counters is asserted against the
partition plan on every call. Raw output is
append-only: every session writes a new file under
benchmarks/exp021/ and never overwrites an old one.

Pools (worker = one thread; shani worker = streams=4
strided, the EXP-005 per-worker geometry):

  mb2      [mb, mb]            mixed2   [mb, shani]
  shani2   [shani, shani]      mb4      [mb, mb, mb, mb]
  mixed22  [mb, mb, shani, shani]
  shani4   [shani, shani, shani, shani]

The statistic is the adopted EXP-017 one (paired
log-ratios, OLS covariate adjustment, pairs
bootstrap), computed by exp021_analyze.py. This
driver records data only; it makes no verdict.
"""
import argparse
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
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "exp021")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import GENESIS, MAX_LE  # noqa: E402
from exp017_paired_bench import node_info, sample_env, env_interval  # noqa: E402
from exp021_pool import MB, SHANI, run_pool  # noqa: E402

PER_WORKER = 65_536

POOLS = {
    "mb2": [MB, MB],
    "mixed2": [MB, SHANI],
    "shani2": [SHANI, SHANI],
    "mb4": [MB, MB, MB, MB],
    "mixed22": [MB, MB, SHANI, SHANI],
    "shani4": [SHANI, SHANI, SHANI, SHANI],
}

COMPARISONS = {
    "mixed2_vs_mb2": ("mb2", "mixed2"),
    "mixed2_vs_shani2": ("shani2", "mixed2"),
    "mb2_vs_shani2": ("shani2", "mb2"),
    "mixed22_vs_mb4": ("mb4", "mixed22"),
    "mixed22_vs_shani4": ("shani4", "mixed22"),
    "mb4_vs_shani4": ("shani4", "mb4"),
}

MANIFEST_FILES = {
    "geo_source": "research/sha256d/extreme_optimization/src/h01_geo.c",
    "geo_binary": "research/sha256d/extreme_optimization/src/libbal_geo.so",
    "avx512_mb_source":
        "research/sha256d/extreme_optimization/src/avx512_mb.c",
    "avx512_mb_binary":
        "research/sha256d/extreme_optimization/src/libbal_v512.so",
    "pool_library":
        "research/sha256d/phase6/benchmarks/exp021_pool.py",
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_pool_call(pool_name, start):
    specs = POOLS[pool_name]
    total = PER_WORKER * len(specs)
    first = sample_env()
    pool = run_pool(specs, GENESIS, start, total, MAX_LE,
                    materialize=False)
    second = sample_env()
    for w in pool["workers"]:
        assert w["rc"] == 0, (pool_name, w)
        assert w["attempted"] == w["part_count"], (pool_name, w)
        if w["family"] == "mb":
            assert w["backend_attempted"] == w["part_count"], \
                (pool_name, w)
    assert pool["attempted_total"] == total, (pool_name, pool)
    workers = [{
        "family": w["family"], "streams": w["streams"],
        "part_start": w["part_start"],
        "part_count": w["part_count"],
        "attempted": w["attempted"],
        "backend_attempted": w["backend_attempted"],
        "elapsed_s": w["elapsed_s"],
    } for w in pool["workers"]]
    return {
        "implementation": pool_name,
        "pool": [list(s) for s in specs],
        "start": start,
        "count": total,
        "threads": len(specs),
        "attempted": pool["attempted_total"],
        "backend_attempted": sum(
            w["backend_attempted"] for w in workers),
        "elapsed_s": pool["elapsed_s"],
        "rate_hs": pool["rate_hs"],
        "workers": workers,
        "env": env_interval(first, second, pool["elapsed_s"]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comparison", required=True,
                    choices=sorted(COMPARISONS))
    ap.add_argument("--pairs", type=int, default=160)
    ap.add_argument("--warmup-pairs", type=int, default=8)
    args = ap.parse_args()
    assert args.pairs >= 100, "a session needs at least 100 pairs"

    pool_a, pool_b = COMPARISONS[args.comparison]
    block = PER_WORKER * len(POOLS[pool_a])
    assert block == PER_WORKER * len(POOLS[pool_b])
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
    }

    record = {
        "experiment": "EXP-021",
        "session_id": session_id,
        "comparison": args.comparison,
        "arm_a_reference": pool_a,
        "arm_b_candidate": pool_b,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "block_size": block,
        "per_worker_block": PER_WORKER,
        "threads": len(POOLS[pool_a]),
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
            "both kernel libraries passed their full gate "
            "sets earlier in the programme (geo: EXP-005 "
            "gates; avx512_mb: the production gate set); "
            "the mixed pool itself passed the EXP-021 "
            "gate set in extreme_optimization/tests/"
            "test_exp021.py before benchmarking (candidate "
            "sets equal to the Python recount across six "
            "splits, all digests vs hashlib, genesis under "
            "both owners, boundary and empty partitions, "
            "exact union accounting); this driver asserts "
            "per-worker attempted and MB backend counts "
            "equal the partition plan on every timed call"),
        "pairs": [],
    }

    block_index = 0
    for _ in range(args.warmup_pairs):
        start = block_index * block
        run_pool_call(pool_a, start)
        run_pool_call(pool_b, start)
        block_index += 1

    for pair_index in range(args.pairs):
        start = block_index * block
        b_first = rng.random() < 0.5
        order = ("B", "A") if b_first else ("A", "B")
        results = {}
        for label in order:
            results[label] = run_pool_call(
                pool_b if label == "B" else pool_a, start)
        ra, rb = results["A"], results["B"]
        record["pairs"].append({
            "pair_index": pair_index,
            "start": start,
            "order": "".join(order),
            "b_first": b_first,
            "a": ra,
            "b": rb,
            "log_ratio_b_over_a": math.log(
                rb["rate_hs"] / ra["rate_hs"]),
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
    assert total_a == args.pairs * block
    assert total_b == args.pairs * block
    record["coverage_assertion"] = {
        "attempted_a": total_a, "attempted_b": total_b,
        "expected_each": args.pairs * block}

    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
