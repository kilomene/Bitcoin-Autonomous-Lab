# Phase 001, Deliverable 13: Original Nonce Search Analysis

Project: NOVA SHA-X, Research Phase 001, Wave 4.
Subject: the v0.1.3 nonce search treated as a formal object: its exact traversal, its coverage, its duplicate structure and its stale-work conditions. All mechanics are from the verified tree (src/main.cpp, BitcoinMiner, lines 2183 to 2362), as reconstructed in MINING_EXECUTION_FLOW.md and POW_TARGET_MATHEMATICS.md section 9. Coverage claims marked PROVEN are additionally executed in RAW_RESULTS/phase001_verification.py (Deliverable 19). No benchmarks were run.

## 1. The search as a formal object

A search instance (one template) is fully described by the tuple:

```
(template) = (nVersion=1, hashPrevBlock, hashMerkleRoot, nBits, key, extranonce)
```

where hashMerkleRoot is itself a function of the transaction list and of the coinbase, and the coinbase is a function of (nBits, extranonce, key). The search variable is the single 32-bit field nNonce at header offset 76. nTime is a secondary, slow variable refreshed only at housekeeping gates (section 3). Everything else in the 80-byte header is fixed for the life of the template (BLOCK_HEADER_SPECIFICATION.md section 5).

The traversal is a deterministic sequential scan, defined by three source facts:

1. Initialisation: `tmp.block.nNonce = 1` (line 2297). The first candidate hashed carries nonce 1.
2. Step: after each unsuccessful hash, the statement `(++tmp.block.nNonce & 0x3ffff) == 0` (line 2344) pre-increments the nonce. The next candidate hashed is the incremented value.
3. Termination of the template: when the incremented value is exactly 0 (the increment after nonce 0xffffffff was hashed), the gate body breaks out of the loop (lines 2347 to 2348).

## 2. Exact coverage per template

Consequence of the three facts, stated exactly:

- The set of nonces hashed for one template is precisely {1, 2, ..., 0xffffffff}.
- Its size is 2^32 - 1 = 4,294,967,295 candidates.
- Nonce 0 is never hashed. It exists in the field's range and in the loop's counter, but it is only ever reached as the post-increment value that triggers the break, never as a hashed candidate.
- The order is strictly increasing with no gaps and no repeats inside one template: the scan is a permutation-free enumeration of the set above, in order.

PROVEN status: the count and the exclusion of 0 are arithmetic consequences of the cited lines; Deliverable 19 executes them three ways (direct identity, gate-count identity, and a width-reduced executable model of the same control flow at 8 and 12 bits, where the enumeration is checked element by element: 255 and 4,095 candidates respectively, nonce 0 never hashed).

## 3. Housekeeping: the 262,144 gate

The increment statement doubles as the loop's only scheduling point. The gate body runs when the incremented nonce is a multiple of 2^18 = 262,144 (mask 0x3ffff). Per full template traversal the gate executes exactly 16,384 times: at incremented nonces 262,144, 524,288, ..., 4,294,705,920 (16,383 times) plus the final wrap to 0 (the 16,384th). Between gates the loop body is exactly: two BlockSHA256 calls, one comparison, one increment, one mask test (MINING_EXECUTION_FLOW.md section 6).

At each gate, in source order (lines 2345 to 2355):

