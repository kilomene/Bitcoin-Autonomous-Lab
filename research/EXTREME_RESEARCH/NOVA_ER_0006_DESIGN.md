# NOVA-ER-0006 design note: incident code registry (register R-30)

Date: 2026-11-17. Written before any code edit, in the
Stage 9 predeclaration style. Entry: NOVA-ER-0006 in
research/EXTREME_RESEARCH/EXPERIMENT_PORTFOLIO.md. EXP
identity: none; this is an engineering change under
register R-30 (rows in
research/master_build/HISTORICAL_OPPORTUNITY_REGISTER.md
and RESEARCH_OPPORTUNITY_REGISTER.md, both NEW at the
time of writing; the authoritative status lives in
research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json,
entry R-30, status NEW, baseline "free-text incident
records").

## Question and hypothesis (from the portfolio)

Can every detected fault, recovery action and backend
refusal in the mining stack carry a stable numeric code
from an append-only registry, so agent reasoning and
post-incident audit key on codes instead of free text?
Hypothesis: a coarse, append-only first taxonomy covers
the observed fault classes without ossifying, because
the observed classes are already enumerated by the
keeper and autopilot records. Studied model: the
MicroBT Whatsminer public error-code documentation
(documentation-sourced only).

## The recorded corpus, censused before designing

The taxonomy is built from what the stack has actually
recorded, not from imagined faults.

.local/autopilot.log (the supervisor's incident record,
165 lines in this checkout) contains exactly six
message shapes:

- "miner started pid=N cmd=..." (64)
- "autopilot up pid=N ..." (56)
- "miner exited rc=N after Ns; restart #K in Bs" (21)
- "autopilot stopped" (15)
- "stop file present; shutting down" (7)
- "evidence stale Ns; killing hung miner" (2)

evidence/mainnet-live.jsonl (the miner's record,
29,887 lines) fault, refusal and recovery classes:

- share_result with accepted=false: 8 (of 906)
- connection_error: 53; reconnect_failed: 66;
  connected / reconnected: 85 / 10 (recovery side)
- candidate_rejected: 18 (independent verification
  refused the candidate)
- template_rejected: 2 (template validation refused
  the template)
- backend_selected: 40, selections only (v512dual 31,
  v512 9); the reason fields explain the selected tier
  and carry no refusal text for unselected tiers, and
  the word "refus" appears nowhere in the file
- authorize_result: 71, all ok=true (no refusal
  instance recorded)

Keeper records (the bal-mainnet-keeper cron's tracking
entries, 2026-11-17) add three classes the repo's own
files do not record directly: autopilot found dead and
restarted; bitcoind RPC down and the node restarted;
miner dead after a pool disconnect and DNS failure,
restarted.

Statistics-side refusal records: mining/aggregation.py
records the categories stale_reports and
duplicate_deliveries into MiningStatistics (EXP-057);
the category leases_abandoned exists in
mining/mining_statistics.py with no current producer.
SafeRecorder (EXP-037) counts swallowed record()
exceptions in a bare errors counter.

## The taxonomy (20 codes, coarse, append-only)

Groups: 1xxx miner lifecycle, 2xxx supervisor
lifecycle, 3xxx self-update path, 4xxx work and report
integrity (statistics), 5xxx upstream and verification
classes whose producing records live in the miner's
evidence log or the keeper's records.

| Code | Name | Class | Emission |
|---|---|---|---|
| 1001 | MINER_EXITED | miner child exited, any rc; autopilot restarts it | autopilot site S2 |
| 1002 | MINER_STALE_EVIDENCE | evidence log stale past the hung window; autopilot kills the miner | autopilot site S3 |
| 1003 | MINER_STARTED | miner child (re)started by the autopilot (recovery action) | autopilot site S1 |
| 2001 | SUPERVISOR_STARTED | autopilot process started | autopilot site S6 |
| 2002 | SUPERVISOR_STOPPED | autopilot shut down at the end of its run loop | autopilot site S5 |
| 2003 | OPERATOR_STOP | stop file present; shutdown requested by the operator path | autopilot site S4 |
| 2004 | INSTANCE_REFUSED | a second autopilot was refused by the single-instance lock | autopilot site S7 |
| 2005 | SUPERVISOR_LOST | supervisor found dead by the outer keeper and restarted | registry only in this change; the keeper is not repo code |
| 3001 | UPDATE_AVAILABLE | self-update found a newer version and started the pull | autopilot site S8 |
| 3002 | UPDATE_PULL_FAILED | update pull failed; current version kept | autopilot site S9 |
| 3003 | UPDATE_REFUSED | new code failed the smoke test and was rolled back (refusal of new code) | autopilot site S10 |
| 3004 | UPDATE_APPLIED | update pulled, smoke test passed, miner restarted onto new code | autopilot site S11 |
| 4001 | REPORT_STALE | a coordinator or aggregation report was rejected as stale | statistics keying K1 (category stale_reports) |
| 4002 | REPORT_DUPLICATE | a report was rejected as a duplicate delivery | statistics keying K2 (category duplicate_deliveries) |
| 4003 | WORK_ABANDONED | a lease was abandoned | statistics keying K3 (category leases_abandoned) |
| 5001 | SHARE_REJECTED | the pool rejected a submitted share (submission failure) | registry only in this change; producer is the miner's evidence record |
| 5002 | UPSTREAM_DISCONNECT | upstream (pool or node) connection failed or unreachable, and its recovery | registry only in this change; producers are the evidence log and the keeper |
| 5003 | BACKEND_REFUSED | a backend tier was refused at probe or selection | registry only in this change; see the corpus note below |
| 5004 | CANDIDATE_REFUSED | independent candidate verification refused a candidate | registry only in this change; producer is the miner's evidence record |
| 5005 | TEMPLATE_REFUSED | template validation refused a template | registry only in this change; producer is the miner's evidence record |

The portfolio's five named starting classes map as:
miner death 1001; stale job 1002 (the job stream going
stale is exactly what the supervisor observes as stale
evidence; 4001 is the distinct coordinator-report
analogue, a different producer and meaning, so it is a
separate code rather than a lumped one); node
disconnect 5002; backend refusal 5003; submission
failure 5001.

Corpus note on 5003: the operational corpus contains
no explicit backend-refusal record (backend_selected
records selections and selected-tier reasons only).
The class is real in the stack's behaviour (EXP-039
guarded probes refuse tiers; dispatch records reasons
in code) and is named by the portfolio, so it is coded
here; the Gate 5 replay records honestly that it has
no instance in the operational corpus. No code is
minted for authorize_result refusals: all 71 recorded
instances are ok=true, the producer is out of scope,
and the append-only discipline means a code is added
when a class is observed or gains a site, not before.

