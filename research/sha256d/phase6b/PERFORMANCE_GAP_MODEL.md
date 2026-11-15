# Phase 6B Performance Gap Model

Purpose: state what the two programme objectives
require, level by level, from recorded evidence only.
Every figure is labelled measured, reproducibly
measured, derived, estimated or theoretical. This
model quantifies the gap; it does not declare the
targets impossible and does not claim scaling alone
solves them.

Objectives (standing, full height): 500 GH/s minimum
system objective; 140 TH/s larger objective. 140 TH/s
is 280 times 500 GH/s.

Initial version: 2026-11-14 (Assignment A). Sources are
the experiment registry
(research/sha256d/extreme_optimization/EXPERIMENT_REGISTRY.md),
the Phase 6 records (research/sha256d/phase6/), and the
live miner status read during the audit. No figure in
this version comes from a new benchmark run by the
audit; the audit ran no benchmarks.

Change note: an Assignment G update dated 2026-11-15
is appended as section 5 below. Sections 1 to 4 above
are the initial version, unchanged. The update does
not silently rewrite them; where it confirms,
supersedes or adds to an initial figure, it says so
explicitly and shows the arithmetic.

## 1. Rates used, with evidence class

| Level | Rate | Class | Source |
|---|---|---|---|
| Live complete system, this VM (miner session rate, exact-attempt accounting after the N-1 fix) | 11.15 MH/s observed 2026-11-15T04:34Z (status events 11.08 to 11.28 MH/s in the same window) | Measured (single live session observation, contended VM, not a benchmark) | .local/mainnet-status.txt and evidence/mainnet-live.jsonl status events read in the Assignment A audit |
| Verified kernel throughput, AVX-512 MB, 2 threads, counted batch | Session medians 6.19 to 6.64 MH/s across the three EXP-017 production-vs-MB sessions; control-arm MB medians 5.76 to 6.68 MH/s | Reproducibly measured (EXP-017 protocol, 3 sessions, 160 pairs each) | phase6/benchmarks/exp017/analysis_20261114T145128Z.json |
| Verified kernel throughput, AVX-512 MB, 2 threads, earlier harness | Median 6.53 MH/s combined session | Measured (median basis, ranges overlapped; superseded as decision evidence by EXP-017) | Registry EXP-007 |
| Best verified per-worker rate (one thread, one kernel) | 3.30 MH/s (SHA-NI streams=4, EXP-003); MB confirmation per-worker 3.20 MH/s (EXP-007) | Measured | Registry EXP-003, EXP-007 |
| Per-thread MB rate implied by EXP-017 2-thread medians | About 3.15 MH/s | Derived (half of the 2-thread session medians; assumes even split, stated as an assumption) | Derived from the EXP-017 row above |
| Production C backend, 2 threads (pre-v512 baseline) | Median 1.63 MH/s (EXP-000); EXP-017 production arm medians 0.81 to 0.99 MH/s under heavier IBD contention | Reproducibly measured | Registry EXP-000; EXP-017 analysis |
| EXP-017 decision result | MB vs production pooled 3.55x (CI 3.17x to 3.97x), significant in every session; streams=4 strided vs production pooled 2.80x (CI 2.53x to 3.09x) | Reproducibly measured | Registry EXP-017 |
| Per-core model band (implementation families priced in the Phase 6 ceiling work) | 6 to 25 MH/s per physical core; 20 MH/s planning figure | Theoretical (model, not measurement) | phase6/PERFORMANCE_TARGET_MODEL.md and the ceiling records it cites |

Not used: the EXP-011 session A dual-batch figure
(8.27 MH/s, single session, unreproduced, raw session
JSON overwritten before archiving). Using it would
flatter every count below. It stays excluded until a
reproduction exists.

Environment note: all measured rates are from this VM
class (about 1.5 effective shared CPUs, 4 vCPUs, live
node in initial block download during most sessions).
They are not universal statements about any processor.
The audit host record is in CURRENT_PRODUCTION_AUDIT.md.

