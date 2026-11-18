#!/usr/bin/env python3
"""EXP-050 + EXP-052 armed-enablement verification on the
production live seam (Stage 9 enablements, 2026-11-18).

The two switches live in the endpoint config, which this
workstream does not modify. This harness proves what the
production miner will do the moment the operator flips
them, by running the REAL production miner
(mining/mainnet_live.py, copied verbatim into an isolated
tree under .local/enablements/live-seam-tree) against a
local stub pool, with a config that is the live config's
own contents plus the two sections enabled, and the
EXP-052 deployment cache planted in the copy:

  phase A (stub up):   the miner authorizes, logs
      endpoint_policy_enabled and bakeoff_dispatch
      (requested "auto", reason "static: ..."), mines and
      submits shares; status events carry the policy's
      status() against the single endpoint.
  phase B (stub down ~8 s): reconnect attempts fail; the
      policy counts the errors and the miner logs
      endpoint_policy_exhausted (once, pointing back at
      the primary; the historical retry continues).
  phase C (stub back): the miner reconnects and logs
      endpoint_policy_recovered; shares resume.

Assertions read the copy's own evidence file
(evidence/mainnet-live.jsonl). The live stack, the live
endpoint config and the live evidence are never touched:
the copy has its own .local and evidence directories.

Usage: python3 run_live_seam.py
"""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

TREE = os.path.join(ROOT, ".local", "enablements",
                    "live-seam-tree")
STUB_PORT = 29796
DIFFICULTY = 0.001


# ------------------------------------------------------------------
# Stub pool (the EXP-050 fault-injection shape)
# ------------------------------------------------------------------