## Predeclared emission sites

autopilot.py (the log() call named; each becomes a
log_incident(code, msg) call whose line gains a
"[code] " prefix token; removing the token restores
the prior line byte-for-byte):

- S1 start_child, "miner started ...": 1003
- S2 run(), "miner {state} after ...; restart #...":
  1001
- S3 run(), "evidence stale ...; killing hung miner":
  1002
- S4 run(), "stop file present; shutting down": 2003
- S5 run(), final "autopilot stopped": 2002
- S6 main(), "autopilot up ...": 2001
- S7 main(), the lock-refusal print "another autopilot
  already owns this checkout; exiting": 2004 (the
  print gains the "[2004] " prefix; it is a stdout
  record, not a log() line)
- S8 maybe_update(), "update available ...": 3001
- S9 maybe_update(), "pull failed; keeping current
  version": 3002
- S10 maybe_update(), "smoke test FAILED on new code;
  rolling back": 3003
- S11 maybe_update(), "updated to ...; restarting
  miner onto new code": 3004

mining_statistics.py (statistics keying; no producer
outside this file changes):

- K1 record("stale_reports") also keys 4001
- K2 record("duplicate_deliveries") also keys 4002
- K3 record("leases_abandoned") also keys 4003
- New public API: MiningStatistics.record_incident
  (code, count, worker, backend), validated against
  the registry; SafeRecorder.record_incident with the
  EXP-037 failure isolation; MiningStatistics
  .incident_snapshot() and .incident_total(code) as
  the code-keyed view.

The autopilot also counts its incidents through a
SafeRecorder and publishes them as a new
"incident_counts" field in heartbeat.json (code ->
count, only codes that have fired). That is the record
the keeper and the awareness layer already read, so
codes reach audit without a new consumer.

## Layering rules (fixed here, not improvised later)

1. Codes annotate records and change no behaviour.
   Log lines gain a prefix token; heartbeat.json gains
   one field; statistics records gain a parallel
   code-keyed view. Nothing else changes shape.
2. snapshot() is NOT extended: test_exp037 pins its
   key set exactly ({"categories", "totals",
   "per_worker", "per_backend"}), and the EXP-037
   rule is that categories are never merged or summed.
   Incidents are not categories; they get their own
   incident_snapshot() view.
3. Gate 3 refusal lives at the validation layer:
   incident_codes.resolve / annotate / prefix and
   MiningStatistics.record_incident raise ValueError
   on an unknown code, and a refused call changes no
   counter.
