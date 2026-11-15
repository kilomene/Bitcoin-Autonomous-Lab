# Block Header Serialization Specification

NOVA SHA-X Master Assignment, work package BR-004 (header and
serialization). The 80-byte block header specified byte by byte:
field layout, per-field byte order, how the serialization is
constructed in the original v0.1.3 and in modern Core v28.1, the
genesis header as a fully annotated worked example, the mutation
table (which fields a miner may roll, and by what mechanism), and
how NOVA's production code corresponds.

Sources: research/phase001/BLOCK_HEADER_SPECIFICATION.md (v0.1.3,
verified tree, line citations); research/bitcoin_core/
CORE_SOURCE_AUDIT.md and MINING_CALL_GRAPH.md (v28.1, pinned
commit 32efe850438ef22e2de39e562af557872a402c31);
research/sha256d/SHA256D_MATHEMATICAL_SPECIFICATION.md section 6
(byte order at the hash boundaries); the Phase A NOVA audit
(research/bitcoin_reverse_engineering/NOVA_REPOSITORY_AUDIT.md)
for the NOVA correspondence. The layout is identical in both eras:
the modern differences are rules about the fields' values, not the
layout.

## 1. The 80 bytes

The header is six fields, serialized in declaration order, with no
length field, no checksum, and no padding: 4 + 32 + 32 + 4 + 4 + 4
= 80 bytes exactly.

| Offset | Size | Field | Type | Byte order in the serialization | Content |
|---|---|---|---|---|---|
| 0 | 4 | nVersion | signed 32-bit (v0.1.3 int; v28.1 int32_t) | little-endian | block version |
| 4 | 32 | hashPrevBlock | uint256 | internal order (the raw memory bytes; the byte reverse of the displayed hex) | hash of the previous block's header |
| 36 | 32 | hashMerkleRoot | uint256 | internal order, as above | merkle root of the block's transactions |
| 68 | 4 | nTime | unsigned 32-bit | little-endian | block timestamp, seconds since epoch |
| 72 | 4 | nBits | unsigned 32-bit | little-endian (the integer so stored is the compact target encoding) | proof-of-work target in compact form |
| 76 | 4 | nNonce | unsigned 32-bit | little-endian | the search variable |

Field notes:

- The two 32-byte fields sit in the header in uint256 internal
  order. A reader comparing header bytes against displayed hashes
  must reverse each 32-byte field: the displayed form is the
  reverse of the stored bytes (v0.1.3 src/uint256.h, GetHex emits
  memory bytes last to first; v28.1 uint256 has the same storage
  and display convention). The previous block's hash was produced
  in internal order and is inserted as is; nothing reverses it at
  insertion.
- nBits stored little-endian means the integer in the header, read
  as a little-endian uint32, is the compact encoding whose top
  byte is the size byte (research/proof_of_work/PROOF_OF_WORK_AND_
  DIFFICULTY_SPECIFICATION.md). In the genesis header the stored
  bytes are ff ff 00 1d for the integer 0x1d00ffff.
- The nonce occupies the last 4 bytes, inside the second 64-byte
  chunk of the SHA-256 input. That placement is the structural
  basis of the nonce-dependence structure (SHA256D specification,
  section 7): header bytes 0 to 63 (version, previous hash, and
  merkle root bytes 36 to 63) contain no field that changes during
  a search.

## 2. Construction in v0.1.3

The header is not a separate struct. It is the first six fields of
class CBlock (src/main.h lines 805 to 815), serialized by the
class's IMPLEMENT_SERIALIZE block (line 828): the six fields in
order, with transactions appended unless the stream type carries
SER_GETHASH or SER_BLOCKHEADERONLY. Integer serialization is a raw
memory copy (src/serialize.h line 105), little-endian on the
platforms this code targets; uint256 fields serialize as their raw
32 memory bytes (src/uint256.h lines 360 to 363).

