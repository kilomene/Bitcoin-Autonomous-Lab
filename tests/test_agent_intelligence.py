#!/usr/bin/env python3
"""Milestone 1 tests for the agent intelligence package
(agent/intelligence/), Master Build Mandate sections 4, 5,
10, 11 and 14.

Pins:

- Permission enforcement at each authority level, including
  the L3 sandbox containment rule and refusal of unknown
  operations.
- Audit append behaviour and failure tolerance (a broken log
  path is counted, never raised).
- Research memory indexing over the REAL registries: a sane
  minimum entry count, honest unparsed accounting, and known
  rejected items (EXP-014 K+W folding, EXP-015 bitslicing)
  found and reported rejected.
- Task registry persistence, dependency gating and the
  evidence gate for done.
- Interface operations against the REAL repository state:
  inspect_status mirrors the actual heartbeat and evidence
  files (or reports not-running honestly), inspect_backends
  returns the shipped dispatch order, candidate verification
  delegates to mining/candidate_verify.py, and start/stop are
  permission-checked but not wired to production.
- Strategy gap arithmetic: 20.6 MH/s is about 0.00412 percent
  of the 500 GH/s objective.
- Optimisation loop transition rules: the rejected-hypothesis
  refusal with citation, the integrate gate refusing an
  incomplete evidence bundle and accepting a complete
  synthetic one, and rollback from monitored.

Run: python3 tests/test_agent_intelligence.py
"""

import json
import os
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from agent.intelligence import Agent
from agent.intelligence.audit import AuditLog
from agent.intelligence.interface import MiningInterface
from agent.intelligence.loop import (CHAIN, INTEGRATED, MONITOR,
                                     OBSERVE, RECORD, ROLLED_BACK,
                                     LoopRefusal, OptimisationLoop)
from agent.intelligence.memory import ResearchMemory
from agent.intelligence.permissions import (
    ACTION_REGISTRY, Level, PermissionChecker, PermissionError)
from agent.intelligence.planning import (PlanningError,
                                         TaskRecord, TaskRegistry)
from agent.intelligence import strategy

CHECKS = 0


def check(cond, msg):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(msg)


def raises(exc_type, fn, msg):
    global CHECKS
    CHECKS += 1
    try:
        fn()
    except exc_type as exc:
        return exc
    raise AssertionError(msg + " (no exception raised)")


def test_permissions():
    l1 = PermissionChecker(granted=Level.L1)
    check(l1.permits("inspect_status"), "L1 may inspect status")
    check(not l1.permits("select_backend"),
          "L1 may not select a backend (L2)")
    raises(PermissionError, lambda: l1.require("select_backend"),
           "L1 select_backend refused")
    raises(PermissionError, lambda: l1.require("start_mining"),
           "L1 start_mining refused")
    l2 = PermissionChecker(granted=Level.L2)
    check(l2.permits("select_backend"), "L2 may select backend")
    check(l2.permits("start_mining"), "L2 may start mining")
    check(not l2.permits("create_experiment"),
          "L2 may not create experiments (L3)")
    sandbox = tempfile.mkdtemp()
    l3 = PermissionChecker(granted=Level.L3, sandbox_root=sandbox)
    check(not l3.permits("create_experiment"),
          "L3 without a sandbox path refused")
    raises(PermissionError, lambda: l3.require("create_experiment"),
           "L3 create_experiment without sandbox refused")
    inside = os.path.join(sandbox, "exp-x")
    check(l3.permits("create_experiment", sandbox_path=inside),
          "L3 inside the sandbox permitted")
    outside = os.path.join(os.path.dirname(sandbox), "elsewhere")
    check(not l3.permits("create_experiment",
                         sandbox_path=outside),
          "L3 outside the sandbox refused")
    raises(PermissionError, lambda: l3.require("no_such_operation"),
           "unknown operation refused")
    spec = ACTION_REGISTRY["start_mining"]
    check(spec.level == Level.L2 and spec.mutates_production,
          "start_mining spec is L2 and marked production-mutating")
    check(not ACTION_REGISTRY["inspect_status"].mutates_production,
          "inspect_status spec is non-mutating")


