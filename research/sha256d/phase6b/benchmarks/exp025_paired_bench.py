#!/usr/bin/env python3
"""EXP-025 paired benchmark driver.

The EXP-023 paired driver with arm B replaced by the
EXP-025 repaired cache (exp025_repaired.py). Same
EXP-017 design: paired units of sixteen candidate
builds, randomised AB or BA order, steal and
runnable-load covariates sampled around every timed
unit, statistic computed by the EXP-017 analyser
(exp025_analyze_incremental.py imports analyse_group
unchanged). Raw output is append-only under
benchmarks/exp025/.

Arms:
  A "current":  mining.engine.MiningEngine
                .build_candidate for every step, as
                production calls it.
  B "repaired": the EXP-025 two-level repaired cache.
                RepairedFamily and RepairedTemplate are
                built inside the timed region, once per
                unit; steps are then served from the
                cache. In the family shape, each sibling
                job is served through build(template=job),
                which recomputes the job's full layered
                identity before serving: the identity
                cost is INSIDE the timed region, exactly
                as a production integration would pay it.

Comparisons (500 transactions, as EXP-023):
  steps500:  sixteen extranonce steps on one template.
  family500: sixteen jobs of one family (identical tx
             set and static fields, advancing curtime),
             one step each.

Predeclared performance criterion: VERIFIED only if
the covariate-adjusted 95 percent CI is entirely above
0 in every session and pooled (the adopted EXP-017
rule).
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
P6 = os.path.join(ROOT, "research/sha256d/phase6/benchmarks")
OUT_DIR = os.path.join(HERE, "exp025")
sys.path.insert(0, HERE)
sys.path.insert(0, P6)
sys.path.insert(0, ROOT)

from exp017_paired_bench import env_interval, sample_env  # noqa: E402
from exp023_amortized import PAYOUT, StubRPC, synth_template  # noqa: E402
from exp025_repaired import RepairedFamily, RepairedTemplate  # noqa: E402
from mining.engine import MiningEngine  # noqa: E402

STEPS = 16


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cpu_model():
    with open("/proc/cpuinfo") as fh:
        for line in fh:
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return "unknown"


def cpu_flags():
    with open("/proc/cpuinfo") as fh:
        for line in fh:
            if line.startswith("flags"):
                want = ("avx2", "avx512f", "avx512bw", "sha_ni",
                        "avx512vbmi2", "avx512ifma")
                have = set(line.split(":", 1)[1].split())
                return sorted(f for f in want if f in have)
    return []


class Arms:
    def __init__(self):
        self.stub = StubRPC()
        self.engine = MiningEngine(self.stub, PAYOUT)

    def unit_steps(self, rng, ntx):
        template = synth_template(rng, ntx, segwit_fraction=0.5,
                                  with_commitment=True)
        self.stub.template = template

        def run_a():
            for en in range(STEPS):
                self.engine.build_candidate(template, en)

        def run_b():
            fam = RepairedFamily(self.stub, PAYOUT)
            prep = RepairedTemplate(fam, template)
            for en in range(STEPS):
                prep.build(en)

        return run_a, run_b

    def unit_family(self, rng):
        base = synth_template(rng, 500, segwit_fraction=0.5,
                              with_commitment=True)
        jobs = []
        for j in range(STEPS):
            job = dict(base)
            job["curtime"] = base["curtime"] + j * 30
            jobs.append(job)
        self.stub.template = base

        def run_a():
            for j, job in enumerate(jobs):
                self.engine.build_candidate(job, j)

        def run_b():
            fam = RepairedFamily(self.stub, PAYOUT)
            prep = RepairedTemplate(fam, jobs[0])
            for j, job in enumerate(jobs):
                prep.build(j, template=job)

        return run_a, run_b


UNITS = {
    "steps500": lambda arms, rng: arms.unit_steps(rng, 500),
    "family500": lambda arms, rng: arms.unit_family(rng),
}


def run_unit(fn):
    first = sample_env()
    t0 = time.perf_counter()
    fn()
    dt = time.perf_counter() - t0
    second = sample_env()
    return dt, env_interval(first, second, dt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comparison", required=True,
                    choices=sorted(UNITS))
    ap.add_argument("--pairs", type=int, default=60)
    ap.add_argument("--warmup-pairs", type=int, default=6)
    args = ap.parse_args()
    assert args.pairs >= 40

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_id = f"{stamp}_{args.comparison}"
    path = os.path.join(OUT_DIR, f"session_{session_id}.json")
    suffix = 2
    while os.path.exists(path):
        session_id = f"{stamp}_{args.comparison}_r{suffix}"
        path = os.path.join(OUT_DIR, f"session_{session_id}.json")
        suffix += 1
    seed = int.from_bytes(
        hashlib.sha256(session_id.encode()).digest()[:8], "little")
    rng = random.Random(seed)

    arms = Arms()
    manifest = {}
    for name, rel in (
            ("driver", "research/sha256d/phase6b/benchmarks/"
                       "exp025_paired_bench.py"),
            ("repaired", "research/sha256d/phase6b/benchmarks/"
                         "exp025_repaired.py"),
            ("prototype_reference", "research/sha256d/phase6/"
                                    "benchmarks/exp023_amortized.py"),
            ("production_reference", "mining/engine.py")):
        manifest[name] = {"path": rel,
                          "sha256": sha256_file(
                              os.path.join(ROOT, rel))}
    record = {
        "experiment": "EXP-025",
        "session_id": session_id,
        "comparison": args.comparison,
        "arm_a_reference": "current_build_candidate",
        "arm_b_candidate": "repaired_two_level_cache",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "unit": f"{STEPS} candidate builds (see driver docstring)",
        "pairs_planned": args.pairs,
        "warmup_pairs": args.warmup_pairs,
        "order_seed": seed,
        "environment_at_start": sample_env(),
        "load_average_at_start":
            open("/proc/loadavg").read().split()[:3],
        "host": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "cpu_model": cpu_model(),
            "cpu_flags_relevant": cpu_flags(),
            "python": platform.python_version(),
            "os_cpu_count": os.cpu_count(),
        },
        "manifest": manifest,
        "correctness_basis": (
            "exp025_gates.py: 19 adversarial invalidation "
            "cases, positive reuse controls, and 1,320 "
            "randomised byte-identity cases of arm B output "
            "vs arm A, all passed before timing; records in "
            "benchmarks/exp025/"),
        "pairs": [],
    }

    make_unit = UNITS[args.comparison]
    for _ in range(args.warmup_pairs):
        run_a, run_b = make_unit(arms, rng)
        run_unit(run_a)
        run_unit(run_b)

    for pair_index in range(args.pairs):
        run_a, run_b = make_unit(arms, rng)
        b_first = rng.random() < 0.5
        order = ("B", "A") if b_first else ("A", "B")
        results = {}
        for label in order:
            fn = run_b if label == "B" else run_a
            dt, env = run_unit(fn)
            results[label] = {
                "implementation": ("repaired_two_level_cache"
                                   if label == "B"
                                   else "current_build_candidate"),
                "count": STEPS,
                "elapsed_s": dt,
                "rate_hs": STEPS / dt,
                "env": env,
            }
        ra, rb = results["A"], results["B"]
        record["pairs"].append({
            "pair_index": pair_index,
            "order": "".join(order),
            "b_first": b_first,
            "a": ra,
            "b": rb,
            "log_ratio_b_over_a": math.log(rb["rate_hs"]
                                           / ra["rate_hs"]),
        })
        if (pair_index + 1) % 20 == 0:
            print(f"{session_id}: {pair_index + 1}/{args.pairs} "
                  f"pairs", flush=True)

    record["finished_utc"] = datetime.now(timezone.utc).isoformat()
    record["environment_at_end"] = sample_env()
    record["load_average_at_end"] = \
        open("/proc/loadavg").read().split()[:3]
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
