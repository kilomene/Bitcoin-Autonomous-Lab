#!/usr/bin/env python3
"""EXP-050 Gate 3 fault injection: the endpoint health policy
(NOVA-ER-0010, register R-26) against local Stratum stubs.

Two stub endpoints on localhost, both speaking enough Stratum
V1 to serve jobs and judge shares exactly (header rebuilt
from job + extranonce1 + extranonce2 + nonce, double SHA-256,
integer target compare). The production StratumClient runs
with a production EndpointHealthPolicy attached, and a small
hashlib miner loop plays the mainnet_live role: read the
current job, scan nonces, submit hits. Scenarios:

  S0  startup failover: primary down at start, fallback up;
      connect_initial lands on the fallback.
  S0b startup exhaustion: both down; connect_initial raises
      (the historical process-exit shape; backstop intact).
  S1  primary dies mid-job: failover completes and the first
      fallback job arrives inside one stub job interval;
      shares before and after are judged exactly.
  S2  primary recovers: exactly one failback, after the
      failback interval, and mining resumes on the primary.
  S3  flapping primary: failbacks stay at or below one per
      damping window (bound is 1, window 60 s, run 26 s).
  S4  all endpoints down mid-session: the policy reports
      exhaustion, no recovery is faked, and when the primary
      returns the recovery is logged and mining resumes.
  S5  share accounting across a switch: submits left
      unanswered on the dying connection are reported as
      unresolved on reset; nothing is submitted twice;
      submitted = accepted + rejected + unresolved holds as
      three separately recorded categories.

Results (timings and per-scenario assertions) are written to
RAW_RESULTS/gate3_results.json next to this file. Nothing
here touches the live miner or any real endpoint.

Usage: python3 exp050_fault_injection.py
"""

import hashlib
import json
import os
import socket
import socketserver
import struct
import sys
import threading
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from mining.endpoint_health import EndpointHealthPolicy  # noqa: E402
from mining.stratum_client import (StratumClient,  # noqa: E402
                                   build_header, dsha256,
                                   target_for_difficulty)

RESULTS = os.path.join(HERE, "RAW_RESULTS", "gate3_results.json")
SHARE_DIFFICULTY = 0.000005  # ~21k expected hashes per share


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ListEvidence:
    """Evidence sink with the StratumClient-facing shape:
    log(event, **fields), kept in memory for assertions."""

    def __init__(self):
        self.events = []
        self.lock = threading.Lock()

    def log(self, event, **fields):
        with self.lock:
            self.events.append({"event": event, **fields})

    def find(self, name):
        with self.lock:
            return [e for e in self.events if e["event"] == name]

    def count(self, name):
        return len(self.find(name))


