"""EXP-039 paired benchmark driver (EXP-017 protocol).

Adapted from the EXP-032 driver (exp032_paired_bench.py)
with the protocol machinery unchanged: paired
65,536-hash blocks, randomised AB or BA order per pair,
steal and runnable-load covariates sampled around every
counted call, at least 100 pairs per session, verdicts
only from 3 or more sessions with the adjusted
bootstrap CI entirely above 0 in every session and
pooled (exp017_analyze statistic, applied by
exp039_analyze.py).

Every arm is a PRODUCTION arm: the batch arms call the
counted batch entries of the production libraries in
.local/cpu (bal_c_batch2, bal_a_batch2, bal_m_batch2 at
streams 4) over the genesis header at the difficulty-1
target (category D, batch scope), and the search arms
call ComputeEngine.search_first_counted on production
ComputeEngine instances pinned with requested= (category
E, complete production search over a no-hit range of
65,536 nonces at target 1; attempted must equal the
range size on every call). The two scopes are measured
and reported separately and are never mixed.

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
        avx2 = ctypes.CDLL(os.path.join(cpu, "libbal_avx2.so"))
        self.a_batch_fn = counted(avx2.bal_a_batch2)
        h01 = ctypes.CDLL(os.path.join(cpu, "libbal_shani.so"))
        self.m_batch_fn = h01.bal_m_batch2
        self.m_batch_fn.restype = ctypes.c_int
        self.m_batch_fn.argtypes = [
            ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
            ctypes.c_uint, ctypes.c_int, ctypes.c_char_p,
            ctypes.c_char_p, ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint64)]
        self.engines = {}
        if need_engine:
            from gpu.engine import ComputeEngine
            for req in ("c", "shani", "avx2"):
                eng = ComputeEngine(requested=req)
                assert eng.backend == req, (req, eng.backend)
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

    def prod_shani_search(self, start, count, threads):
        return self._engine_search("shani", start, count, threads)

    def prod_avx2_search(self, start, count, threads):
        return self._engine_search("avx2", start, count, threads)


BATCH_COMPARISONS = {
    "batch_avx2_vs_c": ("c_batch", "avx2_batch"),
    "batch_shani_m4_vs_c": ("c_batch", "shani_m4_batch"),
}

SEARCH_COMPARISONS = {
    "search_avx2_vs_c": ("prod_c_search", "prod_avx2_search"),
    "search_shani_vs_c": ("prod_c_search", "prod_shani_search"),
}

COMPARISONS = dict(BATCH_COMPARISONS)
COMPARISONS.update(SEARCH_COMPARISONS)

MANIFEST_FILES = {
    "production_c_source": "mining/cpu/bal_batch.c",
    "production_c_binary": ".local/cpu/libbal_batch.so",
    "production_avx2_source": "mining/cpu/bal_avx2_mb.c",
    "production_avx2_binary": ".local/cpu/libbal_avx2.so",
    "production_shani_source": "mining/cpu/bal_shani_streams.c",
    "production_shani_core": "mining/cpu/bal_shani_core.h",
    "production_shani_binary": ".local/cpu/libbal_shani.so",
    "production_probe_source": "mining/cpu/bal_fallback_probe.c",
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
        "avx2": "mining/cpu/build.py build_avx2: gcc -O3 "
                "-mavx2 (kernel TU) and no vector flags "
                "(probe TU), -shared -fPIC",
        "shani": "mining/cpu/build.py build_shani: gcc -O3 "
                 "-msha -mssse3 (kernel TU) and no vector "
                 "flags (probe TU), -shared -fPIC",
        "production": "prebuilt gated libraries, source and "
                      "binary hashes recorded above",
    }

    record = {
        "experiment": "EXP-039 (EXP-017 protocol)",
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
            "every arm is gated by the EXP-039 production "
            "integration suite "
            "(tests/test_exp039_fallback_integration.py): "
            "124,351 batch digests per kernel through the "
            "ComputeEngine seam byte-identical to hashlib "
            "including the 2^32 boundary; candidate sets "
            "identical to the hashlib recount at densities "
            "0, 2^-16, 2^-8 and 1; planted-hit searches "
            "return exact CPU digests and no-hit searches "
            "report attempted == count; the driver "
            "additionally asserts attempted == block size "
            "on every timed call"),
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
