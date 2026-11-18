"""Fleet gateway hardening suite (2026-11-18).

Pins the two fixes recorded in section I of
research/STAGE9/FLEET_ACTIVATION_PLAN.md, both found by
the 2026-11-18 production soak attempt (plan H.4):

- Fix 1: a failed coordinator bind is fatal and
  evidence-visible. Starting the gateway with an
  unbindable coordinator address exits nonzero (code 4),
  fast, writes coordinator_bind_failed, and never writes
  coordinator_listening. The positive side: a normal
  loopback start writes coordinator_listening only once
  the listener is really bound, proven by a fleet worker
  connecting, registering, and completing a whole job
  against a local stub pool.
- Fix 2: the fleet id never reaches a file these modules
  produce. With a known dummy fleet id, the id string
  appears nowhere in the gateway evidence, the gateway
  stdout, the worker log, or the worker stdout of a full
  local run; coordinator_up carries only the id's
  SHA-256 fingerprint. A worker refused for presenting a
  wrong fleet id likewise leaks neither id into its
  output: the refusal is named by error code only. A
  raw protocol probe additionally pins the D-1 root fix
  (fleet audit item 5): the refusal detail the
  coordinator returns on the wire itself contains
  neither the presented nor the expected fleet id.

Everything runs on loopback against an in-process stub
pool; every output lives in a temporary directory. No
real pool, no live stack, no .local state.
"""

import hashlib
import json
import os
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

REPO = os.path.join(os.path.dirname(__file__), "..")
GATEWAY = os.path.join(REPO, "mining", "fleet_gateway.py")
WORKER = os.path.join(REPO, "mining", "fleet_worker.py")

DUMMY = "DUMMYFLEETID-TEST-ONLY-0123456789abcdef"
WRONG = "WRONGFLEETID-TEST-ONLY-fedcba9876543210"
# RFC 5737 TEST-NET-1: never assigned to a local
# interface, so binding to it fails with EADDRNOTAVAIL
# on any host, exactly the soak's Errno 99 shape.
UNBINDABLE = "192.0.2.1"

CHECKS = 0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    if not cond:
        print(f"FAIL: {label}", flush=True)
        sys.exit(1)
    print(f"ok {CHECKS}: {label}", flush=True)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def read(path):
    if not os.path.exists(path):
        return ""
    with open(path) as fh:
        return fh.read()


