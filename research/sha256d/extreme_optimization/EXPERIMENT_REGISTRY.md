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

## Registry state

Four experiments recorded (EXP-000 to EXP-003, one of
them carrying the integration decision run). Next ID:
EXP-004, reserved for the first X-series experiment run
under this tree (recommended: the X-067 decision re-run;
see FINAL_RESEARCH_REPORT.md).
