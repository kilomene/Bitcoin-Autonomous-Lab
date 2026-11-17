#!/usr/bin/env python3
"""EXP-053 analysis: the predeclared EXP-017 statistic,
unchanged, plus the EXP-053 predeclaration's verdict
mapping.

The statistic itself (paired log-ratio, OLS adjustment
on the steal-difference, runnable-load-difference and
order covariates, 10,000-resample pairs bootstrap,
per-session and pooled) is imported from the EXP-017
analyzer so the EXP-053 verdict rests on literally the
same code that produced every earlier verdict in this
programme. This file points it at the EXP-053 session
directory, writes the output under EXP-053
RAW_RESULTS/, and evaluates the verdict mapping
predeclared in PREDECLARATION.md:

  control validity first (pooled adjusted CI of
  control_dual_self must contain 0), then, for
  search_prefix_vs_dual: VERIFIED IMPROVEMENT
  (adjusted CI entirely above 0 in every session and
  pooled), ESTABLISHED NEGATIVE slowdown (entirely
  below 0 pooled and in every session), ESTABLISHED
  NEGATIVE at the predeclared resolution (pooled CI
  contains 0, upper bound below the +0.0118 ceiling,
  half-width at most 0.006), PROMISING HYPOTHESIS
  (pooled entirely above 0 without every session, or
  pooled contains 0 with upper bound at or above the
  ceiling at the target resolution), or RESOLUTION
  LIMIT (budget exhausted above the resolution
  target).
"""
import glob
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(HERE, "RAW_RESULTS", "sessions")
sys.path.insert(0, os.path.join(
    ROOT, "research/sha256d/phase6/benchmarks"))
import exp017_analyze as ea  # noqa: E402

CEILING_LOG = 0.0118  # log(256/253), predeclaration
RESOLUTION_HALFWIDTH = 0.006


def verdict(control, effect):
    if control is None or effect is None:
        return "INCOMPLETE", "missing control or effect sessions"
    c = control["pooled"]["adjusted"]
    if not (c["ci95"][0] <= 0 <= c["ci95"][1]):
        return ("MACHINERY INVALID",
                "control pooled adjusted CI excludes 0: "
                f"{c['ci95']}; no effect verdict may be drawn")
    e = effect["pooled"]["adjusted"]
    lo, hi = e["ci95"]
    halfwidth = (hi - lo) / 2.0
    per = effect["per_session"]
    every_above = all(
        s["adjusted"]["ci95"][0] > 0 for s in per)
    every_below = all(
        s["adjusted"]["ci95"][1] < 0 for s in per)
    if lo > 0 and every_above:
        return ("VERIFIED IMPROVEMENT",
                "adjusted CI entirely above 0 in every "
                "session and pooled (EXP-017 rule)")
    if hi < 0 and every_below:
        return ("ESTABLISHED NEGATIVE (slowdown)",
                "adjusted CI entirely below 0 pooled and "
                "in every session")
    if lo <= 0 <= hi and hi < CEILING_LOG \
            and halfwidth <= RESOLUTION_HALFWIDTH:
        return ("ESTABLISHED NEGATIVE at the predeclared "
                "resolution",
                f"pooled CI {e['ci95']} contains 0 with "
                f"upper bound below the +{CEILING_LOG} "
                f"ceiling and half-width {halfwidth:.4f} "
                f"at most {RESOLUTION_HALFWIDTH}")
    if lo > 0:
        return ("PROMISING HYPOTHESIS",
                "pooled adjusted CI entirely above 0 but "
                "the every-session rule is unmet")
    if lo <= 0 <= hi and hi >= CEILING_LOG \
            and halfwidth <= RESOLUTION_HALFWIDTH:
        return ("PROMISING HYPOTHESIS",
                "pooled CI contains 0 with upper bound at "
                "or above the ceiling at target resolution")
    return ("RESOLUTION LIMIT",
            f"pooled half-width {halfwidth:.4f} above the "
            f"{RESOLUTION_HALFWIDTH} target at budget "
            "exhaustion; retired as unresolvable on this "
            "VM per the portfolio failure criterion")


def main():
    files = sorted(glob.glob(os.path.join(SESSION_DIR,
                                          "session_*.json")))
    if not files:
        print("no EXP-053 sessions found", file=sys.stderr)
        return 1
    groups = {}
    for path in files:
        with open(path) as fh:
            sess = json.load(fh)
        groups.setdefault(sess["comparison"], []).append(sess)
    out = {
        "experiment": "EXP-053 (EXP-017 protocol)",
        "analysis_utc": datetime.now(timezone.utc).isoformat(),
        "statistic": "predeclared EXP-017 statistic, computed "
                     "by the imported exp017_analyze code "
                     "(paired log-ratio, OLS covariate "
                     "adjustment, 10,000-resample pairs "
                     "bootstrap)",
        "ceiling_log": CEILING_LOG,
        "resolution_halfwidth_target": RESOLUTION_HALFWIDTH,
        "session_files": [os.path.basename(f) for f in files],
        "comparisons": {},
    }
    for name in sorted(groups):
        sessions = sorted(groups[name],
                          key=lambda s: s["session_id"])
        rng = np.random.default_rng(53053 + (abs(hash(name)) % 100000))
        out["comparisons"][name] = ea.analyse_group(
            name, sessions, rng)
        pooled = out["comparisons"][name]["pooled"]
        per = out["comparisons"][name]["per_session"]
        every = all(e["adjusted"]["significant_b_faster"]
                    for e in per)
        print(f"{name}: sessions={len(per)} "
              f"adjusted pooled "
              f"{pooled['adjusted']['mean_log_ratio']:+.4f} "
              f"CI {pooled['adjusted']['ci95']} "
              f"pooled_sig={pooled['adjusted']['significant_b_faster']} "
              f"every_session_sig={every}")
    v, why = verdict(out["comparisons"].get("control_dual_self"),
                     out["comparisons"].get("search_prefix_vs_dual"))
    out["verdict"] = {"classification": v, "basis": why}
    print(f"VERDICT: {v}: {why}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(HERE, "RAW_RESULTS",
                        f"analysis_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(
            HERE, "RAW_RESULTS", f"analysis_{stamp}_r{suffix}.json")
        suffix += 1
    with open(path, "x") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