def wait_for(path, needle, timeout=25.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if needle in read(path):
            return True
        time.sleep(0.1)
    return False


# -- in-process stub pool --------------------------------
# The smallest Stratum V1 double that serves one gateway
# session: subscribe, authorize, set_difficulty, one
# notify job, and accept-everything submit judgment. The
# job is synthetic in content but structurally real (the
# staging stub's shape); the gateway's own EXP-036
# verifier is what judges candidates before submission.

STUB_JOB = {
    "job_id": "stub-test-0001",
    "prevhash": hashlib.sha256(
        b"fleet gateway test prevhash").hexdigest(),
    "coinb1": "0100000001000000000000000000000000000000000000"
              "000000000000000000000000000000ffffffff1c",
    "coinb2": "2f466c65657447617465776179546573742f00000000"
              "0100f2052a010000001976a914"
              + "22" * 20 + "88ac00000000",
    "merkle_branch": [],
    "version": "20000000",
    "nbits": "17021673",
}
SHARE_DIFFICULTY = 1e-5


class _StubHandler(socketserver.StreamRequestHandler):
    def _send(self, obj):
        self.wfile.write((json.dumps(obj) + "\n").encode())
        self.wfile.flush()

    def handle(self):
        job = dict(STUB_JOB)
        job["ntime"] = "%08x" % int(time.time())
        for raw in self.rfile:
            try:
                msg = json.loads(raw.decode())
            except Exception:
                continue
            method, mid = msg.get("method"), msg.get("id")
            if method == "mining.subscribe":
                self._send({"id": mid, "result": [
                    [["mining.set_difficulty", "stub1"],
                     ["mining.notify", "stub2"]],
                    "a1b2c3d4", 4], "error": None})
            elif method == "mining.authorize":
                self._send({"id": mid, "result": True,
                            "error": None})
                self._send({"id": None,
                            "method": "mining.set_difficulty",
                            "params": [SHARE_DIFFICULTY]})
                self._send({"id": None,
                            "method": "mining.notify",
                            "params": [
                                job["job_id"], job["prevhash"],
                                job["coinb1"], job["coinb2"],
                                job["merkle_branch"],
                                job["version"], job["nbits"],
                                job["ntime"], True]})
            elif method == "mining.submit":
                self._send({"id": mid, "result": True,
                            "error": None})
            else:
                self._send({"id": mid, "result": True,
                            "error": None})


class _StubServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def start_stub():
    srv = _StubServer(("127.0.0.1", 0), _StubHandler)
    threading.Thread(target=srv.serve_forever,
                     daemon=True).start()
    return srv, srv.server_address[1]


def gateway_cmd(tmp, coord_host, coord_port, pool_port,
                duration):
    return [sys.executable, GATEWAY,
            "--pool-host", "127.0.0.1",
            "--pool-port", str(pool_port),
            "--coord-host", coord_host,
            "--coord-port", str(coord_port),
            "--fleet", DUMMY,
            "--worker", "testgw",
            "--state-dir", os.path.join(tmp, "state"),
            "--evidence", os.path.join(tmp, "gw.jsonl"),
            "--nonce-count", "65536",
            "--chunk-size", "4096",
            "--n-slots", "1",
            "--duration", str(duration)]


def fix1_bind_failure_is_fatal(tmp):
    """(a) Unbindable coordinator address: fast nonzero
    exit, coordinator_bind_failed written,
    coordinator_listening never written."""
    ev = os.path.join(tmp, "gw.jsonl")
    out_path = os.path.join(tmp, "gw.stdout")
    t0 = time.time()
    with open(out_path, "w") as out:
        proc = subprocess.run(
            gateway_cmd(tmp, UNBINDABLE, free_port(),
                        free_port(), 120),
            stdout=out, stderr=subprocess.STDOUT,
            timeout=30)
    elapsed = time.time() - t0
    check(proc.returncode == 4,
          "fix1: unbindable coordinator address exits "
          f"with code 4 (got {proc.returncode})")
    check(elapsed < 25.0,
          f"fix1: bind failure is fast ({elapsed:.1f}s, "
          "not the 120s duration)")
    text = read(ev)
    check("coordinator_bind_failed" in text,
          "fix1: evidence writes coordinator_bind_failed")
    check("EADDRNOTAVAIL" in text
          or "Cannot assign requested address" in text,
          "fix1: the bind error itself is in the evidence")
    check("coordinator_listening" not in text,
          "fix1: coordinator_listening is never written "
          "for a failed bind")
    check(DUMMY not in text and DUMMY not in read(out_path),
          "fix2: even the failed start writes no fleet id "
          "to evidence or stdout")


def fix1_and_fix2_full_run(tmp):
    """(b)+(c) Loopback start against the stub pool: the
    listener is real when coordinator_listening is
    written, a worker registers and completes the job,
    and the dummy fleet id appears in no output file."""
    stub, pool_port = start_stub()
    coord_port = free_port()
    ev = os.path.join(tmp, "gw.jsonl")
    gw_out_path = os.path.join(tmp, "gw.stdout")
    gw_out = open(gw_out_path, "w")
    gw = subprocess.Popen(
        gateway_cmd(tmp, "127.0.0.1", coord_port,
                    pool_port, 300),
        stdout=gw_out, stderr=subprocess.STDOUT)
    try:
        check(wait_for(ev, "coordinator_listening"),
              "fix1: loopback start writes "
              "coordinator_listening")
        # The event must be a fact: the port accepts a
        # connection at the moment the event exists.
        conn = socket.create_connection(
            ("127.0.0.1", coord_port), timeout=5)
        conn.close()
        check(True, "fix1: the coordinator port is really "
                    "bound when the event is written")
        text = read(ev)
        check("coordinator_bind_failed" not in text,
              "fix1: no bind failure on the healthy start")
        check(text.index("coordinator_up")
              < text.index("coordinator_listening"),
              "fix1: coordinator_up precedes "
              "coordinator_listening")

        # A worker presenting the wrong fleet id is
        # refused, and its captured output names the
        # refusal by error code only: neither fleet id
        # may appear in it.
        bad_out_path = os.path.join(tmp, "badworker.stdout")
        with open(bad_out_path, "w") as out:
            bad = subprocess.run(
                [sys.executable, WORKER,
                 "--gateway-host", "127.0.0.1",
                 "--gateway-port", str(coord_port),
                 "--fleet", WRONG,
                 "--worker-id", "w-test-bad",
                 "--log", os.path.join(tmp, "badworker.log"),
                 "--duration", "10"],
                stdout=out, stderr=subprocess.STDOUT,
                timeout=60)
        bad_text = read(bad_out_path)
        check(bad.returncode != 0,
              "fix2: a wrong-fleet worker is refused "
              "(nonzero exit)")
        check("FOREIGN_FLEET" in bad_text,
              "fix2: the refusal is named by its error "
              "code, so it stays diagnosable")
        check(WRONG not in bad_text and DUMMY not in bad_text,
              "fix2: the refused worker's output carries "
              "neither fleet id")

        # D-1 (fleet audit item 5, 2026-11-18): the raw
        # wire refusal itself must carry neither id. The
        # worker-output check above only sees the
        # worker's sanitized rendering; this probe speaks
        # the coordinator protocol directly and asserts
        # on the raw detail string the server returns.
        # Against the pre-fix coordinator the detail was
        # "worker ... presented fleet <WRONG>, expected
        # <DUMMY>", so this check fails there by
        # construction.
        from mining.coordinator import CoordinatorClient
        probe = CoordinatorClient(host="127.0.0.1",
                                  port=coord_port)
        try:
            resp = probe.call(
                {"type": "register",
                 "worker_id": "w-raw-probe",
                 "fleet_id": WRONG,
                 "now": time.time()})
        finally:
            probe.close()
        detail = resp.get("detail", "")
        check(resp.get("ok") is False
              and resp.get("error") == "FOREIGN_FLEET"
              and WRONG not in detail
              and DUMMY not in detail,
              "fix2: the raw FOREIGN_FLEET wire detail "
              "contains neither the presented nor the "
              "expected fleet id (D-1)")

        # The real worker: registers, leases, completes
        # the whole job, exits clean on completion.
        wlog = os.path.join(tmp, "worker.log")
        w_out_path = os.path.join(tmp, "worker.stdout")
        with open(w_out_path, "w") as out:
            w = subprocess.run(
                [sys.executable, WORKER,
                 "--gateway-host", "127.0.0.1",
                 "--gateway-port", str(coord_port),
                 "--fleet", DUMMY,
                 "--worker-id", "w-test-0",
                 "--log", wlog,
                 "--duration", "90",
                 "--exit-on-complete"],
                stdout=out, stderr=subprocess.STDOUT,
                timeout=120)
        check(w.returncode == 0,
              f"fix1: the worker completes the job and "
              f"exits 0 (got {w.returncode})")
        wtext = read(wlog)
        check('"registered"' in wtext,
              "fix1: the worker registered with the "
              "coordinator over TCP")
        check("chunk_completed" in wtext
              and "job_complete" in wtext,
              "fix1: the worker completed chunks and the "
              "whole job through the real listener")
        check(wait_for(ev, "job_declared", timeout=10),
              "fix1: the gateway declared the stub job to "
              "the coordinator")
    finally:
        gw.terminate()
        try:
            gw.wait(timeout=10)
        except subprocess.TimeoutExpired:
            gw.kill()
            gw.wait(timeout=10)
        gw_out.close()
        stub.shutdown()

    # (c) The dummy fleet id appears in NO output of the
    # full run; only its fingerprint is in the evidence.
    fp = hashlib.sha256(DUMMY.encode()).hexdigest()[:12]
    ev_text = read(ev)
    check(DUMMY not in ev_text,
          "fix2: the fleet id is absent from the gateway "
          "evidence of a full run")
    check(f'"fleet_fp": "{fp}"' in ev_text,
          "fix2: coordinator_up carries the fleet id's "
          "SHA-256 fingerprint instead of the id")
    check('"fleet":' not in ev_text,
          "fix2: no evidence event carries a fleet field")
    for name, path in (("gateway stdout", gw_out_path),
                       ("worker log", wlog),
                       ("worker stdout", w_out_path)):
        check(DUMMY not in read(path),
              f"fix2: the fleet id is absent from the "
              f"{name}")


def main():
    # Each scenario gets its own directory so evidence
    # files never share a path.
    with tempfile.TemporaryDirectory(
            prefix="fleet-gw-test-a-") as tmp:
        fix1_bind_failure_is_fatal(tmp)
    with tempfile.TemporaryDirectory(
            prefix="fleet-gw-test-b-") as tmp:
        fix1_and_fix2_full_run(tmp)
    print(f"Fleet gateway hardening suite: {CHECKS} "
          f"checks, ALL PASSED", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
