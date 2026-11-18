#!/usr/bin/env python3
"""Fleet gateway: the pool-facing half of fleet mining
(EXP-055 coordinator fleet path, roadmap F2).

One gateway process holds the lab's single Stratum
connection to the pool (the same mining.stratum_client
StratumClient the live miner uses, the same endpoint
resolution, the same EXP-036 confirmation discipline) and
hosts a mining.coordinator.CoordinatorServer. Every pool
job is declared to the coordinator as a partitioned search
space: slices are (extranonce2 slot, counter) x version x
ntime over the full nonce range, so each registered fleet
worker leases disjoint chunks under its own extranonce2
slot and no two workers can ever be assigned the same
(extranonce2, nonce) work by construction.

Fleet workers never talk to the pool. A worker that finds
a digest at or below the share target hands it to the
coordinator's candidate queue; the gateway drains the
queue, re-verifies every candidate through
mining.candidate_verify.verify_candidate against the
reconstructed header (exactly the confirmation
mining/mainnet_live.py performs before submitting), checks
the template is still the freshest one, and only then
submits through its own pool connection. Pool verdicts are
recorded per fleet worker in the EXP-037 separated
statistics.

The coordinator wire protocol has no job-payload op, so
this module's server subclass adds one read-only op,
"job_info", returning the current job's Stratum fields,
the gateway session's extranonce1 and the pool difficulty.
Everything else is the EXP-055 dispatch, unmodified;
mining/coordinator.py itself is not changed by this
module.

Scope line, binding: this gateway was exercised only in
the Stage 9 fleet staging on this host, against a local
Stratum stub, with workers on loopback. Multi-machine
operation, real-network latency and behaviour, and live
deployment beside (or instead of) the production miner
are UNVERIFIED. Fleet activation was approved by the
owner on 2026-11-18; the live cutover (running this
gateway as the autopilot's miner child in place of
mining/mainnet_live.py) is a separate, later step and
nothing here performs it.

Hardening (2026-11-18, plan section I): a failed
coordinator bind is fatal and evidence-visible
(coordinator_bind_failed, nonzero exit) before the pool
leg starts; listening is claimed only after the bind is
confirmed. The fleet id itself is never written to
evidence: coordinator_up carries only a 12-hex-character
SHA-256 fingerprint of it, and the default evidence path
lives under .local/fleet.
"""

import argparse
import hashlib
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mining.candidate_verify import verify_candidate
from mining.coordinator import CoordinatorServer
from mining.mining_statistics import MiningStatistics
from mining.pow_engine import POW_LIMIT_MAINNET
from mining.stratum_client import Evidence, StratumClient, build_header

DEFAULT_ADDRESS = "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3"
ROOT = os.path.join(os.path.dirname(__file__), "..")


def target_for_difficulty(diff):
    """The pool's share target from its floating difficulty
    (identical formula to mining/mainnet_live.py)."""
    return int((0xFFFF * (1 << 208)) / diff)


class FleetCoordinatorServer(CoordinatorServer):
    """CoordinatorServer plus one read-only op, job_info,
    serving the current pool job payload the gateway
    installed. The payload is gateway state, not
    coordinator state, and is never journaled."""

    def __init__(self, *args, **kwargs):
        self.job_payload = None
        super().__init__(*args, **kwargs)

    def _dispatch(self, msg, journal=True):
        if msg.get("type") == "job_info":
            return {"ok": True, "result": self.job_payload}
        return super()._dispatch(msg, journal=journal)


