# Complete Bitcoin Protocol Map (as it bears on mining)

NOVA SHA-X Master Assignment, deliverable 1 (work package BR-001).

Scope: the Bitcoin protocol exactly where it touches mining: block and
header structure, transaction and coinbase rules, Merkle construction,
proof of work and retargeting, template supply, submission, validation,
chain selection, and block propagation. Modern rules are stated from the
pinned Bitcoin Core v28.1 source (commit
32efe850438ef22e2de39e562af557872a402c31; audit in
BITCOIN_CORE_SOURCE_AUDIT.md in this directory). Where Phase 001
established the original v0.1.3 form (verified tree at
.local/refs-genesis/extracted/sni_rar/), it is noted in a clearly
labelled historical paragraph. Historical behaviour is never stated as
modern consensus, and modern rules are never projected back onto 2009.

Conventions: "target" always means the exact 256-bit integer decoded
from nBits. No consensus statement in this document uses floating-point
difficulty; where an RPC displays a difficulty figure, it is a display
ratio only (research/bitcoin_core/POW_DIFFICULTY_SOURCE.md section 4).

## 1. The block and its header

A block is a header plus a transaction list (class CBlock, src/primitives/block.h:68).
The header is exactly 80 bytes, serialized by SERIALIZE_METHODS
(src/primitives/block.h:37) in this field order, which is the wire order:

| Offset | Size | Field | Type in CBlockHeader (src/primitives/block.h) |
|---|---|---|---|
| 0 | 4 | nVersion | int32_t, line 25 |
| 4 | 32 | hashPrevBlock | uint256, line 26 |
| 36 | 32 | hashMerkleRoot | uint256, line 27 |
| 68 | 4 | nTime | uint32_t, line 28 |
| 72 | 4 | nBits | uint32_t, line 29 |
| 76 | 4 | nNonce | uint32_t, line 30 |

Integers serialize little-endian; the two uint256 fields serialize in
their internal byte order. The block hash is SHA256d over these 80
bytes: CBlockHeader::GetHash (src/primitives/block.cpp:11) runs the
serialized header through HashWriter::GetHash (src/hash.h:115), whose
second pass makes it a double SHA-256. Block size is bounded by
MAX_BLOCK_SERIALIZED_SIZE and MAX_BLOCK_WEIGHT, both 4,000,000
(src/consensus/consensus.h:13 and 15).

Historical form (v0.1.3): the header layout is byte-identical in field
order and size (Phase 001, BLOCK_HEADER_SPECIFICATION.md; the miner's
scratch struct at src/main.cpp lines 2274 to 2290 is layout-identical to
the CBlock serialization at src/main.h line 828). The header format is
the most conservative object in the protocol: unchanged since 2009.

## 2. Transactions and the coinbase

A block's first transaction must be a coinbase (exactly one input, whose
prevout is null), and no later transaction may be one; this is checked
in CheckBlock (src/validation.cpp:3999). The coinbase pays out at most
the block subsidy plus the fees of the block's transactions: ConnectBlock
compares the coinbase output total against nFees + GetBlockSubsidy
(GetBlockSubsidy at src/validation.cpp:1919; the comparison at
validation.cpp:2689). The subsidy halves every nSubsidyHalvingInterval
blocks (210,000 on mainnet, 150 on regtest; src/kernel/chainparams.cpp,
tabulated in POW_DIFFICULTY_SOURCE.md section 4). Coinbase outputs are
immature for COINBASE_MATURITY = 100 blocks (src/consensus/consensus.h:19;
enforced for spends at src/validation.cpp:376).

Since BIP34, the coinbase scriptSig must begin with a push of the block
height; Core's own template coinbase is exactly
CScript() << nHeight << OP_0 (src/node/miner.cpp:161), and contextual
validation checks the height push (src/validation.cpp, BIP34 discussion
at lines 2507 to 2517). The coinbase scriptSig must be 2 to 100 bytes.
Any bytes after the height push belong to the miner: that space is
where the extranonce lives (section 5).

