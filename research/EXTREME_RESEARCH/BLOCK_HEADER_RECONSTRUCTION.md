# Block Header Reconstruction

Stage 1 of the NOVA SHA-X Extreme Research mandate. This
document records an independent reconstruction of complete
Bitcoin blocks from their raw serialized bytes, performed by
the tool in `tools/header_reconstruction.py`, which shares no
code with the production mining path and hashes with the pure
Python reference implementation in
`tools/sha256d_reference.py` (see
SHA256D_REFERENCE_IMPLEMENTATION.md).

Prior work this rests on, cited rather than repeated:

- Phase 001 genesis deconstruction
  (research/phase001/COINBASE_MERKLE_ANALYSIS.md,
  BLOCK_HEADER_SPECIFICATION.md): the genesis block's exact
  construction, field values and asserted hash.
- The Core v28.1 audit
  (research/bitcoin_reverse_engineering/): CBlockHeader
  serialization, SetCompact semantics, and the rule that a
  submitblock null result means processed, not accepted.
- EXP-036 (research/sha256d/exp036/): the exact-verification
  standard this tool follows (integer target comparison only,
  no floating point anywhere in the verdict path).

## 1. The 80-byte header layout

A block header is exactly 80 bytes: 4 + 32 + 32 + 4 + 4 + 4.

| Bytes | Width | Field | Encoding |
|---|---|---|---|
| 0 to 3 | 4 | version | little-endian int32 (miners treat the 4 bytes as a u32 for BIP320 version rolling) |
| 4 to 35 | 32 | previous block hash | internal byte order (the display form is the byte reversal) |
| 36 to 67 | 32 | Merkle root | internal byte order (display form reversed) |
| 68 to 71 | 4 | time (nTime) | little-endian uint32, seconds since epoch |
| 72 to 75 | 4 | nBits | little-endian uint32, compact target encoding |
| 76 to 79 | 4 | nonce | little-endian uint32 |

For every block below, the tool decoded these six fields from
the raw bytes, re-serialized the header from the decoded
fields alone, and confirmed the result is exactly 80 bytes and
byte-identical to the raw slice. It then computed SHA-256 and
SHA-256d of the header with the reference implementation,
confirmed the block hash against the hash Core reported,
decoded the target from nBits with integer arithmetic
(target = mantissa x 256^(exponent-3), or the equivalent right
shift for exponent <= 3), and verified hash <= target as
integers. It also recomputed the full Merkle root from the
parsed transactions (see
MERKLE_AND_TRANSACTION_MATHEMATICS.md) and, for the SegWit
block, the witness commitment.

Reproduce with:

```
python3 research/EXTREME_RESEARCH/tools/header_reconstruction.py --genesis
python3 research/EXTREME_RESEARCH/tools/header_reconstruction.py --mainnet-height 450150
python3 research/EXTREME_RESEARCH/tools/header_reconstruction.py --regtest-height 1491
```

(The mainnet node is pruned and in initial block download; its
RPC can take over a minute per call under load. The height
450170 block below was fetched by hash after two getblockhash
timeouts; its hash comes from two agreeing Core reads.)

## 2. Genesis block (constructed from Phase 001 constants)

The tool constructs the genesis block byte by byte from the
Phase 001 record: scriptSig pushes of 486604799, CBigNum(4)
and the 69-byte Times headline; one 50 BTC output to the
genesis public key; header fields nVersion 1, nTime 1231006505,
nBits 0x1d00ffff, nNonce 2083236893.

- Raw block: 285 bytes, 1 transaction
- Header hex: 0100000000000000000000000000000000000000000000000000000000000000003ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a29ab5f49ffff001d1dac2b7c
- Merkle root (display): 4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b
- SHA-256 of header (single, internal order): af42031e805ff493a07341e2f74ff58149d22ab9ba19f61343e2c86c71c5d66d
- Block hash: 000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
- Target from 0x1d00ffff: 00000000ffff0000000000000000000000000000000000000000000000000000
- Result: ALL PASS, 8 of 8 checks (parse, count, 80-byte
  re-serialization, byte identity, hashlib agreement, hash
  match, hash <= target, Merkle root match)

## 3. Mainnet blocks from the lab's own pruned node

Node state at run time: blocks 450,182 of headers 976,082,
still in initial block download. All three blocks are from
January 2017 (nTime 1485467049 to 1485477599), which is before
SegWit activation at height 481,824, so none of them contains
a witness commitment; see section 5 for where the witness
commitment is verified instead.

### 3.1 Height 450150

- Block hash: 000000000000000002290daa601d1f212b899685db16bd1f9e822221aa71b0ac
- Raw block: 998,051 bytes, 2,573 transactions, 0 SegWit
- Header hex: 000000209692ef7c99811346b8c1c8645bc491f0f0377f9e4648650000000000000000000523af0d6ef8461c8ca3dc77310acc58c9658ad77ceef660277e8d4387eb424aa96d8a5847cc0218c53fcf04
- version 536870912 (0x20000000), prev hash (display) 0000000000000000006548469e7f37f0f091c45b64c8c1b8461381997cef9296
- Merkle root (display): 4a42eb87438d7e2760f6ee7cd78a65c958cc0a3177dca38c1c46f86e0daf2305
- nTime 1485467049, nBits 0x1802cc47, nonce 80691141
- Target: 000000000000000002cc47000000000000000000000000000000000000000000
- Coinbase txid (display): eaa0c68c1ad0fa9397540a8cdcd961b843bac449b94666fe282b9218552b5716
- Result: ALL PASS, 8 of 8 checks

