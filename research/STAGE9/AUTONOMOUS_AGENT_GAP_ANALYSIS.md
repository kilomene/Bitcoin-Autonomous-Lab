# Stage 9.4: Autonomous Agent Gap Analysis and Architecture Completion

Stage: NOVA SHA-X Stage 9.4 (autonomous agent capability and
architecture completion). Baseline: remote HEAD
9d65efe86f1ed119ea9b11eb3aea098f50f52ad4, on top of the
Stage 9.1 baseline (REPOSITORY_BASELINE.md), the Stage 9.2
promotion decisions (PRODUCTION_PROMOTION_DECISIONS.md) and
the Stage 9.3 current-HEAD test audit
(CURRENT_HEAD_TEST_AUDIT.md, including its Corrections
section). Method: every Part A claim is from source read at
this HEAD, with file and line evidence. Every Part B claim
is from work executed in this stage, with raw evidence under
research/STAGE9/evidence_94/.

Hard limits honoured: fleet mining was not activated;
experimental backend dispatch was not enabled; the live
mainnet stack was not touched (no live config changed, the
B2 publisher ships default-off and no production caller
enables it); all experiments ran on isolated scratch state
under .local/stage9/ or, for B1, against a scratch work
source served by a scratch coordinator instance; benchmarks
and suites ran one at a time.

Live stack, read-only observation. Before (2026-11-18T06:10Z):
heartbeat autopilot_pid 2830, miner_pid 2833, miner_state
running, shares_accepted_total 1066. After (2026-11-18T06:33Z):
same pids, shares_accepted_total 1069. Shares non-decreasing
throughout; the same miner process (uptime continuous) ran
for the whole stage. Note: these pids differ from the
parent record earlier in the night (4878/4881); a VM
replacement and keeper restore happened before this stage
began, not during it. The B3 contention window slowed share
production (3 shares over the stage) but never stopped it.

## Part A: gap analysis

### C1. Agent-owned lifecycle

Question: can the agent start, stop, restart and health-check
its own mining and research components without the cron
keeper or a human?

What exists, in source:

- A real, verifying lifecycle controller exists in the agent
  package. agent/intelligence/controller.py MiningController:
  inspect() at line 248 reads the autopilot's published state
  (heartbeat file plus lock pid) and verifies pids against
  /proc cmdlines; start() line 349, stop() line 389 and
  restart() line 435 act through scripts/autopilot.sh and
  verify the postcondition from the heartbeat before
  reporting success; recover() line 612 implements the fault
  taxonomy (miner down, autopilot down, crash loop,
  correctness halt) and signals only a pid read from the
  autopilot's own state whose cmdline verifies
  (signal_verified). select_backend (line 485) and
  refresh_job (line 535) return honest UNSUPPORTED refusals,
  as recorded in Stage 9.2; they are correct behaviour, not
  gaps.
- The package facade wires this controller by default
  (agent/intelligence/__init__.py, Agent class): the L2
  controlled operations act on the real autopilot when a
  caller invokes them.
- Health-check surfaces exist and are read-only:
  MiningController.status(), MiningInterface.inspect_status
  over the heartbeat and evidence census, and the CLI
  (agent/intelligence/__main__.py: status, machine, backends,
  gap, awareness, mode, control-status).
- The GBT research miner is agent-run: agent/autonomous.py
  AutonomousMiner.run_cycles (line 90) benchmarks, selects a
  backend, runs MiningEngine cycles, adapts batch size from
  measured batch times and logs decisions. It is regtest-only
  by chain guard and is launched by a human or a test; it
  manages no processes.

What is missing:

- No agent process runs the controller. There is no daemon,
  service or loop anywhere in the repo that calls start,
  stop, restart or recover on the live stack; the CLI is
  read-only, and the controller is exercised by test suites
  against isolated byte-copy instances (Stage 7 record) and
  by the human-run Stage 8 demonstration script
  (research/EXTREME_RESEARCH/stage8_demonstration.py,
  MiningController constructed at line 213, also against
  isolated instances, not a production path), and by nothing
  else. If the autopilot dies, the agent brain
  does nothing: recovery today comes from the layers below.
- DEF-9.2-4 (the Stage 8 run-1 finding): the production GBT
  path in mining/engine.py published no status between cycle
  start and cycle completion, so the awareness layer's rate
  observation starved. The pool path has its own 10 s status
  publication (mining/mainnet_live.py line 390). Closed in
  this stage by B2, as an opt-in capability; see Part B.

What is delegated today:

