#!/usr/bin/env python3
"""Solo stack test: our Stratum server + our worker + our engine.

A worker connects over TCP, subscribes, receives a job built from
a live getblocktemplate, mines it with the lab ComputeEngine, and
submits shares. The regtest network target is trivially easy, so
valid shares are also blocks: the server must assemble and submit
a block that Bitcoin Core accepts, and the chain tip must move.
"""

import json
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gpu.engine import ComputeEngine
from mining.solo_server import SoloServer, SoloTCPServer
from mining.stratum_client import build_header, target_for_difficulty
from node import node_manager
from node.rpc_client import BitcoinRPC

HOST, PORT = "127.0.0.1", 33399


def wallet_rpc(rpc):
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    return BitcoinRPC(wallet="bal-regtest")


class Worker:
    def __init__(self, payout):
        self.sock = socket.create_connection((HOST, PORT), timeout=30)
        self.f = self.sock.makefile("rwb")
        self.payout = payout
        self.en1 = None
        self.job = None
        self.share_diff = 0.01
        self.results = {}
        self._id = 0

    def send(self, obj):
        self.f.write((json.dumps(obj) + "\n").encode())
        self.f.flush()

    def rpc(self, method, params):
        self._id += 1
        self.send({"id": self._id, "method": method, "params": params})
        while True:
            msg = json.loads(self.f.readline())
            if msg.get("id") == self._id:
                return msg
            self.handle_notify(msg)

    def handle_notify(self, msg):
        if msg.get("method") == "mining.set_difficulty":
            self.share_diff = msg["params"][0]
        elif msg.get("method") == "mining.notify":
            p = msg["params"]
            self.job = {"job_id": p[0], "prevhash": p[1], "coinb1": p[2],
                        "coinb2": p[3], "merkle_branch": p[4],
                        "version": p[5], "nbits": p[6], "ntime": p[7]}

    def read_until_job(self, timeout=20):
        self.sock.settimeout(timeout)
        while self.job is None:
            msg = json.loads(self.f.readline())
            if msg.get("id") is not None:
                continue
            self.handle_notify(msg)


def main():
    node_manager.start()
    rpc = BitcoinRPC()
    wallet = wallet_rpc(rpc)
    payout = wallet.call("getnewaddress", "", "bech32")

    solo = SoloServer(rpc, payout, share_difficulty=0.01)
    server = SoloTCPServer((HOST, PORT), solo, share_difficulty=0.01)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    try:
        w = Worker(payout)
        r = w.rpc("mining.subscribe", ["bal-worker/1.0"])
        w.en1 = r["result"][1]
        assert len(bytes.fromhex(w.en1)) == 4
        r = w.rpc("mining.authorize", [payout, "x"])
        assert r["result"] is True
        w.read_until_job()
        job = dict(w.job)
        print(f"ok: worker subscribed, job {job['job_id']} received")

        engine = ComputeEngine()
        net_target = None
        tip0 = rpc.get_block_count()
        found_block = None
        en2 = 0
        deadline = time.time() + 240
        while time.time() < deadline and not found_block:
            en2 += 1
            en2_hex = f"{en2:08x}"
            # Probe header at nonce 0 to recover the template target
            # from the server side: mine the extranonce space.
            start = 0
            while start < (1 << 32) and time.time() < deadline:
                hdr0, _, _ = build_header(job, w.en1, en2_hex, 0,
                                          "wordswap")
                # The network target on regtest is huge; use the
                # share target to find ANY valid share quickly, then
                # submit the best as block candidate too: at regtest
                # bits, share winners are block winners.
                target = target_for_difficulty(w.share_diff)
                hit = engine.search_first(hdr0, target, start, 1 << 22)
                if not hit:
                    start += 1 << 22
                    continue
                nonce, digest = hit
                resp = w.rpc("mining.submit",
                             [payout, job["job_id"], en2_hex,
                              job["ntime"], f"{nonce:08x}"])
                assert resp["result"] is True, resp
                if solo.blocks_found:
                    found_block = solo.blocks_found[-1]
                break
            if not found_block:
                # Block may require a fresh job; poll server state.
                if solo.blocks_found:
                    found_block = solo.blocks_found[-1]
                else:
                    w.job = None
                    try:
                        w.read_until_job(5)
                        job = dict(w.job)
                    except Exception:
                        pass
        assert found_block, "no block submitted through the solo server"
        assert found_block["accepted"], found_block
        assert rpc.get_block_count() == tip0 + 1
        assert rpc.get_best_block_hash() == found_block["hash"]
        print(f"ok: solo-mined block accepted by Core at height "
              f"{found_block['height']}: {found_block['hash']}")
        print(f"shares accepted {solo.shares_accepted}, "
              f"rejected {solo.shares_rejected}")
        print("ALL SOLO SERVER TESTS PASSED")
        return 0
    finally:
        server.shutdown()


if __name__ == "__main__":
    sys.exit(main())
