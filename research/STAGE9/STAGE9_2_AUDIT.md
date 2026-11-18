# Stage 9.2 Independent Audit

Stage audited: 9.2 (production promotion decisions and
outstanding defect resolution).
Auditor: independent, not the builder.
Date: 2026-11-18.
File under audit: research/STAGE9/PRODUCTION_PROMOTION_DECISIONS.md,
built from research/STAGE9/EXPERIMENT_CLOSURE_LEDGER.json as
corrected after the Stage 9.1 audit.
Method: full table recount against the ledger, systematic
disposition to class consistency check, grep tracing across
mining/, agent/ and gpu/, line level re-reads of the flagged
seams, sha256 recomputation of all 21 baseline hashes in
REPOSITORY_BASELINE.md section 7, live config reads
(read-only), and report spot checks for EXP-057 and EXP-058.
No file under audit was modified. The live miner, autopilot,
node, wallet and endpoint configuration were not modified.
Nothing was pushed.

## Verdict: PASS WITH NOTES

Two minor documentation defects in the tracing narrative
(Defects 1 and 2 below). Neither changes a promotion count,
a class assignment, a flagged finding, or any production
behaviour. All builder claims in the audit brief were
verified, with those two qualifications.

## 1. Claim 1, table completeness and counts: VERIFIED

- The section 4 decision table contains exactly 109 rows,
  109 unique ids, set equal to the 109 ledger records (no
  missing, no extra, no duplicates). Note on method: the
  section 6 registry repair proposal table repeats five ids
  (R-23, R-27, R-32, R-33, R-35) with their current registry
  status NEW; those are proposal rows, not decision rows,
  and were excluded from the count.
- Promotion class counts recomputed from section 4 only:
  ADD TO PRODUCTION 28, KEEP AS RESEARCH 41,
  KEEP DISABLED / EXPERIMENTAL 18, DO NOT ADD 15, DEFER 7.
  Total 109. Matches the builder's section 2 table exactly.
- Systematic consistency check over all 109 rows, not only
  a sample: every row's ledger disposition column equals
  the ledger disposition; all 15 REJECTED records are
  DO NOT ADD; all 7 DEFERRED records are DEFER; the single
  INCONCLUSIVE record (EXP-056) is KEEP AS RESEARCH, not
  DO NOT ADD; no REJECTED record is ADD TO PRODUCTION.
- Sample of 12 rows hand checked against the ledger and
  source: EXP-022 (INTEGRATED, ADD, batch scope stated),
  EXP-026 (INTEGRATED, ADD, live v512dual tier), EXP-056
  (INCONCLUSIVE, KEEP AS RESEARCH), EXP-053 (REJECTED,
  DO NOT ADD), EXP-052 (UNDER_INVESTIGATION, KEEP DISABLED),
  EXP-050 (PROVEN_NOT_INTEGRATED, KEEP DISABLED), EXP-055
  (PROVEN_NOT_INTEGRATED, KEEP DISABLED), EXP-001
  (REJECTED, DO NOT ADD), R-26 (INTEGRATED, KEEP DISABLED,
  the F-1 default-off case), R-23 (UNDER_INVESTIGATION,
  KEEP DISABLED), R-32 (EXPERIMENTAL, KEEP DISABLED),
  R-21 (DEFERRED, DEFER). All consistent. The two
  INTEGRATED records not promoted to ADD are R-12 and
  R-26, both correctly held at KEEP DISABLED / EXPERIMENTAL
  because their switches are default off.

## 2. Claim 2, central tracing claim: VERIFIED WITH NOTES

- mining/mainnet_live.py never imports mining.engine: the
  only engine import is "from gpu import engine as
  gpu_engine" (line 36). Verified by grep.
- mining/solo_server.py imports from mining.engine only at
  two deferred sites: line 536 and line 574. See Defect 2
  for the name count.
- MiningEngine production constructors: agent/autonomous.py
  line 48 and mining/testnet4_attempt.py line 69 verified.
  See Defect 1 for one omitted constructor.

## 3. Claim 3, flagged records: VERIFIED

