# Integration Report: Master Build

Date: 2026-11-15. Every file created and modified by the Master
Build (Milestones 0 to 6 plus the deliverables pass), the
architecture changes, and the integration evidence. File lists
are transcribed from the milestone reports' own file tables and
verified against the tree on 2026-11-15; sizes are bytes in the
tree at verification time.

## Files created

Agent package (Milestone 1 foundation; Milestone 2, 3, 4, 5
modules as marked):

| File | Bytes | Milestone |
|---|---|---|
| agent/intelligence/__init__.py | 3,701 | 1 (facade) |
| agent/intelligence/__main__.py | 1,892 | 1 (CLI; awareness subcommand added in 2) |
| agent/intelligence/permissions.py | 8,319 | 1 |
| agent/intelligence/audit.py | 3,561 | 1 |
| agent/intelligence/memory.py | 11,217 | 1 |
| agent/intelligence/planning.py | 8,231 | 1 |
| agent/intelligence/interface.py | 17,599 | 1 |
| agent/intelligence/strategy.py | 5,823 | 1 |
| agent/intelligence/loop.py | 10,164 | 1 (cycle shape; exercised in 3) |
| agent/intelligence/awareness.py | 34,978 | 2 |
| agent/intelligence/experiments.py | 12,534 | 3 |
| agent/intelligence/scheduler.py | 14,882 | 4 |
| agent/intelligence/resources.py | 13,308 | 5 |

Test suites (each wired into the Makefile and test-all):

| File | Bytes | Covers |
|---|---|---|
| tests/test_agent_intelligence.py | 17,906 | Milestone 1 (86 checks) |
| tests/test_agent_awareness.py | 14,620 | Milestone 2 (51 checks in the 2026-11-15 full run) |
| tests/test_agent_operations.py | 14,910 | Milestones 3, 4, 5 (10,306 checks) |

Research records (research/master_build/):

| File | Bytes |
|---|---|
| MILESTONE0_RECONCILIATION.md | 53,172 |
| RESEARCH_OPPORTUNITY_REGISTER_SEED.md | 49,675 |
| HISTORICAL_MINER_RESEARCH.md | 60,804 |
| HISTORICAL_OPPORTUNITY_REGISTER.md | 19,111 |
| MILESTONE2_LIVE_AWARENESS.md | 17,760 |
| MILESTONE345_BUILD.md | 12,603 |
| MILESTONE6_E2E.md | 10,471 |
| m6_e2e_demo.py | 7,962 |
| RESEARCH_OPPORTUNITY_REGISTER.md | 68,367 |
| EXPERIMENT_REPORTS/INDEX.md | 3,600 |
| TEST_ALL_RUN_2026-11-15.txt | 49,568 |

Deliverable documents (docs/):

| File | Bytes |
|---|---|
| AUTONOMOUS_MINING_ARCHITECTURE.md | 14,343 |
| AGENT_CAPABILITIES.md | 11,537 |
| AGENT_MINING_INTERFACE.md | 10,465 |
| RESEARCH_TO_PRODUCTION_PIPELINE.md | 9,436 |
| IMPLEMENTATION_ROADMAP.md | 7,161 |
| TEST_REPORT.md | 6,693 |
| INTEGRATION_REPORT.md | this file |

## Files modified

- Makefile: three test targets added across the build
  (test-agent-intelligence in Milestone 1, test-agent-awareness
  in Milestone 2, test-agent-operations in Milestones 3 to 5);
  test-all now depends on 36 targets. No other Makefile change.
