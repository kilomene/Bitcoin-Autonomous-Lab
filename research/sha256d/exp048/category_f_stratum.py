#!/usr/bin/env python3
"""EXP-048 category F end-to-end pipeline benchmark: the solo
and pool (Stratum) production pipelines.

Extends the EXP-040 category F harness (research/sha256d/
exp040/category_f.py, which measured the GBT pipeline) to the
lab's two Stratum pipelines, at the production configuration,
against the local regtest Bitcoin Core node:

- solo: the production SoloServer (mining/solo_server.py)
  serving jobs over the production SoloTCPServer, mined by a
  client loop with the mining/mainnet_live.py shape
  (StratumClient + ComputeEngine + EXP-036 confirmation +
  submit). Vardiff is DISABLED for the primary scenarios
  (the production configuration: mining/endpoint_config.py
  defaults it off and the armed cutover config carries no
  vardiff section). Scenario D enables it, harness-side only
  (a VarDiffController passed to the SoloServer constructor,
  built from the production default parameters), and is
  labelled separately everywhere.
- pool: a local pool-protocol stub built in this harness
  (a Stratum server feeding regtest-derived jobs, judging
  shares, and submitting network-target blocks to the node,
  the work a real pool does for a block), consumed by the
  same production client path. The harness NEVER connects
  to public-pool.io and never touches the live miner.

No production file is modified. Stage attribution is by
wrapping, in this process only: a thread-aware segment
timer; a delegating RPC proxy on each server's node client
(GBT fetch, submitblock, chain reads timed separately); the
solo server's submit/validate/refresh methods and its
module-level verify_candidate binding wrapped on the
harness's instance/module reference; a delegating compute
proxy on the client engine (search timing, and scenario C
difficulty amplification by target division inside the
proxy only).

A timed run starts when the harness begins it (after
scenario setup, which is never inside a timed run, exactly
as in EXP-040) and ends when the run's own block is
confirmed as the best block hash. Its first stage,
job_wait, measures the supply latency of the fresh job for
the new tip (the push-based analogue of EXP-040's in-cycle
GBT fetch): the previous block's post-block refresh and
broadcast may still be in flight when the run begins. For
scenario B the loaded template is built during setup; the
server stages of that setup window are recorded separately
in each run (setup_server_stages_s), so the loaded
template's construction cost is measured, not hidden. A run counts
only if it ends in exactly one block accepted by Core
(best-chain equality, the EXP-036 rule: the share response
is a claim, chain state is the fact) and the block's header
passes the EXP-036 exact verifier in the harness.

Scenarios (mirroring EXP-040):
  A  empty mempool, real regtest target, share difficulty
     0.02 (the production solo configuration; the stub sets
     the same). At regtest the network target (~2^255)
     admits about one hash in two while the share target at
     difficulty 0.02 sits at an expected 0.02 * 2^32 =
     85,899,346 hashes, so every accepted share is also a
     block and the search stage already carries real mass.
  B  mempool loaded with 500 simple transactions (the
     EXP-040 loader), template carries 501 transactions.
  C  amplified: empty mempool, the compute proxy divides
     the search (share) target by 2**2. EXP-040 divided the
     network target by 2**24; here the searched target is
     the share target, and dividing it by 2**24 would make
     the expected work per block 0.02 * 2^32 * 2^24 =
     2^50.4 hashes, not measurable in any feasible
     campaign. The factor 4 gives an expected ~3.4e8
     counted hashes per block, about 20x the search mass
     of EXP-040's scenario C. The factor is stated
     wherever the figures appear.
  D  solo only, separately labelled: vardiff ENABLED with
     the production default parameters (endpoint_config
     SOLO_VARDIFF_DEFAULTS, initial difficulty 0.02),
     empty mempool. Everything else identical to A.

Usage:
  python3 category_f_stratum.py run-all
  python3 category_f_stratum.py run --pipeline solo \
      --scenario A --sessions 3 --runs 8

Session files are append-only JSON in RAW_RESULTS next to
this file; a rerun creates new files, never overwrites.
"""

import argparse
import hashlib
import json
import math
import os
import platform
import socket
import socketserver
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "research", "sha256d",
                                "exp040"))

import category_f as exp040  # noqa: E402  (EXP-040 harness)

import mining.solo_server as solo_module  # noqa: E402
from gpu.engine import ComputeEngine  # noqa: E402
from mining import endpoint_config  # noqa: E402
from mining.candidate_verify import (verify_candidate,  # noqa: E402
                                       verify_chain_acceptance)
from mining.engine import (address_script_pubkey,  # noqa: E402
                             build_coinbase, strip_witness)
from mining.mainnet_live import call_attempts  # noqa: E402
from mining.mainnet_live import target_for_difficulty
from mining.pow import dsha256  # noqa: E402
from mining.pow_engine import POW_LIMIT_REGTEST  # noqa: E402
from mining.solo_server import (DIFF1, SoloServer,  # noqa: E402
                                  SoloTCPServer, VarDiffController,
                                  attach_witness, merkle_branch,
                                  share_target_for)
from mining.stratum_client import (Evidence, StratumClient,  # noqa: E402
                                     build_header)
from node.rpc_client import BitcoinRPC  # noqa: E402

