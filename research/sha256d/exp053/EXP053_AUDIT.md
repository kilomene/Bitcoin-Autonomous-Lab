# EXP-053 independent audit: prefix sharing in the dual walker

Date: 2026-11-16 (audit run 23:11 UTC to 2026-11-17
01:35 UTC). Host: AMD EPYC 9D25 126-Core Processor.
Auditor: independent of the campaign author and of
the completing agent. Remote HEAD confirmed
bbd11db9414a1032e15a60fb9bc9b69a613fc83a before
diffing; nothing of EXP-053 is pushed.

## Verdict: PASS WITH NOTES. Defects: 1.

The claimed result, ESTABLISHED NEGATIVE at the
predeclared resolution, is upheld by independent
recomputation from the raw session files. The one
defect found (D-1, a miscomputed steal covariate in
the bench driver) is proven verdict-irrelevant
below: the unadjusted statistic, which uses no
covariates at all, lands in the same verdict branch
with margin, and the adjustment moved the pooled
point estimate by 0.000001. Nothing was pushed and
no production code was modified by the audit.

## 1. Predeclaration integrity

PREDECLARATION.md on disk hashes to
039644d5e196102a5ca687e2ffc23fe806588ba6965ea3cae128cbb7068c0a06,
the value hardcoded in exp053_paired_bench.py,
recorded in the manifest of all 8 campaign sessions,
and quoted in EXP053_REPORT.md. Timestamps (UTC):
build_manifest.json 19:17:02, gates.log 19:18:24,
PREDECLARATION.md mtime 19:19:42, first session
started 19:27:09. The declaration demonstrably
predates every campaign measurement, and the driver
asserted its hash at every session start. The
verdict mapping applied in the report is the mapping
written in the predeclaration, branch by branch:
control validity on the pooled control CI first,
then VERIFIED / slowdown / resolved-null /
PROMISING / RESOLUTION LIMIT on the pooled effect
CI against the +0.0118 ceiling and the 0.006
half-width target. No criterion was added, moved or
reinterpreted after the data existed. The analysis
record covers exactly the 8 campaign sessions; the
pre-campaign shakedown session is preserved in its
own directory and was not analysed.

## 2. Independent recomputation (auditor's own code)

The auditor extracted the recorded pairs and
recomputed the statistic with an independent
implementation (own OLS via normal equations, own
10,000-resample stratified pairs bootstrap, auditor
seeds), mirroring the predeclared EXP-017 statistic
definition: paired log-ratios, per-session
intercepts, slopes on the standardised
steal-difference and runnable-difference plus the
raw order covariate, alpha the mean of the session
intercepts.

Pairing discipline, verified on all 240,000 pairs:
attempted == backend_attempted == 65,536 and rc == 0
on all 480,000 arm calls, zero violations; every
stored log_ratio_b_over_a recomputes from the
recorded arm rates exactly (max error 0.0); AB/BA
splits per session between 14,933 and 15,067;
pair indices sequential; each session's coverage
assertion equals its pair sums; arm implementations
match the comparison (production in both slots for
control, variant in slot B for effect).

Per-session adjusted means from the recomputation
match the recorded analysis to 4 decimal places on
all 8 sessions; CI endpoints agree within 0.0005
(bootstrap stream jitter). Pooled results:

- Control: adjusted mean -0.002951 (recorded
  -0.002951, exact), unadjusted -0.002970 (exact).
- Effect: adjusted mean -0.001657 (recorded
  -0.001657, exact), unadjusted -0.001656 (exact);
  fraction of pairs won by the variant 0.501.

## 3. The control-validity question, attacked directly

The first control session's own adjusted CI excludes
0 ([-0.0223, -0.0011] recorded; auditor's stream
[-0.0226, -0.0013]). The predeclaration's validity
test is, in its own words, the pooled interval: "if
the pooled adjusted CI of control_dual_self excludes
0, the machinery as run is biased and no effect
verdict is drawn". Applying the pooled rule as
written is faithful to the predeclaration, for three
reasons. First, the text names the pooled interval
explicitly; substituting a per-session test after
the fact would be exactly the post-hoc criterion
movement the predeclaration exists to prevent.
Second, the design predeclared per-session
half-widths of about 0.0138, so a single 95 percent
session interval excluding the true value is an
ordinary event at this design size, not an anomaly.
Third, the session pattern is the signature of
session-scale noise, not of a fixed arm bias: the
two control sessions bracket 0 in opposite
directions (adjusted means -0.0119 and +0.0060), the
pooled mean is -0.0030, and the fraction of pairs
won by arm B is 0.5006. A fixed bias would push both
sessions the same way.

The session-level fact does not change the effect
verdict. The predeclaration's remedy for a failed
control is "no effect verdict", not a different
effect verdict, and the pooled test does not fail:
the pooled control CI contains 0 in all five
resample streams computed during this audit
(recorded [-0.0108, +0.0048]; author-code rerun
[-0.0110, +0.0050]; auditor's code [-0.0111,
+0.0052], [-0.0110, +0.0051], [-0.0106, +0.0051]).
The report recorded the session fact openly rather
than hiding it, which is the correct handling.

## 4. Bootstrap-seed stability

exp053_analyze.py derives its seed partly from
Python's salted string hash, so its exact resample
stream differs per invocation (report discloses
this). The auditor reran the author's own analysis
code path with a fresh entropy seed and recomputed
with three further auditor seeds. Effect pooled
adjusted CI across the five streams: recorded
[-0.0059, +0.0027]; author rerun [-0.0059, +0.0026];
auditor [-0.0061, +0.0027], [-0.0059, +0.0027],
[-0.0059, +0.0026]. Upper bounds span 0.0026 to
0.0027 against the 0.0118 ceiling (gap at least
0.0091, about 45 times the observed stream jitter);
half-widths span 0.00429 to 0.00437 against the
0.006 target. The author's rerun reproduced the
verdict string itself: ESTABLISHED NEGATIVE at the
predeclared resolution. The classification is not
seed-sensitive.

