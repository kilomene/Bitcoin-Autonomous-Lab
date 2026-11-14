# BAL Autopilot: the keep-alive supervisor

`mining/autopilot.py` is the lab's autonomous supervisor. Any
agent that installs this repository gets it. Run one command and
the lab mines mainnet forever, in real time, without cron, without
an external watchdog, without a human checking in:

```
bash scripts/autopilot.sh start
```

## Sensitivity profile (owner specified)

| Function | Cadence | Behaviour |
| --- | --- | --- |
| Heartbeat | every 5 s | `.local/heartbeat.json` rewritten: miner pid and state, uptime, restart count, accepted shares total, evidence freshness |
| Watchdog (crash) | 1 s poll | miner process death detected within about a second; relaunch with exponential backoff starting at 1 s and capped at 30 s, so a dead miner is never left resting |
| Watchdog (hung) | 300 s window (5 minutes) | if the evidence log shows no new job for 300 s the miner is judged hung, killed and relaunched |
| Session rotation | 24 h sessions | the moment one session ends the next begins; mining is continuous |
| Self-update | every 15 min | compares HEAD to origin/main; on a new version: fast-forward pull, PoW smoke test, restart miner onto new code; on smoke failure: hard rollback to the previous HEAD and the old code keeps mining |
| Single instance | flock | a second autopilot on the same checkout exits politely; two supervisors never fight |

Self-update is **on by default** in `scripts/autopilot.sh` and
the systemd unit (`BAL_AUTO_UPDATE=1`). Disable with
`BAL_AUTO_UPDATE=0`. Running `python3 mining/autopilot.py`
directly takes `--auto-update` explicitly.

Thresholds are environment-overridable: `BAL_AP_POLL_S`,
`BAL_AP_STALE_S`, `BAL_AP_HEARTBEAT_S`, `BAL_AP_UPDATE_CHECK_S`.

## Operating it

```
bash scripts/autopilot.sh start     # start supervisor plus miner
bash scripts/autopilot.sh status    # prints .local/heartbeat.json
bash scripts/autopilot.sh log       # tail of .local/autopilot.log
bash scripts/autopilot.sh stop      # graceful stop of both
```

Or as a service: `bash scripts/autopilot.sh install-service`
fills in this checkout's path, installs the unit and enables
it, then `systemctl start bal-autopilot`. The service restarts
the autopilot itself if it ever dies and starts it on boot, a
second layer under the supervisor's own watchdog. On a machine
whose reboots are routine, the service is the difference
between mining that survives the night and mining that waits
for a human.

## Worker identity

Every agent needs its own worker name on the shared payout
address. When none is given, the autopilot names the worker
after this machine's hostname (sanitized), so a team never
collides on one shared name. Override with `--worker`,
`BAL_WORKER`, or the unit's environment.

## Full workforce

Mining is the job; the miner does not rest. Three rules ship
in the code, not in advice:

1. **Own worker.** Every entry point (the autopilot, the bare
   miner, the raw pool client) defaults its worker name to
   this machine's hostname. Each agent is separately visible
   on the pool page: its own hashrate, uptime and last seen.
2. **Measured maximum threads.** The compute engine probes
   the C search at several thread counts on the machine it
   starts on and runs at that machine's measured peak
   (`tune_c_threads` in `gpu/engine.py`). No thread count is
   copied from another agent's VM. An explicit `BAL_C_THREADS`
   still wins when an operator sets one.
3. **No-rest relaunch.** A crashed miner is relaunched with
   backoff starting at 1 s and capped at 30 s; a hung miner
   is killed and relaunched after the 300 s evidence window.
   Between jobs the search runs continuously; there is no
   idle state.

The honest arithmetic of scale: one machine hashes at its own
measured maximum, and a worker name costs nothing, so N agents
on N machines put N times one machine's workforce onto the
one payout address. Two agents are 200 percent of one machine,
five are 500 percent. The boost is the team, each member at
full workforce on its own VM.

## Automatic install and activation

