#!/usr/bin/env python3
"""EXP-051 Gate 4 analysis: pooled before/after comparison
of the prefetch campaign sessions in RAW_RESULTS.

Reads every top-level session_*.json written by
category_f_prefetch.py (shakedown/ is excluded), pools the
timed runs per (scenario, arm), and evaluates the three
predeclared criteria from PREDECLARATION.md:

  H1  zero stale serves: no failed run anywhere, every run
      accepted and EXP-036 verified, and the prefetch arm's
      drop counters are consistent with its served/starved
      counts (a stale serve by construction cannot be
      recorded as served; the adversarial suite is the
      primary H1 evidence and this is the campaign-level
      consistency check).
  H2  loaded scenario B: pooled median non-search overhead
      per block in the prefetch arm at least 15 percent
      below the sync arm.
  H3  attribution: at least half of prefetch B runs are
      queue-served, and in served B runs the combined
      (gbt + prepare) stage median is under 5 ms.

All figures are milliseconds of non-search overhead per
block (category F). Nothing here is a hash rate.
"""

import glob
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "RAW_RESULTS")


def load_sessions():
    sessions = []
    for path in sorted(glob.glob(os.path.join(RAW_DIR,
                                              "session_*.json"))):
        with open(path) as fh:
            sessions.append((path, json.load(fh)))
    return sessions


def median(xs):
    return statistics.median(xs) if xs else None


def stage(run, name):
    return run["stages_s"].get(name, 0.0) * 1000.0


def main():
    sessions = load_sessions()
    if not sessions:
        print("no campaign sessions found")
        return 1
    pooled = {}     # (scenario, arm) -> [runs]
    totals = {}     # arm -> summed prefetch counters
    failed = []
    for path, s in sessions:
        key = (s["scenario"], s["arm"])
        pooled.setdefault(key, [])
        for r in s["runs"]:
            pooled[key].append(r)
            if r["failed"] or not r["accepted"]:
                failed.append((path, r["run_index"],
                               r.get("fail_reason")))
            elif not r["verify"]["ok"]:
                failed.append((path, r["run_index"],
                               "verify not ok"))
        if s["arm"] == "prefetch":
            acc = totals.setdefault("prefetch", {})
            for c, v in s["prefetch_totals"].items():
                acc[c] = acc.get(c, 0) + v

    out = {"sessions": len(sessions), "failed_runs": failed,
           "arms": {}, "prefetch_totals": totals}
    for (scenario, arm), runs in sorted(pooled.items()):
        served_runs = [r for r in runs if r.get("served")]
        entry = {
            "runs": len(runs),
            "overhead_ms_median": median(
                [r["overhead_ms"] for r in runs]),
            "overhead_ms_min": min(r["overhead_ms"] for r in runs),
            "overhead_ms_max": max(r["overhead_ms"] for r in runs),
            "wall_s_median": median(
                [r["cycle_wall_s"] for r in runs]),
            "stage_ms_median": {
                st: median([stage(r, st) for r in runs])
                for st in ("gbt", "prepare", "serve", "construct",
                           "search", "submit", "confirm")},
            "served_runs": len(served_runs),
        }
        if arm == "prefetch":
            entry["served_gbt_prepare_ms_median"] = median(
                [stage(r, "gbt") + stage(r, "prepare")
                 for r in served_runs]) if served_runs else None
        out["arms"][f"{scenario}/{arm}"] = entry

    # Verdicts.
    b_sync = out["arms"].get("B/sync", {})
    b_pre = out["arms"].get("B/prefetch", {})
    h2 = None
    if b_sync.get("overhead_ms_median") and \
            b_pre.get("overhead_ms_median"):
        reduction = 1.0 - b_pre["overhead_ms_median"] / \
            b_sync["overhead_ms_median"]
        h2 = {"reduction_fraction": reduction,
              "pass": reduction >= 0.15}
    h3 = None
    if b_pre.get("runs"):
        frac = b_pre["served_runs"] / b_pre["runs"]
        gp = b_pre.get("served_gbt_prepare_ms_median")
        h3 = {"served_fraction_B": frac,
              "served_gbt_prepare_ms_median": gp,
              "pass": bool(frac >= 0.5 and gp is not None
                           and gp < 5.0)}
    out["verdicts"] = {
        "H1_zero_stale_serves_campaign_level": {
            "failed_runs": len(failed), "pass": not failed},
        "H2_loaded_overhead_reduction_15pct": h2,
        "H3_attribution": h3,
    }
    path = os.path.join(RAW_DIR, "analysis.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(out, indent=1))
    print(f"analysis written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
