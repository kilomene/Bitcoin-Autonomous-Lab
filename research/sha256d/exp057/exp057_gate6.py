"""EXP-057 Gate 6: a regtest block produced through the tier.

Shape (predeclaration): a downstream worker connects to
the aggregation tier over TCP stratum, authorizes with its
enrollment token (fleet identity), receives the tier's
workbase, mines it with the lab ComputeEngine, and submits
the winning share to the tier. The tier validates it
through EXP-036 verify_candidate and queues it as a
pending candidate: the chain tip must provably NOT move.
Only the explicit operator action (operator token plus an
explicitly wired SoloServer submitter) submits the block;
it counts only when the node holds it on its active chain
(verify_chain_acceptance) and the height advanced by
exactly one.

Regtest only. No other machine is contacted.
"""

import hashlib
import json
import os
import socket
import sys
import threading
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from exp057_campaign import PREDECLARATION_SHA256  # noqa: E402
from mining.aggregation import (AggregationTCPServer,  # noqa: E402
                                AggregationTier, IdentityError)
from mining.candidate_verify import verify_chain_acceptance  # noqa: E402

FLEET = "nova-fleet-exp057-gate6"
PORT = 33457


def check_predeclaration():
    with open(os.path.join(HERE, "PREDECLARATION.md"),
              "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() \
            == PREDECLARATION_SHA256


class Worker:
    def __init__(self, worker_id, token):
        self.sock = socket.create_connection(("127.0.0.1", PORT),
                                             timeout=60)
        self.f = self.sock.makefile("rwb")
        self._id = 0
        self.en1 = None
        self.job = None
        self.share_diff = None
        self.worker_id = worker_id
        self.token = token

    def send(self, obj):
        self.f.write((json.dumps(obj) + "\n").encode())
        self.f.flush()

    def rpc(self, method, params):
        self._id += 1
        self.send({"id": self._id, "method": method,
                   "params": params})
        while True:
            msg = json.loads(self.f.readline())
            if msg.get("id") == self._id:
                return msg
            self._notify(msg)

    def _notify(self, msg):
        if msg.get("method") == "mining.set_extranonce":
            self.en1 = msg["params"][0]
        elif msg.get("method") == "mining.set_difficulty":
            self.share_diff = msg["params"][0]
        elif msg.get("method") == "mining.notify":
            p = msg["params"]
            self.job = {"job_id": p[0], "prevhash": p[1],
                        "coinb1": p[2], "coinb2": p[3],
                        "merkle_branch": p[4], "version": p[5],
                        "nbits": p[6], "ntime": p[7]}

    def read_until_ready(self, timeout=30):
        self.sock.settimeout(timeout)
        while self.job is None or self.en1 is None:
            msg = json.loads(self.f.readline())
            if msg.get("id") is not None:
                continue
            self._notify(msg)

    def close(self):
        self.sock.close()


def main():
    check_predeclaration()
    from gpu.engine import ComputeEngine
    from mining.stratum_client import (build_header,
                                       target_for_difficulty)
    from node import node_manager
    from node.rpc_client import BitcoinRPC

    node_manager.start()
    rpc = BitcoinRPC()
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    wallet = BitcoinRPC(wallet="bal-regtest")
    payout = wallet.call("getnewaddress", "", "bech32")

    tier = AggregationTier(
        rpc, payout, FLEET, share_difficulty=0.01,
        expected_chain="regtest", operator_token="op-gate6")
    tier.enroll_worker("gate6-w1", "tok-gate6-w1")
    tier.enroll_worker("gate6-w2", "tok-gate6-w2")
    tier.refresh_workbase()
    server = AggregationTCPServer(("127.0.0.1", PORT), tier)
    th = threading.Thread(target=server.serve_forever,
                          daemon=True)
    th.start()
    tip0 = rpc.get_block_count()
    try:
        # A spoofed authorize must fail before any mining.
        bad = Worker.__new__(Worker)
        bad.sock = socket.create_connection(("127.0.0.1", PORT),
                                            timeout=30)
        bad.f = bad.sock.makefile("rwb")
        bad._id = 0
        bad.en1 = None
        bad.job = None
        bad.share_diff = None
        r = bad.rpc("mining.authorize", ["gate6-w1", "wrong"])
        assert r["result"] is False, r
        bad.sock.close()

        w = Worker("gate6-w1", "tok-gate6-w1")
        r = w.rpc("mining.subscribe", ["exp057-gate6/1.0"])
        r = w.rpc("mining.authorize",
                  ["gate6-w1", "tok-gate6-w1"])
        assert r["result"] is True, r
        w.read_until_ready()
        job = dict(w.job)
        engine = ComputeEngine()
        found = None
        en2 = 0
        deadline = time.time() + 240
        while time.time() < deadline and not found:
            en2 += 1
            en2_hex = "%08x" % en2
            start = 0
            while start < (1 << 32) and time.time() < deadline:
                hdr0, _, _ = build_header(job, w.en1, en2_hex, 0,
                                          "wordswap")
                target = target_for_difficulty(w.share_diff)
                hit = engine.search_first(hdr0, target, start,
                                          1 << 22)
                if not hit:
                    start += 1 << 22
                    continue
                nonce, _digest = hit
                resp = w.rpc("mining.submit",
                             ["gate6-w1", job["job_id"], en2_hex,
                              job["ntime"], "%08x" % nonce])
                assert resp["result"] is True, resp
                found = (en2_hex, nonce)
                break
        assert found, "no winning share through the tier"
        # The tier queued the candidate and did NOT submit:
        # the tip is provably unmoved.
        assert rpc.get_block_count() == tip0
        assert tier.upstream_submissions == 0
        assert len(tier.pending_candidates) == 1, \
            tier.pending_candidates
        cand = tier.pending_candidates[0]
        assert cand["worker"] == "gate6-w1"
        assert cand["stale"] is False
        # Wrong operator token refuses.
        try:
            tier.operator_submit_pending("wrong-token")
            raise AssertionError("bad operator token accepted")
        except IdentityError:
            pass
        assert len(tier.pending_candidates) == 1
        # The explicit operator action: wire the submitter,
        # then submit.
        tier.set_submitter(tier.solo_submitter)
        rec = tier.operator_submit_pending("op-gate6")
        assert rec["accepted"], rec
        assert tier.upstream_submissions == 1
        status, accepted = verify_chain_acceptance(rpc,
                                                   rec["hash"])
        assert accepted, (status, rec)
        tip1 = rpc.get_block_count()
        assert tip1 == tip0 + 1, (tip0, tip1)
        assert rpc.get_best_block_hash() == rec["hash"]
        tier.assert_accounting_identity()
        acct = tier.accounting()
        w.close()
    finally:
        server.shutdown()
        server.server_close()
    out = {"height": rec["height"], "hash": rec["hash"],
           "worker": cand["worker"], "tip_before": tip0,
           "tip_after": tip1, "chain_status": status,
           "upstream_submissions": tier.upstream_submissions,
           "accounting_categories": acct["categories"]}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    record = {"experiment": "EXP-057", "gate": 6,
              "host_cpu": "AMD EPYC 9D25", "when_utc": stamp,
              "predeclaration_sha256": PREDECLARATION_SHA256,
              "result": out}
    path = os.path.join(HERE, "RAW_RESULTS",
                        "gate6_%s.json" % stamp)
    with open(path, "w") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
    print("WROTE", path, flush=True)
    print("EXP-057 GATE 6 PASSED:", out, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
