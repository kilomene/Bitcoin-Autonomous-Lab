#!/usr/bin/env python3
"""EXP-054 analysis: the predeclared EXP-017 statistic
plus the EXP-054 predeclaration's Bonferroni
correction and verdict mapping.

The statistic itself (paired log-ratio, OLS adjustment
on the steal-difference, runnable-load-difference and
order covariates, 10,000-resample pairs bootstrap,
per-session and pooled) is computed with the EXP-017
analyzer's own functions (session_frame, design,
fit_alpha, boot_alpha, boot_mean,
variance_decomposition), imported unmodified, so the
EXP-054 verdict rests on literally the same estimator
code that produced every earlier verdict in this
programme. On top of it, per PREDECLARATION.md:

  * the three candidate comparisons (G = 2, 4, 8 vs
    production) form one family; their verdict
    intervals are the same bootstrap distributions
    read at the Bonferroni percentiles for
    per-comparison alpha 0.05 / 3 (98.333 percent,
    percentiles [0.8333, 99.1667]). The control and
    build-control comparisons are single machinery
    checks read at 95 percent.
  * bootstrap seeds are deterministic: each
    comparison's seed is derived from the sha256 of
    its name, never from Python's salted string hash,
    so this analysis is bit-reproducible across
    invocations on the same session files (the
    EXP-053 seed wart, audit note N-2, is not
    inherited).

The EXP-017-era historical extras (the min/max
separation rule and the injected-effect validation in
analyse_group) are not part of EXP-054's predeclared
verdict mapping and are not computed here; the
predeclared machinery check is the control comparison
itself.

Verdict mapping (PREDECLARATION.md): control validity
first (pooled adjusted 95 percent CI of
control_dual_self must contain 0); then per candidate,
from its corrected adjusted CIs: DISPLACING (entirely
above 0 in every session and pooled), SLOWDOWN
(entirely below 0 pooled and in every session), FLAT
(pooled contains 0, half-width at most 0.012),
PROMISING (pooled entirely above 0, every-session
rule unmet), or RESOLUTION LIMIT for the point.
Overall, in precedence order: DISPLACED (any
candidate displacing; VERIFIED IMPROVEMENT for the
largest-estimate displacing point), PROMISING
HYPOTHESIS, CONFIRMED (every candidate FLAT or
SLOWDOWN; the displacement hypothesis is an
ESTABLISHED NEGATIVE at the predeclared resolution),
or RESOLUTION LIMIT.
"""
import glob
import hashlib
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

RESOLUTION_HALFWIDTH = 0.012
FAMILY = ("search_g2_vs_dual", "search_g4_vs_dual",
          "search_g8_vs_dual")
EXPECTED_SESSIONS = {
    "control_dual_self": 2,
    "search_g1_vs_dual": 2,
    "search_g2_vs_dual": 3,
    "search_g4_vs_dual": 3,
    "search_g8_vs_dual": 3,
}
POINT_OF = {"search_g2_vs_dual": 2, "search_g4_vs_dual": 4,
            "search_g8_vs_dual": 8}


def seed_for(name):
    """Deterministic per-comparison seed (sha256 of the
    comparison name; no salted hash())."""
    digest = hashlib.sha256(f"EXP-054:{name}".encode()).digest()
    return int.from_bytes(digest[:8], "little") % (2 ** 31)


def ci_at(estimates, level):
    tail = (1.0 - level) / 2.0 * 100.0
    lo, hi = np.percentile(estimates, [tail, 100.0 - tail])
    return [float(lo), float(hi)]


