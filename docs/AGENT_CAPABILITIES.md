# Agent Capabilities

Date: 2026-11-15, updated 2026-11-16 (Stage 7: production
controller and load-shedding modes). The capabilities,
permissions, operational authority and limitations of the
agent intelligence layer in agent/intelligence/, as built by
the Master Build (Milestones 1 to 5), demonstrated against
the live system in Milestones 2 and 6, and extended in
Stage 7 with a real production controller
(agent/intelligence/controller.py) and cognitive
load-shedding modes (agent/intelligence/modes.py). Sources:
agent/intelligence/permissions.py (the registry table below
is generated from the live ACTION_REGISTRY),
agent/intelligence/interface.py, controller.py, modes.py,
awareness.py, loop.py, experiments.py, scheduler.py,
resources.py, and the milestone reports in
research/master_build/.

## What the agent can do

- Inspect live mining state from real sources only: autopilot
  heartbeat, EvidenceCounter census, miner status file, evidence
  log status events, node state through a read-only RPC, endpoint
  config (Milestone 2, awareness.py).
- Measure the live backend rate over a real window from the
  miner's own separated statistics counters, and the share rate
  from the census delta (Milestone 2).
- Detect degradation against a baseline with named evidence per
  flag, and report checks it could not evaluate as not evaluated
  (Milestone 2).
- State unique coverage honestly: the miner's EXP-037 separated
  counters for its session and the lifetime pool-verdict census,
  with the pool path's missing frontier stated as a gap, not
  filled in (Milestone 2).
- Independently verify any 80-byte candidate header through
  mining/candidate_verify.py (EXP-036): two independent SHA-256d
  implementations must agree, and the target test is exact
  integer comparison (Milestone 1 interface; exercised end to end
  in Milestone 6).
- Compute probabilities, expected waits and target gaps through
  mining/probability.py and strategy.gap_report (Milestone 1).
- Look up and search the research memory (the two narrative
  experiment registries plus the EXP-033 JSON registry, parsed
  into mandate statuses), and rank next investigations from it
  (Milestone 1, memory.py and strategy.py).
- Refuse to re-propose a rejected hypothesis: the optimisation
  loop's hypothesise gate matches keywords against REJECTED
  memory entries and refuses with the citation (demonstrated
  live: K+W folding refused with the EXP-014 citation;
  research/master_build/MILESTONE2_LIVE_AWARENESS.md).
- Run the optimisation cycle as an enforced state machine, run
  experiments inside a contained sandbox with argv-only command
  execution and captured evidence, and judge integration attempts
  against the EXP-017 gate, refusing with the missing items named
  (demonstrated live: the batch-size experiment refused for
  exactly two missing items; research/master_build/
  MILESTONE345_BUILD.md).
- Profile the host, run a measured backend bake-off and thread
  sweep through the real production search path, and cache the
  result as an advisory host profile (Milestone 4, scheduler.py).
- Register workers, assign exact non-overlapping work, track
  honest completion, reassign unfinished work without completing
  it, and compute unique coverage by interval union, on one
  machine (Milestone 5, resources.py; 240-trial randomised
  campaign exact against an independent model).
- Keep a task registry with enforced state transitions and an
  append-only audit trail of every gated operation, including
  permission denials (Milestone 1, planning.py and audit.py).
- Start, stop and restart mining through the production
  MiningController (Stage 7, controller.py), which extends
  the existing autopilot (scripts/autopilot.sh plus the
  heartbeat and lock files), verifies every postcondition
  from the autopilot's own published state before reporting
  success, and never signals a pid it did not read from that
  state and verify against /proc cmdline. Recovery follows
  a fault taxonomy: miner-down and autopilot-down faults
  recover through the autopilot; correctness or consensus
  failures and crash loops at the restart cap halt and
  report, never auto-recover.
- Shed its own discretionary load under contention
  (Stage 7, modes.py): Normal, Brownout and Critical modes
  computed from the load average against EXP-031's effective
  CPU estimate and the miner rate against its own baseline,
  with entry confirmation and a sustained-clear exit window
  so the mode cannot flap. Brownout stops new experiments
  and bake-offs and reduces awareness cadence; Critical
  leaves only status. Mining is never shed, throttled or
  restarted by a mode transition.

## Permissions: the action registry

Every operation the package exposes is named in ACTION_REGISTRY
(agent/intelligence/permissions.py) with its level and whether it
mutates production state. The table below is generated from the
actual registry. The registry contains 24 ActionSpecs: 11 at L1,
10 at L2, 3 at L3.

