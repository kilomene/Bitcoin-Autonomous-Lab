"""Resource registry and exact work assignment (Master
Build Mandate section 7 and 14, Milestone 5).

The mandate's order is explicit: first establish what
resources actually exist, on one machine, before any
distributed claim. This module is that local registry. It
records workers and their machines, hands out deterministic
non-overlapping nonce assignments per (job identity,
extranonce space), tracks batch progress honestly, and
computes unique coverage as a union, never as a sum of
overlapping counters.

Exactness rules (mandate sections 7.1 and 10.1):

- assign refuses any overlap with an existing active or
  completed assignment sharing the same job identity and
  extranonce space, and refuses a nonce end above 2^32.
- An assignment is marked completed ONLY when its reported
  completed batch count equals its total batch count. A
  partial report records progress and leaves the assignment
  active; unfinished work is never recorded as done.
- Repeated computations are stored as their own counter on
  the assignment. They are never added to unique coverage.
- reassign moves an unfinished assignment to another
  worker, preserving its completed-batch progress as the
  frontier the new worker continues from. The moved part is
  not marked complete by the move.
- unique_coverage is the size of the UNION of completed
  ranges and the completed prefixes of active ranges (batch
  progress covers a range from its start in order, the
  EXP-038 frontier model), computed by interval merging.

Persistence is a single JSON document written atomically
(temp file plus os.replace), so a crash mid-write cannot
leave a torn registry. The path is injectable; the default
is .local/agent-resources.json.

Scope limit, stated plainly: this is a single-machine,
single-process registry. It makes no multi-machine claim:
no network protocol, no cross-machine latency or scaling
property is implemented or implied (EXP-043 register).
"""

import json
import os
import time
import uuid

_REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".."))
_LOCAL = os.path.join(_REPO_ROOT, ".local")
NONCE_SPACE = 1 << 32
SCHEMA_VERSION = 1


class AssignmentError(Exception):
    """An assignment request was refused (overlap, overflow,
    unknown worker or assignment, invalid transition)."""


def _space_key(sp):
    """Canonical comparable form of an extranonce
    space value: (first, count) pairs and plain ints both
    map to a tuple; anything else falls back to its string
    form."""
    if isinstance(sp, (list, tuple)) and len(sp) == 2:
        return (int(sp[0]), int(sp[1]))
    if isinstance(sp, int):
        return (sp,)
    return (str(sp),)


def _union_size(intervals):
    """Size of the union of [start, end) intervals."""
    total = 0
    cur_s = cur_e = None
    for s, e in sorted(intervals):
        if cur_s is None:
            cur_s, cur_e = s, e
        elif s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
    if cur_s is not None:
        total += cur_e - cur_s
    return total


