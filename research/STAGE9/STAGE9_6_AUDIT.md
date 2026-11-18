# Stage 9.6: Independent Audit

Auditor: independent of the Stage 9.6 builder. Scope:
research/STAGE9/MAINNET_READINESS_REPORT.md,
research/STAGE9/PERFORMANCE_GAP_REPORT.md, and the
evidence under research/STAGE9/evidence_96/
(live_observation.json, gap_computation.json,
compute_gap.py). Method: every material number was
recomputed by the auditor from primary inputs, the live
stack was re-observed read-only, the miner statistics
census was re-run against .local/miner.out, production
file hashes were re-taken with sha256sum and compared
against the Stage 9.1 baseline and the post Stage 9.4
record, and the cited prior findings were spot-checked
against the Stage 9.1 closure ledger, the Stage 9.2
promotion decisions, the Stage 9.3 test audit, and the
originating experiment reports. Nothing was pushed,
nothing in the live stack was modified, restarted or
reconfigured.

## Verdict: PASS WITH NOTES

No defects. Every material figure in both reports
reproduces exactly under independent recomputation, the
three live-evidence categories are kept strictly
separate, the success criterion is stated plainly as NOT
met, the gate classifications match the cited evidence,
and no target is lowered anywhere. The notes below are
verification-scope notes, not defects.

## 1. Arithmetic, recomputed by the auditor

- Difficulty from nbits: the auditor recomputed the
  difficulty from nbits 0x17021673 alone (target =
  mantissa x 256^(exponent-3); difficulty = difficulty-1
  target / target). Result: 134,823,837,323,272.66,
  exactly the value both reports use. MATCH.
- compute_gap.py: the auditor ran
  research/STAGE9/evidence_96/compute_gap.py. Its output
  reproduces gap_computation.json field for field,
  including difficulty_cross_check_equal true. MATCH.
- Expected hashes per block: difficulty x 2^32
  recomputed as 5.7906397202468024e23. MATCH with both
  reports (about 5.7906e23).
- Expected waiting time: 5.7906397202468024e23 /
  21,357,487.270541083 = 2.7112926005270184e16 seconds =
  859,156,780 years (365.25-day years). MATCH with both
  reports, and both label it a STATISTICAL ESTIMATE.
- Systems to 500 GH/s: 500e9 / 21,357,487.270541083 =
  23,410.99, reported as about 23,411. MATCH.
- Systems to 140 TH/s: 140e12 / 21,357,487.270541083 =
  6,555,078.24, reported as about 6,555,078. MATCH.
- Live stack share of the minimum objective:
  21,357,487 / 500e9 = 0.004271 percent, reported as
  about 0.0043 percent. MATCH.
- Interval rate: (85,259,089,184 - 79,458,423,584) /
  (3,992 - 3,753) s = 5,800,665,600 / 239 =
  24,270,567.36 H/s, reported as 24,270,567 H/s. MATCH.
  The gap report's statement that using the interval
  figure would shrink every gap by about 12 percent also
  checks: 1 - 21,357,487.27 / 24,270,567.36 = 0.1199.
- Per-sample cumulative averages in the gap report's
  table: 79,458,423,584 / 3,753 = 21,171,975.38;
  80,810,681,216 / 3,813 = 21,193,464.78;
  83,713,139,584 / 3,933 = 21,284,805.39;
  85,259,089,184 / 3,992 = 21,357,487.27. All four match
  the table as rounded. MATCH.

## 2. Sustained-rate basis

The headline rate, 21,357,487 H/s, is the cumulative
whole-run average at the final sample (85,259,089,184
hashes / 3,992 s), and the auditor confirmed it is the
figure used in every headline computation in both
reports (waiting time, both systems figures, the
percentage). The higher interval rate (24,270,567 H/s)
is disclosed in both reports, with the reason the
conservative figure is used stated in each. The live
status line re-read by the auditor at 2026-11-18T07:14Z
(t = 4,232 s, 91,148,540,480 hashes, printed rate
21,535,662 H/s, backend v512dual, best share difficulty
51.2302) is consistent with the builder's samples and
with the best-share figure the readiness report cites.

## 3. Live evidence categories

