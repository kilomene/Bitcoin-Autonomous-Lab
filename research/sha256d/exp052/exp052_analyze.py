#!/usr/bin/env python3
"""EXP-052 analysis: the predeclared EXP-017 statistic.

The statistic itself (paired log-ratio, OLS adjustment
on the steal-difference, runnable-load-difference and
order covariates, 10,000-resample pairs bootstrap,
per-session and pooled) is computed with the EXP-017
analyzer's own functions (session_frame, design,
fit_alpha, boot_alpha, boot_mean), imported
unmodified from research/sha256d/phase6/benchmarks/
exp017_analyze.py, so the EXP-052 verdict rests on
literally the same estimator code that produced every
earlier verdict in this programme, exactly as EXP-054
did. Intervals are read at 95 percent (the EXP-052
predeclaration declares no Bonferroni family; its
displacement rule, requiring the interval to clear
the margin in every session and pooled, is the
conservative element). Bootstrap seeds are
deterministic, sha256-derived via
mining.bakeoff_dispatch.seed_for (never the salted
built-in hash).
"""
import os
import sys

import numpy as np

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
sys.path.insert(0, os.path.join(
    ROOT, "research/sha256d/phase6/benchmarks"))
sys.path.insert(0, ROOT)
import exp017_analyze as ea  # noqa: E402
from mining import bakeoff_dispatch as bd  # noqa: E402

RESAMPLES = bd.BOOTSTRAP_RESAMPLES


def ci_at(estimates, level):
    tail = (1.0 - level) / 2.0 * 100.0
    lo, hi = np.percentile(estimates, [tail, 100.0 - tail])
    return [float(lo), float(hi)]


def analyse(name, sessions):
    """One comparison group: per-session and pooled
    adjusted and unadjusted estimates with 95 percent
    bootstrap CIs, in the shape mining.bakeoff_dispatch
    .decide consumes (plus descriptive fields)."""
    rng = np.random.default_rng(bd.seed_for(name))
    frames = [ea.session_frame(s) for s in sessions]
    per_session = []
    for sess, (y, ds, dl, order) in zip(sessions, frames):
        idx = np.zeros(len(y), dtype=int)
        X, alpha_rows = ea.design(y, ds, dl, order, idx)
        alpha, _beta = ea.fit_alpha(X, y, alpha_rows)
        adj_boot = ea.boot_alpha(X, y, [np.arange(len(y))],
                                 alpha_rows, rng)
        un_boot = ea.boot_mean(y, [np.arange(len(y))], rng)
        rates_a = np.array([p["a"]["rate_hs"]
                            for p in sess["pairs"]])
        rates_b = np.array([p["b"]["rate_hs"]
                            for p in sess["pairs"]])
        per_session.append({
            "session_id": sess["session_id"],
            "pairs": len(y),
            "arm_a_median_rate_hs": float(np.median(rates_a)),
            "arm_b_median_rate_hs": float(np.median(rates_b)),
            "median_log_ratio": float(np.median(y)),
            "unadjusted": {
                "mean_log_ratio": float(np.mean(y)),
                "ci95": ci_at(un_boot, 0.95)},
            "adjusted": {
                "mean_log_ratio": float(alpha),
                "ci95": ci_at(adj_boot, 0.95)},
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
        np.full(len(f[0]), j, dtype=int)
        for j, f in enumerate(frames)])
    groups = [np.where(session_idx == j)[0]
              for j in range(len(frames))]
    X, alpha_rows = ea.design(y, ds, dl, order, session_idx)
    alpha, _beta = ea.fit_alpha(X, y, alpha_rows)
    adj_boot = ea.boot_alpha(X, y, groups, alpha_rows, rng)
    un_boot = ea.boot_mean(y, groups, rng)
    pooled = {
        "sessions": len(sessions),
        "pairs": int(len(y)),
        "unadjusted": {
            "mean_log_ratio": float(np.mean(y)),
            "ci95": ci_at(un_boot, 0.95)},
        "adjusted": {
            "mean_log_ratio": float(alpha),
            "ci95": ci_at(adj_boot, 0.95)},
        "fraction_pairs_won_by_b": float(np.mean(y > 0)),
    }
    return {"per_session": per_session, "pooled": pooled}


def analyse_all(session_units):
    """session_units: {comparison_name: {"challenger":
    tier, "sessions": [session dicts in order]}} plus a
    "control" entry. Returns the analysis dict
    bd.decide consumes, with descriptive detail kept."""
    out = {"comparisons": {}, "control": None}
    for name, comp in sorted(session_units.items()):
        result = analyse(name, comp["sessions"])
        result["challenger"] = comp["challenger"]
        if name == "control":
            out["control"] = result
        else:
            out["comparisons"][name] = result
    return out
