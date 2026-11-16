#!/usr/bin/env python3
"""Milestone 2 tests for live mining awareness
(agent/intelligence/awareness.py), Master Build Mandate
Milestone 2.

Unit tests run against injected fixture files in a temp dir:

- a stale heartbeat is flagged heartbeat_stale and reported
  not running,
- a rejected share ratio above the threshold is flagged,
- an unreachable node is reported honestly (reachable False
  with the error named, heights None, node_unreachable flag),
- status-file fields a fixture does not carry are reported
  absent by name, never invented,
- the rate observation math on scripted samples: share rate
  from the census delta, backend rate from the
  backend_hashes delta over the status-event interval, and
  the difficulty-weighted figure labelled an estimate and
  produced only from a recorded share difficulty,
- observe_cycle writes its evidence into the standing task
  and the audit log.

One live smoke test runs snapshot() against the real repo
state and asserts internal consistency: accepted plus
rejected equals share_results in the census, and the running
verdict matches heartbeat freshness.

Run: python3 tests/test_agent_awareness.py
"""

import json
import os
import sys
import tempfile
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from agent.intelligence import Agent
from agent.intelligence.awareness import (
    AWARENESS_TASK_ID, Awareness, parse_status_text)

CHECKS = 0


def check(cond, msg):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(msg)


class FakeRPC:
    def __init__(self, info=None, error=None):
        self.info = info
        self.error = error

    def get_blockchain_info(self):
        if self.error is not None:
            raise self.error
        return self.info


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _fixture_dir(tmp, heartbeat_age_s=10.0, accepted=100,
                 rejected=2, node=None, status_text=None,
                 evidence_events=None):
    d = os.path.join(tmp, "fx")
    os.makedirs(d, exist_ok=True)
    hb_ts = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(time.time() - heartbeat_age_s))
    _write(os.path.join(d, "heartbeat.json"), json.dumps({
        "ts": hb_ts, "autopilot_pid": 111, "miner_pid": 222,
        "miner_state": "running", "miner_uptime_s": 500.0,
        "restarts": 0, "shares_accepted_total": accepted,
        "evidence_age_s": 3.0}))
    _write(os.path.join(d, "evidence-count.json"), json.dumps({
        "version": 1, "accepted": accepted, "rejected": rejected,
        "share_results": accepted + rejected,
        "last_epoch": time.time(), "offset": 10,
        "head_len": 0, "head_sha": "x"}))
    if status_text is None:
        status_text = (
            "MAINNET LIVE MINING\n"
            "t=  500s job=abc123 prev=deadbeef pool_diff=1 "
            "hashes=1,000,000 rate=20,000 H/s best=1.5 "
            "shares_submitted=3\n"
            "worker=addr.worker\n"
            "pool=public-pool.io:21496\n"
            "stratum endpoint: public-pool.io:21496 (mode pool)\n"
            "compute backend: v512dual (native impl: test)\n")
    _write(os.path.join(d, "mainnet-status.txt"), status_text)
    if evidence_events is None:
        evidence_events = [
            {"event": "status",
             "ts": "2026-11-16T00:00:00+00:00",
             "hashes": 1000000, "rate": 20000.0, "best": 1.5,
             "submitted": 3,
             "statistics": {"backend_hashes": 1000000,
                            "unique_nonces": 1000000,
                            "unique_coverage": 990000,
                            "actual_computations": 1000000,
                            "repeated_work": 0},
             "statistics_errors": 0},
            {"event": "share_result", "id": 1, "accepted": True,
             "error": None},
        ]
    _write(os.path.join(d, "evidence.jsonl"), "".join(
        json.dumps(e) + "\n" for e in evidence_events))
    _write(os.path.join(d, "endpoint.json"),
           json.dumps({"mode": "pool"}))
    _write(os.path.join(d, "node-config.json"), "{}")
    if node is None:
        node = FakeRPC(info={"blocks": 900, "headers": 1000,
                             "initialblockdownload": True})
    return d, node


def _awareness(tmp, d, node):
    agent = Agent(local_dir=d,
                  audit_path=os.path.join(d, "audit.jsonl"),
                  tasks_path=os.path.join(d, "tasks.json"))
    return Awareness(
        agent,
        heartbeat_path=os.path.join(d, "heartbeat.json"),
        census_path=os.path.join(d, "evidence-count.json"),
        status_path=os.path.join(d, "mainnet-status.txt"),
        endpoint_path=os.path.join(d, "endpoint.json"),
        node_config_path=os.path.join(d, "node-config.json"),
        evidence_log_path=os.path.join(d, "evidence.jsonl"),
        rpc_factory=lambda path, timeout: node)