class MiniStub:
    """One fake pool endpoint. Serves jobs on a fixed
    prevhash (so endpoints are distinguishable in the client
    evidence), judges shares exactly, and can be killed,
    restarted and flapped under harness control."""

    def __init__(self, port, prevhash_byte, difficulty=SHARE_DIFFICULTY,
                 job_interval_s=4.0, respond_to_submits=True):
        self.port = port
        self.prevhash = (bytes([prevhash_byte]) * 32).hex()
        self.difficulty = difficulty
        self.job_interval_s = job_interval_s
        self.respond_to_submits = respond_to_submits
        self.submits = []
        self.connections = 0
        self._lock = threading.Lock()
        self._conns = {}
        self._next_conn = 0
        self._job_counter = 0
        self._job = None
        self._jobs_by_id = {}
        self._server = None
        self._bcast = None
        self._running = False

    # -- job supply -------------------------------------------------
    def _new_job(self):
        with self._lock:
            self._job_counter += 1
            job = {
                "job_id": f"stub{self.port}-{self._job_counter}",
                "prevhash": self.prevhash,
                "coinb1": ("01000000010000000000000000000000000000"
                           "000000000000000000000000000000000000"
                           "ffffffff"),
                "coinb2": ("ffffffff0100f2052a0100000043410412"
                           "34567890abcdef"),
                "merkle_branch": [],
                "version": "20000000",
                # Mainnet-legal nbits (the genesis bits), so
                # the job also passes the production EXP-036
                # header-validity gate on the mainnet path;
                # the share target comes from set_difficulty.
                "nbits": "1d00ffff",
                "ntime": "%08x" % int(time.time()),
                "clean_jobs": True,
            }
            self._job = job
            self._jobs_by_id[job["job_id"]] = job
            return job

    def _notify_params(self, job):
        return [job["job_id"], job["prevhash"], job["coinb1"],
                job["coinb2"], job["merkle_branch"], job["version"],
                job["nbits"], job["ntime"], job["clean_jobs"]]

    # -- connection handling ----------------------------------------
    def _register(self, sock):
        with self._lock:
            self._next_conn += 1
            cid = self._next_conn
            self.connections += 1
            conn = {"id": cid, "sock": sock,
                    "lock": threading.Lock(),
                    "en1": "%08x" % cid, "alive": True}
            self._conns[cid] = conn
            return conn

    def _unregister(self, conn):
        with self._lock:
            conn["alive"] = False
            self._conns.pop(conn["id"], None)

    def _send(self, conn, msg):
        try:
            with conn["lock"]:
                conn["sock"].sendall(
                    (json.dumps(msg) + "\n").encode())
        except OSError:
            pass

    def _on_message(self, conn, msg):
        method = msg.get("method")
        mid = msg.get("id")
        if method == "mining.subscribe":
            self._send(conn, {
                "id": mid,
                "result": [[["mining.notify", "stub-session"]],
                           conn["en1"], 4],
                "error": None})
        elif method == "mining.suggest_difficulty":
            self._send(conn, {"id": mid, "result": True,
                              "error": None})
        elif method == "mining.authorize":
            self._send(conn, {"id": mid, "result": True,
                              "error": None})
            self._send(conn, {"id": None,
                              "method": "mining.set_difficulty",
                              "params": [self.difficulty]})
            job = self._job or self._new_job()
            self._send(conn, {"id": None, "method": "mining.notify",
                              "params": self._notify_params(job)})
        elif method == "mining.submit":
            p = msg["params"]
            accepted = self._judge(conn, p)
            with self._lock:
                self.submits.append({
                    "job_id": p[1], "extranonce2": p[2],
                    "ntime": p[3], "nonce": p[4],
                    "accepted": accepted,
                    "answered": self.respond_to_submits})
            if self.respond_to_submits:
                self._send(conn, {"id": mid, "result": accepted,
                                  "error": None})

    def _judge(self, conn, params):
        job = self._jobs_by_id.get(params[1])
        if job is None:
            return False
        try:
            nonce = int(params[4], 16)
        except ValueError:
            return False
        header, _m, _c = build_header(job, conn["en1"], params[2],
                                      nonce, "wordswap")
        value = int.from_bytes(dsha256(header), "little")
        return value <= target_for_difficulty(self.difficulty)

    def _broadcast_loop(self):
        while self._running:
            time.sleep(self.job_interval_s)
            if not self._running:
                return
            job = self._new_job()
            with self._lock:
                conns = list(self._conns.values())
            for conn in conns:
                if conn["alive"]:
                    self._send(conn, {
                        "id": None, "method": "mining.notify",
                        "params": self._notify_params(job)})

    # -- lifecycle ----------------------------------------------------
    def start(self):
        stub = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                conn = stub._register(self.request)
                buf = b""
                try:
                    while stub._running:
                        data = self.request.recv(65536)
                        if not data:
                            break
                        buf += data
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            if line.strip():
                                stub._on_message(
                                    conn, json.loads(line))
                except OSError:
                    pass
                finally:
                    stub._unregister(conn)

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = True

        self._server = Server(("127.0.0.1", self.port), Handler)
        self._running = True
        self._new_job()
        t = threading.Thread(target=self._server.serve_forever,
                             daemon=True)
        t.start()
        self._bcast = threading.Thread(target=self._broadcast_loop,
                                       daemon=True)
        self._bcast.start()

    def kill(self):
        self._running = False
        with self._lock:
            conns = list(self._conns.values())
        for conn in conns:
            try:
                conn["sock"].shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn["sock"].close()
            except OSError:
                pass
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def flap(self, up_s, down_s, stop):
        """Alternate up/down until stop is set; ends down."""
        while not stop.is_set():
            self.start()
            if stop.wait(up_s):
                break
            self.kill()
            if stop.wait(down_s):
                break
        try:
            self.kill()
        except Exception:
            pass


# -- client-side helpers ----------------------------------------------


def make_client(port_a, port_b, ev, **policy_kw):
    policy = EndpointHealthPolicy(
        [("127.0.0.1", port_a), ("127.0.0.1", port_b)], **policy_kw)
    client = StratumClient("127.0.0.1", port_a,
                           "bc1qgate3.worker", "x", ev)
    client.suggest_difficulty = 0.001
    client.endpoint_policy = policy
    return client, policy


