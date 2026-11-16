# Stage 6, item 2: independent audit of the solo vardiff production integration

Auditor: independent agent, not the integration author.
Date: 2026-11-16. Host: AMD EPYC 9D25 (hostname htch-runtime).
Scope: the integration of the solo vardiff prototype
(research/vardiff/, register R-12, NOVA-ER-0004) into
production mining/solo_server.py, mining/endpoint_config.py
and mining/solo_mainnet.py, the closure of discrepancy D10
in the same change, the new suite tests/test_solo_vardiff.py
with fixture tests/fixtures/solo_server_pre_integration.py,
and Entry 5 of research/sha256d/phase6b/
PRODUCTION_INTEGRATION_LOG.md.

## Verdict: PASS WITH NOTES

Defects: 0 in production code, 0 in the test suite.
Notes: 5 (N-1 to N-5 below). One note (N-1) is a registry
inconsistency that should be corrected in the push set; it
does not touch production behaviour.

Live stack: not restarted, not signalled. Autopilot pid
2740 and miner pid 2743 throughout, restarts 0. Shares
accepted (autopilot status): 518 before the audit runs,
521 after. Rejected count was not printed by the status
command used; the accepted count and pid continuity are
the disturbance evidence.

## 1. The five integration steps, checked against DESIGN.md section 9

Step 1 (port VarDiffController into mining/solo_server.py
as an optional component; SoloServer gains vardiff=None;
None is the rollback surface). CONFIRMED by code read.
VarDiffController lives at mining/solo_server.py lines 137
to 254 with constructor defaults identical to the
prototype's declared operating point (target_interval 15.0,
floor 0.002, ceiling 1.0, initial 0.02, ema_alpha 0.35,
deadband 1.25, up_hysteresis_s 30.0, up_confirmations 2,
max_up_factor 1.5, max_down_factor 2.0, decay_after_s 60.0,
decay_factor 2.0; compared line by line against
research/vardiff/vardiff.py lines 77 to 82). SoloServer
__init__ takes vardiff=None; passing both a controller and
an explicit share_difficulty raises ValueError;
submit_share dispatches to _submit_share_fixed when
vardiff is None and to _submit_share_vardiff otherwise.

Step 2 (per-connection state, snapshots, job history,
stale and duplicate accounting into the server;
parameterise SoloTCPServer's handler class; the handler
deltas land in production). CONFIRMED by code read.
SoloServer carries connections (keyed by extranonce1
bytes), job_history bounded by job_history_size=8,
adjustment_log, shares_stale, shares_duplicate and
stale_records alongside the workers table.
refresh_job retains the superseded job and snapshots
each live connection's current difficulty against the new
job_id in _vardiff_on_refresh; snapshots for evicted jobs
are pruned. SoloTCPServer __init__ takes
handler_class=_Handler. The production _Handler carries
the deltas: register_connection at connect and
unregister_connection at disconnect, the connection's own
difficulty in the subscribe set_difficulty message, a
pending_notice set_difficulty after a submit that changed
the difficulty, and a per-client set_difficulty ahead of
each broadcast notify (broadcast sends it only when
vardiff is active). Registration, pending_notice and
broadcast are all inert when vardiff is None (early return
or the fixed share_difficulty is served, the same value
the pre-integration handler sent).

Step 3 (close D10: endpoint config is the single source
of the initial difficulty; the divergent constructor
default is removed). CONFIRMED; see section 3 below.

Step 4 (configuration through mining/endpoint_config.py:
target interval, floor, ceiling, hysteresis, decay,
alongside SOLO_SHARE_DIFFICULTY as the initial value).
CONFIRMED by code read. endpoint_config.py carries
SOLO_VARDIFF_TARGET_INTERVAL, FLOOR, CEILING, EMA_ALPHA,
DEADBAND, UP_HYSTERESIS_S, UP_CONFIRMATIONS, MAX_UP_FACTOR,
MAX_DOWN_FACTOR, DECAY_AFTER_S and DECAY_FACTOR, the
SOLO_VARDIFF_DEFAULTS dict, and solo_vardiff_config() which
merges a config file's solo.vardiff section over those
defaults. mining/solo_mainnet.py builds the controller
from the merged config with initial=share_difficulty when
enabled, and constructs SoloServer exactly as before when
not.

