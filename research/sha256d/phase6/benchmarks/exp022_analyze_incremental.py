#!/usr/bin/env python3
"""EXP-022 incremental analysis runner.

Same statistic, same functions, same output schema as
exp022_analyze.py (imported, not reimplemented). The only
difference is scheduling: comparison groups are analysed
in a fixed priority order (the predeclared primary first)
and the output JSON is rewritten after each group, so a
result exists even if the host stalls later groups. The
monolithic exp022_analyze.py run was killed after about
12 minutes without output on the throttled replacement
host; this runner exists to land the primary verdict
first. Group results are identical either way: same
per-group RNG seed derivation as exp022_analyze.main.
"""
import glob
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from exp022_analyze import SESSION_DIR, BOOT, analyse_group  # noqa: E402

PRIORITY = [
    "flagsx_vs_production_d0",
    "flagsx_vs_production_d256",
    "flagsx_vs_production_dall",
    "flagspure_vs_production_d0",
    "flagsx_vs_production_d0_t1",
]


def main():
    files = sorted(glob.glob(os.path.join(SESSION_DIR, "session_*.json")))
    if not files:
        print("no EXP-022 sessions found", file=sys.stderr)
        return 1
    groups = {}
    for path in files:
        with open(path) as fh:
            sess = json.load(fh)
        groups.setdefault(sess["comparison"], []).append(sess)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(SESSION_DIR, f"analysis_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(SESSION_DIR, f"analysis_{stamp}_r{suffix}.json")
        suffix += 1
    out = {
        "experiment": "EXP-022",
        "analysis_utc": datetime.now(timezone.utc).isoformat(),
        "statistic": "the adopted EXP-017 statistic (paired "
                     "log-ratio, OLS covariate adjustment, "
                     "10,000-resample pairs bootstrap), computed "
                     "by exp022_analyze.analyse_group via the "
                     "incremental runner after the monolithic "
                     "run stalled on the throttled host",
        "bootstrap_resamples": BOOT,
        "session_files": [os.path.basename(f) for f in files],
        "comparisons": {},
    }
    order = [n for n in PRIORITY if n in groups]
    order += [n for n in sorted(groups) if n not in PRIORITY]
    for name in order:
        sessions = sorted(groups[name], key=lambda s: s["session_id"])
        rng = np.random.default_rng(22022 + (abs(hash(name)) % 100000))
        out["comparisons"][name] = analyse_group(name, sessions, rng)
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(out, fh, indent=2)
        os.replace(tmp, path)
        pooled = out["comparisons"][name]["pooled"]
        print(f"{name}: adjusted pooled "
              f"{pooled['adjusted']['mean_log_ratio']:+.4f} "
              f"CI {pooled['adjusted']['ci95']} "
              f"significant={pooled['adjusted']['significant_b_faster']}",
              flush=True)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