def test_audit(tmp):
    path = os.path.join(tmp, "audit.jsonl")
    log = AuditLog(path)
    check(log.record("inspect_status", 1, {}, "ok"), "audit write 1")
    check(log.record("select_backend", 2, {"pin": "c"}, "c"),
          "audit write 2")
    records = log.read()
    check(len(records) == 2, "audit reads back both records")
    check(records[0]["operation"] == "inspect_status"
          and records[0]["level"] == 1
          and records[0]["outcome"] == "ok"
          and "ts" in records[0],
          "audit record fields present")
    # Failure tolerance: a path whose parent is a regular file
    # can never be written; record() must count, not raise.
    blocker = os.path.join(tmp, "blocker")
    with open(blocker, "w") as f:
        f.write("x")
    bad = AuditLog(os.path.join(blocker, "audit.jsonl"))
    check(bad.record("inspect_status", 1, {}, "ok") is False,
          "unwritable audit log returns False")
    check(bad.failures == 1, "audit failure counted")
    check(AuditLog(os.path.join(tmp, "missing.jsonl")).read() == [],
          "missing audit log reads as empty")


def test_memory():
    mem = ResearchMemory()
    stats = mem.stats()
    check(stats["indexed"] >= 60,
          f"research memory indexes a sane minimum of entries "
          f"(got {stats['indexed']})")
    check(stats["missing_sources"] == [],
          "all registry sources present")
    e14 = mem.lookup("EXP-014")
    check(e14 is not None and e14.status == "REJECTED",
          "EXP-014 (K+W folding) is indexed as REJECTED")
    e15 = mem.lookup("EXP-015")
    check(e15 is not None and e15.status == "REJECTED",
          "EXP-015 (bitslicing) is indexed as REJECTED")
    hit = mem.was_rejected(["k+w", "folding"])
    check(hit is not None and hit.entry_id == "EXP-014",
          "was_rejected finds EXP-014 for K+W folding")
    hit = mem.was_rejected(["bitslic"])
    check(hit is not None and hit.entry_id == "EXP-015",
          "was_rejected finds EXP-015 for bitslicing")
    check(mem.was_rejected(["zzz-no-such-keyword-zzz"]) is None,
          "was_rejected returns None for an undecided idea")
    h2 = mem.lookup("H-033-02")
    check(h2 is not None and h2.status == "UNDER_INVESTIGATION",
          "H-033-02 (unproven breakthrough) maps to "
          "UNDER_INVESTIGATION, not PROVEN")
    h5 = mem.lookup("H-033-05")
    check(h5 is not None and h5.status == "REJECTED",
          "H-033-05 (E2, refuted by EXP-042) maps to REJECTED")
    results = mem.search(["ternlog"])
    check(len(results) >= 1, "keyword search finds entries")
    return mem


def test_planning(tmp):
    path = os.path.join(tmp, "tasks.json")
    reg = TaskRegistry(path)
    reg.add(TaskRecord(task_id="S1", objective="objective",
                       level="strategic"))
    reg.add(TaskRecord(
        task_id="T1", objective="do the work", parent="S1",
        required_evidence=["test-report", "audit-note"]))
    reg.add(TaskRecord(task_id="T2", objective="dependent",
                       parent="S1", dependencies=["T1"]))
    raises(PlanningError, lambda: reg.transition("T2", "active"),
           "dependency gate blocks active before T1 is done")
    raises(PlanningError, lambda: reg.transition("T1", "done"),
           "planned to done is not an allowed transition")
    reg.transition("T1", "active")
    raises(PlanningError, lambda: reg.transition("T1", "done"),
           "evidence gate blocks done without required evidence")
    raises(PlanningError,
           lambda: reg.transition("T1", "done",
                                  evidence=["test-report"]),
           "partial evidence does not complete the task")
    check(reg.get("T1").state == "active",
          "refused done transition leaves the task active")
    reg.add_evidence("T1", ["test-report", "audit-note"])
    reg.transition("T1", "done")
    check(reg.get("T1").state == "done",
          "full evidence allows done")
    reg.transition("T2", "active")
    check(reg.get("T2").state == "active",
          "dependent task activates once dependency is done")
    reg2 = TaskRegistry(path)
    check(reg2.get("T1") is not None
          and reg2.get("T1").state == "done",
          "task registry persists across instances")
    check(os.path.isfile(path), "task registry file written")


