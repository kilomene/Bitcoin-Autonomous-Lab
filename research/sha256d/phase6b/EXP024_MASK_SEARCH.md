# EXP-024: AVX-512 Mask-Based Early-Exit Search

Experiment ID: EXP-024 (reserved 2026-11-14, Phase 6B).
Status: COMPLETE (executed 2026-11-15; record appended
at the end of this file under "Experiment record").
The predeclared sections below are unchanged from the
reservation; the record follows them.
Track: A (near-term engineering).
Registry: research/sha256d/extreme_optimization/
EXPERIMENT_REGISTRY.md (reservation addendum).
Tests Y-084's mechanism in the search path. EXP-022's
batch-scope verdict does not transfer by assumption;
this experiment exists to measure the search path
itself.

## Predeclared hypothesis

The production v512 search materialises the complete
32-byte digest of every lane of every 16-lane group
and compares each digest scalar, byte by byte, even
when no lane can be a candidate. A search form that
computes the target comparison in vector form over
the transposed final state, carries the result as an
opmask, materialises digests only for qualifying
lanes, and preserves the existing group-atomic early
exit and counted accounting will be faster than the
production search (bal_v_search2 through
ComputeEngine.search_first_counted) on the real
early-exit mining path, at mining-relevant candidate
densities, by a margin the EXP-017 rule can certify.

Null form: at mining densities (a qualifying lane is
rare), the removed work (digest materialisation and
scalar comparison of 16 lanes per group) may be a
small fraction of the three compressions' cost, in
which case the mask form will measure at parity and
the hypothesis fails honestly. The batch-scope 1.82x
of EXP-022 is NOT the predicted effect here: the
batch epilogue it removed (caller buffer copies,
flag-byte writes, Python-side pair location) does not
exist in the same shape in search mode.

## Predeclared success criterion

All of the following, declared before any timing:

1. Correctness gates (below) all pass before
   benchmarking begins.
2. Performance, under the EXP-017 protocol: at least
   3 independent sessions, paired 65,536-hash blocks
   (or the search-path equivalent declared in the
   session manifest: paired counted search calls over
   identical ranges at a declared target), randomised
   AB/BA order, equal-pair controls returning nulls,
   and the adjusted 95 percent confidence interval of
   the paired log-ratio lying entirely above 0 in
   every session and pooled, for the primary
   comparison (mask search vs production search at
   the predeclared primary density, 2 threads).
3. Both reported, never substituted: pure batch
   throughput AND actual early-exit search
   throughput.
4. A fresh regtest block mined and accepted through
   the candidate path before any integration is
   proposed. Integration itself is a separate owner
   decision under the master plan's section 6 rules.

Failure of any element is a recorded result, not a
reason to add sessions: additional sessions require a
new formally declared experiment.

## Section 4.1 audit findings (from Assignment A)

Full trace in CURRENT_PRODUCTION_AUDIT.md section 4.
The load-bearing facts:

- Production entry: bal_v_search2 in
  mining/cpu/bal_avx512_mb.c (line 380), reached from
  gpu/engine.py search_first_counted (line 996) via
  search_first (line 988), called per span by
  mining/mainnet_live.py.
- Generation: block-1 midstate computed once scalar
  per call (v_template_init); per 16-lane group, the
  nonce enters as schedule word W3 via
  _mm512_shuffle_epi8; block-2 and outer compressions
  run transposed (v_compress16); inner state is
  staged through inn[8][16], outer final state
  through dg[8][16].
- Storage today: every valid lane's digest is
  written byte by byte into dig[16][32] on the worker
  stack, in search mode exactly as in batch mode.
  Dummy lanes of a partial group are computed, never
  stored, never counted as coverage.
- Comparison today: scalar v_meets per lane (byte 31
  down to 0). No vector comparison exists in the
  production search path. The vector comparison
  exists only in the research flags kernel
  (vf_group in avx512_mb_flags.c): lexicographic
  unsigned compare of bswap32(state[7-j]) against the
  target words in opmask registers, meets mask equal
  to (not greater) masked to valid lanes; extraction
  only for flagged lanes via ctz bit scanning.
- Extraction today: the single winning digest is
  copied through BalSearchCtx (mutex-published,
  first publisher wins, atomic stop flag; other
  workers stop at group boundaries). A started group
  always completes: early exit is group-atomic, and
  attempted counts every real nonce of completed
  groups; backend counts 16 per group including
  dummy lanes.
