# Stage 9 enablements: independent audit

Date: 2026-11-18. Auditor: independent (not the builder).
Subject: research/STAGE9/ENABLEMENTS_REPORT.md, sha256
741847cef4e67b6bb8247f42b3b2ef7598fda04ce124f2236e69ab7365481738
(verified on disk before auditing; the hash matches the
handoff, so the report audited is the report the builder
wrote). Built on remote HEAD
53ad3933dbef5a86bab4db9119e021f3ff1211c0. Nothing was
pushed by this audit; no production file was modified;
the endpoint config and the solo cutover state were not
touched; no process was restarted.

## Overall verdict: PASS WITH NOTES

Defects found: none. Four notes (N-1 to N-4) are
recorded below; none blocks the push or the flip.

Clearance decisions:

- Cleared for push: YES. The changed-file set is exactly
  the builder's manifest (section 10 evidence), every
  claimed hash matches, and the mandated suites re-run
  clean.
- Section 7 flip cleared for execution after the push:
  YES, SAFE TO EXECUTE AS WRITTEN (see claim 8; note
  N-1 recommends, but does not require, a backup copy
  of the endpoint file first).

## Per-claim verdicts

| Claim | Verdict |
|---|---|
| 1. EXP-051 prefetch ENABLED on the agent path | VERIFIED |
| 2. test_mining_engine.py change encodes designed semantics | VERIFIED, legitimate (explicit verdict below) |
| 3. EXP-057 tier DEPLOYED in staging configuration | VERIFIED |
| 4. EXP-052 dispatch ARMED, fresh campaign, cache honoured | VERIFIED |
| 5. EXP-050 endpoint health ARMED in observe/report mode | VERIFIED, honest description |
| 6. EXP-058 PID NOT ENABLED, deliberately | VERIFIED, correct honest outcome |
| 7. EXP-047 documentation DONE | VERIFIED |
| 8. Section 7 flip procedure safety | SAFE TO EXECUTE AS WRITTEN |
| 9. Test totals (29 checks, 53 prerequisites, 52 of 53) | VERIFIED |
| 10. Hygiene (hashes, U+2014, tree, live stack) | VERIFIED |

## Claim 1: EXP-051 prefetch

agent/autonomous.py sha256 294fe09c... matches the
manifest. AutonomousMiner's constructor defaults
use_prefetch=True (line 44) and passes it to
MiningEngine; mining/engine.py keeps its own default
use_prefetch=False (line 559) and is byte-identical to
the fixes batch (11f288ce...). The disclosure comment
at the enablement site states the snapshot semantics
and the one-value rollback, as the report claims.
Evidence agent_prefetch_run.json matches the report
exactly: prefetch on, heights 113 to 119, 6 blocks
accepted, enqueued 6, served 5, starved 1 (cold first
cycle), all drop counters 0; prefetch off, 119 to 125,
queue_constructed false, all counters 0.

## Claim 2: the test change (explicit verdict)

VERDICT: the updated test is a legitimate encoding of
the mechanism's designed semantics, NOT a weakening
that hides a defect.

Evidence, independently obtained:

- mining/prefetch.py (pre-existing EXP-051 code, not
  written by this builder) documents and implements
  the serve rule: at serve time the entry's
  previousblockhash must still be the node's best
  block and its layered identity is recomputed from
  scratch; the transaction set is the prepared set.
  Mempool freshness was never one of the mechanism's
  correctness gates.
- The updated test still asserts the property under
  test: the spend IS mined (loop bounded at 3 cycles,
  hard assert if not), the txid is in the block, fees
  are greater than 0, every cycle's block is accepted,
  and the persistence and mainnet-guard assertions are
  intact and correctly adjusted for the extra cycles.
  The reason and date are written in the test (lines
  62 to 75) and at the enablement site.
- Causality reproduced by the auditor in both
  directions on the shared regtest node: with the new
  default (prefetch on), make test-mining passes with
  the spend mined after 2 cycles; with an auditor
  control driver constructing
  AutonomousMiner(use_prefetch=False), the identical
  scenario mines the spend in the very first cycle
  (tx_count 2). The one-cycle inclusion lag is caused
  by the enablement and by nothing else.
- The consequence is inclusion timing only, bounded at
  one cycle; blocks remain valid and EXP-036 verified.

