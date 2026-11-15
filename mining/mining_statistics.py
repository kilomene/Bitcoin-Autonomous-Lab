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
