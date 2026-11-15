#!/usr/bin/env python3
"""EXP-026 paired benchmark driver: mask-based early-exit
search vs production search, EXP-017 protocol.

One invocation is one independent session for one named
comparison. Search arms call the counted search entry
points over identical 65,536-nonce ranges in randomised
AB or BA order; the recorded rate is the kernel-reported
attempted count divided by elapsed time (actual work,
never the requested span). At the primary density
(target_int 0, mainnet-like: essentially every span
misses) attempted == 65,536 on every call and is asserted.
At the frequent-hit density (target_int 2^244, about
2^-12 of hashes qualify) the hit-density comparisons run
at 1 thread, where group-atomic accounting is
deterministic, and per-pair attempted equality between
the early-exit arms is asserted; the scan arm (design
D/E) always attempts the full range by construction and
is recorded as such.

The batch comparison (flagsx_vs_prod_batch_d0_t2) is the
pure batch throughput report, kept strictly separate
from the search comparisons: production bal_v_batch2 vs
the EXP-022 flags batch bal_v_batchf2, both digest
storing and flag extracting as in EXP-022.

Predeclared verdict rule (EXP026_MASK_SEARCH.md):
VERIFIED IMPROVEMENT (search scope) iff the primary
comparison maskB_vs_prod_search_d0_t2 is significant
(adjusted CI entirely above 0) in every session and
pooled under the EXP-017 statistic. Gates
(exp026_gates.py, all PASS, plus the ASan/UBSan driver)
precede any timing.
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
OUT_DIR = os.path.join(HERE, "exp026")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(
    ROOT, "research/sha256d/phase6/benchmarks"))
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import GENESIS  # noqa: E402
from exp017_paired_bench import (  # noqa: E402
    node_info, sample_env, env_interval, sha256_file)

BLOCK = 65_536

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

TARGETS = {
    "d0": (0).to_bytes(32, "little"),
    "hit": (1 << 244).to_bytes(32, "little"),
}

# comparison -> (mode, threads, density, arm_a, arm_b)
COMPARISONS = {
    "tern_vs_prod_search_d0_t2": ("search", 2, "d0", "prod", "T"),
    "tern_vs_maskC_search_d0_t2": ("search", 2, "d0", "C", "T"),
    "dual_vs_prod_search_d0_t2": ("search", 2, "d0", "prod", "D"),
    "dual_vs_maskC_search_d0_t2": ("search", 2, "d0", "C", "D"),
    "control_maskC_vs_maskC_d0_t2": ("search", 2, "d0", "C", "C"),
    "tern_vs_prod_search_d0_t1": ("search", 1, "d0", "prod", "T"),
    "dual_vs_prod_search_d0_t1": ("search", 1, "d0", "prod", "D"),
}

MANIFEST_FILES = {
    "production_source":
        "research/sha256d/extreme_optimization/src/avx512_mb.c",
    "production_binary":
        "research/sha256d/extreme_optimization/src/"
        "libbal_v512_exp022base.so",
    "mask_source":
        "research/sha256d/extreme_optimization/src/"
        "avx512_mb_mask_search.c",
    "mask_binary":
        "research/sha256d/extreme_optimization/src/libbal_m512.so",
    "tern_source":
        "research/sha256d/extreme_optimization/src/"
        "avx512_mb_exp026_tern.c",
    "tern_binary":
        "research/sha256d/extreme_optimization/src/libbal_e26t.so",
    "dual_source":
        "research/sha256d/extreme_optimization/src/"
        "avx512_mb_exp026_dual.c",
    "dual_binary":
        "research/sha256d/extreme_optimization/src/libbal_e26d.so",
}

BUILD_CMD = ("gcc -O3 -mavx512f -mavx512bw -shared -fPIC "
             "-Wall -Wextra <src> -lpthread")


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


class Arms:
    def __init__(self):
        base = ctypes.CDLL(os.path.join(
            EO_SRC, "libbal_v512_exp022base.so"))
        self.search_fns = {}
        fn = base.bal_v_search2
        fn.restype = ctypes.c_int
        fn.argtypes = SEARCH_SIG
        self.search_fns["prod"] = fn
        mlib = ctypes.CDLL(os.path.join(EO_SRC, "libbal_m512.so"))
        fn = mlib.bal_v_msearcha2
        fn.restype = ctypes.c_int
        fn.argtypes = SEARCH_SIG
        self.search_fns["C"] = fn
        tlib = ctypes.CDLL(os.path.join(EO_SRC, "libbal_e26t.so"))
        fn = tlib.bal_v_e26t_search2
        fn.restype = ctypes.c_int
        fn.argtypes = SEARCH_SIG
        self.search_fns["T"] = fn
        dlib = ctypes.CDLL(os.path.join(EO_SRC, "libbal_e26d.so"))
        fn = dlib.bal_v_e26d_search2
        fn.restype = ctypes.c_int
        fn.argtypes = SEARCH_SIG
        self.search_fns["D"] = fn
        self.prod_batch = base.bal_v_batch2
        self.prod_batch.restype = ctypes.c_int
        self.prod_batch.argtypes = BATCH_SIG
        flib = ctypes.CDLL(os.path.join(EO_SRC, "libbal_f512.so"))
        self.flags_batch = flib.bal_v_batchf2
        self.flags_batch.restype = ctypes.c_int
        self.flags_batch.argtypes = BATCH_SIG

    def search(self, impl, start, count, threads, target):
        nonce = ctypes.c_uint32(0)
        dig = ctypes.create_string_buffer(32)
        att = ctypes.c_uint64(0)
        back = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = self.search_fns[impl](
            GENESIS, start, count, threads, target,
            ctypes.byref(nonce), dig, ctypes.byref(att),
            ctypes.byref(back))
        dt = time.perf_counter() - t0
        return rc, att.value, back.value, dt

    def batch(self, impl, start, count, threads, target):
        if impl == "prod":
            hashes = ctypes.create_string_buffer(32 * count)
            flags = ctypes.create_string_buffer(count)
            fn = self.prod_batch
            args = (hashes, flags)
        else:
            flagbits = ctypes.create_string_buffer((count + 7) // 8)
            digests = ctypes.create_string_buffer(32 * count)
            fn = self.flags_batch
            args = (flagbits, digests)
        att = ctypes.c_uint64(0)
        back = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = fn(GENESIS, start, count, threads, target, args[0],
                args[1], ctypes.byref(att), ctypes.byref(back))
        dt = time.perf_counter() - t0
        return rc, att.value, back.value, dt


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


def run_call(arms, mode, impl, start, count, threads, target,
             density):
    first = sample_env()
    if mode == "search":
        rc, attempted, backend, dt = arms.search(
            impl, start, count, threads, target)
        assert rc in (0, 1), (impl, rc)
        if density == "d0":
            assert rc == 0 and attempted == count, (
                impl, rc, attempted, count)
        if impl == "S":
            assert attempted == count, (impl, attempted, count)
    else:
        rc, attempted, backend, dt = arms.batch(
            impl, start, count, threads, target)
        assert rc == 0, (impl, rc)
        assert attempted == count, (impl, attempted, count)
        assert backend == expected_backend(count, threads), (
            impl, backend)
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

    mode, threads, density, impl_a, impl_b = COMPARISONS[
        args.comparison]
    target = TARGETS[density]

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
    model, flags = cpu_info()

    record = {
        "experiment": "EXP-026",
        "session_id": session_id,
        "comparison": args.comparison,
        "arm_a_reference": impl_a,
        "arm_b_candidate": impl_b,
        "mode": mode,
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
            "cpu_model": model,
            "relevant_flags": flags,
            "note": ("host recorded per session; both arms built "
                     "with -mavx512f -mavx512bw only"),
        },
        "manifest": manifest,
        "correctness_basis": (
            "exp026_gates.py all PASS before timing plus the "
            "ASan/UBSan driver clean: differentials vs hashlib "
            "through the new group code, candidate-set "
            "equivalence vs production search and a hashlib "
            "recount at four densities, target and nonce "
            "boundaries, exact wave accounting, genesis, "
            "invalid-argument codes"),
        "pairs": [],
    }

    block_index = 0
    for _ in range(args.warmup_pairs):
        start = block_index * args.block_size
        run_call(arms, mode, impl_a, start, args.block_size,
                 threads, target, density)
        run_call(arms, mode, impl_b, start, args.block_size,
                 threads, target, density)
        block_index += 1

    for pair_index in range(args.pairs):
        start = block_index * args.block_size
        b_first = rng.random() < 0.5
        order = ("B", "A") if b_first else ("A", "B")
        results = {}
        for label in order:
            impl = impl_b if label == "B" else impl_a
            results[label] = run_call(
                arms, mode, impl, start, args.block_size, threads,
                target, density)
        ra, rb = results["A"], results["B"]
        if mode == "search" and density == "hit" and \
                impl_a != "S" and impl_b != "S":
            assert ra["attempted"] == rb["attempted"], (
                pair_index, ra["attempted"], rb["attempted"])
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
    record["coverage"] = {
        "attempted_a": total_a, "attempted_b": total_b,
        "requested_each": args.pairs * args.block_size}

    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
