"""Solo vardiff prototype (NOVA-ER-0004, register R-12).

Research code. Imports the production solo server unchanged
and extends it; nothing in mining/ is modified. See DESIGN.md
in this directory for the decided design (EXP-030 matrix M10),
the declared constants, the judging rules, and the Stage 6
integration path this prototype is evidence for.

Shape of the extension:

- VarDiffController: the pure control law (per-connection
  difficulty toward a target share interval, hysteresis on
  increases, idle decay on job changes, floor and ceiling).
  Time is an argument to every method, so the law is testable
  under a simulated clock with no sleeping.

- VarDiffSoloServer: a SoloServer subclass adding
  per-connection difficulty state keyed by extranonce1, a
  per-(connection, job) difficulty snapshot taken when the
  job is issued (a share is judged against the difficulty in
  force for the job it answers), a bounded history of
  superseded jobs so stale shares are classified rather than
  lumped into "unknown job", duplicate detection, and an
  append-only adjustment log. Block candidacy is untouched:
  it is decided by mining/candidate_verify.py's exact integer
  test against the network target at every difficulty
  (EXP-036 separation: difficulty is a share criterion only).

- VarDiffTCPServer / _VarDiffHandler: the wire side. The
  production SoloTCPServer hardcodes its handler class, so
  the pair is mirrored here with exactly four deltas:
  connection registration and teardown, the connection's own
  difficulty in the subscribe set_difficulty message, a
  set_difficulty notice when an adjustment lands, and a
  per-client set_difficulty ahead of each broadcast notify.

Pinned mode (vardiff_enabled=False) delegates submit_share to
the production implementation verbatim: it is the rollback
surface and the differential-test baseline.
"""

import json
import socket
import socketserver
import threading
import time

from mining.candidate_verify import (classify_submit_result,
                                     verify_candidate,
                                     verify_chain_acceptance)
from mining.solo_server import (SoloNotReady, SoloServer,
                                attach_witness, _varint)

# Stratum difficulty-1 target, the same constant the
# production server and mining/stratum_client.py use.
DIFF1 = int("00000000ffff" + "00" * 26, 16)


def share_target_for(difficulty):
    """The production formula, int(diff1 / difficulty),
    integer-exact; identical to SoloServer's constructor
    computation and to stratum_client.target_for_difficulty."""
    return int(DIFF1 / difficulty)


