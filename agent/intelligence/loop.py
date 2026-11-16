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

import math
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime

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
    # Optional expected binding (Prompt 1): when set, every
    # evidence record in the bundle must carry exactly this
    # artifact hash and source commit.
    artifact_sha256: str = ""
    source_commit: str = ""


# Strict evidence schema (Autonomous Mining Brain, Prompt 1,
# item A). An evidence item is a verification record: a dict
# with passed exactly Boolean True, a non-empty verifier_id, a
# 64-char lowercase hex artifact_sha256, a non-empty
# source_commit, a verification_method from this closed
# allowlist, and an ISO-8601 parseable timestamp. Anything
# else fails closed. Truthiness is never consulted: the string
# "false", the string "true" and the integer 1 are all refused.
ALLOWED_VERIFICATION_METHODS = frozenset({
    "differential_reference",
    "independent_recompute",
    "statistical_replication",
    "chain_acceptance",
})
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _is_number(value):
    return isinstance(value, (int, float)) and \
        not isinstance(value, bool)


def _valid_timestamp(value):
    if not isinstance(value, str) or not value:
        return False
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        datetime.fromisoformat(text)
        return True
    except ValueError:
        return False


def validate_evidence_record(value):
    """Strict schema check for one verification record.
    Returns a list of problems; empty means the record is
    schema-valid AND passed is Boolean True."""
    if not isinstance(value, dict):
        return ["record is not a dict"]
    problems = []
    if "passed" not in value:
        problems.append("passed field missing")
    elif type(value["passed"]) is not bool:
        problems.append("passed is not a Boolean")
    elif value["passed"] is not True:
        problems.append("passed is not True")
    vid = value.get("verifier_id")
    if not isinstance(vid, str) or not vid.strip():
        problems.append("verifier_id missing or empty")
    art = value.get("artifact_sha256")
    if not isinstance(art, str) or not _HEX64.match(art):
        problems.append(
            "artifact_sha256 is not a 64-char lowercase hex "
            "string")
    commit = value.get("source_commit")
    if not isinstance(commit, str) or not commit.strip():
        problems.append("source_commit missing or empty")
    method = value.get("verification_method")
    if method not in ALLOWED_VERIFICATION_METHODS:
        problems.append(
            f"verification_method {method!r} not in the "
            "allowlist")
    if not _valid_timestamp(value.get("timestamp")):
        problems.append("timestamp is not ISO-8601 parseable")
    return problems


def _passed(value):
    """Strict form: True only for a schema-valid verification
    record whose passed field is Boolean True. (Prompt 1
    replaced the previous truthiness check, under which a
    dict like {"result": "false"} passed.)"""
    return isinstance(value, dict) and \
        not validate_evidence_record(value)


def _default_verifier_key_path():
    from . import verifier as _verifier
    return _verifier.default_key_path()


def _verify_independent_signature(record, key_path):
    """Verify the HMAC signature on an independent
    verification record against the verifier key file.
    Returns a problem string, or None when the signature is
    valid."""
    from . import verifier as _verifier
    path = key_path or _default_verifier_key_path()
    if not os.path.isfile(path):
        return ("independent verification signature cannot be "
                "verified: verifier key file unavailable")
    try:
        key = _verifier.load_key(path)
    except OSError as exc:
        return (f"independent verification signature cannot "
                f"be verified: verifier key unreadable ({exc})")
    if not _verifier.verify_signature(record, key):
        return ("independent verification signature invalid "
                "or missing: the record was not produced by "
                "the independent verifier service")
    return None


