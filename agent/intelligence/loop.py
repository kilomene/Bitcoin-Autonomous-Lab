"""The autonomous optimisation cycle as an explicit state
machine (Master Build Mandate sections 5 and 5.2, Milestone 3
shape delivered as the Milestone 1 foundation).

The cycle, in order:

    observe, hypothesise, check prior research, analyse
    source, derive change, check mathematical correctness,
    create isolated implementation, run correctness tests,
    run controlled measurement, compare against baseline,
    independent verification, block acceptance, record
    evidence, integrate gate, monitor, rollback.

This module is a workflow engine over records. It does not
edit production code, run benchmarks or verify candidates
itself; it enforces the ORDER of the work and the GATES
between states, and keeps the evidence bundle each gate
inspected. Two gates carry the mandate's hard rules:

- Rejected-hypothesis gate (hypothesise to check prior
  research): if the hypothesis keywords all match a REJECTED
  research memory entry, the transition is refused and the
  refusal carries the rejection citation. The agent must not
  re-propose what the record has already decided.
- Integrate gate (record evidence to integrated): the
  evidence bundle must contain a correctness pass, a
  differential pass, an independent verification record whose
  author differs from the implementation author, and, when a
  performance claim is made, an EXP-017 style statistical
  verdict: at least 3 sessions, a pooled ratio, and a
  confidence interval for the relative improvement (pooled
  ratio minus 1) lying entirely above 0. An incomplete bundle
  is refused with the missing items named.

Rollback is always available from the integrated and
monitored states.
"""

import time
from dataclasses import dataclass, field

OBSERVE = "observe"
HYPOTHESISE = "hypothesise"
CHECK_PRIOR = "check_prior_research"
ANALYSE_SOURCE = "analyse_source"
DERIVE = "derive_change"
CORRECTNESS = "mathematical_correctness"
ISOLATED = "isolated_implementation"
CORRECTNESS_TESTS = "correctness_tests"
MEASUREMENT = "controlled_measurement"
COMPARE = "compare_baseline"
INDEPENDENT = "independent_verification"
BLOCK_ACCEPTANCE = "block_acceptance"
RECORD = "record_evidence"
INTEGRATED = "integrated"
MONITOR = "monitor"
ROLLED_BACK = "rolled_back"
FAILED = "failed"

CHAIN = [OBSERVE, HYPOTHESISE, CHECK_PRIOR, ANALYSE_SOURCE,
         DERIVE, CORRECTNESS, ISOLATED, CORRECTNESS_TESTS,
         MEASUREMENT, COMPARE, INDEPENDENT, BLOCK_ACCEPTANCE,
         RECORD, INTEGRATED, MONITOR]
TERMINAL = (ROLLED_BACK, FAILED)


class LoopRefusal(Exception):
    """A transition was refused. missing names the evidence
    items an integrate attempt lacked; citation carries the
    rejected-memory entry for a rejected-hypothesis refusal."""

    def __init__(self, message, missing=None, citation=None):
        super().__init__(message)
        self.missing = list(missing or [])
        self.citation = citation


@dataclass
class LoopRecord:
    loop_id: str
    hypothesis: str
    keywords: list = field(default_factory=list)
    implementation_author: str = ""
    performance_claim: bool = False
    evidence: dict = field(default_factory=dict)
    state: str = OBSERVE
    history: list = field(default_factory=list)


def _passed(value):
    """An evidence item counts as passed when it is True or a
    dict with a truthy pass/passed/ok field."""
    if value is True:
        return True
    if isinstance(value, dict):
        for key in ("pass", "passed", "ok", "result"):
            if key in value:
                return bool(value[key]) and \
                    value[key] != "fail"
    return False


def validate_integrate_evidence(record):
    """The list of missing or inadequate evidence items for
    the integrate gate; empty means the gate passes."""
    missing = []
    ev = record.evidence or {}
    if not _passed(ev.get("correctness")):
        missing.append("correctness pass")
    if not _passed(ev.get("differential")):
        missing.append("differential pass")
    indep = ev.get("independent_verification")
    if not isinstance(indep, dict) or not indep.get("author"):
        missing.append("independent verification record")
    elif indep.get("author") == record.implementation_author:
        missing.append(
            "independent verification by an author other "
            "than the implementation author")
    elif not _passed(indep):
        missing.append("independent verification pass")
    if record.performance_claim:
        verdict = ev.get("exp017_verdict")
        if not isinstance(verdict, dict):
            missing.append("EXP-017 statistical verdict")
        else:
            sessions = verdict.get("sessions")
            ratio = verdict.get("pooled_ratio")
            ci_low = verdict.get("ci_low")
            ci_high = verdict.get("ci_high")
            if not isinstance(sessions, int) or sessions < 3:
                missing.append(
                    "EXP-017 verdict with at least 3 sessions")
            if not isinstance(ratio, (int, float)) \
                    or ratio <= 1.0:
                missing.append(
                    "EXP-017 pooled ratio above 1")
            if not isinstance(ci_low, (int, float)) \
                    or not isinstance(ci_high, (int, float)) \
                    or ci_low <= 0 or ci_high < ci_low:
                missing.append(
                    "EXP-017 confidence interval for the "
                    "relative improvement entirely above 0")
    return missing


