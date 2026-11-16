#!/usr/bin/env python3
"""Milestones 3, 4 and 5 tests for the agent intelligence
package (agent/intelligence/experiments.py, scheduler.py,
resources.py), Master Build Mandate sections 5, 6.3, 7 and
14.

Pins:

- Experiment runner: a hypothesis matching rejected research
  memory (EXP-014, K+W folding) is refused at the hypothesise
  gate with the citation; sandbox containment refuses
  escapes; shell strings are refused as commands; a real tiny
  experiment runs end to end and the integrate gate refuses
  its incomplete evidence bundle (naming the missing
  independent verification) and accepts a complete synthetic
  one.
- Scheduler: the workload runs through the REAL ComputeEngine
  search path on the C tier with a positive measured rate and
  an exact attempted count; winner ordering is pinned on
  synthetic tables; a fresh cache entry is served instead of
  re-measuring. The full bake-off is deliberately NOT run
  inside this suite (it is a demonstration, run separately),
  so the suite stays fast.
- Resources: overlap refusal, nonce overflow refusal,
  partial completion staying active with progress recorded,
  reassignment preserving progress, repeated computations
  kept out of unique coverage, persistence across instances,
  and a randomised campaign (240 trials) with injected worker
  deaths and reassignments proving completed coverage is
  pairwise disjoint and union-consistent with an independent
  model.

Run: python3 tests/test_agent_operations.py
"""

import json
import os
import random
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from agent.intelligence import Agent
from agent.intelligence.experiments import (
    ExperimentRunner, SandboxEscape)
from agent.intelligence.loop import INTEGRATED, LoopRefusal
from agent.intelligence.resources import (
    AssignmentError, ResourceRegistry)
from agent.intelligence.scheduler import Scheduler, pick_winner

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


def make_agent(tmp):
    return Agent(local_dir=tmp,
                 audit_path=os.path.join(tmp, "a.jsonl"),
                 tasks_path=os.path.join(tmp, "t.json"),
                 sandbox_root=os.path.join(tmp, "sandbox"))


# Experiments ----------------------------------------------------

def test_experiment_refusals(tmp):
    agent = make_agent(tmp)
    runner = ExperimentRunner(agent)
    exc = raises(
        LoopRefusal,
        lambda: runner.create_experiment(
            "fold the K+W constants again",
            ["k+w", "folding"], "agent-test"),
        "rejected hypothesis refused at creation")
    check(exc.citation is not None
          and exc.citation["entry_id"] == "EXP-014",
          "refusal carries the EXP-014 citation")
    record, sandbox = runner.create_experiment(
        "sandbox plumbing probe",
        ["zzz-novel-m345", "sandbox", "plumbing"], "agent-test")
    check(os.path.isdir(sandbox), "sandbox directory created")
    inside = runner.target_path(record, "sub/file.txt")
    check(inside.startswith(os.path.realpath(sandbox)),
          "target_path resolves inside the sandbox")
    raises(SandboxEscape,
           lambda: runner.target_path(record, "../escape.txt"),
           "parent traversal escape refused")
    raises(SandboxEscape,
           lambda: runner.target_path(record, "/etc/passwd"),
           "absolute path escape refused")
    raises(TypeError,
           lambda: runner.run_command(record, "echo hi"),
           "shell string command refused")
    return runner, record


def _vrec(verifier_id, artifact_sha, method="differential_reference"):
    """A strict-schema verification record (Prompt 1)."""
    from agent.intelligence.experiments import CURRENT_SOURCE_COMMIT
    return {"passed": True, "verifier_id": verifier_id,
            "artifact_sha256": artifact_sha,
            "source_commit": CURRENT_SOURCE_COMMIT,
            "verification_method": method,
            "timestamp": "2026-11-15T00:00:00Z"}