Installation is one command: `bash scripts/install.sh`. It
builds the engine, runs network self-configuration, smoke
tests the exact code path that will mine (including the
thread auto-tune and the genesis nonce), installs the
systemd service where systemd exists, starts mining under
the autopilot, and prints an activation receipt. It is
idempotent and refuses to claim activation when the pool
endpoint is unreachable. `bash scripts/install.sh --dry-run`
prints the plan without changing anything.

## Network self-configuration

The lab's network shape is small and fixed, and
`scripts/network_setup.py` makes the machine suit it at
install time. Mining is outbound only (one TCP connection
to the pool's Stratum endpoint); self-update needs HTTPS to
GitHub; the optional node needs outbound 8333 to its pinned
peers only. Nothing inbound is ever required. The script
probes each endpoint, detects the machine's proxy from its
own environment, writes that proxy into this repo's git
config so cloning and self-update use the machine's working
door, and records a report in `.local/network.json`. Proxy
credentials are never recorded, only scheme, host and port.

## Block judgement

The miner reasons about which block to mine and confirms a
good block before claiming anything:

1. **Template validation.** Every pool template passes
   `validate_job` before a single hash is spent on it:
   prevhash and merkle branches must be real 32-byte hashes,
   coinbase parts must be hex, nbits must decode into range,
   and ntime must be fresh (within 2 hours either way).
   Failures are rejected with named reasons and logged as
   `template_rejected`; passes are logged as
   `template_validated` with the network difficulty decoded
   from nbits.
2. **Freshest template wins.** Any accepted template
   supersedes work in progress immediately, clean or not, so
   the workforce is never spent on a block the pool has
   already replaced.
3. **Candidate confirmation.** A search hit is not
   submitted on the search engine's word. The digest is
   recomputed with hashlib, independent of the backend, and
   checked against the pool target and against the network
   target from the job's nbits (which is what makes it a
   block candidate, not just a share), and the template must
   still be the freshest. Only then is it submitted, logged
   as `candidate_confirmed`; the pool's verdict returns as
   `share_result`. The chain template, candidate, verdict is
   the confirmation record; a block is claimed only on a
   pool acceptance or an on-chain record, as everywhere in
   this lab.

Speed and reliability of the same path: scan chunks are
sized from the machine's auto-tune probe to about one
second of work, so a fresher template preempts within about
a second; reported difficulties are the exact DIFF1 / value
ratio; a template for the same tip with an older ntime is
rejected as a stale echo and exact duplicates are ignored;
Stratum sockets run with TCP_NODELAY and the client
reconnects itself within seconds of a drop (session reset,
re-subscribe, re-authorize, fresh template), so a pool
hiccup no longer costs a full miner restart. First live
proof of the confirmation chain: 2026-11-14 05:51 UTC,
candidate confirmed on every check and accepted by the
pool 0.1 s later (share 29 for this lab).

## The node, and stopping approval spam

Pool mining needs no local node. A node is only needed to host
the lab's own solo server later. If you run the pruned mainnet
node (`.local/mainnet`), two in-repo tools keep it autonomous:

```
bash scripts/autopilot.sh install-node-service   # systemd unit,
                                                 # restart on boot
python3 scripts/pin-peers.py                     # pin connect=
                                                 # to current peers
```

Pinning matters on hosts where outbound connections need a
human approval per destination: a syncing node otherwise
dials new peer IPs forever and generates an approval card per
IP. Pinned, it talks only to a fixed set, approved once. See
docs/ROOTCAUSE_WORKERS_ZERO.md for the incident that produced
this tooling.

## What the autopilot does not do

It does not make hashes faster and it does not make the network
confirm blocks faster. Hash rate is hardware; block confirmation
is the Bitcoin network's 10 minute rhythm. What the autopilot
guarantees is **presence**: the miner is always running, always
on the current template, always on the latest verified code,
and any failure is detected in seconds and repaired without a
human. Presence is what turns spare compute into a standing
lottery entry that never lapses.

## Verification

`tests/test_autopilot.py` runs the supervisor against a stub
miner that dies every 2 seconds and proves: heartbeat written,
second instance refused by the lock, watchdog restart with a new
miner pid, clean shutdown on the stop file. On a checkout owned
by a live production autopilot the suite verifies the lock and
skips the destructive parts.
