"""EXP-057: stratum aggregation tier (portfolio NOVA-ER-0017,
register R-27).

A stratum-speaking aggregation tier: it holds ONE upstream
connection (one SoloServer facing the node, whose job
construction, header reconstruction and EXP-036 validation
pipeline are reused verbatim, not reimplemented), fans the
workbase out to downstream fleet workers over Stratum V1,
validates every share through mining.candidate_verify.
verify_candidate, and keeps per-worker accounting through
the EXP-037 separated statistics (mining.mining_statistics).

Fleet identity is the genuinely new work, and it inherits
the EXP-035 and EXP-055 checks rather than ckpool's open
pool trust model:

  * a worker exists only if the operator enrolled it
    (worker_id plus an enrollment token; the tier stores
    only the token's SHA-256 hash, compared in constant
    time);
  * opening a session requires the fleet id to match
    (a foreign fleet is refused, as in EXP-055), the
    worker to be enrolled, and the token to match;
  * a session binds exactly one worker to exactly one
    tier-assigned extranonce1. The worker never chooses
    its extranonce1, and every share is judged under the
    session's extranonce1, so a share can never be
    credited to another worker's slot;
  * sessions never survive a tier restart: the epoch
    bumps on restore and every pre-restart session is
    dead (the EXP-055 restart rule).

Submission authority stays OUT of the tier. The tier
validates and accounts; a verified block candidate is
queued as a pending candidate and is never submitted by
the tier on its own authority. The single submission
path is operator_submit_pending: an explicit operator
action requiring the operator token and an explicitly
configured upstream submitter callable. With no
submitter configured the call refuses. Workers return to
direct endpoints by configuration; nothing in the live
mining paths imports this module, and not deploying it
is the rollback. Fleet activation is owner-gated
(roadmap F2); this module contacts no other machine.
"""

import hashlib
import hmac
import json
import os
import socketserver
import struct
import threading
import time

from mining.candidate_verify import verify_candidate
from mining.mining_statistics import MiningStatistics
from mining.solo_server import SoloServer

# Tier-local disjoint submission categories. An
# authenticated submission lands in exactly one.
CATEGORIES = ("accepted", "below_target", "invalid",
              "stale", "duplicate", "unknown_job")

SNAPSHOT_VERSION = 1


