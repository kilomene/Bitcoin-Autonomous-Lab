"""EXP-057 Gate 4: overhead in form against EXP-043 baselines.

Medians of 3 sessions, this VM only:
  * the tier's authenticated in-process submit path
    (session lookup, dedup, production header
    reconstruction, fast compare; verify_candidate runs
    only on candidate hits, as in production);
  * the same submission made directly to the wrapped
    SoloServer's fixed-difficulty path (the direct
    endpoint the tier generalises);
  * the stratum submit round trip over TCP loopback
    through AggregationTCPServer.
EXP-043 baselines for comparison: prototype manager calls
1 to 5 microseconds in-process; loopback wire shim floor
about 33 to 55 microseconds per round trip at 1 worker.
"""

import hashlib
import json
import os
import random
import socket
import statistics
import struct
import sys
import threading
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from exp057_campaign import (FLEET, PAYOUT,  # noqa: E402
                             PREDECLARATION_SHA256, FakeRPC,
                             check_predeclaration)
from mining.aggregation import (AggregationTCPServer,  # noqa: E402
                                AggregationTier)

N_SUBMITS = 300


def bench_inprocess(rng):
    rpc = FakeRPC()
    tier = AggregationTier(
        rpc, PAYOUT, FLEET, share_difficulty=2.0 ** -28,
        expected_chain="regtest")
    tier.refresh_workbase()
    tier.enroll_worker("w1", "tok-w1")
    sid, en1 = tier.open_session("w1", FLEET, "tok-w1")
    job = tier.current_job()
    curtime = "%08x" % job["template"]["curtime"]
    tier_times, direct_times = [], []
    for _ in range(N_SUBMITS):
        en2 = struct.pack(">I", rng.getrandbits(32)).hex()
        nonce = struct.pack(">I", rng.getrandbits(32)).hex()
        t0 = time.perf_counter_ns()
        tier.submit_share(sid, job["job_id"], en2, curtime,
                          nonce)
        tier_times.append(time.perf_counter_ns() - t0)
        t0 = time.perf_counter_ns()
        tier.solo._submit_share_fixed(job["job_id"], en1, en2,
                                      curtime, nonce,
                                      worker="w1")
        direct_times.append(time.perf_counter_ns() - t0)
    return (statistics.median(tier_times) / 1000.0,
            statistics.median(direct_times) / 1000.0)


class TcpWorker:
    def __init__(self, port, worker, token):
        self.sock = socket.create_connection(("127.0.0.1", port),
                                             timeout=60)
        self.f = self.sock.makefile("rwb")
        self._id = 0
        self.en1 = None
        self.job = None
        self.worker = worker
        self.rpc("mining.subscribe", ["exp057-worker/1.0"])
        r = self.rpc("mining.authorize", [worker, token])
        assert r["result"] is True, r
        while self.job is None or self.en1 is None:
            msg = json.loads(self.f.readline())
            self._notify(msg)

    def _notify(self, msg):
        if msg.get("method") == "mining.set_extranonce":
            self.en1 = msg["params"][0]
        elif msg.get("method") == "mining.notify":
            p = msg["params"]
            self.job = {"job_id": p[0], "ntime": p[7]}

    def rpc(self, method, params):
        self._id += 1
        self.f.write((json.dumps(
            {"id": self._id, "method": method,
             "params": params}) + "\n").encode())
        self.f.flush()
        while True:
            msg = json.loads(self.f.readline())
            if msg.get("id") == self._id:
                return msg
            self._notify(msg)

    def submit(self, en2, nonce):
        return self.rpc("mining.submit",
                        [self.worker, self.job["job_id"], en2,
                         self.job["ntime"], nonce])

    def close(self):
        self.sock.close()


def bench_tcp(rng):
    rpc = FakeRPC()
    tier = AggregationTier(
        rpc, PAYOUT, FLEET, share_difficulty=2.0 ** -28,
        expected_chain="regtest")
    tier.refresh_workbase()
    tier.enroll_worker("w1", "tok-w1")
    server = AggregationTCPServer(("127.0.0.1", 0), tier)
    port = server.server_address[1]
    th = threading.Thread(target=server.serve_forever,
                          daemon=True)
    th.start()
    try:
        w = TcpWorker(port, "w1", "tok-w1")
        times = []
        for _ in range(N_SUBMITS):
            en2 = struct.pack(">I", rng.getrandbits(32)).hex()
            nonce = struct.pack(">I", rng.getrandbits(32)).hex()
            t0 = time.perf_counter_ns()
            w.submit(en2, nonce)
            times.append(time.perf_counter_ns() - t0)
        w.close()
        return statistics.median(times) / 1000.0
    finally:
        server.shutdown()
        server.server_close()


def main():
    check_predeclaration()
    rng = random.Random(20261119)
    tier_us, direct_us, tcp_us = [], [], []
    for _ in range(3):
        a, b = bench_inprocess(rng)
        tier_us.append(a)
        direct_us.append(b)
        tcp_us.append(bench_tcp(rng))
    out = {"experiment": "EXP-057", "gate": 4,
           "host_cpu": "AMD EPYC 9D25",
           "predeclaration_sha256": PREDECLARATION_SHA256,
           "when_utc": datetime.now(timezone.utc).strftime(
               "%Y%m%dT%H%M%SZ"),
           "submits_per_session": N_SUBMITS,
           "tier_inprocess_submit_us_median_of_sessions":
               statistics.median(tier_us),
           "direct_solo_submit_us_median_of_sessions":
               statistics.median(direct_us),
           "tier_tcp_submit_us_median_of_sessions":
               statistics.median(tcp_us),
           "sessions": {"tier_inprocess_us": tier_us,
                        "direct_solo_us": direct_us,
                        "tier_tcp_us": tcp_us},
           "exp043_baselines": {
               "prototype_manager_calls_us": "1 to 5",
               "loopback_wire_shim_floor_us": "33 to 55"}}
    stamp = out["when_utc"]
    path = os.path.join(HERE, "RAW_RESULTS",
                        "overhead_%s.json" % stamp)
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print("WROTE", path, flush=True)
    print("EXP-057 GATE 4:", out, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