1. `CheckForShutdown(3)`: ends the thread outright if shutdown was requested.
2. Wrap test: nonce == 0 breaks (template exhausted).
3. Tip test: `pindexPrev != pindexBest` breaks (a new best tip arrived; the template's previous hash is stale).
4. Mempool test: `nTransactionsUpdated != nTransactionsUpdatedLast && GetTime() - nStart > 60` breaks (the mempool changed AND this template has been running more than 60 seconds).
5. Generation flag: `!fGenerateBitcoins` breaks (user toggled mining off).
6. Otherwise nTime is refreshed in both the scratch buffer and the block object: `max(pindexPrev->GetMedianTimePast()+1, GetAdjustedTime())`.

Two timing consequences follow arithmetically, stated as structure, not measurement: external events (tip change, shutdown, toggle off) are observed with a latency of up to one gate interval, i.e. up to 262,144 hashes of stale or unwanted work; and the nTime refresh quantizes template time to gate boundaries, so a template's hashed nTime values form a step function over its life, not a continuum.

## 4. The extranonce rebuild path and total coverage

Template exhaustion (wrap), and every other break condition, returns control to the outer loop, which rebuilds the candidate from scratch (MINING_EXECUTION_FLOW.md section 6.1). The rebuild:

- pre-increments the miner-local CBigNum `bnExtraNonce` (declared line 2190, starts at 0, so the first template of a run carries extranonce 1) and pushes it as the second item of the new coinbase scriptSig, after nBits (line 2212);
- re-collects transactions, recomputes the merkle root, re-pads both hash buffers, resets the nonce to 1.

Total coverage of a miner run is therefore a product space:

```
candidates(run) = (2^32 - 1) x (number of distinct templates built)
```

and for E distinct extranonce values actually used, coverage = (2^32 - 1) x E distinct headers, provided the templates are otherwise identical. The qualification matters: templates built after a tip change or a mempool-driven rebuild differ in hashPrevBlock or hashMerkleRoot independently of the extranonce, so the run's total distinct-header count is the sum over templates of (nonces actually hashed per template), each template contributing a disjoint header set as long as its (hashPrevBlock, hashMerkleRoot, nBits, nTime-history) tuple differs from every other template's. The extranonce guarantees the merkle root component differs between consecutive templates on the same tip and transaction set, which is exactly the exhaustion-escape it exists for. Because bnExtraNonce is an arbitrary-precision CBigNum with a minimal-length encoding, E is not bounded by the field width; it is bounded in practice by the coinbase scriptSig length rule (2 to 100 bytes, main.h lines 456 to 459), which the counter reaches only after an astronomically large number of templates. The encoding length growth also means consecutive templates do not have identical coinbase lengths; the txid changes both by value and, at byte-width crossings, by length.

## 5. Duplicate-work analysis (precise)

The miner is a single thread (ARCHITECTURE_MAP.md section 4), so the duplicate analysis has no concurrency case. Duplicates can arise only across template rebuilds. There are exactly three overlap mechanisms, and they have different statuses:

1. **Nonce overlap across templates is not duplicate work.** Two templates sharing a nonce value hash different headers whenever any other header byte differs. A rebuild triggered by wrap always changes the extranonce, hence the coinbase, hence the merkle root: zero repeated headers. A rebuild triggered by a tip change changes hashPrevBlock: zero repeated headers. A rebuild triggered by the mempool test changes the transaction set (that is its trigger), hence the merkle root: zero repeated headers. A rebuild triggered by toggling generation off and on restarts the miner function with bnExtraNonce reset to 0 and a fresh key (lines 2189 to 2190): the fresh coinbase key changes the coinbase output script, hence the txid and merkle root: zero repeated headers. In every reachable rebuild path, at least one non-nonce header input changes, so the same 80-byte header is never hashed twice by this program. PROVEN from the rebuild paths enumerated in MINING_EXECUTION_FLOW.md section 6.1, with one stated assumption: the fresh CKey after a restart produces a different public key than the previous run's key (overwhelmingly true for a random key, and the only path on which the argument rests on probability rather than code structure).

2. **Repeated computation inside one candidate is not duplicate candidates, but it is repeated work.** Per candidate, the loop recomputes the template-constant first chunk compression (64 of 192 rounds), the invariant schedule prefix of chunk 2, all 56 word byte-reversals, and both state initialisations (Deliverable 11, section 5; MINING_EXECUTION_FLOW.md section 6.2). This is redundancy within the evaluation of distinct candidates, counted as wasted rounds, not as duplicate coverage. The distinction is the one the Master Assignment's accounting rules require: coverage counts distinct headers; cost counts rounds actually executed. The 0.1.3 search has perfect coverage hygiene and poor round economy, simultaneously.

3. **The nTime refresh creates a subtle non-duplicate.** When the gate refreshes nTime, the scan continues from the current nonce under a new nTime; nonces already scanned under the old nTime are not rescanned under the new one. No duplicate arises (the headers differ by nTime), but the converse gap does: for each nTime epoch within a template, only a suffix or prefix segment of the nonce range is covered under that nTime. Coverage of the (nonce x nTime) product space is a diagonal band, not a rectangle. This is inherent to the sequential design and is recorded because any formal coverage claim for this search must be stated per (template, nTime epoch), not per template alone. The Deliverable 19 loop model abstracts nTime away; the per-template count of section 2 counts hashed candidates, which is exact regardless of how the nTime epochs partition them.

One further boundary case: on success the winning nonce is copied into the block and the loop breaks (line 2317); the assert re-hash (line 2318) recomputes the same header once more through the OpenSSL path. That is a verification computation, one extra SHA-256d per found block, never counted as search work here.

## 6. Stale-work conditions

Work is stale when the header being scanned can no longer produce an acceptable block. The conditions, with the loop's response latency:

| Condition | Why the work is stale | Detected | Response |
|---|---|---|---|
| New best tip (pindexBest moves) | hashPrevBlock no longer the tip; AcceptBlock would still accept a sibling block in principle, but the miner's design treats tip movement as a rebuild trigger | Next gate only (up to 262,144 hashes late) | Break, rebuild on new tip |
| Mempool changed, template older than 60 s | The template omits newer transactions (an opportunity cost, not invalidity: the block would still be valid) | Next gate, and only if the 60 s age test also passes | Break, rebuild with fresh sweep |
| Mempool changed, template younger than 60 s | Same as above | Deliberately ignored | Search continues; the design accepts up to 60 s of mempool staleness unconditionally |
| Generation toggled off | Work unwanted by the operator | Next gate | Break, outer loop exits |
| Shutdown requested | Process ending | At gate via CheckForShutdown(3), which terminates the thread | Thread ends |
| nTime drift | nTime is refreshed to adjusted time at gates; a long template does not go stale on time because AcceptBlock's median-past rule moves slowly and CheckBlock's 2-hour future bound is loose | Continuous refresh | nTime updated in place |

The structural summary: staleness is polled, not signalled, and the poll interval is denominated in hashes (262,144), so the wall-clock staleness bound shrinks as the machine gets faster. At 2009 speeds a gate interval was a substantial fraction of a second to seconds; the same code on a modern CPU would poll thousands of times per second. The design's staleness behaviour is therefore speed-dependent in a way its author could not have intended as a constant; recorded as an analysis observation, not a defect claim.

## 7. What the search does not do

Proven absences, each a design fact for later phases: no nonce partitioning (one thread owns the whole range); no random starting nonce (always 1); no nonce skipping or stride; no mid-search extranonce or merkle mutation (the coinbase is frozen per template); no work identity or coverage record (nothing is logged per template; coverage must be reconstructed from the code, as here); no resumption (a stopped miner restarts its current template's scan from nonce 1 under a new extranonce, losing the partial scan, which is safe only because the new template's headers are all distinct).

## 8. Reproduction

Source: src/main.cpp lines 2183 to 2362 in the verified tree. Executable checks: RAW_RESULTS/phase001_verification.py sections 6 and 7 (candidate count, gate count, width-reduced loop model). Prior reconstruction: MINING_EXECUTION_FLOW.md sections 3 to 6; POW_TARGET_MATHEMATICS.md section 9.

## 9. Limitations

- The no-duplicate-headers result (section 5, item 1) is a source-level argument over the enumerated rebuild paths; it assumes the fresh-key distinctness noted there and does not cover two separately started client processes mining with the same wallet, which the single-instance guard (ARCHITECTURE_MAP.md section 3) exists to prevent.
- Coverage is stated for the search as coded; whether any historical run actually exhausted a full template space is a historical question this phase does not investigate.
