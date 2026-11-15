# SHA-256d Mathematical Specification

NOVA SHA-X Master Assignment, work package BR-003 (exact SHA-256d).
This is the complete, exact specification of the function Bitcoin
mining computes: SHA256d over the 80-byte block header. It is a
specification, not an implementation and not a benchmark: it states
what must be computed, bit for bit, and records the programme's
proven knowledge about the structure of that computation.

Primary sources, all in this repository: research/phase001/
SHA256_CONSTANTS_AND_TABLES.md, SHA256_COMPRESSION_RECONSTRUCTION.md,
MESSAGE_SCHEDULE_ANALYSIS.md, STATE_DEPENDENCY_MAP.md and
SHA256D_RECONSTRUCTION.md (the v0.1.3 reconstruction, every equation
verified against FIPS vectors and the genesis block);
research/sha256d/exp033/MATHEMATICAL_INVESTIGATION.md and
research/sha256d/phase6b/EXP027_COMPUTATION_REPRESENTATIONS.md (the
closed/open status map); EXP-016 and EXP-020 records under
research/sha256d/.

Tier labels, used throughout the programme: a statement is PROVEN
when it is an exact identity, a solver-verified fact, or an exact
recomputation; MEASURED when the programme benchmarked it under the
EXP-017 protocol (cited, never restated as a new measurement here);
ESTABLISHED NEGATIVE when a direction is refuted or closed at a
stated bound; UNPROVEN BREAKTHROUGH for the one shape that remains
unrefuted without evidence. Nothing in this document is a hash rate.

## 1. The function

```
SHA256d(header) = SHA256(SHA256(header))
```

where header is the exact 80-byte serialization specified in
research/bitcoin_reverse_engineering/BLOCK_HEADER_SERIALIZATION_
SPECIFICATION.md. SHA-256 is FIPS 180-4 SHA-256: 32-bit words, all
additions modulo 2^32, the compression function of section 3 below
applied to each 64-byte chunk with the padding of section 5.

Chunk accounting (PROVEN, Phase 001 Deliverable 11, verified by
recomputation):

| Pass | Input | Bytes | 64-byte chunks | Rounds |
|---|---|---|---|---|
| 1 | block header | 80 | 2 | 128 |
| 2 | pass-1 digest | 32 | 1 | 64 |
| total | | | 3 | 192 |

A candidate is a success exactly when the 256-bit result, read as
an unsigned integer, satisfies hash <= T for the target T decoded
from the header's nBits (research/proof_of_work/PROOF_OF_WORK_AND_
DIFFICULTY_SPECIFICATION.md). The comparison needs the complete
digest; no prefix of the computation decides any digest bit
(section 8, early exit).

## 2. Constants and their mathematical origin

Initial state H(0), the first 32 bits of the fractional parts of
the square roots of the first 8 primes (2, 3, 5, 7, 11, 13, 17, 19):

```
6a09e667 bb67ae85 3c6ef372 a54ff53a 510e527f 9b05688c 1f83d9ab 5be0cd19
```

Round constants K[0..63], the first 32 bits of the fractional parts
of the cube roots of the first 64 primes (2 through 311), in order:

```
428a2f98 71374491 b5c0fbcf e9b5dba5 3956c25b 59f111f1 923f82a4 ab1c5ed5
d807aa98 12835b01 243185be 550c7dc3 72be5d74 80deb1fe 9bdc06a7 c19bf174
e49b69c1 efbe4786 0fc19dc6 240ca1cc 2de92c6f 4a7484aa 5cb0a9dc 76f988da
983e5152 a831c66d b00327c8 bf597fc7 c6e00bf3 d5a79147 06ca6351 14292967
27b70a85 2e1b2138 4d2c6dfc 53380d13 650a7354 766a0abb 81c2c92e 92722c85
a2bfe8a1 a81a664b c24b8b70 c76c51a3 d192e819 d6990624 f40e3585 106aa070
19a4c116 1e376c08 2748774c 34b0bcb5 391c0cb3 4ed8aa4a 5b9cca4f 682e6ff3
748f82ee 78a5636f 84c87814 8cc70208 90befffa a4506ceb bef9a3f7 c67178f2
```

Status: PROVEN. Phase 001 recomputed all 72 words by exact integer
arithmetic (isqrt(p * 2^64) mod 2^32 for H(0); icbrt(p * 2^96) mod
2^32 for K) against the literals in the v0.1.3 source (src/sha.cpp
lines 93 to 116): zero mismatches. These are nothing-up-my-sleeve
constants; there is no freedom in them and no programme result
depends on choosing them.