def start_client(client):
    client.connect_initial()
    reader = threading.Thread(target=client.reader_loop, daemon=True)
    reader.start()
    if not client.authorized.wait(timeout=15):
        raise RuntimeError("client never authorized")
    return reader


def wait_for(pred, timeout_s, what):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if pred():
            return time.time() - t0
        time.sleep(0.05)
    raise RuntimeError(f"timeout waiting for {what}")


def current_job(client):
    with client.lock:
        return client.current_job, client.difficulty


def mine_shares(client, n, timeout_s=60):
    """Scan nonces with hashlib for the client's current job
    and submit n shares. Returns the list of (job_id, en2,
    nonce) submitted. Stops early if the job vanishes for
    the whole remaining timeout."""
    submitted = []
    deadline = time.time() + timeout_s
    en2_counter = 0
    while len(submitted) < n and time.time() < deadline:
        job, diff = current_job(client)
        if job is None or diff is None:
            time.sleep(0.1)
            continue
        en2_counter += 1
        en2 = "%0*x" % (client.extranonce2_size * 2, en2_counter)
        header0, _m, _c = build_header(job, client.extranonce1,
                                       en2, 0, "wordswap")
        prefix = header0[:76]
        target = target_for_difficulty(float(diff))
        nonce = 0
        while nonce < (1 << 24) and time.time() < deadline:
            digest = hashlib.sha256(hashlib.sha256(
                prefix + struct.pack("<I", nonce)).digest()).digest()
            if int.from_bytes(digest, "little") <= target:
                client.submit(job, en2, nonce)
                submitted.append((job["job_id"], en2, nonce))
                break
            nonce += 1
    return submitted


def accepted_count(ev):
    return sum(1 for e in ev.find("share_result") if e["accepted"])


# -- scenarios ----------------------------------------------------------


def scenario_s0():
    """Startup failover: primary down, fallback up."""
    pa, pb = free_port(), free_port()
    b = MiniStub(pb, 0xBB)
    b.start()
    ev = ListEvidence()
    client, policy = make_client(pa, pb, ev, error_threshold=2,
                                 failback_interval_s=3.0,
                                 damping_window_s=60.0,
                                 probe_timeout_s=1.0)
    try:
        start_client(client)
        wait_for(lambda: (current_job(client)[0] or {}).get(
            "prevhash") == b.prevhash, 15, "fallback job")
        out = {"authorized_via_fallback": True,
               "failovers": policy.total_failovers,
               "first_job_prevhash": current_job(client)[0]["prevhash"]}
        assert policy.total_failovers == 1
        return out
    finally:
        client.stop_flag = True
        b.kill()


def scenario_s0b():
    """Startup exhaustion: both down, connect_initial raises."""
    pa, pb = free_port(), free_port()
    ev = ListEvidence()
    client, policy = make_client(pa, pb, ev, error_threshold=2,
                                 failback_interval_s=3.0,
                                 damping_window_s=60.0,
                                 probe_timeout_s=1.0)
    raised = None
    try:
        client.connect_initial()
    except (ConnectionError, OSError, TimeoutError) as exc:
        raised = type(exc).__name__
    assert raised is not None, "connect_initial did not raise"
    assert policy.exhausted
    assert ev.count("endpoint_policy_exhausted") == 1
    return {"raised": raised, "exhausted": policy.exhausted,
            "exhaustion_events": ev.count("endpoint_policy_exhausted")}


def scenario_s1():
    """Primary dies mid-job: failover inside one job interval."""
    pa, pb = free_port(), free_port()
    a = MiniStub(pa, 0xAA)
    b = MiniStub(pb, 0xBB)
    a.start()
    b.start()
    ev = ListEvidence()
    client, policy = make_client(pa, pb, ev, error_threshold=2,
                                 failback_interval_s=3.0,
                                 damping_window_s=60.0,
                                 probe_timeout_s=1.0)
    try:
        start_client(client)
        wait_for(lambda: (current_job(client)[0] or {}).get(
            "prevhash") == a.prevhash, 15, "primary job")
        subs = mine_shares(client, 2)
        assert len(subs) == 2
        wait_for(lambda: accepted_count(ev) == 2, 15,
                 "two accepted verdicts on the primary")
        t0 = time.time()
        a.kill()
        wait_for(lambda: ev.count("endpoint_failover") == 1, 20,
                 "failover event")
        wait_for(lambda: (current_job(client)[0] or {}).get(
            "prevhash") == b.prevhash, 20, "first fallback job")
        failover_s = time.time() - t0
        assert failover_s < a.job_interval_s, (
            f"failover {failover_s:.2f}s not inside one job "
            f"interval {a.job_interval_s}s")
        subs_b = mine_shares(client, 2)
        assert len(subs_b) == 2
        wait_for(lambda: accepted_count(ev) == 4, 15,
                 "two accepted verdicts on the fallback")
        assert len(a.submits) == 2 and len(b.submits) == 2
        assert not client._pending_submits
        return {"failover_s": round(failover_s, 3),
                "job_interval_s": a.job_interval_s,
                "primary_submits": len(a.submits),
                "fallback_submits": len(b.submits),
                "accepted_total": accepted_count(ev)}
    finally:
        client.stop_flag = True
        a.kill()
        b.kill()


