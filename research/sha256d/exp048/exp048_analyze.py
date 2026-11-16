#!/usr/bin/env python3
"""EXP-048 analysis: aggregate the category F Stratum
session files in RAW_RESULTS into per-pipeline, per-scenario
statistics: end-to-end time per accepted block, the client
stage partition, the server stage decomposition, the
non-search overhead fraction and overhead milliseconds,
hashes per block, and (per pipeline) the loaded-versus-empty
ratio of medians with a bootstrap confidence interval over
runs. Writes analysis.json next to the session files and
prints the tables the report quotes. Failed runs are
counted and excluded, per the Hashrate Measurement
Specification section 6. Shakedown files (shakedown_
prefix) are excluded by the glob."""

import glob
import json
import os
import random
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "RAW_RESULTS")
CLIENT_STAGES = ("job_wait", "construct", "search",
                 "verify_client", "submit_send", "verdict_wait",
                 "confirm", "residual")
SERVER_STAGES = {
    "solo": ("srv_submit_total", "srv_validate", "srv_verify",
             "srv_refresh_total", "srv_gbt", "srv_submit",
             "srv_chain", "srv_rpc_other"),
    "pool": ("pool_submit_total", "pool_validate", "pool_verify",
             "pool_assemble", "pool_gbt", "pool_submit",
             "pool_chain", "pool_rpc_other"),
}
MANUAL = {"job_wait": "job_wait_s", "verdict_wait":
          "verdict_wait_s", "confirm": "confirm_s"}


def quartiles(xs):
    xs = sorted(xs)
    if len(xs) < 4:
        return (min(xs), max(xs))
    q = st.quantiles(xs, n=4, method="inclusive")
    return (q[0], q[2])


def summarize(xs):
    xs = list(xs)
    if not xs:
        return None
    lo, hi = quartiles(xs)
    return {"n": len(xs), "median": st.median(xs), "min": min(xs),
            "max": max(xs), "iqr": [lo, hi],
            "mean": sum(xs) / len(xs)}


def bootstrap_ratio_ci(a, b, iters=10_000, seed=48048):
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


def stage_value(run, stage):
    if stage in MANUAL:
        return run.get(MANUAL[stage], 0.0)
    if stage == "residual":
        return run.get("residual_s", 0.0)
    return run.get("stages_s", {}).get(stage, 0.0)


def main():
    sessions = {}
    files = {}
    for path in sorted(glob.glob(os.path.join(
            RAW, "session_*.json"))):
        with open(path) as fh:
            s = json.load(fh)
        key = (s["pipeline"], s["scenario"])
        sessions.setdefault(key, []).append(s)
        files.setdefault(key, []).append(os.path.basename(path))

    out = {"pipelines": {}, "files": {}}
    run_sets = {}
    for (pipeline, scenario), sess in sorted(sessions.items()):
        runs = [r for s in sess for r in s["runs"]]
        good = [r for r in runs if not r["failed"]]
        failed = [r for r in runs if r["failed"]]
        run_sets[(pipeline, scenario)] = good
        out["files"][f"{pipeline}/{scenario}"] = files[
            (pipeline, scenario)]
        total_wall = sum(r["cycle_wall_s"] for r in good)
        agg = {
            "sessions": len(sess),
            "runs": len(runs),
            "failed_runs": len(failed),
            "blocks_accepted": len(good),
            "heights": [r.get("height") for r in good],
            "end_to_end_s": summarize(
                r["cycle_wall_s"] for r in good),
            "blocks_per_hour_aggregate": (
                len(good) * 3600.0 / total_wall if total_wall
                else None),
            "hashes_per_block": summarize(
                r["hashes_counted"] for r in good),
            "overhead_fraction": summarize(
                (r["cycle_wall_s"]
                 - r["stages_s"].get("search", 0.0))
                / r["cycle_wall_s"] for r in good),
            "overhead_ms": summarize(
                (r["cycle_wall_s"]
                 - r["stages_s"].get("search", 0.0)) * 1000.0
                for r in good),
            "per_session_median_wall_s": [
                st.median(r["cycle_wall_s"] for r in s["runs"]
                          if not r["failed"]) for s in sess],
            "stages_s": {},
            "server_stages_s": {},
        }
        for stage in CLIENT_STAGES:
            agg["stages_s"][stage] = summarize(
                stage_value(r, stage) for r in good)
        for stage in SERVER_STAGES[pipeline]:
            agg["server_stages_s"][stage] = summarize(
                r.get("server_stages_s", {}).get(stage, 0.0)
                for r in good)
        agg["setup_server_stages_s"] = {}
        for stage in SERVER_STAGES[pipeline]:
            agg["setup_server_stages_s"][stage] = summarize(
                r.get("setup_server_stages_s", {}).get(stage, 0.0)
                for r in good)
        out["pipelines"].setdefault(pipeline, {})[scenario] = agg

    comparisons = {}
    for pipeline in ("solo", "pool"):
        a = run_sets.get((pipeline, "A"))
        b = run_sets.get((pipeline, "B"))
        if a and b:
            def template_supply(r):
                """The full template-supply cost attributable
                to a run: the setup window's GBT (where the
                loaded template is built, scenario B), the
                in-run post-block refresh GBT, the solo
                refresh wrapper remainder, and the client's
                header construction."""
                gbt = ("srv_gbt" if pipeline == "solo"
                       else "pool_gbt")
                total = (
                    r.get("setup_server_stages_s", {}).get(
                        gbt, 0.0)
                    + r.get("server_stages_s", {}).get(gbt, 0.0)
                    + r["stages_s"].get("construct", 0.0))
                if pipeline == "solo":
                    total += r.get(
                        "server_stages_s", {}).get(
                        "srv_refresh_total", 0.0)
                return total
            comparisons[pipeline] = {
                "end_to_end_ratio_of_medians": (
                    st.median(r["cycle_wall_s"] for r in b)
                    / st.median(r["cycle_wall_s"] for r in a)),
                "end_to_end_ratio_ci95": bootstrap_ratio_ci(
                    [r["cycle_wall_s"] for r in b],
                    [r["cycle_wall_s"] for r in a]),
                "template_supply_ratio_of_medians": (
                    st.median(template_supply(r) for r in b)
                    / st.median(template_supply(r) for r in a)),
                "template_supply_ratio_ci95": bootstrap_ratio_ci(
                    [template_supply(r) for r in b],
                    [template_supply(r) for r in a]),
                "template_supply_ms": {
                    "empty_median": st.median(
                        template_supply(r) for r in a) * 1000.0,
                    "loaded_median": st.median(
                        template_supply(r) for r in b) * 1000.0},
            }
    out["loaded_vs_empty"] = comparisons

    path = os.path.join(RAW, "analysis.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(out, indent=1))
    print(f"analysis written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
