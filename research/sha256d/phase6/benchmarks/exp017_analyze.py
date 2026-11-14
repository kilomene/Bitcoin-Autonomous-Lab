#!/usr/bin/env python3
"""EXP-017 analysis: the predeclared paired statistic.

Reads every append-only session file under benchmarks/
exp017/, groups by comparison, and computes, per session
and pooled:

  * the unadjusted mean paired log-ratio with a pairs
    bootstrap 95 percent interval;
  * the adjusted mean paired log-ratio (OLS on the
    steal-difference, runnable-load-difference, and
    order covariates, as predeclared in
    phase6/EXPERIMENT_RESULTS.md) with the same
    bootstrap, refitting on every resample;
  * the fraction of pairs won by arm B;
  * for control comparisons, the historical min/max
    separation rule reconstructed on approximately
    1M-hash pseudo-rounds (16 blocks per arm);
  * a within-session versus between-session variance
    decomposition of the paired log-ratio;
  * for control comparisons, a semi-synthetic injected
    effect recovery check: a known pooled log-ratio of
    +0.20 is added to a residual-resampled null data
    set built from the observed design, and the pooled
    estimator must recover it.

Output is a new timestamped JSON under benchmarks/
exp017/; originals are never modified.
"""
import glob
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(HERE, "exp017")
BOOT = 10_000
SIMS = 1_000
INJECTED_DELTA = 0.20


def percentile_ci(values):
    lo, hi = np.percentile(values, [2.5, 97.5])
    return [float(lo), float(hi)]


def fit_alpha(X, y, alpha_rows):
    """OLS; alpha is the mean of the coefficients whose
    indices are in alpha_rows (one intercept per session
    in pooled fits, the single intercept in session fits)."""
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(np.mean(beta[alpha_rows])), beta


def boot_alpha(X, y, groups, alpha_rows, rng):
    """Pairs bootstrap, stratified by session group."""
    n = len(y)
    estimates = np.empty(BOOT)
    for b in range(BOOT):
        idx = np.concatenate([
            rng.choice(g, size=len(g), replace=True) for g in groups])
        Xb, yb = X[idx], y[idx]
        try:
            beta = np.linalg.solve(Xb.T @ Xb, Xb.T @ yb)
        except np.linalg.LinAlgError:
            beta, *_ = np.linalg.lstsq(Xb, yb, rcond=None)
        estimates[b] = np.mean(beta[alpha_rows])
    return estimates


def boot_mean(y, groups, rng):
    estimates = np.empty(BOOT)
    for b in range(BOOT):
        idx = np.concatenate([
            rng.choice(g, size=len(g), replace=True) for g in groups])
        estimates[b] = np.mean(y[idx])
    return estimates


def session_frame(sess):
    pairs = sess["pairs"]
    y = np.array([p["log_ratio_b_over_a"] for p in pairs], dtype=float)
    ds = np.array([p["b"]["env"]["steal_fraction"]
                   - p["a"]["env"]["steal_fraction"] for p in pairs])
    dl = np.array([p["b"]["env"]["runnable_mean"]
                   - p["a"]["env"]["runnable_mean"] for p in pairs])
    order = np.array([0.5 if p["b_first"] else -0.5 for p in pairs])
    return y, ds, dl, order


def design(y, ds, dl, order, session_idx):
    """Design matrix: one intercept per session, common
    covariate slopes. Covariates standardised once on the
    data being fitted (the predeclared rule)."""
    cols = []
    alpha_rows = []
    for s in sorted(set(session_idx.tolist())):
        cols.append((session_idx == s).astype(float))
        alpha_rows.append(len(cols) - 1)
    for values in (ds, dl):
        sd = float(np.std(values))
        if sd > 1e-12:
            cols.append((values - float(np.mean(values))) / sd)
    cols.append(order.astype(float))
    return np.column_stack(cols), alpha_rows