- (a) Pool-accepted shares: live_observation.json
  records 1,082 accepted at 2026-11-18T07:11:11Z,
  rejected 8, share_results 1,090, with the heartbeat and
  the EXP-037 evidence counter in agreement. The
  auditor's own read at 07:14:33Z showed 1,083 accepted,
  8 rejected, 1,091 share results: the counter rose by
  exactly one share in the interval, as a live counter
  should. The reports state explicitly that shares are
  not blocks, not candidates, and not earnings, and that
  1,082 accepted shares correspond to 0 BTC earned on the
  solo-style pool. No wording anywhere in either report
  blurs shares into earnings or implies a block. MATCH.
- (b) Network-target candidates: the auditor re-ran the
  census against .local/miner.out independently. The
  file held 3,646 status snapshots at audit time (3,639
  at build time; the file is live and appends). Every
  one of the 3,646 carries network_target_candidates 0.
  MATCH: none ever.
- (c) Accepted mainnet blocks: the same census shows
  blocks_submitted 0 and blocks_accepted 0 in all 3,646
  snapshots. The readiness report states the success
  criterion (a real, independently verified, submitted,
  accepted mainnet block) is NOT met, in the verdict
  paragraph, at gate G8, and in section E2(c). MATCH,
  stated plainly.

## 4. Readiness gates (14: PASS 4, FAIL 5, BLOCKED-BY-OWNER 5)

The auditor judged each classification against the cited
evidence:

- G1 PASS: rests on the Stage 9.3 B2 exercise (audited)
  and the Stage 9.5 re-proof. No owner decision is
  involved. Correct.
- G2 PASS: the Stage 9.3 audit record states 48 PASS,
  3 FAIL (the auditor re-read the figure in
  CURRENT_HEAD_TEST_AUDIT.md), with the three failures
  classified as environment, host-fingerprint
  fail-closed, and contention-sensitive respectively.
  The two linked test-design decisions (D-93-2, D-93-3)
  are carried at G12 as BLOCKED-BY-OWNER, so the PASS
  does not smuggle them through. The claim that test-all
  now has 52 prerequisites was verified directly in the
  Makefile: the test-all line lists 52 targets,
  including test-status-publisher. Correct.
- G3 PASS: the auditor read .github/workflows/test.yml
  directly: the clean-runner subset is exactly
  test-exp037, test-exp038, test-probability,
  test-exp049, as the report states. The final-HEAD run
  result (run 44255704573, success) is attributed in the
  report to the Stage 9.5 push record; see note N-1.
  Correct as stated.
- G4 PASS: re-observed live by the auditor (section 9
  below). Correct.
- G5 FAIL (in progress): the auditor's own
  getblockchaininfo at audit time returned blocks
  471,156, headers 976,395, initialblockdownload true,
  verificationprogress 0.1505, pruned, pruneheight
  470730. The report's window figures (471,150 of
  976,395) and its "roughly 505,000 blocks behind"
  (976,395 - 471,150 = 505,245) both check. Correct.
- G6 FAIL (correctly gated on G5): the auditor confirmed
  .local/solo-cutover.json does not exist, the endpoint
  config hash is unchanged (section 6 below), and ran
  the read-only check at audit time: NOT_READY, exit 3,
  "node in initial block download (471159 of 976395
  headers)". Correct.
- G7 FAIL and G8 FAIL: proven by the census in section 3
  above. Correct.
- G9, G10, G11, G13 BLOCKED-BY-OWNER: each is a live
  enablement or deployment of an experimental component
  (fleet activation, EXP-052 dispatch, EXP-057/EXP-058,
  EXP-050/EXP-051), each matches its Stage 9.2 class and
  open items, and none is marked passed. Correct.
- G12 BLOCKED-BY-OWNER: the auditor verified the two
  code locations in source: mining/engine.py line 26 is
  the unconditional "from mining.prefetch import
  PrefetchFeed, PrefetchQueue" (DEF-9.2-2), and
  mining/bakeoff_dispatch.py lines 566 to 567 hold the
  unguarded host_fingerprint() call at the resolver seam
  (DEF-9.2-1). The registry repair, D-93-2, D-93-3 and
  EXP-047 semantics items match the Stage 9.2 and 9.3
  records. Correct.
