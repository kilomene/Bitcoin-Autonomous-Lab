# Autonomous Mining Architecture

Date: 2026-11-15. Status: as built by the Master Build (Milestones 0
to 6). This document describes the agent-directed mining system as it
actually exists in this repository. Where the Master Build Mandate
specified something that is not yet built, the as-built versus
specified section at the end says so explicitly. Sources:
research/master_build/MILESTONE0_RECONCILIATION.md,
MILESTONE2_LIVE_AWARENESS.md, MILESTONE345_BUILD.md,
MILESTONE6_E2E.md, and the agent/intelligence/ package source.

## The shape of the system

The mandate's chain, mapped to real components:

Agent Intelligence -> Strategic Planning -> Research and
Optimisation -> Resource Coordination -> Mining Execution ->
Independent Verification -> Learning and Adaptation.

- Agent intelligence and strategic planning:
  agent/intelligence/ (the Agent facade, strategy.py).
- Research and optimisation: agent/intelligence/memory.py (research
  memory over the existing registries), loop.py (the optimisation
  cycle state machine), experiments.py (the sandboxed experiment
  runner).
- Resource coordination: agent/intelligence/resources.py
  (ResourceRegistry), scheduler.py (machine profile, backend
  bake-off, thread sweep), planning.py (task registry).
- Mining execution: the pre-existing production stack, unchanged by
  this build: mining/autopilot.py supervising
  mining/mainnet_live.py (pool path) or the GBT path through
  mining/engine.py MiningEngine, both searching through
  gpu/engine.py ComputeEngine.
- Independent verification: mining/candidate_verify.py (EXP-036),
  exposed to the agent through the typed interface, plus the
  loop's integrate gate, which requires an independent verifier
  whose author differs from the implementation author.
- Learning and adaptation: the research memory (rejected hypotheses
  refuse re-proposal), the audit trail (.local/agent-audit.jsonl),
  the task registry (.local/agent-tasks.json), and the scheduler's
  cached host profile (.local/agent-scheduler.json).

The agent layer is one Python package of logical subsystems. It is
not a set of services or processes, per the mandate's Milestone 1
instruction.

## The agent package, module by module

All under agent/intelligence/:

| Module | Role |
|---|---|
| __init__.py | The Agent facade: wires checker, audit log, task registry and MiningInterface together; default paths under .local/; lazy research memory; strategy conveniences; status(). |
| permissions.py | The authority model: Level (L1, L2, L3), ActionSpec, ACTION_REGISTRY (22 operations), PermissionChecker. |
| audit.py | AuditLog: append-only JSONL audit trail; write failures are counted, never raised. |
| memory.py | ResearchMemory: parses the two narrative experiment registries and the EXP-033 JSON registry into MemoryEntry records mapped onto the mandate statuses; lookup, keyword search, was_rejected (the loop's guard), by_status. |
| planning.py | TaskRegistry: tasks with objective, dependencies, evidence requirements, budget, success and failure criteria and a completion state; states planned, active, blocked, done, failed, cancelled with enforced transitions (dependencies must be done before active or done; done requires evidence). Persisted as JSON. |
| interface.py | MiningInterface: the typed interface to the mining system (see docs/AGENT_MINING_INTERFACE.md). |
| strategy.py | Objectives and gap accounting: TARGET_MIN_HS 500 GH/s, TARGET_LARGE_HS 140 TH/s, gap_report, next_investigations (ranks non-rejected, non-integrated memory entries by recorded expected benefit), bottleneck_summary (five cited facts from the record, each with its source file). |
| loop.py | OptimisationLoop: the 17-step cycle as a state machine with the rejected-hypothesis gate and the EXP-017 integrate gate (see docs/RESEARCH_TO_PRODUCTION_PIPELINE.md). |
| awareness.py | Awareness: read-only live mining awareness (Milestone 2): snapshot, rate_observation, degradation_check, coverage_report, observe_cycle. |
| experiments.py | ExperimentRunner (Milestone 3): sandbox creation, contained file writes, argv-only command execution with evidence capture, conservative evidence assembly, integrate-gate queries. |
| scheduler.py | Scheduler (Milestone 4): machine profile with an effective-CPU scaling estimate, measured backend bake-off through the real search path, thread sweep, result cache keyed by CPU model plus instruction-flag hash. Advisory only. |
| resources.py | ResourceRegistry (Milestone 5): worker registration and heartbeats, exact non-overlapping assignment, honest completion, reassignment of unfinished work, unique coverage by interval union. Persisted as JSON, single machine. |
| __main__.py | CLI: status and awareness subcommands. |

The pre-existing agent modules are untouched and still serve their
own roles: agent/autonomous.py (AutonomousMiner, the GBT cycle
runner with the EXP-038 checkpoint enabled) and agent/interface.py
(the read-only RPC question layer). The Milestone 0 reconciliation
assessed both in full; the new package extends rather than replaces
them.

## How the agent connects to the mining system

- To the autopilot: read-only, through the files the autopilot
  itself maintains: .local/heartbeat.json (5 s heartbeat) and
  .local/evidence-count.json (the EvidenceCounter lifetime census).
  MiningInterface.inspect_status and Awareness.snapshot parse the
  same files the autopilot's own --status flag prints. The agent
  never signals, restarts or kills the autopilot or the miner.
- To the mining engine: MiningInterface constructs
  gpu.engine.ComputeEngine through an injectable factory for
  probing and backend selection decisions (inspect_backends,
  select_backend). It does not drive MiningEngine.mine_cycle; the
  Milestone 6 demonstration drove the engine directly, with the
  agent inspecting and verifying around it.
- To ComputeEngine: dispatch probing only. Production dispatch
  remains the shipped EXP-039 order (CUDA, v512dual, v512, shani,
  avx2, C, hashlib) inside gpu/engine.py; the scheduler's bake-off
  is an advisory host profile and changes nothing in dispatch.
- To candidate verification: MiningInterface.verify_candidate_op
  calls mining.candidate_verify.verify_candidate by full module
  path (the name matters: gpu/engine.py carries an unrelated
  verify_candidate of its own, recorded in the Milestone 0
  reconciliation, section e). The verifier requires hashlib and
  pure-Python digest agreement and judges by exact integer target
  comparison; the file contains no float operations.
- To work checkpoints: MiningInterface.checkpoint_status reads a
  mining/work_checkpoint.py frontier file (GBT path only; the pool
  path has no checkpoint, by design, and the awareness layer says
  so rather than inventing one).
- To statistics: the awareness layer reads MiningStatistics
  snapshots only as republished in the evidence log's status
  events; the EXP-037 separated categories are consumed as-is and
  snapshot() still has no combined total. Lifetime share totals
  come from the EvidenceCounter census, never from a process-local
  counter.
- To probability: MiningInterface.estimate_probability and
  strategy.gap_report compute through mining/probability.py,
  including its exact-target forms.

## Authority model

Three levels (mandate section 11.1), enforced by PermissionChecker
against ACTION_REGISTRY before any operation runs:

- L1 read-only: inspection of status, machine, backends, research
  memory, plans, audit; candidate verification; probability and
  gap computation. Never mutates anything.
- L2 controlled operations: backend selection decisions, benchmark
  runs, plan writes, loop advances, and the specified start, stop,
  worker-adjustment and recovery operations. The four operations
  that would mutate production execute only through an injectable
  controller callable; the default raises NotImplementedError, so
  in the as-built system they are permission-checked
  specifications, not live controls.
- L3 experimental modifications: creating, editing and recording
  evidence for experiments, permitted only with a sandbox path
  inside the checker's sandbox root (.local/agent-experiments by
  default). An L3 grant without a contained sandbox path is
  refused.

Production integration is not any level's act: it passes the
loop's integrate gate (correctness, differential, independent
verification by a different author, and an EXP-017 verdict when a
performance claim is made) and remains a separate gated act
outside the package, under the standing post-integration audit
rule. Every interface operation writes an audit record, including
permission denials. The full registry table is in
docs/AGENT_CAPABILITIES.md.

The facade's default checker is constructed with an L3 grant
scoped to the sandbox root, so L1 and L2 operations pass and L3
operations pass only inside the sandbox.

## Data flows

Live awareness (Milestone 2), one observe_cycle:

1. Baseline snapshot from heartbeat, census, miner status file,
   evidence log tail, node getblockchaininfo (read-only, bounded
   30 s timeout, single attempt) and endpoint config; every read
   timed.
2. Rate observation over a real window: backend rate from the
   delta of the live process's backend_hashes counter between the
   two status events bracketing the window; share rate from the
   census delta; a difficulty-weighted implied rate only when
   shares were accepted in the window, labelled an estimate.