Historical form (v0.1.3): no height push existed. The miner's coinbase
scriptSig was exactly two pushes, the block's nBits and an incrementing
CBigNum extranonce (src/main.cpp lines 2209 to 2216; the first template
of a run uses extranonce 1). The output paid a raw 65-byte public key
with OP_CHECKSIG (P2PK), not an address script. The subsidy rule was
50 * COIN right-shifted by (nBestHeight / 210000), reading the global
best height rather than the new block's height (src/main.cpp line 675;
Phase 001, MINING_EXECUTION_FLOW.md section 3.5). The 2-to-100-byte
scriptSig rule already existed (src/main.h lines 456 to 459).

## 3. Merkle construction

Leaves are the txids of the block's transactions in block order
(BlockMerkleRoot, src/consensus/merkle.cpp:65, leaves at lines 68 to 72).
ComputeMerkleRoot (src/consensus/merkle.cpp:45) then folds pairwise:
when a level has an odd count, the last hash is duplicated (lines 52 to
54); each parent is the double SHA-256 of the 64-byte concatenation of
its two children, computed by SHA256D64 at line 56, the one production
use of Core's multi-way double-hash machinery. Validation recomputes the
root (CheckMerkleRoot, src/validation.cpp:3918) and additionally rejects
mutated trees: ComputeMerkleRoot reports when two identical hashes were
paired at a level where both were real leaves, the CVE-2012-2459 check
(merkle.cpp lines 47 to 51; rejection at validation.cpp:3934).

The witness tree is parallel: BlockWitnessMerkleRoot
(src/consensus/merkle.cpp:75) uses wtxids with the coinbase leaf forced
to zero (line 79), and its root feeds the coinbase witness commitment
(section 5).

Historical form (v0.1.3): the same pairing and odd-node duplication rule,
implemented as index clamping (i2 = min(i+1, nSize-1)) in
CBlock::BuildMerkleTree (src/main.h lines 868 to 885), with no mutation
defence: CheckBlock only compared the recomputed root (src/main.cpp
lines 1185 to 1187). Byte order was already internal-order end to end,
with reversal only at display (Phase 001, COINBASE_MERKLE_ANALYSIS.md
sections 2 and 3).

## 4. Proof of work and retargeting

The acceptance rule is a single integer comparison. nBits decodes via
arith_uint256::SetCompact (src/arith_uint256.cpp:175): the top byte is
the exponent, the low 23 bits are the mantissa, bit 0x00800000 is a sign
flag reported separately. CheckProofOfWork (src/pow.cpp:137 to 154)
rejects if the encoding is negative, zero, overflowing, or above the
chain's powLimit, and then accepts if and only if
UintToArith256(hash) <= target, equality included. SetCompact itself
never rejects; all rejection lives in CheckProofOfWork. Full evidence:
research/bitcoin_core/POW_DIFFICULTY_SOURCE.md sections 1 and 2.

Retargeting (GetNextWorkRequired, src/pow.cpp:13; CalculateNextWorkRequired,
src/pow.cpp:49): nBits changes only every
DifficultyAdjustmentInterval() = nPowTargetTimespan / nPowTargetSpacing
blocks (2016 on mainnet; src/consensus/params.h:123). The actual
timespan of the period is clamped to [timespan/4, timespan*4], the new
target is old target times clamped timespan divided by target timespan
in arith_uint256, capped at powLimit, and re-encoded with GetCompact
(src/arith_uint256.cpp:195). Chain-specific exceptions: min-difficulty
blocks on chains with fPowAllowMinDifficultyBlocks (pow.cpp:21 to 34),
the testnet4 BIP94 rule taking the period's first block as the retarget
base (pow.cpp:66 to 75), and fPowNoRetargeting on regtest, where the
pow limit compact is always returned. Per-chain parameters are
tabulated in POW_DIFFICULTY_SOURCE.md section 4.

Historical form (v0.1.3): one hardcoded mainnet rule inside
GetNextWorkRequired (src/main.cpp lines 685 to 732): interval 2016,
timespan 1,209,600 s, the same factor-of-4 clamp, BIGNUM
multiply-then-divide, cap at bnProofOfWorkLimit (2^224 - 1,
src/main.h line 22). The walk back is 2015 steps, so the measured span
covers 2015 intervals; that off-by-one is present in the original and
persists in the modern form. The sharp differences are in decoding, not
in the comparison: 0.1.3's CBigNum SetCompact (src/bignum.h lines 257 to
268) lets the sign bit become a true BIGNUM sign and getuint256
(src/bignum.h lines 218 to 231) silently drops it and truncates overflow,
where v28.1 masks the mantissa, reports negative and overflow flags, and
rejects in CheckProofOfWork. For every historically valid encoding both
decode identically (Phase 001, POW_TARGET_MATHEMATICS.md sections 5 and
6). The word "difficulty" appears nowhere in the 0.1.3 tree.

