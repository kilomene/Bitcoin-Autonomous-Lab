# Experiment Registry and Ranked Hypothesis List

Every experiment keeps: id, hypothesis, rationale, baseline,
compiler and flags, machine, correctness result, repeated
benchmarks with median and spread, assembly observations,
decision, and the next question. Failed experiments stay in
the record. The trusted baseline is never overwritten; a
candidate earns production only through the integration rule
(median improvement beyond spread overlap, full differential
correctness, full suite plus a fresh regtest block through the
changed path).

Conditions applying to every entry below, unless an entry says
otherwise: AMD EPYC 9D25 KVM guest, 4 vCPUs capped near 1.5
effective CPUs, live mainnet pool miner and pruned node
contending, gcc 13.3.0, OpenSSL 3.0.13, harness =
experiments/bench_harness.py, accounting per Task 003.9.

## EXP-000: trusted baseline (Stage 3)

- Hypothesis: none; this is the reference measurement.
- Raw data: experiments/exp000_baseline.json.
- Correctness gates inside the harness run: both native
  libraries match hashlib on 20,000 batch digests and re-find
  the genesis nonce by search.
- Production C backend (bal_c_batch2), 1,000,000 hashes/run,
  3 repeats: 1 thread median 1,314,704 H/s (spread 26.9%);
  2 threads median 1,627,792 H/s (spread 12.5%); 4 threads
  median 2,512,762 H/s (spread 82.6%, unstable under the cap).
- Intrinsics backend (bal_i_batch2): 1T 699,926; 2T 848,348;
  4T 1,135,344 H/s. Ratio to production at 2T: about 0.52x.
- Python hashlib fallback: median 304,444 H/s, 1 thread,
  50,000 hashes/run, wide spread (197,609 to 517,731).
- Single-candidate latency: count=1 batch call through ctypes,
  median 31.38 us (production), 31.74 us (intrinsics); p90
  above 1,100 us under contention spikes. Amortized per-hash
  at 1T production: about 0.76 us. The single-call figure is
  boundary overhead, not hash latency; see bottleneck B4.
- Decision: baseline adopted. All future comparisons use this
  harness and must report repeats, median, and spread.

## EXP-001: compiler and flag sweep on production source

- Hypothesis: production flags (-O3 -march=native) leave
  performance on the table that other gcc flag sets recover.
- Method: experiments/compiler_sweep.py builds
  mining/cpu/bal_batch.c under 5 flag sets into .local/shax/,
  verifies 100,000 digests per variant against hashlib plus
  the genesis search, inspects hash_nonce assembly, and
  benchmarks 1M hashes x 3 repeats at 1 and 2 threads.
- Raw data: experiments/exp001_compiler_sweep.json. Full
  write-up: compiler_experiments.md.
- Result (2T medians): production flags 2,347,336 H/s;
  -O2 native 1,472,158 (-37.3%); -O3 generic 2,188,081 (-6.8%);
  -O3 native + LTO 2,195,680 (-6.5%); -O3 native + funroll
  2,050,686 (-12.6%). Every spread overlaps the production
  spread (production spread itself was 70.1% in this session).
- Decision: REJECT all variants; production unchanged.
  No variant's median beat production, and contention spreads
  would have barred integration regardless. The production
  flag set is confirmed adequate; the bottleneck is inside
  OpenSSL's compression and our wrapper shape (B1), not in
  the flags applied to the wrapper.

## EXP-002: H-02 direct SHA-NI kernel (Stage 5, 2026-11-14)

