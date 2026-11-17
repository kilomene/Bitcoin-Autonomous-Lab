# Experiment Registry: Permanent Record Format and Backfill

## The format (mandate section 10, binding for new entries)

Every experiment in this programme, from EXP-004 onward,
is recorded with all of these fields:

1. Experiment ID (EXP-NNN, sequential, never reused).
2. Research hypothesis (the registry ID it tests, H- or
   X-series, quoted).
3. Mathematical or architectural justification.
4. Implementation details (files, build, flags).
5. Test methodology (harness, sizes, repeats, protocol).
6. Correctness evidence (gates run, counts, results).
7. Benchmark evidence (per-run rates, median, min, max,
   spread; coverage versus actual computations stated).
8. Hardware details (machine probe reference, contention
   conditions, load at run time).
9. Statistical analysis (spread overlap, session drift,
   decision rule applied).
10. Result (accepted, rejected, inconclusive, blocked).
11. Rejection or acceptance reason.
12. Follow-up research opportunities (registry IDs).

Entries are append-only. A later experiment may supersede
a conclusion; it may not edit the earlier entry. The
H-series registry in ../experiment_registry.md remains
the record for EXP-000 to EXP-003 in its own format; the
backfill below imports those experiments into this format
by reference, without altering the originals.

## Backfilled entries (imported 2026-11-14)

### EXP-000: Trusted baseline
- Hypothesis: none; reference measurement (Stage 3).
- Justification: no comparison is meaningful without a
  frozen baseline on a frozen harness.
- Implementation: production mining/cpu/bal_batch.c,
  intrinsics mining/cpu/bal_sha_intrin.c, Python hashlib
  fallback; harness ../experiments/bench_harness.py.
- Methodology: 1,000,000 hashes per run, 3 repeats, at 1,
  2, and 4 threads; single-call latency from 3,000
  count=1 batch calls.
- Correctness evidence: both native libraries match
  hashlib on 20,000 batch digests; genesis nonce
  2083236893 re-found by counted search; harness asserts
  attempted == count on every batch run.
- Benchmark evidence: production C medians 1T 1,314,704
  (spread 26.9 percent), 2T 1,627,792 (12.5 percent), 4T
  2,512,762 (82.6 percent); intrinsics 1T 699,926, 2T
  848,348, 4T 1,135,344; hashlib median 304,444 (1T,
  50,000 per run). Single-call latency median 31.38 us
  (production), amortized per-hash about 0.76 us at 1T.
- Hardware: EPYC 9D25 KVM guest, cap about 1.5 effective
  CPUs, live miner and node contending, load above 10;
  probe ../tools/machine_probe_2026-11-14.json.
- Statistical analysis: 4-thread production spread
  (82.6 percent) disqualifies that configuration as a
  planning figure; 2 threads adopted as the tuned
  reference configuration.
- Result: accepted as the trusted baseline.
- Reason: protocol followed; gates green.
- Follow-ups: all later experiments; raw data
  ../experiments/exp000_baseline.json; write-up
  ../baseline_performance.md. Original entry:
  ../experiment_registry.md (EXP-000).

### EXP-001: Compiler and flag sweep on production source
- Hypothesis: H-series compiler question (R-03):
  production flags (-O3 -march=native) leave performance
  on the table that other gcc flag sets recover.
- Justification: cheapest available hypothesis; worth
  closing with evidence.
- Implementation: ../experiments/compiler_sweep.py builds
  mining/cpu/bal_batch.c under 5 flag sets into
  .local/shax/; production untouched.
- Methodology: per variant, 100,000 digests verified
  against hashlib plus the genesis search, then the
  EXP-000 harness at 1M x 3, at 1 and 2 threads; assembly
  of hash_nonce inspected per variant.
- Correctness evidence: all variants pass all gates.
- Benchmark evidence (2T medians): production flags
  2,347,336; LTO 2,195,680 (minus 6.5 percent); generic
  march 2,188,081 (minus 6.8 percent); funroll 2,050,686
  (minus 12.6 percent); -O2 1,472,158 (minus 37.3
  percent). All spreads overlap production's (70.1
  percent in that session). Native variants' hash_nonce
  is instruction-identical (408 instructions, 416 B
  frame); the hot compression lives in libcrypto.
- Hardware: as EXP-000.
- Statistical analysis: no variant's median beat
  production; overlap would have barred integration
  regardless.
- Result: REJECTED (all variants).
- Reason: flags cannot move a bottleneck that is inside
  libcrypto and in the wrapper's shape, not in this
  file's codegen.
- Follow-ups: X-043 to X-045 reopen the compiler question
  for the hand kernels, per R-03's own condition. Raw
  data ../experiments/exp001_compiler_sweep.json;
  write-up ../compiler_experiments.md.

### EXP-002: H-02 direct SHA-NI kernel
- Hypothesis: H-02: a from-scratch SHA-NI kernel using
  SHA256MSG1 and SHA256MSG2 for the schedule closes most
  of the intrinsics path's 2x gap.
- Justification: the intrinsics library contains zero MSG
  instructions and recomputes the schedule in scalar C
  per nonce (R-05, bottleneck B2); the MSG construction
  is the ISA's designed cure.
- Implementation: ../experiments/h02_shani/ (shani_core.h,
  h02_shani.c, libbal_h02.so); org-form state; schedule
  entirely by MSG1/MSG2 (whitepaper GENA/GENB); prefix
  modes 0, 1, 2 folded in for H-03; a BAL_H_SCALAR_SCHED
  twin build as the equivalence reference; counted ABI
  mirroring production.
- Methodology: gates in test_h02.py; benchmarks
  ../experiments/h02_shani/bench_h02.py on the EXP-000
  protocol; assembly by asm_report.py (objdump).
- Correctness evidence: FIPS vectors through
  bal_h_compress; genesis digest exact and search finds
  nonce 2083236893; 120,000 randomized differentials
  against hashlib across the three prefix variants, zero
  mismatches; 5,000 against production byte-identical;
  scalar twin byte-identical over 20,000 (the MSG path is
  the path that ran, and it is equivalent); boundaries,
  five independent template variations, target equality
  and minus-one, candidate-set recount, and counted
  accounting including an exact early-exit figure of
  50,001 all pass.
- Benchmark evidence: session load average 10.87 at run.
  Medians: H-02 MSG 1T 1,690,859, 2T 1,966,395;
  same-session production 1T 1,471,854, 2T 1,403,332;
  scalar twin 2T 751,524 (the MSG schedule alone is worth
  about 2.6x at equal rounds); intrinsics 2T 600,023.
  Spreads 40 to 72 percent; ranges overlap. Prefix
  variants at 2T: snapshot after round 1 1,239,214, after
  round 2 1,448,868, none 1,124,879, all within each
  other's spreads.
- Assembly evidence: hot function hash_p1 494
  instructions, about 2,539 B, sha256rnds2 63, msg1 24,
  msg2 24, stack frame 0 B, 0 calls, zero scalar
  rotate/shift instructions. Whole binary rnds2 350,
  msg1 132, msg2 132; scalar twin 286 / 0 / 0.
