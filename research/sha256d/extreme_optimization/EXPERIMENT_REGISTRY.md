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

## Registry state

Ten experiments recorded (EXP-000 to EXP-009). EXP-004
to EXP-009 ran as one batch on 2026-11-14; the batch
report is EXP004_009_REPORT.md in this directory. No
integration resulted: EXP-004's predeclared criterion
failed and production is byte-identical. Next ID:
EXP-010.
