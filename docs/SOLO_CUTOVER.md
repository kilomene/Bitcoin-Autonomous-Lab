# Solo cutover: from public-pool.io to our own solo server

Status: **staged and armed on 2026-11-14. Not fired.** The node
was at block 412,094 of 975,822 headers, still in initial block
download, when this was written. The switch fires itself when
the sync completes; everything below the audit section is the
machinery that makes that true, and the proof that the
machinery is inert until then.

Why: public-pool.io is a solo pool with a difficulty floor of
1 and a dashboard that lists a worker only while it has recent
credited work (docs/ROOTCAUSE_WORKERS_ZERO.md). At this VM's
rate a difficulty-1 share lands every few minutes at best, so
the worker blinks off the page between shares while hashing at
full rate. Our own solo server (mining/solo_server.py, proven
on regtest block 390 in 2026-11-13 and again at height 763 in
the 2026-11-14 test run) removes both causes: we choose the
share difficulty, and the server's own status tracks connected
workers continuously, share or no share.

## Audit of mining/solo_server.py for mainnet (2026-11-14)

The server was written and proven as a regtest stack. Read
against mainnet duty, seven findings, all fixed in this pass:

1. **No chain gate.** The server served work from whatever
   node its RPC pointed at. A mainnet server fed by a regtest
   node (or the reverse) would build wrong-network blocks
   while looking healthy. Fix: SoloServer takes an
   expected_chain; check_node() compares getblockchaininfo's
   chain on every job refresh and raises ChainMismatch on
   disagreement. The mainnet runner (mining/solo_mainnet.py)
   additionally refuses to start at all unless the node
   reports chain "main".
2. **No IBD gate.** refresh_job called getblocktemplate
   unconditionally; during initial block download it would
   have served templates for a long-dead tip, and every share
   ground on them would be wasted. Fix: check_node() raises
   SoloNotReady while initialblockdownload is true (or the
   node is unreachable), refresh_job refuses, the subscribe
   path refuses the session with a clear log line
   ("solo-server: subscribe refused: node in initial block
   download ..."), and the JobRefresher logs the state change
   once instead of spamming. The lab client reconnects on a
   dropped session, so workers return on their own when work
   is real.
3. **No job refresh.** Jobs were built at subscribe time and
   after a found block only. On mainnet the tip moves every
   ten minutes on average; workers would have mined a stale
   prevhash indefinitely. Fix: JobRefresher polls the node
   every 2 s and broadcasts a fresh job when the tip moves or
   the current job ages past 120 s (mempool and curtime
   freshness). GBT longpoll was considered; tip polling at
   2 s against a local node is simpler and the load is
   trivial.
4. **No per-worker tracking.** mining.authorize discarded the
   worker name; only global counters existed, so "is the
   worker alive and producing" had no server-side answer.
   Fix: authorize and submit both record the worker name;
   SoloServer.stats() reports per-worker accepted, rejected,
   block candidates, blocks, and last-share time, plus global
   counters and the current job. The runner writes it to
   .local/solo-status.json every 5 s.
5. **submitblock could kill the handler and lose a block.**
   An RPC exception propagated out of submit_share and ended
   the connection thread; the candidate record went with it.
   Fix: submission is wrapped; failures are captured into the
   block record (accepted false, reason string) and printed
   loudly, the share still counts, and the post-block job
   refresh still runs. submitblock's own contract (None on
   acceptance, a reason string on rejection) is handled as
   before.
6. **Unvalidated witness commitment slice.** The commitment
   was taken as default_witness_commitment[6:] on faith. The
   value Core 28.1 returns is the full commitment scriptPubKey
   (OP_RETURN, push 36, the aa21a9ed header, the 32-byte
   hash): 38 bytes with a known 6-byte prefix. Fix: the
   format is now validated and anything else raises. The
   re-attach path was also factored into attach_witness(),
   and a test proves it is the exact inverse of
   mining.engine.strip_witness for the coinbases this server
   builds, which is the property block assembly depends on.
