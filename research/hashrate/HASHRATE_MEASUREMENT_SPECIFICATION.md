# Hashrate Measurement Specification

Deliverable: HASHRATE_MEASUREMENT_SPECIFICATION.md
(Master Assignment BR-010, honest hashrate measurement).
Date: 2026-11-15. Status: BINDING specification for every
rate this programme publishes, in any document, dashboard,
README or report. It codifies the EXP-017 decision
protocol, the EXP-031 environment discipline, the NOVA
repository audit's benchmark inventory (section 9), and
the Phase 001 statistical benchmarking framework
(research/phase001/STATISTICAL_BENCHMARKING_FRAMEWORK.md,
Deliverable 18), which it incorporates. Where this
specification and an older document disagree, this
specification governs the labelling of the number.

The governing principle: a number's category, host, kernel
and session are part of the number. A rate stated without
them is defective and must not be published.

## 1. Benchmark categories (exact definitions)

Six categories, never interchangeable, never reported
under each other's names.

- Category A: ordinary SHA-256. Throughput of the single
  SHA-256 compression function over unstructured input.
  No production consumer in this programme needs it.
- Category B: ordinary double SHA-256. SHA-256 applied
  twice over unstructured input of arbitrary length, with
  no header framing, no reusable state and no target
  comparison.
- Category C: exact 80-byte header SHA-256d. The full
  Bitcoin block-header computation: SHA256d over the
  exact serialized 80-byte header, one candidate, full
  framing, no state reuse across candidates and no target
  comparison.
- Category D: mining kernel with reusable header state
  and target comparison. A kernel entry point (batch or
  search form) over fixed header material, with midstate
  or template state reused across candidates and the
  target comparison performed in-kernel or in the counted
  call. Most kernel comparisons in this programme are
  category D in batch form; a search entry measured over
  a fixed header without the surrounding engine is the
  search form of D unless it runs through the production
  engine, in which case it is E.
- Category E: complete production search. The production
  engine's search path end to end at the engine boundary:
  dispatch, the native counted search call, candidate
  extraction and verification machinery, and the engine's
  accounting, over real header material. Measurements
  through ComputeEngine.search_first_counted on real
  engine instances are category E. Component measurements
  inside the pipeline (candidate construction, span-size
  interaction, confirmation cost) are E components and
  must be labelled as components, never summed into an E
  rate and never presented as F.
- Category F: end-to-end pipeline. Template acquisition
  from a node, block and coinbase construction, search,
  candidate verification, and submission, timed as one
  pipeline. F is the only category that may be called
  "end to end".

Related quantities that are not hash rates at all, and
must never be reported as one:

- Candidate-construction rate: candidates constructed per
  unit time by the template and coinbase path (the
  EXP-025 steps500 figure, pooled 23.02x, is a ratio on
  this path). It is reported as a construction figure with
  its shape named, never in H/s as a mining rate.
- Backend computations: lane computations including dummy
  lanes of partial groups (for a 16-lane wave backend,
  ceil(span/16)*16 per span; for AVX2, ceil(span/8)*8).
  Backend counts exceed unique candidates by
  construction and are reported under their own name in
  the Task 003.9 accounting set.
- Verification work: candidate re-verification through
  the production verification path, reported separately
  from search rate; it is on the critical path of any
  found block and is part of category F.
- Model and planning figures: per-core model bands and
  fleet extrapolations are theoretical. They are labelled
  theoretical wherever they appear and never enter a
  measured table.

## 2. Harness inventory: what exists today, per category

From the NOVA repository audit (section 9), verified
against source. This inventory is the current truth; the
gaps in it are stated plainly because the Master
Assignment requires them stated.