RAW_DIR = os.path.join(HERE, "RAW_RESULTS")
SHARE_DIFFICULTY = endpoint_config.SOLO_SHARE_DIFFICULTY  # 0.02
AMPLIFY_SHIFT = 2          # scenario C: search target / 2**2
SOLO_BASE_PORT = 33521
POOL_BASE_PORT = 33621
CONTENT_FILES = ("mining/solo_server.py", "mining/stratum_client.py",
                 "mining/mainnet_live.py", "mining/candidate_verify.py",
                 "mining/engine.py", "gpu/engine.py")
CLIENT_STAGES = ("construct", "search", "verify_client",
                 "submit_send")
SOLO_SERVER_STAGES = ("srv_submit_total", "srv_validate",
                      "srv_verify", "srv_refresh_total", "srv_gbt",
                      "srv_submit", "srv_chain", "srv_rpc_other")
POOL_SERVER_STAGES = ("pool_submit_total", "pool_validate",
                      "pool_verify", "pool_assemble", "pool_gbt",
                      "pool_submit", "pool_chain", "pool_rpc_other")


# ---------------------------------------------------------------- timer

class ThreadTimer:
    """Segment timer safe across threads: each thread keeps
    its own stack, so the solo server's handler thread and the
    harness's client thread can record into one timer. Stage
    totals are exclusive times computed per thread and summed
    (segments never nest across threads in this design)."""

    def __init__(self):
        self._local = threading.local()
        self._lock = threading.Lock()
        self.segments = []   # [label, start, end, thread_ident]

    @contextmanager
    def segment(self, label):
        stack = getattr(self._local, "stack", None)
        if stack is None:
            stack = self._local.stack = []
        t0 = time.perf_counter()
        stack.append(label)
        try:
            yield
        finally:
            t1 = time.perf_counter()
            stack.pop()
            with self._lock:
                self.segments.append(
                    [label, t0, t1, threading.get_ident()])

    def totals(self):
        """{label: exclusive seconds} over all segments so
        far, plus per-label call counts under label + '#n'."""
        with self._lock:
            segs = list(self.segments)
        by_thread = {}
        for s in segs:
            by_thread.setdefault(s[3], []).append(s)
        totals = {}
        for _ident, group in by_thread.items():
            group = sorted(group, key=lambda s: (s[1], -s[2]))
            exclusive = [s[2] - s[1] for s in group]
            stack = []
            for i, s in enumerate(group):
                while stack and group[stack[-1]][2] <= s[1] + 1e-12:
                    stack.pop()
                if stack:
                    exclusive[stack[-1]] -= (s[2] - s[1])
                stack.append(i)
            for i, s in enumerate(group):
                totals[s[0]] = totals.get(s[0], 0.0) + exclusive[i]
                totals[s[0] + "#n"] = totals.get(s[0] + "#n", 0) + 1
        return totals


def stage_diff(after, before, labels):
    return {k: round(after.get(k, 0.0) - before.get(k, 0.0), 6)
            for k in labels}


# ---------------------------------------------------------------- proxies

class ThreadRPC:
    """Delegating proxy over BitcoinRPC timing call() by
    method under a per-pipeline prefix: getblocktemplate ->
    <p>gbt, submitblock -> <p>submit, chain reads ->
    <p>chain, everything else -> <p>rpc_other."""

    _MAP = {"getblocktemplate": "gbt", "submitblock": "submit",
            "getbestblockhash": "chain", "getblockheader": "chain",
            "getblockchaininfo": "chain", "getblockcount": "chain",
            "getblock": "chain"}

    def __init__(self, real, timer, prefix):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_timer", timer)
        object.__setattr__(self, "_prefix", prefix)

    def call(self, method, *params):
        timer = object.__getattribute__(self, "_timer")
        prefix = object.__getattribute__(self, "_prefix")
        label = prefix + self._MAP.get(method, "rpc_other")
        with timer.segment(label):
            return object.__getattribute__(self, "_real").call(
                method, *params)

    def with_timeout(self, timeout, retries=1):
        real = object.__getattribute__(self, "_real")
        timer = object.__getattribute__(self, "_timer")
        prefix = object.__getattribute__(self, "_prefix")
        return ThreadRPC(real.with_timeout(timeout, retries),
                         timer, prefix)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_real"), name)


class TimingCompute:
    """Delegating proxy over ComputeEngine timing the search
    entries. With target_shift > 0 it divides the search
    target by 2**target_shift before delegating (scenario C
    difficulty amplification, harness-side only; see the
    module docstring). Identical in shape to EXP-040's."""

    def __init__(self, real, timer, target_shift=0):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_timer", timer)
        object.__setattr__(self, "_shift", target_shift)

    def _target(self, target):
        shift = object.__getattribute__(self, "_shift")
        return target >> shift if shift else target

    def search_first(self, header, target, start, count):
        timer = object.__getattribute__(self, "_timer")
        real = object.__getattribute__(self, "_real")
        with timer.segment("search"):
            return real.search_first(
                header, self._target(target), start, count)

    def search_first_counted(self, header, target, start, count):
        timer = object.__getattribute__(self, "_timer")
        real = object.__getattribute__(self, "_real")
        with timer.segment("search"):
            return real.search_first_counted(
                header, self._target(target), start, count)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_real"), name)


def compute_span(engine):
    """Scan chunk exactly as mining/mainnet_live.py sizes it:
    about one second of the probed rate, clamped to
    [2**20, 2**24]."""
    probe = engine.last_probe_rate
    if probe and probe > 0:
        return 1 << max(20, min(24, int(math.log2(probe))))
    return 1 << 22


