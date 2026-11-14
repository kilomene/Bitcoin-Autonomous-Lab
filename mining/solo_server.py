"""Solo mining server: our own Stratum V1 pool of one.

The full solo stack, ours end to end: Bitcoin Core supplies
getblocktemplate; this server turns templates into Stratum jobs,
validates shares with the lab's own PoW engine, and when a share
meets the NETWORK target it assembles the complete block and
submits it via submitblock. No third-party pool anywhere.

Conventions match Stratum V1 as implemented by the lab's client
(mining/stratum_client.py), whose header builder is reused by the
test worker so client and server can disagree loudly in tests if
either side drifts.

Job model: the coinbase scriptSig carries an 8-byte extranonce
slot (extranonce1 = per-connection, extranonce2 = per-share).
The server keeps the full template, so on a block candidate it
rebuilds the exact block (coinbase with the submitted extranonce,
the template's transactions verbatim) and submits it.
"""

import json
import socket
import socketserver
import struct
import threading
import time

from mining.pow import dsha256 as double_sha256
from mining.pow import merkle_root, target_from_nbits


def _varint(n):
    if n < 0xfd:
        return bytes([n])
    if n <= 0xffff:
        return b"\xfd" + struct.pack("<H", n)
    return b"\xfe" + struct.pack("<I", n)


def merkle_branch(txids):
    """Stratum merkle branch for the coinbase at index 0. The full
    layer includes the coinbase as element 0 (a dummy stands in for
    it: the branch only ever reads siblings of the coinbase path,
    and the one parent that would depend on the coinbase value is
    never a sibling on that path)."""
    branch = []
    layer = [bytes(32)] + list(txids)
    idx = 0
    while len(layer) > 1:
        sib = idx ^ 1
        branch.append(layer[sib] if sib < len(layer) else layer[idx])
        layer = [double_sha256(
            layer[i] + (layer[i + 1] if i + 1 < len(layer) else layer[i]))
            for i in range(0, len(layer), 2)]
        idx //= 2
    return branch


class SoloServer:
    def __init__(self, rpc, payout_address, share_difficulty=0.01,
                 tag=b"/BAL-solo/"):
        self.rpc = rpc
        self.payout = payout_address
        # Stratum difficulty 1 target: 0x00000000FFFF followed by
        # 26 zero bytes; share target = DIFF1 / difficulty.
        diff1 = int("00000000ffff" + "00" * 26, 16)
        self.share_target = (int(diff1 / share_difficulty)
                             if share_difficulty else 0)
        self.tag = tag
        self.jobs = {}
        self.job_seq = 0
        self.lock = threading.Lock()
        self.blocks_found = []
        self.shares_accepted = 0
        self.shares_rejected = 0
        self.current = None
        self._stop = False

    # -- job construction -------------------------------------------------
    def refresh_job(self):
        from mining.engine import (address_script_pubkey, build_coinbase)
        t = self.rpc.call("getblocktemplate", {"rules": ["segwit"]})
        # Build the coinbase with the lab engine's own builder, with
        # an 8-byte placeholder where the extranonce pair will land.
        # The engine builder handles BIP34, the payout output, and
        # the segwit witness commitment exactly as direct mining does.
        placeholder = b"\xee" * 8
        script = address_script_pubkey(self.rpc, self.payout)
        commitment = None
        if t.get("default_witness_commitment"):
            commitment = bytes.fromhex(
                t["default_witness_commitment"])[6:]
        coinbase, _ = build_coinbase(
            t["height"], t["coinbasevalue"], script, placeholder,
            witness_commitment=commitment)
        marker = b"/BAL/" + placeholder
        at = coinbase.index(marker) + len(b"/BAL/")
        # Serve the STRIPPED coinbase over Stratum: the worker hashes
        # what it assembles, and that hash must be the coinbase txid
        # (which excludes witness data). The server re-attaches the
        # witness (the fixed 32-byte reserved value) when it
        # assembles a winning block, which is exactly the form the
        # template's witness commitment was computed over.
        from mining.engine import strip_witness
        stripped, has_witness = strip_witness(coinbase)
        coinb1 = stripped[:at]
        coinb2 = stripped[at + 8:]
        txids = [bytes.fromhex(tx["txid"])[::-1] for tx in t["transactions"]]
        branch = merkle_branch(txids)
        with self.lock:
            self.job_seq += 1
            job = {
                "job_id": f"{self.job_seq:x}",
                "template": t,
                "has_witness": bool(has_witness),
                "coinb1": coinb1, "coinb2": coinb2,
                "branch": branch,
                "txids": txids,
                "target": target_from_nbits(int(t["bits"], 16)),
            }
            self.jobs = {job["job_id"]: job}
            self.current = job
        return job

    def notify_params(self, job):
        t = job["template"]
        prev = bytes.fromhex(t["previousblockhash"])[::-1]
        prev_swapped = b"".join(prev[i:i + 4][::-1]
                                for i in range(0, 32, 4))
        return [job["job_id"], prev_swapped.hex(),
                job["coinb1"].hex(), job["coinb2"].hex(),
                [b.hex() for b in job["branch"]],
                f'{t["version"]:08x}', t["bits"],
                f'{t["curtime"]:08x}', True]

    # -- share validation ---------------------------------------------------
    def validate_share(self, job, extranonce1, extranonce2_hex, ntime_hex,
                       nonce_hex):
        en2 = bytes.fromhex(extranonce2_hex)
        if len(en2) != 4:
            return None, "bad extranonce2 size"
        coinbase = job["coinb1"] + extranonce1 + en2 + job["coinb2"]
        cb_txid = double_sha256(coinbase)  # served stripped: this is the txid
        # Full root via stored txids (server has the whole template).
        root = merkle_root([cb_txid] + job["txids"])
        t = job["template"]
        header = (
            struct.pack("<i", t["version"])
            + bytes.fromhex(t["previousblockhash"])[::-1]
            + root
            + struct.pack("<I", int(ntime_hex, 16))
            + struct.pack("<I", int(t["bits"], 16))
            + struct.pack("<I", int(nonce_hex, 16)))
        digest = double_sha256(header)
        value = int.from_bytes(digest, "little")
        return ({"header": header, "digest": digest, "value": value,
                 "coinbase": coinbase}, None)

    def submit_share(self, job_id, extranonce1, en2, ntime, nonce):
        with self.lock:
            job = self.jobs.get(job_id)
        if not job:
            self.shares_rejected += 1
            return {"accepted": False, "reason": "unknown job"}
        res, err = self.validate_share(job, extranonce1, en2, ntime, nonce)
        if err:
            self.shares_rejected += 1
            return {"accepted": False, "reason": err}
        is_block = res["value"] <= job["target"]
        is_share = res["value"] <= self.share_target
        if is_block:
            t = job["template"]
            txs = b"".join(bytes.fromhex(tx["data"])
                           for tx in t["transactions"])
            coinbase = res["coinbase"]
            if job.get("has_witness"):
                # Re-attach the coinbase witness: marker and flag
                # after the version, one stack item holding the
                # 32-byte reserved value before the locktime.
                coinbase = (coinbase[:4] + b"\x00\x01" + coinbase[4:-4]
                            + b"\x01\x20" + bytes(32) + coinbase[-4:])
            block = (res["header"] + _varint(1 + len(t["transactions"]))
                     + coinbase + txs)
            r = self.rpc.call("submitblock", block.hex())
            ok = r is None
            rec = {"height": t["height"], "hash": res["digest"][::-1].hex(),
                   "submit_result": r, "accepted": ok}
            self.blocks_found.append(rec)
            self.shares_accepted += 1
            return {"accepted": True, "block": rec}
        if is_share:
            self.shares_accepted += 1
            return {"accepted": True, "block": None}
        self.shares_rejected += 1
        return {"accepted": False, "reason": "low difficulty share"}


