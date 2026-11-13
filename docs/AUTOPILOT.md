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
| Watchdog (crash) | 2 s poll | miner process death detected within seconds; relaunch with capped exponential backoff |
| Watchdog (hung) | 180 s window (3 minutes) | if the evidence log shows no new job for 180 s the miner is judged hung, killed and relaunched |
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

Or as a service: `scripts/bal-autopilot.service` (edit
WorkingDirectory, `systemctl enable --now bal-autopilot`). The
service also restarts the autopilot itself if it ever dies, a
second layer under the supervisor's own watchdog.

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
