# EXP-044: -mtune scheduling variants of the v512 kernel (NOVA-ER-0005)

Experiment: EXP-044 (portfolio identity NOVA-ER-0005).
Date: 2026-11-16. Host: AMD EPYC 9D25 126-Core Processor
(guest, hostname htch-runtime; 4 vCPUs visible, about 2
effective CPUs per EXP-031). Standing condition of every
measurement: the live miner (v512dual backend,
autopilot-supervised, pid 7872 throughout the campaign,
restarts 0, shares accepted 480 at campaign start and
480 at the end), the pruned mainnet node in initial
block download, and other agents' work were running
throughout and were never paused, restarted or
reconfigured. Load average (1 minute) at session starts
rose from 4.89 to 17.79 across the nine batch sessions,
one of the heaviest mixes under which this kernel has
been timed in this programme; sessions were rotated
across comparisons by round so the rise is shared by
all three comparisons rather than concentrated in one.
Research only: no production file was modified (the
gates record and every session manifest pin the
production library and source hashes; first and last
records agree byte for byte, and the production
library, kernel source and build.py hashes were
re-verified unchanged after the campaign).

## The question

EXP-041 closed the 29 vs 28 operation question as an
ESTABLISHED NULL and recorded one untested side
finding: building the v512 kernel with -mtune=znver3
leaves the ALU census at 29 per round but cuts the
standalone compress body's vector moves from 64 to 33
and its instructions from 135 to 113. Whether that
scheduling change survives in the full production
kernel or moves any rate was left UNVERIFIED, as a
scheduling hypothesis needing its own experiment.
EXP-044 is that experiment. It re-verifies the move
claim on the full production kernel build, extends it
to -mtune=znver4 (gcc 13.3 accepts both tunings), and
times both variants against the production library
under the EXP-017 protocol.

## Verdicts (three-tier language)

- znver3, batch scope (category D), 2 threads: NOT
  SIGNIFICANT. Pooled 1.075x [0.941, 1.223]; every
  session's adjusted CI straddles 0. The pooled point
  estimate (+0.0723 log) is smaller than this
  campaign's own control phantom (+0.1216 log in arm
  B's favour, section 4): net of the phantom the
  point estimate is negative (0.952x). There is no
  measurable znver3 effect at this campaign's
  resolution.
- znver4, batch scope, 2 threads: NOT SIGNIFICANT.
  Pooled 0.966x [0.848, 1.099]; sessions disagree in
  sign (0.917x, 0.979x, 1.024x) and every CI straddles
  0. Net of the phantom the point estimate is
  0.855x, descriptive only.
- Search scope (category E): NOT RUN, by the rule
  predeclared in section 1. Neither variant's batch
  pooled point estimate is positive and at or above
  the campaign noise floor (znver3 +0.0723 against a
  floor of 0.1216; znver4 -0.0347). The reason is
  recorded in section 5.

Bottom line: the -mtune scheduling change is real in
the emitted code (section 2: the move and instruction
reductions reproduce exactly on the full production
kernel, for both tunings) and null at the rate level
within this campaign's resolution. This is the same
shape as EXP-041's verdict on the op-count gap, and
it corroborates EXP-041's mechanism conclusion from
an independent direction: within this kernel family,
emitted move count is not the binding term; latency
structure and the guest's delivered CPU capacity are.
Neither variant is a Stage 6 integration candidate
and no integration is recommended. Production build
flags are unchanged.

## 1. Design (stated before the runs)

Arms, all called directly through ctypes with the
counted batch and search ABIs:

- base: bal_v_batch2 / bal_v_search2 in
  .local/cpu/libbal_v512.so (sha256 6dfd8d42...),
  today's production library, built by
  mining/cpu/build.py from mining/cpu/bal_avx512_mb.c
  with the restricted flags -mavx512f -mavx512bw.
  Arm A (reference) in every comparison.
