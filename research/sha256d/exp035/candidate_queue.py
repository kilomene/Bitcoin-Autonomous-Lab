#!/usr/bin/env python3
"""EXP-035 candidate queue prototype (research only).

The Candidate Queue (directive section 12, component 11):
the buffer between workers finding candidate headers and
the EXP-036 Exact Candidate Verifier judging them. Today
production handles candidates synchronously inline, so a
crash between discovery and submission loses the
candidate without a trace (gap analysis, component 11).
The production design (WORK_DISTRIBUTION_DESIGN.md)
persists every accepted record to an append-only journal
before acknowledgement; this prototype implements the
queue semantics and the journal, with the verifier
injected as a callback so tests can count exactly how
many times verification runs.

Semantics:
  * Identity is the full header identity: (job_id,
    generation, extranonce2, version, ntime, nonce).
    This replaces the Qaxe 32-entry (nonce, version) ring
    (matrix M12, weakness W2): duplicates are detected
    against the whole queue history, not a small ring,
    and a duplicate is counted, never verified twice and
    never credited twice.
  * A record carries its lease_id for attribution.
    Lease state does NOT decide verification: validity is
    a property of the header, not of the lease. A
    candidate found under a lease that was later
    reclaimed is still verified once, and attributed as
    from_reclaimed_lease so the accounting stays honest.
  * Generation is checked at drain time: a candidate
    whose job generation is no longer current is dropped
    as stale and never reaches the verifier, because its
    template is no longer the chain tip's work.
  * Order is FIFO. The verifier callback returns a
    classification string (in production, the verdict of
    mining/candidate_verify.py verify_candidate); the
    queue tallies classifications without interpreting
    them.
"""

import json
import os


class CandidateQueue:
    def __init__(self, journal_path=None):
        self.journal_path = journal_path
        self.pending = []          # FIFO of records
        self.seen = {}             # identity -> first record
        self.submitted = 0
        self.duplicates = 0
        self.verified = 0
        self.from_reclaimed_lease = 0
        self.stale_generation_dropped = 0
        self.classifications = {}

    @staticmethod
    def identity(rec):
        return (rec["job_id"], rec["generation"],
                rec["extranonce2"], rec["version"],
                rec["ntime"], rec["nonce"])

    def _journal(self, event, rec):
        if self.journal_path is None:
            return
        line = json.dumps({"event": event, "record": rec},
                          sort_keys=True)
        with open(self.journal_path, "a") as fh:
            fh.write(line + "\n")

    def submit(self, rec):
        """Returns ACCEPTED or DUPLICATE."""
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
        """Verify every pending record once, in order.
        lease_states: optional lease_id -> state map used
        only for attribution. Returns the list of
        (record, classification) actually verified."""
        out = []
        pending, self.pending = self.pending, []
        for rec in pending:
            if rec["generation"] != current_generation:
                self.stale_generation_dropped += 1
                self._journal("stale_generation", rec)
                continue
            if lease_states is not None and \
                    lease_states.get(rec["lease_id"]) \
                    == "reclaimed":
                self.from_reclaimed_lease += 1
            verdict = verifier(rec)
            self.verified += 1
            self.classifications[verdict] = \
                self.classifications.get(verdict, 0) + 1
            self._journal("verified",
                          {"identity": self.identity(rec),
                           "verdict": verdict})
            out.append((rec, verdict))
        return out

    def stats(self):
        return {
            "submitted": self.submitted,
            "duplicates": self.duplicates,
            "verified": self.verified,
            "from_reclaimed_lease":
                self.from_reclaimed_lease,
            "stale_generation_dropped":
                self.stale_generation_dropped,
            "pending": len(self.pending),
            "classifications": dict(self.classifications)}

    @classmethod
    def recover(cls, journal_path):
        """Rebuild queue state from the append-only
        journal after a crash: submitted-but-unverified
        records are pending again; verified records are
        seen (so a resubmission is a duplicate, never a
        second verification)."""
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
        return q