- Verification: engine verify_candidate (hashlib
  recompute plus target check) on every hit; a
  failure triggers a full hashlib rescan of the span
  (fail-closed, fallback event recorded). The miner
  then independently recomputes the digest again in
  mainnet_live.py before submission. A mask is never
  treated as proof anywhere in this chain, and the
  new design must keep it that way.
- Error propagation: kernel codes -1 (bad args),
  -2 (range crossing 2^32), -3 (publish failure),
  -4 (context init failure) become RuntimeError in
  Python for any rc outside (0, 1); pthread_create
  failure runs the span synchronously; the kernel
  search path has no allocation that can fail.
- The flags file exports NO search form:
  bal_v_batchf2 is batch-only. The production library
  exports only bal_v_batch2 and bal_v_search2, and
  gpu/engine.py has no flags binding. The mask search
  must be designed and built, not rewired.

## Designs to compare (directive section 4.3)

- A. Existing production search (baseline, above).
- B. Mask-based search: EXP-022's vector comparison
  inside the search walker; mask identifies
  qualifying lanes; no digest stored for
  non-qualifying lanes.
- C. Mask plus adaptive extraction: full digests
  materialised only for qualifying lanes, with the
  extraction strategy costed for zero, one and
  multiple candidates per group.
- D. Alternative mask representations: opmask
  carry-through vs flag-bit arrays vs scalar
  extraction order; bit scanning and candidate
  compaction costed explicitly.
- E. Termination strategies: stop at the first
  verified candidate within the group scan vs
  complete the group and examine all qualifying
  lanes; measured at declared target densities,
  including the effect of candidate density on the
  comparison itself.

Every design must handle: no qualifying candidates;
one; multiple; partial final groups; odd batch
sizes; nonce-range boundaries including the 2^32
edge; early termination; counter overflow (attempted
and backend are 64-bit; range validation is the
bal_search.h contract); invalid arguments;
allocation failures (any new allocation returns a
distinct error code, as bal_v_batchf2's -5 does);
CPU-feature fallback (the engine must never call the
mask form without the same probe discipline as
v512).

## Gates (all before timing)

1. Differential correctness vs hashlib: randomised
   headers, starts and counts at the programme's
   standard gate sizes (at least 108,000 nonces per
   design), zero mismatches in candidate sets and
   extracted digests.
2. Candidate-set equivalence vs production
   bal_v_search2 and vs a Python recount, at
   densities 0, about 2^-16, about 2^-8 and 1.
3. Target boundaries: equality meets; target minus
   one misses; target plus one behaves as recorded.
4. Nonce boundaries: start 0, start at 0xFFFFFFC0,
   ranges ending exactly at 2^32, unaligned starts,
   counts 1, 5, 15, 16, 17 and odd counts generally.
5. Exact accounting: attempted and backend predicted
   by the wave rule and asserted per call, including
   partial groups and early exits (genesis probe:
   winner 3 nonces into the range reports attempted
   16 under wave semantics).
6. Genesis: digest exact; search re-finds nonce
   2083236893.
7. Multiple candidates in one group: all qualifying
   lanes are reported or the first-winner semantics
   is proven identical to production's (first
   publisher wins is a concurrency outcome; the
   deterministic claim to gate is that the returned
   candidate is always a true qualifying candidate
   and never a non-qualifying one).
8. Sanitizers where available (ASan/UBSan builds of
   the research kernel) clean on the gate corpus.
9. Fresh regtest block through the candidate path
   (before any integration proposal).

## Benchmark plan

EXP-017 protocol as in the success criterion.
Comparisons: each surviving design vs production
search (primary), and surviving designs vs each
other (secondary). Report per-session and pooled
intervals, pairs won, arm medians, host record per
session (CPU model and flags; hosts vary across VM
replacements), node state, thread counts (1 and 2,
with 2 primary as the tuned reference), and both
batch and search throughputs. Raw session JSON
append-only under phase6b/benchmarks/exp024/ with
session-named files, preserved immediately.

## Decision and follow-up

To be filled by the experiment record. Possible
outcomes: VERIFIED IMPROVEMENT in the search path
(eligible to propose integration to the owner);
parity or negative (recorded, design retired or
returned to EXP-026's combined design space with the
measurements as its cost input). No integration is
performed by this experiment.

## Experiment record (2026-11-15)

