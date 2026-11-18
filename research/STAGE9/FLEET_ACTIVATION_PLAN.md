# Fleet activation: design, staging proof, and cutover plan

Date: 2026-11-18. Owner approved fleet activation on
2026-11-18 (roadmap F2 gate). This document is the fleet
activation design and staging report for the Bitcoin
Autonomous Lab. It builds on EXP-055 (mining/coordinator.py),
EXP-057 (mining/aggregation.py), the Stage 9.2 promotion
decisions, and the Stage 9.4 gap analysis section C4.

## Verdict up front

The viable live fleet path for pool-sourced work is the
EXP-055 coordinator chunk protocol, fronted by one new
gateway process that owns the pool connection. The EXP-057
aggregation tier cannot carry pool work at all, for two
independent reasons established from its source in section
A; it remains the right fleet front-end for the post-sync
solo world, and the two mechanisms compose rather than
compete.

The gateway and the fleet worker were built (two new
modules, no existing file modified) and the full path was
proven end to end on this host against a local Stratum
stub: two independent worker processes leased disjoint
chunks of one pool job, examined exactly the declared
16,777,216 nonces with zero repetition, produced 17
candidate shares that the gateway re-verified and
submitted, and the stub pool accepted all 17 with zero
duplicates and zero rejections. All 22 driver checks
passed. Evidence: research/STAGE9/evidence_fleet/.

The live miner was NOT cut over. The live cutover is a
separate step, specified exactly in section F for the
parent to execute or approve. Real cross-machine behaviour
remains UNVERIFIED until a second machine actually joins;
section G is the full register.

## A. Which mechanism can carry pool-sourced work, from the code

### A.1 The aggregation tier cannot ingest pool work

mining/aggregation.py, AggregationTier.__init__ (line 83
at the baseline), builds exactly one upstream:
SoloServer(rpc, payout_address, ...). Its only workbase
source is refresh_workbase(), which calls
SoloServer.refresh_job() (mining/solo_server.py line 533),
which calls rpc.call("getblocktemplate", ...) against a
Bitcoin node. The tier constructs its own coinbase from
that template, paying its own payout address, and fans the
result out to downstream Stratum workers.

There is no code path by which a pool job could enter the
tier: it is a Stratum server, never a Stratum client; it
holds no pool connection; no method accepts externally
built notify params. Public-pool.io work exists only as
mining.notify jobs on the pool connection, with the
pool's coinb1 and coinb2. Nothing in the tier can receive
them.

Second, independent blocker: even the tier's native
workbase is unusable today. Our pruned mainnet node is in
initial block download at about 471,000 of 976,000
headers, so its getblocktemplate tip is a 2017 tip; jobs
built on it name a prevhash the current network rejected
years ago. This is the same staleness that keeps the
armed solo cutover waiting.

Conclusion: the aggregation tier is the fleet front-end
for node-sourced work. After the solo cutover fires (node
synced, current GBT available), the tier can fan that
workbase out to fleet workers with its stronger identity
model (operator enrollment tokens, tier-assigned
extranonce1 per session). For pool-sourced work today it
is not a candidate, and no staging was attempted on it
for that purpose; its EXP-057 proof and UNVERIFIED
register stand unchanged.

### A.2 The coordinator's job model is the pool job's search space

mining/coordinator.py, CoordinatorCore.declare_job
(line 338 at the baseline), builds slices keyed by
(slot, counter), with extranonce2 = (slot << 25) |
counter, crossed with version variants and ntime values,
each slice partitioned into nonce chunks over
[0, nonce_count). That is exactly the decomposition of a
Stratum pool job's search space under one pool session:
the session's extranonce1 is fixed, each worker owns one
extranonce2 slot, and the nonce range is chunked inside
it. Leases carry fencing tokens from one monotonic
counter; reports classify OK, DUPLICATE, STALE,
NOT_HOLDER, UNKNOWN_LEASE; the accounting identity
unique + pending + leased == declared is asserted by
assert_partition_invariant.

What was missing was never the coordinator. It was:

1. a pool-session owner that declares real pool jobs to
   the coordinator, distributes the job payload to
   workers, re-verifies candidates, and submits shares
   through the pool connection (the gateway, section B);
2. a worker program that leases chunks and hashes real
   headers with the production engine (the worker,
   section B).

The coordinator wire protocol has no job-payload op, so
the gateway's server subclass adds one read-only op,
job_info, served from gateway state and never journaled.
mining/coordinator.py itself is unmodified: sha256
b4215980cac03f0e11a772887cc08a6db37ca46df8032e481175940bae032eff,
byte-identical to the Stage 9.1 baseline, as is
mining/aggregation.py (1951a657b1be1968b484514a0defa70e4c10ce93ccc46beb0f0369b74d67c603).

### A.3 The direct-connection baseline is not fleet activation

