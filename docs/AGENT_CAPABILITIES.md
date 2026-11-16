# Agent Capabilities

Date: 2026-11-15. The capabilities, permissions, operational
authority and limitations of the agent intelligence layer in
agent/intelligence/, as built by the Master Build (Milestones 1
to 5) and demonstrated against the live system in Milestones 2
and 6. Sources: agent/intelligence/permissions.py (the registry
table below is generated from the live ACTION_REGISTRY),
agent/intelligence/interface.py, awareness.py, loop.py,
experiments.py, scheduler.py, resources.py, and the milestone
reports in research/master_build/.

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

## Permissions: the action registry

Every operation the package exposes is named in ACTION_REGISTRY
(agent/intelligence/permissions.py) with its level and whether it
mutates production state. The table below is generated from the
actual registry. The registry contains 22 ActionSpecs: 11 at L1,
8 at L2, 3 at L3.

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
| start_mining | L2 controlled operations | yes | Start mining through the injected controller. Not wired to production in Milestone 1. |
| stop_mining | L2 controlled operations | yes | Stop mining through the injected controller. Not wired to production in Milestone 1. |
| adjust_workers | L2 controlled operations | yes | Adjust approved worker settings through the injected controller. Not wired in Milestone 1. |
| run_benchmark | L2 controlled operations | no | Run a controlled benchmark in an experiment context. |
| trigger_recovery | L2 controlled operations | yes | Initiate a recovery operation through the injected controller. Not wired in Milestone 1. |
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
operation, the required level and the granted level. No registry
entry mutates production state in the as-built system: the four
entries marked as mutating are specifications that execute only
through an injected controller, and no production controller is
wired (the default raises NotImplementedError after the
permission check and an audit record).

## Operational authority, stated plainly

The agent's live authority today is: read everything listed
above, decide backend eligibility, run sandboxed experiments and
benchmarks, maintain its own task, audit, scheduler-cache and
resource-registry state under .local/, and judge integration
attempts at the gate. It has no live authority over the running
miner: it cannot start, stop, restart, signal or reconfigure the
miner, the autopilot or either node, and no code path in the
package attempts to. Live supervision remains the autopilot's
and the keeper cron's. Production integration of any experiment
remains a separate gated act outside the package, followed by the
standing independent post-integration audit.

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

Research memory parsing gap (Milestone 1): memory.py maps
registry prose onto mandate statuses heuristically. Its
_map_status returns INTEGRATED only when a verdict line literally
contains "integrated" (and not "not integrated"), or the body
contains the phrase "integrated into production". Measured
consequence on the live registries (2026-11-15): the parsed
memory holds 98 entries with by_status EXPERIMENTAL 46, REJECTED
19, PROVEN 32, UNDER_INVESTIGATION 1, and zero INTEGRATED,
although the Milestone 0 reconciliation (section d) establishes
from source that EXP-007, EXP-017, EXP-022, EXP-025, EXP-026,
EXP-034, EXP-036, EXP-037, EXP-038 and EXP-039 are integrated.
Those entries parse as EXPERIMENTAL (EXP-007, EXP-017, EXP-034,
EXP-036, EXP-037, EXP-038) or PROVEN (EXP-022, EXP-025, EXP-026,
EXP-039). The REJECTED mapping, which the loop's safety gate
depends on, is not affected (EXP-014 parses as REJECTED, and the
live refusal fired correctly). Treat memory INTEGRATED lookups
as unreliable until the parser or the registries carry an
explicit integration marker; the ground truth for integration
status is the Milestone 0 map and the consolidated register
(research/master_build/RESEARCH_OPPORTUNITY_REGISTER.md).

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
  production integration; and its evidence assembly trusts the
  schema of evidence JSON files written inside the sandbox
  (conservative merging, but the files are the experiment's own).
- The awareness layer's node read can take most of a cycle's
  overhead when the node is in initial block download (19.40 s of
  a 32.80 s active overhead in the demonstration) and can time
  out at the bounded 30 s, in which case the node is reported
  unreachable, honestly, for that cycle.
- The agent cannot see or affect the solo cutover, the endpoint
  config flip, or the mainnet node's sync; it reads the endpoint
  mode only.
