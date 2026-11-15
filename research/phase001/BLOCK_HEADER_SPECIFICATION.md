# Phase 001, Deliverable 6: Complete 80-Byte Block Header Specification

Project: NOVA SHA-X, Research Phase 001. Subject: the block header as Bitcoin v0.1.3 defines it (verified tree, SOURCE_INVENTORY.md). All citations are to that tree. The worked example is verified by two independent recomputations (RAW_RESULTS/genesis_recompute_output.txt and a second byte-level recomputation for this document, identical results).

## 1. Definition in source

The header is not a separate struct. It is the first six fields of `class CBlock`, src/main.h lines 805 to 815:

```
class CBlock
{
public:
    // header
    int nVersion;
    uint256 hashPrevBlock;
    uint256 hashMerkleRoot;
    unsigned int nTime;
    unsigned int nBits;
    unsigned int nNonce;

    // network and disk
    vector<CTransaction> vtx;

    // memory only
    mutable vector<uint256> vMerkleTree;
```

and its serialization, src/main.h line 828:

```
    IMPLEMENT_SERIALIZE
    (
        READWRITE(this->nVersion);
        nVersion = this->nVersion;
        READWRITE(hashPrevBlock);
        READWRITE(hashMerkleRoot);
        READWRITE(nTime);
        READWRITE(nBits);
        READWRITE(nNonce);

        // ConnectBlock depends on vtx being last so it can calculate offset
        if (!(nType & (SER_GETHASH|SER_BLOCKHEADERONLY)))
            READWRITE(vtx);
        else if (fRead)
            const_cast<CBlock*>(this)->vtx.clear();
    )
```

Facts fixed by this code (proven):

- The header is exactly the serialization of the six fields in declaration order, produced when the stream type carries SER_GETHASH or SER_BLOCKHEADERONLY (transactions omitted), or as the prefix of the full block serialization otherwise.
- `CBlock::GetHash()` (main.h lines 862 to 865) is `Hash(BEGIN(nVersion), END(nNonce))`: it does not serialize at all, but hashes the raw in-memory bytes from the start of nVersion to the end of nNonce. This works only because the field layout in memory is byte-identical to the serialization (no padding: 4 + 32 + 32 + 4 + 4 + 4 = 80, every field naturally aligned). The miner relies on the same identity for its scratch struct (MINING_EXECUTION_FLOW.md section 4) and asserts the agreement on every found block (src/main.cpp line 2318).
- SetNull (main.h line 845) defaults: nVersion = 1, both hashes 0, nTime = nBits = nNonce = 0. IsNull() (line 857) is nBits == 0.
- There is no header length field, no header checksum, and no separate header type anywhere in the version (proven by the class inventory in ARCHITECTURE_MAP.md).

## 2. Field-by-field specification

All offsets are byte offsets in the 80-byte serialization. Integer serialization is a raw memory copy (serialize.h line 105), little-endian on the x86 platform this code targets. uint256 fields serialize as their raw 32 memory bytes (src/uint256.h lines 360 to 363).