Hashing input construction: CBlock::GetHash() (src/main.h lines
862 to 865) does not serialize at all. It returns Hash(BEGIN
(nVersion), END(nNonce)): the raw in-memory bytes from the start
of nVersion to the end of nNonce, fed to the double SHA-256
(OpenSSL path, src/util.h lines 339 to 346). This is sound only
because the in-memory layout is byte-identical to the
serialization (no padding: every field is naturally aligned and
the sizes sum to 80). The miner relies on the same identity for
its scratch struct and asserts the agreement on every found block
(src/main.cpp line 2318, a debug assertion; the standing evidence
for the agreement is the genesis recomputation, not the assert).

The miner's own per-candidate path does not call GetHash: it
pre-pads the 80 bytes once per template with FormatHashBlocks
(src/main.cpp lines 2138 to 2151) and runs its Crypto++ based
BlockSHA256 over the padded buffers (SHA256D specification,
section 5). The two paths produce byte-identical digests, verified
end to end on the genesis header.

Defaults and identity facts: SetNull (line 845) sets nVersion = 1,
both hashes 0, nTime = nBits = nNonce = 0; IsNull() is nBits == 0.
The on-disk and network block is this header serialization
followed by the compact-size transaction count and the
transactions; the 4-byte message-start and size prefix written by
WriteToDisk (line 919) are file framing, not part of the block or
its hash. CDiskBlockIndex stores the same six fields and
reconstructs the block hash by rebuilding a header and calling
GetHash, so the six fields are the complete identity of a block in
the index as well.

## 3. Construction in v28.1

CBlockHeader (src/primitives/block.h) carries the same six fields
with the same widths: int32_t nVersion, uint256 hashPrevBlock,
uint256 hashMerkleRoot, uint32_t nTime, uint32_t nBits, uint32_t
nNonce. Its serialization (SERIALIZE_METHODS) writes the fields in
the same order with the same conventions: the integers through
the serialization framework's little-endian encoding, the uint256
fields as their 32 internal bytes. The serialized form is
byte-identical to the v0.1.3 form for the same field values; a
header built by either era hashes identically in the other.

Hashing input construction: CBlockHeader::GetHash()
(src/primitives/block.cpp line 11) runs the serialization through
HashWriter (src/hash.h line 115), whose GetHash performs the
second SHA-256 pass inline: the digest is SHA256(SHA256(serialized
header)), with the intermediate digest an opaque byte string
between passes, exactly as specified in the SHA256D
specification, section 6. Two era contrasts worth recording:

- Core v28.1's CSHA256 has no midstate API, and the header hash
  path is single-stream: the multi-way SHA256D64 machinery (8-way
  AVX2, 4-way SSE41, 2-way SHA-NI) is used in production only by
  the merkle tree (src/consensus/merkle.cpp line 56), never for
  header hashing (Core audit). The reusable-prefix structure of
  the header (section 5) is therefore unexploited by Core itself,
  in both eras.
- getblocktemplate does not hand the miner a serialized header. It
  hands out the field values (previousblockhash in displayed
  form, bits, curtime, mintime, height, the transaction list,
  coinbaseaux, coinbasevalue, default_witness_commitment), and
  the external miner constructs the 80 bytes itself (mining call
  graph, section 2). Serialization is the miner's responsibility
  in the modern architecture; in v0.1.3 it was the same process's
  internal affair.

## 4. Worked example: the genesis header, byte by byte

Constructed in the v0.1.3 source at src/main.cpp lines 1456 to
1480 (nVersion 1, hashPrevBlock 0, merkle root from its single
coinbase, nTime 1231006505, nBits 0x1d00ffff, nNonce 2083236893).
The 80 bytes (verified by two independent recomputations in
Phase 001):

```
01000000 0000000000000000000000000000000000000000000000000000000000000000
3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a
29ab5f49 ffff001d 1dac2b7c
```

| Offset | Bytes | Interpretation |
|---|---|---|
| 0 to 3 | 01 00 00 00 | nVersion = 1, little-endian |
| 4 to 35 | 00 ... 00 | hashPrevBlock = 0 (no predecessor) |
| 36 to 67 | 3b a3 ed fd ... 4b 1e 5e 4a | hashMerkleRoot, internal order; reversed for display: 4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b, the source's asserted root, and (one transaction) also the coinbase txid in display form |
| 68 to 71 | 29 ab 5f 49 | nTime = 0x495fab29 = 1231006505 |
| 72 to 75 | ff ff 00 1d | nBits = 0x1d00ffff, decoding to target 0xffff * 2^208 |
| 76 to 79 | 1d ac 2b 7c | nNonce = 0x7c2bac1d = 2083236893 |

