# Proof of Work and Difficulty: Bitcoin Core v28.1 Source Evidence

NOVA SHA-X Master Assignment, Phase A/B. Companion to CORE_SOURCE_AUDIT.md.
All line numbers are from the pinned v28.1 tree (commit
32efe850438ef22e2de39e562af557872a402c31). Code excerpts are short and
verbatim; everything else is a faithful restatement of the source.

## 1. Compact target decoding: arith_uint256::SetCompact

Location: src/arith_uint256.cpp:175 to 193 (declaration
src/arith_uint256.h:271).

```cpp
arith_uint256& arith_uint256::SetCompact(uint32_t nCompact, bool* pfNegative, bool* pfOverflow)
{
    int nSize = nCompact >> 24;
    uint32_t nWord = nCompact & 0x007fffff;
    if (nSize <= 3) {
        nWord >>= 8 * (3 - nSize);
        *this = nWord;
    } else {
        *this = nWord;
        *this <<= 8 * (nSize - 3);
    }
    if (pfNegative)
        *pfNegative = nWord != 0 && (nCompact & 0x00800000) != 0;
    if (pfOverflow)
        *pfOverflow = nWord != 0 && ((nSize > 34) ||
                                     (nWord > 0xff && nSize > 33) ||
                                     (nWord > 0xffff && nSize > 32));
    return *this;
}
```

Semantics, exactly as implemented:

- The top byte (nCompact >> 24) is the exponent nSize; the low 23 bits
  (nCompact & 0x007fffff) are the mantissa nWord; bit 0x00800000 is the sign
  bit and is NOT part of the mantissa.
- Decoded value: nWord * 256^(nSize - 3) when nSize > 3; when nSize <= 3 the
  mantissa is right-shifted by 8 * (3 - nSize) bits instead (integer
  truncation toward zero of the low bytes).
- Negative flag: set only when the mantissa is non-zero AND the sign bit is
  set. A sign bit with a zero mantissa does not count as negative.
- Overflow flag: set only when the mantissa is non-zero AND the value would
  exceed 256 bits, tested as: nSize > 34, or (nWord > 0xff and nSize > 33),
  or (nWord > 0xffff and nSize > 32).
- SetCompact itself never rejects anything. It always writes the decoded
  value (which for overflowing encodings is the wrapped, truncated
  arith_uint256 value) and reports the conditions only through the optional
  out-pointers. Rejection is the caller's job (see CheckProofOfWork).
- The inverse, GetCompact (src/arith_uint256.cpp:195 to 216), re-encodes
  with the sign-bit avoidance rule: if the top mantissa bit 0x00800000
  would be set, the mantissa is shifted right one byte and nSize is
  incremented, so a round trip never produces a spurious negative encoding.

All arithmetic is on arith_uint256, a fixed 8 by 32-bit limb integer. No
floating point appears anywhere in target decoding, comparison, or
retargeting in this revision.

## 2. CheckProofOfWork

Location: src/pow.cpp:137 to 154 (declaration src/pow.h:21).

```cpp
bool CheckProofOfWork(uint256 hash, unsigned int nBits, const Consensus::Params& params)
{
    bool fNegative;
    bool fOverflow;
    arith_uint256 bnTarget;

    bnTarget.SetCompact(nBits, &fNegative, &fOverflow);

    // Check range
    if (fNegative || bnTarget == 0 || fOverflow || bnTarget > UintToArith256(params.powLimit))
        return false;

    // Check proof of work matches claimed amount
    if (UintToArith256(hash) > bnTarget)
        return false;

    return true;
}
```

The complete acceptance rule:

1. Decode nBits with SetCompact, capturing fNegative and fOverflow.
2. Reject (return false) if ANY of: fNegative is true; the decoded target
   is zero; fOverflow is true; the decoded target exceeds the chain's
   powLimit.
3. Reject if the hash, converted with UintToArith256 (little-endian limb
   interpretation, src/arith_uint256.cpp:225), is strictly greater than the
   target.
4. Accept otherwise: hash <= target, with equality accepted.

Call site for block validation: src/validation.cpp:3912, inside
CheckBlockHeader (validation.cpp:3909), where failure produces the
"high-hash" / "proof of work failed" invalid-header result. Note that
CheckProofOfWork validates the nBits claimed in the header; whether that
nBits is the required one for the block's position is a separate check
performed through GetNextWorkRequired in contextual header checks.

## 3. Retargeting

### 3.1 GetNextWorkRequired (src/pow.cpp:13 to 47)

- Difficulty changes only at interval boundaries: if
  (height + 1) % DifficultyAdjustmentInterval() != 0, the required nBits is
  normally the previous block's nBits (pow.cpp:19, 37).
- Min-difficulty exception (chains with fPowAllowMinDifficultyBlocks): if
  the new block's timestamp is more than 2 * nPowTargetSpacing past the
  previous block's timestamp, the pow limit's own compact value is returned
  (pow.cpp:26 to 27); otherwise the code walks back to the last block whose
  nBits was not the min-difficulty value and returns that (pow.cpp:31 to
  34).