def test_interface(tmp):
    audit = AuditLog(os.path.join(tmp, "iface-audit.jsonl"))
    l1 = PermissionChecker(granted=Level.L1)
    iface_l1 = MiningInterface(l1, audit,
                               local_dir=os.path.join(ROOT, ".local"))
    raises(PermissionError, lambda: iface_l1.select_backend("c"),
           "interface enforces L2 for select_backend")
    raises(PermissionError, lambda: iface_l1.start_mining(),
           "interface enforces L2 for start_mining")

    l2 = PermissionChecker(granted=Level.L2)
    iface = MiningInterface(l2, audit,
                            local_dir=os.path.join(ROOT, ".local"))
    # Status against the real repo state: mirror the files,
    # never fabricate. If the heartbeat exists, fields must
    # match it exactly; if not, the result must say so.
    hb_path = os.path.join(ROOT, ".local", "heartbeat.json")
    status = iface.inspect_status()
    if os.path.isfile(hb_path):
        with open(hb_path) as f:
            hb = json.load(f)
        check(status.autopilot_pid == hb.get("autopilot_pid"),
              "inspect_status autopilot pid matches heartbeat")
        check(status.shares_accepted_total
              == hb.get("shares_accepted_total"),
              "inspect_status shares match heartbeat")
        check(status.miner_state == hb.get("miner_state"),
              "inspect_status miner state matches heartbeat")
        check(status.evidence_accepted is not None,
              "evidence census is reported")
    else:
        check(status.running is False
              and "no heartbeat" in status.note,
              "missing heartbeat reported honestly")
    machine = iface.inspect_machine()
    check(machine.logical_cpus >= 1, "machine reports CPUs")
    check("EPYC" in machine.model_name
          or "Xeon" in machine.model_name
          or machine.model_name != "",
          "machine reports a CPU model from /proc/cpuinfo")
    check(machine.has_avx512f or machine.has_avx2
          or machine.flags == [],
          "machine instruction flags are read, not invented")
    genesis = (bytes.fromhex("01000000") + bytes(32)
               + bytes.fromhex(
                   "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc388"
                   "8a51323a9fb8aa4b1e5e4a")
               + bytes.fromhex("29ab5f49ffff001d1dac2b7c"))
    check(len(genesis) == 80, "genesis header is 80 bytes")
    verdict = iface.verify_candidate_op(genesis, chain="main")
    check(verdict.digests_agree, "genesis header digests agree")
    check(verdict.classification == "block_candidate",
          "genesis header is a block candidate under mainnet "
          "pow limit")
    prob = iface.estimate_probability(20.6e6, 1, seconds=60)
    check(prob.expected_hashes == float(1 << 32),
          "expected hashes at difficulty 1 is 2^32")
    check(0.0 < prob.prob_at_least_one < 1.0,
          "probability is a probability")
    sel = iface.select_backend("hashlib")
    check(sel.eligible and sel.selected == "hashlib",
          "hashlib pin is always eligible")
    raises(NotImplementedError, lambda: iface.start_mining(),
           "start_mining is not wired to production in "
           "Milestone 1")
    cp_none = iface.checkpoint_status()
    check(cp_none.exists is False and cp_none.note,
          "checkpoint_status without a path explains itself")
    from mining.work_checkpoint import WorkCheckpoint
    cp_path = os.path.join(tmp, "work-checkpoint.json")
    WorkCheckpoint(cp_path).record(
        bytes(range(32)), 100, "00" * 32, 1700000000, (0, 64),
        2, 12345, complete=False)
    cp = iface.checkpoint_status(cp_path)
    check(cp.exists and cp.frontier_nonce == 12345
          and cp.frontier_extranonce == 2,
          "checkpoint_status reads the real frontier")
    backends = iface.inspect_backends()
    check(backends.dispatch_order == ["CUDA", "v512dual", "v512",
                                      "shani", "avx2", "C",
                                      "hashlib"],
          "dispatch order is the shipped EXP-039 order")
    check(backends.selected in backends.dispatch_order,
          "selected backend is a real dispatch member")
    records = audit.read()
    ops = {r["operation"] for r in records}
    check("inspect_status" in ops and "verify_candidate" in ops,
          "interface operations write audit records")


def test_strategy(mem):
    report = strategy.gap_report(20.6e6)
    check(abs(report["pct_of_min_target"] - 0.00412) < 1e-5,
          "20.6 MH/s is about 0.00412 percent of 500 GH/s")
    check(abs(report["gap_factor_min"] - 500e9 / 20.6e6) < 1.0,
          "gap factor to 500 GH/s is about 24,272")
    check(report["target_large_hs"] == 140e12,
          "large target is 140 TH/s")
    zero = strategy.gap_report(0)
    check(zero["pct_of_min_target"] == 0.0
          and zero["gap_factor_min"] == float("inf"),
          "zero rate reported honestly")
    first = strategy.next_investigations(mem, limit=5)
    second = strategy.next_investigations(mem, limit=5)
    check([c["entry_id"] for c in first]
          == [c["entry_id"] for c in second],
          "next investigations ordering is deterministic")
    check(all(c["status"] not in ("REJECTED", "INTEGRATED")
              for c in first),
          "next investigations exclude rejected and integrated")
    bottlenecks = strategy.bottleneck_summary()
    check(len(bottlenecks) >= 4
          and all(b["source_exists"] for b in bottlenecks),
          "bottleneck facts cite existing source files")


