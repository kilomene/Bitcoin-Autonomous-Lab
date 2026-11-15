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

## EXP-018: Register-resident dual-batch MB (2026-11-14)

Phase 6 experiment for Y-023. A new kernel
(extreme_optimization/src/avx512_mb_reg.c,
libbal_r512.so) restructures EXP-011's
dual-batch shape so both batches' state sets
live in sixteen named zmm variables across an
eight-round ring-relabeled unit: the round's
state rotation is performed by compile-time
argument rotation, writing new A into the
vector that held h and new E into the vector
that held d, with no rename moves. Assembly
audit first, as predeclared: the final body
(1,014 instructions, frame 2,368 bytes) has
exactly one state vector homed in a single
stack slot (3 accesses) and no stack traffic
for the other fifteen; its remaining vector
stack traffic is the two schedule rings (80
accesses), as in every body of this family.
A full 64-round unroll was compiled first
and superseded (3,872 instructions, 214
spill-region stack accesses). Correctness:
the full gate set passes (108,000
differentials, genesis, boundaries, target
equality and minus one, exact accounting,
2^32 group edge). Benchmarks under the
EXP-017 protocol only (7 append-only
sessions in phase6/benchmarks/exp018/,
node in IBD): against single-batch MB the
adjusted pooled log-ratio is +0.0836 (CI
-0.0247 to +0.1902, 1.087x, pairs won
0.554), positive in all three sessions but
significant in none and not pooled; against
production it is +1.5027 (CI 1.4010 to
1.6011, 4.49x), significant everywhere; the
reg-vs-itself control is null (-0.0945, CI
contains 0). Verdict under the predeclared
definitions: residency achieved, significance
not shown, so Y-023 is NOT a verified
improvement; the finding is that state
traffic was not the binding cost in the
dual-batch shape on this machine. Tier:
PROMISING HYPOTHESIS with measured support.
No integration; production byte-identical.
Full record: phase6/EXPERIMENT_RESULTS.md
and extreme_optimization/EXPERIMENT_REGISTRY
.md. Nineteen experiments now recorded
(EXP-000 to EXP-018); next unreserved ID
remains EXP-021 (EXP-019 and EXP-020 are
reserved for the remaining Phase 6 designs).

## EXP-019: Carry-save schedule pricing (2026-11-14)

Phase 6 experiment for Y-002, then Y-001. The
price list ran first, as designed: a paired
microbenchmark (phase6/src/
exp019_price_micro.c, forms verified on
1,600,000 random lanes) pricing the
four-operand schedule sum per pipeline
separation 0..15, three sessions, plus an
L1-resident supplement matching the kernel's
stack-ring operand residency. Two costing
facts decide the experiment before any kernel
question: a software 3:2 compressor is three
instructions (2 VPTERNLOGD plus a VPSLLD
carry alignment the registry's original
costing omitted), so a resolved carry-save
sum costs 5 or 7 instructions against the
incumbent's 3 VPADDD, with dependency chains
of 4 or 5 stages against 3; and every
expanded word is resolved at separation 0
(fused T1) or separation 1 (sigma1 at t+2),
where the measured carry-save price is worst
(1.17 to 1.53 times the incumbent). Under L1
residency the carry-save forms are slower at
every separation from 1 up, intervals
excluding parity at 6, 10, 13 and 15; their
apparent advantage at wide separations under
L2 operand streams is a streaming-pattern
artifact. No form met the predeclared gate
(micro-cost win AND chain win), so no kernel
was built. Verdicts: Y-002 REJECTED (its
winner table is delivered; the winner is the
incumbent), Y-001 REJECTED at the pricing
level. Tier: established negative. The price
list stands as the discovery cost model's
resolution table. Production byte-identical.
Full record: phase6/EXPERIMENT_RESULTS.md and
extreme_optimization/EXPERIMENT_REGISTRY.md.
Twenty experiments now recorded (EXP-000 to
EXP-019); next unreserved ID remains EXP-021
(EXP-020 is reserved for the remaining
Phase 6 design).

## EXP-020: Automated full-round rewriting (2026-11-14)

