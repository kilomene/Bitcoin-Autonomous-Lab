# EXP-029: Parallel and Distributed CPU Execution

Experiment ID: EXP-029 (reserved 2026-11-14, Phase 6B).
Status: COMPLETE 2026-11-15. The allocator core is
proven by test (criterion 1, section 5), coordination
overhead is measured for a local in-process prototype
only (criterion 2, section 6), telemetry and failure
recovery each have a test (criterion 3), the
centralised versus decentralised comparison is filed
(section 8), and the end-to-end gate passed: a fresh
regtest block mined through the distributed path and
accepted by Core (height 829, section 7). No
multi-machine run exists; every distributed-scale
figure beyond this host is UNVERIFIED. Nothing is
integrated; production is byte-identical at close.
Track: A (supporting), software architecture research.

Programme objectives, at full height, unchanged:
500 GH/s minimum system objective; 140 TH/s larger
objective. Section 9 states exactly what this
experiment does and does not say about them.

## 1. Predeclared hypothesis and accounting (unchanged)

Hypothesis: a coordinator that allocates disjoint
nonce ranges to independent CPU workers (threads,
processes, sockets, machines), with dynamic
reassignment on worker failure and template
propagation on tip change, can preserve exact nonce
coverage (no overlap, no accidental gaps) while
scaling aggregate throughput linearly in the number
of workers, minus a measured coordination overhead.
Duplicate work is never counted as unique coverage,
under the accounting separations below, adopted as
standing definitions for the whole phase.

Accounting separations (standing, directive section 9):

- Unique nonce coverage: distinct nonces examined.
- Actual SHA-256 computations: every compression
  actually executed, including repeats.
- Repeated computations: the subset of actual
  computations that re-examined already-covered
  nonces (reassignment overlap, verification excluded).
- Verification computations: independent candidate
  checks, reported separately, never as throughput.
- Candidate submissions: candidates sent onward,
  each independently verified before submission.

## 2. Architecture

Coordinator and workers. The coordinator owns, per
template (job): the declared nonce range, the chunk
partition, the lease table, the completion set and
the five accounting counters. Workers own nothing but
their current lease and their kernel (selected per
machine by the EXP-028 dispatch). Communication is
four message shapes, transport-agnostic (in-process
calls in the prototype; the same shapes map onto the
lab's existing Stratum and RPC surfaces later):

- lease request / lease grant (chunk bounds, job id,
  template identity, lease epoch).
- progress report (chunk id, cumulative examined
  count, current rate): feeds both accounting and
  telemetry.
- completion (chunk id, candidate list, possibly
  empty): idempotent, see section 4.
- heartbeat (worker id, timestamp, rate, backend
  identity from the EXP-028 record).

Template identity: a job is identified by the full
template content, not a sequence number. The EXP-025
lesson applies directly: an identity that omits an
input the work depends on serves stale work silently.
A lease therefore carries the job id plus the
template fingerprint (the EXP-025 layered identity
of the candidate the range belongs to), and a worker
must refuse a lease whose fingerprint does not match
the template it holds. On any mismatch the work is
void: its examinations count as actual computations
under the old job and never as coverage under the new
one.

## 3. The mechanisms, one by one

Nonce-range allocation. The declared range (in
practice [0, 2^32) per extranonce step, or a batch
sub-range of it) is partitioned at job creation into
fixed chunks (prototype default 16,384; the overhead
run compares 10,000 and 1,000). Chunks are the unit of
lease, completion and accounting. The partition is a
list of half-open intervals that tiles the declared
range exactly; the allocator asserts the tiling
invariant (first chunk starts at the range start,
every chunk ends where the next begins, last chunk
ends at the range end) after every mutation in the
test harness, and the invariant is what makes
disjointness a construction property rather than a
runtime hope.

Dynamic distribution. Workers pull leases; the
coordinator never pushes. A fast worker therefore
takes more chunks than a slow one with no rate model
and no rebalancing pass, and a worker that joins late
takes from the same pending queue. Chunk size is the
only tuning knob: smaller chunks balance better and
cost more coordinator operations per nonce (measured
locally, section 6).

Work stealing. When the pending queue is empty and
leased chunks remain, an idle worker may steal: the
allocator splits the unreported tail of the largest
leased chunk, shrinking the victim's lease FIRST
(recorded in the lease table) and only then granting
the tail to the thief. Because the shrink precedes
the grant, no instant exists at which two leases
cover the same nonce. A real worker whose chunk is
stolen learns its new bound from the next coordinator
response and must stop at it; examinations past a
shrunken bound, if a worker races the shrink, are
actual computations that can only ever be reported
against the stolen chunk by its new holder, and the
overlap is repeated computation by definition.

Duplicate-work prevention. Three layers. (a) By
construction: exclusive leases over a tiled partition
make legitimate overlap impossible. (b) By
idempotence: completion is keyed by chunk id; a
duplicate delivery returns DUPLICATE, increments the
duplicate counter, and changes no coverage (tested).
(c) By accounting: any re-examination that does occur
(after a death, a restart, or a steal race) is
counted as repeated computation, never added to
unique coverage. Unique coverage grows only by
completed chunk sizes, and a chunk completes once.

Template propagation on tip change. When the tip
moves (or the template otherwise changes), the
coordinator closes the current job: pending chunks
are discarded, outstanding leases are voided, and a
fresh allocator is constructed for the new template
with its own fingerprint. Workers learn of the change
on their next message of any kind and discard the old
lease. In-flight examinations under the old job stay
in the old job's actual count; they are never carried
into the new job's coverage. The in-repo precedents
are the solo server's JobRefresher (tip poll 2 s,
broadcast on tip move or 120 s job age) and the GBT
longpoll loop in the live miner (about 1.0 s), which
already implement this close-and-replace discipline
for one worker; EXP-029 generalises the bookkeeping,
not the trigger. Propagation latency across machines
is UNVERIFIED (no second machine); the local figure
is the allocator rebuild time, which is trivially the
partition construction cost and is not quoted as a
network number.

