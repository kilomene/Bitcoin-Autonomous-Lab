# Mining Template and Coinbase Specification

NOVA SHA-X Master Assignment, deliverable for work package BR-006.

This document specifies, exactly, how a mining template and its coinbase
are constructed: what Bitcoin Core v28.1 builds server-side, what it
hands to the client, what the client must assemble itself, how NOVA's
production MiningEngine corresponds step by step (EXP-034 verified),
and, in a labelled final section, how the v0.1.3 original did the same
job inside the miner. Modern rules are from the pinned v28.1 tree
(commit 32efe850438ef22e2de39e562af557872a402c31). NOVA facts are from
research/bitcoin_reverse_engineering/NOVA_REPOSITORY_AUDIT.md sections 4
and 6 and research/sha256d/exp034/JOB_TEMPLATE_ENGINE.md, both verified
against production source.

## 1. Server-side construction: BlockAssembler::CreateNewBlock

Entry: interfaces::Mining::createNewBlock (src/node/interfaces.cpp:912)
constructs a BlockAssembler over the active chainstate and mempool and
calls CreateNewBlock (src/node/miner.cpp:109 to 188). For
getblocktemplate the scriptPubKeyIn argument is a dummy,
CScript() << OP_TRUE (src/rpc/mining.cpp:816); the real payout script is
the external miner's own coinbase output, never Core's. Steps, in order:

1. resetBlock (miner.cpp:113; definition line 96). Create an empty
   CBlockTemplate; reserve vtx[0] for the coinbase (miner.cpp:115 to 125).
2. Under LOCK(cs_main): pindexPrev is the chain tip and
   nHeight = tip height + 1 (miner.cpp:127 to 130).
3. nVersion from versionbits ComputeBlockVersion (miner.cpp:132), with
   a regtest-only -blockversion override (miner.cpp:135 to 137).
4. nTime set to the node clock; the lock-time cutoff is the median time
   past (miner.cpp:139 to 140).
5. Transaction selection, if a mempool exists: addPackageTxs
   (miner.cpp:144 to 147; definition line 295) performs ancestor-package
   selection by fee rate under block weight and sigops limits, calling
   AddToBlock (miner.cpp:226) per selected transaction. Fees accumulate
   into nFees.
6. Coinbase construction (miner.cpp:154 to 164), specified in section 2.
7. Witness commitment computation (miner.cpp:163), specified in
   section 3.
8. Header completion (miner.cpp:168 to 173): hashPrevBlock from the tip
   (line 169); UpdateTime (line 170; src/node/miner.cpp:31, raises nTime
   to at least median time past plus 1); nBits =
   GetNextWorkRequired(pindexPrev, pblock, consensus) (line 171;
   src/pow.cpp:13); nNonce = 0 (line 172).
9. If options.test_block_validity is set: TestBlockValidity with
   fCheckPOW = false and fCheckMerkleRoot = false (miner.cpp:176 to
   179). Failure throws, so a template that cannot connect is never
   handed out.

## 2. The server coinbase, byte by byte

Built at src/node/miner.cpp:154 to 164:

- vin[0].prevout is null (the coinbase marker).
- vout[0].scriptPubKey is the caller's scriptPubKeyIn (the OP_TRUE dummy
  on the GBT path).
- vout[0].nValue = nFees + GetBlockSubsidy(nHeight, consensus)
  (miner.cpp:160; GetBlockSubsidy at src/validation.cpp:1919).
- vin[0].scriptSig = CScript() << nHeight << OP_0 (miner.cpp:161).

That scriptSig is the whole server-side statement: a BIP34 height push,
then a single OP_0 byte as placeholder. There is no server-side
extranonce field and no increment operation anywhere in this revision
(full-tree search: no IncrementExtraNonce exists in v28.1). The OP_0
and any bytes after the height push are space the coinbase owner
controls. The coinbase scriptSig must total 2 to 100 bytes, which
bounds the client extranonce space inside the coinbase.

## 3. Witness commitment: generation and placement

ChainstateManager::GenerateCoinbaseCommitment (src/validation.cpp:4076),
called from CreateNewBlock at miner.cpp:163:

1. GetWitnessCommitmentIndex (validation.cpp:4079; helper defined at
   src/consensus/validation.h:164) checks whether the coinbase already
   carries a commitment output.
2. If none exists: witnessroot = BlockWitnessMerkleRoot(block)
   (validation.cpp:4082; src/consensus/merkle.cpp:75, wtxid tree with
   the coinbase leaf forced to zero, merkle.cpp:79). The commitment hash
   is CHash256(witnessroot concatenated with 32 zero bytes), the 32
   zero bytes being the coinbase's reserved witness value
   (validation.cpp:4083).
3. Append a coinbase output with value 0 and scriptPubKey =
   OP_RETURN, push of 0x24 (36) bytes, the 4-byte BIP141 header
   0xaa21a9ed, then the 32-byte commitment hash
   (validation.cpp:4084 to 4094).

