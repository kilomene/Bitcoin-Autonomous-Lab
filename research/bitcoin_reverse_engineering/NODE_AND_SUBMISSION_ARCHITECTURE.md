# Node and Submission Architecture

NOVA SHA-X Master Assignment, deliverable for work package BR-012.

This document describes node architecture strictly as it affects a
miner: how templates are cached and invalidated, how longpoll works,
what submitblock's answer does and does not mean, the validation path a
submission travels, the client behaviour that follows from it (EXP-036's
chain-confirmation rule), Stratum as a separate protocol layer (NOVA's
solo server and pool client), and NOVA's current node integration state.
Modern Core behaviour is from the pinned v28.1 tree (commit
32efe850438ef22e2de39e562af557872a402c31). NOVA state is from
research/bitcoin_reverse_engineering/NOVA_REPOSITORY_AUDIT.md sections 6
to 8 and 15, verified against production source.

## 1. The node's shape, from the miner's side

A v28.1 node presents a miner with exactly three surfaces:

- Template supply: getblocktemplate (src/rpc/mining.cpp:569) backed by
  BlockAssembler behind interfaces::Mining (src/node/interfaces.cpp:912;
  src/node/miner.cpp:109 to 188). Full graph: BITCOIN_MINING_CALL_GRAPH.md
  sections 2 and 3.
- Submission: submitblock (src/rpc/mining.cpp:998) backed by
  ChainstateManager::ProcessNewBlock (src/validation.cpp:4545).
- Chain observation: the read-only queries in src/rpc/blockchain.cpp
  (getbestblockhash, getblock, getblockheader, getblockchaininfo), which
  are the only way to confirm what the first two surfaces did.

Everything else a miner might want (its own extranonce, its own search,
its own candidate queue) is the miner's own business; the node has no
hooks for it. Core itself runs no production search: the only
nonce loop in the tree is the regtest GenerateBlock utility
(src/rpc/mining.cpp:133), single-threaded over the generic CSHA256 path.

## 2. Template caching, invalidation, and longpoll

### 2.1 The cache

The cache lives in the getblocktemplate RPC handler, not in the
assembler: two function-local statics, pindexPrev and pblocktemplate
(src/rpc/mining.cpp:801 to 803). A request rebuilds the template only
if one of three conditions holds (rpc/mining.cpp:800 to 824, the
rebuild test at lines 804 to 805):

1. there is no cached template;
2. the cached template's previous-block hash differs from the current
   tip;
3. the mempool transaction counter changed AND more than 5 seconds
   have passed since the cached template was built.

Otherwise the cached CBlockTemplate is reused as-is. On every answer,
cached or rebuilt, the handler refreshes the mutable fields on the
shared block object: UpdateTime (rpc/mining.cpp:829; src/node/miner.cpp:31)
and pblock->nNonce = 0 (rpc/mining.cpp:830). There is no per-request
rebuild, and the server never mutates the coinbase or any extranonce
between rebuilds, because the server coinbase is a dummy-payout
template artifact (CScript() << OP_TRUE, rpc/mining.cpp:816) that the
client replaces wholesale.

Miner-side consequences, stated plainly:

- Two getblocktemplate calls seconds apart can return the same
  transaction set with only nTime advanced. A miner that treats each
  reply as guaranteed-fresh work will duplicate its own search across
  the extranonce boundary it controls; freshness is the miner's
  accounting problem (NOVA keys it on prevhash and job generation on
  the Stratum paths, and on per-cycle get_template calls on the GBT
  path; NOVA_REPOSITORY_AUDIT.md section 6).
- A mempool change younger than 5 seconds does not invalidate. The
  cost of a slightly stale fee set is bounded by design; the tip-change
  trigger, which is the consensus-critical one, has no such delay.

### 2.2 Longpoll

A getblocktemplate request may carry a longpollid (the tip hex plus
transaction-update counter from a previous reply, serialized at
rpc/mining.cpp:945). The handler parses it (rpc/mining.cpp:683) and,
before answering, waits on tip and mempool change notifications
(rpc/mining.cpp:751 to 790), so the reply arrives when the work
actually changes instead of when the client next polls. In proposal
mode the same RPC instead decodes a proposed block and runs
TestBlockValidity (rpc/mining.cpp:660 to 700); the segwit rule is
required in all modes (rpc/mining.cpp:795 to 798).