SHA-256d of these 80 bytes is, in internal order,
6fe28c0ab6f1b372c1a6a246ae63f74f931e8365e15a089c68d6190000000000;
displayed reversed, 000000000019d6689c085ae165831e934ff763ae46a2a6c172
b3f1b60a8ce26f, the hashGenesisBlock constant (src/main.cpp line
24), numerically below the decoded target, so the header passes
the proof-of-work test of its era and of the modern one.

## 5. Mutation table: what a miner may roll

A "roll" is a change to the header (or to what feeds it) that
produces a fresh candidate space without a new template from the
node. The fields differ fundamentally in mechanism and cost:

| Field | Roll mechanism | Consensus and protocol constraints | Cost of one step | Era notes |
|---|---|---|---|---|
| nNonce | Increment in place; the primary search variable | None: any 32-bit value is legal in any header | One header byte-range changes (bytes 76 to 79); the midstate is untouched | Both eras. v0.1.3 starts at 1 and never hashes 0 (Phase 001, NONCE_SEARCH_ANALYSIS); modern practice starts at 0. The starting value is a search convention, not a rule |
| nTime | Update the timestamp within the legal window | Must exceed the median time past of the previous 11 blocks (contextual rule, both eras in substance); must not exceed network-adjusted time plus 2 hours (v0.1.3 CheckBlock; v28.1 the same 2-hour future bound in contextual checks). getblocktemplate declares "time" mutable and supplies mintime and curtime | Changes chunk 2 word W[1]; invalidates the chunk-2 prefix rounds but not the midstate | v0.1.3 refreshes nTime only at housekeeping gates (every 262,144 candidates); modern miners roll it as needed. Each distinct nTime is a distinct slice of the search space (NONCE_AND_SEARCH_SPACE_MODEL) |
| nVersion | Version rolling under BIP320: vary the general-purpose bits (mask 0x1fffe000) of the version the template provides | The template version encodes BIP9 signalling in its low bits and the 001 top-bit pattern; rolling must preserve the signalling bits the template carries and stay inside the BIP320 general-purpose range. getblocktemplate does not list version among the default mutable fields; pools that support version rolling negotiate it (Stratum version-rolling extension) | Changes chunk 1 word M[0]; invalidates the midstate itself, so each version variant needs its own midstate | Absent entirely in v0.1.3 (version stays 1; nothing constrains it in CheckBlock, but the miner never changes it). Absent from NOVA production today (EXP-034 finding: a genuine gap, owned by EXP-035's search-space work) |
| hashMerkleRoot | Not rolled directly: changed only by changing the coinbase (extranonce, below) or the transaction set, then recomputing the root | The root must match the block's actual transactions and coinbase; the witness commitment in the coinbase must be recomputed when the transaction set or coinbase changes (v28.1 GenerateCoinbaseCommitment; the external miner places default_witness_commitment) | A merkle recomputation: the coinbase leaf plus O(log n) branch hashes for the root path if branches are cached, a full tree rebuild if not; invalidates the midstate (root bytes span the chunk 1 / chunk 2 boundary, offsets 36 to 67) | Both eras: the root is recomputed once per template in v0.1.3 (BuildMerkleTree) and per coinbase change in modern miners |
| (via coinbase) extranonce | Bytes placed by the miner in the coinbase scriptSig, beyond the required pushes; changing them changes the coinbase txid, hence the root | The scriptSig must keep its required content: in v28.1 the BIP34 height push comes first and coinbaseaux flags must be included (GBT contract); the coinbase size bounds (scriptSig 2 to 100 bytes in the historical rule) bound the space. The node never supplies or increments an extranonce: there is no IncrementExtraNonce anywhere in v28.1 (Core audit); the space is entirely client-owned | One coinbase rebuild plus merkle root recomputation per step; each step opens a fresh 2^32 nonce space under a new midstate | v0.1.3: a local CBigNum counter in BitcoinMiner, pushed after nBits in the scriptSig, incremented per template rebuild, never persisted (Phase 001). NOVA: MiningEngine extranonce_space (EXP-034) on the GBT path; extranonce1/extranonce2 pair on Stratum paths |
| hashPrevBlock, nBits | Never rolled | Both are fixed by the chain state and the retarget rule; a header with a different prevhash is a header for a different chain position, and nBits must equal the required value exactly (PoW specification, section 4.3) | Not applicable: changing either is a new template, not a roll | Both eras |

Reconstruction rule, stated once for implementers: the padded
hash buffers and the midstate depend on every byte of the header.
A nonce step changes only bytes 76 to 79 (chunk 2 only). An nTime
step changes chunk 2 only. A version, merkle root, or prevhash
change invalidates chunk 1 and therefore the midstate. Any
implementation that reuses state across a change in the wrong
class silently hashes a different header than it believes it
does; the EXP-025 template cache's layered identity exists
precisely to make that class of error structurally impossible on
the template side (see section 6).

## 6. NOVA's header handling correspondence

From the Phase A audit and the EXP-034/036 records; stated as
correspondence to this specification, not as new claims.

- **GBT path (mining/engine.py).** MiningEngine builds the
  candidate header from the template's fields: version,
  previousblockhash (converted from displayed form to internal
  order), the merkle root it computes from its assembled coinbase
  and the template's transaction set, curtime, bits, and the
  nonce, serialized in exactly the section 1 layout. The
  EXP-025 template cache keys a prepared template by a layered
  identity (family, transaction set, coinbase, header fields), so
  a cached midstate-class object is reused only when every field
  that feeds it is unchanged; the cache is bounded (128 entries)
  with an uncached fallback path preserved. The engine's
  extranonce enters through the coinbase it assembles, and
  EXP-034's opt-in extranonce_space=(first, count) partitions
  which extranonce rounds an engine instance steps (default
  (0, 64), the historical behaviour).
- **Solo server path (mining/solo_server.py).** The server
  assembles coinbase halves (coinb1, coinb2) around the
  extranonce slot and serves jobs whose header fields it fixes;
  workers insert extranonce1 and extranonce2 and roll the nonce.
  EXP-034 found and fixed a real defect here: the extranonce
  split offset was located in the full coinbase and applied to
  the stripped coinbase, corrupting the scriptSig on segwit
  templates; the fix locates the offset in the stripped bytes.
  That defect class is exactly the section 5 warning: a byte
  offset computed against the wrong serialization.
- **Stratum pool path (mining/mainnet_live.py).** The header is
  assembled from the pool's job fields (coinb1, extranonce1,
  extranonce2, coinb2, merkle branches, version, prevhash, nbits,
  ntime) by the standard Stratum construction; the merkle root is
  computed by folding the coinbase hash up the branch list, which
  is the O(log n) path of the mutation table.
