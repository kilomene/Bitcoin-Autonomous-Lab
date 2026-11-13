#!/usr/bin/env python3
"""Task 002 integration tests: Blockchain Intelligence Engine on Regtest.

Covers, against the real node:
1. Service sync stores every block from genesis to tip.
2. A wallet spend is seen in the mempool, inspected with an exact fee,
   then confirmed; analysis of its block verifies merkle root, PoW,
   subsidy and fee agreement between coinbase and per-tx accounting.
3. Persistence: a fresh store object on the same file sees the data.
4. Reorganization: invalidateblock plus new blocks; the service
   detects the fork, records a reorg event, and ends matching the node.
5. Resilience: a service pointed at a dead port reports disconnected
   instead of crashing.

Run: python3 tests/test_intelligence_engine.py [--evidence]
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from blockchain.analysis import BlockAnalyzer
from blockchain.service import MonitorService
from blockchain.store import BlockStore
from blockchain.transactions import TxInspector, TxUnavailable
from node import node_manager
from node.rpc_client import BitcoinRPC

EVIDENCE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "evidence", "regtest",
    "task002-evidence.json")


def wallet_rpc(rpc):
    wallets = rpc.call("listwallets")
    if "bal-regtest" not in wallets:
        rpc.call("createwallet", "bal-regtest")
    return BitcoinRPC(wallet="bal-regtest")


def main():
    evidence = {}
    node_manager.start()
    rpc = BitcoinRPC()
    wallet = wallet_rpc(rpc)
    address = wallet.call("getnewaddress", "", "bech32")

    # Mature some coinbases so the wallet can spend (regtest: 100).
    if rpc.get_block_count() < 130:
        rpc.call("generatetoaddress", 130 - rpc.get_block_count(), address)
    print(f"ok: chain prepared at height {rpc.get_block_count()}")

    tmp = tempfile.mkdtemp(prefix="bal-engine-")
    db_path = os.path.join(tmp, "engine.db")
    store = BlockStore(db_path)
    service = MonitorService(rpc, store, poll_seconds=0.2)

    # 1. Full sync
    result = service.sync_once()
    tip = rpc.get_block_count()
    assert result["status"] == "synced", result
    assert store.block_count() == tip + 1, (store.block_count(), tip)
    assert store.get_sync()["tip_hash"] == rpc.get_best_block_hash()
    assert len(result["new_blocks"]) == tip + 1
    evidence["sync"] = {"tip": tip, "stored_blocks": store.block_count(),
                        "tip_hash": store.get_sync()["tip_hash"]}
    print(f"ok: service synced {store.block_count()} blocks to tip {tip}")

    # 2. Real spend: mempool, fee, confirmation, block analysis.
    # Drain any mempool leftovers from other suites sharing this
    # chain, so the block below contains exactly this test's spend.
    if rpc.call("getmempoolinfo")["size"]:
        rpc.call("generatetoaddress", 1, address)
    dest = wallet.call("getnewaddress", "", "bech32")
    txid = wallet.call("sendtoaddress", dest, 0.5)
    insp = TxInspector(rpc)
    snap = insp.mempool_snapshot()
    assert txid in snap["txids"], "spend not in mempool"
    entry = insp.mempool_entry(txid)
    view = insp.inspect(txid)
    assert view["fee_sats"] is not None and view["fee_sats"] > 0, view
    assert entry["fee_sats"] == view["fee_sats"], (entry, view)
    assert len(view["vin"]) >= 1 and len(view["vout"]) >= 1
    sync2 = service.sync_once()
    assert txid in sync2["mempool_new"], sync2
    assert store.transaction(txid)["in_mempool"] == 1
    print(f"ok: mempool tx {txid[:16]}... fee {view['fee_sats']} sats, "
          f"vsize {view['vsize']}, entry fee agrees")

    new_hashes = rpc.call("generatetoaddress", 1, address)
    service.sync_once()
    confirmed = insp.inspect(txid)
    assert confirmed["confirmations"] == 1, confirmed
    assert confirmed["blockhash"] == new_hashes[0]

    analyzer = BlockAnalyzer(rpc)
    analysis = analyzer.analyze(new_hashes[0])
    assert analysis["merkle_verified"] is True, analysis
    assert analysis["pow_verified"] is True, analysis
    assert analysis["tx_count"] == 2, analysis
    assert analysis["fees_agree"] is True, analysis
    assert analysis["total_fees_sats_from_txs"] == view["fee_sats"]
    from mining.pow import coinbase_subsidy
    assert analysis["subsidy_sats"] == coinbase_subsidy(
        analysis["height"], 150)  # regtest halving interval is 150
    evidence["spend_tx"] = {
        "txid": txid, "fee_sats": view["fee_sats"], "vsize": view["vsize"],
        "vin": len(view["vin"]), "vout": len(view["vout"]),
        "confirmed_in_block": new_hashes[0],
    }
    evidence["block_analysis"] = {
        k: analysis[k] for k in (
            "hash", "height", "tx_count", "subsidy_sats",
            "total_fees_sats_from_coinbase", "total_fees_sats_from_txs",
            "fees_agree", "merkle_verified", "pow_verified", "nonce",
            "bits", "difficulty", "size", "weight", "merkleroot")
    }
    print(f"ok: block {analysis['height']} analysis: merkle verified, "
          f"pow verified, fees agree at {view['fee_sats']} sats")

    # Unavailable transaction handling: a fabricated txid must raise
    # TxUnavailable, never fabricate data.
    try:
        insp.inspect("00" * 32)
        raise AssertionError("expected TxUnavailable")
    except TxUnavailable:
        print("ok: unknown txid raises TxUnavailable with the node reason")

    # Decode check: raw hex round trip through decoderawtransaction.
    raw = rpc.call("getrawtransaction", txid)
    decoded = insp.decode_raw(raw)
    assert decoded["txid"] == txid
    print("ok: decoderawtransaction round trip matches txid")

    # 3. Persistence across a store restart.
    store.close()
    store2 = BlockStore(db_path)
    assert store2.block_count() == rpc.get_block_count() + 1
    assert store2.get_sync()["tip_hash"] == rpc.get_best_block_hash()
    assert store2.transaction(txid) is not None
    print("ok: data persists across store restart")

    # 4. Reorganization handling.
    service2 = MonitorService(rpc, store2, poll_seconds=0.2)
    tip_before = rpc.get_block_count()
    fork_hash = rpc.get_block_hash(tip_before - 2)
    old_tip_hash = rpc.get_best_block_hash()
    rpc.call("invalidateblock", fork_hash)
    assert rpc.get_block_count() == tip_before - 3
    rpc.call("generatetoaddress", 5, address)
    result = service2.sync_once()
    assert result["reorg"] is not None, result
    assert store2.get_sync()["tip_hash"] == rpc.get_best_block_hash()
    assert store2.get_sync()["tip_hash"] != old_tip_hash
    assert any(e["kind"] == "reorg" for e in store2.events("reorg"))
    evidence["reorg"] = {"fork_at_height": tip_before - 2,
                         "dropped": result["reorg"]["dropped_blocks"],
                         "new_tip": store2.get_sync()["tip_hash"]}
    print(f"ok: reorg detected, {result['reorg']['dropped_blocks']} "
          f"stored blocks dropped, store tip matches node tip")

    # 5. RPC failure resilience.
    dead = BitcoinRPC(port=59999, user="x", password="y",
                      timeout=1, retries=1)
    dead_store = BlockStore(os.path.join(tmp, "dead.db"))
    dead_service = MonitorService(dead, dead_store, poll_seconds=0.1)
    res = dead_service.sync_once()
    assert res["status"] == "disconnected", res
    run_res = dead_service.run(max_cycles=2)
    assert run_res["cycles"] == 2
    print("ok: dead node reports disconnected, run loop does not crash")

    store2.close()
    dead_store.close()
    print("ALL INTELLIGENCE ENGINE TESTS PASSED")

    if "--evidence" in sys.argv:
        os.makedirs(os.path.dirname(EVIDENCE_PATH), exist_ok=True)
        with open(EVIDENCE_PATH, "w") as f:
            json.dump(evidence, f, indent=2)
        print(f"evidence written: {EVIDENCE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