class _Handler(socketserver.StreamRequestHandler):
    def setup(self):
        super().setup()
        try:  # signals travel immediately: no Nagle delay on jobs
            self.request.setsockopt(
                socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass

    def handle(self):
        srv: SoloServer = self.server.solo
        extranonce1 = self.server.next_en1()
        with self.server.clients_lock:
            self.server.clients.add(self)
        try:
            self._run(srv, extranonce1)
        finally:
            with self.server.clients_lock:
                self.server.clients.discard(self)

    def _run(self, srv, extranonce1):
        authorized = False
        subscribed = False
        for raw in self.rfile:
            try:
                msg = json.loads(raw.decode())
            except Exception:
                continue
            method = msg.get("method")
            mid = msg.get("id")
            if method == "mining.subscribe":
                subscribed = True
                self._send({"id": mid, "result": [
                    [["mining.set_difficulty", "bal1"],
                     ["mining.notify", "bal2"]],
                    extranonce1.hex(), 4], "error": None})
                diff = 0.01
                self._send({"id": None, "method": "mining.set_difficulty",
                            "params": [self.server.share_difficulty]})
                job = srv.current or srv.refresh_job()
                self._send({"id": None, "method": "mining.notify",
                            "params": srv.notify_params(job)})
            elif method == "mining.authorize":
                authorized = True
                self._send({"id": mid, "result": True, "error": None})
            elif method == "mining.submit":
                worker, job_id, en2, ntime, nonce = msg["params"]
                out = srv.submit_share(job_id, extranonce1, en2, ntime,
                                       nonce)
                self._send({"id": mid, "result": out["accepted"],
                            "error": None if out["accepted"]
                            else [20, out["reason"], None]})
                if out.get("block"):
                    job = srv.refresh_job()
                    self._broadcast(job)
            else:
                self._send({"id": mid, "result": None,
                            "error": [501, "unknown method", None]})

    def _send(self, obj):
        self.wfile.write((json.dumps(obj) + "\n").encode())
        self.wfile.flush()

    def _broadcast(self, job):
        srv: SoloServer = self.server.solo
        with self.server.clients_lock:
            clients = list(self.server.clients)
        for h in clients:
            try:
                h._send({"id": None, "method": "mining.notify",
                         "params": srv.notify_params(job)})
            except Exception:
                pass


class SoloTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, solo: SoloServer, share_difficulty=0.01):
        self.solo = solo
        self.share_difficulty = share_difficulty
        self._en1 = 0
        self._en1_lock = threading.Lock()
        self.clients = set()
        self.clients_lock = threading.Lock()
        super().__init__(addr, _Handler)

    def next_en1(self):
        with self._en1_lock:
            self._en1 += 1
            return self._en1.to_bytes(4, "little")
