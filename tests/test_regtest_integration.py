#!/usr/bin/env python3
"""Regtest integration test for Task 001.

Requires the Lab Regtest node (starts it if needed). Verifies the full
milestone against the real node:

1. getblockchaininfo reports chain "regtest".
2. A wallet exists and yields a fresh address.
3. generatetoaddress advances the height by exactly N.
4. getblock on the newest hash matches the recorded height and links
   to the previous block.
5. getblockheader and getchaintips agree with getblockchaininfo.

Outputs evidence JSON to evidence/regtest/task001-evidence.json when
run with --evidence. Run: python3 tests/test_regtest_integration.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from node import node_manager
from node.rpc_client import BitcoinRPC, RpcError

EVIDENCE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "evidence", "regtest",
    "task001-evidence.json")


def ensure_wallet(rpc):
    wallets = rpc.call("listwallets")
    if "bal-regtest" not in wallets:
        try:
            rpc.call("createwallet", "bal-regtest")
        except RpcError as exc:
            if "already exists" not in str(exc):
                raise
    return BitcoinRPC(wallet="bal-regtest")


def main():
    evidence = {}
    node_manager.start()
    rpc = BitcoinRPC()

    info = rpc.get_blockchain_info()
    assert info["chain"] == "regtest", info["chain"]
    evidence["getblockchaininfo"] = {
        k: info[k] for k in ("chain", "blocks", "headers", "bestblockhash",
                             "difficulty", "mediantime", "pruned",
                             "verificationprogress")
    }
    print(f"ok: getblockchaininfo chain=regtest blocks={info['blocks']}")

    wallet = ensure_wallet(rpc)
    address = wallet.call("getnewaddress", "", "bech32")
    assert address.startswith("bcrt1"), address
    evidence["regtest_address"] = address
    print(f"ok: wallet address {address}")

    before = rpc.get_block_count()
    generated = rpc.call("generatetoaddress", 12, address)
    after = rpc.get_block_count()
    assert len(generated) == 12
    assert after == before + 12, (before, after)
    evidence["generatetoaddress"] = {
        "count": 12, "height_before": before, "height_after": after,
        "hashes": generated,
    }
    print(f"ok: generatetoaddress 12 blocks, height {before} -> {after}")

    tip_hash = rpc.get_best_block_hash()
    assert tip_hash == generated[-1]
    block = rpc.get_block(tip_hash, 1)
    assert block["height"] == after
    assert block["confirmations"] == 1
    assert len(block["tx"]) >= 1  # coinbase at minimum
    prev = rpc.get_block(block["previousblockhash"], 1)
    assert prev["height"] == after - 1
    evidence["getblock_tip"] = {
        k: block[k] for k in ("hash", "height", "time", "mediantime",
                              "nonce", "bits", "difficulty", "chainwork",
                              "previousblockhash", "merkleroot")
    }
    evidence["getblock_tip_tx_count"] = len(block["tx"])
    print(f"ok: getblock tip height={block['height']} txs={len(block['tx'])} "
          f"linked to prev height={prev['height']}")

    header = rpc.get_block_header(tip_hash, True)
    assert header["hash"] == tip_hash and header["height"] == after
    tips = rpc.get_chain_tips()
    assert tips[0]["height"] == after and tips[0]["status"] == "active"
    evidence["getblockheader_tip_height"] = header["height"]
    evidence["getchaintips"] = tips
    print("ok: getblockheader and getchaintips agree with the tip")

    # Wallet should now hold the (matured only after 100 blocks on
    # regtest) balance check: report it, do not assert maturity here.
    evidence["wallet_balance_mine_trusted"] = wallet.call(
        "getbalances")["mine"]["trusted"]
    print("ALL REGTEST TESTS PASSED")

    if "--evidence" in sys.argv:
        os.makedirs(os.path.dirname(EVIDENCE_PATH), exist_ok=True)
        with open(EVIDENCE_PATH, "w") as f:
            json.dump(evidence, f, indent=2)
        print(f"evidence written: {EVIDENCE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
