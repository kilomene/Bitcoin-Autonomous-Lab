# EXP-052 report: bake-off hardening into production dispatch

Date: 2026-11-17. Experiment: EXP-052, portfolio
NOVA-ER-0012, register R-23. Predeclaration:
PREDECLARATION.md in this directory, sha256
4dfba1104beac6de13ea6433ed68271f6f692d59657b7ea5478aeae9212f88d9,
written and hashed before any measurement and pinned
in the campaign driver and the test suite. Raw record:
RAW_RESULTS/ (campaign_exp052-20261117T150042Z.json,
the campaign of record; sessions/ with the 18
(session, comparison) unit files;
bakeoff-dispatch-cache.json, the verdict cache the
campaign produced).

## Verdict: PARTIAL COMPLETE on this host; the static order stands

Classification: **PROMISING HYPOTHESIS** (registry
status UNDER_INVESTIGATION), per the predeclaration's
first verdict branch: Gate 3 all pass, Gate 4 campaign
complete with correctness gates passing, Gate 5 all
pass. The portfolio hypothesis is cross-rotation and
stays unproven; the entry completes only after at
least one rotation of each host kind. What is proven
here, at gate level on the AMD EPYC 9D25 host, is the
hardened mechanism itself: the EXP-017-shaped
protocol ran end to end, the fallback is sound
against every predeclared doubt case, the dispatch
seam honours a valid verdict and falls back on doubt,
and this host's verdict is STATIC.

The verdict on this host is overdetermined. The
static pick is v512dual, and every eligible challenger
is slower by a wide, statistically decisive margin
(pooled adjusted log ratios against v512dual, 95
percent CIs: v512 -0.626 [-0.737, -0.520]; shani
-0.822 [-0.937, -0.707]; avx2 -1.464 [-1.576, -1.348];
c -1.956 [-2.062, -1.846]; hashlib -3.973 [-4.074,
-3.870]). No challenger was anywhere near the
displacement rule, so the static order stands not by
a noise call but by dominance: on this host the
static table already names the fastest tier.

One qualification, disclosed as judgment call 1: the
control comparison (v512dual against a second
instance of itself) returned a pooled adjusted CI of
[-0.110, +0.145], wider than the plus or minus
log(1.05) = 0.0488 resolution bound. Under the
predeclared rule the campaign therefore could not
have certified ANY challenger, even a genuinely
faster one below about a 13 percent advantage. The
STATIC verdict is unaffected (certification failure
can only ever produce STATIC, and every challenger
was in fact far slower), but the resolution cap is a
real property of this campaign and is recorded, not
smoothed over.

## What was built

- mining/bakeoff_dispatch.py (new): host
  fingerprinting (CPU model, sha256 of the sorted
  flags, logical CPUs, from /proc/cpuinfo); tier
  probing under a denotation rule (a requested value
  is eligible only when the engine it constructs
  reports the backend the value denotes, so a silent
  fallback can never be measured under a false name);
  the paired measurement core (65,536-hash blocks
  through ComputeEngine.search_first_counted,
  randomised AB/BA order, steal and runnable
  covariates sampled around every call, attempted
  count asserted equal to the block size); the pure
  decision rule decide(); the verdict cache (atomic
  write, strict validation: exact schema, protocol
  id, fingerprint equality, finite fields, cached
  margin at least the predeclared 0.05, age bound);
  and resolve_requested(), the resolver, which never
  raises, never measures, and returns "auto" (the
  static order) on any doubt with the reason.
- mining/endpoint_config.py: the "bakeoff" section
  in the EXP-050 pattern (BAKEOFF_DEFAULTS, enabled
  False, cache_path, max_age_s 604,800, margin 0.05)
  plus the bakeoff_config() accessor.
