# EXP-035: Final Report

Distributed CPU Agent Architecture: design and
controlled testing. Phase G of the EXP-030 programme.

## What was delivered

- **WORK_DISTRIBUTION_DESIGN.md**: the production design
  for the three components the gap analysis found
  MISSING: Work Lease Manager, Distributed Agent
  Coordinator, Candidate Queue. Search space modelled as
  slices over extranonce2 (Qaxe partition
  (slot << 25) + counter), BIP320 version variants and
  ntime values, times the nonce range, never as nonce
  division alone. Leases carry unique ids, fencing
  tokens and deadlines. Worker registry with fleet
  identity checks, 10 second class telemetry timeout
  and starvation re-registration. One reclaim path for
  death, expiry, worker restart and coordinator restart.
  Candidate Queue with persist-before-acknowledge
  journal, full-header-identity dedup, generation check
  at drain, and a defined flow into the EXP-036 Exact
  Candidate Verifier.
- **Research prototype**: lease_manager.py and
  candidate_queue.py under this directory, generalising
  the proven EXP-029 RangeAllocator with fencing,
  expiry, multi-dimensional slices and the registry.
- **Controlled tests**: TESTS/test_exp035_campaign.py,
  10 targeted fault tests and a 60-trial randomised
  campaign, all passing on this VM. Raw record:
  RAW_RESULTS/campaign_20261115T101733Z.json. Proof
  obligations P1 to P6 and their discharge:
  PROOFS/PROOF_OBLIGATIONS.md.

## Headline results (local simulation, labelled as such)

- 60 of 60 campaign trials completed their declared
  space exactly: 609,280 unique positions in aggregate,
  pairwise disjoint, no gaps.
- Injected faults across the campaign: 2,167 worker
  deaths, 1,564 worker restarts, 801 coordinator
  restarts, 806 lease expiries, 694 legitimate steals,
  6,708 reclaims. Every dishonest or stale claim was
  rejected and counted: 3,190 zombie restart replays
  (all STALE), 2,088 duplicate completion deliveries,
  739 not-holder attempts. None of it entered unique
  coverage.
- 257,020 repeated computations were accounted in their
  own counter, never inside unique coverage.
- Candidate queue: 892 duplicate candidate submissions
  in-campaign, all detected; the verifier was invoked
  exactly once per unique candidate; journal recovery
  preserved both properties across simulated crashes.

## What this does NOT show

Multi-machine overhead, propagation latency and linear
scaling are UNVERIFIED: no numbers exist and none are
claimed. The wire protocol and persistent coordinator
are specified, not built. The roughly 25 fleet agents
were not activated, contacted or measured. No mining
kernel was benchmarked and no production code changed.
The production integration path, ending in a measured
overhead study before any fleet decision, is design
section 13; the fleet activation decision remains the
owner's.

## Addendum (2026-11-15): EXP-043 overhead study

EXP-043 (Phase 002 step 6) measured the coordination
overhead this report left unmeasured, on this VM only,
with simulated local workers. Full record:
../exp043/EXP043_REPORT.md.

Closed by EXP-043: in-process per-operation overhead
of the prototype components (core verbs 0.2 to 5 us
and flat; journalled candidate submit 18.4 us;
checkpoint snapshot 13.3 ms at 512 chunks rising to
420 ms at 8,192, because it deep-copies all retained
history); campaign overhead per completed position at
2, 8 and 32 simulated workers under this report's
fault mix (1,214, 13,764 and 1,525,761 ns per
position) and at 2, 8, 32 and 128 without faults; and
loopback round-trip latency of the prototype's
message shapes between separate processes (33 to
54 us at 1 worker process). The 128-worker fault
trial did not complete inside a 600 s cap (10.89
percent coverage) and is recorded in EXP-043 as a
failed run; the dominant mechanism is the lease()
starvation path scanning every lease record ever
issued, a prototype implementation defect recorded
as a finding for the production build.

Still open, unchanged: multi-machine coordination
overhead, propagation latency over any real network,
and linear scaling across machines remain UNVERIFIED;
the wire protocol and persistent coordinator remain
specified, not built (the EXP-043 loopback shim is a
measurement shim, not the protocol); and the roughly
25 fleet agents were again not activated, contacted
or measured. The fleet activation decision remains
the owner's.
