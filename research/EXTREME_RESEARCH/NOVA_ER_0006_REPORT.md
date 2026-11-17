# NOVA-ER-0006 report: incident code registry (register R-30)

Date: 2026-11-17. Entry: NOVA-ER-0006 in
research/EXTREME_RESEARCH/EXPERIMENT_PORTFOLIO.md;
register R-30. EXP identity: none; engineering change.
Design note (written and fixed before any code edit):
research/EXTREME_RESEARCH/NOVA_ER_0006_DESIGN.md.
Host: AMD EPYC 9D25.

## Verdict: success criterion met

The portfolio's success criterion has two halves, and
both hold. (1) All predeclared incident sites emit
codes from the registry: the 11 autopilot sites and
the 3 statistics keying sites listed below, proven by
the site-coverage scan and the Gate 5 isolated run.
(2) A replay of recorded incident classes maps each
to exactly one code: all 165 lines of the real
autopilot log and every fault, refusal and recovery
class in the real evidence log classified with zero
unmapped incident records (counts in the Gate 5
section). The failure criterion was not triggered: no
recorded fault class resisted coding. One class the
portfolio names, backend refusal, has no instance in
the operational corpus; it is coded (5003) and the
gap is recorded plainly below rather than papered
over. Register R-30 is marked INTEGRATED in
research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json,
and the derived agent integration registry was
regenerated to match (30 INTEGRATED entries).

## The taxonomy (20 codes)

Shipped in mining/incident_registry.json, append-only
by discipline (a shipped code keeps its number, name
and meaning forever; new classes are only appended).

- 1xxx miner lifecycle: 1001 MINER_EXITED,
  1002 MINER_STALE_EVIDENCE, 1003 MINER_STARTED.
- 2xxx supervisor lifecycle: 2001 SUPERVISOR_STARTED,
  2002 SUPERVISOR_STOPPED, 2003 OPERATOR_STOP,
  2004 INSTANCE_REFUSED, 2005 SUPERVISOR_LOST.
- 3xxx self-update: 3001 UPDATE_AVAILABLE,
  3002 UPDATE_PULL_FAILED, 3003 UPDATE_REFUSED,
  3004 UPDATE_APPLIED.
- 4xxx work and report integrity: 4001 REPORT_STALE,
  4002 REPORT_DUPLICATE, 4003 WORK_ABANDONED.
- 5xxx upstream and verification: 5001 SHARE_REJECTED,
  5002 UPSTREAM_DISCONNECT, 5003 BACKEND_REFUSED,
  5004 CANDIDATE_REFUSED, 5005 TEMPLATE_REFUSED.

The portfolio's five starting classes map as: miner
death 1001; stale job 1002 (the supervisor observes a
stale job stream as stale evidence; the distinct
coordinator-report analogue is 4001, a different
producer and meaning, coded separately rather than
lumped); node disconnect 5002; backend refusal 5003;
submission failure 5001.

## What was built

- mining/incident_registry.json (new): the registry
  document, 20 entries with code, name, class,
  description and emission site or producer.
- mining/incident_codes.py (new): the lookup and
  validation module. load_registry validates the
  discipline (complete fields, unique integer codes,
  strictly increasing file order). resolve, annotate
  and prefix refuse unknown codes with
  UnknownIncidentCode (a ValueError); there is no
  default code. check_append_only(old, new) returns
  the violations of the append-only rule between two
  entry lists.
- mining/autopilot.py (edited, additive): a
  log_incident(code, msg) helper resolves the code,
  prefixes the log line with a "[code] " token, and
  counts the incident in a process ledger through
  SafeRecorder; heartbeat() publishes the ledger as a
  new incident_counts field. The import of the coding
  layer is defensive: if it cannot be imported or a
  code cannot be resolved, the plain line is logged
  and supervision is unaffected (counting failures
  are swallowed and counted by SafeRecorder, the
  EXP-037 contract). Sites: S1 start_child 1003;
  S2 miner exit 1001; S3 stale evidence kill 1002;
  S4 stop file 2003; S5 final stop line 2002;
  S6 startup line 2001; S7 lock-refusal print 2004;
  S8 update available 3001; S9 pull failed 3002;
  S10 smoke test rollback 3003; S11 update applied
  3004.
- mining/mining_statistics.py (edited, additive):
  CATEGORY_INCIDENT_CODES keys 4001, 4002 and 4003
  from record() of stale_reports,
  duplicate_deliveries and leases_abandoned (K1 to
  K3), so the existing producers (mining/aggregation
  .py records the first two) emit codes with no
  change outside this file. New record_incident()
  API resolves codes against the registry at call
  time and refuses unknown codes; the ledger is
  exposed by incident_snapshot() and
  incident_total(). snapshot() is deliberately
  unchanged: its key set is pinned by EXP-037 and
  incidents are not categories. The keying path uses
  module constants pinned to the registry by the
  test suite, so record() behaves exactly as before
  even if the registry file is unreadable.
- tests/test_incident_codes.py (new), wired into the
  Makefile as test-incident-codes; test-all is now
  51 targets.

Codes annotate records and change no behaviour:
removing the prefix token, the heartbeat field and
the keying restores prior record shapes byte-for-byte
(the rollback the portfolio predeclared).

## Gate 3 results (34-check suite, refusal and discipline)

- Refusal: resolve, prefix, annotate and
  record_incident raise on 9999, 0, -1, a string,
  None and a float; a refused record_incident changes
  no counter. SafeRecorder refuses-and-counts (errors
  increments, nothing raises), per its contract.
- Append-only: check_append_only detects an in-place
  edit, a removal, a reordering, a renumbered or
  reused code and a middle insertion, and accepts a
  pure append. The shipped registry equals the
  suite's pinned baseline of 20 (code, name) pairs.