## 2. Required unit counts (arithmetic from section 1)

Assumptions stated once: sustained rates equal the
labelled rates with no thermal or contention decay;
fleet efficiency 100 percent (a real deployment
multiplies counts by 1/efficiency); power, cost and
availability are out of scope and are not zero in
reality.

For 500 GH/s (5.0e11 H/s):

| Rate basis | Units required |
|---|---|
| Live system as observed (11.15 MH/s) | About 44,900 such systems |
| MB kernel at 2 threads (6.53 MH/s) | About 76,600 two-thread workers |
| Per-worker best measured (3.30 MH/s) | About 151,500 workers |
| Per-thread derived MB (3.15 MH/s) | About 158,700 threads |
| Production C at EXP-000 (1.63 MH/s) | About 307,200 two-thread workers |
| Model planning core (20 MH/s, theoretical) | 25,000 cores |
| Model band low core (6 MH/s, theoretical) | About 83,300 cores |
| Complete CPU, 64 cores at model planning rate (1.28 GH/s, theoretical) | About 391 CPUs |

For 140 TH/s (1.4e14 H/s), multiply the 500 GH/s
counts by 280:

| Rate basis | Units required |
|---|---|
| Live system as observed | About 12.56 million such systems |
| Per-worker best measured | About 42.4 million workers |
| Model planning core | 7.0 million cores |
| Complete CPU at model planning rate | About 109,400 CPUs |

Gap factors from the live system as observed:
500 GH/s is about 44,900 times the observed live rate;
140 TH/s is about 12.56 million times it. These are
arithmetic gaps, not verdicts.

## 3. What the model says, exactly

1. At every rate this programme has measured, and at
   the theoretical model band's optimistic planning
   figure, both objectives are fleet-scale numbers.
   That is the size of the gap, stated as counts.
2. The gap has two independent factors: a per-unit
   factor (software and per-core rate; research
   addresses this) and a deployment factor (units;
   only resources address this). Neither factor may be
   silently borrowed against the other.
3. A breakthrough, in this model's terms, is a
   per-unit rate outside the model band's assumptions:
   a computation graph whose per-core rate the ceiling
   sets do not price. The model bounds what the known
   families do; it does not bound what a Track B result
   could do.
4. EXP-022 (flags batch, 1.82x in batch scope) and
   EXP-023 (candidate construction, 18.49x per
   extranonce step at 500 transactions) do not change
   any rate in section 1: neither is a search-path hash
   rate, and neither is integrated. They enter this
   model only if EXP-024 or an integration changes a
   measured search or system rate.

## 4. Maintenance rule

When a VERIFIED IMPROVEMENT changes any rate in
section 1, this model is recomputed and the change is
recorded here with the experiment number, the evidence
file, and the evidence class. Model-band changes
require a ceiling-report revision, not an edit here
alone.

## 5. Update: 2026-11-15 (Assignment G, Phase 6B evidence)

Provenance and method: this update uses Phase 6B
evidence only, from EXP-024, EXP-024b, EXP-025,
EXP-026, EXP-027, EXP-028 and EXP-029 as recorded in
phase6b/EXPERIMENT_RESULTS.md and the per-experiment
files named below. This assignment ran no benchmarks.
Every figure below is labelled measured,
reproducibly measured, derived, estimated, theoretical
or unverified. The objectives stay at full height:
500 GH/s minimum system objective and 140 TH/s larger
objective, with 140 TH/s equal to 280 times 500 GH/s
(1.4e14 / 5.0e11 = 280, derived arithmetic).

### 5.1 Live system refresh (read only, no change to the basis)

| Observation | Rate | Class | Source |
|---|---|---|---|
| Live complete system, this VM, refreshed observation: heartbeat 2026-11-15T06:15:24Z, status snapshot at session t = 85 s, backend v512, shares accepted total 198 | 8,465,993 H/s (about 8.47 MH/s) | Measured (single live session observation, short early-session window, contended VM, not a benchmark) | .local/mainnet-status.txt and .local/heartbeat.json read read-only in Assignment G |

