# Bitcoin Mining Call Graph: Bitcoin Core v28.1

NOVA SHA-X Master Assignment, Phase A/B. Foundation for deliverable 3
(BITCOIN_MINING_CALL_GRAPH). Companion to CORE_SOURCE_AUDIT.md and
POW_DIFFICULTY_SOURCE.md. All line numbers are from the pinned v28.1 tree
(commit 32efe850438ef22e2de39e562af557872a402c31).

## 1. Mining RPC surface (src/rpc/mining.cpp)

Registered by RegisterMiningRPCCommands, src/rpc/mining.cpp:1109 to 1128.
Every RPC in this file, with its definition line and purpose:

### 1.1 Category "mining" (public)

| RPC | Defined at | Purpose (as declared in its RPCHelpMan) |
|---|---|---|
| getnetworkhashps | rpc/mining.cpp:108 | Returns the estimated network hashes per second, looked up over the last N blocks (default 120) |
| getmininginfo | rpc/mining.cpp:413 | Returns mining-related state: current block, difficulty, network hash rate, pooled transaction count, chain, and generation status fields |
| prioritisetransaction | rpc/mining.cpp:465 | Accepts a transaction id and a fee delta, prioritising it (or removing prioritisation) for this node's own template assembly |
| getprioritisedtransactions | rpc/mining.cpp:502 | Returns the prioritisation map created by prioritisetransaction |
| getblocktemplate | rpc/mining.cpp:569 | Returns block template data for mining: header fields, transaction list, coinbase value and aux data, target, bits, and (in proposal mode) validates a proposed block instead |
| submitblock | rpc/mining.cpp:998 | Attempts to submit a new serialized block to the network; returns BIP22 result strings |
| submitheader | rpc/mining.cpp:1070 | Submits a block header alone, for testing header acceptance paths |

### 1.2 Category "hidden" (regtest generation family)

| RPC | Defined at | Purpose |
|---|---|---|
| generatetoaddress | rpc/mining.cpp:260 | Mines blocks immediately to an address (regtest) |
| generatetodescriptor | rpc/mining.cpp:215 | Mines blocks immediately to an output descriptor (regtest) |
| generateblock | rpc/mining.cpp:301 | Mines one block immediately to an address or descriptor, optionally with a chosen transaction set and no mempool |
| generate | rpc/mining.cpp:253 | Legacy alias kept for compatibility; forwards to generatetoaddress behaviour |

The getblockchaininfo / getblock / getblockheader / getchaintips / getblockhash
family named in the Master Assignment lives in src/rpc/blockchain.cpp, not in
the mining file; they are read-only chain queries and are not part of the
template or submission path traced here.

## 2. getblocktemplate: request to template

```
getblocktemplate (src/rpc/mining.cpp:569)
|
|-- Parse template request: rules, capabilities, mode (rpc/mining.cpp:660-700)
|     |-- "proposal" mode: decode the proposed block and run TestBlockValidity
|     |     instead of returning a template
|     |-- longpoll: if a longpollid was supplied, wait on tip / mempool change
|           notifications before answering (rpc/mining.cpp:683, 751-790)
|
|-- Require the segwit rule (rpc/mining.cpp:795-798)
|     throws unless the client passed rules containing "segwit"
|
|-- Template cache check (rpc/mining.cpp:800-824)
|     static pindexPrev, static pblocktemplate (rpc/mining.cpp:801-803)
|     Rebuild ONLY if:
|       (a) there is no cached template, or
|       (b) the cached template's prev block hash differs from the current tip, or
|       (c) the mempool transaction counter changed AND more than 5 seconds
|           have passed since the cached template was built
|           (rpc/mining.cpp:804-805)
|     Otherwise the cached CBlockTemplate is reused as-is.
|
|-- interfaces::Mining::createNewBlock(scriptDummy) (rpc/mining.cpp:817)
|     scriptDummy is CScript() << OP_TRUE (rpc/mining.cpp:816); the real
|     payout script is the external miner's own coinbase output, not Core's.
|     |
|     +-- node implementation (src/node/interfaces.cpp:912-917)
|           builds BlockAssembler{ActiveChainstate, mempool, options}
|           with node args applied, then:
|           |
|           +-- BlockAssembler::CreateNewBlock (src/node/miner.cpp:109-188)
|                 [full trace in section 3]
|
|-- Refresh mutable header fields on the (possibly cached) template
|     UpdateTime(pblock, ...) (rpc/mining.cpp:829; src/node/miner.cpp:31)
|     pblock->nNonce = 0 (rpc/mining.cpp:830)
|
|-- Serialize the reply (rpc/mining.cpp:835-995)
      previousblockhash (line 941), bits (line 964, from pblock->nBits),
      target (line 946, arith target re-encoded and hexed),
      curtime (line 963), mintime (line 947, median time past + 1),
      height, transactions with data/fee/sigops per tx (lines 855-875),
      coinbaseaux (line 943: the "flags" hex the client must place in the
      coinbase scriptSig), coinbasevalue (line 944: subsidy + fees from the
      template coinbase output value), longpollid (line 945: tip hex +
      transaction-update counter), capabilities and mutable fields
      ("time", "transactions", "prevblock"),
      default_witness_commitment (lines 971-972, when the template carries
      a witness commitment), rules and versionbits deployment info.
```

