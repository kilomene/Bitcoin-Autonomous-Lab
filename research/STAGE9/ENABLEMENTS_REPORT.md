# Stage 9 enablements report: EXP-052, EXP-057, EXP-058, EXP-050, EXP-051, and the EXP-047 documentation

Date: 2026-11-18. Workstream: Stage 9 enablements, built
on remote HEAD 53ad3933dbef5a86bab4db9119e021f3ff1211c0
(the Stage 9 fixes batch). Owner decision (2026-11-18):
"Enable all five" (EXP-052 bake-off dispatch, EXP-057
aggregation tier, EXP-058 PID controller, EXP-050
endpoint health, EXP-051 prefetch), plus accept EXP-047
first-publisher-wins as production search semantics.

Host: AMD EPYC 9D25 126-Core Processor, 4 logical CPUs;
bake-off fingerprint {cpu_model: "AMD EPYC 9D25 126-Core
Processor", flags_hash: c86584c209897fb5, logical_cpus:
4} (AVX-512F/BW/VL/VBMI and SHA-NI present, probed from
/proc/cpuinfo at the start of this workstream).

Nothing in this workstream was pushed. Every change below
is on disk in the working tree, ready for the independent
audit the standing rule requires before any push.

## Outcome summary

| Item | Outcome | Where it takes effect |
|---|---|---|
| EXP-051 prefetch | ENABLED in code | The GBT/agent path (agent/autonomous.py). Verified live on an isolated regtest node. |
| EXP-057 aggregation tier | DEPLOYED in staging configuration; production runner built | A new runner (mining/aggregation_mainnet.py). Verified end to end against an isolated regtest node. The armed solo cutover still targets the solo server directly; see the remaining step. |
| EXP-052 bake-off dispatch | ARMED: fresh verdict cache planted and honoured; switch flip pending (see below) | The pool miner path (mining/mainnet_live.py), at its next restart after the flip. |
| EXP-050 endpoint health | ARMED in observe/report mode: policy machinery proven live on the production seam; switch flip pending (see below) | The pool miner path (mining/mainnet_live.py), at its next restart after the flip. Failover stays inert until a real second endpoint exists. |
| EXP-058 PID controller | NOT ENABLED, deliberately, with reasons recorded | Nowhere. The controller, its switch and its fallback remain intact and suite-pinned. |
| EXP-047 documentation | DONE | Documentation only: completion report addendum and registry entry. No code changed. |

The one step this workstream did not perform: the
EXP-052 and EXP-050 switches live in
.local/mining-endpoint.json, the endpoint config the
solo cutover owns. This workstream's constraints forbid
modifying that file (its sha256 is unchanged, verified
below), so both items are armed and proven up to the
switch, and the exact scripted flip is recorded in
section 7 for the operator. Everything else in the
owner's decision is fully executed.

## Live stack, before and after

Before (2026-11-18T10:21Z, .local/heartbeat.json):
autopilot pid 3241, miner pid 3248
(mining/mainnet_live.py, worker htch-runtime, against
public-pool.io), shares_accepted_total 1132, restarts 0.
The pruned mainnet node (pid 2291) was syncing in IBD.

During the work: shares rose monotonically (1133 at
10:36Z, 1134 at 10:44Z) with the same pids throughout;
no process was restarted, signalled or reconfigured by
this workstream.

After (2026-11-18T12:12Z, .local/heartbeat.json):
autopilot pid 3241, miner pid 3248 (both unchanged from
before), shares_accepted_total 1147 (from 1132;
non-decreasing at every observation), restarts 0. The
workstream's own staging regtest node was stopped
cleanly at the end; its datadir remains in
.local/enablements/regtest for re-runs. The pre-existing
regtest node and the mainnet node were never touched.

Endpoint config integrity: .local/mining-endpoint.json
sha256 d741cde3c6224406f46f3bae138fb174eb1d780725bcb94
baff4e14a8670c7d3 before, during and after; mode still
"pool"; no section was added to it by this workstream.
.local/solo-cutover.json was never touched.

## 1. EXP-051 prefetch: ENABLED on the agent path

### What changed

