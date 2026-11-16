# SHA-256 Complete Mathematical Model

Stage 1 of the NOVA SHA-X Extreme Research mandate. This is a
consolidation document: it states the complete SHA-256 model
once, in one place, and points to the prior work that derived
or proved each part. It makes no new claims. The pure Python
reference implementation in `tools/sha256d_reference.py`
implements exactly this model and is differentially verified
in SHA256D_DIFFERENTIAL_VERIFICATION.md.

## 1. Arithmetic setting

All state and schedule quantities are 32-bit words. Addition
is modulo 2^32. Bitwise operations are per-bit. ROTR^n is a
right rotation by n bits; SHR^n is a logical right shift.

## 2. Boolean and rotation functions

- Ch(x, y, z) = (x AND y) XOR ((NOT x) AND z)
- Maj(x, y, z) = (x AND y) XOR (x AND z) XOR (y AND z)
- Sigma0(x) = ROTR^2(x) XOR ROTR^13(x) XOR ROTR^22(x)
- Sigma1(x) = ROTR^6(x) XOR ROTR^11(x) XOR ROTR^25(x)
- sigma0(x) = ROTR^7(x) XOR ROTR^18(x) XOR SHR^3(x)
- sigma1(x) = ROTR^17(x) XOR ROTR^19(x) XOR SHR^10(x)

Settled results on these functions (do not re-derive):

- EXP-012 (research/sha256d/): the VPTERNLOGD immediates are
  unique, Ch = 0xCA, Maj = 0xE8, XOR3 = 0x96, and the classic
  operation counts are minimal: Ch costs 3 classic Boolean
  operations, Maj costs 4. Proven three ways (exhaustive
  evaluation, 1M-sample differential, z3 UNSAT).
- The alternative forms Ch_alt, Maj_alt_A and Maj_alt_B are
  exactly equivalent to the definitions above (proven three
  ways; research/sha256d/mathematical_foundations.md).
- EXP-033 (research/sha256d/exp033/): over the instruction
  set {ADD, LUT with any immediate, ROTR, SHR}, Sigma0 and
  Sigma1 each have an exact minimum of 4 instructions; the
  cone-conditioned synthesis for both Sigma cones is UNSAT
  below that bound.
- EXP-042 (research/sha256d/exp042/): the last unrefuted
  cone shape (E2, routing a Sigma output through the Maj or
  Ch value) is refuted at its stated bounds; the cone minimum
  stands at 6 under those bounds.

## 3. Constants

- H(0), the initial state: 8 words, the first 32 bits of the
  fractional parts of the square roots of the first 8 primes
  (2, 3, 5, 7, 11, 13, 17, 19). H(0)[0] = 0x6a09e667.
- K[0..63], the round constants: the first 32 bits of the
  fractional parts of the cube roots of the first 64 primes.
  K[0] = 0x428a2f98, K[63] = 0xc67178f2.

Phase 001 derived all 72 constants from the prime roots by
exact recomputation with zero mismatches, and located them
in the Bitcoin v0.1.3 source (K as a table at src/sha.cpp
lines 99 to 116; H(0) as a literal array inside InitState at
lines 93 to 97): research/phase001/
SHA256_CONSTANTS_AND_TABLES.md. The reference implementation
derives both sets at import time by exact integer arithmetic
(isqrt and integer cube root over scaled integers) rather
than embedding a copied table.

## 4. Message schedule

The 64-byte block is loaded as 16 big-endian words
W[0..15] = M[0..15]. For t from 16 to 63:

W[t] = sigma1(W[t-2]) + W[t-7] + sigma0(W[t-15]) + W[t-16]
       (mod 2^32)

Dependency structure of this recurrence is consolidated in
MESSAGE_SCHEDULE_DEPENDENCY_GRAPH.md.

## 5. Compression

State is 8 words (a, b, c, d, e, f, g, h), initialized to
H(0) for the first block or to the incoming state for later
blocks. For t from 0 to 63:

- T1 = h + Sigma1(e) + Ch(e, f, g) + K[t] + W[t] (mod 2^32)
- T2 = Sigma0(a) + Maj(a, b, c) (mod 2^32)
- (a, b, c, d, e, f, g, h) becomes
  (T1 + T2, a, b, c, d + T1, e, f, g)

Feed-forward: after 64 rounds, each state word is added
(mod 2^32) to the corresponding incoming state word. The
result is the outgoing state.

Settled result on the round as a whole: EXP-020
(research/sha256d/) proved the full round optimal at 28
vector operations within its searched vocabulary (SMT lower
bound 28); EXP-041 later showed the one-operation gap in
the production v512 kernel (29 emitted) is an established
null for performance on this VM, and the production
DualMask search body already emits 28. EXP-027 closed the
named outside-vocabulary spaces (carry-save beyond the
schedule, GFNI affine forms, rotated or byte-swapped state,
IFMA accumulation) at their stated scopes.

## 6. Padding and length encoding

For a message of length L bytes: append 0x80, then zero
bytes until the length is 56 mod 64, then L x 8 as a 64-bit
big-endian integer. The padded message is processed in
64-byte blocks; the digest is the final state serialized as
8 big-endian words (32 bytes).

## 7. SHA-256d

SHA-256d(M) = SHA-256(SHA-256(M)). Bitcoin uses it for block
hashes, TXIDs and WTXIDs. The three-compression structure of
SHA-256d over an 80-byte header, and exactly which parts are
reusable across nonces, is the subject of
SHA256D_PIPELINE_RECONSTRUCTION.md.

## 8. What this model does not claim

The model is the FIPS 180-4 definition restated. Nothing in
it asserts a lower bound on the cost of computing SHA-256 by
an equivalent graph; the programme's own correction on that
point (the conventional reusable-round count is not a proven
universal lower bound) is recorded in
research/sha256d/phase6/OPEN_PROBLEMS.md (OP-1) and carried
through SHA256D_PIPELINE_RECONSTRUCTION.md.
