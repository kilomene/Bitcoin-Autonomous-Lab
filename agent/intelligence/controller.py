"""Production mining controller (Directive 5, Stage 7;
Directive 4 Prompt 2 substance).

MiningController gives the agent brain REAL operational
authority over the existing production supervisor,
mining/autopilot.py, and nothing else. It EXTENDS the
autopilot: supervision, watchdog restarts, backoff, session
rotation and self-update stay exactly where they are. This
module is a typed, verifying client of the autopilot's own
control surface:

- start and stop go through scripts/autopilot.sh, the same
  surface an operator uses (start launches the autopilot;
  stop touches .local/autopilot.stop, which the autopilot
  polls every second).
- state is read from the autopilot's own published files:
  .local/heartbeat.json (written every 5 s) and
  .local/autopilot.lock (the single-instance flock file,
  whose content is the autopilot pid).
- the one signal this controller ever sends (SIGTERM to the
  miner child, inside recover, to let the autopilot's own
  watchdog relaunch it) goes only to a pid read from the
  heartbeat, and only after that pid's /proc cmdline has
  been verified to be the miner. A pid whose cmdline does
  not match is never signalled. There is no code path here
  that signals a guessed, stale-unverified or caller-supplied
  pid.

Every mutating operation VERIFIES its postcondition from the
autopilot's published state before reporting success:
heartbeat freshness and miner_state for start, autopilot
process exit for stop, a changed miner pid for restart. A
verification that times out is a FAILURE, never a success,
and a failed controller call is never reported as success.

Honesty about the current production path (checked in
source, 2026-11-16):

- select_backend: mining/mainnet_live.py constructs
  ComputeEngine() with no requested pin and no CLI argument
  carries one, so no restart can honour a pin either. The
  operation is refused as UNSUPPORTED. (Backend ELIGIBILITY
  decisions remain MiningInterface.select_backend, an L2
  decision that starts nothing.)
- adjust_workers: worker identity and thread counts are
  launch-time only (the autopilot's --worker / BAL_WORKER,
  and the engine's construction inside the miner process).
  There is no runtime adjustment channel, so the operation
  reports RESTART_REQUIRED and applies nothing.
- refresh_job: job supply is push-driven inside the miner
  (pool Stratum mining.notify, or GBT longpoll on the solo
  path). The miner installs no signal handler and reads no
  control file, so there is nothing external to trigger.
  Refused as UNSUPPORTED rather than faked.
- checkpoint: the GBT path's frontier exists
  (mining/work_checkpoint.py, agent/autonomous.py's
  WORK_CHECKPOINT_PATH). checkpoint() reads and reports
  that frontier honestly; the pool path has no checkpoint
  and the result says so.

Recovery taxonomy (recover):

- recoverable, miner down, autopilot alive: the autopilot
  watchdog relaunches the miner within its backoff cap
  (30 s worst case). The controller waits and verifies the
  relaunch; if a verified live miner pid exists but the
  heartbeat shows it exited or hung, it SIGTERMs that
  verified pid to trigger the watchdog, then verifies.
- recoverable, autopilot dead: start it through its script
  and verify.
- non-recoverable, correctness or consensus failure
  (EXP-036 verification failures, or a caller-declared
  correctness fault): HALT and report. Never auto-recovered,
  never looped.
- non-recoverable, crash loop: the heartbeat restart count
  at or beyond CRASH_LOOP_CAP with the miner not running is
  treated as a crash loop beyond the autopilot's own
  backoff handling: HALT and report, no further restarts
  from this controller.

All operations return a ControlResult. ok is True only for
a verified success (or a verified already-in-desired-state).
When a checker is supplied, each operation first requires
its L2 ActionSpec; when an audit log is supplied, each
operation writes one record.
"""

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field

_REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".."))
_LOCAL = os.path.join(_REPO_ROOT, ".local")

HEARTBEAT_STALE_S = 120.0
CRASH_LOOP_CAP = 10
DEFAULT_VERIFY_TIMEOUT_S = 60.0
_AUTOPILOT_NEEDLE = "autopilot.py"
_MINER_NEEDLES = ("mainnet_live.py", "autonomous.py")