### 3.2 Height 450160

- Block hash: 000000000000000001218f9e0b7f22f30c34aec051dbb60b7f9d59ce6ab007c0
- Raw block: 998,080 bytes, 931 transactions, 0 SegWit
- Header hex: 00000020fff5256c1beb0c649f31c480fd4b9d4df2f310a169c8cb0000000000000000001f59ccf3ad352c619802ad699e110a804ae74ab94f6731094ae0b6fc68c45d39eb848a5847cc02181596585e
- version 536870912 (0x20000000), prev hash (display) 000000000000000000cbc869a110f3f24d9d4bfd80c4319f640ceb1b6c25f5ff
- Merkle root (display): 395dc468fcb6e04a0931674fb94ae74a800a119e69ad0298612c35adf3cc591f
- nTime 1485473003, nBits 0x1802cc47, nonce 1582863893
- Target: 000000000000000002cc47000000000000000000000000000000000000000000
- Coinbase txid (display): 11732bae64be47594f2cf0f10ad35aa0db08762937145ebab8226862ecd3a303
- Result: ALL PASS, 8 of 8 checks

### 3.3 Height 450170

- Block hash: 000000000000000000d4c7e6e38e3eefa52cea6e06258a69994bf25c1b26affa
- Raw block: 998,164 bytes, 2,095 transactions, 0 SegWit
- Header hex: 020000200e515bc16ac6d463695a72b25535763a57656c7d9ce14e010000000000000000813d998e2d654d28e382ac4405db952a474374ee0f47e0c394ce7c11c555ec08df968a5847cc02184158bda0
- version 536870914 (0x20000002), prev hash (display) 0000000000000000014ee19c7d6c65573a763555b2725a6963d4c66ac15b510e
- Merkle root (display): 08ec55c5117cce94c3e0470fee7443472a95db0544ac82e3284d652d8e993d81
- nTime 1485477599, nBits 0x1802cc47, nonce 2696763457
- Target: 000000000000000002cc47000000000000000000000000000000000000000000
- Coinbase txid (display): 13e5202c0b35e5f9a244deaf7e0a27fab3281130e3dc8b76deb63a1bdcbb1393
- Result: ALL PASS, 8 of 8 checks. This block is the worked
  Merkle example in MERKLE_AND_TRANSACTION_MATHEMATICS.md.

## 4. Regtest block 1491 (SegWit, witness commitment)

Fetched from the lab's regtest datadir (.local/regtest, RPC
18443) with a temporary node started for this run and stopped
afterward. The mainnet node, autopilot and miner were not
touched.

- Block hash: 21c78c0ba7626411f969ef3a9cf7dd437b49f7d872a13ed969aa761daa18a875
- Raw block: 7,912 bytes, 41 transactions, all 41 in SegWit
  serialization
- Header hex: 00000020fb800d3900e632a630553afb3e9f72be1126ef744f0f53c6d8a3d4ba28cf754687bfe02655d49c5285a8917cedcbdcb714620f43abe3455715905703a7db52ff8c56fa6affff7f2001000000
- version 536870912 (0x20000000), prev hash (display) 4675cf28bad4a3d8c6530f4f74ef2611be729f3efb3a5530a632e600390d80fb
- Merkle root (display): ff52dba7035790155745e3ab430f6214b7dccbed7c91a885529cd45526e0bf87
- nTime 1794791052, nBits 0x207fffff, nonce 1
- Coinbase txid (display): b713b970b16ca39c999bdf7f8ed62d6c0b647780cd038efcbe9d2185ffd2908d
- Witness Merkle root (display): 07dd8d90bc4630d38c22bb616dad77d6d6376163d1bd50621d06eae53eeb535b
- Witness commitment in coinbase: 96239308293fdc28e458c4a436f652b049938a1d05a01d0b39f42b3a77f4abfc
- Result: ALL PASS, 9 of 9 checks (the 8 standard checks plus
  witness commitment verified: SHA-256d of the witness root
  concatenated with the coinbase witness reserved value
  equals the commitment bytes)

## 5. What this establishes, and one correction

Established: the header format, field decodings, target
decoding and Merkle construction in the existing record are
exactly reproducible from raw bytes by an independent tool,
on real mainnet blocks of three different transaction counts
(931, 2,095, 2,573), on the genesis block, and on a SegWit
regtest block including its witness commitment.

Correction to the Stage 1 tasking premise: height 450,000-era
mainnet blocks do NOT carry witness commitments. They predate
SegWit activation (height 481,824) by about seven months, and
the lab node's block store currently ends near height
450,182, so no mainnet witness-commitment block is available
from this node yet. The witness-commitment verification is
therefore demonstrated on regtest block 1491 instead. Once
the mainnet node syncs past height 481,824, the same tool
verifies a mainnet SegWit block with no changes:
`--mainnet-height` at any post-activation height runs the
identical code path, including the commitment check.
