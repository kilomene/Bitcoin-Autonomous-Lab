# Stage 6, Item 1: Independent Audit of the D9 Fix (2026-11-16)

Auditor: independent agent, not the author of the fix.
Scope: the production change recorded as Entry 4 of
research/sha256d/phase6b/PRODUCTION_INTEGRATION_LOG.md
(Stage 0 discrepancy D9, live miner backend line labelling).
Host: AMD EPYC 9D25, hostname htch-runtime, confirmed from
/proc/cpuinfo at audit time. Remote HEAD at audit time:
3ebbaeb216bc1260cfca22c63b9af60d780a971e (the fix is local
and unpushed; the remote tree therefore holds the pre-fix
code, which this audit used as the pristine baseline).

## Verdict: PASS WITH NOTES

Zero defects. Every claim in Entry 4 and in the
reconciliation D9 entry was verified against the code, the
pre-fix baseline, live process state, and fresh test runs.

## Check 1: Diff scope. CONFIRMED

Method: blob-sha comparison of the whole local tree against
the remote tree at HEAD (bal_github local_files() and
remote_tree()), then a unified diff of each changed source
file against its remote (pre-fix) bytes.

- Source files differing from HEAD: exactly the four
  claimed files (mining/mainnet_live.py,
  tests/test_mainnet_live_accounting.py,
  research/EXTREME_RESEARCH/REPOSITORY_RECONCILIATION.md,
  research/sha256d/phase6b/PRODUCTION_INTEGRATION_LOG.md).
  The only other differences are the live evidence log
  (evidence/mainnet-live.jsonl, churns by design) and
  compiled .so artifacts under research/ (build outputs,
  not source, not part of this change).
- mining/mainnet_live.py diff is exactly two hunks: the
  backend_reason helper added (31 lines) and the pre-fix
  if/elif/else labelling block replaced by one call,
  reason_label, reason = backend_reason(desc). Nothing
  else in the file differs: dispatch order, backend
  selection, search, accounting, share handling and the
  backend_selected evidence event are byte-identical to
  the pre-fix file.
- The pre-fix block confirms the defect as recorded: the
  else branch set the label "AVX-512 MB" and read
  desc["v512_reason"] for every backend that was not
  v512dual or v512.
- gpu/engine.py describe() (line 2787) emits exactly the
  five reason fields the helper reads, under the exact
  names used: v512dual_reason, v512_reason, shani_reason,
  avx2_reason, cuda_context_reason (the last mapped from
  the cuda_ctx_reason attribute). The C tier has no
  probe-reason field on the dict (only the c_backend
  boolean), as claimed. ComputeEngine._try_c sets
  backend = "c" only after the library loads and all 256
  self-test digests match the Python recount
  (cpu_digest), so the helper's fixed C line states
  exactly the condition that selection already proved.
- tests file diff is exactly the _desc helper, the two
  D9 test functions, and their two calls in main().
- Integration log diff is a pure append (59 lines added,
  0 removed). Reconciliation diff touches only the D9
  entry (status sentence appended); the D10 entry is
  byte-identical to HEAD.

## Check 2: Correctness of the mapping. CONFIRMED

The engine can produce exactly seven backend values
(assignments enumerated in ComputeEngine.__init__ and the
_try_* methods): cuda, v512dual, v512, shani, avx2, c,
and the initial cpu (pure Python fallback). The auditor
executed backend_reason against simulated describe()
dicts for all seven and against real describe() dicts
from the production engine for every forced tier
(requested = auto, v512dual, v512, shani, avx2, c).
Every mapping matches the claim, including the real
probe strings: each selected backend is paired with its
own field's text, and the C tier returns the fixed line.

Edge behaviour, traced and executed:

- Unknown backend value (for example "quantum") or an
  empty string falls through to "pure Python" /
  "no native backend selected". Not reachable from
  ComputeEngine today (see the seven values above);
  see note N-2.
- A missing or None reason field for a known backend
  yields reason None (printed as "None") rather than an
  exception, because the helper uses desc.get().
  describe() always emits all five fields, and a
  selected tier's _try_* method always sets its reason
  string, so this is unreachable in production; see
  note N-1.
- A dict with no "backend" key raises KeyError from
  desc["backend"]. The pre-fix main() indexed
  desc["backend"] directly as well, so reachability is
  unchanged; describe() always includes the key.

## Check 3: Test quality. CONFIRMED

Auditor's own runs on the fixed tree:

- make test-mainnet-live: ALL PASSED, 7 ok lines (5
  pre-existing accounting checks plus the 2 new D9
  checks), matching the author's count.