def scenario_s2():
    """Primary recovers: exactly one failback, mining resumes."""
    pa, pb = free_port(), free_port()
    a = MiniStub(pa, 0xAA)
    b = MiniStub(pb, 0xBB)
    a.start()
    b.start()
    ev = ListEvidence()
    client, policy = make_client(pa, pb, ev, error_threshold=2,
                                 failback_interval_s=3.0,
                                 damping_window_s=60.0,
                                 probe_timeout_s=1.0)
    try:
        start_client(client)
        wait_for(lambda: (current_job(client)[0] or {}).get(
            "prevhash") == a.prevhash, 15, "primary job")
        a.kill()
        wait_for(lambda: (current_job(client)[0] or {}).get(
            "prevhash") == b.prevhash, 20, "fallback job")
        a.start()
        wait_for(lambda: ev.count("endpoint_failback") == 1, 30,
                 "failback event")
        wait_for(lambda: (current_job(client)[0] or {}).get(
            "prevhash") == a.prevhash, 20, "primary job again")
        subs = mine_shares(client, 1)
        assert len(subs) == 1
        wait_for(lambda: accepted_count(ev) >= 1, 15,
                 "accepted verdict after failback")
        time.sleep(6)
        return {"failbacks": ev.count("endpoint_failback"),
                "failovers": policy.total_failovers,
                "back_on_primary": policy.on_primary}
    finally:
        client.stop_flag = True
        a.kill()
        b.kill()


def scenario_s3():
    """Flapping primary: at most one failback per damping
    window (bound 1, window 60 s, observation 26 s)."""
    pa, pb = free_port(), free_port()
    a = MiniStub(pa, 0xAA)
    b = MiniStub(pb, 0xBB)
    b.start()
    ev = ListEvidence()
    client, policy = make_client(pa, pb, ev, error_threshold=2,
                                 failback_interval_s=2.0,
                                 damping_window_s=60.0,
                                 max_failbacks_per_window=1,
                                 probe_timeout_s=1.0)
    stop = threading.Event()
    flap = threading.Thread(target=a.flap, args=(4.0, 2.5, stop),
                            daemon=True)
    try:
        flap.start()
        start_client(client)
        wait_for(lambda: (current_job(client)[0] or {}).get(
            "prevhash") == b.prevhash, 20, "fallback job")
        time.sleep(26)
        failbacks = ev.count("endpoint_failback")
        assert failbacks == 1, f"failbacks {failbacks} != 1"
        job, _d = current_job(client)
        return {"failbacks_in_26s": failbacks,
                "damping_window_s": 60.0,
                "failovers": policy.total_failovers,
                "client_has_job_at_end": job is not None}
    finally:
        stop.set()
        flap.join(timeout=10)
        client.stop_flag = True
        b.kill()


def scenario_s4():
    """All endpoints down mid-session: exhaustion reported,
    recovery only when an endpoint really returns."""
    pa, pb = free_port(), free_port()
    a = MiniStub(pa, 0xAA)
    b = MiniStub(pb, 0xBB)
    a.start()
    b.start()
    ev = ListEvidence()
    client, policy = make_client(pa, pb, ev, error_threshold=2,
                                 failback_interval_s=3.0,
                                 damping_window_s=60.0,
                                 probe_timeout_s=1.0)
    try:
        start_client(client)
        wait_for(lambda: (current_job(client)[0] or {}).get(
            "prevhash") == a.prevhash, 15, "primary job")
        a.kill()
        b.kill()
        wait_for(lambda: ev.count("endpoint_policy_exhausted") == 1,
                 30, "exhaustion event")
        exhausted_seen = policy.exhausted
        assert exhausted_seen
        assert ev.count("endpoint_policy_recovered") == 0
        assert current_job(client)[0] is None
        a.start()
        wait_for(lambda: ev.count("endpoint_policy_recovered") == 1,
                 30, "recovery event")
        wait_for(lambda: (current_job(client)[0] or {}).get(
            "prevhash") == a.prevhash, 20, "primary job after "
            "recovery")
        subs = mine_shares(client, 1)
        assert len(subs) == 1
        wait_for(lambda: accepted_count(ev) >= 1, 15,
                 "accepted verdict after recovery")
        return {"exhausted_reported": exhausted_seen,
                "recovered_after_primary_returned": True,
                "failovers": policy.total_failovers}
    finally:
        client.stop_flag = True
        a.kill()
        b.kill()