## 5. D-1: the steal covariate is miscomputed (defect, verdict-irrelevant)

exp053_paired_bench.py line 80 computes
steal_delta = second["cpu_steal_jiffies"] -
first["cpu_total_jiffies"], subtracting the first
sample's TOTAL jiffies instead of its steal jiffies.
The recorded steal_fraction is therefore not a steal
fraction (recorded values run to about -76,000).
This bug is new in this driver: the EXP-017 and
EXP-041 drivers carry the correct line
(second steal minus first steal), so the
predeclaration's description of the machinery was
accurate for the protocol it inherited and wrong
only in this transcription.

Verdict impact: none, proven three ways. (i) The
covariate adjustment moved the pooled effect
estimate by 0.000001 (adjusted -0.001657,
unadjusted -0.001656). (ii) The unadjusted pooled
CI, which uses no covariates, independently
satisfies the same verdict branch: auditor's
[-0.0067, +0.0032] contains 0, upper bound below
the 0.0118 ceiling, half-width 0.0049 at most
0.006. (iii) The defective covariate is constructed
identically for both arms and the pair order is
randomised, so it cannot manufacture an arm effect;
the control comparison, run through the same
machinery, pools to -0.0030 with fraction won
0.5006. The defect must be fixed before this driver
is reused (EXP-054 must not inherit line 80), but
it does not touch the EXP-053 classification.

## 6. Correctness gates (auditor's own reruns, one at a time)

- make test-exp053: ALL PASSED. 108,000 randomized
  differentials per library (variant and production
  control), bad 0; vp-vs-vd batch outputs
  byte-identical over 4,194,304 digests, bad 0;
  search exact at threads 1 and in agreement at
  threads 2 and 4 (48 hits). Tallies identical to
  the recorded gates.log.
- make test-avx512dual: ALL PASSED, including
  197,616 differentials through the production
  batch ABI and a fresh regtest block accepted
  through the production backend (height 2369; the
  suite advances the shared regtest chain by its
  own function, as in the author's run at 2368).
  The suites ran sequentially, never in parallel;
  the live miner and node contended throughout, as
  they did for the campaign itself.

## 7. Registries and Makefile

JSON registry: 103 entries (remote 102 plus EXP-053
only; all prior entries identical, other top-level
keys identical); EXP-053 status REJECTED. Both
markdown registries are append-only against remote
(+2,985 bytes each) and their appended chunks are
byte-identical to each other; both state "Next
unreserved ID: EXP-054". Makefile diff against
remote is exactly the new test-exp053 target and
its addition to test-all; test-all count is 44.

## 8. Production untouched

Full blob comparison against remote HEAD bbd11db9
(1,171 remote blobs): content mismatches only in
the Makefile, the three registries, and
evidence/mainnet-live.jsonl (the live evidence
file, perpetually ahead of remote and excluded by
every push driver for that reason). Local-only
paths are the EXP-053 set (research/sha256d/
exp053/** and tests/test_exp053_prefix.py) plus
pre-existing never-pushed build artifacts
(bal-miner and .so files under exp032, exp041 and
exp044, mtimes 2026-11-14 to 2026-11-16 07:56, all
before EXP-053 began). Remote-only paths: none. No
production file differs.

## 9. Scans and live stack

U+2014 count zero across the EXP-053 file set and
tests/test_exp053_prefix.py. Secret-pattern scan:
zero real hits; every 64-hex hit is a public file
hash or block hash (predeclaration, source, binary
and regtest block hashes). Live stack untouched and
undisturbed: heartbeat fresh at audit start and
end, miner_state running on one continuous run
(uptime 6,550 s at start, 15,026 s at end),
shares_accepted_total rising 684 to 710 from the
live miner's own work. Census continuity confirmed
through the heartbeat counter; the audit restarted
nothing.

## Notes

- N-1: PREDECLARATION.md states "Written:
  2026-11-16T19:21Z" while its mtime is 19:19:42Z,
  78 seconds earlier. Immaterial: the hash chain
  (section 1) is the integrity mechanism, and both
  times precede the campaign by minutes.
- N-2: the analysis is not bit-reproducible across
  invocations because of the salted-hash seed
  (section 4). The programme accepted this pattern
  in EXP-053's predeclaration era tooling; the
  stability evidence substitutes for bit equality.
- N-3: Gate 6 correctly did not run; the
  predeclaration runs it only on a VERIFIED
  verdict, and no integration is proposed.
- N-4: the report's claim that the two control
  sessions bracketing 0 is "the signature of
  session-scale noise" is an interpretation; the
  audit's section 3 reaches the same conclusion
  independently, on the predeclaration's text and
  the numbers.

## UNVERIFIED register

- Other hosts: no measurement on the Intel Xeon
  Platinum 8321HC rotation host; the verdict is
  claimed for this AMD host only.
- The batch entry's rate (bal_vp_batch2 was gated
  for correctness only; no batch rate claimed or
  verified).
- Thread counts other than 2, and the prefix share
  combined with other kernel ingredients.
- The counterfactual adjusted CI under a corrected
  steal covariate: not computed, and unnecessary,
  since the verdict branch is already determined
  by the unadjusted interval and the observed
  adjustment shift is 0.000001 (section 5). A
  future campaign reusing this driver must fix
  line 80 first and re-predeclare.
- Full make test-all on this tree state (44
  targets): not run by the auditor; the two suites
  covering the experiment's surface and the
  production path it measured against were run and
  passed, and no production file differs.
- GPU: none exists on this VM and none is claimed.
