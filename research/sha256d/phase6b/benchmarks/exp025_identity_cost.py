#!/usr/bin/env python3
"""EXP-025 identity cost micro-measurement.

Medians over repeated calls on one 500-transaction
template (segwit fraction 0.5, with witness commitment),
StubRPC as in the paired benchmarks:

  build_candidate       production, full uncached pass.
  prototype_prepare     EXP-023 PreparedTemplate build
                        (pays the full pass once, checks
                        only the 8-field fingerprint per
                        sibling afterwards).
  repaired_prepare      EXP-025 RepairedTemplate build
                        (full pass plus identity keys).
  identity_of           the EXP-025 sibling identity
                        recomputation alone: what every
                        sibling serve pays before building.
  repaired_step         one repaired build() with no
                        sibling (the steps-shape per-step
                        cost after preparation).

This is a cost decomposition, not a paired benchmark;
the paired verdict comes from exp025_paired_bench.py.
"""
import json
import os
import random
import statistics
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

from exp023_amortized import (FamilyContext, PAYOUT,  # noqa: E402
                              PreparedTemplate, StubRPC,
                              synth_template)
from exp025_repaired import (RepairedFamily,  # noqa: E402
                             RepairedTemplate, identity_of)
from mining.engine import MiningEngine  # noqa: E402

REPS = 30


def median_ms(fn, reps=REPS):
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times)


def main():
    rng = random.Random(25025)
    stub = StubRPC()
    template = synth_template(rng, 500, segwit_fraction=0.5,
                              with_commitment=True)
    stub.template = template
    eng = MiningEngine(stub, PAYOUT)
    fam_p = FamilyContext(stub, PAYOUT)
    fam_r = RepairedFamily(stub, PAYOUT)
    prep_r = RepairedTemplate(fam_r, template)
    results = {
        "build_candidate_ms": median_ms(
            lambda: eng.build_candidate(template, 0)),
        "prototype_prepare_ms": median_ms(
            lambda: PreparedTemplate(fam_p, template)),
        "repaired_prepare_ms": median_ms(
            lambda: RepairedTemplate(fam_r, template)),
        "identity_of_ms": median_ms(
            lambda: identity_of(fam_r, template)),
        "repaired_step_ms": median_ms(
            lambda: prep_r.build(0), reps=200),
    }
    for k, v in results.items():
        print(f"{k}: {v:.3f} ms", flush=True)
    record = {
        "experiment": "EXP-025",
        "kind": "identity cost decomposition (medians, "
                "not a paired benchmark)",
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "host_cpu": open("/proc/cpuinfo").read().split(
            "model name")[1].split(":")[1].split("\n")[0].strip(),
        "template": "500 transactions, segwit fraction 0.5, "
                    "witness commitment present, StubRPC",
        "reps": REPS,
        "medians_ms": results,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(OUT_DIR, f"identity_cost_{stamp}.json")
    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