## 5. Template supply: getblocktemplate

Core does not mine in production. It supplies templates and validates
results; the miner owns the search. The path is:
getblocktemplate RPC (src/rpc/mining.cpp:569) to
interfaces::Mining::createNewBlock (src/node/interfaces.cpp:912) to
BlockAssembler::CreateNewBlock (src/node/miner.cpp:109 to 188), which
selects transactions by ancestor-package fee rate (addPackageTxs,
miner.cpp:295), builds the coinbase (section 2), fills the header
fields including nBits from GetNextWorkRequired (miner.cpp:171), and
computes the witness commitment through
ChainstateManager::GenerateCoinbaseCommitment (src/validation.cpp:4076):
if the coinbase has no commitment output yet, it appends one paying 0
with scriptPubKey OP_RETURN 0x24 0xaa21a9ed followed by
CHash256(witness root concatenated with 32 zero bytes)
(validation.cpp:4082 to 4094), and exposes the script as the template's
default_witness_commitment (rpc/mining.cpp:971 to 972).

The reply carries previousblockhash, bits, target (the arith target
re-encoded and hexed, rpc/mining.cpp:946), curtime, mintime (median
time past plus 1), height, the transaction list with fee and sigops per
transaction, coinbaseaux.flags (bytes the client must include in the
coinbase scriptSig), coinbasevalue (subsidy plus fees, the exact
maximum coinbase output total), longpollid, and the mutable fields
"time", "transactions", "prevblock". The segwit rule is mandatory
(rpc/mining.cpp:795 to 798).

Two protocol facts miners must design around:

- Template caching: the RPC layer caches one template (static
  pindexPrev and pblocktemplate, rpc/mining.cpp:801 to 803) and rebuilds
  only when the tip changes or the mempool changed and the cached
  template is more than 5 seconds old (rpc/mining.cpp:804 to 805).
  Between rebuilds only nTime is refreshed and nNonce reset to 0
  (rpc/mining.cpp:829 to 830). Fresh work is therefore not a per-request
  guarantee; see NODE_AND_SUBMISSION_ARCHITECTURE.md section 2.
- Extranonce ownership: there is no IncrementExtraNonce anywhere in
  v28.1. The server coinbase's OP_0 after the height push is placeholder
  space; the client places its own extranonce there (plus coinbaseaux
  flags), rebuilds the coinbase, the Merkle root and, when a witness
  commitment is required, the commitment, and searches. Full treatment:
  MINING_TEMPLATE_AND_COINBASE_SPECIFICATION.md.

Longpoll: a request carrying a longpollid waits on tip and mempool
change notifications before answering (rpc/mining.cpp:683 and 751 to
790), so a miner can block on fresh work instead of polling.

Historical form (v0.1.3): none of this existed. There was no RPC and no
template interface; the miner inside the node process built the
coinbase itself, swept its own mempool in transaction-hash order (not
fee order), computed the Merkle root once, and searched (Phase 001,
MINING_EXECUTION_FLOW.md sections 3 and 6).

## 6. Submission

A finished block returns through submitblock (src/rpc/mining.cpp:998):
hex decode, coinbase presence check, duplicate pre-check, then
ChainstateManager::ProcessNewBlock (src/validation.cpp:4545). The RPC
answers with BIP22 result strings: null on success, or a reject string
such as "high-hash", "bad-txnmrklroot", "duplicate",
"duplicate-invalid", "inconclusive". The contract's fine print matters:
null means the block was processed, not that it is in the active best
chain (BITCOIN_MINING_CALL_GRAPH.md section 6;
NODE_AND_SUBMISSION_ARCHITECTURE.md section 3).

Historical form (v0.1.3): submission was an in-process call. On success
the miner saved its coinbase key and called ProcessBlock(NULL, block)
(src/main.cpp line 2334), the same function that handled network-received
blocks, and a block that failed validation was dropped with only a
printf (Phase 001, MINING_EXECUTION_FLOW.md section 7).

## 7. Validation and chain selection