def test_snapshot_fresh(tmp):
    d, node = _fixture_dir(tmp)
    aw = _awareness(tmp, d, node)
    snap = aw.snapshot()
    check(snap["autopilot"]["running"] is True,
          "fresh heartbeat in running state reports running")
    check(snap["autopilot"]["miner_pid"] == 222,
          "miner pid carried from the heartbeat")
    check(snap["evidence_census"]["consistent"] is True,
          "census consistency: accepted + rejected == total")
    check(snap["evidence_census"]["accepted"] == 100,
          "census accepted carried through")
    check(snap["miner_status_file"]["job_id"] == "abc123",
          "status file job parsed")
    check(snap["miner_status_file"]["backend"] == "v512dual",
          "status file backend parsed")
    check(snap["miner_status_file"]["pool_diff"] == 1.0,
          "status file pool difficulty parsed")
    check(snap["miner_status_file"]["absent_fields"] == [],
          "complete fixture status file has no absent fields")
    check(snap["node"]["reachable"] is True
          and snap["node"]["blocks"] == 900
          and snap["node"]["blocks_behind_headers"] == 100,
          "node state carried from the RPC answer")
    check(snap["endpoint"]["mode"] == "pool",
          "endpoint mode read from the config")
    check(snap["evidence_tail"]["last_status_event"]
          ["statistics"]["backend_hashes"] == 1000000,
          "evidence tail statistics republished in snapshot")
    check(all(v >= 0 for v in snap["read_times_ms"].values()),
          "per-source read times recorded")


def test_stale_heartbeat_flagged(tmp):
    d, node = _fixture_dir(tmp, heartbeat_age_s=3600.0)
    aw = _awareness(tmp, d, node)
    snap = aw.snapshot()
    check(snap["autopilot"]["running"] is False,
          "stale heartbeat reports not running")
    check(snap["autopilot"]["heartbeat_age_s"] > 3000,
          "heartbeat age reported from the file timestamp")
    deg = aw.degradation_check({}, current={
        "snapshot": snap, "observation": {}})
    names = [f["flag"] for f in deg["flags"]]
    check("heartbeat_stale" in names,
          "stale heartbeat flagged by the degradation check")
    flag = [f for f in deg["flags"]
            if f["flag"] == "heartbeat_stale"][0]
    check("heartbeat_age_s" in flag["evidence"],
          "the stale flag names its evidence")


def test_rejected_ratio_flagged(tmp):
    d, node = _fixture_dir(tmp, accepted=80, rejected=20)
    aw = _awareness(tmp, d, node)
    snap = aw.snapshot()
    deg = aw.degradation_check({}, current={
        "snapshot": snap, "observation": {}})
    names = [f["flag"] for f in deg["flags"]]
    check("rejected_ratio_high" in names,
          "rejected ratio 0.20 above the 0.05 threshold "
          "is flagged")
    flag = [f for f in deg["flags"]
            if f["flag"] == "rejected_ratio_high"][0]
    check("rejected=20" in flag["evidence"],
          "the ratio flag names the census counts")


def test_unreachable_node_honest(tmp):
    d, node = _fixture_dir(
        tmp, node=FakeRPC(error=TimeoutError("timed out")))
    aw = _awareness(tmp, d, node)
    snap = aw.snapshot()
    check(snap["node"]["reachable"] is False,
          "unreachable node reported unreachable")
    check(snap["node"]["blocks"] is None
          and snap["node"]["headers"] is None,
          "no height invented for an unreachable node")
    check("TimeoutError" in snap["node"]["error"],
          "the RPC error is named in the snapshot")
    deg = aw.degradation_check({}, current={
        "snapshot": snap, "observation": {}})
    names = [f["flag"] for f in deg["flags"]]
    check("node_unreachable" in names,
          "unreachable node flagged by the degradation check")


def test_missing_status_fields_absent(tmp):
    sparse = "MAINNET LIVE MINING\npool=public-pool.io:21496\n"
    d, node = _fixture_dir(tmp, status_text=sparse)
    aw = _awareness(tmp, d, node)
    snap = aw.snapshot()
    absent = snap["miner_status_file"]["absent_fields"]
    for field in ("job_id", "backend", "pool_diff",
                  "session_hashes", "session_rate_hs"):
        check(field in absent,
              f"missing status field {field} reported absent")
    check("job_id" not in snap["miner_status_file"],
          "absent job is not invented")
    parsed = parse_status_text("")
    check(parsed["absent_fields"] and
          "backend" in parsed["absent_fields"],
          "empty status text reports every field absent")


