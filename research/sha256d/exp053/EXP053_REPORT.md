# EXP-053 report: prefix sharing inside the dual-batch walker

Portfolio NOVA-ER-0013, register Y-098, Phase 001 H-6.
Date: 2026-11-16. Host: AMD EPYC 9D25 126-Core
Processor (full AVX-512), 4 vCPUs at about 1.5
effective CPUs, the live mainnet pool miner and the
pruned mainnet node contending throughout (load
average roughly 3 to 18 across the day).

## Verdict

ESTABLISHED NEGATIVE at the predeclared resolution
(three-tier classification: ESTABLISHED NEGATIVE).

The pooled adjusted log-ratio of the prefix-sharing
variant against the production dual walker is
-0.0017 with 95 percent CI [-0.0059, +0.0027]. The
interval contains 0, its upper bound is below the
predeclared arithmetic ceiling of +0.0118 log units,
and its half-width of 0.0043 meets the predeclared
resolution target of at most 0.006. Under the
verdict mapping fixed in PREDECLARATION.md before
any measurement, any true gain from the share is
smaller than the resolution bound and cannot be the
"small significant gain" the portfolio hypothesised.
H-6 is closed for the dual walker: no resolvable
gain. The quantitative residue is the interval
itself: with 95 percent confidence, any true rate
gain is below +0.0027 log units (about +0.27
percent), and the point estimate is slightly
negative (about -0.17 percent). No integration is
proposed or made; production files were never
touched by this experiment. Gate 6 does not run:
the predeclaration runs it only on a VERIFIED
verdict.

## Question and hypothesis

Inside the production dual-batch walker
(bal_vd_search2, .local/cpu/libbal_v512dual.so), the
two batches of a dual group enter chunk 2 from the
same midstate broadcast and differ only in schedule
word W[3], the nonce word. Chunk-2 rounds 0 to 2
consume only W[0], W[1], W[2], so the state after
round 2 is identical for both batches (Stage 1
dependency graph: the identity is proven, not
assumed). The variant (bal_vp_search2) executes
those three rounds once and forks the state. A dual
group executes 256 round steps; the share removes
exactly 3, so the rate ceiling from round count
alone is 256/253, a log-ratio of +0.0118 (about
+1.19 percent), before second-order costs. The
portfolio hypothesis: inside the dual walker, where
the two batches already share setup, the shared
prefix removes duplicated work the standalone form
(EXP-013, ratios straddling 1.0, neither accepted
nor refuted) could not amortise, yielding a small
significant gain.

## Predeclaration

PREDECLARATION.md was written 2026-11-16T19:21Z,
before the Gate 4 campaign and before any timing of
the variant. Its sha256 is
039644d5e196102a5ca687e2ffc23fe806588ba6965ea3cae128cbb7068c0a06.
The bench driver asserts this hash at every session
start and records it in every session manifest; all
8 session manifests carry it, and the file on disk
still hashes to it. The predeclaration fixed the
hypothesis, the ceiling, the EXP-041 resolution
warning (a 3.4 percent ceiling EXP-041 could not
resolve on this VM; this ceiling is three times
smaller), the sizing inputs, the session design,
the statistic, and the verdict mapping used below.
No criterion was added, moved or reinterpreted
after the data existed.

## Variant

build_variant.py generates
src/avx512_dual_exp053_prefix.c from the production
source mining/cpu/bal_avx512_dual.c (sha256
fb3075d1cb5de70520866775a4a69ccb53952b46e1ab4c1924b1df74d0590da7)
and builds src/libbal_e53prefix.so (sha256
b96563e27d27984f159018a051123b3a6d6428c0ad861977996f4af0b08cf166)
with the production restricted flag set
(-mavx512f -mavx512bw, never -march=native). The
variant's arithmetic is the production arithmetic
with one duplicated three-round prefix removed.
Full build record: RAW_RESULTS/build_manifest.json.

## Gate 2 correctness (complete before the campaign)

RAW_RESULTS/gates.log: ALL PASSED, run before the
campaign as a precondition. The variant passed the
shared gate set: 108,000 randomized SHA-256d
differentials vs hashlib, genesis digest and
search (nonce 2083236893), boundaries and odd
counts, crossing and empty range rejection,
template variations, target exact equality and
minus one, the regtest-easy candidate set (82
candidates), and exact accounting (miss 5,000;
early-exit 50,016 of 50,016). The same gate set
passed on the production library as a harness
control. Cross-backend: bal_vp_batch2 vs
bal_vd_batch2 byte-identical over 4,194,304 digests;
search exact at threads 1 and in agreement at
threads 2 and 4 under the EXP-047 corrected
criterion (48 hits, every returned pair genuine).
The suite is tests/test_exp053_prefix.py
(make test-exp053); rerun after the campaign it
passed again with identical tallies (section
"Suites" below).

