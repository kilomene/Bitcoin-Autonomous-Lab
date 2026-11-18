# Stage 9.5 Independent Audit: Autonomous Regtest Discovery

Auditor: independent (did not build Stage 9.5). Subject:
research/STAGE9/REGTEST_AUTONOMOUS_DISCOVERY_REPORT.md and
research/STAGE9/evidence_95/ (36 files). Baseline: remote
HEAD de6bd0891ea620a1ff6c7560c840cefdd12e1dc0 (9.5 work not
yet pushed). All recomputation below was done by the
auditor from the raw evidence files, not by re-running the
builder's verifier.

## Verdict: PASS

No defects. One note (N-1) that confirms, rather than
contradicts, the report's own disclosure.

Live stack guard: heartbeat before the audit
(2026-11-18T06:54:13Z): autopilot_pid 2830, miner_pid 2833,
miner_state running, shares_accepted_total 1074. Heartbeat
after (2026-11-18T06:55:30Z): same pids, miner_state
running, shares_accepted_total 1074, uptime continuous.
The audit read files only and did not disturb the live
mainnet stack.

## Item 1: The 8 blocks. VERIFIED

For each height 1 to 8 the auditor recomputed the block
hash from header_N_hex.txt with hashlib double SHA-256
(display order). Every recomputed hash matches block_N.json
and the report's block table exactly, and every header's
nonce field matches both block_N.json and the report table
(40961, 0, 8192, 2, 65536, 2, 0, 4). Each block's raw hex
begins with the same 80 header bytes as its header file,
each header's previous-hash field links to the prior
block's hash, and every hash integer is at or below the
regtest target. Best-chain membership:
getblockchaininfo_after.json shows chain regtest, blocks 8,
bestblockhash equal to the height-8 hash; block_N.json
confirmations run 8 down to 1 in height order;
getblockchaininfo_initial.json shows height 0 before the
runs. Coinbase: the auditor parsed each raw block hex
directly (header, transaction count, coinbase inputs and
outputs). In all 8 blocks there is exactly 1 transaction,
and the coinbase's first output is exactly 5,000,000,000
satoshis (50.0 BTC regtest subsidy) with scriptPubKey
0014<program>, where <program> is the witness program
obtained by bech32-decoding the run's own payout address
(bcrt1q0ywmz83ql3wrw9d4jxtwcfsfv883p9aj4gksd0 for heights
1 to 5, bcrt1qegscm550uachakw88cf8zch3kqsk5m9wlnv795 for
heights 6 to 8). The two runs' programs differ, as they
should for two fresh addresses.

## Item 2: Agent-driven, not script-driven. VERIFIED

run_stage95.py was read in full. It sets the checkpoint
module constant, creates the isolated wallet and address,
constructs AutonomousMiner with an isolated BlockStore and
a default ComputeEngine, sets two engine attributes for the
publisher opt-in, calls agent.run_cycles(5) once, and
writes the record. It contains no template handling, no
search and no submission logic. The publisher launcher
imports run_stage95 and reuses its shim, differing only in
cycle count (3) and publisher interval (0.02 s), as
disclosed. agent/autonomous.py run_cycles performs the
chain guard, the benchmark and backend selection, and one
MiningEngine.mine_cycle per cycle, recording decisions and
adapting batch size. mining/engine.py _mine_cycle (line
885) fetches the template, searches with
search_first_counted (line 982), submits with submitblock
(line 1010) through the agent's RPC client, and counts
acceptance only when submit returns None and
get_best_block_hash equals the candidate hash. The RPC
traces in both run records show exactly this sequence per
cycle (getblocktemplate, submitblock, getbestblockhash),
preceded by the guard's getblockchaininfo and, in cycle 1
of each run, the one-time template-family calls
validateaddress and getblockchaininfo. There are exactly 5
and 3 submitblock calls, all with result None, and no
other submission path anywhere in the evidence: the
launcher's plain client made wallet calls only, and
verify_stage95.py issues reads only (getblockhash,
getblock). Backend selection: both run records and both
backend-selected decisions record backend v512dual chosen
by the production gpu/engine.py ComputeEngine dispatch
(requested auto), with fallback_reason "CUDA runtime error
35 (no usable NVIDIA device/driver)" and agent-measured
benchmarks of 939,412 H/s (run 1) and 695,305 H/s (run 2).

## Item 3: The shim. VERIFIED, with note N-1

VerifyingRPC (run_stage95.py line 85, call override line
93) was read in full. It does exactly two things: traces
every RPC call with a timestamp (plus template height,
bits and previous hash on getblocktemplate, and the result
on submitblock), and on submitblock it runs the production
mining.candidate_verify.verify_candidate over the
candidate's first 80 bytes under
pow_limit_for_chain("regtest") before forwarding, recording
the verdict and raising instead of forwarding when the
candidate does not meet the network target. It contains no
searching, no template manipulation and no nonce influence;
non-submitblock calls pass straight through. All 8 verdicts
in submit_responses.json (5 run1, 3 run2_publisher) are
classification block_candidate, reason ok, digests_agree
true, meets_network_target true, submit_result None. The
auditor confirmed each verdict's header_hex is byte-equal
to the corresponding header_N_hex.txt, that each verdict's
target equals the independently computed regtest target,
and that each value is at or below that target.