Failure recovery. Worker death is detected two ways:
an explicit fail signal (the prototype's fail_worker,
the production analogue being the autopilot watchdog)
or heartbeat staleness (section 3, telemetry). On
death, the worker's leased chunks return to pending.
Progress the dead worker had reported is not lost
accounting: it is recorded as examined_before on the
chunk, and when the chunk is re-leased that amount is
moved into repeated_computations, because a new
worker will examine those nonces again. The chunk's
unique coverage is credited only when some worker
completes it. Coordinator death: the allocator state
is a JSON-safe snapshot (snapshot/restore in the
prototype); on restore, leases do not survive
(workers are presumed dead or re-registering), so
leased chunks return to pending with the same
examined_before treatment. A coordinator that cannot
recover its snapshot must declare a new job epoch and
treat all prior coverage as unverified: coverage is
only ever claimed from the completion set, never
reconstructed from worker claims after the fact.

Telemetry. Per worker: heartbeat timestamp, current
rate (from progress reports), backend identity and
host record (the EXP-028 section 6 fields). Per job:
the five accounting counters plus pending and leased
totals, which must always satisfy unique + pending +
leased == declared count. Stale-worker detection:
a worker whose heartbeat is older than the timeout
(10 s in the test; the production supervision layers
use 5 s heartbeats and a 300 s hung window at the
process level, which is a different layer and is not
conflated with chunk leases) is listed stale and its
chunks are eligible for fail-and-requeue. The solo
server's per-worker accounting file
(.local/solo-status.json, written every 5 s) is the
existing production shape this telemetry extends.

## 4. Implementation: the allocator prototype

benchmarks/exp029_allocator.py (research only, no
production file touched). RangeAllocator implements
exactly the mechanisms above: tiled partition, pull
leases, cumulative progress, idempotent completion,
fail_worker requeue with examined_before accounting,
steal with shrink-before-grant, snapshot/restore with
lease drop, heartbeat and stale detection, and an
accounting() report carrying the five standing
counters plus pending, leased and complete. Its
verification_computations and candidate_submissions
are structurally 0 at this layer: verification lives
in the engine (gpu/engine.py verify_candidate) and
submission in MiningEngine, and the allocator refuses
by construction to count either as coverage.

Known prototype limitation, recorded plainly: the
allocator's complete() credits actual_computations
with the full chunk size (a completed chunk is
treated as fully examined). For a chunk whose worker
stopped early at its own hit, the engine-level
attempted count is the exact figure and the allocator
figure is an upper bound. The regtest record in
section 7 shows both. Unique coverage is unaffected:
it counts distinct nonces in completed chunks, which
is exact regardless of where inside the chunk a hit
stopped the scan.

