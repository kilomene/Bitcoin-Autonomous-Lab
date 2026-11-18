#!/usr/bin/env python3
"""Fleet worker: the machine-side half of fleet mining
(EXP-055 coordinator fleet path, roadmap F2).

A fleet worker is a plain process any enrolled machine
runs. It holds no wallet, no pool account and no keys: it
registers with the fleet gateway's coordinator under the
fleet id, leases disjoint nonce chunks of the gateway's
current pool job, searches them with the production
ComputeEngine (the same runtime-dispatched backends the
live miner uses), hands every digest meeting the pool
share target to the coordinator's candidate queue, and
reports progress and completion through the wire
protocol. The gateway alone verifies candidates and
submits shares to the pool; the worker never contacts the
pool and could not submit a share if it tried.

Disjointness is by construction, not by trust: the
coordinator assigns each worker one extranonce2 slot per
job and leases only pending chunks inside that worker's
own slices, so two workers' (extranonce2, nonce) spaces
cannot overlap. The worker additionally refuses to hash a
lease whose version or ntime does not match the job
payload the gateway published, and abandons a chunk
uncompleted if the job generation moves on mid-scan (the
coordinator's declare_job supersedes the old job's leases
in the same instant, so an abandoned chunk is reclaimed
by the coordinator, never double-credited).

Examination honesty (EXP-038 frontier discipline): a
completion tells the coordinator the whole chunk was
examined, so the worker must be able to certify that.
The production ComputeEngine's multithreaded early-exit
search cannot certify it: its threads examine per-thread
sub-ranges and stop on a hit, so the examined set of one
call is not a prefix of the requested span and nonces can
remain unexamined behind a hit (the engine reports the
examined count, never a false prefix; the live pool miner
accepts this because the pool path makes no coverage
promise). This worker therefore pins its engine to one
search thread (threads=1), under which the examined set
of every call is exactly a prefix of the requested span,
and advances its scan position by the engine's own
attempted count, hit or miss. A chunk is then examined
nonce by nonce with no holes and no overlaps, and the
sum of attempted counts over a chunk equals the chunk
size exactly. Scale on a multicore machine is by running
more worker processes (each with its own worker id and
coordinator slot), never by widening one worker's search
threads.

Scope line, binding: this worker was exercised only in
the Stage 9 fleet staging on this host, over loopback,
against a local Stratum stub behind the gateway.
Running it on a second machine, over a real network, is
UNVERIFIED until a remote machine actually joins and its
shares are observed end to end.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gpu.engine import ComputeEngine
from mining.coordinator import CoordinatorClient
from mining.stratum_client import build_header


def target_for_difficulty(diff):
    return int((0xFFFF * (1 << 208)) / diff)


class FleetWorker:
    def __init__(self, args):
        self.args = args
        self.client = CoordinatorClient(host=args.gateway_host,
                                        port=args.gateway_port)
        self.log_fh = open(args.log, "a", buffering=1)
        self.engine = None
        self.chunks_completed = 0
        self.total_attempts = 0
        self.total_candidates = 0

    def log(self, event, **fields):
        rec = {"ts": time.time(), "event": event,
               "worker_id": self.args.worker_id,
               "pid": os.getpid(), **fields}
        self.log_fh.write(json.dumps(rec, sort_keys=True) + "\n")

    def call(self, msg):
        out = self.client.call(msg)
        if not out.get("ok"):
            # Refusals are named by error code only, never
            # by the response detail: the FOREIGN_FLEET
            # detail embeds the fleet ids (the one
            # presented and the one expected), and this
            # exception is precisely what lands in the
            # worker's stderr or a captured stdout file.
            # No file a worker produces may carry a fleet
            # id (plan section I).
            raise RuntimeError("coordinator refused %r: %s"
                               % (msg.get("type"),
                                  out.get("error")))
        return out["result"]

    def heartbeat(self):
        self.call({"type": "heartbeat",
                   "worker_id": self.args.worker_id,
                   "now": time.time()})

    def run(self):
        args = self.args
        r = self.call({"type": "register",
                       "worker_id": args.worker_id,
                       "fleet_id": args.fleet, "now": time.time()})
        self.log("registered", result=r)
        # threads=1 is load-bearing, not a performance
        # choice: see "Examination honesty" in the module
        # docstring.
        self.engine = ComputeEngine(requested="auto", threads=1)
        desc = self.engine.describe()
        self.log("backend_selected", backend=desc["backend"],
                 native_impl=desc["native_impl"], threads=1)
        deadline = time.time() + args.duration if args.duration \
            else None
        while deadline is None or time.time() < deadline:
            self.heartbeat()
            acc = self.call({"type": "accounting"})
            if acc["job_id"] is None:
                time.sleep(0.5)
                continue
            info = self.call({"type": "job_info"})
            if info is None \
                    or info["generation"] != acc["generation"]:
                time.sleep(0.25)
                continue
            lease = self.call({"type": "lease",
                               "worker_id": args.worker_id,
                               "now": time.time(),
                               "ttl": args.lease_ttl})
            if lease is None:
                if acc["complete"] and args.exit_on_complete:
                    self.log("job_complete",
                             chunks_completed=
                             self.chunks_completed,
                             total_attempts=self.total_attempts,
                             total_candidates=
                             self.total_candidates)
                    return 0
                time.sleep(0.3)
                continue
            self.work_chunk(lease, info)
        self.log("duration_complete",
                 chunks_completed=self.chunks_completed,
                 total_attempts=self.total_attempts,
                 total_candidates=self.total_candidates)
        return 0

    def work_chunk(self, lease, info):
        args = self.args
        wid = args.worker_id
        # Refuse to hash work that is not the job the
        # gateway published: a lease minted for another
        # version or ntime belongs to a superseded job.
        if lease["version"] != int(info["version"], 16) \
                or lease["ntime"] != int(info["ntime"], 16):
            self.log("lease_job_mismatch",
                     lease_id=lease["lease_id"],
                     lease_version=lease["version"],
                     lease_ntime=lease["ntime"],
                     job_version=info["version"],
                     job_ntime=info["ntime"])
            return
        en2_hex = "%0*x" % (info["extranonce2_size"] * 2,
                            lease["extranonce2"])
        job = {"job_id": info["job_id"],
               "prevhash": info["prevhash"],
               "coinb1": info["coinb1"],
               "coinb2": info["coinb2"],
               "merkle_branch": info["merkle_branch"],
               "version": info["version"],
               "nbits": info["nbits"],
               "ntime": info["ntime"]}
        header, _merkle, _cb = build_header(
            job, info["extranonce1"], en2_hex, 0, "wordswap")
        target = target_for_difficulty(float(info["difficulty"]))
        lo, hi = lease["lo"], lease["hi"]
        size = hi - lo
        pos = lo
        attempts = 0
        candidates = 0
        progressed = False
        abandoned = False
        while pos < hi:
            hit, att, _secs = self.engine.search_first_counted(
                header, target, pos, hi - pos)
            if att <= 0:
                self.log("scan_anomaly", lease_id=lease["lease_id"],
                         pos=pos, att=att)
                abandoned = True
                break
            attempts += att
            if hit is not None:
                nonce_hit, _digest = hit
                out = self.call({
                    "type": "candidate_submit",
                    "record": {
                        "job_id": info["job_id"],
                        "generation": info["generation"],
                        "extranonce2": lease["extranonce2"],
                        "version": lease["version"],
                        "ntime": lease["ntime"],
                        "nonce": nonce_hit,
                        "lease_id": lease["lease_id"],
                        "worker_id": wid}})
                candidates += 1
                self.log("candidate", lease_id=lease["lease_id"],
                         nonce=nonce_hit, queue_result=out)
            # Advance by the engine's own examined count,
            # hit or miss: with one search thread the
            # examined set of the call is exactly the
            # prefix [pos, pos + att), so the scan tiles
            # the chunk with no holes and no overlap.
            pos += att
            if not progressed and attempts >= size // 2:
                r = self.call({"type": "progress",
                               "worker_id": wid,
                               "lease_id": lease["lease_id"],
                               "token": lease["token"],
                               "examined": min(attempts, size)})
                progressed = True
                if r != "OK":
                    self.log("progress_refused",
                             lease_id=lease["lease_id"], result=r)
                    abandoned = True
                    break
            info_now = self.call({"type": "job_info"})
            if info_now is None \
                    or info_now["generation"] != info["generation"]:
                self.log("job_superseded_mid_chunk",
                         lease_id=lease["lease_id"])
                abandoned = True
                break
        self.total_attempts += attempts
        self.total_candidates += candidates
        if abandoned:
            self.log("chunk_abandoned", lease_id=lease["lease_id"],
                     slot=lease["slice"][0],
                     extranonce2=lease["extranonce2"],
                     lo=lo, hi=hi, attempts=attempts,
                     candidates=candidates)
            return
        r = self.call({"type": "complete", "worker_id": wid,
                       "lease_id": lease["lease_id"],
                       "token": lease["token"]})
        if r == "OK":
            self.chunks_completed += 1
        self.log("chunk_completed", lease_id=lease["lease_id"],
                 slot=lease["slice"][0],
                 extranonce2=lease["extranonce2"],
                 lo=lo, hi=hi, attempts=attempts,
                 candidates=candidates, complete_result=r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gateway-host", default="127.0.0.1")
    ap.add_argument("--gateway-port", type=int, default=4033)
    ap.add_argument("--fleet", default="nova-fleet")
    ap.add_argument("--fleet-id-file", default=None,
                    help="read the fleet id from this file "
                         "instead of --fleet; for production "
                         "use, so the id never appears on a "
                         "command line (it is read once at "
                         "startup, stripped, and never logged)")
    ap.add_argument("--worker-id", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--duration", type=int, default=0,
                    help="seconds to run; 0 means until stopped "
                         "or (with --exit-on-complete) the "
                         "current job completes")
    ap.add_argument("--lease-ttl", type=float, default=300.0)
    ap.add_argument("--exit-on-complete", action="store_true")
    args = ap.parse_args()
    if args.fleet_id_file:
        with open(args.fleet_id_file) as fh:
            args.fleet = fh.read().strip()
    worker = FleetWorker(args)
    try:
        return worker.run()
    finally:
        worker.client.close()


if __name__ == "__main__":
    sys.exit(main())
