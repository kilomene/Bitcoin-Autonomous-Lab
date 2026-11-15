# Phase 001, Deliverable 11: Double-SHA-256 Reconstruction

Project: NOVA SHA-X, Research Phase 001, Wave 3.
Subject: the complete SHA256d operation as Bitcoin v0.1.3 performs it on the 80-byte block header: both passes, chunk and padding accounting byte by byte, the two different code paths that compute it (OpenSSL Hash() and the miner's BlockSHA256), the byte order of the intermediate digest, and exactly what state reuse the original mining loop performs (the honest answer: almost none).

Labels: SOURCE FACT (file and line in the verified 0.1.3 tree), PROVEN (checked by recomputation in RAW_RESULTS), STANDARD (mathematics derived independently).

## 1. The operation

SHA256d(header) = SHA256(SHA256(header)), where header is the exact 80-byte serialization (src/main.h lines 862 to 865: CBlock::GetHash returns Hash(BEGIN(nVersion), END(nNonce)), the fields from nVersion through nNonce, 80 bytes, no length prefix and no transaction data).

Compression accounting (STANDARD, verified in section 4):

| pass | input | input bytes | chunks of 64 bytes | compression rounds |
|---|---|---|---|---|
| 1 | block header | 80 | 2 | 128 |
| 2 | pass-1 digest | 32 | 1 | 64 |
| total | | | 3 | 192 |

## 2. Code path A: the Hash() template (OpenSSL), src/util.h lines 338 to 377

The single-range overload used for block hashes, lines 339 to 346:

```cpp
template<typename T1>
inline uint256 Hash(const T1 pbegin, const T1 pend)
{
    uint256 hash1;
    SHA256((unsigned char*)&pbegin[0], (pend - pbegin) * sizeof(pbegin[0]), (unsigned char*)&hash1);
    uint256 hash2;
    SHA256((unsigned char*)&hash1, sizeof(hash1), (unsigned char*)&hash2);
    return hash2;
}
```

SOURCE FACTS: SHA256 here is OpenSSL's one-shot function (src/headers.h line 21 includes `<openssl/sha.h>`). The intermediate digest hash1 is the raw 32-byte OpenSSL output written directly into a uint256's memory; the second pass hashes those 32 bytes as they lie in memory. The two-range and three-range overloads (lines 348 to 377, used for merkle parents and txids) differ only in using SHA256_Init/Update/Final (OpenSSL streaming) for pass 1. Padding is entirely inside OpenSSL and follows the standard: 0x80, zeros, 8-byte big-endian bit length.

Byte order of the intermediate digest: OpenSSL writes the digest as the standard byte string (each state word big-endian). Because that byte string is then treated as an opaque 32-byte input, no byte-order question arises between the passes in this path: pass 2 consumes exactly the bytes pass 1 produced.

## 3. Code path B: the miner's BlockSHA256 (Crypto++), src/main.cpp lines 2138 to 2182 and 2307 to 2315

The mining loop does not call Hash() per candidate. It calls its own double-hash built from the Crypto++ block primitive, in two steps per candidate (lines 2311 to 2312):

```cpp
BlockSHA256(&tmp.block, nBlocks0, &tmp.hash1);
BlockSHA256(&tmp.hash1, nBlocks1, &hash);
```

### 3.1 FormatHashBlocks: the manual padding (lines 2138 to 2151)

```cpp
int FormatHashBlocks(void* pbuffer, unsigned int len)
{
    unsigned char* pdata = (unsigned char*)pbuffer;
    unsigned int blocks = 1 + ((len + 8) / 64);
    unsigned char* pend = pdata + 64 * blocks;
    memset(pdata + len, 0, 64 * blocks - len);
    pdata[len] = 0x80;
    unsigned int bits = len * 8;
    pend[-1] = (bits >> 0) & 0xff;
    pend[-2] = (bits >> 8) & 0xff;
    pend[-3] = (bits >> 16) & 0xff;
    pend[-4] = (bits >> 24) & 0xff;
    return blocks;
}
```

Structural facts, each checkable against the code:

1. Block count formula: blocks = 1 + ((len + 8) / 64) with integer division. For len = 80: 1 + 88/64 = 2. For len = 32: 1 + 40/64 = 1. Matches section 1.
2. The length field is written as only 4 bytes, big-endian, at the very end of the final block. The standard's 8-byte length field's high 4 bytes are never written by this function; they are zero because the memset zeroed the whole padding region first. For any message under 2^32 bits the result is byte-identical to standard padding (PROVEN in section 4). It is nonetheless a hand-rolled special case, correct only because the memset precedes it and the lengths are tiny.
3. It pads in place, inside the caller's struct. The mining loop's work struct (lines 2274 to 2290) is laid out for exactly this: an 80-byte header block, then `pchPadding0[64]` (line 2286), then the 32-byte hash1, then `pchPadding1[64]` (line 2288). The padding regions are part of the struct, preallocated once.

### 3.2 The exact padding bytes for the header double hash

Pass 1, 80-byte input padded to 128 bytes. Bytes 80 to 127:

```
80: 80                                        (the 0x80 terminator)
81..119: 00 (39 bytes)
120..123: 00 00 00 00                         (high half of the length field, from memset)
124..127: 00 00 02 80                         (640 bits, big-endian, written by FormatHashBlocks)
```

Pass 2, 32-byte input padded to 64 bytes. Bytes 32 to 63:

```
32: 80
33..55: 00 (23 bytes)
56..59: 00 00 00 00
60..63: 00 00 01 00                           (256 bits)
```

PROVEN: RAW_RESULTS/sha256d_layout_verify.py re-implements FormatHashBlocks byte for byte, produces exactly these bytes, and shows the manually padded buffers equal the standard FIPS padding of the same inputs ("manual pad pass1 == standard pad: True", "manual pad pass2 == standard pad: True").

### 3.3 BlockSHA256: state handling and byte order (lines 2156 to 2182)

```cpp
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
    else { ... Transform directly on the input words ... }
}
```

Facts:

1. Every call starts from InitState. The state is a local consequence of the call, never carried between calls by the caller.
2. On little-endian hosts (the `detectlittleendian` static at line 2154), each block's 16 words are byte-reversed into a stack buffer before Transform (so Transform receives big-endian-valued words, as Deliverable 8 requires), and after all blocks the 8 state words are byte-reversed in the output buffer. The net effect: pout holds the standard digest byte string, each state word in big-endian byte order, exactly the bytes OpenSSL would produce. The intermediate hash1 in the mining struct is therefore byte-identical to path A's hash1, and the final hash uint256 is asserted equal to path A's result in the loop itself: line 2317, `assert(hash == pblock->GetHash())` on the success path. The two implementations are cross-checked by the program's own assertion every time a block is found (and by the genesis recomputation, Wave 1).
3. The byte reversal of the output is what makes the uint256 numeric comparison of Deliverable 12 work out: the uint256 in memory holds digest bytes in display-reversed order relative to its integer value, and base_uint's limb comparison (src/uint256.h lines 214 to 236) compares from the most significant limb, which corresponds to the first digest bytes. See Deliverable 12, section 3.

## 4. End-to-end verification

RAW_RESULTS/sha256d_layout_verify.py, on the genesis header (constants parsed from src/main.cpp by Wave 1; header bytes listed in SOURCE_INVENTORY.md section 5): FormatHashBlocks gives 2 blocks and 1 block; the double hash computed through the manually padded buffers equals hashlib's SHA256d; the reversed digest is 000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f, matching the source's own assertion at src/main.cpp line 24 and line 1480. The chunk-2 schedule and state behaviour under a nonce flip also matches Deliverables 9 and 10 exactly.

## 5. State reuse in the mining loop: the exact finding

The tasking for this deliverable asked which states the loop precomputes and reuses. The source answer is precise and, for a modern reader, surprising:

**No cryptographic state is precomputed or reused. None.**

- BlockSHA256 calls SHA256::InitState at the top of every invocation (line 2161), and the loop invokes it twice per candidate (lines 2311 to 2312). For every nonce, chunk 1 of pass 1 is recomputed from H(0), even though Deliverable 10 proves its output (the midstate) is nonce-independent and could have been computed once per template.
- There is no midstate variable, no saved state copy, no partial-round precomputation anywhere in BitcoinMiner (the full loop is src/main.cpp lines 2183 to 2360; the search loop proper is lines 2310 to 2357). The Crypto++ API shape (InitState plus Transform on a caller-owned state array) would have made a midstate copy trivial, a single memcpy of the state after chunk 1, and the code does not do it.

What IS prepared once per template, before the search loop (lines 2292 to 2307):

1. The work struct is filled with the header fields (version, previous hash, merkle root, time, bits, nonce = 1).
2. FormatHashBlocks is called once on the header buffer and once on the (still empty) hash1 buffer, so the padding bytes and block counts nBlocks0 = 2 and nBlocks1 = 1 are fixed before the loop. Per candidate, the only bytes of the pass-1 input that change are the 4 nonce bytes (and the 4 time bytes on refresh); the padding never moves.
3. hashTarget is computed once (line 2307).

So the reuse in 0.1.3 is buffer reuse, not state reuse: the padded layout is amortized, the compression is not. Quantified with Deliverable 10's accounting: of the 192 compression rounds per candidate, 64 (chunk 1) are provably template-constant and are nevertheless recomputed every time; a further 3 rounds of chunk 2 have nonce-independent state evolution. The loop also re-runs the full second BlockSHA256 call, including its InitState, per candidate, which is unavoidable in structure since pass 2's input is the candidate's own digest, but it re-pays the byte-reversal setup each time as well.

This is the single largest exact, consensus-preserving inefficiency identifiable in the original mining loop at the reconstruction level, and it is stated here as an accounting fact (64 of 192 rounds provably redundant per candidate), not as a measured performance claim.

## 6. Alternative exact arrangements (analysis only, no implementation)

Whether SHA256d can be arranged differently while producing bit-identical output for every input is a mathematical question, separable into three claims of increasing strength:

1. Reordering and regrouping inside the existing dataflow (addition regrouping, schedule precomputation, midstate caching, evaluating the two passes' fixed parts early): PROVEN exact, because each is an identity over the same expression DAG (mod-2^32 addition is associative and commutative; caching a pure subexpression changes nothing). Midstate reuse is in this class.
2. Substituting algebraically equivalent Boolean forms (for example the two Ch forms and the two Maj forms of Deliverable 8, or the VPTERNLOG-style three-input forms the lab verified in EXP-012): PROVEN exact at the Boolean-function level; whether any such substitution is faster is an implementation question, not a mathematical one.
3. A structurally different computation of the same function (different round decomposition, bitslicing across candidates, carry-save state representations): possible in principle wherever a representation change is accompanied by an exactness proof or exhaustive differential evidence over the affected sub-function; the lab's prior programme (EXP-019, EXP-027, EXP-033) closed several such shapes negatively at stated bounds and left exactly one shape (EXP-033's E2) unrefuted and inconclusive. Nothing in the 0.1.3 source itself suggests or contains any arrangement other than the direct one.

What is NOT possible, and is stated to bound the analysis: skipping rounds, skipping the second pass, or testing a prefix of the digest against the target before completing the hash, while still claiming the exact SHA256d semantics. The target comparison needs the complete 256-bit result, and no prefix of the compression determines any bit of the final digest (the feed-forward and the second pass mix all state words; see Deliverable 10, section 4: pass 2's state is fully nonce-mixed from round 3, and the same holds for any input bit).

## 7. Reproduction

`python3 research/phase001/RAW_RESULTS/sha256d_layout_verify.py` (padding bytes, block counts, genesis double hash, schedule and state witnesses) and `python3 research/phase001/RAW_RESULTS/taint_analysis.py` (the dependency accounting behind section 5).

## 8. Limitations

- Byte-order statements are made for little-endian hosts (the path the code takes when `detectlittleendian` is set, the case on every machine this lab runs). The big-endian branch is a direct pass-through and is analysed only by reading.
- The assert at line 2317 is a debug assertion; in a release build with NDEBUG it would not execute. The claim "the two paths agree" rests on the genesis recomputation and on hashlib agreement, not on the assert alone.
