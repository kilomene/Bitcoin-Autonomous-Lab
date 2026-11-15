# EXP-039 Audit: independent post-integration audit of the fallback tier dispatch

Auditor: independent agent (not the integration author).
Date: 2026-11-15. Host: AMD EPYC 9D25 (avx2, avx512f,
avx512bw, sha_ni present), 4 vCPUs.
Scope: the production code as shipped (gpu/engine.py,
mining/cpu/bal_avx2_mb.c, mining/cpu/bal_shani_streams.c,
mining/cpu/bal_shani_core.h, mining/cpu/bal_fallback_probe.c,
mining/cpu/build.py), the suite
tests/test_exp039_fallback_integration.py, the benchmark
raw sessions under RAW_RESULTS/, and both experiment
registries. Every claim below was re-derived by the
auditor; nothing rests on the integration report alone.

## Verdict: PASS WITH NOTES

Defects: 0. Notes: 4 (N-1 to N-4). No production code was
modified by this audit.

## Check 1: dispatch order and pin semantics. CONFIRMED

gpu/engine.py ComputeEngine.__init__ tries, in order:
CUDA (requested auto/cuda/cuda-only), v512dual (auto,
v512dual), v512 (auto, v512, v512dual), shani (auto,
shani), avx2 (auto, shani, avx2), C (auto, c, v512,
v512dual, shani, avx2), then hashlib. The claimed order
CUDA, v512dual, v512, shani, avx2, C, hashlib is exact.
A shani pin cascades to avx2 then C; a v512 or v512dual
pin never enters the new tiers; a c pin enters neither.
Auditor spot checks at runtime: auto selects v512dual;
requested v512 yields backend v512 with _m_lib and
_a_lib both None; requested c yields c alone; requested
shani and avx2 select their tiers. D-1 discipline holds
for both new tiers: _try_shani (line 1045) and _try_avx2
(line 1214) check hasattr for the probe symbol first,
call the probe, check hasattr for both kernel entry
points (missing names are reported in the reason), and
only then assign argtypes and call kernel code.

## Check 2: probe safety and SHA-less refusal. CONFIRMED by construction; Intel execution UNVERIFIED (N-1)

mining/cpu/bal_fallback_probe.c uses only
__builtin_cpu_supports ("avx2"; "sha" and "ssse3") and
is compiled with no arch flags by _build_fallback_tier
in mining/cpu/build.py (the probe TU gets the base flag
list only). The compiled probe objects in
.local/cpu/.avx2-build/ and .local/cpu/.shani-build/
contain zero vector or SHA instructions (auditor objdump
census: 0 matches for xmm/ymm/zmm/sha256 patterns), so
calling a probe cannot fault on an incapable CPU.
Selection order in _try_shani guarantees the probe runs
before any kernel entry point, so the SHA-NI kernel can
never execute on a SHA-less host. The suite's forced
fallback gates (probe-refusing library, probe-only
library, absent library, per tier) all pass in the
auditor's own run of make test-exp039. Executing the
refusal on the SHA-less Intel Xeon 8321HC or on an
AVX2-only host was NOT done this session (the host here
has every feature); that item stays UNVERIFIED, exactly
as the integration report states.

## Check 3: build flags and shipped libraries. CONFIRMED

_build_fallback_tier compiles the AVX2 kernel TU with
AVX2_FLAGS = ["-mavx2"], the SHA-NI kernel TU with
SHANI_FLAGS = ["-msha", "-mssse3"], and the probe TU
flag-free; no -march=native appears anywhere in the new
build path (the one -march=native in build.py is the
pre-existing _compile helper used only by the older C
batch and intrin builds; see N-3). Auditor objdump
census of the shipped libraries: libbal_avx2.so has 0
zmm instructions, 0 mask-register operands, 310 ymm
instructions; libbal_shani.so has 474 sha256rnds2
instructions and 0 vector registers of any width. Both
match the integration report's census exactly.

## Check 4: correctness, auditor's own differential plus the suite. CONFIRMED

