#!/usr/bin/env python3
"""Local fleet launcher: this machine's fleet bundle as
one supervised unit (plan section K.1/K.3, cutover
2026-11-18).

The autopilot supervises exactly one miner command.
Under the owner's fleet architecture each machine mines
its own pool session, so the production miner on this
machine is a bundle of three processes: one
mining/fleet_gateway.py holding this machine's pool
session and hosting the coordinator on loopback only,
and two mining/fleet_worker.py processes leasing chunks
from it. This launcher is that one command: it starts
the gateway and the workers, restarts a worker that
dies while the gateway lives, mirrors the gateway's
evidence into the production evidence log (below), and
when the gateway exits, or the launcher itself is
terminated, stops the workers and exits with the
gateway's exit status, so the autopilot's restart
semantics apply to the bundle as a whole exactly as
they applied to mining/mainnet_live.py.

Fleet id delivery: the id is a shared secret and never
appears on any command line, in any unit file, or in
any log. The gateway and the workers each receive it
with --fleet-id-file pointing at
.local/fleet/fleet_id.txt (mode 0600) and read it in
their own process at startup; this launcher never reads
the value at all.

Evidence discipline: the autopilot's liveness contract
(heartbeat share totals and the evidence-staleness
watchdog) reads evidence/mainnet-live.jsonl, the
lifetime production log mining/mainnet_live.py wrote.
The gateway keeps its own evidence file under
.local/fleet (plan section I), so the launcher mirrors
every line the gateway appends there into
evidence/mainnet-live.jsonl, verbatim and exactly once
(the mirror starts at the gateway file's size when the
launcher starts and follows appends only). The
gateway's event vocabulary is the same one
mainnet_live.py wrote (same Evidence class, same
share_result events), so the autopilot counts gateway
shares and judges gateway liveness with no code change
on its side. Mirroring can be disabled with
--mirror none (used by smoke runs).

Standard library only.
"""

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FLEET_DIR = os.path.join(ROOT, ".local", "fleet")
PRODUCTION_EVIDENCE = os.path.join(ROOT, "evidence",
                                   "mainnet-live.jsonl")


def log(msg):
    print(f"fleet_local: {msg}", flush=True)


class EvidenceMirror:
    """Follow the gateway evidence file and append every
    new complete line to the production evidence log."""

    def __init__(self, src, dst):
        self.src = src
        self.dst = dst
        self.offset = os.path.getsize(src) \
            if os.path.exists(src) else 0
        self.buf = b""
        self.stop = threading.Event()

    def pump(self):
        try:
            size = os.path.getsize(self.src)
        except OSError:
            return
        if size < self.offset:
            # The source was replaced; start over.
            self.offset = 0
            self.buf = b""
        if size == self.offset:
            return
        with open(self.src, "rb") as f:
            f.seek(self.offset)
            data = f.read()
        self.offset += len(data)
        self.buf += data
        lines = self.buf.split(b"\n")
        self.buf = lines.pop()
        if lines:
            with open(self.dst, "ab") as out:
                for line in lines:
                    out.write(line + b"\n")

    def run(self):
        while not self.stop.is_set():
            self.pump()
            self.stop.wait(1.0)
        self.pump()  # final drain after the gateway stops


