"""Cognitive load-shedding modes (Directive 5, Stage 7;
Directive 4 Prompt 2/3 substance).

Three modes protect the one thing that must never be shed:
mining itself. The agent's discretionary work (experiments,
bake-offs, planning cycles, full-cadence awareness) is shed
in stages as the machine comes under contention, and is only
restored after the contention has cleared for a sustained
window, so the system cannot flap between modes.

- NORMAL: everything available. Experiments and bake-offs
  may run; awareness runs at full cadence.
- BROWNOUT: entered on sustained contention (load average
  high relative to the guest's measured effective CPUs, or
  the miner's measured rate degraded against its own
  baseline). No new experiment runs, no bake-offs, awareness
  cadence reduced. Planning and status continue. Mining is
  untouched.
- CRITICAL: entered on severe contention or severe miner
  rate degradation. The agent does nothing but protect
  mining: no experiments, no bake-offs, no planning cycles
  beyond status, awareness minimal (snapshot only).

Triggers are computed from real signals only: the 1-minute
load average (os.getloadavg) divided by the effective CPU
count (EXP-031 measured about 2 effective CPUs on this
guest; the figure is an input, not a claim about cores), and
the miner backend rate against a baseline rate (the first
rate the manager observes becomes the baseline; awareness
supplies both from its own measurements). A signal that is
absent does not trigger anything: absence is not contention.

Hysteresis, both directions:

- Entry requires ENTRY_CONFIRM_SAMPLES consecutive samples
  at or beyond the entry severity, so one spiked sample
  cannot shed load.
- Exit steps down ONE level at a time (CRITICAL to BROWNOUT
  to NORMAL) and only after the clear condition for the
  current level has held continuously for EXIT_WINDOW_S
  seconds. A sample that re-triggers the current level
  resets the clear clock.

The mode is persisted as JSON (atomically replaced) at the
manager's state path, is visible in awareness snapshots and
in the package status surface, and every transition is
audit-logged with the trigger values that caused it.
Registered transition callbacks are invoked on every
transition; the experiment runner's wind-down is
cooperative: discretionary entry points re-check the mode
at every command boundary, so in-flight discretionary work
stops at its next boundary after a transition, and the
callback is the notification hook for that wind-down.

This module never starts, stops, restarts, signals or
throttles the miner, the autopilot or the node. A mode
transition changes only what the AGENT does.
"""

import json
import os
import time

NORMAL = "normal"
BROWNOUT = "brownout"
CRITICAL = "critical"
_SEVERITY = {NORMAL: 0, BROWNOUT: 1, CRITICAL: 2}
_BY_SEVERITY = {0: NORMAL, 1: BROWNOUT, 2: CRITICAL}

# EXP-031 (research/sha256d/exp031): the guest claims 4 vCPUs
# but delivers about 2 effective CPUs. Load triggers are
# ratios against this estimate.
EFFECTIVE_CPUS_EXP031 = 2.0

# Entry thresholds. The rate thresholds reuse the awareness
# layer's degradation fraction (RATE_DROP_FRACTION 0.25 in
# awareness.py): a 25 percent rate drop is brownout, a 50
# percent drop is critical.
LOAD_BROWNOUT_RATIO = 1.5
LOAD_CRITICAL_RATIO = 3.0
LOAD_CLEAR_RATIO = 1.2
RATE_BROWNOUT_RATIO = 0.75
RATE_CRITICAL_RATIO = 0.50
RATE_CLEAR_RATIO = 0.85

ENTRY_CONFIRM_SAMPLES = 2
EXIT_WINDOW_S = 300.0

# Awareness cadence per mode, seconds between full observe
# cycles when a caller honours the cadence. Critical is
# snapshot-only regardless of cadence.
AWARENESS_INTERVAL_S = {NORMAL: 60.0, BROWNOUT: 300.0,
                        CRITICAL: 900.0}

# Discretionary kinds and whether each mode allows them.
# status is never shed. planning is allowed in brownout
# (the task registry is cheap bookkeeping) and shed in
# critical beyond status reads.
_ALLOWS = {
    NORMAL: {"experiment": True, "bake_off": True,
             "planning": True, "awareness_full": True,
             "status": True},
    BROWNOUT: {"experiment": False, "bake_off": False,
               "planning": True, "awareness_full": False,
               "status": True},
    CRITICAL: {"experiment": False, "bake_off": False,
               "planning": False, "awareness_full": False,
               "status": True},
}


class ModeRefusal(RuntimeError):
    """Discretionary work was refused by the current mode.
    Carries the mode and the kind of work refused."""

    def __init__(self, mode, kind, detail=""):
        self.mode = mode
        self.kind = kind
        msg = (f"mode {mode}: discretionary work of kind "
               f"{kind!r} is shed in this mode")
        if detail:
            msg += f"; {detail}"
        super().__init__(msg)


