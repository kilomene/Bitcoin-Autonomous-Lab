# EXP-053 predeclaration (written before any campaign measurement)

Written: 2026-11-16T19:21Z, before the Gate 4 campaign
ran and before any timing of the variant was taken by
anyone. The campaign manifest records this file's sha256
at campaign start (the EXP-049 audit note N-1 lesson).
EXP-053 is portfolio NOVA-ER-0013, register Y-098,
Phase 001 H-6. Gate 2 correctness was completed before
this declaration (RAW_RESULTS/gates.log): correctness is
a precondition for campaigning, not a measurement of
the effect, and no variant rate has been observed at
the time of writing.

## Hypothesis

Inside the production dual-batch walker (bal_vd_search2,
libbal_v512dual.so), the two batches of a dual group
enter chunk 2 from the same midstate broadcast and
differ only in schedule word W[3], the nonce word.
Chunk-2 rounds 0 to 2 consume only W[0], W[1], W[2], so
the state after round 2 is identical for both batches
(Stage 1 dependency graph: state after rounds 0 to 2
carries no nonce dependence; the identity is proven).
The variant (bal_vp_search2) executes those three
rounds once and forks the state, instead of executing
them twice. The portfolio hypothesis: inside the dual
walker, where the two batches already share setup, the
shared prefix removes duplicated work the standalone
form (EXP-013, ratios straddling 1.0, neither accepted
nor refuted) could not amortise, yielding a small
significant gain.

## Arithmetic ceiling, stated in advance

A dual group executes 256 round steps (2 chunks x 2
batches x 64 rounds). The share removes exactly 3 of
them. The rate ceiling from round count alone is
therefore 256/253, a log-ratio of +0.0118 (about +1.19
percent), before second-order effects (register
pressure, the 8 state copies, staging and compare
costs that do not shrink). Any measured effect above
+0.0118 in log units is prima facie a measurement
artefact and will be investigated as one, not
celebrated.

## EXP-041 resolution warning, stated in advance

EXP-041 priced a 3.4 percent ceiling on this same VM
and could not resolve it: its controls exposed a
cross-library noise floor far above the effect. This
experiment's ceiling is three times smaller. The
sizing probe below is the reason the session design is
as large as it is, and the verdict mapping below
includes the resolution-limit outcome as a first-class
result, exactly as the portfolio's failure criterion
prescribes.

## Sizing inputs (production arm only, measured before this declaration)

RAW_RESULTS/sizing_probe.json: 300 self-paired
production dual-search calls at the EXP-017 block size
(65,536), threads 2, under load 12.8 to 17.7. Per-pair
log-ratio standard deviation 1.2197 (EXP-041 sessions
showed 1.10 to 1.37); mean pair wall 23.3 ms, median
10.9 ms. Derived: 158,752 pairs give a pooled
unadjusted half-width of 0.006; 89,298 pairs give a
per-session half-width of 0.008. The covariate
adjustment may narrow these; the design does not count
on it.

## Gate 4 design (fixed, no optional stopping)

- Arms: A = production bal_vd_search2 (the shipped
  binary .local/cpu/libbal_v512dual.so); B = variant
  bal_vp_search2 (research/sha256d/exp053/src/
  libbal_e53prefix.so). Scope: the counted search
  entries the production engine dispatches to, called
  directly (the EXP-017 / EXP-020 / EXP-041 scope).
  The batch entry carries the identical ingredient and
  is gated at Gate 2 only; no batch rate is claimed.
- Target: integer 1 (never met), so every call walks
  its full 65,536-nonce block; attempted == 65,536 is
  asserted on every timed call.
- Sessions: 6 effect sessions (comparison
  search_prefix_vs_dual) of 30,000 pairs each, and 2
  control sessions (comparison control_dual_self,
  production in both arm slots) of 30,000 pairs each.
  Total budget cap: 240,000 pairs. All 8 sessions run
  regardless of intermediate results; session files
  are append-only and a session interrupted by a VM
  replacement is rerun, never resumed or edited.
