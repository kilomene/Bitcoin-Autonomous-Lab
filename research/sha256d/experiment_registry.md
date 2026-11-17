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
Next unreserved ID: EXP-041.

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
## EXP-039 record (2026-11-15)

EXP-039 (Phase 002 step 1: fallback tier integration)
COMPLETE 2026-11-15, with production changes. Record:
exp039/EXP039_REPORT.md; raw benchmark sessions and
analysis under exp039/RAW_RESULTS/. The EXP-032
verified kernels are now production dispatch tiers in
gpu/engine.py: order CUDA, v512dual, v512, shani
(SHA-NI H-01 multi-stream at streams 4), avx2 (AVX2
multi-buffer, 8 lanes), C, hashlib. Kernel sources
ported from exp032/src/ with byte-identical kernel
bodies (mining/cpu/bal_avx2_mb.c, bal_shani_streams.c,
bal_shani_core.h), plus a flag-free runtime probe
(mining/cpu/bal_fallback_probe.c) gating each tier by
CPUID in the established pattern; restricted build
flags only (kernel TUs -mavx2 and -msha -mssse3, probe
TU no vector flags), D-1 hasattr discipline on every
new ctypes signature. Both tiers serve batch AND
search (the EXP-022 flags precedent did not force
batch-only: both kernel forms carry honest counted
search entries; the SHA-NI form hashes no dummy lanes,
so its backend count equals attempted exactly).
Correctness: 124,351 batch digests per kernel through
the ComputeEngine seam byte-identical to hashlib,
candidate sets identical at densities 0, 2^-16, 2^-8
and 1, planted-hit and no-hit search exactness, one
fresh regtest block per tier forced active (shani
height 1293, avx2 height 1294), suite
tests/test_exp039_fallback_integration.py wired as
make test-exp039 in test-all. Benchmarks under the
EXP-017 protocol (3 sessions per comparison, 120
paired 65,536-hash blocks each, randomised AB or BA,
adjusted bootstrap CI above 0 in every session and
pooled): batch scope category D, avx2 vs C pooled
1.252x [1.185, 1.322] and shani streams 4 vs C pooled
2.812x [2.573, 3.095], both VERIFIED IMPROVEMENT;
search scope category E, avx2 vs C pooled 1.300x
[1.217, 1.390] and shani vs C pooled 2.887x
[2.646, 3.154], both VERIFIED IMPROVEMENT. Host AMD
EPYC 9D25 (SHA-NI present); refusal behaviour on a
SHA-less host is gated by construction and by the
suite's forced-fallback gates but was not executed on
the Intel Xeon 8321HC this session. The live mainnet
miner was not restarted; nothing was pushed.

## EXP-040 record (2026-11-15)

EXP-040 (Phase 002 step 2: category F end-to-end
pipeline benchmark) COMPLETE 2026-11-15, harness plus
measurements, no production changes. Record:
exp040/EXP040_REPORT.md; harness exp040/category_f.py;
analysis exp040/exp040_analyze.py; raw sessions under
exp040/RAW_RESULTS/. The harness times the unmodified
production GBT pipeline (MiningEngine.mine_cycle against
the regtest Core node, v512dual backend) as one system,
with stage attribution by wrapping the harness's own
engine instance at the RPC, prepare/build and compute
seams, and the EXP-036 exact verifier timed on every
accepted block. Campaign: 63 timed runs, 0 failed, every
run one accepted block (heights A 1345 to 1370, C 1372
to 1388, B 1392 to 1417), every header EXP-036 verified.
Category F results (medians, contended single VM,
regtest difficulty; not hash rates): empty template
0.065 s per block, non-search overhead 43.5 ms per block
(fraction 0.930); loaded template (501 transactions)
0.215 s per block, overhead 206.3 ms (fraction 0.992),
prepare plus construct 147x the empty cost; amplified
target variant (search target divided by 2^24, about
2^25 counted hashes per block) overhead fraction 0.015
at the same fixed overhead (49.5 ms). EXP-036
verification costs 2.5 to 3.9 ms per candidate. Suite
tests/test_exp040_category_f.py wired as make
test-exp040 in test-all. Host AMD EPYC 9D25; the live
mainnet miner was not restarted; nothing was pushed.

## EXP-041 record (2026-11-15)

