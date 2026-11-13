#!/usr/bin/env python3
"""Bitcoin Autonomous Lab: Stratum V1 client and mining coordinator.

Connects to a real Stratum pool, receives a real mainnet job, builds the
80-byte block header, and hands nonce ranges to the C miner engine
(bal-miner), which performs double SHA-256 using the host CPU SHA-NI
instructions through OpenSSL.

Every protocol event is written to a JSONL evidence log with a UTC
timestamp. Nothing in the log is simulated: a share is only recorded as
accepted when the pool answers mining.submit with result true.

Honest limits, stated up front: a 4-core CPU VM produces on the order of
tens of MH/s. The Bitcoin network produces hundreds of EH/s. This lab
proves real mining (real job, real hashing, real share protocol), it
does not promise a block. Finding a block solo at this hashrate is a
lottery with an expected wait measured in millions of years. See
docs/HONEST-LIMITS.md.
"""

import argparse
import hashlib
import json
import socket
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

DIFF1_TARGET = 0x00000000FFFF0000000000000000000000000000000000000000000000000000


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def dsha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def target_for_difficulty(diff: float) -> int:
    if diff <= 0:
        raise ValueError("difficulty must be positive")
    return int(DIFF1_TARGET / diff)


def swap_words(data: bytes) -> bytes:
    """Reverse bytes inside each 4-byte word (Stratum prevhash encoding)."""
    out = bytearray()
    for i in range(0, len(data), 4):
        out += data[i:i + 4][::-1]
    return bytes(out)


def build_header(job, extranonce1, extranonce2, nonce, prevhash_mode):
    """Build the 80-byte header for a Stratum job.

    Returns (header_bytes, merkle_root_internal, coinbase_bytes).
    Field encodings follow the Stratum V1 conventions used by public
    pools: version, nbits and ntime arrive as hex strings of big endian
    integers and enter the header little endian; prevhash arrives with
    its 4-byte words byte-swapped; merkle branches arrive as internal
    order hashes and are concatenated directly.
    """
    coinbase = (
        bytes.fromhex(job["coinb1"])
        + bytes.fromhex(extranonce1)
        + bytes.fromhex(extranonce2)
        + bytes.fromhex(job["coinb2"])
    )
    merkle = dsha256(coinbase)
    for branch in job["merkle_branch"]:
        merkle = dsha256(merkle + bytes.fromhex(branch))

    prev = bytes.fromhex(job["prevhash"])
    if prevhash_mode == "wordswap":
        prev_header = swap_words(prev)
    elif prevhash_mode == "reverse":
        prev_header = prev[::-1]
    elif prevhash_mode == "asis":
        prev_header = prev
    else:
        raise ValueError("unknown prevhash mode")

    header = (
        struct.pack("<I", int(job["version"], 16))
        + prev_header
        + merkle
        + struct.pack("<I", int(job["ntime"], 16))
        + struct.pack("<I", int(job["nbits"], 16))
        + struct.pack("<I", nonce)
    )
    assert len(header) == 80
    return header, merkle, coinbase


class Evidence:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.f = open(path, "a", buffering=1)

    def log(self, event, **fields):
        rec = {"ts": utcnow(), "event": event, **fields}
        line = json.dumps(rec)
        with self.lock:
            self.f.write(line + "\n")
        print(line, flush=True)

    def close(self):
        self.f.close()


