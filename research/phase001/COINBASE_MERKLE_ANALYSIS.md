# Phase 001, Deliverable 5: Coinbase and Merkle Tree Analysis

Project: NOVA SHA-X, Research Phase 001. Subject: Bitcoin v0.1.3, verified tree (SOURCE_INVENTORY.md). Citations are to that tree unless a RAW_RESULTS file is named. "Proven" means read from the cited source in this session; the worked example is verified by two independent recomputations (Wave 1's RAW_RESULTS/genesis_recompute.py and a second byte-level recomputation performed for this document, agreeing exactly).

## 1. The coinbase, in full detail

### 1.1 What makes a transaction a coinbase in this version

`CTransaction::IsCoinBase()` (src/main.h line 437): a transaction is a coinbase if and only if it has exactly one input and that input's prevout IsNull, where COutPoint::IsNull (main.h line 157) requires hash == 0 and n == -1 (UINT_MAX). CheckTransaction adds the only other coinbase-specific rule (main.h lines 456 to 459, inside CheckTransaction at line 442): a coinbase's scriptSig must be between 2 and 100 bytes long. CheckBlock requires vtx[0] to be a coinbase and every later transaction not to be (src/main.cpp lines 1168 to 1172).

### 1.2 The miner's coinbase (src/main.cpp lines 2209 to 2216, 2266 to 2267)

Construction is covered field by field in TRANSACTION_RECONSTRUCTION.md section 5. The points that matter for the merkle analysis:

- The coinbase is a completely ordinary CTransaction for hashing purposes: its txid is SerializeHash over its serialization, with no special case.
- Two of its bytes-fields change per template: the extranonce push in scriptSig (increments every template) and, through it, the serialized length when the counter outgrows its byte width; and the output value (subsidy plus the template's fees). Any of these changes the txid, and therefore the merkle root, and therefore the header. That is the entire coupling between the search-space expansion mechanism (extranonce) and the header: extranonce to coinbase bytes to txid to merkle root to header bytes 36 to 67.
- The coinbase is always vtx[0] (pushed first, main.cpp line 2231), so its txid is always leaf 0 of the merkle tree.

### 1.3 The genesis coinbase (src/main.cpp lines 1456 to 1462)

```
        txNew.vin[0].scriptSig     = CScript() << 486604799 << CBigNum(4) << vector<unsigned char>(...pszTimestamp...);
        txNew.vout[0].nValue       = 50 * COIN;
        txNew.vout[0].scriptPubKey = CScript() << CBigNum("0x5F1D...A6704") << OP_CHECKSIG;
```

with pszTimestamp = "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks" (line 1456, 69 bytes). Its serialization, byte by byte (verified in the worked example, section 4):

| Bytes | Contents |
|-------|----------|
| 4 | nVersion = 1 (little-endian 01000000) |
| 1 | vin count = 1 |
| 36 | null prevout: 32 zero bytes, then ffffffff |
| 1 | scriptSig length = 77 (0x4d) |
| 77 | scriptSig: `04 ffff001d` (push of the 4-byte little-endian CBigNum encoding of 486604799 = 0x1d00ffff) + `01 04` (push of CBigNum(4) as one byte 0x04) + `45` (push header for 69 bytes: 0x45 = 69, a direct length byte since 69 < OP_PUSHDATA1) + the 69 headline bytes |
| 4 | nSequence = ffffffff |
| 1 | vout count = 1 |
| 8 | nValue = 5,000,000,000 (little-endian 00f2052a01000000) |
| 1 | scriptPubKey length = 67 (0x43) |
| 67 | scriptPubKey: `41` (push 65 bytes) + the 65-byte uncompressed public key + `ac` (OP_CHECKSIG) |
| 4 | nLockTime = 0 |

Total 204 bytes. Note the scriptSig's first push encodes the same integer the miner pushes first (the block's nBits, 0x1d00ffff): the genesis coinbase follows the miner's own scriptSig pattern, with CBigNum(4) and the headline appended. The public key in the scriptPubKey is the byte-reversal of the CBigNum constant in the source (CBigNum stores the MPI-reversed form; getvch reverses it back out, src/bignum.h line 246), giving the 65-byte key beginning 04678afd... and ending ...bf11d5f. Both facts are verified by the recomputations: building the transaction exactly this way reproduces the source's asserted txid and merkle root (section 4).

## 2. The merkle tree algorithm, as coded

The algorithm is `CBlock::BuildMerkleTree() const`, src/main.h lines 868 to 885, a member of CBlock operating on the block's vtx and its mutable cache member vMerkleTree:

```
    uint256 BuildMerkleTree() const
    {
        vMerkleTree.clear();
        foreach(const CTransaction& tx, vtx)
            vMerkleTree.push_back(tx.GetHash());
        int j = 0;
        for (int nSize = vtx.size(); nSize > 1; nSize = (nSize + 1) / 2)
        {
            for (int i = 0; i < nSize; i += 2)
            {
                int i2 = min(i+1, nSize-1);
                vMerkleTree.push_back(Hash(BEGIN(vMerkleTree[j+i]),  END(vMerkleTree[j+i]),
                                           BEGIN(vMerkleTree[j+i2]), END(vMerkleTree[j+i2])));
            }
            j += nSize;
        }
        return (vMerkleTree.empty() ? 0 : vMerkleTree.back());
    }
```

Step by step, proven from this text:

1. **Leaves.** The tree starts as the list of transaction hashes in block order: vMerkleTree[0..n-1] = GetHash() of each transaction in vtx (lines 871 to 873). Leaf order is block order; the coinbase is leaf 0.
2. **Levels.** While the current level size nSize exceeds 1, the next level has (nSize + 1) / 2 nodes. Nodes are appended to the same vector; the level offset j advances by the previous level's size (line 882), so vMerkleTree holds the whole tree flattened level by level, not just the current frontier.
3. **Parent computation.** For pair index i (stepping by 2), the parent is the two-range Hash() over the raw memory bytes of the left child followed by the raw memory bytes of the right child (lines 878 to 879): parent = SHA256d(left bytes || right bytes), where each child contributes exactly its 32 internal-order bytes (BEGIN/END over a uint256, src/util.h lines 23 to 24 and 349 to 361). The two-range Hash overload builds the first SHA-256 over the concatenation with an OpenSSL SHA256_CTX (Init, Update on the first range, Update on the second, Final) and then applies the one-shot SHA256 to the 32-byte result. No byte reversal occurs at any point inside the tree: children are consumed and produced in uint256 internal order throughout.
4. **Odd-node rule.** The right index is `i2 = min(i+1, nSize-1)` (line 877): when a level has an odd count, the last node is paired with itself. The last parent of such a level is SHA256d(last || last). This is the duplication rule, implemented as index clamping rather than an explicit copy.
5. **Root.** The function returns the last element appended (vMerkleTree.back()), or 0 for an empty block (line 884). For a single-transaction block the loop never runs and the root is the transaction's own hash.
6. **Where the root goes.** The miner assigns it to the header once per template (src/main.cpp line 2294). Validation recomputes it: CheckBlock rejects a block whose hashMerkleRoot differs from a fresh BuildMerkleTree() (src/main.cpp lines 1185 to 1187).

Related functions, for completeness: `CBlock::GetMerkleBranch(int nIndex)` (main.h line 887) extracts an authentication path from the cached flattened tree, and the static `CBlock::CheckMerkleBranch` (line 903) folds a leaf plus branch back to a root using the same two-range Hash, ordering the pair by the index bit at each level. CMerkleTx::SetMerkleBranch (src/main.cpp line 286) uses them to attach wallet transactions to blocks. Neither is on the mining path.

## 3. Byte order at every step (complete statement)

- Transaction serialization: little-endian integers, raw uint256 memory order for hashes inside COutPoint (TRANSACTION_RECONSTRUCTION.md section 2).
- Leaf hash: SHA-256d over the serialization; the digest is stored in uint256 internal order, which is the byte reverse of the displayed txid hex (uint256::GetHex reverses, src/uint256.h line 294). When people write the genesis txid as 4a5e1e4b..., that is the display form; the 32 bytes that enter the merkle tree and the header are 3ba3edfd...a4b1e5e4a (verified in section 4).
- Parent hash: SHA-256d over left-internal-bytes concatenated with right-internal-bytes; output again in internal order.
- Root into header: CBlock::hashMerkleRoot is a uint256 serialized as its raw memory bytes (src/uint256.h lines 360 to 363), so header bytes 36 to 67 are the internal-order root, the reverse of the displayed root hex.
- There is exactly one place where byte order flips: display (GetHex/SetHex). Hashing, tree building, header assembly and target comparison all stay in internal order end to end. Proven from the cited serialization and hashing code.

## 4. Worked example: the genesis block's single transaction

The genesis block (constructed at src/main.cpp lines 1456 to 1480) has exactly one transaction, so by rule 5 of section 2 the merkle root must equal the coinbase's txid, and the source asserts exactly that (line 1479: hashMerkleRoot == 0x4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b). Re-derivation from the source's own constants, following the coded steps:

1. Build the coinbase per section 1.3: scriptSig from 486604799, CBigNum(4) and the 69-byte headline; one output of 50 * COIN to the genesis public key with OP_CHECKSIG; null prevout; sequence and locktime at defaults. Serialized size 204 bytes. Full byte string (from the verified recomputation):
   `01000000 01 0000000000000000000000000000000000000000000000000000000000000000 ffffffff 4d 04ffff001d010445<69 headline bytes> ffffffff 01 00f2052a01000000 43 41<65 key bytes>ac 00000000`
2. Leaf hash (CTransaction::GetHash, main.h line 393; SerializeHash and Hash, src/util.h lines 383 and 339): SHA-256d of the 204 bytes. Internal-order result: `3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a`. Display form (reversed): `4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b`.
3. Tree: vtx.size() = 1, so the level loop condition (nSize > 1) is false immediately; vMerkleTree = [leaf]; the function returns the leaf. Merkle root (display form) = 4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b, equal to the source's asserted constant at main.cpp line 1479.
4. Header embedding: the root enters the header in internal order, which is why the genesis header bytes (BLOCK_HEADER_SPECIFICATION.md section 4) contain `3ba3edfd...4b1e5e4a` at offsets 36 to 67, the reverse of the displayed root.

Verification status: Wave 1's RAW_RESULTS/genesis_recompute.py parsed the constants out of src/main.cpp itself and reproduced both the merkle root and the block hash (RAW_RESULTS/genesis_recompute_output.txt: "merkle recomputed ... MATCH=True"). A second, independent byte-level recomputation performed for this deliverable, assembling the transaction and header from the documented field layout, produced the identical 204-byte transaction, the identical internal-order txid, and the known genesis block hash. The example is therefore verified twice over, and the source's own asserts (main.cpp lines 1479 to 1480) make it a self-check the original code performs at first run.

For a multi-transaction illustration of the pairing rule (derived from the code, not from a historical block): with three transactions A, B, C, level 0 is [A, B, C]; level 1 is [SHA256d(A||B), SHA256d(C||C)] (C duplicated by the min() clamp); the root is SHA256d of those two parents concatenated. With two transactions the root is SHA256d(A||B) directly.

## 5. Intermediate reuse and computational dependencies

What is reused (proven):

- **Within one BuildMerkleTree call:** every computed node is kept in vMerkleTree (the flattened tree), so GetMerkleBranch can extract proofs without recomputation, and parents are computed once each from stored children. Total work for n transactions: n leaf hashes plus (n - 1) parent hashes for n a power of two, and the analogous count otherwise; each parent is one SHA-256d over 64 bytes.
- **Across the miner's life:** nothing. The miner calls BuildMerkleTree once per template (main.cpp line 2294) and it recomputes every leaf hash from the transactions' serializations, even though the mempool map it collected them from is keyed by exactly those hashes (mapTransactions is map<uint256, CTransaction>, main.cpp line 18). The keys are not reused. vMerkleTree is a mutable cache member of CBlock (main.h line 820) but the miner creates a fresh CBlock per template, so the cache never survives into a second template.
- **Dependency structure:** the root depends on the ordered list of serialized transactions and on nothing else: no header field, no target, no timestamp. Conversely, the header's bytes 36 to 67 depend on every byte of every transaction through the tree. Changing any transaction, its position, or the coinbase (including a one-byte extranonce growth) changes the root and restarts the header's hash input completely. Within the search loop, the root is invariant; it changes only at template rebuilds.
- **Verification cost symmetry:** a validating node pays the same full tree computation per block (CheckBlock, main.cpp line 1186), with the same non-reuse of the transaction hashes it computed while processing the transactions individually.

## 6. Findings specific to this deliverable

1. The odd-node duplication rule exists in the original code in its modern form (index clamping, main.h line 877), including its known consequence that a mutated tree with a duplicated last transaction can produce the same root as a shorter tree; the version has no defence against that class of mutation (no duplicate-transaction check appears in CheckBlock beyond the coinbase position rules). Stated as a source observation; the later CVE history is outside this phase's scope and is not relied on.
2. The tree is stored whole (flattened) rather than as a frontier, so memory per block is about 2n hashes; irrelevant at 2009 block sizes, recorded for the architecture record.
3. The coinbase to merkle coupling is the search's only expansion joint: the header nonce space per template is exactly 2^32, and expansion happens by rebuilding the coinbase (extranonce), the tree, and the header, in that dependency order. Any modern redesign starts from this dependency chain, which is proven here from source.