- mining/autopilot.py is the live lifecycle owner: its own
  process supervision (run() line 466; heartbeat every 5 s,
  watchdog poll 1 s, hung window 300 s, exponential backoff,
  session rotation, single-instance flock, self-update inert
  on this checkout). It is a supervisor program, not the
  agent brain: it makes no decisions beyond restart policy.
- Boot persistence is systemd's (scripts/autopilot.sh
  install-service and the bal-*.service units).
- The outermost layer is the external cron keeper (outside
  the repo), which restarts the autopilot and the node. The
  keeper-rule decision of 2026-11-17 (restart on RPC silence)
  is executed by that layer, not by anything in this repo.

Gap verdict C1: the agent OWNS a verified lifecycle
vocabulary but does not OPERATE it. Lifecycle on the live
stack is delegated to autopilot plus systemd plus the
external keeper.

### C2. Research loop

Question: can the agent run a full experiment cycle itself
(hypothesis, predeclaration, execution, measurement under
EXP-017 discipline, verdict, registry update)?

Stage-by-stage mapping:

- Hypothesis and predeclaration: agent/intelligence/loop.py
  OptimisationLoop is a gated state machine over records
  (observe, hypothesise, check prior research, analyse
  source, derive change, mathematical correctness, isolated
  implementation, correctness tests, controlled measurement,
  compare baseline, independent verification, block
  acceptance, record evidence, integrated, monitor). The
  hypothesise gate refuses hypotheses matching REJECTED or
  INTEGRATED research memory entries, with the citation.
  Predeclaration in the EXP-017 sense (sessions, pair count,
  margin fixed before measurement) is a property of the
  experiment designs in research/, written by humans; the
  loop records a performance_claim flag and enforces the
  verdict shape at the gate, but no code writes a
  predeclaration.
- Execution: agent/intelligence/experiments.py
  ExperimentRunner creates a real sandbox per experiment,
  runs argv commands only through the OS-isolated sandbox
  (agent/intelligence/sandbox.py; refused when isolation is
  unavailable), enforces path containment, and re-checks the
  load-shedding mode at every command boundary.
- Measurement and verdict: the integrate gate
  (loop.validate_integrate_evidence) enforces the strict
  evidence schema: correctness and differential verification
  records, an independent verification record whose author
  differs from the implementation author and whose HMAC
  signature verifies against the verifier key
  (agent/intelligence/verifier.py), one artifact hash and
  source commit binding the whole bundle, and, for a
  performance claim, an EXP-017 verdict (at least 3 sessions,
  pooled ratio, confidence interval for the relative
  improvement entirely above 0, NaN and infinity rejected).
  ExperimentRunner.assemble_evidence is conservative (a
  failing record wins over a passing one) and
  attempt_integrate only asks the gate; the runner never
  integrates and never edits production code.
- Evidence integrity: every run and gate decision appends a
  hash-chained record to a ledger outside the sandbox, with
  an HMAC-signed external anchor that makes tail truncation
  detectable (experiments.py verify_ledger).
- Registry update: research memory
  (agent/intelligence/memory.py) parses the narrative
  registries and overlays the derived integration registry
  (agent/intelligence/integrations.py). Regeneration is a
  manual step (python3 -m agent.intelligence.integrations)
  after the Stage 0 registry changes; the experiment
  registries themselves (research/sha256d/experiment_registry
  and the Stage 9.1 closure ledger) are human-maintained
  documents. No code path in the loop writes a verdict back
  into any registry.

What is missing: a driver. ExperimentRunner and
OptimisationLoop are invoked only by tests
(tests/test_agent_intelligence.py,
tests/test_agent_operations.py, tests/test_agent_security.py,
tests/test_agent_controller_modes.py, the last constructing
an ExperimentRunner at line 479) and by the human-run Stage 8
demonstration script
(research/EXTREME_RESEARCH/stage8_demonstration.py,
ExperimentRunner constructed at line 567, a demonstration
against isolated instances, not a production path), and by
nothing in production: no process proposes a
hypothesis, commissions a sandbox run, assembles evidence,
seeks an independent verification, or records the outcome
without a human or a test calling each step. The independent
verification itself is a separate service act (the verifier
key holder), by design.

Gap verdict C2: every stage of the cycle exists as enforced
machinery; the cycle is not self-driving. It is an executable
loop under direction, with the integrate decision and the
registry update deliberately human (or external-service)
acts.

### C3. Resource management and load shedding

Question: does anything measure host load or CPU contention
and shed or defer work?