Executed 2026-11-15, about 04:45 to 05:10 UTC, on the
audit host: AMD EPYC 9D25 126-Core Processor (guest
4 vCPUs, about 1.5 effective shared CPUs), flags
include sha_ni YES, avx512f/bw/dq/vl YES, avx512vbmi
YES, avx512_vbmi2 YES, avx512ifma YES, gfni YES. Both
benchmark libraries built with the restricted flag set
-O3 -mavx512f -mavx512bw (never -march=native). The
live mainnet miner and node were running throughout
(contention is part of the recorded environment, as in
EXP-017); nothing live was stopped, restarted or
altered. Production files are byte-identical to their
pre-experiment hashes (verified at close).

### Implementation

New research source:
research/sha256d/extreme_optimization/src/
avx512_mb_mask_search.c. It is the EXP-022 flags file
byte-identical above its EXP-024 banner, plus the new
search forms built on a new group function, vm_group,
which shares v_compress16, v_template_init and the
BalSearchCtx discipline with production and compares
through the vf_group opmask lexicographic compare.
Built as libbal_m512.so. Exports:

- bal_v_msearch2 (design B): per group, full SHA-256d;
  vector target compare in opmask registers; on a hit
  group every flagged lane's digest is extracted
  (flags style) and the lowest flagged lane is
  published through BalSearchCtx. Zero digest stores
  on a miss group.
- bal_v_msearcha2 (design C): identical walk; a hit
  group extracts ONLY the lowest flagged lane (ctz of
  the mask). Multiple set bits cost the same as one,
  because search-first semantics never need another
  lane of the group. This is the adaptive element:
  extraction work scales with the one lane the caller
  can use, not with the number of qualifying lanes.
- bal_v_msearchs2 (design D/E arm): span-complete
  mask collection. Workers never stop early; each
  group contributes one uint16 mask to a per-span
  array (the alternative mask representation: a
  compact mask array plus deferred extraction, instead
  of an opmask consumed group by group). After the
  join, the lowest qualifying nonce of the whole range
  is found by scanning the array, and its group is
  recomputed once through the production v_group to
  materialise the digest (the recompute is counted in
  backend). A set mask bit whose recomputed digest
  does not meet is never trusted; the scan continues.
- bal_v_mbatch2: batch form of the new group code
  (mode-2 extraction for every lane), present so the
  gates differentially test the new group's digests
  directly and pure batch throughput of the mask
  kernel can be reported separately from search.

