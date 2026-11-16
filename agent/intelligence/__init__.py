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
Stage 7: the facade's interface carries the production
MiningController by default (controller.py), so the L2
controlled operations act on the real autopilot with
verified postconditions; pass controller=False for an
explicitly unwired facade. The facade also owns the
load-shedding ModeManager (modes.py): Normal, Brownout and
Critical modes gate the package's discretionary work and
never touch mining itself.
"""

import os

from .audit import AuditLog
from .controller import MiningController
from .interface import MiningInterface
from .loop import OptimisationLoop
from .modes import ModeManager, ModeRefusal
from .permissions import Level, PermissionChecker
from .planning import TaskRegistry
from . import strategy as _strategy

_REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".."))
_LOCAL = os.path.join(_REPO_ROOT, ".local")

__all__ = ["Agent", "AuditLog", "MiningInterface",
           "MiningController", "ModeManager", "ModeRefusal",
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
                 engine_factory=None, controller=None,
                 verifier_key_path=None, mode_state_path=None):
        local = local_dir or _LOCAL
        self.local_dir = local
        self.verifier_key_path = verifier_key_path or \
            os.path.join(local, "verifier", "verifier.key")
        self.sandbox_root = sandbox_root or os.path.join(
            local, "agent-experiments")
        self.checker = PermissionChecker(
            granted=Level.L3, sandbox_root=self.sandbox_root)
        self.audit = AuditLog(
            audit_path or os.path.join(local, "agent-audit.jsonl"))
        self.tasks = TaskRegistry(
            tasks_path or os.path.join(local, "agent-tasks.json"))
        from .modes import ModeManager
        self.modes = ModeManager(
            state_path=mode_state_path or os.path.join(
                local, "agent-mode.json"),
            audit=self.audit)
        if controller is None:
            from .controller import MiningController
            controller = MiningController(
                repo_root=_REPO_ROOT, local_dir=local,
                checker=self.checker, audit=self.audit)
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
        memory, this facade's permissions and audit, and the
        load-shedding mode gate: transitions into the
        discretionary execution states are refused while the
        mode sheds experiment work."""
        return OptimisationLoop(
            memory=self.memory, checker=self.checker,
            audit=self.audit,
            verifier_key_path=self.verifier_key_path,
            mode_gate=lambda kind: self.modes.allows(kind))

    def mode(self):
        """The current load-shedding mode, for status
        surfaces."""
        return self.modes.current()

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
