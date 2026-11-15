#!/usr/bin/env python3
"""EXP-043 part 3: localhost loopback wire shim.

The EXP-035 prototype has no wire protocol (the EXP-035
final report states the protocol is specified, not
built). This script does NOT build that protocol. It is a
minimal loopback shim: a thin length-prefixed JSON
framing over TCP on 127.0.0.1 that forwards the
prototype's existing message shapes (register, heartbeat,
lease, progress, complete, steal, candidate submit) to a
LeaseManager and CandidateQueue living in a separate
coordinator PROCESS, so the round-trip cost of crossing a
process boundary on this VM can be measured.

Coordinator and workers are separate OS processes on
this one VM. Nothing leaves the loopback interface, no
fleet agent is contacted, and the numbers are loopback
numbers: they are a floor for any real network, never a
measurement of one.

Shim simplifications, stated plainly:
  * The coordinator stamps its own monotonic clock as
    `now` for every call; workers do not send time.
  * Heartbeat timeout and starvation window are widened
    to 60 s so expiry policy does not fire during a
    timing run; what is measured is transport plus
    manager call cost, not expiry behaviour.
  * One lock serialises all manager access in the
    coordinator (the prototype manager is not
    thread-safe); connection handling is threaded so
    network waits overlap.
"""

import json
import multiprocessing as mp
import os
import socket
import struct
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from exp043_common import FLEET, dist, loadavg, manifest, \
    write_result  # noqa: E402

from lease_manager import LeaseManager, LeaseError  # noqa: E402
from candidate_queue import CandidateQueue  # noqa: E402

VERSION = 0x20000000
NTIME = 1700000000
CHUNK = 4096
LEASES_PER_WORKER = 150
NONCE_PER_SLICE = CHUNK * LEASES_PER_WORKER


def send_msg(sock, obj):
    body = json.dumps(obj).encode()
    sock.sendall(struct.pack(">I", len(body)) + body)


def recv_msg(sock):
    hdr = b""
    while len(hdr) < 4:
        part = sock.recv(4 - len(hdr))
        if not part:
            raise ConnectionError("closed")
        hdr += part
    (n,) = struct.unpack(">I", hdr)
    body = b""
    while len(body) < n:
        part = sock.recv(n - len(body))
        if not part:
            raise ConnectionError("closed")
        body += part
    return json.loads(body)


class Coordinator:
    def __init__(self, n_workers):
        self.mgr = LeaseManager(FLEET,
                                heartbeat_timeout=60.0,
                                starvation_window=60.0)
        self.mgr.declare_job("job-wire", 1,
                             NONCE_PER_SLICE, CHUNK,
                             n_workers, [VERSION], [NTIME])
        self.queue = CandidateQueue()
        self.lock = threading.Lock()

    def handle(self, req):
        op = req["op"]
        a = req.get("args", {})
        now = time.monotonic()
        with self.lock:
            try:
                if op == "register":
                    return self.mgr.register_worker(
                        a["worker"], FLEET, now)
                if op == "heartbeat":
                    self.mgr.heartbeat(a["worker"], now)
                    return "OK"
                if op == "lease":
                    got = self.mgr.lease(a["worker"], now,
                                         ttl=60.0)
                    return got
                if op == "progress":
                    return self.mgr.progress(
                        a["worker"], a["lease_id"],
                        a["token"], a["examined"])
                if op == "complete":
                    return self.mgr.complete(
                        a["worker"], a["lease_id"],
                        a["token"])
                if op == "steal":
                    return self.mgr.steal(a["worker"], now,
                                          ttl=60.0)
                if op == "submit_candidate":
                    return self.queue.submit(a["record"])
                if op == "accounting":
                    acc = self.mgr.accounting()
                    acc["queue"] = self.queue.stats()
                    return acc
                return "UNKNOWN_OP"
            except LeaseError as exc:
                raise RpcError(str(exc))


class RpcError(Exception):
    pass


def serve(port_queue, n_workers):
    coord = Coordinator(n_workers)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(64)
    port_queue.put(srv.getsockname()[1])

    def client_thread(conn):
        with conn:
            while True:
                try:
                    req = recv_msg(conn)
                except (ConnectionError, struct.error):
                    return
                try:
                    result = coord.handle(req)
                    send_msg(conn, {"ok": True,
                                    "result": result})
                except RpcError as exc:
                    send_msg(conn, {"ok": False,
                                    "error": str(exc)})

    while True:
        conn, _ = srv.accept()
        threading.Thread(target=client_thread,
                         args=(conn,), daemon=True).start()


def call(sock, op, samples, **args):
    t0 = time.perf_counter_ns()
    send_msg(sock, {"op": op, "args": args})
    resp = recv_msg(sock)
    dt = time.perf_counter_ns() - t0
    samples.setdefault(op, []).append(dt)
    if not resp["ok"]:
        raise RuntimeError("%s: %s" % (op, resp["error"]))
    return resp["result"]