agent/autonomous.py: AutonomousMiner gains a
use_prefetch parameter defaulting to True and passes it
to MiningEngine; a close() method stops the prefetch
feed. That is the whole production change. The engine's
own default stays use_prefetch=False
(mining/engine.py is byte-identical to the fixes batch,
sha256 11f288ce...), so every other MiningEngine caller
(the Stage 8 path, mining/cpu/miner.py, the test
harnesses) is byte-for-byte historical. Rollback is one
value: AutonomousMiner(..., use_prefetch=False).

### Which live path

The GBT/agent path only: agent/autonomous.py's
AutonomousMiner, the path Stage 9.5 proved for
autonomous regtest discovery. The live pool miner
(mining/mainnet_live.py) never imports mining/engine.py
and is untouched by this item. At mainnet difficulty the
EXP-051 record claims the prefetch effect is nil and
measures nothing there; that claim stands unchanged.

### Evidence

Live verification against an isolated regtest node
started for this workstream (.local/enablements/regtest,
RPC 18453; not the lab's mainnet node and not the
pre-existing shared regtest node), driver
research/STAGE9/evidence_enablements/run_agent_prefetch.py,
output research/STAGE9/evidence_enablements/agent_prefetch_run.json:

- Prefetch ON (the new agent default), 6 cycles: chain
  height 113 to 119, 6 blocks accepted by the node,
  backend v512dual; engine statistics: prefetch_enqueued
  6, prefetch_served 5, prefetch_starved 1 (the cold
  first cycle, exactly the documented starvation case),
  zero dropped for identity, stale, superseded or
  overflow.
- Prefetch OFF (rollback construction), 6 cycles: height
  119 to 125, 6 blocks accepted, no queue constructed,
  every prefetch counter 0.
- Verdict printed by the driver: EXP-051 LIVE AGENT-PATH
  VERIFICATION: PASS.

### The one real finding, and its resolution

The first run of make test-mining with the enablement
FAILED: the suite's segwit-spend cycle asserted the
spend appears in the very next block (tx_count == 2);
with prefetch on, the cycle was served a template
prepared before the spend reached the mempool, and the
block carried tx_count 1 (accepted, valid, verified).
Causality was established by control: with the
enablement reverted, the identical suite passed; with it
re-applied, the failure reproduced deterministically.

Root cause: a queue-served template is a prepared
snapshot. The EXP-051 serve rule re-verifies the tip
(previousblockhash still the node's best block) and the
layered identity at serve time, but the transaction set
is the set the feed prepared; a transaction arriving
after preparation enters the next cycle's work. This is
the mechanism's designed semantics (its correctness
gates judge found-flag agreement, genuineness and
EXP-036 verification, never mempool freshness), and
blocks remain valid and fully verified. The consequence
is inclusion timing only, bounded at one cycle.

Resolution: tests/test_mining_engine.py now encodes the
designed semantics explicitly (the spend must be mined
within 3 cycles, with the reason and this date written
in the test), keeping every other assertion (witness
commitment path, fees > 0, the txid in the block,
persistence, the mainnet guard). Re-run: PASS, the spend
mined after 2 cycles with 2564 sats of fees, which is
the one-cycle lag made visible. The agent code carries
the same disclosure in a comment at the enablement
site. An auditor who judges the semantic change
unacceptable can revert the whole item with the one
constructor value; nothing else depends on it.

### UNVERIFIED register, EXP-051

- Any hash-rate or overhead effect of the enablement on
  this host: UNVERIFIED. The live run proves function
  (served/starved counters, accepted blocks), not the
  57.1 percent overhead figure, which remains the
  EXP-051 campaign's measurement, not re-measured here.
- Prefetch on the mainnet GBT path (the agent with
  allow_mainnet=True against the syncing node):
  UNVERIFIED, not run; the node is in IBD and the agent
  path is verified on regtest only, as before.
- Long-horizon feed behaviour across node restarts:
  UNVERIFIED here (the EXP-051 record's own register
  stands).

## 2. EXP-057 aggregation tier: runner built, staging deployment verified

### What changed

New file mining/aggregation_mainnet.py: the production
deployment runner for the tier, in the shape of
mining/solo_mainnet.py. mining/aggregation.py itself is
byte-identical to the Stage 9.1 baseline (sha256
1951a657...). The runner:

- reads the fleet definition (fleet id, operator token,
  worker enrollments, optional payout address) from a
  deployment file in .local (default
  .local/aggregation-tier.json) and FAILS CLOSED without
  it: no deployment file, no tier;
- verifies the upstream node's chain at startup
  (--chain, default "main") and serves the tier on
  127.0.0.1:3334 by default, deliberately NOT 3333, the
  solo cutover's port;
- refreshes the workbase on tip moves or 120 s job age,
  writes status to .local/aggregation-status.json every
  5 s and a tier snapshot to
  .local/aggregation-snapshot.json every 30 s and on
  shutdown, restoring it at startup under the EXP-055
  restart rule (epoch bump, pre-restart sessions dead);
- configures NO upstream submitter, preserving the
  EXP-057 rule in deployment: the tier validates and
  accounts, queues verified block candidates as
  pending, and can never submit one on its own
  authority.

### Which live path

None of today's paths. The tier is a Stratum front-end
for the post-sync solo world; it cannot carry pool work
(its only upstream is a SoloServer fed by
getblocktemplate, per the fleet activation finding).
Today's pool mining and the armed solo cutover are
untouched: the cutover still targets
mining/solo_mainnet.py serving the solo server directly
on 127.0.0.1:3333.

### Evidence

Staging deployment against the isolated regtest node,
driver research/STAGE9/evidence_enablements/run_aggregation_staging.py,
output research/STAGE9/evidence_enablements/aggregation_staging_run.json.
The runner ran in its deployment configuration (fleet
bal-staging-fleet, one enrolled worker, share difficulty
0.0001 chosen so the driver's Python search finds shares
in seconds):

- status at start: fleet enrolled, current job "1",
  node_ready true;
- the enrolled worker authorized over real TCP Stratum,
  received its tier-assigned extranonce1 and a job,
  found a real share by hashing real headers, submitted
  it: result True; tier counters accepted 1, accounted
  under the worker (per_worker stage-worker-1 accepted
  1);
- an unenrolled worker and the enrolled worker with a
  wrong token were both refused at authorize
  (identity_rejected 2);
- the accepted share also met the regtest network
  target and was queued as a pending candidate
  (pending_candidates 1) with upstream_submissions 0:
  the tier submitted nothing, as designed;
- clean SIGTERM shutdown, exit 0, snapshot written with
  the enrollment and counters.
- Verdict printed by the driver: EXP-057 STAGING
  DEPLOYMENT VERIFICATION: PASS.

One staging defect found and fixed in the driver (not
the tier): the first run pointed the tier at the
mainnet lab payout address on a regtest node, and the
SoloServer machinery refused every job build with
"invalid payout address" (chain-checked validation,
failing closed exactly as designed). The staging
deployment file now carries the regtest payout address,
which is what a real deployment file is for.

### Remaining step (exact)

Making the tier the solo front-end at the cutover is
NOT done and is a separate operator step, because the
cutover mechanism (scripts/solo_cutover.py,
docs/SOLO_CUTOVER.md) targets mining/solo_mainnet.py:
after the node finishes syncing and the cutover fires,
an operator who wants the tier in front replaces the
solo server process with
`python3 mining/aggregation_mainnet.py` (defaults:
mainnet node config, chain "main", port 3334) behind a
deployment file at .local/aggregation-tier.json, and
points workers at port 3334. Separately, block
submission from the tier's pending candidates remains
an explicit operator action through
AggregationTier.operator_submit_pending with a submitter
the operator configures at that time; the runner
deliberately wires none.

### UNVERIFIED register, EXP-057

- The tier against the real mainnet node after sync:
  UNVERIFIED (the node is in IBD; SoloServer refuses
  work during IBD by design, so no mainnet job was
  served).
- The tier as the live cutover front-end: UNVERIFIED,
  not attempted (see the remaining step).
- Multi-machine fleet use of the tier: UNVERIFIED,
  unchanged from the EXP-057 record; staging used one
  local worker over loopback.
