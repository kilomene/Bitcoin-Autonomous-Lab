# Phase Master Build Closing Audit

Date: 2026-11-15 (run 2026-11-16 about 01:05 to 01:25 UTC).
Auditor: independent closing auditor, not an author of any code
or document under audit (owner standing rule: after any
production integration, an independent agent audits the actual
production code). Scope: the NOVA SHA-X Master Build (owner
directive 2026-11-15), Milestones 0 to 6 plus the deliverables
pass. Remote head before this build:
3510daa47d426e7e235fe04cecce314eff8b376a (re-confirmed live at
audit start). Sources: research/master_build/ (all milestone
reports), docs/AUTONOMOUS_MINING_ARCHITECTURE.md,
docs/AGENT_CAPABILITIES.md, docs/AGENT_MINING_INTERFACE.md,
docs/RESEARCH_TO_PRODUCTION_PIPELINE.md,
docs/IMPLEMENTATION_ROADMAP.md, docs/TEST_REPORT.md,
docs/INTEGRATION_REPORT.md, and the agent/intelligence/ source.
Nothing was fixed by this audit; findings go back to the
parent. The live miner, autopilot, mainnet node, endpoint
config and solo marker were not touched.

## Verdict: PASS WITH NOTES

Defects: 0. Notes: 6 (N-1 to N-6 below). Every check below was
executed by the auditor with the auditor's own probes,
recounts and recomputations, not transcribed from the build's
reports.

## Check 1: Production integrity: CONFIRMED

Method: bal_github.py imported read-only (local_files(),
remote_tree(), blob_sha()); its main() was never run. Remote
head verified first: 3510daa47d426e7e235fe04cecce314eff8b376a,
exactly the pre-build head. Local comparable files 964, remote
917, differing or local-only entries 53, remote-only entries 0.

Protected paths: zero differences under mining/, gpu/,
blockchain/, dashboard/, scripts/, and in agent/autonomous.py,
agent/interface.py, and tests/ other than the three new agent
suites. Every differing file sits inside the authorised set:
agent/intelligence/ (13 modules, local only), the three
tests/test_agent_*.py suites (local only), docs/ (new
deliverables plus the ARCHITECTURE.md, EVIDENCE.md and
MINING_ENGINE.md dated fixes), research/master_build/ (local
only), README.md and Makefile (differ, authorised).

