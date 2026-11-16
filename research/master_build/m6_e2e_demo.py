#!/usr/bin/env python3
"""Milestone 6: independent end-to-end verification demonstration.

Master Build Mandate section 14 (Milestone 6) and section 15:
demonstrate the complete chain with the Milestone 1 agent layer
in the loop, on regtest:

  agent.intelligence.Agent inspection (status, backends)
    -> mining.engine.MiningEngine.mine_cycle (GBT, submitblock)
    -> node acceptance (submitblock plus best-chain equality,
       the engine's own rule)
    -> agent-side independent verification AROUND the engine
       result: the accepted block is fetched back from the node,
       its 80-byte header is serialised, and
       mining.candidate_verify.verify_candidate runs on it
       (hashlib plus pure-Python agreement required, integer
       target verdict, no floating point anywhere)
    -> best-chain membership confirmed against node state.

The GBT path in mining/engine.py does not call
mining/candidate_verify.py internally; acceptance there is
submitblock plus best-chain equality. This script adds the
EXP-036 verification around the engine result from the agent
side. It modifies no production code.

Regtest only. The node setup mirrors tests/test_mining_engine.py
exactly: node.node_manager.start() (datadir .local/regtest,
RPC port 18443) and the same wallet handling (try loadwallet,
fall back to createwallet). No mainnet node, live miner or
autopilot is touched; the agent inspection calls are read-only
(Level 1) and only append to the agent audit log.

Prints one JSON summary on stdout.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..")))

from agent.intelligence import Agent
from mining.candidate_verify import (pow_limit_for_chain,
                                     verify_candidate,
                                     verify_chain_acceptance)
from mining.engine import MiningEngine
from node import node_manager
from node.rpc_client import BitcoinRPC

MAX_CYCLES = 10


def wallet_rpc(rpc):
    """Identical to tests/test_mining_engine.py."""
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    return BitcoinRPC(wallet="bal-regtest")


def _audit_lines(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [ln.rstrip("\n") for ln in f if ln.strip()]
    except OSError:
        return []


def main():
    wall_start = time.time()
    summary = {"chain": "regtest"}

    # 1. Agent inspection (Level 1, read-only, audited).
    agent = Agent()
    audit_path = agent.audit.path
    audit_before = _audit_lines(audit_path)
    status = agent.status()
    backends = agent.interface.inspect_backends()
    summary["agent_status"] = {
        "running": status.running,
        "note": status.note,
        "miner_state": status.miner_state,
        "shares_accepted_total": status.shares_accepted_total,
        "evidence_accepted": status.evidence_accepted,
        "evidence_rejected": status.evidence_rejected,
    }
    summary["agent_backends"] = {
        "dispatch_order": backends.dispatch_order,
        "selected": backends.selected,
        "requested": backends.requested,
    }

    # 2. Regtest node, exactly as the test harness starts it.
    node_manager.start()
    rpc = BitcoinRPC()
    wallet = wallet_rpc(rpc)
    payout = wallet.call("getnewaddress", "", "bech32")
    info = rpc.get_blockchain_info()
    assert info["chain"] == "regtest", info["chain"]
    tip_before = rpc.get_block_count()
    summary["tip_before"] = tip_before

    # 3. Mining engine at production defaults (template cache
    # on, default extranonce space, default batch size).
    engine = MiningEngine(rpc, payout)
    summary["engine_backend"] = engine.compute.backend
    result = None
    cycles = 0
    while cycles < MAX_CYCLES:
        cycles += 1
        result = engine.mine_cycle()
        if result.get("accepted"):
            break
    summary["cycles_attempted"] = cycles
    if not result or not result.get("accepted"):
        summary["error"] = "no accepted block within bound"
        summary["last_engine_result"] = result
        summary["wall_seconds"] = time.time() - wall_start
        print(json.dumps(summary, indent=2, default=str))
        return 1
    height = result["height"]
    block_hash = result["hash"]
    summary["engine_result"] = {
        k: result.get(k) for k in (
            "accepted", "submit_result", "height", "hash",
            "nonce", "hashes", "batches", "extranonce_rounds",
            "backend", "seconds", "hashrate", "tx_count", "fees")
    }

    # 4. Fetch the accepted block back and verify its header
    # independently, agent-side, with the EXP-036 verifier.
    best = rpc.get_best_block_hash()
    raw_block = bytes.fromhex(rpc.call("getblock", best, 0))
    header = raw_block[:80]
    header_hex_rpc = rpc.call("getblockheader", best, False)
    assert bytes.fromhex(header_hex_rpc) == header, \
        "getblockheader hex disagrees with getblock header bytes"
    pow_limit = pow_limit_for_chain("regtest")
    verdict = verify_candidate(header, pow_limit)
    header_hash = verdict["digest"][::-1].hex()
    summary["verify_candidate"] = {
        "classification": verdict["classification"],
        "reason": verdict["reason"],
        "digests_agree": verdict["digests_agree"],
        "valid_header": verdict["valid_header"],
        "meets_network_target": verdict["meets_network_target"],
        "meets_share_target": verdict["meets_share_target"],
        "nbits": verdict["nbits"],
        "value": str(verdict["value"]),
        "target": str(verdict["target"]),
        "digest_display_hex": header_hash,
    }
    # The same verification routed through the agent interface,
    # so the audit trail carries the verify_candidate operation.
    agent_verdict = agent.interface.verify_candidate_op(
        header, chain="regtest")
    summary["agent_verify_candidate"] = {
        "classification": agent_verdict.classification,
        "reason": agent_verdict.reason,
        "digests_agree": agent_verdict.digests_agree,
        "valid_header": agent_verdict.valid_header,
        "meets_network_target":
            agent_verdict.meets_network_target,
    }

    # 5. Best-chain membership from node state.
    info_after = rpc.get_blockchain_info()
    chain_status, chain_accepted = verify_chain_acceptance(
        rpc, block_hash)
    summary["confirmation"] = {
        "getbestblockhash": best,
        "block_hash": block_hash,
        "header_hash_matches_block_hash": header_hash == block_hash,
        "best_equals_block": best == block_hash,
        "getblockchaininfo_blocks": info_after["blocks"],
        "recorded_height": height,
        "blocks_equals_height": info_after["blocks"] == height,
        "verify_chain_acceptance": chain_status,
        "verify_chain_accepted": chain_accepted,
    }
    ok = (verdict["classification"] == "block_candidate"
          and verdict["meets_network_target"]
          and verdict["digests_agree"]
          and header_hash == block_hash
          and best == block_hash
          and info_after["blocks"] == height
          and chain_accepted)
    summary["demonstration_ok"] = bool(ok)

    # Audit trail for this run.
    audit_after = _audit_lines(audit_path)
    new_lines = audit_after[len(audit_before):]
    summary["agent_audit"] = {
        "path": os.path.relpath(audit_path),
        "records_before": len(audit_before),
        "records_after": len(audit_after),
        "records_for_run": len(new_lines),
        "lines": new_lines,
    }
    summary["height"] = height
    summary["block_hash"] = block_hash
    summary["wall_seconds"] = time.time() - wall_start
    print(json.dumps(summary, indent=2, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