What exists, in source:

- agent/intelligence/modes.py ModeManager: a persisted
  three-mode machine (NORMAL, BROWNOUT, CRITICAL) driven by
  two real signals: the 1-minute load average over the
  EXP-031 effective-CPU estimate (brownout at ratio 1.5,
  critical at 3.0; lines 79 to 86) and the miner backend rate
  against its standing baseline (brownout at 0.75, critical
  at 0.50). Entry needs 2 consecutive confirming samples;
  exit steps down one level at a time after a sustained
  clear window (300 s default). The mode gates discretionary
  work kinds (experiment, bake_off, planning, awareness_full;
  status is never shed) and never touches mining.
- The gates are wired inside the package: OptimisationLoop
  refuses transitions into the execution states while the
  mode sheds (loop.py advance, mode_gate), ExperimentRunner
  refuses create_experiment and re-checks at every
  run_command boundary (experiments.py), and the facade
  passes the mode gate into every loop it builds
  (__init__.py Agent.loop).
- Signal supply exists: agent/intelligence/awareness.py
  _update_mode (line 713) feeds the machine os.getloadavg()
  and the observed miner rate, exactly the production signal
  set, during observe_cycle.
- EXP-058's PID work controller (mining/pid_control.py
  AdaptiveWorkController) exists as a proven-on-paper
  controller for worker count and span; per Stage 9.2 it
  ships disabled, its interval-only scale-up cascade is an
  established negative, and it actuates nothing live.

What is missing:

- Nothing runs awareness continuously. observe_cycle is
  invoked by the CLI (python3 -m agent.intelligence
  awareness) when a human asks; there is no daemon feeding
  the mode machine in production, so on the live stack the
  mode sits wherever it was last left and sheds nothing.
- The bake-off scheduler notices contention but does not
  shed: agent/intelligence/scheduler.py _contention_note
  (line 116) only annotates results with the fact that the
  live miner was running.
- No component measures per-process CPU contention directly;
  the signals are load average and achieved rate only.
- Measured evidence of the gap: the Stage 9.3 audit's D-93-2.
  test-task0039's early-exit promptness bound (attempted
  below 10,000) failed twice under live-miner contention
  (observed 32,519) while its exact-accounting checks passed:
  on this host, unshed discretionary work and the live miner
  contend, and nothing in the running system prevented it.
- A calibration finding from this stage (B3 part 1): with
  the production signal set, the load channel alone holds
  the machine in CRITICAL on the current host (load1 15.3 to
  17.2 against an effective-CPU estimate of 2.0, ratio 7.65
  to 8.60), while the in-guest process table shows only
  about 1.4 CPUs busy. The guest's load average carries
  host-level contention the guest cannot attribute. If
  awareness ran continuously today, the agent would shed
  everything, all the time: the machinery is sound, the
  load signal's calibration on this host class is not.

Gap verdict C3: shedding machinery is real, wired inside
the agent package, and demonstrated end to end in this
stage (B3); it is not active in live production because no
driver feeds it, and its load channel is miscalibrated for
the current host.

### C4. Work allocation and duplicate prevention

Question: what does mining/coordinator.py (EXP-055) prove,
what is wired, and what prevents duplicated work today?

What exists, in source:

- mining/coordinator.py is a complete work-allocation
  system: a persistent coordinator process (CoordinatorServer
  with a TCP listener, serve() line 1090; runnable as
  python3 -m mining.coordinator) speaking a checksummed
  length-prefixed wire protocol; leases with unique ids and
  fencing tokens from one monotonic counter; report
  classification in _check_report (line 497): OK, DUPLICATE,
  STALE, NOT_HOLDER, UNKNOWN_LEASE, where only a live holder
  with the current token credits anything; the restart rule
  (apply_restart_rule, line 712: epoch bump, all leases
  reclaimed, workers re-register); an operation journal plus
  atomic snapshots for persistence; a deduplicating candidate
  queue (identity is the full header identity, persist before
  acknowledge); and assert_partition_invariant (line 773)
  plus the accounting identity unique + pending + leased ==
  declared.
- agent/intelligence/resources.py ResourceRegistry is the
  single-machine predecessor: exact non-overlapping nonce
  assignments per (job identity, extranonce space), completion
  only on full batch reports, coverage as an interval union
  with repeated computations counted separately. Its own
  docstring states the scope: single-machine, single-process.
- EXP-055's own scope line stands: before this stage the
  coordinator had been exercised on one VM with loopback and
  in-process workers only (the protocol transport in its test
  suite passes frames through handle_frame in-process).