- G14 FAIL (explicitly not claimed): consistent with the
  Stage 9.4 classifications and the Stage 9.5 scope.
  Correct.
- Keeper rule item: the report's outstanding-items
  paragraph records that the owner decided the rule
  (keep restart on RPC silence), that restarts have been
  held since 2026-11-17 21:06 PST because the literal
  rule loops during sync, and that its application
  awaits the owner's word. This matches the position the
  parent recorded when the hold was taken. Correct.

No gate marked PASS depends on an owner decision, and no
owner-gated item is marked anything other than
BLOCKED-BY-OWNER.

## 5. Node difficulty trap

Confirmed as the reports describe. The auditor's own
getblockchaininfo returned difficulty
678,760,110,082.99 with a validated tip block time of
1,497,395,460 (June 2017): the node's difficulty field
describes its 2017-era validated tip at height 471,156,
not the current network. Both reports flag this, source
the current difficulty (134,823,837,323,272.66) from the
live miner's template_validated events, and back it with
the nbits cross-check the auditor reproduced in section
1. Correct.

## 6. Remote HEAD labelling and file-level verification

The reports take remote HEAD
5b4b27a1fb5f09172748be6cdcb34e1dd7dcda11 from the stage
brief and label the HEAD value itself UNVERIFIED from
this host (the local checkout has no .git), substituting
file-level hash verification. The auditor re-took the
hashes with sha256sum:

- mining/engine.py:
  866936fd6d41ebcc3a5ecbde886b0a5aa27eeae6ad5483025ddf0b3f1635f1ec,
  the post Stage 9.4 value. MATCH.
- mining/mainnet_live.py:
  c8071ce1286c2bc3350afb05a624fd6fd2b16cb1f17808a86cbe922072e3218c. MATCH
  with REPOSITORY_BASELINE.md section 7.
- mining/autopilot.py:
  3cfafc209f4c4e8a965fe6247c05529df45efcf10687fcdeef7a147e3c1ac60a. MATCH
  with the baseline.
- gpu/engine.py:
  bfe605cbb155b59f6b9857e7643348a0a6504160197a663c86d5859911365d46. MATCH
  with the baseline.
- .local/mining-endpoint.json:
  d741cde3c6224406f46f3bae138fb174eb1d780725bcb94baff4e14a8670c7d3,
  mode pool, unchanged. MATCH.

The builder's own report hashes also verify:
MAINNET_READINESS_REPORT.md
41eab14810d1098d41d64344f2e47fededc508cee6cbfa18989df0feeeb8aea5
and PERFORMANCE_GAP_REPORT.md
3372c2d2e35c2b11c6ea4b36879cba97ff583cda9c0b683ed037d5823d9262ea,
both exactly as handed to the auditor.

## 7. Performance register

Spot-checked against the Stage 9.1 closure ledger, the
Stage 9.2 promotion decisions, and originating reports:

- v512 pooled 3.55x and v512dual pooled 1.718x, VERIFIED
  under EXP-017: as recorded throughout the programme.
  Correct tier.
- EXP-022 pooled 1.441x, batch scope only, with the
  Stage 9.2 flag F-5 caution that it is not in the live
  search rate: present and correctly scoped.
- Fallback tiers: AVX2 1.409x (EXP-032) and 1.252x
  (EXP-039) on byte-identical code, SHA-NI streams-4
  2.861x: all three figures appear in
  PRODUCTION_PROMOTION_DECISIONS.md, and the report
  carries the DEF-9.2-5 discrepancy and the host-gated
  EXP-039 refusal check as UNVERIFIED. Correct.
- EXP-052 PROMISING HYPOTHESIS, STATIC by dominance: the
  five pooled log-ratios (v512 -0.6264, shani -0.8221,
  avx2 -1.4638, C -1.9559, hashlib -3.9732) all appear
  in the closure ledger. Correct tier.
- EXP-058 PROMISING HYPOTHESIS, ships disabled, step_up
  leg ESTABLISHED NEGATIVE, hash-rate effect UNVERIFIED:
  as recorded. Correct.