3. Final snapshot, degradation check against the baseline
   (heartbeat staleness 120 s, restarts, rejected ratio 0.05,
   rate drop fraction 0.25, node behind headers; checks without
   inputs are reported not evaluated), coverage report.
4. The cycle is written to the audit log and to the standing
   planning task live-awareness-observe.

Optimisation loop (Milestone 3): a hypothesis becomes a LoopRecord;
advances are permission-gated (L2 loop_advance) and audited; the
hypothesise step is refused with a citation when the keywords all
match a REJECTED memory entry; the experiment runs inside its
sandbox through ExperimentRunner; evidence JSON files are assembled
conservatively; the integrate gate at record_evidence either
advances the record to integrated (a record decision only) or
refuses with the missing items named. Rollback is available from
the integrated and monitored states.

Resource coordination (Milestone 5): workers register with machine
identity, CPU model, effective CPUs, instructions and backend;
assignments are (job identity, extranonce space, nonce range,
batch grid) and are refused on any overlap with an active or
completed assignment for the same job and extranonce space, on a
nonce end above 2^32, or for an unknown worker; completion counts
only when batches_completed equals batches_total; reassignment
moves the unfinished remainder and completes nothing; unique
coverage is the interval union of completed ranges plus completed
prefixes of active ranges, with repeated computations counted
separately and never as coverage.

End-to-end verification (Milestone 6): agent inspection (L1,
audited) -> regtest node -> production MiningEngine.mine_cycle ->
submitblock plus best-chain acceptance inside the engine ->
agent-side independent verification of the accepted block's header
through mining/candidate_verify.py, also routed through the
interface so the audit trail carries it -> verify_chain_acceptance
confirmation. Recorded: height 1445, hash
027df87dbaf2d87100922ddb55d0d5bbd513fae8c1787152073afb56c823a34e.
Full record: research/master_build/MILESTONE6_E2E.md.

## As built versus specified

Built and demonstrated in this build: the Milestone 1 foundation
(permissions, audit, memory, planning, interface, strategy, loop),
Milestone 2 live awareness against the real miner, the Milestone 3
loop made executable with a real sandboxed experiment and two real
gate refusals, the Milestone 4 advisory scheduler (profile,
bake-off, thread sweep, cache), the Milestone 5 single-machine
resource registry with a 240-trial exactness campaign, and the
Milestone 6 chained regtest demonstration.

Specified by the mandate but NOT yet built:

- Production wire protocol for distributed work (EXP-035 specified
  it; no network protocol exists in the agent layer or the
  registry). Multi-machine coordination overhead, real-network
  propagation latency and cross-machine linear scaling remain
  UNVERIFIED (EXP-043 closed only the in-process and loopback
  parts, on this VM).
- Persistent coordinator: the ResourceRegistry is a
  single-process, single-machine JSON store. There is no
  coordinator service, no lease server, and no worker process
  that connects to it.
- Live start/stop controller wiring: start_mining, stop_mining,
  adjust_workers and trigger_recovery are L2 specifications that
  execute only through an injected controller; no production
  controller is wired, so the agent cannot start, stop or
  reconfigure the live miner. The autopilot and the keeper cron
  remain the live supervision layer.
- Fleet behaviour: no fleet agent was activated, contacted or
  measured. Fleet activation is the owner's decision. Nothing in
  this build speaks to a second machine.
- GBT-path internal verification: mining/engine.py still does not
  call mining/candidate_verify.py inside mine_cycle; Milestone 6
  verified from outside the engine and showed the two verdicts
  agree. Moving verification inside the cycle is an owner decision
  item (see docs/IMPLEMENTATION_ROADMAP.md).
- Stratum V2, job declaration, and push-based template supply
  (historical register R-21, R-29, R-28): investigated and
  registered, not implemented. R-28 additionally needs an owner
  decision on the Bitcoin Core version.

## Performance position, stated as required

The targets are objectives, not established capabilities: 500
GH/s minimum, 140 TH/s larger. Best live observation during this
build: 24,544,788 H/s measured by the Milestone 2 awareness cycle
over a 120 s window on the production search path (category E
conditions, contended VM), which is 0.004909 percent of 500 GH/s
(gap factor about 20,371 such systems). The standing verified live
figure is about 20.6 MH/s on v512dual. No mainnet block has been
found; the balance is 0 BTC; pool shares are not blocks. The
primary success criterion remains unmet.
