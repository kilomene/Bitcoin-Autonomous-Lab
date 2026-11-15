# Phase 001, Deliverable 12: Proof-of-Work and Target Mathematics

Project: NOVA SHA-X, Research Phase 001, Wave 3.
Subject: nBits decoding, target comparison, the retarget rule, and the probability mathematics, exactly as Bitcoin v0.1.3 implements them (OpenSSL BIGNUM based), verified against the source's arithmetic by exact recomputation, and contrasted precisely with the modern v28.1 arith_uint256 form documented in research/bitcoin_core/POW_DIFFICULTY_SOURCE.md.

Labels: SOURCE FACT (file and line in the verified 0.1.3 tree), PROVEN (derived and checked here, scripts in RAW_RESULTS), STANDARD (mathematics derived independently of any source).

## 1. nBits decoding in 0.1.3: CBigNum::SetCompact (src/bignum.h lines 257 to 268)

CBigNum is an OpenSSL BIGNUM subclass (src/bignum.h line 49: `class CBigNum : public BIGNUM`). The actual code:

```cpp
CBigNum& SetCompact(unsigned int nCompact)
{
    unsigned int nSize = nCompact >> 24;
    std::vector<unsigned char> vch(4 + nSize);
    vch[3] = nSize;
    if (nSize >= 1) vch[4] = (nCompact >> 16) & 0xff;
    if (nSize >= 2) vch[5] = (nCompact >> 8) & 0xff;
    if (nSize >= 3) vch[6] = (nCompact >> 0) & 0xff;
    BN_mpi2bn(&vch[0], vch.size(), this);
    return *this;
}
```