class ResourceRegistry:
    """Workers, exact assignments, progress and coverage."""

    def __init__(self, path=None):
        self.path = path or os.path.join(
            _LOCAL, "agent-resources.json")
        self.workers = {}
        self.assignments = {}
        self._load()

    # Persistence ----------------------------------------------
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            self.workers = data.get("workers") or {}
            self.assignments = data.get("assignments") or {}

    def _save(self):
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": SCHEMA_VERSION,
                       "workers": self.workers,
                       "assignments": self.assignments},
                      f, indent=1, sort_keys=True)
        os.replace(tmp, self.path)

    # Workers ----------------------------------------------------
    def register_worker(self, worker_id, machine_id, cpu_model,
                        effective_cpus, instructions, backend):
        """Register (or refresh) one worker. instructions is
        the instruction-set list the worker's host reports."""
        self.workers[worker_id] = {
            "worker_id": worker_id,
            "machine_id": machine_id,
            "cpu_model": cpu_model,
            "effective_cpus": effective_cpus,
            "instructions": list(instructions),
            "backend": backend,
            "registered_ts": time.time(),
            "last_heartbeat": None,
        }
        self._save()
        return self.workers[worker_id]

    def heartbeat(self, worker_id):
        """Stamp a worker's liveness."""
        worker = self.workers.get(worker_id)
        if worker is None:
            raise AssignmentError(
                f"heartbeat for unknown worker {worker_id!r}")
        worker["last_heartbeat"] = time.time()
        self._save()
        return worker["last_heartbeat"]

    # Assignments --------------------------------------------------
    def assign(self, worker_id, job_identity, extranonce_space,
               nonce_start, nonce_end):
        """Hand out one exact, non-overlapping assignment.

        Refuses: unknown worker; an empty or inverted range;
        a nonce end above 2^32; and any overlap with an
        active or completed assignment sharing the same job
        identity and extranonce space.
        """
        if worker_id not in self.workers:
            raise AssignmentError(
                f"assign to unknown worker {worker_id!r}")
        nonce_start = int(nonce_start)
        nonce_end = int(nonce_end)
        if nonce_end > NONCE_SPACE:
            raise AssignmentError(
                f"nonce_end {nonce_end} exceeds the nonce "
                f"space 2^32 ({NONCE_SPACE})")
        if nonce_start < 0 or nonce_end <= nonce_start:
            raise AssignmentError(
                f"invalid nonce range [{nonce_start}, "
                f"{nonce_end})")
        key = _space_key(extranonce_space)
        for other in self.assignments.values():
            if other["job_identity"] != job_identity:
                continue
            if _space_key(other["extranonce_space"]) != key:
                continue
            if other["state"] not in ("active", "completed"):
                continue
            if nonce_start < other["nonce_end"] and \
                    other["nonce_start"] < nonce_end:
                raise AssignmentError(
                    f"range [{nonce_start}, {nonce_end}) "
                    f"overlaps assignment "
                    f"{other['assignment_id']} "
                    f"[{other['nonce_start']}, "
                    f"{other['nonce_end']}) for the same job "
                    "identity and extranonce space")
        assignment_id = uuid.uuid4().hex
        record = {
            "assignment_id": assignment_id,
            "worker_id": worker_id,
            "job_identity": job_identity,
            "extranonce_space": (list(extranonce_space)
                                 if isinstance(extranonce_space,
                                               (list, tuple))
                                 else extranonce_space),
            "nonce_start": nonce_start,
            "nonce_end": nonce_end,
            "state": "active",
            "batches_completed": 0,
            "batches_total": None,
            "repeated_computations": 0,
            "created_ts": time.time(),
            "completed_ts": None,
            "reassignments": [],
        }
        self.assignments[assignment_id] = record
        self._save()
        return record

    def complete(self, assignment_id, batches_completed,
                 batches_total, repeated_computations=0):
        """Report batch progress on an assignment.

        Marks the assignment completed ONLY when
        batches_completed equals batches_total. Otherwise
        records the progress and leaves it active.
        repeated_computations accumulates into its own
        counter, never into unique coverage.
        """
        record = self.assignments.get(assignment_id)
        if record is None:
            raise AssignmentError(
                f"unknown assignment {assignment_id!r}")
        if record["state"] == "completed":
            raise AssignmentError(
                f"assignment {assignment_id} is already "
                "completed; progress on finished work is "
                "refused")
        batches_completed = int(batches_completed)
        batches_total = int(batches_total)
        if batches_total <= 0 or batches_completed < 0 or \
                batches_completed > batches_total:
            raise AssignmentError(
                f"invalid batch progress {batches_completed}/"
                f"{batches_total}")
        if batches_completed < record["batches_completed"]:
            raise AssignmentError(
                "batch progress may not move backwards "
                f"({batches_completed} < "
                f"{record['batches_completed']})")
        record["batches_completed"] = batches_completed
        record["batches_total"] = batches_total
        record["repeated_computations"] += int(
            repeated_computations)
        if batches_completed == batches_total:
            record["state"] = "completed"
            record["completed_ts"] = time.time()
        self._save()
        return record

    def unfinished_for(self, worker_id):
        """The worker's active (unfinished) assignments."""
        return [a for a in self.assignments.values()
                if a["worker_id"] == worker_id
                and a["state"] == "active"]

    def reassign(self, assignment_id, new_worker_id):
        """Move an unfinished assignment to another worker.

        The completed-batch progress is preserved as the new
        worker's frontier; the move itself completes nothing.
        Completed assignments cannot be reassigned.
        """
        record = self.assignments.get(assignment_id)
        if record is None:
            raise AssignmentError(
                f"unknown assignment {assignment_id!r}")
        if new_worker_id not in self.workers:
            raise AssignmentError(
                f"reassign to unknown worker "
                f"{new_worker_id!r}")
        if record["state"] != "active":
            raise AssignmentError(
                f"assignment {assignment_id} is "
                f"{record['state']}; only active assignments "
                "can be reassigned")
        record["reassignments"].append({
            "from": record["worker_id"], "to": new_worker_id,
            "ts": time.time(),
            "batches_completed_at_move":
                record["batches_completed"],
            "batches_total_at_move": record["batches_total"]})
        record["worker_id"] = new_worker_id
        self._save()
        return record

    # Coverage -----------------------------------------------------
    def unique_coverage(self, job_identity):
        """Unique nonce coverage for one job identity.

        Method: interval union over (a) every completed
        assignment's full range and (b) every active
        assignment's completed prefix, where the prefix
        length is floor(range length x batches_completed /
        batches_total) because batch progress covers a range
        from its start in order (the EXP-038 frontier
        model). Repeated computations are excluded by
        construction: they are a separate counter and never
        enter an interval.
        """
        intervals = []
        repeated = 0
        for a in self.assignments.values():
            if a["job_identity"] != job_identity:
                continue
            repeated += a["repeated_computations"]
            if a["state"] == "completed":
                intervals.append(
                    (a["nonce_start"], a["nonce_end"]))
            elif a["state"] == "active" and \
                    a["batches_total"]:
                length = a["nonce_end"] - a["nonce_start"]
                done = length * a["batches_completed"] // \
                    a["batches_total"]
                if done > 0:
                    intervals.append(
                        (a["nonce_start"],
                         a["nonce_start"] + done))
        return {
            "job_identity": job_identity,
            "unique_nonces": _union_size(intervals),
            "intervals": len(intervals),
            "repeated_computations_excluded": repeated,
            "method": (
                "union of completed ranges plus completed "
                "prefixes of active ranges (batch progress "
                "covers a range from its start in order), "
                "computed by interval merging; repeated "
                "computations are a separate counter and "
                "never enter the union"),
        }