This refreshed observation does not replace the
section 2 basis. A single 85 second early-session
reading is not comparable to the Assignment A window,
and session rates on this contended VM vary between
sessions and restarts. Section 2 counts therefore
stay on the Assignment A basis (11.15 MH/s observed
2026-11-15T04:34Z) so that every Phase 6B comparison
remains on one stated basis. For completeness only,
the arithmetic on the refreshed reading alone would
be 5.0e11 / 8.465993e6 = about 59,060 such systems
for 500 GH/s (derived from a single short
observation; not the headline basis, and not used in
any table below).

Production status at this update: production still
runs the single-batch v512 kernel. None of EXP-024,
EXP-024b, EXP-025 or EXP-026 is integrated. No
Phase 6B result therefore changes the live-system
equivalents row in section 2.

### 5.2 New Phase 6B evidence, by experiment

| Experiment | Figure | Class | Source |
|---|---|---|---|
| EXP-024 batch rerun: flags batch vs production batch, density 0, 2 threads | Pooled 1.649x, CI [1.466, 1.860], significant in every session | Reproducibly measured (EXP-017 protocol; reproduces EXP-022 in batch scope only) | phase6b/EXP024_MASK_SEARCH.md; phase6b/EXPERIMENT_RESULTS.md, EXP-024 record; phase6b/benchmarks/exp024/ |
| EXP-024 search, predeclared primary: design B vs production search, density 0, 2 threads | Pooled 1.169x, CI [1.031, 1.327], significant in 1 of 3 sessions; criterion NOT met; classification PROMISING HYPOTHESIS at the time | Reproducibly measured (criterion failed) | Same EXP-024 sources as above |
| EXP-024b search: design C mask search vs production search, density 0, 2 threads, C predeclared as primary | Pooled 1.398x, CI [1.242, 1.578], pairs won 68.3 percent, significant in every session and pooled; VERIFIED IMPROVEMENT (search scope) | Reproducibly measured | phase6b/EXP024_MASK_SEARCH.md, EXP-024b sections; phase6b/EXPERIMENT_RESULTS.md, EXP-024b record; phase6b/benchmarks/exp024b/ |
| EXP-024b search, supporting: design C vs production, density 0, 1 thread | Pooled 1.463x, CI [1.301, 1.648], significant in every session | Reproducibly measured | Same EXP-024b sources as above |
| EXP-024b interleave: design C over design B, same process | Pooled 1.011x, CI [0.895, 1.140], pairs won 50.0 percent, null in every session | Reproducibly measured (null result) | Same EXP-024b sources as above |
| EXP-025 steps500: repaired cache vs uncached build_candidate, steps shape, 500 transactions | Pooled 23.02x, CI [20.22, 25.93], significant in every session and pooled; VERIFIED on the candidate-construction path only (see section 5.3) | Reproducibly measured (construction path, not hash rate) | phase6b/EXP025_CACHE_CORRECTNESS.md; phase6b/EXPERIMENT_RESULTS.md, EXP-025 record |
| EXP-025 family500: repaired cache vs uncached build_candidate, family shape, 500 transactions | Pooled 1.083x, CI [1.022, 1.151], significant in 1 of 3 sessions; NOT VERIFIED under the predeclared rule | Reproducibly measured (criterion failed) | Same EXP-025 sources as above |
| EXP-025 identity cost: one sibling identity recomputation vs one full uncached build, 500 transactions | 3.573 ms median vs 4.499 ms median; 3.573 / 4.499 = 0.794, about 79 percent | Measured (medians, this host) | phase6b/EXP025_CACHE_CORRECTNESS.md |
| EXP-026 C2 DualMask vs production search, density 0, 2 threads | Pooled 1.718x, CI [1.511, 1.955], significant in every session and pooled; VERIFIED IMPROVEMENT (search scope) | Reproducibly measured | phase6b/EXP026_AVX512_EXECUTION.md; phase6b/EXPERIMENT_RESULTS.md, EXP-026 record |
| EXP-026 C2 DualMask vs its strongest single ingredient (mask C), density 0, 2 threads | Pooled 1.444x, CI [1.288, 1.618], significant in every session and pooled | Reproducibly measured | Same EXP-026 sources as above |
| EXP-026 C2 DualMask vs production search, density 0, 1 thread | Pooled 1.967x, significant in every session and pooled | Reproducibly measured | Same EXP-026 sources as above |
| EXP-027 Track B representation search | No representation outside the EXP-020 vocabulary beat the incumbent cones; every space closed at its stated scope except one open sub-space (non-sharing cross-round restructuring, blocker: search-space size) | Derived (proof, counterexample and costing record; no kernel compiled, no benchmark run or claimed) | phase6b/EXP027_COMPUTATION_REPRESENTATIONS.md; phase6b/EXPERIMENT_RESULTS.md, EXP-027 record; phase6b/proofs/ |
| EXP-028 AVX-512 F+BW | Verified (dispatch and correctness) on two hosts: AMD EPYC 9D25 and Intel Xeon Platinum 8321HC | Reproducibly measured (verification across two hosts) | phase6b/EXP028_CPU_ARCHITECTURES.md; phase6b/EXPERIMENT_RESULTS.md, EXP-028 record; phase6b/benchmarks/exp028/ |
| EXP-028 SHA extensions (SHA-NI) | Measured in research on AMD (EXP-002, EXP-003, EXP-005, EXP-021 figures already cited in the registry); Intel SHA specified only | Measured (AMD research) / Unverified (Intel SHA, no rate) | Same EXP-028 sources as above |
| EXP-028 AVX2 and ARMv8 SHA2 plus NEON | Specified, no kernel verified on a target machine, no rate quoted | Unverified | Same EXP-028 sources as above |
| EXP-029 allocator coverage | 120 randomised trials; completed intervals union exactly to the declared range, pairwise disjoint, in every trial; 20,474 repeated computations across 67 trials all accounted and none inside unique coverage | Proven by test (property test record, not a rate measurement) | phase6b/EXP029_DISTRIBUTED_EXECUTION.md; phase6b/EXPERIMENT_RESULTS.md, EXP-029 record; phase6b/benchmarks/exp029/ |
| EXP-029 multi-machine scaling | No multi-machine run exists | Unverified (no numbers) | Same EXP-029 sources as above |

