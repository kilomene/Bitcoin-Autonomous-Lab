# Implementation Roadmap

Date: 2026-11-15. Milestone status for the Master Build Mandate
(section 14), with the evidence file for each milestone, its
dependencies, and the specified-but-unbuilt items carried forward
as future milestones with their gates.

## Milestones 0 to 6: all complete

| Milestone | Status | Evidence | Depended on |
|---|---|---|---|
| 0. Repository and research reconciliation | Complete | research/master_build/MILESTONE0_RECONCILIATION.md (implementation map, agent assessment, execution path audit, EXP-000 to EXP-043 status map, duplicates and unfinished integrations, doc-vs-code differences, reusable components, ranked gaps); seed register now consolidated into research/master_build/RESEARCH_OPPORTUNITY_REGISTER.md | The Phase 002 tree at head 3510daa4 |
| 1. Agent foundation | Complete | agent/intelligence/ package (permissions, audit, memory, planning, interface, strategy, loop, facade); tests/test_agent_intelligence.py, 86 checks, ALL PASSED (also re-run inside the later suites' reports) | Milestone 0 map |
| 2. Live mining awareness | Complete | research/master_build/MILESTONE2_LIVE_AWARENESS.md (full demonstration report: measured live rate 24,544,788 H/s over a 120 s window, no degradation flags, coverage stated and bounded, overhead measured); agent/intelligence/awareness.py; tests/test_agent_awareness.py, 50 checks | Milestone 1 |
| 3. Autonomous optimisation loop | Complete | research/master_build/MILESTONE345_BUILD.md, Milestone 3 sections (ExperimentRunner; K+W refusal at creation; batch-size experiment walked to the gate and refused with two missing items named) | Milestones 1 and 2 |
| 4. Adaptive CPU scheduler | Complete (advisory) | research/master_build/MILESTONE345_BUILD.md, Milestone 4 sections (machine profile, bake-off across all seven tiers, thread sweep, cache behaviour); agent/intelligence/scheduler.py | Milestone 1; EXP-031 characterisation |
| 5. Exact recovery and resource coordination | Complete (single machine) | research/master_build/MILESTONE345_BUILD.md, Milestone 5 sections (ResourceRegistry; 240-trial randomised campaign, coverage pairwise disjoint and equal to an independent model in every trial); agent/intelligence/resources.py | Milestone 1 permissions; EXP-035 design; EXP-038 frontier model; EXP-043 findings |
| 6. Independent end-to-end verification | Complete | research/master_build/MILESTONE6_E2E.md (chained demonstration: agent inspection, production engine, candidate, submission, node acceptance, agent-side EXP-036 verification; regtest height 1445, hash 027df87dbaf2d87100922ddb55d0d5bbd513fae8c1787152073afb56c823a34e) | Milestones 1 and 2; EXP-036 verifier; EXP-040 pipeline record |

Tests for Milestones 3 to 5: tests/test_agent_operations.py,
10,306 checks, ALL PASSED. Full-suite state for the whole build:
docs/TEST_REPORT.md.

## Future milestones: specified, not built

Each item below names its gate. None is scheduled; two are owner
decisions outright, and one is an owner decision before any work
starts.

### F1. Production wire protocol and persistent coordinator

What: the EXP-035 work distribution design as a running system: a
persistent coordinator process, a wire protocol for worker
registration, leases, progress, completion and candidate
hand-off, building on agent/intelligence/resources.py semantics
and carrying in EXP-043's two fixes (prune the lease table, bound
snapshot cost). Gate: the EXP-035 proof obligations P1 to P6 at
the protocol level, a randomised fault campaign at least at the
EXP-035 standard (exact coverage under deaths, restarts,
expiries and steals), and measurement of multi-machine overhead
before any scaling claim. Until this exists, multi-machine
coordination overhead, real-network latency and cross-machine
scaling stay UNVERIFIED.

### F2. Fleet activation

What: running workers on machines beyond this VM under the
coordinator. Gate: OWNER DECISION, explicit. The mandate and the
EXP-030 directive both hold this line: no fleet deployment until
individual resource inventory and coordination correctness are
established (F1), and activation itself is the owner's call, not
the agent's. Nothing in the current build activates, contacts or
measures any other machine.

### F3. Live start/stop controller wiring

What: wiring the L2 start_mining, stop_mining, adjust_workers
and trigger_recovery specifications to a real controller acting
through the autopilot's own mechanisms (never by killing
processes directly, per the Milestone 0 reuse directive). Gate:
an owner-approved authority decision (this changes the agent's
live authority, which today is read-only over the running
system), plus tests proving the controller cannot act outside
the permission registry, plus the standing post-integration
audit.

### F4. Candidate verification inside the GBT cycle

What: either wire mining/candidate_verify.py into
mining/engine.py mine_cycle's hit path, or record the reliance
on Core's submitblock plus best-chain verdict as the standing,
audited design. Gate: OWNER DECISION. Milestone 6 supplies the
evidence that the two verdicts agree on a real engine-produced
block; the divergence is currently documented in
docs/MINING_ENGINE.md (corrected 2026-11-15) and in the Milestone
0 reconciliation, section f, item 7.

### F5. Core multiprocess IPC template supply (register R-28)

What: push-based template supply from Bitcoin Core's
multiprocess mining IPC, with getblocktemplate retained as
fallback. Gate: OWNER DECISION on the Bitcoin Core version. The
lab pins Core 28.1; the IPC route belongs to the Core 32 era
multiprocess build, so this is an infrastructure decision about
the node itself, not an agent-layer change. Source:
research/master_build/RESEARCH_OPPORTUNITY_REGISTER.md, row
R-28 (DEFERRED).

### F6. Remaining registered opportunities

The consolidated register
(research/master_build/RESEARCH_OPPORTUNITY_REGISTER.md) carries
the forward queue: 13 NEW historical rows not yet taken up
(R-25 to R-27, R-29 to R-34 and the rest), the EXP-024b design C
integration question (owner decision, register row H-9), the
EXP-041 -mtune=znver3 measurement (needs its own experiment ID;
next unreserved EXP-044), EXP-028 ARM dispatch (blocked on ARM
hardware), and H-033-02's residual generality
(UNDER_INVESTIGATION, covered only by an inconclusive instrument
at current time budgets). Each follows the pipeline in
docs/RESEARCH_TO_PRODUCTION_PIPELINE.md when taken up.

### F7. EXP-039 refusal check on the Intel host

What: one make test-exp039 run when the SHA-less Intel Xeon
8321HC next hosts the lab, closing the standing UNVERIFIED item
on tier refusal (currently established by probe construction
only). Gate: none beyond host availability; it is a standing
note in the EXP-039 audit.

## Standing operational state (not milestones)

The live pool miner, the autopilot, the keeper cron, the pruned
mainnet node in initial block download, and the armed solo
cutover all continue independently of this roadmap. The success
criterion (a valid mainnet block, independently verified and
accepted) remains unmet; targets remain 500 GH/s minimum and
140 TH/s larger, at full height.
