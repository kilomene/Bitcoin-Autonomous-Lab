# Final Research Report: First Assignment of the Grand Mandate

Date: 2026-11-14. Scope: investigation and documentation
only. No production code was changed, no kernel was built
for this assignment, and the live miner, node, autopilot,
and keeper were not touched. Everything below rests on
the repo's existing records, cited per claim.

## 1. What was assessed

The complete repository was read for this assignment: the
production CPU path (mining/cpu/bal_batch.c,
bal_sha_intrin.c, bal_miner.c, bal_search.h, build.py,
miner.py), the dispatch layer (gpu/engine.py
ComputeEngine, tune_c_threads, the Task 003.9 accounting
definitions), the mining engines and runners
(mining/engine.py, mainnet_live.py, stratum_client.py,
solo_server.py, autopilot.py), the whole research/sha256d
tree including EXP-000 to EXP-003 and their JSON records,
the h02_shani experiment directory, results/RESEARCH.md,
and docs/. The eleven documents in this directory are the
assessment's product.

## 2. Assessment headline

The production mining path is: template (GBT longpoll or
Stratum job), validation and candidate construction in
Python, a per-template 64-round midstate, counted search
in a C library that wraps OpenSSL's SHA-NI compression
(two whole-block Transform calls per nonce), independent
candidate confirmation, and submission gated on node
acceptance. Time goes where the measurements say it goes:
essentially all of it inside the per-nonce compression
and the work around it. Per-span boundary cost amortizes
to about 0.003 percent at live span sizes; per-candidate
verification (3.5 to 5.7 us) binds only at regtest
densities; memory bandwidth is about 25x above the
largest stream mining produces. The exploitable costs are
inside the hash path's structure: a streaming-API wrapper
(408 instructions, 416 B frame per nonce call path) that
cannot express prefix snapshots or phase overlap, and a
single serial round chain per nonce that leaves the core
latency-bound. The lab's research kernels have already
measured both: the MSG schedule is worth about 2.6x over
a scalar schedule at equal rounds, and interleaving
independent chains is worth 2.36x per worker at 2
streams, with the best per-worker median at 3,298,604 H/s
(streams=4, EXP-003) against production's tuned
1,627,792 H/s (EXP-000). Those kernels are proven correct
and not integrated, because the strict beyond-spread
integration test at 2 threads is not yet met on this
contended VM.

## 3. State of knowledge

### Proven (by proof, differential test, or node acceptance)

| Claim | Evidence |
|---|---|
| Precomputation ceiling is 67 of 192 rounds; per-nonce floor 125 | Derivation, ../header_and_midstate_analysis.md |
| First nonce-dependent expanded schedule word is W18 | Recurrence index check, corrected 2026-11-14 |
| Ch_alt, Maj_alt_A, Maj_alt_B are exactly equivalent | Exhaustive bit proof, 1M differential, z3 UNSAT |
| Production is the OpenSSL midstate C library; its tuned rate is 1,627,792 H/s at 2 threads here | EXP-000 |
| Compiler flags on the production wrapper hide no win | EXP-001, rejected with assembly cause |
| The MSG1/MSG2 schedule is correct and worth about 2.6x over scalar at equal rounds | EXP-002 (120,000 differentials, scalar-twin equivalence) |
| Interleaving streams multiplies per-worker throughput; the core is latency-bound in a single chain | EXP-003 stream scaling |
| Reduced-round bias dies by round 24; no statistical shortcut at full rounds | ../results/RESEARCH.md measurements |
| The full pipeline mines blocks Core accepts (regtest), and the solo stack works end to end | mining/engine.py acceptance rule; regtest block 390 via solo server |
| Mining here is compute and latency bound, not memory bound | Probe bandwidth 2.739 GB/s vs about 106 MB/s of digest stores |

### Hypothetical (registered, mechanism stated, untested)

- The stream geometry optimum (3, 5, 6 streams; wave
  shapes; assignment): X-001 to X-005, X-019.
- Hand-scheduled assembly recovering the spill cost:
  X-006, X-007.
- Cross-phase pipelining gains: X-008, X-009, X-102.
- The whole vector multi-buffer family: X-031 to X-034.
- Schedule partial evaluation beyond the state prefix:
  X-023, X-024, X-080.
- Carry-save and GFNI forms in vector rounds: X-020,
  X-021, X-022.
- Pipeline repricing at higher kernel rates: X-059 to
  X-066 and the H-series pipeline entries.

### Untested or unmeasurable on this machine

- GPU execution of the CUDA design: host-proven, device
  UNVERIFIED, no device exists (H-20).
- FPGA and ASIC performance: design packages only
  (H-21, H-22).
- Cycles per hash, IPC, port utilization: perf counters
  unavailable in this guest; all such reasoning is
  labelled reasoning in this tree.
- AVX-512 frequency behaviour under sustained load:
  unobservable directly; X-041 designs the indirect
  measurement.
- Any rate on any other machine: the fleet's dispatch is
  per-machine precisely because rankings may not travel
  (X-107).

## 4. The targets, in one paragraph

500 GH/s is about 152,000x the best verified per-worker
rate and about 25,000 cores at the optimistic per-core
ceiling estimate (about 20 MH/s, derived in
PERFORMANCE_ROADMAP.md from the measured 494-instruction
hot function). 140 TH/s is about 4.24 x 10^7 x the best
per-worker rate, about 7 million cores at that ceiling,
and approximately one modern ASIC unit. Both targets are
fleet-scale or silicon-scale objectives. The per-core
software prize that actually exists is the roughly 6x
between today's best measured per-worker rate and the
planning ceiling, inside the roughly 14x to the absolute
RNDS2 floor. This programme pursues that prize and
reports fleet numbers only when a fleet is measured.

