# Merkle and Transaction Mathematics

Stage 1 of the NOVA SHA-X Extreme Research mandate. This
document consolidates the transaction hashing pipeline: what
is hashed, in which serialization, what may be cached, and
the exact rule that invalidates each cached value. Points
already proven in the existing record are cited and
summarized, not re-derived. The worked recomputations were
executed by `tools/header_reconstruction.py` during Stage 1
and are recorded in BLOCK_HEADER_RECONSTRUCTION.md.

## 1. TXID and WTXID

For a transaction with serialization X:

- TXID = SHA-256d(X_non_witness): the serialization with the
  SegWit marker, flag and witness stacks removed (version,
  inputs without witness, outputs, locktime).
- WTXID = SHA-256d(X_full): the complete serialization
  including marker, flag and witnesses. For a legacy
  transaction the two serializations are identical, so
  TXID = WTXID.

Both are 32-byte digests in internal byte order; the display
form reverses the bytes. The block header's Merkle root is
built over TXIDs only. WTXIDs feed exactly one thing: the
witness Merkle tree behind the witness commitment (section
4). Confusing the two trees is a real defect class: EXP-034
found and fixed the lab's solo server locating the extranonce
split in the full coinbase and applying it to the stripped
coinbase, a 2-byte offset corruption on every SegWit template
(research/sha256d/exp034/JOB_TEMPLATE_ENGINE.md).

## 2. Coinbase serialization and extranonce placement

The coinbase is the first transaction. Its single input has a
null prevout (hash 0x00..00, index 0xffffffff). Its scriptSig
carries, in order, the block height push (BIP34), then
miner-chosen bytes. Phase 001 established the original form
in Bitcoin v0.1.3 (research/phase001/
COINBASE_MERKLE_ANALYSIS.md): the miner's scriptSig was
`<< nBits << ++bnExtraNonce`, the extranonce a local counter
pre-incremented per template, never persisted and never in
the header. The coupling chain Phase 001 proved, and which
still governs the modern code, is:

extranonce bytes -> coinbase serialization -> coinbase TXID
-> Merkle root -> header bytes 36 to 67.

Modern placement in this repository:

- The GBT engine (mining/engine.py) builds the coinbase from
  the template; the EXP-034 extranonce space
  extranonce_space=(first, count), default (0, 64), partitions
  which coinbase variants one engine instance may produce,
  and disjoint spaces produce disjoint coinbases (auditor
  verified byte-identical behaviour inside the default space).
- The solo server (mining/solo_server.py) splits the coinbase
  into the part it serves and the part the miner varies
  (extranonce1 / extranonce2 in Stratum terms). After the
  EXP-034 fix, the split offset is located in the STRIPPED
  coinbase (`stripped.index(marker)`, solo_server.py line
  270), so a witness commitment in the template cannot shift
  it.
