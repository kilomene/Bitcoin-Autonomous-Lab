#!/usr/bin/env python3
"""EXP-035 lease manager prototype (research only).

The production-design core for the Work Lease Manager and
the Distributed Agent Coordinator (directive section 12,
components 8 and 10). It generalises the proven EXP-029
RangeAllocator (research/sha256d/phase6b/benchmarks/
exp029_allocator.py) in four ways the EXP-030 gap analysis
requires for production:

  1. Multi-dimensional search space. A job's declared
     space is a set of slices. A slice is one combination
     of (extranonce2 worker slot, extranonce2 counter,
     version-rolling variant, ntime value) times a nonce
     range. Leases are issued over nonce chunks inside one
     slice. Dividing the 32-bit nonce range alone is NOT
     the model (directive section 8).
  2. Lease identity and fencing. Every lease issuance gets
     a unique lease_id and a fencing token from one
     monotonically increasing counter. Progress and
     completion reports must present the current token.
     A reclaimed, superseded or pre-restart token is
     rejected as STALE and counted, never credited. This
     is what makes "a restarted process must not falsely
     claim unfinished work was completed" enforceable:
     after a restart the worker holds no valid token.
  3. Expiry. Leases carry a deadline, and a worker whose
     heartbeat is older than the telemetry timeout (10 s
     class, matrix M14) is stale. expire() reclaims both
     kinds. Reclaim moves the lease's reported progress
     into examined_before, so the re-examination is
     accounted as repeated work on re-lease, exactly as
     in EXP-029 fail_worker().
  4. Worker registry. Workers register against a fleet
     identity; foreign-fleet registrations are rejected
     (M14). A worker that holds no lease for longer than
     the starvation window must re-register before it can
     lease again (M15). A worker restart notice reclaims
     that worker's leases immediately instead of waiting
     for the timeout.

Preserved from EXP-029, unchanged in substance:
  * A chunk is in exactly one state: pending, leased to
    one worker, or completed. Leases are exclusive.
  * complete() is idempotent per lease: a replayed
    completion from the same lease returns DUPLICATE and
    changes no coverage.
  * Stealing splits the unreported tail of the largest
    leased chunk; the victim's lease shrinks FIRST and
    its fencing token is rotated, so the partition is
    disjoint at every instant and the victim's old token
    is dead.
  * Coordinator restart: snapshot()/restore() preserve
    completed coverage, accounting and the token counter,
    but leases never survive: outstanding leases are
    reclaimed and every pre-restart token becomes STALE.
  * Accounting separations: unique coverage grows only
    by completed chunk sizes; actual computations count
    every reported examination; repeated computations
    count examinations of already-examined positions;
    duplicate and stale reports are counted separately
    and never enter unique coverage.

Time is an explicit parameter everywhere (a simulated
clock in tests, a wall clock in production). This module
performs no hashing and no I/O.
"""


class LeaseError(Exception):
    pass


class ForeignFleetError(LeaseError):
    pass