def test_experiment_end_to_end(runner, record):
    import hashlib
    from agent.intelligence import verifier
    from agent.intelligence.experiments import CURRENT_SOURCE_COMMIT
    artifact_path = runner.write_file(
        record, "artifact.bin", "tiny experiment artifact\n")
    with open(artifact_path, "rb") as f:
        artifact_sha = hashlib.sha256(f.read()).hexdigest()
    crec = _vrec("agent-test", artifact_sha)
    payload = {"correctness": crec, "differential": dict(crec),
               "exp017": None}
    code = ("import json;"
            f"json.dump({payload!r}, open('evidence.json', 'w'));"
            "print('evidence written')")
    result = runner.run_command(
        record, [sys.executable, "-c", code], timeout_s=60)
    check(result["exit_code"] == 0, "tiny experiment exits 0")
    check(result["wall_s"] >= 0, "wall time recorded")
    check(result["termination_reason"] == "exit",
          "sandbox termination reason recorded")
    sandbox = runner.sandbox_of(record)
    with open(os.path.join(sandbox,
                           result["stdout_file"])) as f:
        check("evidence written" in f.read(),
              "stdout captured to the sandbox evidence file")
    hist = [h for h in record.history
            if h.get("event") == "run_command"]
    check(len(hist) == 1 and hist[0]["exit_code"] == 0,
          "run recorded in the loop record history")
    bundle = runner.assemble_evidence(record)
    check(bundle["correctness"]["passed"] is True
          and bundle["differential"]["passed"] is True,
          "evidence bundle carries the strict records")
    check("independent_verification" not in bundle,
          "absent verifier assembles to no verification record")
    runner.walk_to_record(record)
    verdict = runner.attempt_integrate(record)
    check(verdict["integrated"] is False,
          "integrate gate refuses the incomplete bundle")
    check(any("independent verification" in m
              for m in verdict["missing"]),
          "refusal names the missing independent verification")
    signed = verifier.request_verification(
        artifact_path, CURRENT_SOURCE_COMMIT,
        "independent_recompute",
        key_path=runner.agent.verifier_key_path)
    check(signed["passed"] is True
          and signed["artifact_sha256"] == artifact_sha,
          "verifier service returns a signed passing record")
    runner.write_file(record, "evidence-b.json", json.dumps({
        "correctness": crec, "differential": dict(crec),
        "independent_verification": signed, "exp017": None}))
    bundle = runner.assemble_evidence(record)
    check(bundle["independent_verification"]["verifier_id"]
          == verifier.VERIFIER_ID,
          "second evidence file supplies the verifier record")
    verdict = runner.attempt_integrate(record)
    check(verdict["integrated"] is True
          and record.state == INTEGRATED,
          "complete strict bundle passes the integrate gate")
    ok, detail = runner.verify_ledger(record.loop_id)
    check(ok, f"evidence ledger chain verifies ({detail})")


# Scheduler --------------------------------------------------------

def test_scheduler(tmp):
    agent = make_agent(tmp)
    sched = Scheduler(
        agent, cache_path=os.path.join(tmp, "sched.json"))
    median, runs = sched._measure("c", 1, 1, 1 << 16)
    check(median > 0, "C tier search rate is positive")
    check(runs[0]["attempted"] == 1 << 16,
          "attempted count is the full fixed workload")
    check(pick_winner({"a": 1.0, "b": 2.5, "c": 0.5}) == "b",
          "pick_winner takes the highest median")
    check(pick_winner({}) is None,
          "pick_winner of an empty table is None")
    check(pick_winner({"x": 3.0}) == "x",
          "pick_winner of a single tier is that tier")
    machine = agent.interface.inspect_machine()
    key = sched._cache_key(machine)
    synthetic = {"winner": "C", "winner_rate_hs": 123.0,
                 "rows": [], "from_cache": False}
    sched._write_cache(key, machine, synthetic)
    served = sched.bake_off(use_cache=True, max_age_s=3600)
    check(served["from_cache"] is True
          and served["winner"] == "C",
          "fresh cache entry served instead of re-measuring")
    check(served["cache_age_s"] < 3600,
          "cache age reported and within the maximum")


# Resources --------------------------------------------------------

def test_resources(tmp):
    path = os.path.join(tmp, "resources.json")
    reg = ResourceRegistry(path)
    reg.register_worker("w1", "m1", "Test CPU", 2.0,
                        ["avx2"], "C")
    reg.register_worker("w2", "m1", "Test CPU", 2.0,
                        ["avx2"], "C")
    a1 = reg.assign("w1", "job-A", (0, 64), 0, 1000)
    raises(AssignmentError,
           lambda: reg.assign("w2", "job-A", (0, 64), 500, 1500),
           "overlapping assignment refused")
    other = reg.assign("w2", "job-A", (64, 64), 500, 1500)
    check(other["state"] == "active",
          "same range in a different extranonce space allowed")
    raises(AssignmentError,
           lambda: reg.assign("w1", "job-B", (0, 64), 0,
                              (1 << 32) + 1),
           "nonce end above 2^32 refused")
    edge = reg.assign("w1", "job-B", (0, 64),
                      (1 << 32) - 100, 1 << 32)
    check(edge["nonce_end"] == 1 << 32,
          "nonce end exactly 2^32 allowed")
    raises(AssignmentError,
           lambda: reg.assign("ghost", "job-A", (0, 64), 0, 10),
           "assignment to an unknown worker refused")
    rec = reg.complete(a1["assignment_id"], 3, 10,
                       repeated_computations=7)
    check(rec["state"] == "active",
          "partial completion leaves the assignment active")
    check(rec["batches_completed"] == 3,
          "partial progress recorded")
    check(rec["repeated_computations"] == 7,
          "repeated computations stored as their own counter")
    cov = reg.unique_coverage("job-A")
    check(cov["unique_nonces"] == 300,
          "unique coverage counts the completed prefix only "
          f"(got {cov['unique_nonces']})")
    check(cov["repeated_computations_excluded"] == 7,
          "repeated computations excluded from coverage")
    moved = reg.reassign(a1["assignment_id"], "w2")
    check(moved["worker_id"] == "w2"
          and moved["batches_completed"] == 3
          and moved["state"] == "active",
          "reassignment preserves progress and stays active")
    check(all(a["assignment_id"] != a1["assignment_id"]
              for a in reg.unfinished_for("w1")),
          "moved assignment no longer unfinished for w1")
    check(any(a["assignment_id"] == a1["assignment_id"]
              for a in reg.unfinished_for("w2")),
          "moved assignment is unfinished for w2")
    done = reg.complete(a1["assignment_id"], 10, 10)
    check(done["state"] == "completed",
          "full batch completion completes the assignment")
    cov = reg.unique_coverage("job-A")
    check(cov["unique_nonces"] == 1000,
          "completed range counts in full")
    raises(AssignmentError,
           lambda: reg.reassign(a1["assignment_id"], "w1"),
           "completed assignment cannot be reassigned")
    reg.heartbeat("w1")
    check(reg.workers["w1"]["last_heartbeat"] is not None,
          "heartbeat stamps liveness")
    reg2 = ResourceRegistry(path)
    check(reg2.assignments[a1["assignment_id"]]["state"]
          == "completed",
          "registry persists across instances")


