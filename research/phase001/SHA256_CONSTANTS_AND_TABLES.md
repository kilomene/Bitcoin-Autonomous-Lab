# Phase 001, Deliverable 7: SHA-256 Constants and Mathematical Tables

Project: NOVA SHA-X, Research Phase 001 (Bitcoin Genesis Engine Reverse Engineering), Wave 3.
Subject: the constants of the SHA-256 implementation shipped in Bitcoin v0.1.3, exactly as they appear in the source, and their mathematical origin, verified by exact recomputation.

Source under study: the verified v0.1.3 tree (see SOURCE_INVENTORY.md for provenance and per-file SHA-256). The SHA-256 code is NOT in a file named sha256.cpp. It lives in `src/sha.cpp` and `src/sha.h`, a public-domain extract of Crypto++ 5.5.2 (file headers, src/sha.cpp lines 1 to 5 and src/sha.h lines 1 to 5). All line numbers below are from those files unless another file is named.

Status labels used in this wave: SOURCE FACT (read directly from the 0.1.3 source, with file and line), PROVEN (derived here and checked by exact recomputation, script in RAW_RESULTS), STANDARD (standard mathematics or FIPS 180 definitions, derived independently of the source).

## 1. Where the constants live in the 0.1.3 source

Three places, three different storage forms:

| Constant set | Location | Storage form |
|---|---|---|
| SHA-256 initial state H(0) | src/sha.cpp lines 93 to 97, `SHA256::InitState` | A function-local `static const word32 s[8]`, copied to the caller's state array with `memcpy` |
| Round constants K[0..63] | src/sha.cpp lines 99 to 116 | A file-scope `static const word32 SHA256_K[64]` table, read by the round macro as `SHA256_K[i+j]` (line 132) |
| SHA-224 initial state | src/sha.cpp lines 87 to 91, `SHA224::InitState` | Same local-array form as H(0); SHA-224 reuses `SHA256::Transform` (src/sha.h line 147) |

So the round constants ARE a table in this version. What is embedded inline in code instead is the initial state (a literal array inside the InitState function body, not a named file-scope table). The tasking hypothesis "constants embedded inside the transform" is therefore only half right, and the precise split is: K is a table (lines 99 to 116), H(0) is an in-function literal (lines 93 to 97). The transform itself (lines 141 to 164) contains no numeric constants at all except through `SHA256_K`.

Exact source text, src/sha.cpp line 95:

```cpp
static const word32 s[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
```

## 2. The 8 initial state words

| i | H(0)[i] | Origin (STANDARD): first 32 bits of the fractional part of sqrt(p), p = i-th prime |
|---|---|---|
| 0 | 6a09e667 | sqrt(2) |
| 1 | bb67ae85 | sqrt(3) |
| 2 | 3c6ef372 | sqrt(5) |
| 3 | a54ff53a | sqrt(7) |
| 4 | 510e527f | sqrt(11) |
| 5 | 9b05688c | sqrt(13) |
| 6 | 1f83d9ab | sqrt(17) |
| 7 | 5be0cd19 | sqrt(19) |

PROVEN: RAW_RESULTS/constants_verify.py recomputes each word as `isqrt(p * 2^64) mod 2^32` (exact integer arithmetic; floor(sqrt(p) * 2^32) mod 2^32, no floating point anywhere) and compares against the literals parsed out of src/sha.cpp. Result: all 8 match (constants_verify.txt, "H0 match: True").

## 3. The 64 round constants

Definition (STANDARD): K[i] is the first 32 bits of the fractional part of the cube root of the i-th prime (i = 0..63, primes 2 through 311).

The table below is in source order, one row per 4 constants, exactly the source's own grouping (src/sha.cpp lines 100 to 115). Index i runs left to right, top to bottom; the prime for index i is the (i+1)-th prime (2, 3, 5, ..., 311), and constants_verify.txt lists every (index, prime, source value, recomputed value) quadruple individually.

```
428a2f98 71374491 b5c0fbcf e9b5dba5
3956c25b 59f111f1 923f82a4 ab1c5ed5
d807aa98 12835b01 243185be 550c7dc3
72be5d74 80deb1fe 9bdc06a7 c19bf174
e49b69c1 efbe4786 0fc19dc6 240ca1cc
2de92c6f 4a7484aa 5cb0a9dc 76f988da
983e5152 a831c66d b00327c8 bf597fc7
c6e00bf3 d5a79147 06ca6351 14292967
27b70a85 2e1b2138 4d2c6dfc 53380d13
650a7354 766a0abb 81c2c92e 92722c85
a2bfe8a1 a81a664b c24b8b70 c76c51a3
d192e819 d6990624 f40e3585 106aa070
19a4c116 1e376c08 2748774c 34b0bcb5
391c0cb3 4ed8aa4a 5b9cca4f 682e6ff3
748f82ee 78a5636f 84c87814 8cc70208
90befffa a4506ceb bef9a3f7 c67178f2
```

PROVEN: constants_verify.py recomputes every K[i] as `icbrt(p * 2^96) mod 2^32` (exact integer cube root; floor(cbrt(p) * 2^32) mod 2^32) for the first 64 primes and compares against the table parsed from the source. Result: 64 of 64 match, zero mismatches (constants_verify.txt, "K match: True", with the full per-index listing).

## 4. The SHA-224 initial state (present in the same file, unused by Bitcoin mining)

Source, src/sha.cpp line 89: {0xc1059ed8, 0x367cd507, 0x3070dd17, 0xf70e5939, 0xffc00b31, 0x68581511, 0x64f98fa7, 0xbefa4fa4}.

Origin (STANDARD, and a subtlety worth recording): these words are NOT floor(frac(sqrt(p)) * 2^32) for primes 9..16. They are the LOW 32 bits of floor(frac(sqrt(p)) * 2^64) for those primes, which makes them exactly the low halves of the SHA-384 initial state words in the same file (src/sha.cpp lines 251 to 259, e.g. first SHA-384 word 0xcbbb9d5dc1059ed8, low half 0xc1059ed8). PROVEN: constants_verify.py recomputes the 64-bit values by exact integer square root (`isqrt(p * 2^128) mod 2^64`), matches all 8 SHA-384 words, and the low halves match all 8 SHA-224 words ("H384 match: True", "H224 match: True"). A naive 32-bit recomputation disagrees, which is exactly the kind of detail a source-level audit exists to catch.

## 5. What else is in the file (scope note)

src/sha.cpp also contains SHA-1 (lines 24 to 84, Steve Reid's code), SHA-512 and SHA-384 (lines 251 to 554), and a commented-out alternative SHA-256 transform (lines 166 to 249, headed "smaller but slower"). None of these are used by the Bitcoin mining path. SHA-512's K table (80 words) and macros are structurally parallel to SHA-256's and are not part of this deliverable.

## 6. Reproduction

Run: `python3 research/phase001/RAW_RESULTS/constants_verify.py`. It parses the literals out of the untouched 0.1.3 source and compares them against exact-integer recomputations. Expected output tail: "H0 match: True", "H224 match: True", "H384 match: True", "K match: True".

## 7. Limitations

- The mathematical origin of the constants (square and cube roots of primes) is the FIPS 180 definition of SHA-256; the 0.1.3 source itself contains no comment stating it. The agreement is proven by recomputation, but the source's silence is recorded here rather than papered over.
- Nothing in this deliverable is a benchmark or an optimization. It is the constants layer of the baseline reconstruction.
