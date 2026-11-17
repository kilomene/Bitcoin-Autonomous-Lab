# EXP-052 audit: bake-off hardening into production dispatch

Date: 2026-11-17. Auditor: independent (not the
builder). Subject: EXP-052, portfolio NOVA-ER-0012,
register R-23. Predeclaration:
research/sha256d/exp052/PREDECLARATION.md, sha256
verified by the auditor as
4dfba1104beac6de13ea6433ed68271f6f692d59657b7ea5478aeae9212f88d9,
matching the value pinned in the campaign driver and
the test suite.

## Verdict: PASS WITH NOTES, 2 defects

Both defects are real and both are recorded below
with their evidence. Neither affects the campaign
verdict, the classification, or the registry status:
every predeclared gate passes as specified, the
Gate 4 numbers reproduce exactly from the raw units,
and the STATIC verdict follows from the predeclared
rule by two independent routes. Both defects sit in
the resolver's robustness surface, outside the
predeclared Gate 3 case list, and both should be
fixed before any live enablement of the dispatch
switch (which remains an owner decision and was not
attempted).

Classification confirmed: PARTIAL COMPLETE on the
AMD EPYC 9D25 host, PROMISING HYPOTHESIS, registry
status UNDER_INVESTIGATION. The portfolio entry's
completion condition (at least one rotation of each
host kind, or an explicit partial verdict) matches
the recorded scope exactly: the Intel Xeon Platinum
8321HC rotation and a second AMD rotation are
outstanding, and nothing in the report claims
otherwise.

## What the auditor verified independently

1. **Gate 4 statistics, recomputed from the raw
   units.** All 18 (comparison, session) unit files
   are present (6 comparisons x 3 sessions, 150
   pairs each, 0 voided pairs). Every recorded
   log-ratio is consistent with the recorded arm
   rates to 1e-12. Recomputing the EXP-017 statistic
   (the analyzer's own session_frame, design,
   fit_alpha, boot_alpha and boot_mean functions,
   imported unmodified, driven by the auditor's own
   glue under the predeclared seed rule) for the
   control and two challengers (v512, shani)
   reproduces the campaign record to a worst
   difference of 1.1e-16 across per-session and
   pooled adjusted means and CIs: control pooled
   adjusted +0.017467, CI [-0.110114, +0.145157];
   v512 -0.626384, CI [-0.737486, -0.519959]; shani
   -0.822054, CI [-0.936805, -0.707309]. A robustness
   variant (unadjusted paired log-ratio, plain pairs
   bootstrap, a different seed, no covariates) agrees
   in substance: control CI [-0.110, +0.144], v512
   [-0.737, -0.514], shani [-0.934, -0.709]. Re-running
   the shipped decide() on the recorded analysis
   reproduces the recorded decision exactly (winner
   None, qualified [], control_ok False).
2. **Verdict mapping.** The bound is log(1.05) =
   0.048790. The control pooled CI is wider than plus
   or minus the bound, so under the predeclared rule
   no challenger could be certified; independently,
   every challenger's pooled CI lies entirely below
   zero, so no challenger satisfies the displacement
   condition either. STATIC is overdetermined, as the
   report states. The predeclaration's first verdict
   branch (Gate 3 all pass, Gate 4 complete with the
   static pick passing correctness, Gate 5 all pass)
   maps to PARTIAL COMPLETE / PROMISING HYPOTHESIS /
   UNDER_INVESTIGATION, and the registry records
   exactly that. The correctness record shows all six
   eligible tiers passing (1,024 of 1,024 digests,
   genesis agreement) and cuda ineligible (resolved
   to cpu, recorded, excluded). Campaign timing is
   corroborated by file timestamps: started
   2026-11-17T15:00:42Z, record written 15:19:17Z
   (the report's about-18.6-minute total wall; the
   record's 460.3 s is the measurement wall inside
   the 3,600 s budget).
3. **Gate 3, shipped suite plus the auditor's own
   probes.** The shipped suite passes 36 of 36 under
   the auditor's own run. The auditor then ran 38
   additional probes against the resolver and the
   cache validator. All predeclared-class doubts fall
   back to "auto" without raising: extra top-level
   schema key; decision field of the wrong type;
   empty tiers list; boolean timestamp; unknown
   static_pick; an Infinity token in a tier rate;
   the cache path being a directory; fingerprint
   mismatches in logical_cpus (value, type, or an
   extra key in the presented fingerprint); age one
   second beyond max_age_s; a timestamp 301 s in the
   future; malformed max_age_s or margin values in
   the operator config (non-numeric, None, negative,
   NaN). Two probe families did not fall back; they
   are defects D-1 and D-2 below.
