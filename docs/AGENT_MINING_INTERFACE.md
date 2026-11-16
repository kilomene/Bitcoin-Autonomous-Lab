# Agent Mining Interface

Date: 2026-11-15. The typed interface between the agent
intelligence layer and the mining system, as implemented in
agent/intelligence/interface.py (MiningInterface) and
agent/intelligence/awareness.py (Awareness), Master Build
Milestones 1 and 2. Every operation is gated by
agent/intelligence/permissions.py and recorded in the audit log
(.local/agent-audit.jsonl). The audit record schema (audit.py):
version, ts, ts_utc, operation, level, inputs (a summary dict),
outcome, and an optional detail. Audit write failures are counted
on the AuditLog object and never raised into the caller.

General failure behaviour, all operations: a permission refusal
raises the package PermissionError (operation, required level,
granted level) after writing a permission_denied audit record.
Unknown operation names are refused by the checker. Operations
never fabricate telemetry: a missing or stale source is reported
as such in the response itself.

## MiningInterface operations

Constructed with a PermissionChecker, an AuditLog, and injectable
local_dir, engine_factory and controller (all injectable for
tests; defaults are the repo .local directory, the real
ComputeEngine factory, and no controller).

### inspect_status (L1, operation inspect_status)

Request: StatusRequest (empty dataclass; the method also accepts
None). Response: StatusResponse with running, note, autopilot_pid,
miner_pid, miner_state, miner_uptime_s, restarts,
shares_accepted_total, evidence_age_s, heartbeat_age_s,
evidence_accepted, evidence_rejected, evidence_share_results and
the raw heartbeat dict. Source: .local/heartbeat.json and
.local/evidence-count.json, the same files the autopilot's
--status flag prints (autopilot.py exposes no importable status
function). Failure behaviour: a missing heartbeat file is not an
exception; the response reports running False with a note naming
the missing path, and still carries whatever census fields exist.
A heartbeat older than 120 s, or a miner_state other than
running, reports running False with the file's contents as found.
Audit outcome: ok or not_running.

### inspect_machine (L1, operation inspect_machine)

Request: none. Response: MachineResponse with model_name,
logical_cpus, flags (the SSE, AVX, SHA, VBMI, BMI, GFNI and
VPCLMULQDQ subset), has_sha_ni, has_avx2, has_avx512f,
cgroup_cpu_max (read from /sys/fs/cgroup/cpu.max or the v1 quota
file, else None) and effective_cpus_estimate (always None from
this call, with a note pointing at EXP-031's measured estimate of
about 2 effective CPUs). Source: /proc/cpuinfo. Failure
behaviour: an unreadable cpuinfo yields model_name "unknown" and
empty flags rather than an exception.

### inspect_backends (L1, operation inspect_backends)

Request: none. Response: BackendsResponse with dispatch_order
(the canonical EXP-039 order: CUDA, v512dual, v512, shani, avx2,
C, hashlib), selected, requested ("auto"), fallback_reason and
tier_reasons (read from the engine's own reason attributes where
present, guarded by hasattr in the EXP-039 D-1 pattern). The
engine is constructed through the injectable factory and cached
per requested pin. Failure behaviour: probing failures surface
as the ComputeEngine's own fallback selection, not as an
interface exception; the response reports what dispatch chose.

### verify_candidate_op (L1, operation verify_candidate)

Request: a header (80 bytes, or a hex string, converted), a chain
name (default "main") and an optional share_target. Response:
CandidateResponse with classification, reason, digests_agree,
valid_header, meets_network_target, meets_share_target, value,
target, nbits and digest_hex. Implementation:
mining.candidate_verify.verify_candidate with
pow_limit_for_chain(chain); the verifier requires hashlib and
pure-Python digest agreement and judges by exact integer
comparison. Failure behaviour: malformed headers come back as a
classification with a reason from the verifier, not as an
exception; an unknown chain raises from pow_limit_for_chain.
Audit outcome: the classification string.

### estimate_probability (L1, operation estimate_probability)

Request: hashrate_hs, difficulty, optional seconds. Response:
ProbabilityResponse with difficulty, hashrate_hs,
expected_hashes, expected_seconds, median_seconds, p90_seconds,
prob_at_least_one (only when seconds was given) and seconds.
Implementation: mining/probability.py functions of the same
names. Failure behaviour: invalid inputs raise from the
probability module (for example a quantile outside its domain);
nothing is clamped silently.

### checkpoint_status (L1, operation checkpoint_status)

Request: an optional checkpoint file path. Response:
CheckpointResponse with path, exists, note, complete,
frontier_extranonce, frontier_nonce and identity_prefix (first
16 characters of the stored identity). Implementation:
mining/work_checkpoint.py WorkCheckpoint file read. Failure
behaviour: no path given returns exists False with a note
explaining which file to pass (audit outcome no_path); a missing
or unreadable checkpoint returns exists False with the loader's
note (audit outcome no_checkpoint). GBT path only; the pool path
has no checkpoint file to read.

