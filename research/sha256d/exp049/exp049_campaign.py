#!/usr/bin/env python3
"""EXP-049 Gate 4 comparison campaign: the production bench
mode (mining/bench_mode.py) against the existing research
harness measure (agent/intelligence/scheduler.py
Scheduler._measure, the R-35 analogue from the Master
Build), EXP-017-shaped paired sessions.

PREDECLARED AGREEMENT CRITERION (written before any
campaign run, and stated identically in EXP049_REPORT.md
section 6; the manifest records the report file's sha256 at
campaign start so the ordering is checkable):

- Arms: MODE = bench_mode.measure_once on a ComputeEngine()
  constructed exactly as production constructs it (auto
  dispatch, no arguments). HARNESS = Scheduler._measure for
  the tier the mode's engine selected, at the mode engine's
  resolved thread count, repetitions=1.
- Work unit per measurement, both arms: the fixed R-35 unit
  (header bytes(range(80)), target 1, start 0, count
  262,144) through search_first_counted; rate = attempted /
  wall around the call.
- Sessions: 3. Pairs per session: 20. Within each pair the
  two arms run back to back in randomized AB/BA order
  (per-session seeded RNG, seed recorded). Benchmarks run
  strictly one at a time; nothing else is benchmarked
  concurrently by this script. The live miner and any other
  host load are recorded (load average at each session
  start), not controlled.
- Statistic: paired log ratio ln(mode rate / harness rate)
  per pair; per-session and pooled mean with a percentile
  bootstrap 95% CI (10,000 resamples of the pairs, seed
  1049).
- AGREEMENT VERDICT: the hypothesis (the mode reproduces
  the harness's category E figures within session noise) is
  VERIFIED if the pooled bootstrap 95% CI of the mean
  paired log ratio contains 0. If the pooled CI excludes 0,
  the verdict is DISAGREEMENT beyond session noise and the
  entry's failure criterion is met. Per-session CIs are
  reported either way.

Outputs: RAW_RESULTS/campaign_sessions.json (every run),
RAW_RESULTS/campaign_analysis.json (the statistics).
"""

import hashlib
import json
import math
import os
import random
import statistics
import sys
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..")))

from agent.intelligence import Agent              # noqa: E402
from agent.intelligence.scheduler import Scheduler  # noqa: E402
from mining import bench_mode                     # noqa: E402

ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", ".."))
RAW = os.path.join(os.path.dirname(__file__), "RAW_RESULTS")
REPORT = os.path.join(os.path.dirname(__file__),
                      "EXP049_REPORT.md")
COUNT = 1 << 18
PAIRS_PER_SESSION = 20
SESSIONS = 3
BOOTSTRAP_RESAMPLES = 10000
BOOTSTRAP_SEED = 1049


def bootstrap_ci(values, resamples=BOOTSTRAP_RESAMPLES,
                 seed=BOOTSTRAP_SEED):
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(resamples):
        means.append(statistics.fmean(
            values[rng.randrange(n)] for _ in range(n)))
    means.sort()
    lo = means[int(0.025 * resamples)]
    hi = means[int(0.975 * resamples) - 1]
    return lo, hi