What is wired: nothing. No live mining path imports
mining.coordinator (verified by import search across mining,
agent, gpu, blockchain, node and scripts at this HEAD: zero
importers outside tests), and the coordinator module's own
docstring says so. ResourceRegistry is used inside the agent
package's tests and planning surface, not by the live miner.

Duplicate prevention on the live paths today:

- Pool path (mining/mainnet_live.py): a single miner process
  owns the search; its extranonce2 counter increments per job
  in-process, so duplication across processes cannot arise
  because there is one process. There is no cross-process
  mechanism.
- GBT path (mining/engine.py): engines that must not
  duplicate each other are constructed with disjoint
  extranonce_space values (EXP-034; the assignment of spaces
  is the caller's act, by hand), and the EXP-038 work
  checkpoint prevents one restarted engine from rescanning
  its own completed frontier for the same template identity.
- Candidate level: EXP-036 verify_candidate plus Core's own
  verdict on the GBT path, and the pool's share accounting on
  the pool path.

Gap verdict C4: allocation and fencing machinery is proven
at protocol level and, after B1, across independent
processes on one host; it is deployed nowhere, and live
duplicate prevention is single-process by construction.
Fleet allocation remains owner-gated (EXP-035 roadmap F2).

## Part B: architecture completion

### B1. Coordinator machinery across independent processes: DONE

No production code change was needed; the existing server,
client and protocol carried the whole demonstration.

Setup (scratch, .local/stage9/b1/): the coordinator ran as
its own OS process (python3 -m mining.coordinator, TCP on
127.0.0.1) with its own state directory; workers ran as
independent OS processes (worker.py) speaking the wire
protocol through CoordinatorClient over real sockets, doing
real SHA-256d work over leased nonce ranges and keeping
their own JSONL completion logs. Driver: drive.py.

Phase A (parallel completion), evidence
research/STAGE9/evidence_94/b1_phase_a.json plus the worker
logs beside it: a job of 2 slices x 65,536 nonces in 8,192
nonce chunks (131,072 declared) was declared; two workers
(w-alpha, w-beta) leased disjoint slices and completed all
16 chunks (131,072 hashes by the workers' own logs).
Verified three ways: the workers' own interval records are
disjoint and cover [0, 65536) exactly per slice; the
coordinator's accounting reports complete with unique ==
declared and zero duplicate, stale and not-holder reports;
assert_partition_invariant and the accounting identity held
at every checkpoint. The candidate queue worked across
processes: 28 candidates submitted from the two worker
processes, 0 duplicates, all 28 verified on drain.

Phase B (fencing), evidence b1_phase_b.json, w1_result.json
and the w-fence worker logs: a worker incarnation leased a
chunk with a 3 s TTL, reported progress (OK), then stalled.
A foreign worker's completion attempt on the live lease with
the correct token classified NOT_HOLDER. After the deadline
the driver expired the lease (reclaimed, 1 reclaim). A second
process incarnation of the same worker identity re-registered,
re-leased the reclaimed chunk under a new lease id and a
strictly larger fencing token, and completed the whole job.
The stalled incarnation then woke: its late completion
classified STALE and its late progress classified STALE. A
replayed completion of the takeover lease classified
DUPLICATE. Final accounting: complete, unique == declared,
partition invariant and accounting identity held at every
checkpoint.

Neighbour suite: make test-exp055 PASSED (23 checks),
including its regtest block through coordinator-assigned
work.

What B1 proves and does not prove: lease, fencing,
partition and duplicate semantics hold across independent
OS processes over TCP on one host, against a scratch work
source. It says nothing about other machines, real network
latency or partitions between machines; see Part C.

### B2. GBT status publisher (DEF-9.2-4): DONE, default-off

Change (the only production code change in this stage):
mining/engine.py gains a StatusPublisher thread class
(line 492), the shape the Stage 8 demo miner proved,
promoted into the engine. MiningEngine gains three opt-in
constructor parameters (line 562): status_publish=False,
status_interval_s=10.0 (the pool path's cadence),
status_sink=None. When enabled, each mine_cycle runs one
publisher thread for exactly the cycle's duration: the
public mine_cycle (line 858) is now a thin wrapper owning
the thread's lifetime around the renamed _mine_cycle body
(line 885), stopping and joining the thread on every exit
path including exceptions. The publisher republishes the
engine's MiningStatistics totals to the sink with the pool
path's status fields (hashes, rate, submitted, statistics,
statistics_errors); the default sink appends to a bounded
deque (engine.status_events). A raising sink is counted and
never breaks the cycle. With the flag off (every existing
caller), no thread is constructed and behaviour is the
historical one; the new suite proves the enabled and
disabled cycle results are identical. No production caller
enables it and no live config was touched: enabling it on a
live path, and wiring a sink to the awareness evidence log,
remain operator decisions.

New sha256 for mining/engine.py:
866936fd6d41ebcc3a5ecbde886b0a5aa27eeae6ad5483025ddf0b3f1635f1ec.

Tests: new tests/test_status_publisher.py (stub RPC and
fake compute; no node, no native backend) with 5 checks:
default-off identity with the enabled result; periodic
publication during a long cycle with non-decreasing hashes
and the full status field set; raising-sink isolation;
sub-interval cycle cleanliness; thread stop on exception.
PASSED. New Makefile target test-status-publisher, added to
test-all (51 to 52 prerequisites; the Stage 9.3 count is
superseded by this addition). Neighbour suites, run one at
a time, all PASSED: test-template-cache, test-exp051,
test-exp038, test-mining, test-exp040, test-stage8,
test-agent-controller. The CI workflow subset
(.github/workflows/test.yml) was not changed; the new suite
is node-independent and is a candidate for that subset, but
changing the subset is left to the parent and auditor under
the Stage 9.3 corrections discipline.

### B3. Load-aware deferral, demonstrated: DONE (prototype-grade)

Prototype only: nothing was wired into the live miner. The
demo (.local/stage9/b3/) uses the production ModeManager
with production thresholds; only the hysteresis timing
knobs the class exposes for tests were shortened
(entry_confirm_samples=2 is the production default;
exit_window_s=30 against the production 300).

Part 1, the production load channel (evidence
b3_ambient_mode.json): feeding the exact load signal
awareness builds (os.getloadavg over EFFECTIVE_CPUS_EXP031)
at 5 s intervals, the machine entered CRITICAL on the
second sample and held it for all 7 samples (load1 17.21
down to 15.30, ratio 8.60 to 7.65). On this host the load
channel saturates by itself; see the C3 calibration
finding.

Part 2, the deferral arc on the rate channel (evidence
b3_load_deferral.json; the flawed run 1 is kept as
b3_load_deferral_run1_flawed.json, see below): an
orchestrator process measured a real probe rate (120,000
SHA-256d per sample, every 4 s) and fed it as miner_rate_hs
to the ModeManager (baseline 101,268 H/s, the median of
three warmup probes). Two independent worker processes ran
identical 100,000-hash batches for the run's duration; the
gated worker re-read the persisted mode before every batch
and deferred while it shed; the control worker never
checked. Four CPU hog processes ran from t=36 s to t=156 s.
Measured arc: NORMAL to BROWNOUT at t=48 s (probe ratio
0.503), escalating to CRITICAL at t=96 s (ratio 0.440);
hogs off at t=156 s; step-down CRITICAL to BROWNOUT at
t=190 s and BROWNOUT to NORMAL at t=250 s, each after the
sustained clear window. The gated worker deferred on 153
consecutive checks spanning 318 s and completed 56 batches
before the shed window and 19 after the first return to
NORMAL; the control worker completed 229 batches inside the
shed window, unshed. One boundary batch (batch 56, started
0.4 s after the recorded transition) crossed into the shed
window through the check-then-act gap: shedding in this
design is cooperative at command boundaries, never
preemptive, which is exactly the semantics modes.py and
ExperimentRunner document for production. A late noise dip
(ratio 0.699, two samples at t=262 s, after the hogs were
long off) re-entered BROWNOUT and had not cleared when the
run ended at t=340 s; the demo script's strict precomputed
verdict therefore reads INCOMPLETE, and the two reasons are
the boundary batch and that unfinished final exit. The
deferral mechanism itself (observe real rate collapse,
shed, defer discretionary work for the whole shed window,
resume on step-down) is fully present in the record.

Signal quality, stated plainly: the probe rate ratio ranged
0.224 to 3.656 across 85 samples on this host. The machinery
responds to the signal it is given; on this host that signal
is very noisy, and any production use needs the calibration
work recorded in Part C.

Run 1 disclosure: the first run's workers carried a fixed
24-batch quota and exhausted it by t=19 s, before the hogs
started; the mode still transitioned (NORMAL to BROWNOUT at
t=116 s, back at t=180 s) but no worker was left to defer.
Run 2 replaced the quota with duration-based workers and a
median warmup baseline. Both records are in the evidence
directory.

Neighbour suites for the components B3 exercised:
test-agent-controller (which covers modes) PASSED (72
checks) after the demo.

## Code changes in this stage (complete list)

1. mining/engine.py: StatusPublisher plus the opt-in
   MiningEngine wiring of B2. Tested as recorded above.
2. tests/test_status_publisher.py: new suite for B2.
3. Makefile: test-status-publisher target; test-all gains
   one prerequisite (52 total).
No other production file was modified. B1 and B3 code lives
in scratch (.local/stage9/b1/, .local/stage9/b3/) by design
and is not repo code.

## Part C: honesty register

UNVERIFIED after this stage:

- Multi-machine behaviour of everything in C4: B1 is one
  host, loopback TCP, independent processes. Cross-machine
  coordination, real network latency, network partitions and
  clock skew between machines are all UNVERIFIED, and no
  fleet-scale or hash-rate claim may be drawn from B1.
- The coordinator against a real Bitcoin job source over the
  wire end to end (B1's work source was scratch headers; the
  EXP-055 Gate 6 regtest block remains the chain-connected
  evidence, and it was in-process).
- B2's publisher enabled on any live path, and its sink
  wired to the awareness evidence log: deliberately not
  done; the capability is proven only in the new suite's
  stub environment and by the neighbour suites.
- Any protective effect of shedding on the LIVE miner's
  rate: in B3 the live miner was a bystander (its shares
  kept rising, 1066 to 1069, through the contention window),
  but no controlled measurement of miner-rate protection was
  made or may be claimed.
- Load-channel calibration: why this guest's load average
  sits at 15 to 17 with about 1.4 CPUs busy in-guest is
  observed, not root-caused (host-level run-queue accounting
  is the standing hypothesis). Until it is resolved, the
  production load thresholds cannot be trusted on this host
  class, and the rate channel's noise (ratio range 0.224 to
  3.656 in B3) needs a smoothing or calibration study before
  any always-on deployment.
- EXP-058 PID actuation anywhere live, and any hash-rate
  effect of it: unchanged from Stage 9.2.
- Agent-executed lifecycle operations against the live
  stack: the controller's operations remain proven on
  isolated copies and in suites; running them on the live
  stack is an operator act that has not happened.
- An always-on research loop: no part of C2's missing driver
  was built in this stage, deliberately; building it is a
  design decision about how much autonomy the agent should
  exercise, and it is the owner's.

Autonomy classification, stated plainly per area:

- C1 lifecycle: agent-assisted. A verified controller exists
  in the agent's library; the live lifecycle is operated by
  autopilot, systemd and the external keeper, not by the
  agent.
- C2 research loop: agent-assisted. Every stage exists as
  enforced machinery and executes under direction; hypothesis
  generation, scheduling, independent verification and
  registry update are human or external-service acts, and
  integration is never performed by the runner.
- C3 resource management: agent-controlled inside the agent
  package when a driver runs it (the gates genuinely refuse
  and defer work, proven in B3 across processes), but not
  active in live production: no always-on driver feeds the
  mode machine today.
- C4 work allocation: agent-controlled at protocol level on
  one host after B1 (leases, fencing and duplicate
  prevention proven across independent processes), deployed
  nowhere; live duplicate prevention is single-process by
  construction. Fleet autonomy: UNVERIFIED and owner-gated.

Nothing in this stage changes the Stage 9.2 promotion
decisions or the owner gates: EXP-035 fleet activation,
EXP-052 dispatch enablement, EXP-057 deployment and EXP-058
live actuation all remain owner decisions.

## Corrections (2026-11-18)

D-94-1 (minor, documentation precision; from
research/STAGE9/STAGE9_4_AUDIT.md): the C1 and C2 caller
enumerations were incomplete and have been corrected in
place, after re-verification at source.

- C2: the ExperimentRunner test invocation list now also
  includes tests/test_agent_controller_modes.py
  (ExperimentRunner constructed at line 479), which the
  original enumeration omitted.
- C1 and C2: both sections now also mention
  research/EXTREME_RESEARCH/stage8_demonstration.py, which
  constructs a MiningController (line 213, now named in C1)
  and an ExperimentRunner (line 567, now named in C2). That
  script is a human-run Stage 8 demonstration against
  isolated instances, not a production path.

No verdict, classification or other claim was altered by
this correction; the material claims (no daemon, no CLI
operation, nothing in production driving the controller or
the research loop) stand unchanged.
