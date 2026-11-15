"""Mining statistics engine (EXP-037).

One production home for the directive's section 10 categories.
Before this module the lab's counters were per-path fragments
sharing a vocabulary (ComputeEngine Task 003.9 stats, autopilot
heartbeat, solo server stats(), the agent store) with several
categories existing in exactly one path and some in none.

The rule that defines this engine, from directive section 10
and EXP-035 section 7: categories are tracked SEPARATELY and
are never added together. Backend hashes, unique coverage and
verification hashes overlap by construction (a verification
hash is a real hash computation; a repeated examination is a
real nonce position), so any grand total built from them
double-counts. snapshot() therefore returns each category as
its own number and deliberately has no combined total.

Counter-first (translation matrix M11, adopted): every number
here is a counter incremented by the code that did the work,
or a rate derived from such counters by WindowedRate. Nothing
is estimated from shares: share counts say how lucky the
search was, never how much work it did. Per-worker and
per-backend dimensions are first-class (M28): an aggregate
that hides one sick worker or backend is a defect, so every
record() call may carry a worker and/or backend tag and the
snapshot keeps the breakdowns next to the totals.

Category provenance:

Directive section 10: backend_hashes, unique_headers,
unique_nonces, leases_completed, leases_abandoned,
repeated_work, candidates, verification_hashes,
valid_candidates, pool_shares_submitted, pool_shares_accepted,
pool_shares_rejected, network_target_candidates,
blocks_submitted, blocks_accepted, blocks_rejected.

EXP-035 section 7 accounting (kept as its own counters, never
merged into the directive names): unique_coverage (completed
chunk sizes only, in positions), actual_computations (every
reported examination, including repeats), duplicate_deliveries
and stale_reports (rejected coordinator reports). EXP-035's
"repeated computations" is this module's repeated_work: one
counter, two source documents; the equivalence is recorded
here and in STATISTICAL_MODEL.md so the vocabularies cannot
drift apart silently.

What this engine does not do: it does not reach into the live
paths and count on their behalf. Callers record what they did;
tests pin the accounting rules. The evidence-log census (pool
shares over the whole log) lives in mining/autopilot.py's
EvidenceCounter, whose counts feed pool_shares_accepted and
pool_shares_rejected when a consumer builds a snapshot from
the log.

Production wiring (EXP-037 closure, Phase 002 step 4): the
live paths now record as the work happens, through the two
helpers at the bottom of this module. SafeRecorder is the
failure-isolated front end every production caller uses: a
statistics defect must never stop mining, so record()
exceptions are swallowed and counted there instead of
propagating into a search loop (the autopilot EvidenceCounter
sets the precedent: its corrupt-state fallback keeps the
supervisor alive on bad input). FrontierAccountant splits one
process's search examinations into the separated counters
exactly: backend_hashes and actual_computations count every
examination, unique_nonces and unique_headers count only
positions and headers this process had not examined,
repeated_work counts re-examinations, and unique_coverage
advances only over chunks that completed without a hit, the
EXP-035 completed-chunks rule and the same rule the EXP-038
checkpoint frontier follows across restarts. The counters a
process records are that process's session scope; the
evidence census remains the lifetime source for pool shares.
"""

CATEGORIES = (
    # Directive section 10.
    "backend_hashes",
    "unique_headers",
    "unique_nonces",
    "leases_completed",
    "leases_abandoned",
    "repeated_work",
    "candidates",
    "verification_hashes",
    "valid_candidates",
    "pool_shares_submitted",
    "pool_shares_accepted",
    "pool_shares_rejected",
    "network_target_candidates",
    "blocks_submitted",
    "blocks_accepted",
    "blocks_rejected",
    # EXP-035 section 7 accounting.
    "unique_coverage",
    "actual_computations",
    "duplicate_deliveries",
    "stale_reports",
)

_CATEGORY_SET = frozenset(CATEGORIES)


class MiningStatistics:
    """Separated mining counters with per-worker and
    per-backend breakdowns. Counts are exact integers; nothing
    here is sampled or estimated."""

    def __init__(self):
        self._totals = {c: 0 for c in CATEGORIES}
        self._per_worker = {}
        self._per_backend = {}

    def record(self, category, count=1, worker=None, backend=None):
        if category not in _CATEGORY_SET:
            raise ValueError(
                f"unknown statistics category {category!r}; "
                f"categories are fixed by directive section 10 "
                f"and EXP-035 section 7, add new ones there "
                f"first")
        if not isinstance(count, int) or count < 0:
            raise ValueError("count must be a non-negative int")
        if count == 0:
            return
        self._totals[category] += count
        if worker is not None:
            slot = self._per_worker.setdefault(
                worker, {c: 0 for c in CATEGORIES})
            slot[category] += count
        if backend is not None:
            slot = self._per_backend.setdefault(
                backend, {c: 0 for c in CATEGORIES})
            slot[category] += count

    def total(self, category):
        if category not in _CATEGORY_SET:
            raise ValueError(f"unknown statistics category "
                             f"{category!r}")
        return self._totals[category]

    def snapshot(self):
        """All counters, separated. There is intentionally no
        grand-total field: the categories overlap and summing
        them would double-count (see module docstring)."""
        return {
            "categories": list(CATEGORIES),
            "totals": dict(self._totals),
            "per_worker": {k: dict(v)
                           for k, v in self._per_worker.items()},
            "per_backend": {k: dict(v)
                            for k, v in self._per_backend.items()},
        }