Phase 6's closing designed experiment: both
discovery engines over the full round plus
the schedule cone. The saturation reached 28
vector ops per steady-state round in the
AVX-512 vocabulary, and the SMT-guided leg
assembled a matching lower bound (12 offset
ops + 6 combines + 10 adds), so the round
graph is optimal in that vocabulary; nothing
nontrivial is shared between the cones for
either engine to exploit. The one op below
the emitted production code is a codegen
gap, not a graph discovery: gcc emits Maj as
two chained VPTERNLOGD where the proven form
is one. That candidate (P6C-007) promoted to
a gated variant kernel and benchmarked under
the EXP-017 protocol: pooled adjusted
log-ratio +0.0493 (CI -0.067 to +0.167), not
significant, so no verified improvement and
no integration. Verdicts: Y-014 and Y-015
both supported as instruments, negative as
discoveries on this cone. Tier: established.
Full record: phase6/EXPERIMENT_RESULTS.md
and extreme_optimization/EXPERIMENT_REGISTRY
.md. Twenty-one experiments now recorded
(EXP-000 to EXP-020); next unreserved ID
remains EXP-021.

## Integration record: AVX-512 MB production backend (2026-11-14)

Not an experiment: an integration under a
decision. The owner adopted the EXP-017
statistic as the programme's integration
decision rule on 2026-11-14 (replacing the
min/max separation rule) and named the
AVX-512 multi-buffer kernel the target on
its EXP-017 evidence (pooled 3.55x against
production, CI 3.17x to 3.97x, significant
in every session). The kernel is integrated
as ComputeEngine backend "v512" behind
runtime CPUID dispatch (AVX-512F plus
AVX-512BW; flag-free probe plus digest
self-test; clean fallback to the OpenSSL C
backend; requested="c" unchanged). Gates
through the production path passed
(196,608 differentials, accounting parity,
fresh regtest blocks at heights 630 and
700), test-all passes except the
pre-existing test-rtl environment failure,
and the live miner was deployed and
verified on the new backend. Classification:
VERIFIED IMPROVEMENT under the adopted rule.
Full record: phase6/PHASE6_FINAL_REPORT.md,
addendum of 2026-11-14.

## EXP-021: Heterogeneous worker pair (2026-11-14)

Y-097, ranked second in the Phase 6
ranking: whether a mixed worker pool
(AVX-512 MB workers and SHA-NI streams
workers, streams=4 strided per EXP-005,
on disjoint partitions of one search)
beats the best homogeneous pool at equal
threads on this contended guest. Pool
gates pass in full (candidate sets equal
to the Python recount across six splits,
every digest vs hashlib, genesis under
either owner, boundary and empty
partitions, exact union accounting;
tests/test_exp021.py). Benchmark under
the EXP-017 paired protocol, three
sessions per comparison, makespan pool
timing: mixed2 vs mb2 pooled -0.1884 (CI
-0.294 to -0.082), mixed2 vs shani2
+0.0125 (null), mb2 vs shani2 +0.3100;
mixed22 vs mb4 -0.1285 (CI -0.203 to
-0.054), mixed22 vs shani4 +0.1442, mb4
vs shani4 +0.2848. A secondary
recomputation under continuous-assignment
semantics (sum of the recorded per-worker
rates) reproduces the same ordering
(mixed2 vs mb2 -0.1029 pooled; mixed22 vs
mb4 -0.1007, CI excluding 0), and
per-worker medians show no cross-family
contention relief. Y-097 is NOT a
verified improvement: the reproduced
ordering puts the mixed pool below the
homogeneous MB pool production already
runs. Tier: established negative. Full
record: phase6/EXPERIMENT_RESULTS.md,
EXP-021; raw data in
phase6/benchmarks/exp021/. Twenty-two
experiments now recorded (EXP-000 to
EXP-021); next unreserved ID is EXP-022.

## EXP-022: Flags-only MB batch via masks (2026-11-14)