- Per pair: one 65,536-hash block per arm, randomised
  AB or BA order, steal and runnable-load covariates
  sampled around every counted call, 16 warmup pairs
  per session, threads 2, genesis header.
- Statistic: the predeclared EXP-017 statistic,
  computed by the EXP-017 analyzer code itself
  (imported, unmodified): paired log-ratios, OLS
  adjustment on the steal-difference,
  runnable-difference and order covariates,
  10,000-resample pairs bootstrap stratified by
  session, per-session and pooled.
- Expected resolution at design size (unadjusted
  arithmetic): per-session half-width about 0.0138,
  pooled about 0.0056. The per-session EXP-017
  criterion is therefore reachable only if the true
  effect sits at or near the arithmetic ceiling; this
  is stated now, not discovered later.

## Predeclared verdict mapping

Control validity first: if the pooled adjusted CI of
control_dual_self excludes 0, the machinery as run is
biased and no effect verdict is drawn from this
campaign; the outcome is recorded as a machinery /
resolution statement with the control evidence.

Given a valid control:

- VERIFIED IMPROVEMENT: the adjusted CI is entirely
  above 0 in every effect session and pooled (the
  EXP-017 rule). H-6 moves out of UNDER_INVESTIGATION
  as PROVEN at the measured size. Gate 6 then runs
  (fresh regtest block through the production path
  with a production-ABI gate library) and integration
  is recorded as proposed; production itself is
  integrated only as a separate gated step after the
  post-integration audit, per the portfolio rollback
  note.
- ESTABLISHED NEGATIVE (slowdown): the adjusted CI is
  entirely below 0 pooled and in every effect session.
  The variant is rejected; H-6 is closed for the dual
  walker.
- ESTABLISHED NEGATIVE at the predeclared resolution
  (null resolved): the pooled adjusted CI contains 0,
  its upper bound is below the +0.0118 arithmetic
  ceiling, and its half-width is at most 0.006. Any
  true gain is then smaller than the resolution bound
  and cannot be the "small significant gain" the
  portfolio hypothesised; H-6 is closed as no
  resolvable gain in the dual walker, with the CI
  upper bound recorded as the quantitative residue.
- PROMISING HYPOTHESIS: the pooled adjusted CI is
  entirely above 0 but at least one effect session's
  CI is not (the EXP-017 every-session rule unmet), or
  the pooled CI contains 0 with an upper bound at or
  above the ceiling while the half-width target was
  met. The effect is indicated but not verified;
  H-6 stays open on this evidence and the report says
  exactly what would resolve it.
- RESOLUTION LIMIT: the budget is exhausted with the
  pooled half-width above 0.006 and none of the above
  applies. Recorded as a resolution limit per the
  portfolio failure criterion; the item is retired as
  unresolvable on this VM rather than left open, and
  the achieved interval is the result.

## Scope statements declared in advance

- Gates 1, 3 and 5 do not apply (portfolio). Gate 2
  is complete (108,000 randomized differentials vs
  hashlib on the variant, the same set passed by the
  production library as control, byte-identical
  vp-vs-vd batch outputs over 4,194,304 digests,
  search agreement under the EXP-047 corrected
  criterion). Gate 6 runs only on a VERIFIED verdict.
- Exact SHA-256d only; the variant's arithmetic is
  the production arithmetic with one duplicated
  three-round prefix removed, verified bit-exact at
  Gate 2. No consensus property is touched; the
  kernel is a search accelerator over the same
  headers and targets.
- Production files are untouched by this experiment
  whatever the verdict. The live miner and node run
  throughout and are never restarted; their contention
  is part of the measured environment and is recorded
  per call.
- Host: AMD EPYC 9D25 (full AVX-512). No GPU exists
  and none is claimed. Results on other hosts are
  UNVERIFIED by this campaign.