## 5. Criterion 1: coverage proof by test (PASS)

benchmarks/exp029_tests.py, record
allocator_tests_20261115T061200Z.json:

Targeted cases, each asserted exactly:
- Duplicate delivery: completing chunk [0,4) twice
  returns OK then DUPLICATE; unique coverage stays 4;
  duplicate_deliveries is 1.
- Death mid-range: a worker reports 5 of 8 nonces and
  dies; on re-lease, repeated_computations becomes
  exactly 5; after completion unique coverage is 8
  and actual is 13 (5 dead examinations plus 8 live).
- Steal: a 64-nonce chunk with 10 reported is stolen
  from; the partition invariant holds immediately
  after the split; both parts complete; unique
  coverage is exactly 64 with no overlap.
- Coordinator restart: snapshot at 3 reported of 8;
  after restore the chunk is pending, and on re-lease
  repeated_computations becomes exactly 3.
- Telemetry: heartbeats at t=100 and t=115 with a 10 s
  timeout at t=120 list exactly the first worker stale.
- Boundary: a range ending exactly at 2^32 completes
  exactly.

Randomised campaign: 120 trials over randomised
starts (including unaligned starts and ranges ending
at 2^32), counts 1 to 2000, chunk sizes 3 to 777,
worker counts 1 to 8, and randomised injections of
worker death, duplicate delivery, stealing and
coordinator restart. Every trial ends with the union
of completed intervals equal to the declared range
and pairwise disjoint (asserted interval by interval,
not by totals alone), and actual >= unique in every
trial. 67 of 120 trials exercised repeats (20,474
repeated computations in total, all accounted, none
inside unique coverage) and 44 exercised duplicate
deliveries. An earlier 300-trial configuration of
this campaign was cut short by the harness's own cost
(the partition invariant was being re-sorted after
every step); the campaign was re-scoped to 120 trials
with the invariant asserted every 25 steps and at
completion, and passed in full. That is a harness
scoping note, not an allocator finding.

## 6. Criterion 2: coordination overhead (MEASURED, local prototype only)

benchmarks/exp029_overhead.py, record
overhead_20261115T061203Z.json. In-process on this
host (AMD EPYC 9D25 guest, 4 vCPUs, about 1.5
effective CPUs, live miner and node running): worker
threads lease chunks and actually examine 120,000
nonces with hashlib double SHA-256 full scans.

| Workers | Chunk | Unique coverage/s | Efficiency vs 1 worker x W |
|---|---|---|---|
| 1 | 10,000 | 460,929 | 1.000 |
| 2 | 10,000 | 477,355 | 0.518 |
| 4 | 10,000 | 493,484 | 0.268 |
| 4 | 1,000 | 401,237 | 0.218 |

Reading, stated as carefully as the numbers: on this
guest the workers oversubscribe about 1.5 effective
CPUs, so efficiency against a linear ideal mostly
prices thread contention, not the allocator. Two
things do follow. Aggregate unique coverage per
second rose monotonically with workers even here
(460,929 to 493,484), so the allocator is not
serialising the work. And finer chunks cost real
throughput at equal workers (493,484 at chunk 10,000
vs 401,237 at chunk 1,000, both at 4 workers), which
is the coordination overhead made visible in the only
form this host can show it. Template propagation
latency and reassignment cost across machines, and
aggregate efficiency on any multi-machine
configuration, are UNVERIFIED: no second machine
exists, and no number is quoted for them. The
largest configuration actually run is 4 in-process
worker threads on one host, stated in full here as
the criterion requires.

## 7. End-to-end gate: regtest block (PASS)

benchmarks/exp029_regtest.py, record
regtest_20261115T061212Z.json. A DistributedCompute
shim partitions every MiningEngine batch through the
allocator (chunk 16,384) across 2 worker threads,
each running its own production ComputeEngine
(requested="c"). Template, candidate build, assembly
and submission are production mining/engine.py,
unmodified; candidates carry the production engine's
independent verification. Result: block accepted by
Core at height 829, hash
781cc4ef7fc3e583ff6fa9bf277c780083b7252a9d5ede4fed5d213e691a2e8f,
nonce 2048, best-chain and digest re-verified in the
harness. The winning batch's allocator record:
declared [0, 65536), unique coverage 65,536,
repeated 0, duplicate deliveries 0, complete true;
4 candidate hits were found inside the batch (regtest
difficulty) and the lowest nonce was returned. This
is a local in-process distribution (threads, one
process, one host), labelled as such; it is evidence
that the allocator composes with the real mining
path, not evidence about networks.

