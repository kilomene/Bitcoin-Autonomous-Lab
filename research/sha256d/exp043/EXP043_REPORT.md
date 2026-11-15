# EXP-043: EXP-035 Coordination Overhead Study

Phase 002 step 6. This VM only. Every worker in this
study is a local simulated process or an in-process
method call. No fleet agent was activated, contacted,
woken or assigned work; fleet activation remains the
owner's decision. No production code was touched and
nothing was pushed.

## What this study is

EXP-035 delivered the work-distribution design and a
research prototype (lease_manager.py, candidate_queue.py)
and proved the accounting closes exactly under faults.
What it never measured was the coordination overhead:
the UNVERIFIED register carried since EXP-029 read
"multi-machine coordination overhead, propagation
latency, linear scaling: unverified, no numbers exist".
This study measures what can honestly be measured on
one VM, in three parts:

1. In-process cost of each prototype operation
   (micro_bench.py, time.perf_counter_ns around the
   prototype's own calls, 3 sessions).
2. Simulated multi-worker campaigns in the EXP-035
   shape at increasing worker counts, timed
   (campaign_bench.py, 3 fault trials plus 1 no-fault
   trial per scale point).
3. A localhost loopback wire shim: coordinator and
   workers as separate processes on 127.0.0.1
   (wire_bench.py, 3 sessions). The prototype has no
   wire protocol; the shim is a thin framing over the
   existing message shapes and is labelled a shim
   throughout. The production protocol remains unbuilt.

## Environment and method honesty

Host: AMD EPYC 9D25 (this VM reports 4 vCPUs; the cell
share is about 1.5 CPUs). The live mainnet miner ran
throughout the study, and an EXP-042 solver task ran
concurrently during part of it. Load averages are
recorded in every session manifest in RAW_RESULTS
(micro sessions: 1-minute load 4.1 to 11.8 across the
runs; wire sessions about 8 to 11.5; the campaign
session rose from 3.5 to 14.1). All headline numbers
are medians across the 3 sessions of each set. Cells
whose session spread exceeds about 3x are flagged
contention-dominated where they appear. Absolute
numbers on this VM are contended-VM numbers; the
growth patterns between scale points, measured inside
single sessions, are the robust findings.

Simulated positions in the campaigns carry no hashing
cost: a "position" is one nonce in the declared space,
examined by progress reports. Where a comparison to
hashing is made below, it uses the lab's EXP-031
measurement of about 185 ns per hash for one production
thread, and is labelled as sizing context only.

## Part 1: per-operation costs (in-process)

Medians across 3 sessions, nanoseconds unless stated.
Worker sweep slices hold 64 chunks each; the space
sweep holds total chunks constant at 512 while the
declared space varies.

### Constant or near-constant operations

| Operation | Cost | Behaviour |
|---|---|---|
| heartbeat | 220 ns (370 ns at 128 workers) | flat |
| register_worker | 0.73 us | flat from registry 8 to 512 |
| candidate submit (new) | 0.77 us | flat vs seen-history size: 0.86 us at 100 seen, 0.77 at 1,000, 0.75 at 10,000, 0.81 at 20,000 |
| candidate submit (duplicate, the dedup check) | 0.80 us | flat; the dedup is one dict lookup on the full header identity |
| progress report | 1.0 to 1.1 us at chunk 128; 1.8 us at 128 workers; 2.0 us at chunk 2,048 | weak growth |
| complete | 2.6 to 3.0 us up to 32 workers; 3.9 to 4.4 us at 128 workers | weak growth; first slice and last slice cost the same within noise |
| steal | 2.8 us (p95 3.8 us) | measured at small state |
| lease grant | 3.1 to 3.3 us up to 32 workers; 4.6 to 4.7 us at 128 workers | within one slice, grants late in the fill cost about 25 percent more than early grants at 128 workers (scan past non-pending chunks) |

### Operations that grow with state

| Operation | Measured | Driver |
|---|---|---|
| declare_job | 23 us (64 chunks), 204 us (512), 768 us (2,048), 2.97 ms (8,192) | about 0.36 us per chunk; at a fixed 512 chunks it costs 157 to 204 us whether the declared space is 1,024, 65,536 or 1,048,576 positions: chunk count, not position count |
| expire(), idle scan | 0.20 ms with 2,048 active leases; 1.62 ms with 8,192 | scans the worker registry plus every lease record |
| expire(), mass reclaim | 2,048 reclaims in 23.2 ms (11.3 us each); 8,192 in 385.9 ms (47.1 us each) | per-reclaim cost grows with slice count and total state (the reclaim path locates the chunk by scanning) |
| snapshot() (coordinator checkpoint) | 1.7 ms at 64 chunks (sessions 10.3, 1.7, 1.3 ms, contention-flagged), 13.3 ms at 512, 126.8 ms at 2,048, 420.3 ms at 8,192 | deepcopy of the entire retained state: chunks, every lease record ever issued, and the full event log |
| restore() (checkpoint load) | 3.1 ms with 512 active leases, 12.3 ms with 2,048, 348 ms with 8,192 (6.0 us per reclaim at 2,048; 42.5 us at 8,192) | dominated by reclaiming every active lease, at the same per-reclaim cost the expire path shows; two independent measurements agree |

### Candidate queue persistence

| Operation | Cost |
|---|---|
| submit, in-memory | 0.77 us |
| submit, journalled (the prototype's persist-before-acknowledge write: open, append one JSON line, close, per event, on this VM's /tmp) | 18.4 us median, about 24x the in-memory submit; p95 223 us under contention |
| drain, per record, trivial verifier | 7.0 us median of sessions, session range 1.1 to 7.8 us: contention-dominated, treat as an upper bound |
| journal recover, per record | 7.7 us at 1,000 records; 17.0 us at 5,000 (session range 11.8 to 34.1 us): contention-dominated |

One low-sample cell is excluded from conclusions:
progress at chunk size 2 has only 2 samples per session
(the space sweep's smallest point) and reads 5.1 us;
nothing rests on it.

## Part 2: campaign scaling

Fixed declared space of 131,072 positions and 32 chunks
per slice at every scale point, so worker count is the
only variable. The fault mix is the EXP-035 mix
(deaths, restarts, expiries, steals, zombie replays,
duplicate deliveries, not-holder attempts, coordinator
restarts), with two declared deviations recorded in
the deviations section (a 40-restart budget per trial,
and O(1) completion tracking in the harness). Every
completed trial's accounting was asserted exactly at
trial end: union of completed intervals equals the
declared space, pairwise disjoint, duplicates and
repeated work in their own counters.

| Workers | Fault wall (median of 3) | Fault ns per position | No-fault wall | No-fault ns per position | Fault / no-fault |
|---|---|---|---|---|---|
| 2 | 0.159 s | 1,214 | 0.0013 s | 10 | 122x |
| 8 | 1.804 s | 13,764 | 0.017 s | 131 | 105x |
| 32 | 199.99 s | 1,525,761 | 1.116 s | 8,513 | 179x |
| 128 | CAPPED at 600 s, did not complete | n/a (see below) | 76.6 s | 584,481 | n/a |

The 128-worker fault trial is a FAILED run by this
study's own rule and is reported as one: after 600.8 s
and 210,944 loop iterations it had completed 14,280 of
131,072 positions (10.89 percent), with 15,553
reclaims, 9,226 expiry events, 13,571 zombie replays
(all rejected STALE, none credited) and 16,065 lease
records retained. Its accounting does not close and it
is not averaged with completed trials.

Mechanisms, from a 100-second cProfile capture of a
32-worker fault trial (RAW_RESULTS/
profile_w32_fault_100s.txt, reproducible with
profile_campaign.py):

- 67 percent of CPU sits in LeaseManager._holds_lease:
  a scan of every lease record ever issued, run on the
  starvation path of lease() calls. The lease table is
  never pruned. The 32-worker trials end with about
  9,700 lease records retained for 1,024 chunks (about
  9.5 leases issued per chunk under churn); the capped
  128-worker trial retained 16,065 records while
  completing 446 chunks.
- 25 percent sits in snapshot() deepcopy: the
  40-restart budget was spent inside the first 100 s,
  at 0.62 s per snapshot at that state size.
- expire() is 3.7 percent. Everything else is noise by
  comparison.

Fault amplification, stated precisely: the simulated
clock advances about 0.8 s per loop iteration while
each worker is attended once per W iterations, so at
W of 8 and above most workers are heartbeat-stale most
of the time under the design's 10-second timeout class
(matrix M14). expire() reclaims their leases, reported
progress is discarded into the repeated-work counter
(at 32 workers, actual computations are 1.97x the
declared space), and every re-lease pays the history
scan again. This is a property of the prototype and
its parameters under round-robin attention, measured
here; a real fleet heartbeats independently of
coordinator attention, so the churn rate itself does
not transfer. The scan costs it exposes do transfer:
they are in the code path regardless of why re-leasing
happens.

Sizing context only (labelled): against EXP-031's
about 185 ns per hash, coordination per completed
position in this Python prototype is about 0.7 hashes
(no-fault, 8 workers), about 75 hashes (fault mix,
8 workers), and about 8,200 hashes (fault mix,
32 workers). The no-fault 128-worker figure, 584,481 ns
per position with zero faults injected, is the
starvation rule's own churn: most loop iterations are
lease attempts rejected because the worker's last
lease or registration is older than the 10-second
window in simulated time, and each rejected attempt
still pays the _holds_lease scan. 79,601 iterations
moved 131,072 positions.

## Part 3: loopback wire shim

The shim (wire_bench.py) is length-prefixed JSON over
TCP on 127.0.0.1. A coordinator process holds the
prototype manager and queue behind one lock (the
manager is not thread-safe; connection handling is
threaded). Workers are separate processes performing
register, heartbeat, lease, two progress reports and a
completion per cycle, a candidate submit plus a
duplicate every fifth cycle, and one steal mid-run.
Timeouts are widened to 60 s of coordinator monotonic
time so expiry policy does not fire during timing.
This is not the EXP-035 wire protocol, which remains
specified and unbuilt.

Round-trip latency, median of 3 session medians:

| Workers | heartbeat | lease | progress | complete | candidate submit |
|---|---|---|---|---|---|
| 1 | 33 us | 54 us | 40 us | 39 us | 43 us |
| 4 | 120 us | 136 us | 141 us | 134 us | 141 us |
| 16 | 1,004 us | 951 us | 1,128 us | 1,010 us | 1,115 us |

The 1-worker row is the shim's floor: about 35 to 55 us
per round trip, of which the manager call itself is
1 to 5 us (Part 1); the rest is framing, JSON, socket
and process crossing on this VM. The growth to 4 and
16 workers is dominated by process contention on this
VM (17 runnable processes on 4 reported vCPUs with an
about 1.5-CPU cell share, alongside the live miner):
p95 at 16 workers is 9 to 13 ms. Do not read the
16-worker row as a protocol scaling law; it is an
upper bound measured under heavy contention.

End state over the wire: at 1 worker the accounting
closed exactly through the shim (unique coverage
equals declared, 614,400 of 614,400). At 4 and 16
workers the end-of-run snapshots show 99.67 and 99.33
percent coverage; the remainder is stolen tails held
by thieves (the shim's workers do not complete leases
they stole) and chunks in flight at snapshot time.
Candidate dedup over the wire behaved exactly as
designed (at 16 workers: 942 submits, 471 duplicates).
The shim never drains the queue, so verification over
the wire is unmeasured.

Shim failure, recorded: the first version asserted
every completion returns OK. At 4 workers and above, a
steal rotates the victim lease's fencing token, so the
victim's next completion correctly returns STALE
(EXP-035 obligation P3 working as designed); the
assert killed the worker silently, the run hung, and
it was discarded. The fixed shim tolerates STALE
(abandon the lease, lease again) and surfaces worker
errors to the parent. Lost-to-steal completions in the
fixed runs: 0 at 1 worker, 0 to 3 at 4 workers, 14 to
16 at 16 workers.

## Scaling statement

Constant per operation, measured flat across the
studied ranges: heartbeat, registration, candidate
submit and the dedup check (any history size up to
20,000), and, with weak growth only, progress,
completion, steal and lease grant within a slice.

Grows with chunk count: job declaration (about
0.36 us per chunk), the idle expiry scan (about 0.1 to
0.2 us per active lease), and the checkpoint pair.

Grows with retained history, which is the structural
finding of this study: the lease() starvation path
scans every lease ever issued; per-reclaim cost rises
from about 6 us at a 2,048-chunk state to about 43 to
47 us at an 8,192-chunk state; snapshot() deep-copies
the whole history including an event log that nothing
bounds; completed lease records are never pruned.
Campaign wall time per completed position therefore
grows superlinearly with worker count under churn:
1.2 us at 2 workers, 13.8 us at 8, to 1.53 ms at 32,
to non-completion inside 600 s at 128, all under the
EXP-035 fault mix on this VM.

What this implies: the design's core verbs are cheap
and mostly constant, so a production implementation
of the same semantics would not be coordination-bound
on the per-operation path at these scales. The
history scans are prototype implementation defects
relative to the design's intent, not design costs: an
active-lease index per worker makes the starvation
check O(1), pruning completed lease records and
bounding the event log make the checkpoint
proportional to live state only. They are recorded
here as findings for the production build; the
research prototype was not modified.

What this does not imply: anything about machines
that do not exist yet. No real network latency, no
clock skew, no partial network failure, and no fleet
behaviour is measured here, and in-process or loopback
numbers are never multi-machine measurements.

## UNVERIFIED register, updated

Closed by this study (this VM only): in-process
per-operation overhead of the EXP-035 prototype
components; campaign overhead per completed position
at 2, 8 and 32 simulated workers under the EXP-035
fault mix and at 2, 8, 32 and 128 without faults;
loopback round-trip latency of the prototype's
message shapes between separate processes.

Still UNVERIFIED, precisely: multi-machine
coordination overhead; propagation latency over any
real network; linear scaling across machines; the
production wire protocol (still unbuilt; the shim is
not it); persistent-coordinator behaviour in
production; overhead at production chunk sizes and
template rates; and every property of the roughly 25
fleet agents, who were not activated, contacted or
measured.

## Deviations and discarded runs

- The first campaign run was killed and discarded.
  Its driver polled accounting() on every loop
  iteration (profiled at about 19 percent of a
  32-worker trial: harness noise, not prototype cost)
  and its uncapped 128-worker fault configuration was
  projected at multi-hour. On the same seed, the
  32-worker trial 0 measured 347 s under the polluted
  driver and 243 s under the fixed driver. Only
  fixed-driver numbers are reported. The discarded
  run's log is retained in RAW_RESULTS as
  campaign_run.log; the reported run is
  campaign_run2.log.
- Coordinator restarts in campaigns are budgeted at
  40 per trial (the EXP-035 rate of 3 percent per
  iteration is kept until the budget is spent; every
  fault trial at 8 workers and above spent the full
  budget, and the counts are in the raw data). Without
  the budget, restart count scales with iteration
  count and the study measures deepcopy alone.
- The 128-worker fault trial is capped at 600 s and
  recorded as a failed, non-completing run (above).
- The first wire shim version hung on the STALE
  assert and was discarded (above).
- One progress cell (chunk size 2, n=2 per session)
  is reported but excluded from conclusions.

## Files

- micro_bench.py, campaign_bench.py, wire_bench.py,
  exp043_common.py: the study code.
- profile_campaign.py: the profiling driver behind
  the mechanism claims (100 s cProfile capture of a
  32-worker fault trial).
- RAW_RESULTS/: 3 micro session JSONs, 1 campaign
  session JSON (16 completed trials plus the capped
  128-worker fault trial), 3 wire session JSONs, the
  profile capture, and the run logs, including the
  discarded first campaign run's log.
