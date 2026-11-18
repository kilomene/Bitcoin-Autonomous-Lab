# Fleet enrollment: running one machine of the Bitcoin Autonomous Lab fleet

This document enrolls one additional machine into the lab
fleet. It is grounded in the code at commit 7cb12782 and in
the proven single-machine run recorded in
research/STAGE9/FLEET_ACTIVATION_PLAN.md (sections K and L).
Every command below is copy-pasteable and matches the code
as written; where the code forces a per-machine edit, the
edit is stated exactly and flagged as an edit.

## 1. The architecture: what it is and is not

Under the owner's architecture decision of 2026-11-18, each
fleet machine is independent. A fleet machine runs, locally:

- one gateway process (mining/fleet_gateway.py) holding
  that machine's own Stratum session to the pool,
  authorized as the lab payout address plus the machine's
  own pool worker name;
- inside the gateway process, one coordinator
  (mining/coordinator.py) bound to loopback only,
  127.0.0.1 port 4033, which splits the current pool job
  into chunks and leases them to the machine's workers;
- one worker process per core (mining/fleet_worker.py)
  leasing chunks from that local coordinator, hashing
  them, and returning candidates to the gateway, which
  re-verifies every candidate (EXP-036) before submitting
  anything to the pool.

The three processes are started and supervised as one
bundle by the launcher, mining/fleet_local.py.

What it is not:

- No machine connects to another machine's coordinator,
  and no coordinator accepts inbound connections from
  anywhere except the same machine's loopback. Never bind
  the coordinator to 0.0.0.0 or to any external interface:
  the coordinator protocol's only admission check is the
  fleet id at registration, so loopback is the network
  layer control.
- There is no central enrollment server and nothing to
  register with this VM or with any other machine. This
  VM learns of a new machine only from the pool-side
  presence of its worker name and from its operator's
  report.
- The machine holds no wallet, no private keys, no pool
  account credentials, and no Bitcoin node. It cannot
  spend or redirect anything.
- Search spaces stay disjoint across machines because
  the pool gives each machine's session its own
  extranonce1. Inside one machine, the coordinator's
  chunk accounting (disjoint leases, fencing, one holder
  per chunk) keeps that machine's workers disjoint.