- make test-agent-awareness: ALL PASSED, 50 checks. The
  author recorded 51; the difference is discrepancy D8
  exactly (one check is conditional on the node RPC
  answering; it timed out during the auditor's run and
  answered during the author's). Both counts are the
  documented behaviour, not a discrepancy in the fix.

Pre-fix failure, demonstrated in a scratch copy outside
the repo tree (/tmp/d9scratch/repo; the repo's files were
never modified): the scratch tree carried the pre-fix
mainnet_live.py fetched from remote HEAD, the fixed test
file, and copies of the .local/cpu and .local/cuda
libraries the engine loads (without them the engine
falls back to the cpu backend and an unrelated
accounting check fails first; with them the scratch
engine selects v512dual and behaves identically to the
real tree). Result: all 5 pre-existing checks pass, then
the first D9 check fails with AttributeError: module
'mining.mainnet_live' has no attribute 'backend_reason'.
That is the right failure for the right reason: the D9
checks pin behaviour that only the fix provides.

Defect reproduction: replaying the pre-fix inline block
against a simulated shani describe() prints
"compute backend: shani (native impl: shani-streams;
AVX-512 MB: V512 PROBE REASON)", byte-identical to the
author's demonstration.

Coverage note: the suite's real-describe D9 check
exercises only the auto and c modes. The auditor
extended this independently in Check 2 by executing the
helper against real describe() dicts for all six
selectable tiers; all matched their own fields.

## Check 4: Live state. CONFIRMED

- Miner pid 7872, started Mon Nov 16 07:20:19 UTC,
  running mining/mainnet_live.py --duration 86400 under
  autopilot pid 7861. The fixed file's mtime is
  2026-11-16 08:16:12 UTC, about 56 minutes after the
  process started, so the running process holds the
  pre-fix code in memory, as Entry 4 states.
- Heartbeat at 2026-11-16T08:46:14Z: miner_state
  running, restarts 0, shares_accepted_total 487 (the
  author recorded 486 after the work; the count has
  advanced since, and the status file shows the session
  live at 20,865,225 H/s). Nothing restarted the miner.
- The live status file's backend line reads
  "AVX-512 DualMask: selected: ..." for v512dual, the
  one line that is identical before and after the fix,
  consistent with Entry 4.

## Check 5: Documentation. CONFIRMED

- Entry 4's claims match the code on every point the
  auditor checked, including the statement that the
  backend line is written into the status file the
  awareness layer reads (mainnet_live.py writes
  backend_line into .local/mainnet-status.txt;
  agent/intelligence/awareness.py reads that file).
- The reconciliation D9 entry is accurate and now
  carries the FIXED 2026-11-16 status with a pointer to
  Entry 4. D10 is untouched (byte-identical diff
  context, no status change).
- README.md and docs/EVIDENCE.md do not differ from
  HEAD and contain no claim about the backend line or
  its reason labelling, so the fix introduces no drift
  there.

## Check 6: U+2014 scan. CONFIRMED

Byte-level scan (count of the 3-byte UTF-8 sequence) of
all four changed files: 0 occurrences in each. This
audit file is also written without the character.

## Notes

- N-1: The helper reads reason fields with desc.get()
  where the pre-fix code used desc["v512_reason"]
  direct indexing on the v512 and else branches. On a
  malformed dict missing a reason field, the fixed code
  prints "None" instead of raising KeyError. describe()
  always emits every field, so the difference is
  unreachable in production; recorded for completeness.
- N-2: An unrecognised backend string falls through to
  the "pure Python" label. Unreachable today, but if a
  future backend is added to gpu/engine.py without
  updating backend_reason, its session line would be
  mislabelled, the same class of defect D9 fixed. A
  future engine change should extend the helper and
  the D9 test's own_field map in the same commit.
- N-3: The author recorded a full regression of 36 of
  37 make test-all targets (test-rtl failing on the
  absent iverilog binary, the standing environment
  failure). The auditor did not re-run all 37 targets;
  the two suites named for this audit were re-run in
  full, plus the scratch pre-fix run and the mapping
  executions above. The 36 of 37 claim is consistent
  with the standing record but rests on the author's
  run.
- N-4: Registry practice. Prior audits in this
  programme live as standalone report files (for
  example research/sha256d/exp039/EXP039_AUDIT.md and
  research/PHASE002_CLOSING_AUDIT.md) and are referenced
  narratively inside experiment entries; the two
  experiment registries carry no standalone audit
  entries. Following that practice, this audit is not
  registered as an entry in either registry and is
  recorded here only.

## Bottom line

The D9 fix does exactly what Entry 4 says, nothing
more: the live miner's session backend line now names
the selected backend and quotes that backend's own
probe record, for every backend the engine can select.
The change is confined to labelling, the tests pin it
and fail without it, the documentation is accurate,
and the running miner was not disturbed. The fix takes
effect at the miner's next natural restart.