NOVA state: MiningEngine.wait_template (mining/engine.py line 532)
implements this longpoll with a timeout-extended RPC client, but it has
no production caller. agent/autonomous.py drives mine_cycle, which
calls get_template fresh each cycle; the Stratum paths key freshness
on prevhash and job generation instead (NOVA_REPOSITORY_AUDIT.md
section 6). Recorded as an architecture gap (audit section 15, item 4),
not a defect: the GBT path polls where the protocol offers a wait.

## 3. submitblock semantics and the chain-confirmation rule

### 3.1 What the RPC does

submitblock (src/rpc/mining.cpp:998; handler body lines 1016 to 1066):
DecodeHexBlk into a CBlock (line 1020; a failure is a deserialization
error before any consensus code runs); require vtx non-empty and vtx[0]
a coinbase (lines 1024 to 1026); duplicate pre-check under cs_main
(lines 1030 to 1041: already valid returns "duplicate", already failed
returns "duplicate-invalid"); UpdateUncommittedBlockStructures (lines
1043 to 1049); register a submitblock_StateCatcher validation-interface
listener (lines 1055 to 1058) so the RPC can report the exact
validation outcome; then interfaces::Mining::processNewBlock (line
1057).

### 3.2 The validation path

ChainstateManager::ProcessNewBlock (src/validation.cpp:4545) calls
CheckBlock (called at validation.cpp:4563; definition line 3999), which
runs CheckBlockHeader (line 3909; CheckProofOfWork at line 3912, the
exact integer rule of research/bitcoin_core/POW_DIFFICULTY_SOURCE.md),
CheckMerkleRoot (line 3918, recompute plus the CVE-2012-2459 mutation
check), and the transaction-level checks. On success, AcceptBlock
(validation.cpp:4566) runs ContextualCheckBlockHeader (line 4159: the
header's nBits must equal GetNextWorkRequired for its position, plus
timestamp and version rules), stores the block, inserts its index
entry, and chain activation connects it: ActivateBestChain
(src/validation.cpp:3439) makes it the tip only if it connects against
the UTXO set and its chain has the most accumulated work (nChainWork
comparison at validation.cpp:3607).

### 3.3 What the answer means

The result mapping (rpc/mining.cpp:1059 to 1065) returns: "duplicate"
for a not-new but accepted block; "inconclusive" when the validation
interface never reported; otherwise the BIP22 result: null on success,
or a reject string such as "high-hash" or "bad-txnmrklroot". The
precise semantics of null: the block passed CheckBlock and AcceptBlock
and was processed by ProcessNewBlock. Null is NOT proof the block is in
the active best chain. A competing heavier chain can leave a processed
block on a side branch, and only a chain observation
(getbestblockhash, getblock) settles membership.

### 3.4 The client rule (EXP-036)

The correct client behaviour follows directly: record the verbatim
submitblock return, classify it, and decide acceptance from chain
state, never from the return value alone. This is the rule whose
absence was the EXP-036 defect class (a solo path that treated a None
submitblock result as success) and whose implementation is now NOVA's
single verification stage, mining/candidate_verify.py
(NOVA_REPOSITORY_AUDIT.md section 7):

- verify_candidate recomputes SHA-256d twice (hashlib and an independent
  pure-Python implementation) and requires byte agreement; the target
  is decoded from the header's own nBits with Core SetCompact semantics,
  with negative, overflow, zero and above-limit targets rejected, and
  the comparison is exact integer value <= target. No float operation
  decides anything in the module; float difficulty appears only in
  display and statistics contexts elsewhere, never in a submission
  decision.
- classify_submit_result records the verbatim submitblock return
  alongside its class.
- verify_chain_acceptance decides acceptance from chain state (the tip,
  or in-chain with at least one confirmation) and returns "unknown",
  not accepted, when chain state cannot be read.

Per-path state, as audited: the solo path routes every share through
verify_candidate and records a network-target candidate as accepted
only when verify_chain_acceptance confirms tip or in-chain, storing
the verbatim result, its classification and the chain status on the
block record; the EXP-036 defect is closed in source, not merely in
the report. The GBT path (MiningEngine.mine_cycle) applies the same
standard inline (submitblock returns None AND the node's best block
hash equals the block hash) rather than calling
verify_chain_acceptance; the standard is equivalent, the code is not
shared, recorded as a consistency note. The pool path passes every
search hit through verify_candidate before any submission and takes
block candidacy from meets_network_target alone. Audit gap, recorded:
there is no candidate queue between search and submission on any path
(a found candidate is submitted synchronously), and no reorg re-check
follows an accepted block (NOVA_REPOSITORY_AUDIT.md section 15, item 6).

