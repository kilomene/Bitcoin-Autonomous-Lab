#!/usr/bin/env python3
"""EXP-054 paired benchmark driver (EXP-017 protocol).

One invocation is one independent session for one named
comparison. Protocol machinery follows the EXP-041 /
EXP-053 drivers: paired 65,536-hash blocks, randomised
AB or BA order per pair, steal and runnable-load
covariates sampled around every counted call, attempted
asserted equal to the block size on every call. The
steal covariate uses the EXP-017 / EXP-041 form
(second steal sample minus first steal sample); the
EXP-053 driver's D-1 transcription defect (second
steal minus first TOTAL jiffies; see the EXP-053
audit, section 5) is deliberately not inherited.
Verdicts come only from exp054_analyze.py applying the
predeclared EXP-017 statistic, the Bonferroni
correction and the EXP-054 predeclaration's verdict
mapping; this driver records data only.

Arms are the counted search entries called directly
(the EXP-017 / EXP-020 / EXP-041 scope):
  prod_dual_search  bal_vd_search2 of the shipped
                    .local/cpu/libbal_v512dual.so
  e54gran_g{G}_search  bal_vg{G}_search2 of the
                    EXP-054 research library, for
                    G in {1, 2, 4, 8}
over a no-hit range (target integer 1, never met), so
every call walks its full block. The session design
(3 sessions per candidate point, 2 control sessions
and 2 build-control sessions, 30,000 pairs each,
390,000 pairs total) is fixed by
research/sha256d/exp054/PREDECLARATION.md, whose
sha256 is recorded in every session manifest.

Raw output is append-only under RAW_RESULTS/sessions/;
a session interrupted mid-run leaves no file and is
rerun, never resumed.
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
from bench_harness import GENESIS  # noqa: E402

BLOCK = 65_536
THREADS = 2
NO_HIT_TARGET_LE = (1).to_bytes(32, "little")
PREDECLARATION_SHA256 = (
    "2aebc8ede2ed62b56a800976898be4b86d9570ccaea5776b6171aaab4a111e46")


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
        dual = ctypes.CDLL(os.path.join(
            ROOT, ".local/cpu/libbal_v512dual.so"))
        variant = ctypes.CDLL(os.path.join(
            HERE, "src/libbal_e54gran.so"))
        self.search_fns = {
            "prod_dual_search": counted_search(dual.bal_vd_search2),
        }
        for g in (1, 2, 4, 8):
            self.search_fns[f"e54gran_g{g}_search"] = counted_search(
                getattr(variant, f"bal_vg{g}_search2"))

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
        if name in self.__dict__.get("search_fns", {}):
            return lambda s, c, t: self._search(name, s, c, t)
        raise AttributeError(name)


COMPARISONS = {
    "control_dual_self": ("prod_dual_search", "prod_dual_search"),
    "search_g1_vs_dual": ("prod_dual_search", "e54gran_g1_search"),
    "search_g2_vs_dual": ("prod_dual_search", "e54gran_g2_search"),
    "search_g4_vs_dual": ("prod_dual_search", "e54gran_g4_search"),
    "search_g8_vs_dual": ("prod_dual_search", "e54gran_g8_search"),
}

MANIFEST_FILES = {
    "production_dual_source": "mining/cpu/bal_avx512_dual.c",
    "production_dual_binary": ".local/cpu/libbal_v512dual.so",
    "variant_source":
        "research/sha256d/exp054/src/avx512_dual_exp054_granularity.c",
    "variant_binary":
        "research/sha256d/exp054/src/libbal_e54gran.so",
    "predeclaration": "research/sha256d/exp054/PREDECLARATION.md",
    "build_manifest": "research/sha256d/exp054/RAW_RESULTS/"
                      "build_manifest.json",
    "sizing_probe": "research/sha256d/exp054/RAW_RESULTS/"
                    "sizing_probe.json",
    "gates_log": "research/sha256d/exp054/RAW_RESULTS/gates.log",
}


def run_call(arms, impl, start, count):
    first = sample_env()
    rc, attempted, backend, dt = getattr(arms, impl)(
        start, count, THREADS)
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
    ap.add_argument("--pairs", type=int, default=30_000)
    ap.add_argument("--warmup-pairs", type=int, default=16)
    ap.add_argument("--block-size", type=int, default=BLOCK)
    args = ap.parse_args()
    assert args.block_size == BLOCK, "EXP-017 protocol fixes 65,536"
    assert args.pairs >= 100, "a session needs at least 100 pairs"

    impl_a, impl_b = COMPARISONS[args.comparison]
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
    assert manifest["predeclaration"]["sha256"] == \
        PREDECLARATION_SHA256, "predeclaration changed since design"
    manifest["driver"] = {"path": os.path.relpath(
        os.path.abspath(__file__), ROOT),
        "sha256": sha256_file(os.path.abspath(__file__))}
    manifest["build_commands"] = {
        "variant": "gcc -O3 -shared -fPIC -I mining/cpu "
                   "-mavx512f -mavx512bw (restricted set, "
                   "never -march=native); see "
                   "RAW_RESULTS/build_manifest.json",
        "production": "prebuilt gated library, source and "
                      "binary hashes recorded above",
    }

    record = {
        "experiment": "EXP-054 (EXP-017 protocol)",
        "session_id": session_id,
        "comparison": args.comparison,
        "scope": "search",
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
            "Gate 2 passed before the campaign "
            "(RAW_RESULTS/gates.log): every granularity "
            "point passed the shared gate set (108,000 "
            "randomized differentials vs hashlib, "
            "genesis, boundaries, template variations, "
            "target equality and minus one, candidate "
            "set, exact dual wave accounting at 50016), "
            "the production library passed the same set "
            "as control, each point's batch outputs were "
            "byte-identical to the production binary "
            "over 4,194,304 digests, and search agreement "
            "held under the EXP-047 corrected criterion; "
            "the driver additionally asserts attempted "
            "and backend equal the block size on every "
            "timed call"),
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
        if (pair_index + 1) % 2000 == 0:
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
