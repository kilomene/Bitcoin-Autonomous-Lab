#!/usr/bin/env python3
"""EXP-057 deployment staging verification (Stage 9
enablements, 2026-11-18).

Stands the production tier runner
(mining/aggregation_mainnet.py) up in its deployment
configuration against the isolated regtest node
(.local/enablements/regtest), with a staging fleet
definition written to .local/enablements/ (never
committed), and proves end to end over real TCP Stratum:

  1. the runner starts, verifies the chain, restores or
     creates its state, and publishes a status file with a
     current job;
  2. an enrolled worker authorizes, receives a job, finds
     a real share at the tier's share difficulty by
     hashing real headers in this driver, submits it, and
     the tier accepts it (EXP-036 judgment path) and
     accounts it under that worker;
  3. a foreign worker (unenrolled id, and the enrolled id
     with a wrong token) is refused at authorize;
  4. on shutdown the runner writes its snapshot; the
     snapshot carries the enrollment and the accepted
     share's accounting.

Share difficulty is set very low (0.0001) so the Python
search in this driver finds shares in seconds; the point
is the deployment path, not rate. Nothing here touches
the live mainnet stack or the armed solo cutover.

Usage: python3 run_aggregation_staging.py
"""

import hashlib
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

from mining.solo_server import share_target_for

STAGE = os.path.join(ROOT, ".local", "enablements")
DEPLOYMENT = os.path.join(STAGE, "aggregation-tier.json")
STATUS = os.path.join(STAGE, "aggregation-status.json")
SNAPSHOT = os.path.join(STAGE, "aggregation-snapshot.json")
NODE_CONFIG = os.path.join(STAGE, "regtest",
                           "node-config.json")
PORT = 3334
SHARE_DIFFICULTY = 0.0001
FLEET_ID = "bal-staging-fleet"
WORKER = "stage-worker-1"
TOKEN = "staging-token-not-a-secret"
OPERATOR_TOKEN = "staging-operator-not-a-secret"


