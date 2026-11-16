"""Hierarchical planning and the task registry (Master Build
Mandate sections 4.1C and 14).

Planning is hierarchical: Strategic, Project, Task, Execution.
Every task record carries the fields the mandate requires: a
clear objective, a parent, dependencies, required evidence,
expected output, risk level, resource budget, success criteria,
failure criteria and a completion state.

States: planned, active, blocked, done, failed, rejected.

Two gates are enforced structurally:

- A task cannot enter active or done while any dependency is
  not done.
- A task cannot enter done until every item in its
  required_evidence has been supplied, either at transition
  time or recorded earlier with add_evidence(). This is the
  planning form of the lab's honesty rule: unfinished work is
  never recorded as completed.

Persistence is a single JSON file (path injectable; default
.local/agent-tasks.json), written atomically: a sibling temp
file, fsync, then os.replace, the same pattern as
mining/work_checkpoint.py.
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict

PLAN_LEVELS = ("strategic", "project", "task", "execution")
TASK_STATES = ("planned", "active", "blocked", "done",
               "failed", "rejected")
RISK_LEVELS = ("low", "medium", "high")

_TRANSITIONS = {
    "planned": ("active", "blocked", "rejected"),
    "active": ("blocked", "done", "failed", "rejected"),
    "blocked": ("active", "rejected", "failed"),
    "failed": ("active", "rejected"),
    "done": (),
    "rejected": (),
}


class PlanningError(Exception):
    """Raised for an invalid task, transition or gate failure."""


@dataclass
class TaskRecord:
    task_id: str
    objective: str
    level: str = "task"
    parent: str = None
    dependencies: list = field(default_factory=list)
    required_evidence: list = field(default_factory=list)
    expected_output: str = ""
    risk: str = "medium"
    resource_budget: str = ""
    success_criteria: str = ""
    failure_criteria: str = ""
    state: str = "planned"
    evidence: list = field(default_factory=list)
    history: list = field(default_factory=list)
    created_ts: float = 0.0

    def validate(self):
        if self.level not in PLAN_LEVELS:
            raise PlanningError(
                f"task {self.task_id}: level {self.level!r} "
                f"not one of {PLAN_LEVELS}")
        if self.state not in TASK_STATES:
            raise PlanningError(
                f"task {self.task_id}: state {self.state!r} "
                f"not one of {TASK_STATES}")
        if self.risk not in RISK_LEVELS:
            raise PlanningError(
                f"task {self.task_id}: risk {self.risk!r} "
                f"not one of {RISK_LEVELS}")
        if not self.objective:
            raise PlanningError(
                f"task {self.task_id}: objective is required")


def _default_path():
    root = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", ".."))
    return os.path.join(root, ".local", "agent-tasks.json")


class TaskRegistry:
    """Persisted registry of TaskRecord objects."""

    def __init__(self, path=None):
        self.path = path or _default_path()
        self.tasks = {}
        self.load_failures = 0
        self._load()

    # Persistence -------------------------------------------------
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except OSError:
            return
        except ValueError:
            self.load_failures += 1
            return
        items = data.get("tasks") if isinstance(data, dict) else None
        if not isinstance(items, list):
            self.load_failures += 1
            return
        for item in items:
            try:
                rec = TaskRecord(**item)
                rec.validate()
                self.tasks[rec.task_id] = rec
            except (TypeError, PlanningError):
                self.load_failures += 1

    def _save(self):
        payload = {"version": 1,
                   "tasks": [asdict(t) for t in
                             self.tasks.values()]}
        parent = os.path.dirname(os.path.abspath(self.path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    # Operations --------------------------------------------------
    def add(self, record):
        record.validate()
        if record.task_id in self.tasks:
            raise PlanningError(
                f"task {record.task_id} already exists")
        if record.parent is not None \
                and record.parent not in self.tasks:
            raise PlanningError(
                f"task {record.task_id}: parent "
                f"{record.parent!r} not in the registry")
        for dep in record.dependencies:
            if dep not in self.tasks:
                raise PlanningError(
                    f"task {record.task_id}: dependency "
                    f"{dep!r} not in the registry")
        if not record.created_ts:
            record.created_ts = time.time()
        record.history.append(
            {"ts": time.time(), "event": "created",
             "state": record.state})
        self.tasks[record.task_id] = record
        self._save()
        return record

    def get(self, task_id):
        return self.tasks.get(task_id)

    def list(self, state=None, level=None):
        out = list(self.tasks.values())
        if state is not None:
            out = [t for t in out if t.state == state]
        if level is not None:
            out = [t for t in out if t.level == level]
        return sorted(out, key=lambda t: t.task_id)

    def add_evidence(self, task_id, evidence):
        rec = self.tasks.get(task_id)
        if rec is None:
            raise PlanningError(f"unknown task {task_id!r}")
        for item in evidence or []:
            if item not in rec.evidence:
                rec.evidence.append(item)
        rec.history.append({"ts": time.time(),
                            "event": "evidence",
                            "items": list(evidence or [])})
        self._save()
        return rec

    def transition(self, task_id, new_state, evidence=None):
        """Move a task to a new state, enforcing the transition
        map, the dependency gate and the evidence gate for
        done. Raises PlanningError on any refusal; the record
        is unchanged in that case."""
        rec = self.tasks.get(task_id)
        if rec is None:
            raise PlanningError(f"unknown task {task_id!r}")
        if new_state not in TASK_STATES:
            raise PlanningError(
                f"unknown state {new_state!r}")
        allowed = _TRANSITIONS.get(rec.state, ())
        if new_state not in allowed:
            raise PlanningError(
                f"task {task_id}: transition {rec.state} -> "
                f"{new_state} is not allowed")
        if new_state in ("active", "done"):
            unmet = [d for d in rec.dependencies
                     if d not in self.tasks
                     or self.tasks[d].state != "done"]
            if unmet:
                raise PlanningError(
                    f"task {task_id}: dependencies not done: "
                    f"{unmet}")
        supplied = list(rec.evidence)
        for item in evidence or []:
            if item not in supplied:
                supplied.append(item)
        if new_state == "done":
            missing = [e for e in rec.required_evidence
                       if e not in supplied]
            if missing:
                raise PlanningError(
                    f"task {task_id}: cannot mark done; "
                    f"required evidence missing: {missing}")
        old = rec.state
        rec.state = new_state
        rec.evidence = supplied
        rec.history.append({"ts": time.time(),
                            "event": "transition",
                            "from": old, "to": new_state})
        self._save()
        return rec
