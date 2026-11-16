"""Authority levels and action permissions (Master Build Mandate
sections 4.1 and 11.1).

The mandate defines three action categories:

- L1 READ_ONLY: inspect source, telemetry, configuration and
  research. Never mutates anything.
- L2 CONTROLLED: start or stop mining, adjust approved worker
  settings, allocate ranges, run benchmarks, initiate recovery.
  May mutate operational state, never production code or
  consensus-critical values.
- L3 EXPERIMENTAL: create and edit isolated experimental
  implementations and run their tests. Permitted only inside an
  experiment sandbox directory. Production integration is NOT an
  L3 act: it passes the independent integration gate in loop.py.

Every operation this package exposes is named in ACTION_REGISTRY
with its level and whether it mutates production state. No entry
in the registry mutates production state in Milestone 1: the
operations that would (start/stop of the live miner) are L2
specifications whose execution is delegated to an injectable
controller that is not wired to production in this milestone.

Enforcement is a PermissionChecker: a caller holds a granted
level, and require() raises PermissionError when an operation
needs more than the grant, or when an L3 operation is attempted
without a sandbox path inside the checker's sandbox root.
"""

from dataclasses import dataclass
from enum import IntEnum
import os


class Level(IntEnum):
    L1 = 1
    L2 = 2
    L3 = 3


READ_ONLY = Level.L1
CONTROLLED = Level.L2
EXPERIMENTAL = Level.L3

LEVEL_NAMES = {
    Level.L1: "L1 read-only",
    Level.L2: "L2 controlled operations",
    Level.L3: "L3 experimental modifications",
}


class PermissionError(Exception):
    """Raised when an operation exceeds the caller's grant.

    Deliberately shadows the builtin of the same name inside
    this package so callers can catch the package's refusal
    without confusing it with an OS permission failure. The
    attributes name the operation, the level it requires and
    the level the caller holds.
    """

    def __init__(self, operation, required, granted, reason=""):
        self.operation = operation
        self.required = required
        self.granted = granted
        self.reason = reason
        msg = (f"operation {operation!r} requires "
               f"{LEVEL_NAMES.get(required, required)}; caller "
               f"holds {LEVEL_NAMES.get(granted, granted)}")
        if reason:
            msg += f"; {reason}"
        super().__init__(msg)


@dataclass(frozen=True)
class ActionSpec:
    name: str
    level: Level
    mutates_production: bool
    description: str


def _spec(name, level, mutates, description):
    return ActionSpec(name=name, level=Level(level),
                      mutates_production=bool(mutates),
                      description=description)


ACTION_REGISTRY = {spec.name: spec for spec in [
    # L1 read-only operations.
    _spec("inspect_status", 1, False,
          "Read autopilot heartbeat and evidence census state."),
    _spec("inspect_machine", 1, False,
          "Read CPU model, logical CPUs and instruction flags."),
    _spec("inspect_backends", 1, False,
          "Read ComputeEngine probe results and dispatch order."),
    _spec("verify_candidate", 1, False,
          "Independently verify one 80-byte candidate header "
          "through mining/candidate_verify.py."),
    _spec("estimate_probability", 1, False,
          "Evaluate mining probability formulas on given inputs."),
    _spec("checkpoint_status", 1, False,
          "Read a work checkpoint frontier file."),
    _spec("memory_lookup", 1, False,
          "Look up one research memory entry by id."),
    _spec("memory_search", 1, False,
          "Keyword search over the research memory."),
    _spec("gap_report", 1, False,
          "Compute the measured gap to the objective targets."),
    _spec("plan_read", 1, False,
          "Read the task registry."),
    _spec("audit_read", 1, False,
          "Read the audit log."),
    # L2 controlled operations. None of these is wired to the
    # live miner in Milestone 1; start/stop execute only through
    # an injectable controller (see interface.py).
    _spec("select_backend", 2, False,
          "Decide the eligible backend for a requested pin. "
          "Decision only; never starts mining."),
    _spec("start_mining", 2, True,
          "Start mining through the injected controller. Not "
          "wired to production in Milestone 1."),
    _spec("stop_mining", 2, True,
          "Stop mining through the injected controller. Not "
          "wired to production in Milestone 1."),
    _spec("adjust_workers", 2, True,
          "Adjust approved worker settings through the injected "
          "controller. Not wired in Milestone 1."),
    _spec("run_benchmark", 2, False,
          "Run a controlled benchmark in an experiment context."),
    _spec("trigger_recovery", 2, True,
          "Initiate a recovery operation through the injected "
          "controller. Not wired in Milestone 1."),
    _spec("plan_write", 2, False,
          "Create or transition tasks in the task registry."),
    _spec("loop_advance", 2, False,
          "Advance an optimisation loop record one state."),
    # L3 experimental modifications, sandbox only.
    _spec("create_experiment", 3, False,
          "Create an isolated experimental implementation "
          "inside the sandbox directory."),
    _spec("modify_experiment", 3, False,
          "Edit an experimental implementation inside the "
          "sandbox directory."),
    _spec("record_evidence", 3, False,
          "Write experiment evidence inside the sandbox "
          "directory."),
]}


def get_spec(name):
    """The ActionSpec for an operation name, or KeyError."""
    return ACTION_REGISTRY[name]


class PermissionChecker:
    """Enforces the registry against one caller's grant.

    granted: the highest Level the caller holds.
    sandbox_root: directory inside which L3 operations are
    permitted. An L3 require() call must pass sandbox_path
    naming a path inside this root; anything else is refused
    even when the grant itself is L3.
    """

    def __init__(self, granted=Level.L2, sandbox_root=None):
        self.granted = Level(granted)
        self.sandbox_root = (os.path.abspath(sandbox_root)
                             if sandbox_root else None)

    def check(self, name, sandbox_path=None):
        """Return the ActionSpec if permitted, else raise
        PermissionError. Unknown operations are refused."""
        spec = ACTION_REGISTRY.get(name)
        if spec is None:
            raise PermissionError(
                name, Level.L3, self.granted,
                "unknown operation; not in the action registry")
        if spec.level <= Level.L2:
            if self.granted < spec.level:
                raise PermissionError(name, spec.level, self.granted)
            return spec
        # L3: grant plus sandbox containment.
        if self.granted < spec.level:
            raise PermissionError(
                name, spec.level, self.granted,
                "experimental modifications need an L3 grant")
        if sandbox_path is None:
            raise PermissionError(
                name, spec.level, self.granted,
                "L3 operations require a sandbox path")
        if self.sandbox_root is None:
            raise PermissionError(
                name, spec.level, self.granted,
                "no sandbox root configured for this checker")
        target = os.path.abspath(sandbox_path)
        root = self.sandbox_root
        if target != root and not target.startswith(root + os.sep):
            raise PermissionError(
                name, spec.level, self.granted,
                f"sandbox path {target!r} is outside the "
                f"sandbox root {root!r}")
        return spec

    def require(self, name, sandbox_path=None):
        """Alias of check(), named for call sites that gate an
        action before performing it."""
        return self.check(name, sandbox_path=sandbox_path)

    def permits(self, name, sandbox_path=None):
        """Boolean form of check(); never raises."""
        try:
            self.check(name, sandbox_path=sandbox_path)
            return True
        except PermissionError:
            return False
