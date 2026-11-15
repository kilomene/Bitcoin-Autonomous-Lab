# Proof-of-Work and Difficulty Specification

NOVA SHA-X Master Assignment, work package BR-005 (PoW and
difficulty mathematics). The complete specification of how a
32-bit nBits field becomes a 256-bit target, how a candidate hash
is judged, how the target is retargeted, and how the subsidy
interacts with the coinbase value, in both eras of the code: the
original v0.1.3 (OpenSSL BIGNUM) and modern Core v28.1
(arith_uint256). All consensus statements here are exact integer
statements. Floating-point difficulty never appears in any
consensus rule in either era; where difficulty appears at all, it
is a derived display quantity (section 6).

Sources: research/bitcoin_core/POW_DIFFICULTY_SOURCE.md (v28.1,
pinned commit 32efe850438ef22e2de39e562af557872a402c31, file and
line citations throughout); research/phase001/
POW_TARGET_MATHEMATICS.md (v0.1.3, verified tree, with the
byte-level verification script research/phase001/RAW_RESULTS/
pow_math_verify.py). The probability consequences of the target
live in research/probability/BITCOIN_MINING_PROBABILITY_MODEL.md.

## 1. The compact format

nBits is a 32-bit unsigned integer with three parts:

```
bits 24..31 : nSize    (the "exponent")
bit  23     : sign bit
bits 0..22  : mantissa (23 bits in the modern decoding)
```

The intended value is mantissa * 256^(nSize - 3) when nSize > 3,
and mantissa shifted right by 8 * (3 - nSize) bits when nSize <= 3.
The two eras decode this format by different mechanisms, agree on
every historically valid encoding, and diverge exactly on the
encodings that are invalid as targets (section 4).

## 2. Decoding in v28.1: arith_uint256::SetCompact

Location: src/arith_uint256.cpp lines 175 to 193 (full text in the
Core audit, section 1). Semantics, exactly as implemented:

- nSize = nCompact >> 24. The mantissa is masked to 23 bits:
  nWord = nCompact & 0x007fffff. The sign bit (0x00800000) is NOT
  part of the mantissa.
- If nSize <= 3: value = nWord >> (8 * (3 - nSize)). Else: value =
  nWord << (8 * (nSize - 3)), computed in a fixed 8-limb unsigned
  integer, so an oversized value wraps modulo 2^256 in storage.
- fNegative is reported true only when nWord != 0 AND the sign bit
  is set. A sign bit with a zero mantissa is not negative.
- fOverflow is reported true only when nWord != 0 AND the value
  would exceed 256 bits, tested exactly as: nSize > 34, or
  (nWord > 0xff and nSize > 33), or (nWord > 0xffff and
  nSize > 32).
- **SetCompact itself never rejects anything.** It always writes
  the decoded (possibly wrapped) value and reports conditions only
  through the optional out-pointers. Rejection is the caller's job.

The inverse, GetCompact (src/arith_uint256.cpp lines 195 to 216),
re-encodes with the sign-avoidance rule: if the top mantissa bit
0x00800000 would be set, the mantissa is shifted right one byte
and nSize incremented, so a round trip never produces a spurious
negative encoding.

## 3. The acceptance rule in v28.1: CheckProofOfWork

Location: src/pow.cpp lines 137 to 154. The complete rule:

1. Decode nBits with SetCompact, capturing fNegative and
   fOverflow.
2. Reject if ANY of: fNegative; decoded target == 0; fOverflow;
   decoded target > the chain's powLimit.
3. Reject if hash > target, with the hash converted by
   UintToArith256 (little-endian limb interpretation,
   src/arith_uint256.cpp line 225).
4. Accept otherwise.

So the comparison is the unsigned integer rule **hash <= target,
with equality accepted**, and it is reached only after the range
checks of step 2 pass. CheckProofOfWork validates the nBits the
header claims; whether that nBits is the required one for the
block's position is a separate contextual check through
GetNextWorkRequired. Call site: src/validation.cpp line 3912,
inside CheckBlockHeader. All arithmetic is fixed-limb integer; no
floating point appears anywhere in target decoding, comparison, or
retargeting in this revision.

## 4. Decoding and judging in v0.1.3: the BIGNUM era

There is no CheckProofOfWork function in v0.1.3. The mechanisms,
from research/phase001/POW_TARGET_MATHEMATICS.md (verified tree,
line citations there):

### 4.1 SetCompact via OpenSSL MPI (src/bignum.h lines 257 to 268)