Consequences read directly from that table:

1. EXP-024b supersedes the EXP-024 search verdict in
   part: design C is now VERIFIED in search scope,
   where EXP-024 left mask search PROMISING. The
   interleave null result (1.011x) proves the EXP-024
   B/C divergence was a per-process layout and
   scheduling effect, not a code effect, and that
   adaptive extraction (the B/C design difference)
   adds nothing measurable; the mask compare form
   shared by B and C carries the gain. EXP-024's
   batch result (1.649x) stands as a batch-scope
   reproduction of EXP-022 and is not a search rate.
2. EXP-026 DualMask is the largest verified
   search-scope ratio in Phase 6B and the leading
   integration candidate on the record. It is NOT
   integrated, so it changes no live rate here; it
   enters the model only as the labelled derived
   scenario in section 5.4.
3. EXP-027 changes no per-core rate. The per-core
   model band in section 1 therefore stays exactly
   as it was: 6 to 25 MH/s per physical core, 20 MH/s
   planning figure, class theoretical (model, not
   measurement).
4. EXP-028 widens the set of machines the software
   can in principle run on, and verifies the current
   family on two hosts. Portability adds no verified
   rate: AVX2, ARMv8 and Intel SHA carry no rates in
   this model.
5. EXP-029 proves allocator coverage by test and
   nothing more about scale. Distributed scaling
   remains a modelled path, not a measured one: the
   section 2 fleet counts are arithmetic from
   per-unit rates, not a demonstrated distributed
   system. Local prototype note (kept out of every
   equivalents table, by rule): in a local in-process
   prototype on this host only, EXP-029 recorded
   460,929 unique/s at 1 worker, 477,355 at 2 workers
   and 493,484 at 4 workers with chunk 10,000, over
   120,000 hashlib full-scan nonces (measured, local
   prototype only; source: phase6b/EXPERIMENT_RESULTS.md,
   EXP-029 record). Those figures price thread
   contention on this oversubscribed guest and are
   not distributed-system results.