class FleetGateway:
    def __init__(self, args):
        self.args = args
        self.ev = Evidence(args.evidence)
        self.stats = MiningStatistics()
        self.payloads = {}       # generation -> (job, payload, share_target)
        self.pending_submits = {}  # stratum id -> candidate record
        self.submitted = 0
        self.accepted = 0
        self.rejected = 0
        self.dropped_stale = 0
        self.dropped_invalid = 0
        self.block_candidates = 0
        self.declared_generation = None

        from mining.endpoint_config import resolve_endpoint
        pool_host, pool_port, endpoint_mode, endpoint_cfg = \
            resolve_endpoint(args.pool_host, args.pool_port)
        self.endpoint_mode = endpoint_mode
        user = f"{args.address}.{args.worker}"
        self.client = StratumClient(pool_host, pool_port, user,
                                    "x", self.ev)
        if endpoint_mode == "solo":
            self.client.suggest_difficulty = float(
                endpoint_cfg["solo"]["share_difficulty"])
        else:
            self.client.suggest_difficulty = 0.001
        self.ev.log("endpoint_selected", host=pool_host,
                    port=pool_port, mode=endpoint_mode)

        self._coord_error = None
        self._coord_exited = threading.Event()
        self.server = FleetCoordinatorServer(
            args.fleet, state_dir=args.state_dir,
            heartbeat_timeout=args.heartbeat_timeout,
            starvation_window=args.starvation_window,
            verifier=self._verify_candidate)
        # The fleet id is an admission secret and is never
        # written to evidence: evidence files and stdout
        # can leave this host, the id must not. Events
        # carry only a short non-reversible fingerprint,
        # enough to correlate runs of the same fleet.
        fleet_fp = hashlib.sha256(
            args.fleet.encode("utf-8")).hexdigest()[:12]
        self.ev.log("coordinator_up", fleet_fp=fleet_fp,
                    state_dir=args.state_dir,
                    replayed=self.server.replayed_ops,
                    epoch=self.server.core.epoch)

    # -- candidate verification (the drain verifier) --------
    def _verify_candidate(self, rec):
        """EXP-036 confirmation of one queued candidate,
        the same verdicts mining/mainnet_live.py requires:
        the reconstructed header's digests must agree
        across both independent implementations, the header
        target must be legal, and the exact integer compare
        against the share target decides share candidacy.
        Block candidacy comes from check_pow alone."""
        entry = self.payloads.get(rec["generation"])
        if entry is None:
            return "invalid"
        job, payload, share_target = entry
        en2_hex = "%0*x" % (payload["extranonce2_size"] * 2,
                            rec["extranonce2"])
        header, _merkle, _cb = build_header(
            job, payload["extranonce1"], en2_hex,
            rec["nonce"], "wordswap")
        v = verify_candidate(header, POW_LIMIT_MAINNET,
                             share_target=share_target)
        return v["classification"]

    # -- job declaration --------------------------------------
    def _maybe_declare(self):
        client = self.client
        with client.lock:
            job, gen, diff = client.current_job, \
                client.job_generation, client.difficulty
        if job is None or diff is None \
                or client.extranonce1 is None:
            return
        if gen == self.declared_generation:
            return
        payload = {
            "job_id": job["job_id"], "generation": gen,
            "coinb1": job["coinb1"], "coinb2": job["coinb2"],
            "merkle_branch": job["merkle_branch"],
            "prevhash": job["prevhash"],
            "version": job["version"], "nbits": job["nbits"],
            "ntime": job["ntime"],
            "extranonce1": client.extranonce1,
            "extranonce2_size": client.extranonce2_size,
            "difficulty": float(diff),
        }
        share_target = target_for_difficulty(float(diff))
        self.payloads[gen] = (job, payload, share_target)
        # Keep only the newest few generations for the
        # verifier; older records are dropped by the drain
        # as stale-generation before verification anyway.
        for old in sorted(self.payloads)[:-4]:
            del self.payloads[old]
        self.server.job_payload = payload
        out = self.server.handle_message({
            "type": "declare_job", "job_id": job["job_id"],
            "generation": gen,
            "nonce_count": self.args.nonce_count,
            "chunk_size": self.args.chunk_size,
            "n_slots": self.args.n_slots,
            "version_variants": [int(job["version"], 16)],
            "ntime_values": [int(job["ntime"], 16)],
            "counters_per_slot": 1})
        self.declared_generation = gen
        self.ev.log("job_declared", job_id=job["job_id"],
                    generation=gen, slices=out["result"],
                    nonce_count=self.args.nonce_count,
                    chunk_size=self.args.chunk_size,
                    n_slots=self.args.n_slots,
                    difficulty=float(diff))

    # -- candidate drain and pool submission -------------------
    def _drain_and_submit(self):
        out = self.server.handle_message(
            {"type": "candidate_drain"})
        if not out.get("ok"):
            return
        client = self.client
        for item in out["result"]:
            rec, verdict = item["record"], item["verdict"]
            if verdict not in ("share", "block_candidate"):
                self.dropped_invalid += 1
                self.ev.log("candidate_dropped", verdict=verdict,
                            worker=rec["worker_id"],
                            nonce=rec["nonce"])
                continue
            with client.lock:
                fresh = (client.current_job is not None
                         and client.job_generation
                         == rec["generation"]
                         and client.current_job["job_id"]
                         == rec["job_id"])
                job = client.current_job
            if not fresh:
                self.dropped_stale += 1
                self.ev.log("candidate_stale_dropped",
                            worker=rec["worker_id"],
                            nonce=rec["nonce"],
                            generation=rec["generation"])
                continue
            payload = self.payloads[rec["generation"]][1]
            en2_hex = "%0*x" % (payload["extranonce2_size"] * 2,
                                rec["extranonce2"])
            mid = client.submit(job, en2_hex, rec["nonce"])
            self.pending_submits[mid] = rec
            self.submitted += 1
            if verdict == "block_candidate":
                self.block_candidates += 1
                self.ev.log("block_candidate_submitted",
                            worker=rec["worker_id"],
                            nonce=rec["nonce"], id=mid)
            self.stats.record("pool_shares_submitted", 1,
                              worker=rec["worker_id"])
            self.ev.log("share_submitted",
                        worker=rec["worker_id"],
                        nonce=rec["nonce"], id=mid,
                        verdict=verdict)

    def _collect_verdicts(self):
        for mid in list(self.pending_submits):
            resp = self.client.responses.pop(mid, None)
            if resp is None:
                continue
            rec = self.pending_submits.pop(mid)
            accepted = bool(resp.get("result"))
            if accepted:
                self.accepted += 1
            else:
                self.rejected += 1
            self.stats.record(
                "pool_shares_accepted" if accepted
                else "pool_shares_rejected", 1,
                worker=rec["worker_id"])
            self.ev.log("share_result", worker=rec["worker_id"],
                        nonce=rec["nonce"], id=mid,
                        accepted=accepted,
                        error=resp.get("error"))

    # -- main loop ----------------------------------------------
    def _serve_coordinator(self):
        """Thread target for the coordinator listener.

        CoordinatorServer.serve binds before its accept
        loop, so a failed bind raises here, inside this
        thread. The exception is captured, never left to
        die silently on stderr: run() reads it through
        _coord_error and makes the failure fatal."""
        try:
            self.server.serve(self.args.coord_host,
                              self.args.coord_port)
        except Exception as exc:  # bind failure above all
            self._coord_error = exc
        finally:
            self._coord_exited.set()

    def run(self):
        args = self.args
        coord_thread = threading.Thread(
            target=self._serve_coordinator, daemon=True)
        coord_thread.start()
        # Listening is a fact, not a timer. serve() sets
        # _tcp only after bind and listen succeed, so wait
        # for exactly that, for a captured startup error,
        # or for a bounded deadline. A failed bind is
        # fatal and evidence-visible BEFORE the pool leg
        # starts: a gateway that cannot hear its workers
        # must never run pool-connected and declaring
        # while its evidence claims otherwise (the
        # 2026-11-18 soak defect, plan section H.4).
        bind_deadline = time.time() + 10.0
        while getattr(self.server, "_tcp", None) is None \
                and self._coord_error is None \
                and time.time() < bind_deadline:
            time.sleep(0.05)
        if getattr(self.server, "_tcp", None) is None:
            err = self._coord_error
            if err is None:
                err = RuntimeError(
                    "coordinator serve thread exited "
                    "without binding"
                    if self._coord_exited.is_set()
                    else "coordinator bind timed out")
            self.ev.log("coordinator_bind_failed",
                        host=args.coord_host,
                        port=args.coord_port,
                        error="%s: %s" % (type(err).__name__,
                                           err))
            return 4
        self.ev.log("coordinator_listening",
                    host=args.coord_host, port=args.coord_port)

        self.client.connect_initial()
        threading.Thread(target=self.client.reader_loop,
                         daemon=True).start()
        if not self.client.authorized.wait(timeout=30):
            self.ev.log("fatal", error="authorization failed")
            return 3
        self.ev.log("authorized", user=self.client.user)

        deadline = time.time() + args.duration
        last_status = 0.0
        last_expire = 0.0
        while time.time() < deadline \
                and not self.client.stop_flag:
            self._maybe_declare()
            self._drain_and_submit()
            self._collect_verdicts()
            now = time.time()
            if now - last_expire > 30:
                last_expire = now
                self.server.handle_message(
                    {"type": "expire", "now": now})
            if now - last_status > 10:
                last_status = now
                acc = self.server.handle_message(
                    {"type": "accounting"})["result"]
                queue = self.server.handle_message(
                    {"type": "queue_stats"})["result"]
                self.ev.log(
                    "status", submitted=self.submitted,
                    accepted=self.accepted,
                    rejected=self.rejected,
                    dropped_stale=self.dropped_stale,
                    dropped_invalid=self.dropped_invalid,
                    block_candidates=self.block_candidates,
                    statistics=self.stats.snapshot()["totals"],
                    coordinator=acc, queue=queue)
            time.sleep(0.25)
        self.server.write_snapshot()
        self.server.close()
        self.client.stop_flag = True
        self.ev.log("gateway_stop", submitted=self.submitted,
                    accepted=self.accepted,
                    rejected=self.rejected)
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=3600)
    ap.add_argument("--address", default=DEFAULT_ADDRESS)
    ap.add_argument("--worker", default=None,
                    help="pool worker name for the gateway's "
                         "own session; default is this "
                         "machine's hostname")
    ap.add_argument("--evidence",
                    default=os.path.join(
                        ROOT, ".local", "fleet",
                        "fleet-gateway.jsonl"))
    ap.add_argument("--pool-host", default=None)
    ap.add_argument("--pool-port", type=int, default=None)
    ap.add_argument("--fleet", default="nova-fleet")
    ap.add_argument("--fleet-id-file", default=None,
                    help="read the fleet id from this file "
                         "instead of --fleet; for production "
                         "use, so the id never appears on a "
                         "command line (it is read once at "
                         "startup, stripped, and never logged)")
    ap.add_argument("--coord-host", default="127.0.0.1")
    ap.add_argument("--coord-port", type=int, default=4033)
    ap.add_argument("--state-dir",
                    default=os.path.join(ROOT, ".local", "fleet"))
    ap.add_argument("--nonce-count", type=int, default=1 << 32)
    ap.add_argument("--chunk-size", type=int, default=1 << 24)
    ap.add_argument("--n-slots", type=int, default=32)
    ap.add_argument("--heartbeat-timeout", type=float,
                    default=120.0)
    ap.add_argument("--starvation-window", type=float,
                    default=120.0)
    args = ap.parse_args()
    if args.fleet_id_file:
        with open(args.fleet_id_file) as fh:
            args.fleet = fh.read().strip()
    if not args.worker:
        from mining.autopilot import default_worker
        args.worker = default_worker()
    os.makedirs(os.path.dirname(os.path.abspath(args.evidence)),
                exist_ok=True)
    gw = FleetGateway(args)
    return gw.run()


if __name__ == "__main__":
    sys.exit(main())
