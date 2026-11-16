#!/usr/bin/env python3
"""EXP-051 Gate 4 harness: category F before/after for the
prepared-work prefetch queue (register R-33).

Same shape as the EXP-040 harness (research/sha256d/exp040/
category_f.py, imported and reused): the production
MiningEngine.mine_cycle against the local regtest node,
stage timing by delegating proxies, EXP-036 verification of
every accepted block, append-only session JSON. The only
variable between arms is the engine's use_prefetch flag:

  sync     use_prefetch=False: the current production
           behaviour (GBT fetch and prepare on the critical
           path of every cycle).
  prefetch use_prefetch=True: a background longpoll feed
           prepares the next template off the critical path;
           cycles serve from the queue when the EXP-025
           identity recomputation and the tip check pass.

Harness adaptations, all in this file: the feed is given
its own plain RPC connection through the engine's
prefetch_fetcher seam (in production the feed uses the
engine's wait_template; a separate connection here keeps
longpoll waits out of the stage timer, exactly as the
production feed's waits are not part of any cycle), the
prepare instrumentation is thread-aware (feed-thread
prepares are accumulated separately, never written into the
mining thread's segment stack), and each run records the
EXP-037 prefetch counter deltas so served and starved runs
are attributable per run.

Non-search overhead per block = cycle wall time minus the
search stage time (the EXP-040 definition), reported in
milliseconds. Nothing here is a hash rate.

Usage:
  python3 category_f_prefetch.py run-all
  python3 category_f_prefetch.py run --scenario B --arm prefetch \
      --sessions 1 --runs 2
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

_spec = importlib.util.spec_from_file_location(
    "exp040_category_f",
    os.path.join(ROOT, "research", "sha256d", "exp040",
                 "category_f.py"))
cf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cf)

from mining.engine import MiningEngine                        # noqa: E402
from gpu.engine import ComputeEngine                          # noqa: E402
from node.rpc_client import BitcoinRPC                        # noqa: E402

RAW_DIR = os.path.join(HERE, "RAW_RESULTS")
PREFETCH_CATS = ("prefetch_enqueued", "prefetch_served",
                 "prefetch_starved", "prefetch_dropped_identity",
                 "prefetch_dropped_stale",
                 "prefetch_dropped_superseded",
                 "prefetch_dropped_overflow")
MAIN_THREAD = threading.current_thread()


def make_fetcher():
    """The feed's longpoll fetch on its own connection:
    the same call MiningEngine.wait_template makes, on a
    plain (untimed) client."""
    plain = BitcoinRPC()

    def fetch(longpollid):
        client = plain.with_timeout(85)
        return client.call(
            "getblocktemplate",
            {"rules": ["segwit"], "longpollid": longpollid})
    return fetch


def instrument_engine_051(engine, timer, bg):
    """Thread-aware version of the EXP-040 instrumentation.
    prepare_template calls on the mining thread are timed
    as the "prepare" stage; calls on the feed thread are
    accumulated into bg (count and seconds) and never touch
    the segment stack. PreparedTemplate.build is wrapped
    once per prepared object (lock-guarded) so candidate
    construction steps are timed as "construct" wherever
    they run. For the prefetch arm, the queue serve attempt
    is timed as the "serve" stage."""
    orig_prepare = engine.prepare_template
    wrap_lock = threading.Lock()

    def timed_prepare(template):
        if threading.current_thread() is MAIN_THREAD:
            with timer.segment("prepare"):
                prep, was_hit = orig_prepare(template)
        else:
            t0 = time.perf_counter()
            prep, was_hit = orig_prepare(template)
            bg["prepare_s"] += time.perf_counter() - t0
            bg["prepare_calls"] += 1
        with wrap_lock:
            if not getattr(prep, "_exp051_timed", False):
                orig_build = prep.build

                def timed_build(extranonce_int, template=None,
                                now=None):
                    with timer.segment("construct"):
                        return orig_build(
                            extranonce_int, template=template,
                            now=now)
                prep.build = timed_build
                prep._exp051_timed = True
        return prep, was_hit

    engine.prepare_template = timed_prepare
    if engine.use_prefetch:
        orig_serve = engine._prefetch_try_serve

        def timed_serve():
            with timer.segment("serve"):
                return orig_serve()
        engine._prefetch_try_serve = timed_serve
    return engine


def prefetch_totals(engine):
    snap = engine.statistics.snapshot()["totals"]
    return {c: snap[c] for c in PREFETCH_CATS}


def run_session(scenario, arm, session_index, n_runs, loader=None):
    plain = BitcoinRPC()
    wallet = cf.wallet_rpc()
    payout = wallet.call("getnewaddress", "", "bech32")
    timer = cf.SegmentTimer()
    bg = {"prepare_s": 0.0, "prepare_calls": 0}
    trpc = cf.TimingRPC(BitcoinRPC(), timer)
    real_compute = ComputeEngine()
    tcompute = cf.TimingCompute(real_compute, timer, target_shift=0)
    use_prefetch = (arm == "prefetch")
    engine = MiningEngine(
        trpc, payout, compute=tcompute, batch_size=cf.BATCH_SIZE,
        extranonce_space=cf.EXTRANONCE_SPACE,
        use_prefetch=use_prefetch,
        prefetch_fetcher=make_fetcher() if use_prefetch else None)
    instrument_engine_051(engine, timer, bg)

    predeclaration_sha = None
    pre_path = os.path.join(HERE, "PREDECLARATION.md")
    if os.path.exists(pre_path):
        with open(pre_path, "rb") as fh:
            predeclaration_sha = hashlib.sha256(fh.read()).hexdigest()

    session = {
        "experiment": "EXP-051",
        "category": "F",
        "scenario": scenario,
        "arm": arm,
        "session_index": session_index,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "manifest": cf.build_manifest(real_compute.backend),
        "predeclaration_sha256": predeclaration_sha,
        "n_runs_declared": n_runs,
        "setup": {},
        "warmup": None,
        "runs": [],
    }
    session["manifest"]["use_prefetch"] = use_prefetch
    session["manifest"]["loadavg_at_start"] = list(os.getloadavg())

    def clear_mempool():
        """Setup only, never timed (disclosed amendment,
        2026-11-16): the shared regtest mempool accumulates
        foreign transactions from other suites running on
        this node (a scenario B setup observed 575 entries
        against the 500 the scenario defines). Mine blocks
        until the mempool is empty so the scenario definition
        (empty, or exactly the loader's 500) holds exactly,
        as the EXP-040 harness's asserts intend."""
        addr = loader.key.address if loader is not None \
            else payout
        for _ in range(5):
            if plain.call("getmempoolinfo")["size"] == 0:
                return
            plain.call("generatetoaddress", 1, addr)
        assert plain.call("getmempoolinfo")["size"] == 0, \
            "mempool did not clear"

    def setup_mempool():
        clear_mempool()
        if scenario == "B":
            secs = loader.reload()
            size = plain.call("getmempoolinfo")["size"]
            assert size == loader.n, (size, loader.n)
            return {"reload_seconds": secs, "mempool_size": size}
        size = plain.call("getmempoolinfo")["size"]
        assert size == 0, f"expected empty mempool, got {size}"
        return {"mempool_size": 0}

    try:
        session["setup"]["warmup_mempool"] = setup_mempool()
        warm = engine.mine_cycle()
        session["warmup"] = {
            "accepted": bool(warm.get("accepted")),
            "height": warm.get("height"),
            "hash": warm.get("hash"),
            "prefetch": prefetch_totals(engine),
        }
        if not warm.get("accepted"):
            raise RuntimeError(f"warm-up cycle not accepted: {warm}")

        for i in range(n_runs):
            setup_info = setup_mempool()
            timer.reset()
            before = prefetch_totals(engine)
            bg_before = dict(bg)
            t0 = time.perf_counter()
            result = engine.mine_cycle()
            wall = time.perf_counter() - t0
            totals, calls, covered = timer.stage_totals()
            after = prefetch_totals(engine)
            delta = {c: after[c] - before[c] for c in PREFETCH_CATS}
            search_s = totals.get("search", 0.0)
            run = {
                "run_index": i,
                "setup": setup_info,
                "accepted": bool(result.get("accepted")),
                "height": result.get("height"),
                "hash": result.get("hash"),
                "nonce": result.get("nonce"),
                "hashes_counted": result.get("hashes"),
                "batches": result.get("batches"),
                "tx_count": result.get("tx_count"),
                "cycle_wall_s": wall,
                "stages_s": {k: round(v, 6) for k, v in
                             sorted(totals.items())},
                "stage_calls": calls,
                "residual_s": wall - covered,
                "overhead_ms": (wall - search_s) * 1000.0,
                "served": delta["prefetch_served"] == 1,
                "prefetch_delta": delta,
                "bg_prepare_calls": bg["prepare_calls"]
                    - bg_before["prepare_calls"],
                "bg_prepare_s": bg["prepare_s"]
                    - bg_before["prepare_s"],
                "failed": False,
            }
            if not result.get("accepted"):
                run["failed"] = True
                run["fail_reason"] = result.get("reason")
            else:
                v_secs, v_ok, v_class = cf.verify_block(
                    plain, result["hash"])
                run["verify"] = {"seconds": v_secs, "ok": v_ok,
                                 "classification": v_class}
                if not v_ok:
                    run["failed"] = True
                    run["fail_reason"] = \
                        "EXP-036 verification gate failed"
            session["runs"].append(run)
            print(f"  [{scenario}/{arm} s{session_index} run {i}] "
                  f"accepted={run['accepted']} served={run['served']} "
                  f"wall={wall:.4f}s overhead_ms="
                  f"{run['overhead_ms']:.1f} failed={run['failed']}",
                  flush=True)
    finally:
        engine.close_prefetch()

    session["finished_utc"] = datetime.now(timezone.utc).isoformat()
    session["prefetch_totals"] = prefetch_totals(engine)
    if loader is not None:
        session["setup"]["loader"] = {
            "fund_seconds": loader.fund_seconds,
            "reload_seconds": loader.reload_seconds,
            "n_tx": loader.n,
        }
    os.makedirs(RAW_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(
        RAW_DIR,
        f"session_{scenario}_{arm}_{session_index}_{stamp}.json")
    with open(path, "x") as fh:
        json.dump(session, fh, indent=1)
    print(f"  session file: {path}", flush=True)
    return session


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    ra = sub.add_parser("run-all")
    ra.add_argument("--sessions", type=int, default=3)
    ra.add_argument("--runs-a", type=int, default=8)
    ra.add_argument("--runs-b", type=int, default=6)
    ra.add_argument("--n-tx", type=int, default=500)
    r1 = sub.add_parser("run")
    r1.add_argument("--scenario", required=True, choices="AB")
    r1.add_argument("--arm", required=True,
                    choices=("sync", "prefetch"))
    r1.add_argument("--sessions", type=int, default=1)
    r1.add_argument("--runs", type=int, default=4)
    r1.add_argument("--n-tx", type=int, default=500)
    args = ap.parse_args(argv)

    if args.cmd == "run-all":
        plan = []
        for s in range(args.sessions):
            plan.append(("A", "sync", s, args.runs_a))
            plan.append(("A", "prefetch", s, args.runs_a))
        for s in range(args.sessions):
            plan.append(("B", "sync", s, args.runs_b))
            plan.append(("B", "prefetch", s, args.runs_b))
        n_tx = args.n_tx
    else:
        plan = [(args.scenario, args.arm, s, args.runs)
                for s in range(args.sessions)]
        n_tx = args.n_tx

    loader = None
    if any(p[0] == "B" for p in plan):
        loader = cf.MempoolLoader(cf.wallet_rpc(), BitcoinRPC(),
                                  n_tx=n_tx)
    for scenario, arm, s, n_runs in plan:
        print(f"EXP-051 scenario {scenario} arm {arm} session {s}: "
              f"{n_runs} timed runs", flush=True)
        run_session(scenario, arm, s, n_runs, loader=loader)
    return 0


if __name__ == "__main__":
    sys.exit(main())
