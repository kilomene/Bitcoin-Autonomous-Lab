#!/usr/bin/env python3
"""EXP-041 paired benchmark driver (EXP-017 protocol).

Protocol machinery follows the EXP-039 driver: paired
65,536-hash blocks, randomised AB or BA order per pair,
steal and runnable-load covariates sampled around every
counted call, at least 100 pairs per session, verdicts
only from 3 or more sessions with the adjusted bootstrap
CI entirely above 0 in every session and pooled
(exp017_analyze statistic, applied by exp041_analyze.py).

Arms are counted entry points called directly:
  batch arms (category D): bal_v_batch2 of the
    production libbal_v512.so and bal_e41*_batch2 of
    the EXP-041 variant libraries, over the genesis
    header at the difficulty-1 target.
  search arms (category E): the counted production
    search entries bal_v_search2 (libbal_v512.so) and
    bal_vd_search2 (libbal_v512dual.so, the engine's
    search entry) and bal_e41tmaj_search2, over a
    no-hit range of 65,536 nonces (target integer 1,
    never met); attempted must equal the range size on
    every call. Scope note: the search arms call the
    same counted search entries the production engine
    dispatches to, without the thin Python engine
    wrapper; this is the EXP-017/EXP-020 scope.

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
from bench_harness import GENESIS, DIFF1_LE  # noqa: E402

BLOCK = 65_536
THREADS = 2
NO_HIT_TARGET_LE = (1).to_bytes(32, "little")


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


def counted_batch(fn):
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
    def __init__(self):
        cpu = os.path.join(ROOT, ".local/cpu")
        src = os.path.join(HERE, "src")
        v512 = ctypes.CDLL(os.path.join(cpu, "libbal_v512.so"))
        dual = ctypes.CDLL(os.path.join(cpu, "libbal_v512dual.so"))
        base = ctypes.CDLL(os.path.join(src, "libbal_e41base.so"))
        tmaj = ctypes.CDLL(os.path.join(src, "libbal_e41tmaj.so"))
        tfull = ctypes.CDLL(os.path.join(src, "libbal_e41tfull.so"))
        self.batch_fns = {
            "prod_v512_batch": counted_batch(v512.bal_v_batch2),
            "e41base_batch": counted_batch(base.bal_e41base_batch2),
            "e41tmaj_batch": counted_batch(tmaj.bal_e41tmaj_batch2),
            "e41tfull_batch": counted_batch(tfull.bal_e41tfull_batch2),
        }
        self.search_fns = {
            "prod_v512_search": counted_search(v512.bal_v_search2),
            "prod_dual_search": counted_search(dual.bal_vd_search2),
            "e41tmaj_search": counted_search(tmaj.bal_e41tmaj_search2),
        }

    def _batch(self, name, start, count, threads):
        hashes = ctypes.create_string_buffer(32 * count)
        flags = ctypes.create_string_buffer(count)
        attempted = ctypes.c_uint64(0)
        backend = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = self.batch_fns[name](GENESIS, start, count, threads,
                                  DIFF1_LE, hashes, flags,
                                  ctypes.byref(attempted),
                                  ctypes.byref(backend))
        dt = time.perf_counter() - t0
        return rc, attempted.value, backend.value, dt

    def _search(self, name, start, count, threads):
        nonce = ctypes.c_uint32(0)
        digest = ctypes.create_string_buffer(32)
        attempted = ctypes.c_uint64(0)
        backend = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = self.search_fns[name](GENESIS, start, count, threads,
                                   NO_HIT_TARGET_LE,
                                   ctypes.byref(nonce), digest,
                                   ctypes.byref(attempted),
                                   ctypes.byref(backend))
        dt = time.perf_counter() - t0
        return rc, attempted.value, backend.value, dt

    def __getattr__(self, name):
        if name in self.__dict__.get("batch_fns", {}):
            return lambda s, c, t: self._batch(name, s, c, t)
        if name in self.__dict__.get("search_fns", {}):
            return lambda s, c, t: self._search(name, s, c, t)
        raise AttributeError(name)


BATCH_COMPARISONS = {
    "control_batch_self": ("prod_v512_batch", "prod_v512_batch"),
    "control_batch_rebuild": ("prod_v512_batch", "e41base_batch"),
    "batch_tmaj_vs_prod": ("prod_v512_batch", "e41tmaj_batch"),
    "batch_tfull_vs_prod": ("prod_v512_batch", "e41tfull_batch"),
}

SEARCH_COMPARISONS = {
    "search_tmaj_vs_v512": ("prod_v512_search", "e41tmaj_search"),
    "search_tmaj_vs_dual": ("prod_dual_search", "e41tmaj_search"),
}

COMPARISONS = dict(BATCH_COMPARISONS)
COMPARISONS.update(SEARCH_COMPARISONS)

MANIFEST_FILES = {
    "production_v512_source": "mining/cpu/bal_avx512_mb.c",
    "production_v512_binary": ".local/cpu/libbal_v512.so",
    "production_dual_source": "mining/cpu/bal_avx512_dual.c",
    "production_dual_binary": ".local/cpu/libbal_v512dual.so",
    "production_build": "mining/cpu/build.py",
    "variant_base_source":
        "research/sha256d/exp041/src/bal_avx512_mb_exp041_base.c",
    "variant_tmaj_source":
        "research/sha256d/exp041/src/bal_avx512_mb_exp041_tmaj.c",
    "variant_tmaj_binary":
        "research/sha256d/exp041/src/libbal_e41tmaj.so",
    "variant_tfull_source":
        "research/sha256d/exp041/src/bal_avx512_mb_exp041_tfull.c",
    "variant_tfull_binary":
        "research/sha256d/exp041/src/libbal_e41tfull.so",
    "variant_base_binary":
        "research/sha256d/exp041/src/libbal_e41base.so",
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
    ap.add_argument("--pairs", type=int, default=160)
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

    arms = Arms()
    manifest = {}
    for name, rel in MANIFEST_FILES.items():
        full = os.path.join(ROOT, rel)
        manifest[name] = {"path": rel, "sha256": sha256_file(full)}
    manifest["driver"] = {"path": os.path.relpath(
        os.path.abspath(__file__), ROOT),
        "sha256": sha256_file(os.path.abspath(__file__))}
    manifest["build_commands"] = {
        "variants": "gcc -O3 -shared -fPIC -I mining/cpu "
                    "-mavx512f -mavx512bw (restricted set, "
                    "never -march=native); see "
                    "RAW_RESULTS/build_manifest.json",
        "production": "prebuilt gated libraries, source and "
                      "binary hashes recorded above",
    }

    record = {
        "experiment": "EXP-041 (EXP-017 protocol)",
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
            "every variant passed the EXP-041 gate set "
            "(test_exp041_gates.py, RAW_RESULTS/gates.log): "
            "108,000 randomized differentials vs hashlib per "
            "variant byte-identical, genesis digest and "
            "search, boundaries, template variations, target "
            "equality and minus one, candidate-set equality, "
            "exact wave accounting; the driver additionally "
            "asserts attempted == block size on every timed "
            "call"),
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