- The pool path takes the split from the pool's mining.notify
  (coinb1 / coinb2 with the pool's extranonce sizes).

Any change to any coinbase byte changes the coinbase TXID,
which changes exactly one Merkle leaf, which changes the
O(log n) branch nodes on the leftmost path and the root.
Nothing else in the tree is affected.

## 3. Merkle root computation

Given the ordered TXID list L0 (internal byte order):

- If the level has an odd count, duplicate the last node.
- Pair adjacent nodes: parent = SHA-256d(left || right).
- Repeat until one node remains: the Merkle root, stored in
  header bytes 36 to 67 in internal byte order.

Properties that matter for mining:

- The root depends on the tx list's content AND order. Any
  insertion, removal, reordering or edit invalidates it.
- A single-leaf change invalidates only the branch path from
  that leaf to the root; every other branch node is reusable
  verbatim. This is the only incremental Merkle update that
  is ever valid, and it is exactly the coinbase case above.
- The degenerate one-transaction block has root = coinbase
  TXID (genesis: both are
  4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b).

## 4. Witness commitment (BIP141)

When a block contains SegWit transactions, the coinbase
carries an additional output whose script is OP_RETURN,
a 36-byte push, the 4-byte header aa21a9ed, and a 32-byte
commitment:

commitment = SHA-256d(witness_root || reserved_value)

- witness_root is the Merkle root of the WTXID list computed
  exactly as in section 3, except the coinbase leaf is fixed
  at 0x00..00 (the coinbase's own WTXID is never used).
- reserved_value is the single 32-byte item in the coinbase
  input's witness stack.

The commitment binds the witness data into the coinbase TXID
and therefore into the header's Merkle root, without putting
any witness byte into the TXID tree itself.

## 5. Worked recomputations (executed in Stage 1)

### 5.1 Mainnet height 450170: full TXID tree

2,095 transactions parsed from the raw block (998,164 bytes).
The tool computed all 2,095 TXIDs from the stripped
serializations and reduced the tree level by level: 2095,
1048, 524, 262, 131, 66, 33, 17, 9, 5, 3, 2, 1 nodes, with
odd levels duplicating their last node, 2,101 pair hashes in
total. Recomputed root (display):
08ec55c5117cce94c3e0470fee7443472a95db0544ac82e3284d652d8e993d81,
equal to the header field Core served. The same recomputation
matched Core's root at heights 450150 (2,573 tx) and 450160
(931 tx), and for the genesis block.

### 5.2 Regtest height 1491: TXID tree and witness tree

41 transactions, all SegWit serialization. TXID tree root
(display):
ff52dba7035790155745e3ab430f6214b7dccbed7c91a885529cd45526e0bf87,
matching the header. Witness tree over the 41 WTXIDs with
the coinbase leaf fixed at 0x00..00: root (display)
07dd8d90bc4630d38c22bb616dad77d6d6376163d1bd50621d06eae53eeb535b.
SHA-256d of that root concatenated with the coinbase witness
reserved value equals the coinbase commitment
96239308293fdc28e458c4a436f652b049938a1d05a01d0b39f42b3a77f4abfc,
byte for byte. This is the complete BIP141 chain, verified
end to end by the tool (9 of 9 checks on this block).

## 6. Caching and invalidation: the EXP-025 layered identity

EXP-025 (research/sha256d/exp025/, integrated into
mining/engine.py, independently audited) replaced a proven
unsafe prototype cache. Its lesson is the standing rule for
every cache in this pipeline: a cache key must be a complete
identity of everything the cached value depends on, computed
as layered double SHA-256 keys:

- family_key: payout address, scriptPubKey, chain, halving
  interval. Invalidated by: a payout or chain configuration
  change. Nothing in a template touches it.
- tx_key: transaction count, plus per-transaction (txid,
  wtxid, fee) in order, plus the default witness commitment
  string. Invalidated by: any change to the selected
  transaction set, its order, any fee, or the witness
  commitment Core reports.
- coinbase_key: family_key, height, coinbasevalue,
  coinbaseaux flags, witness commitment and a presence byte.
  Invalidated by: a new height, a value change (subsidy or
  fee total), a flags change, or a commitment change.
- header_key: version, previousblockhash as written, bits,
  target as text. Invalidated by: a new tip, a version
  change, or a difficulty change.

The template identity is the double SHA-256 of the three
subkeys; the cache is bounded at 128 entries, and the
uncached builder (build_candidate_uncached) is preserved as
the fallback. Two deliberate exclusions, recorded as the
accepted design boundary (audit note N-2, re-confirmed
since): mintime and curtime are NOT in the identity; the
steps path reads them live at build time. Any future cache
that covers time must extend the identity first.

Applied to the Merkle layer specifically:

| Cached value | Reusable iff | Invalidated by |
|---|---|---|
| One TXID | the stripped serialization is unchanged | any byte change in the transaction |
| One WTXID | the full serialization is unchanged | any byte change, witness included |
| A Merkle branch node | its entire leaf set is unchanged | any change under it |
| The Merkle root | the ordered TXID list is identical | any tx change, insertion, removal, reorder |
| The witness root | the ordered WTXID list is identical (coinbase leaf fixed) | any witness or tx change |
| A prepared template (EXP-025) | the layered identity matches | any key input above |

EXP-036 (research/sha256d/exp036/) closes the loop on the
consumption side: a constructed candidate is never trusted
because it came from a cache or a builder; verify_candidate
recomputes its SHA-256d two independent ways and applies the
integer target test before any submission path accepts it.
Caching decides what may be REUSED; verification decides
what may be SUBMITTED. The two must never be merged.