EXP-041 (Phase 002 step 3: the 29 vs 28 operation
codegen gap campaign) COMPLETE 2026-11-15. The
production AVX-512 MB kernel (mining/cpu/
bal_avx512_mb.c) emits 29 vector ALU ops per
steady-state round: gcc fuses every classic Boolean
cone into a single VPTERNLOGD except Maj, which it
emits as a chained pair (0x60 then 0x78). EXP-020
proved the 28-op form optimal in the vocabulary.
Six research variants of the production kernel were
built under the restricted flag set and censused by
objdump of the v_compress16 loop body: source-level
Maj restructurings (Maj_alt_A, Maj_alt_B, and an OR
form) all still emit 29 (gcc normalises them to a
two-ternlog Maj); flag variations (-O2 and
-mtune=znver3) also emit 29; only the explicit
VPTERNLOGD intrinsic forms reach 28 (tmaj: Maj
0xE8 only; tfull: Ch 0xCA plus Maj 0xE8, the
P6C-007 form). The production DualMask search body
(v_compress16x2_reg) already emits 28 per round;
the gap survives in the v512 kernel and in the dual
library's batch and remainder path (v_compress16).
Correctness: all six variants pass the standard
gate set (108,000 differentials vs hashlib each,
genesis, boundaries, target equality, exact wave
accounting; 102 checks, 0 failures). Benchmarks
under the EXP-017 protocol (3 sessions of 160
pairs each, 65,536-hash blocks, 2 threads): tmaj
batch vs production v512 batch (category D) pooled
adjusted log-ratio -0.0006 (CI -0.106 to +0.106);
tfull batch +0.0301 (CI -0.079 to +0.140); tmaj
search vs production v512 search (category E)
-0.0213 (CI -0.123 to +0.080); tmaj search vs
production v512dual search -0.5900 (CI -0.705 to
-0.475; the dual remains significantly faster,
consistent with EXP-026). No comparison is
significant in the candidate's favour in any
session or pooled: the 28-op form is an
ESTABLISHED NULL for rate, replicating EXP-020's
P6C-007 result on the current production code. An
equal-pair rebuild control (instruction-identical
libraries) disagreed with itself across session
batches (-0.132 pooled over the first three
sessions; +0.494 to +0.549 per session in three
later ones) while the same-library self control
was a clean null (-0.0018, CI -0.117 to +0.108):
cross-library layout sensitivity on this
oversubscribed VM sets a noise floor far above
the 3.4 percent ceiling of the gap. Regtest
soundness: fresh blocks mined through the
production ComputeEngine path with each 28-op
gate library active (logged run: tmaj height
1428, tfull height 1429). Verdicts: tmaj
ESTABLISHED NULL (census 28 achieved, no verified
improvement, NOT integrated); tfull ESTABLISHED
NULL; alta, altb and altc REJECTED (never reach
the 28-op census); flag approaches REJECTED for
this purpose. Full record: exp041/EXP041_REPORT
.md; raw sessions, census and analysis under
exp041/RAW_RESULTS/. Host AMD EPYC 9D25; the live
mainnet miner was not restarted; nothing was
pushed; production code untouched.

## EXP-042 record (2026-11-15)

EXP-042 (Phase 002 step 5: the time-boxed E2
synthesis attempt) COMPLETE 2026-11-15. EXP-033
(H-033-05) left exactly one shape unrefuted in the
round-cone problem: E2, the Sigma output routed
through the Maj (resp. Ch) value, so the Boolean
instruction sits inside the Sigma sub-DAG of a
5-instruction cone over V = {ADD, LUT(any imm),
ROTR, SHR}. Reduction: in any 5-instruction cone,
if the Boolean instruction is outside the Sigma
dependency DAG, H-033-13 and H-033-14 already
exclude the cone; if it is inside (E2 proper), the
DAG minus that instruction is a program of length
at most 3 over the 6-value pool (s, p, q, x, y, m),
with m the Boolean value given free per
cone-realizable example (a superset of the real
interleavings, so UNSAT refutes and SAT would
construct). Result: synthesis UNSAT at iteration 0
for both cones (a-cone Sigma0 through Maj: 540.3 s,
16-example seed; e-cone Sigma1 through Ch: 214.0 s,
16-example seed; z3 5.4.1). E2 is REFUTED at the
stated bounds (straight-line over V, cone length 5,
sum by a single ADD, Boolean output by a single
LUT): ESTABLISHED NEGATIVE at those bounds.
H-033-05 is closed (E1 by EXP-033, E2 here); the
cone minimum over V is exactly 6 under the stated
bounds. Soundness discipline: gates on both cones
(4-instruction incumbent, 200,000 plain-Python
differentials each with 0 mismatches, exact z3
verification over symbolic cone inputs) and a
control synthesis that found a known 3-instruction
program over the same pool (SAT, 219.6 s, passed
its differential), all before any E2 result was
read. Catch-all with the remaining budget: the
EXP-033 full-cone CEGIS at L = 5 rerun per cone
(22-example seed) returned synth unknown at 1,500 s
(a-cone) and 1,400 s (e-cone): INCONCLUSIVE,
recorded as such; it remains the only instrument
covering the out-of-bounds shapes (sum or Boolean
output produced by two or more instructions), so
H-033-02 stays open in that residual generality
only. Solver budget: about 3,904 s of the 5,400 s
box, all runs strictly sequential. No construction
was found, nothing was benchmarked, no rate is
claimed. Full record: exp042/EXP042_REPORT.md;
scripts under exp042/src/; run JSONs and logs under
exp042/PROOFS/ and exp042/RAW_RESULTS/. Host AMD
EPYC 9D25; the live mainnet miner was not
restarted; nothing was pushed; production code
untouched.

## EXP-043 record (2026-11-15)