def scenario_s5():
    """Unresolved accounting: submits unanswered on the dying
    connection are reported, never lost, never doubled."""
    pa, pb = free_port(), free_port()
    a = MiniStub(pa, 0xAA, respond_to_submits=False)
    b = MiniStub(pb, 0xBB)
    a.start()
    b.start()
    ev = ListEvidence()
    client, policy = make_client(pa, pb, ev, error_threshold=2,
                                 failback_interval_s=3.0,
                                 damping_window_s=60.0,
                                 probe_timeout_s=1.0)
    try:
        start_client(client)
        wait_for(lambda: (current_job(client)[0] or {}).get(
            "prevhash") == a.prevhash, 15, "primary job")
        subs_a = mine_shares(client, 2)
        assert len(subs_a) == 2
        wait_for(lambda: len(client._pending_submits) == 2, 10,
                 "two pending submits")
        time.sleep(1.0)
        assert accepted_count(ev) == 0
        a.kill()
        wait_for(lambda: (current_job(client)[0] or {}).get(
            "prevhash") == b.prevhash, 20, "fallback job")
        unres = ev.find("submits_unresolved_on_reset")
        assert len(unres) == 1 and unres[0]["count"] == 2, unres
        subs_b = mine_shares(client, 2)
        assert len(subs_b) == 2
        wait_for(lambda: accepted_count(ev) == 2, 15,
                 "two accepted verdicts on the fallback")
        keys_a = {(s["job_id"], s["extranonce2"], s["nonce"])
                  for s in a.submits}
        keys_b = {(s["job_id"], s["extranonce2"], s["nonce"])
                  for s in b.submits}
        assert not (keys_a & keys_b), "a share was submitted twice"
        submitted = len(a.submits) + len(b.submits)
        accepted = accepted_count(ev)
        rejected = sum(1 for e in ev.find("share_result")
                       if not e["accepted"])
        unresolved = unres[0]["count"]
        assert submitted == 4 and accepted == 2 and rejected == 0
        assert submitted == accepted + rejected + unresolved
        assert not client._pending_submits
        return {"submitted": submitted, "accepted": accepted,
                "rejected": rejected, "unresolved": unresolved,
                "double_submits": 0}
    finally:
        client.stop_flag = True
        a.kill()
        b.kill()


SCENARIOS = [("S0_startup_failover", scenario_s0),
             ("S0b_startup_exhaustion", scenario_s0b),
             ("S1_failover_mid_job", scenario_s1),
             ("S2_failback_on_recovery", scenario_s2),
             ("S3_flapping_primary_damping", scenario_s3),
             ("S4_exhaustion_and_recovery", scenario_s4),
             ("S5_unresolved_accounting", scenario_s5)]


def main():
    results = {"experiment": "EXP-050", "gate": "Gate 3 fault "
               "injection", "started": utcnow(),
               "host": os.uname().nodename, "scenarios": {}}
    ok = True
    for name, fn in SCENARIOS:
        t0 = time.time()
        try:
            out = fn()
            results["scenarios"][name] = {
                "passed": True, "seconds": round(time.time() - t0, 2),
                **out}
            print(f"PASS {name} ({time.time() - t0:.1f}s) {out}",
                  flush=True)
        except Exception as exc:
            ok = False
            results["scenarios"][name] = {
                "passed": False, "seconds": round(time.time() - t0, 2),
                "error": f"{type(exc).__name__}: {exc}"}
            print(f"FAIL {name}: {exc}", flush=True)
    results["finished"] = utcnow()
    results["all_passed"] = ok
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    with open(RESULTS, "w") as f:
        json.dump(results, f, indent=2)
    print("wrote", RESULTS)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