# ---------------------------------------------------------------- miner loop

class JobSuperseded(Exception):
    """A new job generation replaced the run's job mid-search
    (not by this run's own block). The run is recorded failed;
    production would abandon the round the same way."""


class MinerState:
    """Per-session client-loop state. The loop body mirrors
    mining/mainnet_live.py: poll (job, generation, difficulty)
    under the client lock, build the header per extranonce2
    round, scan ~1-second spans with search_first, account
    attempts via call_attempts (the engine's counted stats,
    never the requested span), confirm every candidate
    through the EXP-036 verifier before submitting, and let
    block candidacy come from the verifier alone."""

    def __init__(self, client, compute, timer, plain_rpc,
                 span_size):
        self.client = client
        self.compute = compute
        self.timer = timer
        self.plain = plain_rpc
        self.span_size = span_size
        self.en2_counter = 0
        self.last_mined_job_id = None

    def _wait_verdict(self, mid, timeout_s):
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < timeout_s:
            resp = self.client.responses.get(mid)
            if resp is not None:
                return bool(resp.get("result")), time.perf_counter()
            time.sleep(0.001)
        return None, time.perf_counter()

    def mine_one(self, cycle_t0, server, deadline_s):
        """Mine exactly one block. cycle_t0 is the run's start
        instant (the harness begins the run after scenario
        setup); the cycle ends at chain confirmation of the
        run's block. Returns (run, t_confirm). Raises on
        warm-up-class failures; the session runner converts
        timed-run exceptions into recorded failed runs."""
        client = self.client
        timer = self.timer
        # --- job wait: the fresh job for the new tip (and, in
        # scenario B, the harness-refreshed loaded job) must be
        # the server's current job and held by the client.
        while True:
            with client.lock:
                job = client.current_job
                gen = client.job_generation
                diff = client.difficulty
            if (job is not None and diff is not None
                    and client.authorized.is_set()
                    and job["job_id"] == server.current_job_id()
                    and job["job_id"] != self.last_mined_job_id):
                break
            if time.perf_counter() - cycle_t0 > deadline_s:
                raise TimeoutError("no fresh job within deadline")
            time.sleep(0.002)
        t_job = time.perf_counter()
        job_wait = t_job - cycle_t0
        target = target_for_difficulty(float(diff))
        total_hashes = 0
        shares_only = 0
        run = {"job_id": job["job_id"], "generation": gen,
               "difficulty": diff, "failed": False,
               "tx_count": server.template_tx_count(),
               "branch_len": len(job["merkle_branch"])}
        while True:  # extranonce2 rounds
            self.en2_counter += 1
            en2 = "%0*x" % (client.extranonce2_size * 2,
                            self.en2_counter)
            with timer.segment("construct"):
                header, _m, _cb = build_header(
                    job, client.extranonce1, en2, 0, "wordswap")
            nonce = 0
            while nonce < (1 << 32):
                with client.lock:
                    if client.job_generation != gen:
                        raise JobSuperseded(
                            f"generation {gen} superseded")
                if time.perf_counter() - cycle_t0 > deadline_s:
                    raise TimeoutError("search deadline exceeded")
                span = min(self.span_size, (1 << 32) - nonce)
                hit = self.compute.search_first(
                    header, target, nonce, span)
                total_hashes += call_attempts(
                    self.compute, hit, nonce)
                nonce += span
                if hit is None:
                    continue
                found, digest = hit
                with timer.segment("construct"):
                    check_header, _m2, _c2 = build_header(
                        job, client.extranonce1, en2, found,
                        "wordswap")
                with timer.segment("verify_client"):
                    v = verify_candidate(
                        check_header, POW_LIMIT_REGTEST,
                        share_target=target)
                with client.lock:
                    fresh = client.job_generation == gen
                confirmed = (digest == v["digest"]
                             and v["digests_agree"]
                             and v["valid_header"]
                             and v["meets_share_target"] and fresh)
                if confirmed and v["meets_network_target"]:
                    block_hash = v["digest"][::-1].hex()
                    with timer.segment("submit_send"):
                        mid = client.submit(job, en2, found)
                    t_sent = time.perf_counter()
                    verdict, t_verdict = self._wait_verdict(
                        mid, 180)
                    verdict_wait = t_verdict - t_sent
                    ok = False
                    t_confirm = t_verdict
                    while time.perf_counter() - t_verdict < 180:
                        if self.plain.call(
                                "getbestblockhash") == block_hash:
                            ok = True
                            t_confirm = time.perf_counter()
                            break
                        time.sleep(0.005)
                    wall = t_confirm - cycle_t0
                    run.update({
                        "accepted": bool(ok and verdict),
                        "hash": block_hash, "nonce": found,
                        "hashes_counted": total_hashes,
                        "shares_only": shares_only,
                        "cycle_wall_s": wall,
                        "job_wait_s": job_wait,
                        "verdict_wait_s": verdict_wait,
                        "confirm_s": t_confirm - t_verdict,
                        "verdict": verdict,
                        "chain_confirmed": ok,
                    })
                    if not run["accepted"]:
                        run["failed"] = True
                        run["fail_reason"] = (
                            "verdict/chain confirmation failed: "
                            f"verdict={verdict} chain={ok}")
                    else:
                        self.last_mined_job_id = job["job_id"]
                        hdr = self.plain.call(
                            "getblockheader", block_hash, True)
                        run["height"] = hdr["height"]
                    return run, t_confirm
                if confirmed:
                    # A share that is not a block candidate:
                    # submitted without blocking the search
                    # (production shape); at regtest difficulty
                    # this branch is not expected to fire,
                    # because the network target is far easier
                    # than the share target.
                    client.submit(job, en2, found)
                    shares_only += 1
                nonce = max(nonce, found + 1)
            # extranonce2 round exhausted: next round.


