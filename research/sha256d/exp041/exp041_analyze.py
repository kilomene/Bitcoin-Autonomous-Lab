#!/usr/bin/env python3
"""EXP-041 analysis: the predeclared EXP-017 statistic,
unchanged.

The statistic itself (paired log-ratio, OLS adjustment on
the steal-difference, runnable-load-difference and order
covariates, 10,000-resample pairs bootstrap, per-session
and pooled) is imported from the EXP-017 analyzer so the
EXP-041 verdicts rest on literally the same code that
produced every earlier verdict in this programme. This
file only points it at the EXP-041 session directory and
writes the output under EXP-041 RAW_RESULTS/.

Verdict rule (adopted EXP-017 integration rule): a
candidate is a VERIFIED IMPROVEMENT over its reference
only when the adjusted bootstrap CI is entirely above 0
in every session and pooled.
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


def main():
    files = sorted(glob.glob(os.path.join(SESSION_DIR,
                                          "session_*.json")))
    if not files:
        print("no EXP-041 sessions found", file=sys.stderr)
        return 1
    groups = {}
    for path in files:
        with open(path) as fh:
            sess = json.load(fh)
        groups.setdefault(sess["comparison"], []).append(sess)
    out = {
        "experiment": "EXP-041 (EXP-017 protocol)",
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
        rng = np.random.default_rng(41041 + (abs(hash(name)) % 100000))
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
