#!/usr/bin/env python3
"""Deepening tests (post Task 006): C compute backend, event-driven
monitoring, GBT longpoll, watch-only tracking, peered second node,
and the live dashboard.
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from blockchain.service import MonitorService
from blockchain.store import BlockStore
from blockchain.watch import WatchWallet
from gpu.engine import ComputeEngine, cpu_digest
from mining.cpu.build import build as build_c
from mining.engine import MiningEngine
from node import node_manager, peer_node
from node.rpc_client import BitcoinRPC


def wallet_rpc(rpc):
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    return BitcoinRPC(wallet="bal-regtest")


def test_c_backend():
    built = build_c(log=lambda *a: None)
    assert built["lib"], built
    eng = ComputeEngine()
    assert eng.backend == "c", eng.describe()
    bench = eng.benchmark()
    py = ComputeEngine(requested="cpu")
    assert py.backend == "cpu"
    py_bench = py.benchmark()
    assert bench > py_bench * 2, (bench, py_bench)
    header = bytes(range(80))
    cands, stats = eng.batch_search(header, 1 << 240, 0, 65536)
    assert stats["backend"] == "c"
    for c in cands:
        assert cpu_digest(header, c["nonce"])[::-1].hex() == c["hash"]
    print(f"ok: C midstate backend selected, benchmark {bench:,.0f} H/s "
          f"vs python {py_bench:,.0f} H/s, candidates verified")


def test_event_driven(rpc, wallet):
    store = BlockStore(os.path.join(tempfile.mkdtemp(), "ev.db"))
    service = MonitorService(rpc, store, poll_seconds=0.2)
    service.sync_once()  # pre-sync: the timed section measures wake latency
    addr = wallet.call("getnewaddress", "", "bech32")

    def mine_later():
        time.sleep(1.0)
        rpc.call("generatetoaddress", 1, addr)

    threading.Thread(target=mine_later, daemon=True).start()
    started = time.time()
    result = service.run_event_driven(max_waits=1, wait_timeout_ms=30000)
    elapsed = time.time() - started
    assert result["wakeups"] == 1, result
    assert store.get_sync()["tip_height"] == rpc.get_block_count()
    assert elapsed < 20, elapsed
    print(f"ok: event-driven monitor woke on the new block and synced "
          f"(wait cycle {elapsed:.1f}s incl 1s delayed mining)")


def test_longpoll(rpc, wallet):
    eng = MiningEngine(rpc, wallet.call("getnewaddress", "", "bech32"))
    template = eng.get_template()
    addr = wallet.call("getnewaddress", "", "bech32")

    def mine_later():
        time.sleep(1.0)
        rpc.call("generatetoaddress", 1, addr)

    threading.Thread(target=mine_later, daemon=True).start()
    started = time.time()
    fresh = eng.wait_template(template["longpollid"], timeout_s=30)
    elapsed = time.time() - started
    assert fresh["height"] == template["height"] + 1, fresh["height"]
    assert elapsed < 25, elapsed
    print(f"ok: GBT longpoll returned the next template at height "
          f"{fresh['height']} after {elapsed:.1f}s")


def test_watch(rpc, wallet):
    watcher = WatchWallet(rpc)
    # A fresh address in the spending wallet, watched from outside it.
    target = wallet.call("getnewaddress", "", "bech32")
    watcher.watch(target)
    if rpc.call("getmempoolinfo")["size"]:
        rpc.call("generatetoaddress", 1,
                 wallet.call("getnewaddress", "", "bech32"))
    txid = wallet.call("sendtoaddress", target, 0.33)
    rpc.call("generatetoaddress", 1,
             wallet.call("getnewaddress", "", "bech32"))
    received = watcher.received(target)
    assert any(t["txid"] == txid for t in received), received
    scan = watcher.scan_balance(target)
    assert scan["total_sats"] == 33_000_000, scan
    utxos = watcher.utxos(target)
    assert any(u["txid"] == txid for u in utxos)
    print(f"ok: watch-only wallet saw the incoming 0.33 BTC payment; "
          f"scantxoutset cross-check agrees ({scan['total_sats']} sats)")


def test_peer_node(rpc, wallet):
    assert peer_node.start(), "peer node failed to start"
    peers = peer_node.connect_to_primary()
    assert peers, "no peer connection"
    node2 = peer_node.client()
    addr = wallet.call("getnewaddress", "", "bech32")
    deadline = time.time() + 60
    while node2.get_block_count() < rpc.get_block_count() \
            and time.time() < deadline:
        time.sleep(0.5)
    assert node2.get_best_block_hash() == rpc.get_best_block_hash()
    synced_to = node2.get_block_count()
    rpc.call("generatetoaddress", 2, addr)
    deadline = time.time() + 30
    while node2.get_block_count() < rpc.get_block_count() \
            and time.time() < deadline:
        time.sleep(0.3)
    assert node2.get_best_block_hash() == rpc.get_best_block_hash()
    print(f"ok: peer node synced the full chain ({synced_to} blocks) "
          f"and followed 2 newly mined blocks over P2P")


def test_dashboard(rpc):
    import subprocess
    proc = subprocess.Popen(
        [sys.executable, "-m", "dashboard.server", "18765"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 30
        data = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:18765/api/status",
                        timeout=10) as resp:
                    data = json.load(resp)
                break
            except Exception:
                time.sleep(0.5)
        assert data, "dashboard API never answered"
        assert data["chain"]["blocks"] == rpc.get_block_count()
        assert data["compute"]["backend"] in ("c", "cuda", "cpu")
        with urllib.request.urlopen("http://127.0.0.1:18765/",
                                    timeout=10) as resp:
            page = resp.read().decode()
        assert "Bitcoin Autonomous Lab" in page
        print(f"ok: dashboard serves live status (height "
              f"{data['chain']['blocks']}, backend "
              f"{data['compute']['backend']}) and the page")
    finally:
        proc.terminate()


def main():
    node_manager.start()
    rpc = BitcoinRPC()
    wallet = wallet_rpc(rpc)
    test_c_backend()
    test_event_driven(rpc, wallet)
    test_longpoll(rpc, wallet)
    test_watch(rpc, wallet)
    test_peer_node(rpc, wallet)
    test_dashboard(rpc)
    print("ALL DEEPENING TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