class VarDiffController:
    """The decided control law (DESIGN.md section 4).

    One instance serves every connection; per-connection
    state lives in the dicts returned by new_connection and
    is passed back on each event. The controller holds no
    locks and no clock: callers serialise events and supply
    time, which is what makes the law reproducible under a
    simulated clock in tests.
    """

    def __init__(self, target_interval=15.0, floor=0.002,
                 ceiling=1.0, initial=0.02, ema_alpha=0.35,
                 deadband=1.25,
                 up_hysteresis_s=30.0, up_confirmations=2,
                 max_up_factor=1.5, max_down_factor=2.0,
                 decay_after_s=60.0, decay_factor=2.0):
        if not (0 < floor <= initial <= ceiling):
            raise ValueError(
                "require 0 < floor <= initial <= ceiling")
        if target_interval <= 0:
            raise ValueError("target_interval must be positive")
        if deadband < 1:
            raise ValueError("deadband must be >= 1")
        if not (0 < ema_alpha <= 1):
            raise ValueError("ema_alpha must be in (0, 1]")
        if max_up_factor < 1 or max_down_factor < 1:
            raise ValueError("adjustment factors must be >= 1")
        if decay_factor < 1:
            raise ValueError("decay_factor must be >= 1")
        self.target_interval = float(target_interval)
        self.deadband = float(deadband)
        self.floor = float(floor)
        self.ceiling = float(ceiling)
        self.initial = float(initial)
        self.ema_alpha = float(ema_alpha)
        self.up_hysteresis_s = float(up_hysteresis_s)
        self.up_confirmations = int(up_confirmations)
        self.max_up_factor = float(max_up_factor)
        self.max_down_factor = float(max_down_factor)
        self.decay_after_s = float(decay_after_s)
        self.decay_factor = float(decay_factor)

    def new_connection(self, now):
        return {
            "difficulty": self.initial,
            "connected_at": now,
            "last_share_at": None,
            "ema_interval": None,
            "fast_votes": 0,
            "last_up_at": None,
            "shares": 0,
            "last_clamp_reason": None,
        }

    def _record(self, st, new, reason, ema, clamped):
        old = st["difficulty"]
        st["difficulty"] = new
        return {"reason": reason, "old": old, "new": new,
                "ema_interval": ema, "clamped": clamped}

    def _clamp_event(self, st, desired, reason, ema):
        """Apply a desired difficulty inside the bounds.
        Returns an adjustment record, or None when nothing
        changed (including a repeated clamp at the same bound,
        which is logged once per distinct bound state)."""
        new = min(max(desired, self.floor), self.ceiling)
        clamped = new != desired
        if new == st["difficulty"]:
            if clamped and st["last_clamp_reason"] != reason:
                st["last_clamp_reason"] = reason
                return self._record(st, new, reason, ema, True)
            return None
        st["last_clamp_reason"] = None
        return self._record(st, new, reason, ema, clamped)

    def on_accepted_share(self, st, now):
        """One accepted share from this connection. Returns an
        adjustment record or None. Decreases apply at once;
        increases carry the decided hysteresis (confirmation
        count plus a grace period since the last increase)."""
        st["shares"] += 1
        if st["last_share_at"] is None:
            st["last_share_at"] = now
            return None
        dt = max(now - st["last_share_at"], 1e-9)
        st["last_share_at"] = now
        if st["ema_interval"] is None:
            st["ema_interval"] = dt
        else:
            a = self.ema_alpha
            st["ema_interval"] = a * dt + (1 - a) * st["ema_interval"]
        ema = st["ema_interval"]
        if ema > self.target_interval * self.deadband:
            st["fast_votes"] = 0
            factor = min(ema / self.target_interval,
                         self.max_down_factor)
            return self._clamp_event(
                st, st["difficulty"] / factor,
                "interval above target: decrease", ema)
        if ema < self.target_interval / self.deadband:
            st["fast_votes"] += 1
            if st["fast_votes"] < self.up_confirmations:
                return None
            if (st["last_up_at"] is not None
                    and now - st["last_up_at"]
                    < self.up_hysteresis_s):
                return None
            factor = min(self.target_interval / ema,
                         self.max_up_factor)
            rec = self._clamp_event(
                st, st["difficulty"] * factor,
                "interval below target: increase", ema)
            if rec is not None:
                st["last_up_at"] = now
                st["fast_votes"] = 0
            return rec
        st["fast_votes"] = 0
        return None

    def on_job_change(self, st, now):
        """Idle decay, evaluated on job changes only (there is
        no timer in this design; the production JobRefresher
        guarantees job changes on tip moves and at a maximum
        job age). One decay step per job change once the idle
        threshold has passed, toward the floor."""
        ref = st["last_share_at"]
        if ref is None:
            ref = st["connected_at"]
        if now - ref <= self.decay_after_s:
            return None
        if st["difficulty"] <= self.floor:
            return None
        return self._clamp_event(
            st, st["difficulty"] / self.decay_factor,
            "idle decay", st["ema_interval"])