class StratumClient:
    def __init__(self, host, port, user, password, evidence):
        self.host, self.port = host, port
        self.user, self.password = user, password
        self.ev = evidence
        self.sock = None
        self.buf = b""
        self.next_id = 1
        self.lock = threading.Lock()
        self.extranonce1 = None
        self.extranonce2_size = None
        self.difficulty = None
        self.current_job = None
        self.job_generation = 0
        self.authorized = threading.Event()
        self.responses = {}
        self.methods_by_id = {}
        self.suggest_difficulty = None
        self.stop_flag = False

    def _send(self, method, params):
        with self.lock:
            mid = self.next_id
            self.next_id += 1
            self.methods_by_id[mid] = method
        msg = {"id": mid, "method": method, "params": params}
        self.sock.sendall((json.dumps(msg) + "\n").encode())
        return mid

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=30)
        self.sock.settimeout(1.0)
        self.ev.log("connected", pool=f"{self.host}:{self.port}")
        sub_id = self._send("mining.subscribe", ["BitcoinAutonomousLab/0.1.0"])
        if self.suggest_difficulty is not None:
            self._send("mining.suggest_difficulty", [self.suggest_difficulty])
            self.ev.log("suggest_difficulty_sent",
                        difficulty=self.suggest_difficulty)
        self._send("mining.authorize", [self.user, self.password])
        self._wait_for_subscribe(sub_id)

    def _wait_for_subscribe(self, sub_id):
        deadline = time.time() + 30
        while time.time() < deadline:
            self.poll_once()
            if self.extranonce1 is not None:
                return
        raise TimeoutError("no subscribe response from pool")

    def poll_once(self):
        try:
            data = self.sock.recv(65536)
        except socket.timeout:
            return
        if not data:
            raise ConnectionError("pool closed connection")
        self.buf += data
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            if line.strip():
                self._handle(json.loads(line))

    def _handle(self, msg):
        method = msg.get("method")
        if method == "mining.notify":
            p = msg["params"]
            job = {
                "job_id": p[0],
                "prevhash": p[1],
                "coinb1": p[2],
                "coinb2": p[3],
                "merkle_branch": p[4],
                "version": p[5],
                "nbits": p[6],
                "ntime": p[7],
                "clean_jobs": p[8] if len(p) > 8 else False,
            }
            with self.lock:
                if job["clean_jobs"] or self.current_job is None:
                    self.job_generation += 1
                self.current_job = job
                gen = self.job_generation
            self.ev.log(
                "job", job_id=job["job_id"], generation=gen,
                prevhash=job["prevhash"], nbits=job["nbits"],
                ntime=job["ntime"], clean_jobs=job["clean_jobs"],
                branches=len(job["merkle_branch"]),
            )
        elif method == "mining.set_difficulty":
            self.difficulty = msg["params"][0]
            self.ev.log("set_difficulty", difficulty=self.difficulty)
        elif method == "mining.set_extranonce":
            self.extranonce1 = msg["params"][0]
            self.extranonce2_size = msg["params"][1]
            self.ev.log("set_extranonce", extranonce1=self.extranonce1,
                        extranonce2_size=self.extranonce2_size)
        elif "result" in msg:
            mid = msg.get("id")
            self.responses[mid] = msg
            method = self.methods_by_id.get(mid)
            if method == "mining.subscribe" and msg.get("result"):
                result = msg["result"]
                # subscribe result: [[subscriptions], extranonce1, extranonce2_size]
                try:
                    self.extranonce1 = result[1]
                    self.extranonce2_size = result[2]
                except (TypeError, IndexError):
                    pass
                self.ev.log("subscribed", extranonce1=self.extranonce1,
                            extranonce2_size=self.extranonce2_size)
            elif method == "mining.authorize":
                ok = bool(msg.get("result"))
                self.ev.log("authorize_result", ok=ok, error=msg.get("error"))
                if ok:
                    self.authorized.set()
            elif method == "mining.submit":
                self.ev.log("share_result", id=mid,
                            accepted=bool(msg.get("result")),
                            error=msg.get("error"))
            else:
                self.ev.log("response", id=mid, method=method,
                            result=msg.get("result"), error=msg.get("error"))

    def submit(self, job, extranonce2, nonce):
        params = [
            self.user,
            job["job_id"],
            extranonce2,
            job["ntime"],
            "%08x" % nonce,
        ]
        mid = self._send("mining.submit", params)
        self.ev.log("submit", id=mid, job_id=job["job_id"],
                    extranonce2=extranonce2, ntime=job["ntime"],
                    nonce="%08x" % nonce)
        return mid

    def reader_loop(self):
        while not self.stop_flag:
            try:
                self.poll_once()
            except (ConnectionError, OSError) as exc:
                self.ev.log("connection_error", error=str(exc))
                self.stop_flag = True
                return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="public-pool.io")
    ap.add_argument("--port", type=int, default=21496)
    ap.add_argument("--address", required=True, help="Lab BTC payout address (public only)")
    ap.add_argument("--worker", default="bal1")
    ap.add_argument("--duration", type=int, default=120)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--miner", default="./bal-miner")
    ap.add_argument("--evidence", default="evidence/live-session.jsonl")
    ap.add_argument("--prevhash-mode", default="wordswap",
                    choices=["wordswap", "reverse", "asis"])
    ap.add_argument("--chunk", type=int, default=5_000_000,
                    help="nonces per miner invocation")
    ap.add_argument("--suggest-difficulty", type=float, default=0.001,
                    help="difficulty requested from the pool before authorize; "
                         "public-pool.io clamps this to its minimum of 1, "
                         "without it the pool assigns 100000")
    args = ap.parse_args()

    ev = Evidence(args.evidence)
    user = f"{args.address}.{args.worker}"
    ev.log("session_start", user=user, pool=f"{args.pool}:{args.port}",
           threads=args.threads, duration_s=args.duration,
           prevhash_mode=args.prevhash_mode)

    client = StratumClient(args.pool, args.port, user, "x", ev)
    client.suggest_difficulty = args.suggest_difficulty
    client.connect()
    reader = threading.Thread(target=client.reader_loop, daemon=True)
    reader.start()

    if not client.authorized.wait(timeout=30):
        ev.log("fatal", error="authorization was not confirmed by pool")
        return 3

    deadline = time.time() + args.duration
    extranonce2_counter = 0
    submitted_ids = set()
    total_hashes = 0
    total_seconds = 0.0
    session_best_hash = None
    session_best_diff = 0.0

    while time.time() < deadline and not client.stop_flag:
        with client.lock:
            job = client.current_job
            gen = client.job_generation
            diff = client.difficulty
        if job is None or diff is None:
            time.sleep(0.3)
            continue

        extranonce2_counter += 1
        en2 = "%0*x" % (client.extranonce2_size * 2, extranonce2_counter)
        header, merkle, coinbase = build_header(
            job, client.extranonce1, en2, 0, args.prevhash_mode)
        target = target_for_difficulty(float(diff))
        target_hex = "%064x" % target

        proc = subprocess.Popen(
            [args.miner, "search", header.hex(), target_hex, "0",
             str(args.chunk), str(args.threads)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        # Abandon this search promptly if a clean job replaces it.
        while proc.poll() is None:
            with client.lock:
                if client.job_generation != gen:
                    proc.terminate()
                    break
            if time.time() > deadline:
                proc.terminate()
                break
            time.sleep(0.1)
        out = proc.stdout.read() if proc.stdout else ""

        for line in out.splitlines():
            fields_all = dict(
                kv.split("=", 1) for kv in line.split()[1:] if "=" in kv)
            best_hex = fields_all.get("best_hash")
            if best_hex:
                best_int = int(best_hex, 16)
                best_diff = DIFF1_TARGET / best_int if best_int else float("inf")
                if best_diff > session_best_diff:
                    session_best_diff = best_diff
                    session_best_hash = best_hex
                    ev.log("best_share", job_id=job["job_id"],
                           hash=best_hex,
                           nonce=int(fields_all.get("best_nonce", 0)),
                           difficulty=best_diff, pool_difficulty=diff)
            if line.startswith("FOUND"):
                fields = dict(
                    kv.split("=", 1) for kv in line.split()[1:] if "=" in kv)
                nonce = int(fields["nonce"])
                found_hash = fields["hash"]
                total_hashes += int(fields.get("hashes", 0))
                hash_int = int(found_hash, 16)
                share_diff = DIFF1_TARGET / hash_int if hash_int else float("inf")
                ev.log("share_found", job_id=job["job_id"], nonce=nonce,
                       hash=found_hash, share_difficulty=share_diff,
                       pool_difficulty=diff)
                mid = client.submit(job, en2, nonce)
                submitted_ids.add(mid)
            elif line.startswith("NONE"):
                fields = dict(
                    kv.split("=", 1) for kv in line.split()[1:] if "=" in kv)
                total_hashes += int(fields.get("hashes", 0))
                total_seconds += float(fields.get("seconds", 0))

        # Give submit responses a moment to arrive in the evidence log;
        # the reader thread records share_result for mining.submit ids.
        time.sleep(0.5)
        for mid in list(submitted_ids):
            if mid in client.responses:
                client.responses.pop(mid)
                submitted_ids.discard(mid)

    if total_seconds > 0:
        ev.log("session_hashrate", total_hashes=total_hashes,
               miner_seconds=total_seconds,
               approx_hashrate_hs=int(total_hashes / total_seconds))
    ev.log("session_end", total_hashes=total_hashes,
           best_hash=session_best_hash, best_difficulty=session_best_diff)
    client.stop_flag = True
    ev.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
