# Stage 9.1 Independent Audit

Stage audited: 9.1 (repository and experiment closure).
Auditor: independent, not the builder.
Date: 2026-11-18.
Files under audit: research/STAGE9/REPOSITORY_BASELINE.md,
research/STAGE9/EXPERIMENT_CLOSURE_LEDGER.json,
research/STAGE9/EXPERIMENT_CLOSURE_LEDGER.schema.json,
research/STAGE9/validate_ledger.py,
research/STAGE9/EXPERIMENT_CLOSURE_REPORT.md.
Method: direct source inspection, re-run of the ledger
validator, set comparisons against both registries, sha256
recomputation, import scans, live config and heartbeat reads
(read-only), and read-only GitHub API calls (refs, commits,
recursive tree). No file under audit was modified. The live
miner, autopilot, node, wallet and endpoint configuration
were not modified. Nothing was pushed.

## Verdict: PASS WITH NOTES

Two minor defects, both documentation consistency defects
inside ledger record wording. Neither changes a disposition
count, a verdict, or any production behaviour. Corrections
are specified below; per the audit brief they are not made
by the auditor.

## 1. Claim 1, remote HEAD and churn commits: VERIFIED

Read-only GitHub API at audit time:

- HEAD: 883cf281be6c41617f27b8b44d1aa27e3c94df29. Matches.
- HEAD parent: eca3a641311a98b3ed58065ad5f2ee23523475c5.
  Matches.
- HEAD commit date 2026-11-18T02:36:38Z, message naming
  research/sha256d/exp057/RAW_RESULTS/gate6_20261117T161245Z.json.
  Matches the baseline.
- Recursive tree at HEAD: 1,366 blobs, truncated flag false.
  Matches.
- The deliberate HEAD 11277e6f532a48844be5c9f33aa8ef6a755683c2
  sits at index 18 in the commit list from HEAD, that is,
  exactly 18 commits behind. Matches.
- Sampled 6 of the 18 intervening commits in detail
  (positions 0, 3, 6, 9, 12, 17): each touches exactly one
  file, and every file is a runtime churn path
  (exp057 gate6 JSON, exp057 gate5_snapshot.json, exp055
  gate6_state candidate_journal.jsonl, two exp055 gate6
  JSONs, evidence/mainnet-live.jsonl). The commit messages
  of all 18 were also listed: 13 exp055 RAW_RESULTS, 4
  exp057 RAW_RESULTS, 1 evidence/mainnet-live.jsonl, the
  exact split the baseline records. No production source
  file changed in any of the 18. Claim stands.

## 2. Claim 2, ledger integrity: VERIFIED

- validate_ledger.py re-run by the auditor: output
  "VALID (jsonschema, draft 2020-12): 109 entries",
  exit 0.
- Ledger ids compared set-wise against the authoritative
  registry research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json
  (109 entries): no missing, no extra, no duplicates.
- Every record carries exactly one disposition from the
  allowed 7 (schema enum, string value; validator enforces
  it, and the auditor recomputed the counts independently).
- Computed counts: INTEGRATED 30, PROVEN_NOT_INTEGRATED 44,
  REJECTED 15, EXPERIMENTAL 8, UNDER_INVESTIGATION 4,
  DEFERRED 7, INCONCLUSIVE 1. The ledger's own
  disposition_counts field matches the computed counts
  exactly. Claim stands.

## 3. Claim 3, integration truth against source: VERIFIED, with defects A and B noted

- The ledger INTEGRATED set equals the derived registry
  agent/intelligence/integration_registry.json set exactly
  (30 ids, set equality both directions, checked by the
  auditor).
- INTEGRATED sampled against current source (10 records,
  above the 8 required): EXP-022 (gpu/engine.py
  _try_v512flags at line 1664, _vf_batch_flagged at 1780),
  EXP-025 (mining/engine.py TemplateFamily, PreparedTemplate,
  template_identity, TemplateCache), EXP-026 (v512dual tier
  in gpu/engine.py), EXP-034 (extranonce_space in
  mining/engine.py, solo_server wiring), EXP-036
  (verify_candidate called in mining/mainnet_live.py line
  349 and three sites in mining/solo_server.py), EXP-037
  (FrontierAccountant in mining/mining_statistics.py, used
  by mining/mainnet_live.py; EvidenceCounter in
  mining/autopilot.py), EXP-038 (WorkCheckpoint imported
  and used in mining/engine.py), EXP-039 (_try_shani line
  1076, _try_avx2 line 1245 in gpu/engine.py), R-12
  (VarDiffController in mining/solo_server.py), R-30
  (incident_codes guard import and log_incident sites in
  mining/autopilot.py). All present on the production call
  path as recorded.
