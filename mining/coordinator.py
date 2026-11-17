#!/usr/bin/env python3
"""EXP-055: production wire protocol and persistent coordinator.

The EXP-035 work distribution design (research/sha256d/exp035/
WORK_DISTRIBUTION_DESIGN.md) built as a running system, per
roadmap F1 and portfolio NOVA-ER-0015:

  * a persistent coordinator process (this module, run as
    python3 -m mining.coordinator) holding the Work Lease
    Manager, the worker registry and the Candidate Queue;
  * a wire protocol for worker registration, leases,
    progress, completion and candidate hand-off: length
    prefixed frames (4-byte big-endian payload length, UTF-8
    JSON payload, 4-byte big-endian CRC32 of the payload).
    A frame that fails its checksum or length bound is
    discarded and counted, never absorbed (design section 9);
  * coordinator persistence as an append-only operation
    journal plus periodic atomic snapshots (temp file, fsync,
    os.replace, the EXP-038 pattern). Recovery loads the
    snapshot, replays the journal after it, then applies the
    design's restart rule: the epoch bumps, every outstanding
    lease is reclaimed, and workers must re-register.
    Candidate records keep the EXP-035 candidate journal
    (persist before acknowledge) and its recovery rules.

Semantics are the EXP-035 semantics, unchanged: slices are
(extranonce2 slot, counter) x version variant x ntime value
times a nonce range; leases carry unique ids and fencing
tokens from one monotonic counter; progress and completion
reports are classified OK, DUPLICATE, STALE, NOT_HOLDER or
UNKNOWN_LEASE and only a live holder report with the current
token credits anything; unique coverage grows only on
completion; reclaims move reported progress into
examined_before so re-examination is accounted as repeated
work; stealing shrinks the victim's chunk first and rotates
its token; the accounting identity
unique + pending + leased == declared holds at every
instant. The single-machine ResourceRegistry
(agent/intelligence/resources.py) remains the local
behaviour this generalises; nothing in the live mining
paths imports this module, and not deploying it is the
rollback.

The two EXP-043 prototype defects are carried in as fixes:

  F-A (prune the lease table): the lease store holds only
  ACTIVE leases, indexed per worker (self._active_by_worker),
  so the starvation check (_holds_lease) reads the worker's
  own active set instead of scanning every lease ever
  issued. Completed and dead lease identities survive only
  as compact tombstones (lease id -> holder, and a dead id
  set) sufficient to classify DUPLICATE and STALE reports.
  The event log is a bounded deque and is never snapshotted.
  F-B (bound snapshot cost): snapshot() serialises live
  state only (job, slices and chunks, active leases, worker
  registry, counters, compact tombstones), so its cost is
  proportional to live state, not to history.

Deadlines are coordinator-side: every operation carries the
caller's clock reading as an explicit field and the received
value is the only one that decides expiry (the design's skew
mitigation). Tests drive a simulated clock through the same
field; production workers pass wall time.

Scope line, binding: this build was exercised on one VM with
loopback and in-process workers only. Fleet activation is
owner-gated (roadmap F2); this module contacts no other
machine. Multi-machine coordination, real-network latency
and cross-machine scaling are UNVERIFIED (EXP-055 report).
"""

import copy
import json
import os
import socket
import struct
import sys
import threading
import time
import zlib
from collections import deque

MAX_FRAME = 1 << 20
EVENT_LOG_BOUND = 1024
SNAPSHOT_VERSION = 1


class LeaseError(Exception):
    pass


class ForeignFleetError(LeaseError):
    pass


class FrameError(Exception):
    pass


# ------------------------------------------------------------------
# Wire framing (design section 9)
# ------------------------------------------------------------------