Two exception classes sit outside the authorised set and are
not Master Build changes (note N-1): evidence/mainnet-live.jsonl
differs (the live miner's own log, continuous churn), and 13
.so files under research/sha256d/exp032/ and
research/sha256d/exp041/src/ are local only. Their mtimes
(2026-11-15 09:37 UTC and 20:49 to 21:11 UTC) predate the
Master Build window (first Master Build file 2026-11-16
00:24 UTC); they are Phase 002 era build artifacts that the
push convention excludes as binaries.

## Check 2: Permissions: CONFIRMED

The auditor's own probe against
agent/intelligence/permissions.py and the default Agent facade:

- Unknown operation: refused ("unknown operation; not in the
  action registry").
- L2 operation (start_mining) under an L1 grant: refused
  (requires L2, caller holds L1).
- L3 operation (create_experiment) with a sandbox path outside
  the checker's sandbox root: refused (path outside root named
  in the refusal). Control: the same operation inside the root
  was permitted.
- start_mining and stop_mining through the default facade:
  both raised the Milestone 1 NotImplementedError. The miner
  was untouched: autopilot pid 4904 and miner pid 4912
  identical before and after, miner state running.

## Check 3: Research memory: CONFIRMED

Independent recount from a fresh ResearchMemory: 98 entries
indexed, 0 unparsed, 0 missing sources. Status mix:
EXPERIMENTAL 46, REJECTED 19, PROVEN 32, UNDER_INVESTIGATION 1,
INTEGRATED 0 (the zero is the documented parsing gap, note
N-2). EXP-014 reads REJECTED. EXP-015 reads REJECTED.
H-033-02 reads UNDER_INVESTIGATION, not PROVEN.
was_rejected(["K+W", "constant folding"]), the keyword pair
the milestone reports record as the pair that fired, returns
EXP-014 with status REJECTED. The live ACTION_REGISTRY holds
22 ActionSpecs (11 L1, 8 L2, 3 L3), exactly the count and mix
docs/AGENT_CAPABILITIES.md claims.

## Check 4: Loop gates: CONFIRMED

The auditor's own bundles against validate_integrate_evidence
and OptimisationLoop:

- (a) Complete synthetic bundle, independent verifier
  different from the implementation author: ACCEPTED
  (missing list empty).
- (b) Same bundle with verifier equal to author: REFUSED,
  naming "independent verification by an author other than
  the implementation author".
- (c) Performance-claim bundle whose EXP-017 relative
  improvement interval crosses zero (ci_low -0.05): REFUSED,
  naming the interval-entirely-above-0 requirement.
- (d) A fresh loop record carrying the K+W folding keywords:
  refused at the hypothesise exit, citation EXP-014
  ("EXP-014: K+W constant folding for template-fixed MB
  rounds", status REJECTED, source the extreme optimisation
  registry).

## Check 5: Resources: CONFIRMED

The auditor's own randomised campaign against a fresh
ResourceRegistry in a temp directory: 150 trials, 2 to 5
workers, 1 to 6 assignments each, with partial completions,
worker deaths expressed as reassignments (60 percent of
partials), and repeat-computation noise. Zero failures:
completed ranges pairwise disjoint in every trial; the
registry's unique_coverage equalled the auditor's independent
interval-union model in every trial; a partial completion
never read completed; a reassignment never marked moved work
complete and never lost recorded batch progress; a full
completion always read completed.

## Check 6: Awareness honesty: CONFIRMED

- python3 -m agent.intelligence status: census 415 accepted,
  8 rejected, 423 share results, byte-equal in value to
  .local/evidence-count.json read at the same moment.
  Running verdict true, consistent with the heartbeat
  (miner_state running, heartbeat age 4.9 s, well under the
  120 s staleness bound).
- Awareness snapshot at window 0 (observe_cycle, no waiting):
  census consistent at 415 / 8 / 423, autopilot running,
  pids 4904 / 4912. The mainnet node RPC timed out during
  this snapshot and was reported unreachable, not as a stale
  height (note N-4).
- Milestone 2 rate method verified by the auditor's own
  recomputation from evidence/mainnet-live.jsonl: an adjacent
  pair of status events (2026-11-15T21:21:50Z to 21:22:52Z)
  gives backend_hashes 603,979,776 to 1,845,493,760, delta
  1,241,513,984 over 61.268 s, rate 20,263,556 H/s. The
  arithmetic shape is exactly the documented method (delta of
  the backend_hashes counter over the interval between the
  two bracketing status events). Cross-check of the
  Milestone 2 headline itself: its recorded delta
  2,969,567,232 divided by its reported 24,544,788.25 H/s
  gives 120.99 s, consistent with the stated 120 s window.
  The exact 24.5 MH/s figure was not re-derived, per brief.

## Check 7: Milestone 6 reproduction: CONFIRMED

The auditor ran research/master_build/m6_e2e_demo.py
(exit 0, demonstration_ok true, 3 agent audit records
appended, the documented count). It mined a NEW regtest
block: height 1493, hash
5471636228e1ecc325c17df9e1a57cc48689f69388c9a3c9443bc439ce846565
(tip before the run: 1492). Independent verification by the
auditor against the regtest node: getblockchaininfo reports
blocks 1493 on chain regtest; getbestblockhash equals the
reported hash; the auditor re-ran
mining/candidate_verify.verify_candidate on the block's
80-byte header fetched from the node: classification
block_candidate, digests agree, valid header, meets network
target, and the digest display hex equals the block hash.
getblock reports height 1493.

## Check 8: Bake-off plausibility: CONFIRMED

Source inspection of agent/intelligence/scheduler.py:

- Measurement runs through the real production search path:
  _measure calls engine.search_first_counted(BENCH_HEADER,
  BENCH_TARGET, 0, count) on a ComputeEngine (scheduler.py
  line 147), category E as labelled in the module.
- Advisory only: a full grep of agent/intelligence/ finds no
  assignment into gpu/engine dispatch or backend state and no
  write to the endpoint config anywhere (awareness reads the
  endpoint config through load_config only). The bake-off
  writes only its own cache file and an audit record, and
  returns a winner it never applies. One transient exception,
  note N-3: _measure sets the gpu.engine module global
  C_THREADS on the scheduler's own engine instances and
  restores the saved value in a finally block, the documented
  EXP-031 load-probe mechanism.
- Cache key: _cache_key returns the CPU model name joined
  with the first 16 hex digits of the SHA-256 of the sorted
  instruction flags, so the key includes CPU model and flags.

## Check 9: Documents: CONFIRMED (all five spot-checks)

1. Dispatch order: docs/ARCHITECTURE.md reads "CUDA when a
   real device passes the self-test, then v512dual, v512,
   shani, avx2, the C batch backend, then Python hashlib".
   gpu/engine.py's constructor cascade (v512dual, then v512,
   then shani, then avx2, then C, with CUDA first and hashlib
   as the floor) matches exactly.