- Non-INTEGRATED sampled (EXP-052, EXP-055, EXP-057,
  EXP-058, plus EXP-053, EXP-054, EXP-049): a direct import
  scan shows mining/coordinator.py, mining/aggregation.py
  and mining/pid_control.py are imported only by their test
  suites and their research campaign drivers. No live entry
  point (mining/autopilot.py, mining/mainnet_live.py,
  mining/engine.py, mining/solo_server.py, gpu/engine.py,
  agent code) imports any of them. mining/bench_mode.py
  (EXP-049) is likewise imported by no live module.
- EXP-052 wiring: mining/mainnet_live.py lines 253 to 265
  call mining.bakeoff_dispatch.resolve_requested only
  under bakeoff_cfg["enabled"]; BAKEOFF_DEFAULTS in
  mining/endpoint_config.py ships enabled False. EXP-050
  wiring: EndpointHealthPolicy is imported at
  mining/mainnet_live.py line 208 only when pool mode and
  the pool_health enabled flag are both true (shipped
  default enabled False).
- Live endpoint config .local/mining-endpoint.json has
  exactly the keys mode, pool, solo, payout_address: no
  bakeoff section. No file exists at
  .local/bakeoff-dispatch.json. Claim stands.

## 4. Claim 4, baseline sha256 table: VERIFIED

The auditor recomputed sha256 for all 21 files in the
baseline table (the brief required at least 8). All 21
match the tabled values exactly, including
mining/mainnet_live.py, mining/autopilot.py,
mining/bakeoff_dispatch.py, mining/coordinator.py,
mining/aggregation.py, mining/pid_control.py,
mining/incident_codes.py and gpu/engine.py.

## 5. Claim 5, A4 reconciliations: VERIFIED

- EXP-057 D-1 fix present: mining/aggregation.py lines
  655 to 664 capture the previous session id on
  re-authorize, bind the new session, then close the
  previous one; connection teardown closes the final
  session (line 623 area).
- EXP-057 D-2 fix present: operator_submit_pending (line
  421) peeks instead of popping, re-verifies the stored
  header through verify_candidate before submitting, and
  deletes the candidate by identity only after the
  submitter returns; failures leave it queued. The D-2
  comment in source matches the closure report wording.
- EXP-052 audit fixes present: validate_cache cross-checks
  the winner against its own tier row (eligible must be
  true and resolved_backend must equal the denoted backend),
  and resolve_requested guards wrong-typed arguments
  (config, max_age_s, margin coercions all return the
  "auto" doubt verdict instead of raising).
- EXP-056: ledger disposition INCONCLUSIVE, registry
  status UNDER_INVESTIGATION preserved. Not REJECTED.
  Correct per the brief: a solver budget result is not a
  proof of impossibility.
- EXP-053 and EXP-054 negatives preserved: both ledger
  REJECTED; EXP-053 pooled adjusted log ratio -0.0017
  matches the authoritative registry text; EXP-054 flat
  curve and G = 1 standing, with the G = 8 pooled figure
  -0.1505 in the registry record, match the report.
- NOVA-ER-0006: mining/incident_registry.json holds
  exactly 20 codes (1001 to 1003, 2001 to 2005, 3001 to
  3004, 4001 to 4003, 5001 to 5005). mining/autopilot.py
  emits through log_incident at sites for 1001, 1002,
  1003, 2001, 2002, 2003, 2004 and 3001 to 3004, and the
  heartbeat publishes incident_counts. Live heartbeat read
  during this audit (2026-11-18T02:48Z) carries
  incident_counts {1003: 1, 2001: 1} with 1,040 shares
  accepted, consistent with the baseline context. Emission
  claim is plausible from source and confirmed live.

## 6. Claim 6, discrepancy list spot checks: VERIFIED

