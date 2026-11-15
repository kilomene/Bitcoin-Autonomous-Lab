#!/usr/bin/env python3
"""EXP-040 analysis: aggregate the category F session files
in RAW_RESULTS (campaign files only; shakedown_ files are
excluded by the glob) into per-scenario stage statistics,
the non-search overhead fraction, blocks per hour, and the
loaded-versus-empty ratio of medians with a bootstrap
confidence interval over runs. Writes analysis.json next
to the session files and prints the tables the report
quotes. Failed runs are counted and excluded, per the
Hashrate Measurement Specification section 6."""

import glob
import json
import os
import random
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "RAW_RESULTS")
STAGES = ("gbt", "prepare", "construct", "search", "submit",
          "confirm", "rpc_other", "residual")


def quartiles(xs):
    xs = sorted(xs)
    if len(xs) < 4:
        return (min(xs), max(xs))
    q = st.quantiles(xs, n=4, method="inclusive")
    return (q[0], q[2])


def summarize(xs):
    xs = list(xs)
    lo, hi = quartiles(xs)
    return {"n": len(xs), "median": st.median(xs), "min": min(xs),
            "max": max(xs), "iqr": [lo, hi],
            "mean": sum(xs) / len(xs)}


def bootstrap_ratio_ci(a, b, iters=10_000, seed=40040):
    """CI for median(a)/median(b) by resampling runs within
    each scenario. Measured comparison, not an EXP-017
    protocol verdict (the arms are different templates by
    design, not paired work blocks)."""
    rng = random.Random(seed)
    ratios = []
    for _ in range(iters):
        ma = st.median(rng.choice(a) for _ in a)
        mb = st.median(rng.choice(b) for _ in b)
        ratios.append(ma / mb)
    ratios.sort()
    return [ratios[int(0.025 * iters)], ratios[int(0.975 * iters)]]


def main():
    sessions = {"A": [], "B": [], "C": []}
    for path in sorted(glob.glob(os.path.join(RAW, "session_*.json"))):
        with open(path) as fh:
            s = json.load(fh)
        sessions[s["scenario"]].append(s)

    out = {"scenarios": {}, "files": {}}
    run_sets = {}
    for scen, sess in sessions.items():
        runs = [r for s in sess for r in s["runs"]]
        good = [r for r in runs if not r["failed"]]
        failed = [r for r in runs if r["failed"]]
        run_sets[scen] = good
        out["files"][scen] = [os.path.basename(p) for p in
                              sorted(glob.glob(os.path.join(
                                  RAW, f"session_{scen}_*.json")))]
        total_wall = sum(r["cycle_wall_s"] for r in good)
        agg = {
            "sessions": len(sess),
            "runs": len(runs),
            "failed_runs": len(failed),
            "blocks_accepted": len(good),
            "heights": [r["height"] for r in good],
            "end_to_end_s": summarize(
                r["cycle_wall_s"] for r in good),
            "blocks_per_hour_aggregate": (
                len(good) * 3600.0 / total_wall),
            "hashes_per_block": summarize(
                r["hashes_counted"] for r in good),
            "verify_s": summarize(
                r["verify"]["seconds"] for r in good),
            "overhead_fraction": summarize(
                (r["cycle_wall_s"] - r["stages_s"].get("search", 0.0))
                / r["cycle_wall_s"] for r in good),
            "overhead_ms": summarize(
                (r["cycle_wall_s"] - r["stages_s"].get("search", 0.0))
                * 1000.0 for r in good),
            "per_session_median_wall_s": [
                st.median(r["cycle_wall_s"] for r in s["runs"]
                          if not r["failed"]) for s in sess],
            "stages_s": {},
        }
        for stage in STAGES:
            vals = []
            for r in good:
                if stage == "residual":
                    vals.append(r["residual_s"])
                else:
                    vals.append(r["stages_s"].get(stage, 0.0))
            agg["stages_s"][stage] = summarize(vals)
        agg["prepare_plus_construct_s"] = summarize(
            r["stages_s"].get("prepare", 0.0)
            + r["stages_s"].get("construct", 0.0) for r in good)
        out["scenarios"][scen] = agg

    if run_sets.get("A") and run_sets.get("B"):
        a, b = run_sets["A"], run_sets["B"]
        out["loaded_vs_empty"] = {
            "end_to_end_ratio_of_medians": (
                st.median(r["cycle_wall_s"] for r in b)
                / st.median(r["cycle_wall_s"] for r in a)),
            "end_to_end_ratio_ci95": bootstrap_ratio_ci(
                [r["cycle_wall_s"] for r in b],
                [r["cycle_wall_s"] for r in a]),
            "prepare_construct_ratio_of_medians": (
                st.median(r["stages_s"].get("prepare", 0.0)
                          + r["stages_s"].get("construct", 0.0)
                          for r in b)
                / st.median(r["stages_s"].get("prepare", 0.0)
                            + r["stages_s"].get("construct", 0.0)
                            for r in a)),
            "prepare_construct_ratio_ci95": bootstrap_ratio_ci(
                [r["stages_s"].get("prepare", 0.0)
                 + r["stages_s"].get("construct", 0.0) for r in b],
                [r["stages_s"].get("prepare", 0.0)
                 + r["stages_s"].get("construct", 0.0) for r in a]),
        }

    path = os.path.join(RAW, "analysis.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(out, indent=1))
    print(f"analysis written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
