"""PID control for worker count and span size (EXP-058,
portfolio NOVA-ER-0018, register R-32).

This component sits at the autopilot seam: a supervisor
calls update(signals) once per control sample and gets a
Command (worker count = engine search threads, span size
= nonces per search call, mode). It adapts both quantities
from one measured signal, the span completion interval,
through two cascaded PID loops:

- the inner span loop (fast, velocity form) drives the
  interval error e = (T_target - T_measured) / T_target
  to zero by moving log2(span);
- the outer worker loop (slow, absolute form) reads the
  inner loop's span saturation: sustained saturation at
  the span floor means capacity per worker is scarce and
  desired workers fall; saturation at the ceiling means
  intervals stay fast at the largest spans and desired
  workers rise.

The step policy is retained in code (StepPolicy) and is
both the historical behaviour (gpu/engine.py tune_*
functions probe candidate thread counts once, pick the
peak, and hold) and the fallback: on signal loss, a
non-finite signal, detected oscillation, or host
distress (steal far outside the EXP-031 band), the
controller trips, latches onto the step policy, and
records the trip. Gains are validated at construction:
a mis-configured controller cannot be built.

The controller ships DISABLED by default. A controller
built with enabled=False always returns the step-policy
command, which is exactly today's behaviour; one
configuration value restores the step policy, which
remains in code. Nothing in the live mining paths
imports this module (EXP-058); enabling it against the
production miner is a separate step.

Gain selection is recorded in
research/sha256d/exp058/PREDECLARATION.md, derived from
the EXP-031 recorded signals before any trial ran.
Exact SHA-256d only: this module moves no hashes and
touches no validation path; where validation applies,
EXP-036 (mining/candidate_verify.py) is the only route.
"""

import math
from dataclasses import dataclass, field

# Actuation bounds (fixed by the EXP-058 predeclaration).
WORKERS_MIN = 1
WORKERS_MAX = 4
WORKERS_BASE = 2
LOG2_SPAN_MIN = 20.0
LOG2_SPAN_MAX = 26.0
LOG2_SPAN_MID = 23.0
SPAN_MIN = 1 << 20
SPAN_MAX = 1 << 26
SPAN_MID = 1 << 23

# Control constants (predeclaration, EXP-031 derived).
TARGET_INTERVAL = 2.0        # seconds per span, T_target
SAMPLE_DT = 5.0              # seconds, production heartbeat cadence
WORKER_ACTUATION_THRESHOLD = 0.6
WORKER_DWELL_SAMPLES = 6
SIGNAL_LOSS_TRIP_SAMPLES = 5     # trip at the 6th lost sample
STEAL_TRIP_PERCENT = 25.0        # ten times the EXP-031 band
STEAL_TRIP_SAMPLES = 3
OSC_WINDOW = 40
OSC_WORKER_REVERSALS = 4
OSC_SPAN_SIGN_CHANGES = 16
OSC_SPAN_MATERIAL = 0.15     # log2 per sample, see below


class SignalFault(Exception):
    """A control signal was non-finite or unusable."""


def _finite(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be a real number, got %r"
                         % (name, value))
    if not math.isfinite(value):
        raise ValueError("%s must be finite, got %r" % (name, value))
    return float(value)


@dataclass(frozen=True)
class PIDGains:
    """PID gains, validated at construction.

    A gain fault is a construction fault: non-finite,
    negative or all-zero gains raise ValueError, so a
    mis-configured controller can never be built.
    """

    kp: float
    ki: float
    kd: float

    def __post_init__(self):
        kp = _finite("kp", self.kp)
        ki = _finite("ki", self.ki)
        kd = _finite("kd", self.kd)
        for name, val in (("kp", kp), ("ki", ki), ("kd", kd)):
            if val < 0.0:
                raise ValueError("%s must be >= 0, got %r"
                                 % (name, val))
        if kp == 0.0 and ki == 0.0 and kd == 0.0:
            raise ValueError("at least one gain must be > 0")
        object.__setattr__(self, "kp", kp)
        object.__setattr__(self, "ki", ki)
        object.__setattr__(self, "kd", kd)


# Gains selected from EXP-031 signals, recorded in the
# EXP-058 predeclaration before any trial ran.
SPAN_GAINS = PIDGains(kp=0.35, ki=0.06, kd=0.10)
WORKER_GAINS = PIDGains(kp=0.8, ki=0.04, kd=0.0)


