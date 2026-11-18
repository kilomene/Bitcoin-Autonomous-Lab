#!/usr/bin/env python3
"""Stage 9 fleet staging: a local Stratum V1 stub pool.

This is a test double for public-pool.io, used ONLY on
loopback in the fleet staging. It speaks enough Stratum V1
to serve one gateway session: subscribe (assigning a fixed
extranonce1 and a 4-byte extranonce2 space), authorize,
set_difficulty, one mining.notify job, and mining.submit
judgment. Its job is synthetic in content (a fabricated
prevhash and coinbase split) but structurally real: the
header fields, the nbits value (a real recent mainnet
nbits, 0x17021673) and the share judgment are the real
protocol shapes, and every submitted share is judged by
reconstructing the exact 80-byte header with the
production build_header and comparing the double SHA-256
digest against the exact difficulty target, the same
compare the gateway's verifier performs.

The stub is the duplicate oracle for the staging: it keys
every accepted share on (job_id, extranonce2, ntime,
nonce) and refuses a second submission of the same key as
a duplicate, logging it as its own category. Every submit
and its verdict is appended to a JSONL log the driver
audits after the run.

Nothing here is production code and nothing here ever
faces a real network: it binds 127.0.0.1 only.
"""

import argparse
import hashlib
import json
import socketserver
import sys
import threading
import time

sys.path.insert(0, "/home/hatch/workspace/bitcoin-autonomous-lab")

from mining.stratum_client import build_header, dsha256, \
    target_for_difficulty

JOB = {
    "job_id": "stub-0001",
    "prevhash": hashlib.sha256(
        b"fleet staging prevhash").hexdigest(),
    # Synthetic coinbase split. The bytes are fabricated;
    # only their role in header construction is real (the
    # coinbase is coinb1 + extranonce1 + extranonce2 +
    # coinb2, hashed into the merkle root).
    "coinb1": "0100000001000000000000000000000000000000000000"
              "000000000000000000000000000000ffffffff1c",
    "coinb2": "2f466c65657453746167696e672f000000000100f205"
              "2a010000001976a914"
              + "11" * 20 + "88ac00000000",
    "merkle_branch": [],
    "version": "20000000",
    "nbits": "17021673",
}


class StubPool:
    def __init__(self, share_difficulty, log_path):
        self.share_difficulty = share_difficulty
        self.target = target_for_difficulty(share_difficulty)
        self.extranonce1 = "a1b2c3d4"
        self.extranonce2_size = 4
        self.job = dict(JOB)
        self.job["ntime"] = "%08x" % int(time.time())
        self.lock = threading.Lock()
        self.accepted = {}       # key -> digest difficulty
        self.submits = 0
        self.duplicates = 0
        self.rejected = 0
        self.log_fh = open(log_path, "a", buffering=1)

    def log(self, event, **fields):
        rec = {"ts": time.time(), "event": event, **fields}
        with self.lock:
            self.log_fh.write(json.dumps(rec, sort_keys=True) + "\n")

    def notify_params(self):
        j = self.job
        return [j["job_id"], j["prevhash"], j["coinb1"],
                j["coinb2"], j["merkle_branch"], j["version"],
                j["nbits"], j["ntime"], True]

    def judge(self, user, job_id, en2, ntime, nonce_hex):
        self.submits += 1
        key = (job_id, en2, ntime, nonce_hex)
        if job_id != self.job["job_id"]:
            self.rejected += 1
            self.log("submit_judged", user=user, job_id=job_id,
                     extranonce2=en2, nonce=nonce_hex,
                     accepted=False, reason="unknown job")
            return False, [20, "unknown job", None]
        if key in self.accepted:
            self.duplicates += 1
            self.log("submit_judged", user=user, job_id=job_id,
                     extranonce2=en2, nonce=nonce_hex,
                     accepted=False, duplicate=True,
                     reason="duplicate share")
            return False, [22, "duplicate share", None]
        header, _m, _cb = build_header(
            self.job, self.extranonce1, en2,
            int(nonce_hex, 16), "wordswap")
        digest = dsha256(header)
        value = int.from_bytes(digest, "little")
        if value <= self.target:
            diff = (0xFFFF * (1 << 208)) / value if value else \
                float("inf")
            self.accepted[key] = diff
            self.log("submit_judged", user=user, job_id=job_id,
                     extranonce2=en2, nonce=nonce_hex,
                     accepted=True, difficulty=diff)
            return True, None
        self.rejected += 1
        self.log("submit_judged", user=user, job_id=job_id,
                 extranonce2=en2, nonce=nonce_hex,
                 accepted=False, reason="low difficulty share")
        return False, [20, "low difficulty share", None]


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        pool: StubPool = self.server.pool
        for raw in self.rfile:
            try:
                msg = json.loads(raw.decode())
            except Exception:
                continue
            method = msg.get("method")
            mid = msg.get("id")
            if method == "mining.subscribe":
                self._send({"id": mid, "result": [
                    [["mining.set_difficulty", "stub1"],
                     ["mining.notify", "stub2"]],
                    pool.extranonce1, pool.extranonce2_size],
                    "error": None})
            elif method == "mining.authorize":
                self._send({"id": mid, "result": True,
                            "error": None})
                self._send({"id": None,
                            "method": "mining.set_difficulty",
                            "params": [pool.share_difficulty]})
                self._send({"id": None, "method": "mining.notify",
                            "params": pool.notify_params()})
            elif method == "mining.suggest_difficulty":
                self._send({"id": mid, "result": True,
                            "error": None})
            elif method == "mining.submit":
                user, job_id, en2, ntime, nonce = msg["params"]
                ok, err = pool.judge(user, job_id, en2, ntime,
                                     nonce)
                self._send({"id": mid, "result": ok,
                            "error": err})
            else:
                self._send({"id": mid, "result": None,
                            "error": [501, "unknown method", None]})

    def _send(self, obj):
        self.wfile.write((json.dumps(obj) + "\n").encode())
        self.wfile.flush()


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, pool):
        self.pool = pool
        super().__init__(address, Handler)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--share-difficulty", type=float,
                    default=0.0002)
    ap.add_argument("--log", required=True)
    args = ap.parse_args()
    pool = StubPool(args.share_difficulty, args.log)
    pool.log("stub_up", port=args.port,
             share_difficulty=args.share_difficulty,
             job_id=pool.job["job_id"], ntime=pool.job["ntime"])
    Server(("127.0.0.1", args.port), pool).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