Step 5 (gates before the armed cutover may use it: Gate 2
differential, Gate 3 adversarial, Gate 5 operational,
Gate 6 regtest blocks at adapted difficulties, then an
independent audit; rollback is vardiff=None plus the
endpoint config). CONFIRMED as executed: the suite exists
at tests/test_solo_vardiff.py, is wired into the Makefile
as test-solo-vardiff (test-all is now 38 targets), and
this audit is the independent audit the step requires.
Vardiff remains disabled in the config (section 5 below),
so the cutover cannot use it yet.

## 2. Compatibility gate, independently verified

Fixture authenticity: VERIFIED two ways. (a) Local: the
fixture file is the claimed original plus one prepended
explanatory docstring; stripping that docstring and the
following blank line leaves 27,536 bytes whose sha256 is
518ef05c5c7d49fdf6408e68494fecde24a1c55b337c59576696f77a2a37ab44,
exactly the value the fixture header and Entry 5 claim.
(b) Remote: through ~/workspace/bin/bal_github.py read-only,
the remote tree at HEAD 3ebbaeb216bc1260cfca22c63b9af60d780a971e
lists mining/solo_server.py with git blob sha
a576c82058319e451393e1ab9a7138e36e9d0137, and the git blob
sha of the stripped fixture body is the same value. The
fixture body is byte-identical to the remote
pre-integration file.

Textual identity of the pinned path: validate_share,
notify_params, node_info, check_node and _pow_limit are
byte-identical function bodies between the fixture and
production. _submit_share_fixed is the pristine
submit_share body verbatim except for the rename, an added
docstring, and the extraction of the block-submission
block into the shared _submit_block helper; the extracted
helper contains the same assembly, submitblock,
classify_submit_result, verify_chain_acceptance and
blocks_found operations. note_authorize differs only by a
trailing section comment.

The auditor's own differential (separate script, not the
suite): pristine fixture server and production server,
both at share_difficulty 0.02 on the suite's StubRPC rig,
fed an 18-submission scripted stream (5 valid shares each
submitted twice, 5 low-difficulty shares, an unknown job,
a bad extranonce2 size, an ntime before mintime). Result:
0 decision mismatches (accepted flag, reason string, block
presence and result keys all compared), counters identical
(accepted 10, rejected 8 on both), per-worker counters
identical, blocks_found and candidates_rejected identical.
The default-constructor server (no difficulty argument)
resolved to 0.02 with a share target identical to the
explicit 0.02 server, confirming the D10 path behaviourally.

The suite's own Gate 2 section (C1 to C9) was also read,
not just run: C2 compares (accepted, reason, block
presence) per stream item between pristine and production,
C3 compares the accepted and rejected counters, C4 compares
stats fields. It genuinely compares decisions and counters,
not exit codes.

## 3. D10 closure

CONFIRMED. The SoloServer constructor signature is now
share_difficulty=None; the 0.01 default is gone (the
fixture's pristine signature still carries
share_difficulty=0.01, and suite check F2 pins that the
pre-integration default was 0.01). With no explicit
difficulty and no controller, the value resolves from
endpoint_config.SOLO_SHARE_DIFFICULTY (0.02). The
auditor's repo-wide grep for 0.01 and 0.02 over mining/
and scripts/ found only: the VarDiffController initial
default 0.02 (see N-4), a comment recording the removed
0.01 default, and SOLO_SHARE_DIFFICULTY = 0.02 itself with
its explanatory comment. Production readers take the value
from the config: scripts/solo_cutover.py reads
cfg["solo"]["share_difficulty"] from the merged endpoint
config, mining/mainnet_live.py reads
endpoint_cfg["solo"]["share_difficulty"], and
mining/solo_mainnet.py passes float(solo_cfg
["share_difficulty"]). REPOSITORY_RECONCILIATION.md marks
D10 FIXED 2026-11-16 with the same account (lines 514 to
526 as read). Suite checks F1 to F5 pin the constructor
resolution, the both-arguments refusal, the config merge
and the stats exposure; all passed in the auditor's rerun.

## 4. EXP-036 separation

