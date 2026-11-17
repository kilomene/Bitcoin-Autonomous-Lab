# EXP-054 predeclaration (written before any campaign measurement)

Written: 2026-11-17T01:59Z, before the Gate 4 campaign
ran and before any timing of any granularity point
other than the shipped production entry was taken by
anyone. The campaign manifest records this file's
sha256 at campaign start (the EXP-049 audit note N-1
lesson). EXP-054 is portfolio NOVA-ER-0014, register
Y-043. Gate 2 correctness was completed before this
declaration (RAW_RESULTS/gates.log): correctness is a
precondition for campaigning, not a measurement of
the effect, and no candidate rate has been observed
at the time of writing. The sizing probe below timed
only the shipped production entry against itself.

## Question and hypothesis

The production dual-batch walker (bal_vd_search2,
libbal_v512dual.so) compresses two independent
16-lane batches in one register-resident function.
Inside each eight-round unit of the dual compress,
the two batches' rounds alternate at round
granularity: A round t, B round t, A round t+1,
B round t+1 (the DUAL8 macro). Y-043: coarser
alternation (blocks of 2, 4, 8 rounds) trades latency
hiding against instruction-cache and register
locality, and the optimum is unknown. The research
build (research/sha256d/exp054/src/libbal_e54gran.so,
generated mechanically from the production source)
parameterises the alternation block size G: G = 1 is
the production order; G = 2, 4, 8 run blocks of 2, 4
or 8 rounds of one batch before switching. Only the
order of the two batches' round steps changes; the
batches are independent computations sharing no
state, so every point is exact by construction and
Gate 2 verified that empirically per point
(byte-identical batch outputs against the production
binary over 4,194,304 digests per point).

The portfolio hypothesis: the curve is flat near the
production point, by analogy with EXP-005's geometry
curve on the SHA-NI family (flat top between 2 and 4
streams); a peak elsewhere would be a surprise worth
having. No round work is added or removed at any
point, so there is no arithmetic ceiling of the
EXP-053 kind: any effect is a second-order
scheduling effect (latency hiding, spill and
instruction-cache behaviour), expected small in
either direction.

## Multiple-comparison correction, stated in advance

The campaign tests a family of three candidate
comparisons against the production point:
G = 2, G = 4 and G = 8, each against production
G = 1 (the shipped binary). All candidate verdicts
are drawn from Bonferroni-corrected intervals:
per-comparison two-sided alpha 0.05 / 3, i.e.
98.333 percent intervals, read from the same
EXP-017 bootstrap distribution at the percentiles
[0.8333, 99.1667] instead of [2.5, 97.5]. The
estimator (paired log-ratio, OLS covariate
adjustment, 10,000-resample stratified pairs
bootstrap) is unchanged; only the interval level
moves, as predeclared here. The control comparison
and the build-control comparison below are single
predeclared machinery checks outside the candidate
family and are read at the ordinary 95 percent
level.

## Sizing inputs (production arm only, measured before this declaration)

RAW_RESULTS/sizing_probe.json: 300 self-paired
production dual-search calls at the EXP-017 block
size (65,536), threads 2, under load 8.7 to 11.0.
Per-pair log-ratio standard deviation 1.3770
(EXP-053's probe on the same host measured 1.2197;
EXP-041 sessions showed 1.10 to 1.37). Mean pair
wall 26.6 ms, median 11.8 ms. Derived unadjusted
half-widths at SD 1.3770: per session of 30,000
pairs, 0.0156 at 95 percent and 0.0190 at the
Bonferroni level; pooled over 90,000 pairs, 0.0090
at 95 percent and 0.0110 at the Bonferroni level.
The covariate adjustment may narrow these; the
design does not count on it.

## Resolution target, stated in advance

A candidate point is resolved as flat when its
corrected pooled adjusted interval contains 0 with
half-width at most 0.012 (the unadjusted pooled
expectation above, 0.0110, plus a small margin so
the target does not depend on the adjustment
performing). The per-session corrected half-width
of about 0.019 means the every-session rule below
can declare a displacement only for a true effect
of roughly 2 percent or more; smaller real peaks
surface as PROMISING at best. This is stated now,
not discovered later.

## Gate 4 design (fixed, no optional stopping)

- Arms: A = production bal_vd_search2 (the shipped
  binary .local/cpu/libbal_v512dual.so); B = the
  named point's bal_vg{G}_search2 in the research
  library. Scope: the counted search entries called
  directly (the EXP-017 / EXP-020 / EXP-041 scope).
  The batch entries carry the identical compress
  parameterisation and are gated at Gate 2 only; no
  batch rate is claimed.
- Target: integer 1 (never met), so every call walks
  its full 65,536-nonce block; attempted == 65,536
  is asserted on every timed call.