class PIDController:
    """One discrete PID loop with anti-windup.

    Absolute form: update(error, dt) returns
    kp*e + ki*integral(e dt) + kd*de/dt, clamped to
    [out_min, out_max], with the integral clamped to
    integral_limit and frozen while the output is
    saturated in the direction the error pushes
    (conditional anti-windup). The velocity (increment)
    form is obtained by the caller treating the output
    as an increment; the span loop does exactly that.
    """

    def __init__(self, gains, out_min, out_max, integral_limit):
        if not isinstance(gains, PIDGains):
            raise ValueError("gains must be a PIDGains instance")
        self.gains = gains
        self.out_min = _finite("out_min", out_min)
        self.out_max = _finite("out_max", out_max)
        if self.out_max < self.out_min:
            raise ValueError("out_max < out_min")
        self.integral_limit = _finite("integral_limit",
                                      integral_limit)
        if self.integral_limit < 0.0:
            raise ValueError("integral_limit must be >= 0")
        self._integral = 0.0
        self._prev_error = None

    def reset(self):
        self._integral = 0.0
        self._prev_error = None

    @property
    def integral(self):
        return self._integral

    def update(self, error, dt):
        error = _finite("error", error)
        dt = _finite("dt", dt)
        if dt <= 0.0:
            raise ValueError("dt must be > 0")
        deriv = 0.0
        if self._prev_error is not None and self.gains.kd > 0.0:
            deriv = self.gains.kd * (error - self._prev_error) / dt
        new_integral = self._integral + error * dt
        new_integral = max(-self.integral_limit,
                           min(self.integral_limit, new_integral))
        raw = (self.gains.kp * error
               + self.gains.ki * new_integral + deriv)
        out = max(self.out_min, min(self.out_max, raw))
        saturated = out != raw
        pushing = (raw > self.out_max and error > 0.0) or \
                  (raw < self.out_min and error < 0.0)
        if not (saturated and pushing):
            self._integral = new_integral
        self._prev_error = error
        return out


@dataclass
class Signals:
    """One control sample.

    interval_seconds: measured wall time of one span
    search, or None when the sample is missing (signal
    loss). steal_percent: guest steal over the sample
    window, monitored and used only by the fallback.
    """

    interval_seconds: object = None
    steal_percent: float = 0.0


@dataclass
class Command:
    workers: int
    span: int
    mode: str            # "pid", "step" or "disabled"
    tripped: bool = False
    trip_reason: object = None


@dataclass
class Trip:
    sample: int
    reason: str


class StepPolicy:
    """The retained step policy: baseline and fallback.

    Models the production step behaviour (one-shot probe,
    pick the peak, hold) as a threshold relief stepper
    for fallback duty: while the interval error exceeds
    +/- 25 percent for 3 consecutive samples it steps
    the worker count by 1 in the relieving direction
    (intervals too slow with spans already small means
    too many workers chasing too little capacity: step
    down; intervals too fast means capacity is spare:
    step up) and resets the span to mid, with a
    5-sample cooldown between steps. Its initial command
    is the production default the tuner starts from:
    2 workers, span 2^23.
    """

    ERROR_THRESHOLD = 0.25
    CONSECUTIVE = 3
    COOLDOWN = 5

    def __init__(self, workers=WORKERS_BASE, span=SPAN_MID):
        self.workers = workers
        self.span = span
        self._slow = 0
        self._fast = 0
        self._cooldown = 0

    def reset(self, workers=WORKERS_BASE, span=SPAN_MID):
        self.workers = workers
        self.span = span
        self._slow = 0
        self._fast = 0
        self._cooldown = 0

    def update(self, signals):
        if self._cooldown > 0:
            self._cooldown -= 1
        interval = signals.interval_seconds
        if interval is None or not _is_finite_positive(interval):
            return Command(self.workers, self.span, "step")
        error = (TARGET_INTERVAL - interval) / TARGET_INTERVAL
        if error < -self.ERROR_THRESHOLD:
            self._slow += 1
            self._fast = 0
        elif error > self.ERROR_THRESHOLD:
            self._fast += 1
            self._slow = 0
        else:
            self._slow = 0
            self._fast = 0
        if self._cooldown == 0 and self._slow >= self.CONSECUTIVE:
            self.workers = max(WORKERS_MIN, self.workers - 1)
            self.span = SPAN_MID
            self._slow = 0
            self._cooldown = self.COOLDOWN
        elif self._cooldown == 0 and self._fast >= self.CONSECUTIVE:
            self.workers = min(WORKERS_MAX, self.workers + 1)
            self.span = SPAN_MID
            self._fast = 0
            self._cooldown = self.COOLDOWN
        return Command(self.workers, self.span, "step")