def _union(intervals):
    total = 0
    cur = None
    for s, e in sorted(intervals):
        if cur is None:
            cur = [s, e]
        elif s <= cur[1]:
            cur[1] = max(cur[1], e)
        else:
            total += cur[1] - cur[0]
            cur = [s, e]
    if cur is not None:
        total += cur[1] - cur[0]
    return total


def test_resources_campaign(tmp):
    trials = 240
    total_reassignments = 0
    for trial in range(trials):
        rng = random.Random(20261115 + trial)
        reg = ResourceRegistry(
            os.path.join(tmp, f"campaign-{trial}.json"))
        workers = [f"w{i}" for i in range(3)]
        for w in workers:
            reg.register_worker(w, "m-campaign", "Test CPU",
                                2.0, ["avx2"], "C")
        job = f"job-campaign-{trial}"
        chunk = 256
        n_chunks = 16
        batches_per_chunk = 4
        next_chunk = 0
        model = {}  # assignment_id -> model record
        alive = list(workers)
        for _step in range(60):
            action = rng.random()
            if action < 0.35 and next_chunk < n_chunks:
                start = next_chunk * chunk
                rec = reg.assign(rng.choice(alive), job,
                                 (0, 64), start, start + chunk)
                model[rec["assignment_id"]] = {
                    "start": start, "end": start + chunk,
                    "done": 0, "total": batches_per_chunk,
                    "state": "active"}
                next_chunk += 1
            elif action < 0.70 and model:
                active = [aid for aid, m in model.items()
                          if m["state"] == "active"]
                if not active:
                    continue
                aid = rng.choice(active)
                m = model[aid]
                add = rng.randint(0, m["total"] - m["done"])
                if add == 0:
                    continue
                m["done"] += add
                rec = reg.complete(aid, m["done"], m["total"],
                                   repeated_computations=rng
                                   .randint(0, 3))
                if m["done"] == m["total"]:
                    m["state"] = "completed"
                check(rec["state"] == m["state"],
                      "campaign: registry state matches model")
            elif action < 0.85 and model:
                # Worker death: reassign everything the dead
                # worker holds to a survivor.
                dead = rng.choice(workers)
                survivors = [w for w in workers if w != dead]
                for rec in reg.unfinished_for(dead):
                    reg.reassign(rec["assignment_id"],
                                 rng.choice(survivors))
                    total_reassignments += 1
            else:
                reg.heartbeat(rng.choice(workers))
        completed = [(m["start"], m["end"])
                     for m in model.values()
                     if m["state"] == "completed"]
        for i in range(len(completed)):
            for j in range(i + 1, len(completed)):
                s1, e1 = completed[i]
                s2, e2 = completed[j]
                check(e1 <= s2 or e2 <= s1,
                      "campaign: completed ranges are "
                      "pairwise disjoint")
        intervals = list(completed)
        for m in model.values():
            if m["state"] == "active" and m["done"]:
                length = m["end"] - m["start"]
                intervals.append(
                    (m["start"],
                     m["start"] + length * m["done"]
                     // m["total"]))
        expected = _union(intervals)
        got = reg.unique_coverage(job)["unique_nonces"]
        check(got == expected,
              f"campaign trial {trial}: union coverage "
              f"{got} matches the independent model {expected}")
    print(f"resources campaign: {trials} trials passed, "
          f"{total_reassignments} reassignments, completed "
          "coverage pairwise disjoint and union-consistent")
    check(total_reassignments > 0,
          "campaign actually exercised reassignments")


def main():
    tmp = tempfile.mkdtemp(prefix="agent-operations-")
    runner, record = test_experiment_refusals(tmp)
    test_experiment_end_to_end(runner, record)
    test_scheduler(tmp)
    test_resources(tmp)
    test_resources_campaign(tmp)
    print(f"ALL AGENT OPERATIONS TESTS PASSED ({CHECKS} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
