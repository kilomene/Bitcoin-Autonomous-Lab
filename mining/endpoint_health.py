"""Endpoint health policy for the pool leg (EXP-050, R-26).

Today the pool leg has exactly one endpoint and exactly one
failure behaviour: the Stratum client's reader loop retries
that endpoint once a second forever, and if the process dies
the autopilot restarts it. The 2026-11-15 outage (pool DNS
failure, miner stopped until supervision restarted it) is the
failure shape this policy exists to absorb inside the miner
process, without operator action.

The policy is a named, inspectable object in the poclbm
tolerance-and-failback tradition (ordered servers, a tolerance
count before a server is judged down, a timed retry of the
primary server, failback when it answers again), with one
addition the precedent lacks: a damping window that bounds
failbacks, so a flapping primary cannot pull the session back
and forth. The parameters are the lab's declared operating
point, recorded in mining/endpoint_config.py
(POOL_HEALTH_DEFAULTS); they are not copied constants.

Semantics, precisely:

- Endpoints are ordered; index 0 is the primary. The policy
  always names exactly one current endpoint.
- note_error() counts consecutive failures against the
  current endpoint. Below error_threshold the decision is
  "retry" (the historical same-endpoint retry). At the
  threshold the decision is "failover" and the current
  endpoint advances to the next in order. When the LAST
  endpoint also reaches the threshold, the decision is
  "exhausted" (returned once, at the transition): the policy
  marks itself exhausted, points back at the primary, and
  from there the historical behaviour is what remains (keep
  retrying the primary; the autopilot restart is the outer
  backstop). Exhaustion is a reported state, never a faked
  recovery.
- note_success() clears the consecutive-error count and any
  exhaustion, and reports whether the success ended an
  exhausted episode.
- Failback: while the current endpoint is not the primary,
  failback_due() becomes true once failback_interval_s has
  passed since the last switch or failed probe AND fewer
  than max_failbacks_per_window failbacks have completed
  inside the trailing damping_window_s. A due failback is
  only an attempt: the caller probes the primary, and on
  probe failure note_probe_failed() restarts the interval;
  on success note_failback() moves the policy back to the
  primary and records the failback against the damping
  window. A flapping primary therefore earns at most
  max_failbacks_per_window failbacks per damping window.

The policy is pure decision logic: no sockets, no threads,
an injectable clock. The Stratum client owns all I/O and
feeds the policy events; mining/mainnet_live.py builds the
policy from the endpoint config when the operator enables
it. With the policy disabled (the default) or absent, every
code path is the historical one, byte for byte in behaviour.
"""

import time

POLICY_NAME = "ordered-failover-damped-failback"
POLICY_VERSION = 1