CBigNum::SetCompact builds an OpenSSL MPI byte string by hand: a
4-byte length (low byte = nSize) followed by the three mantissa
bytes of nBits in big-endian order, followed by (nSize - 3) zero
bytes when nSize > 3, and calls BN_mpi2bn. Consequences:

- The mantissa is NOT masked to 23 bits before decoding. The sign
  bit of the compact format becomes the MPI sign bit (the top bit
  of the first magnitude byte), so the decoded CBigNum is a true
  signed value: negative exactly when bit 23 of nBits is set and
  the magnitude is non-zero.
- For nSize < 3, the MPI length truncates the magnitude to its
  first nSize bytes (the same net values as the modern shift).
- The decode is exact at any size: CBigNum is arbitrary precision,
  so there is no overflow at this stage.

GetCompact (lines 269 to 281) serializes with BN_bn2mpi and packs
the first three magnitude bytes under (nSize << 24); the modern
sign-avoidance shift falls out of BN_bn2mpi's leading-zero
insertion. The outputs agree with the modern encoder.

### 4.2 getuint256: where the sign and the overflow go (lines 218 to 231)

The mining loop and the validators judge hashes against
SetCompact(nBits).getuint256(), a conversion that:

- **silently discards the sign**: the MPI sign bit is cleared
  (vch[4] &= 0x7f) and magnitude bytes only are copied, so a
  negative target converts to its absolute value, with no error,
  flag, or record;
- **silently truncates overflow**: at most 32 bytes are copied,
  walking from the low-order end, so a target of 2^256 or more
  wraps to its low 256 bits in effect;
- produces the uint256 in little-endian byte order in memory,
  limbs in increasing significance, which base_uint's operator<=
  compares from the most significant limb down: a plain unsigned
  256-bit comparison of the same integer the modern rule compares.

### 4.3 The validation gates, inlined

- CBlock::CheckBlock (src/main.cpp lines 1180 to 1184): reject if
  SetCompact(nBits) > bnProofOfWorkLimit (a SIGNED BIGNUM
  comparison), and reject if GetHash() > SetCompact(nBits)
  .getuint256() (the unsigned comparison, sign already discarded).
- The same two gates in CBlock::ReadFromDisk (src/main.h lines
  956 to 959).
- CBlock::AcceptBlock (src/main.cpp lines 1210 to 1211): reject
  unless nBits == GetNextWorkRequired(pindexPrev) exactly.
- bnProofOfWorkLimit (src/main.h line 22) is
  ~uint256(0) >> 32 = 2^224 - 1 as a BIGNUM.

The mining loop itself (src/main.cpp line 2307) computes
hashTarget = SetCompact(nBits).getuint256() once per template and
accepts when hash <= hashTarget (line 2315), equality included,
with no limit check of its own; it is safe only because its nBits
always comes from GetNextWorkRequired.

### 4.4 The divergences, stated precisely

For every historically valid encoding the two eras decode
identically (verified over a 14-vector table, Phase 001
Deliverable 12, section 5). They diverge on invalid encodings:

| Case | v28.1 | v0.1.3 |
|---|---|---|
| Sign bit set, non-zero mantissa (e.g. 0x1e80ffff) | fNegative set; CheckProofOfWork rejects before comparison | BIGNUM decodes negative; the signed limit check passes trivially (a negative is never > the limit); getuint256 drops the sign, so the context-free hash check judges against the MAGNITUDE target |
| Overflow (e.g. 0x2200ffff, 0x2300ffff) | fOverflow set; rejected; stored value is the wrapped residue | SetCompact exact at any size; the limit check compares the untruncated BIGNUM and catches oversize; the wrap happens silently later, inside getuint256 (0x2300ffff converts to 0) |
| Zero target | Rejected explicitly in CheckProofOfWork | No zero check anywhere; a zero target simply fails every hash comparison except hash == 0, and passes the limit check |
| Where rejection lives | One function owns all range checks (negative, zero, overflow, over-limit) | Inlined in at least three places, with mixed signed and unsigned comparisons |

The backstop in both eras is the same: on a real chain, a block's
nBits must equal the retarget rule's output exactly (AcceptBlock
in 0.1.3; contextual header checks in v28.1), and that output is
always a canonical GetCompact encoding, so the exotic encodings
above cannot be the required value. The divergence matters for
any code that decodes nBits outside that gate: NOVA's own verifier
(mining/candidate_verify.py, EXP-036) implements the MODERN rule
set (negative and overflow rejection, powLimit comparison,
integer hash <= target), which the Core audit confirms is the
behaviour to match.

Worked vectors (both eras, from the verified table):