4. **The seam.** Diffing mining/mainnet_live.py and
   mining/endpoint_config.py against the pushed
   pre-EXP-052 versions at remote HEAD
   7a54fe72507aa83622aa09ccf39a173466fa6f79 shows
   exactly the declared edits and nothing else: in
   mainnet_live.py, the single conditional block
   replacing `engine = ComputeEngine()`; in
   endpoint_config.py, the additive BAKEOFF_DEFAULTS,
   the "bakeoff" entry in DEFAULT_CONFIG, and the
   bakeoff_config() accessor. ComputeEngine's
   constructor default is requested="auto"
   (gpu/engine.py, class at line 897), so with the
   switch off the construction is identical to the
   pre-EXP-052 line. The live endpoint config carries
   no "bakeoff" section, and the merged live
   bakeoff_config() returns enabled False. The
   bakeoff_dispatch import sits inside the enabled
   branch only. Probes confirm the resolver never
   measures (a rigged engine factory recorded zero
   calls during an enabled resolve, which took
   0.1 ms) and never consults the cache while the
   switch is off (read_cache rigged to raise; the
   disabled resolve still returned "auto"). The real
   campaign cache resolves to its STATIC verdict
   under the live host fingerprint.
5. **Denotation rule.** With stub engine factories:
   an engine reporting a foreign backend for every
   request leaves only the genuinely denoted tier
   eligible; engines reporting backend None, or
   objects with no backend attribute, leave every
   tier ineligible and static_pick returns
   (None, None); a tier raising at construction is
   recorded with its fault and excluded while the
   others stay eligible. A silently falling-back tier
   cannot be measured or cached under the requested
   name through the runner path.
6. **Registries and Makefile, against the remote.**
   Remote HEAD confirmed as
   7a54fe72507aa83622aa09ccf39a173466fa6f79 (read-only
   fetches). Both markdown registries
   (research/sha256d/experiment_registry.md and
   research/sha256d/extreme_optimization/
   EXPERIMENT_REGISTRY.md) are append-only over the
   pushed versions (local files start with the exact
   remote bytes), their appends are byte-identical to
   each other (3,555 bytes each), contain the EXP-052
   entry, and close at "Next unreserved ID: EXP-059."
   The JSON registry parses at 109 entries; the first
   108 are identical (parsed) to the pushed 108, and
   EXP-052 is last with status UNDER_INVESTIGATION.
   The Makefile diff against the remote is limited to
   the test-exp052 target block and the test-all
   token; test-all now lists 50 targets.
7. **Suites run by the auditor.** make test-exp052:
   36 checks, ALL PASSED. make test-exp050: 40
   checks, ALL PASSED. make test-mainnet-live: ALL
   PASSED.
8. **Hygiene.** U+2014 count is zero in all 12
   EXP-052 touched files (module, both seam files,
   test suite, Makefile, three registries,
   predeclaration, report, both drivers). The live
   endpoint config's sha256
   (d741cde3c6224406f46f3bae138fb174eb1d780725bcb94
   baff4e14a8670c7d3) and mtime (2026-11-14) are
   unchanged before and after the audit. No cache
   exists at .local/bakeoff-dispatch.json. The live
   stack (bitcoind, autopilot, miner) was observed
   running at the end of the audit; the auditor
   signalled no live process and ran measurement
   probes only at stub scale.

## Defects

- **D-1 (minor; does not affect the verdict): the
  resolver can raise on wrong-typed arguments,
  falsifying its "never raises" contract.** The
  module and resolver docstrings promise that
  resolve_requested never raises, and Gate 3's
  preamble requires that no case raise out of the
  resolver. The 12 predeclared cases honour that,
  but the argument coercion at the resolver's entry
  is unguarded: a non-mapping bakeoff_cfg (an int,
  a string, a list) raises TypeError or ValueError
  from `dict(bakeoff_cfg or {})` before any doubt
  handling; a non-mapping fingerprint argument
  raises from `dict(fingerprint)` inside
  validate_cache, which read_cache calls outside
  its try block; a non-numeric `now` raises TypeError
  in the age computation. Related: an integer
  cache_path is passed to open() as a file descriptor
  (in the auditor's probe it landed on a closed
  descriptor and was caught as OSError doubt; the
  type is never validated). Live impact today is
  nil: the seam passes bakeoff_config() output (a
  real dict) with fingerprint and now defaulted, so
  none of these inputs can occur on the live path.
  The defect is against the documented contract, and
  the fix (coerce or reject non-mapping cfg and
  fingerprint, and non-numeric now, at resolver
  entry, returning doubt) should land before any
  live enablement.
