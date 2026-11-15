#!/usr/bin/env python3
"""EXP-032 paired benchmark driver (EXP-017 protocol).

One invocation is one independent session for one named
comparison. Protocol, identical to the adopted EXP-017
rule: paired 65,536-hash blocks, randomised AB or BA
order per pair, steal and runnable-load covariates sampled
around every counted call, at least 100 pairs per session,
verdicts only from 3 or more sessions with the adjusted
bootstrap CI entirely above 0 in every session and pooled
(exp017_analyze statistic, applied by exp032_analyze.py).

Two scopes are measured, and they are never mixed:

- batch scope: counted batch entry points (bal_*_batch2)
  over the genesis header at the difficulty-1 target,
  exactly as the EXP-017 driver measures them.
- search scope (the headline scope for EXP-032):
  COMPLETE production search calls over a no-hit range of
  65,536 nonces (target 1, so every arm scans the full
  range and finds nothing; attempted must equal the range
  size on every call). Production arms call
  ComputeEngine.search_first_counted or
  ComputeEngine.batch_search on real ComputeEngine
  instances, so the measured time includes dispatch,
  candidate checking and the engine's own bookkeeping.
  Research arms (avx2_search, shani_m4_search, fsearch)
  call their native search entries through the same
  ctypes pattern the engine's native branches use,
  including the engine's verify_candidate recheck on a
  hit (there are no hits at target 1, so that path is
  exercised by the gates, not here); they are labelled
  research wrappers, never production dispatch.

Raw output is append-only under RAW_RESULTS/sessions/;
this driver records data only and makes no verdict.
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
NO_HIT_TARGET = 1  # int target: digest must be < 1; never met


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


def counted_search(fn):
    fn.restype = ctypes.c_int
    fn.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]
    return fn


class Arms:
    def __init__(self, need_engine):
        cpu = os.path.join(ROOT, ".local/cpu")
        _l, self.c_batch_fn, _s = load_lib(
            os.path.join(cpu, "libbal_batch.so"), "bal_c")
        _l2, self.i_batch_fn, _s2 = load_lib(
            os.path.join(cpu, "libbal_intrin.so"), "bal_i")
        vd = ctypes.CDLL(os.path.join(cpu, "libbal_v512dual.so"))
        self.vd_batch_fn = counted(vd.bal_vd_batch2)
        avx2 = ctypes.CDLL(os.path.join(HERE, "libbal_avx2.so"))
        self.a_batch_fn = counted(avx2.bal_a_batch2)
        self.a_search_fn = counted_search(avx2.bal_a_search2)
        h01 = ctypes.CDLL(os.path.join(HERE, "libbal_h01.so"))
        self.m_batch_fn = h01.bal_m_batch2
        self.m_batch_fn.restype = ctypes.c_int
        self.m_batch_fn.argtypes = [
            ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
            ctypes.c_uint, ctypes.c_int, ctypes.c_char_p,
            ctypes.c_char_p, ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint64)]
        self.m_search_fn = h01.bal_m_search2
        self.m_search_fn.restype = ctypes.c_int
        self.m_search_fn.argtypes = [
            ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
            ctypes.c_uint, ctypes.c_int, ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint64)]
        fs = ctypes.CDLL(os.path.join(HERE, "libbal_v512fsearch.so"))
        self.f_search_fn = counted_search(fs.bal_v_searchf2)
        self.engines = {}
        if need_engine:
            from gpu.engine import ComputeEngine
            for req in ("c", "v512", "v512dual", "auto"):
                eng = ComputeEngine(requested=req)
                assert eng.backend == (
                    "c" if req == "c" else req if req != "auto"
                    else "v512dual"), (req, eng.backend)
                self.engines[req] = eng

    # ---- batch arms ----

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
                flags, ctypes.byref(attempted), ctypes.byref(backend))
        dt = time.perf_counter() - t0
        return rc, attempted.value, backend.value, dt

    def c_batch(self, start, count, threads):
        return self._plain_batch(self.c_batch_fn, start, count,
                                 threads)

    def shani_i_batch(self, start, count, threads):
        return self._plain_batch(self.i_batch_fn, start, count,
                                 threads)

    def v512dual_batch(self, start, count, threads):
        return self._counted_batch(self.vd_batch_fn, start, count,
                                   threads)

    def avx2_batch(self, start, count, threads):
        return self._counted_batch(self.a_batch_fn, start, count,
                                   threads)

    def shani_m4_batch(self, start, count, threads):
        hashes = ctypes.create_string_buffer(32 * count)
        flags = ctypes.create_string_buffer(count)
        attempted = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = self.m_batch_fn(GENESIS, start, count, threads, 4,
                             DIFF1_LE, hashes, flags,
                             ctypes.byref(attempted))
        dt = time.perf_counter() - t0
        return rc, attempted.value, attempted.value, dt

    # ---- search arms (complete production search calls) ----

    def _engine_search(self, req, start, count, threads):
        eng = self.engines[req]
        t0 = time.perf_counter()
        hit, attempted, _secs = eng.search_first_counted(
            GENESIS, NO_HIT_TARGET, start, count)
        dt = time.perf_counter() - t0
        assert hit is None, (req, hit)
        return 0, attempted, attempted, dt

    def prod_c_search(self, start, count, threads):
        return self._engine_search("c", start, count, threads)

    def prod_v512_search(self, start, count, threads):
        return self._engine_search("v512", start, count, threads)

    def prod_dual_search(self, start, count, threads):
        return self._engine_search("v512dual", start, count, threads)

    def prod_flags_batchsearch(self, start, count, threads):
        eng = self.engines["auto"]
        t0 = time.perf_counter()
        cands, stats = eng.batch_search(
            GENESIS, NO_HIT_TARGET, start, count)
        dt = time.perf_counter() - t0
        assert stats["batch_path"] == "flags", stats["batch_path"]
        assert stats["unique_coverage"] == count, stats
        assert not cands, cands
        return 0, count, stats["backend_hashes"], dt

    def _counted_search(self, fn, start, count, threads):
        nonce = ctypes.c_uint32(0)
        digest = ctypes.create_string_buffer(32)
        attempted = ctypes.c_uint64(0)
        backend = ctypes.c_uint64(0)
        target_le = NO_HIT_TARGET.to_bytes(32, "little")
        t0 = time.perf_counter()
        rc = fn(GENESIS, start, count, threads, target_le,
                ctypes.byref(nonce), digest,
                ctypes.byref(attempted), ctypes.byref(backend))
        dt = time.perf_counter() - t0
        assert rc == 0, rc
        return rc, attempted.value, backend.value, dt

    def avx2_search(self, start, count, threads):
        return self._counted_search(self.a_search_fn, start, count,
                                    threads)

    def fsearch(self, start, count, threads):
        return self._counted_search(self.f_search_fn, start, count,
                                    threads)

    def shani_m4_search(self, start, count, threads):
        nonce = ctypes.c_uint32(0)
        digest = ctypes.create_string_buffer(32)
        attempted = ctypes.c_uint64(0)
        target_le = NO_HIT_TARGET.to_bytes(32, "little")
        t0 = time.perf_counter()
        rc = self.m_search_fn(GENESIS, start, count, threads, 4,
                              target_le, ctypes.byref(nonce), digest,
                              ctypes.byref(attempted))
        dt = time.perf_counter() - t0
        assert rc == 0, rc
        return rc, attempted.value, attempted.value, dt


BATCH_COMPARISONS = {
    "batch_avx2_vs_c": ("c_batch", "avx2_batch"),
    "batch_avx2_vs_v512dual": ("v512dual_batch", "avx2_batch"),
    "batch_shani_m4_vs_c": ("c_batch", "shani_m4_batch"),
    "batch_shani_m4_vs_v512dual": ("v512dual_batch", "shani_m4_batch"),
    "batch_shani_i_vs_c": ("c_batch", "shani_i_batch"),
}

SEARCH_COMPARISONS = {
    "search_dual_vs_c": ("prod_c_search", "prod_dual_search"),
    "search_dual_vs_flagsbatch": ("prod_flags_batchsearch",
                                  "prod_dual_search"),
    "search_fsearch_vs_v512": ("prod_v512_search", "fsearch"),
    "search_fsearch_vs_dual": ("prod_dual_search", "fsearch"),
    "search_avx2_vs_dual": ("prod_dual_search", "avx2_search"),
    "search_shani_m4_vs_dual": ("prod_dual_search",
                                "shani_m4_search"),
}

COMPARISONS = dict(BATCH_COMPARISONS)
COMPARISONS.update(SEARCH_COMPARISONS)

MANIFEST_FILES = {
    "production_c_source": "mining/cpu/bal_batch.c",
    "production_c_binary": ".local/cpu/libbal_batch.so",
    "production_intrin_source": "mining/cpu/bal_sha_intrin.c",
    "production_intrin_binary": ".local/cpu/libbal_intrin.so",
    "production_dual_source": "mining/cpu/bal_avx512_dual.c",
    "production_dual_binary": ".local/cpu/libbal_v512dual.so",
    "production_flags_source": "mining/cpu/bal_avx512_flags.c",
    "production_flags_binary": ".local/cpu/libbal_v512flags.so",
    "engine_source": "gpu/engine.py",
    "avx2_source": "research/sha256d/exp032/src/avx2_mb.c",
    "avx2_binary": "research/sha256d/exp032/libbal_avx2.so",
    "h01_source": "research/sha256d/exp032/src/h01_multistream.c",
    "h01_binary": "research/sha256d/exp032/libbal_h01.so",
    "fsearch_source": "research/sha256d/exp032/src/avx512_flags_search.c",
    "fsearch_binary": "research/sha256d/exp032/libbal_v512fsearch.so",
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
    scope = "batch" if args.comparison in BATCH_COMPARISONS \
        else "search"
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

    arms = Arms(need_engine=(scope == "search"))
    manifest = {}
    for name, rel in MANIFEST_FILES.items():
        full = os.path.join(ROOT, rel)
        manifest[name] = {"path": rel, "sha256": sha256_file(full)}
    manifest["driver"] = {"path": os.path.relpath(
        os.path.abspath(__file__), ROOT),
        "sha256": sha256_file(os.path.abspath(__file__))}
    manifest["build_commands"] = {
        "avx2": "gcc -O3 -mavx2 -shared -fPIC src/avx2_mb.c",
        "h01": "gcc -O3 -msha -mssse3 -shared -fPIC "
               "src/h01_multistream.c",
        "fsearch": "gcc -O3 -mavx512f -mavx512bw -shared -fPIC "
                   "src/avx512_flags_search.c",
        "production": "prebuilt gated libraries, source and "
                      "binary hashes recorded above",
    }

    record = {
        "experiment": "EXP-032 (EXP-017 protocol)",
        "session_id": session_id,
        "comparison": args.comparison,
        "scope": scope,
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
        "manifest": manifest,
        "correctness_basis": (
            "every arm passed the EXP-032 gates "
            "(exp032_gates.py): batch digests byte-identical "
            "to hashlib over genesis, random headers and the "
            "2^32 boundary; search entries find the genesis "
            "nonce and planted targets and report exact "
            "attempted counts on no-hit ranges; the driver "
            "additionally asserts attempted == block size on "
            "every timed call"),
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
