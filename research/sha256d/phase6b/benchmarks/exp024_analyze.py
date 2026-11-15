#!/usr/bin/env python3
"""EXP-024 analysis: the EXP-017 predeclared paired
statistic, applied unchanged.

Imports analyse_group from the Phase 6 EXP-017 analyser
(the adopted statistic: paired log-ratio, OLS covariate
adjustment on steal and runnable-load differences and
order, 10,000-resample pairs bootstrap, per-session and
pooled) and applies it to the append-only session files
under phase6b/benchmarks/exp024/. Output is a new
timestamped JSON in the same directory; originals are
never modified.
"""
import glob
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(HERE, "exp024")
sys.path.insert(0, os.path.join(
    ROOT, "research/sha256d/phase6/benchmarks"))
from exp017_analyze import analyse_group  # noqa: E402


def main():
    files = sorted(glob.glob(
        os.path.join(SESSION_DIR, "session_*.json")))
    if not files:
        print("no EXP-024 sessions found", file=sys.stderr)
        return 1
    groups = {}
    for path in files:
        with open(path) as fh:
            sess = json.load(fh)
        groups.setdefault(sess["comparison"], []).append(sess)
    out = {
        "experiment": "EXP-024",
        "analysis_utc": datetime.now(timezone.utc).isoformat(),
        "statistic": "EXP-017 predeclared (paired log-ratio, "
                     "OLS covariate adjustment, 10,000-resample "
                     "pairs bootstrap), imported unchanged from "
                     "phase6/benchmarks/exp017_analyze.py",
        "session_files": [os.path.basename(f) for f in files],
        "comparisons": {},
    }
    for name in sorted(groups):
        sessions = sorted(groups[name],
                          key=lambda s: s["session_id"])
        rng = np.random.default_rng(24024 + (abs(hash(name)) % 100000))
        out["comparisons"][name] = analyse_group(name, sessions, rng)
        pooled = out["comparisons"][name]["pooled"]
        adj = pooled["adjusted"]
        import math
        print(f"{name}: adjusted pooled log-ratio "
              f"{adj['mean_log_ratio']:+.4f} "
              f"ratio {math.exp(adj['mean_log_ratio']):.4f}x "
              f"CI [{math.exp(adj['ci95'][0]):.4f}, "
              f"{math.exp(adj['ci95'][1]):.4f}] "
              f"significant={adj['significant_b_faster']} "
              f"pairs_won={pooled['fraction_pairs_won_by_b']:.3f}")
        for e in out["comparisons"][name]["per_session"]:
            a = e["adjusted"]
            print(f"    {e['session_id']}: log {a['mean_log_ratio']:+.4f} "
                  f"CI [{a['ci95'][0]:+.4f}, {a['ci95'][1]:+.4f}] "
                  f"sig={a['significant_b_faster']} "
                  f"medA {e['arm_a_median_rate_hs']:,.0f} "
                  f"medB {e['arm_b_median_rate_hs']:,.0f}")
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