# ---------------------------------------------------------------- solo pipeline

def instrument_solo(srv, timer):
    """Wrap, in this process only, the harness's SoloServer
    instance methods and the solo_server module's
    verify_candidate binding, so the server's share-handling
    stages are timed on its handler thread. Production files
    are untouched."""
    orig_submit = srv.submit_share

    def timed_submit(*a, **k):
        with timer.segment("srv_submit_total"):
            return orig_submit(*a, **k)
    srv.submit_share = timed_submit

    orig_validate = srv.validate_share

    def timed_validate(*a, **k):
        with timer.segment("srv_validate"):
            return orig_validate(*a, **k)
    srv.validate_share = timed_validate

    orig_refresh = srv.refresh_job

    def timed_refresh(*a, **k):
        with timer.segment("srv_refresh_total"):
            return orig_refresh(*a, **k)
    srv.refresh_job = timed_refresh

    orig_vc = solo_module.verify_candidate

    def timed_vc(*a, **k):
        with timer.segment("srv_verify"):
            return orig_vc(*a, **k)
    solo_module.verify_candidate = timed_vc
    return orig_vc


def make_vardiff_controller():
    """The production default vardiff parameters
    (endpoint_config.solo_vardiff_config over the on-disk
    config, which carries no vardiff section, so the declared
    defaults), initial difficulty the production share
    difficulty: exactly the controller solo_mainnet.py would
    build if an operator enabled vardiff with defaults."""
    vd = endpoint_config.solo_vardiff_config()
    return VarDiffController(
        target_interval=float(vd["target_interval"]),
        floor=float(vd["floor"]), ceiling=float(vd["ceiling"]),
        initial=SHARE_DIFFICULTY,
        ema_alpha=float(vd["ema_alpha"]),
        deadband=float(vd["deadband"]),
        up_hysteresis_s=float(vd["up_hysteresis_s"]),
        up_confirmations=int(vd["up_confirmations"]),
        max_up_factor=float(vd["max_up_factor"]),
        max_down_factor=float(vd["max_down_factor"]),
        decay_after_s=float(vd["decay_after_s"]),
        decay_factor=float(vd["decay_factor"]))


class SoloPipeline:
    """The production solo stack in-process: SoloServer with
    a timed node RPC, served by SoloTCPServer on localhost.
    Vardiff None for scenarios A/B/C (production
    configuration); scenario D passes the default-parameter
    controller."""

    def __init__(self, timer, payout, scenario, port):
        self.timer = timer
        rpc = ThreadRPC(BitcoinRPC(), timer, "srv_")
        if scenario == "D":
            self.srv = SoloServer(rpc, payout,
                                  vardiff=make_vardiff_controller())
        else:
            self.srv = SoloServer(rpc, payout)
        self._orig_vc = instrument_solo(self.srv, timer)
        # Bind retry: a client socket from an earlier session
        # can hold the port in TIME_WAIT (the production
        # server class sets allow_reuse_address, but the
        # vardiff suite still observed EADDRINUSE on this VM;
        # waiting it out in the harness keeps production
        # socket behaviour untouched).
        deadline = time.time() + 120
        while True:
            try:
                self.tcp = SoloTCPServer(("127.0.0.1", port),
                                         self.srv)
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(2)
        self.port = port
        self.thread = threading.Thread(
            target=self.tcp.serve_forever, daemon=True)
        self.thread.start()
        self.srv.refresh_job()

    def current_job_id(self):
        cur = self.srv.current
        return cur["job_id"] if cur else None

    def template_tx_count(self):
        cur = self.srv.current
        return len(cur["template"]["transactions"]) if cur else -1

    def refresh_and_broadcast(self):
        job = self.srv.refresh_job()
        self.tcp.broadcast(job)

    def stats(self):
        return self.srv.stats()

    def close(self):
        try:
            self.tcp.shutdown()
            self.tcp.server_close()
        finally:
            solo_module.verify_candidate = self._orig_vc


# ---------------------------------------------------------------- pool stub

def _varint(n):
    if n < 0xfd:
        return bytes([n])
    if n <= 0xffff:
        return b"\xfd" + n.to_bytes(2, "little")
    return b"\xfe" + n.to_bytes(4, "little")