7. **Protocol nits.** mining.suggest_difficulty (which the
   lab's own client sends) got a 501; it is now acknowledged.
   A dead `diff = 0.01` leftover shadowed the real difficulty
   source; set_difficulty now always serves
   SoloServer.share_difficulty, the single source of truth
   the share target is computed from. Submitted shares with
   an ntime before the template mintime or more than two
   hours in the future are now rejected at validation instead
   of being counted toward a block the network would refuse.

The mainnet node-config schema (rpc_user, rpc_password,
rpc_port, chain in .local/mainnet/node-config.json) differs
from the regtest schema node.rpc_client loads by itself;
mining/endpoint_config.load_mainnet_rpc maps it explicitly,
following mining/testnet4_attempt.py. Credentials are read
in-process only and never printed, here as everywhere.

## Share difficulty: 0.02, and why

Expected seconds per share at hashrate H is d * 2^32 / H.
The v512 backend's measured session rate on this VM is about
12.5M H/s. Difficulty 0.02 gives an expected share every
about 6.9 s; at half that rate, about 14 s. That is frequent
enough that the worker's activity is unmistakably continuous
(the property the pool setup cannot provide at its floor of
1, which is about 344 s at the same rate, with wide Poisson
gaps on top), and sparse enough that share validation and
bookkeeping are negligible load on server and miner. The
value is a config field (solo.share_difficulty in
.local/mining-endpoint.json), changeable without a code edit;
0.02 is the staged value. Block candidates are unaffected:
any share meeting the network target is assembled and
submitted regardless of the share difficulty.

## The mechanism

Three pieces, all in the repo, no code edit at fire time:

1. **Endpoint config** (mining/endpoint_config.py,
   .local/mining-endpoint.json): mode "pool" (the default,
   and the behaviour since 2026-11-13) or mode "solo"
   (127.0.0.1:3333, share difficulty 0.02, payout the lab
   address). mainnet_live.py resolves its Stratum endpoint
   from --pool-host/--pool-port, then BAL_POOL_HOST /
   BAL_POOL_PORT, then this file, then the pool default, and
   logs an endpoint_selected event. The autopilot needs no
   change: it restarts the miner child on any exit, and the
   child reads the config at start. Flipping the file plus
   restarting the child is the whole switch.
2. **The solo service** (mining/solo_mainnet.py,
   scripts/bal-solo.service, installed by
   `bash scripts/autopilot.sh install-solo-service`): a
   systemd unit in the bal-bitcoind.service pattern
   (Restart=always, enabled at install), so once started it
   survives failures and VM replacements like the other
   components. It is deliberately NOT installed or started
   during staging; the cutover script installs it at fire
   time. On a machine where systemd control fails, the
   script falls back to a nohup launch and records that,
   loudly, in the marker.
3. **The cutover script** (scripts/solo_cutover.py): check,
   fire, rollback, status. State lives in
   .local/solo-cutover.json (the marker): armed, firing,
   complete, or rolled_back, with a full history.

fire does, in order: verify preconditions (node out of IBD
with blocks within 2 of headers; miner healthy per the
autopilot heartbeat; endpoint still in pool mode); install
and start the solo service; wait until the server's own
status shows it serving a job whose prevhash is the node
tip; run a live Stratum smoke handshake requiring
set_difficulty equal to the configured 0.02 and a
mining.notify on the exact node tip; flip the endpoint mode
to "solo"; SIGTERM the miner child so the autopilot respawns
it onto the solo endpoint; then verify from primary sources:
a new miner pid in the heartbeat, a "connected" evidence
event naming 127.0.0.1:3333, and the server's per-worker
accounting showing at least 3 accepted shares from the
miner's worker with shares still arriving 45 s later. Any
failure before the flip aborts with the miner untouched.
Any failure after the flip rolls back automatically (below)
and records the reason.

## The watcher

Goal-owned cron **bal-solo-cutover**, every 15 minutes,
delivery to this goal's chat. Each run executes
`solo_cutover.py check` and stays silent on NOT_READY. On
READY it runs `solo_cutover.py fire` and acts on the
outcome: CUTOVER_COMPLETE or ROLLED_BACK are reported to the
owner, logged as tracking entries on the lab goal, and the
cron disables itself (the script's terminal marker states
independently make any later fire a no-op, so the once-only
property does not depend on the cron remembering to stop).
ABORTED_PRE_FLIP is reported once and retried next cycle.
Re-arming after a terminal state is a deliberate human act:
edit the marker, re-enable the cron.

## Rollback

Automatic: any post-flip verification failure flips the
endpoint mode back to "pool", restarts the miner child, and
verifies a "connected" evidence event naming
public-pool.io:21496 before marking rolled_back. Manual:
`python3 scripts/solo_cutover.py rollback` does the same on
demand, and hand-editing .local/mining-endpoint.json's mode
back to "pool" plus any miner restart restores today's
behaviour exactly, because pool mode is the pre-cutover
default path in every resolution rule. The solo service can
be stopped with `systemctl stop bal-solo`; leaving it
running is harmless (it only ever serves our own miner).

## Armed state, and the proof staging changed nothing

As staged on 2026-11-14: endpoint config present with mode
"pool"; marker absent (armed); bal-solo unit not installed;
`solo_cutover.py check` prints NOT_READY (node in initial
block download, 412,094 of 975,822 headers) and
`solo_cutover.py fire` exits 3 on the same line having
written nothing; the live miner (pid 3741 at staging time,
supervised as before) was never restarted, and its accepted
share count kept climbing through the staging work (79 to 82
during the audit window alone).

## Tests

- tests/test_solo_cutover.py (make test-solo-cutover, in
  test-all): IBD refusal, chain-mismatch refusal, node-down
  refusal, synced job construction with commitment
  validation, malformed commitment loudness, witness
  reassembly inverse, the node_ready rule (IBD false, gap at
  most 2), the cutover's own solo_smoke against a live server
  (accepts the right tip and difficulty, rejects wrong ones),
  subscribe refusal during IBD, and endpoint resolution
  (default, solo, env, CLI, corrupt file, set_mode
  round-trip).
- tests/test_solo_server.py (make test-solo): the regtest
  end-to-end in its current form: worker mines through the
  server at difficulty 0.01, the block is accepted by Core
  (height 763, hash
  0000001325090ccf3e4108a2d2a3ca7832f91607d1259c1e970ee0940ec4a2de
  in the 2026-11-14 run), and per-worker accounting is
  asserted for both the winning worker and a second worker
  whose malformed share is rejected under its own name.
- Full test-all after this pass: every target passes except
  the pre-existing test-rtl environment failure (iverilog not
  installed on this VM).