## 4. Stratum: a separate protocol layer

Stratum is not part of Bitcoin Core and not part of the consensus
protocol. It is a pool protocol that sits between a template source and
workers, and it re-implements, inside itself, the template, extranonce
and submission concerns that sections 2 and 3 assign to the GBT and RPC
surfaces. NOVA runs both ends of it:

- Solo server (mining/solo_server.py): the server side, fed by our own
  node. refresh_job (line 228) builds the coinbase with the engine's
  own builder using an 8-byte extranonce placeholder, serves the
  STRIPPED coinbase split as coinb1 and coinb2 around the extranonce
  slot (split located in the stripped bytes, lines 262 to 270; the
  EXP-034 segwit split-offset defect and its fix are specified in
  MINING_TEMPLATE_AND_COINBASE_SPECIFICATION.md section 5.1).
  submit_share (line 351) rebuilds the exact block from coinb1,
  extranonce1, extranonce2, coinb2 and the Merkle branch in
  validate_share (line 302), checks the share against the server
  difficulty, then routes the header through verify_candidate (line
  374); failures land in candidates_rejected and are never submitted.
  JobRefresher (line 451) polls the node every 2 seconds, rebuilds the
  job when the served prevhash no longer matches the node's best block
  hash or the job ages past 120 seconds, and refuses to serve while
  the node is in initial block download, on the wrong chain, or
  unreachable. Note the asymmetry with section 2.1: the solo server's
  freshness is prevhash and age driven, with no 5-second mempool rule,
  because it owns its template pipeline end to end.
- Pool client (mining/stratum_client.py, driven by
  mining/mainnet_live.py): the worker side against an external pool.
  build_header (line 118) assembles the 80-byte header with the wordswap
  prevhash mode the live runner uses. Incoming jobs pass validate_job
  plus duplicate and stale-echo guards (evidence events
  template_validated, template_rejected, template_duplicate, lines 255
  to 310) before they can supersede current work, and every accepted
  job bumps job_generation, which is what mainnet_live checks before
  submitting a share: a hit on a stale generation is never submitted.
  Block candidacy in the evidence log comes from meets_network_target
  in candidate_verify, so a pool share is never recorded as a block.

Stratum is V1 only in NOVA; Stratum V2 is absent (audit section 15,
item 6). The protocol-layer lesson the two ends teach together:
whichever layer supplies work, the authoritative judgement of a
candidate is always the exact integer check in candidate_verify plus
chain confirmation at our own node, never the pool's or the server's
own difficulty bookkeeping (refresh_job takes its job target from the
simple decoder in mining/pow.py for bookkeeping only; the
authoritative judgement of any share still goes through check_pow
inside verify_candidate).

## 5. NOVA node integration state

From NOVA_REPOSITORY_AUDIT.md section 8, verdict VERIFIED with one
recorded starting fact:

- Integration runs through node/rpc_client.py, a typed JSON-RPC wrapper
  with retries and explicit errors; credentials come from .local
  configs, never from source. MiningEngine and SoloServer consume
  getblocktemplate, submitblock, getbestblockhash, getblockheader,
  validateaddress and getblockchaininfo through that client.
  node/node_manager.py manages the regtest node lifecycle (and contains
  no wallet handling at all); node/peer_node.py runs the second peered
  regtest node used by the deepening tests.
- The mainnet node is our own pruned Core 28.1 (prune = 550), installed
  by scripts/setup-bitcoin-core.sh with SHA256SUMS verification, running
  from ~/workspace/bitcoin-core-dist with its datadir under
  .local/mainnet. At audit time it was still in initial block download
  and syncing toward the tip; the solo cutover (endpoint config
  .local/mining-endpoint.json, mode still "pool", guarded by
  scripts/solo_cutover.py and the bal-solo-cutover watcher) is staged
  and armed but has not fired, so live mining still runs against the
  external pool while the node syncs. The solo server's JobRefresher
  refusal to serve during initial block download (section 4) is the
  mechanism that keeps that ordering safe.
- The starting fact the audit recorded for Phase B has since been
  closed by this wave: at audit time no Core source checkout existed
  locally, so every Core-behaviour claim rested on the 28.1 binary's
  observed behaviour and differential tests. The pinned v28.1 source
  tree now exists (.local/refs-core/bitcoin-v28.1, commit
  32efe850438ef22e2de39e562af557872a402c31) and the source-level audits
  in research/bitcoin_core/ and this directory rest on it directly.