Y-084: whether an MB batch form that
computes the target comparison in vector
form, stores one mask bit per hash, and
extracts digests only for flagged lanes
beats production batch at stated candidate
densities. The variant (bal_v_batchf2 in
extreme_optimization/src/avx512_mb_flags.c,
the EXP-007 kernel plus the flags path;
opmask-carried lexicographic compare in
v_meets significance order) passed all
gates before timing: 154,316 density-1
differentials vs hashlib, candidate-set
parity with production at four densities
in extract and pure modes, genesis
recovery, target equality and
minus/plus-one boundaries, accounting
parity on 32 (count, threads) pairs
(benchmarks/exp022_gates.py). Benchmark
under the EXP-017 paired protocol, three
sessions per comparison, every session
individually significant: flagsx vs
production at density approx 0, two
threads (predeclared primary) pooled
+0.5984 (CI +0.5042 to +0.6905), 1.82x;
at 2^-8 +0.4628, 1.59x; at density 1
+0.2854, 1.33x; pure flags +0.6344,
1.89x; primary at one thread +0.6033,
1.83x. The effect is monotone in the
unread-digest fraction: production's
batch epilogue (staging stores, scalar
extraction of all sixteen digests per
group, per-hash output copy, scalar
per-lane compare) was roughly half the
batch call at sparse densities. Y-084 is
a VERIFIED IMPROVEMENT in batch scope;
the search path never paid the epilogue,
no search claim is made, and adopting
the flags output shape for batch
consumers is recorded as a recommendation
for the owner's decision. Production
byte-identical. All work ran on the
Intel Xeon Platinum 8321HC replacement
host (AVX-512F/BW, no SHA, no VBMI) with
both libraries built -mavx512f -mavx512bw.
Full record: phase6/EXPERIMENT_RESULTS.md,
EXP-022; raw data in
phase6/benchmarks/exp022/. Twenty-three
experiments now recorded (EXP-000 to
EXP-022); next unreserved ID is EXP-023.

## EXP-023: Midstate amortisation family (2026-11-14)

Y-076, Y-077 and Y-079, tested as written.
The audit found the family's real target in
the GBT path: build_candidate recomputes
the whole transaction pass, the full merkle
tree and two RPC round trips on every
extranonce call (17.81 ms median per call
at 500 transactions on this host; about
99.6 percent of the repeated work is
extranonce independent), while no serving
path rebuilds a midstate per extranonce
step at all. Gates: 1,320 randomised
byte-identity cases for the two-level
prototype (family constants, per-template
pass and tree, coinbase spine per step),
the snapshot stepper verified against
PureSHA256 and hashlib, and the Y-079 table
verified for all 32 field subsets plus two
boundary rows. Verdicts: Y-076 REJECTED as
specified (established negative: its cache
target changes with every extranonce step
past block-1 round 8, and the named cost
does not exist in the code). Y-077 VERIFIED
IMPROVEMENT at the data level under the
EXP-017 paired protocol (extranonce steps
at 500 transactions pooled 18.49x, job
families 22.06x, every session significant;
churn boundary 0.97x, not significant), its
compression-prefix mechanism separately
rejected as immaterial. Y-079 VERIFIED
TABLE (deepest depths: none, R0, R8, B2R0,
B2R1, SCH17 by shallowest varying field;
the named block-1 half is deepest for no
subset; a tail-word-only change leaves the
midstate valid). Integration of the
prototype into mining/engine.py is a
recommendation for the owner's decision;
production byte-identical. All measurement
ran on the Intel Xeon Platinum 8321HC host.
Full record: phase6/EXPERIMENT_RESULTS.md,
EXP-023; raw data in
phase6/benchmarks/exp023/. Twenty-four
experiments now recorded (EXP-000 to
EXP-023); next unreserved ID is EXP-024.

## EXP-025: EXP-023 cache correctness and identity repair (2026-11-15)