def test_rate_observation_math(tmp):
    d, node = _fixture_dir(tmp)
    aw = _awareness(tmp, d, node)
    samples = [
        {"wall_ts": 1000.0, "accepted": 100, "rejected": 2,
         "share_results": 102, "backend_hashes": 1000000,
         "status_event_ts": 990.0,
         "status_event_session_rate_hs": 20000.0,
         "pool_diff": 1.0},
        {"wall_ts": 1120.0, "accepted": 102, "rejected": 2,
         "share_results": 104, "backend_hashes": 3400000,
         "status_event_ts": 1110.0,
         "status_event_session_rate_hs": 20000.0,
         "pool_diff": 1.0},
    ]
    aw._sample = lambda: samples.pop(0)
    obs = aw.rate_observation(120.0, sleep=lambda s: None)
    check(obs["shares_delta"] == 2, "share delta from census")
    check(abs(obs["share_rate_per_s"] - 2.0 / 120.0) < 1e-12,
          "share rate is the census delta over the wall window")
    check(obs["backend_hashes_delta"] == 2400000,
          "backend delta from the statistics counter")
    check(abs(obs["backend_rate_hs"] - 20000.0) < 1e-9,
          "backend rate is the counter delta over the "
          "status-event interval")
    implied = obs["implied_difficulty_weighted_rate_hs"]
    check(implied is not None
          and abs(implied - 2 * 2 ** 32 / 120.0) < 1e-6,
          "implied estimate uses the recorded share difficulty")
    check("ESTIMATE" in obs["method"],
          "the implied figure is labelled an estimate with "
          "its method")
    # No recorded difficulty: no implied figure, said plainly.
    samples2 = [
        {"wall_ts": 2000.0, "accepted": 5, "rejected": 0,
         "share_results": 5, "backend_hashes": None,
         "status_event_ts": None,
         "status_event_session_rate_hs": None,
         "pool_diff": None},
        {"wall_ts": 2060.0, "accepted": 6, "rejected": 0,
         "share_results": 6, "backend_hashes": None,
         "status_event_ts": None,
         "status_event_session_rate_hs": None,
         "pool_diff": None},
    ]
    aw._sample = lambda: samples2.pop(0)
    obs2 = aw.rate_observation(60.0, sleep=lambda s: None)
    check(obs2["implied_difficulty_weighted_rate_hs"] is None,
          "no recorded difficulty means no implied rate")
    check(obs2["backend_rate_hs"] is None,
          "no status events means no backend rate, honestly")
    check(any("not observable" in n for n in obs2["notes"]),
          "the unobservable backend accounting is noted")


def test_observe_cycle_writes_records(tmp):
    d, node = _fixture_dir(tmp)
    aw = _awareness(tmp, d, node)
    report = aw.observe_cycle(window_s=0.0)
    check(report["kind"] == "awareness_operational_report",
          "observe cycle returns the operational report")
    check(report["overhead"]["total_wall_s"] >= 0,
          "cycle overhead measured")
    check("active_overhead_s_excluding_window"
          in report["overhead"],
          "active overhead reported separately from the "
          "observation window")
    check(report["coverage"]["cannot_state"],
          "coverage report states what cannot be stated")
    check(any("work_checkpoint" in s
              for s in report["coverage"]["cannot_state"]),
          "the pool path checkpoint gap cites "
          "work_checkpoint.py's GBT scope")
    task = aw.agent.tasks.get(AWARENESS_TASK_ID)
    check(task is not None and task.state == "active",
          "the standing awareness task exists and is active")
    check(any(e.startswith("observe_cycle")
              for e in task.evidence),
          "the cycle recorded its evidence on the task")
    records = aw.agent.audit.read()
    check(any(r["operation"] == "awareness_observe"
              for r in records),
          "the cycle wrote audit records")


def test_live_smoke():
    agent = Agent()
    aw = Awareness(agent)
    snap = aw.snapshot()
    census = snap["evidence_census"]
    check(census["present"] is True,
          "live census file present")
    check(census["accepted"] + census["rejected"]
          == census["share_results"],
          "live census internally consistent: accepted plus "
          "rejected equals share_results")
    age = snap["autopilot"]["heartbeat_age_s"]
    if age is not None:
        fresh = age < 120.0 and \
            snap["autopilot"]["miner_state"] == "running"
        check(snap["autopilot"]["running"] == fresh,
              "live running verdict matches heartbeat "
              "freshness")
    node = snap["node"]
    check(node["reachable"] in (True, False),
          "live node read attempted and reported one way or "
          "the other")
    if node["reachable"]:
        check(node["blocks"] <= node["headers"],
              "live node blocks never exceed headers")


def main():
    tmp = tempfile.mkdtemp(prefix="agent-awareness-")
    test_snapshot_fresh(tmp)
    test_stale_heartbeat_flagged(tmp)
    test_rejected_ratio_flagged(tmp)
    test_unreachable_node_honest(tmp)
    test_missing_status_fields_absent(tmp)
    test_rate_observation_math(tmp)
    test_observe_cycle_writes_records(tmp)
    test_live_smoke()
    print(f"ALL AGENT AWARENESS TESTS PASSED ({CHECKS} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