The auditor wrote an independent differential (fresh
hashlib reference computed in the auditor's script, not
the lab's cpu_digest) through the ComputeEngine seam:
26,203 batch digests per kernel (5 random headers x
5,000 nonces, plus counts 1, 3, 8, 9, 17, unaligned
starts 7 and 13, a span ending exactly at 2^32, and
nonce 2^32 - 1), byte-identical to hashlib on both
tiers; a planted-hit search per tier returned the exact
reference digest of a valid nonce. The lab suite was
then run by the auditor: make test-exp039, ALL PASSED
(12 checks), including its 124,351 differentials per
kernel, candidate-set equivalence at densities 0,
2^-16, 2^-8 and 1, and the forced-fallback gates.

## Check 5: regtest blocks per tier. CONFIRMED

Auditor's own run through the production path
(ComputeEngine with the tier forced, MiningEngine,
submitblock plus best-chain confirmation): chain height
1326 at audit start; shani block at height 1327 (hash
4f4e5205ac86e8af47a6874e5f88e06a739725055414cd43c2af7
591ed1bcbb7), avx2 block at height 1328 (hash
78089ff7a4d6bfd4c72da11d5b11c20fc52bbd67e8913e60122f3
7aa9fd0360b), both accepted by Core. The suite run in
check 4 independently produced shani height 1325 and
avx2 height 1326 on the same chain. All regtest work
ran sequentially.

## Check 6: benchmark verdicts. CONFIRMED

The auditor re-implemented the EXP-017 statistic from
scratch (paired log-ratio recomputed from the raw
per-arm rates, with an assertion that the stored
log-ratio field matches; OLS adjustment with one
intercept per session and standardised steal and
runnable differences plus the order covariate; pairs
bootstrap stratified by session, 10,000 resamples) and
applied it to the 12 raw session files (3 sessions x
120 pairs per comparison, attempted == 65,536 asserted
on every pair). Results (auditor's figures; claimed in
brackets):

- batch avx2 vs C: pooled 1.252 [1.186, 1.322]
  (claimed 1.252 [1.185, 1.322]).
- batch shani vs C: pooled 2.812 [2.577, 3.096]
  (claimed 2.812 [2.573, 3.095]).
- search avx2 vs C: pooled 1.300 [1.218, 1.388]
  (claimed 1.300 [1.217, 1.390]).
- search shani vs C: pooled 2.887 [2.655, 3.163]
  (claimed 2.887 [2.646, 3.154]).

All four pooled estimates match to three decimals; CI
bounds differ by at most 0.009, attributable to the
bootstrap RNG stream (N-4). Every individual session is
significant (adjusted CI entirely above 1.0) under the
auditor's recomputation as well, so all four VERIFIED
IMPROVEMENT verdicts stand. Labelling is honest: batch
comparisons are labelled category D and search
comparisons category E in the report, the bench driver
and the session files (scope fields "batch" and
"search"); nothing presents either as an end-to-end
rate.

## Check 7: accounting honesty. CONFIRMED

Kernel ABI: bal_shani_streams.c exports out_attempted
only; partial waves dispatch to smaller stream
instantiations, so no dummy nonce is ever hashed.
bal_avx2_mb.c exports out_attempted and out_backend;
its group loop adds 8 to backend per group and the real
(non-dummy) count to attempted, the v512 group-atomic
rule at 8 lanes. Engine wiring in search_first_counted
sets shani backend_hashes = out_attempted and avx2
backend_hashes = out_backend, matching the docstrings.
Auditor live calls: shani clean miss over 60,000 nonces
reported attempted 60,000 and backend_hashes 60,000
(exact); avx2 clean miss reported attempted 60,000 and
backend_hashes 60,032 (the final partial group rounded
up, at least attempted and bounded). Batch accounting
in _m_batch_flagged stashes (attempted, attempted) and
_a_batch_flagged stashes the kernel's real pair.

## Check 8: registries. CONFIRMED

EXP-039 has a full record section in both registries
that exist: research/sha256d/experiment_registry.md
(record at line 1260) and
research/sha256d/extreme_optimization/EXPERIMENT_REGISTRY.md
(record at line 1756). Both state "Next unreserved ID:
EXP-040" after the record. (The path
research/sha256d/EXPERIMENT_REGISTRY.md does not exist;
the two files above are the registry pair.)

## Check 9: long dash scan. CONFIRMED

Zero occurrences of U+2014 in all 26 EXP-039 touched
files scanned by the auditor: gpu/engine.py,
mining/cpu/bal_avx2_mb.c, bal_shani_streams.c,
bal_shani_core.h, bal_fallback_probe.c, build.py,
tests/test_exp039_fallback_integration.py, the report,
both bench/analysis scripts, all 13 RAW_RESULTS JSON
files, and both registries in full.

## Check 10: live mainnet miner undisturbed. CONFIRMED

Read-only autopilot status before the audit
(2026-11-15T20:12:04Z): autopilot pid 4778, miner pid
4781, restarts 0, shares accepted 347. After the audit
(2026-11-15T20:16:12Z): same pids, restarts 0, shares
accepted 349 (the miner kept mining throughout). The
auditor restarted nothing and reconfigured nothing.

## Notes

- N-1: Refusal behaviour on the SHA-less Intel Xeon
  8321HC and on an AVX2-only host is established by
  probe construction and the suite's forced-fallback
  gates, but was not executed on that hardware this
  session. UNVERIFIED, as the integration report itself
  records. Recommended: run make test-exp039 once on
  the Intel host when it next hosts the lab.
- N-2: The EXP-039 AVX2 batch pooled estimate (1.252x)
  sits below EXP-032's (1.409x) with non-overlapping
  CIs despite identical kernels and flags. The
  integration report records this as an unresolved
  conditions discrepancy; the auditor's recomputation
  confirms the EXP-039 figure on the EXP-039 data, and
  the verdict rule (CI above 1.0 in every session and
  pooled) is met either way. No verdict changes.
- N-3: mining/cpu/build.py's pre-existing _compile
  helper still builds the older C batch and intrin
  libraries with -march=native. That helper is not used
  by the EXP-039 fallback build path, which is
  restricted-flag throughout; recorded for completeness
  only, pre-dating EXP-039.
- N-4: The auditor's bootstrap CIs differ from the
  published ones by at most 0.009 on individual bounds
  (different RNG stream, same statistic and data). No
  estimate and no verdict is affected.

## Evidence index

- Auditor differential: 26,203 digests per kernel,
  planted hits exact, accounting invariants held.
- make test-exp039: ALL PASSED (12 checks), auditor run.
- Auditor regtest: heights 1327 (shani) and 1328 (avx2);
  suite regtest: heights 1325 and 1326.
- Auditor statistics: four pooled ratios and CIs as in
  check 6, from the 12 raw session files.
- objdump census and U+2014 scan as in checks 3 and 9.
