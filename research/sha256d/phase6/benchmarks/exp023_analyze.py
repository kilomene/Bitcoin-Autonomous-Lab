#!/usr/bin/env python3
"""EXP-023 analysis: the predeclared EXP-017 paired
statistic, computed by the EXP-017 analyser's own code
(exp017_analyze.analyse_group) over the append-only
EXP-023 session files. Per session and pooled: unadjusted
and covariate-adjusted mean paired log-ratio with a
10,000-resample pairs bootstrap 95 percent interval, and
the fraction of pairs won by arm B (the amortised
builder). Output is a new timestamped JSON under
benchmarks/exp023/; originals are never modified.
"""
import glob
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(HERE, "exp023")
sys.path.insert(0, HERE)

import exp017_analyze as A  # noqa: E402


def main():
    only = None
    if "--comparison" in sys.argv:
        only = sys.argv[sys.argv.index("--comparison") + 1]
    files = sorted(glob.glob(os.path.join(
        SESSION_DIR, "session_*_steps*.json")) + glob.glob(
        os.path.join(SESSION_DIR, "session_*_family*.json")) + glob.glob(
        os.path.join(SESSION_DIR, "session_*_churn*.json")))
    if not files:
        print("no EXP-023 sessions found", file=sys.stderr)
        return 1
    groups = {}
    for path in files:
        with open(path) as fh:
            sess = json.load(fh)
        if sess.get("experiment") != "EXP-023":
            continue
        if only and sess["comparison"] != only:
            continue
        groups.setdefault(sess["comparison"], []).append(sess)
    out = {
        "experiment": "EXP-023",
        "analysis_utc": datetime.now(timezone.utc).isoformat(),
        "statistic": "predeclared EXP-017 statistic (paired "
                     "log-ratio, OLS covariate adjustment, "
                     "10,000-resample pairs bootstrap), "
                     "computed by exp017_analyze.analyse_group",
        "bootstrap_resamples": A.BOOT,
        "session_files": [os.path.basename(f) for f in files],
        "comparisons": {},
    }
    for name in sorted(groups):
        sessions = sorted(groups[name],
                          key=lambda s: s["session_id"])
        rng = np.random.default_rng(23023 + (abs(hash(name)) % 100000))
        out["comparisons"][name] = A.analyse_group(name, sessions, rng)
        pooled = out["comparisons"][name]["pooled"]
        print(f"{name}: adjusted pooled "
              f"{pooled['adjusted']['mean_log_ratio']:+.4f} "
              f"CI {pooled['adjusted']['ci95']} "
              f"significant={pooled['adjusted']['significant_b_faster']}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(SESSION_DIR, f"analysis_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(SESSION_DIR, f"analysis_{stamp}_r{suffix}.json")
        suffix += 1
    with open(path, "x") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