- Comparisons and sessions, all of 30,000 pairs:
  control_dual_self (production in both arm slots),
  2 sessions; search_g1_vs_dual (the research G = 1
  build against the shipped binary; a build-control
  diagnostic, not a candidate), 2 sessions;
  search_g2_vs_dual, search_g4_vs_dual and
  search_g8_vs_dual, 3 sessions each. Total budget
  cap: 390,000 pairs (13 sessions). All 13 sessions
  run regardless of intermediate results, in the
  fixed chain order control, g2, g4, g8, g1, g2, g4,
  g8, control, g1, g2, g4, g8, so every comparison's
  sessions spread across the campaign window.
  Session files are append-only and a session
  interrupted by a VM replacement is rerun, never
  resumed or edited.
- Per pair: one 65,536-hash block per arm, randomised
  AB or BA order, steal and runnable-load covariates
  sampled around every counted call, 16 warmup pairs
  per session, threads 2, genesis header.
- Covariates: the steal covariate uses the EXP-017 /
  EXP-041 form, second steal sample minus first
  steal sample. The EXP-053 driver's transcription
  defect (audit D-1: second steal minus first TOTAL)
  is not inherited by this driver.
- Statistic: the predeclared EXP-017 statistic,
  computed by the EXP-017 analyzer's own functions
  (imported, unmodified): paired log-ratios, OLS
  adjustment on the steal-difference,
  runnable-difference and order covariates,
  10,000-resample pairs bootstrap stratified by
  session, per-session and pooled. The analyzer's
  bootstrap seeds are deterministic functions of the
  comparison name (sha256-derived integers), so the
  analysis is bit-reproducible across invocations;
  the EXP-053 salted-hash seed wart is not inherited.

## Predeclared verdict mapping

Control validity first: if the pooled adjusted 95
percent CI of control_dual_self excludes 0, the
machinery as run is biased and no candidate verdict
is drawn from this campaign; the outcome is recorded
as a machinery / resolution statement with the
control evidence.

Build-control reading: if the pooled adjusted 95
percent CI of search_g1_vs_dual excludes 0, the
research build itself measures differently from the
shipped binary at that size (a build or code-layout
effect, since G = 1 is the production algorithm).
Candidate verdicts are still drawn by the mapping
below, but the report must print the build-control
point estimate beside every candidate estimate and
state that candidate effects at or below that size
cannot be attributed to granularity alone.

Per candidate point G in {2, 4, 8}, from its
Bonferroni-corrected (98.333 percent) adjusted CIs:

- DISPLACING (VERIFIED IMPROVEMENT for G): the
  corrected CI is entirely above 0 in every session
  and pooled.
- SLOWDOWN (ESTABLISHED NEGATIVE for G): the
  corrected CI is entirely below 0 pooled and in
  every session.
- FLAT: the corrected pooled CI contains 0 and its
  half-width is at most 0.012.
- PROMISING: the corrected pooled CI is entirely
  above 0 but the every-session rule is unmet.
- RESOLUTION LIMIT for G: none of the above (in
  particular, pooled half-width above 0.012 with no
  resolved branch).

Overall verdict at the production point, in this
precedence order:

- DISPLACED: at least one candidate is DISPLACING.
  The displacing point with the largest pooled
  adjusted point estimate is the measured peak; the
  classification is VERIFIED IMPROVEMENT for that
  point over the production point. Integration of a
  new granularity is a separate gated step, not
  part of this experiment; Gates 1, 3, 5 and 6 do
  not apply (portfolio).
- PROMISING HYPOTHESIS: no candidate displaces and
  at least one is PROMISING. The report states
  exactly what would resolve it.
- CONFIRMED (flat curve): every candidate is FLAT
  or SLOWDOWN. The Y-043 displacement hypothesis is
  then an ESTABLISHED NEGATIVE at the predeclared
  resolution: any true gain of a FLAT candidate is
  bounded by its corrected interval's upper bound,
  and SLOWDOWN candidates are excluded outright.
  The production point stands, now with a measured
  curve behind it (the portfolio success criterion:
  a verdict at the production point, confirmed or
  displaced, or a flat curve recorded).
- RESOLUTION LIMIT: the budget is exhausted with
  at least one candidate at RESOLUTION LIMIT and
  none DISPLACING or PROMISING. Recorded as a
  resolution limit per the portfolio failure
  criterion; the item is retired as unresolvable on
  this VM rather than left open, and the achieved
  intervals are the result.

## Scope statements declared in advance

- Gates 1, 3, 5 and 6 do not apply (portfolio).
  Gate 2 is complete (per point: 108,000 randomized
  differentials vs hashlib, byte-identical batch
  outputs vs the production binary over 4,194,304
  digests, search agreement under the EXP-047
  corrected criterion; the same gate set passed on
  the production library as control).
- Exact SHA-256d only; every point's arithmetic is
  the production arithmetic with the two batches'
  round steps reordered, verified bit-exact at
  Gate 2. No consensus property is touched; the
  kernel is a search accelerator over the same
  headers and targets.
- Production files are untouched by this experiment
  whatever the verdict. The live miner and node run
  throughout and are never restarted; their
  contention is part of the measured environment and
  is recorded per call.
- Host: AMD EPYC 9D25 (full AVX-512). No GPU exists
  and none is claimed. Results on other hosts are
  UNVERIFIED by this campaign.
