#!/usr/bin/env python3
"""EXP-046 analysis: the predeclared EXP-017 statistic,
unchanged, imported from the EXP-017 analyzer so the
verdicts rest on literally the same code that produced
the EXP-024b, EXP-032, EXP-039 and EXP-045 verdicts.

Verdict rule (stated in EXP046_REPORT.md section 1
before timing, extending the adopted EXP-017 rule with
its mirror): per comparison, arm B is a VERIFIED
IMPROVEMENT over arm A only when the adjusted bootstrap
CI is entirely above 0 in every session and pooled; an
ESTABLISHED NEGATIVE when it is entirely below 0 in
every session and pooled; anything else is NOT
SIGNIFICANT. The control comparison carries no verdict;
it calibrates the same-arm null under the campaign's
conditions.
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


def verdict(group):
    per = group["per_session"]
    pooled = group["pooled"]["adjusted"]
    every_above = all(
        e["adjusted"]["ci95"][0] > 0 for e in per) \
        and pooled["ci95"][0] > 0
    every_below = all(
        e["adjusted"]["ci95"][1] < 0 for e in per) \
        and pooled["ci95"][1] < 0
    if every_above:
        return "VERIFIED IMPROVEMENT"
    if every_below:
        return "ESTABLISHED NEGATIVE"
    return "NOT SIGNIFICANT"


def main():
    files = sorted(glob.glob(os.path.join(SESSION_DIR,
                                          "session_*.json")))
    if not files:
        print("no EXP-046 sessions found", file=sys.stderr)
        return 1
    groups = {}
    for path in files:
        with open(path) as fh:
            sess = json.load(fh)
        groups.setdefault(sess["comparison"], []).append(sess)
    out = {
        "experiment": "EXP-046 (EXP-017 protocol)",
        "analysis_utc": datetime.now(timezone.utc).isoformat(),
        "statistic": "predeclared EXP-017 statistic, computed "
                     "by the imported exp017_analyze code "
                     "(paired log-ratio, OLS covariate "
                     "adjustment, 10,000-resample pairs "
                     "bootstrap)",
        "session_files": [os.path.basename(f) for f in files],
        "comparisons": {},
    }
    for name in sorted(groups):
        sessions = sorted(groups[name],
                          key=lambda s: s["session_id"])
        rng = np.random.default_rng(46046 + (abs(hash(name)) % 100000))
        group = ea.analyse_group(name, sessions, rng)
        if not name.startswith("control"):
            group["verdict"] = verdict(group)
        out["comparisons"][name] = group
        pooled = group["pooled"]
        per = group["per_session"]
        print(f"{name}: sessions={len(per)} "
              f"adjusted pooled "
              f"{pooled['adjusted']['mean_log_ratio']:+.4f} "
              f"CI {pooled['adjusted']['ci95']} "
              f"verdict={group.get('verdict', 'control')}")
        for e in per:
            print(f"  {e['session_id']}: "
                  f"A median {e['arm_a_median_rate_hs']:,.0f} H/s "
                  f"B median {e['arm_b_median_rate_hs']:,.0f} H/s "
                  f"adjusted {e['adjusted']['mean_log_ratio']:+.4f} "
                  f"CI {e['adjusted']['ci95']}")
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