## 8. Criterion 4: centralised versus decentralised coordination

Compared on the predeclared criteria:

Coverage safety. Centralised: the completion set
lives in one place; disjointness is a construction
property of one partition; the proof burden is the
allocator in section 4. Decentralised (workers
self-allocating from a shared rule, for example
hash-of-worker ranges or a gossip lease table): two
workers can hold overlapping ranges whenever their
views of the lease table diverge, and disjointness
becomes a consensus property that must be proven
under partition, not a construction property. Edge:
centralised, decisively, for exact coverage.

Propagation latency. Centralised: one hop from the
coordinator's tip watcher to each worker's next
message; bounded by the heartbeat and lease cadence.
Decentralised: template changes must flood the
worker graph; latency grows with graph diameter and
stragglers work stale templates longer, voiding more
actual computations. Edge: centralised.

Failure modes. Centralised: the coordinator is a
single point of failure, mitigated by snapshot and
restore (section 3) and by the fact that a dead
coordinator loses no completed coverage, only
in-flight leases; workers idle rather than duplicate.
Decentralised: no single point of failure, but a
network partition splits the range authority itself,
and the two halves can both believe they own a chunk;
recovery requires reconciling two completion sets
with overlaps demoted to repeated computations.
Edge: decentralised for availability, centralised
for correctness under failure.

Verdict of the comparison: for this programme's
non-negotiable (exact coverage, duplicates never
counted as unique), centralised coordination is the
recorded choice for any build beyond the prototype.
Decentralised coordination is filed as considered
and not chosen, for the coverage reason above, not
from preference. This matches the lab's existing
shape (autopilot, keeper, solo server are all
centralised supervisors) without depending on it.

## 9. What this says about the objectives

The gap model (PERFORMANCE_GAP_MODEL.md) puts
500 GH/s at about 44,900 live-system equivalents or
about 25,000 model-planning cores, and 140 TH/s at
280 times that. EXP-029 changes none of those
figures: it measured no new per-unit rate and no
multi-machine aggregate. What it establishes is
narrower and necessary: IF machines are ever added,
the bookkeeping exists to add their rates honestly,
with unique coverage that cannot be inflated by
duplicates, restarts or reassignment, and with the
coordination cost measured at least at prototype
scale. No claim that adding machines reaches
500 GH/s or 140 TH/s is made, because the gap model
does not support one: at measured per-unit rates the
unit counts are the obstacle, and this experiment
does not move per-unit rates at all.

## 10. Per-item verdicts

| Item | Verdict |
|---|---|
| Nonce-range allocation (tiled, exclusive leases) | PROVEN by construction and test (section 5) |
| Dynamic distribution (pull leases) | PROVEN in prototype (sections 5, 6) |
| Work stealing (shrink-before-grant) | PROVEN in prototype (targeted case plus campaign) |
| Duplicate-work prevention | PROVEN (construction, idempotence, accounting; duplicate case exact) |
| Template propagation on tip change | SPECIFIED with in-repo precedents; cross-machine latency UNVERIFIED |
| Failure recovery (worker death, coordinator restart) | PROVEN in prototype (targeted cases exact, campaign injections) |
| Telemetry and stale detection | PROVEN in prototype (targeted case); production shape exists in solo server accounting |
| Coordination overhead | MEASURED, local in-process prototype only; multi-machine UNVERIFIED |
| End-to-end regtest block | PASS, height 829, local in-process distribution |
| Centralised vs decentralised | FILED (section 8): centralised chosen on coverage safety |
| Scaling claim toward 500 GH/s or 140 TH/s | NONE MADE; gap model unchanged |

Predeclared criterion outcome: criteria 1, 3 and 4
met; criterion 2 met at the largest configuration
actually run (4 in-process workers, one host) with
all larger configurations explicitly UNVERIFIED and
carrying no numbers, as the criterion requires. The
linear-scaling clause of the hypothesis is therefore
UNVERIFIED beyond this host, and is recorded as such
rather than as confirmed. No integration; the
prototype stays in the research tree.