Phase 6B Assignment C (EXP-024, the AVX-512
mask-search experiment, is recorded in
phase6b/EXPERIMENT_RESULTS.md). The EXP-023
prototype's 8-field fingerprint was audited
against a dependency matrix derived field by
field from mining/engine.py and mining/pow.py,
and the defect was demonstrated against the
unmodified prototype before any repair: five
stale-serve shapes with the fingerprint
unchanged (middle transaction replaced,
witness-only change with txid fixed, middle
reorder, coinbaseaux flags change, target
change) and two validation bypasses (fee
raised with coinbasevalue fixed, wrong
default_witness_commitment). The repaired
cache (phase6b/benchmarks/exp025_repaired.py)
uses a layered identity (family, transaction,
coinbase and header keys under one dsha256
identity) covering the complete dependency
set; sibling serves recompute the identity
from scratch and raise on mismatch. Gates:
19 adversarial invalidation cases pass,
positive reuse controls pass, 1,320 randomised
differential cases byte-identical to
production build_candidate; regtest block
through the repaired construction accepted at
height 826, hash
4d43835d08290e3db41d3953c47e3e39d213f4b2166299c16be38cd57a3e8734.
Performance re-check under the EXP-017
protocol on an AMD EPYC 9D25 host: steps500
pooled 23.02x (CI 20.22 to 25.93), VERIFIED;
family500 pooled 1.083x, NOT VERIFIED (the
full identity recomputation, 3.573 ms median
against a 4.499 ms uncached build at 500
transactions, consumes most of the family
gain the unsafe fingerprint appeared to buy).
Verdict: ACCEPTED on all six predeclared
correctness elements; the original EXP-023
prototype remains unsafe and unintegrated;
the repaired design is a recommendation for
the owner's decision. Production
byte-identical. Full record:
phase6b/EXP025_CACHE_CORRECTNESS.md and
phase6b/EXPERIMENT_RESULTS.md, EXP-025; raw
data in phase6b/benchmarks/exp025/.
Twenty-six experiment IDs now recorded
(EXP-000 to EXP-025); next unreserved ID is
EXP-026.

## EXP-026: Extreme AVX-512 execution research (2026-11-15)

Phase 6B Assignment D. A written cost model for
five candidate combinations was filed before any
kernel was compiled; three candidates (register
schedule ring, phase pipelining, hand-scheduled
assembly) were killed at the model with quantified
reasons. Two were built. C1 TernMask (EXP-024 mask
kernel with explicit VPTERNLOGD cones) is an
ESTABLISHED NEGATIVE as a combination: pooled
1.083x vs production at 2 threads, not significant,
and pooled 0.764x against its own strongest
ingredient, mask C. C2 DualMask (EXP-018
register-resident dual-batch compress plus the
EXP-024 opmask compare per batch, extraction only
on a hit batch, dual-atomic early exit) is a
VERIFIED IMPROVEMENT in the search path at density
0 under the EXP-017 rule: pooled 1.718x vs
production and 1.444x vs mask C at 2 threads,
significant in every session and pooled, control
null, gates all passed before timing (the gates
caught and the record preserves a real
transcription defect in C2 before its fix), fresh
regtest block accepted at height 827, hash
3bee3dae4d9d8b0c99c38cc6130cc75f5e517491be59fec68c7e31d5128e6c49.
Not integrated; integration is an owner decision.
Registry note: EXP-025's agent appended its record
to this lowercase file while the Phase 6B audit had
identified the uppercase
extreme_optimization/EXPERIMENT_REGISTRY.md as the
live registry; EXP-026 has updated BOTH files and
aligned the uppercase EXP-025 entry, which still
read RESERVED there. Full record:
phase6b/EXP026_AVX512_EXECUTION.md and
phase6b/EXPERIMENT_RESULTS.md, EXP-026; raw data
in phase6b/benchmarks/exp026/. Twenty-seven
experiment IDs now recorded (EXP-000 to EXP-026);
EXP-027 to EXP-029 are reserved by Phase 6B, so
the next unreserved ID is EXP-030.

## EXP-024b: Mask search confirmation run (2026-11-15)

Lettered confirmation of EXP-024, owner approved
2026-11-14, run after EXP-025 and EXP-026; not a
new ID (next unreserved stays EXP-030). Design C
predeclared as primary before timing. Compact
gates PASS (131,072 differentials vs hashlib;
equivalence at densities 0 and 2^-12; genesis
re-found). Primary (C vs production, density 0,
2 threads, EXP-017 protocol): pooled 1.398x
[1.242, 1.578], significant in every session and
pooled, criterion MET; control C vs C null;
1 thread 1.463x, every session. Same-process B/C
interleave: 1.011x, null, so the EXP-024 B/C
divergence was layout and scheduling, not code.
Verdict: design C VERIFIED IMPROVEMENT (search
scope). Not integrated; EXP-026 DualMask remains
the leading integration candidate, C is the
certified single-batch fallback. Full record:
phase6b/EXP024_MASK_SEARCH.md (EXP-024b sections)
and phase6b/EXPERIMENT_RESULTS.md; raw data in
phase6b/benchmarks/exp024b/.