How it works, step by step (SOURCE FACT about the construction; the MPI semantics are OpenSSL's documented format):

1. nSize is the top byte of nBits (the exponent).
2. The code builds an OpenSSL MPI byte string by hand: a 4-byte big-endian length (only the low byte is set, vch[3] = nSize, the rest are zero from the vector initialization), followed by the three mantissa bytes of nBits in big-endian order at vch[4], vch[5], vch[6], followed by (nSize - 3) zero bytes when nSize > 3 (the vector is sized 4 + nSize).
3. BN_mpi2bn parses it: the value's magnitude is the nSize bytes after the length, big-endian, and the SIGN is the top bit of the first magnitude byte, which is vch[4] = (nCompact >> 16) & 0xff. The sign bit of the compact format (bit 23 of nBits) is therefore not masked out before decoding; it becomes the MPI sign bit, and the magnitude is the remaining bits.

Decoded value, in closed form: let m = nCompact & 0x00ffffff (all three mantissa bytes, sign bit included as data). For nSize >= 3 the magnitude is m * 256^(nSize-3), negated if bit 23 of nBits is set. For nSize < 3 the MPI length truncates the magnitude to its first nSize bytes, i.e. magnitude = m >> (8 * (3 - nSize)) computed on the byte string, again with the sign taken from the top bit of the first byte. PROVEN: RAW_RESULTS/pow_math_verify.py emulates this byte-level construction exactly (including the MPI sign rule) and reproduces every test vector in section 5.

The inverse, GetCompact (src/bignum.h lines 269 to 281), serializes the BIGNUM with BN_bn2mpi, takes the MPI length as nSize, and packs the first three magnitude bytes under (nSize << 24). The sign-avoidance that modern code performs with an explicit shift (POW_DIFFICULTY_SOURCE.md section 1) is here inherited from the MPI encoding itself: BN_bn2mpi inserts a leading zero byte when the magnitude's top bit is set, which lengthens nSize by one and shifts the mantissa bytes exactly as the modern rule does. Round trip on the genesis target: GetCompact(SetCompact(0x1d00ffff)) = 0x1d00ffff (exercised in the source itself: GetNextWorkRequired returns bnProofOfWorkLimit.GetCompact() for the genesis case, src/main.cpp line 693).

## 2. From BIGNUM to uint256: getuint256 (src/bignum.h lines 218 to 231)

```cpp
uint256 getuint256()
{
    unsigned int nSize = BN_bn2mpi(this, NULL);
    if (nSize < 4)
        return 0;
    std::vector<unsigned char> vch(nSize);
    BN_bn2mpi(this, &vch[0]);
    if (vch.size() > 4)
        vch[4] &= 0x7f;
    uint256 n = 0;
    for (int i = 0, j = vch.size()-1; i < sizeof(n) && j >= 4; i++, j--)
        ((unsigned char*)&n)[i] = vch[j];
    return n;
}
```

Three behaviours that matter for the comparison in section 6:

1. The sign is silently discarded: vch[4] &= 0x7f clears the MPI sign bit, and the copy loop takes magnitude bytes only. A negative CBigNum converts to its absolute value as a uint256. There is no error, no flag, no record.
2. Overflow is silently truncated: the loop copies at most 32 bytes, taking the LOW-order bytes of the magnitude (it walks from the end of the MPI byte string). A target of 2^256 or more wraps modulo 2^256 in effect (the exact residue is the low 256 bits).
3. The result's byte layout: byte i of the uint256 is the i-th least significant byte of the magnitude, i.e. the uint256 holds the integer in little-endian byte order in memory, with limbs pn[0..7] (src/uint256.h lines 29 to 30) in increasing significance.

## 3. The target comparison, as the mining loop and the validators perform it

Mining loop (src/main.cpp line 2307 and line 2315):

```cpp
uint256 hashTarget = CBigNum().SetCompact(pblock->nBits).getuint256();
...
if (hash <= hashTarget)
```

The comparison is base_uint's operator<= (src/uint256.h lines 226 to 236), which walks limbs from pn[7] down to pn[0] and returns at the first differing limb: a plain unsigned 256-bit integer comparison, most significant limb first. The hash operand is the BlockSHA256 output buffer reinterpreted as a uint256. Byte-order consistency: BlockSHA256 stores its final state byte-reversed (Deliverable 11, section 3.3), so the uint256's most significant byte is the first byte of the standard digest; the integer being compared is the digest interpreted as a big-endian 256-bit number, which is the same integer GetHash() produces through OpenSSL and the same integer the displayed hex (GetHex reverses the memory bytes) shows. Acceptance is hash <= target, equality included (both operator<= in the loop and the validators' `GetHash() > target` rejection form, below, agree on this).

The validation gates in 0.1.3 (there is no function named CheckProofOfWork in this version; the checks are inlined):

- src/main.cpp lines 1180 to 1184, CBlock::CheckBlock: reject if `CBigNum().SetCompact(nBits) > bnProofOfWorkLimit` (a SIGNED BIGNUM comparison), reject if `GetHash() > CBigNum().SetCompact(nBits).getuint256()` (the unsigned comparison, sign already discarded by getuint256).
- src/main.h lines 956 to 959: the same two gates in CBlock::ReadFromDisk.
- src/main.cpp lines 1210 to 1211, CBlock::AcceptBlock: reject unless `nBits == GetNextWorkRequired(pindexPrev)` exactly. This equality gate is what confines the decoding edge cases of section 6 on a real chain: a block's nBits must equal the one value the retarget rule produces, so exotic encodings cannot be the required value. But CheckBlock, the context-free gate applied to orphan blocks, contains no negative or overflow rejection of its own beyond the signed limit comparison.
- bnProofOfWorkLimit is src/main.h line 22: `static const CBigNum bnProofOfWorkLimit(~uint256(0) >> 32);` = 2^256 - 1 shifted right 32 = 2^224 - 1, as a BIGNUM built through the uint256 conversion.

## 4. "Difficulty" in 0.1.3: it does not exist

SOURCE FACT, established by exhaustive search: the string "difficulty" (any case) appears nowhere in the 0.1.3 tree, and there is no GetDifficulty function. The version works purely with targets and the proof-of-work limit. The quantity later Bitcoin versions call difficulty is, as mathematics (STANDARD, derived here, not read from the source):

```
D(T) = T1 / T,   where T1 = SetCompact(0x1d00ffff) = 0xffff * 2^208
```

so D = 1 exactly at the genesis target. Section 7 uses D only through T. Any document that attributes a difficulty computation to 0.1.3 code is inventing it; the RPC-era difficulty display came later.

## 5. Decoding vectors, both forms (PROVEN, pow_math_verify.py)

| nBits | 0.1.3 CBigNum (signed) | 0.1.3 getuint256 | v28.1 value | v28.1 flags |
|---|---|---|---|---|
| 1d00ffff | 0xffff * 2^208 | same | same | none |
| 1b0404cb | 0x0404cb * 2^192 | same | same | none |
| 0300ffff | 0xffff | same | same | none |
| 0200ffff | 0xff | same | same | none |
| 0100ffff | 0 | 0 | 0 | none |
| 01800000 | 0 (MPI negative zero) | 0 | 0 | none (zero mantissa) |
| 1e80ffff | NEGATIVE 0xffff * 2^216 | 0xffff * 2^216 (sign dropped) | 0xffff * 2^216 | NEGATIVE |
| 2200ffff | 0xffff * 2^248 (exact, about 2^264) | 0xff * 2^248 (truncated) | 0xff * 2^248 (wrapped) | OVERFLOW |
| 2300ffff | 0xffff * 2^256 (exact) | 0 (truncated) | 0 (wrapped) | OVERFLOW |
| 2100ffff | 0xffff * 2^240 | same | same | none |

For every historically valid encoding the three columns agree. They diverge exactly on the encodings that are invalid as targets, and they diverge in mechanism: the modern form computes flags and lets the caller reject; the 0.1.3 form has no flags and its two consumers (signed limit check, unsigned hash check) each see a different shadow of the decoded value.

## 6. The sharpest differences: 0.1.3 Bignum handling vs v28.1 arith_uint256

Stated precisely, with the modern side cited to research/bitcoin_core/POW_DIFFICULTY_SOURCE.md (v28.1 src/arith_uint256.cpp lines 175 to 193, src/pow.cpp lines 137 to 154):

1. Sign. Modern: the mantissa is masked to 23 bits (nCompact & 0x007fffff) BEFORE decoding, the sign bit is reported separately as fNegative (true only for a non-zero mantissa), and CheckProofOfWork rejects negative targets outright. 0.1.3: the sign bit rides into the MPI magnitude's top byte and becomes a true BIGNUM sign; the signed limit check in CheckBlock then passes trivially for negative targets (a negative is never > the limit), and getuint256 silently converts to the absolute value for the hash comparison. Net effect: in 0.1.3's context-free check, an nBits with the sign bit set is treated as its magnitude target; in v28.1 it is rejected before any comparison. (On an actual chain the AcceptBlock equality gate of section 3 blocks such an nBits in both eras, because the required nBits is always a canonical GetCompact output.)
2. Overflow. Modern: values above 256 bits are detected by exact size tests and reported as fOverflow; CheckProofOfWork rejects them; the stored value is the wrapped residue. 0.1.3: CBigNum is arbitrary precision, so SetCompact is exact for any nSize; the wrap happens later and silently, inside getuint256's 32-byte copy. The 0.1.3 limit check still catches oversized targets because it compares the untruncated BIGNUM, but the mining loop (line 2307) applies getuint256 with no limit check of its own; it is safe only because its nBits always comes from GetNextWorkRequired.
3. Zero target. Modern CheckProofOfWork rejects bnTarget == 0 explicitly. 0.1.3 has no zero check: a zero target simply makes the hash comparison fail for every hash except 0 itself (and the limit check passes). Same practical outcome on the hash gate, different mechanism, and the difference matters for any code that reuses the decoded value for something other than the comparison.
4. Where rejection lives. Modern: one function, CheckProofOfWork, owns range validation (negative, zero, overflow, over-limit) and is called from header validation. 0.1.3: the checks are inlined in at least three places (CheckBlock, ReadFromDisk, and implicitly AcceptBlock's equality), with the limit compared as a BIGNUM in two of them.
5. Arithmetic substrate. Modern: fixed 8-limb unsigned arithmetic, no allocation, no floating point, identical behaviour on every platform. 0.1.3: OpenSSL BIGNUM with heap allocation and the MPI byte-string round trip for every decode and encode; the retarget's multiply and divide (section 7) are BIGNUM operations whose division truncates toward zero (BN_div semantics for positive operands = floor, matching the modern arith_uint256 division for the positive values involved).
6. GetCompact. Modern: integer code with the explicit sign-avoidance shift. 0.1.3: the same net encoding falls out of BN_bn2mpi's leading-zero insertion (section 1). The outputs agree; only the mechanism differs.

## 7. The retarget rule as coded: GetNextWorkRequired (src/main.cpp lines 685 to 732)

Constants, defined inside the function (lines 687 to 689): nTargetTimespan = 14 * 24 * 60 * 60 = 1,209,600 seconds; nTargetSpacing = 10 * 60 = 600 seconds; nInterval = 1,209,600 / 600 = 2016.

Behaviour (line-cited):

- pindexLast == NULL (genesis): return bnProofOfWorkLimit.GetCompact() (lines 692 to 693), i.e. 0x1d00ffff.
- (height + 1) mod 2016 != 0: return the previous block's nBits unchanged (lines 696 to 697).
- At a boundary: walk back nInterval - 1 = 2015 steps to the first block of the period (lines 700 to 704); nActualTimespan = last.nTime - first.nTime (line 707). Note the consequence: the measured span covers 2015 inter-block intervals for a 2016-block period, the well-known off-by-one, present verbatim in this original code.
- Clamp the actual timespan into [nTargetTimespan / 4, nTargetTimespan * 4] = [302,400, 4,838,400] (lines 708 to 711): one retarget can multiply the target by at most 4 or divide it by at most 4.
- bnNew = SetCompact(previous nBits); bnNew = bnNew * nActualTimespan / nTargetTimespan (lines 714 to 717, BIGNUM multiply then divide, in that order, so no precision is lost to an early division).
- Cap: if bnNew > bnProofOfWorkLimit, bnNew = bnProofOfWorkLimit (lines 719 to 720). Return bnNew.GetCompact() (line 728).

Differences from v28.1 (POW_DIFFICULTY_SOURCE.md section 3): the modern rule has the same timespan, spacing, interval and factor-4 clamp on mainnet, but adds machinery 0.1.3 entirely lacks: per-chain parameter sets (0.1.3 hardcodes the single mainnet rule in the function body; there is no chainparams, no testnet, no regtest in this tree), the min-difficulty exception for test chains, the testnet4 BIP94 first-block rule, and the fPowNoRetargeting switch. The modern off-by-one is identical (the first block of the period is found the same way). Also absent in 0.1.3: any median-time or future-time rule inside the retarget itself; timestamp sanity lives in CheckBlock (2-hour future limit, src/main.cpp line 1165) and in the miner's use of GetMedianTimePast (line 2295).

## 8. Probability mathematics (STANDARD, derived independently; numerics PROVEN by pow_math_verify.py)

Model: the double hash of a candidate header is treated as uniform on the integers [0, 2^256). This is the standard random-oracle model for SHA-256d; it is an assumption about the hash function, stated here as one, and every quantity below is conditional on it.

Success event: hash <= T, which contains exactly T + 1 integers. Therefore

```
p = (T + 1) / 2^256
```

Trials are independent, so the trial count to first success is geometric:

```
P(first success on trial k) = (1 - p)^(k-1) * p
P(at least one success in N trials) = 1 - (1 - p)^N  (approximately 1 - exp(-N * p) for small p)
E[trials] = 1 / p = 2^256 / (T + 1)
E[time] = E[trials] / R        (R = candidate rate in hashes per second)
median trials = ceil( ln(1/2) / ln(1 - p) )  (approximately ln 2 * E[trials])
```

Elapsed unsuccessful trials do not change p for the next trial (the geometric distribution is memoryless); expected time is not a deadline. These are properties of the model, stated because the directive requires them stated.

At the genesis (difficulty-1) target T1 = 0xffff * 2^208 = 2^224 - 2^208:

```
p(T1) = (T1 + 1) / 2^256 = 2.3282709094019083e-10
E[trials] = 2^256 / (T1 + 1) = 4,295,032,833.000015 (exact fraction in pow_math_verify.txt)
```

The famous "2^32 expected hashes at difficulty 1" is an approximation, and this reconstruction pins down exactly where it comes from: E = 2^32 * 2^224 / (2^224 - 2^208 + 1), i.e. E / 2^32 = 1.0000152590218967. The identity E = 2^32 is EXACT not for T1 but for the proof-of-work limit target T_limit = 2^224 - 1 (bnProofOfWorkLimit, src/main.h line 22): E = 2^256 / (T_limit + 1) = 2^256 / 2^224 = 2^32 exactly (PROVEN in the script). The 1.5e-5 relative gap between the two statements is the gap between T1 and T_limit (T_limit / T1 = 1.0000152590218967, the same ratio). Median trials at T1: about 2,977,089,899 (ln 2 * E). Probability of at least one success inside one full nonce space of 2^32 trials at T1: 1 - (1 - p)^(2^32) = 0.6321149454, the familiar 1 - 1/e shape, here computed from the exact p.

For a general target, expected hashes scale inversely with (T + 1); in terms of the section-4 ratio, E(T) = E(T1) * (T1 + 1) / (T + 1), approximately 2^32 * D(T) with D as defined there, with the same 1.0000152 correction carried along.

## 9. Nonce space and exhaustion in this version (SOURCE FACT, src/main.cpp lines 2297, 2310 to 2357)

- The nonce is a 32-bit field; the per-template space is 2^32 values.
- The loop starts at nNonce = 1 (line 2297), not 0.
- Each iteration hashes the current nonce, then the housekeeping statement `(++tmp.block.nNonce & 0x3ffff) == 0` (line 2344) increments the counter (every iteration) and runs its body every 262,144 increments: shutdown check, new-tip check, transaction-update check, and nTime refresh (line 2355).
- When the increment wraps the counter to exactly 0 (after 0xffffffff has been hashed), the body breaks out of the search loop (lines 2347 to 2348). Consequence: nonce value 0 is never hashed by this loop; the values actually tried per template are 1 .. 0xffffffff, which is 2^32 - 1 candidates.
- Breaking out rebuilds the whole block template in the outer loop, and the rebuild increments the coinbase extranonce: `txNew.vin[0].scriptSig << nBits << ++bnExtraNonce` (line 2212, bnExtraNonce declared at line 2190 as a CBigNum starting at 0). A new extranonce changes the coinbase, hence the merkle root, hence chunk 1 of the header: exhaustion is escaped by changing the template, not by extending the nonce field. nTime is also refreshed on the periodic path and at rebuild.
- At difficulty 1, section 8 gives a 63.2 percent success probability per full space, so exhaustion without success is the outcome about 36.8 percent of the time per template even at the easiest target the system ever used; the rebuild path is therefore not an edge case but a routine part of the original search architecture.

## 10. Reproduction

`python3 research/phase001/RAW_RESULTS/pow_math_verify.py` prints the full vector table (signed 0.1.3 value, getuint256 value, modern value and flags for 14 nBits encodings), the genesis target check (0xffff * 2^208, hash <= target), the limit ratio, and every probability quantity in section 8 as exact fractions before decimal approximation.

## 11. Limitations

- The MPI sign and truncation semantics are OpenSSL's documented BN_mpi2bn / BN_bn2mpi behaviour, emulated byte for byte in the verification script; the 0.1.3 tree links OpenSSL (libeay32.dll ships in the archive) but does not contain its source, so the emulation is verified against the documented format and against the known-good genesis values, not against OpenSSL source in-tree.
- The uniform-hash model of section 8 is an assumption, as it is in every Bitcoin probability treatment; the source itself contains no probability code, and nothing in this deliverable attributes any to it.
- Difficulty D is used only as derived mathematics (section 4); it has no 0.1.3 code existence.
