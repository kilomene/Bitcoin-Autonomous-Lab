# EXP-054 independent audit

Date: 2026-11-17. Auditor: independent agent, not the
author. Remote HEAD at audit time:
c9887794e658f13221beaa497a43e65ac8d2ba71. No push was
made by this audit. Scope: PREDECLARATION.md,
EXP054_REPORT.md, exp054_analyze.py,
exp054_paired_bench.py, RAW_RESULTS/ (13 session
files, analysis_20261117T065523Z.json, campaign.log,
gates.log), the three registries, the Makefile, and
the production tree.

## Verdict: PASS WITH NOTES

Defects: 0. The campaign, the analysis and the
report's verdict (CONFIRMED: production granularity
G = 1 stands; the Y-043 displacement hypothesis is
an ESTABLISHED NEGATIVE at the predeclared
resolution) are upheld by independent recomputation
from the raw session files. Notes N-1 to N-4 below
are observations, not defects; each is already
disclosed in the report itself.

## 1. Predeclaration integrity

sha256 of PREDECLARATION.md computed by the auditor:
2aebc8ede2ed62b56a800976898be4b86d9570ccaea5776b6171aaab4a111e46.
It matches the PREDECLARATION_SHA256 constant pinned
in exp054_paired_bench.py and the predeclaration
hash recorded in all 13 session manifests (the set
of distinct manifest predeclaration hashes has size
1). The driver asserts this hash at session start.
The session manifests also carry exactly one driver
hash, one variant binary hash and one production
binary hash across all 13 sessions.

## 2. Independent recomputation

The auditor recomputed the statistic from the raw
session files with separately written code (own OLS
design, fit and 10,000-resample stratified pairs
bootstrap implementation of the predeclared EXP-017
estimator; a different bootstrap seed from the
analyzer's, so interval endpoints carry independent
Monte Carlo noise while point estimates must agree
exactly). Pooled results, auditor values with the
analysis JSON values in brackets:

- control_dual_self: adjusted -0.003839
  [-0.003839], unadjusted -0.003850 [-0.003850];
  adjusted 95 percent CI [-0.0147, +0.0071]
  (analysis [-0.0146, +0.0070]), contains 0.
- search_g1_vs_dual (build control): adjusted
  -0.065764 [-0.065764], unadjusted -0.065786
  [-0.065786]; adjusted 95 percent CI
  [-0.0766, -0.0553] (analysis [-0.0763, -0.0550]),
  excludes 0.
- search_g2_vs_dual: adjusted +0.001649 [+0.001649],
  unadjusted +0.001648 [+0.001648]; Bonferroni
  98.333 percent adjusted CI [-0.0091, +0.0123]
  (analysis [-0.0088, +0.0121]).
- search_g4_vs_dual: adjusted -0.052140 [-0.052140],
  unadjusted -0.052125 [-0.052125]; corrected CI
  [-0.0618, -0.0426] (analysis [-0.0617, -0.0425]).
- search_g8_vs_dual: adjusted -0.150453 [-0.150453],
  unadjusted -0.150429 [-0.150429]; corrected CI
  [-0.1600, -0.1407] (analysis [-0.1600, -0.1408]).

Every pooled point estimate, adjusted and
unadjusted, agrees with the analysis JSON to the
sixth decimal. Interval endpoints agree to within
bootstrap Monte Carlo variation (worst case about
0.0004, at the G = 2 corrected upper bound).

Bonferroni correction: the analyzer reads family
members (G = 2, 4, 8) at level 1 - 0.05/3 =
0.983333, percentiles [0.8333, 99.1667], and the two
controls at 95 percent, exactly as predeclared. The
auditor's recomputation used the same levels.

Verdict branches, checked against the
predeclaration's mapping:

- Control pooled adjusted 95 percent CI contains 0:
  machinery valid, candidate verdicts may be drawn.
- G = 2: corrected pooled CI contains 0, half-width
  0.0105 (analysis) / 0.0107 (auditor), at most the
  predeclared 0.012 target: FLAT.
- G = 4: corrected CI entirely below 0 pooled and
  in every session (auditor per-session corrected
  intervals all end below 0): SLOWDOWN.
- G = 8: corrected CI entirely below 0 pooled and
  in every session: SLOWDOWN.
- No candidate DISPLACING, none PROMISING, every
  candidate FLAT or SLOWDOWN: overall CONFIRMED by
  the predeclared precedence order. The report's
  build-control paragraph prints the -0.0658 offset
  beside the candidate estimates and states that
  effects at or below that size cannot be attributed
  to granularity alone, as the predeclaration
  requires; the G = 4 caveat and the G = 8
  beyond-offset reading in the report are accurate.

## 3. Pairing discipline

Session counts match the predeclared plan exactly:
control 2, build control (g1) 2, g2 3, g4 3, g8 3;
13 sessions, 30,000 pairs each, 390,000 pairs total
(the budget cap). All 780,000 timed arm calls record
attempted == backend_attempted == 65,536 and
rc == 0 (zero violations). Stored log-ratios
recompute from the recorded arm rates with maximum
error 0.0. AB/BA splits per session run from 14,827
to 15,173 (balanced). Coverage assertions equal the
pair sums in every session (30,000 x 65,536 per
arm). Campaign order in campaign.log follows the
predeclared fixed chain, with two interruptions
handled by rerun, never resume (see section 5).