## EXP-027: New computational representations (2026-11-15)

Phase 6B Assignment E, Track B. Characterised
search outside the vocabulary EXP-020 closed,
with a negative result. Every named space ends
closed at a stated scope: GFNI affine forms
(sigma maps proven GF(2)-linear by z3 UNSAT, but
every Sigma0 output byte depends on all four
input bytes, refuting single-instruction forms
and flooring any GFNI network at 11 ops against
the incumbent 4; Ch and Maj proven non-affine by
z3 SAT counterexamples, numerically rechecked;
GFNI hardware semantics differential-verified at
1,000,000 bytes); VPSHUFB rotations (all 625
byte-select patterns refuted on 10,038 inputs;
the mixed construction proven exact and measured
at 2.00x the VPROLD price); alternative state
representations (rotated and byte-swapped forms
refuted by addition counterexamples; bitslicing
already closed by EXP-015; delta state by
EXP-016); carry-save beyond the schedule (round
additions have deferral distance exactly 0
because every state output is bitwise-consumed
next round; T1 costs 6 or 8 against 4 at the
standing compressor price); addition networks
(binary-add counting floor met by the incumbent;
lookahead census about 18 ops per add; 52-bit
IFMA accumulation proven exact and costed out at
5 against 4); joint optimisation (0 nontrivial
subterms shared across the round boundary; the
outer compression's 48 computed schedule words
all depend on the inner digest, 0 independent
rounds; non-sharing cross-round restructuring
left explicitly open, blocker search-space size);
schedule forms (unrolled tree exactly 259,905
nodes at W63 against 384 DAG ops); automated
instruction selection over extended vocabularies
(no cone extracted below its EXP-020 cost).
No VERIFIED IMPROVEMENT, no PROMISING
HYPOTHESIS; no kernel compiled, so no EXP-017
benchmark was triggered. Not integrated.
Production byte-identical. Full record:
phase6b/EXP027_COMPUTATION_REPRESENTATIONS.md
and phase6b/EXPERIMENT_RESULTS.md, EXP-027;
proofs in phase6b/proofs/; raw data in
phase6b/benchmarks/exp027/. Twenty-eight
experiment IDs now recorded (EXP-000 to
EXP-027); EXP-028 and EXP-029 are reserved by
Phase 6B, so the next unreserved ID is EXP-030.

## EXP-028 and EXP-029: Phase 6B Assignment F (2026-11-15)

EXP-028 (cross-architecture roadmap): COMPLETE as a
roadmap and dispatch specification. Flag-free probe
TU (16-bit feature mask) and executable dispatch
spec verified on the AMD EPYC 9D25 host (mask
0xffff, object census scalar-only, five fallback
scenarios as expected). AVX-512 F+BW VERIFIED on
two hosts (AMD EPYC 9D25; Intel Xeon 8321HC, no SHA
extensions, no VBMI); SHA extensions MEASURED in
research on AMD (EXP-002/003/005, EXP-021); Intel
SHA, AVX-512 wider subsets, AVX2 and ARMv8 SHA2
plus NEON SPECIFIED, UNVERIFIED, no rates quoted;
portable C and hashlib VERIFIED floor. Not
integrated. Full record: phase6b/EXP028_CPU_
ARCHITECTURES.md and phase6b/EXPERIMENT_RESULTS.md;
artifacts in phase6b/benchmarks/exp028/.