class LeaseManager:
    def __init__(self, fleet_id, heartbeat_timeout=10.0,
                 starvation_window=10.0):
        self.fleet_id = fleet_id
        self.heartbeat_timeout = heartbeat_timeout
        self.starvation_window = starvation_window
        self.workers = {}   # id -> registry record
        self.job = None     # current job declaration
        self.slices = []    # slice dicts (see declare_job)
        self.leases = {}    # lease_id -> lease record
        self._lease_seq = 0
        self._token_seq = 0
        self.epoch = 0      # bumps on coordinator restore
        # accounting (aggregated over slices)
        self.actual = 0
        self.repeated = 0
        self.duplicate_deliveries = 0
        self.stale_reports = 0
        self.not_holder_attempts = 0
        self.unknown_lease_reports = 0
        self.reclaims = 0
        self.reregistrations = 0
        self.events = []

    # -- registry ------------------------------------------------
    def register_worker(self, worker_id, fleet_id, now):
        if fleet_id != self.fleet_id:
            raise ForeignFleetError(
                "worker %s presented fleet %r, expected %r"
                % (worker_id, fleet_id, self.fleet_id))
        rec = self.workers.get(worker_id)
        if rec is None:
            self.workers[worker_id] = {
                "worker_id": worker_id,
                "registered_at": now,
                "last_heartbeat": now,
                "last_lease_at": None,
                "slot_by_job": {},
                "restarts": 0,
            }
            self.events.append(("register", worker_id))
            return "REGISTERED"
        rec["last_heartbeat"] = now
        # Re-registration restarts the starvation clock:
        # the M15 rule is that a starved worker
        # re-registers INSTEAD of idling, and may then
        # lease again.
        rec["last_lease_at"] = now
        self.reregistrations += 1
        self.events.append(("reregister", worker_id))
        return "REREGISTERED"

    def heartbeat(self, worker_id, now, rate=None):
        rec = self.workers.get(worker_id)
        if rec is None:
            raise LeaseError("heartbeat from unregistered "
                             "worker %s" % worker_id)
        rec["last_heartbeat"] = now
        rec["rate"] = rate

    def stale_workers(self, now):
        return [w for w, r in self.workers.items()
                if now - r["last_heartbeat"]
                > self.heartbeat_timeout]

    def worker_restarted(self, worker_id, now):
        """Coordinator learns a worker process restarted
        (in production: from the EXP-038 supervisor). Its
        leases are reclaimed immediately; the worker must
        re-register before leasing again."""
        rec = self.workers.get(worker_id)
        if rec is None:
            raise LeaseError("restart notice for unknown "
                             "worker %s" % worker_id)
        rec["restarts"] += 1
        rec["last_heartbeat"] = None  # must re-register
        out = []
        for lease in list(self.leases.values()):
            if lease["worker"] == worker_id \
                    and lease["state"] == "active":
                out.append(self._reclaim(lease,
                                         "worker_restart"))
        self.events.append(("worker_restart", worker_id))
        return out

    # -- job declaration ------------------------------------------
    def declare_job(self, job_id, generation, nonce_count,
                    chunk_size, n_slots, version_variants,
                    ntime_values, counters_per_slot=1):
        """Declare the search space for one job. The space
        is the Cartesian product of extranonce2 slices
        (slot, counter), version variants and ntime values,
        each times the nonce range [0, nonce_count).
        A new declaration invalidates the previous job:
        outstanding leases die with it and stale-generation
        reports are rejected by token, as in EXP-029's
        per-template allocator rule."""
        if self.job is not None:
            for lease in self.leases.values():
                if lease["state"] == "active":
                    lease["state"] = "superseded"
            self.events.append(("job_superseded",
                                self.job["job_id"]))
        self.job = {"job_id": job_id,
                    "generation": generation,
                    "nonce_count": nonce_count,
                    "chunk_size": chunk_size}
        self.slices = []
        for slot in range(n_slots):
            for counter in range(counters_per_slot):
                for version in version_variants:
                    for ntime in ntime_values:
                        chunks = []
                        lo = 0
                        while lo < nonce_count:
                            hi = min(lo + chunk_size,
                                     nonce_count)
                            chunks.append({
                                "lo": lo, "hi": hi,
                                "state": "pending",
                                "lease_id": None,
                                "reported": 0,
                                "examined_before": 0})
                            lo = hi
                        self.slices.append({
                            "slot": slot,
                            "counter": counter,
                            "extranonce2": (slot << 25)
                            | counter,
                            "version": version,
                            "ntime": ntime,
                            "chunks": chunks})
        self.events.append(("declare_job", job_id,
                            generation, len(self.slices)))
        return len(self.slices)

    def declared_total(self):
        if self.job is None:
            return 0
        return len(self.slices) * self.job["nonce_count"]

    def _slot_for(self, worker_id):
        rec = self.workers[worker_id]
        key = self.job["job_id"]
        if key not in rec["slot_by_job"]:
            used = {r["slot_by_job"][key]
                    for r in self.workers.values()
                    if key in r["slot_by_job"]}
            slot = 0
            while slot in used:
                slot += 1
            rec["slot_by_job"][key] = slot
        return rec["slot_by_job"][key]

    # -- leasing ---------------------------------------------------
    def _new_lease(self, worker_id, sl, ch, now, ttl):
        self._lease_seq += 1
        self._token_seq += 1
        lease = {
            "lease_id": "L%d" % self._lease_seq,
            "token": self._token_seq,
            "epoch": self.epoch,
            "worker": worker_id,
            "slice": (sl["slot"], sl["counter"],
                      sl["version"], sl["ntime"]),
            "extranonce2": sl["extranonce2"],
            "version": sl["version"],
            "ntime": sl["ntime"],
            "lo": ch["lo"], "hi": ch["hi"],
            "issued_at": now, "deadline": now + ttl,
            "state": "active",
        }
        self.leases[lease["lease_id"]] = lease
        ch["state"] = "leased"
        ch["lease_id"] = lease["lease_id"]
        ch["reported"] = 0
        if ch["examined_before"]:
            self.repeated += ch["examined_before"]
            ch["examined_before"] = 0
        self.workers[worker_id]["last_lease_at"] = now
        self.events.append(("lease", lease["lease_id"],
                            worker_id, lease["slice"],
                            ch["lo"], ch["hi"]))
        return dict(lease)

    def lease(self, worker_id, now, ttl=30.0):
        rec = self.workers.get(worker_id)
        if rec is None or rec["last_heartbeat"] is None:
            raise LeaseError("worker %s is not registered"
                             % worker_id)
        if rec["last_lease_at"] is not None and \
                now - rec["last_lease_at"] \
                > self.starvation_window and \
                not self._holds_lease(worker_id):
            raise LeaseError(
                "worker %s starved past the window; it "
                "must re-register (M15)" % worker_id)
        slot = self._slot_for(worker_id)
        for sl in self.slices:
            if sl["slot"] != slot:
                continue
            for ch in sl["chunks"]:
                if ch["state"] == "pending":
                    return self._new_lease(worker_id, sl,
                                            ch, now, ttl)
        return None

    def _holds_lease(self, worker_id):
        return any(l["worker"] == worker_id
                   and l["state"] == "active"
                   for l in self.leases.values())

    def _slice_of(self, lease):
        for sl in self.slices:
            if (sl["slot"], sl["counter"], sl["version"],
                    sl["ntime"]) == lease["slice"]:
                return sl
        return None

    def _chunk_of(self, lease):
        sl = self._slice_of(lease)
        if sl is None:
            return None
        for ch in sl["chunks"]:
            if ch["lo"] == lease["lo"] \
                    and ch["lease_id"] == lease["lease_id"]:
                return ch
        return None

    def _check_report(self, worker_id, lease_id, token):
        """Classify a progress/completion report.
        Returns (lease, status) where status is None for a
        valid live report, else the rejection class."""
        lease = self.leases.get(lease_id)
        if lease is None:
            self.unknown_lease_reports += 1
            return None, "UNKNOWN_LEASE"
        if lease["state"] == "completed":
            self.duplicate_deliveries += 1
            return lease, "DUPLICATE"
        if lease["state"] != "active" \
                or lease["token"] != token \
                or lease["epoch"] != self.epoch:
            self.stale_reports += 1
            return lease, "STALE"
        if lease["worker"] != worker_id:
            self.not_holder_attempts += 1
            return lease, "NOT_HOLDER"
        return lease, None

    def progress(self, worker_id, lease_id, token, examined):
        lease, status = self._check_report(worker_id,
                                           lease_id, token)
        if status is not None:
            return status
        ch = self._chunk_of(lease)
        size = ch["hi"] - ch["lo"]
        if not (ch["reported"] <= examined <= size):
            raise LeaseError("progress out of bounds")
        self.actual += examined - ch["reported"]
        ch["reported"] = examined
        return "OK"

    def complete(self, worker_id, lease_id, token):
        lease, status = self._check_report(worker_id,
                                           lease_id, token)
        if status is not None:
            return status
        ch = self._chunk_of(lease)
        size = ch["hi"] - ch["lo"]
        self.actual += size - ch["reported"]
        ch["reported"] = size
        ch["state"] = "completed"
        ch["lease_id"] = None
        lease["state"] = "completed"
        self.events.append(("complete", lease_id,
                            worker_id))
        return "OK"

    # -- reclaim, expiry, stealing --------------------------------
    def _reclaim(self, lease, reason):
        ch = self._chunk_of(lease)
        if ch is not None and ch["state"] == "leased":
            ch["examined_before"] = ch["reported"]
            ch["reported"] = 0
            ch["state"] = "pending"
            ch["lease_id"] = None
        lease["state"] = "reclaimed"
        lease["reclaim_reason"] = reason
        self.reclaims += 1
        self.events.append(("reclaim", lease["lease_id"],
                            reason))
        return lease["lease_id"]

    def fail_worker(self, worker_id):
        out = []
        for lease in list(self.leases.values()):
            if lease["worker"] == worker_id \
                    and lease["state"] == "active":
                out.append(self._reclaim(lease,
                                         "worker_failed"))
        return out

    def expire(self, now):
        """Reclaim leases past their deadline and leases
        held by heartbeat-stale workers."""
        stale = set(self.stale_workers(now))
        out = []
        for lease in list(self.leases.values()):
            if lease["state"] != "active":
                continue
            if now > lease["deadline"]:
                out.append(self._reclaim(lease,
                                         "lease_expired"))
            elif lease["worker"] in stale:
                out.append(self._reclaim(
                    lease, "worker_stale"))
        return out

    def steal(self, thief_id, now, ttl=30.0, min_tail=2):
        """Split the unreported tail of the largest active
        lease held by another worker, EXP-029 style: the
        victim's chunk shrinks first and its fencing token
        rotates, then the tail is leased to the thief."""
        best = None
        for sl in self.slices:
            for ch in sl["chunks"]:
                if ch["state"] != "leased":
                    continue
                lease = self.leases[ch["lease_id"]]
                if lease["worker"] == thief_id:
                    continue
                tail = (ch["hi"] - ch["lo"]) \
                    - ch["reported"]
                if tail >= 2 * min_tail and (
                        best is None or tail > best[0]):
                    best = (tail, sl, ch, lease)
        if best is None:
            return None
        _tail, sl, ch, victim = best
        size = ch["hi"] - ch["lo"]
        tail_lo = ch["lo"] + ch["reported"] \
            + (size - ch["reported"]) // 2
        stolen = {"lo": tail_lo, "hi": ch["hi"],
                  "state": "pending", "lease_id": None,
                  "reported": 0, "examined_before": 0}
        ch["hi"] = tail_lo
        victim["hi"] = tail_lo
        self._token_seq += 1
        victim["token"] = self._token_seq  # old token dies
        sl["chunks"].append(stolen)
        sl["chunks"].sort(key=lambda c: c["lo"])
        self.events.append(("steal", thief_id,
                            victim["lease_id"], tail_lo))
        return self._new_lease(thief_id, sl, stolen, now,
                               ttl)

    # -- coordinator restart ---------------------------------------
    def snapshot(self):
        import copy
        return copy.deepcopy({
            "fleet_id": self.fleet_id,
            "job": self.job,
            "slices": self.slices,
            "leases": self.leases,
            "workers": self.workers,
            "lease_seq": self._lease_seq,
            "token_seq": self._token_seq,
            "epoch": self.epoch,
            "actual": self.actual,
            "repeated": self.repeated,
            "duplicate_deliveries":
                self.duplicate_deliveries,
            "stale_reports": self.stale_reports,
            "not_holder_attempts": self.not_holder_attempts,
            "unknown_lease_reports":
                self.unknown_lease_reports,
            "reclaims": self.reclaims,
            "reregistrations": self.reregistrations})

    @classmethod
    def restore(cls, snap):
        obj = cls(snap["fleet_id"])
        obj.job = snap["job"]
        obj.slices = snap["slices"]
        obj.leases = snap["leases"]
        obj.workers = snap["workers"]
        obj._lease_seq = snap["lease_seq"]
        obj._token_seq = snap["token_seq"]
        obj.epoch = snap["epoch"] + 1  # pre-restart tokens die
        obj.actual = snap["actual"]
        obj.repeated = snap["repeated"]
        obj.duplicate_deliveries = \
            snap["duplicate_deliveries"]
        obj.stale_reports = snap["stale_reports"]
        obj.not_holder_attempts = snap["not_holder_attempts"]
        obj.unknown_lease_reports = \
            snap["unknown_lease_reports"]
        obj.reclaims = snap["reclaims"]
        obj.reregistrations = snap["reregistrations"]
        obj.events = [("restore", obj.epoch)]
        # Leases never survive a coordinator restart.
        for lease in obj.leases.values():
            if lease["state"] == "active":
                obj._reclaim(lease, "coordinator_restart")
        for rec in obj.workers.values():
            rec["last_heartbeat"] = None  # re-register (M15)
        return obj

    # -- accounting --------------------------------------------------
    def completed_intervals(self):
        """Completed (slice_key, lo, hi) triples."""
        out = []
        for sl in self.slices:
            key = (sl["slot"], sl["counter"], sl["version"],
                   sl["ntime"])
            for ch in sl["chunks"]:
                if ch["state"] == "completed":
                    out.append((key, ch["lo"], ch["hi"]))
        return sorted(out)

    def accounting(self):
        unique = pending = leased = 0
        for sl in self.slices:
            for ch in sl["chunks"]:
                size = ch["hi"] - ch["lo"]
                if ch["state"] == "completed":
                    unique += size
                elif ch["state"] == "pending":
                    pending += size
                else:
                    leased += size
        return {
            "job_id": self.job["job_id"] if self.job
            else None,
            "generation": self.job["generation"]
            if self.job else None,
            "declared_total": self.declared_total(),
            "unique_coverage": unique,
            "actual_computations": self.actual,
            "repeated_computations": self.repeated,
            "duplicate_deliveries":
                self.duplicate_deliveries,
            "stale_reports": self.stale_reports,
            "not_holder_attempts": self.not_holder_attempts,
            "unknown_lease_reports":
                self.unknown_lease_reports,
            "reclaims": self.reclaims,
            "pending": pending, "leased": leased,
            "complete": unique == self.declared_total()
            and self.declared_total() > 0}

    def assert_partition_invariant(self):
        """Every slice's chunks tile its nonce range with
        no gap and no overlap, at any instant."""
        for sl in self.slices:
            ivs = sorted((c["lo"], c["hi"])
                         for c in sl["chunks"])
            assert ivs[0][0] == 0, ivs
            assert ivs[-1][1] == self.job["nonce_count"], ivs
            for (a_lo, a_hi), (b_lo, _b) in zip(ivs,
                                                ivs[1:]):
                assert a_hi == b_lo, ("gap or overlap", ivs)
        return True