## 3. The compression function

One chunk: 16 big-endian message words M[0..15] (section 6 for byte
order), an 8-word state (a, b, c, d, e, f, g, h), 64 rounds.

Auxiliary functions (all operations on 32-bit words):

```
S0(x) = ROTR^2(x)  XOR ROTR^13(x) XOR ROTR^22(x)
S1(x) = ROTR^6(x)  XOR ROTR^11(x) XOR ROTR^25(x)
s0(x) = ROTR^7(x)  XOR ROTR^18(x) XOR SHR^3(x)      (schedule only)
s1(x) = ROTR^17(x) XOR ROTR^19(x) XOR SHR^10(x)     (schedule only)
Ch(e,f,g)  = g XOR (e AND (f XOR g))
           = (e AND f) XOR ((NOT e) AND g)          (equivalent form)
Maj(a,b,c) = (a AND b) OR (c AND (a OR b))
           = (a AND b) XOR (b AND c) XOR (c AND a)  (equivalent form)
```

The two Ch forms are bit-identical and the two Maj forms are
bit-identical (PROVEN identities, standard Boolean algebra; the
first of each pair is the form the v0.1.3 macros use, src/sha.cpp
lines 120 to 121, and the form modern Core uses; the three-input
logic encodings Ch = 0xCA and Maj = 0xE8 for VPTERNLOGD were
verified by the programme in EXP-012).

Round t (t = 0..63), with W_t and K_t from sections 2 and 4:

```
T1 = h + S1(e) + Ch(e,f,g) + K_t + W_t        (mod 2^32 throughout)
T2 = S0(a) + Maj(a,b,c)
(a,b,c,d,e,f,g,h) := (T1 + T2, a, b, c, d + T1, e, f, g)
```

Feed-forward (Davies-Meyer): after round 63, the working state is
added wordwise, mod 2^32, into the incoming state; that sum is the
chunk's output state. The initial state of a pass is H(0); the
initial state of chunk 2 of pass 1 is chunk 1's output state (the
midstate, section 7); the output state of the last chunk, written
as eight big-endian words, is the pass digest.

Operation census of the round as specified (a transcription, not a
measurement): T1 is a five-operand sum (4 binary adds), T2 a
two-operand sum, plus one add each for the new a and the new e: 7
word additions in the round function proper, plus 4 in the schedule
expansion for rounds 16 to 63. Under the programme's vector cost
model, EXP-020 proved the joint round-plus-schedule cost optimal at
28 vector operations within its searched vocabulary {VPADDD,
VPTERNLOGD, classic bitwise, VPROLD, VPSRLD}; production code emits
29, a known compiler codegen gap, not a mathematical one (EXP-033
section 5 records it as unchanged by that phase).

## 4. The message schedule

```
W[i] = M[i]                                                   0 <= i <= 15
W[i] = s1(W[i-2]) + W[i-7] + s0(W[i-15]) + W[i-16]            16 <= i <= 63
```

all additions mod 2^32. Dependency lags are 2, 7, 15 and 16. The
v0.1.3 code evaluates this recurrence in a 16-word circular buffer
with an in-place += (src/sha.cpp line 118); the regrouping is an
exact identity by associativity and commutativity of mod-2^32
addition (PROVEN, Phase 001 Deliverable 9). The sigma maps s0, s1,
S0, S1 are GF(2)-linear maps on the word (XORs of rotations and
shifts only); the schedule recurrence is not linear, because of its
modular additions (section 7.3).

## 5. Padding

Standard FIPS padding: append 0x80, then zero bytes, then the
message bit length as an 8-byte big-endian integer, to a multiple
of 64 bytes. For the two passes of SHA-256d on a header the padded
forms are exact and fixed:

Pass 1 (80 bytes to 128): byte 80 is 0x80; bytes 81 to 119 are
zero; bytes 120 to 123 are zero (high half of the length field);
bytes 124 to 127 are 00 00 02 80 (640 bits).

Pass 2 (32 bytes to 64): byte 32 is 0x80; bytes 33 to 55 are zero;
bytes 56 to 59 are zero; bytes 60 to 63 are 00 00 01 00 (256 bits).