def main():
    os.makedirs(RAW, exist_ok=True)
    report_sha = None
    if os.path.exists(REPORT):
        with open(REPORT, "rb") as f:
            report_sha = hashlib.sha256(f.read()).hexdigest()
    mode_engine = bench_mode.ComputeEngine()
    desc = mode_engine.describe()
    tier = desc["backend"]
    threads = desc["c_threads"]
    tmp = tempfile.mkdtemp(prefix="exp049-campaign-")
    agent = Agent(local_dir=tmp)
    sched = Scheduler(
        agent, cache_path=os.path.join(tmp, "sched.json"))
    manifest = {
        "experiment": "EXP-049 Gate 4 campaign",
        "report_sha256_at_start": report_sha,
        "host_cpu": bench_mode.host_profile()["cpu_model"],
        "mode_backend": tier,
        "mode_threads": threads,
        "harness_tier": tier,
        "harness_threads": threads,
        "count_per_measurement": COUNT,
        "pairs_per_session": PAIRS_PER_SESSION,
        "sessions_planned": SESSIONS,
        "started_utc": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sessions": [],
    }
    all_ratios = []
    for s in range(SESSIONS):
        rng = random.Random(49049 + s)
        session = {
            "index": s,
            "seed": 49049 + s,
            "load_average_at_start": list(os.getloadavg()),
            "started_utc": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pairs": [],
        }
        for p in range(PAIRS_PER_SESSION):
            mode_first = rng.random() < 0.5
            pair = {"index": p,
                    "order": "mode-first" if mode_first
                             else "harness-first"}

            def run_mode():
                attempted, wall, rate = \
                    bench_mode.measure_once(mode_engine, COUNT)
                return {"attempted": attempted,
                        "wall_s": wall, "rate_hs": rate}

            def run_harness():
                rate, runs = sched._measure(
                    tier, threads, 1, COUNT)
                return {"attempted": runs[0]["attempted"],
                        "wall_s": runs[0]["wall_s"],
                        "rate_hs": rate}

            if mode_first:
                pair["mode"] = run_mode()
                pair["harness"] = run_harness()
            else:
                pair["harness"] = run_harness()
                pair["mode"] = run_mode()
            pair["log_ratio"] = math.log(
                pair["mode"]["rate_hs"]
                / pair["harness"]["rate_hs"])
            session["pairs"].append(pair)
            all_ratios.append(pair["log_ratio"])
            print(f"session {s} pair {p}: "
                  f"mode {pair['mode']['rate_hs']:,.0f} H/s, "
                  f"harness {pair['harness']['rate_hs']:,.0f} "
                  f"H/s, log ratio {pair['log_ratio']:+.4f}",
                  flush=True)
        ratios = [pr["log_ratio"] for pr in session["pairs"]]
        lo, hi = bootstrap_ci(ratios)
        session["mean_log_ratio"] = statistics.fmean(ratios)
        session["bootstrap_ci95"] = [lo, hi]
        session["mode_median_rate_hs"] = statistics.median(
            pr["mode"]["rate_hs"] for pr in session["pairs"])
        session["harness_median_rate_hs"] = statistics.median(
            pr["harness"]["rate_hs"] for pr in session["pairs"])
        manifest["sessions"].append(session)
        print(f"session {s}: mean log ratio "
              f"{session['mean_log_ratio']:+.4f}, CI95 "
              f"[{lo:+.4f}, {hi:+.4f}]", flush=True)
    lo, hi = bootstrap_ci(all_ratios)
    pooled_mean = statistics.fmean(all_ratios)
    verdict = ("AGREEMENT VERIFIED: pooled CI contains 0"
               if lo <= 0.0 <= hi else
               "DISAGREEMENT: pooled CI excludes 0")
    analysis = {
        "pairs_total": len(all_ratios),
        "pooled_mean_log_ratio": pooled_mean,
        "pooled_ratio": math.exp(pooled_mean),
        "pooled_bootstrap_ci95": [lo, hi],
        "verdict": verdict,
        "per_session": [
            {"index": s["index"],
             "mean_log_ratio": s["mean_log_ratio"],
             "bootstrap_ci95": s["bootstrap_ci95"],
             "mode_median_rate_hs": s["mode_median_rate_hs"],
             "harness_median_rate_hs":
                 s["harness_median_rate_hs"]}
            for s in manifest["sessions"]],
    }
    manifest["finished_utc"] = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(os.path.join(RAW, "campaign_sessions.json"),
              "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    with open(os.path.join(RAW, "campaign_analysis.json"),
              "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=1, sort_keys=True)
    print(json.dumps(analysis, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
