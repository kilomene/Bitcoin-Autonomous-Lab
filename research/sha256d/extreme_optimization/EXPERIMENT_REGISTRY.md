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

## Registry state

Sixteen experiments recorded (EXP-000 to
EXP-015), plus Part B (HYPOTHESIS_REGISTRY_Y.md,
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
this machine (EXP010_PART_A_REPORT.md). Next
unreserved ID: EXP-016.