class WindowedRate:
    """Rate over trailing windows, derived from a cumulative
    counter's samples (counter-first, M11): feed it
    (timestamp, cumulative_count) pairs from a real counter and
    it reports counts per second over 1m / 10m / 1h style
    windows. The result is exactly as measured as the counter
    behind it; this class adds no estimation of its own.

    rate(window) uses the last sample at or before now as the
    end point and the last sample at or before now - window as
    the baseline, falling back to the earliest sample (and its
    shorter true span) when the window reaches before the
    first sample.
    """

    def __init__(self, max_samples=100000):
        self._samples = []
        self._max_samples = max_samples

    def add(self, ts, cumulative):
        if self._samples and ts < self._samples[-1][0]:
            raise ValueError("samples must be non-decreasing "
                             "in time")
        if self._samples and cumulative < self._samples[-1][1]:
            raise ValueError("cumulative counter went backwards; "
                             "start a new WindowedRate for a "
                             "reset counter")
        self._samples.append((float(ts), int(cumulative)))
        if len(self._samples) > self._max_samples:
            del self._samples[:len(self._samples)
                               - self._max_samples]

    def rate(self, window_s, now=None):
        if window_s <= 0:
            raise ValueError("window must be positive")
        if not self._samples:
            return 0.0
        if now is None:
            now = self._samples[-1][0]
        end = None
        baseline = None
        for ts, cum in self._samples:
            if ts <= now:
                end = (ts, cum)
            if ts <= now - window_s:
                baseline = (ts, cum)
        if end is None:
            return 0.0
        if baseline is None:
            baseline = self._samples[0]
        span = end[0] - baseline[0]
        if span <= 0:
            return 0.0
        return (end[1] - baseline[1]) / span


class SafeRecorder:
    """Failure-isolated record() front end for production
    callers (EXP-037 wiring).

    Mining must never stop because statistics broke: every
    exception from the wrapped MiningStatistics is swallowed
    here and counted in self.errors, so a caller can see that
    recording degraded without the search loop ever seeing the
    failure. The wrapped object is exposed as .stats so
    consumers and tests can snapshot it. The separation rule
    is unchanged: each call still names exactly one category,
    and no call ever sums categories.
    """

    def __init__(self, stats=None):
        self.stats = stats if stats is not None \
            else MiningStatistics()
        self.errors = 0

    def record(self, category, count=1, worker=None,
               backend=None):
        try:
            self.stats.record(category, count, worker=worker,
                              backend=backend)
        except Exception:
            self.errors += 1

    def snapshot(self):
        return self.stats.snapshot()


class FrontierAccountant:
    """Per-process search accounting with exact separation
    (EXP-037 wiring, EXP-035 rules).

    Tracks, per header, the next unexamined nonce for this
    process. record_search(header, start, attempted, completed)
    splits one search call's examined interval
    [start, start + attempted) against that frontier:

    - backend_hashes and actual_computations grow by every
      examination, repeats included;
    - unique_nonces grows only by positions at or beyond the
      frontier (never examined for this header by this
      process), and unique_headers by 1 the first time a
      header is searched;
    - repeated_work grows by the positions below the frontier
      (already examined for this header);
    - unique_coverage grows by the unique positions only when
      completed is true, that is when the chunk ran to its end
      without a hit: EXP-035 counts completed chunk sizes
      only, and a hit chunk's coverage is credited through
      the candidate counters, not here. This is the same rule
      the EXP-038 checkpoint applies before advancing its
      persistent frontier.

    All recording goes through a SafeRecorder, so accounting
    can never raise into a search loop. Returns the
    (unique, repeated) split for callers and tests.
    """

    def __init__(self, stats=None):
        self.recorder = SafeRecorder(stats)
        self.stats = self.recorder.stats
        self._frontier = {}

    @property
    def errors(self):
        return self.recorder.errors

    def record_search(self, header, start, attempted, completed,
                      worker=None, backend=None):
        if header not in self._frontier:
            self._frontier[header] = 0
            self.recorder.record("unique_headers", 1,
                                 worker=worker, backend=backend)
        frontier = self._frontier[header]
        end = start + attempted
        unique = max(0, end - max(frontier, start))
        repeated = attempted - unique
        self._frontier[header] = max(frontier, end)
        self.recorder.record("backend_hashes", attempted,
                             worker=worker, backend=backend)
        self.recorder.record("actual_computations", attempted,
                             worker=worker, backend=backend)
        if unique:
            self.recorder.record("unique_nonces", unique,
                                 worker=worker, backend=backend)
            if completed:
                self.recorder.record("unique_coverage", unique,
                                     worker=worker,
                                     backend=backend)
        if repeated:
            self.recorder.record("repeated_work", repeated,
                                 worker=worker, backend=backend)
        return unique, repeated

    def snapshot(self):
        return self.stats.snapshot()
