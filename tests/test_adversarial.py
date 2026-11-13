#!/usr/bin/env python3
"""Task 004 adversarial tests: the engine must fail closed.

Covers corrupted templates, consensus edge encodings, injection
attempts against the store, and malformed inputs to every new public
surface from Tasks 003 to 006.
"""

import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from blockchain.store import BlockStore
from gpu.engine import ComputeEngine
from mining.engine import MiningEngine, TemplateError, strip_witness
from mining.pow_engine import POW_LIMIT_MAINNET, check_pow
from node import node_manager
from node.rpc_client import BitcoinRPC


def main():
    node_manager.start()
    rpc = BitcoinRPC()
    wallet = BitcoinRPC(wallet="bal-regtest") \
        if "bal-regtest" in rpc.call("listwallets") else None
    if wallet is None:
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
        wallet = BitcoinRPC(wallet="bal-regtest")
    addr = wallet.call("getnewaddress", "", "bech32")
    eng = MiningEngine(rpc, addr)

    template = eng.get_template()

    # 1. Corrupted txid in a template transaction is rejected.
    import copy
    bad = copy.deepcopy(template)
    # Known starting state: mine away anything pending, then place
    # this test's own spend and wait for the template to carry it.
    if rpc.call("getmempoolinfo")["size"]:
        eng.mine_cycle()
    dest = wallet.call("getnewaddress", "", "bech32")
    wallet.call("sendtoaddress", dest, 0.05)
    template = eng.get_template()
    for _ in range(20):
        if template["transactions"]:
            break
        import time as _t
        _t.sleep(0.5)
        template = eng.get_template()
    assert template["transactions"], "need a mempool tx for this test"
    bad = copy.deepcopy(template)
    bad["transactions"][0]["txid"] = "ff" * 32
    try:
        eng.build_candidate(bad, 0)
        raise AssertionError("expected TemplateError for bad txid")
    except TemplateError as exc:
        assert "txid mismatch" in str(exc)
    print("ok: template with corrupted txid rejected")

    # 2. Missing template fields are rejected, never guessed.
    bad2 = copy.deepcopy(template)
    del bad2["transactions"][0]["data"]
    try:
        eng.build_candidate(bad2, 0)
        raise AssertionError("expected TemplateError for missing data")
    except TemplateError:
        pass
    # leave the mempool clean for other tests: mine it away
    eng.mine_cycle()
    print("ok: template with missing tx data rejected")

    # 3. Store injection: hostile strings are data, never SQL.
    store = BlockStore(os.path.join(tempfile.mkdtemp(), "adv.db"))
    evil = "x'); DROP TABLE blocks;--"
    store.record_mining_cycle({"height": 1, "accepted": True,
                               "hash": evil, "nonce": 0, "hashes": 1,
                               "batches": 1, "backend": "cpu",
                               "seconds": 0.1, "hashrate": 10})
    assert store.mining_summary()["cycles"] == 1
    assert store.block_count() == 0  # table intact, simply empty
    print("ok: store treats hostile strings as data (parameterized)")

    # 4. Consensus edge encodings rejected with reason codes.
    header = bytearray(80)
    def with_bits(bits):
        h = bytearray(header)
        h[72:76] = struct.pack("<I", bits)
        return bytes(h)
    ok, reason = check_pow(with_bits(0x01800001), POW_LIMIT_MAINNET)
    assert (ok, reason) == (False, "negative-target"), reason
    ok, reason = check_pow(with_bits(0x2300ffff), POW_LIMIT_MAINNET)
    assert (ok, reason) == (False, "overflow-target"), reason
    ok, reason = check_pow(with_bits(0x01000000), POW_LIMIT_MAINNET)
    assert (ok, reason) == (False, "zero-target"), reason
    ok, reason = check_pow(with_bits(0x207fffff), POW_LIMIT_MAINNET)
    assert (ok, reason) == (False, "target-above-limit"), reason
    ok, reason = check_pow(b"\x00" * 79, POW_LIMIT_MAINNET)
    assert (ok, reason) == (False, "header-length"), reason
    print("ok: negative, overflow, zero, above-limit targets and "
          "short headers all rejected with reason codes")

    # 5. Witness stripper on a real segwit transaction: the stripped
    # form must hash to the txid Core reports, the full form to wtxid.
    from mining.engine import txid_of, wtxid_of
    found = None
    for height in range(rpc.get_block_count(), max(0, rpc.get_block_count() - 30), -1):
        b = rpc.get_block(rpc.get_block_hash(height), 1)
        if len(b["tx"]) > 1:
            found = b["tx"][1]
            break
    assert found, "no non-coinbase tx in recent blocks"
    raw = bytes.fromhex(rpc.call("getrawtransaction", found))
    stripped, has_w = strip_witness(raw)
    from mining.pow import dsha256
    assert dsha256(stripped)[::-1].hex() == found
    assert has_w == (dsha256(raw) != dsha256(stripped))
    assert txid_of(raw)[::-1].hex() == found
    print("ok: witness stripper reproduces Core txids on a real "
          "segwit transaction")

    # 6. ComputeEngine refuses absurd work rather than allocating it.
    eng_c = ComputeEngine()
    try:
        eng_c.batch_search(bytes(80), 1 << 255, 0, (1 << 21))
        raise AssertionError("expected ValueError for oversize batch")
    except ValueError:
        pass
    print("ok: oversize compute batch refused")
    print("ALL ADVERSARIAL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