2. Roadmap: docs/IMPLEMENTATION_ROADMAP.md marks Milestones
   0 to 6 Complete. Every cited evidence item is present:
   MILESTONE0_RECONCILIATION.md, the agent/intelligence
   package with tests/test_agent_intelligence.py (Milestone
   1), MILESTONE2_LIVE_AWARENESS.md, MILESTONE345_BUILD.md
   (Milestones 3, 4 and 5), MILESTONE6_E2E.md.
3. Register rows: the consolidated register claims 280 rows.
   The auditor counted data rows per section: H-033 14,
   Phase 001 9, X-series 116, Y-series 108, historical 33
   (35 minus R-01 and R-02 merged, as the register states).
   Total exactly 280.
4. TEST_REPORT's 35 of 36: in
   research/master_build/TEST_ALL_RUN_2026-11-15.txt the
   auditor counted 35 suite PASSED lines (11 before the
   test-rtl halt, 24 in the individually run continuation)
   and exactly one failure, test-rtl, whose failure text is
   the assertion carrying "/bin/sh: 1: iverilog: not found".
   (A naive grep counts 36 PASSED strings because the failing
   assertion quotes the expected pass string; the per-target
   count is 35.)
5. INTEGRATION_REPORT file list: all 33 listed created files
   exist at exactly the listed byte sizes; all 13
   agent/intelligence modules on disk appear in the list and
   none is missing; the Makefile claim also verifies
   (test-all depends on 36 targets).

## Check 10: Global: CONFIRMED

Byte scan of all 39 files on the INTEGRATION_REPORT list plus
the modified files (Makefile, README.md, docs/ARCHITECTURE.md,
docs/MINING_ENGINE.md, docs/EVIDENCE.md): U+2014 occurrences
zero. Secret scan (values loaded in memory only, never
printed): the mainnet RPC password from
.local/mainnet/node-config.json appears in no scanned file;
no wallet private key or WIF material appears in any scanned
file. The only wallet-field presence found is the lab's
public payout address in README.md, docs/EVIDENCE.md and
research/master_build/MILESTONE2_LIVE_AWARENESS.md, which is
the published mining identity, not secret material.

Live state at audit close: autopilot pid 4904 and miner pid
4912 both running (processes verified in ps), miner state
running, census 415 accepted and 8 rejected, at the required
floor of 415 accepted.

## Defects

None. Defect list is empty.

## Notes

- N-1. Check 1's two exception classes (the live evidence log
  and 13 pre-build .so artifacts under research/sha256d/) are
  outside the authorised set by construction, not by build
  action. A future push manifest should keep excluding both,
  as the Phase 002 push did.
- N-2. The research memory's status parser assigns INTEGRATED
  to 0 of 98 entries although at least ten experiments are
  integrated per the Milestone 0 source map. Already disclosed
  by the build itself (INTEGRATION_REPORT discrepancy 3 and
  the AGENT_CAPABILITIES limitations). The REJECTED gate the
  loop depends on is unaffected; all four loop gate probes in
  Check 4 behaved correctly.
- N-3. scheduler._measure transiently mutates the gpu.engine
  module global C_THREADS (set, then restored in a finally
  block) on engine instances the scheduler itself constructs.
  This is a thread-count knob, not a dispatch mutation, and
  the agent process is separate from the miner process, so
  production cannot observe it. Recorded so the "no mutation"
  claim is read precisely: no dispatch, backend or endpoint
  state is mutated anywhere in agent/intelligence/.
- N-4. During this audit the pruned mainnet node's RPC timed
  out under IBD load (the standing pattern on this VM). The
  awareness layer reported the node unreachable with the
  error, which is the honest behaviour the module promises.
  No height was fabricated at any point.
- N-5. The Milestone 2 report counts its suite as 50 checks
  while the full run prints 51. Already disclosed by the
  build (INTEGRATION_REPORT discrepancy 2, docs/TEST_REPORT).
- N-6. This audit's own runs advanced shared state exactly as
  designed: the regtest chain moved 1492 to 1493 (Check 7),
  and the status and awareness reads appended agent audit
  records. The original Milestone 6 block (height 1445, hash
  027df87dbaf2d87100922ddb55d0d5bbd513fae8c1787152073afb56c823a34e)
  stands in MILESTONE6_E2E.md; the reproduction block at 1493
  is additional evidence, not a replacement.

## Standing state restated

Nothing in this audit changes the programme's honest
position: the success criterion (a valid, independently
verified, submitted and accepted mainnet block) is not met;
the pool balance is 0 BTC; pool shares stand at 415 accepted
and 8 rejected; the targets stand at full height (500 GH/s
minimum, 140 TH/s larger) with the measured gap recorded in
the build's own documents. Fleet activation remains the
owner's decision and was not exercised.
