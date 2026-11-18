# Stage 9 Fixes Batch: Independent Audit

Date: 2026-11-18. Auditor: independent (not the builder or the
finisher). Scope: exactly the Stage 9 fixes batch approved by
the owner on 2026-11-18 (DEF-9.2-1, DEF-9.2-2, the section 6
registry repair with the enablement annotation, D-04, D-93-2,
D-93-3, and the two dated documentation sections). Baseline
remote HEAD d6b7db82e5164a348ad3adaf491b46365529d303; pre-batch
hashes are the Stage 9.1 baseline and post-9.4 values. Nothing
was pushed by this audit and no audited file was modified.

## Verdict: PASS WITH NOTES (no defects)

Every claimed change is present, confined to its claimed
scope, and verified by re-run tests. The batch is cleared for
push. The DEF-9.2-1 prerequisite for EXP-052 live enablement
is cleared (section 2).

## 1. File hashes

All nine changed files match the claimed after-values exactly:

- mining/bakeoff_dispatch.py e218e70a0d57e0c3213907fd393b753b1b1755f4ae97a36c02edbdfc9555c0b0
- mining/engine.py 11f288ce9387deb5d56c9810f2755927ce247d30c5ea960e4053e9d909fa07da
- research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json c333c8ef59c81a4b18ddad84674429eca7d84cd3ed27e039af8cddb07cb85f24
- agent/intelligence/integration_registry.json 1b64dcacd0b24e5a4aa35c91671cb2ee5c279beb726b8d514ebc635e5fe7709a (claimed byte-identical; confirmed)
- research/phase001/MATHEMATICAL_OPTIMIZATION_HYPOTHESES.md dbd49b826419b15c014d10ea19deea09fd2997975f885684282e9bcd3548516c
- tests/test_task0039_accounting.py caf84a4cd47d172e1a086045afc915bab805618e246d5b212520402401f21e51
- tests/test_exp052_bakeoff_dispatch.py ce916df46e63bff4a6efcd80e1447e5df29318e3a3200892dd527500469a3d4d
- research/STAGE9/CURRENT_HEAD_TEST_AUDIT.md 10f0dcbcb982023989c4c1d46f401028bd0f5046cded4941541920d2df8c6747
- research/STAGE9/PRODUCTION_PROMOTION_DECISIONS.md e0fd22d7a6f93b2b3ebace67ac16187604672be931337564522f04c7169de266

No drift in the spot-checked untouched production files; all
equal their Stage 9.1 baseline values: mining/mainnet_live.py
c8071ce1, mining/autopilot.py 3cfafc20, mining/coordinator.py
b4215980, gpu/engine.py bfe605cb, mining/aggregation.py
1951a657, mining/pid_control.py cfdcdd84,
mining/endpoint_config.py c0801074, mining/incident_codes.py
5382f95e.

## 2. DEF-9.2-1 (bakeoff guard)