EXP-043 (Phase 002 step 6: the EXP-035 coordination
overhead study, this VM only; no fleet agent
activated, contacted or measured). In-process
operation costs for the EXP-035 prototype:
heartbeat 220 ns, registration 0.73 us, candidate
submit and dedup check 0.77 to 0.80 us flat to
20,000 seen, lease grant 3.1 to 4.7 us, complete
2.6 to 4.4 us, steal 2.8 us; journalled submit
18.4 us (about 24x the in-memory submit). Costs
that grow: declare_job about 0.36 us per chunk;
expire idle scan 0.20 ms at 2,048 active leases to
1.62 ms at 8,192; per-reclaim cost about 6 us at a
2,048-chunk state to about 45 us at 8,192; snapshot
13.3 ms at 512 chunks to 420 ms at 8,192 (deepcopy
of all retained history, event log included).
Campaigns at a fixed 131,072 positions under the
EXP-035 fault mix, accounting asserted exact at the
end of every completed trial: 1,214 ns per
completed position at 2 workers, 13,764 at 8,
1,525,761 at 32; the 128-worker fault trial was
capped at 600 s and FAILED to complete (10.89
percent coverage, accounting open, recorded as a
failed run, never averaged). No-fault campaigns:
10, 131, 8,513 and 584,481 ns per position at 2, 8,
32 and 128 workers. Profile of a 32-worker fault
trial: 67 percent of CPU in _holds_lease scanning
every lease record ever issued (the lease table is
never pruned; about 9,700 records retained for
1,024 chunks), 25 percent in snapshot deepcopy.
Loopback wire shim (thin JSON framing over the
prototype's message shapes; NOT the production
wire protocol, which remains unbuilt): round trips
33 to 54 us at 1 worker process, medians about 1 ms
at 16 worker processes under heavy contention;
accounting closed exactly over the shim at 1
worker. Still UNVERIFIED: all multi-machine
coordination overhead, propagation latency over any
real network, linear scaling across machines, the
production wire protocol, and every property of
the roughly 25 fleet agents. Full record:
exp043/EXP043_REPORT.md; raw sessions, profile and
run logs under exp043/RAW_RESULTS/. Host AMD EPYC
9D25; the live mainnet miner was not restarted;
nothing was pushed; production code untouched.

Next unreserved ID: EXP-044.

## EXP-045 record (2026-11-16)