| nBits | Decoded target | Notes |
|---|---|---|
| 0x1d00ffff | 0xffff * 2^208 | genesis / difficulty-1 target T1 |
| 0x1b0404cb | 0x0404cb * 2^192 | a later mainnet encoding |
| 0x0300ffff | 0xffff | nSize = 3 boundary |
| 0x0200ffff | 0xff | nSize < 3 truncation/shift path |
| 0x0100ffff | 0 | decodes to zero |
| 0x01800000 | 0 | sign bit with zero mantissa: not negative in either era's net behaviour |

## 5. The retarget rule

### 5.1 Shared skeleton (both eras, mainnet parameters)

- Interval: DifficultyAdjustmentInterval = nPowTargetTimespan /
  nPowTargetSpacing = 1,209,600 / 600 = 2016 blocks. In v28.1 it
  is a derived value (src/consensus/params.h line 123), not a
  stored constant; in v0.1.3 the constants are hardcoded inside
  the function (src/main.cpp lines 687 to 689).
- Off boundary: the required nBits is the previous block's nBits.
- At a boundary: actual timespan = (last block time) minus (first
  block of the period's time); clamp the actual timespan into
  [timespan / 4, timespan * 4] = [302,400, 4,838,400] seconds, so
  one retarget changes the target by at most a factor of 4 in
  either direction; new target = old target * clamped timespan /
  target timespan (multiply first, then divide, in exact integer
  arithmetic); cap at the proof-of-work limit; return GetCompact.
- **The off-by-one is in both eras.** The walk back from the last
  block of the period to the first covers 2015 steps, so the
  measured span covers 2015 inter-block intervals for a 2016-block
  period. It is present verbatim in the original code (src/main.cpp
  lines 700 to 704) and the modern code finds the period's first
  block the same way. Any reimplementation that "fixes" it
  disagrees with consensus.

### 5.2 v28.1 specifics (src/pow.cpp)

- GetNextWorkRequired (lines 13 to 47): boundary logic,
  min-difficulty exception, delegation to
  CalculateNextWorkRequired (lines 49 to 84) with the first block
  time of the current interval.
- Min-difficulty exception (chains with
  fPowAllowMinDifficultyBlocks: testnet3, testnet4, regtest): if
  the new block's timestamp is more than 2 * nPowTargetSpacing
  past the previous block's, the pow limit's compact value is
  returned; otherwise the code walks back to the last block whose
  nBits was not the min-difficulty value.
- fPowNoRetargeting (regtest): CalculateNextWorkRequired returns
  the previous nBits unchanged (lines 51 to 52).
- **Testnet4 BIP94 (params.enforce_BIP94, src/pow.cpp lines 66 to
  75): the old target for the retarget multiplication is read
  from the FIRST block of the difficulty period, not the last**,
  because min-difficulty exception blocks in the period must not
  dilute the retarget. This is the one place where the modern
  rule departs from "previous target times ratio" in substance,
  and any NOVA code claiming testnet4 agreement must reproduce it.
- PermittedDifficultyTransition (lines 88 to 135): a helper for
  header-sync logic; within the factor-of-4 envelope at
  boundaries, old == new elsewhere; always true on min-difficulty
  chains.
- Per-chain parameters (src/kernel/chainparams.cpp, tabulated in
  the Core audit section 4): mainnet powLimit is the 2^224 - 1
  class (compact 0x1d00ffff); signet's is lower (0x1e0377ae
  class); regtest's is the 2^255 - 1 class (compact 0x207fffff),
  with timespan 86,400 s, interval 144, fPowNoRetargeting true,
  and halving interval 150.

### 5.3 v0.1.3 specifics (src/main.cpp lines 685 to 732)

- Genesis case: pindexLast == NULL returns
  bnProofOfWorkLimit.GetCompact() = 0x1d00ffff (lines 692 to 693).
- One hardcoded mainnet rule in the function body: there is no
  chainparams, no testnet, no regtest, no min-difficulty exception,
  no BIP94, no no-retargeting switch in this tree.
- The multiply and divide are OpenSSL BIGNUM operations;
  BN_div truncates toward zero, which for the positive values
  involved equals the modern floor division.
- Timestamp sanity is not part of the retarget: it lives in
  CheckBlock (2-hour future limit, line 1165) and in the miner's
  use of GetMedianTimePast.

## 6. Difficulty: a derived display quantity only

Neither era's consensus code computes or compares a difficulty.
The word does not occur in the v0.1.3 tree at all (exhaustive
search, Phase 001 Deliverable 12, section 4). In v28.1 the
difficulty figure shown by RPCs is derived from the ratio of the
pow limit target to the current target and plays no part in any
consensus check (Core audit, section 4).

