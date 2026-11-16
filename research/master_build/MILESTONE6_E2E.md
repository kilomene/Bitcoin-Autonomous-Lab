# Milestone 6: Independent End-to-End Verification Demonstration

Master Build Mandate section 14 (Milestone 6) and section 15.
Executed 2026-11-16 (UTC timestamps in the audit excerpt below)
by the standalone script `research/master_build/m6_e2e_demo.py`.
No production code, agent package code, test, or Makefile was
modified. The script and this report are the only new files.

## Result in one line

Regtest block at height **1445**, hash
**027df87dbaf2d87100922ddb55d0d5bbd513fae8c1787152073afb56c823a34e**,
mined by the production engine in one cycle, accepted by the
node as its best block, and then independently verified
agent-side by the EXP-036 verifier: classification
`block_candidate`, reason `ok`, digests agree, exact integer
target test passed.

## The chain as executed (real module and function names)

1. Agent inspection (Level 1, read-only, audited):
   `agent.intelligence.Agent` facade constructed with default
   paths (audit log `.local/agent-audit.jsonl`).
   `Agent.status()` delegates to
   `agent.intelligence.interface.MiningInterface.inspect_status`,
   which reads the autopilot heartbeat and evidence census
   files. `MiningInterface.inspect_backends` probes
   `gpu.engine.ComputeEngine` dispatch (selected: v512dual).
2. Node: `node.node_manager.start()` (datadir `.local/regtest`,
   RPC port 18443), the same call the test harness makes.
   Wallet handling mirrors `tests/test_mining_engine.py`
   exactly: if `bal-regtest` is not in `listwallets`, try
   `loadwallet`, fall back to `createwallet`; payout address
   from `getnewaddress` (bech32) via
   `node.rpc_client.BitcoinRPC`.
3. Mining: `mining.engine.MiningEngine(rpc, payout)` at
   production defaults (template cache on at 128 entries,
   extranonce space (0, 64), batch size 65536).
   `MiningEngine.mine_cycle()` ran once: getblocktemplate,
   prepared-template candidate construction, v512dual search,
   hit at nonce 0 after 32 counted hashes, `submitblock`
   returned None, and the engine's own acceptance rule
   (submitblock None plus `getbestblockhash` equality) marked
   the cycle accepted. The block carries 2 transactions
   (coinbase plus one wallet transaction already in the
   mempool) and 2564 sats of fees.
4. Agent-side independent verification around the engine
   result: the script fetched the block back with
   `getblock` (verbosity 0) at the node's best hash, took the
   first 80 bytes as the header, cross-checked them against
   `getblockheader` (non-verbose hex), and ran
   `mining.candidate_verify.verify_candidate(header,
   mining.candidate_verify.pow_limit_for_chain("regtest"))`.
   The same header was also routed through
   `MiningInterface.verify_candidate_op` so the agent audit
   trail carries the verification operation.
5. Best-chain confirmation: `getbestblockhash` equals the
   block hash, `getblockchaininfo` reports blocks = 1445 =
   the recorded height, and
   `mining.candidate_verify.verify_chain_acceptance` returned
   status `tip`, accepted True.

## verify_candidate verdict fields

- classification: `block_candidate`
- reason: `ok`
- digests_agree: true (hashlib `mining.pow.dsha256` and the
  pure-Python `mining.pow_engine.double_sha256_pure` produced
  byte-identical digests)
- valid_header: true
- meets_network_target: true (exact integer comparison,
  digest value <= target; no floating point anywhere in
  `mining/candidate_verify.py`)
- meets_share_target: false (no share target was passed;
  this is the network-target verdict only)
- nbits: 545259519 (0x207fffff, the regtest encoding)
- digest value (integer):
  1127196603039155355607445571629585088967852776218306386863390976069039530830
- target (integer):
  57896037716911750921221705069588091649609539881711309849342236841432341020672
- header hash from the verifier digest (display order):
  027df87dbaf2d87100922ddb55d0d5bbd513fae8c1787152073afb56c823a34e,
  identical to the node-reported block hash.

## Script output verbatim

One engine banner line preceded the JSON on stdout
(`full-workforce: AVX-512 DualMask search threads auto-tuned
to 1 on this machine (probe 7,095,924 H/s)`, printed by the
ComputeEngine probe). The JSON summary exactly as printed:

```json
{
  "chain": "regtest",
  "agent_status": {
    "running": true,
    "note": "live heartbeat",
    "miner_state": "running",
    "shares_accepted_total": 411,
    "evidence_accepted": 411,
    "evidence_rejected": 8
  },
  "agent_backends": {
    "dispatch_order": [
      "CUDA",
      "v512dual",
      "v512",
      "shani",
      "avx2",
      "C",
      "hashlib"
    ],
    "selected": "v512dual",
    "requested": "auto"
  },
  "tip_before": 1444,
  "engine_backend": "v512dual",
  "cycles_attempted": 1,
  "engine_result": {
    "accepted": true,
    "submit_result": null,
    "height": 1445,
    "hash": "027df87dbaf2d87100922ddb55d0d5bbd513fae8c1787152073afb56c823a34e",
    "nonce": 0,
    "hashes": 32,
    "batches": 1,
    "extranonce_rounds": 1,
    "backend": "v512dual",
    "seconds": 0.09362322099968878,
    "hashrate": 341.78750056398263,
    "tx_count": 2,
    "fees": 2564
  },
  "verify_candidate": {
    "classification": "block_candidate",
    "reason": "ok",
    "digests_agree": true,
    "valid_header": true,
    "meets_network_target": true,
    "meets_share_target": false,
    "nbits": 545259519,
    "value": "1127196603039155355607445571629585088967852776218306386863390976069039530830",
    "target": "57896037716911750921221705069588091649609539881711309849342236841432341020672",
    "digest_display_hex": "027df87dbaf2d87100922ddb55d0d5bbd513fae8c1787152073afb56c823a34e"
  },
  "agent_verify_candidate": {
    "classification": "block_candidate",
    "reason": "ok",
    "digests_agree": true,
    "valid_header": true,
    "meets_network_target": true
  },
  "confirmation": {
    "getbestblockhash": "027df87dbaf2d87100922ddb55d0d5bbd513fae8c1787152073afb56c823a34e",
    "block_hash": "027df87dbaf2d87100922ddb55d0d5bbd513fae8c1787152073afb56c823a34e",
    "header_hash_matches_block_hash": true,
    "best_equals_block": true,
    "getblockchaininfo_blocks": 1445,
    "recorded_height": 1445,
    "blocks_equals_height": true,
    "verify_chain_acceptance": "tip",
    "verify_chain_accepted": true
  },
  "demonstration_ok": true,
  "agent_audit": {
    "path": ".local/agent-audit.jsonl",
    "records_before": 13,
    "records_after": 16,
    "records_for_run": 3,
    "lines": [
      "{\"inputs\": {}, \"level\": 1, \"operation\": \"inspect_status\", \"outcome\": \"ok\", \"ts\": 1794789512.511175, \"ts_utc\": \"2026-11-16T00:38:32Z\", \"version\": 1}",
      "{\"inputs\": {}, \"level\": 1, \"operation\": \"inspect_backends\", \"outcome\": \"ok\", \"ts\": 1794789513.631473, \"ts_utc\": \"2026-11-16T00:38:33Z\", \"version\": 1}",
      "{\"inputs\": {\"chain\": \"regtest\"}, \"level\": 1, \"operation\": \"verify_candidate\", \"outcome\": \"block_candidate\", \"ts\": 1794789531.6022587, \"ts_utc\": \"2026-11-16T00:38:51Z\", \"version\": 1}"
    ]
  },
  "height": 1445,
  "block_hash": "027df87dbaf2d87100922ddb55d0d5bbd513fae8c1787152073afb56c823a34e",
  "wall_seconds": 19.166383981704712
}
```

Wall time 19.17 s, of which the large majority was regtest
node startup (the node was not running when the script
started; `node_manager.start()` launched it). The mining
cycle itself took 0.094 s.

## Agent audit trail excerpt for the run

The run appended 3 records to `.local/agent-audit.jsonl`
(records 13 before, 16 after), verbatim:

```
{"inputs": {}, "level": 1, "operation": "inspect_status", "outcome": "ok", "ts": 1794789512.511175, "ts_utc": "2026-11-16T00:38:32Z", "version": 1}
{"inputs": {}, "level": 1, "operation": "inspect_backends", "outcome": "ok", "ts": 1794789513.631473, "ts_utc": "2026-11-16T00:38:33Z", "version": 1}
{"inputs": {"chain": "regtest"}, "level": 1, "operation": "verify_candidate", "outcome": "block_candidate", "ts": 1794789531.6022587, "ts_utc": "2026-11-16T00:38:51Z", "version": 1}
```

## What this proves, and what it does not

Proves:

- The complete mandated chain executes with the new agent
  layer in the loop on regtest: agent inspection, production
  mining engine, candidate discovery, submission, node
  acceptance, and an independent post-acceptance verification
  of the accepted block's header, all in one run, with the
  agent operations recorded in the audit trail.
- The EXP-036 verifier agrees with Core's acceptance on a
  real engine-produced block: the header Core accepted as its
  tip passes the exact integer target test with two
  independent SHA-256d implementations in agreement.
- The Milestone 0 reconciliation flag is answered in
  practice: the GBT path's internal acceptance rule
  (submitblock plus best-chain equality) and the EXP-036
  verifier reach the same verdict on the same block, with
  the verifier applied from outside the engine.

Does not prove:

- A regtest block is not a mainnet block. Regtest difficulty
  is trivial (this block was found at nonce 0 after 32
  counted hashes). Nothing here is evidence about mainnet
  block discovery, and the project's success criterion (a
  valid mainnet block, independently verified and accepted)
  remains unmet.
- The pool path and its share accounting are a separate
  pipeline (mining/mainnet_live.py and
  mining/stratum_client.py against public-pool.io). This
  demonstration does not exercise it; the agent status figures
  in the output (411 accepted shares) are read from the live
  miner's own census files, not produced by this run.
- The agent-side verification wraps the engine rather than
  changing it: `mining/engine.py` still does not call
  `mining/candidate_verify.py` inside `mine_cycle`. Whether
  to move verification inside the GBT cycle is an owner
  decision item, stated as such; this demonstration supplies
  the evidence that the two verdicts agree, and changes no
  production behaviour.
- No performance claim: the cycle hashrate figure in the
  engine result is a 0.094 s regtest sample at trivial
  difficulty and is not a benchmark.

## Failures encountered

None in the demonstration itself: the first run exited 0
with `demonstration_ok: true`. The only stderr output was
two connection-refused lines from `node_manager`'s own
readiness polling while bitcoind was starting, which is the
harness's normal startup behaviour. The regtest node was
left running, as the test suites expect (they call
`node_manager.start()`, which reuses a running node).
