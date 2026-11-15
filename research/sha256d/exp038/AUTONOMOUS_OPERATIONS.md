# EXP-038: Autonomous Mining Operations

Date: 2026-11-15. Implements directive section 11 for the
Bitcoin Autonomous Lab: documents the supervision and
recovery system as it actually stands, and adds the one
missing mechanism this phase builds, the work-state
checkpoint (mining/work_checkpoint.py, wired into
MiningEngine.mine_cycle and enabled by
agent/autonomous.py). Tests:
tests/test_exp038_checkpoint.py (Makefile target
test-exp038).

## 1. Supervision layering, as built

| Layer | Mechanism | Where |
|---|---|---|
| Miner supervisor | Heartbeat every 5 s; watchdog polls the child every 1 s; a child that exits is relaunched with exponential backoff (1 s start, 30 s cap, reset after 60 s healthy); a live child whose evidence log goes stale past 300 s is killed and relaunched; sessions rotate every 24 h; flock single instance | mining/autopilot.py, scripts/autopilot.sh |
| Service supervision | systemd units for the autopilot, the mainnet node and (at cutover) the solo server | scripts/bal-autopilot.service, bal-bitcoind.service, bal-solo.service |
| Outer keeper | A goal-owned cron outside this repository restarts the autopilot and the node themselves; the repository alone does not contain this layer and this document does not pretend otherwise | goal crons (bal-mainnet-keeper) |
| Cutover guard | Preconditions, live Stratum smoke test, server-side share verification, automatic rollback to pool mining on failure | scripts/solo_cutover.py |
| Connection recovery | Stratum client reconnects with a full session reset (new extranonce1, fresh job generation guards); solo JobRefresher refuses work while the node is unready and resumes when it recovers | mining/stratum_client.py, mining/solo_server.py |
| Backend safety | Backend selection runs CPUID probes and hashlib self-tests before a backend is trusted; a bad candidate triggers a fail-closed rescan rather than a submission | gpu/engine.py |

The autopilot's self-update is real code but inert in this
checkout (no .git directory, so its git calls return None
and it exits silently, and the heartbeat reports version
"unknown"). Recorded here because an operations document
that lists it as live would be wrong.

## 2. Recovery semantics

| Failure | Behaviour | What survives |
|---|---|---|
| Miner crash or exit | Autopilot relaunches within backoff (worst case about 30 s) | Evidence log (append-only); on the GBT path, the work checkpoint (section 3) |
| Miner hung (no new evidence) | Killed after the 300 s staleness window, relaunched | Same as crash |
| Autopilot death | Outer keeper restarts it; the miner child is re-adopted by a fresh supervisor start | Evidence log, count state, work checkpoint |
| Node death or RPC failure | Keeper restarts bitcoind; solo JobRefresher refuses work until the node is ready and out of initial download | Node data directory; no work is served against a stale tip |
| VM replacement | Services return under systemd and the keeper; the miner resumes pool work on a fresh pool session | Everything under .local and evidence/ that the replacement preserves; GBT search position via the checkpoint |
| Template change mid-search | The cycle's template identity no longer matches anything else; in-flight work on the old template is abandoned by construction | The checkpoint record for the old identity, which will simply never match again |

The standing rule from the directive: a restarted process
must not falsely claim unfinished work was completed. Before
this phase that rule held only by absence (a restarted miner
claimed nothing about the old session, and also repeated all
of its work). Section 3 makes it hold by construction.

## 3. The work-state checkpoint, as implemented

Home: mining/work_checkpoint.py. Consumer: MiningEngine
(opt-in constructor argument checkpoint_path, default None).
Enabled in production by agent/autonomous.py at
.local/work-checkpoint.json.

Semantics: positions are (extranonce, nonce) pairs in the
lexicographic order mine_cycle walks them. The record holds
a frontier (fe, fn): every position with extranonce below fe
was examined over its full nonce range, and in round fe
every nonce below fn was examined. Because the walk is
strictly ordered, one frontier is an exact description of
completed coverage for a template, not an estimate.

Rules:

- The frontier advances only after a batch's search returns
  without a hit. A batch that produces a hit never advances
  it: that batch was partly examined, the cycle ends there,
  and a later cycle on the same template rescans that one
  batch. The rescan is repeated work and is visible as such.
