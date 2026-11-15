#!/usr/bin/env python3
"""EXP-022 integration confirmation analysis: the adopted
EXP-017 paired statistic, applied to the production
flags batch confirmation sessions under benchmarks/
exp022f/.

Reads every session file, groups by comparison, and
computes per session and pooled the adjusted mean
paired log-ratio (OLS on the steal-difference,
runnable-load-difference and order covariates) with a
pairs bootstrap 95 percent interval (10,000 resamples,
refitting on every resample), plus the unadjusted
figures and the fraction of pairs won by arm B. Ratios
are reported as exp(log-ratio). SCOPE: arm B over arm A
is a BATCH-scope ratio (flags batch vs production
batch); it is not a search or system rate.

Output is a new timestamped JSON under benchmarks/
exp022f/; originals are never modified.
"""
import glob
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(HERE, "exp022f")
sys.path.insert(0, os.path.join(
    "/home/hatch/workspace/bitcoin-autonomous-lab",
    "research/sha256d/phase6/benchmarks"))
from exp017_analyze import analyse_group  # noqa: E402


def ratio(entry):
    adj = entry["adjusted"]
    lo, hi = adj["ci95"]
    return {
        "mean_log_ratio": adj["mean_log_ratio"],
        "ratio": math.exp(adj["mean_log_ratio"]),
        "ci95_ratio": [math.exp(lo), math.exp(hi)],
        "significant_b_faster": adj["significant_b_faster"],
    }


def main():
    paths = sorted(glob.glob(os.path.join(
        SESSION_DIR, "session_*.json")))
    if not paths:
        print("no sessions found", file=sys.stderr)
        return 1
    by_comparison = {}
    for path in paths:
        with open(path) as fh:
            sess = json.load(fh)
        by_comparison.setdefault(sess["comparison"], []).append(sess)
    rng = np.random.default_rng(20261115)
    out = {
        "experiment": "EXP-022 integration confirmation",
        "analysed_utc": datetime.now(timezone.utc).isoformat(),
        "scope": ("BATCH scope only: flags batch vs "
                  "production batch; not a search or "
                  "system rate"),
        "comparisons": {},
    }
    for name, sessions in sorted(by_comparison.items()):
        sessions.sort(key=lambda s: s["session_id"])
        result = analyse_group(name, sessions, rng)
        pooled = ratio(result["pooled"])
        pooled["pairs"] = result["pooled"]["pairs"]
        pooled["sessions"] = result["pooled"]["sessions"]
        pooled["fraction_pairs_won_by_b"] = \
            result["pooled"]["fraction_pairs_won_by_b"]
        per = []
        for entry in result["per_session"]:
            r = ratio(entry)
            r["session_id"] = entry["session_id"]
            r["pairs"] = entry["pairs"]
            r["fraction_pairs_won_by_b"] = \
                entry["fraction_pairs_won_by_b"]
            per.append(r)
        out["comparisons"][name] = {
            "pooled_adjusted": pooled,
            "per_session_adjusted": per,
        }
        print(f"{name}: pooled adjusted ratio "
              f"{pooled['ratio']:.3f}x CI "
              f"[{pooled['ci95_ratio'][0]:.3f}, "
              f"{pooled['ci95_ratio'][1]:.3f}] "
              f"significant={pooled['significant_b_faster']} "
              f"pairs_won={pooled['fraction_pairs_won_by_b']:.3f}")
        for r in per:
            print(f"  {r['session_id']}: {r['ratio']:.3f}x CI "
                  f"[{r['ci95_ratio'][0]:.3f}, "
                  f"{r['ci95_ratio'][1]:.3f}] "
                  f"significant={r['significant_b_faster']}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(
        SESSION_DIR, f"analysis_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(
            SESSION_DIR, f"analysis_{stamp}_r{suffix}.json")
        suffix += 1
    with open(path, "x") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
