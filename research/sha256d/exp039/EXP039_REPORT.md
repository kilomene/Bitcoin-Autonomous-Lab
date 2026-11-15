# EXP-039 Report: fallback tier integration (Phase 002 step 1)

Status: COMPLETE 2026-11-15, with production changes.
Programme: NOVA SHA-X, Phase 002 step 1 (the tier
dispatch the EXP-032 report deferred as the EXP-030
programme's next phase). Host for every measurement
and gate in this report: AMD EPYC 9D25 126-Core
Processor (flags include avx2, avx512f, avx512bw and
sha_ni), 4 vCPUs visible. Evidence standard: only what
was built, tested and measured in this session counts;
labels follow the programme taxonomy.

## 1. What shipped

The two EXP-032 verified kernels are now production
dispatch tiers in gpu/engine.py. Selection order:

    CUDA, v512dual, v512, shani, avx2, C, hashlib

- shani: the SHA-NI H-01 multi-stream kernel at
  streams 4 (mining/cpu/bal_shani_streams.c over
  bal_shani_core.h, library .local/cpu/libbal_shani.so,
  counted entries bal_m_batch2 and bal_m_search2).
- avx2: the AVX2 multi-buffer kernel, 8 lanes
  (mining/cpu/bal_avx2_mb.c, library
  .local/cpu/libbal_avx2.so, counted entries
  bal_a_batch2 and bal_a_search2).

Both tiers serve the batch path AND the search path.
The EXP-022 flags precedent (batch-only) did not force
batch-only here, because both kernel forms carry
honest counted search entries: the AVX2 form mirrors
the AVX-512 group-atomic search exactly (dummy lanes
repeat the last real nonce, so backend computations
are at least the attempted count), and the SHA-NI form
hashes no dummy lanes at all (partial waves dispatch
to smaller stream instantiations), so its backend
count equals the attempted count exactly, on batch and
on search. That accounting is stated in the engine
module docstring and returned by describe().

Dispatch anchors in gpu/engine.py: library paths and
SHANI_STREAMS = 4 at lines 216 to 220; selection gates
at lines 931 (shani), 935 (avx2) and 938 to 940 (C);
_try_shani at line 1045; _m_batch and _m_batch_flagged
at lines 1167 and 1177; _try_avx2 at line 1214;
_a_batch and _a_batch_flagged at lines 1294 and 1304.
A pin keeps its pre-existing meaning: the new gates
fire for requested "auto" and for their own pins only
(a "shani" pin may cascade to avx2 then C; a "v512" or
"v512dual" pin never routes into the new tiers), which
preserves the standing forced-fallback contracts of
the older suites exactly.

## 2. Inherited work: assessment

A previous agent started this integration and stopped
mid-work. Its four kernel files and its build.py
integration were assessed line by line and ALL KEPT
unchanged; the engine dispatch, the test suite, the
benchmarks and this report are this session's work.

- mining/cpu/bal_avx2_mb.c: kernel body byte-identical
  to the EXP-032 verified research kernel
  (exp032/src/avx2_mb.c); the only differences are the
  header comment (provenance, accounting, ABI notes).
- mining/cpu/bal_shani_core.h: byte-identical to
  exp032/src/shani_core.h (diff 0 lines).
- mining/cpu/bal_shani_streams.c: kernel body
  identical to exp032/src/h01_multistream.c; the diff
  is header comments and include paths only. Its
  counted search entry reports attempted only, which
  is honest for this kernel form (no dummy lanes).
- mining/cpu/bal_fallback_probe.c: flag-free
  translation unit using __builtin_cpu_supports for
  avx2 and for sha plus ssse3; the compiled probe
  objects contain zero vector registers, so the probe
  can never fault on an incapable CPU.
- mining/cpu/build.py: the build integration was
  already present and sound (restricted flags:
  AVX2_FLAGS = ["-mavx2"], SHANI_FLAGS = ["-msha",
  "-mssse3"], probe TU flag-free; loud but nonfatal
  failure; D-1 style hashlib smoke tests at build
  time). Fresh rebuilds of both tiers returned ok with
  supported = 1 and the smoke test passing.

Compiled-code census of the shipped libraries
(objdump): libbal_avx2.so has 0 zmm registers, 0 mask
registers and 310 ymm registers (pure AVX2 code, no
AVX-512 leakage); libbal_shani.so has 474 sha256rnds2,
180 sha256msg1 and 180 sha256msg2 instructions and 0
vector registers of any width. No -march=native
anywhere; runtime gating is by CPUID probe in the
established pattern, with hasattr guards around every
new ctypes signature (D-1 discipline).

## 3. Correctness gates (all through the production seam)

Suite: tests/test_exp039_fallback_integration.py,
wired as make test-exp039 and added to test-all.
Result: ALL PASSED (12 checks), run twice.

- Selection: on this host the pins resolve auto to
  v512dual, v512dual to v512dual, v512 to v512, shani
  to shani, avx2 to avx2, c to c.
- Forced fallback: with a probe-refusing library, a
  probe-only library, or no library at all, each tier
  is skipped with a recorded reason and the engine
  still returns the exact genesis candidate set from
  the surviving fallback.
- Differentials: 124,351 batch digests per kernel
  through ComputeEngine.batch_search, byte-identical
  to a hashlib reference (6 seeded random headers x
  20,000 nonces, plus counts 1, 2, 3, 4, 5, 7, 8, 9,
  15, 16, 17, unaligned starts 7 and 13, a span ending
  exactly at 2^32, and the single nonce 2^32 - 1).
- Candidate sets: identical to the hashlib recount at
  target densities 0, about 2^-16, about 2^-8 and 1,
  on both tiers.
- Search: a planted hit returns the exact CPU digest;
  a clean miss reports attempted == count on both
  tiers; shani backend_hashes == attempted exactly;
  avx2 backend_hashes >= attempted and bounded by the
  wave rule.
- Regtest: one fresh block per tier forced active
  through the production ComputeEngine: shani at
  height 1293 (hash
  48751c5c25bddea7bb055eb72ca234258fa60752104114e33cc
  1595fbeb3f444), avx2 at height 1294 (hash
  451c313f44565615b44809f079f321b6ec82de936659fd2e0b
  c335aad320611a). Both accepted by Core.

Regression suites, run first-party on a quiet machine
after the integration: test-engine PASS (9 checks),
test-avx512 PASS (6), test-avx512dual PASS (6),
test-avx512flags PASS (7), test-mining PASS (4),
test-cpu PASS (3), test-exp039 PASS (12). An earlier
apparent test-engine failure during this session was
traced to a concurrent full-suite sweep run by
another agent mining regtest blocks on the same
chain; the isolated diagnostic and the clean rerun
both pass, and the sweep's own test-engine run also
passed. The pre-existing environment failure
test-rtl (iverilog absent) is unchanged and unrelated.

## 4. Benchmarks (EXP-017 protocol)

Driver exp039_paired_bench.py (the EXP-032 driver
adapted to production arms only), analysis
exp039_analyze.py with the exp017_analyze statistic.
Per comparison: 3 sessions, 120 paired 65,536-hash
blocks per session, randomised AB or BA order per
pair, steal and runnable-load covariates sampled
around every counted call, attempted == block size
asserted on every call. Raw sessions and the analysis
JSON are under RAW_RESULTS/. Session conditions were
heavily contended (mean runnable queue about 12; the
C batch arm's median rate was 0.83M to 1.07M H/s at 2
threads, well below its quiet-machine rate): the
paired design with covariate adjustment is what the
verdicts rest on, and absolute rates from these
sessions should not be quoted as machine capability.

Batch scope (category D, counted batch entries over
the genesis header at the difficulty-1 target):

- avx2 vs C: sessions 1.160 [1.081, 1.246],
  1.428 [1.271, 1.607], 1.185 [1.103, 1.273];
  pooled 1.252x [1.185, 1.322]. VERIFIED IMPROVEMENT.
- shani streams 4 vs C: sessions 3.097 [2.810, 3.429],
  2.564 [2.194, 3.083], 2.839 [2.401, 3.423];
  pooled 2.812x [2.573, 3.095]. VERIFIED IMPROVEMENT.

Search scope (category E, production
ComputeEngine.search_first_counted over a no-hit
65,536-nonce range at target 1):

- avx2 vs C: sessions 1.247 [1.095, 1.424],
  1.377 [1.235, 1.542], 1.281 [1.171, 1.402];
  pooled 1.300x [1.217, 1.390]. VERIFIED IMPROVEMENT.
- shani vs C: sessions 2.794 [2.411, 3.279],
  3.284 [2.848, 3.845], 2.603 [2.247, 3.052];
  pooled 2.887x [2.646, 3.154]. VERIFIED IMPROVEMENT.

Relation to EXP-032: the SHA-NI batch pooled estimate
(2.812x) sits inside the EXP-032 interval
(2.861x [2.671, 3.089]). The AVX2 batch pooled
estimate (1.252x) is lower than EXP-032's
(1.409x [1.340, 1.480]) and the two intervals do not
overlap; the kernels and flags are identical, so the
difference is attributed to session conditions (the
EXP-039 sessions ran under far heavier co-runner
pressure, which need not scale both kernels equally).
The EXP-039 verdicts rest on the EXP-039 sessions
alone, per protocol; the discrepancy is recorded, not
resolved, and does not change any verdict because the
rule is a CI entirely above 1.0, met in every session.

## 5. Fleet and safety notes

- The SHA-NI tier can never execute on a SHA-less
  host: selection requires bal_shani_supported() from
  the flag-free probe, the probe requires the CPUID
  sha and ssse3 features, and the tier's own build
  smoke test applies the same gate. The fleet's Intel
  Xeon 8321HC (no SHA-NI) will therefore select avx2
  or lower. That refusal path was NOT executed on the
  Intel host this session; it is established by
  construction and by the suite's forced-fallback
  gates, and remains the one UNVERIFIED item here.
  Behaviour on an AVX2-only host (no AVX-512) is
  likewise gated by construction and unexecuted.
- The live mainnet miner was not restarted and not
  reconfigured; it kept its existing backend
  (v512dual) throughout. The new tiers reach live
  mining only through the normal autopilot restart
  path on a host where the faster tiers are absent.
- Nothing was pushed; no fleet agent was activated.
- Practical effect: on this AMD host nothing changes
  (v512dual still wins). The tiers pay off exactly
  where they were aimed: a SHA-NI host without AVX-512
  now mines at about 2.8x the C rate instead of the C
  rate, an AVX2-only host at about 1.25x, and the
  fallback ladder no longer has a cliff between v512
  and C.