EXP-029 (distributed execution roadmap): COMPLETE.
Allocator prototype proven by targeted cases and a
120-trial randomised campaign (exact disjoint
coverage in every trial; 20,474 repeated
computations accounted, none in unique coverage);
coordination overhead measured for a local
in-process prototype only (460,929 unique/s at 1
worker, 493,484 at 4 workers chunk 10,000, 120,000
nonces, this contended host); distributed-path
regtest block accepted at height 829, hash
781cc4ef7fc3e583ff6fa9bf277c780083b7252a9d5ede4fed5d213e691a2e8f;
centralised coordination chosen on coverage safety;
multi-machine scaling UNVERIFIED; no claim toward
500 GH/s or 140 TH/s. Not integrated. Full record:
phase6b/EXP029_DISTRIBUTED_EXECUTION.md and
phase6b/EXPERIMENT_RESULTS.md; artifacts in
phase6b/benchmarks/exp029/. Thirty experiment IDs
now recorded (EXP-000 to EXP-029 plus EXP-024b);
the next unreserved ID is EXP-030.

## Integration addendum: EXP-026 C2 DualMask (2026-11-15)

The owner decided on 2026-11-14 to integrate
EXP-026 candidate C2 (DualMask) after EXP-024b
finished. C2 is now the production backend
"v512dual" (kernel mining/cpu/bal_avx512_dual.c;
gates: 197,616 differentials, 0 mismatches; suite
23 of 24 with only the pre-existing test-rtl
environment failure; regtest blocks at heights 830
and 877; first live share 2026-11-15T06:57:29Z).
Independent post-integration audit:
phase6b/DUALMASK_POST_INTEGRATION_AUDIT.md, verdict
PASS WITH NOTES, zero defects (auditor's own
121,400 differentials; regtest block at height
910). Full record:
phase6b/PRODUCTION_INTEGRATION_LOG.md Entry 1 and
phase6b/EXPERIMENT_RESULTS.md (integration record).
Phase 6B closed with
phase6b/PHASE6B_FINAL_REPORT.md. The next
unreserved ID remains EXP-030.

## EXP-030 programme reservation (2026-11-15)

Owner directive 2026-11-15 reserves EXP-030 to EXP-038
for the EXP-030 umbrella programme (open-source mining
intelligence, CPU architecture transformation, autonomous
mining, mathematical breakthrough). EXP-030 umbrella:
IN PROGRESS, Phase A (reference repository audit)
executed 2026-11-15, record in exp030/REPOSITORY_AUDIT.md
and exp030/REFERENCE_TO_NOVA_MATRIX.md. EXP-031 VM
intelligence, EXP-032 CPU execution engine, EXP-033
mathematics, EXP-034 job and template engine, EXP-035
distributed architecture, EXP-036 exact verification and
submission, EXP-037 statistics and probability, EXP-038
autonomous operations: all RESERVED, not started. This
supersedes EXP-028's naming of AVX2 as the EXP-030
candidate; AVX2 multi-buffer work sits inside EXP-032.
Next unreserved ID: EXP-039.

## EXP-032 record (2026-11-15)

EXP-032 (CPU execution engine, EXP-030 Phase D)
COMPLETE 2026-11-15, research only, no production
change. Record: exp032/EXP032_REPORT.md; gates,
33 paired sessions and analysis under
exp032/RAW_RESULTS/. Host AMD EPYC 9D25, EXP-017
protocol throughout, complete production search
benchmarked as the headline scope. Verdicts: AVX2
multi-buffer batch VERIFIED IMPROVEMENT over the
production C batch (pooled 1.409x, CI [1.340, 1.480]);
SHA-NI H-01 4-stream batch VERIFIED IMPROVEMENT over
C (pooled 2.861x, CI [2.671, 3.089]) and 0.726x of
v512dual batch, the strongest verified fallback for
SHA-NI hosts without AVX-512; production
bal_sha_intrin.c ESTABLISHED NEGATIVE as a batch
backend (0.517x of C). Flags question closed: the
EXP-022 flags approach does NOT improve the real
search path (flags batch_search used as search is
2.565x slower than the native dual search; a
flags-form search entry is not significant against
the v512 search, pooled 0.967x CI [0.885, 1.059],
and 0.493x of the dual search). Production dual
search confirmed at pooled 6.781x over production C
search end to end. Nothing integrated; AVX2 and
SHA-NI streams kernels are dispatch candidates for
non-AVX-512 host classes only.

## EXP-037 and EXP-038 record (2026-11-15)