| Operation | Level | Mutates production | Description |
|---|---|---|---|
| inspect_status | L1 read-only | no | Read autopilot heartbeat and evidence census state. |
| inspect_machine | L1 read-only | no | Read CPU model, logical CPUs and instruction flags. |
| inspect_backends | L1 read-only | no | Read ComputeEngine probe results and dispatch order. |
| verify_candidate | L1 read-only | no | Independently verify one 80-byte candidate header through mining/candidate_verify.py. |
| estimate_probability | L1 read-only | no | Evaluate mining probability formulas on given inputs. |
| checkpoint_status | L1 read-only | no | Read a work checkpoint frontier file. |
| memory_lookup | L1 read-only | no | Look up one research memory entry by id. |
| memory_search | L1 read-only | no | Keyword search over the research memory. |
| gap_report | L1 read-only | no | Compute the measured gap to the objective targets. |
| plan_read | L1 read-only | no | Read the task registry. |
| audit_read | L1 read-only | no | Read the audit log. |
| select_backend | L2 controlled operations | no | Decide the eligible backend for a requested pin. Decision only; never starts mining. |
| start_mining | L2 controlled operations | yes | Start mining through the production MiningController (agent/intelligence/controller.py) over the autopilot control surface. Wired in Stage 7. |
| stop_mining | L2 controlled operations | yes | Stop mining through the production MiningController over the autopilot control surface. Wired in Stage 7. |
| restart_mining | L2 controlled operations | yes | Restart mining through the production MiningController (verified stop plus start with a miner pid change). Wired in Stage 7. |
| adjust_workers | L2 controlled operations | yes | Adjust approved worker settings through the production MiningController. Launch-time only in the current production path: the controller reports restart-required and applies nothing silently. |
| refresh_job | L2 controlled operations | no | Request a mining job refresh through the production MiningController. No external trigger exists in the current production path (job supply is push-driven inside the miner); the controller refuses it as unsupported rather than faking an effect. |
| run_benchmark | L2 controlled operations | no | Run a controlled benchmark in an experiment context. |
| trigger_recovery | L2 controlled operations | yes | Initiate a recovery operation through the production MiningController, under its fault taxonomy (correctness failures and crash loops halt, never auto-recover). Wired in Stage 7. |
| plan_write | L2 controlled operations | no | Create or transition tasks in the task registry. |
| loop_advance | L2 controlled operations | no | Advance an optimisation loop record one state. |
| create_experiment | L3 experimental modifications | no | Create an isolated experimental implementation inside the sandbox directory. |
| modify_experiment | L3 experimental modifications | no | Edit an experimental implementation inside the sandbox directory. |
| record_evidence | L3 experimental modifications | no | Write experiment evidence inside the sandbox directory. |

Enforcement (PermissionChecker): unknown operations are refused;
an operation above the caller's grant is refused; an L3 operation
additionally requires a sandbox path inside the checker's sandbox
root, and is refused without one even when the grant is L3.
Refusals raise the package's PermissionError carrying the
operation, the required level and the granted level. The five
entries marked as mutating production state execute through
the production MiningController (controller.py); an explicitly
unwired interface (controller=False, the test seam) still
raises NotImplementedError for them after the permission
check and an audit record.

## Operational authority, stated plainly

The agent's live authority today is: read everything listed
above, decide backend eligibility, run sandboxed experiments
and benchmarks, maintain its own task, audit, scheduler-cache,
resource-registry and mode state under .local/, judge
integration attempts at the gate, and, through the production
MiningController, start, stop, restart and recover the miner
by extending the existing autopilot. The controller creates
no competing supervision: the autopilot keeps its watchdog,
backoff, session rotation and self-update, and the keeper
cron remains an independent layer. The controller's one
signal (SIGTERM to the miner child inside recover, so the
watchdog relaunches it) goes only to a pid read from the
autopilot heartbeat and verified against /proc cmdline;
there is no guessed-PID path. Every mutating call verifies
its postcondition and reports failure honestly when it does
not materialise.

