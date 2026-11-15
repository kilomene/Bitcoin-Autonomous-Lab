# Phase 001, Deliverable 4: Complete Bitcoin Transaction Reconstruction

Project: NOVA SHA-X, Research Phase 001. Subject: transactions in Bitcoin v0.1.3, exactly as coded in the verified tree (SOURCE_INVENTORY.md). All citations are to that tree. "Proven" means read from the cited source in this session. Where modern Bitcoin differs, the difference is flagged; nothing modern is projected back into this version.

## 1. The types

All transaction types are declared in `src/main.h`. There is no transaction module file.

| Type | Lines | Fields |
|------|-------|--------|
| COutPoint | 147 to 186 | `uint256 hash; unsigned int n;` A reference to one output of a previous transaction. SetNull sets hash = 0 and n = -1 (UINT_MAX). IsNull tests both. |
| CTxIn | 193 to 268 | `COutPoint prevout; CScript scriptSig; unsigned int nSequence;` nSequence defaults to UINT_MAX in the constructors; IsFinal() is nSequence == UINT_MAX (line 226). |
| CTxOut | 274 to 351 | `int64 nValue; CScript scriptPubKey;` SetNull sets nValue = -1 (line 307). |
| CTransaction | 357 to 594 | `int nVersion; vector<CTxIn> vin; vector<CTxOut> vout; int nLockTime;` SetNull sets nVersion = 1, clears both vectors, nLockTime = 0 (lines 385 to 391). |
| CMerkleTx | 598 to 654 | CTransaction plus hashBlock, vMerkleBranch, nIndex (a transaction with its merkle proof). |
| CWalletTx | 660 to 731 | CMerkleTx plus vtxPrev, mapValue (string key/value metadata), vOrderForm, nTimeReceived, fFromMe, fSpent. The wallet's record; not a wire type. |
| CTxIndex | 738 to 791 | Database record (not part of a transaction): CDiskTxPos pos, vector<CDiskTxPos> vSpent with one entry per output. |
| CDiskTxPos | 80 to 129 | unsigned int nFile, nBlockPos, nTxPos: where a transaction sits in the blk*.dat files. |

## 2. Serialization format, as coded

Serialization is defined by each class's IMPLEMENT_SERIALIZE block, executed by the framework in `src/serialize.h`. Two framework facts determine the byte format (both proven from serialize.h):

- Primitive integers are written by raw memory copy, `WRITEDATA(s, obj)` = `s.write((char*)&(obj), sizeof(obj))` (line 105). On the x86 platform this is little-endian. There is no endian conversion anywhere in the serializer.
- Vectors and byte strings are prefixed with a compact-size length (WriteCompactSize, line 161): one byte if under 253, 0xfd plus a uint16 if up to 65535, 0xfe plus a uint32, 0xff plus a uint64. A CScript serializes as its underlying vector<unsigned char>: length prefix plus raw script bytes.
- uint256 serializes as its raw 32 memory bytes (src/uint256.h lines 360 to 363), i.e. the internal little-endian-limb order, which is the reverse of the displayed hex order.
- COutPoint serializes FLATDATA (main.h line 155): the 32 hash bytes followed by the 4 bytes of n, 36 bytes total, no length prefixes.

The resulting wire/disk layout of a CTransaction (serialize block at main.h line 371: READWRITE(nVersion), READWRITE(vin), READWRITE(vout), READWRITE(nLockTime)):

| Order | Field | Encoding | Size |
|-------|-------|----------|------|
| 1 | nVersion | int32, raw (little-endian) | 4 |
| 2 | vin count | compact size | 1+ |
| 3 | each CTxIn | prevout (36 bytes FLATDATA), scriptSig (compact size + bytes), nSequence (uint32 raw) | 41+ per input plus script |
| 4 | vout count | compact size | 1+ |
| 5 | each CTxOut | nValue (int64 raw, little-endian, in satoshis), scriptPubKey (compact size + bytes) | 9+ per output plus script |
| 6 | nLockTime | int32, raw | 4 |

CTxIn's own block is at main.h line 219 (prevout, scriptSig, nSequence); CTxOut's at line 292 (nValue, scriptPubKey). The same serialization is used for network, disk and hashing; the stream-type flags (SER_NETWORK, SER_DISK, SER_GETHASH, serialize.h lines 37 to 43) change behaviour only where a class tests them (CBlock tests SER_GETHASH/SER_BLOCKHEADERONLY to omit transactions; CTransaction itself does not branch on stream type). One quirk is visible in CTransaction's block: the line `nVersion = this->nVersion;` sits between the READWRITE of nVersion and the vectors, a no-op self-assignment left in the source.