class VarDiffSoloServer(SoloServer):
    """SoloServer with per-connection vardiff. See DESIGN.md."""

    def __init__(self, rpc, payout_address, controller=None,
                 vardiff_enabled=True, pinned_difficulty=0.02,
                 job_history_size=8, **kwargs):
        if "share_difficulty" in kwargs:
            raise ValueError(
                "share_difficulty is owned by the vardiff layer: "
                "pass controller initial or pinned_difficulty")
        self.vardiff_enabled = bool(vardiff_enabled)
        self.controller = controller or VarDiffController()
        base = (self.controller.initial if self.vardiff_enabled
                else pinned_difficulty)
        super().__init__(rpc, payout_address,
                         share_difficulty=base, **kwargs)
        self.pinned_difficulty = pinned_difficulty
        self.job_history_size = int(job_history_size)
        self.job_history = []
        # en1 bytes -> {"state", "worker", "snapshots", "seen",
        #               "notified"}
        self.connections = {}
        self.adjustment_log = []
        self.shares_stale = 0
        self.shares_duplicate = 0
        self.stale_records = []

    # -- connection lifecycle --------------------------------
    def register_connection(self, extranonce1, now=None):
        if not self.vardiff_enabled:
            return
        now = time.time() if now is None else now
        with self.lock:
            conn = {
                "state": self.controller.new_connection(now),
                "worker": None,
                "snapshots": {},
                "seen": set(),
                "notified": self.controller.initial,
            }
            if self.current is not None:
                conn["snapshots"][self.current["job_id"]] = \
                    self.controller.initial
            self.connections[bytes(extranonce1)] = conn

    def unregister_connection(self, extranonce1):
        with self.lock:
            self.connections.pop(bytes(extranonce1), None)

    def connection_difficulty(self, extranonce1):
        if not self.vardiff_enabled:
            return self.share_difficulty
        with self.lock:
            conn = self.connections.get(bytes(extranonce1))
        if conn is None:
            return self.share_difficulty
        return conn["state"]["difficulty"]

    def pending_notice(self, extranonce1):
        """The difficulty to push to this client, if it changed
        since the last notice; consumes the notice."""
        if not self.vardiff_enabled:
            return None
        with self.lock:
            conn = self.connections.get(bytes(extranonce1))
            if conn is None:
                return None
            cur = conn["state"]["difficulty"]
            if cur == conn["notified"]:
                return None
            conn["notified"] = cur
            return cur

    def note_authorize(self, worker):
        super().note_authorize(worker)

    # -- adjustment log ---------------------------------------
    def _log_adjustment(self, extranonce1, conn, rec, now):
        entry = {"ts": now,
                 "connection": bytes(extranonce1).hex(),
                 "worker": conn["worker"] if conn else None,
                 "reason": rec["reason"], "old": rec["old"],
                 "new": rec["new"],
                 "ema_interval": rec["ema_interval"],
                 "clamped": rec["clamped"]}
        with self.lock:
            self.adjustment_log.append(entry)
        return entry

    # -- job lifecycle -----------------------------------------
    def refresh_job(self):
        old = self.current
        job = super().refresh_job()
        if not self.vardiff_enabled:
            return job
        now = time.time()
        with self.lock:
            if old is not None and old["job_id"] != job["job_id"]:
                self.job_history.append(old)
                del self.job_history[:-self.job_history_size]
            keep = {j["job_id"] for j in self.job_history}
            keep.add(job["job_id"])
            conns = list(self.connections.items())
        for en1, conn in conns:
            st = conn["state"]
            conn["snapshots"][job["job_id"]] = st["difficulty"]
            conn["snapshots"] = {
                k: v for k, v in conn["snapshots"].items()
                if k in keep}
            rec = self.controller.on_job_change(st, now)
            if rec is not None:
                self._log_adjustment(en1, conn, rec, now)
        return job

    def _find_job(self, job_id):
        """(job, stale) for a job id: current first, then the
        bounded superseded history."""
        with self.lock:
            job = self.jobs.get(job_id)
            if job is not None:
                return job, False
            for j in self.job_history:
                if j["job_id"] == job_id:
                    return j, True
        return None, False

    # -- accounting --------------------------------------------
    def _count_vd(self, worker, kind):
        with self.lock:
            rec = self._worker_rec(worker or "unknown")
            rec["last_submit_at"] = time.time()
            rec[kind] = rec.get(kind, 0) + 1
            if kind == "stale":
                self.shares_stale += 1
            elif kind == "duplicate":
                self.shares_duplicate += 1

    def stats(self):
        out = super().stats()
        if self.vardiff_enabled:
            with self.lock:
                conns = {
                    en1.hex(): {
                        "difficulty":
                            c["state"]["difficulty"],
                        "ema_interval":
                            c["state"]["ema_interval"],
                        "shares": c["state"]["shares"],
                        "worker": c["worker"],
                    } for en1, c in self.connections.items()}
                out["vardiff"] = {
                    "enabled": True,
                    "target_interval":
                        self.controller.target_interval,
                    "floor": self.controller.floor,
                    "ceiling": self.controller.ceiling,
                    "initial": self.controller.initial,
                    "shares_stale": self.shares_stale,
                    "shares_duplicate": self.shares_duplicate,
                    "adjustments": len(self.adjustment_log),
                    "connections": conns,
                }
        else:
            out["vardiff"] = {"enabled": False,
                              "pinned": self.pinned_difficulty}
        return out

    # -- share submission ---------------------------------------
    def submit_share(self, job_id, extranonce1, en2, ntime, nonce,
                     worker=None):
        if not self.vardiff_enabled:
            return super().submit_share(
                job_id, extranonce1, en2, ntime, nonce,
                worker=worker)
        en1 = bytes(extranonce1)
        with self.lock:
            conn = self.connections.get(en1)
            if conn is not None and worker:
                conn["worker"] = str(worker)
        # Duplicate detection precedes all judging: a repeat is
        # its own category, never a second acceptance and never
        # an adjustment trigger.
        if conn is not None:
            key = (job_id, en2, ntime, nonce)
            with self.lock:
                seen = key in conn["seen"]
                if not seen:
                    conn["seen"].add(key)
                    if len(conn["seen"]) > 200000:
                        conn["seen"] = {key}
            if seen:
                self._count_vd(worker, "duplicate")
                return {"accepted": False,
                        "reason": "duplicate share",
                        "classification": "duplicate"}
        job, stale = self._find_job(job_id)
        if job is None:
            self._count(worker, False)
            return {"accepted": False, "reason": "unknown job",
                    "classification": "unknown_job"}
        if stale:
            return self._submit_stale(
                job, conn, extranonce1, en2, ntime, nonce, worker)
        snap = None
        if conn is not None:
            snap = conn["snapshots"].get(job_id)
        share_target = (share_target_for(snap) if snap is not None
                        else self.share_target)
        return self._submit_current(
            job, share_target, conn, extranonce1, en2, ntime,
            nonce, worker)

    def _after_accept(self, conn, extranonce1):
        if conn is None:
            return
        now = time.time()
        rec = self.controller.on_accepted_share(conn["state"], now)
        if rec is not None:
            self._log_adjustment(extranonce1, conn, rec, now)

    def _submit_current(self, job, share_target, conn,
                        extranonce1, en2, ntime, nonce, worker):
        """The production submit pipeline with the share target
        taken from this connection's snapshot for this job. The
        network-target leg is identical to production: difficulty
        never enters candidate judging."""
        res, err = self.validate_share(job, extranonce1, en2,
                                       ntime, nonce)
        if err:
            self._count(worker, False)
            return {"accepted": False, "reason": err,
                    "classification": "invalid"}
        if not (res["value"] <= job["target"]
                or res["value"] <= share_target):
            self._count(worker, False)
            return {"accepted": False,
                    "reason": "low difficulty share",
                    "classification": "below_target"}
        v = verify_candidate(res["header"], self._pow_limit(),
                             share_target=share_target)
        if v["target"] != job["target"]:
            v = dict(v, classification="invalid",
                     reason="header-target-mismatch")
        if v["classification"] == "invalid":
            rec = {"height": job["template"]["height"],
                   "hash": res["digest"][::-1].hex(),
                   "reason": v["reason"], "worker": worker}
            with self.lock:
                self.candidates_rejected.append(rec)
            self._count(worker, False, candidate=True)
            return {"accepted": False,
                    "reason": f"exact verification failed: "
                              f"{v['reason']}",
                    "classification": "invalid"}
        if v["meets_network_target"]:
            rec = self._submit_block(job, res, v, worker,
                                     stale=False)
            self._count(worker, True, block=rec["accepted"],
                        candidate=True)
            self._after_accept(conn, extranonce1)
            return {"accepted": True, "block": rec,
                    "classification": "block_candidate"}
        if v["meets_share_target"]:
            self._count(worker, True)
            self._after_accept(conn, extranonce1)
            return {"accepted": True, "block": None,
                    "classification": "share"}
        self._count(worker, False)
        return {"accepted": False,
                "reason": "low difficulty share",
                "classification": "below_target"}

    def _submit_stale(self, job, conn, extranonce1, en2, ntime,
                      nonce, worker):
        """A share answering a superseded job: classified,
        never counted as an accepted share, and judged against
        its own job and its own snapshot. A network-target hit
        is still a real candidate and goes through the exact
        pipeline; chain state decides its acceptance."""
        res, err = self.validate_share(job, extranonce1, en2,
                                       ntime, nonce)
        if err:
            self._count_vd(worker, "stale")
            self._stale_record(job, worker, "stale-invalid", err)
            return {"accepted": False,
                    "reason": f"stale job: {err}",
                    "classification": "stale"}
        snap = None
        if conn is not None:
            snap = conn["snapshots"].get(job["job_id"])
        share_target = (share_target_for(snap) if snap is not None
                        else None)
        meets_net = res["value"] <= job["target"]
        meets_share = (share_target is not None
                       and res["value"] <= share_target)
        if not (meets_net or meets_share):
            self._count_vd(worker, "stale")
            self._stale_record(job, worker, "stale-low",
                               "below its job's targets")
            return {"accepted": False,
                    "reason": "stale job: below target",
                    "classification": "stale"}
        v = verify_candidate(res["header"], self._pow_limit(),
                             share_target=share_target)
        if v["target"] != job["target"]:
            v = dict(v, classification="invalid",
                     reason="header-target-mismatch")
        if v["classification"] == "invalid":
            rec = {"height": job["template"]["height"],
                   "hash": res["digest"][::-1].hex(),
                   "reason": v["reason"], "worker": worker,
                   "stale": True}
            with self.lock:
                self.candidates_rejected.append(rec)
            self._count_vd(worker, "stale")
            return {"accepted": False,
                    "reason": f"stale job: exact verification "
                              f"failed: {v['reason']}",
                    "classification": "stale"}
        if v["meets_network_target"]:
            rec = self._submit_block(job, res, v, worker,
                                     stale=True)
            self._count_vd(worker, "stale")
            return {"accepted": False, "block": rec,
                    "reason": "stale job: block candidate "
                              "submitted",
                    "classification": "stale"}
        self._count_vd(worker, "stale")
        self._stale_record(job, worker, "stale-valid",
                           "met its job's share target")
        return {"accepted": False, "reason": "stale job",
                "classification": "stale"}

    def _stale_record(self, job, worker, kind, detail):
        with self.lock:
            self.stale_records.append({
                "height": job["template"]["height"],
                "job_id": job["job_id"], "worker": worker,
                "kind": kind, "detail": detail,
                "ts": time.time()})

    def _submit_block(self, job, res, v, worker, stale):
        """Block assembly and submission, mirroring the
        production solo server step for step (EXP-036: the
        submitblock response is a claim; chain state is the
        fact)."""
        t = job["template"]
        txs = b"".join(bytes.fromhex(tx["data"])
                       for tx in t["transactions"])
        coinbase = res["coinbase"]
        if job.get("has_witness"):
            coinbase = attach_witness(coinbase)
        block = (res["header"] + _varint(1 + len(t["transactions"]))
                 + coinbase + txs)
        block_hash = res["digest"][::-1].hex()
        rpc_error = None
        try:
            r = self.rpc.call("submitblock", block.hex())
        except Exception as exc:
            rpc_error = exc
            r = f"submitblock RPC failed: {exc}"
        classification = ("rpc-error" if rpc_error is not None
                          else classify_submit_result(r))
        if rpc_error is None:
            chain_status, chain_ok = verify_chain_acceptance(
                self.rpc, block_hash)
        else:
            chain_status, chain_ok = "unknown", False
        ok = bool(chain_ok and classification
                  in ("accepted", "duplicate"))
        if not ok:
            print(f"vardiff-solo: BLOCK NOT ACCEPTED at height "
                  f"{t['height']}: submitblock said {r!r} "
                  f"({classification}), chain state "
                  f"{chain_status}", flush=True)
        rec = {"height": t["height"], "hash": block_hash,
               "submit_result": r,
               "submit_classification": classification,
               "chain_status": chain_status,
               "chain_verified": chain_ok,
               "verify_reason": v["reason"],
               "accepted": ok, "stale": stale}
        with self.lock:
            self.blocks_found.append(rec)
        return rec