Template invalidation triggers, stated exactly: a new chain tip, or a
mempool change that is at least 5 seconds newer than the cached template.
There is no per-request rebuild and no coinbase or extranonce mutation by
the server between rebuilds; between rebuilds only nTime is refreshed and
nNonce is reset to 0 on the shared cached block object.

## 3. BlockAssembler::CreateNewBlock (src/node/miner.cpp:109 to 188)

```
BlockAssembler::CreateNewBlock(scriptPubKeyIn)
|
|-- resetBlock() (miner.cpp:113; definition line 96)
|-- Create empty CBlockTemplate; reserve vtx[0] for the coinbase (miner.cpp:115-125)
|-- LOCK(cs_main); pindexPrev = chain tip; nHeight = tip height + 1 (miner.cpp:127-130)
|-- pblock->nVersion = versionbits ComputeBlockVersion (miner.cpp:132)
|     (regtest-only -blockversion override, miner.cpp:135-137)
|-- pblock->nTime = node clock now (miner.cpp:139); lock-time cutoff = median time past (line 140)
|-- If a mempool exists: addPackageTxs (miner.cpp:144-147; definition line 295)
|     ancestor-package selection by fee rate under block weight and sigops
|     limits; AddToBlock per selected tx (miner.cpp:226)
|-- Build the coinbase (miner.cpp:154-164)
|     vin[0].prevout = null; vout[0].scriptPubKey = scriptPubKeyIn
|     vout[0].nValue = nFees + GetBlockSubsidy(nHeight, consensus) (line 160)
|     vin[0].scriptSig = CScript() << nHeight << OP_0 (line 161)
|       [BIP34 height push, then an OP_0 placeholder. There is no
|        server-side extranonce field and no increment operation.]
|     vchCoinbaseCommitment = ChainstateManager::GenerateCoinbaseCommitment
|       (miner.cpp:163; src/validation.cpp:4076, see section 4)
|-- Fill the header (miner.cpp:168-173)
|     hashPrevBlock = tip hash (line 169)
|     UpdateTime (line 170; src/node/miner.cpp:31: raises nTime to at least
|       median time past + 1, never lowers below the passed-in time rules)
|     nBits = GetNextWorkRequired(pindexPrev, pblock, consensus) (line 171;
|       src/pow.cpp:13)
|     nNonce = 0 (line 172)
|-- If options.test_block_validity: TestBlockValidity with fCheckPOW=false
      and fCheckMerkleRoot=false (miner.cpp:176-179); failure throws, so a
      template that cannot connect is never handed out
```

## 4. Witness commitment (segwit coinbase commitment)

```
ChainstateManager::GenerateCoinbaseCommitment(block, pindexPrev)
  (src/validation.cpp:4076)
|
|-- GetWitnessCommitmentIndex(block) (validation.cpp:4079; the helper itself
|     is defined inline at src/consensus/validation.h:164)
|-- If no commitment output exists yet:
|     witnessroot = BlockWitnessMerkleRoot(block) (validation.cpp:4082;
|       src/consensus/merkle.cpp:75)
|     commitment hash = CHash256(witnessroot || 32 zero bytes) (validation.cpp:4083)
|     Append coinbase output: value 0, scriptPubKey =
|       OP_RETURN 0x24 0xaa21a9ed || commitment hash (validation.cpp:4084-4094)
|     (the 0xaa21a9ed prefix is the BIP141 witness commitment header)
|-- Returns the commitment script bytes; CreateNewBlock stores them in
      CBlockTemplate::vchCoinbaseCommitment, and getblocktemplate exposes
      them as "default_witness_commitment" for the external miner to place
      in its own coinbase (rpc/mining.cpp:971-972)
```

Key division of labour: Core computes what the commitment must be, but in
the getblocktemplate model the external miner builds the actual coinbase
transaction. If the miner changes the transaction set or the coinbase, the
commitment and the Merkle root change with it; Core re-derives and checks
both on submission.

## 5. Extranonce: the honest v28.1 picture

- There is no IncrementExtraNonce function anywhere in the v28.1 source
  tree (verified by a full search of src/). The historical helper from
  early Core versions is gone.
- The server-side coinbase scriptSig is exactly height plus OP_0
  (miner.cpp:161). The OP_0 and any bytes after the height push are space
  the coinbase owner controls.
- getblocktemplate therefore pushes all extranonce work to the client:
  the client receives coinbaseaux.flags (must be included in the
  scriptSig), coinbasevalue (the exact maximum coinbase output total), the
  transaction list, and default_witness_commitment. The client assembles
  the coinbase with its own extranonce in the scriptSig, rebuilds the
  Merkle root (whose leaves include the coinbase), and searches the nonce.
- The generate family (section 7) does not use an extranonce either: on
  nonce exhaustion it abandons the template and builds a fresh block,
  whose coinbase differs only because a new template was constructed.

