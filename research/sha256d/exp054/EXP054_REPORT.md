# EXP-054 report: dual-batch interleave granularity sweep

Date: 2026-11-17. Experiment: EXP-054, portfolio
NOVA-ER-0014, register Y-043. Predeclaration:
PREDECLARATION.md in this directory, sha256
2aebc8ede2ed62b56a800976898be4b86d9570ccaea5776b6171aaab4a111e46,
written and hash-pinned in the bench driver before
any campaign measurement. Raw record: RAW_RESULTS/
(13 session files, campaign.log, gates.log,
build_manifest.json, sizing_probe.json,
analysis_20261117T065523Z.json, analysis_run.log).

## Verdict: CONFIRMED (flat curve at the production point)

Overall classification, by the predeclaration's
verdict mapping applied in its precedence order:
**CONFIRMED**. No candidate displaces the production
point and none is PROMISING; every candidate is FLAT
or SLOWDOWN at the predeclared resolution. The
Y-043 displacement hypothesis is therefore an
**ESTABLISHED NEGATIVE** at the predeclared
resolution: the production interleave granularity
(G = 1, round-by-round alternation of the two
batches inside the dual compress) stands, now with
a measured curve behind it. The portfolio success
criterion (a measured curve with a verdict at the
production point, confirmed or displaced) is met.
No integration is proposed or needed; production
files were never touched. Gates 1, 3, 5 and 6 do
not apply (portfolio).

Per-point classifications, from the Bonferroni
corrected (98.333 percent, per-comparison alpha
0.05 / 3) adjusted intervals, exactly as
predeclared:

- G = 2: FLAT. Pooled adjusted log-ratio +0.0016
  (about +0.16 percent), corrected CI
  [-0.0088, +0.0121], half-width 0.0105, at most
  the predeclared 0.012 resolution target. Any
  true gain of G = 2 over the production point is
  bounded by the corrected upper bound, about
  +1.22 percent.
- G = 4: SLOWDOWN (ESTABLISHED NEGATIVE for this
  point). Pooled adjusted -0.0521 (about
  -5.1 percent), corrected CI [-0.0617, -0.0425],
  entirely below 0 pooled and in every session.
  Attribution caveat under the build-control
  reading below.
- G = 8: SLOWDOWN (ESTABLISHED NEGATIVE for this
  point). Pooled adjusted -0.1505 (about
  -14.0 percent), corrected CI [-0.1600, -0.1408],
  entirely below 0 pooled and in every session,
  and larger in magnitude than the build-control
  offset, so a granularity penalty at G = 8 is
  supported beyond the build effect.

## Machinery validity (checked first, as predeclared)

Control comparison (production binary in both arm
slots, 2 sessions, 60,000 pairs): pooled adjusted
-0.0038, 95 percent CI [-0.0146, +0.0070], contains
0; the machinery as run is not biased and candidate
verdicts may be drawn. Both control sessions
individually contain 0 (adjusted -0.0068 and
-0.0008); fraction of pairs won by arm B 0.4976.

Build control (research G = 1 build against the
shipped binary, 2 sessions, 60,000 pairs): pooled
adjusted -0.0658, 95 percent CI [-0.0763, -0.0550],
which EXCLUDES 0. The research build itself
measures about 6.4 percent slower than the shipped
binary at G = 1, where the algorithm is identical:
a build or code-layout effect, exactly the case
the predeclaration's build-control paragraph
covers. As predeclared, the build-control point
estimate (-0.0658) is printed beside every
candidate estimate in the curve table below, and
candidate effects at or below that size cannot be
attributed to granularity alone. Concretely: the
G = 4 slowdown against production (-0.0521) is
smaller than the build offset, so it cannot be
attributed to granularity alone; the G = 8
slowdown (-0.1505) exceeds the build offset by a
wide margin. For orientation only (differences of
pooled log point estimates, no intervals, no
verdict weight): net of the build-control offset,
G = 2 sits at about +0.067, G = 4 at about +0.014
and G = 8 at about -0.085 relative to the research
build's own G = 1 baseline. The verdict mapping
does not use these netted figures; every
classification above is against the shipped
production binary, as predeclared.

## The measured curve

Pooled adjusted log-ratios against the shipped
production binary (arm A), Bonferroni corrected
98.333 percent intervals for the three candidates,
95 percent for the two controls. Median rates are
the production arm's per-session medians, shown to
make the environment visible; they are not the
statistic.

