#!/usr/bin/env python3
"""Deployment runner for the lab's stratum aggregation tier
(EXP-057, portfolio NOVA-ER-0017, register R-27).

Stage 9 enablements, 2026-11-18 (owner decision: enable all
five). EXP-057 proved the tier on this VM and left deployment
as the remaining step; this runner is that step, in the shape
of mining/solo_mainnet.py. It serves mining/aggregation.py's
AggregationTier against a node, with the fleet definition
(fleet id, operator token, worker enrollments) read from a
deployment file in .local that is never committed:

    .local/aggregation-tier.json
    {"fleet_id": "...", "operator_token": "...",
     "payout_address": "bc1q..." (optional; default the lab
     address from the endpoint config),
     "workers": [{"worker_id": "...", "token": "..."}, ...]}

Behaviour that matters:

- Fail closed: no deployment file, no tier. A missing or
  malformed deployment file is a fatal startup error, never
  an open tier.
- Chain is verified at startup: the node's
  getblockchaininfo chain must equal --chain (default
  "main"), and the tier's SoloServer re-checks the chain on
  every job refresh and refuses work during initial block
  download, exactly as the solo server does.
- The default port is 3334, deliberately NOT 3333: 3333 is
  the solo server's port, the armed solo cutover's target
  (docs/SOLO_CUTOVER.md). The tier must never squat it. The
  cutover still targets mining/solo_mainnet.py; making the
  tier the cutover front-end is a separate operator step
  that this runner does not perform.
- Submission authority stays out of the tier (the EXP-057
  rule): this runner configures NO upstream submitter, so
  the tier validates and accounts, queues verified block
  candidates as pending, and can never submit one on its
  own. Pending candidates are persisted in the snapshot
  and counted in the status file; submitting one remains
  an explicit operator action through
  AggregationTier.operator_submit_pending with a submitter
  the operator configures at that time.
- State: a snapshot (enrollments, counters, epoch) is
  written to .local/aggregation-snapshot.json every 30 s
  and on shutdown, and restored on startup with the
  EXP-055 restart rule (the epoch bumps; every pre-restart
  session is dead). Status is written atomically to
  .local/aggregation-status.json every 5 s.
- A fresh job is built whenever the node tip moves
  (checked every 2 s) or the current job ages past 120 s,
  mirroring the solo runner. Connected sessions keep the
  job they were issued; the tier's bounded job history
  classifies their late shares as stale, by design.

Run manually only if you mean it:

    python3 mining/aggregation_mainnet.py
"""

import argparse
import json
import os
import signal
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mining import endpoint_config
from mining.aggregation import AggregationTCPServer, AggregationTier
from mining.pow_engine import POW_LIMIT_MAINNET, POW_LIMIT_REGTEST

ROOT = os.path.join(os.path.dirname(__file__), "..")
DEFAULT_DEPLOYMENT = os.path.join(ROOT, ".local",
                                  "aggregation-tier.json")
DEFAULT_STATUS = os.path.join(ROOT, ".local",
                              "aggregation-status.json")
DEFAULT_SNAPSHOT = os.path.join(ROOT, ".local",
                                "aggregation-snapshot.json")
DEFAULT_PORT = 3334


def log(msg):
    line = (f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
            f"aggregation-mainnet: {msg}")
    print(line, flush=True)


def load_deployment(path):
    """The fleet definition. Raises ValueError on any
    malformation: a tier with a half-read fleet definition
    must never start."""
    with open(path) as f:
        dep = json.load(f)
    if not isinstance(dep, dict):
        raise ValueError("deployment file is not a JSON object")
    fleet_id = dep.get("fleet_id")
    if not isinstance(fleet_id, str) or not fleet_id:
        raise ValueError("deployment file has no fleet_id")
    workers = dep.get("workers")
    if not isinstance(workers, list) or not workers:
        raise ValueError("deployment file enrolls no workers")
    for w in workers:
        if not isinstance(w, dict) \
                or not isinstance(w.get("worker_id"), str) \
                or not w.get("worker_id") \
                or not isinstance(w.get("token"), str) \
                or not w.get("token"):
            raise ValueError(f"malformed worker enrollment: {w!r}")
    return dep


def write_status(tier, node_info, path, chain):
    job = tier.current_job()
    st = {
        "ts": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "fleet_id": tier.fleet_id,
        "epoch": tier.epoch,
        "generation": tier.generation,
        "workers_enrolled": sorted(tier.workers),
        "sessions_open": len(tier.sessions),
        "current_job": (job or {}).get("job_id"),
        "counters": dict(tier.counters),
        "per_worker": {k: dict(v)
                       for k, v in tier.per_worker.items()},
        "statistics": tier.stats.snapshot()["totals"],
        "pending_candidates": len(tier.pending_candidates),
        "upstream_submissions": tier.upstream_submissions,
    }
    if node_info:
        st["node"] = {
            "chain": node_info.get("chain"),
            "blocks": node_info.get("blocks"),
            "headers": node_info.get("headers"),
            "initialblockdownload": node_info.get(
                "initialblockdownload"),
            "tip": node_info.get("bestblockhash"),
        }
        st["node_ready"] = (
            node_info.get("chain") == chain
            and not node_info.get("initialblockdownload"))
    else:
        st["node"] = None
        st["node_ready"] = False
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, path)


