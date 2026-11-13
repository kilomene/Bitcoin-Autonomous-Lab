#!/usr/bin/env python3
"""Tasks 005/006 tests: autonomous mining engine and agent, live.

Proves on the real regtest node:
1. Autonomous cycles mine blocks through getblocktemplate and
   submitblock (node tip advances by exactly the cycle count, and
   each accepted hash is the node best block).
2. A cycle with a segwit spend in the mempool includes it (witness
   commitment path), across the regtest halving boundary if reached.
3. Statistics and decisions persist in the store.
4. The chain guard refuses a mainnet shaped RPC.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.autonomous import AutonomousMiner
from blockchain.store import BlockStore
from node import node_manager
from node.rpc_client import BitcoinRPC


class FakeMainnetRPC:
    def get_blockchain_info(self):
        return {"chain": "main", "blocks": 900000}


def wallet_rpc(rpc):
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    return BitcoinRPC(wallet="bal-regtest")


def main():
    node_manager.start()
    rpc = BitcoinRPC()
    wallet = wallet_rpc(rpc)
    payout = wallet.call("getnewaddress", "", "bech32")

    store = BlockStore(os.path.join(tempfile.mkdtemp(), "mine.db"))
    agent = AutonomousMiner(rpc, payout, store=store)

    tip0 = rpc.get_block_count()
    out = agent.run_cycles(2)
    assert all(c["accepted"] for c in out["cycles"]), out["cycles"]
    tip1 = rpc.get_block_count()
    assert tip1 == tip0 + 2, (tip0, tip1)
    assert out["cycles"][-1]["hash"] == rpc.get_best_block_hash()
    print(f"ok: 2 autonomous cycles accepted, tip {tip0} -> {tip1}, "
          f"last hash is node best block")

    # Segwit spend through the engine. (Mempool is empty here: the
    # cycles above mined everything pending.)
    assert rpc.call("getmempoolinfo")["size"] == 0
    dest = wallet.call("getnewaddress", "", "bech32")
    txid = wallet.call("sendtoaddress", dest, 0.1)
    out2 = agent.run_cycles(1)
    cyc = out2["cycles"][0]
    assert cyc["accepted"] and cyc["tx_count"] == 2, cyc
    block = rpc.get_block(cyc["hash"], 1)
    assert txid in block["tx"]
    assert cyc["fees"] > 0
    print(f"ok: segwit spend mined by the engine at height "
          f"{cyc['height']} with fees {cyc['fees']} sats")

    summary = store.mining_summary()
    assert summary["cycles"] == 3 and summary["accepted"] == 3, summary
    import json as _json
    kinds = []
    for e in store.events("agent_decision", 50):
        detail = e["detail"]
        kinds.append(_json.loads(detail)["kind"]
                     if isinstance(detail, str) else detail["kind"])
    assert "backend-selected" in kinds and "cycle-accepted" in kinds, kinds
    print(f"ok: stats persisted ({summary}); decision log has "
          f"backend-selected and cycle-accepted entries")

    guard = AutonomousMiner(FakeMainnetRPC(), payout,
                            store=BlockStore(":memory:"))
    try:
        guard.run_cycles(1)
        raise AssertionError("expected mainnet refusal")
    except RuntimeError as exc:
        assert "refuses mainnet" in str(exc)
    print("ok: autonomous agent refuses mainnet without explicit opt in")
    print("ALL MINING ENGINE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
