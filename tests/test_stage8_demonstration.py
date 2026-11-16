#!/usr/bin/env python3
"""Stage 8 tests: the autonomous agent-directed mining
demonstration machinery (research/EXTREME_RESEARCH/
stage8_demonstration.py), re-checked at smaller scale.

What this suite pins, against an ISOLATED autopilot instance
whose miner child is the real Stage 8 regtest miner
(research/EXTREME_RESEARCH/stage8_regtest_miner.py: the
production MiningEngine / ComputeEngine GBT path):

- the optimisation loop's hypothesise gate refuses a
  REJECTED re-proposal (EXP-014) and an INTEGRATED
  re-proposal (EXP-026), each with its citation;
- mining starts and stops through the agent interface's L2
  operations executed by the production MiningController,
  with verified postconditions;
- a block found through that path verifies through the
  EXP-036 gate (interface verify_candidate operation plus
  verify_chain_acceptance against the regtest node);
- the accounting the miner publishes is EXP-037 separated:
  the MiningStatistics totals carry exactly the fixed
  category set with no combined total, unique counters never
  exceed the backend counter, and the miner's own
  blocks_accepted equals the block events it recorded;
- a declared correctness fault halts controller recovery
  and leaves the running stack untouched.

Differences from the live demonstration, disclosed: the
search-target amplification shift is 8 here instead of 24
(the EXP-040 harness parameter; it changes only how long
each search runs, never what counts as a block), and the
miner is capped at 3 blocks before idling. The live mainnet
stack is never started, stopped, restarted or signalled;
the only node this suite talks to is the shared regtest
node (started through node.node_manager if it is down,
the same assumption the other regtest suites make).

Run: python3 tests/test_stage8_demonstration.py
"""

import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from agent.intelligence import Agent
from agent.intelligence.awareness import Awareness
from agent.intelligence.controller import MiningController
from agent.intelligence.loop import LoopRefusal
from mining.candidate_verify import verify_chain_acceptance
from mining.mining_statistics import CATEGORIES
from node.rpc_client import BitcoinRPC

MINER_SCRIPT = os.path.join(
    ROOT, "research", "EXTREME_RESEARCH",
    "stage8_regtest_miner.py")

CHECKS = 0


def check(cond, msg):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(msg)


def ensure_regtest_node():
    from node import node_manager
    if not node_manager.is_running():
        node_manager.start(wait_seconds=120)


def make_instance(tmp):
    iso = os.path.join(tmp, "iso")
    for sub in ("mining", "scripts", ".local", "evidence"):
        os.makedirs(os.path.join(iso, sub))
    shutil.copy(os.path.join(ROOT, "mining", "autopilot.py"),
                os.path.join(iso, "mining", "autopilot.py"))
    shutil.copy(os.path.join(ROOT, "scripts", "autopilot.sh"),
                os.path.join(iso, "scripts", "autopilot.sh"))
    state = os.path.join(tmp, "agent")
    os.makedirs(state)
    iso_local = os.path.join(iso, ".local")
    env = {"BAL_AP_MINER_CMD": json.dumps(
               [sys.executable, MINER_SCRIPT]),
           "BAL_AUTO_UPDATE": "0",
           "BAL_AP_HEARTBEAT_S": "1",
           "BAL_AP_POLL_S": "0.2",
           "BAL_AP_STALE_S": "3600",
           "BAL_STAGE8_EVIDENCE": os.path.join(
               iso, "evidence", "mainnet-live.jsonl"),
           "BAL_STAGE8_CHECKPOINT": os.path.join(
               iso_local, "work-checkpoint.json"),
           "BAL_STAGE8_AMPLIFY_SHIFT": "8",
           "BAL_STAGE8_MAX_BLOCKS": "3"}
    ctl = MiningController(
        repo_root=iso, local_dir=iso_local,
        verify_timeout_s=60.0, poll_s=0.25, env_extra=env,
        miner_needles=("stage8_regtest_miner.py",))
    agent = Agent(
        local_dir=iso_local,
        audit_path=os.path.join(state, "agent-audit.jsonl"),
        tasks_path=os.path.join(state, "agent-tasks.json"),
        sandbox_root=os.path.join(state, "agent-experiments"),
        controller=ctl,
        verifier_key_path=os.path.join(state, "verifier",
                                       "verifier.key"),
        mode_state_path=os.path.join(state, "agent-mode.json"))
    aw = Awareness(
        agent,
        heartbeat_path=os.path.join(iso_local,
                                    "heartbeat.json"),
        census_path=os.path.join(iso_local,
                                 "evidence-count.json"),
        status_path=os.path.join(iso_local,
                                 "mainnet-status.txt"),
        endpoint_path=os.path.join(iso_local,
                                   "mining-endpoint.json"),
        node_config_path=os.path.join(
            ROOT, ".local", "regtest", "node-config.json"),
        evidence_log_path=os.path.join(
            iso, "evidence", "mainnet-live.jsonl"),
        rpc_factory=lambda path, timeout: BitcoinRPC(
            ).with_timeout(timeout, retries=1))
    return iso, ctl, agent, aw