- Hardware: as EXP-000.
- Statistical analysis: medians favour H-02 in-session;
  overlap bars any integration claim from this run alone
  (decided jointly with EXP-003's decision run).
- Result: accepted as a proven research kernel; NOT
  integrated.
- Reason: correctness is total; the performance decision
  belongs to the interleaved decision run (EXP-003).
- Follow-ups: H-01 (EXP-003), X-010, X-011, X-012, X-016,
  X-024, X-045, X-046. H-03's verdict inside this
  experiment: INCONCLUSIVE (the predicted 2.4 percent
  effect is below this VM's noise floor). Raw data
  ../experiments/h02_shani/exp002_benchmarks.json.

### EXP-003: H-01 multi-stream interleave, and the integration decision run
- Hypothesis: H-01: one thread evaluating 2 or 4
  independent nonces with independent state chains hides
  SHA256RNDS2 latency and beats the OpenSSL-wrapped path
  end to end.
- Justification: the round chain is serial per nonce
  (MATHEMATICAL_DISCOVERY.md section 3); interleaving
  independent chains is the standard cure, and EXP-002
  supplied the kernel to interleave.
- Implementation: ../experiments/h02_shani/
  h01_multistream.c (libbal_h01.so); streams 1, 2, 4 in
  one worker thread; blocked chunks; wave dispatch 4
  then 2 then 1; wave-atomic search accounting.
- Methodology: gates in test_h01.py; benchmarks
  bench_h01.py (EXP-000 protocol); decision run
  bench_decision.py: production, H-02, H-01 streams 2
  and 4, round-robin interleaved in one session, 5 x 1M,
  at 1 and 2 threads.
- Correctness evidence: 108,000 randomized differentials
  per stream count (324,000 total, zero bad); genesis;
  boundaries; odd counts; invalid stream count rejected;
  miss accounting exact; wave-accounting proof: winner
  at scan position 50,001 found with attempted == 4.
- Benchmark evidence: session load average 9.95.
  Per-worker (1 thread) medians: streams=1 1,064,406;
  streams=2 2,515,315 (2.36x streams=1); streams=4
  3,298,604 (spread 98.0 percent). Two-thread totals:
  2,022,309 / 3,171,230 / 3,481,103. Single-candidate
  latency about 30 us at every stream count
  (boundary-dominated). Decision run at 2 threads
  (load average 7.46): production median 1,183,205
  (spread 142.3 percent), H-02 2,068,798, H-01 streams=2
  1,932,862, streams=4 3,084,485 (spread 37.0 percent);
  streams=4 won 4 of 5 rounds; at 1 thread the new
  kernels' ranges fully clear production's range.
- Assembly evidence: standalone 1-stream body 176
  instructions, 7 xmm registers, frame 0 B, zero stack
  ops; all multi-stream bodies inlined into one
  2,985-instruction function, frame 1,056 B, 365 xmm
  stack ops (register spill signature of 4 streams
  against 16 xmm registers). Whole binary rnds2 474,
  msg1 180, msg2 180.
- Hardware: as EXP-000.
- Statistical analysis: the strict integration rule
  requires beating production beyond spread at the
  2-thread tuned configuration. Production's best sample
  (2,442,181) overlaps streams=4's minimum (2,130,229).
  The direction is consistent across three sessions;
  the beyond-spread margin at 2 threads is not
  established on this contended VM.
- Result: hypothesis SUPPORTED as a performance
  direction; integration DECLINED.
- Reason: the rule, applied as written. Production stays
  byte-identical; no backend was wired in; no suite or
  regtest integration work was performed, because its
  precondition was not met.
- Follow-ups: X-067 (the quiet-window decision re-run is
  the recorded next step, for example after the node
  finishes initial block download), X-001 to X-005,
  X-019 (geometry), X-006, X-007 (spill attack). Raw data
  ../experiments/h02_shani/exp003_benchmarks.json and
  exp_decision_benchmarks.json.


### EXP-004: X-067 integration decision re-run
- Hypothesis: X-067 (quiet-window re-run separates the
  ranges that overlapped in EXP-003's decision run).
- Justification: medians favoured H-01 streams=4 by 1.75x
  to 2.6x across three sessions; only the noise floor was
  in question.
- Implementation: no new code; benchmarks/
  bench_exp004_decision.py extends bench_decision.py to
  9 rounds and adds the X-070 steal sampler.
- Methodology: round-robin interleaved, 9 x 1M hashes,
  production C vs H-01 streams=2 and 4, at 2 and 1
  threads, run at the lowest-load dip observed (1-minute
  load 3.92 falling to 2.49). Node state at batch start:
  blocks 408,981 of headers 975,789, IBD true, progress
  0.0812: the window is relative, recorded as such.
  Predeclared rule: integrate only if streams=4 minimum
  exceeds production maximum at 2 threads.
- Correctness evidence: attempted == count asserted per
  run; kernels previously gate-verified (EXP-003).
- Benchmark evidence: benchmarks/exp004_decision.json.
  2 threads: production median 1,463,346 (min 584,142,
  max 2,346,013, spread 120.4 percent); streams=2 median
  2,361,226; streams=4 median 4,212,571 (min 2,057,942,
  max 5,507,203, spread 81.9 percent). 1 thread:
  production 833,012; streams=4 2,553,065.
- Hardware: EPYC 9D25 guest, live miner and node running;
  steal 2.24 percent (2-thread config), 1.43 (1-thread).
- Statistical analysis: streams=4 minimum exceeds
  production's median by 41 percent but not its maximum;
  separation not achieved; spreads remain 82 to 142
  percent despite the dip.
- Result: rejected (the integration, not the kernel).
- Reason: the strict beyond-spread rule is unmet for the
  second time; production stays byte-identical.
- Follow-up: revisit after node IBD completes; a future
  contender (EXP-007's multi-buffer) needs its own
  decision run under the same rule.

### EXP-005: Stream geometry sweep
- Hypothesis: X-001, X-002, X-004, X-005 (stream count
  and assignment geometry inside the H-01 framework).
- Justification: EXP-003 mapped only counts 1, 2, 4 with
  blocked assignment; 3 and 6 and strided assignment were
  unmeasured points on the programme's central curve.
- Implementation: src/h01_geo.c (streams 1, 2, 3, 4, 6;
  mode 0 blocked, mode 1 strided), libbal_geo.so.
- Methodology: full gate set per variant via
  tests/gates.py and tests/test_exp005_geo.py; combined
  interleaved benchmark, 5 rounds x 1M at 1 and 2
  threads (benchmarks/exp005_008_kernels.json; session
  load rose 2.82 to 10.86, recorded).
- Correctness evidence: ALL gates pass for all ten
  (streams, mode) variants, at least 100,000 randomized
  differentials each; wave-exact early-exit accounting
  derived and asserted per geometry (blocked s3 50,001;
  blocked s6 100,000; strided s4 50,004).
- Benchmark evidence: 2-thread medians (H/s): blocked
  s1 1,419,401; s2 2,046,508; s3 1,999,538; s4 2,476,649;
  s6 2,593,711; strided s3 3,360,311; strided s4
  3,473,271 (spread 52.3 percent). Assembly: 2- and
  3-stream bodies standalone, frame 0 B, zero stack ops;
  the 4/6-stream inlined walk body is 4,563 instructions,
  frame 1,536 B, 790 xmm stack ops.
- Hardware: as EXP-004.
- Statistical analysis: the curve is flat-topped from 3
  to 6 within session noise; strided meets or beats
  blocked at both counts measured at 2 threads.
- Result: accepted as the family's geometry map.
- Acceptance reason: correctness complete; best geometry
  named streams=4 strided at 2 threads, streams=6
  blocked indistinguishable.
- Follow-up: X-019 wave shapes; a quieter host to resolve
  the exact optimum count.

### EXP-006: Hand-scheduled schedule-first variant
- Hypothesis: X-006, X-007 (attacks the champion's
  measured spill cost).
- Justification: EXP-003/EXP-005 assembly showed up to
  790 xmm stack ops in the inlined multi-stream body.
- Implementation: src/h01_hsf.c: technique (a) full MSG
  schedule expanded into a stack W array before rounds
  (software-pipelined schedule build), technique (b) the
  group K vector loaded once and shared across streams.
  Technique (c), inline assembly, not built (below).
- Methodology: gates for streams 2, 3, 4 (tests/
  test_exp006_hsf.py, ALL pass); same combined benchmark
  session as EXP-005.
- Correctness evidence: full gate set per stream count.
- Benchmark evidence: 2-thread medians: hsf s2 1,903,147
  vs geo s2 2,046,508; hsf s3 2,223,113 vs geo s3
  1,999,538; hsf s4 1,887,981 vs geo s4 blocked
  2,476,649. Assembly: hot body 1,374 instructions, 117
  xmm stack ops (6.7x fewer than geo's inlined body),
  frame 2,752 B dominated by deliberate W storage.
- Hardware: as EXP-004.
- Statistical analysis: parity at 2 to 3 streams, behind
  at 4; the spill reduction did not convert to time.
- Result: rejected as champion; retained as evidence.
- Reason: W-array store/load traffic costs about what
  the spills cost, and the 2-stream compiler body
  already has a 0 B frame and zero stack ops, so
  technique (c)'s premise is refuted at pair level; it
  was not built, and that reasoning is the record.
- Follow-up: none inside this family; spill traffic is
  not the binding constraint at the best geometries.

### EXP-007: AVX-512 16-way multi-buffer (X-031, gate X-041)
- Hypothesis: X-031 (a 16-lane zmm multi-buffer beats
  the H-01 streams=4 per-worker rate); gate X-041
  (sustained AVX-512 frequency behaviour).
- Justification: width replaces interleave depth; the
  CPU exposes AVX-512F/BW with vprold rotates.
- Implementation: src/avx512_mb.c (transposed state,
  vector schedule, broadcast midstate, outer phase fed
  from inner state vectors), libbal_v512.so; gate
  program src/freq_gate.c.
- Methodology: X-041 first: alternating scalar and
  AVX-512 fixed-work blocks, two runs. Then the full
  gate set (tests/test_exp007_avx512.py) including lane
  semantics; combined benchmark session plus an
  independent confirmation session (7 rounds x 1M,
  benchmarks/exp007_confirm.json).
- Correctness evidence: ALL gates pass, including
  partial-group accounting (attempted 100,003, backend
  100,016), sub-group (5 / 16), and the 2^32 group-edge
  case. Dummy lanes are computed but never stored and
  never counted as coverage.
- Benchmark evidence: combined session 2-thread median
  6,526,467 (min 2,379,216, max 9,331,180, spread 106.5
  percent), 1-thread median 1,986,785. Confirmation
  session (heavier load): median 3,195,024 vs geo s4
  strided 2,323,591 vs production 1,035,433. X-041:
  run 1 unstable both types; run 2 scalar rates rose
  36 percent across blocks while AVX-512 rates stayed
  flat (drift -6 percent): no catastrophic penalty; the
  flat response is an unresolved observation.
- Hardware: as EXP-004; no perf counters in this guest.
- Statistical analysis: median lead reproduced in two
  interleaved sessions; ranges overlap everything, so
  no separation claim. Variance is the widest measured.
- Result: accepted as the family's fastest measured
  implementation on a median basis (VERIFIED
  IMPROVEMENT, median basis, stated conditions).
- Acceptance reason: correctness complete and the
  median ranking survived an independent re-run.
- Follow-up: X-032 (AVX2 8-way, for non-AVX-512
  machines; not built here, its rotate cost prior is
  worse on this CPU); a decision run under the EXP-004
  rule before any integration discussion; X-041 re-run
  on a quieter host.

### EXP-008: Cross-nonce phase pipelining (X-009)
- Hypothesis: X-009 (interleaving different phases of
  adjacent nonces beats same-phase interleaving at
  equal chain count).
- Justification: block 2 and the outer hash have
  different data shapes; port complementarity might pay.
- Implementation: src/h01_phase.c, run_mixed fuses
  block 2 of nonce n+1 with the outer hash of nonce n;
  declared accounting: attempted counts completed
  digests (the co-computed next block 2 is uncounted
  real work), asserted exactly (genesis probe 50,001).
- Methodology: full gate set (tests/test_exp008_phase.
  py, ALL pass); combined benchmark session.
- Correctness evidence: complete, including template
  variations and target gates.
- Benchmark evidence: medians 1,665,271 (1 thread) and
  2,104,688 (2 threads). Assembly: fused body 673
  instructions, 63 SHA256RNDS2, frame 576 B, 74 xmm
  stack ops.
- Hardware: as EXP-004.
- Statistical analysis: parity with the 2-stream
  same-phase kernel (2,046,508 at 2 threads); below
  every 4-plus-chain contender.
- Result: rejected on this core.
- Reason: both phases are the same round machinery; no
  complementarity premium appears.
- Follow-up: X-009 stays open only for cores with
  demonstrably different phase costs.

### EXP-009: Pipeline and interaction study
- Hypothesis: the pipeline around the kernel (X-059
  construction cost, span sizing, confirmation) hides
  costs that change the optimal configuration as
  kernels speed up.
- Justification: owner instruction during this batch:
  the whole computational path, not one function.
- Implementation: measurement only; benchmarks/
  bench_exp009_pipeline.py and bench_exp009_fix.py
  (real-RPC redo and min-based span redo).
- Methodology: build_candidate timed against a counting
  zero-latency stub RPC at 0/10/100/500 transactions and
  against the real regtest node; span sizes 4,096 to
  4,194,304 at 2 threads (median pass, then min-of-7
  redo); hashlib confirmation timing; a real
  MiningEngine mine_cycle against the stub with wrapped
  timers.
- Correctness evidence: not a kernel experiment; the
  stub templates pass build_candidate's own txid
  re-verification, and the real-RPC run used the node's
  own template and a wallet address from the node.
- Benchmark evidence: benchmarks/exp009_pipeline.json.
  Stub build_candidate medians: 0.018 ms (0 tx), 0.126
  (10), 0.921 (100), 8.919 (500); exactly one
  validateaddress and one getblockchaininfo RPC per
  call. Real RPC (2-tx template): 4.447 ms per call,
  validateaddress alone 3.963 ms median; GBT intake
  1.06 ms median. Per template (64 extranonce calls):
  up to about 571 ms construction at 500 tx plus about
  285 ms validateaddress latency. Span redo: small-span
  minimum-time rates meet or exceed large-span rates
  for all three kernels measured, so per-call overhead
  is under about 10 us and under 0.1 percent at span
  65,536 (best case). Mine-cycle split (stub, 0 tx):
  search 99.958 percent, construction 0.006 percent,
  other 0.036 percent. Confirmation: 1.1 us median per
  candidate (hashlib); at regtest density and 6.5M H/s
  that is about 2.8 percent of one core.
- Hardware: as EXP-004; regtest node started for the
  real-RPC parts and stopped afterwards.
- Statistical analysis: the median-based span fit of
  the first pass was noise-dominated and is superseded
  by the min-based redo, which is labelled best-case.
- Result: accepted (measurements stand; X-059 is now
  priced, not cited).
- Acceptance reason: every quantity was measured in
  this batch, with the two flawed first passes kept in
  the record and corrected.
- Follow-up: X-059's fix (cache the payout script and
  chain info per template) is a production change and
  waits for an integration window; confirmation cost
  repricing belongs with any multi-buffer integration
  decision.

### EXP-010: Part A decision closure, executed during IBD on the owner's immediate order

- Hypothesis: at least one challenger (H-01
  streams=4 strided, or the AVX-512 multi-buffer)
  separates completely from production C at 2
  threads under the predeclared rule, earning
  integration (X-067's decision, Part A of the
  Next Research Phase).
- Justification: both challengers had beaten
  production on medians in every prior session
  (EXP-003 to EXP-007) but had never cleared the
  beyond-spread criterion; the decision had to be
  closed one way or the other.
- Implementation: no new code. Contenders are the
  production library (.local/cpu libbal_batch.so),
  src/h01_geo.c streams=4 strided (mode 1), and
  src/avx512_mb.c. Decision benchmark:
  benchmarks/bench_exp010_decision.py; gates:
  tests/test_exp010_partA.py.
- Methodology: full gate set first, then one
  session, 2 worker threads, round-robin
  interleaved, 15 rounds of 1M hashes per
  contender, attempted asserted per run. Per-round
  1-minute load and per-round CPU steal recorded.
  Predeclared rule, unchanged from EXP-004: a
  candidate passes only if its minimum round rate
  exceeds production's maximum round rate.
  Execution context: the owner ordered immediate
  execution during mainnet initial block download,
  overriding the wait-for-sync condition; the
  contention is part of the result. Node 410,518
  to 410,520 of 975,803 headers, IBD true
  throughout; 1-minute load 12.39 to 12.60 for the
  whole session; session steal 1.63 percent.
- Correctness evidence: all gates pass for all
  three contenders: 108,000 randomized
  differentials each, genesis digest and search,
  boundaries, crossing and empty ranges rejected,
  five template variations, target exact equality
  and minus one, regtest-easy candidate set
  identical to a Python recount (82 over 20,000),
  exact accounting including wave-exact early exit
  (50,001 production; 50,004 strided; 50,016
  multi-buffer). No contender excluded.
- Benchmark evidence (raw data in benchmarks/
  exp010_partA_decision.json; 95 percent
  percentile-bootstrap CIs for the medians):
  production C median 1,209,879 (CI 1,078,769 to
  1,714,289), min 886,493, max 2,288,008, spread
  115.8 percent. Streams=4 strided median
  3,342,449 (CI 3,065,806 to 3,895,558), min
  1,440,195, max 5,128,658, spread 110.4 percent.
  AVX-512 multi-buffer median 3,551,903 (CI
  3,135,148 to 5,002,645), min 2,006,621, max
  9,384,014, spread 207.7 percent.
- Hardware: lab VM as EXP-004, under the heaviest
  sustained contention of the programme (saturated
  runnable queue, syncing node, live pool miner).
- Statistical analysis: median ratios 2.76x and
  2.94x with candidate median CIs clear of
  production's CI, but the predeclared criterion
  is a min-over-max separation test: streams=4
  min 1,440,195 and multi-buffer min 2,006,621
  both fall below production max 2,288,008.
  Variance attribution for the multi-buffer
  kernel: rate vs steal correlation +0.221, rate
  vs load -0.095; calm-round median 3,562,042 vs
  spiked-round median 3,515,186 (1.3 percent
  apart); production control correlation -0.521.
  Steal and load spikes do not explain the slow
  rounds; the excess variance is implementation
  behaviour under a saturated runnable queue.
- Result: neither candidate passes; no
  integration; production byte-identical. The
  Part A decision is closed for this machine.
- Rejection reason: the criterion is complete
  separation, and both candidates' worst rounds
  overlap production's best round, for the third
  recorded time (EXP-003 decision, EXP-004,
  EXP-010).
- Follow-up: reopening requires a materially
  quieter environment or a kernel whose minimum
  clears production's maximum under the same
  rule; Y-101 (contention-normalized decision
  statistic) and Y-023 (register-resident
  multi-buffer state) are the registered routes.

### EXP-011: Dual-batch interleaved AVX-512 multi-buffer

- Hypothesis: two independent 16-lane batches
  interleaved round-by-round in one worker hide
  vector round latency, as H-01 streams did for
  SHA-NI (the Y-registry's dual-batch candidate,
  Part D of the Next Research Phase order).
- Justification: EXP-003 proved the latency
  mechanism in the SHA-NI family; EXP-007 made MB
  the fastest family, and its interleave depth was
  untested.
- Implementation: src/avx512_mb2.c (v_compress16x2,
  v_group2, dual-aware walker; single-group path
  below 17 remaining nonces). Production untouched.
- Methodology: full gate set
  (tests/test_exp011_onward.py), then three
  interleaved benchmark sessions against production,
  geo s4 strided and MB16 (benchmarks/
  exp011_onward_kernels.json and exp011_confirm.json;
  session A figures transcribed in the batch report).
- Correctness evidence: all gates pass, including
  108,000 randomized differentials, genesis,
  boundaries, template variations, target equality
  and minus one, exact 32-group atomic accounting
  (early-exit attempted exactly 50,016 on the
  genesis probe; partial-group backend 100,016 at
  count 100,003).
- Benchmark evidence: medians relative to
  same-session MB16: session A 0.97x (1 thread),
  2.27x (2 threads, the highest 2-thread median of
  the programme at 8,267,078 H/s); session B 1.41x,
  0.64x; session C 0.58x, 1.15x. Spreads to 250
  percent. Assembly: dual body 239 instructions,
  48 VMOVDQA64 (memory-backed state).
- Hardware: lab VM as EXP-004; node still in IBD;
  contention the worst of the programme so far.
- Statistical analysis: cross-session medians
  inconsistent in sign at 1 thread; no separation.
- Result: not accepted as an improvement;
  retained as a promising hypothesis.
- Rejection reason (for the improvement claim):
  does not reproduce across sessions under the
  EXP-004 standard.
- Follow-up: Y-023 (register-resident dual batch)
  and Y-043 (interleave granularity), in a quieter
  window.

### EXP-012: VPTERNLOGD Boolean cone, searched, proven, and measured

- Hypothesis: Ch, Maj and the sigma XOR triples
  each cost several classic vector ops; one
  VPTERNLOGD each would shed about 6 ops per round
  (the X-027/X-094 line, with the instruction-
  level realization as the new element).
- Justification: AVX-512F includes a general
  3-input bitwise instruction; the SHA-256 round's
  Boolean functions are 3-input functions.
- Implementation: proofs/boolean_cone_search.py
  (search and proofs) and src/avx512_mb_tern.c
  (explicit ternlog forms throughout v_compress16).
- Methodology: exhaustive search over all 256
  immediates against 8-row truth tables; exact
  op-count BFS over classic ops for the lower
  bound; z3 bit-vector UNSAT for the closed forms;
  1,000,000-sample differential; full gate set;
  interleaved benches in sessions A and C.
- Correctness evidence: unique immediates Ch 202
  (0xCA), Maj 232 (0xE8), XOR3 150 (0x96); classic
  minima Ch 3 ops, Maj 4 ops, XOR3 2 ops (closure
  level sizes 8, 38, 152, 232, 256); z3 UNSAT for
  both closed forms; differential clean; all
  kernel gates pass (108,000 differentials).
- Benchmark evidence: ratios to MB16: session A
  0.81x / 0.90x, session C 0.97x / 1.13x (parity).
  Assembly: explicit form 111 instructions, 6
  VPTERNLOGD; baseline 116 instructions, 7
  VPTERNLOGD. gcc had already applied the
  optimization to the baseline.
- Hardware: as EXP-011.
- Statistical analysis: parity is the predicted
  outcome of the assembly comparison and is what
  the benches show.
- Result: accepted as a formal result and a
  codegen fact; rejected as a performance
  hypothesis (no gain exists to take).
- Acceptance reason: the search and proofs are
  complete for the stated op libraries; the
  assembly audit explains the parity.
- Follow-up: the pair (MB16, ternlog twin) is the
  programme's equal-pair noise control (Y-103);
  joint-cone sharing continues as Y-013.

### EXP-013: Cross-lane prefix and schedule sharing in MB

- Hypothesis: block-2 rounds 0..2 and schedule
  words W16/W17 are lane-independent (W18
  analysis), so computing them once per template
  removes 3 of 64 block-2 rounds and 2 schedule
  generations per group.
- Justification: the dependency derivation is
  proven; EXP-002's H-03 found the same effect
  below the noise floor in the SHA-NI family, and
  the vector family owed its own measurement.
- Implementation: src/avx512_mb_share.c (scalar
  prefix state and shared words in
  v_template_init; v_compress16_from starting at
  round 3).
- Methodology: full gate set, three interleaved
  sessions as EXP-011.
- Correctness evidence: all gates pass (108,000
  differentials; accounting identical to MB16,
  including early-exit 50,016).
- Benchmark evidence: ratios to MB16: session A
  1.06x / 1.11x; session B 1.21x / 0.65x;
  session C 0.51x / 0.86x.
- Hardware: as EXP-011.
- Statistical analysis: the predicted effect
  (about 2.4 percent of per-nonce rounds) is an
  order of magnitude below session noise.
- Result: neither accepted nor refuted; retained
  as a combination ingredient.
- Reason: effect size below the measurable floor
  on this VM, stated plainly rather than rounded.
- Follow-up: Y-093 (share inside dual batch) in a
  quieter window.

### EXP-014: K+W constant folding for template-fixed MB rounds

- Hypothesis: for block-2 rounds 0..17 except
  round 3 the schedule word is a per-template
  constant, so K[t] + W[t] folds once per template
  and saves one vector add per such round
  (extends X-024 into the vector family).
- Justification: 17 folded adds per block-2
  compression, exact by substitution.
- Implementation: src/avx512_mb_kw.c (kw table in
  the template; v_compress16_kw for block 2).
- Methodology: full gate set, sessions A and C.
- Correctness evidence: all gates pass (108,000
  differentials; accounting identical to MB16).
- Benchmark evidence: ratios to MB16: session A
  0.65x / 0.93x; session C 0.64x / 1.09x. No
  session shows a gain.
- Hardware: as EXP-011.
- Statistical analysis: consistently at or below
  parity at 1 thread; the 2-thread figures
  straddle parity without reproducing a gain.
- Result: rejected as implemented.
- Rejection reason: the folded operand's
  per-round broadcast and branch structure cost
  what the saved add was worth; the theoretical
  saving was under 2 percent of per-hash work.
- Follow-up: Y-070 (recurrence-level folding)
  only if its dependency analysis shows a much
  larger foldable set.

### EXP-015: Bitsliced 32-lane SHA-256d, implemented

- Hypothesis: bitslicing (32 hashes in bit
  planes, rotations free as reindexing) might
  beat the vector family despite ripple-carry
  additions; X-029 had only an analytic bound.
- Justification: the rotation and Boolean costs
  genuinely vanish in planes; the open empirical
  question was the addition tax on this core.
- Implementation: src/bitslice32.c (plane state,
  ripple-carry plane adds, rotating state offset,
  scalar midstate broadcast, 32-group atomic
  accounting).
- Methodology: full gate set; a Python replica of
  the logic was verified against hashlib to
  isolate a C transcription bug the gates caught
  (carry re-read after an aliased write in
  bs_add); fix, re-gate, then benches in
  sessions A and C.
- Correctness evidence: all gates pass after the
  fix (108,000 differentials; early-exit 50,016;
  partial-group backend 100,032 at count 100,003).
- Benchmark evidence: medians 109,921 and
  116,330 H/s (1 thread), 172,365 and 186,090
  (2 threads); spreads 21 to 41 percent, the
  tightest of the batch. About 0.03x of MB16 and
  about 0.13x of production in the same sessions.
- Hardware: as EXP-011.
- Statistical analysis: the deficit is two
  orders of magnitude beyond any session noise;
  no subtlety needed.
- Result: rejected by measurement.
- Rejection reason: ripple-carry addition costs
  roughly 160 plane ops per 32-bit add, several
  adds per round, swamping the free rotations;
  X-029's analytic bound is confirmed by an
  implementation.
- Follow-up: hybrid schedule-only bitslicing is
  registered as Y-004; the full form is closed
  on this core.

### EXP-016: Nonce dependency derivation for block 2 (Phase 6)

- Hypothesis: the dependence of block 2's schedule
  and state on the nonce word W3 either supports a
  nonce-separation work reduction (the premise of
  Y-065 and Y-075) or refutes it; the 67-round
  precomputation ceiling implies the boundary but
  had never been derived word by word.
- Mathematical basis: the schedule recurrence and
  round function, analysed by sound per-bit
  influence masks with a carry bound for modular
  addition, sampled functional classification
  (IND, AFF, LIN, NONLIN) with delta linearity
  tests, and z3 bit-vector proofs at the boundary.
  Full derivation: ../phase6/MATHEMATICAL_
  DISCOVERIES.md, MD-1.
- Implementation: ../phase6/src/nonce_dependency.py
  (pure-Python reference SHA-256, masks,
  classification, z3 through the repo-local solver
  environment). Runtime about 16 s of CPU.
- Correctness evidence: the reference
  implementation matches hashlib bit-exactly on
  random messages and on the production miner's
  header, inner and outer shapes; the z3 W20
  counterexample was re-verified numerically in
  the reference implementation.
- Benchmark evidence: not applicable (derivation,
  not a kernel). Raw results:
  ../phase6/analysis/exp016_dependency_results.json;
  proofs: ../phase6/proofs/exp016_z3_results.json.
- Statistical analysis: closures rest on the z3
  results (UNSAT for the W18 and W19 delta forms
  and for round-3 a and e affinity; a numerically
  verified counterexample for W20). Sampling agrees
  exactly (delta violation rates 0.0 for W16 to
  W19, 1.0 for W20 to W25, three templates in full
  agreement); the sound masks are used only for
  completeness rounds.
- Result: separation exists exactly at W18
  (delta sigma0 of the nonce) and W19 (delta the
  nonce), saving nothing at either; the state is
  affine in the nonce only at S_4 (a, e), all
  words nonlinear from S_8, sound masks complete
  at S_9.
- Decision: Y-065 and Y-075 REFUTED as work
  reductions (proof grade). The derivation is
  adopted as the programme reference for nonce
  dependency.
- Follow-up: Workstream A proceeds to EXP-019
  (representation) and EXP-020 (whole-cone
  rewriting), which EXP-016 does not address;
  Y-066 and Y-090 lose their premise.

### EXP-017: The measurement stack (Phase 6, Y-101, Y-102, Y-103)

- Hypothesis: a fine-grained paired design with
  a predeclared covariate-adjusted statistic
  returns stable verdicts on this VM where three
  whole-round min/max decisions (EXP-003
  decision, EXP-004, EXP-010) failed on
  variance.
- Mathematical basis: paired log-ratios of
  equal-size counted batches cancel drift slower
  than a block pair; OLS adjustment on the
  per-arm steal and runnable-load differences;
  pairs bootstrap intervals. Statistic and
  decision rule were written into the Phase 6
  record before the validation runs.
- Implementation: ../phase6/benchmarks/
  exp017_paired_bench.py and exp017_analyze.py.
  No kernel and no production code changed.
- Correctness evidence: geo s=4 strided and
  AVX-512 MB rebuilt from unchanged sources
  (hashes in every session manifest) and passed
  the full gate set (108,000 differentials
  each); production verified on 100,000 digests
  vs hashlib; the driver asserts attempted and
  backend equal the 65,536 block size on every
  call, and every session's coverage assertion
  holds exactly.
- Benchmark evidence: 12 append-only sessions
  in ../phase6/benchmarks/exp017/ (four
  comparisons, three sessions each, 160 pairs
  of 65,536-hash blocks at 2 threads, node in
  IBD throughout, heights 410,864 to 410,947;
  analysis_20261114T145128Z.json). Controls,
  adjusted pooled log-ratio: production vs
  itself +0.0137 (CI -0.0786 to +0.1081); MB vs
  itself +0.0077 (CI -0.1047 to +0.1167); all
  six control sessions contain 0; the old
  min/max rule passed a phantom difference in
  0 of 6 control sessions. Real comparisons,
  adjusted pooled: MB vs production +1.2652
  (CI 1.1546 to 1.3767, 3.55x), significant in
  every session; geo s4 strided vs production
  +1.0298 (CI 0.9265 to 1.1283, 2.80x),
  significant in every session.
- Statistical analysis: within-session variance
  of the paired log-ratio 1.12 to 1.61;
  between-session component 0.000 for three
  comparisons and 0.0434 for geo (its session
  means genuinely move). Covariate adjustment
  priced: pooled CI width ratios 0.970 to
  0.999 versus unadjusted, point shifts at most
  0.0004; the pairing carries the value, the
  covariates are near-neutral on this data.
  Injected-effect recovery: known +0.20
  recovered with bias at most 0.0006 over 1,000
  residual-resampled simulations per control
  design.
- Result: Y-103 PASS, Y-102 PASS at 65,536
  hashes, Y-101 PARTIAL (statistic valid,
  adjustment near-neutral). Both candidates
  are significantly faster than production
  under the EXP-017 measurement rule. That is
  a measurement result, not an integration.
- Decision: measurement stack adopted for
  Phase 6 records from EXP-018 onward. A
  proposal to replace the integration decision
  rule with the EXP-017 rule is recorded in
  ../phase6/EXPERIMENT_RESULTS.md for the
  owner; it is not enacted.
- Follow-up: EXP-018 (Y-023) is decided under
  this statistic.
- Owner decision and integration
  (2026-11-14): the owner ADOPTED the EXP-017
  rule as the programme's integration decision
  rule, replacing the min/max separation rule,
  and named the AVX-512 multi-buffer kernel
  the integration target. The kernel is now
  the production CPU backend ("v512") behind
  runtime CPUID dispatch (AVX-512F plus
  AVX-512BW, probe plus digest self-test, clean
  fallback to the OpenSSL C backend). Full
  gates passed through the production path,
  including a fresh regtest block at height
  630, and the live miner was deployed and
  verified on the new backend. Classification:
  VERIFIED IMPROVEMENT under the adopted rule.
  Full record: ../phase6/PHASE6_FINAL_REPORT
  .md, addendum of 2026-11-14.

### EXP-018: Register-resident dual-batch MB (Phase 6, Y-023)

- Hypothesis: EXP-011's dual-batch kernel
  (highest single-session 2-thread median of
  the programme, 8.27M H/s, never reproduced)
  pays for its interleave with array-handled
  state and 48 vmovdqa64; a restructured dual
  body holding both batches' state sets in zmm
  registers should cut that traffic enough to
  reproduce a gain over single-batch MB.
- Mathematical basis: the round's state
  rotation is a relabelling, (T1+T2, a, b, c,
  d+T1, e, f, g); writing new A into the vector
  that held h and new E into the vector that
  held d, with compile-time rotated argument
  tuples, performs the rotation with no data
  movement, and the orientation repeats every
  eight rounds. Exact by construction.
- Predicted effect: zero or near-zero state
  spills and no rename moves in the hot loop,
  and a significant paired gain over
  single-batch MB if state traffic was the
  binding cost.
- Implementation: src/avx512_mb_reg.c
  (bal_r_batch2, bal_r_search2; libbal_r512
  .so), sixteen named state vectors, two
  stack schedule rings, EXP-012 VPTERNLOGD
  cones, an eight-round ring unit repeated
  eight times. A full 64-round unroll was
  compiled first and superseded: 3,872
  instructions, 3,776-byte frame, 214 zmm
  stack accesses in its spill region.
  avx512_mb.c and avx512_mb2.c unmodified.
- Assembly evidence: ../phase6/benchmarks/
  exp018/asm_audit.json. Final dual body
  v_compress16x2_reg: 1,014 instructions,
  frame 2,368 bytes; zmm stack instructions
  90, of which 80 are schedule ring accesses
  and 10 are in the spill area; exactly one
  state vector is homed in one stack slot
  (0xc0, 3 accesses), the other fifteen have
  no stack traffic. EXP-011 dual body rebuilt:
  212 instructions (239 in its own report),
  frame 2,112, vmovdqa64 48 including 16
  per-iteration renames. Single-batch body:
  111 instructions, frame 1,088, vmovdqa64
  24. Residency achieved at the near-zero
  level; schedule ring traffic remains in
  all bodies.
- Correctness evidence: tests/test_exp018.py,
  all gates pass: 108,000 differentials vs
  hashlib, genesis digest and search,
  boundaries, template variations, target
  equality and minus one, regtest-easy set
  (82), exact accounting including early
  exit 50,016, partial backend 100,016 at
  count 100,003, sub-group backend 16 at
  count 5, 2^32 group edge.
- Benchmark evidence: seven append-only
  sessions in ../phase6/benchmarks/exp018/
  (analysis_20261114T151341Z.json), EXP-017
  protocol, 160 pairs of 65,536 hashes at 2
  threads per session, node in IBD (heights
  411,173 to 411,194 of 975,810 where the
  RPC answered). Primary, reg vs single
  batch MB, adjusted pooled +0.0836 (CI
  -0.0247 to +0.1902, 1.087x), pairs won
  0.554, positive point estimate in all
  three sessions, not significant in any
  session or pooled. Context, reg vs
  production: pooled +1.5027 (CI 1.4010 to
  1.6011, 4.49x), significant everywhere.
  Control (reg vs itself): -0.0945 (CI
  -0.2770 to +0.0884), null as required.
- Result: residency achieved, rate gain not
  significant; the finding is that state
  traffic was not the binding cost in the
  dual-batch shape on this machine.
- Decision: Y-023 is NOT a verified
  improvement under its predeclared
  definitions. Tier: PROMISING HYPOTHESIS
  with measured support. No integration;
  production byte-identical.
- Follow-up: variant retained in tree,
  gated and benchmarked; the audit method
  (regions from the prologue, spill slots
  by offset) is the template for Y-024 and
  any schedule-residency design.

### EXP-019: Carry-save schedule pricing, then engine (Phase 6, Y-002, Y-001)

- Hypothesis: the four-operand schedule sum
  (W[t-16] + sigma0(W[t-15]) + W[t-7] +
  sigma1(W[t-2])) prices lower as a carry-save
  network than as the add tree the production
  compiler emits, at some consumption distance
  (Y-002); if so, a whole-schedule carry-save
  generator (Y-001) is worth building.
- Mathematical basis: carry-save addition is
  exact (3:2 compressor identities, parity and
  majority, with the carry vector aligned by a
  shift). The open question was never
  correctness but price: ops, dependency
  chain, and measured cost per distance.
- Predicted effect: registry costing assumed
  one carry-save level at two ternlog ops.
  The audit below corrects that count before
  any measurement: a software compressor is
  2 VPTERNLOGD plus 1 VPSLLD (carry
  alignment), so a resolved four-operand sum
  costs 5 instructions (one level) or 7 (two
  levels) against the incumbent's 3 VPADDD,
  with chains of 4 or 5 stages against 3.
- Implementation: no kernel. Tooling only:
  ../phase6/src/exp019_price_micro.c (five
  exact forms, self-verified on 1,600,000
  random lanes, zero mismatches) and
  ../phase6/benchmarks/exp019_price_list.py
  plus exp019_l1_supplement.py. Production
  mining/cpu/bal_avx512_mb.c untouched.
- Assembly evidence: microbenchmark runner
  loops emit exactly the intended forms
  (current 3 VPADDD; cs1 2 VPTERNLOGD +
  1 VPSLLD + 2 VPADDD; csfull 4 + 2 + 1).
  The production hot loop's schedule sum is
  likewise emitted as three serially
  dependent VPADDD, so the incumbent form is
  the emitted serial chain, as the registry
  claimed for Y-001's limitation.
- Benchmark evidence: paired microbenchmark,
  three sessions, 63 paired repeats per
  separation (full table in ../phase6/
  analysis/exp019_price_list.json). At the
  recurrence's actual separations the
  carry-save forms cost, relative to the
  incumbent: separation 0 (T1) 1.27 to 1.53;
  separation 1 (sigma1 at t+2) 1.17 to 1.26;
  separation 6 (direct at t+7) 1.02 to 1.15.
  An apparent carry-save advantage at
  separations 8 to 15 under L2-resident
  operand streams (0.80 to 0.97) reversed
  under an L1-resident supplement matching
  the kernel's stack-ring residency: 1.06 to
  1.49 at separations 1 to 15, intervals
  excluding parity at 6, 10, 13 and 15. The
  node was mid-restart during the sessions
  (RPC unavailable; debug.log block files to
  height 412,014, IBD continuing).
- Statistical analysis: not a kernel
  comparison; the statistic is the paired
  log-ratio of ns per vector op within
  repeats, bootstrap intervals as recorded.
  The decisive pattern needs no subtlety:
  carry-save loses on ops, on chain, and on
  measured cost under kernel-faithful
  residency, at every separation where
  resolution is forced (0 and 1) by the
  widest margins in the table.
- Result: the price list is delivered
  (Y-002's stated success), and its winner at
  every relevant distance is the incumbent.
  No form met the predeclared gate (micro
  cost win AND chain win), so no kernel was
  built, per the experiment's order of work.
- Decision: Y-002 REJECTED as a cheaper
  materialization; Y-001 REJECTED as a work
  reduction on this instruction set at the
  pricing level (deferral is bounded by
  sigma1 at separation 1, and a sigma cannot
  consume a redundant pair). Tier:
  established negative for both.
- Follow-up: the price list is the discovery
  cost model's resolution table
  (COMPUTATION_GRAPH_RESEARCH.md section 4),
  with the compressor priced at 3
  instructions. The balanced-tree control's
  inconsistent readings across residency
  regimes are left as a data point for
  Y-003. Production byte-identical.

### EXP-020: Automated full-round rewriting (Phase 6, Y-014, Y-015)

- Hypothesis: an e-graph over the full round
  (Search A, saturation) or solver-guided
  rewriting and bounded superoptimisation
  (Search B) find an equivalent formulation
  cheaper than the production round, in ops
  or depth, somewhere the cone-by-cone proofs
  of EXP-012 could not see: shared subterms,
  addition-tree shapes, cross-term reuse.
- Implementation: expression DAGs for the
  round and the schedule cone, verified
  against an independent scalar round (2,000
  states) and the scalar schedule recurrence
  (2,000 templates) before any search.
  Saturation: 388 expressions in campaign 1,
  490 in campaign 2, fixpoint both.
  Superoptimisation: Boolean BFS over all
  256 three-input functions; addition-network
  BFS (T1 and the schedule sum exhaustive,
  the (a', e') pair to level 3 in 600 s);
  stochastic mutation seeded at the
  extraction, 20,000 proposals.
- Correctness evidence: z3 UNSAT on (a', e',
  W[t]) jointly for both extracted forms,
  behind 1,000,000-sample differentials with
  0 mismatches. The promoted variant passes
  the full gate set (108,000 differentials,
  genesis, boundaries, target equality and
  minus-one, regtest-easy set, exact
  accounting) in tests/test_exp020.py.
- Measured result: extraction reaches 28
  vector ops per steady-state round in the
  AVX-512 vocabulary, and Search B assembles
  a matching lower bound (12 offset ops +
  6 combines + 10 adds), so the incumbent's
  graph is optimal in that vocabulary. The
  one op below the emitted code (29) is
  codegen, not graph: gcc emits Maj as two
  chained VPTERNLOGD where the proven form
  is one (0xE8). The variant kernel with
  single-ternlog Ch and Maj (28 emitted,
  mechanically audited) benchmarked under
  the EXP-017 protocol: pooled adjusted
  log-ratio +0.0493 (CI -0.067 to +0.167),
  positive in all three sessions, not
  significant in any session or pooled;
  control session null as required.
- Decision: closure for the round cone
  within the stated vocabulary, rewrite set
  and bounds; P6C-007 is not a verified
  improvement under the adopted rule, no
  integration, production byte-identical.
  Tier: established (characterisation, lower
  bound, benchmark null). Full record and
  artifacts: ../phase6/EXPERIMENT_RESULTS.md,
  EXP-020; candidates P6C-005 to P6C-009 in
  ../phase6/proofs/exp020_candidates.json.

### EXP-021: Heterogeneous worker pair (Phase 6, Y-097)

- Hypothesis: on the contended guest, the
  SHA-NI streams family (latency-chain bound)
  and the AVX-512 MB family (wide-vector
  bound) stress different resources, so a
  mixed worker pool (some one-thread workers
  of each family on disjoint partitions of
  one search) beats the best homogeneous
  pool at equal total threads.
- Implementation: a pool driver
  (../phase6/benchmarks/exp021_pool.py)
  partitioning a range into contiguous
  wave-multiple chunks, one Python thread
  per worker around one counted batch call
  (MB: bal_v_batch2 threads=1; SHA-NI:
  bal_m_batch2m threads=1, streams=4,
  strided, the EXP-005 geometry), barrier
  start, makespan timing. Pools mb2,
  mixed2, shani2 and mb4, mixed22, shani4;
  all pairwise comparisons, three sessions
  each, EXP-017 paired protocol.
- Correctness evidence: the pool gate set
  (tests/test_exp021.py) passes before
  benchmarking: candidate sets equal to
  the Python recount and identical across
  six splits, every digest vs hashlib,
  genesis flagged by either family as
  partition owner, range ending at 2^32,
  unaligned start, empty partition, exact
  union accounting; the bench driver
  asserts per-worker counted accounting on
  every timed call.
- Measured result: adjusted pooled
  log-ratios, predeclared makespan
  statistic: mixed2 vs mb2 -0.1884 (CI
  -0.294 to -0.082), mixed2 vs shani2
  +0.0125 (CI -0.087 to +0.109, null), mb2
  vs shani2 +0.3100 (significant in every
  session); mixed22 vs mb4 -0.1285 (CI
  -0.203 to -0.054), mixed22 vs shani4
  +0.1442 (significant pooled), mb4 vs
  shani4 +0.2848 (significant in every
  session). A secondary recomputation
  under continuous-assignment semantics
  (sum of per-worker rates, from the
  recorded worker elapsed times) gives
  the same ordering: mixed2 vs mb2
  -0.1029 pooled, mixed22 vs mb4 -0.1007
  (CI excluding 0). Per-worker medians
  show no cross-family relief: an MB
  worker runs at 3.02M beside a SHA-NI
  worker vs 3.10M beside another MB
  worker; a SHA-NI worker at 1.68M beside
  MB vs 1.76M beside SHA-NI.
- Decision: Y-097 is NOT a verified
  improvement; the reproduced ordering is
  MB pool above mixed pool above (four
  threads) or equal to (two threads) the
  SHA-NI pool, the opposite of the
  registry's success line against the MB
  pool. Tier: established negative for
  the heterogeneity mechanism on this
  guest. No integration; the homogeneous
  MB configuration production already
  runs remains the fastest measured.
  Production byte-identical. Environment
  note: all measurements predate the VM
  replacement of about 18:08 UTC onto a
  host without SHA extensions or VBMI, on
  which neither research library as built
  re-executes (full note in the EXP-021
  record). Full record and artifacts:
  ../phase6/EXPERIMENT_RESULTS.md,
  EXP-021; benchmarks/exp021/ (18
  sessions, the analysis, the secondary
  analysis).

### EXP-022: Flags-only MB batch via mask registers (Phase 6, Y-084)

- Hypothesis: MB batch mode stores 32 bytes
  per hash that most consumers never read;
  a batch form that computes the target
  comparison in vector form, stores one mask
  bit per hash, and extracts digests only
  for flagged lanes gains in batch-shaped
  consumers (verification, statistics) at
  stated candidate densities. The registry
  scopes the claim to batch mode; a
  search-mode reading (retiring lanes
  mid-batch) is structurally void in the
  lockstep kernel, since a lane's digest
  exists only when its group completes.
- Implementation: research variant
  avx512_mb_flags.c (the EXP-007 kernel
  unchanged in its batch and search paths)
  plus bal_v_batchf2: after the two
  compressions, a vector lexicographic
  compare in v_meets significance order is
  carried in opmask registers, the group
  result is one __mmask16 accumulated into
  a flag-bit array, and the transpose store
  and per-lane extraction happen only for
  flagged lanes (or never, with digests
  NULL). Built on the current Intel host
  with the restricted flag set
  (-O3 -mavx512f -mavx512bw), the baseline
  from the unmodified research source.
- Correctness evidence: gates
  (../phase6/benchmarks/exp022_gates.py)
  all pass before timing: 154,316
  density-1 differentials vs hashlib,
  candidate-set parity with production at
  densities 0, 2^-16, 2^-8 and 1 in both
  extract and pure modes, genesis nonce
  recovery with hashlib digest equality,
  target equality and minus/plus-one
  boundaries, accounting parity on 32
  (count, threads) pairs; the bench driver
  asserts attempted and backend on every
  timed call.
- Measured result: adjusted pooled
  log-ratios under the EXP-017 paired
  protocol, three sessions per comparison,
  every session individually significant.
  Flagsx vs production batch at density
  approx 0, two threads (the predeclared
  primary): +0.5984 (CI +0.5042 to
  +0.6905), 1.82x, pairs won 0.742. At
  2^-8: +0.4628, 1.59x. At density 1:
  +0.2854, 1.33x. Pure flags at density
  approx 0: +0.6344, 1.89x. Primary at one
  thread: +0.6033, 1.83x. The effect is
  monotone in the unread-digest fraction,
  as the mechanism predicts: what is
  removed is production's batch epilogue
  (staging stores, scalar extraction of
  all sixteen digests per group, the
  per-hash output copy, the scalar
  per-lane compare), roughly half the
  batch call at sparse densities.
- Decision: Y-084 is a VERIFIED
  IMPROVEMENT in batch scope under the
  adopted rule. No integration by this
  experiment: the live miner's search path
  never paid the batch epilogue, and
  adopting a flags-only output shape for
  the engine's batch consumers is an
  interface decision for the owner,
  recommended for flags-and-rare-digests
  consumers at about 1.8x on
  sparse-candidate batch work. Production
  byte-identical. Full record and
  artifacts: ../phase6/EXPERIMENT_RESULTS.md,
  EXP-022; benchmarks/exp022/ (15 sessions,
  gates record, analysis).

### EXP-023: Midstate amortisation family (Y-076, Y-077, Y-079)

- Hypotheses: Y-076 (extranonce-dimension
  midstate amortisation in the solo shape),
  Y-077 (two-level midstate cache for job
  families), Y-079 (snapshot-depth decision
  table by template field), tested as
  written.
- Audit first: in the GBT path,
  build_candidate recomputes the full
  transaction pass (500 txid and 500 wtxid
  recomputations at 500 transactions), the
  full merkle tree (503 double hashes), the
  body join and two RPC round trips on every
  extranonce call (17.81 ms median per call
  at 500 transactions on this host, up to
  1,139.9 ms per template over 64 calls);
  about 99.6 percent of that repeated work is
  extranonce-independent. No lab serving path
  rebuilds a midstate per extranonce step:
  the stratum step costs 117.9 us against a
  full nonce scan (share 3.4e-7), and the
  solo server holds no midstate at all (its
  per-share validation prices at 24.3 ms at
  500 transactions, its own full rebuild).
- Correctness evidence: gates all pass
  before timing (../phase6/benchmarks/
  exp023_gates.py): the round stepper
  matches PureSHA256 and snapshot completions
  match hashlib; 1,320 randomised
  byte-identity cases of the amortised
  builder against build_candidate; the
  merkle spine equals merkle_root at 47 leaf
  counts; the Y-079 table verified for all
  32 field subsets plus two boundary rows.
- Measured result: the two-level prototype
  (family constants, per-template
  transaction pass and merkle tree, coinbase
  spine per step) under the EXP-017 paired
  protocol, three sessions per comparison,
  every primary session significant. 16
  extranonce steps on one 500-transaction
  template: pooled 18.49x (adjusted +2.9174,
  CI +2.7884 to +3.0406), pairs won 1.000. At
  100 transactions: 16.46x. Sixteen jobs of
  one family, one step each: 22.06x, pairs
  won 1.000. Boundary control (tx set churns
  every job): 0.97x, not significant, as the
  mechanism predicts.
- Decision: Y-076 REJECTED as specified,
  established negative: its cache target is
  not extranonce independent (a root change
  alters block-1 bytes 36 onward and the
  midstate; only the R8 prefix, rounds 0 to
  8, survives an extranonce step) and no
  serving path rebuilds a midstate per
  extranonce step for it to save. Y-077
  VERIFIED IMPROVEMENT at the data level in
  the serving path (prototype; integration
  into mining/engine.py recommended to the
  owner, break-even about 1.8 steps per
  template); its compression-prefix
  mechanism is separately rejected as
  immaterial (valid without alignment only
  to R8, to R11 only under 2^-96 merkle-head
  alignment, worth at most about 304 us per
  block-1 compression in a Python path and
  zero in the kernel path). Y-079 VERIFIED
  TABLE: deepest snapshots are none (version
  varies), R0 (prevhash), R8 (merkle), B2R0
  (time), B2R1 (nbits), SCH17 (none of the
  five); the named block-1 half (R11) is
  deepest for no field subset, and a
  tail-word-only change leaves the full
  midstate valid. Production byte-identical.
  Full record and artifacts:
  ../phase6/EXPERIMENT_RESULTS.md, EXP-023;
  benchmarks/exp023/ (12 sessions, gates
  record, audit, four analyses).

## Registry state

Twenty-four experiments recorded (EXP-000 to
EXP-023), plus Part B (HYPOTHESIS_REGISTRY_Y.md,
Y-001 to Y-108) and Part C
(PERFORMANCE_CEILING.md) of the Next Research
Phase. EXP-011 to EXP-015 ran as one batch on
2026-11-14; the batch report is
EXP011_ONWARD_REPORT.md in this directory. No
integration resulted from that batch and
production is byte-identical: it produced no
verified improvement, two closures (EXP-012,
EXP-015), one implementation negative (EXP-014),
and two unseparated promising results (EXP-011,
EXP-013). EXP-010 (Part A decision closure) ran
afterwards on the owner's immediate order, during
initial block download rather than after sync:
both challengers failed the predeclared
beyond-spread criterion a third time, no
integration was performed, production remains
byte-identical, and the decision is closed for
this machine (EXP010_PART_A_REPORT.md). Phase 6
opened 2026-11-14: its first assignment audited
the programme, corrected the 125-round, ceiling
and memory conclusions in place, ranked all 108
Y hypotheses, built the discovery system's first
component, and executed EXP-016, which refuted
Y-065 and Y-075 as work reductions with proof
grade evidence. EXP-017 (the measurement stack)
has since run and is recorded above; EXP-018
(Y-023, register-resident dual-batch) has also
run and is recorded above: residency achieved,
no significant gain over single-batch MB, not
a verified improvement. EXP-019 (carry-save
schedule pricing) has also run and is recorded
above: the price list closes Y-002 and Y-001
as established negatives, and no kernel was
built. EXP-020 (full-round rewriting) has also
run and is recorded above: the round cone is
characterised at its vocabulary optimum (28
ops, matching lower bound), the single
codegen-gap candidate promoted, gated and
benchmarked to a non-significant result, and
production remains byte-identical. EXP-021
(Y-097, heterogeneous worker pair) has also
run and is recorded above: the mixed pool
reproduces below the homogeneous MB pool at
both thread counts under both timing
semantics measured, Y-097 is an established
negative, and no integration resulted.
EXP-022 (Y-084, flags-only MB batch) has
also run and is recorded above: the
flags-only batch form is a verified
improvement in batch scope at all three
stated densities (pooled 1.82x at sparse
candidates), production byte-identical,
integration of the output shape left as
the owner's interface decision.
EXP-023 (Y-076, Y-077, Y-079, the midstate
amortisation family) has also run and is
recorded above: Y-076 is rejected as
specified (no per-extranonce midstate
rebuild exists in the serving paths, and
its cache target is not extranonce
independent past round 8), Y-077 is a
verified improvement at the data level in
the serving path (pooled 18.49x on
extranonce steps at 500 transactions,
22.06x on job families, parity when the tx
set churns every job), and Y-079 is a
verified snapshot-depth table whose named
block-1 half depth serves no common field
variation. Production byte-identical.
Phase 6 records live in ../phase6/ (plan,
results, final report). Next unreserved ID:
EXP-024.

---

## Registry addendum (2026-11-14): Phase 6B reservations

The following IDs are reserved by the Phase 6B
directive and the Assignment A audit. Status for
each: RESERVED / NOT STARTED. Full predeclared
records (hypothesis, success criterion, gates) live
in ../phase6b/. No existing entry above is altered
by this addendum, and no ID is renumbered. Next
unreserved ID after this addendum: EXP-030.

### EXP-024 (Phase 6B, Track A)

Scope: AVX-512 mask-based early-exit search:
bring the EXP-022 vector mask comparison into the
real production early-exit search path and measure
it there. Status: COMPLETE 2026-11-15. Gates G1 to
G9 PASS; fresh regtest blocks at heights 824 (design
C) and 825 (design B) through the mask kernel.
Primary comparison (design B vs production search,
density 0, 2 threads, EXP-017 protocol): pooled
1.169x [1.031, 1.327], significant pooled and in 1
of 3 sessions, so the predeclared every-session
criterion is NOT met. Design C: 1.416x [1.255,
1.603], significant in every session and pooled on
its own comparison, not promoted (not the
predeclared primary; its density-0 margin is not
attributable to adaptive extraction). Verdict:
PROMISING HYPOTHESIS; not integrated; confirmation
run EXP-024b specified. Record:
../phase6b/EXP024_MASK_SEARCH.md.
EXP-024b (confirmation, executed 2026-11-15,
owner approved): design C predeclared primary;
pooled 1.398x [1.242, 1.578] vs production at
density 0, 2 threads, significant in every session
and pooled, criterion MET; control null;
same-process B/C interleave 1.011x null (the
EXP-024 B/C divergence was layout, not code).
Design C is a VERIFIED IMPROVEMENT (search scope);
not integrated; EXP-026 DualMask stays the leading
integration candidate and C the certified
single-batch fallback.

### EXP-025 (Phase 6B, Track A)

Scope: EXP-023 cache correctness: complete
dependency analysis and layered cache identity for
the EXP-023 prototype, with adversarial invalidation
tests, before any cache integration is trusted.
Status: COMPLETE 2026-11-15 (ACCEPTED as a
correctness repair; aligned here 2026-11-15 by
EXP-026, whose agent found this entry still marked
reserved while the lowercase registry
research/sha256d/experiment_registry.md carried the
full EXP-025 record). Record:
../phase6b/EXP025_CACHE_CORRECTNESS.md.

### EXP-026 (Phase 6B, Track A)

Scope: extreme AVX-512 execution research: combined
designs from EXP-018, EXP-020, EXP-022 and EXP-024,
chosen from a written cost model before building.
Status: COMPLETE 2026-11-15. C2 DualMask (EXP-018
dual-batch residency plus EXP-024 opmask compare)
is a VERIFIED IMPROVEMENT in the search path at
density 0 (pooled 1.718x vs production and 1.444x
vs mask C at 2 threads, significant in every
session under the EXP-017 rule; regtest height
827); C1 TernMask is an ESTABLISHED NEGATIVE
(pooled 0.764x vs its own ingredient). Not
integrated; integration is an owner decision.
Record: ../phase6b/EXP026_AVX512_EXECUTION.md.
Addendum (2026-11-15): the owner decided on
2026-11-14 to integrate C2, and C2 is now the
production backend "v512dual" (integration record:
../phase6b/PRODUCTION_INTEGRATION_LOG.md Entry 1;
independent audit ../phase6b/
DUALMASK_POST_INTEGRATION_AUDIT.md, PASS WITH
NOTES, zero defects). The "not integrated" status
above is superseded by this addendum.

### EXP-027 (Phase 6B, Track B)

Scope: new computational representations for exact
SHA-256d outside the vocabulary closed by EXP-020
(GFNI affine forms, shuffle rotations, alternative
state and addition representations, joint
optimisation), each formally verified before any
performance claim. Status: COMPLETE 2026-11-15.
Characterised search with a negative result: the
sigma maps are proven GF(2)-linear but GFNI forms
cost out (floor 11, construction 35, incumbent 4;
Ch and Maj proven non-affine by counterexample);
pure shuffle rotations refuted exhaustively (625
patterns, 0 survivors) and the mixed form measured
at 2.00x the VPROLD price; rotated and byte-swapped
states refuted by addition counterexamples;
carry-save closed for the round cones by the
distance-0 consumption result (T1 6 or 8 vs 4);
addition counting floor met by the incumbent; the
52-bit IFMA form proven exact and costed out at 5
vs 4; cross-round sharing census 0 shared
nontrivial nodes; outer compression fully
digest-dependent (48 of 48 words, 0 independent
rounds); unrolled schedule form 259,905 nodes at
W63 vs 384 DAG ops. One sub-space left explicitly
open (non-sharing cross-round restructuring,
blocker: search-space size). No kernel built, no
benchmark claimed, nothing integrated. Record:
../phase6b/EXP027_COMPUTATION_REPRESENTATIONS.md;
proofs in ../phase6b/proofs/; differentials in
../phase6b/benchmarks/exp027/.

### EXP-028 (Phase 6B, supporting)

Scope: cross-architecture software research:
runtime detection, safe fallback and exact output
for AVX-512, AVX2, SHA extensions and ARM families,
with per-architecture evidence classes stated.
Status: COMPLETE 2026-11-15 as a roadmap and
dispatch specification. A flag-free 16-bit probe TU
and an executable dispatch specification were built
and verified on this host (probe object free of
vector mnemonics, mask 0xffff agreeing with
cpuinfo, five fallback scenarios as expected,
including the D-1 incomplete-library pattern).
AVX-512 F+BW MB: VERIFIED on two hosts (AMD EPYC
9D25; Intel Xeon Platinum 8321HC, which has no SHA
extensions and no VBMI). SHA extensions: MEASURED
in research on AMD (EXP-002/003/005; EXP-021 pool
ordering); Intel SHA SPECIFIED, UNVERIFIED, no
rate. AVX-512 wider subsets: detection specified,
no kernel, EXP-027 priced the candidate forms out.
AVX2 and ARMv8 SHA2 plus NEON: SPECIFIED,
UNVERIFIED, no kernel, no rate quoted. Portable C
and hashlib: VERIFIED floor. Not integrated.
Record: ../phase6b/EXP028_CPU_ARCHITECTURES.md;
artifacts in ../phase6b/benchmarks/exp028/.

### EXP-029 (Phase 6B, supporting)

Scope: parallel and distributed CPU execution:
exact nonce-range allocation, dynamic distribution,
failure recovery and duplicate prevention, under the
phase's standing accounting separations. Status:
COMPLETE 2026-11-15. The research allocator
prototype (tiled partition, exclusive pull leases,
idempotent completion, death and restart requeue
with repeated-computation accounting, shrink-before-
grant stealing, telemetry) is proven by targeted
cases plus a 120-trial randomised campaign: every
trial's completed intervals union exactly to the
declared range, pairwise disjoint, 20,474 repeated
computations all accounted outside unique coverage.
Coordination overhead measured for a local
in-process prototype only (120,000 nonces: 460,929
unique/s at 1 worker to 493,484 at 4 workers, chunk
10,000, on this contended guest); multi-machine
figures UNVERIFIED, none quoted. End-to-end gate:
fresh regtest block through the distributed path
accepted at height 829, hash
781cc4ef7fc3e583ff6fa9bf277c780083b7252a9d5ede4fed5d213e691a2e8f.
Centralised coordination chosen over decentralised
on coverage safety (filed comparison). Linear
scaling beyond this host UNVERIFIED; no claim
toward 500 GH/s or 140 TH/s. Not integrated.
Record: ../phase6b/EXP029_DISTRIBUTED_EXECUTION.md;
artifacts in ../phase6b/benchmarks/exp029/. Next
unreserved ID after EXP-028 and EXP-029: EXP-030.

### EXP-030 to EXP-038 (EXP-030 programme, reserved 2026-11-15)

Owner directive 2026-11-15 (record:
~/workspace/goals/bitcoin-autonomous-lab-private-bitcoin-
mining-lab/files/EXP030_DIRECTIVE_RECORD.md; programme
title: Open-Source Mining Intelligence,
CPU Architecture Transformation, Autonomous Mining and
Mathematical Breakthrough Programme). This reservation
SUPERSEDES EXP-028's naming of an AVX2 multi-buffer build
as the EXP-030 candidate: AVX2 multi-buffer work now sits
inside EXP-032. IDs:

- EXP-030: umbrella programme (Phases A to H). Status:
  IN PROGRESS, Phase A (reference repository audit)
  executed 2026-11-15. Record: ../exp030/REPOSITORY_AUDIT.md
  and ../exp030/REFERENCE_TO_NOVA_MATRIX.md.
- EXP-031: CPU and virtual machine intelligence.
  RESERVED, not started.
- EXP-032: CPU execution engine (includes the AVX2
  multi-buffer build moved from EXP-028's EXP-030 naming).
  RESERVED, not started.
- EXP-033: Bitcoin header and SHA-256d mathematical
  investigation. RESERVED, not started.
- EXP-034: Autonomous job and template engine. RESERVED,
  not started.
- EXP-035: Distributed CPU agent architecture design.
  RESERVED, not started.
- EXP-036: Exact candidate verification and block
  submission. RESERVED, not started.
- EXP-037: Mining statistics and probability engine.
  RESERVED, not started.
- EXP-038: Autonomous mining operations. RESERVED, not
  started.

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

## EXP-054 record (2026-11-17)

EXP-054 (NOVA-ER-0014, register Y-043: dual-batch
interleave granularity sweep) is COMPLETE with a
CONFIRMED verdict: the production point stands,
and the displacement hypothesis is an ESTABLISHED
NEGATIVE at the predeclared resolution. The
research build (bal_vg{G}_search2,
research/sha256d/exp054/src/libbal_e54gran.so,
generated mechanically from the production
bal_avx512_dual.c) parameterises the alternation
block size G in {1, 2, 4, 8}; only the order of
the two batches' round steps changes. Gate 2
passed before the campaign (per point: 108,000
randomized differentials vs hashlib, byte-
identical batch outputs vs the production binary
over 4,194,304 digests, search agreement under the
EXP-047 corrected criterion; the production
library passed the same set as control). EXP-017
campaign, 13 sessions of 30,000 paired 65,536-hash
blocks (390,000 pairs, threads 2): control pooled
adjusted -0.0038, 95 percent CI [-0.0146,
+0.0070], contains 0, machinery valid; build
control (research G = 1 vs the shipped binary)
pooled adjusted -0.0658, CI [-0.0763, -0.0550],
excludes 0, so candidate effects at or below that
size cannot be attributed to granularity alone.
Candidates, Bonferroni corrected 98.333 percent
intervals: G = 2 pooled adjusted +0.0016, CI
[-0.0088, +0.0121], half-width 0.0105, FLAT (any
true gain at most about +1.22 percent); G = 4
pooled adjusted -0.0521, CI [-0.0617, -0.0425],
SLOWDOWN (at or below the build offset, so not
attributable to granularity alone); G = 8 pooled
adjusted -0.1505, CI [-0.1600, -0.1408], SLOWDOWN
beyond the build offset. No candidate displaces
and none is promising, so Y-043 is closed: the
production granularity (G = 1) is confirmed with a
measured curve behind it. No integration:
production files were never touched, Gates 1, 3, 5
and 6 do not apply (portfolio), and make test-
exp054 (72 checks, tallies identical to the pre-
campaign gates.log) and make test-avx512dual
passed after the campaign, the latter with a fresh
regtest block at height 2370 through the
production backend. Eleven sessions ran on AMD
EPYC 9D25 and the final G = 4 and G = 8 sessions
on AMD EPYC 9D64 after a VM replacement (killed
sessions rerun per the predeclaration, never
resumed). The original builder ended without a
final report; the completing agent re-verified the
raw data pair by pair (attempted counts, return
codes, log-ratio recomputation with max error 0.0)
before running the predeclared analysis. The
EXP-053 audit lessons are implemented in this
driver (steal covariate in the EXP-017 form,
deterministic sha256-derived analysis seeds).
EXP-052 stays reserved for NOVA-ER-0012 (bake-off
hardening, which completes only across host
rotations). An independent audit is owed before
any push. UNVERIFIED: other hosts (the Intel Xeon
Platinum 8321HC rotation host is unmeasured; the
two AMD hosts disagree on slowdown magnitude), the
batch entries' rates (Gate 2 only, no rate
claimed), thread counts other than 2, intermediate
granularity points and combinations with other
kernel ingredients, and the mechanism of the build
offset. Full record:
research/sha256d/exp054/EXP054_REPORT.md and
RAW_RESULTS/.

Next unreserved ID: EXP-055.