The fleet id is a local admission credential only. The
gateway's coordinator checks it when a local worker
registers; a process presenting a different id is refused
as a foreign fleet. The id is generated on the machine,
stored on the machine, and never transmitted anywhere:
not to the pool, not to another machine, not in any log
(the gateway evidence records only fleet_fp, the first 12
hex characters of the id's SHA-256).

## 2. Prerequisites

- This repo, at commit 7cb12782 or later:

      git clone https://github.com/kilomene/Bitcoin-Autonomous-Lab.git
      cd Bitcoin-Autonomous-Lab
      git rev-parse HEAD

- Python 3 (the production host runs Python 3.12; the
  fleet modules use the standard library only).
- Outbound TCP access to public-pool.io port 21496.
- Optional but recommended: a C compiler (gcc) and the
  OpenSSL development headers, to build the native search
  backends (section 5). Without them the machine still
  mines, on the fallback tiers described there.

## 3. Step 1: generate the fleet id

Run in the repo root:

    mkdir -p .local/fleet
    python3 -c "import secrets,sys; sys.stdout.write(secrets.token_hex(32))" > .local/fleet/fleet_id.txt
    chmod 600 .local/fleet/fleet_id.txt

secrets.token_hex(32) returns 64 hex characters from the
operating system's CSPRNG. Rules for the id, all enforced
by the mechanism rather than by trust:

- Never print it, never paste it anywhere, never send it
  to anyone. There is no step in this document that needs
  its value.
- Never pass it on a command line. The gateway and the
  workers accept --fleet-id-file PATH and read the value
  in-process at startup; the launcher passes only the
  path (.local/fleet/fleet_id.txt by default) and never
  reads the value at all. (Both modules also accept a
  --fleet value whose default is the literal string
  nova-fleet; that form exists for isolated tests and
  must not be used in production, because a command line
  value is visible in process listings.)
- Rotating the id means generating a new file and
  restarting the bundle; local workers still presenting
  the old id are refused as a foreign fleet.

## 4. Step 2: choose the machine's pool worker name

Each machine MUST use its own distinct pool worker name.
Two machines sharing one name would share one pool
identity; distinct names are what the pool-side accounting
and the per-session extranonce separation assume.

The name is a launcher argument, not a code edit:
mining/fleet_local.py option --worker (its default is
htch-runtime, this VM's name; do not reuse it). The
gateway authorizes to the pool as:

    bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3.<worker name>

Choose a short name unique to the machine, for example
the hostname with a fleet suffix (atlas-fleetgw) or any
name the operator assigns. Keep it to lowercase letters,
digits, and dashes: the name travels inside the Stratum
authorize string, and the lab's naming code keeps worker
names to that alphabet.

## 5. Step 3: worker topology, and the search backends

### Worker processes

Run one worker process per physical core. Worker ids
follow the convention <machine>-<index>: for a four-core
machine named atlas, atlas-0, atlas-1, atlas-2, atlas-3.

The ids are a launcher argument, not a code edit:
mining/fleet_local.py option --worker-ids takes a
comma-separated list (its default is local-0,local-1, the
two workers of the proven run on this VM). The launcher
starts one worker per listed id, restarts a worker that
dies while the gateway lives (per-worker backoff, 2 s
doubling to a 60 s cap), and stops all workers when the
gateway exits.

Each worker pins its search engine to a single thread:
mining/fleet_worker.py constructs
ComputeEngine(requested="auto", threads=1). This is
load-bearing, not a performance choice. The production
engine's multithreaded early-exit search cannot certify
that a chunk was examined completely; the single-thread
search examines an exact prefix of the requested span, so
the engine's own attempted count certifies the span.
Scale is therefore by worker processes, never by search
threads. Do not edit the threads pin.

One bound from the coordinator's construction: the
launcher passes --n-slots 32 to the gateway, so at most
32 workers can hold chunks of one job on one machine.
On the proven host, roughly 2 effective CPUs meant 2
workers roughly saturated the machine; more workers than
effective cores adds contention, not rate.

### Search backends on a fresh machine

The native backend libraries are built locally into
.local/cpu/ (gitignored); a fresh clone contains none of
them. Build them with:

    python3 mining/cpu/build.py

This needs gcc (or cc) and, for the base C library, the
OpenSSL development headers (it links -lcrypto). It
builds libbal_batch.so (OpenSSL C), libbal_v512dual.so,
libbal_v512.so, libbal_v512flags.so, libbal_avx2.so, and
libbal_shani.so, smoke-tests each one it builds, and
exits non-zero only if the base C library fails. A tier
whose build fails, whose library is missing, or whose
CPU probe reports the kernel cannot run on this CPU is
simply skipped at runtime.

At startup each worker's ComputeEngine (gpu/engine.py,
requested="auto") dispatches in this order: CUDA,
v512dual, v512, SHA-NI, AVX2, C, and finally the pure
Python hashlib backend, reported as backend "cpu". With
no native libraries at all, the worker still mines on
the hashlib backend, at a small fraction of the native
rate. Nothing about enrollment changes: the fallback is
a rate difference, never a correctness difference (every
native tier must reproduce hashlib digests exactly in
its self-tests before it is selected). Each worker logs
a backend_selected event in its log file
(.local/fleet/worker-<id>.jsonl) naming the backend it
actually got, so the operator can see which tier the
machine is on.

## 6. Step 4: endpoint and payout

The gateway resolves its pool endpoint through
mining/endpoint_config.py, the same loader the direct
miner uses. Precedence: the gateway's --pool-host and
--pool-port (the launcher forwards its own --pool-host
and --pool-port when given), then the BAL_POOL_HOST and
BAL_POOL_PORT environment variables, then the file
.local/mining-endpoint.json, then the built-in default.

The built-in default, which applies when the file is
absent, is exactly the production endpoint:

- mode "pool"
- host public-pool.io, port 21496
- payout address bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3
  (the gateway's --address default, LAB_PAYOUT_ADDRESS
  in mining/endpoint_config.py)

A fresh machine therefore needs NOTHING in .local for
the endpoint and payout to resolve identically to
production. In particular, do not copy another machine's
.local/mining-endpoint.json: that file is machine-local
state (on this VM it also carries the solo cutover
configuration), and a copied file whose mode is later
flipped on the other machine would silently change what
a local copy does if it were ever shared back. Leave the
file absent.

Payout accrues to the lab wallet through the machine's
own pool session: every verified share the gateway
submits is authorized under the lab address above, so
pool-side credit accumulates to
bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3 regardless of
which machine found the share. The machine itself holds
no keys and no payout configuration beyond that address
default.

## 7. Step 5: run the bundle

### Option A: the launcher directly, under any supervisor

    cd /path/to/Bitcoin-Autonomous-Lab
    python3 mining/fleet_local.py --worker <machine-worker-name> --worker-ids <machine>-0,<machine>-1

With no further arguments the launcher uses the
production configuration: gateway duration 86400 s,
coordinator 127.0.0.1:4033, state dir .local/fleet,
gateway evidence .local/fleet/fleet-gateway.jsonl,
fleet id file .local/fleet/fleet_id.txt, declaration
parameters nonce-count 4294967296, chunk-size 16777216,
n-slots 32, worker lease TTL 300 s. It mirrors the
gateway evidence into evidence/mainnet-live.jsonl (the
production evidence log the lab's autopilot liveness
contract reads; harmless without an autopilot). On
SIGTERM or SIGINT it stops the whole bundle and exits
0; when the gateway exits (including at the end of its
86400 s duration) the launcher stops the workers and
exits with the gateway's status. Run it under a
supervisor that restarts it on exit (systemd
Restart=always, or the lab autopilot below) so the
machine mines continuously.

### Option B: under the lab autopilot, with systemd (the proven route)

This is the arrangement proven on this VM (plan section
L). The autopilot supervises one miner command; the
fleet bundle becomes that command through one
environment line.

1. Install the unit:

       bash scripts/autopilot.sh install-service
       systemctl start bal-autopilot

   install-service writes scripts/bal-autopilot.service
   to /etc/systemd/system/bal-autopilot.service,
   substituting the machine's repo path for REPLACE_REPO,
   reloads systemd, and enables the unit.

2. EDIT (forced by the code): the template's
   BAL_AP_MINER_CMD line contains this VM's absolute
   launcher path literally:

       Environment=BAL_AP_MINER_CMD="[\"/usr/bin/python3\",\"/home/hatch/workspace/bitcoin-autonomous-lab/mining/fleet_local.py\"]"

   install-service substitutes only REPLACE_REPO and
   REPLACE_DIST; it does not touch this line. If the
   repo on the enrolling machine lives anywhere other
   than /home/hatch/workspace/bitcoin-autonomous-lab,
   edit the installed unit
   (/etc/systemd/system/bal-autopilot.service) so the
   path is the machine's own mining/fleet_local.py.
   The machine's installed unit will differ from the
   repo template in this line; that difference is
   expected and is per-machine configuration, not a
   code change.

3. EDIT (the per-machine settings): as installed, the
   line passes no launcher arguments, so the launcher
   defaults would apply: worker name htch-runtime and
   worker ids local-0,local-1, both wrong for a new
   machine. Extend the JSON array in the same line with
   the machine's own settings from sections 4 and 5.
   Example for a four-core machine named atlas whose
   repo is at /home/atlas/Bitcoin-Autonomous-Lab:

       Environment=BAL_AP_MINER_CMD="[\"/usr/bin/python3\",\"/home/atlas/Bitcoin-Autonomous-Lab/mining/fleet_local.py\",\"--worker\",\"atlas-fleetgw\",\"--worker-ids\",\"atlas-0,atlas-1,atlas-2,atlas-3\"]"

   Keep the quoting exactly as shown: the value is
   wrapped in double quotes and every inner quote is
   backslash-escaped. systemd's Environment parsing
   consumes unescaped inner quotes as grouping, and
   the autopilot would receive a string that is not
   valid JSON and fail to start the miner (proven and
   recorded in plan section L.3).

4. Apply and start:

       systemctl daemon-reload
       systemctl restart bal-autopilot

### Standing warning: the miner command is the whole switch

The autopilot runs the fleet bundle only because
BAL_AP_MINER_CMD names the launcher. If that environment
is absent, the autopilot's default miner command is
mining/mainnet_live.py (mining/autopilot.py reads
BAL_AP_MINER_CMD and falls back to the direct miner).
So any supervisor change that restarts the autopilot
without the fleet line, reinstalling the unit from a
template that lacks the line, or starting the autopilot
detached by hand, silently reverts the machine to plain
mainnet_live mining: still mining, still to the same
wallet, but with no coordinator, no chunk accounting,
and no fleet evidence. This is not hypothetical: on
this VM a VM replacement wiped the unit, the keeper
cron restarted the autopilot detached, and the machine
mined via mainnet_live until the service was
reinstalled (plan section L and the restore recorded
with it). After any supervisor change, confirm the
autopilot's miner child is fleet_local.py, not
mainnet_live.py:

    ps -eo args | grep -E "fleet_local|mainnet_live" | grep -v grep

## 8. Verification checklist

Run these on the enrolling machine after the bundle has
been up for a few minutes. All paths are inside the
repo.

1. Coordinator listener, loopback only:

       ss -tlnp | grep 4033

   Exactly one listener, 127.0.0.1:4033, owned by the
   gateway's python3 process. A listener on 0.0.0.0 or
   on any external address fails enrollment: stop and
   fix the bind before continuing. (If the coordinator
   fails to bind, the gateway writes a
   coordinator_bind_failed event and exits with code 4;
   it never logs coordinator_listening in that case.)

2. Gateway authorized under the machine's own name:

       grep '"authorized"' .local/fleet/fleet-gateway.jsonl | tail -1

   The user field reads
   bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3.<machine-worker-name>.
   Earlier lines should show endpoint_selected naming
   public-pool.io port 21496 and coordinator_listening.

3. Jobs being declared:

       grep -c '"job_declared"' .local/fleet/fleet-gateway.jsonl

   A growing count. The pool sends a new job roughly
   every half minute, and the gateway declares each one
   at production width on arrival.

4. Workers registered, backends known, chunks exact:
   for each worker id,

       grep -E '"registered"|"backend_selected"' .local/fleet/worker-<id>.jsonl
       grep '"chunk_completed"' .local/fleet/worker-<id>.jsonl | tail -3

   Each worker log shows registered and backend_selected
   (threads 1). Every chunk_completed line reports
   attempts exactly equal to hi minus lo (16777216 at
   the production chunk size). A chunk whose attempts
   differ from its span, or a scan_anomaly event, fails
   enrollment: stop and report it.

5. First pool-accepted share, from the gateway's own
   counters:

       grep '"status"' .local/fleet/fleet-gateway.jsonl | tail -1

   The gateway logs a status event about every 10 s
   with submitted, accepted, and rejected totals.
   Enrollment is verified when accepted is at least 1
   and rejected is 0; each accepted share also appears
   as a share_result event with accepted true, naming
   the worker id that found it. At the pool's difficulty
   floor of 1, a share is expected every few minutes at
   a native-backend rate, and far less often on the
   hashlib fallback; absence of a share in the first
   minutes is statistics, not failure, provided items 1
   to 4 pass and the totals keep moving.

6. Pool-side presence: the public-pool dashboard for
   the lab wallet,

       https://web.public-pool.io/#/app/bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3

   lists the machine's worker name with its accepted
   shares. (The dashboard is not readable from every
   network; the gateway counters in item 5 are the
   authoritative local evidence.)

Report the outcome of items 1 to 5, with the worker
name and the backend each worker selected, to the lab
operator. That report is the enrollment record: there
is no other registry.

## 9. Leaving the fleet

Stop the bundle and nothing else is required:

    systemctl stop bal-autopilot

or, for a directly supervised launcher, stop the
launcher (SIGTERM): it stops the workers and the
gateway and exits 0. There is nothing to deregister on
any other machine, at the pool, or anywhere else; the
machine's worker name simply stops appearing. Shares
already accepted stay credited to the lab wallet. The
machine may delete .local/fleet/ (including
fleet_id.txt and the coordinator state) once stopped;
keep the evidence files if the operator wants the
machine's mining record.

## 10. Honest limits

- These instructions are a per-machine repetition of a
  run proven on exactly one machine: the loopback soak
  against the real pool (plan section K.6) and the
  production cutover of this VM (plan section L),
  with 2 workers on a host with roughly 2 effective
  CPUs. Enrollment by a real second machine is
  UNVERIFIED until one completes the section 8
  checklist end to end and reports it.
- Fleet width beyond 2 workers on one machine is
  unmeasured. The one-worker-per-core topology and
  the 32-slot bound are from the code and the
  coordinator's construction, not from a wide run.
- The gateway block-candidate path has never occurred:
  at difficulty 1, shares are the observed traffic, and
  no block candidate has ever been submitted through a
  gateway. The code path exists
  (block_candidate_submitted) and is unexercised.
- A coordinator restart in the middle of a run is
  unexercised. Replay-on-start after an unclean stop
  is exercised (the production start replayed 583
  journal operations); mid-run restart and resume is
  not.
- Backend rates differ by machine and by CPU; no rate
  is promised for any enrolling machine. The proven
  host measured about 11.4 MH/s combined from 2
  workers on the v512dual backend.