- **Verification (mining/candidate_verify.py, EXP-036).** A found
  candidate is re-serialized and re-hashed independently
  (hashlib and a pure-Python implementation must agree), and the
  digest is judged by the integer rule of the PoW specification
  before any submission. Header handling therefore closes the
  loop: the bytes that were searched are the bytes that are
  re-verified, and a serialization discrepancy anywhere in the
  chain shows up as a digest mismatch, not as a submitted invalid
  block.

Gaps recorded against this specification, honestly: NOVA
production has no version rolling and no miner-side ntime rolling
on any path (EXP-034, re-verified there by test); its search-space
expansion mechanisms are the nonce, the engine extranonce rounds,
and the Stratum extranonce pair. The model of the full space,
including the unimplemented dimensions, is research/nonce_search/
NONCE_AND_SEARCH_SPACE_MODEL.md.

## 7. Reproduction

- Genesis header bytes and hash: research/phase001/RAW_RESULTS/
  genesis_recompute.py and sha256d_layout_verify.py.
- v0.1.3 construction: src/main.h lines 805 to 865 and
  src/serialize.h line 105 of the verified tree.
- v28.1 construction: src/primitives/block.h and block.cpp of the
  pinned tree, as cited in research/bitcoin_core/CORE_SOURCE_
  AUDIT.md.