def worker_proc(idx, port, out_queue):
    wid = "w%d" % idx
    samples = {}
    try:
        _worker_run(wid, port, samples, out_queue)
    except Exception:
        import traceback
        out_queue.put({"worker": wid, "completed": 0,
                       "cycles": 0, "samples": samples,
                       "accounting_seen": None,
                       "error": traceback.format_exc()})


def _worker_run(wid, port, samples, out_queue):
    sock = socket.create_connection(("127.0.0.1", port))
    try:
        call(sock, "register", samples, worker=wid)
        completed = 0
        cycles = 0
        lost_to_steal = 0
        # Every worker steals once mid-run; a steal rotates
        # the victim lease's fencing token, so the victim's
        # next completion comes back STALE. That is correct
        # prototype behaviour (EXP-035 P3), and this harness
        # tolerates it: the lease is abandoned uncounted and
        # the worker leases again. The first version of
        # this shim asserted OK and died silently on the
        # first steal at W >= 4, hanging the run; the
        # failure and this fix are recorded in the report.
        while completed < LEASES_PER_WORKER:
            cycles += 1
            assert cycles < 20 * LEASES_PER_WORKER, \
                "worker cycle guard tripped"
            call(sock, "heartbeat", samples, worker=wid)
            lease = call(sock, "lease", samples, worker=wid)
            if lease is None:
                break
            size = lease["hi"] - lease["lo"]
            call(sock, "progress", samples, worker=wid,
                 lease_id=lease["lease_id"],
                 token=lease["token"], examined=size // 2)
            call(sock, "progress", samples, worker=wid,
                 lease_id=lease["lease_id"],
                 token=lease["token"], examined=size)
            res = call(sock, "complete", samples, worker=wid,
                       lease_id=lease["lease_id"],
                       token=lease["token"])
            if res == "STALE":
                lost_to_steal += 1
                continue
            assert res == "OK", res
            completed += 1
            if completed == LEASES_PER_WORKER // 2:
                call(sock, "steal", samples, worker=wid)
            if completed % 5 == 0:
                rec = {"job_id": "job-wire", "generation": 1,
                       "extranonce2": lease["extranonce2"],
                       "version": lease["version"],
                       "ntime": lease["ntime"],
                       "nonce": lease["lo"],
                       "lease_id": lease["lease_id"],
                       "worker_id": wid}
                r1 = call(sock, "submit_candidate", samples,
                          record=rec)
                r2 = call(sock, "submit_candidate", samples,
                          record=rec)
                assert (r1, r2) == ("ACCEPTED", "DUPLICATE"), \
                    (r1, r2)
        acc = call(sock, "accounting", samples)
        out_queue.put({"worker": wid, "completed": completed,
                       "cycles": cycles,
                       "lost_to_steal": lost_to_steal,
                       "samples": samples,
                       "accounting_seen": acc})
    finally:
        sock.close()


def run_config(n_workers):
    port_queue = mp.Queue()
    server = mp.Process(target=serve,
                        args=(port_queue, n_workers))
    server.start()
    port = port_queue.get()
    out_queue = mp.Queue()
    t0 = time.perf_counter()
    procs = [mp.Process(target=worker_proc,
                        args=(i, port, out_queue))
             for i in range(n_workers)]
    for p in procs:
        p.start()
    results = [out_queue.get(timeout=240)
               for _ in range(n_workers)]
    for p in procs:
        p.join()
    wall_s = time.perf_counter() - t0
    server.terminate()
    server.join()
    errors = [r["error"] for r in results if r.get("error")]
    if errors:
        raise RuntimeError("worker errors:\n"
                           + "\n".join(errors))
    merged = {}
    for r in results:
        for op, ss in r["samples"].items():
            merged.setdefault(op, []).extend(ss)
    # The last accounting snapshot any worker saw is not
    # necessarily final; take the one with the highest
    # coverage as the closest to final state.
    acc = max((r["accounting_seen"] for r in results),
              key=lambda a: a["unique_coverage"])
    return {
        "workers": n_workers,
        "leases_per_worker": LEASES_PER_WORKER,
        "wall_s": round(wall_s, 4),
        "completed_total": sum(r["completed"]
                               for r in results),
        "lost_to_steal_total": sum(r.get("lost_to_steal", 0)
                                   for r in results),
        "rtt": {op: dist(ss) for op, ss in merged.items()},
        "final_accounting": {
            "declared_total": acc["declared_total"],
            "unique_coverage": acc["unique_coverage"],
            "complete": acc["complete"],
            "queue": acc["queue"]},
    }


def main():
    payload = manifest("wire_loopback_shim")
    payload["shim"] = ("length-prefixed JSON over TCP "
                       "127.0.0.1, threaded coordinator, "
                       "one lock around the prototype "
                       "manager; NOT the EXP-035 wire "
                       "protocol, which remains unbuilt")
    payload["configs"] = []
    for w in (1, 4, 16):
        cfg = run_config(w)
        payload["configs"].append(cfg)
        print("wire config done: workers", w, "wall",
              cfg["wall_s"], "s", flush=True)
    payload["loadavg_at_end"] = loadavg()
    path = write_result("wire", payload)
    print("WROTE", path)


if __name__ == "__main__":
    main()