For NOVA this confirms the design already in production: the extranonce
space is owned by the mining engine (in our case MiningEngine's
extranonce_space, EXP-034), never by Core, and Core's role is template
supply and authoritative validation.

## 6. submitblock: submission and validation entry path

```
submitblock (src/rpc/mining.cpp:998; handler body 1016-1066)
|
|-- DecodeHexBlk into a CBlock (rpc/mining.cpp:1020); failure is a
|     deserialization error, before any consensus code runs
|-- Require block.vtx non-empty and vtx[0] a coinbase (rpc/mining.cpp:1024-1026)
|-- Duplicate pre-check under cs_main (rpc/mining.cpp:1030-1041)
|     LookupBlockIndex(block.GetHash()):
|       already valid to BLOCK_VALID_SCRIPTS: return "duplicate"
|       already marked failed: return "duplicate-invalid"
|-- UpdateUncommittedBlockStructures (rpc/mining.cpp:1043-1049)
|     fills in uncommitted witness data for a block whose prev is known
|-- Register a submitblock_StateCatcher validation-interface listener so the
|     RPC can report the exact validation outcome (rpc/mining.cpp:1055-1058)
|-- interfaces::Mining::processNewBlock (rpc/mining.cpp:1057)
|     |
|     +-- ChainstateManager::ProcessNewBlock (src/validation.cpp:4545)
|           |
|           |-- CheckBlock (called at validation.cpp:4563; definition line 3999)
|           |     |-- CheckBlockHeader (line 3909)
|           |     |     CheckProofOfWork(GetHash(), nBits) (line 3912)
|           |     |       [integer target rule: POW_DIFFICULTY_SOURCE.md]
|           |     |-- CheckMerkleRoot (line 3918): BlockMerkleRoot recompute
|           |     |     and CVE-2012-2459 mutation check
|           |     |-- transaction-level checks (coinbase position, sizes,
|           |           duplicate txids, sigops budget)
|           |
|           |-- AcceptBlock (validation.cpp:4566) when CheckBlock passed
|                 |-- ContextualCheckBlockHeader (line 4159): the header's
|                 |     nBits must equal GetNextWorkRequired for its
|                 |     position, timestamp rules, version rules
|                 |-- block storage, index insertion
|                 |-- ConnectBlock / chain activation: full transaction,
|                       script and witness validation against the UTXO set;
|                       the block becomes the tip only if it connects and
|                       its chain has the most accumulated work
|
|-- Result mapping (rpc/mining.cpp:1059-1065)
      not new but accepted: "duplicate"
      validation interface never reported: "inconclusive"
      otherwise BIP22ValidationResult(state): null (success, block accepted
      and processed) or a BIP22 reject string such as "high-hash",
      "bad-txnmrklroot", "duplicate-invalid" and the other reject reasons
```

Acceptance semantics, precisely: submitblock returning null means the block
passed CheckBlock and AcceptBlock and was processed by ProcessNewBlock; it
does not by itself prove the block is in the active best chain (a competing
heavier chain can still leave it on a side branch). Chain confirmation is a
separate observation (getblock / getbestblockhash), which is exactly the
rule NOVA's EXP-036 submission path implements: submitblock's return value
is recorded verbatim and acceptance requires chain confirmation.

## 7. The internal generation path (regtest only)

```
generatetoaddress / generatetodescriptor / generateblock (rpc/mining.cpp:215-412)
|
|-- generateBlocks (rpc/mining.cpp:160)
|     loop per requested block:
|       blocktemplate = miner.createNewBlock(coinbase_script) (line 164)
|         [same BlockAssembler path as section 3]
|       GenerateBlock(chainman, miner, block, nMaxTries, ...) (line 169)
|
+-- GenerateBlock (rpc/mining.cpp:133-158)
      block.hashMerkleRoot = BlockMerkleRoot(block) (line 136)
      while tries remain and nNonce not exhausted and not interrupted:
          if CheckProofOfWork(block.GetHash(), block.nBits) passes, stop
          else ++block.nNonce (lines 138-141)
      on success: miner.processNewBlock (line 153), the same ProcessNewBlock
      path as submitblock
```

This is the only nonce-searching loop inside Core 28.1. It is
single-threaded, uses the generic CSHA256 header hash for every candidate,
has no midstate reuse and no vectorisation, and exists to produce regtest
blocks on demand. It is not a production miner and is compiled into the same
binary only as an RPC utility.

## 8. Summary of the graph

- Template path: getblocktemplate, interfaces::Mining::createNewBlock,
  BlockAssembler::CreateNewBlock, with GenerateCoinbaseCommitment and
  GetNextWorkRequired as the two consensus-critical helpers, plus a
  tip-and-5-second-mempool cache in the RPC layer.
- Search path: entirely external in production. Core supplies fields and
  targets; the external miner owns coinbase assembly, extranonce, Merkle
  root maintenance, and the nonce search.
- Submission path: submitblock, ProcessNewBlock, CheckBlock
  (CheckBlockHeader and CheckProofOfWork, CheckMerkleRoot), AcceptBlock,
  ConnectBlock. BIP22 strings are the contract, and best-chain membership
  is a separate confirmation step.