class ControllerRefusal(Exception):
    """A controller safety guard refused an action (for
    example a pid whose cmdline does not verify)."""


@dataclass
class ControlResult:
    action: str
    ok: bool
    status: str  # ok | failed | restart_required |
    #              unsupported | refused | halted
    detail: str = ""
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    verified: bool = False


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _parse_ts(ts):
    import calendar
    try:
        return float(calendar.timegm(
            time.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S")))
    except (ValueError, TypeError):
        return None


def pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def pid_cmdline(pid):
    """The /proc cmdline of a pid as one string, or None
    when the process is gone or unreadable."""
    try:
        with open(f"/proc/{int(pid)}/cmdline", "rb") as f:
            raw = f.read()
    except (OSError, ValueError, TypeError):
        return None
    return raw.replace(b"\x00", b" ").decode(
        "utf-8", errors="replace").strip()


class MiningController:
    """Real control over one checkout's autopilot.

    repo_root: the checkout the autopilot belongs to
    (default this repo). local_dir: its .local directory
    (default repo_root/.local). All paths derive from these
    two, so tests point the controller at an isolated copy.
    checker / audit: optional package wiring; the interface
    layer supplies its own, so a standalone controller may
    omit them.
    verify_timeout_s / poll_s: postcondition polling budget.
    env_extra: extra environment for the autopilot script
    (tests use it for BAL_AP_MINER_CMD and BAL_AUTO_UPDATE).
    miner_needles: cmdline substrings that verify a miner
    pid before any signal; injectable because an isolated
    test miner is a stub script, not mainnet_live.py.
    runner: injectable subprocess runner
    callable(argv, cwd, env) -> (rc, stdout, stderr); the
    default is subprocess.run without a shell.
    clock / sleep: injectable for tests.
    """

    def __init__(self, repo_root=None, local_dir=None,
                 checker=None, audit=None,
                 verify_timeout_s=DEFAULT_VERIFY_TIMEOUT_S,
                 poll_s=0.5, env_extra=None,
                 miner_needles=None, runner=None,
                 clock=None, sleep=None):
        self.repo_root = os.path.abspath(repo_root or _REPO_ROOT)
        self.local_dir = os.path.abspath(
            local_dir or os.path.join(self.repo_root, ".local"))
        self.checker = checker
        self.audit = audit
        self.verify_timeout_s = float(verify_timeout_s)
        self.poll_s = float(poll_s)
        self.env_extra = dict(env_extra or {})
        self.miner_needles = tuple(
            miner_needles or _MINER_NEEDLES)
        self._runner = runner or self._default_runner
        self._clock = clock or time.time
        self._sleep = sleep or time.sleep
        self.script = os.path.join(
            self.repo_root, "scripts", "autopilot.sh")
        self.heartbeat_path = os.path.join(
            self.local_dir, "heartbeat.json")
        self.lock_path = os.path.join(
            self.local_dir, "autopilot.lock")
        self.stop_path = os.path.join(
            self.local_dir, "autopilot.stop")
        self.checkpoint_path = os.path.join(
            self.local_dir, "work-checkpoint.json")

    # Plumbing -------------------------------------------------
    @staticmethod
    def _default_runner(argv, cwd, env):
        proc = subprocess.run(
            argv, cwd=cwd, env=env, capture_output=True,
            text=True, timeout=300)
        return proc.returncode, proc.stdout, proc.stderr

    def _gate(self, spec_name):
        if self.checker is not None:
            self.checker.require(spec_name)

    def _audit(self, operation, level, inputs_summary, outcome,
               detail=None):
        if self.audit is not None:
            self.audit.record(operation, level, inputs_summary,
                              outcome, detail=detail)

    def _run_script(self, verb):
        env = dict(os.environ)
        env.update(self.env_extra)
        return self._runner(["bash", self.script, verb],
                            cwd=self.repo_root, env=env)

    # State reading ----------------------------------------------
    def _lock_pid(self):
        try:
            with open(self.lock_path, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def inspect(self):
        """The autopilot's published state, plus liveness and
        cmdline verification of the pids it publishes. Read
        only; never signals anything."""
        hb = _read_json(self.heartbeat_path) or {}
        now = self._clock()
        hb_epoch = _parse_ts(hb.get("ts"))
        age = (now - hb_epoch) if hb_epoch else None
        ap_pid = hb.get("autopilot_pid") or self._lock_pid()
        miner_pid = hb.get("miner_pid")
        ap_alive = pid_alive(ap_pid)
        ap_cmd = pid_cmdline(ap_pid) if ap_alive else None
        miner_alive = pid_alive(miner_pid)
        miner_cmd = pid_cmdline(miner_pid) if miner_alive \
            else None
        fresh = age is not None and age < HEARTBEAT_STALE_S
        return {
            "heartbeat": hb or None,
            "heartbeat_age_s": age,
            "heartbeat_fresh": bool(fresh),
            "autopilot_pid": ap_pid,
            "autopilot_alive": bool(ap_alive),
            "autopilot_verified": bool(
                ap_cmd and _AUTOPILOT_NEEDLE in ap_cmd),
            "autopilot_cmdline": ap_cmd,
            "miner_pid": miner_pid,
            "miner_state": hb.get("miner_state"),
            "miner_alive": bool(miner_alive),
            "miner_verified": bool(
                miner_cmd and any(
                    n in miner_cmd for n in self.miner_needles)),
            "miner_cmdline": miner_cmd,
            "miner_uptime_s": hb.get("miner_uptime_s"),
            "restarts": hb.get("restarts"),
            "shares_accepted_total":
                hb.get("shares_accepted_total"),
            "running": bool(
                fresh and ap_alive
                and hb.get("miner_state") == "running"
                and miner_alive),
        }

    def status(self):
        self._gate("inspect_status")
        info = self.inspect()
        result = ControlResult(
            action="status", ok=True, status="ok",
            detail=("running" if info["running"] else
                    "not running (per the autopilot's own "
                    "published state)"),
            after=info, verified=True)
        self._audit("inspect_status", 1, {}, result.status,
                    detail={"running": info["running"]})
        return result

    # The guessed-PID guard -------------------------------------
    def signal_verified(self, pid, sig, kind):
        """Signal pid ONLY when it was read from the
        autopilot's own published state for the given kind
        ("autopilot" or "miner") AND its live /proc cmdline
        verifies against that kind's needle. Anything else
        raises ControllerRefusal and signals nothing. This is
        the single signalling primitive of this module."""
        info = self.inspect()
        if kind == "autopilot":
            published = info["autopilot_pid"]
            needles = (_AUTOPILOT_NEEDLE,)
        elif kind == "miner":
            published = info["miner_pid"]
            needles = self.miner_needles
        else:
            raise ControllerRefusal(f"unknown signal kind {kind!r}")
        if not pid or int(pid) != int(published or -1):
            raise ControllerRefusal(
                f"pid {pid} is not the {kind} pid the "
                f"autopilot publishes ({published}); refusing "
                "to signal a pid that did not come from the "
                "autopilot's own state")
        cmd = pid_cmdline(pid)
        if not cmd or not any(n in cmd for n in needles):
            raise ControllerRefusal(
                f"pid {pid} cmdline does not verify as the "
                f"{kind} (cmdline: {cmd!r}); refusing to "
                "signal an unverified pid")
        os.kill(int(pid), sig)
        return True

    # Verification polling ---------------------------------------
    def _wait_for(self, predicate, timeout_s=None):
        deadline = self._clock() + (
            timeout_s if timeout_s is not None
            else self.verify_timeout_s)
        info = self.inspect()
        while not predicate(info):
            if self._clock() >= deadline:
                return info, False
            self._sleep(self.poll_s)
            info = self.inspect()
        return info, True

    # Operations ---------------------------------------------------
    def start(self):
        self._gate("start_mining")
        before = self.inspect()
        if before["running"]:
            result = ControlResult(
                action="start", ok=True, status="ok",
                detail=("already running; verified from the "
                        "autopilot heartbeat, nothing started"),
                before=before, after=before, verified=True)
            self._audit("start_mining", 2, {"action": "start"},
                        "already_running")
            return result
        try:
            rc, out, err = self._run_script("start")
        except Exception as exc:
            result = ControlResult(
                action="start", ok=False, status="failed",
                detail=f"autopilot script failed to run: {exc}",
                before=before)
            self._audit("start_mining", 2, {"action": "start"},
                        "failed", detail=result.detail)
            return result
        after, ok = self._wait_for(lambda i: i["running"])
        result = ControlResult(
            action="start", ok=ok,
            status="ok" if ok else "failed",
            detail=(
                "autopilot and miner verified running from "
                "the heartbeat"
                if ok else
                "start was issued through scripts/autopilot.sh "
                f"(rc={rc}) but the postcondition did not "
                "materialise inside the verification window: "
                "no fresh heartbeat with miner_state running; "
                f"script output: {(out or err or '')[-300:]}"),
            before=before, after=after, verified=ok)
        self._audit("start_mining", 2, {"action": "start"},
                    result.status, detail=result.detail[:240])
        return result

    def stop(self):
        self._gate("stop_mining")
        before = self.inspect()
        if not before["autopilot_alive"] and \
                before["miner_state"] != "running":
            result = ControlResult(
                action="stop", ok=True, status="ok",
                detail=("already stopped; no live autopilot "
                        "process and the heartbeat does not "
                        "report a running miner"),
                before=before, after=before, verified=True)
            self._audit("stop_mining", 2, {"action": "stop"},
                        "already_stopped")
            return result
        try:
            rc, out, err = self._run_script("stop")
        except Exception as exc:
            result = ControlResult(
                action="stop", ok=False, status="failed",
                detail=f"autopilot script failed to run: {exc}",
                before=before)
            self._audit("stop_mining", 2, {"action": "stop"},
                        "failed", detail=result.detail)
            return result
        ap_pid = before["autopilot_pid"]
        after, ok = self._wait_for(
            lambda i: not i["autopilot_alive"]
            and i["miner_state"] != "running")
        if ap_pid and pid_alive(ap_pid):
            ok = False
        result = ControlResult(
            action="stop", ok=ok,
            status="ok" if ok else "failed",
            detail=(
                "autopilot process exited and the heartbeat "
                "no longer reports a running miner"
                if ok else
                "stop was requested through scripts/"
                "autopilot.sh but the autopilot process did "
                "not exit inside the verification window; "
                "reporting failure, not success"),
            before=before, after=after, verified=ok)
        self._audit("stop_mining", 2, {"action": "stop"},
                    result.status, detail=result.detail[:240])
        return result

    def restart(self):
        self._gate("restart_mining")
        before = self.inspect()
        old_miner = before["miner_pid"]
        stopped = self.stop()
        if not stopped.ok:
            result = ControlResult(
                action="restart", ok=False, status="failed",
                detail=("restart aborted: the stop phase did "
                        "not verify (" + stopped.detail + ")"),
                before=before, after=stopped.after)
            self._audit("restart_mining", 2,
                        {"action": "restart"}, "failed",
                        detail=result.detail[:240])
            return result
        started = self.start()
        if not started.ok:
            result = ControlResult(
                action="restart", ok=False, status="failed",
                detail=("restart failed at the start phase: "
                        + started.detail),
                before=before, after=started.after)
            self._audit("restart_mining", 2,
                        {"action": "restart"}, "failed",
                        detail=result.detail[:240])
            return result
        new_miner = started.after.get("miner_pid")
        changed = bool(new_miner and old_miner
                       and int(new_miner) != int(old_miner))
        if before["running"] and not changed:
            result = ControlResult(
                action="restart", ok=False, status="failed",
                detail=("miner pid did not change across the "
                        f"restart (before {old_miner}, after "
                        f"{new_miner}); the restart is not "
                        "verified"),
                before=before, after=started.after)
            self._audit("restart_mining", 2,
                        {"action": "restart"}, "failed",
                        detail=result.detail[:240])
            return result
        result = ControlResult(
            action="restart", ok=True, status="ok",
            detail=(f"restart verified: miner pid "
                    f"{old_miner} to {new_miner}"),
            before=before, after=started.after, verified=True)
        self._audit("restart_mining", 2, {"action": "restart"},
                    "ok", detail=result.detail)
        return result

    def select_backend(self, pin="auto"):
        self._gate("select_backend")
        result = ControlResult(
            action="select_backend", ok=False,
            status="unsupported",
            detail=(
                f"backend pin {pin!r} cannot be honoured by "
                "the current production path: mining/"
                "mainnet_live.py constructs ComputeEngine() "
                "with no requested pin and exposes no CLI or "
                "runtime channel for one, so neither a live "
                "change nor a restart can apply it. Refused "
                "as unsupported rather than faked. Backend "
                "eligibility decisions remain available as "
                "MiningInterface.select_backend."))
        self._audit("select_backend", 2, {"pin": pin},
                    "unsupported", detail=result.detail[:240])
        return result

    def adjust_workers(self, count):
        self._gate("adjust_workers")
        if not isinstance(count, int) or isinstance(count, bool) \
                or count < 1:
            result = ControlResult(
                action="adjust_workers", ok=False,
                status="refused",
                detail=f"worker count {count!r} is not a "
                       "positive integer")
            self._audit("adjust_workers", 2, {"count": count},
                        "refused", detail=result.detail)
            return result
        result = ControlResult(
            action="adjust_workers", ok=False,
            status="restart_required",
            detail=(
                f"worker count {count} NOT applied: worker "
                "identity and thread counts are launch-time "
                "only in the current production path (the "
                "autopilot's --worker / BAL_WORKER at launch, "
                "and the ComputeEngine construction inside "
                "the miner process). No runtime adjustment "
                "channel exists; applying this requires a "
                "miner restart under a launch configuration "
                "that carries it, which this controller does "
                "not silently perform."))
        self._audit("adjust_workers", 2, {"count": count},
                    "restart_required",
                    detail=result.detail[:240])
        return result

    def refresh_job(self):
        self._gate("refresh_job")
        result = ControlResult(
            action="refresh_job", ok=False,
            status="unsupported",
            detail=(
                "no external job-refresh trigger exists in "
                "the current production path: job supply is "
                "push-driven inside the miner process (pool "
                "Stratum mining.notify, or GBT longpoll on "
                "the solo path); the miner installs no signal "
                "handler and reads no control file. Refused "
                "as unsupported rather than faked."))
        self._audit("refresh_job", 2, {}, "unsupported",
                    detail=result.detail[:240])
        return result

    def checkpoint(self, path=None):
        self._gate("checkpoint_status")
        target = path or self.checkpoint_path
        before = self.inspect()
        from mining.work_checkpoint import WorkCheckpoint
        cp = WorkCheckpoint(target)
        data = cp._load() if hasattr(cp, "_load") else None
        note = getattr(cp, "last_note", "")
        if data is None:
            result = ControlResult(
                action="checkpoint", ok=True, status="ok",
                detail=(
                    "no GBT work checkpoint at " + target +
                    " (" + (note or "file absent") + "). The "
                    "pool mining path has no checkpoint by "
                    "design (mining/work_checkpoint.py serves "
                    "the GBT path only); nothing was created "
                    "or advanced by this call."),
                before=before,
                after={"checkpoint_exists": False,
                       "path": target})
            self._audit("checkpoint_status", 1,
                        {"path": target}, "no_checkpoint")
            return result
        result = ControlResult(
            action="checkpoint", ok=True, status="ok",
            detail=(
                "GBT work checkpoint frontier read from "
                + target + "; this is a read of the engine "
                "path's own checkpoint file, not an advance "
                "of it. The pool path has no checkpoint."),
            before=before,
            after={"checkpoint_exists": True, "path": target,
                   "complete": data.get("complete"),
                   "frontier_extranonce":
                       data.get("frontier_extranonce"),
                   "frontier_nonce": data.get("frontier_nonce")},
            verified=True)
        self._audit("checkpoint_status", 1, {"path": target},
                    "ok")
        return result

    # Recovery -----------------------------------------------------
    def classify_fault(self, info=None, correctness_failure=False):
        """The recovery taxonomy over one inspect() picture.
        Returns (fault, recoverable): fault is one of none,
        miner_down, autopilot_down, crash_loop, correctness.
        """
        if correctness_failure:
            return "correctness", False
        info = info or self.inspect()
        restarts = info.get("restarts") or 0
        if info["running"]:
            return "none", True
        if info["autopilot_alive"]:
            if restarts >= CRASH_LOOP_CAP:
                return "crash_loop", False
            return "miner_down", True
        return "autopilot_down", True

    def recover(self, correctness_failure=False):
        self._gate("trigger_recovery")
        before = self.inspect()
        fault, recoverable = self.classify_fault(
            before, correctness_failure=correctness_failure)
        if fault == "none":
            result = ControlResult(
                action="recover", ok=True, status="ok",
                detail=("no fault: autopilot and miner "
                        "verified running; nothing recovered"),
                before=before, after=before, verified=True)
            self._audit("trigger_recovery", 2, {},
                        "no_fault")
            return result
        if not recoverable:
            if fault == "correctness":
                detail = (
                    "correctness or consensus failure declared "
                    "or surfaced (EXP-036 class): these are "
                    "never auto-recovered. Halting recovery, "
                    "leaving the stack exactly as found, and "
                    "reporting for human decision.")
            else:
                detail = (
                    f"crash loop: heartbeat restart count "
                    f"{before.get('restarts')} is at or beyond "
                    f"the cap {CRASH_LOOP_CAP} with the miner "
                    "not running. The autopilot's own backoff "
                    "has already had its chance; this "
                    "controller halts and reports instead of "
                    "looping restarts.")
            result = ControlResult(
                action="recover", ok=False, status="halted",
                detail=detail, before=before, after=before)
            self._audit("trigger_recovery", 2, {},
                        "halted", detail=detail[:240])
            return result
        if fault == "autopilot_down":
            started = self.start()
            result = ControlResult(
                action="recover", ok=started.ok,
                status=started.status,
                detail=("recoverable fault autopilot_down: "
                        + started.detail),
                before=before, after=started.after,
                verified=started.verified)
            self._audit("trigger_recovery", 2, {},
                        result.status,
                        detail=result.detail[:240])
            return result
        # miner_down, autopilot alive: the watchdog owns the
        # relaunch. Wait for it first.
        after, ok = self._wait_for(lambda i: i["running"])
        if not ok and after.get("miner_pid") and \
                after.get("miner_alive"):
            # A live miner pid exists but the heartbeat does
            # not show it running (hung or exited between
            # polls): trigger the watchdog by terminating
            # ONLY that verified pid, then verify again.
            try:
                self.signal_verified(after["miner_pid"],
                                     signal.SIGTERM, "miner")
            except ControllerRefusal as exc:
                result = ControlResult(
                    action="recover", ok=False, status="refused",
                    detail=("recoverable fault miner_down: "
                            "the watchdog did not relaunch "
                            "inside the window and the miner "
                            f"pid could not be verified for a "
                            f"signal ({exc}); nothing was "
                            "signalled"),
                    before=before, after=after)
                self._audit("trigger_recovery", 2, {},
                            "refused", detail=result.detail[:240])
                return result
            after, ok = self._wait_for(lambda i: i["running"])
        result = ControlResult(
            action="recover", ok=ok,
            status="ok" if ok else "failed",
            detail=(
                "recoverable fault miner_down: the autopilot "
                "watchdog relaunched the miner and the "
                "heartbeat verifies it running"
                if ok else
                "recoverable fault miner_down: the miner did "
                "not return to a verified running state "
                "inside the verification window; reporting "
                "failure, not success"),
            before=before, after=after, verified=ok)
        self._audit("trigger_recovery", 2, {}, result.status,
                    detail=result.detail[:240])
        return result