Validation is layered, and each layer is a separate function a miner can
reason about:

1. CheckBlockHeader (src/validation.cpp:3909): CheckProofOfWork on the
   header hash and claimed nBits (validation.cpp:3912).
2. CheckBlock (src/validation.cpp:3999): header check, CheckMerkleRoot
   with the mutation check (validation.cpp:3918), coinbase position,
   size and weight limits, duplicate txids, sigops budget.
3. ContextualCheckBlockHeader (src/validation.cpp:4159), run from
   AcceptBlock: the header's nBits must equal GetNextWorkRequired for
   its exact position, plus timestamp rules (not more than 2 hours in
   the future; after median time past) and version rules.
4. ConnectBlock, run during ActivateBestChain (src/validation.cpp:3439):
   full transaction, script and witness validation against the UTXO
   set, coinbase value ceiling (validation.cpp:2689), maturity rules.

Chain selection is by accumulated work, never by height or arrival
order: each block index entry carries nChainWork, the sum of
GetBlockProof over its chain, and ActivateBestChain connects the branch
whose tip has strictly more work than the current tip (work comparison
at validation.cpp:3607; the has-more-or-same-work gate at
validation.cpp:4465). A valid block on a lighter branch is stored, not
adopted. This is why submission success and best-chain membership are
different observations (section 6).

Historical form (v0.1.3): the same conceptual gates inlined: CheckBlock
(src/main.cpp line 1154) held the PoW checks at lines 1180 to 1184
(decoded target must not exceed bnProofOfWorkLimit; GetHash() must not
exceed the target) and the Merkle comparison at lines 1185 to 1187;
AcceptBlock (line 1192) required nBits to equal GetNextWorkRequired
exactly (line 1210). There was no separate CheckProofOfWork function
and no contextual header function; the equality gate in AcceptBlock is
what confined the Bignum decoding edge cases on a real chain in both
eras (Phase 001, POW_TARGET_MATHEMATICS.md section 3).

## 8. Block propagation

A block that becomes the best tip is announced to peers by the node that
accepted it; miners learn of competing blocks the same way. In v28.1 the
announcement machinery is in src/net_processing.cpp: peers choose per
connection between inventory (inv), headers-first announcement, and
compact blocks. Compact block relay (BIP152) uses CMPCTBLOCK messages
at version 2 (net_processing.cpp:180, CMPCTBLOCKS_VERSION), with
getdata upgraded to MSG_CMPCT_BLOCK for peers that provide them
(net_processing.cpp:2995) and missing transactions filled through
SendBlockTransactions (net_processing.cpp:2704). Headers announcements
send CBlockHeader objects directly (net_processing.cpp:4518 to 4540).
For a miner the operational consequence is template staleness: a new
tip invalidates work in progress, and the tip-change rebuild trigger in
section 5 plus longpoll exist precisely to bound that window.

Historical form (v0.1.3): propagation was a single mechanism. Inside
AcceptBlock, if the accepted block became the best chain, the node
called RelayInventory(CInv(MSG_BLOCK, hash)) (src/main.cpp line 1222;
CInv at src/net.h line 766), advertising the inventory to all peers,
which then requested the full block. No headers-first mode, no compact
blocks, and peer discovery itself ran over IRC (Phase 001,
ARCHITECTURE_MAP.md).

## 9. The mining-relevant protocol in one view

- Fixed: the 80-byte header, the SHA256d block hash, the Merkle pairing
  rule, the integer target comparison, the 2016-block retarget with its
  factor-of-4 clamp, the subsidy schedule, 100-block coinbase maturity.
  All of these are recognizably the 2009 rules, tightened at the edges
  (BIP34 height push, witness commitment, mutation check) but never
  replaced.
- Moved: everything about work management. In 0.1.3 the miner was the
  node; in v28.1 the node supplies cached templates over RPC, owns no
  extranonce, runs no production search, and judges submissions through
  a layered validation pipeline whose final word is accumulated work.
- Absent in both eras: any midstate or reusable-header-state facility in
  the node's own hashing code, and any specialised header-hash path.
  Core verifies headers with the same generic single-stream CSHA256 a
  wallet uses (BITCOIN_CORE_SOURCE_AUDIT.md section 3). Every mining
  optimisation in NOVA SHA-X is therefore engine-side by necessity, not
  by choice.