- D-01 accurate: the authoritative registry has exactly
  10 NEW rows (R-23, R-24, R-25, R-27, R-29, R-31, R-32,
  R-33, R-34, R-35). The five the report names as executed
  (R-23, R-27, R-32, R-33, R-35) are all NEW in the
  registry, and their ledger dispositions match their
  covering experiments (R-23 UNDER_INVESTIGATION as
  EXP-052, R-27 PROVEN_NOT_INTEGRATED as EXP-057, R-32
  EXPERIMENTAL as EXP-058, R-33 PROVEN_NOT_INTEGRATED as
  EXP-051, R-35 PROVEN_NOT_INTEGRATED as EXP-049). The
  other five NEW rows are DEFERRED in the ledger.
- D-05 accurate: EXP-032 records AVX2 batch pooled 1.409x
  CI [1.340, 1.480]; EXP-039 records 1.252x CI [1.185,
  1.322]; the intervals do not overlap, both registry
  entries themselves record the conflict as unresolved,
  and the ledger carries it in known_limitations on both
  records.
- D-10 accurate: there is no .github directory and no CI
  configuration anywhere in the tree outside .local (the
  auditor searched for workflow and CI files; the only
  hits are unrelated names containing the letters ci).
  The baseline statement that CI status is "none exists"
  is correct.

## 7. Claim 7, long dash scan: VERIFIED

Byte scan for U+2014 over all five Stage 9.1 files under
audit: zero occurrences in each. This audit file was
scanned after writing and also contains zero.

## Defects

### Defect 1 (minor, ledger record accuracy): EXP-050 record contradicts the source and the report's own D-07

File: research/STAGE9/EXPERIMENT_CLOSURE_LEDGER.json,
record EXP-050.
Evidence: the record gives disposition
PROVEN_NOT_INTEGRATED, affects_production_path false, and
a disposition_basis stating the result "is not invoked by
the production call path (checked against current source
imports)". That is not what the source shows:
mining/mainnet_live.py imports EndpointHealthPolicy from
mining/endpoint_health.py (line 208) and constructs it
whenever pool mode and the default-off enabled flag are
set, and mining/stratum_client.py carries the policy
hooks. It is the same implementation whose register row
R-26 the ledger records as INTEGRATED with
affects_production_path true, and the closure report's
own discrepancy D-07 describes "R-26 and EXP-050's
policy" together as "integrated as code but disabled or
opt-in by default". One implementation cannot be both
invoked and not invoked by the same call path.
Correction needed: amend the EXP-050 record so its basis
and affects_production_path describe the conditional
default-off wiring (integrated code, unchanged live
behaviour), or state explicitly that the disposition
follows the authoritative registry PROVEN status while
the code presence is as R-26 records. The disposition
itself may stand under the builder's declared mapping
rule; the non-invocation claim may not. No count changes.

### Defect 2 (minor, ledger record accuracy): EXP-051 record overstates non-invocation the same way

File: research/STAGE9/EXPERIMENT_CLOSURE_LEDGER.json,
record EXP-051.
Evidence: the record gives PROVEN_NOT_INTEGRATED,
affects_production_path false, with the same
"not invoked by the production call path" basis. In
source, mining/engine.py imports PrefetchFeed and
PrefetchQueue from mining/prefetch.py unconditionally
(line 26) and MiningEngine constructs and serves the
prefetch queue behind use_prefetch, default False (lines
544 to 567 and the serve path). The closure report D-07
again describes the prefetch hook as integrated code,
opt-in. The module is loaded on the production path;
only its effect is off by default.
Correction needed: same shape as Defect 1: describe the
hook as wired but opt-in-off in the record basis and
affects flag, or tie the wording explicitly to the
registry-status mapping rule. No count changes.

## Notes (not defects)

- N-1: The baseline's node state figures (height about
  470,267 of 976,342) are labelled context and were not
  re-derived in this audit; the node RPC was not queried.
  Nothing in Stage 9.1 depends on them.
- N-2: The Makefile figures in the baseline were spot
  checked: the test-all line carries 51 prerequisites,
  consistent with the baseline's count.
- N-3: Stage 9.1 ran no tests and no benchmarks, and says
  so. Current-HEAD test status remains Stage 9.3's
  deliverable, exactly as the closure report states. The
  success criterion (a verified accepted mainnet block)
  remains unmet and is not upgraded anywhere in the
  audited files; pool shares are never presented as
  blocks. The 500 GH/s and 140 TH/s objectives stand
  unmet and unconcealed.
