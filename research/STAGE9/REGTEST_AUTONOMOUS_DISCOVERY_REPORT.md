# Stage 9.5: Isolated Autonomous Regtest Block Discovery

Stage: NOVA SHA-X Stage 9.5. Baseline: remote HEAD
de6bd0891ea620a1ff6c7560c840cefdd12e1dc0, on top of the
Stage 9.3 current-HEAD test audit (CURRENT_HEAD_TEST_AUDIT.md,
B2 candidate and block correctness, evidence_93) and the
Stage 9.4 gap analysis (AUTONOMOUS_AGENT_GAP_ANALYSIS.md).
Raw evidence: research/STAGE9/evidence_95/.

Result in one line: the lab's own agent stack
(agent/autonomous.py AutonomousMiner driving
mining/engine.py MiningEngine through the production
gpu/engine.py ComputeEngine dispatch), launched once per run
and then left alone, discovered and got accepted 8
consecutive blocks (heights 1 to 8) on a fresh isolated
regtest node, with no human or scripted per-block
intervention. Every block was independently re-verified
outside the agent's own accounting.

## Disclosure block (read first)

- This is REGTEST, a private toy chain on one isolated node.
  Nothing in this report is mainnet, mainnet-equivalent, or
  earnings. The 50 BTC per block coinbase figures are regtest
  subsidy on a chain with no other participants and no value.
- Regtest target: nBits 0x207fffff in every template and
  every block. The corresponding target integer is about
  2^255, so the probability that one SHA-256d hash meets the
  target is about 0.5, and the expected number of hashes per
  block is about 2.
- Mainnet contrast: at mainnet difficulty 134,823,837,323,272
  the expected number of hashes per block is difficulty times
  2^32, about 5.79e23. At the agent's own measured benchmark
  on this host (939,412 H/s, run 1), that is an expected wait
  of roughly 2e10 years per block. Regtest success at these
  settings demonstrates the correctness of the agent's loop,
  and nothing about mainnet feasibility.
- The agent's chain guard (agent/autonomous.py) refuses
  mainnet without an explicit allow_mainnet flag, which no
  launcher passed. This run is not, and does not rehearse,
  autonomous mainnet operation.

## Setup and hard limits

- Fresh isolated datadir .local/stage95/node, Bitcoin Core
  28.1, RPC 127.0.0.1:18643, P2P 18644. Both ports were
  verified free before use (18443 and 8332 were in use by the
  shared regtest and mainnet nodes and were not touched).
  Initial state: chain regtest, height 0 (genesis only),
  evidence getblockchaininfo_initial.json.
- Live mainnet stack untouched. Heartbeat before
  (2026-11-18T06:47:23Z): autopilot_pid 2830, miner_pid 2833,
  miner_state running, shares_accepted_total 1072. Heartbeat
  after (2026-11-18T06:51:36Z): same pids, miner uptime
  continuous (2629.1 s to 2882.4 s), shares_accepted_total
  1072. Shares non-decreasing; the same miner process ran
  throughout. .local/mining-endpoint.json, the wallet, the
  mainnet node, and the shared .local/regtest and
  .local/stage9 datadirs were not touched.
- The isolated node was stopped after evidence capture; its
  datadir remains at .local/stage95/node.
- Host: AMD EPYC 9D25, 4 vCPUs visible, no GPU (the
  ComputeEngine dispatch recorded the CUDA fallback reason
  "CUDA runtime error 35 (no usable NVIDIA device/driver)").

## Run narrative

Run 1 (launcher .local/stage95/run_stage95.py, source in
evidence): the launcher constructed the agent and called
agent.run_cycles(5) once. Inside that single call the agent:

1. Checked the chain through its guard (RPC trace:
   getblockchaininfo, chain regtest, passed).
2. Benchmarked through the production ComputeEngine dispatch
   and selected the backend itself: v512dual, measured
   939,412 H/s. Decision recorded: backend-selected.
