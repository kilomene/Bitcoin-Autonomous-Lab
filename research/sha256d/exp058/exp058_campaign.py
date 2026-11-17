#!/usr/bin/env python3
"""EXP-058 Gate 3 campaign: PID worker/span control
against the EXP-031 recorded-signal plant.

Deterministic seeded simulation, 160 samples per
scenario, one at a time. The plant is the disclosed fit
to the six EXP-031 loadprobe points (see
PREDECLARATION.md): E(n, C) = min(n, C) *
(1 - 0.04 * max(0, min(n, C) - 1)) *
(1 - 0.015 * max(0, n - C)), aggregate rate R1 * E with
R1 = 5,341,402 H/s (EXP-031 mean 1-thread rate), span
interval T = span / (R / n). Measurement noise is
multiplicative sigma 10 percent on each interval
sample, as predeclared.

Stability bounds are evaluated on the TRUE interval
error (the regulated physical quantity); the measured
error statistics are recorded alongside. A bound on
the measured error at the predeclared noise level
would be a bound on the noise itself (sigma 10 percent
on T is sigma 0.10 on e, so |e| <= 0.15 is a 1.5-sigma
band), which no controller could satisfy; this
metrics definition is disclosed in the report's
judgment calls.

The step policy baseline runs the identical scenarios
and seeds. All rates in the output are plant-model
outputs; no rate claim is made (portfolio: a rate
claim would need its own EXP-017 entry).
"""

import hashlib
import json
import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from mining.pid_control import (AdaptiveWorkController,  # noqa: E402
                                PIDGains, Signals, StepPolicy,
                                TARGET_INTERVAL)

PREDECLARATION_SHA256 = \
    "ef3b69a5d2a3c9eb6270e143d1248e4c95940c70ede047ea3d69b6037f07c78d"

R1 = 5341402.0
SAMPLES = 160
SEED = 20261117
NOISE_SIGMA = 0.10