### 5.3 Candidate construction is not hash rate (EXP-025)

The EXP-025 steps500 figure, pooled 23.02x, is a
per-extranonce-step candidate-construction rate: how
much faster a repaired cache constructs the next
candidate than an uncached build_candidate call. It
is never a hash rate, never a search rate, and it
enters no equivalents count in this model. The same
applies to the earlier EXP-023 construction figures
cited in section 3 of the initial version. EXP-025
is ACCEPTED as a correctness repair (all six
predeclared elements pass; source:
phase6b/EXP025_CACHE_CORRECTNESS.md), and the cost
of doing the identity completely is stated honestly:
one full identity recomputation costs about 79
percent of one uncached build at 500 transactions
(3.573 ms / 4.499 ms = 0.794, measured medians),
which is why the family500 shape keeps only 1.083x
and is NOT VERIFIED while the steps shape, the shape
the live GBT loop exercises, keeps the verified
23.02x on its construction path.

### 5.4 DualMask derived scenario (projection, not a measurement)

Precondition, stated plainly: this scenario exists
only if the owner decides to integrate EXP-026 C2
DualMask, and only if the kernel-scope ratio then
held at whole-system level. Neither has happened.
Production still runs the single-batch v512 kernel.
Every figure in this section is class derived
(projection from a kernel-scope ratio), not measured
at system level, and no figure here replaces
section 2.

Arithmetic, shown in full. Kernel-scope input:
1.718x (reproducibly measured, EXP-026, density 0,
2 threads, vs production search).

For 500 GH/s (5.0e11 H/s):

| Basis | Current (production, section 2) | DualMask scenario (derived projection) | Arithmetic |
|---|---|---|---|
| Live-system equivalents (basis 11.15 MH/s) | About 44,900 systems (5.0e11 / 11.15e6 = 44,843) | About 26,100 systems | 44,900 / 1.718 = 26,135; cross-check 5.0e11 / (11.15e6 x 1.718) = 26,102; both round to about 26,100 |
| Model planning cores (20 MH/s per core, theoretical) | 25,000 cores (5.0e11 / 20e6 = 25,000) | About 14,550 cores | 25,000 / 1.718 = 14,552 |

For 140 TH/s (1.4e14 H/s), multiply the 500 GH/s
counts by 280 (derived from the standing 280x
relation):

| Basis | Current (production, section 2) | DualMask scenario (derived projection) | Arithmetic |
|---|---|---|---|
| Live-system equivalents | About 12.56 million systems (44,843 x 280 = 12,556,054) | About 7.31 million systems | 26,102 x 280 = 7,308,560 |
| Model planning cores (theoretical) | 7.0 million cores (25,000 x 280 = 7,000,000) | About 4.07 million cores | 14,552 x 280 = 4,074,560 |

Even under this projection, both objectives remain
fleet-scale numbers. A 1.718x kernel-scope gain, if
it held at system level, divides the counts by
1.718; it does not change the order of magnitude of
the gap, and it is not evidence that the ratio will
hold at system level.

### 5.5 Headline equivalents, restated after Phase 6B

Current production basis (unchanged by Phase 6B,
because nothing from Phase 6B is integrated):