CreateNewBlock stores the script in
CBlockTemplate::vchCoinbaseCommitment; getblocktemplate exposes it as
"default_witness_commitment" (src/rpc/mining.cpp:971 to 972) for the
external miner to place in its own coinbase. Division of labour, stated
exactly: Core computes what the commitment must be for the transaction
set it selected. If the client changes the transaction set or the
coinbase, the commitment and the Merkle root change with it, and the
client must recompute both; Core re-derives and checks both on
submission (CheckMerkleRoot, src/validation.cpp:3918, and the witness
checks in ConnectBlock).

## 4. What the client receives and must assemble

The getblocktemplate reply (serialization at src/rpc/mining.cpp:835 to
995) gives the client: previousblockhash (line 941), bits (line 964),
target (line 946, the decoded target re-encoded and hexed; informational,
the consensus value is the one decoded from bits), curtime (line 963),
mintime (line 947), height, the transaction list with data, fee and
sigops per transaction (lines 855 to 875), coinbaseaux (line 943, whose
flags hex the client must place in the coinbase scriptSig),
coinbasevalue (line 944, subsidy plus fees: the exact maximum total the
coinbase outputs may pay), longpollid (line 945), the mutable field
list ("time", "transactions", "prevblock"), and
default_witness_commitment when present (lines 971 to 972).

Client duties, in dependency order:

1. Build the coinbase: null prevout; scriptSig = height push,
   coinbaseaux flags, and the client's own extranonce bytes in the
   OP_0 placeholder space; outputs paying at most coinbasevalue in
   total, including the payout output and, when the template carries a
   witness commitment, an output carrying the commitment script.
2. Recompute the witness commitment if the transaction set or the
   coinbase differs from the template's (section 3 rule).
3. Compute txids, build the Merkle tree with the coinbase as leaf 0,
   and place the root in header bytes 36 to 67.
4. Fill the remaining header fields (version, previousblockhash, time
   within mintime and curtime rules, bits) and search the nonce; on
   nonce exhaustion, change the extranonce (which restarts this list at
   step 1, because the coinbase, the Merkle root and the first header
   chunk all change) or fetch a fresh template.

## 5. NOVA correspondence: MiningEngine (EXP-034 verified)

NOVA's production engine (mining/engine.py) implements section 4 as
follows. Sources: NOVA_REPOSITORY_AUDIT.md sections 4 and 6;
research/sha256d/exp034/JOB_TEMPLATE_ENGINE.md. All statements below
were verified against production source by those audits.

- Template acquisition: MiningEngine.get_template (engine.py line 529)
  calls getblocktemplate with rules ["segwit"], the mandatory rule of
  section 4. wait_template (line 532) implements the GBT longpoll but
  has no production caller; agent/autonomous.py calls get_template
  fresh each cycle.
- Coinbase construction (build_coinbase, engine.py line 117;
  build_candidate_uncached, lines 558 to 623): BIP34 height push, the
  "/BAL/" marker, the extranonce as a 4-byte little-endian integer
  appended after the marker, coinbaseaux flags appended when present,
  then the payout output plus, when any transaction has a witness, the
  BIP141 witness commitment output (aa21a9ed header over
  dsha256(witness root concatenated with the reserved value)). This is
  exactly the section 4 step 1 and 2 sequence.
- Validation before search: template transactions are re-parsed; txid
  (dsha256 of the stripped serialization) and wtxid (dsha256 of the
  full serialization) are recomputed and a txid mismatch rejects the
  template; coinbasevalue must equal subsidy plus fees or the template
  is rejected. Merkle root: the uncached path computes
  merkle_root([coinbase txid] plus txids) via mining/pow.py; the cached
  (EXP-025) path precomputes tree levels over [zero || txids] and folds
  the coinbase txid in per extranonce step (root_with_coinbase,
  engine.py line 373). Byte identity between the paths is gated by
  tests/test_template_cache.py and the EXP-034 audit's independent
  recomputation.
- Template cache identity (EXP-023 fingerprint question, EXP-025
  repair): identity = dsha256(tx_key || coinbase_key || header_key),
  computed only after the full validation pass, covering payout,
  scriptPubKey, chain, halving interval, ordered (txid, wtxid, fee)
  triples, the default_witness_commitment string, height,
  coinbasevalue, coinbaseaux flags, the witness commitment and its
  presence byte, version, previousblockhash as written, bits, and the
  target as text. mintime and curtime are deliberately not keyed; the
  header time is read live per build (max(mintime + 1, min(now,
  curtime))). Full field-by-field record: NOVA_REPOSITORY_AUDIT.md
  section 4, verdict VERIFIED AS DOCUMENTED.