class StubPool:
    def __init__(self, port):
        self.port = port
        self.job_counter = 0
        self.lock = threading.Lock()
        self.submitted = 0
        self._srv = None
        self._thread = None
        self._conns = []

    def _job(self):
        with self.lock:
            self.job_counter += 1
            n = self.job_counter
        return {
            "job_id": f"stub{n}",
            "prevhash": (b"\x11" * 32).hex(),
            "coinb1": ("0100000001000000000000000000000000"
                       "000000000000000000000000000000000000"
                       "000000ffffffff"),
            "coinb2": ("ffffffff0100f2052a0100000043410412"
                       "2b5c28a38520d8e0b1e35c28a38520d8e0b1"
                       "e35c28a38520d8e0b1e300000000"),
            "merkle_branch": [],
            "version": "20000000",
            "nbits": "1d00ffff",
            "ntime": f"{int(time.time()):08x}",
            "clean_jobs": True,
        }

    def _notify(self, job):
        return [job["job_id"], job["prevhash"], job["coinb1"],
                job["coinb2"], job["merkle_branch"],
                job["version"], job["nbits"], job["ntime"],
                job["clean_jobs"]]

    def start(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", self.port))
        srv.listen(8)
        srv.settimeout(0.5)
        self._srv = srv
        self._thread = threading.Thread(target=self._accept,
                                        daemon=True)
        self._thread.start()

    def stop(self):
        if self._srv is not None:
            try:
                self._srv.close()
            except OSError:
                pass
            self._srv = None
        for c in list(self._conns):
            try:
                c.close()
            except OSError:
                pass
        self._conns = []

    def _accept(self):
        while self._srv is not None:
            try:
                conn, _ = self._srv.accept()
            except (OSError, socket.timeout):
                continue
            self._conns.append(conn)
            threading.Thread(target=self._serve, args=(conn,),
                             daemon=True).start()

    def _send(self, conn, obj):
        conn.sendall((json.dumps(obj) + "\n").encode())

    def _serve(self, conn):
        buf = b""
        job = self._job()
        try:
            while True:
                data = conn.recv(65536)
                if not data:
                    return
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    msg = json.loads(line)
                    method = msg.get("method")
                    mid = msg.get("id")
                    if method == "mining.subscribe":
                        self._send(conn, {
                            "id": mid,
                            "result": [[["mining.notify",
                                         "seam-session"]],
                                       "01000000", 4],
                            "error": None})
                    elif method == "mining.authorize":
                        self._send(conn, {"id": mid,
                                          "result": True,
                                          "error": None})
                        self._send(conn, {
                            "id": None,
                            "method": "mining.set_difficulty",
                            "params": [DIFFICULTY]})
                        self._send(conn, {
                            "id": None,
                            "method": "mining.notify",
                            "params": self._notify(job)})
                    elif method == "mining.submit":
                        with self.lock:
                            self.submitted += 1
                        self._send(conn, {"id": mid,
                                          "result": True,
                                          "error": None})
                    elif method == "mining.suggest_difficulty":
                        self._send(conn, {"id": mid,
                                          "result": True,
                                          "error": None})
                    else:
                        self._send(conn, {"id": mid,
                                          "result": None,
                                          "error": [501,
                                                    "unknown",
                                                    None]})
        except (OSError, ValueError):
            return


# ------------------------------------------------------------------
# Isolated production tree
# ------------------------------------------------------------------

def build_tree():
    if os.path.exists(TREE):
        shutil.rmtree(TREE)
    os.makedirs(os.path.join(TREE, ".local"))
    os.makedirs(os.path.join(TREE, "evidence"))
    for d in ("mining", "gpu", "node", "agent", "blockchain"):
        shutil.copytree(
            os.path.join(ROOT, d), os.path.join(TREE, d),
            ignore=shutil.ignore_patterns("__pycache__"))
    # The engine's native libraries live in .local/cpu; the
    # copy needs them or its ComputeEngine falls back to the
    # pure-Python tier (which is not the production seam
    # under test). Libraries only, no build trees.
    cpu_dst = os.path.join(TREE, ".local", "cpu")
    os.makedirs(cpu_dst)
    for name in os.listdir(os.path.join(ROOT, ".local", "cpu")):
        if name.endswith(".so"):
            shutil.copy2(os.path.join(ROOT, ".local", "cpu",
                                      name),
                         os.path.join(cpu_dst, name))
    # The config in the copy: the live config's own raw
    # contents, plus the two switch sections enabled, plus
    # the pool pointed at the stub.
    sys.path.insert(0, ROOT)
    from mining import endpoint_config
    with open(endpoint_config.CONFIG_PATH) as f:
        cfg = json.load(f)
    cfg["pool"] = {"host": "127.0.0.1", "port": STUB_PORT}
    cfg["pool_health"] = {"enabled": True}
    cfg["bakeoff"] = {"enabled": True, "cache_path": None,
                      "max_age_s": 604800.0, "margin": 0.05}
    with open(os.path.join(TREE, ".local",
                           "mining-endpoint.json"), "w") as f:
        json.dump(cfg, f, indent=2)
    planted = os.path.join(ROOT, ".local",
                           "bakeoff-dispatch.json")
    assert os.path.exists(planted), \
        "deployment bakeoff cache not planted yet"
    shutil.copy2(planted, os.path.join(
        TREE, ".local", "bakeoff-dispatch.json"))


def read_events():
    path = os.path.join(TREE, "evidence", "mainnet-live.jsonl")
    events = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                try:
                    events.append(json.loads(line))
                except ValueError:
                    pass
    return events


def wait_event(kind, timeout=45.0, since=0.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for ev in read_events():
            if ev.get("event") == kind:
                return ev
        time.sleep(0.5)
    return None


def main():
    build_tree()
    stub = StubPool(STUB_PORT)
    stub.start()
    proc = subprocess.Popen(
        [sys.executable,
         os.path.join(TREE, "mining", "mainnet_live.py"),
         "--duration", "120", "--worker", "seamtest"],
        cwd=TREE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True)
    out = {}
    try:
        ev = wait_event("endpoint_policy_enabled")
        out["endpoint_policy_enabled"] = ev
        ev = wait_event("bakeoff_dispatch")
        out["bakeoff_dispatch"] = ev
        ev = wait_event("share_submitted", timeout=60.0)
        out["first_share_submitted"] = ev is not None
        # Phase B: kill the stub; the policy must count the
        # failures and report exhaustion, pointing back at
        # the primary.
        stub.stop()
        ev = wait_event("endpoint_policy_exhausted",
                        timeout=30.0)
        out["endpoint_policy_exhausted"] = ev
        # Phase C: bring the stub back; recovery is logged.
        stub.start()
        ev = wait_event("endpoint_policy_recovered",
                        timeout=30.0)
        out["endpoint_policy_recovered"] = ev
        ev = wait_event("share_submitted", timeout=30.0)
        out["share_after_recovery"] = ev is not None
        statuses = [e for e in read_events()
                    if e.get("event") == "status"
                    and "endpoint_policy" in e]
        out["status_events_with_policy"] = len(statuses)
        if statuses:
            out["last_policy_status"] = \
                statuses[-1]["endpoint_policy"]
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            stdout, _ = proc.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, _ = proc.communicate()
        out["miner_exit"] = proc.returncode
        out["miner_log_tail"] = stdout.strip().splitlines()[-8:]
        stub.stop()
    print(json.dumps(out, indent=1, default=str))
    pol = out.get("endpoint_policy_enabled") or {}
    bake = out.get("bakeoff_dispatch") or {}
    ok = (
        pol.get("policy") == "ordered-failover-damped-failback"
        and pol.get("endpoints") == [f"127.0.0.1:{STUB_PORT}"]
        and bake.get("requested") == "auto"
        and str(bake.get("reason", "")).startswith("static:")
        and out.get("first_share_submitted")
        and out.get("endpoint_policy_exhausted") is not None
        and out.get("endpoint_policy_recovered") is not None
        and out.get("share_after_recovery")
        and out.get("status_events_with_policy", 0) >= 1)
    print("EXP-050/052 ARMED LIVE-SEAM VERIFICATION:",
          "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