- Operator submission of a pending candidate end to
  end: UNVERIFIED in this deployment configuration
  (the tier queued one; no submitter is configured).

## 3. EXP-052 bake-off dispatch: ARMED, fresh verdict planted

### What changed

Deployment state only; no production code changed
(mining/bakeoff_dispatch.py is byte-identical to the
fixes batch, sha256 e218e70a...; mining/mainnet_live.py
and mining/endpoint_config.py are untouched):

1. The bake-off campaign was re-run on the current host
   instance. The 2026-11-17 campaign's cache is void
   here by design (its fingerprint flags_hash
   51d3e983ddf6ac93 does not match this instance's
   c86584c209897fb5; same CPU model, same logical CPUs),
   and a fingerprint mismatch is the protocol's own
   re-run trigger. The re-run used the campaign driver
   unmodified, with outputs directed to
   research/STAGE9/evidence_enablements/exp052-rerun/
   so the campaign of record's RAW_RESULTS are
   untouched.
2. The re-run's verdict cache is planted at
   .local/bakeoff-dispatch.json (sha256
   3639d026c7dd493e232cc0a78feb9d1c065b0edfceab2d46dde92bb5
   bcfba76), the resolver's default cache path. .local
   state, never committed.

### Campaign re-run result (campaign exp052-20261118T103448Z)

Same predeclared protocol (predeclaration sha256
verified by the driver before measuring): 3 sessions,
150 paired 65,536-hash blocks per comparison, 18 of 18
units measured, measurement wall 524.6 s beside the
live stack. Verdict: STATIC, by the same dominance as
the campaign of record. Pooled adjusted log-ratios
against v512dual (95 percent CIs): v512 -0.6356
[-0.7579, -0.5119]; shani -0.9829 [-1.1178, -0.8534];
avx2 -1.6031 [-1.7182, -1.4851]; c -1.8809 [-1.9950,
-1.7613]; hashlib -3.9693 [-4.0798, -3.8501]. Median
rates (category E, contended, descriptive): v512dual
8,282,006 H/s; v512 4,654,531; shani 3,348,610; avx2
812,040; c 701,189; hashlib 95,991. cuda ineligible (no
CUDA device), as before. The control pooled adjusted CI
[-0.1759, +0.0838] is again wider than plus or minus
log(1.05) = 0.0488, so this campaign likewise could not
have certified any challenger at the 5 percent margin;
the STATIC verdict is unaffected (certification failure
can only produce STATIC, and every challenger was far
slower). Classification stays PROMISING HYPOTHESIS,
UNDER_INVESTIGATION; the cross-rotation portfolio
hypothesis stays unproven.

### Which live path, and the state of the switch

The seam is the pool miner path: mining/mainnet_live.py
consults resolve_requested at engine construction when
the endpoint config's bakeoff section is enabled. (This
corrects the workstream brief's framing of the seam as
the GBT/agent path; the import graph is unambiguous and
the EXP-052 report records the same seam.) With the
cache planted and the section enabled, the resolver
returns the verdict instead of today's "disabled"
answer:

- resolve_requested with the live merged config (switch
  off): ("auto", "disabled: bake-off dispatch is off;
  static order (today's behaviour)").
- The same merged config with the section enabled:
  ("auto", "static: the bake-off verdict for this host
  confirms the static order").
- The planted cache validates under the current
  fingerprint (read_cache: ok, "cache valid", winner
  None).

So the moment the switch flips, dispatch on this host
is decided by the measured verdict rather than by the
switch being off, and the engine it produces is
identical (requested "auto", v512dual by the static
order the verdict confirms). The end-to-end behaviour
on the real production code path, including the
miner-start evidence event, is proven in section 4's
live-seam run. The flip itself is the operator step in
section 7; it takes effect at the next miner restart
after the flip (the autopilot restarts the miner
routinely; the running miner does not re-read the
config, and this workstream did not restart it).

### UNVERIFIED register, EXP-052

- The flip on the live config and any post-flip live
  miner start: UNVERIFIED here by constraint (section
  7); proven on the isolated copy instead (section 4).
- Gate 5 measured-winner (a genuine challenger winning
  and dispatch following it): UNVERIFIED, unchanged;
  both genuine campaigns on this host produced STATIC.
- The Intel Xeon 8321HC rotation and a second AMD
  rotation: outstanding and UNVERIFIED, unchanged.
- Cache behaviour across a VM replacement that changes
  the fingerprint again: the verdict voids itself to
  "auto" on mismatch, by design; the re-run trigger
  would apply again.

## 4. EXP-050 endpoint health: ARMED in observe/report mode

### What was determined

The policy (mining/endpoint_health.py) and its wiring
(mining/stratum_client.py, mining/mainnet_live.py)
already exist and are byte-identical to the audited
record; no code change was needed or made. The lab has
exactly one pool endpoint (public-pool.io:21496) and
names no fallback, so the honest enablement is the
policy armed over the single live endpoint: it observes
and reports (its status() rides in the miner's status
evidence; exhaustion and recovery are logged as
events), and failover has no target and stays inert.
Inventing a second endpoint to make failover live was
explicitly not done. The recorded EXP-050 enablement
condition (a real second endpoint) remains the gate for
failover itself.

### Evidence: the armed live-seam run

Driver research/STAGE9/evidence_enablements/run_live_seam.py,
output research/STAGE9/evidence_enablements/live_seam_run.json.
An isolated copy of the production tree (code copied
verbatim, its own .local and evidence) ran the real
mining/mainnet_live.py against a local stub pool, with
a config equal to the live config's contents plus
pool_health and bakeoff enabled and the planted
EXP-052 cache in place:

- startup evidence: endpoint_policy_enabled (policy
  "ordered-failover-damped-failback", endpoints
  ["127.0.0.1:29796"], error threshold 3, failback
  interval 300 s, damping window 1800 s, max 1 failback
  per window) and bakeoff_dispatch (requested "auto",
  reason "static: the bake-off verdict for this host
  confirms the static order"); backend v512dual;
  shares submitted and confirmed through EXP-036;
- stub killed: the miner's reconnect failures fed the
  policy, which logged endpoint_policy_exhausted with
  action "retrying primary; autopilot restart remains
  the backstop" (the historical behaviour, now named
  and reported instead of silent);
- stub restored: endpoint_policy_recovered logged;
  shares resumed;
- status events during the run carry the policy's
  status() (current endpoint, on_primary, error counts
  by endpoint).
- Verdict printed by the driver: EXP-050/052 ARMED
  LIVE-SEAM VERIFICATION: PASS.

### UNVERIFIED register, EXP-050

- Failover to a real second endpoint and damped
  failback between real endpoints: UNVERIFIED, and
  inert until a real second endpoint is named; the
  EXP-050 Gate 3/Gate 5 stub evidence stands as the
  mechanism's proof, unchanged.
- The flip on the live config and the first live miner
  start under it: UNVERIFIED here by constraint
  (section 7); proven on the isolated copy instead.
- Policy behaviour over days of live operation
  (exhaustion episodes under real pool outages):
  UNVERIFIED until the flip has run live.

## 5. EXP-058 PID controller: NOT ENABLED, deliberately

No code was changed and nothing was wired. The
controller (mining/pid_control.py, byte-identical,
sha256 cfdcdd84...) keeps its own switch
(make_work_controller({"pid_enabled": True})), its
predeclared gains and its latching step-policy
fallback, all pinned by its suite (10 checks, PASS)
and by the new enablements suite (no live production
module imports it).

Reasons, in the record's own terms:

1. The EXP-058 record does not propose this step: its
   verdict section and UNVERIFIED register state that
   actuation against the live production miner is
   UNVERIFIED and not attempted, that integration is a
   separate step, and (judgment call 6) that the
   component "is not proposed for live-miner integration
   on this record". Enabling it anyway would override
   the experiment's own audited safety record, not
   fulfil it.
2. Half of the cascade is refuted: worker scale-up from
   the interval-only signal is an ESTABLISHED NEGATIVE
   (the signal cannot observe spare capacity; Gate 3's
   step_up reach bound failed for that structural
   reason). The controller as built runs both loops as
   one unit; there is no supported "span loop only"
   production configuration to enable instead, and
   inventing one would be a new, unpredeclared design.
3. There is no actuation surface to wire into: the
   production miner constructs its ComputeEngine with
   its own thread tuning and derives its scan span from
   the probe rate for template-preemption latency (a
   different design target from the controller's 2.0 s
   interval), and the autopilot supervises processes,
   not engine parameters. Wiring would mean building a
   new control channel into the live miner, which is a
   design task with its own predeclaration, not an
   enablement.

The exact remaining step: a future predeclaration
covering production actuation (signal source from the
live miner's own span timings, the actuation channel,
and a Gate 5-shaped supervised trial against the real
miner at reduced scope), or an owner-directed
integration design that supersedes the EXP-058 record's
position. Until then the honest state is: mechanism
proven at Gate 3/Gate 5 scope against a trial workload,
production actuation not enabled.

## 6. EXP-047: first-publisher-wins accepted (documentation)

No production code contradicts the accepted semantics
(a scan of gpu/engine.py, mining/cpu/bal_search.h,
mining/engine.py and agent/ finds no text claiming a
span-minimum guarantee), so this item is documentation
only, exactly as briefed.

### research/sha256d/exp047/EXP047_COMPLETION_REPORT.md

Appended at the end (after section 7):

> ## 8. Owner acceptance (2026-11-18)
>
> Addendum recorded by the Stage 9 enablements
> workstream, 2026-11-18. Documentation only: this
> addendum changes no production code, no campaign
> result and no verdict above.
>
> The integration question left open in section 6
> (accept and document first-publisher-wins, or pay
> for a minimum reduction inside the production search
> context) is decided: on 2026-11-18 the owner accepted
> first-publisher-wins (search_first_counted) as the
> production search semantics. It supersedes the
> original minimum-identity criterion (criterion S-C as
> first predeclared), which remains an ESTABLISHED
> NEGATIVE: a multithreaded native search returns the
> first genuine hit its thread partitions publish
> (mining/cpu/bal_search.h, bal_ctx_publish over
> bal_partition thread spans), not the span minimum,
> and no minimum reduction will be paid for in the
> production search context. The corrected-criterion
> re-verification stands as recorded above (search
> VERIFIED under the corrected criterion: found-flag
> agreement and hit genuineness on every backend, with
> minimum identity recorded as a statistic). A caller
> that needs the span minimum uses batch_search
> enumeration (exact here and in the batch campaign) or
> a single-threaded search, which returns the minimum.

### research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json, EXP-047 entry

measured_result, appended sentence (before the change
the field ended "...the original minimum-identity
criterion remains an ESTABLISHED NEGATIVE."):

> OWNER DECISION (2026-11-18, Stage 9 enablements):
> first-publisher-wins (search_first_counted) is
> accepted as the production search semantics,
> superseding the original minimum-identity criterion;
> no minimum reduction will be paid for in the
> production search context. A caller that needs the
> span minimum uses batch_search enumeration or a
> single-threaded search. Documentation only; no
> production code changed.

unresolved[0], before: "Whether to accept and document
first-publisher-wins semantics or pay for a minimum
reduction in the search context is an open integration
decision, left to a future gated decision". After:
"RESOLVED 2026-11-18: the owner accepted
first-publisher-wins as the production search semantics
(see the dated owner-decision note in this entry's
measured_result); no minimum reduction will be paid for
in the production search context".

The same registry file carries one dated enablement
note appended to each of the EXP-050, EXP-051, EXP-052,
EXP-057 and EXP-058 entries' measured_result fields,
recording the outcomes above in the registry's own
terms. Registry validation: make test-agent-intelligence
PASS (106 checks) after the edits.

## 7. The pending operator flip (EXP-052 and EXP-050)

Both switches are sections of .local/mining-endpoint.json.
The flip is a scripted write through the config's own
writer (never a hand edit; mode, pool, solo and payout
are preserved verbatim), to be run by whoever holds
authority over that file:

```python
import json
from mining import endpoint_config as ec

with open(ec.CONFIG_PATH) as f:
    raw = json.load(f)          # the raw file, unmerged
raw["bakeoff"] = {"enabled": True}
raw["pool_health"] = {"enabled": True}
ec.write_config(raw)            # atomic, mode 0600
print(json.load(open(ec.CONFIG_PATH)))
```

Effect and timing: the running miner does not re-read
the config. At the next miner restart (the autopilot
restarts the miner on VM replacement and on miner
exit), the miner logs endpoint_policy_enabled and
bakeoff_dispatch events in evidence/mainnet-live.jsonl,
constructs its engine with the resolver's verdict
("auto", STATIC for this host), and carries the
policy's status() in its status events from then on.
Rollback is the same write with both "enabled" values
false. Nothing about the endpoint itself changes: mode
stays "pool", the pool stays public-pool.io:21496, and
the solo cutover remains armed and unaffected (it owns
the mode field; these sections are inert to it).

## 8. Test evidence

Suites run one at a time on this host, in this order,
after all changes above were in place (the test-all
tally follows in the closing section):

| Suite | Result |
|---|---|
| make test-enablements (new, tests/test_stage9_enablements.py) | 29 checks, ALL PASSED |
| make test-exp051 | ALL PASSED (incl. Gate 6 queue-served regtest block) |
| make test-exp057 | 15 checks, ALL PASSED (incl. Gate 6 regtest block through the tier) |
| make test-exp050 | 40 checks, ALL PASSED |
| make test-exp052 | 46 checks, ALL PASSED |
| make test-exp058 | 10 checks, ALL PASSED |
| make test-mining | ALL PASSED after the documented test update (section 1); FAILED before it, and PASSED with the enablement reverted (control), as recorded |
| make test-agent-intelligence | 106 checks, ALL PASSED |
| make test-mainnet-live | ALL PASSED |
| make test-solo-cutover | ALL PASSED |
| make test-engine | ALL PASSED |
| make test-autopilot | ALL PASSED (with its designed skip: a live autopilot owns this checkout) |
| make test-agent-operations | 10,309 checks, ALL PASSED |
| make test-stage8 | 18 checks, ALL PASSED |
| make test-status-publisher | ALL PASSED |
| make test-template-cache | ALL PASSED |

The new suite is wired into the Makefile as
test-enablements and added to test-all (test-all now
has 53 prerequisites, up from 52).

## 9. Closing: test-all tally

make -k test-all (all 53 prerequisites, run after every
change above was in place; full log at
research/STAGE9/evidence_enablements/test_all.log):
52 of 53 suites PASSED. The single failure is
test-rtl: AssertionError "/bin/sh: 1: iverilog: not
found", the pre-existing environment failure classified
in the Stage 9.3 audit (the iverilog simulator is not
installed on this host), unrelated to this workstream
and reported as-is. Both fixes-batch suites pass inside
the full run (test-exp052 46 checks, test-task0039
accounting checks ok), as does the new test-enablements
(29 checks, the last suite run).

## 10. Manifest of changed and created files

Changed (sha256 after; before in parentheses where the
file existed):

- agent/autonomous.py: 294fe09ce49fdf344ccb6048cdd8ff5daf9f242457040ca3411532385b84fc4b (before f7a841baab2da1ebf9d533c02973420aec17ecd5c867cbe5b8d0fb2d0d6340ae)
- tests/test_mining_engine.py: 62d1a6aa07e4affe81262a3a78a6b2c872e4cdbc4ede7cf98898b14462fec8a6
- Makefile: 929279177c23a79563173a917977bbf9a57830120aacc7e64ec60a71e1347423
- research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json: d646c32c4c1449b310f52778228261b077957c35bcbf5943f45b8ca1becd1cf9 (before c333c8ef59c81a4b18ddad84674429eca7d84cd3ed27e039af8cddb07cb85f24, the fixes-batch state)
- research/sha256d/exp047/EXP047_COMPLETION_REPORT.md: c9239f6a813a53fe8f0136ac131fffbebddc73ea68c6155925285cffa58577c4 (before 4b4e7d84c1b0152503836d3ef6e6e0321f2a1107a28f9a8e626d635a1a745514)

Created:

- mining/aggregation_mainnet.py: b538c8c0518c90e1f533a4e53b41cf842210a5525029851adcecd496a47d9fd7
- tests/test_stage9_enablements.py: 0f26860efc6fc8c4d324b12e05a4e418445626897c3d482c09537f3721c19cd2
- research/STAGE9/evidence_enablements/run_agent_prefetch.py: 8d0df8c03f245c3d49c753dbe63fd9f68af46a2e1c0ef9b5db2ae83d89dbeb75
- research/STAGE9/evidence_enablements/run_aggregation_staging.py: 1c281ae224deab7184f23f6725e3fddb93beaa73cab9e9f8e60e4b0667d7f916
- research/STAGE9/evidence_enablements/run_live_seam.py: 5464bfac806bbc7f8d4bcafb12e5fe2188a2339449df9e5211c44c78d259984c
- research/STAGE9/evidence_enablements/agent_prefetch_run.json: 602e9e7229526b4a214536dbe880c5676c0e5ac05d2d02ef1c8697b83eaa6a01
- research/STAGE9/evidence_enablements/aggregation_staging_run.json: a6cbd97439db64ea6a8559aae7d676b82b4cac7d35f2074689137122e9ca9469
- research/STAGE9/evidence_enablements/live_seam_run.json: 0a4d7149af4332f56ae6d393c541d5b4cd5c7233c6982b837e2802e4b699bd69
- research/STAGE9/evidence_enablements/exp052-rerun/campaign_record.json: eea7593faa7ffb91a891222d4fe76f9627862d535a0b2ade2fcc2025d3551d4d
- research/STAGE9/evidence_enablements/exp052-rerun/bakeoff-dispatch-cache.json: 3639d026c7dd493e232cc0a78feb9d1c065b0edfceab2d46dde92bb5bbcfba76
- research/STAGE9/evidence_enablements/exp052-rerun/campaign.log: 958a62a0b952b0f6b3c9d698db6f63963008c92246746d28cfe3767e8f20a500
- research/STAGE9/evidence_enablements/exp052-rerun/sessions/: the campaign driver's 18 (session, comparison) unit records, enumerated in campaign_record.json.
- research/STAGE9/evidence_enablements/test_all.log: the full test-all log (hash recorded in the workstream handoff, since this section cannot hash a file that also documents this report's own final state).

Deployment state planted (.local only, never committed):

- .local/bakeoff-dispatch.json: 3639d026c7dd493e232cc0a78feb9d1c065b0edfceab2d46dde92bb5bbcfba76 (byte-identical copy of the re-run campaign's cache)
- .local/enablements/regtest/: the isolated staging node's datadir and node-config (credentials mode 0600, values not recorded here), stopped at the close of the work.
- .local/enablements/aggregation-tier.json: the staging fleet definition (staging tokens, mode 0600); aggregation-status.json and aggregation-snapshot.json alongside it.
- .local/enablements/live-seam-tree/: the isolated copy used by the live-seam run (its own .local and evidence; the copy's evidence file is the run's primary record).

Verified unchanged (sha256, audited baselines):

- mining/engine.py 11f288ce9387deb5d56c9810f2755927ce247d30c5ea960e4053e9d909fa07da (fixes batch)
- mining/bakeoff_dispatch.py e218e70a0d57e0c3213907fd393b753b1b1755f4ae97a36c02edbdfc9555c0b0 (fixes batch)
- mining/aggregation.py 1951a657b1be1968b484514a0defa70e4c10ce93ccc46beb0f0369b74d67c603 (Stage 9.1 baseline)
- mining/pid_control.py cfdcdd845a6a4bdfb1e9e2619bf4369376dd803ca45fe5eb7b754a4a1c51ed22 (Stage 9.1 baseline)
- mining/mainnet_live.py c8071ce1286c2bc3350afb05a624fd6fd2b16cb1f17808a86cbe922072e3218c (Stage 9.1 baseline)
- mining/endpoint_config.py c08010747aeed251df2b6ec498b21530be7facd269a5b79d76948c42a006a405 (Stage 9.1 baseline)
- .local/mining-endpoint.json d741cde3c6224406f46f3bae138fb174eb1d780725bcb94baff4e14a8670c7d3 (mode "pool", untouched)

U+2014 (long dash) scan over every file created or
edited by this workstream, this report included: zero
occurrences.