N-1 (note, not a defect): the shim's refusal condition
keys on meets_network_target alone, exactly as the report
discloses ("raises instead of forwarding if the candidate
does not meet the network target"). A hypothetical
candidate that met the target while its digests disagreed
would be forwarded. The case never arose (all 8 verdicts
had digests_agree true), and the code matches the
disclosure word for word, so this is recorded only so the
shim's exact contract stays on record.

## Item 4: Publisher finding. VERIFIED; conclusion FAIR

status_events.json: run 1 has 0 events; run 2 has 6 events,
each carrying the full production field set (event, hashes,
rate, submitted, statistics, statistics_errors 0), with the
submitted counter progressing 0, 0, 1, 1, 1, 2, bracketing
run 2's real submissions. Run 1's recorded cycle durations
are 0.1371, 0.1274, 0.0872, 0.0138 and 0.0832 s (range
0.014 to 0.137 s), all below the 0.25 s interval. The
mechanism is confirmed in production code:
StatusPublisher.run (mining/engine.py line 492) waits one
full interval before its first publication, so a cycle
shorter than one interval can never publish. The report's
conclusion, that the 10 s production cadence can never
publish at regtest cycle lengths and the publisher is a
long-cycle instrument, is a fair reading of the code and
the evidence, and the report itself scopes it correctly as
a property of cycle length rather than a publisher defect.
Not overstated.

## Item 5: Disclosure arithmetic. VERIFIED

Auditor's own computation: nBits 0x207fffff decodes to
target = 0x7fffff x 2^232 =
57896037716911750921221705069588091649609539881711309849342236841432341020672
(identical to the target recorded in the shim verdicts).
Target over 2^256 is 0.49999994, so p is about 0.5 per hash
and the expected hashes per block are 2.0000002, about 2,
as disclosed. Mainnet: 134,823,837,323,272 x 2^32 =
579,063,972,024,677,419,712,512, about 5.79e23 expected
hashes, as disclosed; divided by the run 1 benchmark of
939,412 H/s this gives about 1.95e10 years, matching the
report's "roughly 2e10 years". Text check: the report
calls the run regtest throughout, states "Nothing in this
report is mainnet, mainnet-equivalent, or earnings", and
its classification section answers "Autonomous mainnet
operation: NO, explicitly not", noting the chain guard and
that no allow_mainnet flag was passed (confirmed in the
launcher source and in agent/autonomous.py, where
allow_mainnet defaults to False and the guard raises on
chain main).

## Item 6: Attempts accounting. VERIFIED, no inconsistency

Engine-counted attempts per block from the cycle records:
32, 32, 64, 32, 32, 32, 32, 32 (heights 1 to 8). The
decision log's cycle-accepted entries carry the identical
hashes= values per height, and the engine statistics
totals agree (run 1: 192 backend hashes over 5 blocks, 5
submitted, 5 accepted, 0 rejected, 0 repeated work; run 2:
96 over 3 blocks). Batch counts are 1 per cycle. The
report discloses that the counted search is strided across
vector lanes, so the winning nonce is not bounded by the
counted attempts (height 1: nonce 40961 against 32 counted
attempts); the auditor confirmed that pairing in the
records. The batch-size adjustments in the decision log (3
per run; run 1: 65536 to 131072 to 262144 to 524288) match
the report narrative, and the report's per-block decision
timestamps match the decision log to the centisecond.

## Item 7: Isolation. VERIFIED

The run's datadir is .local/stage95/node; its bitcoin.conf
sets rpcport=18643 and port=18644. The shared endpoint
config .local/mining-endpoint.json hashes to
d741cde3c6224406f46f3bae138fb174eb1d780725bcb94baff4e14a8670c7d3,
the recorded untouched value. A filesystem scan found no
file under .local/regtest or .local/stage9 modified during
the run window (2026-11-18T06:50 to 06:51Z), all run state
(store, logs, checkpoint redirect) sits inside
.local/stage95, and no shared .local/work-checkpoint.json
was created (no checkpoint file exists in .local/stage95
either, consistent with the report's statement that the
EXP-038 checkpoint never engaged). U+2014 scan over
REGTEST_AUTONOMOUS_DISCOVERY_REPORT.md: zero occurrences.

## Summary

Every material claim in the Stage 9.5 report was
independently reproduced from the raw evidence or the
production source: the 8 blocks and their coinbases, the
agent-owned per-block sequence, the production backend
dispatch with its CUDA error 35 fallback, the disclosed
shim and its 8 block_candidate verdicts, the publisher
behaviour at both intervals, the disclosure arithmetic,
the attempts accounting, and the isolation of the run. The
report's autonomy classification (agent-controlled mining
loop inside an agent-assisted launch; autonomous regtest
discovery yes, scoped to the discovery loop; autonomous
mainnet operation explicitly no) is supported by the
evidence as written.

Verdict: PASS (one note, N-1; no defects).