def _default_state_path():
    root = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", ".."))
    return os.path.join(root, ".local", "agent-mode.json")


def compute_ratios(signals):
    """Derive (load_ratio, rate_ratio) from a signals dict.
    Either is None when its inputs are absent. signals may
    carry load_ratio / rate_ratio directly, or the raw
    load1 / effective_cpus and miner_rate_hs /
    baseline_rate_hs pairs."""
    load_ratio = signals.get("load_ratio")
    if load_ratio is None:
        load1 = signals.get("load1")
        eff = signals.get("effective_cpus") or \
            EFFECTIVE_CPUS_EXP031
        if load1 is not None and eff:
            load_ratio = float(load1) / float(eff)
    rate_ratio = signals.get("rate_ratio")
    if rate_ratio is None:
        rate = signals.get("miner_rate_hs")
        base = signals.get("baseline_rate_hs")
        if rate is not None and base:
            rate_ratio = float(rate) / float(base)
    return load_ratio, rate_ratio


def desired_severity(load_ratio, rate_ratio):
    """The severity the signals ask for, 0, 1 or 2. Absent
    signals ask for nothing."""
    sev = 0
    if load_ratio is not None:
        if load_ratio >= LOAD_CRITICAL_RATIO:
            sev = max(sev, 2)
        elif load_ratio >= LOAD_BROWNOUT_RATIO:
            sev = max(sev, 1)
    if rate_ratio is not None:
        if rate_ratio <= RATE_CRITICAL_RATIO:
            sev = max(sev, 2)
        elif rate_ratio <= RATE_BROWNOUT_RATIO:
            sev = max(sev, 1)
    return sev


