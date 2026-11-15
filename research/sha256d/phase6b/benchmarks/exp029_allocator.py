#!/usr/bin/env python3
"""EXP-029 range allocator prototype (research only).

A coordinator-side allocator over one declared nonce
range [start, start+count) for one template (job_id).
It is the testable core of EXP029_DISTRIBUTED_EXECUTION
.md. It performs no hashing itself; workers lease
chunks, report progress, and complete chunks.

Design rules (the document's standing separations):
  * The declared range is partitioned into fixed chunks
    at construction. A chunk is in exactly one state:
    pending, leased (to one worker), or completed.
    Leases are exclusive: a chunk is never leased to two
    workers at once, so two workers never legitimately
    hold the same nonces.
  * complete() is idempotent per chunk: a duplicate
    delivery returns DUPLICATE and changes no coverage.
  * Worker death: fail_worker() requeues the worker's
    leased chunks. Progress the dead worker had reported
    (progress() calls) is work actually executed on
    nonces that a later worker will examine again, so it
    is moved into repeated_computations when the chunk
    is re-leased, and the re-execution itself is counted
    in actual_computations. Unique coverage only ever
    grows by completed chunk sizes, never by attempts.
  * Work stealing: steal() splits the unreported tail
    of the largest leased chunk when that tail is at
    least twice the minimum steal size. The original
    lease shrinks FIRST (recorded), then the tail is
    leased to the thief, so the partition stays disjoint
    at every instant.
  * Coordinator restart: snapshot() returns a JSON-safe
    state; restore() rebuilds it. Leases do not survive
    a restart (workers are presumed dead or re-register),
    so leased chunks return to pending and their
    reported progress is accounted as repeated on
    re-lease, exactly as in fail_worker().
  * Template propagation: a new job_id invalidates the
    whole allocator. Work on a stale template is never
    counted toward the new job's coverage; the caller
    constructs a fresh allocator per template (see the
    document, section on tip change).

Accounting (returned by accounting()):
  unique_coverage: sum of completed chunk sizes.
  actual_computations: every reported examination,
    including repeats (progress + completions).
  repeated_computations: examinations of nonces that
    had already been examined (re-leased chunk progress
    from a dead or restarted lease).
  verification_computations: always 0 here; candidate
    verification happens in the engine layer and is
    reported there, never as throughput.
  candidate_submissions: counted by the caller layer,
    0 here.
  Invariant: unique_coverage + pending + leased ==
  declared count, and completed chunks are pairwise
  disjoint by construction (asserted in tests over the
  recorded intervals).
"""

import json


class AllocatorError(Exception):
    pass