- Resume requires all three of: the template's EXP-025
  layered identity, the engine's extranonce space, and the
  template's curtime basis. The identity deliberately
  excludes time fields (EXP-025's rule) while header time is
  a per-build input, so the time basis is matched separately:
  a resumed scan never claims coverage recorded under a
  different time basis. Any mismatch, a corrupt file, or a
  frontier outside the space starts the cycle fresh, and the
  cycle result's "checkpoint" field carries the reason.
- A space recorded complete is not rescanned under the same
  identity: the cycle returns "nonce space exhausted" with
  zero hashes rather than repeating finished work.
- Writes are atomic (sibling temp file, fsync, os.replace,
  best-effort directory fsync). A crash mid-write leaves the
  old record or the new one, never a torn file.
- With no checkpoint configured, mine_cycle's behaviour and
  result dicts are byte-for-byte the historical ones; a test
  pins the absence of the "checkpoint" key and the historical
  full rescan.

Scope boundary, stated once and plainly: the checkpoint
serves the GBT path (direct getblocktemplate solo mining).
The Stratum pool path does not use MiningEngine and is
untouched by this phase: its work separation is the
pool-assigned extranonce1 per connection, its job state
belongs to the pool session, and a restarted pool miner
starts a new session whose separation the pool itself
provides, so there is no local position to checkpoint and
claiming one would be false precision. The lab's Stratum
solo server likewise holds no search position (its workers
do); coordinator-level progress belongs to the EXP-035 lease
manager's progress positions, designed there and not
duplicated here. Solo-server workers are Stratum clients,
and their positions are session state, not checkpointed
state, in this phase.

## 4. Candidate recovery: the honest status

Still open. A candidate confirmed in the pool path exists as
process memory and one evidence-log line; a crash between
confirmation and submission loses it. EXP-035 designed the
remedy (a persist-before-acknowledge candidate queue whose
journal replays after a crash, section 8 of its design), and
EXP-036 hardened what happens to a candidate once it reaches
verification and submission, including chain-state
acceptance checks on the solo path. The queue itself is not
built, and the checkpoint in section 3 does not cover
candidates and does not claim to.

## 5. Dispositions: M15, M18, M21

M15 (starved worker re-registers, Qaxe slave pattern):
adopted in the EXP-035 design as the starvation window with
re-registration, and its fencing rules are what make the
checkpoint's restart story safe at fleet level. In today's
single-worker production there is no fleet to starve; the
working analogues are the autopilot's unconditional relaunch
of a dead miner and the Stratum client's reconnect with
session reset. Design disposition, no separate implementation
claimed.

M18 (sustained-performance policy under thermal or steal
pressure): investigate, recorded as a design note only.
EXP-031 characterised this guest: steal is modest and flat
(about 1.4 to 2.7 percent under load), no thermal interface
is exposed inside the guest, and the binding constraint is a
capacity allocation of about 2 effective CPUs. A shed-load
policy has nothing to sense and nothing measured to tune
against here. The note for a future host: on sustained steal
above a threshold, shed worker threads before the watchdog's
staleness window starts confusing contention with hangs, and
resume only below a hysteresis band. Unmeasured and
unimplemented; no numbers claimed.

M21 (ramp load changes in small steps): the restart path
already ramps (backoff doubles from 1 s to a 30 s cap, and
session rotation is a clean handover, not a step change of
load). Thread-count ramping at template or session changes
is a design note in the same status as M18: plausible on a
contended guest, unmeasured, not implemented.

M10 (adaptive solo share difficulty, from the EXP-037
matrix row): design note. The control loop translates (aim
at a target share interval as workers come and go, grace
period on increases, hysteresis), the register does not.
Not implemented: the solo share difficulty remains the
configured constant, and the verifier-flooding risk the loop
would manage is bounded today by the solo server's single
deployment. Recorded so the idea is neither lost nor
overclaimed.

## 6. Startup self-tests and resource exhaustion

Startup: backend dispatch self-tests exist and are real
(CPUID probe plus a hashlib differential before a backend is
selected). There is no end-to-end pre-mining check (node
reachable, template valid, payout correct) on the live pool
path before hashing resumes; the GBT path gets the equivalent
per cycle because template_identity validates the template
before the first batch. Stated as a gap, not patched over in
prose.

Resource exhaustion: the evidence log grows without bound.
This phase bounded the cost of COUNTING it (EXP-037's
incremental census), not its disk growth; nothing watches
disk or memory on the live path, and log rotation policy is
future work. The checkpoint and count-state files are small
bounded JSON and are not a growth concern.

## 7. Tests

tests/test_exp038_checkpoint.py proves, against a fake RPC
and a recording fake compute: a budget-interrupted cycle
checkpoints exactly the batches that completed; a restarted
engine resumes at the frontier with the two processes'
searched ranges disjoint and jointly complete; a completed
space is not rescanned; a new template identity starts fresh
with the reason recorded; a mid-round frontier resumes at
the exact nonce; the unit match rules (identity, space,
time basis, out-of-space frontier, corrupt file, completion
verdict); and that an engine without a checkpoint behaves
exactly as it did before this phase.
