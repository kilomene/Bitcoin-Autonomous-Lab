#!/usr/bin/env python3
"""EXP-025 incremental analysis.

Imports the identical analyse_group statistic from the
EXP-017 analyser (phase6/benchmarks/exp017_analyze.py)
and processes ONE comparison per invocation, writing its
result to its own append-only JSON under
benchmarks/exp025/ immediately. The statistic, bootstrap
count and covariate adjustment are unchanged; only the
scheduling differs (the EXP-022 and EXP-024 remedy for
host CPU pressure from the live miner and node).
"""
import glob
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(HERE, "exp025")
sys.path.insert(0, os.path.join(
    ROOT, "research/sha256d/phase6/benchmarks"))
from exp017_analyze import analyse_group  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print("usage: exp025_analyze_incremental.py <comparison>")
        return 2
    name = sys.argv[1]
    files = sorted(glob.glob(
        os.path.join(SESSION_DIR, "session_*.json")))
    sessions = []
    for path in files:
        with open(path) as fh:
            sess = json.load(fh)
        if sess["comparison"] == name:
            sessions.append(sess)
    if not sessions:
        print(f"no sessions for {name}", file=sys.stderr)
        return 1
    sessions.sort(key=lambda s: s["session_id"])
    rng = np.random.default_rng(25025 + (abs(hash(name)) % 100000))
    result = analyse_group(name, sessions, rng)
    pooled = result["pooled"]
    adj = pooled["adjusted"]
    print(f"{name}: adjusted pooled log-ratio "
          f"{adj['mean_log_ratio']:+.4f} "
          f"ratio {math.exp(adj['mean_log_ratio']):.4f}x "
          f"CI [{math.exp(adj['ci95'][0]):.4f}, "
          f"{math.exp(adj['ci95'][1]):.4f}] "
          f"significant={adj['significant_b_faster']} "
          f"pairs_won={pooled['fraction_pairs_won_by_b']:.3f}",
          flush=True)
    for e in result["per_session"]:
        a = e["adjusted"]
        print(f"    {e['session_id']}: log {a['mean_log_ratio']:+.4f} "
              f"CI [{a['ci95'][0]:+.4f}, {a['ci95'][1]:+.4f}] "
              f"sig={a['significant_b_faster']} "
              f"medA {e['arm_a_median_rate_hs']:,.0f} "
              f"medB {e['arm_b_median_rate_hs']:,.0f}", flush=True)
    out = {"experiment": "EXP-025", "comparison": name,
           "analysis_utc": datetime.now(timezone.utc).isoformat(),
           "statistic": "EXP-017 predeclared, imported unchanged "
                        "from phase6/benchmarks/exp017_analyze.py "
                        "(analyse_group); incremental scheduling",
           "session_files": [s["session_id"] for s in sessions],
           "result": result}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(
        SESSION_DIR, f"analysis_inc_{name}_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(
            SESSION_DIR, f"analysis_inc_{name}_{stamp}_r{suffix}.json")
        suffix += 1
    with open(path, "x") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