- F-1 (R-26 / EXP-050): mining/mainnet_live.py lines 204 to
  218 construct EndpointHealthPolicy only when
  pool_health_config reports enabled; the shipped default
  is enabled False; mining/stratum_client.py initialises
  endpoint_policy to None (line 212) and its policy hooks
  guard on None (for example _maybe_failback at line 451
  area, _policy_note_success at line 429). The live config
  .local/mining-endpoint.json has exactly the keys mode,
  pool, solo, payout_address: no pool_health section. The
  policy object is therefore None at runtime under the
  default and live config. Claim stands.
- F-3 (EXP-052): the seam is at mining/mainnet_live.py
  lines 253 to 265 exactly as stated: resolve_requested is
  imported and called only under bakeoff_cfg["enabled"];
  BAKEOFF_DEFAULTS ships enabled False; the live config
  has no bakeoff section (keys above); no file exists at
  .local/bakeoff-dispatch.json. Claim stands.
- F-5 (EXP-022): gpu/engine.py line 996 calls
  _try_v512flags at construction; the flags entry
  (_vf_batch_flagged) is routed only inside batch_search
  (lines 2429 to 2442, AVX-512 backends only, with fallback
  to the materialised batch). search_first (line 1846) is
  a thin wrapper over search_first_counted and contains no
  flags routing; mining/mainnet_live.py line 324 calls
  engine.search_first. Batch scope only. Claim stands.
- F-7 (R-13): grep over mining/, agent/ and gpu/ shows no
  live import of mining/coordinator.py (only comments in
  stratum_client.py, engine.py, mining_statistics.py and
  work_checkpoint.py mention a coordinator in prose). The
  live re-verification is candidate_verify.verify_candidate,
  as the decisions file states. Claim stands.

## 4. Claim 4, A4 reconciliation spot checks: VERIFIED

- EXP-057 D-1 fix present in mining/aggregation.py: in
  _AggHandler._run, a successful re-authorize captures
  previous_sid, binds the new session, then closes the
  previous one (comment cites the EXP-057 audit D-1);
  handle() closes the connection's final session in its
  finally block.
- EXP-057 D-2 fix present: operator_submit_pending
  (line 421) peeks at pending_candidates[index] instead of
  popping, re-verifies the stored header through
  verify_candidate, and removes the candidate only after
  the submitter returns; the D-2 comment in source matches
  the decisions file wording.
- EXP-055 mechanisms sampled in mining/coordinator.py:
  _completed_ids and _dead_ids tombstones (lines 266 to
  267), lease_info answering for live and tombstoned ids
  (line 484 area), _check_report (line 497) rejecting
  completed, dead, wrong token and stale epoch reports,
  apply_restart_rule (line 712) bumping the epoch and
  reclaiming outstanding leases, and
  assert_partition_invariant (line 773). The decisions
  file's fencing, lease and recovery description matches
  the source. Its multi-machine limitation statement is
  honest: no live import, loopback and in-process proof
  only.
- EXP-058 proposal is design only: no production file was
  modified in this stage (see Claim 6, all 21 hashes
  match), and section 5.6 labels the canary probe
  "design only, NOT implemented", with its own experiment
  id and predeclaration required before promotion. The
  missed step_up scale-up requirement is preserved, not
  upgraded.

## 5. Claim 5, DEF-9.2-1 and DEF-9.2-2: VERIFIED, minor rating correct

- DEF-9.2-1 is real: in mining/bakeoff_dispatch.py,
  resolve_requested computes
  "fp = fingerprint if fingerprint is not None else
  host_fingerprint()" (lines 566 to 567 in the baseline
  numbering) outside any try block, and the caller in
  mining/mainnet_live.py (lines 253 to 265) has no wrapper.
  The minor rating is correct: host_fingerprint's only file
  read (/proc/cpuinfo) is guarded by "except OSError", and
  the remaining operations (hashlib.sha256, os.cpu_count)
  have no realistic raise path today; the seam is also
  unreachable while the switch is off. It is a contract
  hardening item before enablement, exactly as rated.