def dsha(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def write_deployment():
    with open(os.path.join(STAGE, "regtest", "payout.txt")) as f:
        payout = f.read().strip()
    dep = {"fleet_id": FLEET_ID,
           "operator_token": OPERATOR_TOKEN,
           "payout_address": payout,
           "workers": [{"worker_id": WORKER, "token": TOKEN}]}
    with open(DEPLOYMENT, "w") as f:
        json.dump(dep, f, indent=2)
    os.chmod(DEPLOYMENT, 0o600)


class Stratum:
    def __init__(self, port):
        self.sock = socket.create_connection(
            ("127.0.0.1", port), timeout=30)
        self.buf = b""
        self.next_id = 0

    def _read_msg(self):
        while b"\n" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("tier closed connection")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def call(self, method, params):
        self.next_id += 1
        mid = self.next_id
        self.sock.sendall((json.dumps(
            {"id": mid, "method": method,
             "params": params}) + "\n").encode())
        notes = []
        while True:
            msg = self._read_msg()
            if msg.get("id") == mid:
                return msg, notes
            notes.append(msg)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def find_share(job, en1_hex, target):
    job_id, prev_swapped, coinb1, coinb2, branch, \
        version, bits, ntime, _clean = job
    en1 = bytes.fromhex(en1_hex)
    en2 = bytes.fromhex("00000000")
    coinbase = bytes.fromhex(coinb1) + en1 + en2 \
        + bytes.fromhex(coinb2)
    root = dsha(coinbase)
    for b in branch:
        root = dsha(root + bytes.fromhex(b))
    prev = b"".join(
        bytes.fromhex(prev_swapped)[i:i + 4][::-1]
        for i in range(0, 32, 4))
    ver = int(version, 16)
    nt = int(ntime, 16)
    nb = int(bits, 16)
    nonce = 0
    while nonce < (1 << 32):
        header = (struct.pack("<i", ver) + prev + root
                  + struct.pack("<I", nt)
                  + struct.pack("<I", nb)
                  + struct.pack("<I", nonce))
        if int.from_bytes(dsha(header), "little") <= target:
            return job_id, "00000000", ntime, f"{nonce:08x}"
        nonce += 1
    raise RuntimeError("no share found in the nonce space")


def wait_status(pred, timeout=60.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with open(STATUS) as f:
                st = json.load(f)
            if pred(st):
                return st
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise TimeoutError("status condition not met")


def main():
    write_deployment()
    for p in (STATUS, SNAPSHOT):
        if os.path.exists(p):
            os.unlink(p)
    proc = subprocess.Popen(
        [sys.executable,
         os.path.join(ROOT, "mining", "aggregation_mainnet.py"),
         "--node-config", NODE_CONFIG, "--chain", "regtest",
         "--deployment", DEPLOYMENT, "--status-path", STATUS,
         "--snapshot-path", SNAPSHOT,
         "--share-difficulty", str(SHARE_DIFFICULTY)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True)
    out = {"port": PORT, "share_difficulty": SHARE_DIFFICULTY}
    try:
        st = wait_status(lambda s: s.get("current_job"))
        out["status_at_start"] = {
            "fleet_id": st["fleet_id"], "epoch": st["epoch"],
            "workers_enrolled": st["workers_enrolled"],
            "current_job": st["current_job"],
            "node_ready": st["node_ready"]}
        # Enrolled worker: full session and a real share.
        c = Stratum(PORT)
        sub, _ = c.call("mining.subscribe", ["bal-staging/0.1"])
        auth, notes = c.call("mining.authorize", [WORKER, TOKEN])
        assert auth.get("result") is True, auth
        # The tier sends set_extranonce and the first notify
        # AFTER the authorize response; drain until both
        # have arrived.
        en1_hex = None
        job = None
        pending = list(notes)
        while en1_hex is None or job is None:
            if pending:
                n = pending.pop(0)
            else:
                n = c._read_msg()
            if n.get("method") == "mining.set_extranonce":
                en1_hex = n["params"][0]
            if n.get("method") == "mining.notify":
                job = n["params"]
        assert en1_hex and job
        target = share_target_for(SHARE_DIFFICULTY)
        job_id, en2, ntime, nonce = find_share(job, en1_hex,
                                               target)
        sub_res, _ = c.call(
            "mining.submit",
            [WORKER, job_id, en2, ntime, nonce])
        out["share_submit_result"] = sub_res.get("result")
        out["share_submit_error"] = sub_res.get("error")
        c.close()
        # Foreign worker and wrong token: refused.
        refused = {}
        for label, params in (
                ("unenrolled", ["ghost-worker", TOKEN]),
                ("wrong_token", [WORKER, "not-the-token"])):
            c2 = Stratum(PORT)
            c2.call("mining.subscribe", ["bal-staging/0.1"])
            r, _ = c2.call("mining.authorize", params)
            refused[label] = (r.get("result") is False)
            c2.close()
        out["refusals"] = refused
        st = wait_status(
            lambda s: s["counters"].get("accepted", 0) >= 1)
        out["tier_counters"] = st["counters"]
        out["per_worker"] = st["per_worker"]
        out["pending_candidates"] = st["pending_candidates"]
        out["upstream_submissions"] = st["upstream_submissions"]
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            stdout, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, _ = proc.communicate()
        out["runner_exit"] = proc.returncode
        out["runner_log_tail"] = stdout.strip().splitlines()[-6:]
    snap = None
    if os.path.exists(SNAPSHOT):
        with open(SNAPSHOT) as f:
            snap = json.load(f)
    out["snapshot"] = None if snap is None else {
        "fleet_id": snap["fleet_id"], "epoch": snap["epoch"],
        "workers": sorted(snap["workers"]),
        "counters": snap["counters"]}
    print(json.dumps(out, indent=1))
    ok = (out.get("share_submit_result") is True
          and all(out.get("refusals", {}).values())
          and out["tier_counters"].get("accepted", 0) >= 1
          and out["per_worker"].get(WORKER, {}).get(
              "accepted", 0) >= 1
          and out.get("upstream_submissions") == 0
          and out.get("runner_exit") == 0
          and out["snapshot"] is not None
          and out["snapshot"]["workers"] == [WORKER])
    print("EXP-057 STAGING DEPLOYMENT VERIFICATION:",
          "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