PROVEN byte-identical to the standard padding (Phase 001
Deliverable 11, section 3.2, recomputed). Historical note with
specification force: the v0.1.3 miner hand-rolled this padding
(FormatHashBlocks, src/main.cpp lines 2138 to 2151), writing only
the low 4 bytes of the length field and relying on a preceding
memset for the high 4; the result is identical for any message
shorter than 2^32 bits, which covers every Bitcoin use, but a
specification must state the full 8-byte field, as above.

## 6. Byte order at every boundary

Byte order is where informal descriptions of SHA-256d most often go
wrong, so every boundary is stated:

1. **Header bytes to pass-1 words.** The 80 header bytes are taken
   in order; each consecutive 4 bytes form one word big-endian
   (first byte most significant). Header bytes 0 to 63 are chunk 1
   (words M[0..15]); bytes 64 to 79 are chunk 2 words M[0..3],
   followed by the padding words of section 5 (M[4] = 0x80000000,
   M[5..14] = 0, M[15] = 640).
2. **Inside the compression.** Words are 32-bit integers; rotations
   and shifts are on the integer value. There is no byte order
   inside a word once loaded.
3. **Pass-1 digest to pass-2 input.** The digest is the byte string
   formed by writing the eight output state words big-endian, in
   order. Pass 2 consumes exactly those 32 bytes, loaded big-endian
   as its M[0..7], followed by padding (M[8] = 0x80000000,
   M[9..14] = 0, M[15] = 256). No reversal, no reinterpretation:
   the intermediate digest is an opaque byte string between the
   passes. (The v0.1.3 miner's BlockSHA256 byte-reverses its output
   state words precisely so that its in-memory buffer holds this
   same byte string; Phase 001 Deliverable 11, section 3.3.)
4. **Final digest to integer.** The block hash as an integer is the
   final 32-byte digest read big-endian (equivalently: the
   displayed hex string read as a hexadecimal number). Bitcoin's
   uint256 storage holds the byte-reversed (internal) order and
   displays reversed; the comparison hash <= T is on the integer,
   and is identical under either storage convention as long as both
   operands use the same one (PoW specification, section 3;
   research/bitcoin_core/POW_DIFFICULTY_SOURCE.md section 2 on
   UintToArith256).
5. **Header fields inside the header bytes** are little-endian
   integers and internal-order hashes; that is a property of the
   header serialization, specified in the companion serialization
   specification, and it does not interact with the big-endian word
   loading here: the compression sees bytes, not fields.

## 7. Nonce-dependence structure (the mining-relevant mathematics)

Fix a template: every header byte except the 4 nonce bytes (header
bytes 76 to 79) is fixed. The nonce is therefore chunk 2 word W[3]
of pass 1, and chunk 1 contains no nonce at all.

### 7.1 Schedule dependence (PROVEN, two independent methods)

From the lags of section 4 applied to the single tainted input
W[3] (Phase 001 Deliverables 9 and 10: symbolic taint computation,
plus a numeric witness on the genesis header, one nonce bit
flipped, differing words exactly {3} union {18..63}):

- W[16] and W[17] are nonce-independent.
- **W[18] is the first nonce-dependent expanded schedule word**,
  reached through the lag-15 term: W[18] = s1(W[16]) + W[11] +
  s0(W[3]) + W[2], and for a fixed template the entire nonce
  influence on W[18] is the single additive term s0(nonce).
- W[19] carries the nonce only through its final additive term,
  the nonce word itself: W[19] = s1(W[17]) + W[12] + s0(W[4]) +
  W[3].
- Every W[i] for i >= 18 is nonce-dependent.

EXP-016 established the same boundary independently, and EXP-033
re-derived and strengthened the two single-term facts to proofs:
the XOR delta of W[18] under a nonce change is exactly
s0(nonce-delta structure) (in EXP-033's notation, D(W18) =
sigma0(nonce) and D(W19) = nonce), holding on 100,000 of 100,000
random samples and proven with z3 over fully symbolic template
words.

### 7.2 State dependence (PROVEN, same methods)

Pass 1, chunk 1: no state word at any round depends on the nonce.
Its output state, the **midstate**, is a pure function of header
bytes 0 to 63.

Pass 1, chunk 2 (incoming state is the midstate, nonce-free):
rounds 0 to 2 leave every state word nonce-free; round 3 (the
round that consumes W[3]) marks exactly {a, e}; round 4 marks
{a, b, e, f}; round 5 marks {a, b, c, e, f, g}; from round 6 on,
all 8 state words are nonce-dependent (saturation). After
feed-forward, all 8 pass-1 digest words are nonce-dependent.