- Implementation: experiments/h02_shani/ (shani_core.h,
  h02_shani.c, libbal_h02.so). Message schedule produced
  entirely by SHA256MSG1/SHA256MSG2 (whitepaper GENA/GENB
  construction); zero scalar schedule words. Scalar code:
  initial word loads, byte swaps, padding constants,
  feed-forward adds, and two scalar ROUNDS (template round 2
  once per template; mode-2 variant's per-nonce round 3).
- Correctness: ALL gates pass (test_h02.py): FIPS vectors,
  genesis, 120,000 randomized differentials across 3 prefix
  variants (0 bad), 5,000 vs production byte-identical,
  boundaries, 5 template variations, target equality/minus
  one/recount, counted accounting incl. early exit 50,001.
  Scalar twin (BAL_H_SCALAR_SCHED, 0 MSG instructions)
  byte-identical over 20,000: cross-implementation proof the
  MSG path is the path that ran and is equivalent.
- Assembly (hash_p1, per-nonce hot function): 494 insns,
  sha256rnds2 63, msg1 24, msg2 24, stack frame 0 B, 2 xmm
  stack ops, 0 calls, 0 scalar rotate/shift instructions.
  Whole binary: rnds2 350, msg1 132, msg2 132.
- Benchmarks (bench_h02.py, load avg 10.87 at run): H-02
  medians 1T 1,690,859 / 2T 1,966,395 H/s vs same-session
  production 1T 1,471,854 / 2T 1,403,332 and intrinsics
  2T 600,023. Spreads 40 to 72 percent, ranges overlap.
  Scalar twin 2T median 751,524: the MSG schedule alone is
  worth about 2.6x over the scalar schedule at equal rounds.
- Prefix variants (H-03 folded in): snapshot after round 1
  vs after round 2 vs none, all medians within each other's
  spreads (2T: 1,239,214 / 1,448,868 / 1,124,879). The
  predicted 2.4 percent effect is below this VM's noise
  floor: INCONCLUSIVE here, neither confirmed nor refuted.
- Decision: kernel stays in the research tree. Production
  unchanged (integration rule, see EXP-003 decision run).

## EXP-003: H-01 multi-stream interleave (Stage 5, 2026-11-14)

- Implementation: experiments/h02_shani/h01_multistream.c,
  libbal_h01.so. Streams 1/2/4 inside one worker thread
  (not OS threads), blocked nonce chunks per stream, wave
  dispatch 4 then 2 then 1 so partial waves never hash
  dummy nonces; coverage exact and disjoint. Search wave
  semantics: a wave is atomic; other streams' hashes in the
  winning wave are counted in attempted; winner is first
  published, not lowest nonce.
- Correctness: ALL gates pass (test_h01.py): 108,000
  randomized differentials per stream count (324,000 total,
  0 bad), genesis, boundaries, odd counts, miss accounting
  exact, and an exact wave-accounting proof: winner at scan
  position 50,001 found with attempted == 4.
- Assembly: 1-stream body 176 insns, 7 xmm registers, frame
  0 B, no stack ops. All variants inlined into
  walk_span.constprop.0: 2,985 insns, frame 1,056 B, 365 xmm
  stack ops: 4 streams x 8 live vectors cannot fit 16
  architectural xmm registers, so the compiler spills
  heavily. Whole binary rnds2 474, msg1 180, msg2 180.
- Benchmarks (bench_h01.py, load avg 9.95): per-worker
  (threads=1) medians: streams=1 1,064,406; streams=2
  2,515,315 (2.36x streams=1, same session); streams=4
  3,298,604 with 98.0 percent spread. Threads=2 totals:
  2,022,309 / 3,171,230 / 3,481,103. Single-candidate
  latency (count=1 call): about 30 us at every stream
  count, boundary-overhead dominated as in EXP-000.
- Decision run (bench_decision.py, round-robin interleaved,
  5 x 1M, load avg 7.46): at 2 threads, medians:
  production 1,183,205 (spread 142.3 percent), H-02
  2,068,798, H-01 s2 1,932,862, H-01 s4 3,084,485 (spread
  37.0 percent). Streams=4 won 4 of 5 rounds; production's
  best sample (2,442,181) still overlaps streams=4's
  minimum (2,130,229). At 1 thread the new kernels' ranges
  fully clear production's range.
- Decision: NOT INTEGRATED. The integration rule requires
  beating production beyond spread at the 2-thread
  configuration; medians favour the new kernels 1.75x to
  2.6x and the direction is consistent across three
  sessions, but the 2-thread ranges still overlap in the
  decision run, so the strict test is not met on this
  contended VM. Production stays byte-identical. Next
  question: repeat the decision run in a quieter window
  (for example after node IBD completes); if ranges then
  separate, wire H-01 streams=4 (or 2) as a selectable
  backend with fallback, run the full suite, and mine a
  fresh regtest block through mining/engine.py before any
  default changes.


## EXP-004 to EXP-009: first X-series batch (2026-11-14)

Full records in extreme_optimization/EXPERIMENT_REGISTRY.md
(mandate section 10 format) and the batch report
extreme_optimization/EXP004_009_REPORT.md. Summary:

- EXP-004 (X-067 decision re-run): 9 interleaved rounds at
  the best observed load dip (node still in IBD: blocks
  408,981, progress 0.0812; steal 2.24 percent). At 2
  threads, H-01 streams=4 median 4,212,571 vs production
  1,463,346, but streams=4 minimum 2,057,942 does not
  exceed production maximum 2,346,013. The predeclared
  beyond-spread criterion FAILED a second time. NOT
  INTEGRATED; production byte-identical.
- EXP-005 (geometry sweep): streams 3 and 6 and a strided
  assignment mode added to the H-01 framework (extreme_
  optimization/src/h01_geo.c); all variants pass the full
  gate set with wave-exact accounting per geometry. Best
  geometry at 2 threads: streams=4 strided (median
  3,473,271), streams=6 blocked indistinguishable; the
  curve is flat-topped from 3 to 6.
- EXP-006 (X-006/X-007): schedule-first hand-scheduled
  variant cuts hot-body spill ops 790 to 117 but does not
  improve throughput (parity at 2 to 3 streams, behind at
  4). Negative result: spill traffic is not the binding
  cost; the inline-assembly pair was not built because
  the 2-stream compiler body already has a 0 B frame and
  zero stack ops.
- EXP-007 (X-031, gate X-041): AVX-512 16-way multi-
  buffer (extreme_optimization/src/avx512_mb.c) passes
  all gates including partial-group lane accounting. It
  posts the fastest medians measured on this VM at 2
  threads in two interleaved sessions (6,526,467 and
  3,195,024 H/s), with the widest variance and no
  separation claim. X-041 frequency gate: inconclusive
  under contention, no catastrophic AVX-512 penalty.
- EXP-008 (X-009): cross-nonce phase pipelining matches
  a second same-phase stream (median 2,104,688 at 2
  threads) and loses to deeper interleaving; the phase
  premium is not supported on this core.
- EXP-009 (pipeline study, measurement only): X-059
  priced. build_candidate issues exactly one
  validateaddress and one getblockchaininfo RPC per call;
  validateaddress is a 3.963 ms median round trip against
  the regtest node and dominates construction below
  roughly 250 template transactions; per-transaction
  re-verification is about 17.8 us (stub: 0.018 ms at 0
  tx to 8.919 ms at 500 tx per call; up to about 571 ms
  per template at 64 extranonce rounds). Span-size
  interaction: none measurable (per-call overhead under
  about 10 us, under 0.1 percent at span 65,536, min-
  based best case). Mine-cycle split (stub, 0 tx):
  search 99.958 percent of wall. Confirmation at 1.1 us
  per candidate becomes about 2.8 percent of a core at
  regtest density and 6.5M H/s.

## Ranked hypotheses (H-01 to H-24)

Benefit classes: marginal (under about 5%), moderate
(5 to 30%), large (over 30%), unknown. Ranked by expected
value on THIS machine: benefit x probability, divided by
effort and risk.

### H-01: Multi-stream interleaved SHA-NI kernel
- Statement: one thread evaluating 2 or 4 independent nonces
  with independent register state chains hides SHA256RNDS2
  latency and beats the OpenSSL-wrapped path end to end.
- Rationale: SHA-NI round pairs have multi-cycle latency and
  the round chain is serial per nonce; interleaving is the
  standard cure and the flags (sha_ni) are present.
- Expected benefit: large. Difficulty: high. Risk: medium
  (register pressure, schedule bookkeeping per stream).
- Validation: prototype in the research tree, differential
  vs hashlib at 100k+, harness benchmark at 1/2/4 streams,
  assembly spill check. Status: MEASURED 2026-11-14
  (EXP-003): supported; streams=2 gives 2.36x per-worker
  over streams=1 in-session; streams=4 highest medians,
  heavy spills; not integrated, decision-run spread rule.

### H-02: Direct single-stream SHA-NI kernel with real schedule instructions
- Statement: a from-scratch SHA-NI kernel using SHA256MSG1
  and SHA256MSG2 for the schedule closes most of the
  intrinsics path's 2x gap (bottleneck B2) even before
  interleaving.
- Rationale: the current intrinsics kernel has 0 sha256msg
  sites and recomputes the schedule in scalar C per nonce.
- Expected benefit: moderate to large. Difficulty: medium.
  Risk: low to medium. Validation: same protocol as H-01;
  it is also H-01's stepping stone. Status: MEASURED
  2026-11-14 (EXP-002): all correctness gates pass, MSG
  schedule proven by scalar-twin equivalence, medians
  above production in every session; not integrated,
  decision-run spread rule.

### H-03: Block-2 prefix precomputation (rounds 0..2)
- Statement: precomputing the block-2 state after round 2 per
  template (canonical ceiling, header_and_midstate_analysis)
  saves 3 of 125 per-nonce rounds, about 2.4%.
- Rationale: exact identity; bounded and proven above. The
  intrinsics path currently snapshots after round 1 due to
  RNDS2 pairing; a single scalar round 2 or a repacked layout
  reaches the ceiling. OpenSSL's whole-block Transform API
  cannot express it in the production path.
- Expected benefit: marginal. Difficulty: medium (in a new
  kernel, low). Risk: low. Validation: differential tests
  plus micro-benchmark inside the H-02 kernel. Status:
  MEASURED 2026-11-14 inside EXP-002: all three prefix
  variants shipped and correct; the 2.4 percent effect is
  below this VM's noise floor, spreads fully overlap:
  INCONCLUSIVE on this machine, identity itself proven by
  the differentials.

### H-04: Candidates-only batch output
- Statement: a batch entry point that writes only flags (or
  candidate records) instead of all 32-byte digests cuts
  store traffic 32x on the enumeration path.
- Rationale: batch2 currently writes count x 32 bytes of
  digests that search-style callers never read; at 1M nonces
  that is 32 MB of stores per batch through a contended
  memory system.
- Expected benefit: marginal to moderate. Difficulty: low.
  Risk: low. Validation: new entry point alongside the old,
  differential flags vs existing batch, harness benchmark.
  Status: OPEN.

### H-05: Fewer Python/ctypes crossings, larger spans (h)
- Statement: end-to-end mining throughput rises when batch
  spans grow and per-call overhead (B4: 31 us per crossing)
  is amortized; there is an optimum against template
  freshness.
- Rationale: measured boundary overhead is about 40x one
  hash's amortized cost.
- Expected benefit: marginal (already partly exploited by
  the live miner's 1 s spans). Difficulty: low. Risk: low
  (stale work if oversized). Validation: end-to-end regtest
  mining rate vs span size sweep. Status: OPEN.

### H-06: Ch and Maj reformulations in a hand kernel (c)
- Statement: the proven forms in boolean_equivalence.md
  (Ch_alt 3 ops vs 4, Maj alternatives 4 ops vs 5, shorter
  dependency chains) speed up rounds evaluated outside
  SHA256RNDS2 (prefix rounds, SIMD designs).
- Rationale: equivalence proven three ways in this pass.
- Expected benefit: marginal, and zero inside OpenSSL or
  inside RNDS2 rounds. Difficulty: low where applicable.
  Risk: none to correctness (proven), only wasted effort.
  Validation: assembly diff plus harness benchmark in the
  H-02 kernel context. Status: OPEN, proof complete.

### H-07: Circular 16-word schedule in the CPU C path (d)
- Statement: a circular schedule reduces register and stack
  pressure versus a 64-word array in a hand-written CPU
  kernel (the CUDA source already carries both variants).
- Rationale: 16 live words instead of 64; known technique.
- Expected benefit: marginal to moderate in a scalar kernel;
  irrelevant to the OpenSSL path. Difficulty: medium.
  Risk: low. Validation: variant in the H-02 kernel,
  differential + benchmark + stack-frame comparison.
  Status: OPEN.

### H-08: AVX2 4-way multi-buffer SHA-256 (f)
- Statement: four independent hashes in 256-bit lanes with
  vectorized schedule and rounds beat scalar SHA-NI
  throughput per core.
- Rationale: avx2 present; multi-buffer is a proven design
  family. Counterweight: SHA-NI already does 2 rounds per
  instruction on dedicated hardware.
- Expected benefit: unknown, plausibly negative against
  SHA-NI. Difficulty: high. Risk: medium. Validation:
  prototype, differential, harness. Status: OPEN, ranked
  below the SHA-NI line on prior evidence.

### H-09: AVX-512 multi-buffer SHA-256 (g)
- Statement: the exposed AVX-512 set (f, dq, bw, vl, vbmi2,
  ifma) supports 8-way (or 4-way 512-bit) multi-buffer with
  vector rotates, possibly beating AVX2 width economics.
- Rationale: flags verified present in the guest.
- Expected benefit: unknown. Difficulty: high. Risk: medium
  (frequency and cap behaviour of wide vectors in a shared
  guest is unobservable from inside). Validation: as H-08
  plus a check that wide-vector use does not degrade the
  co-running miner. Status: OPEN.

### H-10: Thread affinity and pinning under the cap (i)
- Statement: pinning worker threads to vCPUs reduces
  migration noise and spread on this VM.
- Rationale: spreads of 27 to 83% in EXP-000 suggest
  scheduling noise dominates some configurations.
- Expected benefit: marginal, mostly variance reduction.
  Difficulty: low. Risk: low (could also pin us onto a busy
  host core). Validation: harness runs with and without
  taskset, spread comparison over more repeats. Status: OPEN.

### H-11: Dynamic chunking for load balance
- Statement: splitting spans into small chunks with atomic
  work claiming smooths the imbalance when host contention
  varies mid-span.
- Rationale: the cap makes per-thread speed time-varying;
  static partitions strand slow chunks.
- Expected benefit: marginal to moderate under contention,
  zero on a quiet machine. Difficulty: medium. Risk: low.
  Validation: harness variant under induced load. Status: OPEN.

### H-12: Compiler programme continued: clang and PGO (e, remainder)
- Statement: clang's codegen or profile-guided optimization
  of the wrapper beats gcc -O3 native.
- Rationale: EXP-001 exhausted the cheap gcc flag space and
  found nothing; clang is not installed here and PGO was not
  tried. Prior probability is low because the hot loop is in
  libcrypto.
- Expected benefit: marginal. Difficulty: low (PGO) to
  medium (obtaining clang at $0). Risk: none (measurement
  only). Validation: EXP-001 protocol extended. Status: OPEN.

### H-13: Timestamp rolling economics (m)
- Statement: rolling nTime extends a template's useful life
  without a new getblocktemplate, at a re-precompute cost of
  3 rounds (prefix state) per roll.
- Rationale: invariance classes in
  header_and_midstate_analysis.md; relevant when the nonce
  space per template is exhausted or GBT is slow.
- Expected benefit: marginal at CPU rates (the 2^32 nonce
  space lasts about 44 minutes at 1.6 MH/s, and longpoll
  already refreshes templates), larger for faster future
  backends. Difficulty: low. Risk: medium (consensus time
  rules must be respected exactly). Validation: regtest
  mining with rolled timestamps accepted by Core. Status: OPEN.

### H-14: Span size vs template freshness (j)
- Statement: there is a measurable optimum span where stale
  work losses balance boundary overhead.
- Rationale: B4 overhead argues large; chain-tip changes
  argue small; the live miner uses about 1 s spans today.
- Expected benefit: marginal. Difficulty: low. Risk: low.
  Validation: regtest and live-miner log analysis across
  span settings. Status: OPEN.

### H-15: Extranonce vs nonce partitioning for multi-worker coverage (l)
- Statement: for N workers on one template, partitioning by
  nonce range beats extranonce-per-worker (which forces a
  new midstate per worker) unless workers are on separate
  machines or templates.
- Rationale: midstate cost is 64 rounds once per template;
  partitioning is free and exact. The lab already partitions
  by worker name per machine on the pool path.
- Expected benefit: marginal (mostly a design guardrail).
  Difficulty: low. Risk: low. Validation: accounting audit
  with Task 003.9 definitions. Status: OPEN.

### H-16: Early target pre-check (k)
- Statement: some cheap partial evaluation could reject most
  candidates before the full outer hash completes.
- Analysis: the target compares the FULL outer digest, whose
  every word depends on all 64 outer rounds and the
  feed-forward. The comparison order (most significant word
  first) does not create a shortcut, because the most
  significant digest word is only known after the final
  round. No exact partial check is known; this entry exists
  to record the argument and catch any future proposal
  against it.
- Expected benefit: none expected (likely refutation).
  Difficulty: low (argument), high (any real counterexample
  would be a research result). Risk: high if misapplied
  (probabilistic filtering is banned). Status: OPEN as an
  analysis item only; no implementation authorized without
  an exactness proof.

### H-17: Dual-template interleaving
- Statement: interleaving two templates' nonces in one
  thread (two midstates) hides latency like H-01 while also
  diversifying template staleness.
- Rationale: same latency logic as H-01 with a pipeline
  benefit; costs a second state set.
- Expected benefit: unknown, subsumed by H-01 if streams
  already saturate. Difficulty: medium. Risk: low.
  Validation: after H-01 results. Status: OPEN, deferred.

### H-18: ADX/BMI2-assisted round arithmetic
- Statement: adcx/adox parallel carry chains or BMI2
  rotates (rorx) shave instructions in a scalar kernel.
- Rationale: adx and bmi2 are present; SHA-256 adds are
  mod 2^32 without carries between words, so the carry-chain
  benefit is doubtful; rorx could cut rotate sequences in
  non-SHA-NI code.
- Expected benefit: marginal to none. Difficulty: medium.
  Risk: low. Validation: micro-kernel comparison. Status: OPEN.

### H-19: Output buffer alignment and page placement
- Statement: aligning batch output buffers to cache lines or
  using large pages measurably changes batch throughput.
- Rationale: 32 MB of digest stores per 1M batch is the one
  real memory stream in the system.
- Expected benefit: marginal. Difficulty: low. Risk: none.
  Validation: harness A/B with aligned allocator. Status:
  OPEN, largely moot if H-04 lands.

### H-20: GPU research track (Stage 10)
- Blocked: no NVIDIA GPU exists on this VM (Tasks 002/003
  gates remain UNVERIFIED). The CUDA design work (midstate,
  candidate filtering, persistent context) is ready to
  measure the day hardware appears. Status: BLOCKED on
  hardware, research-only until then.

### H-21: FPGA pipelined compression research (Stage 10)
- The lab has RTL and a simulated netlist (fpga/, asic/);
  no board exists. Research questions (round pipelining,
  timing closure) are documented in results/FPGA_RESULTS.md
  and results/ASIC_RESULTS.md. Status: BLOCKED on hardware.

### H-22: ASIC datapath research (Stage 10)
- Pre-layout design package exists; no PDK or tapeout path
  at $0. Research-only. Status: BLOCKED.

### H-23: Hybrid CPU plus accelerator work split (Stage 10)
- Depends on H-20 to H-22 having a real second device.
  Status: BLOCKED on hardware.

### H-24: Statistical or reduced-round shortcut at full rounds
- REJECTED, settled by prior lab evidence: reduced-round
  bias is measurable at 16 to 20 rounds and dead by round 24
  (results/RESEARCH.md), winners follow the geometric law,
  and full SHA-256d is 64 rounds twice. See
  rejected_hypotheses.md. Status: REJECTED, do not relitigate
  without new evidence of a different kind.

## Pointer: the extreme optimization tree (2026-11-14)

The Grand Research Mandate opened a dedicated tree at
research/sha256d/extreme_optimization/. It contains: the
X-series hypothesis registry (X-001 to X-116, a separate
numbering from H-01 to H-24 above, with cross-references
stated on the entries), an experiment registry in the
mandate section 10 format with EXP-000 to EXP-003 and the
integration decision run backfilled as imported entries
(this file remains the original record for those
experiments), a bottleneck analysis of the production
path, a performance roadmap with the honest quantitative
assessment of the 500 GH/s and 140 TH/s targets, and a
first-assignment report recommending the next five
experiments, starting with the quiet-window decision
re-run already recorded as EXP-003's next step. Nothing
in this file's history is altered by the new tree.

## Pointer: Next Research Phase batch (2026-11-14)

Parts B, C and D of the Next Research Phase order
ran in the extreme_optimization tree. Part B is a
new hypothesis registry (HYPOTHESIS_REGISTRY_Y.md,
Y-001 to Y-108, no renamed repeats of H or X
entries). Part C is PERFORMANCE_CEILING.md (the
eight ceiling questions with three derived
assumption sets). Part D ran five experiments,
recorded in full in the tree's EXPERIMENT_REGISTRY
.md and EXP011_ONWARD_REPORT.md:

- EXP-011 dual-batch interleaved MB: promising,
  unseparated (ratios to MB16 across three
  sessions from 0.58x to 2.27x by configuration).
- EXP-012 VPTERNLOGD cone: unique immediates
  (Ch 0xCA, Maj 0xE8, XOR3 0x96), classic minima
  proven (3, 4 and 2 ops), z3 UNSAT; the compiler
  already emits ternlog in the baseline MB kernel,
  so the explicit form is parity. Formal closure.
- EXP-013 cross-lane prefix sharing in MB:
  correct, effect below this VM's noise floor.
- EXP-014 K+W folding in MB: no gain as
  implemented; rejected for this shape.
- EXP-015 bitsliced SHA-256d: implemented and
  measured at about 0.03x of MB16; X-029's
  analytic bound confirmed by measurement.

No integration; production byte-identical. EXP-010
was at that point reserved for the Part A decision
closure; it has since run, see the EXP-010 pointer
section at the end of this file.

## EXP-010: Part A decision closure (2026-11-14)

Executed on the owner's immediate order during
mainnet initial block download (node at blocks
410,518 to 410,520 of 975,803 headers, IBD true,
1-minute load 12.39 to 12.60, session steal 1.63
percent), pre-empting the post-sync watcher. Full
record: extreme_optimization/EXP010_PART_A_REPORT.md
and extreme_optimization/EXPERIMENT_REGISTRY.md;
raw data in extreme_optimization/benchmarks/
exp010_partA_decision.json.

All three contenders passed the full gate set
(108,000 differentials each, exact accounting).
At 2 threads, 15 interleaved rounds of 1M:
production C median 1,209,879 H/s (max 2,288,008);
H-01 streams=4 strided median 3,342,449 (min
1,440,195); AVX-512 multi-buffer median 3,551,903
(min 2,006,621). The predeclared criterion
(candidate minimum above production maximum)
FAILED for both candidates, the third recorded
failure of the same test (EXP-003 decision run,
EXP-004, EXP-010). No integration; production
byte-identical; the Part A decision is closed for
this machine. AVX-512 variance attribution: steal
and load spikes do not explain its slow rounds
(calm and spiked medians 1.3 percent apart, rate
vs steal correlation +0.221 against production's
-0.521 control); the excess variance is
implementation behaviour under a saturated
runnable queue.

## Pointer: Phase 6, first assignment (2026-11-14)

Phase 6 (Breakthrough Computation Research) opened
with an audit of this programme, in-place
corrections to the 125-round, ceiling, and memory
conclusions, a published ranking of all 108
Y hypotheses, the design and seed build of the
automated discovery system, and one executed
experiment: EXP-016, the nonce dependency
derivation, which refuted Y-065 and Y-075 as work
reductions with proof-grade evidence (full record
in extreme_optimization/EXPERIMENT_REGISTRY.md;
mathematics in phase6/MATHEMATICAL_DISCOVERIES.md
MD-1). All Phase 6 records live in phase6/,
starting with phase6/PHASE6_FINAL_REPORT.md. Next
unreserved experiment ID at that point: EXP-017,
which has since run; see the EXP-017 section
below. Phase 6 reserves EXP-018 to EXP-020;
next unreserved ID: EXP-021.

## EXP-017: The measurement stack (2026-11-14)

Phase 6's measurement experiment (Y-101, Y-102,
Y-103). A paired benchmark driver alternates
arms in 65,536-hash blocks with randomised
order and per-call steal and runnable-load
covariates; the predeclared statistic is the
covariate-adjusted mean paired log-ratio with
a 10,000-resample pairs bootstrap (definition
written into phase6/EXPERIMENT_RESULTS.md
before the runs). Twelve append-only sessions
in phase6/benchmarks/exp017/: both equal-pair
controls (production vs itself, AVX-512 MB vs
itself) returned nulls in all three sessions
each and pooled (adjusted +0.0137, CI -0.0786
to +0.1081; +0.0077, CI -0.1047 to +0.1167),
and the historical min/max rule passed a
phantom difference in 0 of 6 control sessions.
Real comparisons under the EXP-017 rule:
AVX-512 MB vs production adjusted pooled
+1.2652 (CI 1.1546 to 1.3767, 3.55x),
significant in every session; streams=4
strided vs production +1.0298 (CI 0.9265 to
1.1283, 2.80x), significant in every session.
Covariate adjustment was priced near-neutral
(pooled CI width ratios 0.970 to 0.999); the
pairing carries the decision value. Variance
decomposition and sessions-needed estimates
are in the full record. This is a measurement
result under stated contention, NOT an
integration: the programme's integration
criterion is unchanged, and a proposal to
replace it with the EXP-017 rule is recorded
for the owner in phase6/EXPERIMENT_RESULTS.md.
Sub-verdicts: Y-103 PASS, Y-102 PASS at
65,536 hashes, Y-101 PARTIAL. Full record:
phase6/EXPERIMENT_RESULTS.md and
extreme_optimization/EXPERIMENT_REGISTRY.md.