- znver3: the identical kernel source rebuilt
  research-side with -mtune=znver3 added to the
  kernel translation unit only, every other flag
  identical to production (sha256 fa657724...).
  Arm B (candidate).
- znver4: the same with -mtune=znver4 (sha256
  2efe00d9...). Arm B (candidate).

Build fidelity control: a third research build with
no extra flag (the replica) came out byte-identical
to the production library (same sha256 6dfd8d42...),
so this host's gcc and the recorded production
command lines reproduce production exactly, and the
only difference between the timed arms is the -mtune
flag's effect on the kernel object. -mtune changes
scheduling only, never the ISA; -march=native was
never used. gcc 13.3.0 accepts both znver3 and
znver4, so both variants were built and run.

Comparisons (batch scope is category D: the counted
batch entry at the difficulty-1 target, the EXP-045
batch-bench convention; the batch form has no early
exit, so attempted == 65,536 on every call, asserted
by the driver):

  znver3_vs_base_batch_t2        primary, 2 threads
  znver4_vs_base_batch_t2        primary, 2 threads
  control_base_vs_base_batch_t2  control (the same
                                 production entry point
                                 in both arms)

Protocol: EXP-017 exactly. Paired 65,536-hash blocks,
randomised AB or BA order per pair, steal and
runnable-load covariates sampled around every counted
call, 120 pairs per session, 3 sessions per
comparison, sessions strictly one at a time and
rotated across comparisons by round. Verdicts come
only from the imported exp017 statistic (paired
log-ratio, OLS covariate adjustment, 10,000-resample
pairs bootstrap): VERIFIED IMPROVEMENT requires the
adjusted CI entirely above 0 in every session and
pooled; ESTABLISHED NEGATIVE requires it entirely
below 0 in every session and pooled; anything else is
NOT SIGNIFICANT. The control carries no verdict; its
pooled adjusted mean defines the campaign noise
floor.

Search-scope rule (predeclared): search sessions
(density 0, 2 threads, with their own control) run
for a variant iff its batch pooled adjusted mean log
ratio is positive and at or above the noise floor,
that is, at least the absolute pooled adjusted mean
of the batch control. Otherwise search is skipped
and the reason recorded.

Correctness gates run before any timing (section 3);
any variant failing them would have been stopped as
a correctness failure. None did.

## 2. Census: the EXP-041 move claim re-verified on the full kernel

Method: EXP-041's census method (function bodies
located via the symbol table, disassembled with
objdump, instructions counted; moves are the
EXP-041 set vmovdqa64, vmovdqa32, vmovdqu64,
vmovdqu32). The kernel compiles v_compress16 as a
loop over t = 0..63 whose body is one round, so the
body count is the per-round emitted cost.

v_compress16 alone:

| build | total insns | vector insns | moves | ALU per round |
|---|---|---|---|---|
| production | 135 | 95 | 64 | 29 |
| replica | 135 | 95 | 64 | 29 |
| znver3 | 113 | 64 | 33 | 29 |
| znver4 | 113 | 64 | 33 | 29 |

Full hot path (v_compress16 + v_walk, the whole
kernel body that executes per batch wave):

| build | total insns | moves |
|---|---|---|
| production | 4,987 | 163 |
| replica | 4,987 | 163 |
| znver3 | 4,827 | 132 |
| znver4 | 4,695 | 132 |

Findings:

- EXP-041's standalone-body numbers reproduce
  exactly on the full production kernel build: 135
  instructions and 64 moves for production, 113 and
  33 under -mtune=znver3, ALU census 29 in every
  build. The claim is re-verified, not merely
  carried forward.
- znver4's compress body is identical in census to
  znver3's (113 / 33 / 29); the two tunings differ
  only inside v_walk scheduling (4,695 vs 4,827
  total hot-path instructions, same 132 moves).