| Category | Harnesses that exist | State |
|---|---|---|
| A | None | ABSENT BY DESIGN. No harness measures single SHA-256 throughput as a headline number, and none presents one as a mining rate. No A claim exists or is needed. |
| B | Reference loops only: the raw hashlib loop inside mining/cpu/miner.py benchmark(); hashlib reference arms inside larger harnesses | Present only as a reference inside other measurements. Never presented as mining throughput. |
| C | Component benches: research/sha256d/experiments/bench_harness.py (counted batch2 entries on the genesis header, count-1 latency); the SHA-NI benches in research/sha256d/experiments/h02_shani/ (header inputs, C/D boundary); Makefile bal-miner bench (fixed header scan, C/D) | Measured only as components inside C/D work. No standalone C headline rate is published. |
| D | gpu/benchmark.py (ComputeEngine.benchmark_report: batch_search over a fixed 80-byte header, full enumeration with in-kernel target comparison, Task 003.9 accounting); the EXP-017 paired benches of phase6 and phase6b (batch arms); the EXP-032 batch arms; the dashboard and agent benchmark figure (ComputeEngine.benchmark(), which is category D and is displayed under the bare label "benchmark": a labelling defect recorded in the audit) | The programme's strongest evidence base. Every VERIFIED kernel ratio in section 7 batch scope comes from here. |
| E | EXP-032 search arms through real ComputeEngine instances; bench_exp009_pipeline.py (candidate construction cost, span-size interaction, candidate confirmation cost, GBT round trip, stub-RPC mine_cycle split: E components, measured separately and labelled as such in its own docstring); the EXP-031 load probe (search_first_counted under controlled load, a load probe, not a rate claim); the live miner's status rate (computed from search_first attempted counts, a genuine E rate, observed not benchmarked) | Component-labelled measurements and live observations exist. No single controlled E benchmark campaign is published as the system rate; the EXP-032 search arms are the controlled E evidence. |
| F | None | MISSING AS A MEASUREMENT. No benchmark anywhere in the tree measures F as a rate. End-to-end correctness is proven by regtest tests (functional, un-timed) and by live pool operation. F is validated, not benchmarked. Building the F harness is an open Master Assignment item (BR-010); until it is built and run under this specification, no F rate may be quoted by anyone, in any document. |

The one historical mislabel, kept as the standing
example: the README's "End to end engine rate 6,617,558
H/s" is a category D batch_search figure from the
C-backend era, two backend generations stale. It is not
an end-to-end rate and must not be cited as one.

## 3. The decision rule: the EXP-017 paired protocol

Verdicts (VERIFIED IMPROVEMENT, and any integration
decision that rests on a rate) use the EXP-017 protocol,
adopted 2026-11-14, unchanged:

1. At least 3 independent sessions per comparison.
2. Paired blocks of 65,536 hashes; both arms perform the
   same work per block; every timed call asserts
   attempted == 65,536 (or the block's declared size)
   under the backend's accounting rule.
3. Randomized AB/BA arm order within each session.
4. Covariates sampled around every counted call: steal
   and runnable load (the EXP-017 driver samples
   /proc/stat steal jiffies and load averages per call).
5. The verdict statistic is the predeclared one: paired
   log-ratios with an OLS adjustment on the
   steal-difference, runnable-load-difference and order
   covariates, and a pairs bootstrap confidence interval
   (the EXP-017 analyzer's own code; EXP-032 imported
   that code rather than reimplementing it, which is the
   required pattern).
6. A VERIFIED IMPROVEMENT requires the adjusted
   confidence interval to lie entirely above 0 in every
   session and in the pooled estimate. A result that
   depends on one session is not a result (EXP-024 design
   B: pooled 1.169x with only 1 of 3 sessions supporting
   it, correctly not integrated).
7. Full correctness gates before any benchmark counts:
   byte-exact differentials against the reference
   implementation (hashlib), zero mismatches, including
   boundary counts, odd counts, thread counts and a range
   ending exactly at 2^32 where the kernel claims the
   full space.
8. Before integration: a fresh regtest block mined
   through the candidate path, and after integration an
   independent audit by an agent that did not author the
   change (the 2026-11-14 rule), before anything else
   moves.

Benchmarks run one at a time on this host, never in
parallel: parallel runs corrupt the statistics on a
shared-CPU VM. A run contaminated by a co-running
benchmark is discarded, not averaged.

## 4. Required metrics per run

Every benchmark run records, at minimum:

- Median (primary), minimum, maximum, and variance or
  interquartile range of the per-block rates; per-session
  verdicts reported individually before pooling; pooled
  estimates with bootstrap confidence intervals.
- Correctness counters: differentials run and mismatches
  (must be zero).
- Thread scaling: rates at 1, 2 and N threads for any
  multi-threaded arm, so saturation is visible rather
  than assumed (EXP-031 found saturation at 2 threads on
  this VM class; a scaling claim without the 1-thread
  anchor is invalid).
- CPU utilization over the run window and the thread
  count used.
- Work coverage: distinct headers hashed in the run, by
  construction of the paired blocks, never estimated from
  time multiplied by rate.
- Duplicate work: counted and reported as its own
  counter, per the EXP-035/EXP-037 accounting separation.
  Repeated computations are recorded, never credited as
  coverage.
- Candidate verification cost, where the measured path
  includes verification, reported separately from the
  search rate.
- Instruction-level counters: only where counters are
  actually accessible. On this VM class they are NOT
  (perf_event_paranoid 4, perf_event_open EPERM;
  EXP-031), so IPC and per-instruction rate claims are
  prohibited here; operation counts come from the census
  and SMT records (EXP-020), not from counters.

## 5. Environment manifest (required with every run)

Every session file carries a manifest. A rate without a
manifest is UNVERIFIED.

- Host CPU model and full relevant flag list. The lab has
  run two materially different hosts (AMD EPYC 9D25 with
  full AVX-512 plus SHA-NI; Intel Xeon Platinum 8321HC
  with AVX-512F/BW/VL/VNNI and no SHA extensions); results
  do not transfer silently between them.
- VM characterization per EXP-031: claimed vCPUs,
  measured effective CPUs, baseline busy fraction, load
  average, steal range, memory. On this VM class: 4
  claimed, about 2 effective, baseline 61 to 64 percent
  busy, load 7.0 to 7.5 (1 minute), steal 1.4 to 2.7
  percent.
- Contention state: what else was running (live miner,
  syncing node, other work), stated, never omitted. All
  EXP-031 and EXP-032 rates are alongside-production
  rates and say so.
- Compiler and exact build flags. Production vector
  libraries: restricted -mavx512f -mavx512bw, never
  -march=native. The C batch library's -march=native is
  by design and must be recorded as such. Research builds
  record their own flag sets (EXP-032: AVX2 library
  -mavx2 only; SHA-NI library -msha -mssse3; flags-search
  library the production restricted set).
- The backend actually selected by the production probe,
  not the intended one, and the dispatch order in force.
- Git head or content hash of every source file in the
  measured path, and of the harness itself (the EXP-032
  session files carry source and binary sha256 manifests;
  that is the required pattern).

## 6. Raw artifact retention

- Session outputs are append-only files in the
  experiment's RAW_RESULTS or benchmarks directory, never
  overwritten; a rerun creates a new file. (The one
  historical violation, EXP-011's overwritten session A
  JSON, is why that figure is excluded from every model:
  it survives as transcription only and is not evidence.)
- The manifest of section 5 is stored with the raw
  numbers, in the same file or a sibling with a shared
  session identifier.
- Published summaries cite the raw file paths. Any number
  that cannot be traced to a raw file is withdrawn.
- Failures and contaminated runs are retained and
  labelled, not deleted: EXP-032 keeps its first gates run
  (a gate-density defect in the harness, kernels
  exonerated, rerun passes) and EXP-028 keeps its first
  probe record (a wrong harness expectation) for exactly
  this reason.
- Failed and negative arms are part of the record. A
  campaign that reports only its winning arm is defective
  under this specification.

## 7. Labelling rules

Every published figure, in any document, dashboard,
README, report or message, carries:

1. Its category (A to F, or the named non-rate quantity:
   construction rate, backend computations, verification
   cost, theoretical model).
2. Its host (CPU model; guest where applicable).
3. Its kernel or backend identity, and its scope (batch
   or search) where the category admits both.
4. Its session or observation basis: the experiment and
   session files for a protocol figure; "single live
   session observation, contended, not a benchmark" for a
   live rate.
5. Its thread count.
6. Its evidence class: VERIFIED (EXP-017 protocol,
   criterion met), measured observation, measured
   (non-protocol), derived, estimated, theoretical, or
   UNVERIFIED.

Additional standing rules:

- Algorithmic gains are claimed at the category measured.
  Promotion of a D gain to an E or F claim requires
  measuring at that category. (The EXP-022 flags gain is
  a batch-scope D figure; EXP-032 measured its search
  form at E and it did not survive. The EXP-025 steps
  figure is a construction ratio and is never a hash
  rate.)
- Same-host pairing: an algorithmic claim is only ever a
  ratio between two arms measured on the same host in the
  same sessions. Cross-host ratios are reported, if at
  all, as UNVERIFIED beyond correctness.
- Compiler separation: if two arms differ in compiler or
  flags, the comparison measures the pair (algorithm,
  toolchain) and the report must say so.
- Environment covariates: a session whose covariates
  depart materially from the campaign norm is flagged in
  the raw file, and its inclusion or exclusion is decided
  before pooling, never after seeing the verdict.
- Host changes reset campaigns: a campaign spanning a VM
  replacement that changed the CPU model is two
  campaigns; pooling across the change is prohibited.
- A one-thread result is never compared with a
  multi-thread result without the distinction stated in
  the same sentence as the ratio.

## 8. Prohibition list

The following are prohibited in any programme output.
Each corresponds to a real incident or near-miss in the
programme record, which is why they are rules and not
advice.

1. Reporting a theoretical aggregate (core-count
   extrapolations, model-band products, summed per-unit
   rates) as a measured result.
2. Labelling a category D figure "end to end", or
   presenting any figure at a higher category than the
   one measured.
3. Reporting a candidate-construction rate as a hash
   rate, in H/s or as a multiplier on a hash rate.
4. Reporting backend computations (including dummy
   lanes) as unique candidate coverage, or counting
   duplicate work as coverage in any form.
5. Quoting a rate without its category, host, kernel,
   session basis and thread count.
6. Pooling measurements across hosts, across a host
   change, or across contaminated sessions.
7. Integrating, or claiming, an improvement on a
   microbenchmark alone, without the full EXP-017 gate
   set of section 3.
8. Deleting or omitting negative arms, failed sessions
   or contaminated runs from a campaign record.
9. Presenting a benchmark median without its spread and
   its per-session verdicts.
10. Presenting a live observation (a miner status rate, a
    dashboard figure) as a benchmark result, or a
    benchmark result as a live rate.
11. Confusing pool shares with accepted blocks, or a
    share rate with a block-discovery rate. Block claims
    require chain evidence; shares are category E/F
    operational events, not blocks.
12. Claiming any category F rate before an F harness
    exists and has been run under this specification.
    Today none exists.

## 9. Current verified rate table (as of this specification)

All VERIFIED figures in the programme, with category,
host and source. Every entry is an EXP-017 protocol
result on the AMD EPYC 9D25 guest unless it says
otherwise; all are contended-VM measurements (live miner
and node running) unless the entry is a live observation,
which is labelled as such. Ratios only: absolute session
medians live in the cited raw records, because on this VM
an absolute rate without its session covariates is not
reproducible.

| Figure | Ratio and CI | Category and scope | Source |
|---|---|---|---|
| v512 AVX-512 MB vs production C | pooled 3.55x [3.17, 3.97] | D, batch (counted batch entries, 2 threads) | EXP-017 |
| SHA-NI H-01 streams 4 strided vs production | pooled 2.80x [2.53, 3.09] | D, batch (2 threads) | EXP-017 decision set (EXP-003/005 family) |
| EXP-022 flags batch vs production batch | pooled 1.441x [1.261, 1.645] | D, batch only; production integration benchmark | PRODUCTION_INTEGRATION_LOG Entry 3 |
| EXP-024 flags batch rerun vs production batch | pooled 1.649x [1.466, 1.860] | D, batch only (reproduction of EXP-022 in batch scope) | EXP-024 |
| EXP-024b design C mask search vs production search | pooled 1.398x [1.242, 1.578] | E, search scope (2 threads); VERIFIED, not integrated | EXP-024b |
| EXP-026 C2 DualMask vs production v512 search | pooled 1.718x [1.511, 1.955] | E, search scope (2 threads); integrated as v512dual | EXP-026 |
| EXP-026 C2 DualMask vs its strongest ingredient (mask C) | pooled 1.444x [1.288, 1.618] | E, search scope (2 threads) | EXP-026 |
| EXP-026 C2 DualMask vs production v512 search, 1 thread | pooled 1.967x | E, search scope (1 thread) | EXP-026 |
| AVX2 MB batch vs production C batch | pooled 1.409x [1.340, 1.480] | D, batch (2 threads); VERIFIED, not dispatched | EXP-032 |
| SHA-NI H-01 streams-4 batch vs production C batch | pooled 2.861x [2.671, 3.089] | D, batch (2 threads); VERIFIED, not dispatched | EXP-032 |
| Production v512dual search vs production C search | pooled 6.781x [6.154, 7.467] | E, complete production search through ComputeEngine (2 threads) | EXP-032 |

Measured negatives and nulls that bound the same space
(recorded so the table cannot be read as wins only):
production SHA-NI intrin batch vs C batch 0.517x
[0.497, 0.536], ESTABLISHED NEGATIVE (EXP-032); flags-form
search entry vs v512 search 0.967x [0.885, 1.059], NOT
SIGNIFICANT (EXP-032); EXP-020 P6C-007 single-ternlog Maj
variant 1.051x [0.935, 1.182], NOT SIGNIFICANT, not
integrated; EXP-024 design B 1.169x, criterion failed;
EXP-025 family500 construction ratio 1.083x, NOT VERIFIED.

Absolute anchors, measured, host-bound (not protocol
verdicts): production C batch 1 thread median 1,314,704
H/s and hashlib 304,444 H/s (EXP-000, AMD guest, category
D and B-shaped reference respectively); H-01 streams 4
per-worker 1-thread median 3.30M H/s (EXP-003, AMD);
EXP-031 load probe through the production engine on
v512dual, 1 thread 5.19 to 5.50M H/s, 2 threads 9.36 to
11.21M H/s, 4 threads 9.92 to 10.25M H/s (category E load
probe, alongside production); EXP-032 production dual
search session medians 8.24M to 14.78M H/s at 2 threads
(category E); live miner session observations 20.6 to
21.5M H/s on v512dual (category E observations, single
live sessions under contention, not benchmarks).

Not in this table, by rule: the EXP-025 steps500 pooled
23.02x (a candidate-construction ratio, section 1); the
EXP-011 dual-batch session figure (raw record
overwritten, excluded as evidence); every theoretical
model-band figure (the 6 to 25M H/s per-core band and the
20M H/s planning figure are theoretical and live in the
gap model under that label); any GPU figure (no device
exists; none has ever been measured).

## 10. Standing state, stated plainly

- Categories A: unmeasured by design. B: reference only.
  C: components only. D: strong protocol evidence. E:
  controlled search-arm evidence (EXP-032) plus labelled
  component measurements and live observations. F: no
  measurement exists.
- The targets (500 GH/s minimum, 140 TH/s larger) are
  system objectives. System counts derived from the rates
  in section 9 are arithmetic under stated assumptions
  (research/cpu_architecture/VM_RESOURCE_CAPACITY_REPORT.md,
  section 9) and are never measured performance.
- This specification is amended only by a recorded
  decision that names the section changed and the
  evidence for the change. A number published in
  violation of it is withdrawn, not defended.