class RangeAllocator:
    def __init__(self, job_id, start, count, chunk_size):
        if count <= 0 or chunk_size <= 0:
            raise AllocatorError("count and chunk_size > 0")
        if start < 0 or start + count > (1 << 32):
            raise AllocatorError("range outside nonce space")
        self.job_id = job_id
        self.start = start
        self.count = count
        self.chunk_size = chunk_size
        self.chunks = []  # dicts: lo, hi, state, worker,
        # reported (max progress offset reported under the
        # current lease), examined_before (nonces of this
        # chunk examined under earlier leases)
        lo = start
        while lo < start + count:
            hi = min(lo + chunk_size, start + count)
            self.chunks.append({
                "lo": lo, "hi": hi, "state": "pending",
                "worker": None, "reported": 0,
                "examined_before": 0})
            lo = hi
        self.actual = 0
        self.repeated = 0
        self.duplicate_deliveries = 0
        self.heartbeats = {}  # worker -> (ts, rate)
        self.events = []

    # -- leasing -------------------------------------------------
    def lease(self, worker):
        for ch in self.chunks:
            if ch["state"] == "pending":
                ch["state"] = "leased"
                ch["worker"] = worker
                ch["reported"] = 0
                if ch["examined_before"]:
                    # Re-execution of already-examined
                    # nonces: count the earlier examinations
                    # as repeated at re-lease time; the new
                    # examinations add to actual as reported.
                    self.repeated += ch["examined_before"]
                    ch["examined_before"] = 0
                self.events.append(("lease", worker,
                                    ch["lo"], ch["hi"]))
                return (ch["lo"], ch["hi"])
        return None

    def _chunk_of(self, worker, lo):
        for ch in self.chunks:
            if ch["lo"] == lo and ch["state"] == "leased" \
                    and ch["worker"] == worker:
                return ch
        return None

    def progress(self, worker, lo, examined):
        """Worker reports it has examined `examined`
        nonces of its leased chunk (cumulative)."""
        ch = self._chunk_of(worker, lo)
        if ch is None:
            raise AllocatorError("progress for unheld chunk")
        if not (ch["reported"] <= examined <= ch["hi"] - ch["lo"]):
            raise AllocatorError("progress out of bounds")
        self.actual += examined - ch["reported"]
        ch["reported"] = examined

    def complete(self, worker, lo):
        ch = None
        for c in self.chunks:
            if c["lo"] == lo:
                ch = c
                break
        if ch is None:
            raise AllocatorError("unknown chunk")
        if ch["state"] == "completed":
            self.duplicate_deliveries += 1
            self.events.append(("duplicate", worker, lo))
            return "DUPLICATE"
        if ch["state"] != "leased" or ch["worker"] != worker:
            raise AllocatorError("complete by non-holder")
        size = ch["hi"] - ch["lo"]
        self.actual += size - ch["reported"]
        ch["reported"] = size
        ch["state"] = "completed"
        ch["worker"] = None
        self.events.append(("complete", worker, lo))
        return "OK"

    # -- failure and stealing ------------------------------------
    def fail_worker(self, worker):
        requeued = []
        for ch in self.chunks:
            if ch["state"] == "leased" and ch["worker"] == worker:
                ch["examined_before"] = ch["reported"]
                ch["reported"] = 0
                ch["state"] = "pending"
                ch["worker"] = None
                requeued.append((ch["lo"], ch["hi"]))
        self.heartbeats.pop(worker, None)
        self.events.append(("fail", worker, tuple(requeued)))
        return requeued

    def steal(self, thief, min_tail=2):
        """Split the unreported tail of the largest leased
        chunk. Returns the stolen (lo, hi) or None."""
        best = None
        for ch in self.chunks:
            if ch["state"] != "leased" or ch["worker"] == thief:
                continue
            tail = (ch["hi"] - ch["lo"]) - ch["reported"]
            if tail >= 2 * min_tail and (
                    best is None or tail > best[0]):
                best = (tail, ch)
        if best is None:
            return None
        ch = best[1]
        tail_lo = ch["lo"] + ch["reported"] + \
            ((ch["hi"] - ch["lo"] - ch["reported"]) // 2)
        stolen = {"lo": tail_lo, "hi": ch["hi"],
                  "state": "leased", "worker": thief,
                  "reported": 0, "examined_before": 0}
        ch["hi"] = tail_lo
        self.chunks.append(stolen)
        self.chunks.sort(key=lambda c: c["lo"])
        self.events.append(("steal", thief, tail_lo,
                            stolen["hi"]))
        return (tail_lo, stolen["hi"])

    # -- restart ---------------------------------------------------
    def snapshot(self):
        return json.loads(json.dumps({
            "job_id": self.job_id, "start": self.start,
            "count": self.count,
            "chunk_size": self.chunk_size,
            "chunks": self.chunks, "actual": self.actual,
            "repeated": self.repeated,
            "duplicate_deliveries": self.duplicate_deliveries}))

    @classmethod
    def restore(cls, snap):
        obj = cls.__new__(cls)
        obj.job_id = snap["job_id"]
        obj.start = snap["start"]
        obj.count = snap["count"]
        obj.chunk_size = snap["chunk_size"]
        obj.chunks = snap["chunks"]
        obj.actual = snap["actual"]
        obj.repeated = snap["repeated"]
        obj.duplicate_deliveries = snap["duplicate_deliveries"]
        obj.heartbeats = {}
        obj.events = [("restore",)]
        for ch in obj.chunks:
            if ch["state"] == "leased":
                ch["examined_before"] = ch["reported"]
                ch["reported"] = 0
                ch["state"] = "pending"
                ch["worker"] = None
        return obj

    # -- telemetry -------------------------------------------------
    def heartbeat(self, worker, ts, rate):
        self.heartbeats[worker] = (ts, rate)

    def stale_workers(self, now, timeout_s):
        return [w for w, (ts, _r) in self.heartbeats.items()
                if now - ts > timeout_s]

    # -- accounting --------------------------------------------------
    def completed_intervals(self):
        return sorted((c["lo"], c["hi"]) for c in self.chunks
                      if c["state"] == "completed")

    def accounting(self):
        unique = sum(c["hi"] - c["lo"] for c in self.chunks
                     if c["state"] == "completed")
        pending = sum(c["hi"] - c["lo"] for c in self.chunks
                      if c["state"] == "pending")
        leased = sum(c["hi"] - c["lo"] for c in self.chunks
                     if c["state"] == "leased")
        return {
            "job_id": self.job_id,
            "declared_range": [self.start, self.start + self.count],
            "unique_coverage": unique,
            "actual_computations": self.actual,
            "repeated_computations": self.repeated,
            "verification_computations": 0,
            "candidate_submissions": 0,
            "duplicate_deliveries": self.duplicate_deliveries,
            "pending": pending, "leased": leased,
            "complete": unique == self.count}

    def assert_partition_invariant(self):
        ivs = sorted((c["lo"], c["hi"]) for c in self.chunks)
        assert ivs[0][0] == self.start, ivs
        assert ivs[-1][1] == self.start + self.count, ivs
        for (a_lo, a_hi), (b_lo, _b_hi) in zip(ivs, ivs[1:]):
            assert a_hi == b_lo, (ivs, "gap or overlap")
        return True