- DEF-9.2-2 is real: mining/engine.py line 26 is the
  unconditional top level import
  "from mining.prefetch import PrefetchFeed, PrefetchQueue",
  while construction is behind use_prefetch (default
  False). Minor and cosmetic today, as rated: a broken
  prefetch module would break MiningEngine import for
  callers that never enable it.

## 6. Claim 6 and Claim 7, registry proposal and no production change: VERIFIED

- Authoritative registry
  research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json:
  R-23, R-27, R-32, R-33 and R-35 all currently carry
  status NEW. Verified directly.
- The proposal does not overclaim: R-32 proposed
  EXPERIMENTAL matches the EXP-058 report classification
  (PROMISING HYPOTHESIS, registry status EXPERIMENTAL,
  step_up leg negative). R-27 proposed PROVEN matches the
  EXP-057 report classification (PROVEN, protocol level),
  and the decisions file still classes both EXP-057 and
  R-27 as KEEP DISABLED / EXPERIMENTAL, not ADD TO
  PRODUCTION. R-23 proposed UNDER_INVESTIGATION, R-33 and
  R-35 proposed PROVEN are consistent with their ledger
  dispositions (EXP-052 UNDER_INVESTIGATION, EXP-051 and
  EXP-049 PROVEN_NOT_INTEGRATED).
- No production code was modified: sha256 recomputed for
  all 21 files in REPOSITORY_BASELINE.md section 7; all
  21 match the baseline table exactly, including
  mining/pid_control.py, mining/coordinator.py,
  mining/aggregation.py, mining/bakeoff_dispatch.py,
  mining/engine.py and gpu/engine.py.
- Long dash scan: byte scan for U+2014 over
  PRODUCTION_PROMOTION_DECISIONS.md found zero
  occurrences. This audit file was scanned after writing
  and also contains zero.

## Defects

### Defect 1 (minor, tracing completeness): one MiningEngine constructor omitted

File: research/STAGE9/PRODUCTION_PROMOTION_DECISIONS.md,
section 1.
Evidence: the file states MiningEngine's "only production
constructors in the tree are agent/autonomous.py (line 48)
and mining/testnet4_attempt.py (line 69)". A third
non-test constructor exists: mining/cpu/miner.py line 133
constructs MiningEngine inside its miner class. That module
is not imported by any live entry point (grep over mining/,
agent/ and gpu/ finds it mentioned only in a gpu/engine.py
comment), so the live path conclusion is unchanged, but
the word "only" is inaccurate as written.
Correction needed: amend section 1 to name mining/cpu/
miner.py as a third, non-live constructor, or qualify the
sentence to live and agent paths. No class or count
changes.

### Defect 2 (minor, tracing accuracy): solo_server imports three names, not two helpers

File: research/STAGE9/PRODUCTION_PROMOTION_DECISIONS.md,
section 1 and the EXP-034 row.
Evidence: the file states mining/solo_server.py imports
two helpers from mining.engine (build_coinbase,
strip_witness). In source, line 536 imports
address_script_pubkey and build_coinbase together, and
line 574 imports strip_witness: three names at two import
sites. The substantive claim (only deferred helper imports,
no MiningEngine use) is correct.
Correction needed: amend the wording to "three helpers
(address_script_pubkey, build_coinbase, strip_witness) at
two deferred import sites". No class or count changes.

## Notes (not defects)

- N-1: The F-6 family scope statements (GBT and agent path,
  not the live pool path) are consistent with the tracing
  in section 2 of this audit and with the Stage 9.1 audit.
- N-2: The decisions file does not upgrade any UNVERIFIED
  item: EXP-052 cross-host rotations, EXP-055 and EXP-057
  multi-machine behaviour, EXP-058 live actuation, and the
  three open NOVA-ER-0006 items are all carried open with
  owners named. The success criterion (a verified accepted
  mainnet block) remains unmet and is stated as such; pool
  shares are never presented as blocks. The 500 GH/s and
  140 TH/s objectives stand unmet and unconcealed.
- N-3: DEF-9.2-3, DEF-9.2-4 and DEF-9.2-5 are carried
  research and observability items, not production
  defects; their ratings and fix-before-reuse conditions
  are reasonable on the evidence checked.