Design D assessment beyond the scan arm: the other
candidate representations (opmask carry-through,
which B and C already are; flag-bit arrays, which are
the scan arm's storage and the EXP-022 batch form)
collapse into these two shapes in the search path:
consume the mask immediately per group, or store it
compactly and extract later. Bit scanning and
candidate compaction costs are the ctz loop measured
inside B (all flagged lanes) versus C (lowest lane
only); the hit-density C vs B comparison below prices
exactly that difference.

Design E (termination): the primary shape keeps
production semantics, stop at the first group
containing a hit (group-atomic). The scan arm is the
complete-the-span strategy, measured at the frequent
-hit density where the difference is largest: it does
the full 65,536 hashes of every block while the
early-exit arms stop after the first hit group, so
its per-block useful-work rate collapses by roughly
the hit position ratio. Completing a group and
examining all its qualifying lanes (versus stopping
at the lowest) is priced by B vs C at the same
density: B extracts every flagged lane of the hit
group, C only the lowest.

Search semantics match production exactly: same
bal_validate_range codes (-1 bad args, -2 range
crossing 2^32), same bal_partition spans, same
publish discipline (first publisher wins across
workers; within a worker, the lowest lane of the
first hit group of its span), same counted accounting
(attempted counts the real nonces of completed
groups, backend counts 16 per group including dummy
lanes). The scan arm is the documented exception:
attempted == count always; backend adds the single
recomputed group (16) on a hit. Return codes mirror
production (-3 publish failure, -4 context init
failure); the scan and batch forms add -5 for a
scratch allocation failure. B and C allocate nothing.
A mask is never treated as proof: the regtest harness
and the engine discipline recompute every candidate
with hashlib before use.

### Gates (all before timing; all PASS)

Driver: phase6b/benchmarks/exp024_gates.py; record:
benchmarks/exp024/gates_20261115T044747Z.json.

- G1 differential, new group code vs hashlib:
  149,932 nonces across 4 headers and thread counts
  1 and 2 at density 1, digests byte-identical to
  hashlib AND to the production batch, flags all set,
  accounting identical to production. PASS.
- G2 candidate-set equivalence: 40 randomised spans
  x 4 densities (0, about 2^-16, about 2^-8, 1). At
  1 thread, B, C, scan and production all return the
  recount minimum with the exact digest on every
  span; at 2 and 3 threads every arm returns a true
  recount member with an exact digest. PASS.
- G3 target boundaries: 24 sampled nonces x 4
  implementations: target == digest meets, digest
  minus 1 misses, digest plus 1 meets. PASS.
- G4 nonce boundaries: 14 spans including starts 0
  and 0xFFFFFFC0, ranges ending exactly at 2^32, the
  final nonce alone, counts 1, 5, 15, 16, 17, 31, 33:
  lowest nonce and exact digest on every arm, with
  exact early-exit accounting. PASS.
- G5 exact accounting at 1 thread: miss attempted ==
  count and backend == 16 * ceil(count / 16) over the
  count table {1, 5, 15, 16, 17, 31, 100, 1000,
  65537}; hit accounting predicted by the wave rule
  from independent recounts; genesis probe (winner 3
  nonces into a 100,000 span) reports attempted 16
  and backend 16 on B, C and production; scan arm
  attempted == count with backend == full backend
  plus 16 on hits. PASS. An independent spot check
  after the gate run re-verified 29 further recounted
  hit spans exactly for B, C and the scan arm.
- G6 genesis: all three arms re-find nonce
  2083236893 with the exact hashlib digest at
  2 threads. PASS.
- G7 invalid arguments: null header, target and
  outputs, zero count, 0 and 17 threads all return
  -1; ranges crossing 2^32 return -2; no crashes.
  PASS.
- G8 multiple candidates in one group: density-1
  single-group spans return the lowest qualifying
  lane on every arm. PASS.
- G9 sanitizers: exp024_san_driver.c built with the
  kernel under ASan/UBSan (-fno-sanitize-recover=all)
  ran the boundary, invalid-argument and 200
  randomised-span corpus per arm plus the batch form:
  SAN_DRIVER_OK, no sanitizer finding. PASS.

### Fresh regtest gate (PASS)

Driver: phase6b/benchmarks/exp024_regtest.py; record:
benchmarks/exp024/regtest_20261115T044829Z.json. The
harness binds the mask kernel into the production
block-building path through a research shim exposing
the counted-search interface: production
mining/engine.py MiningEngine obtains the template
from the lab regtest Core, builds the candidate
(coinbase, Merkle root, header), assembles and
submits the block; the nonce search itself runs in
the research kernel; the shim independently
recomputes every candidate with hashlib and checks
the target before returning it (fail-closed, as the
production engine does). The production
ComputeEngine is not the search backend in this
harness; that is the honest limit of binding a
research kernel without editing production code.

- Design C block: height 824, hash
  63794c057b32200815533cfe59126a057fa158f69750e0a020d42e82fd2caf14,
  nonce 0, accepted, best-block match.
- Design B block: height 825, hash
  48605bb7111942760c57601c2962097bd3cd4264d415d85f6dd8df4d5a1e9737,
  nonce 50000, accepted, best-block match.
Both winning digests were re-verified against the
blocks as read back from Core (getblock, cpu_digest
of the header equals the block hash).

### Machine-code evidence

Audit: phase6b/benchmarks/exp024_asm_audit.py;
record: benchmarks/exp024/asm_audit_20261115T045019Z.json
(objdump of libbal_m512.so and the production base
library).

- vm_group (mask group): 576 instructions; 15 counted
  opmask-writing vpcmp instructions (the unrolled
  8-word lexicographic compare, vpcmpltud and
  vpcmpnleud pairs writing %k registers); zero scalar
  byte compares. Exactly 8 zmm stack stores sit after
  the kortestw mask guard: the digest staging stores,
  reachable only behind a test of extract_mode and a
  kortestw of the meets mask, both branching to the
  exit region. On a miss group they never execute:
  zero digest stores on the miss path, as designed.
  The 43 zmm stores before the guard are the
  inner-state staging (present in both kernels; it
  feeds the outer compression) plus the compiler's
  spill of the final state, which the compare
  consumes from stack slots.
- Production v_walk (v_group inlined by the compiler
  in this build): 3,948 instructions; ZERO opmask
  compares in the entire production library; its
  target test is a scalar byte-compare loop
  (movzbl byte load plus cmp %<reg>l, memory, in a
  loop body executed per byte per lane), and its
  staging stores and per-lane extraction run
  unconditionally for every group.
- Whole-library census: 30 vpcmp instructions in
  libbal_m512.so (compare loops of vm_group and
  vf_group), 0 in the production base library.

### Benchmarks (EXP-017 protocol, measured)

27 sessions, 120 pairs plus 8 warmup pairs each,
65,536-hash blocks, randomised AB/BA, rate =
attempted / elapsed. Raw sessions:
benchmarks/exp024/session_*.json (append-only).
Analysis: the EXP-017 statistic imported unchanged
(exp017_analyze.analyse_group); the monolithic
analyser stalled under host CPU pressure, so results
come from exp024_analyze_incremental.py, one
comparison per invocation, identical statistic, the
remedy recorded for EXP-022. Per-comparison records:
benchmarks/exp024/analysis_inc_*.json. Absolute rates
tonight run above the EXP-017 era figures on both
arms (this host's contention profile varies; the
live miner and node were up throughout). Only the
paired ratios carry the verdict.

Primary comparison, design B vs production search,
density 0 (mainnet-like, target_int 0), 2 threads:

| session | prod median H/s | mask B median H/s | adjusted log-ratio [95% CI] | sig |
|---|---|---|---|---|
| 045026 | 8,584,804 | 10,777,459 | +0.088 [-0.122, +0.308] | no |
| 045034 | 9,415,537 | 11,154,518 | +0.147 [-0.075, +0.371] | no |
| 045043 | 6,665,788 | 8,132,740 | +0.233 [+0.022, +0.448] | yes |
| pooled | | | +0.156, ratio 1.169x [1.031, 1.327], pairs won 63.6% | yes (pooled only) |

Design C vs production search, density 0, 2 threads:

| session | prod median H/s | mask C median H/s | adjusted log-ratio [95% CI] | sig |
|---|---|---|---|---|
| 045052 | 6,673,839 | 8,413,145 | +0.296 [+0.110, +0.475] | yes |
| 045100 | 7,714,184 | 10,752,870 | +0.384 [+0.147, +0.619] | yes |
| 045109 | 9,460,079 | 12,883,100 | +0.325 [+0.119, +0.536] | yes |
| pooled | | | +0.348, ratio 1.416x [1.255, 1.603], pairs won 69.2% | yes |

Equal-pair control, mask B vs mask B, density 0,
2 threads: pooled log-ratio -0.084, ratio 0.920x
[0.817, 1.035], no session significant, pairs won
46.4%. The control returns a null, as the protocol
requires; its point estimate also bounds residual
same-code effects (process layout, scheduling) at
roughly 8% in this environment.

Design B vs production, density 0, 1 thread: pooled
+0.234, ratio 1.264x [1.115, 1.428], significant
pooled; sessions +0.162 [-0.043, +0.365] no, +0.203
[-0.020, +0.421] no, +0.336 [+0.119, +0.554] yes.
Same pattern as the primary: positive everywhere,
decisive only pooled.

Frequent-hit density (target_int 2^244, about 2^-12
of hashes qualify), 1 thread, search throughput:

| comparison | pooled ratio [95% CI] | sig | pairs won |
|---|---|---|---|
| B vs production | 1.073x [0.937, 1.241] | no | 61.1% |
| C vs production | 1.099x [0.956, 1.263] | no | 60.6% |
| C vs B | 1.035x [0.920, 1.155] | no | 50.6% |

At this density per-call times are short (median
first hit at 3,616 attempted of 65,536), fixed call
costs and contention bursts widen the intervals
(one session CI spans more than a log unit). The
adaptive extraction difference (C vs B) is not
measurable here, as expected: at 2^-12 a hit group
almost always carries exactly one qualifying lane,
so extracting all flagged lanes and extracting the
lowest lane are the same work. Median time to
candidate: production 1.01 ms, B 0.96 ms, C 0.94 ms.

Design E, complete-the-span (scan arm) vs production
early exit, same hit density: the scan's
attempted/elapsed rate reads 2.839x [2.411, 3.379]
in the scan's favour, and that figure is an artifact
of the rate definition, reported here precisely so
it is never quoted as a search improvement: the scan
performs all 65,536 hashes of every block (median
attempted 65,536 vs production 3,616), amortising
fixed call costs over 18x more hashes. The search
quantity, time to candidate, is decisive the other
way: median 9.72 ms for the scan vs 1.58 ms for
production early exit in the same sessions, 6.16x
slower, for a candidate that is the same lowest
nonce. Completing the span is an ESTABLISHED
NEGATIVE for search. (The scan shape remains the
correct one where a complete candidate map is the
product; that is the batch form, below.)

Pure batch throughput, reported separately and never
substituted for search: EXP-022 flags batch vs
production batch, density 0, 2 threads (rerun inside
this experiment's sessions): pooled ratio 1.649x
[1.466, 1.860], significant in every session
(+0.477, +0.399, +0.628), pairs won 74.4%. This
reproduces EXP-022's batch-scope verified result
(1.82x pooled there) under tonight's conditions.

### Verdict

Predeclared criterion (restated above): VERIFIED
IMPROVEMENT (search scope) requires the primary
comparison, design B vs production at density 0,
2 threads, to be significant in every session and
pooled. It is significant pooled (1.169x) and in one
of three sessions. The criterion is NOT met.
Failure of any element is a recorded result, not a
reason to add sessions, and no sessions were added.

Design C meets the same statistical bar on its own
comparison (significant in every session and pooled,
1.416x), and that is recorded as measured fact. It
does not upgrade the verdict, for two reasons stated
plainly. First, C was not the predeclared primary;
promoting it after seeing the data is exactly what
the predeclared rule exists to prevent. Second, at
density 0 the adaptive extraction never executes:
B and C run identical miss-path code (one vm_group,
the extract_mode value differs in a register the
miss path only tests), so C's larger margin cannot
be attributed to its design difference. The B/C
divergence at density 0 is itself evidence about
this environment: non-code effects (per-process
library layout, scheduling) move paired ratios by
amounts comparable to B's whole margin, which is
what B's wide session intervals are showing.

Classification: PROMISING HYPOTHESIS. Mask-based
early-exit search is faster than production search
on the miss path in every point estimate taken
(B pooled 1.169x at 2 threads, 1.264x at 1 thread;
C pooled 1.416x), the direction is consistent, the
control is null, the gates and the regtest blocks
pass, and the mechanism is visible in the machine
code (opmask compare, zero digest stores on the
miss path). It is not yet a VERIFIED IMPROVEMENT
under the owner's EXP-017 rule, and it is not
integrated. Production is unchanged.

Follow-ups, in order:
1. EXP-024b (confirmation, to be predeclared before
   timing): design C named primary; same protocol;
   plus one same-process arm interleaving B and C
   calls within a single session file to separate
   code effects from per-process layout effects. If
   C then meets the every-session rule, it earns
   VERIFIED IMPROVEMENT (search scope) and an
   integration recommendation for the owner's
   decision, through the section 11 gates.
2. A hit-density rerun with longer blocks or a
   lower-overhead harness if the owner wants the
   frequent-hit regime priced tightly; tonight's
   intervals there are contention dominated.
3. EXP-026 inherits both mask forms as candidates
   for its combined design (with EXP-018 residency
   and EXP-020 vocabulary results), and the
   layout-effect warning above: on this host class,
   single-binary paired comparisons of near-identical
   code paths carry an ~8% same-code bias floor.

Effect on PERFORMANCE_GAP_MODEL.md: none. The model
cites production, production is unchanged, and no
VERIFIED search improvement exists to add. The
PROMISING figures live here, labelled intermediate.
The mission targets stand at full height: 500 GH/s
minimum objective, 140 TH/s larger objective; this
experiment moves neither, and its best pooled search
figure (1.416x, PROMISING) would in any case be an
increment on a ~12 MH/s live system, not a step
change toward either target.

### Files

Created: research/sha256d/extreme_optimization/src/
avx512_mb_mask_search.c and libbal_m512.so;
research/sha256d/phase6b/benchmarks/exp024_gates.py,
exp024_san_driver.c, exp024_regtest.py,
exp024_asm_audit.py, exp024_paired_bench.py,
exp024_analyze.py (monolithic, stalled, superseded
for scheduling only), exp024_analyze_incremental.py;
session, gate, regtest, asm and analysis records
under research/sha256d/phase6b/benchmarks/exp024/
(27 session files, gates_20261115T044747Z.json,
regtest_20261115T044829Z.json,
asm_audit_20261115T045019Z.json, 9 analysis_inc
files). No production file was modified; no
historical record was edited.

## EXP-024b: confirmation run (predeclared 2026-11-15, before any timing)

Owner approval: given 2026-11-14, to run after EXP-025
and EXP-026, both now complete. EXP-024b is a lettered
confirmation run of EXP-024, not a new experiment
number; the next unreserved ID stays EXP-030. This
section was written and saved before any EXP-024b
gate or timing run. No integration is performed by
this run regardless of outcome; a pass earns an
integration RECOMMENDATION for a separate owner
decision.

Predeclared primary comparison: design C
(bal_v_msearcha2, adaptive lowest-lane extraction)
vs production search (bal_v_search2), density 0
(mainnet-like, target_int 0), 2 threads, EXP-017
protocol: at least 3 independent sessions, 120 pairs
per session, 65,536-hash paired blocks, randomised
AB/BA order, paired log-ratio with steal/load
covariate adjustment and bootstrap 95 percent CI
(EXP-017 statistic imported unchanged).

Predeclared success criterion: the adjusted CI lies
entirely above 0 in EVERY session and pooled.
Anything less is NOT VERIFIED and design C stays
PROMISING HYPOTHESIS. No sessions may be added after
seeing results.

Secondary arm (evidence about the layout-effect
question only, never a substitute for the primary
criterion): same-process B/C interleave. Within one
process and one session structure, B and C blocks
alternate in randomised AB/BA order (both symbols
loaded from the same libbal_m512.so into one
process), density 0, 2 threads, 3 sessions x 120
pairs. If the B/C gap from EXP-024 (C pooled 1.416x
vs B pooled 1.169x against production, measured in
separate processes) survives when layout and
scheduling environment are held common, the gap is
a code effect; if it collapses toward 1.0, the
EXP-024 divergence was substantially a per-process
layout or scheduling effect. Note the mechanism
prior: at density 0 the adaptive extraction never
executes, so B and C run identical miss-path code
apart from the extract_mode value; a large surviving
gap would itself be surprising and would be reported
as such.

Controls: C vs C equal-pair control (density 0,
2 threads, 3 sessions x 120 pairs) must be null
(no session significant, pooled CI containing 0).
Supporting evidence (not the criterion): the primary
comparison also run at 1 thread, 3 sessions x 120
pairs.

Gates before timing: the EXP-024 gates passed for
this exact kernel and library; a compact confirmation
is re-run (differentials vs hashlib on at least
50,000 nonces for design C through the batch form,
candidate-set equivalence for C at density 0 and
about 2^-12 against a hashlib recount and production,
genesis nonce 2083236893 re-found by C). If the
library needed rebuilding, the full EXP-024 gate set
would be re-run instead; it does not (libbal_m512.so
is the EXP-024 build, hash recorded in the gate
record).

Relation to EXP-026, stated before timing: EXP-026's
C2 DualMask already combines EXP-018 dual-batch
residency with this same opmask compare and is a
VERIFIED IMPROVEMENT (1.718x vs production, 1.444x
vs mask C, every session). EXP-024b therefore no
longer decides whether the mask compare helps; it
decides the narrower historical question EXP-024
left open: whether design C alone, the single-batch
mask form, meets the every-session rule on its own,
and whether the EXP-024 B/C divergence was code or
layout. A VERIFIED result here would add a certified
single-batch fallback form and a cleaner attribution
record; it would not displace DualMask as the
stronger candidate, and it would not by itself
recommend integrating C over DualMask.

### EXP-024b record (executed 2026-11-15)

Executed 2026-11-15, about 05:40 to 05:46 UTC, on
AMD EPYC 9D25 126-Core Processor (guest 4 vCPUs,
about 1.5 effective shared CPUs), flags sha_ni,
avx512f/bw/dq/vl, avx512vbmi, avx512_vbmi2,
avx512ifma, gfni all present (recorded per session
and in the gate record). Same library build as
EXP-024 (libbal_m512.so, sha256 in the gate record);
no rebuild was needed, so the compact gate set
applied. The live mainnet miner and node ran
throughout and were not stopped, restarted or
altered (autopilot pid 2394, miner pid 2397,
restarts 0, shares 195 at close). Production files
byte-identical to their pre-run hashes at close.

Compact gates (driver exp024b_gates.py; record
benchmarks/exp024b/gates_20261115T054030Z.json),
all PASS before timing:
- K1 differentials for design C: 131,072 nonces
  across 4 headers at 1 and 2 threads, byte-identical
  to hashlib and to the production batch.
- K2 candidate-set equivalence for C: 24 spans at
  densities 0 and about 2^-12, identical to the
  hashlib recount minimum and to production at
  1 thread.
- K3 genesis: C re-finds nonce 2083236893 with the
  exact hashlib digest at 2 threads.

Benchmarks (EXP-017 protocol, 12 sessions x 120
pairs, 65,536-hash blocks, randomised AB/BA; raw
files under benchmarks/exp024b/, analysis by
exp024b_analyze_incremental.py importing the
EXP-017 statistic unchanged):

Primary, design C vs production search, density 0,
2 threads (the predeclared criterion):

| session | prod median H/s | mask C median H/s | adjusted log-ratio [95% CI] | sig |
|---|---|---|---|---|
| 054035 | 7,714,372 | 11,002,259 | +0.387 [+0.162, +0.613] | yes |
| 054044 | 9,023,394 | 11,156,831 | +0.291 [+0.092, +0.504] | yes |
| 054100 | 8,246,294 | 10,644,960 | +0.323 [+0.127, +0.517] | yes |
| pooled | | | +0.335, ratio 1.398x [1.242, 1.578], pairs won 68.3% | yes |

The adjusted CI lies entirely above 0 in EVERY
session and pooled. The predeclared criterion is
MET. This also reproduces EXP-024's own C
comparison (1.416x there) under a predeclared
primary, which is what EXP-024 could not certify.

Control, C vs C, density 0, 2 threads: pooled
-0.045, ratio 0.956x [0.850, 1.080], no session
significant, pairs won 47.2%. Null, as required.

Secondary arm, same-process B/C interleave (arm A
is B, arm B is C; both symbols from the same
libbal_m512.so in one process), density 0,
2 threads: pooled +0.011, ratio 1.011x [0.895,
1.140], pairs won exactly 50.0%, no session
significant (sessions -0.078, -0.017, +0.145).
The B/C gap does NOT survive when layout and
scheduling environment are held common. Reading:
B and C are the same speed on the density-0 miss
path, exactly as the mechanism prior said (the
adaptive extraction never executes there, and the
two walkers differ only in a mode value the miss
path tests). The EXP-024 divergence between B
(1.169x) and C (1.416x) against production,
measured in separate processes, was therefore
substantially a per-process layout and scheduling
effect, not a code effect. What verifies here is
the mask search form itself, shared by B and C:
opmask compare, zero digest stores on a miss
group. Design C is certified as the named carrier
of that form because it was the predeclared
primary and because its extraction is never worse
than B's (at hit densities it extracts strictly
less; EXP-024 priced that difference as not
measurable at 2^-12, and nothing here changes
that).

Supporting evidence, C vs production at 1 thread:
pooled +0.381, ratio 1.463x [1.301, 1.648], pairs
won 75.3%, significant in every session. Not the
criterion; consistent with it.

### EXP-024b verdict

Classification: VERIFIED IMPROVEMENT (search
scope, density 0), for design C, the single-batch
mask search form, under the owner's EXP-017 rule:
compact gates passed before timing on top of the
full EXP-024 gate set for this exact kernel,
criterion met in every session and pooled,
control null, and the fresh regtest blocks of
EXP-024 (heights 824 and 825, through this kernel)
stand as the candidate-path evidence. No
integration is performed by this run.

Integration recommendation (for the owner's
separate decision, stated with the EXP-026
context the predeclared section promised): EXP-026
C2 DualMask is already a VERIFIED IMPROVEMENT and
is strictly stronger where both are measured
(1.718x vs production and 1.444x vs mask C at
2 threads, every session). A verified design C
therefore does NOT add a faster candidate and does
not displace DualMask as the leading integration
candidate. What it adds: (1) a certified
single-batch fallback form of the mask compare,
simpler than the dual-batch kernel, if the owner
wants the mask mechanism in production ahead of or
instead of the dual-batch change; (2) a closed
attribution record: the mask compare itself, not
adaptive extraction and not layout luck, carries
the single-batch gain (interleave 1.011x for C
over B in-process, both about 1.4x over production
across two independent experiment nights). If only
one mask form is ever integrated, the evidence
favours DualMask; design C's recommendation is as
the fallback and the attribution proof, and it is
recorded at that strength only.

Effect on PERFORMANCE_GAP_MODEL.md: none from this
run (production unchanged; Assignment G may cite
the verified 1.398x single-batch figure alongside
DualMask's 1.718x). The mission targets stand at
full height: 500 GH/s minimum objective, 140 TH/s
larger objective; a 1.4x search increment on a
system of this size is an intermediate result,
not a step change toward either target.

### EXP-024b files

Created: phase6b/benchmarks/exp024b_gates.py,
exp024b_paired_bench.py,
exp024b_analyze_incremental.py; records under
phase6b/benchmarks/exp024b/ (1 gates record, 12
session files, 4 analysis records). No production
file was modified; no historical record was edited
(this section and the predeclared section above
are appends).