- Site coverage: the log_incident literals in
  mining/autopilot.py are exactly the predeclared
  site set {1001, 1002, 1003, 2001, 2002, 2003, 3001,
  3002, 3003, 3004}, the S7 print carries prefix(2004),
  every literal is a registry code, and no incident
  message stem remains on a bare log() call.
- Keying: stale_reports, duplicate_deliveries and
  leases_abandoned key exactly 4001, 4002 and 4003 in
  totals, per-worker and per-backend views; a
  non-incident category keys nothing; snapshot()
  keeps exactly its pinned key set.

## Gate 5 results (isolated instance and replay)

Isolated instance: a byte-copy of the mining package
in a temp directory, stub miner, fast thresholds,
evidence seeded with one job event timestamped 2020
so the stale path fires. Its own autopilot.log shows
the coded sequence end to end: [2001] supervisor up,
[1003] miner started, [1002] stale evidence kill,
[1001] miner exited, [1003] restart (the stale cycle
fired twice before the stop, so 1002 and 1003 appear
twice each in the run's counts: {1001: 1, 1002: 2,
1003: 2, 2001: 1, 2002: 1, 2003: 1}). A second
starter against the same isolated tree printed the
[2004] refusal and exited 0. The isolated
heartbeat.json incident_counts matched the coded log
lines exactly, with one stated exception: the final
heartbeat is written before the [2002] stop line is
logged (the pre-existing teardown order), so 2002
lags by exactly its own line. Nothing in the live
tree was touched by the run.

Replay over the recorded corpus (read only): all 165
lines of .local/autopilot.log mapped to exactly one
code with zero unmapped lines (1001: 21, 1002: 2,
1003: 64, 2001: 56, 2002: 15, 2003: 7; the update
sites 3001 to 3004 and the refusal print 2004 have
code sites but no recorded instance in this log).
Evidence classes mapped: 5001 share rejected 8,
5002 upstream disconnect 214 (53 connection_error,
66 reconnect_failed, 85 connected, 10 reconnected),
5004 candidate refused 18, 5005 template refused 2.
The keeper's recorded classes map as: supervisor
found dead and restarted, fault 2005 with recovery
2001; node RPC down and restarted, 5002; miner dead
after pool disconnect and DNS failure, 5002 with
1001. Classes with no instance in the operational
corpus: 2004 (its record is a stdout print, verified
in the isolated run instead), 2005 (keeper-produced),
3001 to 3004 (the self-update path has never fired
in the recorded history), 4003 (the category has no
current producer), 5003 (next section).

## The 5003 note (backend refusal)

The operational evidence corpus records backend
selections only: backend_selected carries the
selected tier and its reason, unselected tiers carry
no reason, and no refusal text exists anywhere in
the file. So the replay finds zero 5003 instances,
and the suite asserts exactly that rather than
inventing a mapping. The class is nonetheless real
and coded: EXP-039's guarded probes refuse tiers by
construction and dispatch records per-tier reasons
in code, and the portfolio names backend refusal as
a starting class. If a future producer records
refusals explicitly, the code is already assigned;
minting it now is the taxonomy doing its job, and
claiming a replay instance for it would be false.

## Suites

- test-incident-codes: 34 checks, ALL PASSED (run
  twice, before and after the register updates).
- test-autopilot: ALL PASSED (self-skipped against
  the live stack, lock verified, as designed).
- test-mainnet-live: ALL PASSED.
- test-agent-intelligence: ALL PASSED (106 checks),
  after the derived registry regeneration.
- test-exp037 (statistics pin): ALL PASSED.
- test-exp057 (aggregation records into the edited
  statistics engine): 15 checks, ALL PASSED.
- python -m py_compile clean on mining/autopilot.py,
  mining/mining_statistics.py, mining/incident_codes
  .py and tests/test_incident_codes.py.

## Register changes

- research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json:
  entry R-30 updated in place, status NEW to
  INTEGRATED, with the measured result, evidence and
  unresolved items recorded (the R-26 pattern).
- agent/intelligence/integration_registry.json:
  regenerated with agent.intelligence.integrations
  .write_registry(); 29 to 30 INTEGRATED entries,
  R-30 included; test-agent-intelligence re-run
  green (above).
- research/sha256d/experiment_registry.md and
  research/sha256d/extreme_optimization/
  EXPERIMENT_REGISTRY.md: the NOVA-ER-0006 record
  appended to both, byte-identical (2,500 bytes
  each); next unreserved ID unchanged at EXP-059.
- The master_build opportunity registers are dated
  snapshots (2026-11-15) and were not rewritten;
  the authoritative status is the experiment
  registry's, as with R-26 before.

## UNVERIFIED and not claimed

- Live records carrying codes: the running autopilot
  (pid 3248, miner pid 3251, both untouched by this
  work) still runs the pre-change code. Coded live
  records begin only after the next natural autopilot
  restart, which the keeper performs on its own
  schedule; no restart, signal or reconfiguration
  was forced, and .local/mining-endpoint.json is
  byte-identical, sha256:
  d741cde3c6224406f46f3bae138fb174eb1d780725bcb94baff4e14a8670c7d3.
- Emission at the 5xxx and 2005 producers: the codes
  are assigned and their recorded classes are
  replay-mapped, but mining/mainnet_live.py's
  evidence writer does not yet stamp codes onto its
  events and the keeper is not repo code. Wiring
  either is future work, not part of this change.
- The update-path codes (3001 to 3004) are verified
  at their sites by the coverage scan only; the path
  has never fired on this VM (no .git checkout), so
  no end-to-end instance exists anywhere.
- Independent audit and push are the parent's steps,
  not performed here.