- mining/mainnet_live.py: one conditional block at
  the engine construction. Only when the operator
  enabled the section does it consult the resolver
  and log the outcome; disabled (the default, and
  the live config's state) the engine is constructed
  with requested "auto" spelled out, which is the
  constructor's own default: today's behaviour
  exactly. The switch was NOT enabled in this
  experiment; live enablement is an owner decision.
- research/sha256d/exp052/exp052_campaign.py (the
  Gate 4 driver and bake-off runner; resumable,
  per-unit atomic files, predeclaration hash verified
  before measuring) and exp052_analyze.py (the
  EXP-017 statistic computed with the EXP-017
  analyzer's own functions imported unmodified, the
  EXP-054 pattern).
- tests/test_exp052_bakeoff_dispatch.py and the
  Makefile test-exp052 target (test-all becomes 50).

The C_THREADS dependency named in the portfolio
entry was verified from the code, not re-fixed:
Stage 7 made the thread count instance-scoped on
ComputeEngine (gpu/engine.py); the measurement path
passes it through the constructor per instance and
sets or restores no shared state.

## The decision rule (as built, as predeclared)

3 sessions; per session and comparison, 150 paired
65,536-hash blocks at 2 threads; EXP-017 statistic
(paired log ratio, OLS adjustment on steal-difference,
runnable-difference and order covariates, 10,000
resample pairs bootstrap, sha256-derived deterministic
seeds). A challenger displaces the static pick iff
its adjusted CI lower bound exceeds log(1.05) in
every session and pooled, the control pooled CI lies
entirely within plus or minus log(1.05), and the
challenger passed correctness. Otherwise STATIC.
The cache is fingerprint-keyed; a host change voids
it (static fallback) and a fresh runner invocation
produces the new host's verdict: the re-run on host
change. Dispatch never measures.

## Gate 4: the campaign of record

Campaign exp052-20261117T150042Z, host AMD EPYC 9D25
126-Core Processor (fingerprint flags hash
51d3e983ddf6ac93, 4 logical CPUs), run beside the
live mining stack (contention recorded per pair;
mean steal fractions and runnable loads are in the
campaign record). All 18 (comparison, session) units
measured, 0 skipped, 0 voided pairs, 450 pairs per
comparison. Measurement wall 460.3 s inside the
3,600 s budget; total process wall about 18.6
minutes, the remainder being per-tier correctness
and the bootstrap analysis under contention.

Correctness (re-run per tier before measurement, the
EXP-049 self-check): all six eligible tiers passed,
1,024 of 1,024 batch digests against hashlib and the
genesis-span agreement, every tier. cuda was
ineligible (no CUDA device; requested "cuda" resolves
to the cpu fallback, recorded, excluded).

Median rates across all recorded arms (category E,
contended, descriptive): v512dual 8,802,838 H/s;
v512 4,912,312 H/s; shani 4,046,727 H/s; avx2
1,112,710 H/s; c 740,233 H/s; hashlib 99,234 H/s.

Pooled adjusted estimates (log ratio against
v512dual): v512 -0.6264, CI [-0.7375, -0.5200];
shani -0.8221, CI [-0.9368, -0.7073]; avx2 -1.4638,
CI [-1.5763, -1.3477]; c -1.9559, CI [-2.0619,
-1.8464]; hashlib -3.9732, CI [-4.0737, -3.8702].
Every per-session CI tells the same story (all upper
bounds below -0.52). Control: pooled adjusted mean
+0.0175, CI [-0.1101, +0.1452]; the resolution check
failed as described above, so the decision record
shows qualified: [] with the control reason first.
Verdict: STATIC. The campaign cache was written to
RAW_RESULTS/bakeoff-dispatch-cache.json; the live
resolver path (.local/bakeoff-dispatch.json) was
deliberately not written (planting deployment state
is an operator act, and the switch is off besides).

## Gate 3: adversarial fallback (all pass)

Exercised in the test suite against the resolver:
cache missing; cache not JSON; missing keys; wrong
types; CPU-model fingerprint mismatch; flags-hash
mismatch; stale cache; future timestamp; unknown
winner; NaN token and string-in-numeric-field;
cached margin below the predeclared margin; protocol
mismatch; total probe failure (the runner records
PROBE_FAILURE and writes no cache, and a pre-existing
cache is untouched by construction, since the write
happens only after a complete campaign); switch off
with a valid winner cache present (the cache is
never consulted); valid STATIC verdict. Every case
resolved to the static order with a doubt, disabled
or static reason, and none raised out of the
resolver. The decision rule's own branches
(displacement, control failure, one-session failure,
multi-qualifier argmax) are pinned by unit checks on
synthetic analyses.

## Gate 5: dispatch seam trial (isolated, all pass)

In a temporary directory with explicit config dicts
and cache paths, never the live config: (a) the real
campaign cache with the switch on resolves to its
STATIC verdict; (b) a restricted protocol run (tiers
v512 and shani, static v512, 1 session, 40 pairs,
the same runner code and margin rule) produced a
genuine cache (verdict STATIC; shani is far slower
than v512) and the resolver honoured it, with the
constructed engine matching the static engine's
backend; (c) that cache corrupted fell back to
static; (d) that cache with a tampered fingerprint
fell back to static (the re-run that produced it
also exercised the driver's unit-skip resumability);
(e) the switch off ignored the cache. The live
endpoint config's sha256
(d741cde3c6224406f46f3bae138fb174eb1d780725bcb94
baff4e14a8670c7d3) was identical before and after
the whole experiment, and the live stack's processes
(autopilot, miner, node) kept their pids throughout.

## Judgment calls and disclosures

1. **Sizing-basis miss (recorded, not corrected
   after the fact).** The predeclaration's margin
   basis expected the paired design at 150 pairs per
   session to resolve percent-level effects, by
   extrapolation from EXP-054 (0.16 percent at
   30,000 pairs). The measured control says this
   campaign's pooled resolution was about plus or
   minus 13 percent under the day's contention
   (load averages 8 to 10, the syncing node and the
   live miner competing). The rule absorbed the miss
   exactly as designed: no certification was
   possible, and the verdict defaulted to STATIC.
   Nothing was re-sized, re-run or re-tuned after
   seeing results. A future rotation campaign that
   wants certification power at a 5 percent margin
   needs materially more pairs per session; that is
   a new predeclaration's decision, not this one's.
2. **The winner branch of Gate 5 is verified at
   component level, not by a measured winner.** Both
   genuine protocol runs in this experiment (the
   campaign and the restricted run) produced STATIC
   verdicts, because on this host the static pick
   genuinely dominates. The seam's winner path is
   exercised by a schema-valid winner cache written
   by the module's own cache writer (Gate 3
   baseline, resolving to the winner) and by the
   decide() units. A measured-winner Gate 5, where a
   real challenger wins and dispatch follows it,
   remains UNVERIFIED and belongs to the rotation
   campaign (most plausibly the Intel host, whose
   static pick differs).
3. **Restricted-run tier medians in the Gate 5
   record are a seam exercise**, not evidence about
   the tiers; the campaign of record is the only
   measurement cited for rates.

## Suites

make test-exp052: 36 checks, ALL PASSED.
Neighbours, all passed after the seam edits:
test-exp050 (40 checks), test-mainnet-live (ALL),
test-exp049 (20 checks), test-agent-operations
(10,309 checks). test-all becomes 50 targets.

## UNVERIFIED register

- Behaviour across host rotations (an Intel Xeon
  Platinum 8321HC rotation, a second AMD rotation):
  UNVERIFIED and outstanding; the portfolio entry
  completes only there or stays partial. This is the
  headline open item.
- A measured-winner Gate 5 (a genuine challenger
  winning and dispatch following it): UNVERIFIED;
  see judgment call 2.
- Live enablement of the dispatch switch, and any
  effect of a bake-off pick on the live mining rate:
  UNVERIFIED, not attempted; enablement is an owner
  decision.
- Certification power at the 5 percent margin on a
  future campaign: UNVERIFIED at 150 pairs per
  session (this campaign resolved about 13 percent);
  a rotation campaign needs its own predeclaration
  with a pair count sized from this control.
- The pick on any host other than this one:
  UNVERIFIED. The cache voids itself elsewhere by
  design (Gate 3 cases 4 and 5), but that the
  protocol picks correctly on an unseen host is the
  cross-rotation claim and is unproven.
- Long-horizon cache behaviour (staleness inside
  the 7-day bound while contention drifts):
  UNVERIFIED; the bound is a design value.
- Behaviour under real fleet conditions (multiple
  machines): UNVERIFIED; no other machine was
  contacted.

An independent audit is owed before any push.

## Defect-fix addendum (2026-11-17)

The independent audit (EXP052_AUDIT.md, PASS WITH
NOTES) found two defects in mining/bakeoff_dispatch.py,
both in the resolver's robustness surface, neither
affecting the campaign verdict, the classification or
the registry status. Both are fixed, with regression
tests in tests/test_exp052_bakeoff_dispatch.py (layer
3b). Host: AMD EPYC 9D25. This addendum changes no
predeclaration, campaign result, gate verdict or
registry status; EXP-052 stays PARTIAL COMPLETE on
this host, PROMISING HYPOTHESIS, UNDER_INVESTIGATION.

- D-1 (the resolver could raise on wrong-typed
  arguments): resolve_requested coerced its config
  with an unguarded dict(), validate_cache coerced
  the presented fingerprint with dict() outside
  read_cache's guard, a non-numeric now raised
  TypeError in the age computation, and an integer
  cache_path reached open() as a file descriptor.
  The module and this report describe the resolver
  as never raising; before this fix that was false
  for these inputs (the live seam passes a real
  config dict with fingerprint and now defaulted, so
  no live input could reach them). Fixes, all in
  mining/bakeoff_dispatch.py: the config coercion
  returns doubt on TypeError or ValueError; the
  fingerprint coercion inside validate_cache returns
  doubt the same way; now is coerced with float()
  and is doubt on failure; read_cache rejects a
  cache_path that is not a str or os.PathLike before
  opening anything. The documented never-raises
  contract is now true as written. Regression
  checks: non-mapping config (int, string, list),
  non-mapping fingerprint, non-numeric now and
  integer cache_path each resolve to "auto" with a
  doubt reason and no exception (6 checks).
- D-2 (cache validation never cross-checked the
  winner against the cache's own tier rows): a cache
  whose winner was ineligible in its own row (the
  audit's probe: winner "cuda", its row eligible
  false with resolved backend cpu), or whose winner
  had no tier row at all, validated and resolved to
  that winner. Fix, in validate_cache: a non-None
  winner must have a tier row with eligible true and
  resolved_backend equal to the denoted backend for
  that tier; any inconsistency is doubt. The only
  writer, the campaign runner, derives its winner
  from decide() over eligible, correctness-passing
  tiers and cannot emit such a record, and the
  campaign of record's cache still validates and
  resolves to its STATIC verdict under the live
  fingerprint. Regression checks: winner ineligible
  in its own row, winner with no tier row, and a
  winner row resolved to a different backend are
  each doubt (3 checks).

Suites after the fixes: make test-exp052, 45 checks
(36 before, 9 added), ALL PASSED. Neighbours:
test-mainnet-live ALL PASSED; test-exp050, 40 checks,
ALL PASSED on re-run (its first post-fix run failed
one isolated-process liveness check, gate5 "miner
alive after failback"; that suite exercises no
bake-off code path, and the identical suite passed
in full on the immediate re-run, so the failure is
recorded as a contention flake, not a regression).
The live endpoint config's sha256 and mtime are
unchanged, no cache was planted at
.local/bakeoff-dispatch.json, and the live stack
(autopilot, miner, node) was not disturbed.
