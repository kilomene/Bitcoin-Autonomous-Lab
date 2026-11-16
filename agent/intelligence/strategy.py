"""Strategic intelligence: objectives, gap accounting and
investigation ranking (Master Build Mandate sections 1.1, 4.1A
and 16).

The targets are objectives, not established capabilities. Every
number this module returns is labelled as a gap between a
measured rate supplied by the caller and those objectives; the
module never invents a rate of its own.
"""

import os

TARGET_MIN_HS = 500e9      # 500 GH/s minimum objective
TARGET_LARGE_HS = 140e12   # 140 TH/s larger objective

_REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".."))


def gap_report(verified_rate_hs):
    """Gap between one measured rate and both objectives.

    Returns a dict with the measured rate, each target, the
    percentage of each target the rate represents, and the
    remaining gap factor (target divided by rate). A zero or
    negative rate is reported honestly: percentages 0 and gap
    factors infinite.
    """
    rate = float(verified_rate_hs)
    if rate > 0:
        pct_min = rate / TARGET_MIN_HS * 100.0
        pct_large = rate / TARGET_LARGE_HS * 100.0
        gap_min = TARGET_MIN_HS / rate
        gap_large = TARGET_LARGE_HS / rate
    else:
        pct_min = 0.0
        pct_large = 0.0
        gap_min = float("inf")
        gap_large = float("inf")
    return {
        "measured_rate_hs": rate,
        "target_min_hs": TARGET_MIN_HS,
        "target_large_hs": TARGET_LARGE_HS,
        "pct_of_min_target": pct_min,
        "pct_of_large_target": pct_large,
        "gap_factor_min": gap_min,
        "gap_factor_large": gap_large,
        "note": ("Targets are objectives, not established "
                 "capabilities. The measured rate is the "
                 "caller's verified figure; this report adds "
                 "no measurement of its own."),
    }


# Ranking preference for next investigations: fresh and deferred
# questions first, then work already under investigation, then
# experimental results that may deserve a second look. PROVEN
# entries rank last among the eligible; REJECTED and INTEGRATED
# entries are excluded entirely.
_STATUS_RANK = {"NEW": 0, "DEFERRED": 1, "UNDER_INVESTIGATION": 2,
                "EXPERIMENTAL": 3, "PROVEN": 4}
_EXCLUDED = ("REJECTED", "INTEGRATED")


def next_investigations(memory, limit=5):
    """Rank candidate investigations from the research memory.

    Excludes REJECTED and INTEGRATED entries. Prefers NEW and
    DEFERRED entries, and among equals prefers a recorded
    expected benefit over none, then the larger benefit.
    Ordering is fully deterministic: status rank, benefit,
    entry id, source.
    """
    candidates = []
    for e in memory.entries:
        if e.status in _EXCLUDED:
            continue
        rank = _STATUS_RANK.get(e.status, 5)
        benefit = e.expected_benefit
        candidates.append({
            "entry_id": e.entry_id,
            "title": e.title,
            "status": e.status,
            "expected_benefit": benefit,
            "source": e.source,
            "_rank": rank,
            "_benefit_key": (0, -benefit) if benefit else (1, 0.0),
        })
    candidates.sort(key=lambda c: (c["_rank"], c["_benefit_key"],
                                   c["entry_id"], c["source"]))
    out = []
    for c in candidates[:limit]:
        out.append({k: c[k] for k in
                    ("entry_id", "title", "status",
                     "expected_benefit", "source")})
    return out


def bottleneck_summary():
    """The current known bottlenecks, as cited facts from the
    record. Each item names its source file so the claim can be
    rechecked against the primary evidence."""
    items = [
        {"fact": ("This VM delivers about 2 effective CPUs "
                  "despite presenting 4 vCPUs (EXP-031 "
                  "estimates 1.87 to 2.04); per-system throughput "
                  "is capped by the guest allocation, not by "
                  "visible vCPU count."),
         "source": "research/sha256d/exp031/"
                   "CPU_VM_CHARACTERIZATION.md"},
        {"fact": ("Best verified complete production search on "
                  "this host is the v512dual backend at EXP-017 "
                  "pooled 6.781x over the production C search "
                  "(EXP-032 confirmation); 500 GH/s is about "
                  "33,800 such contended VMs."),
         "source": "research/sha256d/exp032/EXP032_REPORT.md"},
        {"fact": ("The full SHA-256 round is closed at its "
                  "vocabulary optimum of 28 vector operations "
                  "(EXP-020); production v512 emits 29 and "
                  "closing that gap measured as an established "
                  "null (EXP-041). The DualMask search body "
                  "already emits 28."),
         "source": "research/PHASE002_CLOSING_AUDIT.md"},
        {"fact": ("Coordination prototype costs are dominated "
                  "by implementation defects, not design: at 32 "
                  "workers about 67 percent of CPU sat in an "
                  "unpruned lease scan and 25 percent in "
                  "snapshot deep copies; a 128-worker fault "
                  "trial failed to complete in 600 s (EXP-043)."),
         "source": "research/sha256d/exp043/EXP043_REPORT.md"},
        {"fact": ("End-to-end non-search overhead per block is "
                  "about 44 ms empty and about 206 ms with 500 "
                  "transactions on regtest (EXP-040 category F); "
                  "at production difficulty the search dominates "
                  "and this overhead is not the binding limit."),
         "source": "research/sha256d/exp040/EXP040_REPORT.md"},
    ]
    for item in items:
        item["source_exists"] = os.path.isfile(
            os.path.join(_REPO_ROOT, item["source"]))
    return items