def encode_frame(payload_obj):
    payload = json.dumps(payload_obj, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_FRAME:
        raise FrameError("payload exceeds frame bound")
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + payload \
        + struct.pack(">I", crc)


def decode_frame(buf):
    """Decode one frame from the front of buf. Returns
    (obj, bytes_consumed). Raises FrameError on a bad length
    or checksum; the caller discards and counts, never
    absorbs."""
    if len(buf) < 8:
        raise FrameError("short frame")
    (length,) = struct.unpack(">I", buf[:4])
    if length <= 0 or length > MAX_FRAME:
        raise FrameError("frame length out of bounds")
    if len(buf) < 4 + length + 4:
        raise FrameError("truncated frame")
    payload = buf[4:4 + length]
    (crc,) = struct.unpack(">I", buf[4 + length:8 + length])
    if zlib.crc32(payload) & 0xFFFFFFFF != crc:
        raise FrameError("frame checksum mismatch")
    return json.loads(payload.decode("utf-8")), 8 + length


# ------------------------------------------------------------------
# Candidate queue (EXP-035 semantics, integrated)
# ------------------------------------------------------------------

class CandidateQueue:
    """Deduplicating FIFO between workers and the verifier.
    Identity is the full header identity; persist before
    acknowledge when a journal path is set."""

    def __init__(self, journal_path=None):
        self.journal_path = journal_path
        self.pending = []
        self.seen = {}
        self.submitted = 0
        self.duplicates = 0
        self.verified = 0
        self.from_reclaimed_lease = 0
        self.stale_generation_dropped = 0
        self.classifications = {}
        self._fh = None
        if journal_path is not None:
            self._fh = open(journal_path, "a")

    @staticmethod
    def identity(rec):
        return (rec["job_id"], rec["generation"],
                rec["extranonce2"], rec["version"],
                rec["ntime"], rec["nonce"])

    def _journal(self, event, rec):
        if self._fh is None:
            return
        self._fh.write(json.dumps(
            {"event": event, "record": rec},
            sort_keys=True) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def submit(self, rec):
        self.submitted += 1
        key = self.identity(rec)
        if key in self.seen:
            self.duplicates += 1
            self._journal("duplicate", rec)
            return "DUPLICATE"
        self.seen[key] = rec
        self.pending.append(rec)
        self._journal("submit", rec)
        return "ACCEPTED"

    def drain(self, verifier, current_generation,
              lease_states=None):
        out = []
        pending, self.pending = self.pending, []
        for rec in pending:
            if rec["generation"] != current_generation:
                self.stale_generation_dropped += 1
                self._journal("stale_generation", rec)
                continue
            if lease_states is not None and \
                    lease_states.get(rec["lease_id"]) \
                    in ("reclaimed", "dead", "superseded"):
                self.from_reclaimed_lease += 1
            verdict = verifier(rec)
            self.verified += 1
            self.classifications[verdict] = \
                self.classifications.get(verdict, 0) + 1
            self._journal("verified",
                          {"identity": list(self.identity(rec)),
                           "verdict": verdict})
            out.append((rec, verdict))
        return out

    def stats(self):
        return {
            "submitted": self.submitted,
            "duplicates": self.duplicates,
            "verified": self.verified,
            "from_reclaimed_lease": self.from_reclaimed_lease,
            "stale_generation_dropped":
                self.stale_generation_dropped,
            "pending": len(self.pending),
            "classifications": dict(self.classifications)}

    def close(self):
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    @classmethod
    def recover(cls, journal_path):
        q = cls(journal_path=None)
        verified_keys = set()
        with open(journal_path) as fh:
            for line in fh:
                entry = json.loads(line)
                if entry["event"] == "submit":
                    rec = entry["record"]
                    q.seen[cls.identity(rec)] = rec
                    q.submitted += 1
                elif entry["event"] == "verified":
                    verified_keys.add(
                        tuple(entry["record"]["identity"]))
                elif entry["event"] == "duplicate":
                    q.duplicates += 1
        for key, rec in q.seen.items():
            if key not in verified_keys:
                q.pending.append(rec)
        q.journal_path = journal_path
        q._fh = open(journal_path, "a")
        return q


# ------------------------------------------------------------------
# Coordinator core (EXP-035 lease manager semantics, F-A/F-B fixes)
# ------------------------------------------------------------------

class CoordinatorCore:
    def __init__(self, fleet_id, heartbeat_timeout=10.0,
                 starvation_window=10.0, candidate_journal=None):
        self.fleet_id = fleet_id
        self.heartbeat_timeout = heartbeat_timeout
        self.starvation_window = starvation_window
        self.workers = {}
        self.job = None
        self.slices = []
        self._slice_by_key = {}
        # F-A: only ACTIVE leases live here.
        self.leases = {}
        self._active_by_worker = {}
        self._chunk_loc = {}       # lease_id -> chunk dict
        # Compact tombstones: completed lease_id -> holder;
        # dead (reclaimed or superseded) lease ids.
        self._completed_ids = {}
        self._dead_ids = set()
        self._lease_seq = 0
        self._token_seq = 0
        self.epoch = 0
        self.actual = 0
        self.repeated = 0
        self.duplicate_deliveries = 0
        self.stale_reports = 0
        self.not_holder_attempts = 0
        self.unknown_lease_reports = 0
        self.reclaims = 0
        self.reregistrations = 0
        self.bad_frames = 0
        self.events = deque(maxlen=EVENT_LOG_BOUND)
        self.queue = CandidateQueue(candidate_journal)

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
        return "OK"

    def stale_workers(self, now):
        return [w for w, r in self.workers.items()
                if r["last_heartbeat"] is not None
                and now - r["last_heartbeat"]
                > self.heartbeat_timeout]

    def worker_restarted(self, worker_id, now):
        rec = self.workers.get(worker_id)
        if rec is None:
            raise LeaseError("restart notice for unknown "
                             "worker %s" % worker_id)
        rec["restarts"] += 1
        rec["last_heartbeat"] = None
        out = []
        for lease in list(self.leases.values()):
            if lease["worker"] == worker_id:
                out.append(self._reclaim(lease,
                                         "worker_restart"))
        self.events.append(("worker_restart", worker_id))
        return out

    # -- job declaration ------------------------------------------
    def declare_job(self, job_id, generation, nonce_count,
                    chunk_size, n_slots, version_variants,
                    ntime_values, counters_per_slot=1):
        if self.job is not None:
            for lease in list(self.leases.values()):
                self._kill_lease(lease, "superseded")
            self.events.append(("job_superseded",
                                self.job["job_id"]))
        self.job = {"job_id": job_id,
                    "generation": generation,
                    "nonce_count": nonce_count,
                    "chunk_size": chunk_size}
        self.slices = []
        self._slice_by_key = {}
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
                        sl = {
                            "slot": slot,
                            "counter": counter,
                            "extranonce2": (slot << 25)
                            | counter,
                            "version": version,
                            "ntime": ntime,
                            "chunks": chunks}
                        self.slices.append(sl)
                        self._slice_by_key[
                            (slot, counter, version,
                             ntime)] = sl
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

    # -- lease bookkeeping (F-A) -----------------------------------
    def _index_add(self, lease):
        self._active_by_worker.setdefault(
            lease["worker"], set()).add(lease["lease_id"])

    def _index_drop(self, lease):
        s = self._active_by_worker.get(lease["worker"])
        if s is not None:
            s.discard(lease["lease_id"])
            if not s:
                del self._active_by_worker[lease["worker"]]

    def _holds_lease(self, worker_id):
        # F-A: the worker's own active set, never a history scan.
        return bool(self._active_by_worker.get(worker_id))

    def _kill_lease(self, lease, state):
        """Remove an active lease from the live store, leaving
        only its compact tombstone."""
        self._index_drop(lease)
        self._chunk_loc.pop(lease["lease_id"], None)
        del self.leases[lease["lease_id"]]
        if state == "completed":
            self._completed_ids[lease["lease_id"]] = \
                lease["worker"]
        else:
            self._dead_ids.add(lease["lease_id"])

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
        self._index_add(lease)
        self._chunk_loc[lease["lease_id"]] = ch
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

    def lease_info(self, lease_id):
        """Registry reconciliation query (design section 4):
        the state of one lease identity, live or tombstoned."""
        lease = self.leases.get(lease_id)
        if lease is not None:
            return dict(lease)
        if lease_id in self._completed_ids:
            return {"lease_id": lease_id, "state": "completed",
                    "worker": self._completed_ids[lease_id]}
        if lease_id in self._dead_ids:
            return {"lease_id": lease_id, "state": "reclaimed"}
        return {"lease_id": lease_id, "state": "unknown"}

    def _check_report(self, worker_id, lease_id, token):
        lease = self.leases.get(lease_id)
        if lease is None:
            if lease_id in self._completed_ids:
                self.duplicate_deliveries += 1
                return None, "DUPLICATE"
            if lease_id in self._dead_ids:
                self.stale_reports += 1
                return None, "STALE"
            self.unknown_lease_reports += 1
            return None, "UNKNOWN_LEASE"
        if lease["token"] != token \
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
        ch = self._chunk_loc[lease_id]
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
        ch = self._chunk_loc[lease_id]
        size = ch["hi"] - ch["lo"]
        self.actual += size - ch["reported"]
        ch["reported"] = size
        ch["state"] = "completed"
        ch["lease_id"] = None
        self._kill_lease(lease, "completed")
        self.events.append(("complete", lease_id,
                            worker_id))
        return "OK"

    # -- reclaim, expiry, stealing --------------------------------
    def _reclaim(self, lease, reason):
        ch = self._chunk_loc.get(lease["lease_id"])
        if ch is not None and ch["state"] == "leased":
            ch["examined_before"] = ch["reported"]
            ch["reported"] = 0
            ch["state"] = "pending"
            ch["lease_id"] = None
        self._kill_lease(lease, "reclaimed")
        self.reclaims += 1
        self.events.append(("reclaim", lease["lease_id"],
                            reason))
        return lease["lease_id"]

    def fail_worker(self, worker_id):
        out = []
        for lease in list(self.leases.values()):
            if lease["worker"] == worker_id:
                out.append(self._reclaim(lease,
                                         "worker_failed"))
        return out

    def expire(self, now):
        stale = set(self.stale_workers(now))
        out = []
        for lease in list(self.leases.values()):
            if now > lease["deadline"]:
                out.append(self._reclaim(lease,
                                         "lease_expired"))
            elif lease["worker"] in stale:
                out.append(self._reclaim(
                    lease, "worker_stale"))
        return out

    def steal(self, thief_id, now, ttl=30.0, min_tail=2):
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
        victim["token"] = self._token_seq
        sl["chunks"].append(stolen)
        sl["chunks"].sort(key=lambda c: c["lo"])
        self.events.append(("steal", thief_id,
                            victim["lease_id"], tail_lo))
        return self._new_lease(thief_id, sl, stolen, now,
                               ttl)

    # -- snapshot / restore (F-B) ----------------------------------
    def snapshot(self):
        """Live state only: no event log, no lease history
        beyond compact tombstones (F-B)."""
        return {
            "version": SNAPSHOT_VERSION,
            "fleet_id": self.fleet_id,
            "heartbeat_timeout": self.heartbeat_timeout,
            "starvation_window": self.starvation_window,
            "job": copy.deepcopy(self.job),
            "slices": copy.deepcopy(self.slices),
            "leases": copy.deepcopy(self.leases),
            "workers": copy.deepcopy(self.workers),
            "completed_ids": dict(self._completed_ids),
            "dead_ids": sorted(self._dead_ids),
            "lease_seq": self._lease_seq,
            "token_seq": self._token_seq,
            "epoch": self.epoch,
            "actual": self.actual,
            "repeated": self.repeated,
            "duplicate_deliveries": self.duplicate_deliveries,
            "stale_reports": self.stale_reports,
            "not_holder_attempts": self.not_holder_attempts,
            "unknown_lease_reports": self.unknown_lease_reports,
            "reclaims": self.reclaims,
            "reregistrations": self.reregistrations,
            "queue_stats": self.queue.stats(),
            "queue_seen": [list(k) for k in self.queue.seen],
            "queue_pending": copy.deepcopy(self.queue.pending),
        }

    def _load_state(self, snap):
        self.fleet_id = snap["fleet_id"]
        self.heartbeat_timeout = snap.get(
            "heartbeat_timeout", self.heartbeat_timeout)
        self.starvation_window = snap.get(
            "starvation_window", self.starvation_window)
        self.job = snap["job"]
        self.slices = snap["slices"]
        self._slice_by_key = {
            (sl["slot"], sl["counter"], sl["version"],
             sl["ntime"]): sl for sl in self.slices}
        self.leases = snap["leases"]
        self.workers = snap["workers"]
        self._completed_ids = dict(snap.get("completed_ids",
                                            {}))
        self._dead_ids = set(snap.get("dead_ids", []))
        self._lease_seq = snap["lease_seq"]
        self._token_seq = snap["token_seq"]
        self.epoch = snap["epoch"]
        self.actual = snap["actual"]
        self.repeated = snap["repeated"]
        self.duplicate_deliveries = \
            snap["duplicate_deliveries"]
        self.stale_reports = snap["stale_reports"]
        self.not_holder_attempts = snap["not_holder_attempts"]
        self.unknown_lease_reports = \
            snap["unknown_lease_reports"]
        self.reclaims = snap["reclaims"]
        self.reregistrations = snap["reregistrations"]
        self._active_by_worker = {}
        self._chunk_loc = {}
        for lease in self.leases.values():
            lease["slice"] = tuple(lease["slice"])
            self._index_add(lease)
            sl = self._slice_by_key.get(lease["slice"])
            if sl is not None:
                for ch in sl["chunks"]:
                    if ch["lease_id"] == lease["lease_id"]:
                        self._chunk_loc[lease["lease_id"]] = ch
                        break
        for rec in self.workers.values():
            rec["slot_by_job"] = dict(rec.get("slot_by_job",
                                              {}))
        qs = snap.get("queue_stats") or {}
        self.queue.submitted = qs.get("submitted", 0)
        self.queue.duplicates = qs.get("duplicates", 0)
        self.queue.verified = qs.get("verified", 0)
        self.queue.from_reclaimed_lease = qs.get(
            "from_reclaimed_lease", 0)
        self.queue.stale_generation_dropped = qs.get(
            "stale_generation_dropped", 0)
        self.queue.classifications = dict(
            qs.get("classifications", {}))
        self.queue.seen = {
            tuple(k): None for k in snap.get("queue_seen", [])}
        self.queue.pending = snap.get("queue_pending", [])
        for rec in self.queue.pending:
            self.queue.seen[CandidateQueue.identity(rec)] = rec
        for k, rec in list(self.queue.seen.items()):
            if rec is None:
                del self.queue.seen[k]
                self.queue.seen[k] = {
                    "job_id": k[0], "generation": k[1],
                    "extranonce2": k[2], "version": k[3],
                    "ntime": k[4], "nonce": k[5],
                    "lease_id": "unknown", "worker_id": "unknown"}

    def apply_restart_rule(self):
        """Design section 6 rule 4: leases never survive a
        coordinator restart; the epoch bumps so every
        pre-restart token is dead; workers re-register."""
        self.epoch += 1
        for lease in list(self.leases.values()):
            self._reclaim(lease, "coordinator_restart")
        for rec in self.workers.values():
            rec["last_heartbeat"] = None
        self.events.append(("restore", self.epoch))

    @classmethod
    def restore(cls, snap, candidate_journal=None):
        obj = cls(snap["fleet_id"],
                  candidate_journal=candidate_journal)
        obj._load_state(snap)
        obj.apply_restart_rule()
        return obj

    # -- accounting --------------------------------------------------
    def completed_intervals(self):
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
        for sl in self.slices:
            ivs = sorted((c["lo"], c["hi"])
                         for c in sl["chunks"])
            assert ivs[0][0] == 0, ivs
            assert ivs[-1][1] == self.job["nonce_count"], ivs
            for (a_lo, a_hi), (b_lo, _b) in zip(ivs,
                                                ivs[1:]):
                assert a_hi == b_lo, ("gap or overlap", ivs)
        return True


# ------------------------------------------------------------------
# Persistence: operation journal + atomic snapshots
# ------------------------------------------------------------------

# Operations replayed from the journal after a snapshot. Each
# entry is the wire message itself (deterministic given its
# explicit clock field), so replay re-executes dispatch.
JOURNALED_OPS = {
    "register", "heartbeat", "declare_job", "lease",
    "progress", "complete", "steal", "expire",
    "worker_restarted", "fail_worker", "candidate_submit",
    "candidate_drain",
}


class CoordinatorServer:
    """One coordinator: core + journal + snapshots + dispatch.

    The same handle_frame bytes path serves the TCP listener
    and the in-process protocol transport used by the EXP-055
    campaign, so every test operation passes through frame
    encode, checksum verification and decode.
    """

    def __init__(self, fleet_id, state_dir=None,
                 heartbeat_timeout=10.0, starvation_window=10.0,
                 verifier=None):
        self.state_dir = state_dir
        self._lock = threading.Lock()
        self._seq = 0
        self._journal_fh = None
        cand_journal = None
        snap = None
        journal_tail = []
        if state_dir is not None:
            os.makedirs(state_dir, exist_ok=True)
            cand_journal = os.path.join(
                state_dir, "candidate_journal.jsonl")
            snap_path = os.path.join(state_dir,
                                     "snapshot.json")
            if os.path.exists(snap_path):
                with open(snap_path) as fh:
                    blob = json.load(fh)
                snap = blob["state"]
                self._seq = blob["seq"]
            jpath = os.path.join(state_dir, "journal.jsonl")
            if os.path.exists(jpath):
                with open(jpath) as fh:
                    for line in fh:
                        entry = json.loads(line)
                        if entry["seq"] > self._seq:
                            journal_tail.append(entry)
            self._journal_fh = open(jpath, "a")
        if snap is not None:
            # Load the snapshot state WITHOUT the restart
            # rule: the journal tail after the snapshot was
            # issued by the live system (workers registered,
            # tokens live) and must replay against that
            # state. The restart rule is applied once,
            # after replay, to the fully rebuilt state.
            self.core = CoordinatorCore(
                snap["fleet_id"],
                heartbeat_timeout=heartbeat_timeout,
                starvation_window=starvation_window,
                candidate_journal=None)
            self.core._load_state(snap)
            # Candidate state is recovered from its own
            # journal (P6), not from the snapshot copy.
            if cand_journal and os.path.exists(cand_journal):
                self.core.queue = CandidateQueue.recover(
                    cand_journal)
            elif cand_journal:
                self.core.queue = CandidateQueue(cand_journal)
        else:
            self.core = CoordinatorCore(
                fleet_id,
                heartbeat_timeout=heartbeat_timeout,
                starvation_window=starvation_window,
                candidate_journal=cand_journal)
            if cand_journal and os.path.exists(cand_journal) \
                    and os.path.getsize(cand_journal) > 0:
                self.core.queue.close()
                self.core.queue = CandidateQueue.recover(
                    cand_journal)
        self.verifier = verifier or (lambda rec: "share")
        # Replay the journal tail deterministically, then the
        # restart rule applies once to the rebuilt state.
        replayed = 0
        for entry in journal_tail:
            self._seq = entry["seq"]
            if entry["msg"].get("type") in (
                    "candidate_submit", "candidate_drain"):
                # Candidate state is owned by the candidate
                # journal and was already recovered from it
                # above; re-executing these would double
                # count submissions and re-run verification.
                continue
            self._dispatch(entry["msg"], journal=False)
            replayed += 1
        if snap is not None or journal_tail:
            # Recovery is a coordinator restart: the rule
            # applies once to the fully rebuilt state (epoch
            # bumps, every outstanding lease is reclaimed,
            # workers must re-register). Leases issued
            # during replay die here with the rest; their
            # completions, being journaled before the crash,
            # were already credited during replay.
            self.core.apply_restart_rule()
        self.replayed_ops = replayed

    # -- persistence -------------------------------------------
    def _journal(self, msg):
        if self._journal_fh is None:
            return
        self._seq += 1
        self._journal_fh.write(json.dumps(
            {"seq": self._seq, "msg": msg},
            sort_keys=True) + "\n")
        self._journal_fh.flush()
        os.fsync(self._journal_fh.fileno())

    def write_snapshot(self):
        if self.state_dir is None:
            return None
        blob = {"seq": self._seq, "state": self.core.snapshot()}
        path = os.path.join(self.state_dir, "snapshot.json")
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(blob, fh, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        try:
            dfd = os.open(self.state_dir, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass
        return path

    def close(self):
        # Clean shutdown records a snapshot, so the next
        # start recovers from it with the journal tail empty
        # and the epoch monotonic across restarts. A crash
        # (no close) recovers from the last snapshot plus
        # the journal tail instead; Gate 5 exercises both.
        if self.state_dir is not None:
            try:
                self.write_snapshot()
            except Exception:
                pass
        if self._journal_fh is not None:
            self._journal_fh.close()
            self._journal_fh = None
        self.core.queue.close()

    # -- dispatch ------------------------------------------------
    def _dispatch(self, msg, journal=True):
        op = msg.get("type")
        core = self.core
        try:
            if op == "ping":
                return {"ok": True, "result": "PONG",
                        "epoch": core.epoch}
            if op == "register":
                r = core.register_worker(
                    msg["worker_id"], msg["fleet_id"],
                    msg["now"])
                out = {"ok": True, "result": r}
            elif op == "heartbeat":
                core.heartbeat(msg["worker_id"], msg["now"],
                               msg.get("rate"))
                out = {"ok": True, "result": "OK"}
            elif op == "declare_job":
                n = core.declare_job(
                    msg["job_id"], msg["generation"],
                    msg["nonce_count"], msg["chunk_size"],
                    msg["n_slots"], msg["version_variants"],
                    msg["ntime_values"],
                    msg.get("counters_per_slot", 1))
                out = {"ok": True, "result": n}
            elif op == "lease":
                got = core.lease(msg["worker_id"], msg["now"],
                                 msg.get("ttl", 30.0))
                out = {"ok": True, "result": got}
            elif op == "lease_info":
                out = {"ok": True,
                       "result": core.lease_info(
                           msg["lease_id"])}
            elif op == "progress":
                r = core.progress(
                    msg["worker_id"], msg["lease_id"],
                    msg["token"], msg["examined"])
                out = {"ok": True, "result": r}
            elif op == "complete":
                r = core.complete(
                    msg["worker_id"], msg["lease_id"],
                    msg["token"])
                out = {"ok": True, "result": r}
            elif op == "steal":
                got = core.steal(msg["worker_id"], msg["now"],
                                 msg.get("ttl", 30.0),
                                 msg.get("min_tail", 2))
                out = {"ok": True, "result": got}
            elif op == "expire":
                out = {"ok": True,
                       "result": core.expire(msg["now"])}
            elif op == "worker_restarted":
                out = {"ok": True,
                       "result": core.worker_restarted(
                           msg["worker_id"], msg["now"])}
            elif op == "fail_worker":
                out = {"ok": True,
                       "result": core.fail_worker(
                           msg["worker_id"])}
            elif op == "candidate_submit":
                r = core.queue.submit(msg["record"])
                out = {"ok": True, "result": r}
            elif op == "candidate_drain":
                states = {lid: core.lease_info(lid)["state"]
                          for lid in
                          {rec["lease_id"]
                           for rec in core.queue.pending}}
                drained = core.queue.drain(
                    self.verifier,
                    core.job["generation"] if core.job else -1,
                    lease_states=states)
                out = {"ok": True, "result": [
                    {"record": rec, "verdict": verdict}
                    for rec, verdict in drained]}
            elif op == "accounting":
                out = {"ok": True, "result": core.accounting()}
            elif op == "completed_intervals":
                out = {"ok": True, "result": [
                    [list(k), lo, hi] for k, lo, hi
                    in core.completed_intervals()]}
            elif op == "queue_stats":
                out = {"ok": True,
                       "result": core.queue.stats()}
            elif op == "partition_check":
                out = {"ok": True,
                       "result":
                           core.assert_partition_invariant()}
            elif op == "restart":
                # In-place coordinator restart (snapshot and
                # restore semantics, no disk): used by the
                # campaign; Gate 5 uses a real state directory.
                snap = core.snapshot()
                cand = core.queue
                new = CoordinatorCore.restore(snap)
                new.queue = cand
                self.core = new
                out = {"ok": True, "result": "RESTARTED",
                       "epoch": new.epoch}
            elif op == "snapshot":
                self.write_snapshot()
                out = {"ok": True, "result": "SNAPSHOT"}
            elif op == "stats":
                out = {"ok": True, "result": {
                    "bad_frames": core.bad_frames,
                    "active_leases": len(core.leases),
                    "completed_tombstones":
                        len(core._completed_ids),
                    "dead_tombstones": len(core._dead_ids),
                    "epoch": core.epoch,
                    "journal_seq": self._seq}}
            else:
                out = {"ok": False,
                       "error": "unknown op %r" % (op,)}
        except ForeignFleetError as exc:
            out = {"ok": False, "error": "FOREIGN_FLEET",
                   "detail": str(exc)}
        except LeaseError as exc:
            out = {"ok": False, "error": "LEASE_ERROR",
                   "detail": str(exc)}
        except (KeyError, TypeError, ValueError) as exc:
            out = {"ok": False, "error": "BAD_REQUEST",
                   "detail": "%s: %s" % (type(exc).__name__,
                                          exc)}
        if journal and op in JOURNALED_OPS and out.get("ok"):
            self._journal(msg)
        return out

    def handle_frame(self, frame_bytes):
        """One framed request in, one framed response out.
        A frame that fails its checksum is discarded and
        counted, never absorbed: the response is a framed
        BAD_FRAME error and no dispatch happens."""
        with self._lock:
            try:
                msg, _used = decode_frame(frame_bytes)
            except FrameError as exc:
                self.core.bad_frames += 1
                return encode_frame(
                    {"ok": False, "error": "BAD_FRAME",
                     "detail": str(exc)})
            return encode_frame(self._dispatch(msg))

    def handle_message(self, msg):
        with self._lock:
            return self._dispatch(msg)

    # -- TCP serving ----------------------------------------------
    def serve(self, host, port):
        srv = socket.socket(socket.AF_INET,
                            socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET,
                       socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(64)
        self._tcp = srv
        self.port = srv.getsockname()[1]
        threads = []
        try:
            while True:
                conn, _addr = srv.accept()
                t = threading.Thread(
                    target=self._serve_conn, args=(conn,),
                    daemon=True)
                t.start()
                threads.append(t)
        except (KeyboardInterrupt, OSError):
            pass
        finally:
            srv.close()

    def _serve_conn(self, conn):
        buf = b""
        with conn:
            while True:
                try:
                    data = conn.recv(65536)
                except OSError:
                    return
                if not data:
                    return
                buf += data
                while len(buf) >= 4:
                    (length,) = struct.unpack(">I", buf[:4])
                    if length <= 0 or length > MAX_FRAME:
                        self.core.bad_frames += 1
                        conn.sendall(encode_frame(
                            {"ok": False,
                             "error": "BAD_FRAME",
                             "detail": "length bound"}))
                        return
                    if len(buf) < 8 + length:
                        break
                    frame, buf = buf[:8 + length], \
                        buf[8 + length:]
                    conn.sendall(self.handle_frame(frame))


class CoordinatorClient:
    """Worker-side client. transport is "tcp" (host/port) or
    a CoordinatorServer instance (in-process protocol
    transport: frames still encode, checksum and decode)."""

    def __init__(self, server=None, host=None, port=None):
        self.server = server
        self.host = host
        self.port = port
        self._sock = None
        if server is None:
            self._sock = socket.create_connection((host, port))
            self._sock.settimeout(120)

    def call(self, msg):
        frame = encode_frame(msg)
        if self.server is not None:
            resp_frame = self.server.handle_frame(frame)
            resp, _ = decode_frame(resp_frame)
            return resp
        self._sock.sendall(frame)
        buf = b""
        while len(buf) < 4:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise ConnectionError("coordinator closed")
            buf += chunk
        (length,) = struct.unpack(">I", buf[:4])
        while len(buf) < 8 + length:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise ConnectionError("coordinator closed")
            buf += chunk
        resp, _ = decode_frame(buf[:8 + length])
        return resp

    def call_raw(self, frame_bytes):
        """Send raw bytes (wire-integrity tests)."""
        if self.server is not None:
            resp, _ = decode_frame(
                self.server.handle_frame(frame_bytes))
            return resp
        self._sock.sendall(frame_bytes)
        buf = self._sock.recv(65536)
        resp, _ = decode_frame(buf)
        return resp

    def close(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="mining.coordinator",
        description="EXP-055 persistent coordinator (F1).")
    ap.add_argument("--fleet", default="nova-fleet")
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--heartbeat-timeout", type=float,
                    default=10.0)
    ap.add_argument("--starvation-window", type=float,
                    default=10.0)
    args = ap.parse_args(argv)
    server = CoordinatorServer(
        args.fleet, state_dir=args.state_dir,
        heartbeat_timeout=args.heartbeat_timeout,
        starvation_window=args.starvation_window)
    print("coordinator up: fleet=%s state_dir=%s replayed=%d "
          "epoch=%d" % (args.fleet, args.state_dir,
                        server.replayed_ops,
                        server.core.epoch), flush=True)
    try:
        server.serve(args.host, args.port)
    finally:
        server.write_snapshot()
        server.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