## 5. The first five experiments, recommended and ranked

Six candidates were evaluated. The ranking weighs
information gained per unit cost, whether the experiment
unblocks others, and whether its result survives this
VM's noise.

### Experiment 1: X-067, the quiet-window integration decision re-run
- What: repeat the EXP-003 decision protocol (round-robin
  interleaved, 2 threads, production vs H-02 vs H-01
  streams 2 and 4) in a window with the node past initial
  block download, at least 9 repeats per contender, node
  state and load recorded per run.
- Why first: it is hours of machine time and it decides
  the programme's largest open question: whether a kernel
  family with consistent 1.75x to 2.6x median advantages
  enters production. Every kernel experiment after it is
  either improving an integrated champion or competing
  against one.
- Gates: the decision rule is unchanged (beyond spread at
  2 threads). If it passes, integration follows the full
  rule: selectable backend with fallback, full suite, and
  a fresh regtest block through mining/engine.py. If it
  fails on separated ranges, the family ranking is
  re-opened on evidence, not on hope.
- Expected information gain: decisive, either way.

### Experiment 2: stream geometry sweep (X-001, X-019, X-002, X-004, X-005)
- What: inside the existing h01_multistream framework,
  build and measure streams 3, 5, and 6, strided versus
  blocked assignment at the best count, and
  double-buffered waves at 4 streams; per-worker at 1
  thread first (the cleanest signal), then the mix
  question (X-073).
- Why second: it maps the one curve the programme is
  already standing on, at framework cost (hours per
  point), and its output chooses the configuration that
  Experiment 3 hand-optimizes. Running 3 after 2 would
  waste the expensive work on a possibly wrong stream
  count.
- Gates: full H-01 gate set per variant (100,000 plus
  differentials, boundaries, exact accounting); assembly
  record per variant (frame, spill ops).
- Expected information gain: the family's optimum and
  the spill curve's shape.

### Experiment 3: X-006 and X-007, hand-scheduled assembly
- What: hand-written variants of the best geometry from
  Experiment 2 (2-stream explicit allocation, and
  4-stream with deliberate spill layout), verified
  against the same gate set.
- Why third: spills are the current champion's one
  measured structural cost (365 xmm stack ops, 1,056 B
  frame at 4 streams). This is the only candidate that
  attacks a cost already proven to exist in the best
  kernel, rather than a hypothesized one.
- Gates: differential gates plus an instruction-level
  diff against the compiler build, so the gain (or its
  absence) is attributable.
- Expected information gain: whether the compiler or the
  register file is the real ceiling at the best geometry.

### Experiment 4: X-031 and X-032, AVX-512 multi-buffer prototype
- What: a 16-lane and an 8-lane zmm multi-buffer
  SHA-256d prototype (vprold rotates, proven Ch/Maj
  forms, vector schedule), gated by the full correctness
  set, accompanied by X-041's frequency drift
  measurement and X-034's 4-lane control if the family
  underperforms.
- Why fourth: it is the largest untested implementation
  family on this CPU and the only remaining candidate
  with a plausible family-reordering outcome. It ranks
  below the SHA-NI work because its prior is genuinely
  uncertain in both directions (per-hash instruction
  count reasoning puts it in the same few-hundred range
  as the measured champion) and its cost is weeks, not
  hours.
- Gates: the standard gate set at multi-buffer scale
  (per-lane differentials), plus the drift measurement
  reported alongside any rate.
- Expected information gain: the family's existence as a
  contender, or its cost anatomy if it fails.

### Experiment 5: X-009, cross-nonce phase pipelining
- What: in the best SHA-NI geometry, interleave the outer
  hash of nonce n with block 2 of nonce n+1 in one
  worker, and measure against the same-phase layout at
  equal stream count.
- Why fifth: phase diversity is the strongest untested
  scheduling idea inside the proven family (the two
  phases have measurably different instruction mixes),
  and it composes with whatever wins Experiments 2
  and 3. It ranks last of the five because its
  implementation cost is real and its premise
  (port-level complementarity) cannot be observed
  directly in this guest, only through the wall-clock
  result.
- Gates: standard gates, with accounting definitions for
  the pipelined early-exit case written before the
  benchmark, not after.
- Expected information gain: whether phase mixing is a
  real axis or a story.

### The sixth candidate, and why it waits
Pipeline overhead elimination (flags-only output H-04
end to end, plus the X-059 to X-061 construction caching)
is real, cheap, and independent of every kernel question.
It is not in the five because at current rates its total
addressable win is small (the digest store stream is
about 4 percent of the measured copy floor; construction
waste is per extranonce round, not per nonce), and its
value grows with kernel speed, so it belongs to Phase 4,
after the kernel it will serve is chosen. It is the
first alternate and can run in parallel with any of the
five whenever a second worker is free, since it touches
pipeline code the kernel experiments do not.

## 6. What this assignment changed

Created: the extreme_optimization tree (eleven documents,
five subdirectories with their own READMEs), 116
X-series hypotheses, the permanent experiment format with
EXP-000 to EXP-003 backfilled, and pointer sections in
../experiment_registry.md and ../research_findings.md.
Changed: nothing else. Production code, the live miner,
the node, the autopilot, and the keeper are untouched,
and the existing research history is preserved as it
stood.