def analyse_group(name, sessions, rng):
    frames = [session_frame(s) for s in sessions]
    per_session = []
    for sess, (y, ds, dl, order) in zip(sessions, frames):
        idx = np.zeros(len(y), dtype=int)
        X, alpha_rows = design(y, ds, dl, order, idx)
        alpha, _beta = fit_alpha(X, y, alpha_rows)
        adj_boot = boot_alpha(X, y, [np.arange(len(y))], alpha_rows, rng)
        un_boot = boot_mean(y, [np.arange(len(y))], rng)
        rates_a = np.array([p["a"]["rate_hs"] for p in sess["pairs"]])
        rates_b = np.array([p["b"]["rate_hs"] for p in sess["pairs"]])
        entry = {
            "session_id": sess["session_id"],
            "pairs": len(y),
            "arm_a_median_rate_hs": float(np.median(rates_a)),
            "arm_b_median_rate_hs": float(np.median(rates_b)),
            "unadjusted": {
                "mean_log_ratio": float(np.mean(y)),
                "ci95": percentile_ci(un_boot),
                "significant_b_faster": bool(
                    percentile_ci(un_boot)[0] > 0),
            },
            "adjusted": {
                "mean_log_ratio": alpha,
                "ci95": percentile_ci(adj_boot),
                "significant_b_faster": bool(
                    percentile_ci(adj_boot)[0] > 0),
            },
            "fraction_pairs_won_by_b": float(np.mean(y > 0)),
            "mean_steal_fraction_a": float(np.mean(
                [p["a"]["env"]["steal_fraction"] for p in sess["pairs"]])),
            "mean_steal_fraction_b": float(np.mean(
                [p["b"]["env"]["steal_fraction"] for p in sess["pairs"]])),
            "mean_runnable_a": float(np.mean(
                [p["a"]["env"]["runnable_mean"] for p in sess["pairs"]])),
            "mean_runnable_b": float(np.mean(
                [p["b"]["env"]["runnable_mean"] for p in sess["pairs"]])),
        }
        if name.startswith("control"):
            entry["old_minmax_rule"] = old_rule(sess)
        per_session.append(entry)

    y = np.concatenate([f[0] for f in frames])
    ds = np.concatenate([f[1] for f in frames])
    dl = np.concatenate([f[2] for f in frames])
    order = np.concatenate([f[3] for f in frames])
    session_idx = np.concatenate([
        np.full(len(f[0]), j, dtype=int) for j, f in enumerate(frames)])
    groups = [np.where(session_idx == j)[0]
              for j in range(len(frames))]
    X, alpha_rows = design(y, ds, dl, order, session_idx)
    alpha, beta = fit_alpha(X, y, alpha_rows)
    adj_boot = boot_alpha(X, y, groups, alpha_rows, rng)
    un_boot = boot_mean(y, groups, rng)
    adj_ci = percentile_ci(adj_boot)
    un_ci = percentile_ci(un_boot)
    pooled = {
        "sessions": len(sessions),
        "pairs": int(len(y)),
        "unadjusted": {
            "mean_log_ratio": float(np.mean(y)),
            "ci95": un_ci,
            "significant_b_faster": bool(un_ci[0] > 0),
            "ci_width": float(un_ci[1] - un_ci[0]),
        },
        "adjusted": {
            "mean_log_ratio": alpha,
            "ci95": adj_ci,
            "significant_b_faster": bool(adj_ci[0] > 0),
            "ci_width": float(adj_ci[1] - adj_ci[0]),
        },
        "fraction_pairs_won_by_b": float(np.mean(y > 0)),
        "covariate_value": {
            "ci_width_ratio_adjusted_over_unadjusted": float(
                (adj_ci[1] - adj_ci[0]) / (un_ci[1] - un_ci[0])),
            "point_shift_adjusted_minus_unadjusted": float(
                alpha - float(np.mean(y))),
        },
        "variance_decomposition": variance_decomposition(frames),
    }
    if name.startswith("control"):
        pooled["old_minmax_rule"] = {
            "sessions_passing_phantom": int(sum(
                e["old_minmax_rule"]["passed"] for e in per_session)),
            "sessions_total": len(per_session),
        }
        pooled["injected_effect_validation"] = injected_validation(
            X, y, session_idx, alpha_rows, beta, rng)
    return {"per_session": per_session, "pooled": pooled}