Read in full at resolve_requested in mining/bakeoff_dispatch.py.
When no fingerprint argument is supplied, the host_fingerprint()
call is wrapped in try/except; any exception returns
("auto", "doubt: host fingerprint unavailable (<exc>); static
order"), the documented fail-closed shape, with a dated
DEF-9.2-1 comment. The guard wraps only the fingerprint call:
the downstream read_cache call and the measured-winner return
are outside it and unchanged, so the guard cannot swallow a
legitimate measured-winner path. A winner is reachable only
through a successful read_cache, exactly as before.

Regression check 35 in tests/test_exp052_bakeoff_dispatch.py
monkeypatches bd.host_fingerprint to raise RuntimeError, calls
resolve_requested with no fingerprint argument (the guarded
path), and asserts requested == "auto" and a reason starting
with "doubt:". Re-run output confirms it verbatim: "ok 35:
DEF-9.2-1: raising host_fingerprint resolves to the doubt
verdict, never raises (doubt: host fingerprint unavailable
(cpuinfo vanished); static order)".

DEF-9.2-1 is therefore fixed and regression-tested. The
prerequisite this defect placed in front of EXP-052 live
enablement is cleared.

## 3. DEF-9.2-2 (engine prefetch import)

mining/engine.py has no top-level prefetch import. PrefetchQueue
is imported inside the use_prefetch branch of __init__ and
PrefetchFeed inside _prefetch_note_current, each with a dated
DEF-9.2-2 comment. Independently reproduced: with
mining.prefetch hard-blocked by an import hook that raises
ImportError, mining.engine imports cleanly, MiningEngine and
StatusPublisher are present, and mining.prefetch is never
loaded into sys.modules.

Confinement: script_num_push was read in full and is the 9.3
BIP34 fix exactly as the 9.3 audit describes it (0 is OP_0, -1
is OP_1NEGATE, 1 to 16 are the single opcodes OP_1 to OP_16,
with the bad-cb-height history in the docstring). The
StatusPublisher class is intact with its 9.4 docstring and the
opt-in constructor parameters (status_publish=False,
status_interval_s=10.0, status_sink=None). It sits at line 491
against the 9.4 audit's line 492; the one-line shift is exactly
the removed top-level import line, which is itself evidence
the change is confined to the import and its two use sites
(see note N-3).

## 4. Registry repair

Parsed research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json
directly: 109 entries. Status comparison against the
registry_status recorded per entry in the Stage 9.1 closure
ledger gives exactly five differences, all claimed, all from
NEW: R-23 to UNDER_INVESTIGATION, R-27 to PROVEN, R-32 to
EXPERIMENTAL, R-33 to PROVEN, R-35 to PROVEN. No other entry's
status changed.

The enablement field is present on exactly 10 rows with exactly
the claimed strings: R-26 "default-off"; R-12 "default-off,
path-scoped (solo)"; EXP-022 "path-scoped (batch)"; EXP-025,
EXP-034, EXP-038, PHASE001-H-1, PHASE001-H-5, R-08, R-10
"path-scoped (GBT and agent path)". These strings match the
dated "Registry repair applied (2026-11-18)" section appended
to PRODUCTION_PROMOTION_DECISIONS.md, which also records the
encoding, the post-repair registry sha256 (matches the file),
and the validation results.

Text repairs: D-02, the registry basis framing now names HEAD
d6b7db82 with a dated framing note, and R-23's open question is
rewritten to point at the EXP-052 report and its outstanding
rotations and enablement decision. D-03, the EXP-030 entry's
reservation wording is replaced with a resolved note
referencing the EXP-030-PHASE-A to H records. D-06, the R-30
entry's stale restart sentence is replaced with a resolved
note stating the restart has happened and live heartbeats
carry incident_counts.

Derived registry: sha256 1b64dcac as claimed; its generator
drops the enablement field (no derived entry carries one), and
its 30 INTEGRATED ids equal the Stage 9.1 ledger's INTEGRATED
disposition set exactly.

## 5. D-04 (Phase 001 table)

research/phase001/MATHEMATICAL_OPTIMIZATION_HYPOTHESES.md line
81: H-8 reads "Closed, REJECTED (EXP-041)". Line 82: H-9 reads
"PROVEN (EXP-024b); superseded by EXP-026 as the integration
candidate; not integrated". Both exact.

## 6. D-93-2 (test-task0039)

test_early_exit_accounting in tests/test_task0039_accounting.py
now constructs ComputeEngine(requested="c", threads=1). The
promptness bound is not loosened: the assertion remains
attempted < 100000 // 10, that is below 10,000, and every
exact-accounting identity (backend_hashes == attempted,
unique_coverage == attempted, device_hashes == 0,
verification_hashes == 1, candidate_count == 1, the exact
30,000-count miss) is still asserted. The in-test comment
records that the audits offered two options (a quiet-host run
or a thread bound) with no recommendation between them, and
that the thread bound is the least-invasive choice under the
owner's batch approval. The dated "Fixes batch resolutions
(2026-11-18)" section in CURRENT_HEAD_TEST_AUDIT.md carries the
same disclosure. Re-run on this host under live-miner
contention: PASS, including the fresh regtest block.

## 7. D-93-3 (test-exp052 Gate 5a)

Gate 5a now compares the campaign cache fingerprint against
the live fingerprint field by field (cpu_model, flags_hash,
logical_cpus). On a proven mismatch it asserts requested ==
"auto", a reason starting with "doubt:", and the words
"fingerprint mismatch" in the reason; a resolver returning a
measured winner on a foreign cache would fail that assertion.
The matching-fingerprint branch is unchanged (STATIC or winner
assertions as before). On this host the mismatch branch is the
one that executes: re-run check 44 passes through it, with
cache flags_hash 51d3e983ddf6ac93 vs live c86584c209897fb5, the
same pair the 9.3 audit recorded.

## 8. Tests re-run by this audit (sequentially)

- validate_ledger.py: VALID (jsonschema, draft 2020-12), 109 entries.
- test-exp052 (make test-exp052, run twice): PASS, 46 checks,
  including check 35 (DEF-9.2-1) and check 44 (Gate 5a mismatch
  branch).
- test-task0039 (make test-task0039): PASS under live
  contention, all checks including the regtest block.
- test-agent-intelligence (make test-agent-intelligence):
  PASS, 106 checks.
- Spot re-runs beyond the mandated set, all PASS:
  test-exp051 (prefetch suite, the DEF-9.2-2 neighbour),
  test-engine, test-status-publisher, test-template-cache.
- Makefile test-all still lists 52 prerequisites (counted).

Claimed but not independently re-run by this audit:
test-mining and test-mainnet-live (see note N-1).

## 9. Hygiene and live state

U+2014 count is zero in all nine changed files and in this
audit. No .local/bakeoff-dispatch.json exists; no live state
was planted. The endpoint config is unchanged (sha256
d741cde3c6224406f46f3bae138fb174eb1d780725bcb94baff4e14a8670c7d3),
mode pool, with no bakeoff section, so the dispatch switch
remains disabled in the live configuration. The live miner was
running at both audit reads (heartbeat 2026-11-18T10:06:47Z
and 10:11:59Z), restarts 0, shares_accepted_total 1129,
non-decreasing against the 1,086 recorded at Stage 9 closure.

## Notes

- N-1 (verification scope): test-mining and test-mainnet-live
  were claimed PASS by the builders and were not independently
  re-run here; the mandated re-run set plus the four
  engine-adjacent suites all pass. UNVERIFIED by this audit,
  builder-claimed only.
- N-2 (encoding choice, disclosed): section 6 of the 9.2
  decisions originally proposed the enablement annotation as a
  field with three separate values; the batch encodes it as a
  single composite string, a parent-chosen encoding disclosed
  in the claim and in the appended registry-repair section.
  The value and scope assignments match section 6 exactly. Not
  a defect.
- N-3 (confinement evidence): the pre-batch engine.py is not
  on disk (no .git in the local checkout), so confinement of
  the DEF-9.2-2 change rests on content inspection (the BIP34
  and StatusPublisher regions match their audit descriptions,
  and the one-line StatusPublisher shift is exactly the removed
  import), the blocked-import reproduction, and the passing
  engine suites. That combination is sufficient; a byte-level
  diff against the pre-batch file is UNVERIFIED because the
  file is unavailable.

## Clearance

The batch is cleared for push as one scoped change. The
DEF-9.2-1 prerequisite for EXP-052 live enablement is cleared:
the resolver can no longer raise out of the fingerprint path,
and the regression check proving it is in the suite. Live
enablement itself remains an operator act on the live
configuration, which this batch correctly did not touch.