Pass 2: every message word is a pass-1 digest word, hence
nonce-dependent; the state is fully nonce-mixed from round 3 and
in substance from the start. No part of pass 2 is reusable across
candidates (PROVEN by taint; independently confirmed by EXP-033's
digest taint: all 48 computed outer schedule words are
digest-dependent and the number of digest-independent complete
outer rounds is 0).

### 7.3 Where linearity ends (PROVEN)

The nonce's influence is exactly linear for precisely two expanded
words: after 3 rounds of chunk 2, state words a and e are
integer-affine in the nonce with slope 1 (z3-proven, EXP-033). At
W[20] linearity ends: the claim that the W[20] XOR delta is
GF(2)-linear in the nonce delta is REFUTED by a z3 counterexample
(EXP-033 section 3.1, model re-verified numerically). W[20] is the
first schedule word whose nonce dependence is fully nonlinear
(EXP-016), and every later word inherits nonlinearity through the
recurrence's modular additions. Consequence, stated as the
programme's standing result: there is no linear-algebraic
representation of the schedule past W[19], and no exact shortcut
down that path.

### 7.4 The 67 of 192 accounting, with its exact status

Per template, the conventional implementation computes once: all
64 rounds of pass 1 chunk 1, plus rounds 0 to 2 of chunk 2 (whose
state evolution is nonce-free), totalling 67 of the 192 rounds.
Per candidate it must compute the remaining 61 rounds of chunk 2
and all 64 rounds of pass 2, totalling 125.

Status, stated with the precision EXP-033 established: **this is
an accounting of the conventional implementation, not a lower
bound.** It is re-derived from the taint boundary (the nonce
enters at W[3], first consumed in round 3; W[18] is the first
expanded word it touches). Nothing in the programme turns it into
a universal bound on all possible computations of SHA-256d, and no
document may cite 125 rounds per candidate as a proven minimum
work. What is proven is narrower and still useful: within the
dependency structure, no part of pass 2 and no nonce-dependent
part of chunk 2 can be computed before the nonce is fixed, and the
midstate (plus the 3 fixed rounds after it) is the complete
template-invariant prefix of the conventional dataflow.

Historical note: the v0.1.3 miner did not take even this
accounting. It recomputed chunk 1 from H(0) for every candidate
(BlockSHA256 calls InitState per candidate; Phase 001 Deliverable
11, section 5): 64 of its 192 rounds per candidate were provably
template-constant and were recomputed anyway. Modern production
(NOVA included) caches the midstate; that is an exact identity
(caching a pure subexpression), not an approximation.

## 8. Closed and open mathematical status map

The map below consolidates EXP-020, EXP-027 and EXP-033. Each entry
carries its bound; a closure is valid only at its stated scope.

### 8.1 Proven optima and identities (PROVEN)

- The joint round-plus-schedule cost is optimal at 28 vector ops
  within the EXP-020 searched vocabulary; Sigma0 and Sigma1 each
  have minimum exactly 4 instructions over the vocabulary
  {ADD, LUT(any immediate), ROTR, SHR} given the produced word and
  arbitrary independent side values (EXP-033 CEGIS UNSAT at length
  3, incumbents proven exact). The cone-conditioned form of the
  same question (exploiting the correlation s = T1 + T2, shape E1)
  is also UNSAT for both cones: the Sigma sub-DAG needs at least 4
  instructions unconditionally.
- Ch and Maj alternative forms (section 3) are exact identities;
  their VPTERNLOGD encodings (0xCA, 0xE8) are proven (EXP-012).
- Addition counting floors: a five-operand sum needs at least 4
  binary adds and a four-operand sum at least 3; the incumbents
  achieve both (EXP-027 C5, EXP-020 BFS agrees).

### 8.2 Established negatives (ESTABLISHED NEGATIVE, at stated scope)

- **Non-sharing cross-round graph restructuring** in the R1 to R6
  word-level rewrite system: e-graph equality saturation found no
  cheaper graph for the two-round round function (converged to a
  fixed point in the rounds-only case; the joint rounds-plus-
  schedule case hit its class cap with identical extraction costs,
  so the joint statement is bounded by that cap). EXP-033.
