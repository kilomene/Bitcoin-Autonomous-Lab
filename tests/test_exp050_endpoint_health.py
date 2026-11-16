#!/usr/bin/env python3
"""EXP-050 tests: the endpoint health policy (R-26).

- Policy unit tests (fake clock): tolerance counting,
  ordered failover, the exhaustion transition and recovery,
  failback timing, and the damping bound under a flapping
  primary (at most max_failbacks_per_window failbacks in
  any damping window).
- Config tests: the policy is disabled by default (the live
  stack's behaviour is the historical single-endpoint one),
  partial pool_health sections merge over defaults, the
  ordered endpoint list puts the resolved primary first and
  skips malformed fallbacks.
- Gate 3 (condensed; the full campaign with timings lives
  in research/sha256d/exp050/): failover mid-job against
  local stubs, unresolved-submit accounting across a
  switch, startup exhaustion raising.
- Gate 5: an isolated instance (byte copies of the mining
  and gpu trees, its own .local, its own evidence) running
  the production mainnet_live against two stubs: start on
  the primary, fail over when it dies, fail back when it
  returns, stop by signal, the process alive throughout.
  The live tree and live miner are never touched.
"""

import hashlib
import json
import os
import shutil
import signal
import socket
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), ".."))

from mining.endpoint_config import (load_config,  # noqa: E402
                                    pool_health_config,
                                    pool_policy_endpoints,
                                    resolve_endpoint)
from mining.endpoint_health import EndpointHealthPolicy  # noqa: E402
from mining.stratum_client import (StratumClient,  # noqa: E402
                                   build_header, dsha256,
                                   target_for_difficulty)

CHECKS = 0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(f"check {CHECKS} failed: {label}")
    print(f"ok {CHECKS} - {label}")


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


# ---------------------------------------------------------------- policy


def test_policy_units():
    clk = FakeClock()
    p = EndpointHealthPolicy(
        [("a", 1), ("b", 2), ("c", 3)], error_threshold=3,
        failback_interval_s=30.0, damping_window_s=100.0,
        max_failbacks_per_window=1, clock=clk)
    check(p.current == ("a", 1) and p.on_primary,
          "policy starts on the primary")
    check(p.note_error() == "retry" and p.note_error() == "retry",
          "errors below the threshold retry the same endpoint")
    check(p.note_error() == "failover" and p.current == ("b", 2),
          "third consecutive error fails over to endpoint 2")
    info = p.note_success()
    check(info["was_exhausted"] is False
          and p.consecutive_errors == 0,
          "success clears the consecutive count")
    for _ in range(3):
        p.note_error()
    check(p.current == ("c", 3), "failover advances in order")
    check(p.note_error() == "retry"
          and p.note_error() == "retry"
          and p.note_error() == "exhausted",
          "last endpoint at threshold reports exhaustion once")
    check(p.exhausted and p.current == ("a", 1),
          "exhaustion points back at the primary")
    check(p.note_error() == "retry",
          "errors while exhausted keep retrying the primary")
    info = p.note_success()
    check(info["was_exhausted"] is True and not p.exhausted,
          "success after exhaustion is reported as recovery")
    st = p.status()
    check(st["total_failovers"] == 2 and st["total_errors"] == 10
          and st["endpoints"] == ["a:1", "b:2", "c:3"],
          "status reports separated counters, never a sum")

    # failback timing and damping, driven on the fake clock
    clk2 = FakeClock()
    q = EndpointHealthPolicy(
        [("a", 1), ("b", 2)], error_threshold=2,
        failback_interval_s=10.0, damping_window_s=100.0,
        max_failbacks_per_window=1, clock=clk2)
    q.note_error()
    check(q.note_error() == "failover",
          "setup: failover at t=0")
    check(not q.failback_due(9.9) and q.failback_due(10.0),
          "failback due exactly at the interval")
    q.note_probe_failed(10.0)
    check(not q.failback_due(19.9) and q.failback_due(20.0),
          "a failed probe restarts the interval")
    q.note_failback(20.0)
    check(q.on_primary and q.total_failbacks == 1,
          "failback returns to the primary")
    q.note_error(21.0)
    check(q.note_error(21.0) == "failover",
          "flap: primary dies again, failover again")
    check(not q.failback_due(50.0),
          "damping blocks a second failback inside the window")
    check(not q.failback_due(119.9) and q.failback_due(120.0),
          "failback budget returns when the window passes")

    r = EndpointHealthPolicy([("only", 9)], error_threshold=2,
                             clock=FakeClock())
    check(r.note_error() == "retry"
          and r.note_error() == "exhausted"
          and r.current == ("only", 9),
          "single-endpoint policy degenerates to retry + report")
    for bad in (lambda: EndpointHealthPolicy([]),
                lambda: EndpointHealthPolicy([("a", 1)],
                                             error_threshold=0)):
        try:
            bad()
            check(False, "invalid policy parameters raise")
        except ValueError:
            check(True, "invalid policy parameters raise")