## Claim 3: EXP-057 aggregation tier

mining/aggregation_mainnet.py sha256 b538c8c0...
matches. Read in full: it fails closed (missing or
malformed deployment file is a fatal startup error,
return 2), verifies the node's chain at startup
against --chain (mismatch is fatal), defaults to port
3334 and never 3333, restores the snapshot through
AggregationTier.restore (aggregation.py line 570 bumps
the epoch on restore, the EXP-055 restart rule; the
module is byte-identical to baseline, 1951a657...),
and configures NO upstream submitter (none is passed;
the startup log line states it). Staging evidence
aggregation_staging_run.json matches the report
exactly: enrolled worker share accepted and accounted
per worker (stage-worker-1 accepted 1), unenrolled and
wrong-token authorizations refused (identity_rejected
2), pending_candidates 1 with upstream_submissions 0,
clean exit 0, snapshot written. The report's remaining
step is stated exactly (the armed cutover still
targets mining/solo_mainnet.py; an operator submitter
is not wired) and the UNVERIFIED register does not
overclaim.

## Claim 4: EXP-052 bake-off dispatch

Import graph verified by search: the only production
caller of resolve_requested is mining/mainnet_live.py
(lines 253 to 267, at engine construction, gated on
the endpoint config's bakeoff section). The builder's
correction of the brief's framing is right: the seam
is the pool miner path, and the EXP-052 report records
the same seam.

Host fingerprint re-probed by the auditor:
{AMD EPYC 9D25 126-Core Processor, flags_hash
c86584c209897fb5, logical_cpus 4}. The planted cache
.local/bakeoff-dispatch.json (sha256 3639d026...)
carries exactly this fingerprint, campaign_id
exp052-20261118T103448Z, winner null, static_pick
v512dual, margin 0.05, and is identical to the re-run
campaign's cache file. read_cache against the current
fingerprint returns (True, "cache valid"). Campaign
record verified: 18 of 18 units measured, 0 skipped,
150 pairs per session, wall 524.6 s, predeclaration
sha256 4dfba110... equals the on-disk
PREDECLARATION.md, pooled adjusted log-ratios match
the report to four decimals (v512 -0.6356, shani
-0.9829, avx2 -1.6031, c -1.8809, hashlib -3.9693),
control pooled CI [-0.1759, +0.0838] too wide for the
5 percent margin and disclosed as such in both the
record's decision block and the report. The campaign
driver (research/sha256d/exp052/exp052_campaign.py)
and every other repo file not in the manifest are
byte-identical to remote HEAD 53ad3933 per the claim
10 tree comparison, so the campaign ran unmodified.
Resolver behaviour reproduced: live merged config
(switch off) returns ("auto", "disabled: ...");
the same config with the section enabled returns
("auto", "static: the bake-off verdict for this host
confirms the static order"). Old-cache voiding
verified empirically: a cache copy carrying the
2026-11-17 fingerprint (51d3e983) resolves to
("auto", "doubt: host fingerprint mismatch ...;
static order"), so the old cache was indeed inert on
this instance and the re-run was the protocol's own
trigger.

## Claim 5: EXP-050 endpoint health

No code change was needed and none was made
(endpoint_health.py, stratum_client.py and
mainnet_live.py are at their audited hashes). The
production seam is as the report describes:
mainnet_live builds the EndpointHealthPolicy only in
pool mode when the pool_health section is enabled,
attaches it to the stratum client, logs
endpoint_policy_enabled, and carries policy.status()
in status events (line 406); the client logs
endpoint_policy_exhausted and endpoint_policy_recovered.
Merged live config shows pool_health enabled False
with fallbacks [] (no second endpoint invented;
.local/mining-endpoint.json sha256 d741cde3...,
mode "pool", unchanged). The isolated-seam evidence
live_seam_run.json contains every claimed event with
the claimed parameters, shares before and after the
outage, and total_failovers 0. Judgment: "armed in
observe/report mode" is an honest description. The
policy observes, names exhaustion and recovery, and
reports status; failover has no target and stays
inert, exactly as the report states.

## Claim 6: EXP-058 PID controller

All three stated reasons verified against the record
and the code:

1. EXP058_REPORT.md judgment call 6 states the
   component "is not proposed for live-miner
   integration on this record", and its UNVERIFIED
   register states actuation against the live
   production miner is UNVERIFIED and not attempted,
   integration a separate step.
2. mining/pid_control.py's AdaptiveWorkController
   runs the inner span loop and the outer worker loop
   as one cascade in a single update() producing one
   Command; make_work_controller exposes a single
   pid_enabled switch. There is no supported
   span-only configuration; the worker scale-up half
   rests on the interval-only signal whose step_up
   reach is an established negative.
3. No actuation surface exists in the production
   miner: mainnet_live constructs ComputeEngine with
   requested only and derives its scan span from the
   probe rate for template-preemption latency; the
   autopilot supervises processes, not engine
   parameters.

The enablements suite genuinely pins the state: it
reads mining/autopilot.py, mining/mainnet_live.py,
mining/engine.py, agent/autonomous.py and
mining/fleet_gateway.py and asserts "pid_control"
appears in none of them (auditor's own search across
mining/, agent/, gpu/ and scripts/ confirms zero
production importers), and it verifies the
controller's own switch and disabled default in
isolation.

Judgment, stated plainly: NOT ENABLED is the correct
honest outcome under the owner's "enable all five"
instruction. No supported partial enablement existed
that the builder missed: the only candidate (span
loop only) would require splitting the predeclared
cascade into a configuration the experiment never
specified, measured or audited, which is a new design
requiring its own predeclaration, not an enablement.
Enabling the whole unit would have wired a refuted
scale-up path into the live miner against the
experiment's own audited record. The builder recorded
the exact remaining step instead. That is the
decision the evidence supports.

## Claim 7: EXP-047 documentation

EXP047_COMPLETION_REPORT.md sha256 c9239f6a...
matches; the appended section 8 "Owner acceptance
(2026-11-18)" is present with the wording the report
quotes, recording first-publisher-wins
(search_first_counted) as the accepted production
semantics, the minimum-identity criterion as an
ESTABLISHED NEGATIVE, and batch_search or
single-threaded search as the route to the span
minimum. Registry EXP-047: measured_result carries
the dated owner-decision note and unresolved[0] is
marked RESOLVED 2026-11-18. The auditor's own search
of gpu/engine.py, mining/cpu/bal_search.h,
mining/engine.py, agent/ and mining/*.py finds no
text claiming a span-minimum guarantee, confirming
the builder's scan. The registry's dated enablement
notes on the EXP-050, EXP-051, EXP-052, EXP-057 and
EXP-058 entries were each read and match the
outcomes verified under claims 1, 3, 4, 5 and 6.

## Claim 8: section 7 flip procedure (reviewed, not executed)

VERDICT: SAFE TO EXECUTE AS WRITTEN.

Reasoning from mining/endpoint_config.py and
scripts/solo_cutover.py:

- The procedure loads the RAW endpoint file, adds
  only the two sections, and writes through
  endpoint_config.write_config (atomic replace, mode
  0600). Mode, pool, solo and payout_address are
  preserved verbatim. The merged reader supplies the
  sections' remaining defaults (bakeoff cache_path
  null means the module default, the planted cache;
  margin default 0.05 equals the cache's recorded
  margin; pool_health fallbacks default to empty).
- The armed solo cutover is not broken: the cutover
  script gates on load_config()["mode"] == "pool"
  (unaffected), and flips through set_mode(), which
  loads the MERGED config and writes it back, so both
  sections survive the cutover's own flip and its
  rollback verbatim. In solo mode the pool_health
  policy is never constructed (mainnet_live gates it
  on pool mode) and the bakeoff resolver returns
  "auto" with the STATIC verdict, the identical
  engine, so neither section can disturb solo share
  production or the cutover's verification.
- The keeper and the autopilot do not parse these
  sections; the miner reads the config at (re)start,
  which is the stated effect timing.
- Rollback (same write with both enabled values
  false) restores today's behaviour exactly: with
  enabled false the resolver is never consulted and
  the policy is never constructed. See note N-1 for
  the one cosmetic difference.

## Claim 9: test totals

Suites re-run by the auditor, one at a time:
test-enablements 29 checks ALL PASSED;
test-exp050 40 checks ALL PASSED; test-exp052 46
checks ALL PASSED; test-exp057 15 checks ALL PASSED;
test-exp058 10 checks ALL PASSED; test-mining ALL
PASSED (see claim 2); test-exp051 ALL PASSED. Every
count matches the report. The Makefile's test-all
prerequisite list contains exactly 53 entries with
test-enablements last. test_all.log sha256
20b362b2... matches the handoff; the log contains
the test-rtl failure as an iverilog-not-found
AssertionError and the enablements suite passing as
the final suite, consistent with the claimed 52 of
53 with the pre-existing Stage 9.3 environment
failure as the only miss. The full 53 were not
re-run by this audit (outside the mandate); the
tally rests on the builder's log plus the seven
suites re-run here (note N-2).

## Claim 10: hygiene

- Every sha256 in the report's manifest (5 changed,
  11 created/evidence files, the planted cache, and
  the 7 "verified unchanged" files) was recomputed
  and matches. The report's own hash matches.
- U+2014 count is zero in every created or edited
  file, this audit's subject files included (auditor
  scan of all 17 manifest files).
- Full-tree comparison against remote HEAD 53ad3933
  (recursive tree, git blob shas, 1,464 remote
  blobs): changed files are exactly the manifest's 5
  (Makefile, agent/autonomous.py, tests/
  test_mining_engine.py, EXPERIMENT_REGISTRY.json,
  EXP047_COMPLETION_REPORT.md); local-only files are
  exactly the manifest's created set, the previously
  known fleet in-flight set (18 files, from the
  earlier fleet workstream, not this one), timestamped
  Gate 6 RAW_RESULTS outputs of suite runs, and the
  bal-miner binary dated 2026-11-14 (pre-existing
  build output); remote-only files: none. The only
  other changed paths are live/test churn:
  evidence/mainnet-live.jsonl (the running miner's
  own append-only evidence) and the exp055/exp057
  Gate 5/6 state files that those suites rewrite on
  every run, including this audit's re-runs. No
  unlisted source modification exists.
- Live stack undisturbed: heartbeat at
  2026-11-18T12:19Z shows autopilot pid 3241, miner
  pid 3248, restarts 0, shares_accepted_total 1148
  (1132 before the workstream, 1147 at the builder's
  close; non-decreasing throughout).
  .local/mining-endpoint.json is byte-identical to
  its pre-workstream state (d741cde3..., mode
  "pool"); .local/solo-cutover.json does not exist
  and was not created.

## Notes

- N-1 (flip rollback exactness): the section 7
  rollback is behaviourally exact but not byte-exact:
  it leaves bakeoff and pool_health sections with
  enabled false in the file, where the pre-flip file
  has no such sections. Under load_config merging the
  two states are indistinguishable, and set_mode()
  preserves either. A prudent operator copies the
  file aside before flipping so a byte-exact restore
  is available. Not a safety issue; does not change
  the claim 8 verdict.
- N-2 (tally evidence basis): the 52 of 53 test-all
  tally is the builder's logged run, spot-checked
  here (log hash, the rtl failure line, the final
  enablements line) plus seven suites re-run
  independently, all passing with the claimed counts.
- N-3 (run-dependent figure): the builder's
  test-mining run recorded the segwit spend mined
  with 2564 sats of fees; the auditor's re-run
  recorded 3782 sats. Fee totals depend on the
  regtest wallet's UTXO set at run time; the material
  observation (spend mined after 2 cycles under
  prefetch, first cycle without) reproduced exactly.
  No claim is affected.
- N-4 (staging scope): the EXP-057 staging run's
  snapshot shows epoch 0 because the tier started
  fresh; the restore-with-epoch-bump path is verified
  by code reading (aggregation.py line 570) and by
  the EXP-055/EXP-057 suites, not by the staging run
  itself. The report does not claim otherwise.

## Defects

None.

## Bottom line

The enablements workstream is CLEARED FOR PUSH. The
section 7 flip is CLEARED FOR EXECUTION after the
push, as written. EXP-051 is enabled, EXP-057 is
deployed in staging configuration, EXP-052 and
EXP-050 are armed and proven up to the switch,
EXP-058 is correctly not enabled with the reason on
record, and the EXP-047 documentation is done. No
claim in the builder's report was found overstated.