EXP-037 (mining statistics and probability, EXP-030
section 10) and EXP-038 (autonomous mining operations,
section 11) COMPLETE 2026-11-15, with production
changes. Records: exp037/STATISTICAL_MODEL.md and
exp037/FINAL_REPORT.md; exp038/AUTONOMOUS_OPERATIONS.md
and exp038/FINAL_REPORT.md. EXP-037: the autopilot
evidence census defect is fixed (EvidenceCounter in
mining/autopilot.py counts the whole evidence log
incrementally with a persisted offset; production log
247 accepted where the old 2,000,000-byte tail window
returned 222, brute-force verified in tests);
mining/mining_statistics.py holds the directive and
EXP-035 categories as separated counters, never summed,
with per-worker and per-backend breakdowns and a
counter-derived WindowedRate; mining/probability.py
adopts the research formulas (expected hashes D * 2^32,
expected time (D * 2^32) / R, P = 1 - exp(-R t /
(D * 2^32))) into production reach, pinned to known
values. EXP-038: mining/work_checkpoint.py records an
exact (extranonce, nonce) frontier of completed GBT
search per template identity, extranonce space and
curtime basis, written atomically, advancing only over
completed batches; MiningEngine resumes from it under
an opt-in checkpoint_path (default off, behaviour
identical when off) and agent/autonomous.py enables it
at .local/work-checkpoint.json. Tests
test_exp037_statistics.py and test_exp038_checkpoint.py
pass, wired as test-exp037 and test-exp038 in test-all
(28 targets, 25 passing; failures are the known
environment three: test-rtl without iverilog, and
test-cpu-correction and test-task003 SIGILL on this
SHA-less Intel host). Nothing live was restarted; the
census fix reaches the heartbeat at the autopilot's
next natural restart.

## EXP-033 record (2026-11-15)

EXP-033 (Bitcoin header and SHA-256d mathematical
investigation, EXP-030 Phase H) COMPLETE 2026-11-15,
research only, no production change, no kernel built
and no benchmark run. Record:
exp033/MATHEMATICAL_INVESTIGATION.md, with
exp033/HYPOTHESIS_REGISTRY.json; proofs and raw
results under exp033/PROOFS/ and exp033/RAW_RESULTS/.
Host Intel Xeon Platinum 8321HC; z3 5.4.1. Scope 1
(the one sub-space EXP-027 left open: non-sharing
cross-round graph restructuring): word-level e-graph
equality saturation over the two-round round function
found NO cheaper graph (rounds-only case converged at
2,388 enodes and 336 classes, per-root extraction
costs identical before and after; joint case capped
at 35,615 enodes; saturation soundness verified with
0 mismatches in 380,520 enode evaluations):
ESTABLISHED NEGATIVE at the stated bounds.
Instruction synthesis over V = {ADD, LUT, ROTR, SHR}:
Sigma0 and Sigma1 each proven to need exactly 4
instructions given the produced word and arbitrary
independent side values (CEGIS UNSAT at iteration 0;
4-instruction incumbents z3-proven exact), so a round
cone costs 6 by the 1 + 4 + 1 accounting, matching
the incumbent, except for one named shape (routing
Sigma through the Maj or Ch value: open for both
cones). The other candidate shape, exploiting the
s = T1 + T2 correlation inside the Sigma sub-DAG, is
EXCLUDED for both cones by cone-conditioned synthesis
UNSAT (16 cone-realizable examples each; two earlier
Sigma0 attempts timed out at 900 s under heavier
contention before the successful run). Scope 2 (header
mathematics re-derived): W18 is the first
nonce-dependent expanded schedule word (W16 and W17
nonce-free; 46 of 48 expanded words nonce-dependent);
the W18 and W19 delta identities hold exactly
(100,000 of 100,000 samples and z3 UNSAT); W20 delta
GF(2)-linearity REFUTED by a z3 counterexample,
numerically re-verified; the conventional accounting
is re-derived at 67 of 192 rounds per template and
125 per nonce, stated as accounting and NOT a lower
bound; the outer compression has 0 digest-independent
rounds (48 of 48 computed schedule words and 64 of 64
rounds digest-dependent), and comparison early exit
saves no rounds. No VERIFIED IMPROVEMENT is claimed:
no rate was measured, and a proven identity is a
mathematical result, not a speedup.