CONFIRMED by code read and by the suite. In
_submit_share_vardiff, _submit_current and _submit_stale,
verify_candidate is called with the job's network judging
inputs unchanged: the reconstructed header and
self._pow_limit(); the only vardiff-dependent input is
share_target, which feeds meets_share_target only. Block
candidacy in all three paths is v["meets_network_target"],
and block submission goes through the same _submit_block
helper as the fixed path, with chain confirmation as the
acceptance rule. A stale share that meets the network
target is submitted through that pipeline and is counted
in the stale category, never as an accepted share; its
record carries stale=True. Suite checks E6 (verify_candidate
network verdict identical across share targets 0.002,
0.02, 0.5, 1.0 and None, on a fixed header) and E7 (two
connections with different snapshot difficulties on the
same job split share and below_target classifications
exactly as their snapshots dictate, with zero submissions
reaching the stub node) are real checks with real
assertions, and both passed in the auditor's rerun.

## 5. Safety defaults and rollback surface

CONFIRMED. SOLO_VARDIFF_DEFAULTS has "enabled": False, and
DEFAULT_CONFIG embeds it, so any config load without an
explicit vardiff section yields disabled. The live
.local/mining-endpoint.json on disk carries no vardiff
section at all and mode "pool"; solo_vardiff_config on it
therefore returns enabled False. mining/solo_mainnet.py
constructs the fixed-difficulty server when disabled.
Rollback surfaces exist at both levels the design names:
vardiff=None in code, and the config switch off.

## 6. Forbidden and untouched claims

CONFIRMED. .local/mining-endpoint.json mtime 2026-11-14
17:27 and scripts/solo_cutover.py mtime 2026-11-14 17:22,
both unmodified. .local/solo-cutover.json does not exist.
mining/mainnet_live.py mtime 2026-11-16 08:16, the D9 fix
time, before the vardiff integration files (08:52); it
carries the D9 helper and no vardiff reference (grep found
only its endpoint-config share_difficulty read).
mining/work_checkpoint.py mtime 2026-11-15 11:03, predating
the integration, and the solo path never imports it (the
EXP-038 boundary in DESIGN.md section 6 holds by code
read: no import of work_checkpoint in mining/solo_server.py).

## 7. Suites re-run by the auditor, strictly sequentially

All runs on 2026-11-16, one at a time, AMD EPYC 9D25.

- make test-solo-vardiff: exit 0, 59 of 59 checks passed,
  "ALL SOLO VARDIFF TESTS PASSED" (about 611 s wall).
- make test-solo: exit 0, ALL SOLO SERVER TESTS PASSED.
- make test-solo-cutover: exit 0, ALL SOLO CUTOVER TESTS
  PASSED (10 ok lines).
- make test-exp034: exit 0, ALL EXP-034 JOB AND TEMPLATE
  TESTS PASSED (21 ok lines).
- make test-exp036: exit 0, ALL EXP-036 VERIFICATION TESTS
  PASSED (12 ok lines).
- make test-exp038: exit 0, ALL EXP-038 CHECKPOINT TESTS
  PASSED (7 ok lines).

The author's evidence logs agree: bal-test-solo-vardiff-
run4.log records 59 of 59, and bal-test-all-vardiff.log
records the full regression stopping at test-rtl on the
missing iverilog binary (the known pre-existing
environment failure, reproduced in that log verbatim).

test-autopilot claim: the author attributes its regression
failure to a pre-existing environment precondition. The
auditor VERIFIED the precondition statically rather than
by running the suite (running it would spawn a second
autopilot against the live checkout). The suite's skip
path reads a pid from .local/autopilot.lock and skips only
if that pid is alive; the lock file is 0 bytes (the live
autopilot flocks it but writes no pid), so int("") raises
ValueError, the skip cannot fire, and the suite proceeds
against a checkout whose heartbeat belongs to the live
autopilot. mining/autopilot.py is untouched by this
change. The claim is consistent with the code and the
on-disk state, and the failure is not a vardiff defect.

## 8. Regtest Gate 6, verified from the chain

VERIFIED directly, not only from suite records. The
regtest node (datadir .local/regtest, left running by the
suites) reports block count 1748 at audit time. Block at
height 1658 has hash
000000227d0e82d1d8e8270b7979cdc7c037c84bef231d0028651fcf7b439e76,
exactly the hash Entry 5 records for the first
vardiff-active block, with 91 confirmations. Height 1679
exists on the best chain with 70 confirmations. The
auditor's own test-solo-vardiff rerun additionally mined
its section D blocks through both modes during this audit
(D4, D10, D16 and D18 all passed in that run, each checking
Core acceptance and best-hash equality at run time).

