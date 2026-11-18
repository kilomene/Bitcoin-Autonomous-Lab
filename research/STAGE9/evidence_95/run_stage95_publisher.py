#!/usr/bin/env python3
"""Stage 9.5 supplementary LAUNCHER (disclosed): publisher
evidence run.

Identical construction to run_stage95.py (imported and reused,
including its VerifyingRPC shim and its isolated checkpoint
redirect), with two differences: 3 cycles instead of 5, and
the Stage 9.4 StatusPublisher interval set to 0.02 s instead
of 0.25 s, because in the main run every cycle completed in
less than the 0.25 s interval and the publisher emitted zero
events (its first publication happens one interval after the
cycle starts). This run continues the same isolated chain
(heights 6 to 8) with a fresh agent instance over the same
isolated store, so the publisher's output is captured as
evidence. Output: run_output_publisher.json, agent log
agent_publisher.log.
"""

import json
import logging
import os
import sys
import time

STAGE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, STAGE)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(
        os.path.join(STAGE, "agent_publisher.log")),
        logging.StreamHandler(sys.stdout)])
log = logging.getLogger("bal.stage95.publisher_launcher")

import run_stage95 as L
from agent.autonomous import AutonomousMiner
from blockchain.store import BlockStore
from gpu.engine import ComputeEngine
from node.rpc_client import BitcoinRPC


def main():
    wallet = BitcoinRPC(host=L.RPC_HOST, port=L.RPC_PORT,
                        user=L.RPC_USER, password=L.RPC_PASSWORD,
                        wallet="stage95")
    payout = wallet.call("getnewaddress", "", "bech32")
    log.info("payout address (isolated node wallet): %s", payout)

    rpc = L.VerifyingRPC(host=L.RPC_HOST, port=L.RPC_PORT,
                         user=L.RPC_USER, password=L.RPC_PASSWORD)
    store = BlockStore(os.path.join(STAGE, "agent-store.db"))
    compute = ComputeEngine()
    agent = AutonomousMiner(rpc, payout, store=store,
                            compute=compute)
    agent.engine.status_publish = True
    agent.engine.status_interval_s = 0.02

    t0 = time.time()
    out = agent.run_cycles(3)
    t1 = time.time()

    record = {
        "launcher": "run_stage95_publisher.py",
        "started_ts": t0, "ended_ts": t1,
        "payout_address": payout,
        "status_interval_s": 0.02,
        "chain": out["chain"],
        "backend": out["backend"],
        "fallback_reason": out["fallback_reason"],
        "benchmark_hs": out["benchmark_hs"],
        "cycles": out["cycles"],
        "decisions": out["decisions"],
        "summary": out["summary"],
        "engine_statistics": agent.engine.statistics.snapshot(),
        "status_events": list(agent.engine.status_events),
        "rpc_trace": rpc.trace,
        "verifications": rpc.verifications,
    }
    with open(os.path.join(STAGE, "run_output_publisher.json"),
              "w") as f:
        json.dump(record, f, indent=2)
    for c in out["cycles"]:
        print({k: c.get(k) for k in
               ("accepted", "height", "hash", "nonce", "hashes",
                "batches", "backend", "reason")})
    print(f"status_events captured: "
          f"{len(record['status_events'])}")
    print("run_output_publisher.json written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