What the controller does NOT do, by measured fact about the
current production path, not by omission: it cannot apply a
backend pin (mining/mainnet_live.py constructs
ComputeEngine() with no pin and no CLI carries one, so
select_backend at the controller is refused as unsupported;
the interface's eligibility decision is unaffected), it
cannot adjust worker counts at runtime (launch-time only,
reported restart-required, nothing applied silently), and
it cannot trigger a job refresh (job supply is push-driven
inside the miner; refused as unsupported). It has no
authority over either node, the solo cutover or the endpoint
config. Production integration of any experiment remains a
separate gated act outside the package, followed by the
standing independent post-integration audit.

Load-shedding modes bound the agent's own appetite, never
mining's: in Brownout and Critical the experiment runner,
the bake-off and the loop's discretionary transitions refuse
new work, and awareness reduces cadence or goes minimal.
Mode state is persisted at .local/agent-mode.json, shown in
awareness snapshots and by python3 -m agent.intelligence
mode, and every transition is audit-logged with its trigger
values.

## Limitations

Awareness gaps (Milestone 2, from the demonstration report):

- Pool-side job internals beyond what the miner itself publishes:
  the layer sees job id, generation, prevhash, nbits and ntime
  from the status file and evidence log, and the endpoint from
  config. It cannot see the pool's own accounting or the pool's
  view of the worker.
- Freshness is bounded by republication cadence: heartbeat 5 s,
  evidence status events roughly once a minute, census as the
  autopilot counts. Between those, the layer is blind by
  construction.
- No exact searched frontier exists for the live pool path:
  mining/work_checkpoint.py serves the GBT path only, so unique
  coverage for the pool miner rests on the miner's own separated
  counters, cross-checked only against the pool-verdict census.
- Remaining work for the pool path cannot be stated: the pool
  assigns jobs and there is no finite declared search space per
  job from this side of the protocol.
- Rejection reasons are limited to the census count and the error
  field of individual share_result events; the pool offers no
  richer reason channel.
- The node read is deliberately limited to getblockchaininfo.
  The node is not the live miner's job source while the endpoint
  mode is pool.
- Whether the pool would accept a block is unexercised:
  network_target_candidates is 0 in every session to date.

Research memory parsing gap (Milestone 1), FIXED 2026-11-16
(Stage 7, wave 1, item A; discrepancy D6): memory.py maps
registry prose onto mandate statuses heuristically. Its
_map_status returns INTEGRATED only when a verdict line literally
contains "integrated" (and not "not integrated"), or the body
contains the phrase "integrated into production". Measured
consequence on the live registries (2026-11-15): the parsed
memory held 98 entries with zero INTEGRATED, although the
Stage 0 reconciliation registry
(research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json) records
the integrations verified in source. The fix does not change
the parser. A derived machine-readable integration registry
(agent/intelligence/integration_registry.json, built by
agent/intelligence/integrations.py from the Stage 0 registry)
is now authoritative for integration status only: after
parsing, an entry whose id the registry records reports
INTEGRATED unless its parse is REJECTED (never overridden),
registry ids with no narrative entry are indexed from the
registry itself, and every other field still comes from the
narrative parse. Measured after the fix (2026-11-16): the
memory reports 28 distinct INTEGRATED ids, exactly the Stage 0
registry's INTEGRATED set, computed live on both sides by the
intelligence suite. The optimisation loop's prior-research
gate now also refuses a hypothesis matching an INTEGRATED
entry, with the citation, so integrated work is not
re-proposed as new. The REJECTED mapping, which the loop's
safety gate depends on, is unaffected (EXP-014 and EXP-015
still parse and report REJECTED).

Further limitations:

- The rejected-hypothesis gate matches on recorded wording:
  keywords must all appear in the entry's text. In the live
  demonstration, ["K+W folding"] alone did not fire because the
  registry text says "K+W constant folding"; ["K+W", "constant
  folding"] fired. A paraphrased re-proposal can pass the gate.
- The scheduler is advisory and its measurements are short,
  contended host profiles (262,144 hashes per repetition), not
  EXP-017 verdicts; its bake-off winner in the demonstration was
  inside run-to-run noise (0.8 percent margin). It changes no
  production dispatch, thread tuning or live state.
- The resource registry is single-process and single-machine,
  persisted as one JSON file. It implements no network protocol
  and claims no multi-machine behaviour.
- The experiment runner's gate pass would still not be a
  production integration. (Updated 2026-11-15, Autonomous
  Mining Brain Prompt 1: evidence assembly no longer trusts
  the sandbox files' schema. The integrate gate applies a
  strict verification-record schema, and independent
  verification must be a record signed by the separate
  verifier service, agent/intelligence/verifier.py, whose
  HMAC key the experimental sandbox cannot read. Experiments
  now run in a real operating-system sandbox,
  agent/intelligence/sandbox.py, and every run is chained
  into an append-only evidence ledger outside the sandbox.
  One measured host limitation stands: this VM's systemd
  scope cgroup properties are accepted but do not enforce,
  so memory and task caps are enforced by rlimits and a
  runner-side process-tree watchdog instead. See
  research/autonomous_brain/PROMPT1_SECURITY_REPORT.md.)
- The awareness layer's node read can take most of a cycle's
  overhead when the node is in initial block download (19.40 s of
  a 32.80 s active overhead in the demonstration) and can time
  out at the bounded 30 s, in which case the node is reported
  unreachable, honestly, for that cycle.
- The agent cannot see or affect the solo cutover, the endpoint
  config flip, or the mainnet node's sync; it reads the endpoint
  mode only.
- Controller limits (Stage 7): postcondition verification is
  bounded by the heartbeat cadence (5 s) and the verification
  window (60 s default); a start whose miner comes up after
  the window is reported failed even if it later succeeds,
  and the next status read shows the truth. The crash-loop
  cap (10 restarts in the heartbeat) is a controller policy
  over the autopilot's counter, not an autopilot feature.
  Recovery of a hung miner relies on the autopilot watchdog
  after a verified SIGTERM; if the watchdog itself is the
  fault, the controller reports failure rather than escalating
  to unverified signals.
- Mode limits (Stage 7): triggers see only the load average
  and the miner rate awareness republishes; a contention
  source that moves neither (for example pure disk pressure)
  does not shed load. Wind-down of in-flight discretionary
  work is cooperative at command and transition boundaries,
  not a kill: a single long-running experiment command runs
  to its own timeout inside the Prompt 1 sandbox.