class OptimisationLoop:
    """State machine over LoopRecord objects.

    memory: a memory.ResearchMemory used by the rejected
    hypothesis gate; may be None, in which case that gate
    cannot fire and says so in the record history.
    checker and audit: optional package wiring; when a checker
    is supplied, advance and rollback require the L2
    loop_advance operation.
    """

    def __init__(self, memory=None, checker=None, audit=None):
        self.memory = memory
        self.checker = checker
        self.audit = audit

    def new_record(self, loop_id, hypothesis, keywords=None,
                   implementation_author="",
                   performance_claim=False):
        rec = LoopRecord(
            loop_id=loop_id, hypothesis=hypothesis,
            keywords=list(keywords or []),
            implementation_author=implementation_author,
            performance_claim=bool(performance_claim))
        rec.history.append({"ts": time.time(), "event": "created",
                            "state": rec.state})
        return rec

    def _gate_permission(self, rec, action):
        if self.checker is not None:
            self.checker.require("loop_advance")

    def _note(self, rec, event, **extra):
        entry = {"ts": time.time(), "event": event,
                 "state": rec.state}
        entry.update(extra)
        rec.history.append(entry)
        if self.audit is not None:
            self.audit.record(
                "loop_advance", 2,
                {"loop_id": rec.loop_id, "event": event},
                event)

    def advance(self, record):
        """Move one state forward, enforcing the gates.
        Raises LoopRefusal on a gate failure; the record is
        unchanged in that case."""
        self._gate_permission(record, "advance")
        if record.state in TERMINAL:
            raise LoopRefusal(
                f"loop {record.loop_id} is in terminal state "
                f"{record.state}")
        if record.state == MONITOR:
            raise LoopRefusal(
                f"loop {record.loop_id} is at monitor, the "
                "last chain state; roll back or leave it "
                "monitored")
        idx = CHAIN.index(record.state)
        nxt = CHAIN[idx + 1]
        if record.state == HYPOTHESISE and nxt == CHECK_PRIOR:
            self._check_not_rejected(record)
        if record.state == RECORD and nxt == INTEGRATED:
            missing = validate_integrate_evidence(record)
            if missing:
                raise LoopRefusal(
                    f"loop {record.loop_id}: integrate gate "
                    f"refused; evidence bundle incomplete",
                    missing=missing)
        old = record.state
        record.state = nxt
        self._note(record, "advance", **{"from": old, "to": nxt})
        return record

    def _check_not_rejected(self, record):
        if self.memory is None:
            record.history.append(
                {"ts": time.time(),
                 "event": "prior_check_skipped_no_memory"})
            return
        if not record.keywords:
            return
        hit = self.memory.was_rejected(record.keywords)
        if hit is not None:
            citation = {"entry_id": hit.entry_id,
                        "title": hit.title,
                        "status": hit.status,
                        "source": hit.source}
            raise LoopRefusal(
                f"loop {record.loop_id}: hypothesis matches "
                f"rejected research memory entry "
                f"{hit.entry_id}; re-proposing a rejected "
                "idea is refused",
                citation=citation)

    def rollback(self, record, reason=""):
        """Always available from integrated and monitored
        states; refused elsewhere so a rollback claim always
        refers to something that was integrated."""
        self._gate_permission(record, "rollback")
        if record.state not in (INTEGRATED, MONITOR):
            raise LoopRefusal(
                f"loop {record.loop_id}: rollback is available "
                f"from integrated or monitor, not from "
                f"{record.state}")
        old = record.state
        record.state = ROLLED_BACK
        self._note(record, "rollback",
                   **{"from": old, "reason": reason})
        return record

    def fail(self, record, reason=""):
        if record.state in TERMINAL:
            raise LoopRefusal(
                f"loop {record.loop_id} is already terminal")
        old = record.state
        record.state = FAILED
        self._note(record, "failed",
                   **{"from": old, "reason": reason})
        return record
