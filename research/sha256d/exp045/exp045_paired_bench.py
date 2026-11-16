#!/usr/bin/env python3
"""EXP-045 paired benchmark driver (EXP-017 protocol).

One invocation is one independent session for one named
comparison. Protocol, identical to the adopted EXP-017
rule and to the EXP-032 / EXP-039 drivers: paired
65,536-hash blocks, randomised AB or BA order per pair,
steal and runnable-load covariates sampled around every
counted call, 120 pairs per session, verdicts only from
3 or more sessions with the adjusted bootstrap CI
entirely above 0 in every session and pooled
(exp017_analyze statistic, applied by exp045_analyze.py).

EXP-045 is a 2x2 design over the two factors that differ
between the EXP-032 and EXP-039 AVX2 batch campaigns,
plus the production C comparator measured inside each
harness shape:

- Harness DIRECT: the counted batch entries called via
  ctypes with caller-allocated buffers, exactly the call
  shape both historical batch drivers used (EXP-032
  exp032_paired_bench.py and EXP-039
  exp039_paired_bench.py batch arms are the same code).
- Harness SEAM: production ComputeEngine.batch_search on
  engines pinned by requested=, timed wall-clock around
  the whole engine call, so dispatch, buffer handling,
  flag scanning, candidate checking and stats assembly
  are all inside the measurement, as they are in
  production use.

- Library RESEARCH: research/sha256d/exp032/libbal_avx2.so
  (the .so EXP-032 measured; sha256 recorded per session).
- Library PROD: .local/cpu/libbal_avx2.so (the .so
  EXP-039 measured; sha256 recorded per session).

Comparisons:
  direct_prodlib_avx2_vs_c        (replicates EXP-039 cell)
  direct_researchlib_avx2_vs_c    (replicates EXP-032 cell)
  seam_prodlib_avx2_vs_c
  seam_researchlib_avx2_vs_c
  direct_avx2prod_vs_avx2research (provenance head-to-head,
                                   C removed from the pair)

The seam research-library arm needs one documented
harness construction: the research library has no CPUID
probe symbol, so production dispatch would refuse it.
The driver builds a ComputeEngine pinned to avx2 through
normal dispatch, then replaces the engine's loaded
library object with a ctypes handle on the research
library, argtypes set exactly as gpu/engine.py
_try_avx2 sets them. Only the library object differs.

Thread count is pinned to 2 in both harnesses: the
direct arms pass threads=2, and the seam runs with
BAL_C_THREADS=2 (the engine's documented override), so
gpu.engine.C_THREADS == 2 is asserted and recorded.

The live miner, autopilot and node run throughout and
are never touched. Raw output is append-only under
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
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
sys.path.insert(0, ROOT)
from bench_harness import load_lib, GENESIS, DIFF1_LE  # noqa: E402

BLOCK = 65_536
THREADS = 2
DIFF1_INT = 0xFFFF << 208

C_LIB = os.path.join(ROOT, ".local/cpu/libbal_batch.so")
AVX2_PROD_LIB = os.path.join(ROOT, ".local/cpu/libbal_avx2.so")
AVX2_RESEARCH_LIB = os.path.join(
    ROOT, "research/sha256d/exp032/libbal_avx2.so")


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
    steal_delta = second["cpu_steal_jiffies"] - first["cpu_total_jiffies"]
    return {
        "steal_fraction": (steal_delta / total_delta
                           if total_delta > 0 else 0.0),
        "steal_jiffies_delta": steal_delta,
        "total_jiffies_delta": total_delta,
        "runnable_mean": 0.5 * (first["runnable"] + second["runnable"]),
        "load1_mean": 0.5 * (first["load1"] + second["load1"]),
        "elapsed_s": elapsed,
    }


def counted(fn):
    fn.restype = ctypes.c_int
    fn.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]
    return fn


class Arms:
    def __init__(self, need_engine):
        _l, self.c_batch_fn, _s = load_lib(C_LIB, "bal_c")
        prod = ctypes.CDLL(AVX2_PROD_LIB)
        self.ap_batch_fn = counted(prod.bal_a_batch2)
        research = ctypes.CDLL(AVX2_RESEARCH_LIB)
        self.ar_batch_fn = counted(research.bal_a_batch2)
        self.engines = {}
        if need_engine:
            import gpu.engine as engine_mod
            from gpu.engine import ComputeEngine
            assert engine_mod.C_THREADS == THREADS, (
                "seam thread pin broken", engine_mod.C_THREADS)
            eng_c = ComputeEngine(requested="c")
            assert eng_c.backend == "c", eng_c.backend
            self.engines["c"] = eng_c
            eng_p = ComputeEngine(requested="avx2")
            assert eng_p.backend == "avx2", eng_p.backend
            self.engines["avx2_prod"] = eng_p
            eng_r = ComputeEngine(requested="avx2")
            assert eng_r.backend == "avx2", eng_r.backend
            lib = ctypes.CDLL(AVX2_RESEARCH_LIB)
            counted(lib.bal_a_batch2)
            eng_r._a_lib = lib
            self.engines["avx2_research"] = eng_r

    # ---- direct harness arms ----

    def _plain_batch(self, fn, start, count, threads):
        hashes = ctypes.create_string_buffer(32 * count)
        flags = ctypes.create_string_buffer(count)
        attempted = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = fn(GENESIS, start, count, threads, DIFF1_LE, hashes,
                flags, ctypes.byref(attempted))
        dt = time.perf_counter() - t0
        return rc, attempted.value, attempted.value, dt

    def _counted_batch(self, fn, start, count, threads):
        hashes = ctypes.create_string_buffer(32 * count)
        flags = ctypes.create_string_buffer(count)
        attempted = ctypes.c_uint64(0)
        backend = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = fn(GENESIS, start, count, threads, DIFF1_LE, hashes,
                flags, ctypes.byref(attempted),
                ctypes.byref(backend))
        dt = time.perf_counter() - t0
        return rc, attempted.value, backend.value, dt

    def d_c(self, start, count, threads):
        return self._plain_batch(self.c_batch_fn, start, count,
                                 threads)

    def d_avx2_prod(self, start, count, threads):
        return self._counted_batch(self.ap_batch_fn, start, count,
                                   threads)

    def d_avx2_research(self, start, count, threads):
        return self._counted_batch(self.ar_batch_fn, start, count,
                                   threads)

    # ---- seam harness arms ----

    def _seam_batch(self, key, start, count, threads):
        eng = self.engines[key]
        t0 = time.perf_counter()
        cands, stats = eng.batch_search(GENESIS, DIFF1_INT, start,
                                        count)
        dt = time.perf_counter() - t0
        assert stats["unique_coverage"] == count, stats
        assert stats["batch_path"] == "materialised", stats
        assert not cands, cands
        return 0, count, stats["backend_hashes"], dt

    def s_c(self, start, count, threads):
        return self._seam_batch("c", start, count, threads)

    def s_avx2_prod(self, start, count, threads):
        return self._seam_batch("avx2_prod", start, count, threads)

    def s_avx2_research(self, start, count, threads):
        return self._seam_batch("avx2_research", start, count,
                                threads)


COMPARISONS = {
    "direct_prodlib_avx2_vs_c": ("d_c", "d_avx2_prod"),
    "direct_researchlib_avx2_vs_c": ("d_c", "d_avx2_research"),
    "seam_prodlib_avx2_vs_c": ("s_c", "s_avx2_prod"),
    "seam_researchlib_avx2_vs_c": ("s_c", "s_avx2_research"),
    "direct_avx2prod_vs_avx2research": ("d_avx2_research",
                                        "d_avx2_prod"),
}

CELLS = {
    "direct_prodlib_avx2_vs_c": {
        "harness": "direct", "avx2_library": "production",
        "replicates": "EXP-039 batch cell"},
    "direct_researchlib_avx2_vs_c": {
        "harness": "direct", "avx2_library": "research",
        "replicates": "EXP-032 batch cell"},
    "seam_prodlib_avx2_vs_c": {
        "harness": "seam", "avx2_library": "production",
        "replicates": "neither (new cell)"},
    "seam_researchlib_avx2_vs_c": {
        "harness": "seam", "avx2_library": "research",
        "replicates": "neither (new cell)"},
    "direct_avx2prod_vs_avx2research": {
        "harness": "direct", "avx2_library": "both",
        "replicates": "neither (provenance head-to-head)"},
}

MANIFEST_FILES = {
    "production_c_source": "mining/cpu/bal_batch.c",
    "production_c_binary": ".local/cpu/libbal_batch.so",
    "production_avx2_source": "mining/cpu/bal_avx2_mb.c",
    "production_avx2_binary": ".local/cpu/libbal_avx2.so",
    "research_avx2_source": "research/sha256d/exp032/src/avx2_mb.c",
    "research_avx2_binary": "research/sha256d/exp032/libbal_avx2.so",
    "production_build": "mining/cpu/build.py",
    "engine_source": "gpu/engine.py",
}


def run_call(arms, impl, start, count):
    first = sample_env()
    rc, attempted, backend, dt = getattr(arms, impl)(
        start, count, THREADS)
    second = sample_env()
    assert rc == 0, (impl, rc)
    assert attempted == count, (impl, attempted, count)
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


def cpu_model():
    with open("/proc/cpuinfo") as fh:
        for line in fh:
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return "unknown"


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

    impl_a, impl_b = COMPARISONS[args.comparison]
    need_engine = impl_a.startswith("s_") or impl_b.startswith("s_")
    if need_engine:
        assert os.environ.get("BAL_C_THREADS") == str(THREADS), (
            "seam sessions must run with BAL_C_THREADS=2")
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

    arms = Arms(need_engine=need_engine)
    manifest = {}
    for name, rel in MANIFEST_FILES.items():
        full = os.path.join(ROOT, rel)
        manifest[name] = {"path": rel, "sha256": sha256_file(full)}
    manifest["driver"] = {"path": os.path.relpath(
        os.path.abspath(__file__), ROOT),
        "sha256": sha256_file(os.path.abspath(__file__))}
    manifest["build_commands"] = {
        "avx2_research": "gcc -O3 -mavx2 -shared -fPIC -Wall "
                         "-Wextra src/avx2_mb.c -lpthread "
                         "(exp032/build.sh, single TU)",
        "avx2_production": "mining/cpu/build.py build_avx2: "
                           "gcc -O3 -mavx2 -shared -fPIC for the "
                           "kernel TU compiled separately, "
                           "flag-free probe TU, linked together",
        "production_c": "prebuilt gated library, source and "
                        "binary hashes recorded above",
    }

    record = {
        "experiment": "EXP-045 (EXP-017 protocol)",
        "session_id": session_id,
        "comparison": args.comparison,
        "scope": "batch",
        "cell": CELLS[args.comparison],
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
        "host": {
            "hostname": platform.node(),
            "cpu_model": cpu_model(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "os_cpu_count": os.cpu_count(),
        },
        "miner_heartbeat_at_start": heartbeat_snapshot(),
        "manifest": manifest,
        "correctness_basis": (
            "every arm passed the EXP-045 gates "
            "(exp045_gates.py): at least 131,072 batch "
            "digests per arm path byte-identical to hashlib "
            "through its own harness before any timing; the "
            "driver additionally asserts attempted == block "
            "size on every timed call"),
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
            results[label] = run_call(arms, impl, start,
                                      args.block_size)
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