class PoolStub:
    """A local pool-protocol stub, harness code only. It does
    the work a real pool does for a block: builds jobs from
    the node's getblocktemplate (with the production
    coinbase builder and merkle branch helpers), serves them
    over Stratum V1, judges submitted shares against its
    share target, runs every target-meeting candidate
    through the EXP-036 exact verifier, assembles and
    submits network-target blocks, and counts a block only
    when the node's chain state confirms it. It is NOT a
    production component and is never connected to any
    external pool; multi-worker pool infrastructure,
    payout accounting and vardiff are outside its scope by
    design (the solo pipeline covers the lab's own server;
    this stub exists so the production CLIENT path has a
    pool-shaped counterparty on regtest)."""

    def __init__(self, timer, payout, port,
                 share_difficulty=SHARE_DIFFICULTY):
        self.timer = timer
        self.rpc = ThreadRPC(BitcoinRPC(), timer, "pool_")
        self.payout = payout
        self.share_difficulty = share_difficulty
        self.share_target = share_target_for(share_difficulty)
        self.lock = threading.Lock()
        self.current = None
        self.job_seq = 0
        self.blocks_found = []
        self.shares_accepted = 0
        self.shares_rejected = 0
        self.clients = set()
        self.clients_lock = threading.Lock()
        self._en1 = 0
        self._en1_lock = threading.Lock()
        self.tcp = _StubTCPServer(("127.0.0.1", port), self)
        self.port = port
        self.thread = threading.Thread(
            target=self.tcp.serve_forever, daemon=True)
        self.thread.start()
        self.refresh_job()

    # -- job construction (mirrors SoloServer.refresh_job,
    # using the same production helpers) -------------------
    def refresh_job(self):
        t = self.rpc.call("getblocktemplate", {"rules": ["segwit"]})
        placeholder = b"\xee" * 8
        script = address_script_pubkey(self.rpc, self.payout)
        commitment = None
        if t.get("default_witness_commitment"):
            raw_commit = bytes.fromhex(
                t["default_witness_commitment"])
            if (len(raw_commit) != 38
                    or raw_commit[:6] != b"\x6a\x24\xaa\x21\xa9\xed"):
                raise ValueError(
                    "unexpected default_witness_commitment format")
            commitment = raw_commit[6:]
        coinbase, _ = build_coinbase(
            t["height"], t["coinbasevalue"], script, placeholder,
            witness_commitment=commitment)
        marker = b"/BAL/" + placeholder
        stripped, has_witness = strip_witness(coinbase)
        at = stripped.index(marker) + len(b"/BAL/")
        coinb1 = stripped[:at]
        coinb2 = stripped[at + 8:]
        txids = [bytes.fromhex(tx["txid"])[::-1]
                 for tx in t["transactions"]]
        branch = merkle_branch(txids)
        from mining.pow import target_from_nbits
        with self.lock:
            self.job_seq += 1
            job = {
                "job_id": f"{self.job_seq:x}",
                "template": t,
                "has_witness": bool(has_witness),
                "coinb1": coinb1, "coinb2": coinb2,
                "branch": branch, "txids": txids,
                "target": target_from_nbits(int(t["bits"], 16)),
            }
            job["client"] = self._client_job(job)
            self.current = job
        return job

    def _client_job(self, job):
        params = self.notify_params(job)
        return {"job_id": params[0], "prevhash": params[1],
                "coinb1": params[2], "coinb2": params[3],
                "merkle_branch": params[4], "version": params[5],
                "nbits": params[6], "ntime": params[7]}

    def notify_params(self, job):
        """The Stratum notify encoding, identical to
        SoloServer.notify_params (the lab's client/server
        convention; agreement is proven by every accepted
        block, since the stub validates with the same
        build_header the client mines with)."""
        t = job["template"]
        prev = bytes.fromhex(t["previousblockhash"])[::-1]
        prev_swapped = b"".join(prev[i:i + 4][::-1]
                                for i in range(0, 32, 4))
        return [job["job_id"], prev_swapped.hex(),
                job["coinb1"].hex(), job["coinb2"].hex(),
                [b.hex() for b in job["branch"]],
                f'{t["version"]:08x}', t["bits"],
                f'{t["curtime"]:08x}', True]

    # -- connection bookkeeping ------------------------------
    def next_en1(self):
        with self._en1_lock:
            self._en1 += 1
            return self._en1.to_bytes(4, "little")

    def broadcast(self, job):
        with self.clients_lock:
            clients = list(self.clients)
        for h in clients:
            try:
                h._send({"id": None,
                         "method": "mining.set_difficulty",
                         "params": [self.share_difficulty]})
                h._send({"id": None, "method": "mining.notify",
                         "params": self.notify_params(job)})
            except Exception:
                pass

    def refresh_and_broadcast(self):
        job = self.refresh_job()
        self.broadcast(job)

    # -- harness-facing state --------------------------------
    def current_job_id(self):
        with self.lock:
            return self.current["job_id"] if self.current else None

    def template_tx_count(self):
        with self.lock:
            cur = self.current
            return (len(cur["template"]["transactions"])
                    if cur else -1)

    def stats(self):
        with self.lock:
            return {
                "share_difficulty": self.share_difficulty,
                "payout": self.payout,
                "shares_accepted": self.shares_accepted,
                "shares_rejected": self.shares_rejected,
                "blocks_found": len(self.blocks_found),
                "blocks": list(self.blocks_found),
                "current_job": None if self.current is None else {
                    "job_id": self.current["job_id"],
                    "height":
                        self.current["template"]["height"]},
            }

    def close(self):
        self.tcp.shutdown()
        self.tcp.server_close()

    # -- share judging ---------------------------------------
    def submit_share(self, extranonce1, job_id, en2, ntime,
                     nonce_hex, worker=None):
        """Returns (accepted, block_record_or_None). Mirrors
        the production solo fixed path's judging order: fast
        integer compare, then the EXP-036 exact gate, then
        block assembly and chain-confirmed submission."""
        timer = self.timer
        with timer.segment("pool_submit_total"):
            with self.lock:
                job = (self.current if self.current
                       and self.current["job_id"] == job_id
                       else None)
            if job is None:
                with self.lock:
                    self.shares_rejected += 1
                return False, None
            with timer.segment("pool_validate"):
                header, _merkle, coinbase = build_header(
                    job["client"], extranonce1.hex(), en2,
                    int(nonce_hex, 16), "wordswap")
                digest = dsha256(header)
                value = int.from_bytes(digest, "little")
            if not (value <= job["target"]
                    or value <= self.share_target):
                with self.lock:
                    self.shares_rejected += 1
                return False, None
            with timer.segment("pool_verify"):
                v = verify_candidate(header, POW_LIMIT_REGTEST,
                                     share_target=self.share_target)
            if v["classification"] == "invalid" \
                    or v["target"] != job["target"]:
                with self.lock:
                    self.shares_rejected += 1
                return False, None
            if v["meets_network_target"]:
                rec = self._submit_block(job, header, coinbase,
                                         digest, v)
                with self.lock:
                    self.shares_accepted += 1
                return True, rec
            if v["meets_share_target"]:
                with self.lock:
                    self.shares_accepted += 1
                return True, None
            with self.lock:
                self.shares_rejected += 1
            return False, None

    def _submit_block(self, job, header, coinbase_stripped,
                      digest, v):
        timer = self.timer
        t = job["template"]
        with timer.segment("pool_assemble"):
            coinbase = coinbase_stripped
            if job.get("has_witness"):
                coinbase = attach_witness(coinbase)
            txs = b"".join(bytes.fromhex(tx["data"])
                           for tx in t["transactions"])
            block = (header
                     + _varint(1 + len(t["transactions"]))
                     + coinbase + txs)
        block_hash = digest[::-1].hex()
        rpc_error = None
        try:
            r = self.rpc.call("submitblock", block.hex())
        except Exception as exc:
            rpc_error = exc
            r = f"submitblock RPC failed: {exc}"
        if rpc_error is None:
            chain_status, chain_ok = verify_chain_acceptance(
                self.rpc, block_hash)
        else:
            chain_status, chain_ok = "unknown", False
        from mining.candidate_verify import classify_submit_result
        classification = ("rpc-error" if rpc_error is not None
                          else classify_submit_result(r))
        ok = bool(chain_ok and classification
                  in ("accepted", "duplicate"))
        rec = {"height": t["height"], "hash": block_hash,
               "submit_result": r,
               "submit_classification": classification,
               "chain_status": chain_status,
               "chain_verified": chain_ok, "accepted": ok}
        with self.lock:
            self.blocks_found.append(rec)
        return rec