class _VarDiffHandler(socketserver.StreamRequestHandler):
    """Mirror of mining/solo_server._Handler with the four
    vardiff deltas named in this module's docstring."""

    def setup(self):
        super().setup()
        try:
            self.request.setsockopt(
                socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass

    def handle(self):
        srv = self.server.solo
        extranonce1 = self.server.next_en1()
        self._en1 = extranonce1
        srv.register_connection(extranonce1)
        with self.server.clients_lock:
            self.server.clients.add(self)
        try:
            self._run(srv, extranonce1)
        finally:
            with self.server.clients_lock:
                self.server.clients.discard(self)
            srv.unregister_connection(extranonce1)

    def _run(self, srv, extranonce1):
        worker_name = "unknown"
        for raw in self.rfile:
            try:
                msg = json.loads(raw.decode())
            except Exception:
                continue
            method = msg.get("method")
            mid = msg.get("id")
            if method == "mining.subscribe":
                self._send({"id": mid, "result": [
                    [["mining.set_difficulty", "bal1"],
                     ["mining.notify", "bal2"]],
                    extranonce1.hex(), 4], "error": None})
                self._send({"id": None,
                            "method": "mining.set_difficulty",
                            "params": [srv.connection_difficulty(
                                extranonce1)]})
                try:
                    job = srv.current or srv.refresh_job()
                except SoloNotReady as exc:
                    print(f"vardiff-solo: subscribe refused: "
                          f"{exc}", flush=True)
                    return
                self._send({"id": None, "method": "mining.notify",
                            "params": srv.notify_params(job)})
            elif method == "mining.authorize":
                if msg.get("params"):
                    worker_name = str(msg["params"][0])
                srv.note_authorize(worker_name)
                with srv.lock:
                    conn = srv.connections.get(
                        bytes(extranonce1))
                    if conn is not None:
                        conn["worker"] = worker_name
                self._send({"id": mid, "result": True,
                            "error": None})
            elif method == "mining.suggest_difficulty":
                self._send({"id": mid, "result": True,
                            "error": None})
            elif method == "mining.submit":
                worker, job_id, en2, ntime, nonce = msg["params"]
                out = srv.submit_share(job_id, extranonce1, en2,
                                       ntime, nonce,
                                       worker=str(worker))
                self._send({"id": mid, "result": out["accepted"],
                            "error": None if out["accepted"]
                            else [20, out["reason"], None]})
                notice = srv.pending_notice(extranonce1)
                if notice is not None:
                    self._send({"id": None,
                                "method": "mining.set_difficulty",
                                "params": [notice]})
                if out.get("block"):
                    try:
                        job = srv.refresh_job()
                    except SoloNotReady as exc:
                        print(f"vardiff-solo: post-block refresh "
                              f"refused: {exc}", flush=True)
                    else:
                        self._broadcast(job)
            else:
                self._send({"id": mid, "result": None,
                            "error": [501, "unknown method", None]})

    def _send(self, obj):
        self.wfile.write((json.dumps(obj) + "\n").encode())
        self.wfile.flush()

    def _broadcast(self, job):
        self.server.broadcast(job)


class VarDiffTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, solo):
        self.solo = solo
        self.share_difficulty = solo.share_difficulty
        self._en1 = 0
        self._en1_lock = threading.Lock()
        self.clients = set()
        self.clients_lock = threading.Lock()
        super().__init__(addr, _VarDiffHandler)

    def next_en1(self):
        with self._en1_lock:
            self._en1 += 1
            return self._en1.to_bytes(4, "little")

    def broadcast(self, job):
        """Fresh job to every worker, each preceded by that
        connection's own current difficulty (the difficulty in
        force for the job it is about to receive)."""
        with self.clients_lock:
            clients = list(self.clients)
        for h in clients:
            try:
                en1 = getattr(h, "_en1", None)
                if en1 is not None:
                    h._send({"id": None,
                             "method": "mining.set_difficulty",
                             "params": [
                                 self.solo.connection_difficulty(
                                     en1)]})
                    with self.solo.lock:
                        conn = self.solo.connections.get(
                            bytes(en1))
                        if conn is not None:
                            conn["notified"] = \
                                conn["state"]["difficulty"]
                h._send({"id": None, "method": "mining.notify",
                         "params": self.solo.notify_params(job)})
            except Exception:
                pass
