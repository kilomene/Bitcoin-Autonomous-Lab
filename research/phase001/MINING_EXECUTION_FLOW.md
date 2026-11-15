# Phase 001, Deliverable 3: Original Mining Execution Flow

Project: NOVA SHA-X, Research Phase 001. Subject: the Bitcoin v0.1.3 CPU miner exactly as coded in the verified tree (SOURCE_INVENTORY.md). All line numbers cite `src/main.cpp` unless another file is named. "Proven" means the cited source was read in this session. No benchmarks were run; performance statements are structural (what the code recomputes), not measured.

## 1. Where the miner lives

There is no mining module. The miner is one function, `bool BitcoinMiner()` at src/main.cpp line 2183, in the file that also contains chain validation, the mempool and the wallet glue, preceded by two helper functions written only for it:

- `int FormatHashBlocks(void* pbuffer, unsigned int len)`, line 2138: SHA-256 padding, applied once per buffer before the search.
- `void BlockSHA256(const void* pin, unsigned int nBlocks, void* pout)`, line 2156: a whole-message SHA-256 built directly on the Crypto++ single-block transform, because the search needs to hash pre-padded buffers block by block.

The thread host is `ThreadBitcoinMiner(void* parg)` at src/net.cpp line 894. The comment on line 893 is part of the record: "todo: start one thread per processor, use getenv("NUMBER_OF_PROCESSORS")". Mining in v0.1.3 is single-threaded; parallel mining was a noted intention, not an implementation (proven).

## 2. Thread start and lifetime

1. Start sites: application startup, src/ui.cpp lines 3039 to 3041 (`if (fGenerateBitcoins) _beginthread(ThreadBitcoinMiner, 0, NULL)`), and the menu toggle `CMainFrame::OnMenuOptionsGenerate`, src/ui.cpp lines 821 to 829, which sets the global `fGenerateBitcoins` (src/main.cpp line 49), persists it as a wallet setting, and starts a new thread when toggled on.
2. ThreadBitcoinMiner (net.cpp lines 894 to 906) sets vfThreadRunning[3], calls CheckForShutdown(3), then calls BitcoinMiner() inside the project's exception-catching macro and prints its return value.
3. BitcoinMiner's first actions (lines 2185 to 2191): print "BitcoinMiner started", `SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_LOWEST)`, create a fresh `CKey key` and `key.MakeNewKey()`, set `CBigNum bnExtraNonce = 0`, and enter the outer loop `while (fGenerateBitcoins)`.
4. Termination: the function returns true when the outer loop condition fails (generation toggled off) or false early if block allocation fails (line 2226) or saving the coinbase key fails (line 2330). Shutdown is cooperative: CheckForShutdown(3) (net.cpp line 1059) ends the thread outright if fShutdown is set; the miner calls it at lines 2194, 2198 and 2346. Note the asymmetry: toggling generation off is only observed at the outer loop head and in the inner loop's periodic housekeeping (line 2353), so a search in progress can run up to one housekeeping interval (262,144 hashes, section 6) before noticing.

## 3. Outer loop: one iteration builds one candidate block

Each pass of the outer while loop (lines 2191 to 2362) does the following, in order.

### 3.1 Wait for the network (lines 2193 to 2199)

```
        Sleep(50);
        CheckForShutdown(3);
        while (vNodes.empty())
        {
            Sleep(1000);
            CheckForShutdown(3);
        }
```

The miner refuses to mine with zero connected peers: it sleeps in one-second steps until `vNodes` (the global peer vector, src/net.h line 420) is non-empty. Proven. This is a policy choice visible only here; nothing else in the version gates mining on connectivity.

### 3.2 Snapshot the work context (lines 2201 to 2203)

```
        unsigned int nTransactionsUpdatedLast = nTransactionsUpdated;
        CBlockIndex* pindexPrev = pindexBest;
        unsigned int nBits = GetNextWorkRequired(pindexPrev);
```