| Objective | Live-system equivalents (11.15 MH/s basis, measured observation) | Model planning cores (20 MH/s, theoretical) |
|---|---|---|
| 500 GH/s | About 44,900 systems | 25,000 cores |
| 140 TH/s | About 12.56 million systems | 7.0 million cores |

DualMask scenario (derived projection only, section
5.4; not the current system, not a measurement):

| Objective | Live-system equivalents | Model planning cores |
|---|---|---|
| 500 GH/s | About 26,100 systems | About 14,550 cores |
| 140 TH/s | About 7.31 million systems | About 4.07 million cores |

### 5.6 Exclusion restated

The EXP-011 session A dual-batch figure (8.27 MH/s,
single session, unreproduced, raw session JSON
overwritten before archiving) stays excluded from
this update for exactly the reason stated in
section 1. No Phase 6B experiment reproduces it, and
using it would flatter every count above.

### 5.7 Maintenance note for this update

Under the section 4 rule, no rate in section 1
changed in this update, because no Phase 6B result
is integrated into production. If the owner later
integrates DualMask (or any other verified Phase 6B
form), the model is recomputed from a fresh live
system observation and the EXP-017 record at that
time, and the change is recorded here with the
experiment number, the evidence file and the
evidence class. The DualMask scenario in section 5.4
is then retired or replaced by the measured result,
never silently promoted to a measured figure.

## 6. Post-integration note: 2026-11-15 (Assignment H)

Event: the owner decided on 2026-11-14 to integrate
EXP-026 C2 DualMask, and the integration executed
(PRODUCTION_INTEGRATION_LOG.md Entry 1; independent
audit DUALMASK_POST_INTEGRATION_AUDIT.md, verdict
PASS WITH NOTES, zero defects). Production now runs
the "v512dual" backend. This note is appended under
the section 5.7 maintenance rule; it does not
rewrite section 5, and the section 5.4 scenario is
retired in favour of the observation below, not
promoted to a measured figure.

Live observations on v512dual (class: measured
observation; single live sessions under contention
on this VM, not benchmarks): session rates of 21.4
to 21.5 MH/s in the integration record's deployment
reads and 20.6 MH/s in the audit's reads (status at
session t = 735 s). The range used below is 20.6 to
21.5 MH/s. First pool-accepted share on the new
backend at 2026-11-15T06:57:29Z; 205 accepted shares
at audit time.

Equivalents recomputed on the observed rate
(arithmetic shown; class: derived from measured
observations):

For 500 GH/s (5.0e11 H/s):

- At 20.6 MH/s: 5.0e11 / 20.6e6 = 24,272, about
  24,000 such systems.
- At 21.5 MH/s: 5.0e11 / 21.5e6 = 23,256, about
  23,300 such systems.

For 140 TH/s (1.4e14 H/s), 280 times the 500 GH/s
counts:

- At 20.6 MH/s: 1.4e14 / 20.6e6 = 6,796,117, about
  6.80 million such systems.
- At 21.5 MH/s: about 6.51 million such systems.

What did not change:

- The verified kernel-scope DualMask ratio remains
  1.718x (reproducibly measured, EXP-026, density 0,
  2 threads). The live observations above are not a
  controlled system-level measurement of that ratio;
  session rates on this contended VM vary between
  sessions and restarts (compare the section 5.1
  refresh reading of 8.47 MH/s on the previous
  backend in a short early-session window).
- The per-core model band is unchanged: 6 to 25 MH/s
  per physical core, 20 MH/s planning figure (class:
  theoretical). The planning-core counts therefore
  stand as in section 2 and section 5.5: 25,000
  cores for 500 GH/s and 7.0 million cores for
  140 TH/s.
- Both objectives remain fleet-scale. The
  integration divided the observation-based
  live-system equivalents by roughly 2 against the
  Assignment A observation (44,843 to 24,272 at the
  rates observed); it did not change the order of
  magnitude of the gap, and no figure in this note
  is a benchmark.