class Bundle:
    def __init__(self, args):
        self.args = args
        self.gateway = None
        self.workers = {}        # worker id -> Popen
        self.worker_restart = {}  # worker id -> (due, backoff)
        self.stop_flag = False

    # -- process starts ------------------------------------
    def start_gateway(self):
        a = self.args
        cmd = [sys.executable,
               os.path.join(ROOT, "mining", "fleet_gateway.py"),
               "--duration", str(a.gateway_duration),
               "--worker", a.worker,
               "--coord-host", a.coord_host,
               "--coord-port", str(a.coord_port),
               "--state-dir", a.state_dir,
               "--evidence", a.evidence,
               "--fleet-id-file", a.fleet_id_file,
               "--nonce-count", "4294967296",
               "--chunk-size", "16777216",
               "--n-slots", "32",
               "--heartbeat-timeout", "120",
               "--starvation-window", "120"]
        if a.pool_host:
            cmd += ["--pool-host", a.pool_host]
        if a.pool_port:
            cmd += ["--pool-port", str(a.pool_port)]
        out = open(os.path.join(a.state_dir,
                                "fleet-gateway.stdout"), "a")
        self.gateway = subprocess.Popen(
            cmd, stdout=out, stderr=subprocess.STDOUT)
        log(f"gateway started pid={self.gateway.pid}")

    def start_worker(self, wid):
        a = self.args
        cmd = [sys.executable,
               os.path.join(ROOT, "mining", "fleet_worker.py"),
               "--gateway-host", a.coord_host,
               "--gateway-port", str(a.coord_port),
               "--fleet-id-file", a.fleet_id_file,
               "--worker-id", wid,
               "--log", os.path.join(
                   a.state_dir, f"worker-{wid}.jsonl"),
               "--duration", "0",
               "--lease-ttl", "300"]
        out = open(os.path.join(a.state_dir,
                                f"worker-{wid}.stdout"), "a")
        proc = subprocess.Popen(
            cmd, stdout=out, stderr=subprocess.STDOUT)
        self.workers[wid] = proc
        log(f"worker {wid} started pid={proc.pid}")
        return proc

    # -- shutdown -------------------------------------------
    def stop_children(self):
        procs = [p for p in self.workers.values()
                 if p.poll() is None]
        if self.gateway is not None \
                and self.gateway.poll() is None:
            procs.append(self.gateway)
        for p in procs:
            p.terminate()
        deadline = time.time() + 8.0
        for p in procs:
            left = deadline - time.time()
            if left <= 0:
                break
            try:
                p.wait(timeout=left)
            except subprocess.TimeoutExpired:
                pass
        for p in procs:
            if p.poll() is None:
                p.kill()

    def wait_for_coordinator(self, timeout=15.0):
        """Wait until the coordinator port accepts a TCP
        connection before starting any worker. A worker
        started against a not-yet-bound coordinator exits
        on connection refused (its designed behaviour for
        an unreachable gateway); waiting for the bind
        keeps every bundle start clean instead of
        spending a worker restart on the race. Bounded:
        if the port never opens, the workers start anyway
        and supervision handles it."""
        a = self.args
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.stop_flag \
                    or self.gateway.poll() is not None:
                return
            try:
                conn = socket.create_connection(
                    (a.coord_host, a.coord_port), timeout=1)
                conn.close()
                return
            except OSError:
                time.sleep(0.1)

    # -- supervision loop ------------------------------------
    def run(self):
        a = self.args
        os.makedirs(a.state_dir, exist_ok=True)
        mirror = None
        if a.mirror != "none":
            mirror = EvidenceMirror(a.evidence, a.mirror)
        self.start_gateway()
        self.wait_for_coordinator()
        for wid in a.worker_ids.split(","):
            wid = wid.strip()
            if wid:
                self.start_worker(wid)
                self.worker_restart[wid] = (None, 2.0)
        mirror_thread = None
        if mirror is not None:
            mirror_thread = threading.Thread(
                target=mirror.run, daemon=True)
            mirror_thread.start()
        try:
            while True:
                if self.stop_flag:
                    log("termination requested; stopping "
                        "the bundle")
                    self.stop_children()
                    return 0
                rc = self.gateway.poll()
                if rc is not None:
                    log(f"gateway exited rc={rc}; stopping "
                        "the workers")
                    self.stop_children()
                    return rc if rc >= 0 else 128 + (-rc)
                now = time.time()
                for wid, proc in list(self.workers.items()):
                    if proc.poll() is None:
                        continue
                    due, backoff = self.worker_restart[wid]
                    if due is None:
                        log(f"worker {wid} exited "
                            f"rc={proc.returncode}; restart "
                            f"in {backoff:.0f}s")
                        self.worker_restart[wid] = (
                            now + backoff,
                            min(backoff * 2, 60.0))
                    elif now >= due:
                        self.start_worker(wid)
                        self.worker_restart[wid] = (None, 2.0)
                time.sleep(0.5)
        finally:
            if mirror is not None:
                mirror.stop.set()
                if mirror_thread is not None:
                    mirror_thread.join(timeout=5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gateway-duration", type=int,
                    default=86400)
    ap.add_argument("--worker", default="htch-runtime",
                    help="pool worker name for this "
                         "machine's gateway session; the "
                         "same name the live miner used, "
                         "so pool accounting continues "
                         "under the one identity")
    ap.add_argument("--coord-host", default="127.0.0.1")
    ap.add_argument("--coord-port", type=int, default=4033)
    ap.add_argument("--state-dir", default=FLEET_DIR)
    ap.add_argument("--evidence",
                    default=os.path.join(
                        FLEET_DIR, "fleet-gateway.jsonl"))
    ap.add_argument("--fleet-id-file",
                    default=os.path.join(
                        FLEET_DIR, "fleet_id.txt"))
    ap.add_argument("--worker-ids", default="local-0,local-1")
    ap.add_argument("--mirror", default=PRODUCTION_EVIDENCE,
                    help="production evidence log to mirror "
                         "gateway evidence into, or 'none'")
    ap.add_argument("--pool-host", default=None)
    ap.add_argument("--pool-port", type=int, default=None)
    args = ap.parse_args()

    bundle = Bundle(args)

    def on_signal(signum, frame):
        bundle.stop_flag = True

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    return bundle.run()


if __name__ == "__main__":
    sys.exit(main())
