#!/usr/bin/env python3
"""EXP-055 Gate 2: independent model of the EXP-035 design.

Written from research/sha256d/exp035/WORK_DISTRIBUTION_DESIGN.md
only, for differential accounting against the production
coordinator (mining/coordinator.py). It shares no code with
the coordinator: where the coordinator stores chunk records
and prunes finished leases into tombstones, this model keeps
the full lease history (the EXP-035 prototype's shape) and
computes coverage from interval lists per slice. If the two
implementations agree on every status classification and
every accounting counter over seeded operation scripts, the
accounting is differentially verified; any divergence is a
Gate 2 failure and is reported, never patched over.

The model implements the design's rules as written:

  * a job's declared space is slices (slot, counter,
    version, ntime) times [0, nonce_count), chunked;
  * extranonce2 = (slot << 25) | counter; a worker binds to
    the lowest free slot for the job on first lease;
  * leases are exclusive, carry fencing tokens from one
    monotonic counter, and have deadlines;
  * reports classify OK / DUPLICATE / STALE / NOT_HOLDER /
    UNKNOWN_LEASE; only completion credits unique coverage;
  * reclaim (death, expiry, restart, coordinator restart)
    moves reported progress to examined_before, booked as
    repeated work at re-lease;
  * stealing shrinks the victim chunk first and rotates
    its token, then leases the tail to the thief;
  * a worker idle past the starvation window without
    holding a lease must re-register before leasing;
  * coordinator restart bumps the epoch, reclaims every
    outstanding lease and forces re-registration;
  * a new job declaration supersedes the old job's leases.
"""


class ModelError(Exception):
    pass


class ForeignFleet(ModelError):
    pass