Worked size check (proven by our recomputation, RAW_RESULTS/genesis_recompute_output.txt): the genesis coinbase serializes to exactly 204 bytes under these rules: 4 (version) + 1 (vin count) + 36 (null prevout) + 1 (scriptSig length 77) + 77 + 4 (sequence) + 1 (vout count) + 8 (value) + 1 (scriptPubKey length 67) + 67 + 4 (locktime) = 204.

## 3. Transaction identity: the txid

`CTransaction::GetHash()` (main.h line 393) returns `SerializeHash(*this)`. SerializeHash (src/util.h lines 383 to 390) serializes the object into a CDataStream with type SER_GETHASH and returns `Hash(ss.begin(), ss.end())`, the double SHA-256 template (src/util.h line 339):

```
    uint256 hash1;
    SHA256((unsigned char*)&pbegin[0], (pend - pbegin) * sizeof(pbegin[0]), (unsigned char*)&hash1);
    uint256 hash2;
    SHA256((unsigned char*)&hash1, sizeof(hash1), (unsigned char*)&hash2);
    return hash2;
```

These SHA256 calls are OpenSSL's (headers.h line 18 includes openssl/sha.h; util.h uses the one-shot and SHA256_CTX forms). So: txid = SHA256(SHA256(serialized transaction)), computed over the full serialization of section 2, stored internally in uint256 memory order, and displayed byte-reversed by uint256::GetHex (src/uint256.h line 294). There is no separate witness or stripped hash in this version; the txid covers exactly the bytes above, including scriptSigs. Proven.

## 4. Script construction relevant to mining

CScript is a byte vector with push operators (src/script.h lines 327 to 471); the full opcode table is the opcodetype enum at script.h line 17. The pushes the mining path uses:

- `operator<<(unsigned int)` and the other integer overloads route to push_uint64/push_int64 (lines 397 to 406, 330 to 356): values 1 to 16 and -1 become the single opcode bytes OP_1..OP_16 (0x51 to 0x60) and OP_1NEGATE (0x4f); every other value becomes a CBigNum byte-vector push. Zero becomes an empty byte-vector push (a single 0x00 length byte, i.e. OP_0); derived from push_int64 falling through to the CBigNum path with an empty getvch(), stated as derivation, not a quoted line.
- `operator<<(const CBigNum&)` (line 437) pushes b.getvch(): the little-endian sign-magnitude encoding produced by CBigNum::getvch (src/bignum.h line 246), wrapped by the vector push below.
- `operator<<(const vector<unsigned char>&)` (lines 443 to 462): if size < 76 (OP_PUSHDATA1), one length byte; if size <= 0xff, OP_PUSHDATA1 plus one length byte; else OP_PUSHDATA2 plus a uint16 length; then the bytes.
- `operator<<(const uint256&)` (lines 430 to 435) pushes a single length byte 32 then the raw memory bytes (used outside mining).
- `operator<<(opcodetype)` (lines 408 to 421) appends the opcode byte itself; OP_CHECKSIG is the only opcode the miner emits.

Validation of scripts is EvalScript (src/script.cpp line 44), reached for transaction inputs through VerifySignature (src/script.cpp line 1115), which evaluates scriptSig, then OP_CODESEPARATOR, then scriptPubKey as one script (line 1126). The miner never builds scriptSigs for ordinary transactions; it only verifies them (through ConnectInputs) and copies the transactions verbatim.

## 5. Coinbase construction in block assembly

The block assembly function in this version is `BitcoinMiner()` itself (src/main.cpp line 2183); there is no CreateNewBlock. The coinbase is built at lines 2209 to 2216:

```
        CTransaction txNew;
        txNew.vin.resize(1);
        txNew.vin[0].prevout.SetNull();
        txNew.vin[0].scriptSig << nBits << ++bnExtraNonce;
        txNew.vout.resize(1);
        txNew.vout[0].scriptPubKey << key.GetPubKey() << OP_CHECKSIG;
```

and completed at lines 2266 to 2267, after transaction collection:

```
        pblock->nBits = nBits;
        pblock->vtx[0].vout[0].nValue = pblock->GetBlockValue(nFees);
```

Properties, all proven from these lines and the class definitions:

- Exactly one input, prevout null (hash 0, n = UINT_MAX): this is what makes it a coinbase under CTransaction::IsCoinBase (main.h line 437). Its nSequence keeps the CTxIn default UINT_MAX.
- scriptSig is two pushes and nothing else: the candidate block's nBits first, then the extranonce (section 7). No timestamp text, no miner tag, no height (block height in the coinbase does not exist in this version; that is a much later rule, noted only to prevent projection).
- Exactly one output: scriptPubKey = push of the miner key's 65-byte uncompressed public key, then OP_CHECKSIG (a pay-to-public-key output; there is no address hash in the coinbase). The key is a fresh CKey made when BitcoinMiner starts (line 2189) and replaced after each success (line 2331); it is saved to the wallet only when a block is found (AddKey, line 2329).
- nVersion and nLockTime keep the CTransaction defaults (1 and 0).
- The coinbase is placed at vtx[0] before any other transaction (line 2231), and CheckBlock enforces that position for all blocks (main.cpp lines 1168 to 1172).
- The genesis coinbase (main.cpp lines 1456 to 1462) is the same shape with a different scriptSig: `CScript() << 486604799 << CBigNum(4) << timestamp bytes`, where 486604799 is 0x1d00ffff, the genesis nBits as an integer; i.e. the genesis scriptSig follows the same "nBits first" pattern the miner uses, plus the extra CBigNum(4) and the newspaper headline. Its output pays the well-known genesis public key constant with value 50 * COIN. Full byte analysis in COINBASE_MERKLE_ANALYSIS.md.

## 6. Reward calculation: GetBlockValue and the halving rule as coded

`int64 CBlock::GetBlockValue(int64 nFees) const`, src/main.cpp lines 675 to 683:

```
int64 CBlock::GetBlockValue(int64 nFees) const
{
    int64 nSubsidy = 50 * COIN;

    // Subsidy is cut in half every 4 years
    nSubsidy >>= (nBestHeight / 210000);

    return nSubsidy + nFees;
}
```

The rule as coded, precisely:

- Base subsidy 50 * COIN = 5,000,000,000 satoshis (COIN = 100,000,000, main.h line 18).
- Halving is an arithmetic right shift of the subsidy by (nBestHeight / 210000), integer division. The comment says "every 4 years"; the code counts blocks, 210,000 per era. A shift (not a division by 2^era computed separately) means era k subsidy is exactly floor(5,000,000,000 / 2^k), and once the shift count reaches 33 the subsidy is 0 (5e9 < 2^33), which follows from the shift semantics; the total issuance implied by the shift rule is a known consequence, derived here arithmetically, not stated in the source.
- The height used is the global `nBestHeight`, the height of the current best tip at the moment of the call, not the height of the block being built (which would be nBestHeight + 1). At a halving boundary this makes the miner's own candidate use the pre-boundary era for the first block of the new era. Whether ConnectBlock accepts that is determined by the same function: ConnectBlock checks `vtx[0].GetValueOut() > GetBlockValue(nFees)` (main.cpp line 953) with the same global state, so miner and validator agree because both call the same code in the same state. Recorded as a faithful quirk of the code as written, proven from lines 675 to 683 and 953.
- The return value is subsidy plus the block's total fees; the miner assigns it as the coinbase's single output value (line 2267). A coinbase claiming more than GetBlockValue(nFees) is rejected in ConnectBlock; claiming less is allowed by this check (no exact-equality requirement exists in the cited code).

## 7. The extranonce mechanism, located exactly

The extranonce in v0.1.3 is a local variable of BitcoinMiner, and nothing else:

- Declaration: `CBigNum bnExtraNonce = 0;` at src/main.cpp line 2190, beside the miner key, before the outer loop. It is a CBigNum (arbitrary precision), not a fixed-width integer.
- Increment and placement: `txNew.vin[0].scriptSig << nBits << ++bnExtraNonce;` at line 2212. Pre-increment, once per outer-loop iteration, i.e. once per candidate block template. The first template of a run carries extranonce 1. It is the second push of the coinbase scriptSig, after nBits.
- Encoding: pushed through CScript::operator<<(const CBigNum&) (script.h line 437), so its bytes are CBigNum::getvch() (bignum.h line 246), little-endian sign-magnitude, minimally sized: the byte length of the scriptSig grows as the counter grows, which changes the coinbase serialization, hence its txid, hence the merkle root, for every template. That is the mechanism's purpose in the search: when the 32-bit header nonce wraps to 0, the inner loop breaks (main.cpp line 2347 to 2349) and the outer loop rebuilds with the next extranonce, opening a fresh 2^32 nonce space under a new merkle root.
- Ownership and lifetime: owned solely by the BitcoinMiner invocation. It is not persisted, not shared between threads, not part of CBlock or CTransaction state, and resets to 0 every time the miner thread (re)starts. Two miner threads started by toggling would each run their own counter from 0 (and use different coinbase keys, so their work still differs; the key difference is the actual separator, inferred from lines 2189 to 2190 and 2329 to 2331).
- What it is not: there is no extranonce in the header, no extranonce2 split, no pool-assigned extranonce, and no roll of the coinbase inside the inner loop. Within one template, the only mutable header fields are nNonce (every candidate) and nTime (at housekeeping gates). Proven by the complete inner loop text in MINING_EXECUTION_FLOW.md section 6.