Each remote machine could simply run mining/mainnet_live.py
against public-pool.io under its own worker name; the
owner's agent Nova already does exactly this, and the
pool's per-connection extranonce1 keeps the spaces
disjoint by construction. That is real mining, but it is
not activation under roadmap F2: there is no lab-side
coordination, accounting, fencing, or candidate
verification, and the lab can neither see nor steer it.
It remains the standing fallback: any enrolled machine
whose gateway is unreachable can be pointed back at the
pool directly by its operator, under its own worker name,
with no lab state to unwind.

## B. What was built

Two new modules. No existing file was modified.

### B.1 mining/fleet_gateway.py (sha256 f4ec8bfbda269738...)

One process, three parts:

- Pool session: mining.stratum_client.StratumClient,
  endpoint resolved by mining/endpoint_config exactly as
  mining/mainnet_live.py resolves it (arguments, then
  BAL_POOL_HOST and BAL_POOL_PORT, then
  .local/mining-endpoint.json, then the public-pool
  default). Authorizes as <payout address>.<worker>.
- Coordinator host: a FleetCoordinatorServer
  (CoordinatorServer subclass adding the job_info op),
  with its own state directory for the operation journal
  and snapshots, so the EXP-055 restart rule (epoch bump,
  all leases reclaimed, workers re-register) applies to
  the fleet unchanged.