def test_loop_gates(agent):
    loop = agent.loop()
    rec = loop.new_record(
        "stage8-suite-rejected",
        "K+W constant folding of the message-schedule "
        "constants for a fixed template",
        keywords=["K+W", "folding"])
    loop.advance(rec)
    try:
        loop.advance(rec)
        raise SystemExit("rejected probe was not refused")
    except LoopRefusal as exc:
        check(exc.citation is not None
              and exc.citation["entry_id"] == "EXP-014"
              and exc.citation["status"] == "REJECTED",
              "REJECTED re-proposal refused with the "
              "EXP-014 citation")
    rec2 = loop.new_record(
        "stage8-suite-integrated",
        "a dual-batch masked search backend (v512dual) "
        "for the production search path",
        keywords=["v512dual"])
    loop.advance(rec2)
    try:
        loop.advance(rec2)
        raise SystemExit("integrated probe was not refused")
    except LoopRefusal as exc:
        check(exc.citation is not None
              and exc.citation["entry_id"] == "EXP-026"
              and exc.citation["status"] == "INTEGRATED",
              "INTEGRATED re-proposal refused with the "
              "EXP-026 citation")


def test_mining_cycle(tmp):
    iso, ctl, agent, aw = make_instance(tmp)
    try:
        rpc = BitcoinRPC()
        start_height = rpc.get_blockchain_info()["blocks"]
        started = agent.interface.start_mining()
        check(started.ok and started.verified,
              f"interface start_mining verifies "
              f"({started.detail})")
        info = ctl.inspect()
        check(info["running"] and info["miner_verified"],
              "isolated miner running and cmdline-verified")

        deadline = time.time() + 300
        height = start_height
        while time.time() < deadline:
            snap = aw.snapshot()
            blocks = (snap["node"] or {}).get("blocks")
            if blocks is not None and blocks > start_height:
                height = blocks
                break
            time.sleep(2)
        check(height > start_height,
              "regtest height advanced under the isolated "
              "miner, observed through awareness snapshots")

        best = rpc.get_best_block_hash()
        header = bytes.fromhex(
            rpc.call("getblockheader", best, False))
        resp = agent.interface.verify_candidate_op(
            header, chain="regtest")
        check(resp.classification == "block_candidate"
              and resp.meets_network_target
              and resp.digests_agree,
              "the found block verifies through the "
              "interface EXP-036 operation")
        status, accepted = verify_chain_acceptance(rpc, best)
        check(accepted and status in ("tip", "in-chain"),
              f"chain acceptance verified ({status})")

        # A declared correctness fault halts recovery and
        # leaves the stack untouched.
        pid_before = ctl.inspect()["miner_pid"]
        halt = agent.interface.trigger_recovery(
            correctness_failure=True)
        check(not halt.ok and halt.status == "halted",
              "correctness fault halts recovery")
        check(ctl.inspect()["miner_pid"] == pid_before
              and ctl.inspect()["running"],
              "the halted recovery left the miner untouched")

        stopped = agent.interface.stop_mining()
        check(stopped.ok and stopped.verified,
              f"interface stop_mining verifies "
              f"({stopped.detail})")
        check(ctl.inspect()["running"] is False,
              "isolated instance down after the verified "
              "stop")

        # Accounting separation over the miner's own
        # evidence log.
        events = []
        with open(os.path.join(iso, "evidence",
                               "mainnet-live.jsonl")) as f:
            for line in f:
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
        blocks_ev = [e for e in events
                     if e.get("event") == "block"]
        check(len(blocks_ev) >= 1,
              "the miner recorded at least one block event")
        check(any(e["hash"] == best for e in blocks_ev),
              "the verified best block is one the isolated "
              "miner recorded")
        statuses = [e for e in events
                    if e.get("event") == "status"]
        check(bool(statuses),
              "the miner published status events")
        totals = statuses[-1]["statistics"]
        check(set(totals.keys()) == set(CATEGORIES),
              "statistics totals carry exactly the EXP-037 "
              "category set (separated, no combined total)")
        check(totals["unique_nonces"]
              <= totals["backend_hashes"],
              "unique nonces never exceed backend hashes")
        check(totals["blocks_accepted"] == len(blocks_ev),
              "miner blocks_accepted equals its recorded "
              "block events")
        check(totals["blocks_submitted"]
              == totals["blocks_accepted"],
              "every submitted block was accepted on "
              "regtest")
    finally:
        try:
            ctl.stop()
        except Exception:
            pass


def main():
    ensure_regtest_node()
    tmp = tempfile.mkdtemp(prefix="stage8-suite-")
    _iso, _ctl, agent, _aw = make_instance(
        os.path.join(tmp, "gates"))
    test_loop_gates(agent)
    test_mining_cycle(os.path.join(tmp, "cycle"))
    print(f"ALL STAGE 8 DEMONSTRATION TESTS PASSED "
          f"({CHECKS} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