class EndpointHealthPolicy:
    """Ordered failover with damped failback. See the module
    docstring for the exact semantics of every decision."""

    def __init__(self, endpoints, error_threshold=3,
                 failback_interval_s=300.0, damping_window_s=1800.0,
                 max_failbacks_per_window=1, probe_timeout_s=5.0,
                 clock=None):
        if not endpoints:
            raise ValueError("policy needs at least one endpoint")
        eps = []
        for ep in endpoints:
            host, port = ep
            eps.append((str(host), int(port)))
        if int(error_threshold) < 1:
            raise ValueError("error_threshold must be at least 1")
        if float(failback_interval_s) < 0:
            raise ValueError("failback_interval_s must be >= 0")
        if float(damping_window_s) < 0:
            raise ValueError("damping_window_s must be >= 0")
        if int(max_failbacks_per_window) < 0:
            raise ValueError("max_failbacks_per_window must be >= 0")
        if float(probe_timeout_s) <= 0:
            raise ValueError("probe_timeout_s must be positive")
        self.name = POLICY_NAME
        self.version = POLICY_VERSION
        self.endpoints = eps
        self.error_threshold = int(error_threshold)
        self.failback_interval_s = float(failback_interval_s)
        self.damping_window_s = float(damping_window_s)
        self.max_failbacks_per_window = int(max_failbacks_per_window)
        self.probe_timeout_s = float(probe_timeout_s)
        self._clock = clock if clock is not None else time.monotonic
        self.current_index = 0
        self.consecutive_errors = 0
        self.exhausted = False
        self.last_switch_ts = None
        self.last_probe_ts = None
        self.failback_ts = []
        self.total_failovers = 0
        self.total_failbacks = 0
        self.total_errors = 0
        self.errors_by_endpoint = {}
        self.transitions = []

    def _now(self, now):
        return self._clock() if now is None else float(now)

    @property
    def current(self):
        return self.endpoints[self.current_index]

    @property
    def primary(self):
        return self.endpoints[0]

    @property
    def on_primary(self):
        return self.current_index == 0

    def _record(self, kind, now, **fields):
        rec = {"kind": kind, "ts": now}
        rec.update(fields)
        self.transitions.append(rec)

    def note_error(self, now=None):
        """Register one consecutive failure against the
        current endpoint. Returns "retry", "failover", or
        "exhausted" (the last only at the transition into
        exhaustion; errors while exhausted return "retry")."""
        now = self._now(now)
        self.total_errors += 1
        key = "%s:%d" % self.current
        self.errors_by_endpoint[key] = \
            self.errors_by_endpoint.get(key, 0) + 1
        self.consecutive_errors += 1
        if self.exhausted:
            return "retry"
        if self.consecutive_errors < self.error_threshold:
            return "retry"
        if self.current_index < len(self.endpoints) - 1:
            frm = self.current
            self.current_index += 1
            self.consecutive_errors = 0
            self.last_switch_ts = now
            self.total_failovers += 1
            self._record("failover", now, from_endpoint=frm,
                         to_endpoint=self.current)
            return "failover"
        # The last endpoint reached the threshold too: the
        # policy is exhausted. Point back at the primary (the
        # historical retry target) and say so, once.
        self.exhausted = True
        self.current_index = 0
        self.consecutive_errors = 0
        self.last_switch_ts = now
        self._record("exhausted", now)
        return "exhausted"

    def note_success(self, now=None):
        """Register a successful connection on the current
        endpoint: clears the consecutive-error count and any
        exhaustion. Returns a dict reporting whether this
        success ended an exhausted episode."""
        now = self._now(now)
        was_exhausted = self.exhausted
        self.exhausted = False
        self.consecutive_errors = 0
        if was_exhausted:
            self._record("recovered", now, endpoint=self.current)
        return {"was_exhausted": was_exhausted,
                "endpoint": self.current}

    def failback_due(self, now=None):
        """True when a failback probe attempt is due: off the
        primary, not exhausted, the failback interval has
        passed since the last switch and the last failed
        probe, and the damping window still has failback
        budget."""
        now = self._now(now)
        if self.current_index == 0 or self.exhausted:
            return False
        if self.last_switch_ts is not None and \
                now - self.last_switch_ts < self.failback_interval_s:
            return False
        if self.last_probe_ts is not None and \
                now - self.last_probe_ts < self.failback_interval_s:
            return False
        recent = [t for t in self.failback_ts
                  if now - t < self.damping_window_s]
        return len(recent) < self.max_failbacks_per_window

    def note_probe_failed(self, now=None):
        """A failback probe found the primary still down:
        the next attempt waits another failback interval."""
        now = self._now(now)
        self.last_probe_ts = now
        self._record("failback_probe_failed", now,
                     primary=self.primary)

    def note_failback(self, now=None):
        """A failback probe answered: move back to the
        primary and charge the failback to the damping
        window. Returns the new current endpoint."""
        now = self._now(now)
        frm = self.current
        self.failback_ts.append(now)
        self.total_failbacks += 1
        self.current_index = 0
        self.consecutive_errors = 0
        self.last_switch_ts = now
        self.last_probe_ts = now
        self._record("failback", now, from_endpoint=frm,
                     to_endpoint=self.current)
        return self.current

    def status(self):
        """Plain-dict snapshot for status lines, evidence
        events and the agent layer. Counts are reported as
        their own categories, never summed (EXP-037 rule)."""
        return {
            "policy": self.name,
            "version": self.version,
            "endpoints": ["%s:%d" % ep for ep in self.endpoints],
            "current": "%s:%d" % self.current,
            "on_primary": self.on_primary,
            "consecutive_errors": self.consecutive_errors,
            "exhausted": self.exhausted,
            "total_errors": self.total_errors,
            "total_failovers": self.total_failovers,
            "total_failbacks": self.total_failbacks,
            "errors_by_endpoint": dict(self.errors_by_endpoint),
            "error_threshold": self.error_threshold,
            "failback_interval_s": self.failback_interval_s,
            "damping_window_s": self.damping_window_s,
            "max_failbacks_per_window":
                self.max_failbacks_per_window,
        }