4. The hot paths can never be killed by the registry:
   the autopilot's log_incident degrades to the plain
   log line if the registry cannot be read, and counts
   the incident through SafeRecorder, whose contract
   (EXP-037) is to swallow and count recording
   failures. The statistics keying path (K1 to K3)
   uses module constants pinned to the registry by
   the test suite, so record() behaves exactly as
   before even if the registry file is unreadable.
   This layering mirrors the existing precedent:
   record() already refuses unknown categories by
   raising, while SafeRecorder refuses-and-counts.
5. Registry discipline: codes are integers, unique,
   strictly increasing in file order; an entry's code,
   name and meaning are immutable once shipped; new
   classes are only ever appended. mining/
   incident_codes.py exposes check_append_only(old,
   new) returning the list of discipline violations,
   and the test suite pins the shipped baseline
   (code, name) pairs and asserts the shipped registry
   still matches it exactly.

## Gate criteria (predeclared)

Gate 3 (refusal and discipline), all in
tests/test_incident_codes.py:

- resolve, annotate, prefix and record_incident raise
  on unknown codes (9999, 0, -1, a string, None); a
  refused record_incident changes no incident counter.
- check_append_only detects each of: a mutated
  meaning, a removed entry, a reordered pair, a reused
  code under a new name, an insertion in the middle;
  and accepts a pure append. The shipped registry
  validates (unique, increasing, complete fields) and
  equals the pinned baseline.
- Site coverage: every log_incident literal in
  mining/autopilot.py is a registry code; the set of
  literals equals the predeclared site set {1001,
  1002, 1003, 2001, 2002, 2003, 3001, 3002, 3003,
  3004} plus the S7 prefix site {2004};
  CATEGORY_INCIDENT_CODES values are exactly {4001,
  4002, 4003} and all in the registry.
- Statistics keying: recording stale_reports,
  duplicate_deliveries and leases_abandoned keys
  exactly 4001, 4002, 4003 (totals and per-worker);
  recording any other category keys nothing;
  snapshot() keeps exactly its pinned key set.

Gate 5 (end to end, isolated instance only): a
byte-copy of the mining package in a temp directory,
run with a stub miner and fast thresholds, seeded
evidence carrying one old job event so the stale path
fires. Required observations in the isolated copy's
own records:

- the isolated autopilot.log shows, in order, coded
  lines for 2001 (up), 1003 (miner started), 1002
  (stale evidence kill), 1001 (miner exited), 1003
  (restart), 2003 (stop file), 2002 (stopped);
- a second instance started against the same isolated
  tree prints the [2004] refusal and exits 0;
- the isolated heartbeat.json incident_counts equals
  the counts of coded lines in the isolated log;
- replay: a classifier whose rules are fixed here
  (autopilot log shapes by message prefix; evidence
  events share_result accepted=false -> 5001,
  connection_error and reconnect_failed -> 5002,
  connected and reconnected -> 5002 recovery side,
  candidate_rejected -> 5004, template_rejected ->
  5005, backend_selected -> selection record, maps
  to 5003 only if a reason field records a refusal,
  of which the corpus has none) maps every
  incident-class record in the real .local/
  autopilot.log and evidence/mainnet-live.jsonl to
  exactly one code, with zero unmapped incident lines
  in the autopilot log, and reports the per-code
  instance counts. Classes with no instance in the
  corpus (3001 to 3004, 2004, 2005, 5003, 4003) are
  named as such, not silently passed over.

Gates 1, 2, 4 and 6 do not apply (portfolio).

## Success and failure criteria (portfolio, verbatim in substance)

Success: all predeclared incident sites emit codes
from the registry, and a replay of recorded incident
classes maps each to exactly one code.

Failure: a fault class in the records cannot be coded
without splitting hairs, indicating the taxonomy is
wrong at its first step; that triggers a taxonomy
redesign, not more codes.

## Scope limits and rollback

Emission is wired only where this change is scoped:
mining/autopilot.py and mining/mining_statistics.py.
The 5xxx classes and 2005 are coded in the registry
(the taxonomy is the stack's, not one file's) with
their producers named; wiring emission into
mining/mainnet_live.py's evidence writer or into the
keeper (not repo code) is not part of this change and
is not claimed. Live records will carry codes only
after the next natural autopilot restart; nothing in
this change restarts, signals or reconfigures the
live stack, and .local/mining-endpoint.json is not
touched. Rollback: removing the prefix tokens, the
heartbeat field and the statistics keying restores
prior record shapes byte-for-byte; the registry file
and module are additive new files.
