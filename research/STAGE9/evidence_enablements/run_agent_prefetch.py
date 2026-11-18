#!/usr/bin/env python3
"""EXP-051 live enablement verification (Stage 9
enablements, 2026-11-18).

Runs the production agent path (agent/autonomous.py
AutonomousMiner) against an isolated regtest node
(.local/enablements/regtest, started for this workstream;
NOT the lab's mainnet node and NOT the pre-existing
regtest node), twice:

  1. prefetch ON: AutonomousMiner with its new default
     (use_prefetch=True). The engine's EXP-037 statistics
     must show the prefetch machinery alive: at least one
     prefetch_served or prefetch_starved transition, and
     blocks accepted by the node.
  2. prefetch OFF: AutonomousMiner(use_prefetch=False),
     the rollback construction. Its statistics must show
     NO prefetch counters at all (the historical path),
     and blocks must still be accepted.

The two runs mine on the same isolated chain in sequence;
heights are recorded so acceptance is checkable against
the node's own getblockcount. Nothing here touches the
live mainnet stack.

Usage: python3 run_agent_prefetch.py [cycles]
"""

import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

NODE_CFG = os.path.join(ROOT, ".local", "enablements",
                        "regtest", "node-config.json")
PAYOUT_FILE = os.path.join(ROOT, ".local", "enablements",
                           "regtest", "payout.txt")


def make_rpc():
    from node.rpc_client import BitcoinRPC
    with open(NODE_CFG) as f:
        cfg = json.load(f)
    return BitcoinRPC(cfg.get("rpc_host", "127.0.0.1"),
                      int(cfg["rpc_port"]), cfg["rpc_user"],
                      cfg["rpc_password"])


def run_one(rpc, payout, cycles, **kwargs):
    from agent.autonomous import AutonomousMiner
    miner = AutonomousMiner(rpc, payout, **kwargs)
    before = rpc.call("getblockcount")
    t0 = time.time()
    out = miner.run_cycles(cycles=cycles,
                           max_batches_per_cycle=400)
    wall = time.time() - t0
    miner.close()
    after = rpc.call("getblockcount")
    totals = miner.engine.statistics.snapshot()["totals"]
    return {
        "use_prefetch": miner.use_prefetch,
        "queue_constructed":
            miner.engine.prefetch_queue is not None,
        "height_before": before, "height_after": after,
        "blocks_accepted_by_agent":
            sum(1 for c in out["cycles"] if c.get("accepted")),
        "backend": out["backend"],
        "wall_s": round(wall, 2),
        "prefetch_counters": {
            k: totals.get(k, 0) for k in (
                "prefetch_enqueued", "prefetch_served",
                "prefetch_starved", "prefetch_dropped_identity",
                "prefetch_dropped_stale",
                "prefetch_dropped_superseded",
                "prefetch_dropped_overflow")
            if k in totals or miner.use_prefetch},
        "statistics_totals": totals,
    }


def main():
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    rpc = make_rpc()
    info = rpc.get_blockchain_info()
    assert info["chain"] == "regtest", info["chain"]
    with open(PAYOUT_FILE) as f:
        payout = f.read().strip()
    result = {"chain": info["chain"],
              "node_height_at_start": info["blocks"],
              "cycles_per_run": cycles}
    result["prefetch_on"] = run_one(rpc, payout, cycles)
    result["prefetch_off"] = run_one(
        rpc, payout, cycles, use_prefetch=False)
    print(json.dumps(result, indent=1))
    on = result["prefetch_on"]
    off = result["prefetch_off"]
    ok = (
        on["queue_constructed"]
        and on["blocks_accepted_by_agent"] > 0
        and on["height_after"] > on["height_before"]
        and (on["prefetch_counters"].get("prefetch_served", 0)
             + on["prefetch_counters"].get("prefetch_starved", 0)
             > 0)
        and not off["queue_constructed"]
        and off["blocks_accepted_by_agent"] > 0
        and all(v == 0 for k, v in
                off["statistics_totals"].items()
                if k.startswith("prefetch_")))
    print("EXP-051 LIVE AGENT-PATH VERIFICATION:",
          "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