class ModeManager:
    """The persisted load-shedding mode machine.

    state_path: JSON state file (injectable for tests;
    default .local/agent-mode.json).
    audit: optional AuditLog; every transition is recorded
    under operation mode_transition with its trigger values.
    entry_confirm_samples / exit_window_s: hysteresis
    parameters, injectable so tests can drive the machine
    without waiting.
    clock: injectable time source (defaults to time.time).
    """

    def __init__(self, state_path=None, audit=None,
                 entry_confirm_samples=ENTRY_CONFIRM_SAMPLES,
                 exit_window_s=EXIT_WINDOW_S, clock=None):
        self.state_path = state_path or _default_state_path()
        self.audit = audit
        self.entry_confirm_samples = int(entry_confirm_samples)
        self.exit_window_s = float(exit_window_s)
        self._clock = clock or time.time
        self._callbacks = []
        self._state = self._load()

    # Persistence --------------------------------------------
    def _load(self):
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and \
                    data.get("mode") in _SEVERITY:
                return {
                    "mode": data["mode"],
                    "since": data.get("since"),
                    "baseline_rate_hs":
                        data.get("baseline_rate_hs"),
                    "last_signals": data.get("last_signals"),
                    "last_ratios": data.get("last_ratios"),
                    "pending_severity":
                        data.get("pending_severity", 0),
                    "pending_count":
                        data.get("pending_count", 0),
                    "clear_since": data.get("clear_since"),
                    "transitions": data.get("transitions", 0),
                    "last_transition":
                        data.get("last_transition"),
                }
        except (OSError, ValueError):
            pass
        return {"mode": NORMAL, "since": None,
                "baseline_rate_hs": None, "last_signals": None,
                "last_ratios": None, "pending_severity": 0,
                "pending_count": 0, "clear_since": None,
                "transitions": 0, "last_transition": None}

    def _save(self):
        try:
            parent = os.path.dirname(
                os.path.abspath(self.state_path))
            os.makedirs(parent, exist_ok=True)
            tmp = self.state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=1,
                          sort_keys=True)
            os.replace(tmp, self.state_path)
        except OSError:
            pass

    # Inspection -----------------------------------------------
    def current(self):
        """The current mode as a plain dict, for status
        surfaces."""
        return {
            "mode": self._state["mode"],
            "since": self._state["since"],
            "baseline_rate_hs":
                self._state["baseline_rate_hs"],
            "last_signals": self._state["last_signals"],
            "last_ratios": self._state["last_ratios"],
            "transitions": self._state["transitions"],
            "last_transition": self._state["last_transition"],
            "awareness_interval_s":
                AWARENESS_INTERVAL_S[self._state["mode"]],
            "allows": dict(_ALLOWS[self._state["mode"]]),
        }

    @property
    def mode(self):
        return self._state["mode"]

    def allows(self, kind):
        return _ALLOWS[self._state["mode"]].get(kind, False)

    def require_allowed(self, kind, detail=""):
        if not self.allows(kind):
            raise ModeRefusal(self._state["mode"], kind,
                              detail=detail)
        return True

    def awareness_interval_s(self):
        return AWARENESS_INTERVAL_S[self._state["mode"]]

    def on_transition(self, callback):
        """Register callback(old_mode, new_mode, trigger) for
        mode transitions. The experiment wind-down hook."""
        self._callbacks.append(callback)
        return callback

    # Baseline ---------------------------------------------------
    def note_rate(self, rate_hs):
        """Record a miner rate observation. The first rate
        seen becomes the standing baseline; later rates do
        not move it (a degraded rate must not redefine
        normal). Returns the baseline."""
        if rate_hs is None:
            return self._state["baseline_rate_hs"]
        if self._state["baseline_rate_hs"] is None:
            self._state["baseline_rate_hs"] = float(rate_hs)
            self._save()
        return self._state["baseline_rate_hs"]

    def reset_baseline(self, rate_hs=None):
        self._state["baseline_rate_hs"] = (
            float(rate_hs) if rate_hs is not None else None)
        self._save()
        return self._state["baseline_rate_hs"]

    # The machine --------------------------------------------------
    def _clear_for_current(self, load_ratio, rate_ratio):
        """True when the signals no longer trigger the
        CURRENT level: load below the clear ratio and rate
        above the clear ratio, for whichever signals are
        present. With no signals present there is nothing to
        clear on, so the mode holds (absence is not
        recovery)."""
        if load_ratio is None and rate_ratio is None:
            return False
        if load_ratio is not None and \
                load_ratio >= LOAD_CLEAR_RATIO:
            return False
        if rate_ratio is not None and \
                rate_ratio <= RATE_CLEAR_RATIO:
            return False
        return True

    def _transition(self, new_mode, trigger, now):
        old = self._state["mode"]
        self._state["mode"] = new_mode
        self._state["since"] = now
        self._state["transitions"] += 1
        self._state["pending_severity"] = 0
        self._state["pending_count"] = 0
        self._state["clear_since"] = None
        self._state["last_transition"] = {
            "from": old, "to": new_mode, "ts": now,
            "trigger": trigger}
        self._save()
        if self.audit is not None:
            self.audit.record(
                "mode_transition", 2,
                {"from": old, "to": new_mode},
                "transition", detail=trigger)
        for cb in list(self._callbacks):
            try:
                cb(old, new_mode, trigger)
            except Exception:
                pass
        return new_mode

    def update(self, signals, now=None):
        """Feed one signals sample; returns the current mode
        dict. signals: dict with any of load1,
        effective_cpus, load_ratio, miner_rate_hs,
        baseline_rate_hs, rate_ratio. The trigger values of
        every transition are persisted and audit-logged."""
        now = float(now if now is not None else self._clock())
        signals = dict(signals or {})
        rate = signals.get("miner_rate_hs")
        if rate is not None and \
                signals.get("baseline_rate_hs") is None:
            signals["baseline_rate_hs"] = self.note_rate(rate)
        load_ratio, rate_ratio = compute_ratios(signals)
        self._state["last_signals"] = {
            k: signals.get(k) for k in (
                "load1", "effective_cpus", "miner_rate_hs",
                "baseline_rate_hs", "heartbeat_age_s")
            if signals.get(k) is not None}
        self._state["last_ratios"] = {
            "load_ratio": load_ratio, "rate_ratio": rate_ratio}
        cur = _SEVERITY[self._state["mode"]]
        want = desired_severity(load_ratio, rate_ratio)
        trigger = {
            "load_ratio": load_ratio, "rate_ratio": rate_ratio,
            "load1": signals.get("load1"),
            "effective_cpus": signals.get("effective_cpus"),
            "miner_rate_hs": signals.get("miner_rate_hs"),
            "baseline_rate_hs":
                signals.get("baseline_rate_hs"),
            "desired_severity": want}
        if want > cur:
            if self._state["pending_severity"] == want:
                self._state["pending_count"] += 1
            else:
                self._state["pending_severity"] = want
                self._state["pending_count"] = 1
            self._state["clear_since"] = None
            if self._state["pending_count"] >= \
                    self.entry_confirm_samples:
                self._transition(_BY_SEVERITY[want], trigger,
                                 now)
                return self.current()
        elif want == cur:
            self._state["pending_severity"] = 0
            self._state["pending_count"] = 0
            self._state["clear_since"] = None
        else:
            self._state["pending_severity"] = 0
            self._state["pending_count"] = 0
            if self._clear_for_current(load_ratio, rate_ratio):
                if self._state["clear_since"] is None:
                    self._state["clear_since"] = now
                elif now - self._state["clear_since"] >= \
                        self.exit_window_s:
                    self._transition(_BY_SEVERITY[cur - 1],
                                     trigger, now)
                    return self.current()
            else:
                self._state["clear_since"] = None
        self._save()
        return self.current()