- EXP-050 and EXP-051 harness figures (prefetch loaded
  overhead 389.7 ms to 167.3 ms) appear in the closure
  ledger; the report classes them as latency results,
  not hash-rate results, both UNVERIFIED for live
  enablement. Correct.
- ESTABLISHED NEGATIVE set: EXP-024b design C via
  EXP-046 (the auditor confirmed pooled 0.674x [0.590,
  0.768] in research/sha256d/exp046/EXP046_REPORT.md),
  EXP-053 (pooled -0.0017, in the ledger), EXP-041 and
  EXP-044 (28-op gap closure), EXP-054 displacement.
  Correct.
- Ceilings: EXP-031 effective CPUs 1.87 to 2.04 and the
  1T v512dual figures 5.19M/5.50M H/s confirmed in the
  ledger entry; EXP-020 28-op vocabulary optimum and the
  within-about-1.5x statement as recorded; EXP-056
  solver time 6,519.3 s of 6,600 s confirmed in the
  ledger and the promotion decisions, H-033-02
  INCONCLUSIVE. Correct.
- The gap report states plainly (section 5, and again in
  its opening) that no CPU-software path measured or
  credibly projected in this programme reaches 500 GH/s
  on one system of this class. Neither target is lowered
  anywhere in either report; both are restated at full
  height (500 GH/s, 140 TH/s) as unmet. Correct.

## 8. Character and wording scan

The auditor scanned both reports and all three evidence
files for the U+2014 character: zero occurrences in all
five files. Wording scan: shares are described only as
pool-accepted work; the only earnings statement is that
1,082 accepted shares correspond to 0 BTC earned; no
sentence in either report implies a candidate or a block
was found. Clean.

## 9. Live stack treatment

Read-only throughout, by builder and auditor alike. At
audit time (2026-11-18T07:14Z to 07:20Z): autopilot pid
2830 and miner pid 2833, the same pids as at build time,
both started 06:03Z; heartbeat shows miner_state
running, restarts 0, shares_accepted_total 1,083;
mainnet bitcoind pid 3310 running and advancing (height
471,159 at the auditor's cutover check). No process was
restarted, stopped or reconfigured by this audit.

## Notes

- N-1 (verification scope): the G3 evidence for the
  final-HEAD CI run (run 44255704573, success) is
  carried from the Stage 9.5 push record. The auditor
  verified the workflow file's subset directly but did
  not independently re-query GitHub: the local checkout
  has no .git and the push tooling is off-limits to an
  audit. That one item is UNVERIFIED by independent
  re-query; it is consistent with everything observable
  locally, and the report attributes it to the push
  record rather than presenting it as locally observed.
- N-2 (live counters move): between the build window and
  this audit, shares rose 1,082 to 1,083, the miner.out
  census grew 3,639 to 3,646 snapshots, and the node
  advanced 471,150 to 471,159. All movement is in the
  expected direction for a live stack and confirms the
  reports describe the state at their stated window, not
  a frozen fixture.
- N-3 (rounding): the gap report's sample table rounds
  cumulative averages to whole H/s; the second sample
  rounds 21,193,464.78 up to 21,193,465 under ordinary
  rounding while the headline figure truncates
  21,357,487.27 to 21,357,487. Immaterial at these
  magnitudes; no figure changes.

## For the Stage 9.7 final audit

- Carry forward: remote HEAD remains unverifiable from
  this host class by design (no .git in the checkout);
  the file-hash substitution used in Stages 9.3 to 9.6
  is the standing method and held again here.
- The paired EXP-017 AVX2 re-measure proposed for
  DEF-9.2-5 remains an owner-directed item only; Stage
  9.6 correctly records it as unresolved and does not
  run it.
- The keeper rule's application during IBD remains the
  owner's open decision (rule decided 2026-11-17,
  restarts held since 21:06 PST that day). Stage 9.6
  records it accurately; 9.7 should not reclassify it.
- The three FAIL gates that are statistics, not defects
  (G7, G8) and the two that are time (G5, G6) should be
  carried into the final report at exactly the weight
  Stage 9.6 gives them: the stack is correct, tested,
  supervised and mining valid work, and the success
  criterion is unmet with an expected waiting time of
  about 8.59e8 years at the measured live rate.