| point | sessions | pooled adj | corrected CI | class |
|---|---|---|---|---|
| control (prod vs prod) | 2 | -0.0038 | [-0.0146, +0.0070] (95%) | valid |
| G = 1 (build control) | 2 | -0.0658 | [-0.0763, -0.0550] (95%) | build offset |
| G = 2 | 3 | +0.0016 | [-0.0088, +0.0121] | FLAT |
| G = 4 | 3 | -0.0521 | [-0.0617, -0.0425] | SLOWDOWN |
| G = 8 | 3 | -0.1505 | [-0.1600, -0.1408] | SLOWDOWN |

Per-session adjusted means (verdict-level
intervals in the analysis JSON):

- Control: -0.0068, -0.0008.
- G = 1 build control: -0.0623, -0.0692.
- G = 2: +0.0014, +0.0015, +0.0019 (all three
  sessions on the 9D25 host; fraction of pairs won
  by the candidate 0.5048 pooled).
- G = 4: -0.0632, -0.0723 (9D25), -0.0209 (9D64;
  see the host note below).
- G = 8: -0.2092, -0.1882 (9D25), -0.0539 (9D64).

The unadjusted pooled means agree with the
adjusted ones to within 0.0001 on every comparison
(control -0.0039, G = 1 -0.0658, G = 2 +0.0016,
G = 4 -0.0521, G = 8 -0.1504), and the unadjusted
statistic, which uses no covariates, lands in the
same verdict branch for every point. The covariate
adjustment moved no pooled estimate by more than
0.00003 and changed no interval's verdict side.

Shape of the curve, stated plainly: against the
shipped binary, the curve is flat at G = 2 within
about a percent and falls off a cliff by G = 8.
Because the research build carries a roughly
-0.066 layout offset of its own, the granularity
curve inside the research build is better read as:
flat to mildly positive at G = 2 and G = 4, and a
clear penalty at G = 8. Either way, no point
offers a verified gain over the production point,
and the production point is confirmed.

## Gates

Gate 2 (correctness, completed before the
campaign, RAW_RESULTS/gates.log): ALL PASSED, 72
PASS lines. Per granularity point (G = 1, 2, 4, 8)
and for the production library as control: 108,000
randomized differentials vs hashlib (540,000 total,
bad 0); batch outputs byte-identical to the
production binary over 4,194,304 digests per point
(16,777,216 total, bad 0); search exact at threads
1 and in agreement at threads 2 and 4 under the
EXP-047 corrected criterion (48 genuine hits per
point). Only the order of the two batches' round
steps differs between points; the arithmetic is
the production arithmetic, verified bit-exact.