## Gate 4 campaign, as run

Design (predeclared): arms A = production
bal_vd_search2, B = variant bal_vp_search2, called
directly at the counted search entries (the
EXP-017 / EXP-020 / EXP-041 scope); target integer
1, never met, so every call walks its full block;
65,536-hash blocks; threads 2; genesis header; 16
warmup pairs per session; randomised AB or BA
order per pair; steal and runnable-load covariates
sampled around every counted call. Sessions: 6
effect (search_prefix_vs_dual) and 2 control
(control_dual_self, production in both arm slots),
30,000 pairs each, 240,000 pairs total, exactly
the predeclared budget cap. All 8 sessions ran
regardless of intermediate results, in the chain
order control, effect, effect, effect, control,
effect, effect, effect, from 19:27 UTC to about
20:51 UTC, ending with CAMPAIGN_ALL_SESSIONS_DONE
in RAW_RESULTS/campaign.log. Session files are
append-only; none was edited or resumed.

Independent verification of the raw data by the
completing agent (not the campaign author):

- All 8 session files hold exactly 30,000 pairs;
  per-session AB/BA splits fall between 14,933 and
  15,067, consistent with per-pair randomisation.
- Every arm of every pair (480,000 arm calls)
  records attempted == backend_attempted == 65,536
  and rc == 0. Zero violations.
- Every stored log_ratio_b_over_a (240,000 pairs)
  recomputes from the recorded arm rates to within
  1e-9. Zero mismatches.
- Unadjusted per-session mean log-ratios recomputed
  from the raw pairs match the analyzer's
  unadjusted means exactly, session by session.
- Every session manifest records the predeclaration
  sha256 above and the same production and variant
  binary hashes as the build manifest.

## Analysis

Statistic: the predeclared EXP-017 statistic,
computed by the EXP-017 analyzer code itself
(imported, unmodified) through exp053_analyze.py:
paired log-ratios, OLS adjustment on the
steal-difference, runnable-difference and order
covariates, 10,000-resample pairs bootstrap
stratified by session, per-session and pooled.
Analysis record:
RAW_RESULTS/analysis_20261116T223112Z.json.

Control (control_dual_self, 60,000 pairs):

- Session 20261116T192709Z: adjusted mean -0.0119,
  CI [-0.0223, -0.0011].
- Session 20261116T195835Z: adjusted mean +0.0060,
  CI [-0.0050, +0.0168].
- Pooled adjusted: mean -0.0030,
  CI [-0.0108, +0.0048]. Pooled unadjusted: -0.0030,
  CI [-0.0119, +0.0058]. Fraction of pairs won by
  arm B: 0.5006.

The pooled control CI contains 0, so under the
predeclared rule the machinery is not shown biased
and an effect verdict may be drawn. Recorded
honestly: the first control session's own CI
excludes 0 on the low side. The two control
sessions bracket 0 in opposite directions, which
is the signature of session-scale noise on this
VM (the same cross-session spread EXP-041
documented), not of a fixed arm bias, and the
predeclared validity test is the pooled interval.
The verdict below follows the predeclaration as
written.

Effect (search_prefix_vs_dual, 180,000 pairs),
adjusted per-session means and CIs:

- 20261116T194049Z: -0.0011, CI [-0.0121, +0.0097]
- 20261116T195223Z: -0.0036, CI [-0.0108, +0.0035]
- 20261116T195528Z: +0.0010, CI [-0.0062, +0.0083]
- 20261116T200947Z: +0.0008, CI [-0.0098, +0.0119]
- 20261116T202422Z: +0.0005, CI [-0.0106, +0.0117]
- 20261116T203925Z: -0.0076, CI [-0.0186, +0.0036]

No effect session is significant in either
direction. Pooled adjusted: mean -0.0017,
CI [-0.0059, +0.0027]; pooled unadjusted: mean
-0.0017, CI [-0.0066, +0.0033]. Fraction of pairs
won by the variant: 0.501. The covariate
adjustment narrowed the pooled CI by about 12
percent (width ratio 0.877) and moved the point
estimate by less than 0.0001; the verdict does not
rest on the adjustment.

## Verdict mapping, applied as predeclared

Control valid (above). Then, for the effect:

- Not VERIFIED IMPROVEMENT: the pooled CI is not
  entirely above 0, and no session's CI is.
- Not ESTABLISHED NEGATIVE (slowdown): the pooled
  CI is not entirely below 0.
- ESTABLISHED NEGATIVE at the predeclared
  resolution: the pooled CI contains 0, its upper
  bound (+0.0027) is below the +0.0118 arithmetic
  ceiling, and its half-width (0.0043) is at most
  the predeclared 0.006. This is the outcome.