3. For each of 5 cycles, the engine fetched a fresh
   getblocktemplate, prepared it through the EXP-025 template
   cache (cycle 1 also shows the one-time template-family
   calls validateaddress and getblockchaininfo in the RPC
   trace), searched with the production counted search
   (search_first_counted), and on each hit submitted with
   submitblock and confirmed acceptance by comparing
   getbestblockhash, all inside MiningEngine._mine_cycle
   (mining/engine.py line 885; submitblock at line 1010).
4. Recorded a cycle-accepted decision per block, and adapted
   its own batch size from measured batch times between
   cycles (65536 to 131072 to 262144 to 524288 over the run;
   decision kind batch-size-adjusted, 3 times).

All 5 cycles were accepted on the first batch each. Run 1
window: 2026-11-18T06:50:14.14Z to 06:50:17.80Z.

Run 2 (supplementary, launcher run_stage95_publisher.py):
identical construction and shim, 3 cycles, differing only in
the StatusPublisher interval (0.02 s instead of 0.25 s; see
the publisher section for why). Heights 6 to 8, all accepted
on the first batch each. Run 2 window:
2026-11-18T06:50:56.71Z to 06:50:58.10Z. Agent benchmark in
run 2: 695,305 H/s (same host, live miner contending; the
figure is the agent's own measurement, recorded as such).

No human or scripted action occurred between any template
fetch and its block's acceptance in either run. The RPC
traces (run_output.json, run_output_publisher.json) show the
complete call sequence per cycle: getblocktemplate,
submitblock, getbestblockhash, repeated by the agent's loop
alone.

Attempts accounting, stated precisely: the "attempts" column
below is the engine's counted hash total for the cycle, from
the production counted search (search_first_counted). That
search is strided across vector lanes, so the winning nonce
is not bounded by the attempt count (height 1: 32 counted
attempts, winning nonce 40961). The smallest counted unit
observed is 32. Totals: run 1, 192 counted attempts over 5
blocks; run 2, 96 over 3 blocks. Against the disclosed
expectation of about 2 hashes per block at p about 0.5,
these counts are the backend's lane-grouped accounting of
the same trivial search, not a discrepancy.

## Block table

All blocks: bits 207fffff, 1 transaction (coinbase only),
coinbase value 50.0 BTC (regtest subsidy). Decision time is
the agent's own cycle-accepted record (UTC); header time is
the block's nTime as reported by Core (UTC).

| Height | Hash | Nonce | Attempts (counted) | Batches | Header time | Agent decision time |
|---|---|---|---|---|---|---|
| 1 | 510b366a89bf00381e269be0867f99396279cf762081f0a61e511cfd939e7f7a | 40961 | 32 | 1 | 06:50:14 | 06:50:14.93 |
| 2 | 0e223faf4071e6e5c590ba0e8c3e17f0436b66e25b2039305ff479cc59e19f51 | 0 | 32 | 1 | 06:50:16 | 06:50:15.30 |
| 3 | 6b16624ef948d3d6faecb0c6304b44fd60094261063292e3d1097220a2c9346c | 8192 | 64 | 1 | 06:50:16 | 06:50:15.64 |
| 4 | 56bba31fd825660b35932f540e4788bb0a4e8f9429df8a2526ef4a805b5aa0e9 | 2 | 32 | 1 | 06:50:18 | 06:50:16.93 |
| 5 | 0f2df5db3536e0e54fdaaea37fa53abcdfe2e58ca89f7eba2f5cbebed7b2e6bc | 65536 | 32 | 1 | 06:50:18 | 06:50:17.50 |
| 6 | 7c1d6cb45f5f6af7302124bb5f2e8306c304a4e8cff3086899b2383bfb6face3 | 2 | 32 | 1 | 06:50:57 | 06:50:57.40 |
| 7 | 3f6c74996bf53217d7e3a87509d7d6efe02db10581b091b87e31e450debf7984 | 0 | 32 | 1 | 06:50:57 | 06:50:57.70 |
| 8 | 355befc49de42316047b51037ab536ea3451819eff2dc91976ef06b78b65754f | 4 | 32 | 1 | 06:50:57 | 06:50:57.90 |

Header times at heights 2 and 4 read a second or two after
the decision time because nTime is taken from the template's
curtime (the node's clock basis), not from the discovery
instant; the decision timestamps are the discovery record.

Payout addresses (both from the isolated node's own wallet
"stage95", created by the launchers on the isolated node):
run 1 (heights 1 to 5) bcrt1q0ywmz83ql3wrw9d4jxtwcfsfv883p9aj4gksd0;
run 2 (heights 6 to 8) bcrt1qegscm550uachakw88cf8zch3kqsk5m9wlnv795.

## Decision-log summary

Full record: evidence_95/decision_log.json (agent-recorded,
both runs), evidence_95/agent.log and agent_publisher.log
(full module logs), and the RPC traces inside the two run
records. Decision counts: backend-selected 2 (one per run),
cycle-accepted 8, batch-size-adjusted 6, cycle-failed 0,
mining_error 0. Refusals and fallbacks: the chain guard
passed (regtest); the ComputeEngine dispatch fell back from
CUDA to v512dual with the reason recorded in the
backend-selected decision; the shim refused nothing (no
candidate failed verification); the engine recorded no
checkpoint anomaly: every cycle hit on its first batch, so
no completed-batch frontier was ever recorded and no
checkpoint file was ever created; each cycle's result
honestly reports "no checkpoint file; starting fresh" under
the EXP-038 rules, and the launcher redirect guaranteed any
checkpoint state would have landed inside .local/stage95.
Engine statistics for run 1 (engine.statistics snapshot):
192 backend hashes, 5 candidates, 5 blocks submitted, 5
accepted, 0 rejected, 0 repeated work.

## Launcher and shim disclosure

Launchers (sources in evidence_95, originals in
.local/stage95): run_stage95.py and
run_stage95_publisher.py. A launcher does only this:
constructs the RPC client, the store, the compute engine
and the AutonomousMiner; applies the configuration items
below; calls run_cycles once; writes the run record. It
contains no template handling, no search and no submission
logic. Per-block sequencing is entirely the agent's and
engine's code.

Configuration applied by the launchers, each item disclosed:

1. Work checkpoint redirect (run_stage95.py line 68):
   agent.autonomous.WORK_CHECKPOINT_PATH is set to
   .local/stage95/work-checkpoint.json before the agent is
   constructed. The module default is the shared
   .local/work-checkpoint.json; the redirect keeps all run
   state inside the isolated directory. AutonomousMiner
   exposes no constructor parameter for this path.
2. Isolated store: BlockStore is constructed with
   .local/stage95/agent-store.db (its default is the shared
   .local/regtest/engine.db). The store IS a constructor
   parameter of AutonomousMiner; no code was patched.
3. Payout address: a wallet named stage95 was created on
   the isolated node by the launcher and a fresh bech32
   address taken from it per run.
4. StatusPublisher opt-in (run_stage95.py lines 147 to 148):
   agent.engine.status_publish set to True and
   agent.engine.status_interval_s set to 0.25 (run 1) or
   0.02 (run 2) after construction. AutonomousMiner's
   constructor does not expose the Stage 9.4 opt-in;
   MiningEngine.mine_cycle reads the flag at call time, so
   no agent or engine code was modified.

SHIM (one, disclosed precisely): VerifyingRPC,
run_stage95.py line 85 (call override at line 93), a
node.rpc_client.BitcoinRPC subclass used as the agent's RPC
client. It does two things: (a) traces every RPC call with a
timestamp (the source of the RPC traces in the run records,
including template height, bits and previous hash per
getblocktemplate, and the submitblock result per
submission); (b) on submitblock, before forwarding, it runs
the production EXP-036 verifier
(mining.candidate_verify.verify_candidate) over the
candidate's 80-byte header under the regtest pow limit
(pow_limit_for_chain("regtest")), records the verdict, and
raises instead of forwarding if the candidate does not meet
the network target. All 8 verdicts: classification
block_candidate, reason ok, digests agree, meets network
target true, nBits 0x207fffff (evidence:
submit_responses.json). No verdict refused.

Why the shim exists: the GBT agent path's own in-loop
verification is Core's submitblock result plus the
engine's best-chain comparison, by the engine's stated
design (the comment at the hit branch of _mine_cycle:
the GBT path's verification is Core's own submitblock and
best-chain verdict, so the EXP-036 classifications are not
recorded there). verify_candidate is wired on the pool path
(mining/mainnet_live.py), the solo server and the
aggregation tier only. The shim adds the lab's own verifier
at the submission boundary of this run without modifying
any agent or engine code; it does not change what the agent
decides, only refuses to forward a candidate that failed
verification (a case that did not occur).

## StatusPublisher evidence

The Stage 9.4 publisher (mining/engine.py StatusPublisher,
opt-in status_publish) was enabled on both runs, as above.

- Run 1 (interval 0.25 s): 0 events. Every cycle's recorded
  duration was 0.014 to 0.137 s, and the publisher's first
  publication happens one full interval after the cycle
  starts, so no cycle lived long enough to publish. The
  publisher thread was constructed and stopped per cycle by
  the production mine_cycle wrapper; it simply had nothing
  to report within a sub-interval cycle.
- Run 2 (interval 0.02 s): 6 events captured
  (evidence_95/status_events.json), carrying the full
  production status field set (event, hashes, rate,
  submitted, statistics totals, statistics_errors 0), with
  the submitted counter progressing 0, 0, 1, 1, 1, 2 across
  the run's cycles, bracketing real submissions exactly as
  the awareness layer requires.

Finding: at regtest cycle durations the production cadence
(10 s default) can never publish; the publisher is a
long-cycle instrument. That is a property of cycle length,
not a publisher defect: on any cycle lasting minutes (the
live-difficulty case the Stage 9.4 fix was built for) the
10 s cadence publishes throughout. Recorded here so the
Stage 9.4 B2 evidence is not over-read: B2's proof was in
its stub suite; this run is the first time the publisher
ran inside real agent cycles, and it published correctly
whenever a cycle outlived one interval.

## Independent verification (builder-side, not the agent)

Performed by .local/stage95/verify_stage95.py (source in
evidence) after both runs, over heights 1 to 8, using a
plain RPC client (no shim):

- Block hash recomputed from the raw block hex with
  hashlib SHA-256d over the 80-byte header: matches the
  node's hash and the agent's reported hash for all 8
  blocks.
- Height and best-chain membership from the node:
  getblockchaininfo tip 8; every block sits at its height in
  the best chain (confirmations 8 down to 1).
- Production acceptance checker
  (mining.candidate_verify.verify_chain_acceptance):
  heights 1 to 7 "in-chain" accepted, height 8 "tip"
  accepted.
- Coinbase: in every block the coinbase's first output pays
  exactly the payout address of the run that produced the
  block, at 50.0 BTC (the regtest subsidy; no fees, coinbase
  only transaction).
- Full record: evidence_95/verification.json; per-block raw
  hex, header hex and decoded blocks beside it.

## Gaps found, against the Stage 9.4 classifications

1. Verifier wiring on the agent path (finding, against the
   C1/C2 picture). The agent's mining loop does not invoke
   the lab's production candidate verifier in-loop; its
   verification is delegated to Core's submitblock and
   best-chain verdict, by engine design. The EXP-036
   verifier is wired on the pool, solo-server and
   aggregation paths only. This run needed the disclosed
   RPC-boundary shim to place the production verifier inside
   the agent's submission path. No 9.4 verdict changes: C1
   and C2 remain agent-assisted; but any future claim that
   the agent path verifies candidates with the lab's own
   verifier is false at this HEAD without such a shim or an
   engine change.
2. Publisher reachability (finding, against C1). The Stage
   9.4 StatusPublisher is reachable from MiningEngine but
   not from AutonomousMiner: the agent's constructor neither
   exposes nor enables it, so an agent run publishes status
   only if whoever launches it sets engine attributes after
   construction, as these launchers did. Combined with the
   cycle-length property above, agent-run status publication
   is currently a launcher act, not an agent capability.
3. Agent state paths (minor, against C1). AutonomousMiner's
   work checkpoint path is a module constant pointing at a
   shared .local file, not a constructor parameter; the
   store path is a parameter. Isolating an agent run's state
   therefore requires the launcher redirect in item 1 of
   the disclosure. No defect in behaviour; an interface gap.
4. What this run confirms of 9.4: the C1 description of
   run_cycles (benchmarks, selects a backend, runs
   MiningEngine cycles, adapts batch size from measured
   batch times, logs decisions; regtest-only by chain guard;
   launched by a human or a test; manages no processes) is
   accurate end to end against a real node. Nothing in this
   run gives the agent a lifecycle it did not have: it did
   not start, stop or health-check any component, and the
   node it mined against was started by the operator side.
   C2 is untouched by this run (no research-loop activity).
   C3 and C4 are untouched (no mode machine driver ran; no
   coordinator was involved; duplicate prevention here is
   the single-process construction 9.4 describes, and the
   EXP-038 checkpoint, redirected into the isolated
   directory, never engaged because every cycle hit on its
   first batch).

## Autonomy classification of THIS run

- Agent-assisted: YES, in part. A human-authored launcher
  created the node wallet, configured the agent (items 1 to
  4 above), chose the cycle counts (5 and 3), and started
  each run. The run was commissioned and bounded from
  outside the agent.
- Agent-controlled: YES, for the mining loop itself. Within
  each run, every operational decision was the agent's and
  engine's own code: chain check, backend selection from
  its own benchmark, per-cycle template acquisition,
  candidate construction, search, verification at the
  submission boundary (shim) and by Core's verdict,
  submission, best-chain acceptance confirmation, and batch
  adaptation. No per-block human or scripted intervention
  occurred.
- Autonomous regtest discovery: YES, this run is evidence
  for this class, scoped exactly as follows: the lab's
  agent stack, unattended inside a launched run, discovered
  blocks on an isolated regtest node and got them accepted
  into the best chain, 8 blocks in a row across two runs,
  at a target where discovery is expected within about 2
  hashes. The class claim covers the discovery loop only,
  not lifecycle, not research, not fleet operation.
- Autonomous mainnet operation: NO, explicitly not. The
  agent refuses mainnet by chain guard; no mainnet flag was
  passed; the live mainnet stack is a separate pool path
  under autopilot and keeper supervision and was not
  touched; and the disclosure block's arithmetic shows the
  discovery demonstrated here says nothing about mainnet
  feasibility.

## Evidence index (research/STAGE9/evidence_95/)

- run_output.json, run_output_publisher.json: full run
  records (cycles, decisions, engine statistics, status
  events, RPC traces, shim verifications).
- decision_log.json: the agent's recorded decisions, both
  runs, with UTC timestamps.
- agent.log, agent_publisher.log: full module logs.
- submit_responses.json: per-submission Core response (null,
  Core's acceptance) with the shim's production-verifier
  verdict per candidate.
- status_events.json: publisher output, both runs (run 1
  empty, as explained).
- block_N_hex.txt, header_N_hex.txt, block_N.json for
  N = 1 to 8: raw blocks, headers, decoded blocks.
- verification.json: the independent verification record.
- getblockchaininfo_initial.json,
  getblockchaininfo_after.json: node state before and after.
- run_stage95.py, run_stage95_publisher.py: the launchers,
  including the shim. verify_stage95.py: the builder-side
  verifier.