def old_rule(sess, blocks_per_round=16):
    """Historical rule on pseudo-rounds: candidate min
    rate over approximately 1M-hash rounds must exceed
    reference max rate."""
    pairs = sess["pairs"]
    rates = {"a": [], "b": []}
    for start in range(0, len(pairs) - blocks_per_round + 1,
                       blocks_per_round):
        chunk = pairs[start:start + blocks_per_round]
        for arm in ("a", "b"):
            total_time = sum(p[arm]["elapsed_s"] for p in chunk)
            total_hashes = sum(p[arm]["count"] for p in chunk)
            rates[arm].append(total_hashes / total_time)
    passed = bool(rates["b"] and min(rates["b"]) > max(rates["a"]))
    return {
        "pseudo_rounds_per_arm": len(rates["a"]),
        "blocks_per_pseudo_round": blocks_per_round,
        "candidate_min_rate_hs": float(min(rates["b"])),
        "reference_max_rate_hs": float(max(rates["a"])),
        "passed": passed,
    }


def variance_decomposition(frames):
    ys = [f[0] for f in frames]
    ns = np.array([len(y) for y in ys], dtype=float)
    means = np.array([np.mean(y) for y in ys])
    variances = np.array([np.var(y, ddof=1) for y in ys])
    within = float(np.sum((ns - 1) * variances) / np.sum(ns - 1))
    sampling = float(np.mean(variances / ns))
    between_observed = float(np.var(means, ddof=1)) if len(ys) > 1 else 0.0
    between = max(0.0, between_observed - sampling)
    n_typ = float(np.mean(ns))
    out = {
        "within_session_variance": within,
        "between_session_variance": between,
        "between_session_variance_observed": between_observed,
        "sampling_variance_of_session_means": sampling,
        "session_means": [float(m) for m in means],
        "typical_pairs_per_session": n_typ,
    }
    for halfwidth in (0.10, 0.05):
        var_of_grand_mean_per_session = between + within / n_typ
        needed = math.ceil(
            (1.96 / halfwidth) ** 2 * var_of_grand_mean_per_session)
        out[f"sessions_needed_for_ci_halfwidth_{halfwidth}"] = int(needed)
    return out


def injected_validation(X, y, session_idx, alpha_rows, beta, rng):
    """Residual-resampled data with a known pooled effect
    of +INJECTED_DELTA; the pooled estimator must recover
    it. The design (covariates, order, session sizes) is
    the observed control design."""
    fitted = X @ beta
    residuals = y - fitted
    session_intercepts = beta[alpha_rows]
    baseline = fitted - np.array(
        [session_intercepts[s] for s in session_idx])
    pinv = np.linalg.pinv(X)
    recovered = np.empty(SIMS)
    for k in range(SIMS):
        e = np.concatenate([
            rng.choice(residuals[session_idx == s],
                       size=int(np.sum(session_idx == s)),
                       replace=True)
            for s in sorted(set(session_idx.tolist()))])
        y_sim = baseline + INJECTED_DELTA + e
        beta_sim = pinv @ y_sim
        recovered[k] = np.mean(beta_sim[alpha_rows])
    lo, hi = np.percentile(recovered, [2.5, 97.5])
    return {
        "injected_delta": INJECTED_DELTA,
        "simulations": SIMS,
        "mean_recovered": float(np.mean(recovered)),
        "empirical_central_95_range": [float(lo), float(hi)],
        "delta_inside_range": bool(lo <= INJECTED_DELTA <= hi),
        "mean_bias": float(np.mean(recovered) - INJECTED_DELTA),
    }


def main():
    files = sorted(glob.glob(os.path.join(SESSION_DIR, "session_*.json")))
    if not files:
        print("no EXP-017 sessions found", file=sys.stderr)
        return 1
    groups = {}
    for path in files:
        with open(path) as fh:
            sess = json.load(fh)
        groups.setdefault(sess["comparison"], []).append(sess)
    out = {
        "experiment": "EXP-017",
        "analysis_utc": datetime.now(timezone.utc).isoformat(),
        "statistic": "predeclared in phase6/EXPERIMENT_RESULTS.md "
                     "EXP-017 (paired log-ratio, OLS covariate "
                     "adjustment, 10,000-resample pairs bootstrap)",
        "bootstrap_resamples": BOOT,
        "session_files": [os.path.basename(f) for f in files],
        "comparisons": {},
    }
    for name in sorted(groups):
        sessions = sorted(groups[name],
                          key=lambda s: s["session_id"])
        rng = np.random.default_rng(17017 + (abs(hash(name)) % 100000))
        out["comparisons"][name] = analyse_group(name, sessions, rng)
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