def test_config():
    health = pool_health_config(load_config())
    check(health["enabled"] is False,
          "pool health policy is disabled by default (live "
          "behaviour is the historical single endpoint)")
    merged = pool_health_config(
        {"pool_health": {"enabled": True, "error_threshold": 5}})
    check(merged["enabled"] is True
          and merged["error_threshold"] == 5
          and merged["failback_interval_s"] == 300.0,
          "partial pool_health section merges over defaults")
    eps = pool_policy_endpoints(
        {"pool_health": {"fallbacks": [
            {"host": "backup.example", "port": 3333},
            {"host": "no-port.example"},
            {"port": 1234},
            "junk",
            {"host": "main.example", "port": 21496},
            {"host": "second.example", "port": "4444"}]}},
        "main.example", 21496)
    check(eps == [("main.example", 21496),
                  ("backup.example", 3333),
                  ("second.example", 4444)],
          "endpoint list: primary first, malformed fallbacks "
          "skipped, duplicate primary dropped")
    host, port, mode, _cfg = resolve_endpoint(
        path=os.path.join(ROOT, ".local",
                          "definitely-missing-endpoint.json"))
    check((host, port, mode) == ("public-pool.io", 21496, "pool"),
          "endpoint resolution with no config is unchanged")


# ------------------------------------------------------------------ stub


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ListEvidence:
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
    """One fake pool endpoint: serves jobs on a fixed
    prevhash, judges shares exactly, killable/restartable."""

    def __init__(self, port, prevhash_byte, difficulty=0.000005,
                 job_interval_s=4.0, respond_to_submits=True):
        self.port = port
        self.prevhash = (bytes([prevhash_byte]) * 32).hex()
        self.difficulty = difficulty
        self.job_interval_s = job_interval_s
        self.respond_to_submits = respond_to_submits
        self.submits = []
        self._lock = threading.Lock()
        self._conns = {}
        self._next_conn = 0
        self._job_counter = 0
        self._job = None
        self._jobs_by_id = {}
        self._server = None
        self._running = False

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
                # Mainnet-legal nbits (the genesis bits): the
                # production miner's EXP-036 gate judges the
                # header against POW_LIMIT_MAINNET, so a
                # regtest-style target would be rejected as
                # above the limit. The share target is set by
                # set_difficulty, independently of nbits.
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

    def _register(self, sock):
        with self._lock:
            self._next_conn += 1
            conn = {"id": self._next_conn, "sock": sock,
                    "lock": threading.Lock(),
                    "en1": "%08x" % self._next_conn, "alive": True}
            self._conns[conn["id"]] = conn
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
            self._send(conn, {"id": mid, "result": [
                [["mining.notify", "stub-session"]],
                conn["en1"], 4], "error": None})
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
                    "accepted": accepted})
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
        threading.Thread(target=self._server.serve_forever,
                         daemon=True).start()
        threading.Thread(target=self._broadcast_loop,
                         daemon=True).start()

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


def wait_for(pred, timeout_s, what):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if pred():
            return
        time.sleep(0.05)
    raise AssertionError(f"timeout waiting for {what}")


def current_job(client):
    with client.lock:
        return client.current_job, client.difficulty


def mine_shares(client, n, timeout_s=60):
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


def make_client(port_a, port_b, ev):
    policy = EndpointHealthPolicy(
        [("127.0.0.1", port_a), ("127.0.0.1", port_b)],
        error_threshold=2, failback_interval_s=3.0,
        damping_window_s=60.0, probe_timeout_s=1.0)
    client = StratumClient("127.0.0.1", port_a,
                           "bc1qgate3.worker", "x", ev)
    client.suggest_difficulty = 0.001
    client.endpoint_policy = policy
    return client, policy


