#!/usr/bin/env python3
"""EXP-058 Gate 5: supervised live trial of the PID
worker/span controller against a trial workload.

The controller actuates a TRIAL workload only: a
separate process running the production ComputeEngine
(v512dual, target 1 full scans, the EXP-031 load-probe
pattern) beside production. The live miner, autopilot,
node and endpoint config are untouched and unobserved
except through the contention they cause. Once per
sample the controller sets the trial engine's thread
count and span (search range size); the measured
interval is the real wall time of one span search;
steal is read from /proc/stat over the same window.

Quiet-window condition (predeclared): the trial starts
only if the 1-minute load average is <= 9.0 at start
(EXP-031's standing baseline was 7.0 to 7.5 with the
live stack up). If unmet, the trial is recorded NOT
RUN with the observed load figures and the actuated
trial stays UNVERIFIED; no shadow substitute is
claimed as Gate 5.

Automatic fallback is armed identically to Gate 3. On
any trip the trial engine reverts to the step-policy
command (2 threads, span 2^23) for the remainder of
the trial, and the trip is a Gate 5 failure unless the
trip condition is itself visible in the recorded live
signals.

Rates recorded here are descriptive trial telemetry
only; no rate claim is made (portfolio: a rate claim
would need its own EXP-017 entry).
"""

import hashlib
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from mining.pid_control import (AdaptiveWorkController,  # noqa: E402
                                Signals, TARGET_INTERVAL)

PREDECLARATION_SHA256 = \
    "ef3b69a5d2a3c9eb6270e143d1248e4c95940c70ede047ea3d69b6037f07c78d"

SAMPLES = 60
QUIET_LOAD1_MAX = 9.0
STEP_COMMAND = (2, 1 << 23)


def check_predeclaration():
    with open(os.path.join(HERE, "PREDECLARATION.md"),
              "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() \
            == PREDECLARATION_SHA256


def read_stat():
    with open("/proc/stat") as fh:
        for line in fh:
            parts = line.split()
            if parts and parts[0] == "cpu":
                vals = [int(x) for x in parts[1:11]]
                keys = ("user", "nice", "system", "idle",
                        "iowait", "irq", "softirq", "steal",
                        "guest", "guest_nice")
                return dict(zip(keys, vals))
    return {}


def steal_percent(before, after):
    deltas = {k: after[k] - before[k] for k in before}
    total = sum(deltas.values())
    if total <= 0:
        return 0.0
    return 100.0 * deltas["steal"] / total


def loadavg():
    with open("/proc/loadavg") as fh:
        parts = fh.read().split()
    return [float(parts[0]), float(parts[1]), float(parts[2])]


def main():
    check_predeclaration()
    out = {"experiment": "EXP-058", "gate": 5,
           "predeclaration_sha256": PREDECLARATION_SHA256,
           "samples_planned": SAMPLES}
    load = loadavg()
    out["loadavg_at_start"] = load
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = os.path.join(HERE, "RAW_RESULTS",
                        "gate5_%s.json" % ts)
    if load[0] > QUIET_LOAD1_MAX:
        out["status"] = "NOT_RUN"
        out["reason"] = ("quiet-window condition unmet: "
                         "1-minute load average %.2f > %.1f"
                         % (load[0], QUIET_LOAD1_MAX))
        with open(path, "w") as fh:
            json.dump(out, fh, indent=1)
        print("GATE 5 NOT RUN: %s" % out["reason"], flush=True)
        print("wrote %s" % path, flush=True)
        return 2

    from gpu.engine import ComputeEngine
    engine = ComputeEngine()
    header = bytes(range(80))
    target = 1

    def one_search(workers, span, start):
        engine.c_threads = workers
        engine.c_threads_tuned = True
        before = read_stat()
        wall0 = time.perf_counter()
        hit, attempted, seconds = engine.search_first_counted(
            header, target, start, span)
        wall = time.perf_counter() - wall0
        after = read_stat()
        return wall, attempted, steal_percent(before, after), hit

    # Warmup (backend load), not a trial sample.
    one_search(2, 1 << 21, 0)

    ctrl = AdaptiveWorkController(enabled=True)
    workers, span = 2, 1 << 23
    cursor = 1 << 21
    rows = []
    tripped = None
    for i in range(SAMPLES):
        wall, attempted, steal, hit = one_search(
            workers, span, cursor)
        cursor += span
        error = (TARGET_INTERVAL - wall) / TARGET_INTERVAL
        cmd = ctrl.update(Signals(wall, steal))
        if tripped is None and ctrl.trips:
            tripped = {"sample": ctrl.trips[-1].sample,
                       "reason": ctrl.trips[-1].reason}
        if tripped is not None:
            workers, span = STEP_COMMAND
        else:
            workers, span = cmd.workers, cmd.span
        rows.append({
            "i": i, "interval_seconds": round(wall, 4),
            "error": round(error, 4),
            "steal_percent": round(steal, 3),
            "attempted": attempted,
            "rate_hs": round(attempted / wall, 1)
                       if wall > 0 else None,
            "hit": None if hit is None else hit[0],
            "command_workers": workers,
            "command_span": span,
            "mode": cmd.mode,
        })
        print("sample %d: interval %.3fs e=%+.3f steal %.1f%% "
              "-> workers %d span %d mode %s"
              % (i, wall, error, steal, workers, span,
                 cmd.mode), flush=True)

    after15 = [abs(r["error"]) for r in rows if r["i"] >= 15]
    inband = sum(1 for e in after15 if e <= 0.30) / len(after15) \
        if after15 else 0.0
    checks = {
        "completed_all_samples": len(rows) == SAMPLES,
        "commands_in_bounds": all(
            1 <= r["command_workers"] <= 4
            and (1 << 20) <= r["command_span"] <= (1 << 26)
            for r in rows),
        "no_nan": all(math.isfinite(r["interval_seconds"])
                      and math.isfinite(r["error"])
                      for r in rows),
        "inband_after15_at_least_0.80": inband >= 0.80,
    }
    # A trip fails Gate 5 unless its condition is visible
    # in the recorded live signals. Oscillation on live
    # signals is a controller failure, never visible as
    # an external condition. Host distress is visible in
    # the steal column; signal loss cannot occur here
    # (the driver generates every sample) and would be a
    # failure if claimed.
    trip_excused = False
    if tripped is not None:
        if tripped["reason"] == "host_distress" and any(
                r["steal_percent"] > 25.0 for r in rows):
            trip_excused = True
        checks["trip_excused_by_live_signals"] = trip_excused
    out.update({
        "status": "RUN",
        "rows": rows,
        "trips": tripped,
        "trip_excused": trip_excused,
        "inband_after15": round(inband, 4),
        "loadavg_at_end": loadavg(),
        "backend": (engine.last_search_stats or {}).get(
            "backend"),
        "checks": checks,
    })
    out["verdict"] = all(checks.values())
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print("wrote %s" % path, flush=True)
    print("GATE 5 verdict: %s (inband after 15: %.3f, trips: %s)"
          % (out["verdict"], inband, tripped), flush=True)
    return 0 if out["verdict"] else 1


if __name__ == "__main__":
    sys.exit(main())