class WorkbaseRefresher(threading.Thread):
    """Tip-watch job refresh, mirroring the solo runner's
    JobRefresher cadence: a fresh workbase when the tip
    moves or the current job ages past max_age_s. Refresh
    failures (node busy, chain wrong, IBD) are logged and
    retried on the next pass; the tier simply has no fresh
    job to hand out meanwhile, which is the designed
    refusal, not an error state."""

    def __init__(self, tier, rpc, log_fn, poll_s=2.0,
                 max_age_s=120.0):
        super().__init__(daemon=True, name="bal-tier-refresher")
        self.tier = tier
        self.rpc = rpc
        self.log = log_fn
        self.poll_s = poll_s
        self.max_age_s = max_age_s
        self._stop_evt = threading.Event()
        self._tip = None
        self._job_at = 0.0

    def stop(self):
        self._stop_evt.set()

    def run(self):
        while not self._stop_evt.is_set():
            try:
                tip = self.rpc.call("getbestblockhash")
                job = self.tier.current_job()
                stale = job is None or \
                    (time.time() - self._job_at) > self.max_age_s
                if tip != self._tip or stale:
                    self.tier.refresh_workbase()
                    self._tip = tip
                    self._job_at = time.time()
            except Exception as exc:
                self.log(f"workbase refresh deferred: {exc}")
            self._stop_evt.wait(self.poll_s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--share-difficulty", type=float,
                    default=None)
    ap.add_argument("--address", default=None)
    ap.add_argument("--node-config", default=None,
                    help="node-config.json for the upstream "
                         "node (default: the mainnet node's)")
    ap.add_argument("--chain", default="main",
                    help="expected chain of the upstream node "
                         "(main or regtest)")
    ap.add_argument("--deployment", default=DEFAULT_DEPLOYMENT)
    ap.add_argument("--status-path", default=DEFAULT_STATUS)
    ap.add_argument("--snapshot-path", default=DEFAULT_SNAPSHOT)
    args = ap.parse_args()

    try:
        dep = load_deployment(args.deployment)
    except (OSError, ValueError) as exc:
        log(f"FATAL: cannot load deployment file "
            f"{args.deployment}: {exc}; not starting (the "
            f"tier fails closed: no fleet definition, no tier)")
        return 2

    rpc = endpoint_config.load_mainnet_rpc(args.node_config)
    info = rpc.call("getblockchaininfo")
    if info.get("chain") != args.chain:
        log(f"FATAL: node chain is {info.get('chain')!r}, "
            f"expected {args.chain!r}; not starting")
        return 2
    log(f"node chain {info['chain']}, blocks {info['blocks']} "
        f"of headers {info['headers']}, ibd="
        f"{info.get('initialblockdownload')}")

    cfg = endpoint_config.load_config()
    payout = args.address or dep.get("payout_address") \
        or cfg["payout_address"]
    pow_limit = {"main": POW_LIMIT_MAINNET,
                 "regtest": POW_LIMIT_REGTEST}.get(args.chain)

    if os.path.exists(args.snapshot_path):
        tier = AggregationTier.restore(
            args.snapshot_path, rpc, payout,
            share_difficulty=args.share_difficulty,
            expected_chain=args.chain, pow_limit=pow_limit)
        log(f"restored tier snapshot {args.snapshot_path} "
            f"(epoch now {tier.epoch}; pre-restart sessions "
            f"are dead by the restart rule)")
        if tier.fleet_id != dep["fleet_id"]:
            log(f"FATAL: snapshot fleet {tier.fleet_id!r} != "
                f"deployment fleet {dep['fleet_id']!r}; "
                f"not starting")
            return 2
        for w in dep["workers"]:
            if w["worker_id"] not in tier.workers:
                tier.enroll_worker(w["worker_id"], w["token"])
                log(f"enrolled worker {w['worker_id']!r} "
                    f"(added by the deployment file)")
    else:
        tier = AggregationTier(
            rpc, payout, dep["fleet_id"],
            share_difficulty=args.share_difficulty,
            expected_chain=args.chain, pow_limit=pow_limit,
            operator_token=dep.get("operator_token"))
        for w in dep["workers"]:
            tier.enroll_worker(w["worker_id"], w["token"])
        log(f"fresh tier for fleet {dep['fleet_id']!r}: "
            f"{len(dep['workers'])} worker(s) enrolled")

    server = AggregationTCPServer((args.bind, args.port), tier)
    refresher = WorkbaseRefresher(tier, rpc, log)
    refresher.start()
    write_status(tier, info, args.status_path, args.chain)
    log(f"aggregation tier listening on {args.bind}:"
        f"{args.port}, fleet {dep['fleet_id']!r}, share "
        f"difficulty {tier.solo.share_difficulty}, payout "
        f"{payout}, upstream submitter: none (the tier "
        f"validates and accounts only)")

    stop = {"flag": False}

    def on_signal(signum, frame):
        stop["flag"] = True
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    serve_thread = threading.Thread(target=server.serve_forever,
                                    daemon=True)
    serve_thread.start()
    last_snapshot = time.time()
    try:
        while not stop["flag"]:
            time.sleep(5)
            try:
                node_info = rpc.call("getblockchaininfo")
            except Exception:
                node_info = None
            write_status(tier, node_info, args.status_path,
                         args.chain)
            if time.time() - last_snapshot >= 30.0:
                tier.write_snapshot(args.snapshot_path)
                last_snapshot = time.time()
    finally:
        refresher.stop()
        server.shutdown()
        server.server_close()
        tier.write_snapshot(args.snapshot_path)
        try:
            node_info = rpc.call("getblockchaininfo")
        except Exception:
            node_info = None
        write_status(tier, node_info, args.status_path,
                     args.chain)
        log("aggregation tier stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