- Search space: mine_cycle (engine.py lines 640 to 789) steps
  extranonce rounds; extranonce_space (constructor, lines 463 to 510)
  is an opt-in (first, count) window inside the 32-bit extranonce
  range, default (0, 64), the historical behaviour. Two engines with
  the same payout, template and default space build byte-identical
  candidates (EXP-034 test C1); disjoint windows are the caller's
  responsibility and no production coordinator assigns them yet
  (EXP-035 is a research prototype). Neither version rolling (BIP320)
  nor timestamp rolling exists on any NOVA path: the header version is
  the template's, and time is the template-bounded computation above.
  Recorded as a genuine gap, not a defect.

### 5.1 The segwit split-offset defect (EXP-034): history and fix

The solo server path (mining/solo_server.py) serves Stratum workers a
split coinbase: coinb1, the 8-byte extranonce slot, extranonce2, coinb2.
EXP-034 found a real defect in SoloServer.refresh_job: the extranonce
split offset was located in the FULL coinbase returned by
build_coinbase and then applied to the STRIPPED coinbase:

```
at = coinbase.index(marker) + len(b"/BAL/")
stripped, has_witness = strip_witness(coinbase)
coinb1 = stripped[:at]
coinb2 = stripped[at + 8:]
```

When the coinbase carries a witness commitment, the full form has the
2-byte segwit marker and flag ahead of the input, so the offset landed
2 bytes late in the stripped form: coinb1 retained the last 2
placeholder bytes, and the final 2 bytes of extranonce2 fell outside
the scriptSig and overwrote the first 2 bytes of the coinbase sequence
field. Worker and server stayed mutually consistent (both concatenate
the same coinb1 and coinb2) and the height push and commitment output
survive the shift, so a block found this way would very likely still
have been accepted by Core; the damage was to the extranonce model (2
of 8 slot bytes frozen, 2 relocated into the sequence field) and to any
external worker reasoning about the coinbase. The pre-existing solo
tests never exercised it because they mine an empty mempool, whose
templates carry no witness commitment and whose full and stripped forms
coincide. The solo server was not live when the defect was found (the
cutover is armed; the mainnet node was still syncing), so no live work
was ever served this way.

Fix, in production at mining/solo_server.py lines 262 to 270: the
marker is located in the stripped bytes
(at = stripped.index(marker) plus the marker length), with a comment
recording why. For witnessless coinbases the behaviour is byte-identical
to before; for witness coinbases the split is now exact. Coverage:
EXP-034 test C3 asserts the assembled scriptSig byte for byte, test B1
asserts worker and server header agreement on a segwit template, test
B2 mines a block through the fixed path, and the test-solo and
test-exp036 suites stay green (JOB_TEMPLATE_ENGINE.md section 3). The
NOVA audit re-confirmed the fix in source and added one nuance: the
served scriptSig carries "/BAL/" plus the 8-byte extranonce slot; no
"/BAL-solo/" tag exists in the served bytes, and a stored solo tag
parameter is unused. That is a documentation defect in SoloServer, not
a correctness defect (NOVA_REPOSITORY_AUDIT.md section 7).

## 6. Historical contrast: the v0.1.3 in-miner original (2009, not modern consensus)

Phase 001 established the original form from the verified tree
(MINING_EXECUTION_FLOW.md sections 3.3 to 3.5;
COINBASE_MERKLE_ANALYSIS.md section 1). Differences from sections 1
to 4, stated as history only:

- No server and client: the miner inside the node process built the
  coinbase itself (src/main.cpp lines 2209 to 2216). scriptSig was
  exactly two pushes: the block's nBits and the pre-incremented local
  extranonce CBigNum (line 2212), a variable local to BitcoinMiner
  (line 2190), never persisted, never shared, and not in the header.
- No height push (BIP34 did not exist), no witness commitment, no
  coinbaseaux, no template: transaction selection was a repeated sweep
  of the node's own mempool in transaction-hash order, admitting what
  passed ConnectInputs against a scratch test pool (lines 2222 to
  2265), the opposite ordering principle from addPackageTxs fee-rate
  packages.
- The coinbase value was set after collection to GetBlockValue(nFees)
  (line 2267), subsidy computed from the global best height (line 675),
  and the single output paid a fresh wallet key as a raw public key
  with OP_CHECKSIG; the key was persisted only when a block was found
  (line 2329).
- The Merkle root was computed exactly once per template by
  BuildMerkleTree (src/main.h line 868), which recomputed every leaf
  hash from serialization even though the mempool map was keyed by
  those same hashes; the keys were not reused (Phase 001,
  COINBASE_MERKLE_ANALYSIS.md section 5).
- Extranonce exhaustion worked the same way in structure as section 4
  step 4: nonce wrap broke the search loop, the outer loop rebuilt the
  whole template with the next extranonce, changing coinbase, Merkle
  root and header together (lines 2347 to 2348 and 2212). The modern
  client-side extranonce is this mechanism, moved across the RPC
  boundary; Core's OP_0 placeholder is the fossil of the space the
  0.1.3 miner filled with its own counter.