_ART = "a" * 64
_COMMIT = "18ff4eb070a066dec4424cf9cd4d8282fa9a38b3"


def _vrec(verifier_id, method="differential_reference"):
    """A strict-schema verification record (Prompt 1)."""
    return {"passed": True, "verifier_id": verifier_id,
            "artifact_sha256": _ART, "source_commit": _COMMIT,
            "verification_method": method,
            "timestamp": "2026-11-15T00:00:00Z"}


def _signed_independent():
    from agent.intelligence import verifier
    key = verifier.load_key()
    return verifier.sign_record(
        _vrec(verifier.VERIFIER_ID,
              method="independent_recompute"), key)


def test_loop(mem):
    loop = OptimisationLoop(memory=mem)
    rec = loop.new_record("L-REJ", "fold K+W again",
                          keywords=["k+w", "folding"],
                          implementation_author="agent-a")
    loop.advance(rec)
    check(rec.state == "hypothesise", "loop advances to hypothesise")
    exc = raises(LoopRefusal, lambda: loop.advance(rec),
                 "rejected hypothesis cannot leave hypothesise")
    check(exc.citation is not None
          and exc.citation["entry_id"] == "EXP-014",
          "rejection refusal carries the EXP-014 citation")
    check(rec.state == "hypothesise",
          "refused transition leaves the state unchanged")

    rec2 = loop.new_record(
        "L-OK", "a genuinely new layout idea",
        keywords=["zzz", "novel", "undecided", "layout"],
        implementation_author="agent-a", performance_claim=True)
    while rec2.state != RECORD:
        loop.advance(rec2)
    exc = raises(LoopRefusal, lambda: loop.advance(rec2),
                 "integrate gate refuses an empty evidence bundle")
    check("correctness pass" in exc.missing,
          "integrate refusal names the missing correctness pass")
    rec2.evidence.update({
        "correctness": _vrec("agent-a"),
        "differential": _vrec("agent-a"),
        "independent_verification": _vrec("agent-a")})
    exc = raises(LoopRefusal, lambda: loop.advance(rec2),
                 "self-verification is not independent")
    check(any("other" in m for m in exc.missing),
          "integrate refusal names the independence failure")
    rec2.evidence["independent_verification"] = \
        _signed_independent()
    exc = raises(LoopRefusal, lambda: loop.advance(rec2),
                 "performance claim without EXP-017 verdict "
                 "is refused")
    check(any("EXP-017" in m for m in exc.missing),
          "integrate refusal names the missing EXP-017 verdict")
    rec2.evidence["exp017_verdict"] = {
        "sessions": 3, "pooled_ratio": 1.40,
        "ci_low": 0.24, "ci_high": 0.58}
    loop.advance(rec2)
    check(rec2.state == INTEGRATED,
          "complete evidence bundle passes the integrate gate")
    loop.advance(rec2)
    check(rec2.state == MONITOR, "integrated advances to monitor")
    loop.rollback(rec2, reason="test rollback")
    check(rec2.state == ROLLED_BACK,
          "rollback from monitor is always available")
    check(CHAIN[0] == OBSERVE and CHAIN[-1] == MONITOR,
          "chain spans observe to monitor")


def test_facade(tmp):
    agent = Agent(local_dir=tmp,
                  audit_path=os.path.join(tmp, "a.jsonl"),
                  tasks_path=os.path.join(tmp, "t.json"),
                  sandbox_root=os.path.join(tmp, "sandbox"))
    status = agent.status()
    check(status.running is False
          and "no heartbeat" in status.note,
          "facade in an empty local dir reports not running, "
          "honestly")
    report = agent.gap_report(20.6e6)
    check(abs(report["pct_of_min_target"] - 0.00412) < 1e-5,
          "facade gap report matches the strategy arithmetic")
    check(agent.checker.permits(
        "create_experiment",
        sandbox_path=os.path.join(tmp, "sandbox", "e1")),
        "facade grants L3 inside its sandbox only")
    check(not agent.checker.permits(
        "create_experiment", sandbox_path="/etc/e1"),
        "facade refuses L3 outside its sandbox")


def main():
    tmp = tempfile.mkdtemp(prefix="agent-intelligence-")
    test_permissions()
    test_audit(tmp)
    mem = test_memory()
    test_planning(tmp)
    test_interface(tmp)
    test_strategy(mem)
    test_loop(mem)
    test_facade(tmp)
    print(f"ALL AGENT INTELLIGENCE TESTS PASSED ({CHECKS} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