- At a boundary it delegates to CalculateNextWorkRequired with the first
  block time of the current interval (pow.cpp:41 to 46).

### 3.2 CalculateNextWorkRequired (src/pow.cpp:49 to 84)

- If fPowNoRetargeting, returns the previous nBits unchanged (pow.cpp:51
  to 52). This is the regtest case.
- Actual timespan is clamped to [nPowTargetTimespan / 4,
  nPowTargetTimespan * 4] before use (pow.cpp:56 to 59): a single retarget
  can change the target by at most a factor of 4 in either direction.
- New target = old target * clamped timespan / nPowTargetTimespan, computed
  in arith_uint256 (pow.cpp:77 to 78), then capped at powLimit (pow.cpp:80
  to 81), and returned via GetCompact (pow.cpp:83).
- Testnet4 special case (BIP94, params.enforce_BIP94): the old target is
  taken from the FIRST block of the difficulty period rather than the last,
  because min-difficulty exception blocks must not dilute the retarget
  (pow.cpp:66 to 75).

### 3.3 PermittedDifficultyTransition (src/pow.cpp:88 to 135)

A helper (used by header-sync logic) that checks a proposed nBits change is
within the factor-of-4 envelope at interval boundaries and requires
old == new elsewhere; it always returns true on min-difficulty chains.

### 3.4 DifficultyAdjustmentInterval

Defined in src/consensus/params.h:123:
`int64_t DifficultyAdjustmentInterval() const { return nPowTargetTimespan / nPowTargetSpacing; }`
It is a derived value, not a stored constant.

## 4. Per-chain parameters (src/kernel/chainparams.cpp)

All values read directly from the chain parameter constructors.

| Parameter | Mainnet | Testnet (testnet3) | Testnet4 | Signet | Regtest |
|---|---|---|---|---|---|
| Params class | CMainParams, line 81 | CTestNetParams, line 207 | CTestNet4Params, line 308 | SigNetParams, line 407 | CRegTestParams, line 523 |
| powLimit | 00000000ffffffff... (line 99) | 00000000ffffffff... (line 223) | 00000000ffffffff... (line 322) | 00000377ae000000... (line 469) | 7fffffffffffffff... (line 539) |
| nPowTargetTimespan | 14 * 24 * 60 * 60 = 1,209,600 s (line 100) | same (line 224) | same (line 323) | same (line 461) | 24 * 60 * 60 = 86,400 s (line 540) |
| nPowTargetSpacing | 10 * 60 = 600 s (line 101) | 600 s (line 225) | 600 s (line 324) | 600 s (line 462) | 600 s (line 541) |
| DifficultyAdjustmentInterval (derived) | 2016 | 2016 | 2016 | 2016 | 144 |
| fPowAllowMinDifficultyBlocks | false (line 102) | true (line 226) | true (line 325) | false (line 463) | true (line 542) |
| enforce_BIP94 | false (line 103) | false (line 227) | true (line 326) | false (line 464) | true (line 543) |
| fPowNoRetargeting | false (line 104) | false (line 228) | false (line 327) | false (line 465) | true (line 544) |
| nSubsidyHalvingInterval | 210000 (line 87) | 210000 (line 213) | 210000 (line 314) | 210000 (line 454) | 150 (line 531) |

Notes on the table:

- powLimit strings are the uint256 internal byte-order literals exactly as
  written in the source; the mainnet/testnet/testnet4 limit is the familiar
  2^224 - 1 class limit (compact 0x1d00ffff), signet's is lower
  (compact 0x1e0377ae class), and regtest's is 2^255 - 1 class (compact
  0x207fffff), which is why regtest mining is trivially easy.
- Signet's constructor assigns its fields in a different order (powLimit at
  line 469, after the timespan fields at 461 to 465); the values are as
  tabulated.
- Regtest combines fPowNoRetargeting = true with
  fPowAllowMinDifficultyBlocks = true and enforce_BIP94 = true; in practice
  GetNextWorkRequired on regtest always returns the pow limit compact
  because retargeting is disabled.
- The "difficulty" figure shown by RPCs is a display quantity derived from
  the ratio of the pow limit target to the current target; it plays no part
  in any consensus check in this source. All consensus comparisons are the
  integer comparisons of sections 1 and 2.

## 5. What this means for NOVA (evidence-based, no new claims)

- NOVA's exact-verification component (mining/candidate_verify.py, EXP-036)
  implements this same rule set: SetCompact decoding with negative and
  overflow rejection, powLimit comparison, and hash <= target in integers.
  This document is the Core-side source evidence that behaviour must match,
  including the two easy-to-miss details: a zero mantissa with the sign bit
  set is not negative, and SetCompact itself never rejects.
- Any NOVA retarget or difficulty code must reproduce the factor-of-4
  timespan clamp and the testnet4 BIP94 first-block rule to agree with Core
  on those chains; on regtest it must reproduce the no-retargeting rule and
  the 150-block halving interval (a divergence the lab has hit before).