## 9. Character and secret scan

Zero U+2014 characters in every changed file scanned:
mining/solo_server.py, mining/endpoint_config.py,
mining/solo_mainnet.py, tests/test_solo_vardiff.py,
tests/fixtures/solo_server_pre_integration.py,
research/sha256d/phase6b/PRODUCTION_INTEGRATION_LOG.md,
research/vardiff/PORTFOLIO_SUMMARY.md and
research/EXTREME_RESEARCH/REPOSITORY_RECONCILIATION.md.
No secret material in the changed production files: the
only matches for credential-shaped patterns are the
pre-existing rpc_password field name and its in-process
read in endpoint_config.load_mainnet_rpc; no value is
printed or committed.

## 10. Registries and reconciliation

Both markdown registries carry the R-12 integration
update marked INTEGRATED with the same account as Entry 5:
research/sha256d/experiment_registry.md (integration update
appended to the R-12 record) and research/sha256d/
extreme_optimization/EXPERIMENT_REGISTRY.md (same).
REPOSITORY_RECONCILIATION.md marks D10 FIXED.
research/vardiff/PORTFOLIO_SUMMARY.md carries the dated
integration appendix and correctly states that the
independent audit was still owed at its writing.
One registry does not agree: see N-1.

## Notes

- N-1 (registry inconsistency, correct before or at push):
  research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json still
  carries R-12 as EXPERIMENTAL with the pre-integration
  text ("production implementation still open", the 0.01
  constructor default cited as current, and "No production
  vardiff implementation exists" in its unresolved list).
  The file is the Stage 0 registry (generated 2026-11-15,
  basis HEAD 18ff4eb0), so its staleness is a snapshot
  artefact rather than an author claim; Entry 5's "both
  experiment registries" refers to the two markdown
  registries, which do agree. Either update the JSON entry
  or record explicitly that the JSON is a frozen Stage 0
  snapshot, so a future reader does not take its R-12 entry
  as current.
- N-2 (Gate 2 coverage observation): neither the suite's
  stub stream nor the auditor's own differential produced a
  network-target block candidate through the pinned path
  (blocks_found stayed empty on both rigs), so the pinned
  block path rests on the textual identity of
  _submit_share_fixed plus _submit_block (section 2) and on
  the live pinned-mode block in suite check D10, not on a
  stub differential of the block branch. Adequate, but
  worth knowing.
- N-3 (test-autopilot): verified statically only, for the
  reason given in section 7. The underlying quirk (the
  autopilot lock carries no pid, so the suite's live-stack
  skip can never fire) is pre-existing and outside this
  change; it will keep failing test-all on any checkout
  with a live autopilot until either the lock gains a pid
  or the skip test changes.
- N-4 (residual value duplication, not a D10 reopening):
  VarDiffController's own default initial=0.02 duplicates
  the config value inside the controller class, matching
  the prototype's declared operating point. No production
  path relies on it: solo_mainnet.py always passes
  initial=share_difficulty from the config, and the
  SoloServer fixed path resolves from the config. A caller
  who constructs VarDiffController() directly gets the
  prototype defaults, which currently coincide with the
  config; if SOLO_SHARE_DIFFICULTY ever changes, direct
  construction would silently keep 0.02. Worth a comment
  or a config read at that point, not a change now.
- N-5 (inherited bounded-memory behaviour): the duplicate
  seen-set resets to just the newest key once it exceeds
  200,000 entries, so a duplicate older than the reset
  would be judged fresh. This is byte-identical to the
  verified prototype's behaviour (research/vardiff/
  vardiff.py lines 389 to 393) and is a deliberate memory
  bound, recorded here only so the property is on record.

## Left unverified

- Full make test-all was not re-run by the auditor; the
  six suites named in the audit brief were re-run, and the
  author's bal-test-all-vardiff.log covers the rest up to
  the known test-rtl environment failure.
- test-autopilot was not executed (section 7, N-3).
- Nothing on mainnet, two-client interference on one
  server, the rate-stepped stability campaign, and any
  other host remain unverified, exactly as Entry 5 and the
  portfolio appendix state.
- The auditor did not re-run the prototype suite; the
  production suite's ported sections A to F are its
  successor evidence.