def analyse(name, sessions):
    """One comparison group, EXP-017 statistic via the
    imported primitives, CIs at 95 percent and at the
    comparison's verdict level (Bonferroni 98.333
    percent for family members, else 95 percent)."""
    level = 1.0 - 0.05 / 3.0 if name in FAMILY else 0.95
    rng = np.random.default_rng(seed_for(name))
    frames = [ea.session_frame(s) for s in sessions]
    per_session = []
    for sess, (y, ds, dl, order) in zip(sessions, frames):
        idx = np.zeros(len(y), dtype=int)
        X, alpha_rows = ea.design(y, ds, dl, order, idx)
        alpha, _beta = ea.fit_alpha(X, y, alpha_rows)
        adj_boot = ea.boot_alpha(X, y, [np.arange(len(y))],
                                 alpha_rows, rng)
        un_boot = ea.boot_mean(y, [np.arange(len(y))], rng)
        rates_a = np.array([p["a"]["rate_hs"] for p in sess["pairs"]])
        rates_b = np.array([p["b"]["rate_hs"] for p in sess["pairs"]])
        per_session.append({
            "session_id": sess["session_id"],
            "pairs": len(y),
            "arm_a_median_rate_hs": float(np.median(rates_a)),
            "arm_b_median_rate_hs": float(np.median(rates_b)),
            "median_log_ratio": float(np.median(y)),
            "unadjusted": {
                "mean_log_ratio": float(np.mean(y)),
                "ci95": ci_at(un_boot, 0.95),
                "ci_verdict_level": ci_at(un_boot, level),
            },
            "adjusted": {
                "mean_log_ratio": alpha,
                "ci95": ci_at(adj_boot, 0.95),
                "ci_verdict_level": ci_at(adj_boot, level),
            },
            "fraction_pairs_won_by_b": float(np.mean(y > 0)),
            "mean_steal_fraction_a": float(np.mean(
                [p["a"]["env"]["steal_fraction"]
                 for p in sess["pairs"]])),
            "mean_steal_fraction_b": float(np.mean(
                [p["b"]["env"]["steal_fraction"]
                 for p in sess["pairs"]])),
            "mean_runnable_a": float(np.mean(
                [p["a"]["env"]["runnable_mean"]
                 for p in sess["pairs"]])),
            "mean_runnable_b": float(np.mean(
                [p["b"]["env"]["runnable_mean"]
                 for p in sess["pairs"]])),
        })

    y = np.concatenate([f[0] for f in frames])
    ds = np.concatenate([f[1] for f in frames])
    dl = np.concatenate([f[2] for f in frames])
    order = np.concatenate([f[3] for f in frames])
    session_idx = np.concatenate([
        np.full(len(f[0]), j, dtype=int) for j, f in enumerate(frames)])
    groups = [np.where(session_idx == j)[0]
              for j in range(len(frames))]
    X, alpha_rows = ea.design(y, ds, dl, order, session_idx)
    alpha, _beta = ea.fit_alpha(X, y, alpha_rows)
    adj_boot = ea.boot_alpha(X, y, groups, alpha_rows, rng)
    un_boot = ea.boot_mean(y, groups, rng)
    adj95 = ci_at(adj_boot, 0.95)
    adjv = ci_at(adj_boot, level)
    un95 = ci_at(un_boot, 0.95)
    unv = ci_at(un_boot, level)
    pooled = {
        "sessions": len(sessions),
        "pairs": int(len(y)),
        "unadjusted": {
            "mean_log_ratio": float(np.mean(y)),
            "ci95": un95,
            "ci_verdict_level": unv,
            "ci_width": float(un95[1] - un95[0]),
        },
        "adjusted": {
            "mean_log_ratio": alpha,
            "ci95": adj95,
            "ci_verdict_level": adjv,
            "ci_width": float(adj95[1] - adj95[0]),
            "ci_verdict_level_width": float(adjv[1] - adjv[0]),
        },
        "fraction_pairs_won_by_b": float(np.mean(y > 0)),
        "covariate_value": {
            "ci_width_ratio_adjusted_over_unadjusted": float(
                (adj95[1] - adj95[0]) / (un95[1] - un95[0])),
            "point_shift_adjusted_minus_unadjusted": float(
                alpha - float(np.mean(y))),
        },
        "variance_decomposition": ea.variance_decomposition(frames),
    }
    return {"verdict_level": level, "per_session": per_session,
            "pooled": pooled}


def classify_point(group):
    per = group["per_session"]
    pooled = group["pooled"]["adjusted"]
    lo, hi = pooled["ci_verdict_level"]
    halfwidth = (hi - lo) / 2.0
    every_above = all(
        s["adjusted"]["ci_verdict_level"][0] > 0 for s in per)
    every_below = all(
        s["adjusted"]["ci_verdict_level"][1] < 0 for s in per)
    if lo > 0 and every_above:
        return "DISPLACING"
    if hi < 0 and every_below:
        return "SLOWDOWN"
    if lo <= 0 <= hi and halfwidth <= RESOLUTION_HALFWIDTH:
        return "FLAT"
    if lo > 0:
        return "PROMISING"
    return "RESOLUTION LIMIT"