As mathematics, difficulty is defined relative to the
difficulty-1 target T1 = SetCompact(0x1d00ffff) = 0xffff * 2^208:

```
D(T) = T1 / T        (a rational number, in general not an integer)
```

D = 1 exactly at T1. Its only legitimate uses are communication
and the probability model's difficulty form (expected hashes
approximately D * 2^32, with the exact correction stated in the
probability model, section 4). **Any use of floating-point
difficulty as a consensus test, a target comparison, or a block
acceptance criterion is a defect**: the EXP-030 Phase A audit
found exactly that defect pattern in the Qaxe firmware family
(judging blocks by floating-point difficulty, matrix finding W1)
and NOVA rejected it there; NOVA's own paths compare integers
only (EXP-036).

## 7. Subsidy, halving, and the coinbase value

The target mathematics meets the money supply at one point: the
maximum value the coinbase may claim.

### 7.1 v28.1

- GetBlockSubsidy(nHeight, consensus) returns the era subsidy:
  50 * COIN in era 0, right-shifted by (nHeight /
  nSubsidyHalvingInterval); mainnet interval 210,000 (chainparams),
  regtest 150.
- BlockAssembler sets the coinbase output value to nFees +
  GetBlockSubsidy(nHeight) (src/node/miner.cpp line 160, per the
  mining call graph), where nHeight is the height of the block
  being built and nFees is the total fee of the selected
  transactions.
- Consensus enforcement is in block connection: a coinbase
  claiming more than subsidy plus the block's actual fees is
  invalid; claiming less is permitted (the difference is burned).

### 7.2 v0.1.3 (src/main.cpp lines 675 to 683)

- CBlock::GetBlockValue(nFees) returns (50 * COIN right-shifted
  by (nBestHeight / 210000)) + nFees, and the miner assigns it as
  the coinbase's single output value (line 2267); ConnectBlock
  rejects a coinbase whose output exceeds GetBlockValue(nFees)
  (line 953), with under-claiming allowed, as in the modern rule.
- Two era differences with specification force: the shift is an
  arithmetic right shift of the subsidy itself, so era k subsidy
  is exactly floor(5,000,000,000 / 2^k) and reaches 0 when the
  shift count reaches 33; and **the height used is the global
  nBestHeight, the current best tip's height, not the height of
  the block being built** (which is nBestHeight + 1). At a halving
  boundary the first block of the new era is therefore valued at
  the old era's subsidy by this code, and miner and validator
  agree only because both call the same function in the same
  state. Recorded as a faithful quirk of the original (Phase 001,
  TRANSACTION_RECONSTRUCTION.md section 6); the modern code uses
  the new block's own height and does not have the quirk.

### 7.3 The interaction, stated once

The subsidy rule bounds the coinbase value; the coinbase bytes
determine the coinbase txid; the txid determines the merkle root;
the merkle root is header bytes 36 to 67. So the subsidy and fee
total are inputs to the search space itself: change the claimed
value and every candidate header changes. This is why template
construction (BR-006) and the search-space model (BR-007) treat
the coinbase as part of the template identity, and why the
probability model conditions on a fixed template.

## 8. What an implementation must reproduce (checklist)

Drawn from both eras; NOVA's candidate verifier (EXP-036) is
checked against this list in its audit.

1. Mask the mantissa to 23 bits; report negative only for a
   non-zero mantissa with the sign bit set; report overflow by
   the exact size tests of section 2.
2. Reject negative, zero, overflowing, and over-powLimit targets
   before comparing; never let a decode silently drop a sign or
   wrap a value into a comparison.
3. Compare hash <= target as unsigned 256-bit integers, equality
   accepted.
4. Retarget only at interval boundaries; clamp the timespan to
   the factor-of-4 envelope; multiply before dividing; cap at
   powLimit; reproduce the 2015-step period walk; reproduce the
   min-difficulty exception and the BIP94 first-block rule on the
   chains that have them; reproduce no-retargeting on regtest.
5. Treat difficulty as display and probability shorthand only.
6. Bound the coinbase claim by subsidy (at the new block's
   height, modern rule) plus actual fees.

## 9. Reproduction

- v0.1.3 side: research/phase001/RAW_RESULTS/pow_math_verify.py
  prints the signed decode, the getuint256 conversion, and the
  modern decode with flags for 14 nBits encodings, plus the
  genesis target check.
- v28.1 side: the pinned source itself, src/arith_uint256.cpp
  lines 175 to 216 and src/pow.cpp lines 13 to 154, as cited in
  research/bitcoin_core/POW_DIFFICULTY_SOURCE.md.
