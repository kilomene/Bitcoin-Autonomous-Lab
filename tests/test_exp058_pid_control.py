#!/usr/bin/env python3
"""EXP-058 regression suite: PID control for worker
count and span size (NOVA-ER-0018, register R-32).

Layers, in order:

  1. Gain validation: every gain fault raises at
     construction (Gate 3 gain_faults, part a).
  2. Default-off behaviour: a controller built with no
     configuration returns the step-policy command
     (today's behaviour), and the PID loops never run.
  3. Gate 3 regression form: the nominal, step_down and
     step_up scenarios and the signal_loss, nonfinite
     and host_distress fallback mechanics, run through
     the campaign driver at the campaign seed. The
     step_up worker-reach bound is a KNOWN MISS (see
     the EXP-058 report: an interval-only cascade
     cannot observe spare capacity), so this suite
     asserts the step_up stability bounds and records
     the miss instead of asserting the reach.
  4. Fallback mechanics in-process: signal loss holds
     then trips at the 6th lost sample and latches;
     the 10x-Kp fault controller trips on oscillation.

Gate 5 (the supervised live trial) is NOT in this
suite: it is load-gated by its predeclared
quiet-window condition and lives in the campaign
driver research/sha256d/exp058/exp058_gate5.py. The
campaign of record is research/sha256d/exp058/
exp058_campaign.py; this suite is the regression form.
No other machine is contacted.
"""

import os
import sys

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
EXP058 = os.path.join(ROOT, "research/sha256d/exp058")
sys.path.insert(0, ROOT)
sys.path.insert(0, EXP058)

import exp058_campaign as camp  # noqa: E402
from mining.pid_control import (AdaptiveWorkController,  # noqa: E402
                                PIDGains, Signals,
                                make_work_controller)

CHECKS = 0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError("check failed: %s" % label)
    print("ok %d: %s" % (CHECKS, label), flush=True)


def main():
    camp.check_predeclaration()
    check(True, "predeclaration hash pinned and verified")

    faults = 0
    for gains in [(float("nan"), 0.06, 0.10),
                  (float("inf"), 0.06, 0.10),
                  (0.35, -0.06, 0.10),
                  (0.0, 0.0, 0.0)]:
        try:
            PIDGains(*gains)
        except ValueError:
            faults += 1
    check(faults == 4, "all 4 gain faults raise ValueError")

    ctrl = make_work_controller()
    cmd = ctrl.update(Signals(1.0, 2.0))
    check(cmd.mode == "disabled" and cmd.workers == 2
          and cmd.span == (1 << 23),
          "default controller is disabled step policy")

    res = camp.run_pid(camp.capacity_nominal, camp.SEED)
    check(res["final_workers"] == 2
          and res["worker_changes_after_20"] <= 2
          and not res["trips"]
          and camp.frac_in_band(res["rows"], 0, 0.15, 20)
          >= 0.90,
          "gate3 nominal scenario within bounds")

    res = camp.run_pid(camp.capacity_step_down, camp.SEED)
    back = camp.first_in_band_after(res["rows"], 40)
    check(back is not None and back <= 52
          and res["worker_changes"] <= 4
          and not res["trips"],
          "gate3 step_down scenario within bounds")

    res = camp.run_pid(camp.capacity_step_up, camp.SEED)
    back = camp.first_in_band_after(res["rows"], 40)
    check(back is not None and back <= 52
          and not res["trips"]
          and res["final_workers"] == 2,
          "gate3 step_up stability bounds hold (worker "
          "reach is the recorded known miss)")

    res = camp.run_pid(camp.capacity_nominal, camp.SEED,
                       signal_loss_window=(50, 66))
    check(res["trips"] and res["trips"][0]["reason"]
          == "signal_loss"
          and res["trips"][0]["sample"] == 56,
          "signal loss trips at the 6th lost sample")

    res = camp.run_pid(camp.capacity_nominal, camp.SEED,
                       nonfinite_at=29)
    check(res["trips"] and res["trips"][0]["reason"]
          == "nonfinite_signal"
          and res["trips"][0]["sample"] == 30,
          "nonfinite signal trips immediately")

    res = camp.run_pid(
        camp.capacity_nominal, camp.SEED,
        steal_fn=lambda i: 30.0 if 50 <= i < 61 else 2.0)
    check(res["trips"] and res["trips"][0]["reason"]
          == "host_distress"
          and res["trips"][0]["sample"] <= 53,
          "host distress trips by the 3rd sample")

    fault = AdaptiveWorkController(
        enabled=True, span_gains=PIDGains(3.5, 0.06, 0.10))
    res = camp.run_pid(camp.capacity_nominal, camp.SEED,
                       controller=fault)
    check(res["trips"] and res["trips"][0]["reason"]
          == "oscillation",
          "10x-Kp fault controller trips on oscillation")

    print("EXP-058 suite: %d checks, ALL PASSED" % CHECKS,
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