def _is_finite_positive(value):
    return isinstance(value, (int, float)) \
        and not isinstance(value, bool) \
        and math.isfinite(value) and value > 0.0


@dataclass
class AdaptiveWorkController:
    """Cascaded PID worker/span controller with a
    latching step-policy fallback. Ships disabled: with
    enabled=False every update returns the step-policy
    command and the PID loops never run.
    """

    enabled: bool = False
    span_gains: PIDGains = field(default=SPAN_GAINS)
    worker_gains: PIDGains = field(default=WORKER_GAINS)
    target_interval: float = TARGET_INTERVAL

    def __post_init__(self):
        # Integral state limits are set so the integral
        # TERM is bounded by the predeclaration's clamps:
        # 1.0 log2 of accumulated correction for the span
        # loop, 1.0 worker for the worker loop. dt inside
        # the loops is counted in control samples (the
        # predeclaration derives every gain per sample;
        # the wall cadence is SAMPLE_DT seconds).
        self._span_pid = PIDController(
            self.span_gains, -0.5, 0.5,
            integral_limit=(1.0 / self.span_gains.ki
                            if self.span_gains.ki > 0 else 0.0))
        # Worker PID output is desired workers around the
        # base; integral contribution clamped to 1.0
        # worker (integral state in error*seconds units
        # is scaled by dt inside the loop, so the state
        # limit is 1.0 / ki / dt at the nominal cadence:
        # use a state limit that bounds the contribution).
        self._worker_pid = PIDController(
            self.worker_gains, WORKERS_MIN - WORKERS_BASE,
            WORKERS_MAX - WORKERS_BASE,
            integral_limit=(1.0 / self.worker_gains.ki
                            if self.worker_gains.ki > 0 else 0.0))
        self._step = StepPolicy()
        self._mode = "pid" if self.enabled else "disabled"
        self._log2_span = LOG2_SPAN_MID
        self._workers = WORKERS_BASE
        self._desired = float(WORKERS_BASE)
        self._since_change = WORKER_DWELL_SAMPLES
        self._sample = 0
        self._lost = 0
        self._steal_high = 0
        self.trips = []
        self._worker_dir_history = []
        self._span_sign_history = []
        self._last_worker_dir = 0
        self._history = []

    @property
    def mode(self):
        return self._mode

    @property
    def workers(self):
        return self._workers

    @property
    def span(self):
        return int(round(2.0 ** self._log2_span))

    @property
    def desired_workers(self):
        return self._desired

    @property
    def history(self):
        return list(self._history)

    def reset(self):
        """Operator reset: clear the latch and the loops."""
        self.__post_init__()

    def _trip(self, reason):
        self.trips.append(Trip(self._sample, reason))
        self._mode = "step"
        self._step.reset(self._workers, self.span)

    def _check_oscillation(self):
        window = self._worker_dir_history[-OSC_WINDOW:]
        reversals = 0
        prev = 0
        for d in window:
            if d != 0 and prev != 0 and d != prev:
                reversals += 1
            if d != 0:
                prev = d
        if reversals >= OSC_WORKER_REVERSALS:
            return True
        signs = self._span_sign_history[-OSC_WINDOW:]
        changes = sum(1 for a, b in zip(signs, signs[1:])
                      if a != 0 and b != 0 and a != b)
        return changes >= OSC_SPAN_SIGN_CHANGES

    # Span velocity materiality: a per-sample log2 span
    # move below this is regulation dither around the
    # setpoint (the nominal loop's corrections are a few
    # hundredths of a log2), not oscillation. The
    # oscillation detector counts sign changes only
    # between material moves; a fault-gain loop slams
    # the +/- 0.5 clamp on alternate samples and trips
    # it immediately. See the EXP-058 report's judgment
    # calls for the build-time disclosure.

    def update(self, signals, dt=1.0):
        """Advance one control sample. dt is counted in
        samples (see __post_init__), not seconds."""
        self._sample += 1
        if not self.enabled:
            cmd = self._step.update(signals)
            cmd.mode = "disabled"
            self._history.append(cmd)
            return cmd
        if self._mode == "step":
            cmd = self._step.update(signals)
            cmd.tripped = True
            cmd.trip_reason = self.trips[-1].reason if self.trips \
                else None
            self._history.append(cmd)
            return cmd

        interval = signals.interval_seconds
        # Non-finite or unusable signal: immediate trip.
        if interval is not None and not _is_finite_positive(
                interval):
            self._trip("nonfinite_signal")
            cmd = self._step.update(Signals(None,
                                            signals.steal_percent))
            cmd.tripped = True
            cmd.trip_reason = "nonfinite_signal"
            self._history.append(cmd)
            return cmd
        # Signal loss: hold, then trip at the 6th loss.
        if interval is None:
            self._lost += 1
            if self._lost > SIGNAL_LOSS_TRIP_SAMPLES:
                self._trip("signal_loss")
                cmd = self._step.update(signals)
                cmd.tripped = True
                cmd.trip_reason = "signal_loss"
                self._history.append(cmd)
                return cmd
            cmd = Command(self._workers, self.span, "pid")
            self._history.append(cmd)
            return cmd
        self._lost = 0

        # Host distress: steal far outside the EXP-031 band.
        steal = signals.steal_percent
        if isinstance(steal, (int, float)) \
                and math.isfinite(steal) \
                and steal > STEAL_TRIP_PERCENT:
            self._steal_high += 1
            if self._steal_high >= STEAL_TRIP_SAMPLES:
                self._trip("host_distress")
                cmd = self._step.update(signals)
                cmd.tripped = True
                cmd.trip_reason = "host_distress"
                self._history.append(cmd)
                return cmd
        else:
            self._steal_high = 0

        error = (self.target_interval - interval) \
            / self.target_interval

        # Inner span loop (velocity form).
        delta = self._span_pid.update(error, dt)
        self._span_sign_history.append(
            0 if abs(delta) < OSC_SPAN_MATERIAL
            else (1 if delta > 0 else -1))
        self._log2_span = max(LOG2_SPAN_MIN, min(
            LOG2_SPAN_MAX, self._log2_span + delta))

        # Outer worker loop (absolute form) on span
        # saturation, actuated with threshold and dwell.
        # The saturation error carries the deadband the
        # predeclaration describes in words ("sustained
        # saturation NEAR the floor / ceiling"): span
        # within +/- 0.75 log2 of mid is the neutral
        # zone, |sat| <= 0.25, and contributes no error,
        # because the equilibrium span at the optimal
        # worker count sits slightly above mid and a
        # deadband-free integral would chase it forever.
        sat = (self._log2_span - LOG2_SPAN_MID) / 3.0
        if sat > 0.25:
            sat_error = sat - 0.25
        elif sat < -0.25:
            sat_error = sat + 0.25
        else:
            sat_error = 0.0
        offset = self._worker_pid.update(sat_error, dt)
        self._desired = WORKERS_BASE + offset
        self._since_change += 1
        direction = 0
        if self._since_change >= WORKER_DWELL_SAMPLES:
            if self._desired - self._workers \
                    >= WORKER_ACTUATION_THRESHOLD:
                direction = 1
            elif self._workers - self._desired \
                    >= WORKER_ACTUATION_THRESHOLD:
                direction = -1
        if direction != 0:
            self._workers = max(WORKERS_MIN, min(
                WORKERS_MAX, self._workers + direction))
            self._since_change = 0
            self._worker_dir_history.append(direction)
            self._last_worker_dir = direction
        else:
            self._worker_dir_history.append(0)

        if self._check_oscillation():
            self._trip("oscillation")
            cmd = self._step.update(signals)
            cmd.tripped = True
            cmd.trip_reason = "oscillation"
            self._history.append(cmd)
            return cmd

        cmd = Command(self._workers, self.span, "pid")
        self._history.append(cmd)
        return cmd


def make_work_controller(config=None):
    """Build a controller from a configuration mapping.

    Default and missing configuration both yield the
    disabled controller (step policy only): enabling PID
    control is an explicit, operator-visible choice of
    one configuration value, per the EXP-058 rollback
    design.
    """
    config = config or {}
    enabled = bool(config.get("pid_enabled", False))
    span_gains = SPAN_GAINS
    worker_gains = WORKER_GAINS
    if "span_gains" in config:
        g = config["span_gains"]
        span_gains = g if isinstance(g, PIDGains) else \
            PIDGains(g["kp"], g["ki"], g["kd"])
    if "worker_gains" in config:
        g = config["worker_gains"]
        worker_gains = g if isinstance(g, PIDGains) else \
            PIDGains(g["kp"], g["ki"], g["kd"])
    return AdaptiveWorkController(enabled=enabled,
                                  span_gains=span_gains,
                                  worker_gains=worker_gains)