class IdentityError(Exception):
    """A session or submission failed a fleet identity
    check. Counted, never absorbed."""


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AggregationTier:
    """The aggregation core. One upstream SoloServer;
    downstream sessions are explicit objects here and TCP
    connections in AggregationTCPServer below, both routed
    through submit_share so there is one judgment path."""

    def __init__(self, rpc, payout_address, fleet_id,
                 share_difficulty=None, expected_chain=None,
                 pow_limit=None, operator_token=None,
                 submitter=None, job_history_size=8):
        self.solo = SoloServer(
            rpc, payout_address,
            share_difficulty=share_difficulty,
            expected_chain=expected_chain, pow_limit=pow_limit)
        self.fleet_id = fleet_id
        self.share_target = self.solo.share_target
        self.job_history_size = int(job_history_size)
        self.job_history = []
        self.generation = 0
        self.epoch = 0
        # worker_id -> {"token_hash", "enrolled_at"}
        self.workers = {}
        # session_id -> {"worker_id", "extranonce1" (bytes),
        #                "opened_at"}
        self.sessions = {}
        self._session_seq = 0
        self._en1_seq = 0
        self._operator_hash = (_hash_token(operator_token)
                               if operator_token else None)
        # The upstream submitter is a callable
        # (job, res, verdict, worker) -> record dict, or
        # None. The tier never calls it except from
        # operator_submit_pending.
        self.submitter = submitter
        self.upstream_submissions = 0
        # Accounting: EXP-037 separated statistics plus the
        # tier-local disjoint counters (global + per worker).
        self.stats = MiningStatistics()
        self.counters = {c: 0 for c in CATEGORIES}
        self.counters["identity_rejected"] = 0
        self.per_worker = {}
        self._seen = set()   # (worker, job, en2, ntime, nonce)
        self.pending_candidates = []
        self.lock = threading.Lock()

    # -- operator-side enrollment and configuration ---------
    def enroll_worker(self, worker_id, token):
        with self.lock:
            if worker_id in self.workers:
                raise ValueError("worker %r already enrolled"
                                 % worker_id)
            self.workers[worker_id] = {
                "token_hash": _hash_token(token),
                "enrolled_at": time.time()}

    def set_operator_token(self, token):
        self._operator_hash = _hash_token(token)

    def set_submitter(self, submitter):
        self.submitter = submitter

    # -- workbase --------------------------------------------
    def refresh_workbase(self):
        """Build a fresh workbase from the upstream node
        through the production SoloServer machinery and fan
        it out (it becomes the current job for every
        session). The superseded job is retained in the
        bounded history for stale classification."""
        old = self.solo.current
        job = self.solo.refresh_job()
        with self.lock:
            if old is not None and old["job_id"] != job["job_id"]:
                self.job_history.append(old)
                del self.job_history[:-self.job_history_size]
            self.generation += 1
        return job

    def current_job(self):
        return self.solo.current

    def notify_params(self, job=None):
        return self.solo.notify_params(job or self.solo.current)

    def _find_job(self, job_id):
        with self.lock:
            if self.solo.current is not None \
                    and self.solo.current["job_id"] == job_id:
                return self.solo.current, False
            cur = self.solo.jobs.get(job_id)
            if cur is not None:
                return cur, False
            for j in self.job_history:
                if j["job_id"] == job_id:
                    return j, True
        return None, False

    # -- sessions (fleet identity) ----------------------------
    def open_session(self, worker_id, fleet_id, token):
        """Authenticate and bind a session. Raises
        IdentityError on a foreign fleet, an unenrolled
        worker, or a token mismatch (including a token
        belonging to another worker: it simply does not
        match this worker's hash)."""
        with self.lock:
            if fleet_id != self.fleet_id:
                self.counters["identity_rejected"] += 1
                raise IdentityError(
                    "foreign fleet %r" % (fleet_id,))
            rec = self.workers.get(worker_id)
            if rec is None:
                self.counters["identity_rejected"] += 1
                raise IdentityError(
                    "unenrolled worker %r" % (worker_id,))
            if not hmac.compare_digest(
                    rec["token_hash"], _hash_token(token or "")):
                self.counters["identity_rejected"] += 1
                raise IdentityError(
                    "token mismatch for worker %r" % worker_id)
            self._session_seq += 1
            self._en1_seq += 1
            session_id = "S%d" % self._session_seq
            en1 = struct.pack(">I", self._en1_seq)
            self.sessions[session_id] = {
                "worker_id": worker_id, "extranonce1": en1,
                "opened_at": time.time(), "epoch": self.epoch}
            return session_id, en1

    def close_session(self, session_id):
        with self.lock:
            self.sessions.pop(session_id, None)

    def _session(self, session_id):
        sess = self.sessions.get(session_id)
        if sess is None or sess["epoch"] != self.epoch:
            return None
        return sess

    # -- accounting --------------------------------------------
    def _worker_counters(self, worker):
        rec = self.per_worker.get(worker)
        if rec is None:
            rec = {c: 0 for c in CATEGORIES}
            self.per_worker[worker] = rec
        return rec

    def _count(self, worker, category):
        self.counters[category] += 1
        self._worker_counters(worker)[category] += 1
        self.stats.record("pool_shares_submitted", 1,
                          worker=worker)
        if category == "accepted":
            self.stats.record("pool_shares_accepted", 1,
                              worker=worker)
        elif category in ("below_target", "invalid",
                          "unknown_job"):
            self.stats.record("pool_shares_rejected", 1,
                              worker=worker)
        elif category == "stale":
            self.stats.record("stale_reports", 1, worker=worker)
        elif category == "duplicate":
            self.stats.record("duplicate_deliveries", 1,
                              worker=worker)

    def accounting(self):
        snap = self.stats.snapshot()
        return {
            "categories": dict(self.counters),
            "per_worker": {k: dict(v) for k, v
                           in self.per_worker.items()},
            "exp037_totals": snap["totals"],
            "exp037_per_worker": snap["per_worker"],
            "pending_candidates": len(self.pending_candidates),
            "upstream_submissions": self.upstream_submissions,
            "epoch": self.epoch,
            "generation": self.generation,
            "sessions": len(self.sessions),
            "workers_enrolled": len(self.workers)}

    def assert_accounting_identity(self):
        """The predeclared Gate 3 identity: EXP-037
        pool_shares_submitted equals the sum of the six
        disjoint tier categories, globally and per worker,
        and the per-worker EXP-037 breakdowns reconcile
        with the tier-local per-worker counters."""
        total = sum(self.counters[c] for c in CATEGORIES)
        snap = self.stats.snapshot()
        assert snap["totals"]["pool_shares_submitted"] == total, \
            (snap["totals"], self.counters)
        for worker, cats in self.per_worker.items():
            wtotal = sum(cats[c] for c in CATEGORIES)
            pw = snap["per_worker"].get(worker, {})
            assert pw.get("pool_shares_submitted", 0) == wtotal, \
                (worker, pw, cats)
            assert pw.get("pool_shares_accepted", 0) \
                == cats["accepted"]
            assert pw.get("pool_shares_rejected", 0) == \
                cats["below_target"] + cats["invalid"] \
                + cats["unknown_job"]
        return True

    # -- share judgment (the one path) --------------------------
    def submit_share(self, session_id, job_id, extranonce2_hex,
                     ntime_hex, nonce_hex, claimed_worker=None):
        """Judge one share. Returns a dict with accepted,
        category and reason. Identity failures raise
        IdentityError after counting identity_rejected:
        an unauthenticated submission never enters the
        share accounting at all."""
        with self.lock:
            sess = self._session(session_id)
            if sess is None:
                self.counters["identity_rejected"] += 1
                raise IdentityError(
                    "unknown or dead session %r" % (session_id,))
            worker = sess["worker_id"]
            en1 = sess["extranonce1"]
            if claimed_worker is not None \
                    and claimed_worker != worker:
                self.counters["identity_rejected"] += 1
                raise IdentityError(
                    "share claimed by %r on a session bound "
                    "to %r" % (claimed_worker, worker))
        job, stale = self._find_job(job_id)
        if job is None:
            with self.lock:
                self._count(worker, "unknown_job")
            return {"accepted": False, "category": "unknown_job",
                    "reason": "unknown job", "worker": worker}
        key = (worker, job_id, extranonce2_hex, ntime_hex,
               nonce_hex)
        with self.lock:
            if key in self._seen:
                self._count(worker, "duplicate")
                return {"accepted": False,
                        "category": "duplicate",
                        "reason": "duplicate share",
                        "worker": worker}
            self._seen.add(key)
        res, err = self.solo.validate_share(
            job, en1, extranonce2_hex, ntime_hex, nonce_hex)
        if err:
            with self.lock:
                self._count(worker, "invalid")
            return {"accepted": False, "category": "invalid",
                    "reason": err, "worker": worker}
        if stale:
            return self._judge_stale(job, res, worker)
        if not (res["value"] <= job["target"]
                or res["value"] <= self.share_target):
            with self.lock:
                self._count(worker, "below_target")
            return {"accepted": False,
                    "category": "below_target",
                    "reason": "low difficulty share",
                    "worker": worker}
        v = verify_candidate(res["header"], self.solo._pow_limit(),
                             share_target=self.share_target)
        with self.lock:
            self.stats.record("verification_hashes", 1,
                              worker=worker)
        if v["target"] != job["target"]:
            v = dict(v, classification="invalid",
                     reason="header-target-mismatch")
        if v["classification"] == "invalid":
            with self.lock:
                self._count(worker, "invalid")
            return {"accepted": False, "category": "invalid",
                    "reason": "exact verification failed: %s"
                              % v["reason"],
                    "worker": worker}
        if v["meets_network_target"]:
            with self.lock:
                self._count(worker, "accepted")
                self.stats.record("candidates", 1, worker=worker)
                self.stats.record("valid_candidates", 1,
                                  worker=worker)
                self.stats.record("network_target_candidates", 1,
                                  worker=worker)
                self.pending_candidates.append({
                    "job_id": job["job_id"], "worker": worker,
                    "header": res["header"].hex(),
                    "coinbase": res["coinbase"].hex(),
                    "hash": res["digest"][::-1].hex(),
                    "stale": False,
                    "verify_reason": v["reason"]})
            return {"accepted": True,
                    "category": "block_candidate",
                    "reason": "verified block candidate queued; "
                              "not submitted (submission is an "
                              "operator action)",
                    "worker": worker, "block": None}
        if v["meets_share_target"]:
            with self.lock:
                self._count(worker, "accepted")
                self.stats.record("valid_candidates", 1,
                                  worker=worker)
            return {"accepted": True, "category": "share",
                    "reason": "ok", "worker": worker}
        with self.lock:
            self._count(worker, "below_target")
        return {"accepted": False, "category": "below_target",
                "reason": "low difficulty share",
                "worker": worker}

    def _judge_stale(self, job, res, worker):
        """A share answering a superseded job: classified
        stale, never counted accepted. A network-target hit
        is still exact-verified and, if verified, queued as
        a stale pending candidate; it is never submitted by
        the tier."""
        meets = (res["value"] <= job["target"]
                 or res["value"] <= self.share_target)
        if not meets:
            with self.lock:
                self._count(worker, "stale")
            return {"accepted": False, "category": "stale",
                    "reason": "stale job: below target",
                    "worker": worker}
        v = verify_candidate(res["header"], self.solo._pow_limit(),
                             share_target=self.share_target)
        with self.lock:
            self.stats.record("verification_hashes", 1,
                              worker=worker)
            self._count(worker, "stale")
        if v["classification"] != "invalid" \
                and v["meets_network_target"]:
            with self.lock:
                self.stats.record("candidates", 1, worker=worker)
                self.stats.record("network_target_candidates", 1,
                                  worker=worker)
                self.pending_candidates.append({
                    "job_id": job["job_id"], "worker": worker,
                    "header": res["header"].hex(),
                    "coinbase": res["coinbase"].hex(),
                    "hash": res["digest"][::-1].hex(),
                    "stale": True, "verify_reason": v["reason"]})
            return {"accepted": False, "category": "stale",
                    "reason": "stale job: verified block "
                              "candidate queued; not submitted",
                    "worker": worker}
        return {"accepted": False, "category": "stale",
                "reason": "stale job", "worker": worker}

    # -- the single submission path (operator action only) -----
    def operator_submit_pending(self, operator_token, index=0):
        """Submit one queued verified candidate upstream.
        This is an operator action, not tier behaviour: it
        requires the operator token and an explicitly
        configured submitter, and it is the only code path
        in this module that submits anything. The
        candidate's stored header is re-verified through
        EXP-036 immediately before submission, so nothing
        unverified can be submitted even here. On any
        failure the candidate stays queued (D-2 fix); it
        is removed only once the submitter has returned."""
        if self._operator_hash is None:
            raise IdentityError("no operator token configured")
        if not hmac.compare_digest(
                self._operator_hash,
                _hash_token(operator_token or "")):
            with self.lock:
                self.counters["identity_rejected"] += 1
            raise IdentityError("operator token mismatch")
        if self.submitter is None:
            raise RuntimeError(
                "no upstream submitter configured; the tier "
                "does not submit on its own authority")
        # D-2 fix (EXP-057 audit): peek, do not pop. The
        # candidate is removed only after the submitter
        # returns successfully (below); a failed job
        # lookup, a failed re-verification or a submitter
        # exception retains it in the queue, so a genuine
        # verified candidate is never silently discarded
        # by a transient failure.
        with self.lock:
            cand = self.pending_candidates[index]
        job, _stale = self._find_job(cand["job_id"])
        if job is None and self.solo.current is not None \
                and self.solo.current["job_id"] == cand["job_id"]:
            job = self.solo.current
        if job is None:
            raise RuntimeError("candidate job %r no longer "
                               "available" % cand["job_id"])
        header = bytes.fromhex(cand["header"])
        v = verify_candidate(header, self.solo._pow_limit(),
                             share_target=self.share_target)
        if not v["meets_network_target"]:
            raise RuntimeError(
                "pending candidate failed re-verification: %s"
                % v["reason"])
        res = {"header": header,
               "coinbase": bytes.fromhex(cand["coinbase"]),
               "digest": v["digest"], "value": v["value"]}
        rec = self.submitter(job, res, v, cand["worker"])
        with self.lock:
            # Submission happened: remove exactly this
            # candidate (by identity, so an equal record
            # queued twice is not removed by mistake).
            for i, queued in enumerate(self.pending_candidates):
                if queued is cand:
                    del self.pending_candidates[i]
                    break
            self.upstream_submissions += 1
            self.stats.record("blocks_submitted", 1,
                              worker=cand["worker"])
            if rec.get("accepted"):
                self.stats.record("blocks_accepted", 1,
                                  worker=cand["worker"])
            else:
                self.stats.record("blocks_rejected", 1,
                                  worker=cand["worker"])
        return rec

    def solo_submitter(self, job, res, v, worker):
        """The regtest and solo-stack submitter: the
        production SoloServer block assembly and submission
        (EXP-036 chain verification included). Wired in
        explicitly by the operator; never a default."""
        return self.solo._submit_block(job, res, v, worker)

    # -- persistence (Gate 5) ------------------------------------
    @staticmethod
    def _job_blob(job):
        if job is None:
            return None
        return {
            "job_id": job["job_id"],
            "template": job["template"],
            "has_witness": job["has_witness"],
            "coinb1": job["coinb1"].hex(),
            "coinb2": job["coinb2"].hex(),
            "branch": [b.hex() for b in job["branch"]],
            "txids": [t.hex() for t in job["txids"]],
            "target": job["target"]}

    @staticmethod
    def _job_from_blob(blob):
        if blob is None:
            return None
        return {
            "job_id": blob["job_id"], "template": blob["template"],
            "has_witness": blob["has_witness"],
            "coinb1": bytes.fromhex(blob["coinb1"]),
            "coinb2": bytes.fromhex(blob["coinb2"]),
            "branch": [bytes.fromhex(b) for b in blob["branch"]],
            "txids": [bytes.fromhex(t) for t in blob["txids"]],
            "target": blob["target"]}

    def snapshot(self):
        with self.lock:
            return {
                "version": SNAPSHOT_VERSION,
                "fleet_id": self.fleet_id,
                "epoch": self.epoch,
                "generation": self.generation,
                "session_seq": self._session_seq,
                "en1_seq": self._en1_seq,
                "workers": {k: dict(v) for k, v
                            in self.workers.items()},
                "operator_hash": self._operator_hash,
                "counters": dict(self.counters),
                "per_worker": {k: dict(v) for k, v
                               in self.per_worker.items()},
                "stats": self.stats.snapshot(),
                "seen": sorted(self._seen),
                "pending_candidates":
                    [dict(c) for c in self.pending_candidates],
                "upstream_submissions": self.upstream_submissions,
                "current_job": self._job_blob(self.solo.current),
                "job_history": [self._job_blob(j)
                                for j in self.job_history],
                "job_seq": self.solo.job_seq}

    def write_snapshot(self, path):
        blob = self.snapshot()
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(blob, fh, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        return path

    @classmethod
    def restore(cls, path, rpc, payout_address,
                share_difficulty=None, expected_chain=None,
                pow_limit=None, submitter=None):
        with open(path) as fh:
            blob = json.load(fh)
        tier = cls(rpc, payout_address, blob["fleet_id"],
                   share_difficulty=share_difficulty,
                   expected_chain=expected_chain,
                   pow_limit=pow_limit, submitter=submitter)
        tier.epoch = blob["epoch"] + 1   # restart rule: bump
        tier.generation = blob["generation"]
        tier._session_seq = blob["session_seq"]
        tier._en1_seq = blob["en1_seq"]
        tier.workers = blob["workers"]
        tier._operator_hash = blob["operator_hash"]
        tier.counters = blob["counters"]
        tier.per_worker = blob["per_worker"]
        tier._seen = {tuple(x) for x in blob["seen"]}
        tier.pending_candidates = blob["pending_candidates"]
        tier.upstream_submissions = blob["upstream_submissions"]
        saved = blob["stats"]
        for cat, val in saved["totals"].items():
            tier.stats._totals[cat] = val
        for worker, cats in saved["per_worker"].items():
            tier.stats._per_worker[worker] = dict(cats)
        for backend, cats in saved["per_backend"].items():
            tier.stats._per_backend[backend] = dict(cats)
        cur = cls._job_from_blob(blob["current_job"])
        if cur is not None:
            tier.solo.current = cur
            tier.solo.jobs = {cur["job_id"]: cur}
        tier.job_history = [cls._job_from_blob(b)
                            for b in blob["job_history"]]
        tier.solo.job_seq = blob["job_seq"]
        # Sessions are deliberately NOT restored: every
        # pre-restart session is dead and workers
        # re-authenticate (EXP-055 restart rule).
        tier.sessions = {}
        return tier


# ------------------------------------------------------------------
# Stratum V1 front end
# ------------------------------------------------------------------

class _AggHandler(socketserver.StreamRequestHandler):
    def setup(self):
        super().setup()
        try:
            self.request.setsockopt(
                __import__("socket").IPPROTO_TCP,
                __import__("socket").TCP_NODELAY, 1)
        except OSError:
            pass

    def handle(self):
        tier: AggregationTier = self.server.tier
        self._session_id = None
        try:
            self._run(tier)
        finally:
            if self._session_id is not None:
                tier.close_session(self._session_id)

    def _run(self, tier):
        for raw in self.rfile:
            try:
                msg = json.loads(raw.decode())
            except Exception:
                continue
            method = msg.get("method")
            mid = msg.get("id")
            if method == "mining.subscribe":
                self._send({"id": mid, "result": [
                    [["mining.set_difficulty", "agg1"],
                     ["mining.notify", "agg2"]],
                    "00000000", 4], "error": None})
            elif method == "mining.authorize":
                # Fleet identity at the stratum layer:
                # params are [worker_id, enrollment_token];
                # the fleet id is the tier's own. A session
                # is opened only on an exact match, and the
                # connection's extranonce1 is the session's.
                params = msg.get("params") or []
                worker = str(params[0]) if params else ""
                token = str(params[1]) if len(params) > 1 else ""
                try:
                    sid, en1 = tier.open_session(
                        worker, tier.fleet_id, token)
                except IdentityError as exc:
                    self._send({"id": mid, "result": False,
                                "error": [24, str(exc), None]})
                    return
                # D-1 fix (EXP-057 audit): a successful
                # re-authorize on this connection closes the
                # previous session before the new one is
                # bound, so no session is orphaned to
                # outlive its connection (handle() only ever
                # had the final session id to close).
                previous_sid = self._session_id
                self._session_id = sid
                if previous_sid is not None \
                        and previous_sid != sid:
                    tier.close_session(previous_sid)
                self._en1_hex = en1.hex()
                # Re-send the subscribe-shaped binding: the
                # client learns its extranonce1 here, bound
                # to its authenticated identity.
                self._send({"id": mid, "result": True,
                            "error": None})
                self._send({"id": None,
                            "method": "mining.set_extranonce",
                            "params": [self._en1_hex, 4]})
                self._send({"id": None,
                            "method": "mining.set_difficulty",
                            "params": [tier.solo.share_difficulty]})
                job = tier.current_job() or tier.refresh_workbase()
                self._send({"id": None, "method": "mining.notify",
                            "params": tier.notify_params(job)})
            elif method == "mining.submit":
                if self._session_id is None:
                    self._send({"id": mid, "result": False,
                                "error": [25, "not authorized",
                                            None]})
                    continue
                claimed, job_id, en2, ntime, nonce = msg["params"]
                try:
                    out = tier.submit_share(
                        self._session_id, job_id, en2, ntime,
                        nonce, claimed_worker=str(claimed))
                except IdentityError as exc:
                    self._send({"id": mid, "result": False,
                                "error": [24, str(exc), None]})
                    continue
                self._send({"id": mid,
                            "result": out["accepted"],
                            "error": None if out["accepted"]
                            else [20, out["reason"], None]})
            elif method == "mining.suggest_difficulty":
                self._send({"id": mid, "result": True,
                            "error": None})
            else:
                self._send({"id": mid, "result": None,
                            "error": [501, "unknown method",
                                      None]})

    def _send(self, obj):
        self.wfile.write((json.dumps(obj) + "\n").encode())
        self.wfile.flush()


class AggregationTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, tier):
        self.tier = tier
        super().__init__(address, _AggHandler)
