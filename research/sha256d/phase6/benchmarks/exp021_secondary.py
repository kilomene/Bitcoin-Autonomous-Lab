#!/usr/bin/env python3
"""EXP-021 secondary analysis (descriptive, not the
verdict statistic).

The predeclared EXP-021 statistic times pool blocks
by their makespan: workers start on a barrier and the
block ends when the slowest worker finishes. That is
exact for homogeneous pools, whose workers run at the
same speed, but a production search does not barrier:
each worker takes the next span when it finishes, so
a mixed pool's steady-state throughput is the SUM of
its workers' concurrent rates, not the makespan rate
of equal blocks. The paired driver recorded every
worker's own elapsed time, so the implied
continuous-assignment rate of every recorded call can
be recomputed exactly:

    implied rate = sum over workers of
                   part_count / worker_elapsed

This script recomputes the paired log-ratios from the
implied rates and runs the same adjusted statistic
(exp021_analyze.analyse_group) over them, and also
tabulates per-worker median rates by family and pool
context (descriptive; worker contexts come from
different sessions, so cross-context comparisons
carry the session-conditions caveat). Output is a
new timestamped JSON under benchmarks/exp021/;
originals are never modified. The EXP-021 verdict
rests on the predeclared makespan statistic in
exp021_analyze.py; this file exists so the record
does not overclaim what the barrier design proves.
"""
import glob
import json
import os
import statistics
import sys
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(HERE, "exp021")
sys.path.insert(0, HERE)
from exp021_analyze import analyse_group  # noqa: E402


def implied_rate(call):
    total = 0.0
    for w in call["workers"]:
        if w["part_count"] > 0:
            total += w["part_count"] / w["elapsed_s"]
    return total


def main():
    files = sorted(glob.glob(os.path.join(SESSION_DIR,
                                          "session_*.json")))
    if not files:
        print("no EXP-021 sessions found", file=sys.stderr)
        return 1
    groups = {}
    worker_rates = {}
    for path in files:
        with open(path) as fh:
            sess = json.load(fh)
        for pair in sess["pairs"]:
            for arm in ("a", "b"):
                call = pair[arm]
                for w in call["workers"]:
                    if w["part_count"] > 0:
                        key = (call["implementation"],
                               w["family"])
                        worker_rates.setdefault(key, []).append(
                            w["part_count"] / w["elapsed_s"])
        new_pairs = []
        for pair in sess["pairs"]:
            ra = implied_rate(pair["a"])
            rb = implied_rate(pair["b"])
            npair = dict(pair)
            npair["a"] = dict(pair["a"], rate_hs=ra)
            npair["b"] = dict(pair["b"], rate_hs=rb)
            import math
            npair["log_ratio_b_over_a"] = math.log(rb / ra)
            new_pairs.append(npair)
        nsess = dict(sess, pairs=new_pairs)
        groups.setdefault(sess["comparison"], []).append(nsess)

    out = {
        "experiment": "EXP-021",
        "kind": "secondary descriptive analysis: implied "
                "continuous-assignment rates recomputed "
                "from recorded per-worker elapsed times; "
                "NOT the predeclared verdict statistic",
        "analysis_utc": datetime.now(timezone.utc).isoformat(),
        "comparisons": {},
        "worker_median_rates_hs": {
            f"{pool}/{fam}": {
                "calls": len(v),
                "median_rate_hs": float(statistics.median(v)),
            }
            for (pool, fam), v in sorted(worker_rates.items())
        },
    }
    for name in sorted(groups):
        sessions = sorted(groups[name],
                          key=lambda s: s["session_id"])
        rng = np.random.default_rng(21099 + (abs(hash(name)) % 100000))
        out["comparisons"][name] = analyse_group(name, sessions, rng)
        pooled = out["comparisons"][name]["pooled"]
        print(f"{name}: implied-rate adjusted pooled "
              f"{pooled['adjusted']['mean_log_ratio']:+.4f} "
              f"CI {pooled['adjusted']['ci95']} "
              f"significant={pooled['adjusted']['significant_b_faster']}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(
        SESSION_DIR, f"secondary_implied_rates_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(
            SESSION_DIR,
            f"secondary_implied_rates_{stamp}_r{suffix}.json")
        suffix += 1
    with open(path, "x") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
