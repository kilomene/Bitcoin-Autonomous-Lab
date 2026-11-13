#!/usr/bin/env python3
"""Milestone run for Tasks 003 to 006: one captured live session.

Steps: CUDA build and diagnostics, PoW engine cross-verification of
the live chain, then three autonomous mining cycles on regtest with
a segwit spend included in the second cycle. Writes
evidence/regtest/task003-006-evidence.json.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.autonomous import AutonomousMiner
from blockchain.store import BlockStore
from gpu import diagnostics
from gpu.cuda.build import build as cuda_build
from mining.pow_engine import POW_LIMIT_REGTEST, check_pow, double_sha256_pure
from node import node_manager
from node.rpc_client import BitcoinRPC

EVIDENCE = os.path.join(os.path.dirname(__file__), "..",
                        "evidence", "regtest", "task003-006-evidence.json")


def main():
    evidence = {}
    print("== CUDA build and diagnostics ==")
    built = cuda_build()
    diag = diagnostics.collect()
    evidence["cuda"] = {"nvcc": built["nvcc"], "lib_built": bool(built["lib"]),
                        "host_test_built": bool(built["host_test"]),
                        "diagnostics": diag}
    print(json.dumps(diag, indent=2))

    node_manager.start()
    rpc = BitcoinRPC()
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    wallet = BitcoinRPC(wallet="bal-regtest")
    payout = wallet.call("getnewaddress", "", "bech32")

    print("== PoW engine cross-verification of the live chain ==")
    tip = rpc.get_block_count()
    bad = 0
    for height in range(tip + 1):
        bhash = rpc.get_block_hash(height)
        header = bytes.fromhex(rpc.call("getblockheader", bhash, False))
        ok, _ = check_pow(header, POW_LIMIT_REGTEST)
        if not ok or double_sha256_pure(header)[::-1].hex() != bhash:
            bad += 1
    evidence["pow_cross_verify"] = {"blocks_checked": tip + 1,
                                    "mismatches": bad}
    print(f"checked {tip + 1} headers, mismatches: {bad}")
    assert bad == 0

    print("== Autonomous mining: 3 cycles ==")
    store = BlockStore()
    agent = AutonomousMiner(rpc, payout, store=store)
    tip0 = rpc.get_block_count()
    out1 = agent.run_cycles(1)
    dest = wallet.call("getnewaddress", "", "bech32")
    spend = wallet.call("sendtoaddress", dest, 0.15)
    out2 = agent.run_cycles(2)
    cycles = out1["cycles"] + out2["cycles"]
    for c in cycles:
        print({k: c.get(k) for k in ("accepted", "height", "hash", "nonce",
                                     "hashes", "backend", "tx_count",
                                     "fees")})
    assert all(c["accepted"] for c in cycles)
    assert rpc.get_block_count() == tip0 + 3
    assert cycles[-1]["hash"] == rpc.get_best_block_hash()
    evidence["autonomous_mining"] = {
        "tip_before": tip0, "tip_after": rpc.get_block_count(),
        "spend_txid": spend, "cycles": [
            {k: c.get(k) for k in ("accepted", "height", "hash", "nonce",
                                   "hashes", "batches", "backend",
                                   "tx_count", "fees", "hashrate")}
            for c in cycles],
        "summary": store.mining_summary(),
        "benchmark_hs": out1["benchmark_hs"],
        "backend": out1["backend"],
        "fallback_reason": out1["fallback_reason"],
    }
    with open(EVIDENCE, "w") as f:
        json.dump(evidence, f, indent=2)
    print(f"evidence written: {EVIDENCE}")
    print("MILESTONE 003-006: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
