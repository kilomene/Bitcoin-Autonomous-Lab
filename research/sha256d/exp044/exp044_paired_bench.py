#!/usr/bin/env python3
"""EXP-044 paired benchmark driver (EXP-017 protocol).

One invocation is one independent session for one named
comparison. Design stated in EXP044_REPORT.md section 1
before any timing: the production v512 kernel
(mining/cpu/bal_avx512_mb.c, production library
.local/cpu/libbal_v512.so) is re-built research-side
with only -mtune=znver3 or -mtune=znver4 added to the
kernel translation unit (every other flag identical to
mining/cpu/build.py; the replica build with no extra
flag is byte-identical to the production library), and
the variants are timed against the production library
itself:

  base    bal_v_batch2 / bal_v_search2 in
          .local/cpu/libbal_v512.so (arm A, reference)
  znver3  same entries in the znver3 research library
          (arm B, candidate)
  znver4  same entries in the znver4 research library
          (arm B, candidate)

Comparisons:
  znver3_vs_base_batch_t2        batch (category D),
                                 PRIMARY scope, 2 threads
  znver4_vs_base_batch_t2        batch, PRIMARY, 2 threads
  control_base_vs_base_batch_t2  control (same library
                                 both arms), batch
  znver3_vs_base_search_d0_t2    search (category E),
                                 density 0, SECONDARY
  znver4_vs_base_search_d0_t2    search, density 0
  control_base_vs_base_search_d0_t2  control, search

The search scope runs only under the rule predeclared
in the report: for a variant, search sessions run iff
its batch pooled adjusted mean log ratio is positive
and at or above the campaign noise floor (the absolute
pooled adjusted mean of the batch control); the search
control runs iff any search comparison runs.

Protocol, identical to the adopted EXP-017 rule and to
the EXP-045 / EXP-046 drivers: paired 65,536-hash
blocks, randomised AB or BA order per pair, steal and
runnable-load covariates sampled around every counted
call, 120 pairs per session, 3 sessions per comparison,
sessions run strictly one at a time and rotated across
comparisons by round. Verdicts come only from
exp044_analyze.py applying the imported exp017
statistic: VERIFIED IMPROVEMENT requires the adjusted
bootstrap CI entirely above 0 in every session and
pooled; ESTABLISHED NEGATIVE requires it entirely
below 0 in every session and pooled; anything else is
NOT SIGNIFICANT.

Batch calls use the difficulty-1 target (DIFF1_LE),
the EXP-045 batch-bench convention; the batch form has
no early exit, so attempted == 65,536 on every call,
asserted. Search calls use target_int 0 (density 0,
the mainnet-like all-miss case), attempted == 65,536
asserted, exactly as EXP-046.

The live miner, autopilot and node run throughout and
are never touched; heartbeat snapshots and load are
recorded per session. Raw output is append-only under
RAW_RESULTS/sessions/; this driver records data only
and makes no verdict.
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
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "RAW_RESULTS", "sessions")
sys.path.insert(0, os.path.join(
    ROOT, "research/sha256d/phase6/benchmarks"))
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import GENESIS, DIFF1_LE  # noqa: E402
from exp017_paired_bench import (  # noqa: E402
    node_info, sample_env, env_interval, sha256_file)

BLOCK = 65_536
CPU_DIR = os.path.join(ROOT, ".local/cpu")
SRC_DIR = os.path.join(HERE, "src")
BASE_LIB = os.path.join(CPU_DIR, "libbal_v512.so")
Z3_LIB = os.path.join(SRC_DIR, "libbal_v512_exp044_znver3.so")
Z4_LIB = os.path.join(SRC_DIR, "libbal_v512_exp044_znver4.so")
TARGET_D0 = (0).to_bytes(32, "little")

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

# comparison -> (scope, threads, arm_a_reference, arm_b_candidate)
COMPARISONS = {
    "znver3_vs_base_batch_t2": ("batch", 2, "base", "znver3"),
    "znver4_vs_base_batch_t2": ("batch", 2, "base", "znver4"),
    "control_base_vs_base_batch_t2": ("batch", 2, "base", "base"),
    "znver3_vs_base_search_d0_t2": ("search", 2, "base", "znver3"),
    "znver4_vs_base_search_d0_t2": ("search", 2, "base", "znver4"),
    "control_base_vs_base_search_d0_t2": ("search", 2, "base",
                                          "base"),
}

MANIFEST_FILES = {
    "kernel_source": "mining/cpu/bal_avx512_mb.c",
    "probe_source": "mining/cpu/bal_avx512_probe.c",
    "production_build": "mining/cpu/build.py",
    "base_binary": ".local/cpu/libbal_v512.so",
    "replica_binary":
        "research/sha256d/exp044/src/"
        "libbal_v512_exp044_replica.so",
    "znver3_binary":
        "research/sha256d/exp044/src/"
        "libbal_v512_exp044_znver3.so",
    "znver4_binary":
        "research/sha256d/exp044/src/"
        "libbal_v512_exp044_znver4.so",
}


def cpu_info():
    model = "unknown"
    flags = []
    try:
        with open("/proc/cpuinfo") as fh:
            text = fh.read()
        for line in text.splitlines():
            if line.startswith("model name") and model == "unknown":
                model = line.split(":", 1)[1].strip()
            if line.startswith("flags") and not flags:
                flags = line.split(":", 1)[1].split()
    except OSError:
        pass
    wanted = ("sha_ni", "avx2", "avx512f", "avx512bw", "avx512dq",
              "avx512vl", "avx512vbmi", "avx512_vbmi2",
              "avx512ifma", "avx512_vnni", "gfni", "vaes",
              "bmi1", "bmi2", "adx")
    return model, {w: (w in flags) for w in wanted}


def heartbeat_snapshot():
    path = os.path.join(ROOT, ".local/heartbeat.json")
    try:
        with open(path) as fh:
            hb = json.load(fh)
        return {k: hb.get(k) for k in (
            "ts", "miner_state", "miner_pid", "restarts",
            "shares_accepted_total")}
    except Exception as exc:  # read-only observation only
        return {"error": str(exc)}


class Arms:
    def __init__(self):
        self.batch_fns = {}
        self.search_fns = {}
        for name, path in (("base", BASE_LIB), ("znver3", Z3_LIB),
                           ("znver4", Z4_LIB)):
            lib = ctypes.CDLL(path)
            bfn = lib.bal_v_batch2
            bfn.restype = ctypes.c_int
            bfn.argtypes = BATCH_SIG
            self.batch_fns[name] = bfn
            sfn = lib.bal_v_search2
            sfn.restype = ctypes.c_int
            sfn.argtypes = SEARCH_SIG
            self.search_fns[name] = sfn

    def batch(self, impl, start, count, threads):
        hashes = ctypes.create_string_buffer(32 * count)
        flags = ctypes.create_string_buffer(count)
        att = ctypes.c_uint64(0)
        back = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = self.batch_fns[impl](
            GENESIS, start, count, threads, DIFF1_LE, hashes,
            flags, ctypes.byref(att), ctypes.byref(back))
        dt = time.perf_counter() - t0
        return rc, att.value, back.value, dt

    def search(self, impl, start, count, threads):
        nonce = ctypes.c_uint32(0)
        dig = ctypes.create_string_buffer(32)
        att = ctypes.c_uint64(0)
        back = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = self.search_fns[impl](
            GENESIS, start, count, threads, TARGET_D0,
            ctypes.byref(nonce), dig, ctypes.byref(att),
            ctypes.byref(back))
        dt = time.perf_counter() - t0
        return rc, att.value, back.value, dt


def run_call(arms, scope, impl, start, count, threads):
    first = sample_env()
    if scope == "batch":
        rc, attempted, backend, dt = arms.batch(
            impl, start, count, threads)
    else:
        rc, attempted, backend, dt = arms.search(
            impl, start, count, threads)
    assert rc == 0, (impl, rc)
    assert attempted == count, (impl, attempted, count)
    second = sample_env()
    return {
        "implementation": impl,
        "start": start,
        "count": count,
        "threads": threads,
        "rc": rc,
        "attempted": attempted,
        "backend_attempted": backend,
        "elapsed_s": dt,
        "rate_hs": attempted / dt,
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

    scope, threads, impl_a, impl_b = COMPARISONS[args.comparison]

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
    manifest["build_note"] = (
        "research libraries built by exp044/build_variants.py "
        "replicating mining/cpu/build.py's build_v512 commands "
        "exactly, with -mtune=znver3 or -mtune=znver4 added to "
        "the kernel translation unit only; the replica build "
        "with no extra flag is byte-identical to the "
        "production library (sha256 6dfd8d42...), so the "
        "timed difference is the -mtune flag alone")
    model, flags = cpu_info()

    record = {
        "experiment": "EXP-044 (EXP-017 protocol)",
        "session_id": session_id,
        "comparison": args.comparison,
        "scope": scope,
        "density": ("n/a (batch, difficulty-1 target)"
                    if scope == "batch" else "d0 (target_int 0)"),
        "arm_a_reference": impl_a,
        "arm_b_candidate": impl_b,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "block_size": args.block_size,
        "threads": threads,
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
            "cpu_model": model,
            "relevant_flags": flags,
        },
        "miner_heartbeat_at_start": heartbeat_snapshot(),
        "manifest": manifest,
        "correctness_basis": (
            "exp044_gates.py PASS before timing: 786,432 batch "
            "differentials vs hashlib across the three "
            "libraries (262,144 per library); candidate-set "
            "equivalence vs a hashlib recount at densities 0, "
            "2^-16, 2^-8, 1 on 36 spans including nonce "
            "boundary spans; 2-thread accounting and genesis "
            "checks; uniform rc -2 refusal of spans crossing "
            "2^32. The driver additionally asserts rc == 0 "
            "and attempted == 65,536 on every timed call"),
        "pairs": [],
    }

    block_index = 0
    for _ in range(args.warmup_pairs):
        start = block_index * args.block_size
        run_call(arms, scope, impl_a, start, args.block_size,
                 threads)
        run_call(arms, scope, impl_b, start, args.block_size,
                 threads)
        block_index += 1

    for pair_index in range(args.pairs):
        start = block_index * args.block_size
        b_first = rng.random() < 0.5
        order = ("B", "A") if b_first else ("A", "B")
        results = {}
        for label in order:
            impl = impl_b if label == "B" else impl_a
            results[label] = run_call(
                arms, scope, impl, start, args.block_size, threads)
        ra, rb = results["A"], results["B"]
        record["pairs"].append({
            "pair_index": pair_index,
            "start": start,
            "order": "".join(order),
            "b_first": b_first,
            "a": ra,
            "b": rb,
            "log_ratio_b_over_a": math.log(rb["rate_hs"] /
                                           ra["rate_hs"]),
        })
        block_index += 1
        if (pair_index + 1) % 40 == 0:
            print(f"{session_id}: {pair_index + 1}/{args.pairs} pairs",
                  flush=True)

    record["finished_utc"] = datetime.now(timezone.utc).isoformat()
    record["environment_at_end"] = sample_env()
    record["load_average_at_end"] = open("/proc/loadavg").read().split()[:3]
    record["node_at_end"] = node_info()
    record["miner_heartbeat_at_end"] = heartbeat_snapshot()
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