## 4. The two EXP-053 lessons

(a) Steal covariate. exp054_paired_bench.py,
env_interval(), computes verbatim:

    steal_delta = second["cpu_steal_jiffies"] - first["cpu_steal_jiffies"]

the correct EXP-017 / EXP-041 form; the EXP-053
D-1 defect (second steal minus first TOTAL) is not
present. Corroboration: recorded steal_fraction over
all 780,000 arm calls lies in [0.0, 1.0].

(b) Deterministic seed. exp054_analyze.py seed_for()
derives each comparison's seed from
hashlib.sha256 of "EXP-054:" plus the comparison
name, taken mod 2**31. The only occurrence of
"hash(" in the analyzer is a docstring stating that
the salted hash is not used; there is no salted
hash() call. The analysis is deterministic in its
point estimates (confirmed exactly) and
bit-reproducible under its own seeds by
construction.

## 5. Host-change judgment

Session manifests confirm 11 sessions on AMD EPYC
9D25 and the final two sessions (the third G = 4
session, 20261117T052839Z, and the third G = 8
session, 20261117T054630Z) on AMD EPYC 9D64 after a
VM replacement; campaign.log records the
replacement and the rerun of the killed session.
The report discloses this as judgment call 1. The
auditor verified the slowdown does not rest on
pooling across hosts: on the 9D64 host alone, the
G = 4 session's corrected interval is entirely
below 0 (auditor [-0.0329, -0.0093]) and the G = 8
session's is entirely below 0 (auditor
[-0.0666, -0.0412]), as are all four 9D25 sessions
for those points. Pooled magnitudes for G = 4 and
G = 8 are cross-host mixtures and read lower than
the 9D25-only sessions; the report says so.

## 6. Suites (run one at a time by the auditor)

- make test-exp054: ALL PASSED (the Gate 2 suite;
  tallies match RAW_RESULTS/gates.log, 72 PASS
  lines: per point 108,000 randomized differentials
  with bad 0, byte-identical batch outputs over
  4,194,304 digests per point, search agreement
  under the EXP-047 corrected criterion).
- make test-avx512dual: ALL PASSED, including a
  fresh regtest block accepted through the
  production backend at height 2371 (the completing
  agent's run recorded 2370; the shared chain has
  advanced by one since, which is the expected
  shared-regtest behaviour, not a discrepancy).

## 7. Registries and Makefile

- JSON registry
  (research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json):
  104 entries; EXP-054 present with status REJECTED
  (the rejected object is the displacement
  hypothesis, matching the EXP-053 treatment).
- Both markdown registries
  (research/sha256d/experiment_registry.md and
  research/sha256d/extreme_optimization/EXPERIMENT_REGISTRY.md)
  carry the EXP-054 record; the appended sections
  are byte-identical (3,220 bytes each) and end with
  "Next unreserved ID: EXP-055."
- Makefile: test-exp054 target present; test-all
  lists 45 targets.

## 8. Production diff and scans

Full-tree blob comparison against remote HEAD
c9887794 (1,197 remote blobs, tree not truncated):
36 differing files, every one inside the EXP-054
scope (research/sha256d/exp054/**,
tests/test_exp054_granularity.py, Makefile, the
three registries); zero out-of-scope differences,
zero remote-only files, with only the standing
exclusions applied (evidence/mainnet-live.jsonl,
build artifacts under exp032/exp041/exp044,
__pycache__). Production code is untouched.
U+2014 count across the 36 in-scope files: 0.
High-signal secret patterns across the same set: 0.

## Notes

- N-1: The build-control offset (about -0.066) is
  larger than the G = 4 effect, so the G = 4
  SLOWDOWN is a statement against the shipped
  binary under the predeclared mapping, not an
  attribution to granularity. The report states
  this openly; no correction is owed.
- N-2: Pooled G = 4 and G = 8 magnitudes mix two
  AMD hosts (section 5). Classifications are
  per-session robust; magnitudes are host-specific.
- N-3: The analyzer's bootstrap intervals and the
  auditor's differ at the third to fourth decimal
  by seed choice alone; no verdict branch is near
  a boundary except G = 2's FLAT half-width, which
  holds under both seeds (0.0105 and 0.0107 against
  the 0.012 target).
- N-4: Full make test-all (45 targets) was not
  rerun by this audit; the two suites covering this
  experiment's surface and its production baseline
  were run and passed (section 6).

## UNVERIFIED register

- The Intel Xeon Platinum 8321HC rotation host: no
  EXP-054 session ran on it; per-point magnitudes
  and the build offset size there are unmeasured.
- Batch entry rates at any granularity point (Gate 2
  correctness only; no batch rate claimed).
- Thread counts other than 2; granularity points
  G = 3, 5, 6, 7 and beyond 8; granularity combined
  with other kernel ingredients.
- The mechanism of the build-control offset (code
  layout versus build flags is not isolated).
- Full make test-all on this tree state (see N-4).
- GPU: none exists on this VM and none is claimed.