- agent/intelligence/__main__.py: the awareness subcommand added
  in Milestone 2 (the status subcommand's behaviour unchanged).
- Deliverables-pass documentation fixes (2026-11-15), each the
  smallest correct edit, with history preserved as dated notes:
  docs/ARCHITECTURE.md (dispatch order in the module map;
  EXP-039 kernel files and mining/endpoint_config.py added to the
  mining entry; agent/autonomous.py and agent/intelligence/ added
  to the agent entry; dashboard/server.py recorded as existing;
  decision 3 marked superseded by a dated update),
  docs/MINING_ENGINE.md (EXP-039 tiers added to the 2026-11-15
  update's dispatch sentence; step 5's candidate re-verification
  sentence corrected with a dated note stating what engine.py
  actually does), README.md (research map extended to exp030 to
  exp043 plus research/master_build; a dated 2026-11-15 update
  added under the 2026-11-13 at-a-glance status; test target
  counts updated to 36 with the test-rtl environment caveat in
  three places), docs/EVIDENCE.md (target count updated to 36
  with the same caveat).

No production code file was created or modified by the Master
Build: mining/, gpu/, agent/autonomous.py and agent/interface.py
are untouched, as every milestone report states and as the
Phase 002 closing audit's stability check pattern confirms for
the earlier milestones.

## Architecture changes

- A new logical layer, agent/intelligence/, now sits above the
  existing mining stack: permissions and audit (Milestone 1),
  research memory over the existing registries, a task registry,
  a typed read-mostly interface over the autopilot's own state
  files, the ComputeEngine probe, the EXP-036 verifier, the
  EXP-038 checkpoint reader and the probability module.
- Live awareness (Milestone 2) is a read-only consumer of the
  autopilot heartbeat, the EvidenceCounter census, the miner
  status file, the evidence log and a bounded read-only node RPC.
- The optimisation cycle (Milestone 3) exists as an enforced
  state machine with a rejected-hypothesis gate and the EXP-017
  integrate gate; experiments execute only inside sandboxes under
  .local/agent-experiments/.
- The scheduler (Milestone 4) is advisory: it measures and
  caches a host profile; production dispatch is unchanged.
- The resource registry (Milestone 5) is a single-machine
  component implementing EXP-035 assignment semantics; no wire
  protocol or persistent coordinator exists.
- Nothing about the mining engine, its determinism, its dispatch
  order, or the live supervision (autopilot plus keeper cron)
  changed.

## Integration evidence

- Suites: test-agent-intelligence ALL PASSED (86 checks),
  test-agent-awareness ALL PASSED (51 checks in the full run),
  test-agent-operations ALL PASSED (10,306 checks, including the
  240-trial resources campaign). Full suite: 35 of 36 targets
  pass; test-rtl fails for the standing environmental reason
  (iverilog absent). Full record: docs/TEST_REPORT.md and
  research/master_build/TEST_ALL_RUN_2026-11-15.txt.
- Milestone 6 chained demonstration: agent inspection (L1,
  audited) -> production MiningEngine cycle on regtest ->
  submitblock acceptance -> agent-side independent verification
  through mining/candidate_verify.py -> chain confirmation.
  Accepted block: height 1445, hash
  027df87dbaf2d87100922ddb55d0d5bbd513fae8c1787152073afb56c823a34e.
  The run appended exactly 3 records to the agent audit log.
  Full record: research/master_build/MILESTONE6_E2E.md.
- Live miner undisturbed: no milestone touched, restarted or
  signalled the live miner, autopilot or nodes. The
  EvidenceCounter census (accepted / rejected) across the build
  window, from the milestone reports and the tree: 406 to 407
  accepted at the Milestone 1 observation era, 410 accepted / 8
  rejected at the Milestone 2 demonstration (2026-11-16T00:35
  UTC), 411 / 8 in the Milestone 6 output (00:38 UTC), and 415 /
  8 after this deliverables pass's suite run. The rejected count
  never moved; the accepted count only grew, which is the live
  miner mining through the whole build.
- Gate behaviour demonstrated against the real system, not
  fixtures only: the K+W folding refusal with the EXP-014
  citation, and the batch-size experiment's integrate refusal
  naming exactly two missing evidence items (both in
  docs/RESEARCH_TO_PRODUCTION_PIPELINE.md).

## Discrepancies found while writing these deliverables

Recorded plainly, per the build's rules:

1. The deliverables brief described the permission registry as
   23 ActionSpecs. The actual ACTION_REGISTRY in
   agent/intelligence/permissions.py contains 22 (11 L1, 8 L2,
   3 L3), counted from the live registry. docs/AGENT_CAPABILITIES
   .md carries the true table and count.
2. The Milestone 2 report counts its suite as 50 checks; the
   2026-11-15 full run prints 51 checks for
   test-agent-awareness. Noted in docs/TEST_REPORT.md.
3. The research memory's status parser assigns INTEGRATED to
   zero of 98 parsed entries, although at least ten experiments
   are integrated per the Milestone 0 source-level map. This is
   the Milestone 1 parsing gap, documented with its mechanism in
   docs/AGENT_CAPABILITIES.md (limitations). The loop's REJECTED
   gate is unaffected.
4. make test-all cannot run past its first failing target, so a
   naive full-suite run stops at test-rtl (target 12 of 36).
   docs/TEST_REPORT.md records how the remaining targets were
   completed and why.