- `nTransactionsUpdatedLast` records the mempool change counter for the staleness check in the search loop.
- `pindexPrev` is the current best tip (a raw pointer into mapBlockIndex; read without a lock).
- `nBits` comes from `GetNextWorkRequired` (line 685): the previous block's nBits unless the height is a retarget boundary, in which case the two-week timespan rule with factor-of-4 clamping applies, and the result is clamped to bnProofOfWorkLimit (lines 719 to 720). For the genesis parent (NULL) it returns the limit's compact form (lines 691 to 692).

### 3.3 Build the coinbase transaction (lines 2209 to 2216)

```
        CTransaction txNew;
        txNew.vin.resize(1);
        txNew.vin[0].prevout.SetNull();
        txNew.vin[0].scriptSig << nBits << ++bnExtraNonce;
        txNew.vout.resize(1);
        txNew.vout[0].scriptPubKey << key.GetPubKey() << OP_CHECKSIG;
```

- One input with a null prevout (the coinbase marker, COutPoint with hash 0 and n = UINT_MAX; COutPoint::SetNull at src/main.h line 156, IsCoinBase test at main.h line 437).
- scriptSig is exactly two pushes: the block's nBits (as an unsigned int, so CScript::push_uint64, src/script.h lines 340 to 356: for 0x1d00ffff this becomes the CBigNum byte-vector push `04 ffff001d`) and the pre-incremented extranonce (`++bnExtraNonce`, a CBigNum push of its little-endian getvch() bytes; the first candidate of a miner run uses extranonce 1, encoded as the single byte OP_1 = 0x51 by the small-value rule in push_int64/push_uint64 via operator<<(const CBigNum&) at script.h line 437; the encoding rule is proven from script.h, the byte value for extranonce 1 is our derivation from it).
- One output whose scriptPubKey is a push of the 65-byte public key of the run's CKey followed by OP_CHECKSIG. The output value is not set here; it is filled in after transaction collection (section 3.5).
- Full analysis in TRANSACTION_RECONSTRUCTION.md and COINBASE_MERKLE_ANALYSIS.md.

### 3.4 Collect transactions from the mempool (lines 2222 to 2265)

The block object is allocated (`auto_ptr<CBlock> pblock`), the coinbase is pushed as vtx[0], and then, holding cs_main and cs_mapTransactions, the miner repeatedly sweeps the whole mempool map until a full sweep adds nothing or the block reaches MAX_SIZE/2 bytes:

```
            while (fFoundSomething && nBlockSize < MAX_SIZE/2)
            {
                fFoundSomething = false;
                unsigned int n = 0;
                for (map<uint256, CTransaction>::iterator mi = mapTransactions.begin(); mi != mapTransactions.end(); ++mi, ++n)
                {
                    if (vfAlreadyAdded[n])
                        continue;
                    CTransaction& tx = (*mi).second;
                    if (tx.IsCoinBase() || !tx.IsFinal())
                        continue;
                    int64 nMinFee = tx.GetMinFee(pblock->vtx.size() < 100);
                    map<uint256, CTxIndex> mapTestPoolTmp(mapTestPool);
                    if (!tx.ConnectInputs(txdb, mapTestPoolTmp, CDiskTxPos(1,1,1), 0, nFees, false, true, nMinFee))
                        continue;
                    swap(mapTestPool, mapTestPoolTmp);
                    pblock->vtx.push_back(tx);
                    ...
                }
            }
```

Structural facts (proven): iteration order is `std::map<uint256, CTransaction>` order, i.e. by transaction hash, not by fee or arrival. A candidate transaction is admitted only if `ConnectInputs` (line 772, called with fBlock=false, fMiner=true) succeeds against a scratch copy of the test pool: inputs must exist, signatures must verify, no input may already be spent in the test pool, coinbase inputs must be mature, and the transaction's fee (inputs minus outputs, accumulated into the shared `nFees` at lines 848 to 855) must reach `tx.GetMinFee(...)`, where the discount flag makes the first 100 block transactions effectively free under 10 KB (comment at lines 2248 to 2250, GetMinFee at main.h line 504). The repeated sweeps exist so that a transaction whose parent is also in the mempool can be admitted on a later pass once the parent is in the test pool. Each admitted transaction costs a full copy of mapTestPool (the Tmp copy per candidate at line 2256), a real inefficiency visible in the source. `vfAlreadyAdded` is a parallel vector<char> indexed by sweep position.