# ---------------------------------------------------------------- Gate 3


def test_gate3_failover():
    pa, pb = free_port(), free_port()
    a = MiniStub(pa, 0xAA)
    b = MiniStub(pb, 0xBB)
    a.start()
    b.start()
    ev = ListEvidence()
    client, policy = make_client(pa, pb, ev)
    try:
        client.connect_initial()
        threading.Thread(target=client.reader_loop,
                         daemon=True).start()
        check(client.authorized.wait(timeout=15),
              "gate3: client authorized on the primary")
        wait_for(lambda: (current_job(client)[0] or {}).get(
            "prevhash") == a.prevhash, 15, "primary job")
        subs = mine_shares(client, 2)
        check(len(subs) == 2, "gate3: two shares mined on primary")
        wait_for(lambda: accepted_count(ev) == 2, 15,
                 "primary verdicts")
        t0 = time.time()
        a.kill()
        wait_for(lambda: ev.count("endpoint_failover") == 1, 20,
                 "failover event")
        wait_for(lambda: (current_job(client)[0] or {}).get(
            "prevhash") == b.prevhash, 20, "fallback job")
        check(time.time() - t0 < a.job_interval_s,
              "gate3: failover inside one job interval")
        subs_b = mine_shares(client, 2)
        check(len(subs_b) == 2, "gate3: mining resumed on fallback")
        wait_for(lambda: accepted_count(ev) == 4, 15,
                 "fallback verdicts")
        check(len(a.submits) == 2 and len(b.submits) == 2
              and not client._pending_submits,
              "gate3: submits split 2/2, none pending, none doubled")
    finally:
        client.stop_flag = True
        a.kill()
        b.kill()


def test_gate3_unresolved_and_exhaustion():
    pa, pb = free_port(), free_port()
    a = MiniStub(pa, 0xAA, respond_to_submits=False)
    b = MiniStub(pb, 0xBB)
    a.start()
    b.start()
    ev = ListEvidence()
    client, policy = make_client(pa, pb, ev)
    try:
        client.connect_initial()
        threading.Thread(target=client.reader_loop,
                         daemon=True).start()
        check(client.authorized.wait(timeout=15),
              "gate3: authorized for the accounting scenario")
        wait_for(lambda: (current_job(client)[0] or {}).get(
            "prevhash") == a.prevhash, 15, "primary job")
        subs = mine_shares(client, 2)
        check(len(subs) == 2, "gate3: two unanswered shares sent")
        wait_for(lambda: len(client._pending_submits) == 2, 10,
                 "two pending submits")
        a.kill()
        wait_for(lambda: (current_job(client)[0] or {}).get(
            "prevhash") == b.prevhash, 20, "fallback job")
        unres = ev.find("submits_unresolved_on_reset")
        check(len(unres) == 1 and unres[0]["count"] == 2,
              "gate3: unanswered submits reported unresolved on "
              "reset, as their own category")
        subs_b = mine_shares(client, 2)
        wait_for(lambda: accepted_count(ev) == 2, 15,
                 "fallback verdicts")
        keys_a = {(s["job_id"], s["extranonce2"], s["nonce"])
                  for s in a.submits}
        keys_b = {(s["job_id"], s["extranonce2"], s["nonce"])
                  for s in b.submits}
        check(len(subs_b) == 2 and not (keys_a & keys_b)
              and len(a.submits) + len(b.submits) == 4,
              "gate3: no share submitted twice across the switch")
    finally:
        client.stop_flag = True
        a.kill()
        b.kill()

    # startup exhaustion: both endpoints down, connect raises
    pa2, pb2 = free_port(), free_port()
    ev2 = ListEvidence()
    client2, policy2 = make_client(pa2, pb2, ev2)
    raised = False
    try:
        client2.connect_initial()
    except (ConnectionError, OSError, TimeoutError):
        raised = True
    check(raised and policy2.exhausted
          and ev2.count("endpoint_policy_exhausted") == 1,
          "gate3: startup exhaustion raises and is reported "
          "(backstop intact, no faked recovery)")


# ---------------------------------------------------------------- Gate 5


