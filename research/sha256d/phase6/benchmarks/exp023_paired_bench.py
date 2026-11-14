#!/usr/bin/env python3
"""EXP-023 paired benchmark driver (Y-076/Y-077).

One invocation is one independent session for one named
comparison. The paired unit is sixteen candidate builds;
the two arms alternate in randomised AB or BA order with
steal and runnable-load covariates sampled around every
timed unit, exactly the EXP-017 design, with the statistic
computed by exp023_analyze.py (which reuses the EXP-017
analyser unchanged). Raw output is append-only under
benchmarks/exp023/.

Arms:
  A "current":   mining.engine.MiningEngine.build_candidate
                 for every step, as production calls it.
  B "amortised": the EXP-023 two-level prototype
                 (exp023_amortized.py): FamilyContext and
                 PreparedTemplate are built inside the
                 timed region, once per unit, then the
                 unit's steps are served from the cache.

Comparisons:
  steps500 / steps100: sixteen extranonce steps on one
    template of 500 / 100 transactions (Y-076's corrected
    extranonce dimension; level-2 reuse).
  family500: sixteen jobs of one family (identical tx
    set and static fields, advancing curtime), one step
    each (Y-077's job-family shape; levels 1+2 reuse).
  churn500: sixteen jobs whose tx sets each differ from
    the base by five replaced transactions (the boundary
    case: level 2 must be rebuilt per job, only level 1
    is reused).
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
OUT_DIR = os.path.join(HERE, "exp023")
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from exp017_paired_bench import env_interval, sample_env  # noqa: E402
from exp023_amortized import (FamilyContext, PAYOUT,  # noqa: E402
                              PreparedTemplate, StubRPC,
                              synth_template)
from mining.engine import MiningEngine  # noqa: E402
from mining.pow import coinbase_subsidy  # noqa: E402

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


class Arms:
    def __init__(self):
        self.stub = StubRPC()
        self.engine = MiningEngine(self.stub, PAYOUT)

    # -- unit builders (untimed): return a closure pair --
    def unit_steps(self, rng, ntx):
        template = synth_template(rng, ntx, segwit_fraction=0.5,
                                  with_commitment=True)
        self.stub.template = template

        def run_a():
            for en in range(STEPS):
                self.engine.build_candidate(template, en)

        def run_b():
            fam = FamilyContext(self.stub, PAYOUT)
            prep = PreparedTemplate(fam, template)
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
            fam = FamilyContext(self.stub, PAYOUT)
            prep = PreparedTemplate(fam, jobs[0])
            for j, job in enumerate(jobs):
                prep.build(j, template=job)

        return run_a, run_b

    def unit_churn(self, rng):
        from exp023_amortized import synth_tx
        from mining.engine import txid_of
        base = synth_template(rng, 500, segwit_fraction=0.5,
                              with_commitment=True)
        jobs = []
        for j in range(STEPS):
            txs = list(base["transactions"])
            fees = sum(tx["fee"] for tx in txs)
            for k in range(5):
                raw = synth_tx(rng, segwit=bool(k % 2))
                fee = rng.randrange(500, 5000)
                fees += fee - txs[j * 5 + k]["fee"]
                txs[j * 5 + k] = {"txid": txid_of(raw)[::-1].hex(),
                                  "data": raw.hex(), "fee": fee}
            job = dict(base)
            job["transactions"] = txs
            job["coinbasevalue"] = coinbase_subsidy(
                base["height"], 150) + fees
            # The churned set no longer matches the base
            # template's stated witness commitment; drop the
            # field, as a GBT response for this set would
            # carry its own (build_candidate only checks it
            # when present).
            job.pop("default_witness_commitment", None)
            jobs.append(job)
        self.stub.template = base

        def run_a():
            for j, job in enumerate(jobs):
                self.engine.build_candidate(job, j)

        def run_b():
            fam = FamilyContext(self.stub, PAYOUT)
            for j, job in enumerate(jobs):
                prep = PreparedTemplate(fam, job)
                prep.build(j)

        return run_a, run_b


UNITS = {
    "steps500": lambda arms, rng: arms.unit_steps(rng, 500),
    "steps100": lambda arms, rng: arms.unit_steps(rng, 100),
    "family500": lambda arms, rng: arms.unit_family(rng),
    "churn500": lambda arms, rng: arms.unit_churn(rng),
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
    ap.add_argument("--pairs", type=int, default=50)
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
            ("driver", os.path.relpath(os.path.abspath(__file__), ROOT)),
            ("prototype", "research/sha256d/phase6/benchmarks/"
                          "exp023_amortized.py"),
            ("production_reference", "mining/engine.py")):
        manifest[name] = {"path": rel,
                          "sha256": sha256_file(os.path.join(ROOT, rel))}
    record = {
        "experiment": "EXP-023",
        "session_id": session_id,
        "comparison": args.comparison,
        "arm_a_reference": "current_build_candidate",
        "arm_b_candidate": "amortised_two_level",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "unit": f"{STEPS} candidate builds (see driver docstring)",
        "pairs_planned": args.pairs,
        "warmup_pairs": args.warmup_pairs,
        "order_seed": seed,
        "environment_at_start": sample_env(),
        "load_average_at_start": open("/proc/loadavg").read().split()[:3],
        "host": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "cpu_model": cpu_model(),
            "python": platform.python_version(),
            "os_cpu_count": os.cpu_count(),
        },
        "manifest": manifest,
        "correctness_basis": (
            "exp023_gates.py: 1,320 randomised byte-identity "
            "cases of arm B output vs arm A (header, body, "
            "all scalar fields), all gates passed before "
            "timing; record in benchmarks/exp023/"),
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
                "implementation": ("amortised_two_level"
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
            "log_ratio_b_over_a": math.log(rb["rate_hs"] / ra["rate_hs"]),
        })
        if (pair_index + 1) % 20 == 0:
            print(f"{session_id}: {pair_index + 1}/{args.pairs} pairs",
                  flush=True)

    record["finished_utc"] = datetime.now(timezone.utc).isoformat()
    record["environment_at_end"] = sample_env()
    record["load_average_at_end"] = open("/proc/loadavg").read().split()[:3]
    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