### 3.5 Fix the coinbase value and the header fields (lines 2266 to 2300)

```
        pblock->nBits = nBits;
        pblock->vtx[0].vout[0].nValue = pblock->GetBlockValue(nFees);
```

GetBlockValue (line 675) returns subsidy plus accumulated fees; subsidy is 50 * COIN shifted right by (nBestHeight / 210000) (lines 677 to 681; note it reads the global nBestHeight, the height of the current best tip, not the new block's height).

Then the hash buffer is prebuilt (section 4): the miner copies the header fields into a local struct, simultaneously assigning them into pblock: hashPrevBlock from pindexPrev->GetBlockHash() (line 2293), hashMerkleRoot from pblock->BuildMerkleTree() (line 2294, so the merkle tree is computed exactly once per candidate block, after all transactions are final), nTime = max(pindexPrev->GetMedianTimePast() + 1, GetAdjustedTime()) (line 2295), nBits (line 2296), and nNonce = 1 (line 2297). The nonce starts at 1, not 0 (proven).

## 4. The prebuilt hash buffer: layout and padding

Lines 2274 to 2300 define the working layout, an anonymous struct local to BitcoinMiner:

```
        struct unnamed1
        {
            struct unnamed2
            {
                int nVersion;
                uint256 hashPrevBlock;
                uint256 hashMerkleRoot;
                unsigned int nTime;
                unsigned int nBits;
                unsigned int nNonce;
            }
            block;
            unsigned char pchPadding0[64];
            uint256 hash1;
            unsigned char pchPadding1[64];
        }
        tmp;
```

Byte map of `tmp` (offsets from &tmp; sizes are exact on this platform because every member is 4-byte aligned and uint256 is 32 bytes):

| Offset | Size | Contents |
|--------|------|----------|
| 0 | 4 | block.nVersion |
| 4 | 32 | block.hashPrevBlock (uint256 raw memory order) |
| 36 | 32 | block.hashMerkleRoot (uint256 raw memory order) |
| 68 | 4 | block.nTime |
| 72 | 4 | block.nBits |
| 76 | 4 | block.nNonce |
| 80 | 64 | pchPadding0: scratch space for the first hash's padding |
| 144 | 32 | hash1: the first SHA-256 output, in uint256 memory order |
| 176 | 64 | pchPadding1: scratch space for the second hash's padding |

The first 80 bytes are layout-identical to the CBlock header serialization (same field order as CBlock::Serialize, src/main.h line 828; the miner relies on this identity, and proves it at runtime with the assert in section 7).

Padding is computed once, before the search (lines 2299 to 2300):

```
        unsigned int nBlocks0 = FormatHashBlocks(&tmp.block, sizeof(tmp.block));
        unsigned int nBlocks1 = FormatHashBlocks(&tmp.hash1, sizeof(tmp.hash1));
```

FormatHashBlocks (lines 2138 to 2151) takes a buffer and a length, computes `blocks = 1 + ((len + 8) / 64)`, zeroes from len to the end of the padded region, writes 0x80 at pdata[len], and writes the bit length big-endian into the last four bytes of the padded region. For the header (len 80): nBlocks0 = 2, padded size 128 bytes, occupying tmp offsets 0 to 127 (the 80 header bytes plus 48 bytes into pchPadding0). For hash1 (len 32): nBlocks1 = 1, padded size 64 bytes, occupying tmp offsets 144 to 207 (hash1 plus 32 bytes of pchPadding1). Two details worth recording: only four length bytes are written (pend[-1] to pend[-4]); the high four bytes of the SHA-256 64-bit length field are left as the memset zeros, which is correct for these short inputs but makes FormatHashBlocks a short-message specialisation, not a general padding routine. And the padding bytes are written into the struct's scratch arrays, which is why the struct carries 64 spare bytes after each hashed region.

This is the version's midstate arrangement, stated precisely: the padding and block framing are precomputed once per candidate block, but no compression state is precomputed. Every candidate still runs both hashes from the initial state (section 5). Calling this a midstate optimisation would be wrong; it is a padding precomputation.

## 5. The hash primitive used by the search: BlockSHA256

Lines 2156 to 2180:

```
void BlockSHA256(const void* pin, unsigned int nBlocks, void* pout)
{
    unsigned int* pinput = (unsigned int*)pin;
    unsigned int* pstate = (unsigned int*)pout;

    CryptoPP::SHA256::InitState(pstate);

    if (*(char*)&detectlittleendian != 0)
    {
        for (int n = 0; n < nBlocks; n++)
        {
            unsigned int pbuf[16];
            for (int i = 0; i < 16; i++)
                pbuf[i] = ByteReverse(pinput[n * 16 + i]);
            CryptoPP::SHA256::Transform(pstate, pbuf);
        }
        for (int i = 0; i < 8; i++)
            pstate[i] = ByteReverse(pstate[i]);
    }
    else
    {
        for (int n = 0; n < nBlocks; n++)
            CryptoPP::SHA256::Transform(pstate, pinput + n * 16);
    }
}
```

Facts, all proven from this excerpt and sha.h/sha.cpp:

- The state is re-initialised on every call (InitState, sha.cpp line 93). Nothing is carried between candidates.
- On little-endian hosts (the branch taken on x86), every input word is byte-reversed into a stack buffer before Transform, because the in-memory buffers hold little-endian words while SHA-256 consumes big-endian words. That is 16 byte-reversals per 64-byte block, repeated for every block of every candidate.
- After the last block, the eight state words are byte-reversed back (lines 2172 to 2173), converting the digest into the little-endian-limb memory layout of uint256, so the result can be compared and stored as a uint256 without further conversion. This is why the miner's `hash` and `hash1` are directly uint256-comparable.
- Transform itself (sha.cpp line 141) is the Crypto++ compression: a 16-word rolling message schedule and 64 partially unrolled rounds. It processes exactly one block per call.
- Endianness is detected at runtime from a static int (`detectlittleendian`, line 2154) rather than at compile time.

## 6. The search loop

Lines 2305 to 2361. Setup (lines 2305 to 2308): `nStart = GetTime()`, and the target is decoded once per candidate block:

```
        uint256 hashTarget = CBigNum().SetCompact(pblock->nBits).getuint256();
```

(SetCompact at src/bignum.h line 257 decodes the compact nBits through OpenSSL's MPI format; getuint256 converts to the fixed-width type. The comparison that follows is the uint256 limb comparison, operator<= at src/uint256.h line 226, most significant limb first. No floating point is involved anywhere in the search or the target path.)

The loop itself (`loop` is the project's macro for `for (;;)`, src/util.h line 22):

```
        loop
        {
            BlockSHA256(&tmp.block, nBlocks0, &tmp.hash1);
            BlockSHA256(&tmp.hash1, nBlocks1, &hash);


            if (hash <= hashTarget)
            {
                ... success, section 7 ...
                break;
            }

            // Update nTime every few seconds
            if ((++tmp.block.nNonce & 0x3ffff) == 0)
            {
                CheckForShutdown(3);
                if (tmp.block.nNonce == 0)
                    break;
                if (pindexPrev != pindexBest)
                    break;
                if (nTransactionsUpdated != nTransactionsUpdatedLast && GetTime() - nStart > 60)
                    break;
                if (!fGenerateBitcoins)
                    break;
                tmp.block.nTime = pblock->nTime = max(pindexPrev->GetMedianTimePast()+1, GetAdjustedTime());
            }
        }
```

Exact mechanics, proven from the excerpt:

1. **Hash.** Two BlockSHA256 calls per candidate: the first over the 2 padded blocks of the header buffer, writing the intermediate digest into tmp.hash1 (overwriting the previous candidate's value in place; its padding in pchPadding1 is untouched by the write because only 32 bytes are written); the second over the 1 padded block of hash1, writing the final digest to the local `hash`.
2. **Compare.** `if (hash <= hashTarget)`: equality passes. This is the complete proof-of-work test in the miner, a single unsigned 256-bit comparison.
3. **Increment.** The nonce is incremented as a side effect of the housekeeping test, `++tmp.block.nNonce`, executed once per unsuccessful candidate. The nonce lives at tmp offset 76, the last four bytes of the header's second block.
4. **Housekeeping gate.** The body under the test runs only when the incremented nonce is a multiple of 0x40000 (262,144), because the mask is 0x3ffff. Between gates, the loop is exactly: two hashes, one compare, one increment, one mask test. There is no per-candidate check of shutdown, tip movement, mempool change, or the generation flag.
5. **Housekeeping actions, in order:** CheckForShutdown(3); break if the nonce wrapped to 0 (the full 2^32 space for this template is exhausted; the outer loop will rebuild with the next extranonce); break if pindexBest moved (a new tip arrived); break if the mempool changed (nTransactionsUpdated differs) and this template is more than 60 seconds old; break if generation was toggled off; otherwise refresh nTime in both tmp.block and pblock to max(median time past of the snapshot tip plus 1, adjusted time). Note the refreshed nTime is written into the already-padded buffer without re-running FormatHashBlocks, which is correct because nTime sits inside the 80 hashed bytes and the padding depends only on length. Note also that the refresh dereferences pindexPrev without a null check (line 2355), safe only because the loop is unreachable with a null tip in practice (mining waits for peers, and a peer implies a chain); recorded as a latent sharp edge, not an observed failure.

### 6.1 Restart conditions (complete list)

The inner loop exits, returning to the outer loop which rebuilds the candidate from scratch (new coinbase with the next extranonce, new transaction sweep, new merkle root, new padding), when any of these occurs: success (section 7, after processing the block); nonce wrap to 0; best tip changed; mempool changed and template older than 60 seconds; generation toggled off; shutdown requested (via CheckForShutdown ending the thread). There is no other exit. In particular, a changed mempool does not restart a template younger than 60 seconds, and a changed tip restarts immediately but only at the next 262,144-hash gate.

### 6.2 Repeated computations inside the loop, identified from source

Per candidate, the loop recomputes all of the following, none of which depends on the nonce:

1. **The entire first 64-byte block compression of the header hash.** Header bytes 0 to 63 (version, previous hash, and the first 28 bytes of the merkle root) never change during a template's life, yet BlockSHA256 starts from InitState and processes block 0 on every call (main.cpp lines 2161 to 2170). One of the three total block compressions per candidate (two for the header, one for hash1) is therefore over invariant data. This is the single largest structural redundancy in the loop, and it is exactly the computation a carried midstate would eliminate; v0.1.3 does not carry one.
2. **Most of the second header block.** Of header bytes 64 to 79, only nTime (68 to 71) and nNonce (76 to 79) can change; the merkle root tail (64 to 67), nBits (72 to 75) and all 48 padding bytes are invariant, but the block is re-transformed in full per candidate (necessarily so once the nonce is inside it, but the schedule words for the invariant prefix are recomputed as part of it).
3. **All byte-reversal work.** 48 word byte-reversals for input (3 blocks times 16 words) plus 8 for output state per candidate on the little-endian path (lines 2165 to 2173), including for the invariant block 0.
4. **State initialisation.** InitState's 32-byte copy runs twice per candidate (once per BlockSHA256 call), and the second call's input block (hash1 plus its padding) is re-formed from the fresh hash1 each time.
5. **The assert re-hash, on success only.** When a candidate passes, `assert(hash == pblock->GetHash())` (line 2318) recomputes the whole double hash through the OpenSSL path; in a release build with NDEBUG this disappears, in a debug build it is a full extra SHA-256d per found block (negligible, and it doubles as a cross-implementation check, section 7).

Outside the loop but per template, also repeated: BuildMerkleTree recomputes every leaf transaction hash from serialization (tx.GetHash() per transaction, main.h line 872) even though mapTransactions is keyed by those same hashes; the miner does not reuse the map keys. And per outer iteration, the coinbase, the full mempool sweep with its per-candidate mapTestPool copies (section 3.4), and both FormatHashBlocks paddings are redone even when only the extranonce changed.

## 7. Success handling: what happens when a candidate passes

Lines 2315 to 2341:

```
            if (hash <= hashTarget)
            {
                pblock->nNonce = tmp.block.nNonce;
                assert(hash == pblock->GetHash());
                printf("BitcoinMiner:\n");
                printf("proof-of-work found  \n  hash: %s  \ntarget: %s\n", ...);
                pblock->print();
                SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_NORMAL);
                CRITICAL_BLOCK(cs_main)
                {
                    // Save key
                    if (!AddKey(key))
                        return false;
                    key.MakeNewKey();
                    // Process this block the same as if we had received it from another node
                    if (!ProcessBlock(NULL, pblock.release()))
                        printf("ERROR in BitcoinMiner, ProcessBlock, block not accepted\n");
                }
                SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_LOWEST);
                Sleep(500);
                break;
            }
```

Step by step:

1. The winning nonce is copied from the scratch buffer into the block object (line 2317). Every other header field was already assigned into pblock during prebuild (lines 2292 to 2297), so pblock is now the complete candidate.
2. The assert cross-checks the miner's Crypto++ result against `CBlock::GetHash()` (src/main.h line 862), which is the OpenSSL double SHA-256 over the serialized header. Two independent SHA-256 implementations agreeing on the winning candidate is therefore verified in debug builds at the moment it matters most (proven from source; whether the shipped bitcoin.exe was built with asserts enabled is not recorded in the tree and is stated here as unknown).
3. The thread priority is raised to normal, cs_main is taken, and the coinbase key is saved to the wallet with `AddKey(key)` (line 2329; AddKey itself is at main.cpp line 65 and persists the key through CWalletDB) so the block reward is spendable by this wallet. A fresh key is then generated for the next candidate (line 2331). Note the ordering consequence: the key that received this block's reward is only persisted on success; a key whose mining was abandoned is never saved (its would-be rewards were never earned, so nothing is lost; inferred from the single AddKey call site in the miner).
4. The block is submitted through the exact path a network-received block takes: `ProcessBlock(NULL, pblock.release())` (line 2334), NULL marking it as locally generated. ProcessBlock (line 1236) runs CheckBlock (line 1154: size limits, timestamp not more than two hours in the future, first transaction coinbase and only one, per-transaction CheckTransaction, the proof-of-work checks at lines 1180 to 1184, namely SetCompact(nBits) must not exceed bnProofOfWorkLimit and GetHash() must not exceed the decoded target, and merkle root must equal BuildMerkleTree()), then AcceptBlock (line 1192: duplicate and previous-block presence, timestamp after the median time past, nBits must equal GetNextWorkRequired(pindexPrev) exactly at line 1210, write to the blk file, AddToBlockIndex, which connects it and reorganizes if it becomes the best chain), and finally, inside AcceptBlock at line 1222, `if (hashBestChain == hash) RelayInventory(CInv(MSG_BLOCK, hash))` advertises the new block to all peers (net.h line 766). ProcessBlock also recursively accepts any orphans that were waiting on this block (lines 1273 to 1292).
5. Priority is restored to lowest, the miner sleeps 500 ms, and the inner loop breaks; the outer loop builds the next candidate on the new tip with the next extranonce and a fresh key.

There is no separate submission, signing, or announcement step: ProcessBlock is the whole of it, and a mined block that fails CheckBlock or AcceptBlock is dropped with only a printf (line 2335). The miner does not retry or adjust in that case.

## 8. The loop's exact structure, in a few lines

One thread. Per candidate block: build coinbase (nBits and an incrementing extranonce in scriptSig, fresh key in the output), sweep the mempool by hash order admitting transactions that pass ConnectInputs against a scratch test pool, set the coinbase value to subsidy (50 BTC halving every 210,000 blocks of best height) plus fees, compute the merkle root once, copy the 80-byte header into a scratch struct with room for padding, pad both hash buffers once. Per nonce: SHA-256d the padded header (2 blocks) then the padded first hash (1 block), both from the initial state, byte-reversing all words in and out; accept if hash <= target decoded from nBits; increment the nonce; every 262,144 increments, check shutdown, wrap, tip change, stale mempool, and the generation flag, and refresh nTime. On success: save the key, hand the block to ProcessBlock, which validates, stores, connects and relays it exactly as if it had arrived from a peer.