- Declaration and submission loop: on every new pool job
  generation, declare_job(job_id = the pool job id,
  generation = the client job generation,
  nonce_count, chunk_size, n_slots,
  version_variants = [the job's version],
  ntime_values = [the job's ntime], counters_per_slot = 1)
  and publish the job payload through job_info. Every
  0.25 s it drains the candidate queue with an EXP-036
  verifier (verify_candidate over the reconstructed
  header, POW_LIMIT_MAINNET, the pool share target),
  drops candidates whose generation is no longer the
  freshest (counted, never submitted), and submits
  verified shares through its own pool connection. Pool
  verdicts are collected per fleet worker into the
  EXP-037 separated statistics (pool_shares_submitted,
  pool_shares_accepted, pool_shares_rejected, per worker),
  republished in a status evidence event every 10 s. A
  verified block candidate is submitted the same way and
  logged as its own event (block_candidate_submitted);
  the pool, not the gateway, is the block judge, exactly
  as on the live path today. The gateway also sends the
  coordinator an expire op every 30 s so dead workers'
  chunks are reclaimed.

### B.2 mining/fleet_worker.py (sha256 7d8ad97665631853...)

The only program a fleet machine runs. It registers with
the coordinator under the fleet id, heartbeats, and
loops: read the current job identity from the accounting
op, fetch the job payload from job_info, lease a chunk,
refuse the lease if its version or ntime does not match
the published payload, build the header with the
production build_header (wordswap prevhash mode, the
live path's convention), search with the production
ComputeEngine, hand every digest meeting the share target
to the candidate queue, report progress at half-chunk,
and complete the lease. It holds no wallet, no pool
account, and no keys, and it cannot submit anything to
the pool: submission exists only in the gateway.

### B.3 The examination-honesty finding (staging run 1)

A completion tells the coordinator the whole chunk was
examined, so the worker must be able to certify that.
Staging run 1 used the engine the way the live miner does
(multithreaded early-exit search, scan position advanced
past each hit) and the attempt accounting exposed the
flaw: one worker over-counted its slice by 247 attempts
(re-examining nonces past a hit that other threads had
already covered) and the other under-counted by 173,346
(its scan position jumped past a hit while other threads'
sub-ranges behind that hit were never examined). The
engine itself is honest: it reports the examined count
and never claims a prefix. The live pool path accepts
this because it makes no coverage promise. The
coordinator's completion does make one.

Fix, now part of the worker's design: the worker pins
its engine to one search thread (ComputeEngine threads=1),
under which each call's examined set is exactly a prefix
of the requested span, and advances its scan position by
the engine's own attempted count, hit or miss. Chunks
then tile exactly: in runs 2 and 3 the summed attempted
count per slice equals the slice size to the nonce.
Scale on a multicore machine is by running more worker
processes (each with its own worker id and coordinator
slot), never by widening one worker's search threads.

## C. Staging proof (this host, isolated, loopback only)

Harness (in evidence_fleet/): stub_pool.py, a local
Stratum V1 stub that serves one synthetic-but-structural
job (real field shapes; nbits 0x17021673, a real recent
mainnet nbits taken from the Stage 9.6 evidence; share
difficulty 0.0002) and acts as the duplicate oracle: it
reconstructs every submitted header with the production
build_header, judges the digest against the exact target,
and refuses a second submission of any
(job_id, extranonce2, ntime, nonce) key as a duplicate.
drive.py orchestrates and cross-audits four independent
records: coordinator accounting, gateway evidence, stub
pool log, and both worker logs.

Configuration: stub on 127.0.0.1:14031, coordinator on
127.0.0.1:14032, fleet id nova-fleet-staging, declared
job of 2 slices x 2^23 nonces in 2^20 chunks, n_slots 2.
Workers w-fleet-a (slot 0, extranonce2 0) and w-fleet-b
(slot 1, extranonce2 33,554,432), both on the v512dual
backend, one search thread each. Expected shares at the
stub difficulty over 16,777,216 hashes: about 19.5
(0.0002 x 2^32 = 858,993 expected hashes per share).

Three runs were made; all are preserved in the evidence.

- Run 1: FAIL on two driver checks. attempts_equal_declared
  failed (the multithreaded examination flaw of section
  B.3) and gateway_all_shares_accepted failed on a driver
  bug (it counted the StratumClient's own share_result
  lines in the shared evidence file alongside the
  gateway's per-worker lines). All substantive checks
  (disjointness, duplicates, accounting) already passed.
- Run 2: the threads=1 worker fix made attempts exact.
  One driver check still failed: the gateway republishes
  its EXP-037 totals on a 10 s cadence and the run's
  mining finished inside one cadence, so the last status
  event predated the final verdicts. A driver timing
  artifact, not an accounting error; the driver now waits
  for the totals to catch up before judging them.
- Run 3: PASS, all 22 checks. Final numbers:

  - Coordinator accounting at completion: declared
    16,777,216; unique coverage 16,777,216; actual
    computations 16,777,216; repeated computations 0;
    duplicate deliveries 0; stale reports 0; not-holder
    attempts 0; reclaims 0; complete true; partition
    invariant held.
  - Completed intervals: per slice, 8 chunks tiling
    [0, 8,388,608) contiguously, disjoint across slices.
  - Workers: each completed exactly its own slot's 8
    chunks; summed attempted counts 8,388,608 per worker,
    equal to the slice size exactly.
  - Candidate queue: submitted 17, verified 17,
    duplicates 0, stale-generation dropped 0, pending 0;
    all 17 classified "share" by the gateway's EXP-036
    verifier.
  - Gateway: 17 shares submitted to the stub, 17
    accepted, 0 rejected; EXP-037 totals
    pool_shares_submitted 17, pool_shares_accepted 17,
    pool_shares_rejected 0 (per-worker: w-fleet-a 11,
    w-fleet-b 6).
  - Stub oracle: 17 judged, 17 accepted, 0 duplicates,
    0 rejected; every accepted (job_id, extranonce2,
    nonce) key distinct.
  - Fencing and duplicate probes against the same
    coordinator after the main evidence was snapshotted:
    foreign fleet registration refused (FOREIGN_FLEET);
    completion by a non-holder classified NOT_HOLDER;
    completion with a wrong token classified STALE;
    a replayed candidate classified DUPLICATE by the
    queue; a completion then its replay classified OK
    then DUPLICATE.
  - Live stack: heartbeat read before and after the run
    showed the same autopilot pid (3144) and miner pid
    (3156), miner running, shares 1,128 and non-decreasing.
    The staging never connected to the real pool, never
    read or wrote the endpoint config, and bound only
    127.0.0.1.

Regression: with the two new modules present and no
existing file changed, make test-exp055 (23 checks) and
make test-exp057 (15 checks) both pass
(evidence_fleet/test_exp055.out, test_exp057.out).

Environmental note: at about 10:03 UTC, after the staging
had completed and been verified, a host service restart
stopped the live stack (miner exited rc=-15, autopilot
later gone, heartbeat frozen at 10:03:34Z with 1,129
shares). This is the known VM-replacement pattern;
restoration belongs to the bal-mainnet-keeper cron and
was left to it. It is recorded here because it followed
the staging in time, not because the staging caused it:
the staging's own live-stack check passed at completion
with the stack running.

## D. Production activation specification

Processes (all on this VM unless stated):

1. Fleet gateway: python3 mining/fleet_gateway.py, run as
   the autopilot's miner child in place of
   mining/mainnet_live.py (section F). Parameters:
   endpoint from the existing endpoint config (pool mode,
   public-pool.io:21496, unmodified); --coord-host
   <this VM's Tailscale address>; --coord-port 4033;
   --state-dir .local/fleet; --nonce-count 4294967296
   (2^32, the full nonce range per slice); --chunk-size
   16777216 (2^24); --n-slots 32; --heartbeat-timeout 120;
   --starvation-window 120; worker lease TTL 300 s
   (worker-side default).
2. Coordinator: hosted inside the gateway process (no
   separate process). State in .local/fleet (journal,
   snapshots, candidate journal).
3. Fleet workers: on remote machines, section E. A worker
   on this VM is also possible during the soak (section
   F, step 3).

Bind decision: the coordinator binds to the Tailscale
interface address only, never 0.0.0.0 and never a public
interface. Reason: the coordinator protocol's only
admission check is the fleet id at registration; there is
no per-worker token in EXP-055 (token enrollment exists
only in the aggregation tier). The tailnet is the lab's
existing private overlay for reaching the owner's other
machines, and its ACLs are the network-layer control.
The fleet id is treated as a shared secret: chosen by
the operator at activation, passed to workers out of
band, never committed to the repo. Rotating it means
restarting the gateway with a new id; workers with the
old id are refused as a foreign fleet. Staging bound
127.0.0.1 only, and this VM's own Tailscale address and
its reachability from a second machine must be confirmed
at activation time (during this staging the Tailscale
connector reported this host enrolled, not verified).

Capacity notes, from the coordinator's construction:
extranonce2 is (slot << 25) | counter with
counters_per_slot 1, so a 4-byte extranonce2 space (the
pool's current size) admits slots 0 to 127; n_slots 32
caps concurrent workers per job at 32. Declaring a job
builds one chunk record per chunk per slice: at the
production parameters that is 32 slices x 256 chunks =
8,192 records per declaration, rebuilt on every pool job.
The staging declared 16 records per job; the declaration
cost at production width was not measured and is in the
UNVERIFIED register.

Enrollment (operator acts):

1. Choose the production fleet id and coordinator port
   (4033 proposed).
2. For each worker process: assign a unique worker id by
   convention <machine>-<index> (for example nova-1,
   nova-2 for two processes on one machine; htch-1 for
   one here).
3. Give the machine's operator, out of band: gateway
   Tailscale address, port, fleet id, and their worker
   ids. There is no enrollment call to make: registration
   is the worker's first act, checked against the fleet
   id. The operator confirms enrollment after the fact in
   the gateway evidence (the worker appears in status
   events' coordinator accounting and its shares appear
   under its worker id).

## E. What a remote machine must run to join

Concrete steps for the operator of any other machine
(for example the owner's other agents):

1. Install this repo at the activation HEAD (git clone of
   kilomene/Bitcoin-Autonomous-Lab, or a copy of the
   tree). The native CPU backend libraries under
   .local/cpu should be present or built per the repo's
   build steps; without them the ComputeEngine probe
   falls back through its dispatch order to the C or
   hashlib tiers and the worker still mines, slower.
   No other setup: no wallet, no pool account, no keys,
   no Bitcoin node.
2. Receive from the lab operator, out of band: the
   gateway's Tailscale address, port 4033, the fleet id,
   and the worker id(s) assigned to this machine. The
   machine must be on the same tailnet.
3. Start one worker process per assigned worker id:

   python3 mining/fleet_worker.py \
     --gateway-host <gateway Tailscale address> \
     --gateway-port 4033 \
     --fleet <fleet id> \
     --worker-id <assigned id> \
     --log <a writable path for its JSONL log>

   Run as many processes as the machine has CPU capacity
   for; each process searches single-threaded by design
   (section B.3), so one process per core is the intended
   density.
4. Keep the processes running under whatever supervisor
   that machine already uses. Behaviour on failures: if
   the gateway's coordinator restarts with its state
   intact, the worker recovers in place (its leases are
   reclaimed, it leases fresh chunks; a completion against
   a dead lease is classified STALE and the chunk is
   abandoned uncompleted). If the coordinator's state is
   wiped, the worker's heartbeat is refused as unknown and
   the worker exits; the local supervisor restarts it and
   it registers fresh. If the gateway is unreachable, the
   worker's connection fails and it exits; same restart
   path.
5. Payout needs nothing on the remote machine: all shares
   are submitted by the gateway under the lab wallet
   bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3. Leaving
   the fleet is stopping the processes; there is no
   deregistration step (the coordinator's heartbeat
   timeout and expiry reclaim the worker's chunks).

## F. Live cutover steps remaining (parent to execute or approve)

Not performed by this staging. In order:

1. Confirm this VM's Tailscale address (tailscale ip -4)
   and its reachability from one intended fleet machine.
2. Choose the production fleet id and confirm port 4033.
3. Standalone soak against the real pool, live miner
   untouched: start the gateway by hand with
   --worker <hostname>-fleetgw (a distinct pool worker
   name, so its session cannot be confused with the live
   miner's), coordinator bound to the Tailscale address,
   state dir .local/fleet-soak. Confirm from its evidence
   that it authorizes, declares each pool job, and idles
   with zero submissions. Then start one local worker
   against it (pointed at the Tailscale address) and
   confirm end-to-end shares under that worker's id at
   the pool's real difficulty (the pool clamps difficulty
   to a minimum of 1, so expect roughly one share per
   2^32 hashes per worker, minutes to tens of minutes per
   share at fleet rates). Measure declare_job cost at
   production width during this soak. Stop both processes.
4. Post-integration audit of mining/fleet_gateway.py and
   mining/fleet_worker.py by an auditor who did not write
   them (standing owner rule for production integrations),
   covering at minimum the submission path and the
   threads=1 examination claim.
5. The cutover itself: add one Environment line to
   scripts/bal-autopilot.service,
   Environment=BAL_AP_MINER_CMD=["/usr/bin/python3","mining/fleet_gateway.py","--duration","86400","--coord-host","<Tailscale address>","--coord-port","4033","--state-dir",".local/fleet","--evidence",".local/fleet/fleet-gateway.jsonl"]
   (the autopilot already honours BAL_AP_MINER_CMD as a
   full miner-command override, mining/autopilot.py
   line 545; the gateway's pool worker name then defaults
   to the same hostname-based name the autopilot computes,
   or set BAL_WORKER in the unit to pin it), reinstall the
   unit with scripts/autopilot.sh install-service, and
   restart the autopilot service. From that moment the
   autopilot supervises the gateway exactly as it
   supervised the miner: same endpoint config, same
   evidence discipline, miner child restarted on exit.
6. Enroll remote machines per section E, one at a time,
   confirming each in the gateway evidence before the
   next.
7. Rollback, at any point: remove the BAL_AP_MINER_CMD
   line, reinstall the unit, restart the autopilot.
   mining/mainnet_live.py resumes on the unmodified
   endpoint config. No state migration exists in either
   direction; the coordinator's .local/fleet directory is
   simply left behind.

Risk statement for the parent: cutting over replaces a
proven single process with a gateway plus coordinator
whose only full-path proof is this loopback staging
against a stub. The failure modes are bounded (the
autopilot restarts the gateway; the coordinator recovers
from its journal; rollback is one unit edit), but the
soak in step 3 and the audit in step 4 are what stand
between this staging and the live path, and neither
should be skipped.

## G. UNVERIFIED register

- Multi-machine operation: UNVERIFIED. No second machine
  has joined. Everything in section C is one host,
  loopback, two worker processes.
- Real-network behaviour: UNVERIFIED. Latency, partial
  failure, and clock skew across machines (coordinator
  deadlines consume caller-supplied clock readings, the
  EXP-035 skew mitigation, untested across real clocks)
  are all unmeasured.
- Live cutover: NOT PERFORMED and UNVERIFIED. The gateway
  has never connected to public-pool.io. Behaviour under
  the pool's real job cadence, its difficulty floor of 1,
  its reconnect behaviour, and template churn (each new
  job supersedes the declared job and kills in-flight
  leases; staging served one static job, and supersession
  was exercised only by the driver's probe declaration)
  is UNVERIFIED.
- Block candidate path through the gateway: UNVERIFIED
  in this staging. All 17 candidates classified "share";
  the block_candidate drain-and-submit branch is
  code-reviewed but was not executed end to end here. (The
  same confirmation discipline is proven on the GBT path
  by Stages 9.3 and 9.5, not through this gateway.)
- Declaration cost at production width (8,192 chunk
  records per job): UNVERIFIED; staging declared 16.
  Measure during the section F soak.
- Fleet width: UNVERIFIED beyond 2 workers and 2 slots.
  n_slots 32 is a configuration choice, not a measurement.
- Coordinator restart recovery in the gateway-hosted
  form: UNVERIFIED here. The standalone coordinator's
  recovery is proven (EXP-055 Gate 5); the gateway was
  terminated by the driver at teardown and its state
  directory holds the journal and candidate journal, but
  no restart-and-resume cycle was run in this staging.
- Tailscale reachability of this VM from a fleet machine:
  UNVERIFIED (see section D).
- Aggregation tier against a real upstream or a second
  machine: UNVERIFIED, unchanged from the EXP-057
  register. Its fleet role begins only when a synced node
  can serve it current templates.
- Coordinator admission strength: the fleet id is the
  only gate (no per-worker token). This is a known design
  limitation carried from EXP-055, mitigated by the
  tailnet bind and ACLs, not a measured property.

## Evidence index (research/STAGE9/evidence_fleet/)

- summary.json: run 3 (PASS) full driver record, with
  accounting, queue, probe, and live-stack snapshots.
- summary_run1.json, summary_run2.json: the two earlier
  runs and their failing checks, as analysed in
  sections B.3 and C.
- gateway.jsonl: run 3 gateway evidence (declarations,
  submissions, per-worker verdicts, status events).
- stub.jsonl: run 3 stub pool judgment log.
- worker-w-fleet-a.jsonl, worker-w-fleet-b.jsonl: run 3
  worker logs (registrations, chunk intervals, attempts,
  candidates, completions).
- drive.py, stub_pool.py: the harness as run.
- test_exp055.out, test_exp057.out: regression suites.
- gateway.stdout, worker-w-fleet-a.stdout,
  worker-w-fleet-b.stdout: process output captures.

## H. Production soak attempt, 2026-11-18: stopped at the coordinator bind

Date: 2026-11-18. This section records the execution of
section F steps 1 to 3 (fleet id, Tailscale bind, standalone
real-pool soak) by the fleet soak agent. The soak STOPPED
at the coordinator bind: the bind is a failed safety
property on this VM today, no fallback bind was attempted,
and the worker was never started. What was measured before
the stop is recorded with numbers; the rest is stated
plainly as not performed.

### H.1 Step 1 and 2 outcomes: fleet id and bind address

- Production fleet id: generated from a CSPRNG (64 hex
  characters) and stored only in .local state at
  .local/fleet/fleet_id.txt, mode 0600. It is referred to
  here and in the soak handoff only by that storage path,
  never by value. The soak launchers read it in-process so
  it never appeared in any OS process list or shell
  command line.
- This VM's Tailscale IPv4 address: 100.80.59.125, from
  the tailscale CLI (the "tailscale ip -4" flag form is
  unsupported by this client build; the plain "tailscale
  ip" output was used). The CLI reports the host enrolled
  and Connected.
- Port 4033 was free on this host before the start.

### H.2 declare_job cost at production width: measured

Measured in-process before the soak, through the same
CoordinatorServer.handle_message declare path the gateway
uses, with the production parameters (nonce_count 2^32,
chunk_size 2^24, n_slots 32, counters_per_slot 1; one
version variant, one ntime value), against a throwaway
state directory. CoordinatorCore.declare_job materializes
every chunk record eagerly (32 slices x 256 chunk records
= 8,192 records; declared_total 137,438,953,472 = 32 x
2^32). Three declarations: 0.026 s for the first (fresh
state, journal append included), 0.004 s and 0.003 s for
superseding declarations. Verdict: declaration cost at
production width is viable at the pool's real job cadence
by roughly two orders of magnitude; the register item
"declaration cost at production width UNVERIFIED" is
CLOSED by this measurement. The gateway's own declarations
during H.3 ran at the same production width.

### H.3 The gateway's pool leg worked; the coordinator leg never existed

The gateway was started by hand at 2026-11-18T12:44:11Z
(NOT under the autopilot), worker name
htch-runtime-fleetgw, state dir and evidence under
.local/fleet. Its pool leg behaved exactly as specified:

- Endpoint resolved by mining/endpoint_config exactly as
  the live miner resolves it: public-pool.io:21496, mode
  pool (evidence event endpoint_selected).
- Subscribed (extranonce2 size 8) and authorized as
  bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3.htch-runtime-fleetgw.
- The gateway suggested difficulty 0.001; the pool set
  difficulty 1. The pool's difficulty floor of 1 is
  therefore confirmed empirically for this session type,
  not only from the plan.
- Three real jobs arrived and were declared in-process at
  production width inside about 32 seconds: job 6b502b
  generation 1 at 12:44:17Z, job 6b5bc5 generation 2 at
  12:44:47Z, job 6b6744 generation 3 at 12:44:49Z, all at
  difficulty 1.0, nbits 17021673 (network difficulty
  134,823,837,323,272.66 on the validated template). Real
  job changes from the pool were therefore observed on
  the gateway's pool leg at a cadence of seconds to tens
  of seconds.
- Submissions: zero. No candidate could be produced,
  because no worker could ever connect (H.4). Gateway
  session accounting for the fleetgw worker: submitted 0,
  accepted 0, rejected 0, dropped_stale 0,
  dropped_invalid 0.

### H.4 The bind failure, root cause, and a gateway defect

The coordinator serve thread died at startup:
srv.bind((100.80.59.125, 4033)) raised OSError Errno 99,
Cannot assign requested address. Root cause, established
by direct inspection: the address 100.80.59.125 is not
assigned to any interface in this VM's network namespace.
The namespace has exactly two IPv4 interfaces, lo
(127.0.0.1) and host0 (198.19.0.2); there is no tailscale0
interface and no tailscaled process in-namespace. An
isolated test bind to 100.80.59.125 reproduced Errno 99.
The Tailscale connector reports the enrolled address, but
on this VM it provides no bindable tailnet interface
inside the namespace (consistent with userspace or
out-of-namespace operation). Binding the coordinator to
the Tailscale interface address from inside this VM is
therefore impossible today. Per the bind decision
(section D), binding 0.0.0.0 or the host0 address instead
was NOT attempted: either would expose a fleet-id-only
admission protocol on a non-tailnet interface. ss showed
nothing listening on port 4033 at any point.

Gateway defect found, recorded for the section F step 4
audit: FleetGateway.run waits up to 5 seconds for
server._tcp to appear, then logs "coordinator_listening"
unconditionally. The bind had already failed, _tcp was
never set, and the evidence nevertheless claims listening
at 12:44:16Z while the exception sat in the process's
stdout. The gateway then ran pool-connected and declaring
in-process, deaf to all workers, with its evidence
asserting the opposite. A failed coordinator bind must
be a fatal, evidence-visible error before the cutover.

Second defect-adjacent finding for the audit: the gateway
logs the fleet id itself in its coordinator_up evidence
event. In this soak the evidence lived under .local/fleet
and stays local. But the section F step 5 cutover command
sets --evidence evidence/fleet-gateway.jsonl, a
repo-relative path; if that file were ever committed, the
fleet id would leak with it. Before the cutover, either
the evidence path must stay under .local or the
coordinator_up event must stop carrying the fleet id.

### H.5 Actions taken and live stack state

- The worker (soak-local-0) was never started.
- The gateway was terminated by SIGTERM at about
  12:45 UTC, roughly 90 seconds after start, once the
  bind failure and its root cause were confirmed. It did
  not write a clean-exit snapshot; the coordinator state
  in .local/fleet (journal.jsonl, candidate_journal.jsonl)
  stands as it was, and the EXP-055 restart rule (replay,
  epoch bump, leases reclaimed) applies to any future
  gateway start against that directory.
- Live stack, read-only checks only, undisturbed:
  before (heartbeat 2026-11-18T12:43:15Z) autopilot pid
  4349, miner pid 4352, miner_state running, restarts 0,
  shares_accepted_total 1,151. After (heartbeat
  2026-11-18T12:45:12Z) the same pids, running, restarts
  0, shares_accepted_total 1,153. The live miner worked
  throughout; the gateway's separate pool session never
  touched it, the endpoint config, or any service.

### H.6 Soak goal scorecard

1. Gateway connects to the real pool, receives real jobs
   at the real difficulty, declares them: PROVEN for the
   pool leg and the in-process declaration (H.3); the
   declarations were never visible to any worker because
   the coordinator had no listener.
2. Worker leases chunks, hashes, returns candidates:
   NOT PERFORMED (worker never started).
3. Candidates verified in the gateway and submitted to
   the real pool: NOT PERFORMED (no candidates existed).
4. Pool-accepted vs rejected for the fleetgw session:
   0 submitted, 0 accepted, 0 rejected.
5. declare_job cost at production width: MEASURED, see
   H.2. Viable; register item closed.
6. Real job change observed: YES on the pool leg, three
   jobs in about 32 seconds (H.3); no worker-visible job
   change could occur.

### H.7 UNVERIFIED register, updated

- NEW BLOCKER: coordinator bind to the Tailscale
  interface on this VM: IMPOSSIBLE today (H.4). Fleet
  activation over the tailnet cannot proceed until this
  VM gains a bindable tailnet interface (for example an
  in-namespace tailscaled in tun mode), or the parent
  approves a different private path that preserves the
  bind decision's intent. Reachability of this VM from a
  fleet machine stays UNVERIFIED and is now downstream of
  this blocker.
- Multi-machine operation: UNVERIFIED, unchanged. No
  second machine has joined; nothing in this attempt
  changes that.
- End-to-end fleet shares at the real pool through the
  gateway and a worker: UNVERIFIED. The pool leg alone
  (connect, authorize, difficulty floor 1, real jobs,
  production-width declarations) is now VERIFIED as far
  as H.3 states, and no further.
- Gateway bind-failure masking (H.4): defect recorded;
  fix and re-verification belong to the step 4 audit and
  the cutover preparation, not to this soak.
- Everything else in section G stands unchanged:
  real-network behaviour, block candidate path through
  the gateway, fleet width beyond staging, coordinator
  restart recovery in gateway-hosted form (this attempt
  adds one data point: an unclean gateway stop leaves a
  replayable journal, recovery itself still unexercised),
  and the aggregation tier register.

## I. H.4 fixes applied, 2026-11-18

Date: 2026-11-18. Both findings of H.4 are fixed in the
working tree (not pushed; the push belongs to the step 4
audit's clearance, as does the cutover). The live stack
was not touched by this work.

### I.1 Fix 1: a failed coordinator bind is fatal

mining/fleet_gateway.py no longer waits on a timer and
logs coordinator_listening unconditionally. The serve
call now runs in a wrapper thread target
(_serve_coordinator) that captures any exception from
CoordinatorServer.serve (which binds before its accept
loop, so a bind failure raises there) into _coord_error
instead of letting it die silently on stderr. run()
then waits for a fact: the listener's _tcp set (serve
sets it only after bind and listen succeed), a captured
startup error, or a bounded 10 second deadline. On
failure it writes a coordinator_bind_failed evidence
event carrying the host, port, and the error itself,
and returns exit code 4 before the pool leg starts: no
coordinator_listening, no pool connection, no declaring.
On success coordinator_listening is written only after
the bind is confirmed. mining/coordinator.py is
unchanged (it already raises on bind; the missing hook
was the gateway's failure to listen for that raise), so
the EXP-055 baseline file stays byte-identical.

### I.2 Fix 2: the fleet id never reaches a produced file

Three closes, in the two fleet modules:

1. The gateway's coordinator_up evidence event no
   longer carries the fleet id. It carries fleet_fp,
   the first 12 hex characters of the id's SHA-256:
   non-reversible, and enough to correlate runs of the
   same fleet. (Fingerprint chosen over omitting the
   field entirely, for that correlatability.)
2. The gateway's default --evidence path moved from
   the repo-relative evidence/fleet-gateway.jsonl to
   .local/fleet/fleet-gateway.jsonl, and the section F
   step 5 cutover command above now passes
   --evidence .local/fleet/fleet-gateway.jsonl as
   well. Fleet runtime artifacts live under .local by
   default and by plan, not merely by operator care.
3. A second leak path found by audit of the two
   modules: mining/coordinator.py's FOREIGN_FLEET
   refusal detail embeds both fleet ids (presented and
   expected), and mining/fleet_worker.py's call()
   raised with the full response, so a refused worker's
   stderr or captured stdout (the staging evidence
   keeps exactly such .stdout files) would carry the
   real fleet id. The worker now names refusals by
   error code only. The refusal stays diagnosable
   (FOREIGN_FLEET says what happened) and carries no
   id.

Residuals, stated plainly. The FOREIGN_FLEET detail on
the wire still contains the ids: the root fix belongs
to mining/coordinator.py, which this change
deliberately does not touch (pinned EXP-055 baseline);
the file-leak path is closed at the worker, the only
client these modules ship, and any future client must
be held to the same error-code-only rule. Separately,
the coordinator journal and snapshot under the state
dir contain the fleet id by design (journal replay
must re-execute register ops; the snapshot stores core
state). Both the gateway default and the step 5
command keep --state-dir under .local/fleet; that
discipline is load-bearing and is now recorded here.

### I.3 Test evidence

New suite tests/test_fleet_gateway.py, wired into the
Makefile as test-fleet-gateway and added to test-all
(test-all grows by one suite). 23 checks, ALL PASSED,
run 2026-11-18 on this host, everything on loopback
against an in-process stub pool, all outputs in
temporary directories:

- Unbindable coordinator address (192.0.2.1, RFC 5737
  TEST-NET-1, the soak's Errno 99 shape): exit code 4
  in 0.6 s against a 120 s duration,
  coordinator_bind_failed written with the error,
  coordinator_listening never written.
- Loopback start: coordinator_listening written, and
  the port verifiably accepts a connection at the
  moment the event exists; a worker registers over
  TCP, completes all chunks and the whole job, exits
  0; the gateway declares the stub job.
- Wrong-fleet worker: refused with a nonzero exit, its
  captured output names FOREIGN_FLEET and contains
  neither the presented nor the expected fleet id.
- Full run with a known dummy fleet id: the id string
  is absent from the gateway evidence, the gateway
  stdout, the worker log, and the worker stdout;
  coordinator_up carries the id's fingerprint as
  fleet_fp and no event carries a fleet field.

Regression suites, run one at a time after the fixes:
test-exp055, 23 checks, ALL PASSED; test-exp057, 15
checks, ALL PASSED. A tree-wide grep (excluding .local)
for the suite's dummy ids matches only the test source
that defines them; no produced file in the tree
contains them.

## J. D-1 root fix applied, 2026-11-18

The fleet audit (research/STAGE9/FLEET_AUDIT.md, defect
D-1, item 5 ruling) required the FOREIGN_FLEET wire
residual left open in section I to be root-fixed in
mining/coordinator.py before activation: a refused
registration returned both fleet ids in its wire
detail, and the fleet id is the fleet's only admission
credential, so the refusal was a credential oracle.
That fix is now applied.

The change is one message. CoordinatorCore.
register_worker raises ForeignFleetError with "worker
%s presented a foreign fleet id" (the worker id only).
Neither the presented nor the expected fleet id
appears in the message, and therefore not in the wire
"detail" CoordinatorServer returns for a refused
registration. Nothing else changed: admission
decisions, the journal and snapshot format (both still
carry the fleet id by design, under the state dir),
chunk accounting, and every other error code and
detail behave exactly as before. A full grep of
mining/coordinator.py confirms the fleet id value now
flows only to construction, the register comparison,
and snapshot store and restore; every other error
message in the module names worker ids only. Two
examined sites were deliberately left: main()'s
startup print echoes the operator's own --fleet
command-line value to that same operator's stdout (not
a wire field, not an error, disclosed to nobody else),
and the EXP-035 research prototype
research/sha256d/exp035/lease_manager.py carries the
same legacy string (historical research code, imported
by nothing in mining/, not part of the fleet path).

Pin update. The section A.2 statement that
mining/coordinator.py is byte-identical to the Stage
9.1 baseline is superseded by this section. The Stage
9.1 pin, sha256
b4215980cac03f0e11a772887cc08a6db37ca46df8032e481175940bae032eff,
is RETIRED. The current pin for mining/coordinator.py
is sha256
27c20bcbb4a6b75e1df8187c0556249f484235871ae38e01c937d2e2992d1b7b.
mining/aggregation.py is unchanged
(1951a657b1be1968b484514a0defa70e4c10ce93ccc46beb0f0369b74d67c603).
The old pin's other appearances
(REPOSITORY_BASELINE.md, STAGE9_FINAL_AUDIT.md,
FIXES_BATCH_AUDIT.md, FLEET_AUDIT.md) are dated
historical records and stand as written; this section
is the current pin assertion.

Re-verification, per the audit's item 5 protocol, run
2026-11-18 on this host, suites one at a time:

- test-exp055: 23 checks, ALL PASSED, including gate
  6 (a regtest block through coordinator-assigned
  work). No test pinned the old detail text, so no
  test edit was needed there.
- test-fleet-gateway: 24 checks, ALL PASSED. One
  check was added (check 14): a raw protocol probe
  registers with a wrong dummy fleet id and asserts
  the raw wire response is refused with FOREIGN_FLEET
  and its detail contains neither the presented nor
  the expected dummy id. Against the pre-fix
  coordinator the detail embedded both ids, so the
  check fails there by construction. The suite count
  grows from 23 to 24.
- The staging evidence in
  research/STAGE9/evidence_fleet/ is historical and
  was not re-run or modified; its recorded
  FOREIGN_FLEET detail, with staging dummy ids,
  remains the record of the pre-fix wire format.

With this fix, the audit's re-verification conditions
for the D-1 gate on plan F steps 5 and 6 are met on
the code side. Activation itself remains subject to
the coordinator hosting decision and the rest of the
cutover procedure.