def validate_integrate_evidence(record, verifier_key_path=None):
    """The list of missing or inadequate evidence items for
    the integrate gate; empty means the gate passes.

    Strict schema (Prompt 1): correctness, differential and
    independent verification must each be a valid verification
    record (see validate_evidence_record). The independent
    record must additionally carry a verifier_id different
    from the implementation author and a valid HMAC signature
    from the verifier service (see verifier.py); an unsigned
    or author-signed record is refused. All records in the
    bundle must bind the same artifact hash and source commit,
    and must match the record's expected binding when one is
    set. The EXP-017 verdict rejects NaN and infinity anywhere
    and malformed confidence intervals."""
    missing = []
    ev = record.evidence or {}
    for key, label in (("correctness", "correctness pass"),
                       ("differential", "differential pass")):
        item = ev.get(key)
        if item is None:
            missing.append(label)
        else:
            problems = validate_evidence_record(item)
            if problems:
                missing.append(
                    f"{label} (invalid verification record: "
                    f"{'; '.join(problems)})")
    indep = ev.get("independent_verification")
    if not isinstance(indep, dict):
        missing.append("independent verification record")
    else:
        problems = validate_evidence_record(indep)
        if problems:
            missing.append(
                "independent verification record (invalid: "
                + "; ".join(problems) + ")")
        elif indep.get("verifier_id") == \
                record.implementation_author:
            missing.append(
                "independent verification by an author other "
                "than the implementation author")
        else:
            sig_problem = _verify_independent_signature(
                indep, verifier_key_path)
            if sig_problem:
                missing.append(sig_problem)
    # Bundle binding: every present record must agree on the
    # artifact and the source commit, and must match the
    # expected binding when the loop record carries one.
    bound = []
    for key in ("correctness", "differential",
                "independent_verification"):
        item = ev.get(key)
        if isinstance(item, dict) and \
                isinstance(item.get("artifact_sha256"), str) \
                and isinstance(item.get("source_commit"), str):
            bound.append((item["artifact_sha256"],
                          item["source_commit"]))
    if bound and len(set(bound)) > 1:
        missing.append(
            "evidence binding mismatch: verification records "
            "disagree on artifact_sha256 or source_commit")
    expected_art = getattr(record, "artifact_sha256", "") or ""
    expected_commit = getattr(record, "source_commit", "") or ""
    if bound and expected_art and \
            any(a != expected_art for a, _c in bound):
        missing.append(
            "evidence bound to a different artifact_sha256 "
            "than the loop record expects")
    if bound and expected_commit and \
            any(c != expected_commit for _a, c in bound):
        missing.append(
            "evidence bound to a different source_commit "
            "than the loop record expects")
    if record.performance_claim:
        verdict = ev.get("exp017_verdict")
        if not isinstance(verdict, dict):
            missing.append("EXP-017 statistical verdict")
        else:
            sessions = verdict.get("sessions")
            ratio = verdict.get("pooled_ratio")
            ci_low = verdict.get("ci_low")
            ci_high = verdict.get("ci_high")
            if type(sessions) is not int or sessions < 3:
                missing.append(
                    "EXP-017 verdict with at least 3 sessions")
            if not _is_number(ratio) \
                    or not math.isfinite(ratio) or ratio <= 1.0:
                missing.append(
                    "EXP-017 pooled ratio above 1 (finite "
                    "number required; NaN and infinity are "
                    "rejected)")
            if not _is_number(ci_low) \
                    or not _is_number(ci_high) \
                    or not math.isfinite(ci_low) \
                    or not math.isfinite(ci_high) \
                    or ci_low <= 0 or ci_high < ci_low:
                missing.append(
                    "EXP-017 confidence interval for the "
                    "relative improvement entirely above 0 "
                    "(finite bounds, lower not above upper)")
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

    def __init__(self, memory=None, checker=None, audit=None,
                 verifier_key_path=None):
        self.memory = memory
        self.checker = checker
        self.audit = audit
        self.verifier_key_path = verifier_key_path

    def new_record(self, loop_id, hypothesis, keywords=None,
                   implementation_author="",
                   performance_claim=False,
                   artifact_sha256="", source_commit=""):
        rec = LoopRecord(
            loop_id=loop_id, hypothesis=hypothesis,
            keywords=list(keywords or []),
            implementation_author=implementation_author,
            performance_claim=bool(performance_claim),
            artifact_sha256=artifact_sha256 or "",
            source_commit=source_commit or "")
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
            missing = validate_integrate_evidence(
                record, verifier_key_path=self.verifier_key_path)
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