## 8. Fees: how they are computed and where they go

- Per transaction, the fee is defined inside `CTransaction::ConnectInputs` (main.cpp lines 848 to 855): nTxFee = (sum of spent outputs' values) minus GetValueOut(); a negative fee is an error; if nTxFee < nMinFee the transaction is refused for this purpose (return false, not an error); otherwise nFees += nTxFee accumulates into the caller's total.
- In block assembly, the miner calls ConnectInputs with fMiner = true and nMinFee = tx.GetMinFee(pblock->vtx.size() < 100) (main.cpp line 2253). GetMinFee (main.h line 504) is (1 + serialized bytes / 1000) * CENT, with CENT = 1,000,000 satoshis (0.01 BTC), and returns 0 under 10,000 bytes when the discount flag is set, which the miner sets while the block has under 100 transactions. The source comment (lines 2248 to 2250) states the intent: fee requirements are "mainly only needed for flood control"; under 10K is free for the first 100 transactions; base rate 0.01 per KB.
- The accumulated nFees goes only into the coinbase value through GetBlockValue (section 6). There is no separate fee output and no fee market ordering: see section 9.
- For mempool admission (not mining), AcceptTransaction calls ConnectInputs with nMinFee = 0 (main.cpp line 469), so admission itself does not impose the miner's fee floor; the floor is applied at block assembly time only. Proven from the two call sites.

## 9. Transaction selection for a new block

Source: the collection loop in BitcoinMiner, main.cpp lines 2236 to 2265, analysed mechanically in MINING_EXECUTION_FLOW.md section 3.4. The selection policy as coded:

- **Pool:** the global `mapTransactions` (main.cpp line 18), the mempool. Transactions enter it through CTransaction::AcceptTransaction (line 406) via AddToMemoryPool (line 481), which also registers every input in mapNextTx and bumps nTransactionsUpdated. Coinbase transactions are refused as loose transactions (lines 411 to 412).
- **Order:** `std::map` iteration order, which is uint256 key order: transactions are considered in transaction-hash order. There is no fee-per-byte sorting, no arrival order, no priority by age or value anywhere in the selection code (proven by the loop text; the absence is the finding).
- **Eligibility filters:** skip if already added (vfAlreadyAdded), skip coinbases, skip non-final transactions (IsFinal, main.h line 398: locktime and sequence based).
- **Admission test:** ConnectInputs against a scratch copy of the test pool (section 8), which enforces input existence (in the database, in already-selected block transactions through the test pool, or in the mempool for the CDiskTxPos(1,1,1) sentinel case at ConnectInputs lines 797 to 812), signature validity, no double spend within the selected set, coinbase maturity (COINBASE_MATURITY = 100, enforced at ConnectInputs lines 828 to 832), and the fee floor.
- **Dependency handling:** repeated full sweeps until a sweep adds nothing, so children can follow parents selected in an earlier sweep.
- **Size limit:** the loop stops adding when nBlockSize reaches MAX_SIZE/2 (line 2245), i.e. 16 MB of serialized transactions, half the MAX_SIZE = 0x02000000 block size ceiling (main.h line 17). nBlockSize accumulates SER_NETWORK sizes of added transactions only; it does not include the coinbase (added before the loop) or header overhead. There is no weight concept and no transaction count limit in the code.
- **No eviction or reservation:** transactions not selected simply remain in mapTransactions for the next template.

## 10. Differences from the modern design that must not be blurred

Against research/bitcoin_core/ (the v28.1 audit in this repository): the modern system separates the mempool (with fee-ordered selection in the block assembler), pays the coinbase to script forms derived from addresses, includes the block height in the coinbase (BIP34), and assembles blocks through getblocktemplate and a dedicated miner interface. None of that exists here. In v0.1.3 the miner, the mempool, selection and the coinbase are one function and two global maps; the reward key is a raw public key in a P2PK output; the coinbase scriptSig is nBits plus a local CBigNum counter; and the subsidy era is read off the global best height. Every statement in this document is about the 2009 code only.