- On the full hot path the move reduction is 163 to
  132 (19 percent fewer moves) and the instruction
  reduction is 3 to 6 percent, much smaller in
  proportion than in the compress body alone,
  because v_walk's addressing, schedule expansion
  and digest stores do not shrink.

Full census data: RAW_RESULTS/census.json; build
commands and hashes: RAW_RESULTS/build_manifest.json.

## 3. Correctness gates (before timing)

exp044_gates.py, the EXP-046 gate set unchanged,
gate truth is hashlib alone. All gates PASS for all
three libraries:

- G1 differentials: 786,432 batch digests
  byte-identical to hashlib across the three
  libraries (262,144 per library: genesis at starts
  0 and 65,536 at 2 threads, a random header at the
  unaligned start 12,345, genesis on the span ending
  exactly at 2^32 at 1 thread).
- G2 candidate-set equivalence at 1 thread against a
  hashlib recount at densities 0, about 2^-16,
  about 2^-8 and 1, on 36 spans including starts 0
  and 1, unaligned starts, the single last nonce
  2^32-1, and spans ending exactly at 2^32 (20 spans
  with a recount hit): returned nonce and digest
  identical on every span, for every library.
- G3 multi-thread: density-0 accounting exact at 2
  threads on plain and boundary spans; the genesis
  nonce re-found at 2 threads by all three with the
  exact digest; density-1 hits at 2 threads carry
  exact digests.
- G4 boundary refusals: spans crossing or starting
  at 2^32 refused with rc -2 and zero accounting by
  all three kernels.

Record: RAW_RESULTS/gates_20261116T075744Z.json.

## 4. Results (batch scope, category D, 2 threads)

Nine sessions, 1,080 pairs, 141,557,760 timed
hashes, zero discards. Adjusted log ratios (positive
favours arm B); ratios are exp of the log values.
Analysis: RAW_RESULTS/analysis_20261116T080524Z.json.

znver3 vs base:

| session | A median (base) | B median (znver3) | adjusted | ratio |
|---|---|---|---|---|
| 075820Z | 4,636,307 H/s | 5,188,905 H/s | +0.0319 [-0.228, +0.279] | 1.032x [0.796, 1.322] |
| 075937Z | 3,253,601 H/s | 3,970,133 H/s | +0.1344 [-0.081, +0.351] | 1.144x [0.922, 1.421] |
| 080043Z | 3,427,663 H/s | 3,368,113 H/s | +0.0422 [-0.162, +0.261] | 1.043x [0.851, 1.299] |
| pooled | | | +0.0723 [-0.061, +0.202] | 1.075x [0.941, 1.223] |

Verdict: NOT SIGNIFICANT.

znver4 vs base:

| session | A median (base) | B median (znver4) | adjusted | ratio |
|---|---|---|---|---|
| 075847Z | 4,911,288 H/s | 4,455,201 H/s | -0.0863 [-0.306, +0.133] | 0.917x [0.737, 1.142] |
| 075957Z | 4,632,320 H/s | 4,090,388 H/s | -0.0217 [-0.247, +0.210] | 0.979x [0.781, 1.233] |
| 080108Z | 3,004,739 H/s | 3,091,805 H/s | +0.0242 [-0.192, +0.260] | 1.024x [0.825, 1.297] |
| pooled | | | -0.0347 [-0.165, +0.095] | 0.966x [0.848, 1.099] |

Verdict: NOT SIGNIFICANT.

Control (base vs base, same entry point both arms):

| session | adjusted |
|---|---|
| 075912Z | +0.1444 [-0.090, +0.381] |
| 080020Z | +0.1283 [-0.104, +0.373] |
| 080135Z | +0.0948 [-0.132, +0.300] |
| pooled | +0.1216 [-0.006, +0.251] (1.129x) |

Control analysis. The same-arm control measured a
pooled phantom of +0.1216 log (1.129x) favouring arm
B, consistent in sign across all three sessions
(+0.144, +0.128, +0.095). This is the same phenomenon
EXP-046 recorded (its search control phantom was
+0.170 under rising load): under this guest's
contention, the arm called second in a pair, or the
position the randomised order assigns to B,
systematically times faster than the covariate
adjustment removes. Two consequences, stated at full
strength:

- The phantom is larger than znver3's entire pooled
  point estimate (+0.0723) and of the same sign, so
  znver3's apparent lead is fully explained by the
  campaign's own null behaviour. Net of the phantom,
  znver3's point estimate is -0.0493 (0.952x) and
  znver4's is -0.1563 (0.855x). The netting is
  descriptive only (the phantom is a pooled
  same-arm mean, not a per-pair correction) and
  changes no formal tier; it is reported so the
  positive znver3 point estimate is not read as
  evidence of a real effect.
- No formal tier was changed by the control: both
  variants are NOT SIGNIFICANT on the predeclared
  rule alone, phantom or no phantom.

Condition dependence (the EXP-045 caveat): the base
arm's session medians span 3.00M to 4.91M H/s across
the nine sessions, a 1.6x spread driven by when each
session ran (load1 at starts 4.89 to 17.79), while
the paired ratios stay comparatively tight. Absolute
rates from this campaign are condition samples, not
kernel constants, exactly as EXP-045 established for
the AVX2 tier.

## 5. Search scope: not run, per the predeclared rule

The rule (section 1): search sessions run for a
variant iff its batch pooled adjusted mean log
ratio is positive and at or above the noise floor
(the batch control's absolute pooled adjusted mean,
0.1216). znver3 pooled +0.0723: positive but below
the floor. znver4 pooled -0.0347: not positive.
Neither variant triggers the search scope, so no
search sessions were run and the search control was
not run either. The skipped scope is a consequence
of the predeclared rule, not a gap in the campaign:
a scheduling change whose batch point estimate
cannot be separated from the same-arm phantom has
no measured effect for the search path (whose hot
loop is the same v_walk body) to inherit, and
EXP-041's tmaj search arm already returned a null
for a strictly larger code change on the same path.

## 6. Limitations

- Single host (AMD EPYC 9D25). Nothing here is
  measured on the Intel Xeon 8321HC rotation host or
  on bare metal; -mtune effects are microarchitecture
  scheduling effects and could differ elsewhere. The
  production host is a Zen-family part, so znver
  tunings were tested on their target family, which
  is the favourable case for the hypothesis.
- The null is a resolution statement, not a proof
  that the true effect is exactly zero: this
  campaign's noise floor (control phantom 0.1216
  log, about 13 percent) is large, and an effect
  below it cannot be resolved here either way. What
  is established is that neither tuning produces an
  effect at or above the floor on the batch path,
  and znver3's point estimate does not survive
  comparison with the campaign's own control.
- Batch scope is category D (the counted batch
  entry called directly), not the Python
  ComputeEngine wrapper and not an end-to-end
  (category F) rate. Search scope was not run
  (section 5).
- The mechanism reading (move count is not the
  binding term) is static-schedule reasoning plus
  the rate nulls; no hardware counter evidence
  exists on this VM (perf counters are
  EPERM-blocked, EXP-031).

## 7. Files

- build_variants.py: variant builder replicating
  production's build_v512 commands; RAW_RESULTS/
  build_manifest.json records exact commands and
  source and binary hashes.
- exp044_census.py: disassembly census;
  RAW_RESULTS/census.json.
- exp044_gates.py: correctness gates;
  RAW_RESULTS/gates_20261116T075744Z.json.
- exp044_paired_bench.py: EXP-017 paired driver
  (batch and search scopes); nine batch session
  JSONs under RAW_RESULTS/sessions/ with full
  manifests, load and heartbeat snapshots.
- exp044_analyze.py: the imported EXP-017 statistic
  and verdict rule; RAW_RESULTS/
  analysis_20261116T080524Z.json.
- src/: the three research libraries (replica,
  znver3, znver4).