def verdict(groups, counts_ok):
    if not counts_ok:
        return ("INCOMPLETE",
                "session counts do not match the predeclared "
                "design; no verdict may be drawn")
    control = groups.get("control_dual_self")
    if control is None:
        return "INCOMPLETE", "missing control sessions"
    c = control["pooled"]["adjusted"]["ci95"]
    if not (c[0] <= 0 <= c[1]):
        return ("MACHINERY INVALID",
                f"control pooled adjusted 95% CI excludes 0: "
                f"{c}; no candidate verdict may be drawn")
    points = {}
    for name in FAMILY:
        if name not in groups:
            return "INCOMPLETE", f"missing sessions for {name}"
        points[name] = classify_point(groups[name])
    displacing = [n for n in FAMILY if points[n] == "DISPLACING"]
    if displacing:
        peak = max(
            displacing,
            key=lambda n: groups[n]["pooled"]["adjusted"]
            ["mean_log_ratio"])
        return ("DISPLACED (VERIFIED IMPROVEMENT)",
                f"candidate G = {POINT_OF[peak]} displaces the "
                f"production point under the Bonferroni-corrected "
                f"EXP-017 rule; per-point: {points}")
    if any(v == "PROMISING" for v in points.values()):
        return ("PROMISING HYPOTHESIS",
                f"no candidate displaces; per-point: {points}")
    if all(v in ("FLAT", "SLOWDOWN") for v in points.values()):
        return ("CONFIRMED (flat curve; ESTABLISHED NEGATIVE "
                "for the displacement hypothesis)",
                f"every candidate FLAT or SLOWDOWN at the "
                f"predeclared resolution; per-point: {points}")
    return ("RESOLUTION LIMIT",
            f"budget exhausted with an unresolved candidate; "
            f"per-point: {points}")


def main():
    files = sorted(glob.glob(os.path.join(SESSION_DIR,
                                          "session_*.json")))
    if not files:
        print("no EXP-054 sessions found", file=sys.stderr)
        return 1
    groups_raw = {}
    for path in files:
        with open(path) as fh:
            sess = json.load(fh)
        groups_raw.setdefault(sess["comparison"], []).append(sess)
    counts = {n: len(s) for n, s in groups_raw.items()}
    counts_ok = all(counts.get(n) == k
                    for n, k in EXPECTED_SESSIONS.items())
    out = {
        "experiment": "EXP-054 (EXP-017 protocol)",
        "analysis_utc": datetime.now(timezone.utc).isoformat(),
        "statistic": "predeclared EXP-017 statistic, computed "
                     "by the imported exp017_analyze functions "
                     "(paired log-ratio, OLS covariate "
                     "adjustment, 10,000-resample pairs "
                     "bootstrap); deterministic sha256-derived "
                     "seeds, bit-reproducible",
        "correction": "Bonferroni across the 3 candidate "
                      "comparisons: verdict intervals at "
                      "98.333 percent (alpha 0.05 / 3) for "
                      "family members; control and "
                      "build-control at 95 percent",
        "resolution_halfwidth_target": RESOLUTION_HALFWIDTH,
        "session_files": [os.path.basename(f) for f in files],
        "session_counts": counts,
        "session_counts_match_predeclaration": counts_ok,
        "comparisons": {},
    }
    for name in sorted(groups_raw):
        sessions = sorted(groups_raw[name],
                          key=lambda s: s["session_id"])
        out["comparisons"][name] = analyse(name, sessions)
        pooled = out["comparisons"][name]["pooled"]
        print(f"{name}: sessions={pooled['sessions']} "
              f"adjusted pooled "
              f"{pooled['adjusted']['mean_log_ratio']:+.4f} "
              f"CI95 {pooled['adjusted']['ci95']} "
              f"CI-verdict {pooled['adjusted']['ci_verdict_level']}")
    g1 = out["comparisons"].get("search_g1_vs_dual")
    if g1 is not None:
        ci = g1["pooled"]["adjusted"]["ci95"]
        out["build_control"] = {
            "pooled_adjusted_mean": g1["pooled"]["adjusted"]
            ["mean_log_ratio"],
            "ci95": ci,
            "excludes_zero": bool(not (ci[0] <= 0 <= ci[1])),
            "reading": "if excludes_zero, the research build "
                       "itself measures differently from the "
                       "shipped binary at that size; candidate "
                       "effects at or below that size cannot "
                       "be attributed to granularity alone "
                       "(predeclaration)",
        }
        print(f"build control: mean "
              f"{out['build_control']['pooled_adjusted_mean']:+.4f} "
              f"CI95 {ci} excludes_zero="
              f"{out['build_control']['excludes_zero']}")
    points = {}
    for name in FAMILY:
        if name in out["comparisons"]:
            points[f"G={POINT_OF[name]}"] = classify_point(
                out["comparisons"][name])
    out["point_classifications"] = points
    v, why = verdict(out["comparisons"], counts_ok)
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