The portfolio success criterion is met: an EXP-017
verdict, significant or not, that moves H-6 out of
UNDER_INVESTIGATION. H-6 is closed for the dual
walker as no resolvable gain. Together with
EXP-013, prefix sharing has now been measured in
both its forms on this host: the standalone form
straddles 1.0 unresolved at its resolution, and
the dual-walker form is bounded below +0.27
percent at this campaign's resolution.

## Suites run by the completing agent

Run one at a time, sequentially, after the
campaign, on the same AMD host:

- make test-exp053 (the Gate 2 suite): ALL PASSED,
  identical tallies to the pre-campaign gates.log
  (108,000 differentials per library, 4,194,304
  cross-backend digests with 0 bad, 48 search hits
  in agreement). Log:
  RAW_RESULTS/test_exp053_rerun.log.
- make test-avx512dual (production DualMask
  integration): ALL PASSED, including 197,616
  differentials through the production batch ABI
  and a fresh regtest block accepted through the
  production backend at height 2368 (hash
  68f163a4574faf046368a99898a03ce456c507ad24f915cbfdab74dee8ad965e).
  Log: RAW_RESULTS/test_avx512dual_rerun.log.

make test-all now carries 44 targets; the
test-exp053 target was added by the original
builder and is included in test-all. A full
test-all run was not repeated for this
research-only change; the two suites above cover
the experiment's own surface and the production
path it measured against.

## Execution incidents, recorded honestly

- The original builder agent died on a transport
  error mid-campaign (during session 2). The
  campaign shell chain survived as an orphaned
  process and completed all 8 sessions untouched;
  no session needed a rerun, and none was resumed
  or edited, per the predeclaration's rule for
  interrupted sessions (the interruption hit the
  agent, not a session).
- A VM replacement at about 21:20 UTC killed the
  first analysis run after about 19 minutes,
  before it wrote any output. The analysis was
  rerun detached and completed at 22:31 UTC after
  about 71 minutes of wall time. The campaign
  itself ran entirely before the replacement, on
  the AMD host recorded in every session manifest.
- One machinery note: exp053_analyze.py derives
  its bootstrap seed partly from Python's salted
  string hash, so the exact resample stream
  differs between invocations. The statistic, the
  10,000-resample count and the verdict mapping
  are the predeclared ones, and the verdict
  margins (upper bound 0.0027 against a 0.0118
  ceiling; half-width 0.0043 against a 0.006
  target) are far wider than bootstrap jitter at
  this resample count, so the classification is
  not seed-sensitive.

## Production impact

None. The experiment modified no production file;
the variant, harness and analysis live entirely
under research/sha256d/exp053/, with
tests/test_exp053_prefix.py and the Makefile
test-exp053 target as the only additions outside
it. The live miner and node ran throughout and
were never restarted by the experiment; their
contention is part of the measured environment
and is recorded per call in the session files.
There is nothing to roll back.

## UNVERIFIED register

- Other hosts: the Intel Xeon Platinum 8321HC
  rotation host would run the same AVX-512F/BW
  code, but no measurement exists there; nothing
  in this verdict is claimed for it.
- The batch entry's rate: bal_vp_batch2 was gated
  at Gate 2 for correctness only; no batch rate is
  claimed, per the predeclaration's scope.
- Thread counts other than 2: the campaign
  measured the production dispatch configuration
  used by EXP-017; other thread counts are
  unmeasured.
- Combinations: the prefix share combined with
  other kernel ingredients (EXP-022 flags, EXP-024
  designs) is untested; this verdict covers the
  share alone inside the production walker.
- GPU: none exists on this VM and none is
  claimed.
- Independent audit: this completion has not been
  independently audited. Per programme discipline
  an audit is owed before any push; nothing has
  been pushed.

## Files

- PREDECLARATION.md (preserved untouched)
- EXP053_REPORT.md (this file)
- build_variant.py, exp053_paired_bench.py,
  exp053_analyze.py
- src/avx512_dual_exp053_prefix.c,
  src/libbal_e53prefix.so
- RAW_RESULTS/build_manifest.json,
  RAW_RESULTS/sizing_probe.json,
  RAW_RESULTS/gates.log, RAW_RESULTS/campaign.log,
  RAW_RESULTS/analysis_run.log,
  RAW_RESULTS/analysis_20261116T223112Z.json,
  RAW_RESULTS/test_exp053_rerun.log,
  RAW_RESULTS/test_avx512dual_rerun.log,
  RAW_RESULTS/sessions/ (8 session files),
  RAW_RESULTS/shakedown/ (pre-campaign shakedown
  session, preserved)
- tests/test_exp053_prefix.py; Makefile
  (test-exp053 target, in test-all)
- Registry updates: research/sha256d/
  experiment_registry.md,
  research/sha256d/extreme_optimization/
  EXPERIMENT_REGISTRY.md,
  research/EXTREME_RESEARCH/
  EXPERIMENT_REGISTRY.json