- **D-2 (minor hardening gap; does not affect the
  verdict): cache validation never cross-checks the
  winner against the cache's own tier rows.** Two
  auditor probes validate and resolve to a winner
  that the cache itself contradicts: (a) winner
  "cuda" in a cache whose tiers row for cuda records
  eligible false with resolved backend cpu resolves
  to requested "cuda"; (b) a winner whose tier has
  no row in the tiers list at all resolves to that
  winner. Presented with the switch on, case (a)
  would make mainnet_live construct
  ComputeEngine(requested="cuda"), which silently
  resolves to the cpu fallback: the silent-fallback
  failure mode the denotation rule exists to
  prevent, reachable through an internally
  inconsistent cache. The predeclared Gate 3 case 7
  covers only a winner naming an unknown tier, so no
  predeclared gate fails. Mitigations are real: the
  only writer, the campaign runner, derives its
  winner from decide() over eligible,
  correctness-passing challengers and cannot emit
  such a record, and validation still requires exact
  fingerprint equality with the current host. The
  missing check is cheap (the winner's tier row must
  exist with eligible true and resolved_backend equal
  to the denoted backend) and should land before any
  live enablement.

## Notes

- **N-1: a cached margin edited upward validates,
  and that is the predeclared rule, not an
  oversight.** A cache whose margin field was raised
  to 0.50 after writing resolves to its winner. The
  predeclaration's validation criterion is "cached
  margin at least the predeclared 0.05"; the recorded
  margin documents the rule the decision was made
  under, and decide() applies the margin itself at
  campaign time. Symmetrically, raising the operator
  config margin above the cached margin produces
  doubt, as designed (the resolver takes the maximum
  of the two). Recorded so the behaviour is a
  conscious reading of the spec.
- **N-2: boundary semantics.** Age exactly equal to
  max_age_s validates, matching the predeclaration's
  "at most max_age_s". The future-timestamp tolerance
  is a 300 s implementation constant the
  predeclaration does not state: a timestamp exactly
  300 s in the future validates, 301 s is doubt. The
  report lists a future-timestamp case among those
  exercised; the constant's value is the auditor's
  observation, not a predeclared bound. No verdict
  impact.
- **N-3: a winner equal to the static pick resolves
  under the "winner:" reason with the tier name
  rather than "auto" with the "static:" reason.**
  Dispatch is identical (the requested value denotes
  the same backend the static order would construct);
  only the seam's log wording differs. Cosmetic.
- **N-4: the control's resolution failure is
  estimator-robust.** The report's judgment call 1
  (this campaign resolved about plus or minus
  13 percent, not the percent level the sizing basis
  expected) is corroborated by the auditor's
  unadjusted, differently seeded recomputation
  (control CI [-0.110, +0.144]). The conclusion that
  no challenger could have been certified at the
  5 percent margin does not depend on the covariate
  adjustment, and the STATIC verdict does not depend
  on the control clause at all (every challenger CI
  lies entirely below zero).

## UNVERIFIED

- The campaign's historical running conditions
  (contention, load averages, steal) as fact: the
  auditor verified the raw record's internal
  integrity and every statistic derived from it, but
  did not witness the 2026-11-17 15:00 UTC run, and
  the recorded median rates are descriptive values
  from that run, not re-measured (re-measuring would
  be a new campaign under its own predeclaration,
  not an audit).
- A measured-winner Gate 5: both genuine protocol
  runs produced STATIC verdicts, so the seam's winner
  path is verified only through synthetic winner
  caches (the shipped suite's baseline and the
  auditor's probes P1, P2, P3 and P12, two of which
  produced defect D-2). A genuine challenger winning
  and dispatch following it remains UNVERIFIED, as
  the report's own register states.
- Behaviour across host rotations (Intel Xeon
  Platinum 8321HC, a second AMD rotation), live
  enablement and any live-rate effect, certification
  power at the 5 percent margin in a future campaign,
  long-horizon cache behaviour inside the 7-day
  bound, and fleet conditions: all UNVERIFIED and
  outstanding, per the predeclaration and the
  report's registers, and untouched by this audit.

Nothing was fixed and nothing was pushed by the
auditor. D-1 and D-2 are referred to the parent for
a fix decision before any push that would enable
the switch; neither blocks recording EXP-052 as
PARTIAL COMPLETE on this host.