class Model:
    def __init__(self, fleet_id, heartbeat_timeout=10.0,
                 starvation_window=10.0):
        self.fleet_id = fleet_id
        self.heartbeat_timeout = heartbeat_timeout
        self.starvation_window = starvation_window
        self.workers = {}       # id -> record
        self.job = None
        # slice key -> sorted list of [lo, hi, state, lease_id,
        #                             reported, examined_before]
        self.slices = {}
        self.leases = {}        # full history, never pruned
        self.lease_seq = 0
        self.token_seq = 0
        self.epoch = 0
        self.actual = 0
        self.repeated = 0
        self.duplicate_deliveries = 0
        self.stale_reports = 0
        self.not_holder_attempts = 0
        self.unknown_lease_reports = 0
        self.reclaims = 0
        self.reregistrations = 0

    # registry -------------------------------------------------
    def register_worker(self, worker_id, fleet_id, now):
        if fleet_id != self.fleet_id:
            raise ForeignFleet(worker_id)
        rec = self.workers.get(worker_id)
        if rec is None:
            self.workers[worker_id] = {
                "last_heartbeat": now, "last_lease_at": None,
                "slot_by_job": {}, "restarts": 0}
            return "REGISTERED"
        rec["last_heartbeat"] = now
        rec["last_lease_at"] = now
        self.reregistrations += 1
        return "REREGISTERED"

    def heartbeat(self, worker_id, now):
        rec = self.workers.get(worker_id)
        if rec is None:
            raise ModelError("unknown worker")
        rec["last_heartbeat"] = now
        return "OK"

    # jobs -------------------------------------------------------
    def declare_job(self, job_id, generation, nonce_count,
                    chunk_size, n_slots, version_variants,
                    ntime_values, counters_per_slot=1):
        if self.job is not None:
            for lease in self.leases.values():
                if lease["state"] == "active":
                    lease["state"] = "superseded"
        self.job = {"job_id": job_id, "generation": generation,
                    "nonce_count": nonce_count,
                    "chunk_size": chunk_size}
        self.slices = {}
        for slot in range(n_slots):
            for counter in range(counters_per_slot):
                for version in version_variants:
                    for ntime in ntime_values:
                        chunks = []
                        lo = 0
                        while lo < nonce_count:
                            hi = min(lo + chunk_size,
                                     nonce_count)
                            chunks.append([lo, hi, "pending",
                                           None, 0, 0])
                            lo = hi
                        self.slices[(slot, counter, version,
                                     ntime)] = chunks
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

    # leasing ----------------------------------------------------
    def _chunk_of(self, lease):
        for ch in self.slices[lease["slice"]]:
            if ch[0] == lease["lo"] and ch[3] == \
                    lease["lease_id"]:
                return ch
        return None

    def _issue(self, worker_id, key, ch, now, ttl):
        self.lease_seq += 1
        self.token_seq += 1
        lease = {"lease_id": "L%d" % self.lease_seq,
                 "token": self.token_seq, "epoch": self.epoch,
                 "worker": worker_id, "slice": key,
                 "extranonce2": (key[0] << 25) | key[1],
                 "version": key[2], "ntime": key[3],
                 "lo": ch[0], "hi": ch[1], "issued_at": now,
                 "deadline": now + ttl, "state": "active"}
        self.leases[lease["lease_id"]] = lease
        ch[2] = "leased"
        ch[3] = lease["lease_id"]
        ch[4] = 0
        if ch[5]:
            self.repeated += ch[5]
            ch[5] = 0
        self.workers[worker_id]["last_lease_at"] = now
        return dict(lease)

    def lease(self, worker_id, now, ttl=30.0):
        rec = self.workers.get(worker_id)
        if rec is None or rec["last_heartbeat"] is None:
            raise ModelError("not registered")
        if rec["last_lease_at"] is not None and \
                now - rec["last_lease_at"] \
                > self.starvation_window and not any(
                    l["worker"] == worker_id
                    and l["state"] == "active"
                    for l in self.leases.values()):
            raise ModelError("starved; re-register (M15)")
        slot = self._slot_for(worker_id)
        for key in sorted(self.slices):
            if key[0] != slot:
                continue
            for ch in self.slices[key]:
                if ch[2] == "pending":
                    return self._issue(worker_id, key, ch,
                                       now, ttl)
        return None

    def _classify(self, worker_id, lease_id, token):
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
        lease, status = self._classify(worker_id, lease_id,
                                       token)
        if status is not None:
            return status
        ch = self._chunk_of(lease)
        size = ch[1] - ch[0]
        if not (ch[4] <= examined <= size):
            raise ModelError("progress out of bounds")
        self.actual += examined - ch[4]
        ch[4] = examined
        return "OK"

    def complete(self, worker_id, lease_id, token):
        lease, status = self._classify(worker_id, lease_id,
                                       token)
        if status is not None:
            return status
        ch = self._chunk_of(lease)
        size = ch[1] - ch[0]
        self.actual += size - ch[4]
        ch[4] = size
        ch[2] = "completed"
        ch[3] = None
        lease["state"] = "completed"
        return "OK"

    # reclaim paths ------------------------------------------------
    def _reclaim(self, lease, reason):
        ch = self._chunk_of(lease)
        if ch is not None and ch[2] == "leased":
            ch[5] = ch[4]
            ch[4] = 0
            ch[2] = "pending"
            ch[3] = None
        lease["state"] = "reclaimed"
        self.reclaims += 1
        return lease["lease_id"]

    def fail_worker(self, worker_id):
        return [self._reclaim(l, "worker_failed")
                for l in list(self.leases.values())
                if l["worker"] == worker_id
                and l["state"] == "active"]

    def worker_restarted(self, worker_id, now):
        rec = self.workers.get(worker_id)
        if rec is None:
            raise ModelError("unknown worker")
        rec["restarts"] += 1
        rec["last_heartbeat"] = None
        return [self._reclaim(l, "worker_restart")
                for l in list(self.leases.values())
                if l["worker"] == worker_id
                and l["state"] == "active"]

    def expire(self, now):
        stale = {w for w, r in self.workers.items()
                 if r["last_heartbeat"] is not None
                 and now - r["last_heartbeat"]
                 > self.heartbeat_timeout}
        out = []
        for lease in list(self.leases.values()):
            if lease["state"] != "active":
                continue
            if now > lease["deadline"]:
                out.append(self._reclaim(lease,
                                         "lease_expired"))
            elif lease["worker"] in stale:
                out.append(self._reclaim(lease,
                                         "worker_stale"))
        return out

    def steal(self, thief_id, now, ttl=30.0, min_tail=2):
        best = None
        for key in sorted(self.slices):
            for ch in self.slices[key]:
                if ch[2] != "leased":
                    continue
                lease = self.leases[ch[3]]
                if lease["worker"] == thief_id:
                    continue
                tail = (ch[1] - ch[0]) - ch[4]
                if tail >= 2 * min_tail and (
                        best is None or tail > best[0]):
                    best = (tail, key, ch, lease)
        if best is None:
            return None
        _t, key, ch, victim = best
        size = ch[1] - ch[0]
        tail_lo = ch[0] + ch[4] + (size - ch[4]) // 2
        stolen = [tail_lo, ch[1], "pending", None, 0, 0]
        ch[1] = tail_lo
        victim["hi"] = tail_lo
        self.token_seq += 1
        victim["token"] = self.token_seq
        chunks = self.slices[key]
        chunks.append(stolen)
        chunks.sort(key=lambda c: c[0])
        return self._issue(thief_id, key, stolen, now, ttl)

    def coordinator_restart(self):
        self.epoch += 1
        for lease in list(self.leases.values()):
            if lease["state"] == "active":
                self._reclaim(lease, "coordinator_restart")
        for rec in self.workers.values():
            rec["last_heartbeat"] = None

    # accounting ---------------------------------------------------
    def completed_intervals(self):
        out = []
        for key, chunks in self.slices.items():
            for ch in chunks:
                if ch[2] == "completed":
                    out.append((key, ch[0], ch[1]))
        return sorted(out)

    def accounting(self):
        unique = pending = leased = 0
        for chunks in self.slices.values():
            for ch in chunks:
                size = ch[1] - ch[0]
                if ch[2] == "completed":
                    unique += size
                elif ch[2] == "pending":
                    pending += size
                else:
                    leased += size
        return {
            "declared_total": self.declared_total(),
            "unique_coverage": unique,
            "actual_computations": self.actual,
            "repeated_computations": self.repeated,
            "duplicate_deliveries": self.duplicate_deliveries,
            "stale_reports": self.stale_reports,
            "not_holder_attempts": self.not_holder_attempts,
            "unknown_lease_reports":
                self.unknown_lease_reports,
            "reclaims": self.reclaims,
            "pending": pending, "leased": leased,
            "complete": unique == self.declared_total()
            and self.declared_total() > 0}