Gate 4 (the campaign): 13 sessions of 30,000 pairs
in the predeclared fixed chain order (control, g2,
g4, g8, g1, g2, g4, g8, control, g1, g2, g4, g8),
390,000 pairs total, exactly the predeclared
budget cap, all sessions run regardless of
intermediate results. 780,000 timed arm calls,
every one recording attempted == backend_attempted
== 65,536 and rc == 0 (asserted by the driver on
every call and re-verified pair by pair by the
completing agent: stored log-ratios recompute from
the recorded arm rates with max error 0.0, AB/BA
splits between 14,827 and 15,173 per session,
coverage assertions equal to the pair sums, one
driver hash, one variant binary hash and one
production binary hash across all 13 session
manifests, and every manifest carrying this
predeclaration's sha256).

Resolution achieved: the sizing probe (production
arm only, before the declaration) measured a
per-pair log-ratio SD of 1.3770 and predicted a
pooled Bonferroni half-width of about 0.0110; the
achieved corrected pooled half-widths are 0.0105
(G = 2), 0.0096 (G = 4) and 0.0096 (G = 8), all at
or under the predeclared 0.012 FLAT resolution
target.

## The two EXP-053 audit lessons, as implemented here

(a) Steal covariate. The EXP-053 driver's D-1
defect (second steal sample minus first TOTAL
jiffies) is NOT present in this driver.
exp054_paired_bench.py, env_interval(), computes
verbatim:

    steal_delta = second["cpu_steal_jiffies"] - first["cpu_steal_jiffies"]

the EXP-017 / EXP-041 form. Corroboration from the
data: the recorded steal_fraction of all 780,000
arm calls lies in [0.0, 1.0] (per-arm session means
0.017 to 0.038), where the defective formula
produced values around -76,000 in EXP-053. No
verdict-impact assessment is needed: the covariate
is correctly computed, and the unadjusted
cross-check above agrees regardless.

(b) Deterministic analysis seed.
exp054_analyze.py derives each comparison's
bootstrap seed from sha256 (seed_for():
sha256 of "EXP-054:" plus the comparison name,
taken mod 2**31); Python's salted string hash is
not used anywhere in the analyzer. The analysis is
bit-reproducible across invocations on the same
session files; the EXP-053 salted-hash wart (audit
note N-2) is not inherited.

## Judgment calls, stated openly

1. Host change mid-campaign. The campaign was
   interrupted twice (campaign.log). The first
   interruption (position 6) was rerun on the same
   host. The second was a VM replacement that
   changed the host from AMD EPYC 9D25 to AMD EPYC
   9D64; per the predeclaration's rule, the killed
   session was rerun, never resumed or edited, so
   the third G = 4 session and the third G = 8
   session were measured on the 9D64 host. The
   predeclaration names the 9D25 host. The paired
   design keeps every session internally valid
   (both arms on the same host inside a session)
   and the pooled estimator fits per-session
   intercepts, so the host shift enters as
   between-session variance, not arm bias. The
   direction of every G = 4 and G = 8 session
   agrees on both hosts (each session's corrected
   interval entirely below 0), so neither SLOWDOWN
   classification rests on pooling across hosts;
   but the pooled magnitudes for G = 4 and G = 8
   are mixtures across two hosts and read lower
   than the 9D25-only sessions (the 9D64 sessions
   show visibly smaller penalties and lower
   absolute rates, with mean steal about 0.038
   against about 0.018). G = 2, the control and
   the build control were measured entirely on
   9D25.
2. Build-control attribution. Covered above: the
   G = 4 classification is a slowdown against the
   shipped production binary under the predeclared
   mapping, and at the same time it is at or below
   the measured build offset and so cannot be
   attributed to granularity alone. Both statements
   are in the record; neither is hidden.
3. Analysis provenance. The original builder ended
   without a final report after the campaign
   completed. The analysis was run once, detached,
   from the builder's launch; a second analyzer
   process started in error by the completing agent
   was killed minutes in, before producing any
   output, restoring the one-process rule. The
   analysis is a deterministic pure function of the
   session files (see lesson (b)), so the brief CPU
   sharing cannot touch the numbers. The surviving
   run exited rc 0 (analysis_run.log, ANALYSIS_EXIT
   marker) and wrote
   analysis_20261117T065523Z.json.
4. Registry status. The registry records this
   experiment as REJECTED, matching the EXP-053
   treatment of an established negative: the
   rejected object is the displacement hypothesis
   (Y-043's open question), not the production
   point, which the same verdict confirms.

## UNVERIFIED register

- Other hosts: 11 of 13 sessions on AMD EPYC 9D25,
  2 on AMD EPYC 9D64 (see judgment call 1). The
  Intel Xeon Platinum 8321HC rotation host is
  unmeasured; per-point magnitudes, and the size
  of the build offset, are host-specific.
- The batch entries' rates (Gate 2 correctness
  only; no batch rate claimed, per predeclaration).
- Thread counts other than 2.
- Granularity combined with other kernel
  ingredients (the EXP-053 prefix share, EXP-022
  flags), and granularity points between the swept
  ones (G = 3, 5, 6, 7) or beyond 8.
- Whether a research build laid out to match the
  shipped binary's code layout would erase the
  -0.0658 build offset; the offset is measured,
  its mechanism (layout vs build flags) is not
  isolated.
- Full make test-all on this tree state (45
  targets after this experiment's Makefile
  addition): the two suites covering this
  experiment's surface and the production path it
  measured against were run by the completing
  agent, one at a time, and passed (make
  test-exp054: ALL PASSED, 72 PASS lines, tallies
  identical to the pre-campaign gates.log; make
  test-avx512dual: ALL PASSED, including a fresh
  regtest block at height 2370 through the
  production backend); test-all as a whole was
  not rerun.
- GPU: none exists on this VM and none is claimed.