- **Carry-save and redundant representations across the round
  boundary**: every word produced by an addition is consumed
  bitwise in the very next round and arithmetically 3 rounds
  later; the deferral distance of every round addition is exactly
  0, and a software 3:2 compressor costs 3 instructions against
  the adds it would save. EXP-027 C4, EXP-033 section 2.4,
  EXP-019 (schedule pricing).
- **GFNI affine forms**: the sigma maps are GF(2)-linear (proven)
  but any GFNI construction costs at least 11 ops against the
  4-op incumbent; Ch and Maj are not GF(2)-affine at all
  (counterexamples). EXP-027 C1.
- **VPSHUFB rotations**: pure shuffle forms refuted exhaustively;
  the mixed form is exact but measured at 2.00x the VPROLD price
  (an EXP-019-style form price, labelled as such). EXP-027 C2.
- **Rotated and byte-swapped state domains**: refuted by
  counterexample (neither commutes with addition). EXP-027 C3.
- **Bitsliced state**: closed by measurement in EXP-015 (about
  0.03x of the multi-buffer kernel).
- **Cross-round subterm sharing**: census 0 nontrivial shared
  subterms across the round boundary. EXP-027 C6.
- **Outer-hash precomputation and partial execution**: 0
  digest-independent outer rounds; no part of the outer
  compression can be computed before the inner digest exists.
  EXP-027 C6, EXP-033 section 3.3.
- **Comparison early exit**: no proper prefix of the outer rounds
  determines any digest word (every digest word is a feed-forward
  sum over the final state), so early exit can save comparisons,
  never rounds. EXP-033 section 3.4.
- **K+W folding** (EXP-014) and the **GF(2)-linear schedule**
  (section 7.3) are likewise closed.

### 8.3 The one open shape (UNPROVEN BREAKTHROUGH)

**E2: Maj-routed (resp. Ch-routed) Sigma.** The cone accounting of
section 8.1 (1 instruction producing the new state word, at least
4 in the Sigma sub-DAG, at least 1 producing Maj or Ch, totalling
the incumbent 6) bounds 5 only if the Maj/Ch instruction sits
outside the Sigma sub-DAG. If the Sigma output is routed through
the Maj (resp. Ch) value, so the Boolean instruction sits inside
the Sigma sub-DAG, the accounting does not exclude a 5-instruction
cone. Status, exactly as EXP-033 left it: shape E1 (correlation
exploitation) is EXCLUDED for both cones; shape E2 is unrefuted
for both cones; the direct full-cone synthesis attack at length 5
was INCONCLUSIVE (solver timeout at the stated bound, not a proof
in either direction). No program of the E2 shape is known. Its
ceiling, if it exists, is at most about 2 ops per round across
both cones. It is labelled UNPROVEN BREAKTHROUGH: plausible only
in the sense of not yet refuted, with no evidence of a rate, and
it must never be reported as an improvement, a finding of fact
about SHA-256d's true cost, or progress toward any throughput
target.

### 8.4 Explicitly untouched territory

EXP-033 records, and this specification repeats: restructuring in
models outside the searched bounds (bit-level circuits with
cross-word carry structure not expressible as word operations,
fusion across more than two rounds, vocabularies with vector
rotates or funnel shifts as single ops) is unsearched and remains
UNPROVEN BREAKTHROUGH territory. Reduced-round cryptanalysis
results (output bias measurable at 16 to 20 rounds, gone by 24)
characterize the safety margin of the full 64-round construction;
they are not results about the full-round function and are never
cited as such anywhere in this programme.

## 9. Relationship to benchmark categories

This specification defines the function that the Master
Assignment's benchmark categories measure at different scopes:
category C is exactly this function over the 80-byte header;
category D adds midstate reuse (section 7.4) and the target
comparison; category B is this function over arbitrary input.
A rate measured for one category is not a rate for another, and
in particular no number in this document is a rate at all.

## 10. Reproduction

- Constants: research/phase001/RAW_RESULTS/constants_verify.py.
- Round equations, padding, genesis double hash:
  research/phase001/RAW_RESULTS/sha256d_layout_verify.py.
- Taint maps: research/phase001/RAW_RESULTS/taint_analysis.py.
- Status map: EXP-033 PROOFS/ and RAW_RESULTS/ (z3 artifacts,
  e-graph saturation outputs, synthesis gates) and EXP-027's
  proofs and records files, all under research/sha256d/.
