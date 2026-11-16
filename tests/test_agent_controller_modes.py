#!/usr/bin/env python3
"""Stage 7 tests: the production MiningController
(agent/intelligence/controller.py) and the cognitive
load-shedding modes (agent/intelligence/modes.py).

Controller tests run against an ISOLATED autopilot instance:
a temp-directory checkout containing a copy of
mining/autopilot.py and scripts/autopilot.sh, its own .local
directory, and a stub miner child (a sleep loop) injected
through BAL_AP_MINER_CMD. The live mainnet stack is never
started, stopped, restarted or signalled by this suite; the
only live-side contact is none at all.

Pins:

- start brings the isolated miner up and the postcondition
  verifies from the heartbeat; a second start reports
  already running; restart verifies a miner pid change;
  stop verifies the autopilot process exit.
- a controller pointed at a broken instance (no autopilot
  script) reports failure, never success.
- the guessed-PID guard: signal_verified refuses a pid that
  is not the pid the autopilot publishes, and refuses the
  miner pid under the autopilot kind; a verified miner
  signal is accepted and the watchdog relaunches the miner.
- recover: no fault on a healthy instance; a correctness
  fault halts and leaves the miner untouched; an autopilot
  down fault is recovered by starting it; a crash loop
  (restart count at the cap, miner down) halts.
- honest refusals: select_backend unsupported,
  adjust_workers restart-required and unapplied,
  refresh_job unsupported, checkpoint reads the GBT
  frontier honestly (absent, then present).
- interface wiring: the default controller is a
  MiningController; L1 is refused start_mining; the L2
  operations route to the controller's results.

Mode tests drive the machine with synthetic signals and a
fake clock: entry confirmation, direct escalation to
Critical, one-level step-down, exit hysteresis that cannot
flap on an oscillating signal, audit logging of transitions
with trigger values, persistence across instances, and the
discretionary gates actually enforced at the experiment
runner, the scheduler bake-off and the optimisation loop.
Awareness honours Critical with a minimal cycle.

Run: python3 tests/test_agent_controller_modes.py
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from agent.intelligence import Agent
from agent.intelligence.audit import AuditLog
from agent.intelligence.awareness import Awareness
from agent.intelligence.controller import (
    ControllerRefusal, MiningController)
from agent.intelligence.experiments import ExperimentRunner
from agent.intelligence.interface import MiningInterface
from agent.intelligence.loop import LoopRefusal
from agent.intelligence.modes import (
    BROWNOUT, CRITICAL, NORMAL, ModeManager, ModeRefusal)
from agent.intelligence.permissions import (
    Level, PermissionChecker, PermissionError)
from agent.intelligence.scheduler import Scheduler

CHECKS = 0


def check(cond, msg):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(msg)


def raises(exc_type, fn, msg):
    global CHECKS
    CHECKS += 1
    try:
        fn()
    except exc_type as exc:
        return exc
    raise AssertionError(msg + " (no exception raised)")


# Isolated autopilot harness -------------------------------------

STUB_MINER = (
    "import time\n"
    "while True:\n"
    "    time.sleep(0.2)\n")


def make_isolated(tmp):
    iso = os.path.join(tmp, "iso")
    os.makedirs(os.path.join(iso, "mining"))
    os.makedirs(os.path.join(iso, "scripts"))
    os.makedirs(os.path.join(iso, ".local"))
    os.makedirs(os.path.join(iso, "evidence"))
    shutil.copy(os.path.join(ROOT, "mining", "autopilot.py"),
                os.path.join(iso, "mining", "autopilot.py"))
    shutil.copy(os.path.join(ROOT, "scripts", "autopilot.sh"),
                os.path.join(iso, "scripts", "autopilot.sh"))
    stub = os.path.join(iso, "stub_miner.py")
    with open(stub, "w", encoding="utf-8") as f:
        f.write(STUB_MINER)
    env = {"BAL_AP_MINER_CMD": json.dumps(
               [sys.executable, stub]),
           "BAL_AUTO_UPDATE": "0",
           "BAL_AP_HEARTBEAT_S": "1",
           "BAL_AP_POLL_S": "0.2",
           "BAL_AP_STALE_S": "300"}
    ctl = MiningController(
        repo_root=iso, local_dir=os.path.join(iso, ".local"),
        verify_timeout_s=45.0, poll_s=0.25, env_extra=env,
        miner_needles=("stub_miner.py",))
    return iso, ctl


def test_controller_lifecycle(tmp):
    iso, ctl = make_isolated(tmp)
    try:
        info = ctl.inspect()
        check(info["running"] is False,
              "isolated instance starts down")
        started = ctl.start()
        check(started.ok and started.verified,
              f"start verifies running ({started.detail})")
        info = ctl.inspect()
        check(info["running"] is True
              and info["miner_verified"] is True
              and info["autopilot_verified"] is True,
              "heartbeat pids alive and cmdline-verified")
        first_miner = info["miner_pid"]
        again = ctl.start()
        check(again.ok and "already running" in again.detail,
              "second start reports already running, verified")
        status = ctl.status()
        check(status.ok and status.after["running"] is True,
              "status reports the verified running state")

        # Guessed-PID guard.
        decoy = subprocess.Popen(["sleep", "120"])
        try:
            raises(ControllerRefusal,
                   lambda: ctl.signal_verified(
                       decoy.pid, signal.SIGTERM, "miner"),
                   "a pid the autopilot does not publish is "
                   "refused")
            check(decoy.poll() is None,
                  "the decoy was not signalled")
            raises(ControllerRefusal,
                   lambda: ctl.signal_verified(
                       first_miner, signal.SIGTERM, "autopilot"),
                   "the miner pid under the autopilot kind "
                   "is refused")
            check(ctl.inspect()["miner_alive"] is True,
                  "the miner was not signalled by the "
                  "refused call")
        finally:
            decoy.terminate()
            decoy.wait(timeout=10)

        # A verified miner signal triggers the autopilot's
        # own watchdog relaunch.
        check(ctl.signal_verified(first_miner,
                                  signal.SIGTERM, "miner")
              is True,
              "the published, cmdline-verified miner pid "
              "may be signalled")
        deadline = time.time() + 45
        new_miner = None
        while time.time() < deadline:
            info = ctl.inspect()
            if info["running"] and info["miner_pid"] \
                    and info["miner_pid"] != first_miner:
                new_miner = info["miner_pid"]
                break
            time.sleep(0.25)
        check(new_miner is not None,
              "watchdog relaunched the miner with a new pid "
              "after the verified signal")

        restarted = ctl.restart()
        check(restarted.ok and restarted.verified,
              f"restart verifies ({restarted.detail})")
        check(restarted.after["miner_pid"] != new_miner,
              "restart changed the miner pid")

        healthy = ctl.recover()
        check(healthy.ok and "no fault" in healthy.detail,
              "recover on a healthy instance is a verified "
              "no-op")
        halted = ctl.recover(correctness_failure=True)
        check(not halted.ok and halted.status == "halted",
              "a correctness fault halts recovery")
        check(ctl.inspect()["running"] is True,
              "the halted recovery left the miner untouched")

        stopped = ctl.stop()
        check(stopped.ok and stopped.verified,
              f"stop verifies the exit ({stopped.detail})")
        check(ctl.inspect()["running"] is False,
              "instance is down after the verified stop")
        again_stop = ctl.stop()
        check(again_stop.ok
              and "already stopped" in again_stop.detail,
              "second stop reports already stopped")

        # Autopilot-down recovery starts it again.
        recovered = ctl.recover()
        check(recovered.ok and recovered.verified,
              "recover restarts a down autopilot and "
              f"verifies ({recovered.detail})")
        check(ctl.inspect()["running"] is True,
              "instance running after recovery")
        final_stop = ctl.stop()
        check(final_stop.ok, "cleanup stop verifies")
    finally:
        try:
            ctl.stop()
        except Exception:
            pass


def test_controller_broken_and_honest(tmp):
    empty = os.path.join(tmp, "empty")
    os.makedirs(os.path.join(empty, ".local"))
    broken = MiningController(
        repo_root=empty, local_dir=os.path.join(empty, ".local"),
        verify_timeout_s=3.0, poll_s=0.2)
    failed = broken.start()
    check(not failed.ok and failed.status == "failed",
          "a controller pointed at a broken instance "
          "reports failure, not success")
    check(failed.verified is False,
          "the failed start is not marked verified")

    iso, ctl = make_isolated(tmp)
    sel = ctl.select_backend("v512")
    check(not sel.ok and sel.status == "unsupported",
          "select_backend is refused as unsupported on the "
          "current production path")
    adj = ctl.adjust_workers(4)
    check(not adj.ok and adj.status == "restart_required",
          "adjust_workers reports restart-required")
    bad = ctl.adjust_workers(0)
    check(not bad.ok and bad.status == "refused",
          "a non-positive worker count is refused")
    ref = ctl.refresh_job()
    check(not ref.ok and ref.status == "unsupported",
          "refresh_job is refused as unsupported (no "
          "external trigger exists)")
    cp = ctl.checkpoint()
    check(cp.ok and cp.after["checkpoint_exists"] is False,
          "checkpoint honestly reports no GBT checkpoint "
          "on the isolated instance")
    from mining.work_checkpoint import WorkCheckpoint
    WorkCheckpoint(ctl.checkpoint_path).record(
        bytes(range(32)), 100, "00" * 32, 1700000000, (0, 64),
        2, 12345, complete=False)
    cp2 = ctl.checkpoint()
    check(cp2.ok and cp2.after["checkpoint_exists"] is True
          and cp2.after["frontier_nonce"] == 12345,
          "checkpoint reads the real GBT frontier when one "
          "exists")

    # Crash loop: a fabricated heartbeat with the restart
    # count at the cap, a dead miner, and a live decoy as
    # the published autopilot pid. Recovery must halt and
    # must not attempt a start.
    fake_local = os.path.join(tmp, "fake", ".local")
    os.makedirs(fake_local)
    decoy = subprocess.Popen(["sleep", "120"])
    try:
        hb = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                  time.gmtime()),
              "autopilot_pid": decoy.pid, "miner_pid": 999999,
              "miner_state": "exited rc=1",
              "miner_uptime_s": 0, "restarts": 99,
              "shares_accepted_total": 0,
              "evidence_age_s": 1.0}
        with open(os.path.join(fake_local, "heartbeat.json"),
                  "w", encoding="utf-8") as f:
            json.dump(hb, f)
        fake = MiningController(
            repo_root=os.path.join(tmp, "fake"),
            local_dir=fake_local, verify_timeout_s=3.0)
        verdict = fake.recover()
        check(not verdict.ok and verdict.status == "halted"
              and "crash loop" in verdict.detail,
              "a crash loop at the restart cap halts "
              "recovery instead of looping restarts")
    finally:
        decoy.terminate()
        decoy.wait(timeout=10)


def test_interface_wiring(tmp):
    iso, ctl = make_isolated(tmp)
    audit = AuditLog(os.path.join(tmp, "iface-audit.jsonl"))
    l1 = PermissionChecker(granted=Level.L1)
    iface_l1 = MiningInterface(l1, audit, controller=False)
    raises(PermissionError, lambda: iface_l1.start_mining(),
           "interface enforces L2 for start_mining even "
           "with a controller wired")
    agent = Agent(local_dir=os.path.join(iso, ".local"),
                  audit_path=os.path.join(tmp, "a.jsonl"),
                  tasks_path=os.path.join(tmp, "t.json"),
                  sandbox_root=os.path.join(tmp, "sandbox"),
                  controller=ctl)
    try:
        check(isinstance(agent.interface.resolved_controller,
                         MiningController),
              "the facade interface resolves to a "
              "MiningController")
        started = agent.interface.start_mining()
        check(started.ok,
              "interface start_mining executes through the "
              "real controller")
        adj = agent.interface.adjust_workers(2)
        check(not adj.ok
              and adj.status == "restart_required",
              "interface adjust_workers returns the "
              "controller's restart-required result")
        ref = agent.interface.refresh_job()
        check(not ref.ok and ref.status == "unsupported",
              "interface refresh_job returns the "
              "controller's unsupported result")
        halted = agent.interface.trigger_recovery(
            correctness_failure=True)
        check(not halted.ok and halted.status == "halted",
              "interface trigger_recovery halts on a "
              "correctness fault")
        stopped = agent.interface.stop_mining()
        check(stopped.ok,
              "interface stop_mining executes through the "
              "real controller")
        ops = {r["operation"] for r in agent.audit.read()}
        check("start_mining" in ops and "stop_mining" in ops,
              "controlled operations are audit-logged")
    finally:
        try:
            ctl.stop()
        except Exception:
            pass


# Modes ------------------------------------------------------------

class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def make_modes(tmp, clock, audit=None):
    return ModeManager(
        state_path=os.path.join(tmp, "mode.json"),
        audit=audit, entry_confirm_samples=2,
        exit_window_s=100.0, clock=clock)


def test_mode_machine(tmp):
    clock = FakeClock()
    audit = AuditLog(os.path.join(tmp, "mode-audit.jsonl"))
    mm = make_modes(tmp, clock, audit=audit)
    fired = []
    mm.on_transition(lambda old, new, trig: fired.append(
        (old, new)))
    check(mm.mode == NORMAL, "mode starts normal")
    out = mm.update({"load_ratio": 1.6}, now=1000.0)
    check(out["mode"] == NORMAL,
          "one contention sample does not shed (entry "
          "confirmation)")
    out = mm.update({"load_ratio": 1.6}, now=1005.0)
    check(out["mode"] == BROWNOUT,
          "two confirmed contention samples enter brownout")
    check(mm.allows("experiment") is False
          and mm.allows("bake_off") is False
          and mm.allows("planning") is True
          and mm.allows("status") is True,
          "brownout sheds experiments and bake-offs only")
    check(fired == [(NORMAL, BROWNOUT)],
          "transition callback fired once")
    recs = [r for r in audit.read()
            if r["operation"] == "mode_transition"]
    check(len(recs) == 1
          and recs[0]["detail"]["load_ratio"] == 1.6,
          "the transition is audit-logged with its trigger "
          "values")

    # Hysteresis: oscillating clear/trigger samples must
    # not flap the mode out of brownout.
    t = 1010.0
    for i in range(6):
        mm.update({"load_ratio": 0.5}, now=t)
        t += 40.0
        mm.update({"load_ratio": 1.6}, now=t)
        t += 10.0
        check(mm.mode == BROWNOUT,
              "oscillating signal does not flap brownout "
              f"(cycle {i})")
    # A sustained clear exits one level after the window.
    mm.update({"load_ratio": 0.5}, now=t)
    mm.update({"load_ratio": 0.5}, now=t + 99.0)
    check(mm.mode == BROWNOUT,
          "clear shorter than the exit window holds the "
          "mode")
    mm.update({"load_ratio": 0.5}, now=t + 100.0)
    check(mm.mode == NORMAL,
          "sustained clear for the exit window steps down")

    # Direct escalation to critical, then one-level steps.
    mm.update({"load_ratio": 3.5}, now=2000.0)
    out = mm.update({"load_ratio": 3.5}, now=2005.0)
    check(out["mode"] == CRITICAL,
          "severe contention escalates directly to critical")
    check(mm.allows("planning") is False
          and mm.allows("status") is True,
          "critical sheds everything but status")
    mm.update({"load_ratio": 0.4}, now=2100.0)
    mm.update({"load_ratio": 0.4}, now=2200.0)
    check(mm.mode == BROWNOUT,
          "critical steps down to brownout, not straight "
          "to normal")
    mm.update({"load_ratio": 0.4}, now=2300.0)
    mm.update({"load_ratio": 0.4}, now=2400.0)
    check(mm.mode == NORMAL,
          "brownout steps down to normal after its own "
          "clear window")

    # Rate-based trigger against the standing baseline.
    mm2 = make_modes(os.path.join(tmp, "m2"), clock)
    mm2.update({"miner_rate_hs": 20.0e6}, now=3000.0)
    check(mm2.current()["baseline_rate_hs"] == 20.0e6,
          "the first observed rate becomes the baseline")
    mm2.update({"miner_rate_hs": 9.0e6}, now=3005.0)
    out = mm2.update({"miner_rate_hs": 9.0e6}, now=3010.0)
    check(out["mode"] == CRITICAL,
          "a rate at 45 percent of baseline is critical")

    # Persistence across instances.
    mm3 = ModeManager(state_path=mm.state_path,
                      entry_confirm_samples=2,
                      exit_window_s=100.0, clock=clock)
    check(mm3.mode == NORMAL
          and mm3.current()["transitions"]
          == mm.current()["transitions"],
          "mode state persists across instances")


def test_mode_gates(tmp):
    clock = FakeClock()
    agent = Agent(local_dir=tmp,
                  audit_path=os.path.join(tmp, "a.jsonl"),
                  tasks_path=os.path.join(tmp, "t.json"),
                  sandbox_root=os.path.join(tmp, "sandbox"),
                  mode_state_path=os.path.join(tmp, "mode.json"),
                  controller=False)
    # Drive the facade's manager to brownout.
    agent.modes.entry_confirm_samples = 2
    agent.modes.update({"load_ratio": 2.0}, now=1000.0)
    agent.modes.update({"load_ratio": 2.0}, now=1005.0)
    check(agent.modes.mode == BROWNOUT,
          "facade mode manager reached brownout")
    runner = ExperimentRunner(agent)
    raises(ModeRefusal,
           lambda: runner.create_experiment(
               "mode gate probe", ["zzz-mode-gate-probe"],
               "agent-test"),
           "experiment creation refused in brownout")
    sched = Scheduler(
        agent, cache_path=os.path.join(tmp, "sched.json"))
    raises(ModeRefusal, lambda: sched.bake_off(),
           "bake-off measurement refused in brownout")
    loop = agent.loop()
    rec = loop.new_record("mode-gate-loop", "mode gate probe",
                          keywords=["zzz-mode-gate-probe"])
    # Walk to the doorstep of the discretionary states:
    # observe to hypothesise to check prior to analyse to
    # derive to mathematical correctness (5 advances); the
    # next state is isolated_implementation.
    for _ in range(5):
        loop.advance(rec)
    check(rec.state == "mathematical_correctness",
          "loop walked to the discretionary doorstep")
    raises(LoopRefusal, lambda: loop.advance(rec),
           "loop transition into the isolated implementation "
           "state refused in brownout")
    # Back to normal: the same transition is allowed. The
    # facade manager carries the production exit window
    # (300 s), so the sustained clear must span it.
    agent.modes.update({"load_ratio": 0.3}, now=2000.0)
    agent.modes.update({"load_ratio": 0.3}, now=2301.0)
    check(agent.modes.mode == NORMAL,
          "mode recovered to normal for the gate retest")
    loop.advance(rec)
    check(rec.state == "isolated_implementation",
          "the gated transition proceeds in normal mode")
    # run_command gate: create in normal, flip to critical,
    # the next command boundary refuses.
    record, _sandbox = runner.create_experiment(
        "wind down probe", ["zzz-wind-down-probe"],
        "agent-test")
    agent.modes.update({"load_ratio": 4.0}, now=3000.0)
    agent.modes.update({"load_ratio": 4.0}, now=3005.0)
    check(agent.modes.mode == CRITICAL,
          "mode escalated to critical mid-experiment")
    raises(ModeRefusal,
           lambda: runner.run_command(
               record, [sys.executable, "-c", "pass"]),
           "run_command refuses at the command boundary "
           "in critical (in-flight wind-down)")


def test_awareness_mode(tmp):
    d = os.path.join(tmp, "aw")
    os.makedirs(d)
    hb_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                          time.gmtime())
    with open(os.path.join(d, "heartbeat.json"), "w") as f:
        json.dump({"ts": hb_ts, "autopilot_pid": 111,
                   "miner_pid": 222, "miner_state": "running",
                   "miner_uptime_s": 5.0, "restarts": 0,
                   "shares_accepted_total": 3,
                   "evidence_age_s": 1.0}, f)
    with open(os.path.join(d, "evidence-count.json"),
              "w") as f:
        json.dump({"accepted": 3, "rejected": 0,
                   "share_results": 3}, f)
    with open(os.path.join(d, "mainnet-status.txt"),
              "w") as f:
        f.write("MAINNET LIVE MINING\npool=x\n")
    with open(os.path.join(d, "evidence.jsonl"), "w") as f:
        f.write("")
    with open(os.path.join(d, "endpoint.json"), "w") as f:
        json.dump({"mode": "pool"}, f)
    with open(os.path.join(d, "node-config.json"), "w") as f:
        f.write("{}")

    class FakeRPC:
        def get_blockchain_info(self):
            return {"blocks": 1, "headers": 1,
                    "initialblockdownload": False}

    agent = Agent(local_dir=d,
                  audit_path=os.path.join(d, "audit.jsonl"),
                  tasks_path=os.path.join(d, "tasks.json"),
                  sandbox_root=os.path.join(d, "sandbox"),
                  controller=False)
    aw = Awareness(
        agent,
        heartbeat_path=os.path.join(d, "heartbeat.json"),
        census_path=os.path.join(d, "evidence-count.json"),
        status_path=os.path.join(d, "mainnet-status.txt"),
        endpoint_path=os.path.join(d, "endpoint.json"),
        node_config_path=os.path.join(d, "node-config.json"),
        evidence_log_path=os.path.join(d, "evidence.jsonl"),
        rpc_factory=lambda path, timeout: FakeRPC())
    snap = aw.snapshot()
    check(snap["mode"] is not None
          and snap["mode"]["mode"] == NORMAL,
          "snapshot reports the current mode")
    agent.modes.update({"load_ratio": 4.0}, now=1000.0)
    agent.modes.update({"load_ratio": 4.0}, now=1005.0)
    check(agent.modes.mode == CRITICAL,
          "mode driven to critical for the awareness test")
    report = aw.observe_cycle(window_s=0.0)
    check(report["rate_observation"] is None
          and "critical" in report["mode_note"],
          "critical awareness cycle is minimal (snapshot "
          "only, no rate window)")


def main():
    tmp = tempfile.mkdtemp(prefix="agent-controller-modes-")
    test_controller_lifecycle(os.path.join(tmp, "life"))
    test_controller_broken_and_honest(
        os.path.join(tmp, "broken"))
    test_interface_wiring(os.path.join(tmp, "iface"))
    test_mode_machine(os.path.join(tmp, "modes"))
    test_mode_gates(os.path.join(tmp, "gates"))
    test_awareness_mode(os.path.join(tmp, "awfx"))
    print(f"ALL AGENT CONTROLLER AND MODE TESTS PASSED "
          f"({CHECKS} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