def check_predeclaration():
    with open(os.path.join(HERE, "PREDECLARATION.md"),
              "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() \
            == PREDECLARATION_SHA256


def effectiveness(n, capacity):
    return min(n, capacity) \
        * (1 - 0.04 * max(0, min(n, capacity) - 1)) \
        * (1 - 0.015 * max(0, n - capacity))


def plant_interval(n, span, capacity):
    per_worker = R1 * effectiveness(n, capacity) / n
    return span / per_worker


def capacity_nominal(i):
    return 2.0


def capacity_step_down(i):
    return 2.0 if i < 40 else 1.1


def capacity_step_up(i):
    return 2.0 if i < 40 else 3.2


def capacity_ramp_down(i):
    if i < 40:
        return 2.0
    if i < 80:
        return 2.0 - 0.8 * (i - 40) / 40.0
    return 1.2


def capacity_burst_dip(i):
    return 0.8 if 60 <= i < 75 else 2.0


def run_pid(capacity_fn, seed, controller=None,
            signal_loss_window=None, nonfinite_at=None,
            steal_fn=None):
    rng = random.Random(seed)
    ctrl = controller or AdaptiveWorkController(enabled=True)
    n, span = 2, 1 << 23
    rows = []
    prev_workers = n
    worker_changes = 0
    changes_after_20 = 0
    span_dirs = []
    prev_span = span
    for i in range(SAMPLES):
        cap = capacity_fn(i)
        t_true = plant_interval(n, span, cap)
        t_meas = t_true * (1 + rng.gauss(0, NOISE_SIGMA))
        steal = steal_fn(i) if steal_fn else 2.0
        if signal_loss_window and signal_loss_window[0] <= i \
                < signal_loss_window[1]:
            cmd = ctrl.update(Signals(None, steal))
        elif nonfinite_at is not None and i == nonfinite_at:
            cmd = ctrl.update(Signals(float("inf"), steal))
        else:
            cmd = ctrl.update(Signals(t_meas, steal))
        if cmd.workers != prev_workers:
            worker_changes += 1
            if i > 20:
                changes_after_20 += 1
            prev_workers = cmd.workers
        if cmd.span != prev_span:
            span_dirs.append(1 if cmd.span > prev_span else -1)
            prev_span = cmd.span
        n, span = cmd.workers, cmd.span
        rows.append({
            "i": i, "capacity": cap,
            "t_true": t_true, "t_meas": t_meas,
            "e_true": (TARGET_INTERVAL - t_true)
                      / TARGET_INTERVAL,
            "e_meas": (TARGET_INTERVAL - t_meas)
                      / TARGET_INTERVAL,
            "workers": cmd.workers, "span": cmd.span,
            "mode": cmd.mode,
            "trip_reason": cmd.trip_reason,
        })
    reversals = sum(1 for a, b in zip(span_dirs, span_dirs[1:])
                    if a != b)
    return {
        "rows": rows,
        "worker_changes": worker_changes,
        "worker_changes_after_20": changes_after_20,
        "span_reversals": reversals,
        "trips": [{"sample": t.sample, "reason": t.reason}
                  for t in ctrl.trips],
        "final_workers": n,
    }


def run_step_baseline(capacity_fn, seed):
    rng = random.Random(seed)
    policy = StepPolicy()
    n, span = policy.workers, policy.span
    rows = []
    prev_workers = n
    worker_changes = 0
    span_dirs = []
    prev_span = span
    for i in range(SAMPLES):
        cap = capacity_fn(i)
        t_true = plant_interval(n, span, cap)
        t_meas = t_true * (1 + rng.gauss(0, NOISE_SIGMA))
        cmd = policy.update(Signals(t_meas, 2.0))
        if cmd.workers != prev_workers:
            worker_changes += 1
            prev_workers = cmd.workers
        if cmd.span != prev_span:
            span_dirs.append(1 if cmd.span > prev_span else -1)
            prev_span = cmd.span
        n, span = cmd.workers, cmd.span
        rows.append({
            "i": i, "capacity": cap, "t_true": t_true,
            "e_true": (TARGET_INTERVAL - t_true)
                      / TARGET_INTERVAL,
            "workers": cmd.workers, "span": cmd.span,
        })
    reversals = sum(1 for a, b in zip(span_dirs, span_dirs[1:])
                    if a != b)
    return {"rows": rows, "worker_changes": worker_changes,
            "span_reversals": reversals, "final_workers": n}


def frac_in_band(rows, lo, band, start):
    sel = [abs(r["e_true"]) for r in rows if r["i"] >= start]
    if not sel:
        return 0.0
    return sum(1 for e in sel if e <= band) / len(sel)


def first_in_band_after(rows, start, band=0.15):
    for r in rows:
        if r["i"] >= start and abs(r["e_true"]) <= band:
            return r["i"]
    return None


def material_span_reversals(rows):
    """Sign changes between material span moves
    (|delta log2 span| >= 0.15): the oscillation-scale
    quantity, comparable across controllers. Raw sign
    changes of a continuous controller's per-sample
    span are regulation dither and are recorded
    separately as span_reversals."""
    signs = []
    for a, b in zip(rows, rows[1:]):
        d = math.log2(b["span"] / a["span"])
        if abs(d) >= 0.15:
            signs.append(1 if d > 0 else -1)
    return sum(1 for x, y in zip(signs, signs[1:]) if x != y)


def metrics(res):
    rows = res["rows"]
    return {
        "worker_changes": res["worker_changes"],
        "span_reversals": res["span_reversals"],
        "span_material_reversals": material_span_reversals(rows),
        "trips": res["trips"],
        "final_workers": res["final_workers"],
        "inband_true_after20": round(
            frac_in_band(rows, 0, 0.15, 20), 4),
        "inband_meas_after20": round(
            sum(1 for r in rows if r["i"] >= 20
                and abs(r["e_meas"]) <= 0.15)
            / max(1, sum(1 for r in rows if r["i"] >= 20)), 4),
    }


def main():
    check_predeclaration()
    out = {"experiment": "EXP-058", "gate": 3,
           "predeclaration_sha256": PREDECLARATION_SHA256,
           "seed": SEED, "samples": SAMPLES,
           "noise_sigma": NOISE_SIGMA, "R1": R1,
           "scenarios": {}}
    verdicts = {}

    scenarios = {
        "nominal": capacity_nominal,
        "step_down": capacity_step_down,
        "step_up": capacity_step_up,
        "ramp_down": capacity_ramp_down,
        "burst_dip": capacity_burst_dip,
    }
    for name, fn in scenarios.items():
        res = run_pid(fn, SEED)
        base = run_step_baseline(fn, SEED)
        m = metrics(res)
        bm = {"worker_changes": base["worker_changes"],
              "span_reversals": base["span_reversals"],
              "span_material_reversals":
                  material_span_reversals(base["rows"]),
              "final_workers": base["final_workers"],
              "inband_true_after20": round(
                  frac_in_band(base["rows"], 0, 0.15, 20), 4)}
        checks = {}
        rows = res["rows"]
        if name == "nominal":
            checks["workers_settle_at_2"] = \
                res["final_workers"] == 2 and all(
                    r["workers"] == 2 for r in rows
                    if r["i"] >= 100)
            checks["changes_after_20_at_most_2"] = \
                res["worker_changes_after_20"] <= 2
            checks["span_in_bounds"] = all(
                (1 << 20) <= r["span"] <= (1 << 26)
                for r in rows)
            checks["zero_trips"] = len(res["trips"]) == 0
            checks["inband_after20_at_least_0.90"] = \
                m["inband_true_after20"] >= 0.90
        elif name in ("step_down", "step_up"):
            back = first_in_band_after(rows, 40)
            checks["return_within_12"] = \
                back is not None and back <= 52
            checks["inband_after52_at_least_0.90"] = \
                frac_in_band(rows, 0, 0.15, 52) >= 0.90
            checks["changes_at_most_4"] = \
                res["worker_changes"] <= 4
            checks["zero_trips"] = len(res["trips"]) == 0
            if name == "step_up":
                reach = [r["i"] for r in rows
                         if r["workers"] >= 3]
                checks["workers_reach_3_by_80"] = \
                    bool(reach) and min(reach) <= 80
        elif name == "ramp_down":
            checks["inband025_after50_at_least_0.90"] = \
                frac_in_band(rows, 0, 0.25, 50) >= 0.90
            checks["changes_at_most_4"] = \
                res["worker_changes"] <= 4
            checks["zero_trips"] = len(res["trips"]) == 0
        elif name == "burst_dip":
            back = first_in_band_after(rows, 75)
            checks["return_within_15_of_dip_end"] = \
                back is not None and back <= 90
            checks["changes_at_most_5"] = \
                res["worker_changes"] <= 5
            checks["zero_trips"] = len(res["trips"]) == 0
        verdicts[name] = all(checks.values())
        out["scenarios"][name] = {
            "pid": m, "step_baseline": bm, "checks": checks,
            "verdict": verdicts[name],
            "rows": rows,
        }
        print("scenario %-10s verdict=%s pid=%s baseline=%s"
              % (name, verdicts[name], m, bm), flush=True)

    # signal_loss scenario
    res = run_pid(capacity_nominal, SEED,
                  signal_loss_window=(50, 66))
    rows = res["rows"]
    pre = rows[49]
    held = all(rows[i]["workers"] == pre["workers"]
               and rows[i]["span"] == pre["span"]
               for i in range(50, 55))
    trip = res["trips"][0] if res["trips"] else None
    checks = {
        "commands_held_first_5_lost": held,
        "trip_signal_loss_at_6th": bool(trip)
            and trip["reason"] == "signal_loss"
            and trip["sample"] == 56,
        "commands_always_in_bounds": all(
            1 <= r["workers"] <= 4
            and (1 << 20) <= r["span"] <= (1 << 26)
            and math.isfinite(r["span"]) for r in rows),
    }
    verdicts["signal_loss"] = all(checks.values())
    out["scenarios"]["signal_loss"] = {
        "pid": metrics(res), "checks": checks,
        "verdict": verdicts["signal_loss"], "rows": rows}
    print("scenario signal_loss verdict=%s checks=%s"
          % (verdicts["signal_loss"], checks), flush=True)

    # gain_faults scenario
    construction = {}
    for label, gains in {
            "nan_kp": (float("nan"), 0.06, 0.10),
            "inf_kp": (float("inf"), 0.06, 0.10),
            "negative_ki": (0.35, -0.06, 0.10),
            "all_zero": (0.0, 0.0, 0.0)}.items():
        try:
            PIDGains(*gains)
            construction[label] = False
        except ValueError:
            construction[label] = True
    res_nf = run_pid(capacity_nominal, SEED, nonfinite_at=29)
    trip_nf = res_nf["trips"][0] if res_nf["trips"] else None
    fault_ctrl = AdaptiveWorkController(
        enabled=True,
        span_gains=PIDGains(3.5, 0.06, 0.10))
    res_f = run_pid(capacity_nominal, SEED, controller=fault_ctrl)
    trip_f = res_f["trips"][0] if res_f["trips"] else None
    checks = {
        "construction_faults_all_raise": all(
            construction.values()),
        "nonfinite_trips_immediately": bool(trip_nf)
            and trip_nf["reason"] == "nonfinite_signal"
            and trip_nf["sample"] == 30,
        "tenx_kp_trips_oscillation": bool(trip_f)
            and trip_f["reason"] == "oscillation"
            and trip_f["sample"] < 160,
    }
    verdicts["gain_faults"] = all(checks.values())
    out["scenarios"]["gain_faults"] = {
        "construction": construction, "checks": checks,
        "verdict": verdicts["gain_faults"],
        "nonfinite_trip": trip_nf, "fault_trip": trip_f}
    print("scenario gain_faults verdict=%s checks=%s"
          % (verdicts["gain_faults"], checks), flush=True)

    # host_distress scenario
    res = run_pid(capacity_nominal, SEED,
                  steal_fn=lambda i: 30.0 if 50 <= i < 61
                  else 2.0)
    trip = res["trips"][0] if res["trips"] else None
    checks = {
        "trip_host_distress_by_3rd": bool(trip)
            and trip["reason"] == "host_distress"
            and trip["sample"] <= 53,
        "latched": res["rows"][-1]["mode"] == "step",
    }
    verdicts["host_distress"] = all(checks.values())
    out["scenarios"]["host_distress"] = {
        "pid": metrics(res), "checks": checks,
        "verdict": verdicts["host_distress"],
        "rows": res["rows"]}
    print("scenario host_distress verdict=%s checks=%s"
          % (verdicts["host_distress"], checks), flush=True)

    # Annex: seed robustness for the three headline
    # scenarios (recorded, not bound-evaluated).
    annex = {}
    for sname, fn in (("nominal", capacity_nominal),
                      ("step_down", capacity_step_down),
                      ("step_up", capacity_step_up)):
        annex[sname] = {}
        for seed in (1, 2):
            r = run_pid(fn, seed)
            annex[sname][str(seed)] = metrics(r)
    out["annex_other_seeds"] = annex

    out["verdicts"] = verdicts
    out["gate3_all_bounds_met"] = all(verdicts.values())
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = os.path.join(HERE, "RAW_RESULTS",
                        "campaign_%s.json" % ts)
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print("wrote %s" % path, flush=True)
    print("GATE 3 all bounds met: %s" % out["gate3_all_bounds_met"],
          flush=True)
    return 0 if out["gate3_all_bounds_met"] else 1


if __name__ == "__main__":
    sys.exit(main())