EXP-045 (NOVA-ER-0002: AVX2 batch discrepancy
resolution). EXP-032 measured the AVX2 multi-buffer
batch at pooled 1.409x [1.340, 1.480] against
production C; EXP-039 measured the byte-identical
kernel as the production tier at 1.252x [1.185, 1.322];
the intervals do not overlap and the EXP-039 audit
(note N-2) left the discrepancy unresolved. EXP-045
crossed every candidate factor in one campaign on the
AMD EPYC 9D25 host (EXP-017 protocol throughout, 15
sessions, 120 paired 65,536-hash blocks each, live
miner running and untouched): harness (direct ctypes
vs the production ComputeEngine.batch_search seam) by
library (research-built exp032 .so vs production-built
.local .so), production C measured inside every cell,
plus a direct library head-to-head. Gates first:
917,504 hashlib differentials across all six arm
paths, zero mismatches. Forensics: both campaigns'
manifests record the identical libbal_batch.so sha256
(8794238c...), refuting baseline drift; the kernel
sources differ only in comments; the compiled kernel
code is instruction-identical between the two
libraries (bal_a_batch2 41 insns identical;
a_walk.constprop.0 2,380 insns identical except
RIP-relative constant-pool displacements). Results
(adjusted pooled): direct/production-lib 1.274x
[1.222, 1.328]; direct/research-lib 1.286x [1.233,
1.345]; seam/production-lib 1.287x [1.236, 1.340];
seam/research-lib 1.315x [1.261, 1.374]; head-to-head
production vs research 0.976x [0.930, 1.025], NOT
SIGNIFICANT. Verdict: CAUSE IDENTIFIED. The
discrepancy is a session-conditions effect on the
AVX2 arm (session medians 0.64M to 2.57M H/s across
campaigns against C's stable 0.84M to 1.07M), not a
kernel, build, harness or baseline difference; every
factor effect is measured at 3 percent or less while
the between-campaign spread is about 12 percent.
Both historical VERIFIED IMPROVEMENT verdicts stand;
the point estimates are condition-drawn, and the
defensible current band is 1.27x to 1.32x under load.
No discards; no production file modified. Full
record: exp045/EXP045_REPORT.md; sessions, gates,
analysis and disassembly comparison under
exp045/RAW_RESULTS/. (EXP-044 stands pre-committed
to the -mtune scheduling study, NOVA-ER-0005, per the
Extreme Research portfolio; it is not this record.)

Next unreserved ID: EXP-046.

## R-12 prototype record (2026-11-16): solo vardiff (NOVA-ER-0004)

The decided solo vardiff design (register R-12, EXP-030
matrix M10: adapt share difficulty toward a target share
interval with hysteresis on increases) is implemented as a
RESEARCH PROTOTYPE in research/vardiff/ (DESIGN.md,
vardiff.py, TESTS/test_vardiff.py, TEST_RESULTS.md,
PORTFOLIO_SUMMARY.md). No EXP number is consumed: the
Extreme Research portfolio assigns EXP identity at
integration candidacy, and this work is the pre-candidacy
prototype, recorded here under its register identity R-12 /
NOVA-ER-0004. No production file was modified; the
prototype subclasses mining/solo_server.py's SoloServer and
mirrors its TCP handler with four named deltas.

Design as built: per-connection difficulty (keyed by
extranonce1) toward a 15 s target share interval, EMA alpha
0.35, deadband [target/1.25, target x 1.25], increases
gated by 2 confirmations plus a 30 s grace period and
capped at 1.5x per step, decreases free of hysteresis and
capped at 2x per step, floor 0.002, ceiling 1.0, initial
0.02 (the operative endpoint-config value). A share is
judged against the difficulty snapshot taken when its job
was issued, so an adjustment never invalidates issued work.
Stale shares (bounded 8-job history) are classified into
their own category, never counted as accepted, and still
routed through the EXP-036 exact pipeline when they meet
the network target; duplicates are their own category and
never count as work. Difficulty never enters candidate
judging (the EXP-036 separation). Idle clients decay to
the floor on job changes (60 s threshold, halving steps);
reconnects restart at the initial difficulty. Discrepancy
D10 (endpoint config 0.02 vs the SoloServer constructor
default 0.01) is documented in the design, NOT fixed:
closure is step 3 of the Stage 6 integration path the
design specifies.

Verification (suite research/vardiff/TESTS/test_vardiff.py,
final recorded run 2026-11-16 on AMD EPYC 9D25, transient
systemd unit vardiff-full5, raw log at
research/vardiff/TESTS/full-run.log): 41 of 41 checks
passed, exit 0. Control law under a simulated clock
(convergence from both sides, hysteresis, caps, floor,
ceiling, decay window, reconnect); the target formula
integer-identical to production and the acceptance
comparison exact at the boundary through
candidate_verify.meets_target; pinned-mode differential
against production SoloServer on a scripted stub stream
(decisions and counters identical); live regtest over TCP
(fast client raised with a replayable adjustment log,
ceiling clamp, duty-cycled slow client lowered, silent
client decayed to the floor, stale share classified with
its block accepted by Core as the new tip, reconnect at
initial). Gates 1 to 3 and 6 for the prototype; Gate 4
does not apply (no rate claimed). Run history includes two
harness defects found and fixed (proxy-routed loopback RPC
answered by an egress-proxy 503; a scripted-client makefile
reader poisoned by its own timeout), one test premise
corrected (the ceiling scenario is rate-relative and now
runs a 60 s target instance), one run lost to a VM
replacement with no result claimed, and the deadband's
origin: the first law draft hunted at equilibrium (68
adjustments in 120 simulated shares) and the band is the
fix. Portfolio verdict: SUCCESS at prototype scope, with
D10 closure explicitly carried to Stage 6
(PORTFOLIO_SUMMARY.md). Not verified: anything on mainnet,
two-client interference on one server, the rate-stepped
stability campaign, any other host.

Integration update (2026-11-16): INTEGRATED. R-12 is now
production code, integrated exactly along the DESIGN.md
section 9 path. VarDiffController, the per-connection
state, per-job difficulty snapshots, the bounded 8-job
history, stale and duplicate accounting and the full
adjustment log live in mining/solo_server.py behind the
optional SoloServer vardiff parameter (None restores the
pre-integration behaviour exactly, and is the rollback
surface). mining/endpoint_config.py carries the vardiff
parameters alongside SOLO_SHARE_DIFFICULTY, and
mining/solo_mainnet.py builds the controller when the
endpoint config enables it; the config default is
disabled, so the armed solo cutover keeps today's
fixed-difficulty behaviour until an operator enables
vardiff after the independent audit. D10 is closed in the
same change: the SoloServer constructor default is
removed, and the endpoint config value 0.02 is the single
source of the initial difficulty. Production suite
tests/test_solo_vardiff.py (make test-solo-vardiff, 59
checks, all passing 2026-11-16 on AMD EPYC 9D25): the
prototype's 41 checks ported to the production classes;
the Gate 2 differential against a pristine copy of the
pre-integration solo_server.py, taken from remote HEAD
3ebbaeb2 and pinned as tests/fixtures/
solo_server_pre_integration.py (jobs, decisions and
counters identical with vardiff off); Gate 3 adversarial
(oscillation injection, rate step, stale and duplicate
floods); the EXP-036 separation shown at unit and server
level (the network verdict is independent of the share
target); Gate 5 (job refresh and recovery with vardiff
live); Gate 6 regtest blocks accepted by Core through
the vardiff-active path and through the pinned default
path (the recorded run mined blocks 1658 to 1679 on the
best chain). See research/sha256d/phase6b/
PRODUCTION_INTEGRATION_LOG.md, Entry 5. An independent
post-integration audit is owed before vardiff is enabled
on the live cutover. Still not verified: anything on
mainnet, two-client interference on one server, the
rate-stepped stability campaign, any other host.

Next unreserved ID: EXP-046.

## EXP-046 record (2026-11-16)

EXP-046 (NOVA-ER-0003: EXP-024b design C re-measurement
against today's production search). EXP-024b verified
design C (bal_v_msearcha2, libbal_m512.so) at pooled
1.398x [1.242, 1.578] against the production search of
2026-11-14 and certified it as a single-batch fallback
form. Production search has since moved to v512dual
(EXP-026). EXP-046 re-measured design C, byte-identical
library (sha256 1566a9d2..., matching the EXP-024b gates
record), against today's production libraries on the
AMD EPYC 9D25 host: bal_vd_search2 (primary) and
bal_v_search2 (secondary), EXP-017 protocol, density 0,
12 sessions, 120 paired 65,536-hash blocks each,
sessions rotated by round, live miner running and
untouched (shares accepted 477 to 478). Gates first:
786,432 batch differentials vs hashlib across the three
libraries, candidate-set equivalence vs a hashlib
recount at densities 0, 2^-16, 2^-8, 1 on 36 spans
including nonce boundary spans, 2-thread accounting and
genesis checks, uniform rc -2 refusal of spans crossing
2^32; zero mismatches. Results (adjusted pooled):
against v512dual at 1 thread 0.674x [0.590, 0.768],
ESTABLISHED NEGATIVE (every session and pooled entirely
below 0); against v512dual at 2 threads 0.750x [0.654,
0.863], NOT SIGNIFICANT under the every-session rule
(one session straddling, direction uniformly negative);
against the current v512 build at 2 threads 1.366x
[1.192, 1.569], NOT SIGNIFICANT (third session
straddling). Control (maskC vs maskC) measured a pooled
phantom of +0.170 log ratio in arm B's favour under
this campaign's rising load (load1 4.11 to 20.28 at
session starts), against EXP-024b's clean -0.045; the
phantom flatters every maskC figure, leaves the
secondary lead at about 1.15x net, and changes no
formal tier. Verdict: design C holds no advantage
against today's production search and is superseded by
v512dual; its EXP-024b fallback certification is
downgraded to a historically verified form against the
library build of that date, not renewed against today's
builds. No discards; no production file modified. Full
record: exp046/EXP046_REPORT.md; gates, sessions and
analysis under exp046/RAW_RESULTS/. (EXP-044 stands
pre-committed to the -mtune scheduling study,
NOVA-ER-0005, per the Extreme Research portfolio; it
runs next.)

## EXP-044 record (2026-11-16)

EXP-044 (NOVA-ER-0005: -mtune scheduling variants of
the v512 kernel, the study EXP-041 left open).
EXP-041 found -mtune=znver3 cuts the standalone
compress body's vector moves 64 to 33 at the same 29
ALU per round but never timed it. EXP-044 rebuilt the
production kernel source (mining/cpu/bal_avx512_mb.c)
research-side with -mtune=znver3 and -mtune=znver4
added to the kernel TU only, all other flags
identical to production (the replica build with no
extra flag is byte-identical to the production
library, sha256 6dfd8d42...), and timed both against
the production library on the AMD EPYC 9D25 host,
EXP-017 protocol, batch scope (category D), 2
threads, 9 sessions, 120 paired 65,536-hash blocks
each, sessions rotated by round, live miner running
and untouched (shares accepted 480 to 480). Census
first: EXP-041's numbers reproduce exactly on the
full production kernel (v_compress16: production 135
insns / 64 moves / 29 ALU; znver3 and znver4 both
113 / 33 / 29; full hot path v_compress16 + v_walk:
production 4,987 insns / 163 moves, znver3 4,827 /
132, znver4 4,695 / 132). Gates first: 786,432 batch
differentials vs hashlib across the three libraries,
candidate-set equivalence vs a hashlib recount at
densities 0, 2^-16, 2^-8, 1 on 36 spans including
nonce boundary spans, 2-thread accounting and
genesis checks, uniform rc -2 refusal of spans
crossing 2^32; zero mismatches. Results (adjusted
pooled): znver3 1.075x [0.941, 1.223], NOT
SIGNIFICANT (every session straddling); znver4
0.966x [0.848, 1.099], NOT SIGNIFICANT (sessions
disagreeing in sign). Control (base vs base)
measured a pooled phantom of +0.1216 log (1.129x)
favouring arm B, larger than znver3's entire point
estimate (+0.0723); net of the phantom both point
estimates are negative (descriptive only, no tier
changed). Search scope not run under the predeclared
rule (neither variant's batch point estimate
positive and at or above the 0.1216 noise floor).
Verdict: the move reduction is real in the emitted
code and null at the rate level within this
campaign's resolution; neither variant is a Stage 6
integration candidate; production flags unchanged.
No discards; no production file modified. Full
record: exp044/EXP044_REPORT.md; build manifest,
census, gates, sessions and analysis under
exp044/RAW_RESULTS/.

Next unreserved ID: EXP-047.

## EXP-047 record (2026-11-16)

EXP-047 (NOVA-ER-0007, register X-096: cross-backend
differential fuzzing at scale). Predeclared campaign
(seed 47047) through the production ComputeEngine seam on
the AMD EPYC 9D25 host, backends v512dual, v512, shani,
avx2, c, cpu (CUDA absent, no GPU). Batch campaign
completed at full predeclared scale with zero mismatches:
4,615,011 digests per native backend, every one
byte-identical to the hashlib reference, 46,150,110 direct
pairwise comparisons among the five native backends
(69,225,165 pairwise relations counting the reference
relations), across random headers, boundary nonces,
unaligned spans, partial batches and spans ending exactly
at 2^32; the largest single differential campaign in the
programme (prior maxima 648,000 and 491,520). VERIFIED as
a correctness result; no performance claim. The search
campaign then FAILED under its predeclared failure rule
at its first case (S_FULL-00): search_first_counted on
v512 returned nonce 2083236893 where the predeclared
criterion S-C required the span minimum 2083204125.
Critical finding, characterized and reproduced (minimal
repro returns the exact campaign nonce on call 0): the
production search winner is first-publisher-wins by
design (mining/cpu/bal_search.h bal_ctx_publish over
bal_partition thread spans; all five native search ABIs
share it), so which genuine hit a multithreaded native
search returns is scheduling-dependent. Characterization
(1,242 search calls): non-minimum genuine returns on all
five native backends (22 to 130 of 200 at density 1;
present at 2^-8 and 2^-16), always exactly another span's
first nonce, eliminated at one thread; zero wrong
digests, zero false hits, zero false misses anywhere;
batch_search hit sets exact on every executed surface.
The minimum-hit invariant is an ESTABLISHED NEGATIVE;
the cpu backend and single-threaded search do return the
minimum. Production impact: none on mining correctness
(returned candidates are independently verified before
submission; any genuine hit is a valid candidate); a
caller needing the minimum must use batch_search
enumeration or one thread. Not executed after the stop:
the remaining search cases (including the T_SOLO ladder)
and the Gate 3 malformed-input set, recorded as
unverified. No production file modified; live miner
untouched (shares accepted 586 to 587). Full record:
exp047/EXP047_REPORT.md; manifest, batch results,
mismatch record, characterization and repro under
exp047/RAW_RESULTS/.

Completion campaign (2026-11-16, same seed and host):
the unexecuted remainder was executed in full under a
corrected S-C criterion predeclared in
exp047/EXP047_COMPLETION_REPORT.md (found-flag agreement
plus hit genuineness judged; minimum identity recorded as
a statistic, never pass/fail). Search ladder: all 30
cases, 17,694,720 nonces per backend per surface, 390
surface checks, 108 search_first_counted calls, zero
found-flag disagreements, zero false hits, zero false
misses, zero wrong digests; empty-set agreement at the
exact solo density (T_SOLO, difficulty 0.02, zero
reference hits in 8,388,608 nonces per backend as
expected); boundary first-hit calls returned the named
nonces on all six backends. Minimum-identity statistics:
cpu 16 of 16 minimum; native backends 6 to 13 of 16
minimum with every non-minimum return a genuine hit
(first-publisher-wins, as characterized). Gate 3 executed
as campaign items: G1 to G14 ValueError uniformly on all
six engines, G15/G16 refused on all five native backends,
zero deviations, PASS. EXP-047 roll-up: batch VERIFIED,
search VERIFIED under the corrected criterion, Gate 3
PASS; the original minimum-identity criterion stands as
an ESTABLISHED NEGATIVE, and whether to add a minimum
reduction to production search or accept and document
the semantics is left to a future gated decision. No
production file modified; live miner untouched (shares
accepted 587 to 589). Completion records under
exp047/RAW_RESULTS/ (completion_manifest.json,
completion_search_results.json,
completion_sc_statistics.json,
completion_gate3_results.json).

Next unreserved ID: EXP-048.

## EXP-048 record (2026-11-16)

EXP-048 (NOVA-ER-0008: category F end-to-end measurement
at production difficulty for the solo and pool
pipelines, extending EXP-040 which measured the GBT
pipeline only). Harness-side wrapping only, zero
production changes: production SoloServer (vardiff
disabled, the production configuration) and a local
harness pool stub, both mined by the production client
path (StratumClient, ComputeEngine v512dual,
mainnet_live loop shape) against the regtest node at the
production share difficulty 0.02. Scenarios per
pipeline: A empty, B loaded (501 transactions), C
amplified (search target divided by 2^2 in the compute
proxy; 2^24 on the share target is arithmetically
infeasible), plus solo D with vardiff enabled on
production defaults, separately labelled. 136 timed
runs, 0 failed, every run exactly one Core-accepted
block passing the EXP-036 gate. Non-search overhead
medians per block: solo 97.0 ms empty, 152.4 ms loaded,
115.6 ms amplified, 89.3 ms vardiff-on; pool 55.9 ms
empty, 210.7 ms loaded, 97.7 ms amplified; against
EXP-040's GBT 43.5 / 206.3 / 49.5 ms, the same band.
Hypothesis verdict: same-order overheads SUPPORTED;
share handling the largest stage SUPPORTED broadly
(the server submit path inside the verdict wait) and
REFUTED narrowly (validate plus EXP-036 verify is only
about 2 to 5 ms per share; the mass is submitblock and
chain confirmation); amplified method transfers with
zero production changes SUPPORTED with the stated
factor adaptation. Counted-hashes accounting probe
recorded (the AVX-512 counted attempts are the parallel
search's own accounting, not a positional census).
Live miner untouched (share census 589/8 before, 600/8
after). Full record: research/sha256d/exp048/
EXP048_REPORT.md and RAW_RESULTS/.

Next unreserved ID: EXP-049.

## EXP-049 record (2026-11-16)

EXP-049 (NOVA-ER-0009, register R-35: offline benchmark
mode in the production binary). New production module
mining/bench_mode.py: one command (python3
mining/bench_mode.py) prints the host profile and a
category E rate through the production ComputeEngine
search path on a fixed work unit (header bytes(range(80)),
target 1, 262,144 hashes, byte-identical to the
scheduler's R-35 unit). The safety property is structural:
the module imports only the standard library plus
gpu.engine, so its code path contains no endpoint
resolution, no Stratum client and no submission symbols;
a dedicated module was chosen over a mainnet_live.py flag
because mainnet_live imports the Stratum client at module
level. Gates: 1/2 self-check on every invocation (1,024
batch digests byte-identical to hashlib, genesis candidate
verified against the known hash and target, zero
mismatches); Gate 3 four ways (AST scan, import closure,
socket-rigged run, strace run with zero network syscalls;
endpoint config hash unchanged); Gate 5 clean-environment
run from a foreign cwd; Gate 4 paired campaign against
Scheduler._measure (3 sessions, 60 pairs, randomized
AB/BA, criterion predeclared in the report before the
run): pooled mean log ratio +0.178, bootstrap CI95
[-0.062, +0.418] contains 0, AGREEMENT VERIFIED at that
width (point estimates consistently positive, unexplained,
recorded as an observation). Suites: test-exp049 20/20,
test-gpu, test-mainnet-live, test-engine all passed. Live
miner untouched (share census 602/8 before, 604/8 after).
UNVERIFIED: the Intel Xeon 8321HC host, a literal fresh VM
replacement run, tighter agreement under quiet conditions,
CUDA hosts. Full record: research/sha256d/exp049/
EXP049_REPORT.md and RAW_RESULTS/.

Next unreserved ID: EXP-050.

## EXP-050 record (2026-11-16)

EXP-050 (NOVA-ER-0010, register R-26: endpoint health
policy for the pool leg). New production module
mining/endpoint_health.py: EndpointHealthPolicy, a named,
inspectable decision object (ordered endpoints, N
consecutive errors before failover, a timed failback
retry of the primary, and a damping window bounding
failbacks, the addition the poclbm precedent lacks).
Configuration lives in mining/endpoint_config.py
(pool_health section, pool_health_config(),
pool_policy_endpoints()); defaults reproduce today's
single-endpoint behaviour exactly (enabled false, no
fallbacks), so the live stack is unaffected until an
operator enables it. Wiring is additive: StratumClient
gains an optional endpoint_policy (None is the historical
behaviour byte for byte), connect_initial() for the
startup path, policy-driven retargeting inside the
existing reconnect loop, failback probes between reads,
and submits_unresolved_on_reset accounting (a share is
submitted exactly once; verdicts that can never arrive
are reported as their own category, EXP-037 rule);
mainnet_live builds the policy in pool mode when enabled
and carries policy.status() in its status events. The
autopilot restart is unchanged and remains the outer
backstop. One real defect was found and fixed during the
campaign: pending-submit registration raced fast verdicts
(a discard could land before the add, leaving a phantom
pending id); registration now happens inside _send,
before the bytes leave. Gates: 1, 2, 4, 6 do not apply
(no new hash path, no benchmark claim, no consensus
surface). Gate 3 fault injection against local stubs
(research/sha256d/exp050/exp050_fault_injection.py, 7
scenarios, all passed): startup failover and startup
exhaustion (connect raises, backstop intact); mid-job
failover to the first fallback job in 0.084 s against a
4.0 s job interval; exactly one failback on recovery;
flapping primary (4 s up / 2.5 s down) earned exactly 1
failback in 26 s under a 60 s damping window; mid-session
exhaustion reported once with no faked recovery, recovery
logged when the primary returned; accounting identity
submitted 4 = accepted 2 + rejected 0 + unresolved 2 as
separately recorded categories, zero double submissions.
Gate 5: an isolated instance (byte copies, own .local)
running production mainnet_live through start, primary
death, failover, an accepted share on the fallback,
primary return, failback, and stop by signal, the process
alive throughout. Production suite
tests/test_exp050_endpoint_health.py (make test-exp050,
40 checks, all passing 2026-11-16 on AMD EPYC 9D25);
test-mainnet-live, test-solo and test-solo-vardiff
(59/59) also passed. Live miner untouched (share census
609/8 before, 613/8 after; the delta is the live miner's
own shares). An independent post-integration audit is
owed before any push, and before the policy is enabled
on the live stack. UNVERIFIED: failover against the real
public-pool.io, any real second endpoint (none exists in
the live config), other hosts, live enablement. Full
record: research/sha256d/exp050/EXP050_REPORT.md and
RAW_RESULTS/.

Next unreserved ID: EXP-051.

## EXP-051 record (2026-11-16)

EXP-051 (NOVA-ER-0011, register R-33: prepared-work
prefetch queue) is COMPLETE and VERIFIED at regtest
difficulty. New production module mining/prefetch.py
(PrefetchQueue, PrefetchFeed), wired into
MiningEngine.mine_cycle behind opt-in use_prefetch=False
(the disabled default is byte-for-byte the historical
behaviour and the rollback surface; pinned by test). A
background GBT longpoll feed prepares the next template
through the EXP-025 cache while search runs on the
current one; at a transition the queue serves its newest
entry only after its previousblockhash is confirmed to
still be the node's best block and its EXP-025 layered
identity is recomputed from scratch and matches the
identity it was prepared under. Any failure drops the
entry (counted by reason) and the cycle falls back to
the synchronous fetch and prepare, so a candidate
prepared under identity A is never searched under
identity B. Seven separated EXP-037 counters were added
(prefetch_enqueued, prefetch_served, prefetch_starved,
prefetch_dropped_identity, prefetch_dropped_stale,
prefetch_dropped_superseded, prefetch_dropped_overflow);
snapshot() still has no combined total. Predeclared
criteria (research/sha256d/exp051/PREDECLARATION.md,
written before measuring): H1 zero stale serves, H2
loaded median non-search overhead per block at least 15
percent below the synchronous arm, H3 at least half of
loaded prefetch runs queue-served with (gbt + prepare)
under 5 ms in served runs. Gate 3 adversarial suite
tests/test_exp051_prefetch.py (make test-exp051, all
passing, AMD EPYC 9D25): queue unit gates (stale tip,
unverifiable tip, identity confusion twice, superseded,
overflow, duplicate), feed dedupe, engine gates on a
fake node (cold starve, served cycle, identity confusion
refused, stale drop after an external block, rapid tip
changes), the disabled default, and Gate 6 on the real
regtest node (a queue-served block accepted by Core and
EXP-036 verified). NO stale serve was found anywhere.
Gate 4 in category F form through the EXP-040 harness
shape (84 timed runs, 0 failed, every block EXP-036
verified): loaded scenario B median non-search overhead
389.7 ms synchronous vs 167.3 ms prefetch, a 57.1
percent reduction (H2 PASS); served fraction in B 1.0,
18 of 18, with (gbt + prepare) at 0.0 ms median in
served runs (H3 PASS); campaign counters enqueued 62,
served 42 (every timed prefetch run), starved 6 (the
six session warm-ups), superseded 16, identity and
stale drops 0 in the campaign. Scenario A (empty) is
reported without a verdict: the removable stages are
about 7 ms there and both arms are dominated by
submit/confirm variance under load 9 to 16. Gates 1
and 2 inherited and re-run: test-exp034, test-exp036,
test-template-cache, test-exp037, test-mining and
test-exp040 all passed; make test-engine (the
intelligence suite, outside this change's import graph)
failed three times on its full-sync assertion while
external blocks were landing on the shared regtest
chain, recorded as environment interference with the
evidence in the report. The solo server seam is
declared out of scope (it does not consume
MiningEngine; its JobRefresher already pre-builds jobs
server-side). Live miner untouched (share census 614/8
before and after). An independent post-integration
audit is owed before any push. UNVERIFIED: mainnet
difficulty effect (claimed nil, unmeasured), the solo
server seam, other hosts, long-run feed soaking.
Full record: research/sha256d/exp051/EXP051_REPORT.md
and RAW_RESULTS/.

Next unreserved ID: EXP-052.

## EXP-053 record (2026-11-16)

EXP-053 (NOVA-ER-0013, register Y-098, Phase 001
H-6: chunk-2 prefix sharing inside the dual-batch
walker) is COMPLETE with an ESTABLISHED NEGATIVE
verdict at the predeclared resolution. The variant
(bal_vp_search2, research/sha256d/exp053/src/
libbal_e53prefix.so, generated from the production
bal_avx512_dual.c) executes chunk-2 rounds 0 to 2
once for the two batches of a dual group and forks
the state, removing 3 of 256 round steps
(arithmetic ceiling log(256/253) = +0.0118, about
+1.19 percent). The predeclaration
(research/sha256d/exp053/PREDECLARATION.md, written
before any variant timing, its sha256 recorded in
every session manifest) fixed the design: Gate 2
correctness first, then an EXP-017 campaign of 6
effect sessions and 2 control sessions of 30,000
paired 65,536-hash blocks each (240,000 pairs, the
budget cap), randomized AB/BA, threads 2, the
EXP-017 statistic computed by the imported
analyzer code. Gate 2 passed before the campaign
and again on rerun (make test-exp053: ALL PASSED;
108,000 randomized differentials vs hashlib on
variant and production control, byte-identical
vp-vs-vd batch outputs over 4,194,304 digests,
search agreement under the EXP-047 corrected
criterion). The completing agent re-verified the
raw campaign data pair by pair: every arm of every
pair attempted exactly 65,536 with rc 0, and every
stored log-ratio recomputes from the recorded
rates. Control pooled adjusted mean -0.0030, CI
[-0.0108, +0.0048]: contains 0, machinery valid
under the predeclared rule. Effect pooled adjusted
mean -0.0017, CI [-0.0059, +0.0027]; no effect
session significant; fraction of pairs won by the
variant 0.501. The pooled CI contains 0, its upper
bound is below the +0.0118 ceiling and its
half-width 0.0043 is at most the predeclared 0.006:
ESTABLISHED NEGATIVE at the predeclared
resolution. Any true gain is below +0.0027 log
units (about +0.27 percent) with 95 percent
confidence, which cannot be the small significant
gain hypothesised; H-6 is closed for the dual
walker (the standalone form remains EXP-013's
straddle, neither accepted nor refuted). No
integration: production files were never touched,
Gate 6 does not run on a negative verdict, and
make test-avx512dual passed after the campaign
with a fresh regtest block at height 2368 through
the production backend. The original builder died
mid-campaign on a transport error; the orphaned
campaign chain completed all 8 sessions untouched,
and a VM replacement killed the first analysis run
before output, so the analysis was rerun detached.
EXP-052 stays reserved for NOVA-ER-0012 (bake-off
hardening, which completes only across host
rotations). An independent audit is owed before
any push. UNVERIFIED: other hosts, the batch
entry's rate (Gate 2 only, no rate claimed),
thread counts other than 2, combinations with
other kernel ingredients. Full record:
research/sha256d/exp053/EXP053_REPORT.md and
RAW_RESULTS/.

Next unreserved ID: EXP-054.
