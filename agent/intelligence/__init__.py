"""Agent intelligence package: the autonomous operational
intelligence layer of NOVA SHA-X (Master Build Mandate,
Milestone 1).

One Agent facade wires the logical subsystems together:

- permissions: the three mandate authority levels and the
  action registry that enforces them.
- audit: the append-only audit trail.
- memory: persistent research memory over the existing
  experiment registries.
- planning: the hierarchical task registry.
- interface: the typed mining-engine interface over the
  existing production surfaces.
- strategy: objectives, gap accounting, investigation
  ranking, cited bottlenecks.
- loop: the optimisation cycle state machine with its
  rejected-hypothesis and integrate gates.

The facade's default grant follows the mandate: L2 for
operations, with L3 available only inside the experiment
sandbox directory (.local/agent-experiments by default).
Nothing in this package starts, stops or restarts the live
miner, autopilot or node in Milestone 1.
"""

import os

from .audit import AuditLog
from .interface import MiningInterface
from .loop import OptimisationLoop
from .permissions import Level, PermissionChecker
from .planning import TaskRegistry
from . import strategy as _strategy

_REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".."))
_LOCAL = os.path.join(_REPO_ROOT, ".local")

__all__ = ["Agent", "AuditLog", "MiningInterface",
           "OptimisationLoop", "PermissionChecker",
           "TaskRegistry", "Level"]


class Agent:
    """The Milestone 1 agent facade.

    All paths are injectable for tests. Defaults live under
    the repo .local directory: the audit log, the task
    registry and the experiment sandbox.
    """

    def __init__(self, local_dir=None, audit_path=None,
                 tasks_path=None, sandbox_root=None,
                 engine_factory=None, controller=None):
        local = local_dir or _LOCAL
        self.local_dir = local
        self.sandbox_root = sandbox_root or os.path.join(
            local, "agent-experiments")
        self.checker = PermissionChecker(
            granted=Level.L3, sandbox_root=self.sandbox_root)
        self.audit = AuditLog(
            audit_path or os.path.join(local, "agent-audit.jsonl"))
        self.tasks = TaskRegistry(
            tasks_path or os.path.join(local, "agent-tasks.json"))
        self.interface = MiningInterface(
            self.checker, self.audit, local_dir=local,
            engine_factory=engine_factory, controller=controller)
        self._memory = None

    @property
    def memory(self):
        """The research memory, parsed lazily on first use so
        importing the facade and reading live status stay
        cheap."""
        if self._memory is None:
            from .memory import ResearchMemory
            self._memory = ResearchMemory()
        return self._memory

    def loop(self):
        """A new optimisation loop bound to the research
        memory, this facade's permissions and audit."""
        return OptimisationLoop(memory=self.memory,
                                checker=self.checker,
                                audit=self.audit)

    # Strategy conveniences --------------------------------------
    def gap_report(self, verified_rate_hs):
        return _strategy.gap_report(verified_rate_hs)

    def next_investigations(self, limit=5):
        return _strategy.next_investigations(self.memory,
                                             limit=limit)

    def bottleneck_summary(self):
        return _strategy.bottleneck_summary()

    # Status convenience ------------------------------------------
    def status(self):
        return self.interface.inspect_status()