class _StubTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, stub):
        self.stub = stub
        super().__init__(addr, _StubHandler)

    def handle_error(self, request, client_address):
        # A client closing its socket at session teardown
        # surfaces here as a reset/broken pipe in the handler
        # thread; it is not a measurement event. Other errors
        # keep the default (loud) behaviour.
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError,
                            BrokenPipeError)):
            return
        super().handle_error(request, client_address)


class _StubHandler(socketserver.StreamRequestHandler):
    def setup(self):
        super().setup()
        try:
            self.request.setsockopt(
                socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self._send_lock = threading.Lock()

    def _send(self, obj):
        with self._send_lock:
            self.wfile.write((json.dumps(obj) + "\n").encode())
            self.wfile.flush()

    def handle(self):
        stub: PoolStub = self.server.stub
        extranonce1 = stub.next_en1()
        self._en1 = extranonce1
        with stub.clients_lock:
            stub.clients.add(self)
        try:
            self._run(stub, extranonce1)
        finally:
            with stub.clients_lock:
                stub.clients.discard(self)

    def _run(self, stub, extranonce1):
        for raw in self.rfile:
            try:
                msg = json.loads(raw.decode())
            except Exception:
                continue
            method = msg.get("method")
            mid = msg.get("id")
            if method == "mining.subscribe":
                self._send({"id": mid, "result": [
                    [["mining.set_difficulty", "exp048-1"],
                     ["mining.notify", "exp048-2"]],
                    extranonce1.hex(), 4], "error": None})
                self._send({"id": None,
                            "method": "mining.set_difficulty",
                            "params": [stub.share_difficulty]})
                job = stub.current or stub.refresh_job()
                self._send({"id": None, "method": "mining.notify",
                            "params": stub.notify_params(job)})
            elif method == "mining.authorize":
                self._send({"id": mid, "result": True,
                            "error": None})
            elif method == "mining.suggest_difficulty":
                self._send({"id": mid, "result": True,
                            "error": None})
            elif method == "mining.submit":
                worker, job_id, en2, ntime, nonce = msg["params"]
                accepted, block = stub.submit_share(
                    extranonce1, job_id, en2, ntime, nonce,
                    worker=str(worker))
                self._send({"id": mid, "result": accepted,
                            "error": None if accepted
                            else [20, "rejected", None]})
                if block is not None:
                    # A block moved the tip: fresh job for the
                    # new tip, as a real pool would serve.
                    try:
                        job = stub.refresh_job()
                    except Exception:
                        continue
                    stub.broadcast(job)
            else:
                self._send({"id": mid, "result": None,
                            "error": [501, "unknown method", None]})


# ---------------------------------------------------------------- manifest

def build_manifest(backend, pipeline, scenario, span_size):
    model = ""
    flags = []
    try:
        with open("/proc/cpuinfo") as fh:
            text = fh.read()
        for line in text.splitlines():
            if line.startswith("model name") and not model:
                model = line.split(":", 1)[1].strip()
            if line.startswith("flags") and not flags:
                flags = line.split(":", 1)[1].split()
    except OSError:
        pass
    keep = [f for f in ("avx2", "avx512f", "avx512bw", "avx512vl",
                        "avx512vbmi", "avx512vbmi2", "sha_ni",
                        "sse4_1", "ssse3") if f in flags]
    hashes = {}
    for rel in CONTENT_FILES + (
            "research/sha256d/exp048/category_f_stratum.py",):
        path = os.path.join(ROOT, rel)
        with open(path, "rb") as fh:
            hashes[rel] = hashlib.sha256(fh.read()).hexdigest()
    return {
        "host_cpu": model,
        "hostname": platform.node(),
        "cpu_flags_relevant": keep,
        "python": platform.python_version(),
        "backend_selected": backend,
        "dispatch_order": ["cuda", "v512dual", "v512", "shani",
                           "avx2", "c", "hashlib"],
        "pipeline": pipeline,
        "scenario": scenario,
        "share_difficulty": SHARE_DIFFICULTY,
        "target_shift": AMPLIFY_SHIFT if scenario == "C" else 0,
        "span_size": span_size,
        "loadavg_at_manifest": list(os.getloadavg()),
        "contention": ("live mainnet pool miner (v512dual) and "
                       "pruned mainnet node running throughout; "
                       "figures are contended single-VM regtest "
                       "pipeline figures, category F"),
        "source_sha256": hashes,
    }


# ---------------------------------------------------------------- sessions

def port_for(pipeline, scenario, sidx):
    if pipeline == "solo":
        return SOLO_BASE_PORT + sidx + (100 if scenario == "D"
                                        else 0)
    return POOL_BASE_PORT + sidx


def setup_mempool(scenario, loader, plain, server):
    """Scenario setup, never inside a timed run (EXP-040
    discipline). For B the loaded job must be the server's
    current job before the run starts."""
    if scenario == "B":
        secs = loader.reload()
        size = plain.call("getmempoolinfo")["size"]
        assert size == loader.n, (size, loader.n)
        # Core serves a cached getblocktemplate until the
        # mempool change is about 5 s old or the tip moves
        # (v28.1 behaviour, recorded in the Master Assignment
        # Core audit), so an immediate refresh can still carry
        # the pre-load template. Poll the refresh until the
        # served template actually carries the loaded
        # transactions. All of this is setup, never inside a
        # timed run.
        t0 = time.perf_counter()
        while True:
            server.refresh_and_broadcast()
            txs = server.template_tx_count()
            if txs == loader.n:
                break
            if time.perf_counter() - t0 > 120:
                raise RuntimeError(
                    f"template never loaded: {txs} txs after "
                    f"120 s (mempool {size})")
            time.sleep(1.0)
        return {"reload_seconds": secs, "mempool_size": size,
                "template_tx_count": txs,
                "template_wait_seconds":
                    time.perf_counter() - t0}
    size = plain.call("getmempoolinfo")["size"]
    assert size == 0, f"expected empty mempool, got {size}"
    return {"mempool_size": 0}


def run_session(pipeline, scenario, sidx, n_runs, loader=None):
    plain = BitcoinRPC()
    wallet = exp040.wallet_rpc()
    payout = wallet.call("getnewaddress", "", "bech32")
    timer = ThreadTimer()
    shift = AMPLIFY_SHIFT if scenario == "C" else 0
    real_compute = ComputeEngine()
    compute = TimingCompute(real_compute, timer, target_shift=shift)
    span_size = compute_span(real_compute)
    port = port_for(pipeline, scenario, sidx)
    if pipeline == "solo":
        server = SoloPipeline(timer, payout, scenario, port)
        server_labels = SOLO_SERVER_STAGES
    else:
        server = PoolStub(timer, payout, port)
        server_labels = POOL_SERVER_STAGES
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    os.makedirs(RAW_DIR, exist_ok=True)
    ev = Evidence(os.path.join(
        RAW_DIR, f"client_evidence_{pipeline}_{scenario}_"
                 f"{sidx}_{stamp}.jsonl"))
    user = f"{payout}.exp048"
    client = StratumClient("127.0.0.1", port, user, "x", ev)
    client.suggest_difficulty = SHARE_DIFFICULTY
    session = {
        "experiment": "EXP-048",
        "category": "F",
        "pipeline": pipeline,
        "scenario": scenario,
        "session_index": sidx,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "manifest": build_manifest(real_compute.backend, pipeline,
                                   scenario, span_size),
        "target_shift": shift,
        "share_difficulty": SHARE_DIFFICULTY,
        "n_runs_declared": n_runs,
        "setup": {},
        "warmup": None,
        "runs": [],
    }
    deadline_s = 1800 if scenario == "C" else 900
    try:
        client.connect()
        threading.Thread(target=client.reader_loop,
                         daemon=True).start()
        if not client.authorized.wait(timeout=30):
            raise RuntimeError("client authorization not confirmed")
        miner = MinerState(client, compute, timer, plain,
                           span_size)
        session["setup"]["warmup_mempool"] = setup_mempool(
            scenario, loader, plain, server)
        warm, _t = miner.mine_one(
            time.perf_counter(), server, deadline_s)
        session["warmup"] = {
            "accepted": bool(warm.get("accepted")),
            "height": warm.get("height"), "hash": warm.get("hash"),
            "hashes": warm.get("hashes_counted"),
            "failed": bool(warm.get("failed"))}
        if warm.get("failed") or not warm.get("accepted"):
            raise RuntimeError(f"warm-up run failed: {warm}")
        for i in range(n_runs):
            snap_setup = timer.totals()
            setup_info = setup_mempool(scenario, loader, plain,
                                       server)
            snap0 = timer.totals()
            run_start = time.perf_counter()
            try:
                run, _t = miner.mine_one(
                    run_start, server, deadline_s)
            except Exception as exc:
                run = {"failed": True,
                       "fail_reason": f"{type(exc).__name__}: {exc}",
                       "accepted": False,
                       "cycle_wall_s": time.perf_counter() - run_start}
            snap1 = timer.totals()
            run["setup_server_stages_s"] = stage_diff(
                snap0, snap_setup, server_labels)
            diff = stage_diff(snap1, snap0,
                              CLIENT_STAGES + server_labels)
            run["stages_s"] = {k: diff[k] for k in CLIENT_STAGES}
            run["server_stages_s"] = {k: diff[k]
                                      for k in server_labels}
            run["setup"] = setup_info
            if not run.get("failed"):
                accounted = (run["job_wait_s"]
                             + run["verdict_wait_s"]
                             + run["confirm_s"]
                             + sum(run["stages_s"].values()))
                run["residual_s"] = run["cycle_wall_s"] - accounted
            session["runs"].append(run)
            print(f"  [{pipeline}/{scenario} s{sidx} run {i}] "
                  f"accepted={run.get('accepted')} "
                  f"height={run.get('height')} "
                  f"wall={run.get('cycle_wall_s', -1):.3f}s "
                  f"hashes={run.get('hashes_counted')} "
                  f"failed={run.get('failed')}", flush=True)
        session["server_stats_end"] = server.stats()
    finally:
        session["finished_utc"] = datetime.now(
            timezone.utc).isoformat()
        if loader is not None:
            session["setup"]["loader"] = {
                "fund_seconds": loader.fund_seconds,
                "reload_seconds": loader.reload_seconds,
                "n_tx": loader.n}
        path = os.path.join(
            RAW_DIR, f"session_{pipeline}_{scenario}_{sidx}_"
                     f"{stamp}.json")
        with open(path, "x") as fh:
            json.dump(session, fh, indent=1)
        print(f"  session file: {path}", flush=True)
        try:
            client.stop_flag = True
            if client.sock is not None:
                client.sock.close()
        except Exception:
            pass
        server.close()
        ev.close()
    return session


def drain_mempool(plain, wallet):
    """Setup hygiene between pipelines: confirm any leftover
    mempool transactions with one block to a wallet address
    (untimed, recorded by callers in their logs)."""
    size = plain.call("getmempoolinfo")["size"]
    if size:
        addr = wallet.call("getnewaddress", "", "bech32")
        plain.call("generatetoaddress", 1, addr)
    return plain.call("getmempoolinfo")["size"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    ra = sub.add_parser("run-all")
    ra.add_argument("--n-tx", type=int, default=500)
    r1 = sub.add_parser("run")
    r1.add_argument("--pipeline", required=True,
                    choices=("solo", "pool"))
    r1.add_argument("--scenario", required=True,
                    choices="ABCD")
    r1.add_argument("--sessions", type=int, default=1)
    r1.add_argument("--session-start", type=int, default=0)
    r1.add_argument("--runs", type=int, default=2)
    r1.add_argument("--n-tx", type=int, default=500)
    args = ap.parse_args(argv)

    if args.cmd == "run-all":
        plan = [("solo", "A", 3, 8), ("solo", "C", 3, 5),
                ("solo", "B", 3, 8), ("solo", "D", 2, 5),
                ("pool", "A", 3, 8), ("pool", "C", 3, 5),
                ("pool", "B", 3, 8)]
        n_tx = args.n_tx
    else:
        if args.scenario == "D" and args.pipeline != "solo":
            ap.error("scenario D is solo-only")
        plan = [(args.pipeline, args.scenario, args.sessions,
                 args.runs)]
        n_tx = args.n_tx

    loader = None
    plain = BitcoinRPC()
    wallet = exp040.wallet_rpc()
    for pipeline, scenario, n_sessions, n_runs in plan:
        if scenario == "B" and loader is None:
            loader = exp040.MempoolLoader(
                exp040.wallet_rpc(), BitcoinRPC(), n_tx=n_tx)
        start = (args.session_start if args.cmd == "run" else 0)
        for s in range(start, start + n_sessions):
            print(f"EXP-048 {pipeline}/{scenario} session {s}: "
                  f"{n_runs} timed runs", flush=True)
            run_session(pipeline, scenario, s, n_runs,
                        loader=loader)
        if scenario == "B":
            left = drain_mempool(plain, wallet)
            print(f"  post-B drain: mempool size {left}",
                  flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