def read_events(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return out


def wait_event(path, pred, timeout_s, what):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        events = read_events(path)
        for i, e in enumerate(events):
            if pred(e):
                return i, events
        time.sleep(0.25)
    raise AssertionError(f"timeout waiting for {what}")


def test_gate5_isolated_instance():
    pa, pb = free_port(), free_port()
    a = MiniStub(pa, 0xAA, difficulty=0.0005, job_interval_s=10.0)
    b = MiniStub(pb, 0xBB, difficulty=0.0005, job_interval_s=10.0)
    a.start()
    b.start()
    iso = tempfile.mkdtemp(prefix="exp050-gate5-")
    proc = None
    try:
        for pkg in ("mining", "gpu"):
            shutil.copytree(
                os.path.join(ROOT, pkg), os.path.join(iso, pkg),
                ignore=shutil.ignore_patterns("__pycache__"))
        cpu_dst = os.path.join(iso, ".local", "cpu")
        os.makedirs(cpu_dst)
        cpu_src = os.path.join(ROOT, ".local", "cpu")
        for name in os.listdir(cpu_src):
            if name.endswith(".so"):
                shutil.copy2(os.path.join(cpu_src, name),
                             os.path.join(cpu_dst, name))
        cfg = {
            "mode": "pool",
            "pool": {"host": "127.0.0.1", "port": pa},
            "pool_health": {
                "enabled": True,
                "fallbacks": [{"host": "127.0.0.1", "port": pb}],
                "error_threshold": 2,
                "failback_interval_s": 5.0,
                "damping_window_s": 60.0,
                "max_failbacks_per_window": 1,
                "probe_timeout_s": 2.0,
            },
            "payout_address":
                "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3",
        }
        with open(os.path.join(iso, ".local",
                               "mining-endpoint.json"), "w") as f:
            json.dump(cfg, f, indent=2)
        ev_path = os.path.join(iso, "evidence.jsonl")
        log_path = os.path.join(iso, "miner.log")
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("BAL_POOL_")}
        with open(log_path, "w") as logf:
            proc = subprocess.Popen(
                [sys.executable,
                 os.path.join(iso, "mining", "mainnet_live.py"),
                 "--duration", "900", "--worker", "gate5",
                 "--evidence", ev_path],
                cwd=iso, env=env, stdout=logf,
                stderr=subprocess.STDOUT)
        wait_event(ev_path,
                   lambda e: e["event"] == "endpoint_policy_enabled",
                   60, "policy enabled in the isolated instance")
        check(True, "gate5: isolated miner started with the "
                    "policy enabled")
        wait_event(ev_path,
                   lambda e: e["event"] == "job"
                   and e.get("prevhash") == a.prevhash,
                   120, "first job from the primary")
        check(proc.poll() is None,
              "gate5: miner alive and mining on the primary")
        a.kill()
        idx, _ = wait_event(
            ev_path,
            lambda e: e["event"] == "endpoint_failover",
            60, "failover in the isolated instance")
        wait_event(ev_path,
                   lambda e: e["event"] == "job"
                   and e.get("prevhash") == b.prevhash,
                   60, "first job from the fallback")
        check(proc.poll() is None,
              "gate5: miner survived the primary's death "
              "(no process restart, no operator action)")
        wait_event(ev_path,
                   lambda e: e["event"] == "share_result"
                   and e.get("accepted"),
                   120, "an accepted share on the fallback")
        check(True, "gate5: mining verified on the fallback "
                    "through the full production path")
        a.start()
        wait_event(ev_path,
                   lambda e: e["event"] == "endpoint_failback",
                   120, "failback in the isolated instance")
        wait_event(ev_path,
                   lambda e: e["event"] == "job"
                   and e.get("prevhash") == a.prevhash,
                   60, "job from the primary after failback")
        check(proc.poll() is None,
              "gate5: miner alive after failback")
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=20)
        check(True, "gate5: isolated miner stopped by signal "
                    "after start, failover, recovery, failback")
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
        a.kill()
        b.kill()
        shutil.rmtree(iso, ignore_errors=True)


def main():
    test_policy_units()
    test_config()
    test_gate3_failover()
    test_gate3_unresolved_and_exhaustion()
    test_gate5_isolated_instance()
    print(f"ALL {CHECKS} EXP-050 ENDPOINT HEALTH CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
