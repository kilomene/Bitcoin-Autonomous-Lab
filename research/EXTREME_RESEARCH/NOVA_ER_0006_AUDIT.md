# NOVA-ER-0006 independent audit: incident code registry (register R-30)

Date: 2026-11-17. Auditor: independent (not the
builder). Scope: the NOVA-ER-0006 change set in the
working tree, audited against the pushed tree at
remote HEAD 6528aae071fff74922f2d4a2b3b98e48ed440697
(read-only git-blobs fetches at that pinned commit)
and against the design note and report
(research/EXTREME_RESEARCH/NOVA_ER_0006_DESIGN.md and
NOVA_ER_0006_REPORT.md) and the portfolio entry
NOVA-ER-0006. Host: AMD EPYC 9D25.

## Verdict: PASS WITH NOTES, 0 defects

Every claim in the report was independently verified:
the additive-only diff, the fail-safe layering, Gate 3
refusal and append-only discipline (shipped suite plus
the auditor's own probes), the Gate 5 isolated run and
the corpus replay (independently re-implemented, exact
count match), the register updates, and the hygiene
checks. No defect was found. Three notes are recorded;
none affects the verdict.

## Claim 1: additive-only edits (VERIFIED)

Unified diffs of mining/autopilot.py and
mining/mining_statistics.py, local tree against the
remote blobs at HEAD 6528aae0, hunk by hunk:

- autopilot.py: a docstring paragraph; the defensive
  import block (with the sys.path insert that makes it
  importable as a script); the _INCIDENTS ledger and
  the log_incident helper; eleven log() or print sites
  converted to log_incident(code, msg) or the
  prefix(2004) print, with every message string
  byte-identical to the remote version after the
  prefix token is removed; and the conditional
  incident_counts field in heartbeat(). No other hunk
  exists: thresholds, EvidenceCounter, git and update
  logic, lock handling, signal handling and control
  flow are untouched.
- mining_statistics.py: a docstring paragraph;
  CATEGORY_INCIDENT_CODES and the lazy _incident_codes
  loader; three new ledger dicts in __init__; the
  keying call appended at the end of record(), after
  all pre-existing counter updates, through
  _key_incident, which performs only dict operations
  and cannot raise; the new _key_incident,
  record_incident, incident_total and
  incident_snapshot methods; and SafeRecorder gaining
  record_incident and incident_snapshot passthroughs.
  No other hunk exists.
- snapshot() itself has no diff hunk, so its key set
  is unchanged by construction; test_exp037, which
  pins that shape, passes under the auditor's own run
  (below).

## Claim 2: the coding layer can never kill supervision (VERIFIED)

Five sabotage variants were run as isolated byte-copy
autopilot instances in temp directories (stub miner,
fast thresholds; the live instance was never touched):

- registry file deleted; registry file corrupted
  (invalid JSON); registry file discipline-violating
  (a duplicated code): in each, the instance started,
  started its miner, wrote a heartbeat with the miner
  running, and exited 0 on the stop file, with plain
  uncoded log lines and heartbeat incident_counts
  present but empty (prefix resolution fails per line;
  counting is refused and swallowed by SafeRecorder,
  exactly the design's layering rule 4).
- incident_codes.py replaced by a module that raises
  RuntimeError at import, and incident_codes.py
  deleted: in each, the combined defensive import
  fails, _INCIDENTS is None, the heartbeat carries no
  incident_counts field, and supervision behaviour is
  otherwise identical (start, miner start, heartbeat,
  clean stop, exit 0, no traceback).
- Statistics side, in sabotaged trees: record() of a
  keyed category still records its totals and keys
  4001 from the module constants with the registry
  missing or the module sabotaged, exactly as before
  the change. The keying path never reads the registry
  at runtime, as designed.

## Claim 3: Gate 3 (VERIFIED, suite plus auditor probes)

tests/test_incident_codes.py run by the auditor: 34
checks, ALL PASSED, including its Gate 5 isolated
instance and replay (see claim 4). The auditor's own
additional probes, all passing:

- Wrong-type forms of an existing code ("1001",
  1001.0, True, a list, a dict) are refused with
  UnknownIncidentCode by resolve, prefix and annotate,
  and with ValueError by MiningStatistics
  .record_incident; a refused record_incident changes
  no counter, for every bad type. annotate on a
  non-dict raises TypeError, as documented.
- check_append_only violation kinds beyond the
  shipped suite: a duplicate code appended at the end,
  a name-only edit, an emission-only edit, a
  class-only edit, an append whose code is below the
  current maximum (out of order), an existing code
  reused at the end, and a malformed old list are each
  detected; a clean append is accepted.
- Non-literal emission: every log_incident call site
  in mining/autopilot.py was enumerated; all eleven
  take integer literals (1001, 1002, 1003, 2001, 2002,
  2003, 3001, 3002, 3003, 3004) and the single prefix
  call takes the literal 2004. The only bare log()
  call in the file is the one inside log_incident
  itself. There is no variable-smuggled emission site
  in the shipped tree for the coverage scan to miss
  (see note N-2 for the scan's inherent limit).

## Claim 4: Gate 5 and replay (VERIFIED, independently re-implemented)

The auditor snapshotted the corpus at 2026-11-17
16:08 UTC (.local/autopilot.log, 165 lines;
evidence/mainnet-live.jsonl, 30,050 lines) and
re-ran the replay with an independently written
classifier implementing the design note's fixed
rules:

- Autopilot log: all 165 lines map to exactly one
  code, zero unmapped. Per-code counts match the
  report exactly: 1001: 21, 1002: 2, 1003: 64,
  2001: 56, 2002: 15, 2003: 7. The nine normalized
  line shapes in the file are variants of the six
  censused classes; the update shapes (3001 to 3004)
  and the refusal print (2004) have no instance, as
  the report states.
- Evidence log: per-code counts match the report
  exactly: 5001: 8, 5002: 214 (connection_error 53,
  reconnect_failed 66, connected 85, reconnected 10),
  5004: 18, 5005: 2. A full event-type census (20
  types) found no fault-class event type outside the
  classifier: the remaining types are non-incident
  records (job, status, submit, template_validated,
  candidate_confirmed, endpoint_selected, and the
  success sides of share and authorize flows).
- The 5003 zero-instance claim was verified, not
  trusted: the substring "refus" appears in zero of
  the 30,050 evidence lines; all 70 *_reason values
  across the 40 backend_selected events are either
  null (31, serialized as the string "None") or a
  "selected: ..." string for the selected tier only
  (39); no refusal semantics of any wording exists.
  The 8 rejected shares all carry pool "Job not
  found" errors (genuine 5001 instances), no accepted
  share carries a non-null error, and all 71
  authorize_result events are ok=true, confirming the
  design's decision to mint no authorize-refusal code.
- Gate 5 isolated instance: the shipped suite's
  byte-copy run passed under the auditor's own
  execution (checks 28 to 31), with counts {1001: 1,
  1002: 2, 1003: 2, 2001: 1, 2002: 1, 2003: 1}, the
  [2004] second-starter refusal, and heartbeat
  incident_counts matching the coded lines with the
  disclosed 2002 teardown lag. The auditor's five
  sabotage instances (claim 2) exercised the same
  machinery further.

## Claim 5: registers (VERIFIED)

- research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json
  against the remote at HEAD 6528aae0, parsed: 109
  entries on both sides; the ONLY differing entry is
  R-30 (status NEW to INTEGRATED, measured_result,
  evidence and unresolved rewritten). The entry
  follows the R-26 pattern field for field, its
  measured_result text is accurate against everything
  verified above, and independently_reproduced
  honestly remains "no".
- agent/intelligence/integration_registry.json
  against the remote, parsed: 29 to 30 entries; the
  only difference is the added R-30 record; every
  shared record is identical and the non-entry keys
  are unchanged. The regeneration added exactly R-30.
- Both markdown registries: each local file has the
  remote file as an exact byte prefix (append-only);
  each append is exactly 2,500 bytes; the two appends
  are byte-identical; the append closes at "Next
  unreserved ID: EXP-059.", unchanged.
- Makefile against the remote: the diff is limited
  to the new test-incident-codes target and the
  test-all token; test-all now lists 51 prerequisites
  (remote: 50), the last being test-incident-codes.

## Claim 6: hygiene and neighbour suites (VERIFIED)

- U+2014 count is zero in all twelve touched files
  (the two new mining files, the two edited mining
  files, the test suite, the Makefile, the three
  registries, both markdown registries, the design
  note and the report) and in this audit file.
- .local/mining-endpoint.json sha256 at audit start
  and audit end:
  d741cde3c6224406f46f3bae138fb174eb1d780725bcb94baff4e14a8670c7d3,
  unchanged.
- Live stack observed at audit start and end and
  never signalled: autopilot pid 3248, miner pid
  3251, bitcoind running. The live heartbeat still
  has no incident_counts field and the live
  autopilot log still has its 165 pre-change lines,
  confirming the running autopilot still executes the
  pre-change code and nothing restarted it.
- Neighbour suites run by the auditor: test-autopilot
  ALL PASSED (self-skipped against the live stack,
  lock verified, as designed); test-mainnet-live ALL
  PASSED; test-agent-intelligence ALL PASSED (106
  checks, consistent with the regenerated derived
  registry); test-exp037 ALL PASSED (the snapshot pin
  holds). The builder's additional claim for
  test-exp057 was also spot-verified: 15 checks, ALL
  PASSED.

## Defects

None. (D-list empty.)

## Notes

- N-1 (not verdict-affecting): the Gate 3 refusal
  contract is stated for unknown codes, and there it
  holds exactly (ValueError everywhere). At the
  direct MiningStatistics.record_incident API, a
  missing registry file raises FileNotFoundError and
  an import-time-raising incident_codes module
  propagates its own exception (the lazy loader in
  mining_statistics catches only ImportError), rather
  than ValueError. No shipped claim covers that case,
  record() is unaffected, and the only production
  caller (SafeRecorder, in the autopilot) swallows
  all exceptions, so supervision and the hot paths
  are insulated; recorded here so the exception-type
  boundary is documented precisely.
- N-2 (not verdict-affecting): the site-coverage scan
  matches log_incident calls by a numeric-literal
  regex. The auditor verified by enumeration that
  every shipped call site is a literal, so Gate 3
  holds for this tree; the scan is a check on the
  current tree, not a structural bar against a future
  non-literal emission site.
- N-3 (not verdict-affecting): the evidence corpus is
  live and append-only (29,887 lines at the design
  census, 30,050 at the auditor's snapshot). The four
  mapped evidence counts were identical at the
  builder's run and the auditor's because the lines
  appended in between carried no new fault-class
  events; the counts are exact for the corpus as
  snapshotted, and the suite's evidence assertions
  use at-least thresholds for this reason.

## UNVERIFIED

- Keeper-side records: the report's mapping of the
  bal-mainnet-keeper's recorded classes (2005 with
  recovery 2001; node down as 5002) is stated against
  the keeper's tracking entries, which are not repo
  code and were not part of the auditable tree. The
  mapping is consistent with the design census, but
  the auditor did not independently re-derive it.
- Live records carrying codes: this begins only after
  the next natural autopilot restart, which had not
  occurred by audit end (verified above). The coded
  live record stream is therefore not yet observed.
- The self-update sites (3001 to 3004) end to end:
  the path has never fired on this VM; the sites are
  verified by the coverage scan and the diff only, as
  the report itself states.
- Emission at the 5xxx and 2005 producers: assigned
  and replay-mapped, not wired, by the change's own
  declared scope; nothing about their future wiring
  is verified here.