### select_backend (L2, operation select_backend)

Request: a pin string (one of cuda, v512dual, v512, shani, avx2,
c, hashlib, auto; case-insensitive). Response: BackendSelection
with requested, selected, eligible and a note. Decision only:
mining is never started. The hashlib pin is answered without
constructing an engine (always eligible). Failure behaviour: an
unknown pin raises ValueError naming the expected set; a pin the
host cannot serve returns eligible False with the tier dispatch
actually cascaded to, not an exception.

### start_mining and stop_mining (L2, operations start_mining, stop_mining)

Request: none. Response: whatever the injected controller
returns. These are the interface's only production-mutating
specifications. Failure behaviour, as built: with no controller
injected (the production default), the operation is
permission-checked, an audit record with outcome not_implemented
is written, and NotImplementedError is raised. No code path in
the package starts or stops the live miner, the autopilot or a
node. The registry also carries adjust_workers and
trigger_recovery as L2 specifications; Milestone 1 defines no
MiningInterface method for them, so they exist as permission
specifications only.

## Awareness operations

Awareness (agent/intelligence/awareness.py) is constructed over
an Agent facade and takes its checker, audit log and task
registry from it. Every operation requires the L1 inspect_status
permission and the observe cycle writes one audit record
(operation awareness_observe). All source paths and the node RPC
factory are injectable; the node read is a single attempt with a
bounded 30 s timeout. Responses are plain dicts.

### snapshot()

Returns one coherent live picture: ts_utc; autopilot (running,
note, pids, state, uptime, restarts, heartbeat and evidence ages,
shares_accepted_total); evidence_census (present, accepted,
rejected, share_results, consistent); miner_status_file (present,
job_id, prevhash_prefix, pool_diff, session_hashes,
session_rate_hs, best_share_difficulty, shares_submitted,
session_elapsed_s, worker, pool_endpoint, backend, absent_fields
naming every field the file did not carry); evidence_tail (last
status event with the republished MiningStatistics snapshot, last
job event, last share result); node (reachable, blocks, headers,
initialblockdownload, blocks_behind_headers, error);
endpoint (mode and pool/solo addresses); read_times_ms per
source. Failure behaviour: a missing heartbeat reports the
autopilot section as not running with the reason; an unreachable
or timed-out node reports reachable False with the error, and the
rest of the snapshot is still returned.

### rate_observation(window_s)

Samples the census and the evidence tail twice across a real
window. Returns window_requested_s, window_wall_s, shares_delta,
share_rate_per_s, backend_hashes_delta, backend_rate_hs,
backend_interval_s, implied_difficulty_weighted_rate_hs (only
when shares were accepted in the window and a pool share
difficulty is recorded; labelled an estimate with its method),
pool_share_difficulty, a method string describing exactly how
each figure was computed, and notes. Failure behaviour: when the
bracketing status events or counters are absent, the affected
figure is null and the method string says why; no rate is
interpolated.

### degradation_check(baseline, current=None)

Returns flags (each naming its evidence), not_evaluated (checks
whose inputs were absent, never silently passed) and the
thresholds used: heartbeat_stale_s 120, rejected_ratio 0.05,
rate_drop_fraction 0.25. Checks: heartbeat staleness, restarts
above 0, rejected share ratio, rate drop against the baseline,
node falling behind its headers.

### coverage_report()

Returns the statistics event timestamp, the census, can_state
(the EXP-037 separated counters from the miner's last status
event and the lifetime census, with their scopes stated) and
cannot_state (no exact pool-path frontier exists, no finite
remaining work can be stated for pool jobs, nothing fresher than
the last status event can be quoted). It never merges the
session counters and the lifetime census into one figure.

### observe_cycle(window_s=0)

One full pass: baseline snapshot, rate observation, final
snapshot, degradation check against the cycle-start baseline,
coverage report, per-phase overhead timings (with the deliberate
window separated from active overhead), and the standing task
record (task id live-awareness-observe in the planning registry,
one evidence entry per cycle). Returns the structured
operational report (kind awareness_operational_report).

## Facade and CLI surface

agent.intelligence.Agent exposes: status() (delegates to
inspect_status), memory (lazy ResearchMemory), loop() (a new
OptimisationLoop bound to the memory, checker and audit),
gap_report(verified_rate_hs), next_investigations(limit) and
bottleneck_summary() (delegating to strategy.py). Research
memory access itself (lookup, search, was_rejected, by_status,
stats) is gated at the call sites that use it under the L1
memory_lookup and memory_search operations.

CLI (python3 -m agent.intelligence): status prints the live
status; awareness [window_s] runs one observe cycle and prints
the operational report as JSON.