| Offset | Size | Field | Type in source | Byte order on the wire | Meaning and source of value |
|--------|------|-------|----------------|------------------------|-----------------------------|
| 0 | 4 | nVersion | int (signed 32-bit) | Little-endian | Block version. SetNull default 1; the genesis block uses 1 (main.cpp line 1467); the miner never changes the CBlock default, so mined blocks are version 1. Nothing in CheckBlock constrains its value in this version (proven by the CheckBlock text, main.cpp lines 1154 to 1190). |
| 4 | 32 | hashPrevBlock | uint256 | Internal order: the 32 memory bytes of the uint256, which is the byte reverse of the displayed previous-block hash hex | Hash of the previous block's header, as computed by GetHash. Miner: pindexPrev->GetBlockHash() (main.cpp line 2293). Genesis: 0 (line 1465). |
| 36 | 32 | hashMerkleRoot | uint256 | Internal order, byte reverse of the displayed merkle root hex | Root of the block's transaction merkle tree, BuildMerkleTree (main.h line 868). See COINBASE_MERKLE_ANALYSIS.md. |
| 68 | 4 | nTime | unsigned int | Little-endian | Block timestamp, seconds since epoch. Miner: max(previous tip's median time past + 1, GetAdjustedTime()) at template build (main.cpp line 2295), refreshed at housekeeping gates during the search (line 2355). Validation bounds: must exceed the previous block's median time past (AcceptBlock, main.cpp line 1206 to 1207) and must not be more than 2 hours ahead of adjusted time (CheckBlock, lines 1164 to 1165). |
| 72 | 4 | nBits | unsigned int | Little-endian as an integer; the integer itself is the compact target encoding (top byte is the size, low three bytes the word, bignum.h lines 257 to 267) | The proof-of-work target in compact form. Miner: GetNextWorkRequired(pindexPrev) (main.cpp line 2203). Validation: the decoded target must not exceed bnProofOfWorkLimit and the block hash must not exceed the decoded target (CheckBlock lines 1180 to 1184), and nBits must equal GetNextWorkRequired exactly (AcceptBlock line 1210). |
| 76 | 4 | nNonce | unsigned int | Little-endian | The search variable. Miner starts it at 1 per template (main.cpp line 2297) and increments it in the scratch buffer per candidate (line 2344). |

Total: 4 + 32 + 32 + 4 + 4 + 4 = 80 bytes. There are no other header bytes, in this or any stream type.

## 3. Internal versus displayed byte order (the one rule that explains everything)

uint256 stores its value as eight little-endian 32-bit limbs, pn[0] least significant (src/uint256.h lines 26 to 30). Three consequences, each proven from the cited code:

1. **Hash inputs and outputs are internal order.** GetHash feeds the raw memory bytes BEGIN(nVersion) to END(nNonce) to the double SHA-256 (main.h lines 862 to 865), and the digest bytes written by OpenSSL's SHA256 into a uint256 buffer are taken as the value directly (util.h lines 339 to 346). The merkle tree likewise consumes and produces internal-order bytes (COINBASE_MERKLE_ANALYSIS.md section 3).
2. **Display is reversed.** uint256::GetHex (uint256.h line 294) emits the memory bytes from last to first. The familiar block hash string (for genesis, 000000000019d668...) is the reverse of the 32 bytes the second SHA-256 actually produced (6fe28c0a...00000000 in internal order, verified in our recomputation). SetHex parses display form back into internal order (lines 303 to 333).
3. **Comparison is numeric on the internal representation.** operator<= for base_uint (uint256.h line 226) compares limbs from pn[WIDTH-1] down to pn[0], i.e. most significant first, which is a true unsigned 256-bit comparison of the value whose display form is the reversed hex. The miner's `hash <= hashTarget` (main.cpp line 2315) and CheckBlock's `GetHash() > target` rejection (line 1182 to 1184) are therefore comparisons of the displayed hash read as a big-endian number, even though no big-endian byte string ever exists in memory. The miner's BlockSHA256 byte-reverses its output state words precisely so its result lands in this internal layout (main.cpp lines 2172 to 2173).

For the two hash fields inside the header, the same rule applies in reverse: hashPrevBlock and hashMerkleRoot sit in the header in internal order. The previous block's hash was produced in internal order and is inserted as is; nothing reverses it at insertion. A reader comparing header bytes against displayed hashes must reverse each 32-byte field, as the worked example shows.

## 4. Worked example: the genesis header, byte by byte

The genesis block is constructed at src/main.cpp lines 1456 to 1480 with nVersion = 1, hashPrevBlock = 0, merkle root from its single coinbase, nTime = 1231006505, nBits = 0x1d00ffff, nNonce = 2083236893. Its 80-byte header (RAW_RESULTS/genesis_recompute_output.txt, re-verified for this document):

```
01000000 0000000000000000000000000000000000000000000000000000000000000000 3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a 29ab5f49 ffff001d 1dac2b7c
```

Field annotation:

| Offset | Bytes (hex) | Interpretation |
|--------|-------------|----------------|
| 0 to 3 | 01 00 00 00 | nVersion = 1, little-endian |
| 4 to 35 | 00 ... 00 (32 bytes) | hashPrevBlock = 0 (genesis has no predecessor) |
| 36 to 67 | 3b a3 ed fd 7a 7b 12 b2 7a c7 2c 3e 67 76 8f 61 7f c8 1b c3 88 8a 51 32 3a 9f b8 aa 4b 1e 5e 4a | hashMerkleRoot in internal order. Reversed for display: 4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b, the source's asserted root (main.cpp line 1479) and, the block having one transaction, also its txid (COINBASE_MERKLE_ANALYSIS.md section 4) |
| 68 to 71 | 29 ab 5f 49 | nTime little-endian = 0x495fab29 = 1231006505 (2009-01-03 18:15:05 UTC; the UTC rendering is our conversion of the source's epoch value) |
| 72 to 75 | ff ff 00 1d | nBits little-endian = 0x1d00ffff. Decoded by CBigNum::SetCompact (bignum.h line 257): size byte 0x1d = 29, word 0x00ffff, target = 0x00ffff shifted left by 8 * (29 - 3) = 208 bits, i.e. 0x00000000ffff0000000000000000000000000000000000000000000000000000 |
| 76 to 79 | 1d ac 2b 7c | nNonce little-endian = 0x7c2bac1d = 2083236893 |

Hash check (verified): SHA-256d of these 80 bytes in internal order is 6fe28c0ab6f1b372c1a6a246ae63f74f931e8365e15a089c68d6190000000000; displayed reversed it is 000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f, the hashGenesisBlock constant (main.cpp line 24), and as a number it is below the decoded target above, so the header passes the CheckBlock proof-of-work test. The source performs the equivalent assert at first run (line 1480).

Note where the nonce sits: bytes 76 to 79 are the last four bytes of the header, inside the second 64-byte SHA-256 block (bytes 64 to 127 after padding). The first block (bytes 0 to 63: version, previous hash, and merkle root bytes 36 to 63) contains no field that changes during a search. This placement, combined with the miner starting both hashes from the initial state per candidate, is the structural fact behind the repeated-computation finding in MINING_EXECUTION_FLOW.md section 6.2.

## 5. Mutation rules during mining (what may change, what forces reconstruction)

From the miner's code (src/main.cpp lines 2292 to 2355) and the validation code:

| Field | Changes inside the search loop? | Changes at template rebuild? | Effect of changing it |
|-------|--------------------------------|------------------------------|------------------------|
| nVersion | Never (stays 1) | Never in practice (CBlock default) | Would change block 0 of the hash input; no code path in the miner touches it |
| hashPrevBlock | Never | Yes, when the best tip moves; a tip move also breaks the search loop at the next housekeeping gate (line 2349 to 2350) | Full restart: new template, new coinbase, new tree |
| hashMerkleRoot | Never | Yes, whenever the transaction set, the coinbase extranonce, or the coinbase value changes, i.e. every template | Recomputed once per template by BuildMerkleTree (line 2294); sits across the block 0/block 1 boundary of the hash input (bytes 36 to 67), so it invalidates both compression blocks |
| nTime | Yes, but only at housekeeping gates (every 262,144 candidates), refreshed to max(median past + 1, adjusted time) (line 2355) | Yes, set at build (line 2295) | Changes block 1 of the hash input only; padding is unaffected because length is unchanged, and the miner updates it in place in the padded buffer |
| nBits | Never | Yes, from GetNextWorkRequired (line 2203); also embedded as the first push of the coinbase scriptSig (line 2212), so an nBits change changes the merkle root too | Changes block 1 of the hash input and the target the loop compares against (line 2307) |
| nNonce | Yes, every candidate (++tmp.block.nNonce, line 2344) | Reset to 1 at each template (line 2297) | The search variable; bytes 76 to 79, block 1 only |

Reconstruction rule, stated as the code implements it: the padded hash buffers are rebuilt (FormatHashBlocks, lines 2299 to 2300) exactly once per template, after every field except nNonce and nTime is final. Inside the loop only the last eight bytes of the header (nBits is fixed, so in practice the four nNonce bytes, and occasionally the four nTime bytes) ever change. Everything else that could change a header byte is pushed out to a full template rebuild by the loop's break conditions. There is no mechanism in this version to change the merkle root, the previous hash, or the transaction set mid-search.

## 6. Header-adjacent facts recorded for completeness

- The block as stored and relayed is the header serialization followed by the compact-size transaction count and the transactions (CBlock::Serialize with no GETHASH/BLOCKHEADERONLY flag, main.h line 828). On disk, WriteToDisk prefixes the 4-byte pchMessageStart and the serialized size (main.h line 919); those eight bytes are file framing, not part of the block or its hash.
- CDiskBlockIndex (main.h line 1133; its GetBlockHash at line 1170) stores the same six fields (with hashPrev/hashNext in place of pointers) and reconstructs the block hash by rebuilding a CBlock header and calling GetHash, proof that the six fields are the complete identity of a block in this version's index as well.
- The version's own header comment in main.h (lines 795 to 800) describes the design in one sentence: nodes collect transactions into a block, hash them into a hash tree, and scan nonce values until the block's hash satisfies proof of work. The 80-byte layout specified above is that design's exact byte form, unchanged in layout from the modern header (the modern differences are in rules about the fields' values, not in the layout; stated from the v28.1 audit in research/bitcoin_core/, not from this tree).
