# Mathematical Discovery: the SHA-256d Computation, Mapped

Every item is marked ESTABLISHED (proven or differentially
verified in this lab), HYPOTHESIS (registered, untested or
incompletely tested), or SPECULATION (no test design yet).
Derivations in full live in ../mathematical_foundations.md
and ../header_and_midstate_analysis.md; this document is
the map and the transformation space.

## 1. The computation (ESTABLISHED)

block_hash = SHA256(SHA256(header)), header = 80 bytes. A
candidate meets proof of work when the 32-byte result, read
as a little-endian 256-bit integer, is at most the target
decoded from nBits. Equality meets the target.

Hashing one header takes exactly three compression
evaluations, 192 rounds in total:

1. Inner block 1: header bytes 0..63 into the SHA-256
   initial state. Output: the midstate.
2. Inner block 2: header bytes 64..79, the 0x80 pad byte,
   zeros, and the 64-bit bit-length 640, into the midstate.
   Output: the inner digest.
3. Outer block: the 32-byte inner digest, 0x80, zeros, and
   the bit-length 256, into the initial state. Output: the
   candidate block hash.

Both messages are fixed length, so both paddings are
constants except for the data words themselves. There is
no streaming subtlety and no fourth compression.

## 2. Header layout and word map (ESTABLISHED)

| Bytes | Field | Block | Words |
|---|---|---|---|
| 0..3 | version | inner 1 | W0 |
| 4..35 | previous block hash | inner 1 | W1..W8 |
| 36..63 | merkle root, first 28 bytes | inner 1 | W9..W15 |
| 64..67 | merkle root, last 4 bytes | inner 2 | W0 |
| 68..71 | timestamp (nTime) | inner 2 | W1 |
| 72..75 | nBits | inner 2 | W2 |
| 76..79 | nonce, little-endian in the header | inner 2 | W3 |

Message words are big-endian, so block-2 W3 is the
byte-reversed nonce. Every lab path reproduces the genesis
hash at nonce 2083236893, which pins this convention down.
Block-2 padding words: W4 = 0x80000000, W5..W13 = 0,
W14 = 0, W15 = 640. Outer block: W0..W7 are the inner
digest words, W8 = 0x80000000, W9..W14 = 0, W15 = 256.

## 3. Round function anatomy (ESTABLISHED)

State: eight 32-bit words (a..h). Per round t, with message
word W_t and constant K_t, all additions mod 2^32:

    S1 = ROTR6(e) ^ ROTR11(e) ^ ROTR25(e)
    Ch = (e & f) ^ (~e & g)
    T1 = h + S1 + Ch + K_t + W_t
    S0 = ROTR2(a) ^ ROTR13(a) ^ ROTR22(a)
    Maj = (a & b) ^ (a & c) ^ (b & c)
    T2 = S0 + Maj
    (a..h) <- (T1+T2, a, b, c, d+T1, e, f, g)

Dependency structure, which drives all execution research:

- T1 depends on e, f, g, h (through S1 and Ch), W_t, K_t.
- T2 depends on a, b, c only.
- The next round's e is d + T1; the next round's a is
  T1 + T2. The critical path through one round is the S1
  rotation-xor chain into the T1 addition tree into the
  next round's e and a. Within one hash this chain is
  strictly serial: round t+1 cannot begin its T1 before
  round t's T1 exists. This is a property of the function
  definition, not of any implementation, and it is the
  mathematical reason independent-stream interleaving
  (H-01, EXP-003) is the large lever and within-round
  tricks are small ones.
- The state rotation is a renaming, not a computation:
  seven of the eight next-state words are copies of current
  words. Implementations that physically move them waste
  instructions; SHA-NI's operand layout and unrolled scalar
  code both rename instead (../round_optimization.md).

## 4. Message schedule (ESTABLISHED, with the W18 correction)

W_0..W_15 are the block's big-endian words. For t = 16..63:

    s0 = ROTR7(W_{t-15}) ^ ROTR18(W_{t-15}) ^ SHR3(W_{t-15})
    s1 = ROTR17(W_{t-2}) ^ ROTR19(W_{t-2}) ^ SHR10(W_{t-2})
    W_t = W_{t-16} + s0 + W_{t-7} + s1        (mod 2^32)

(Sigma definitions as in
../header_and_midstate_analysis.md, which states the FIPS
180-4 forms.)

Consequences, all verified in ../header_and_midstate_analysis.md:

- Only 16 schedule words are ever live; a circular buffer
  is exact (H-07).
- In block 2, rounds 0, 1, 2 consume W0 (merkle tail), W1
  (timestamp), W2 (nBits). Round 3 consumes W3, the nonce:
  the first round whose T1 is nonce-dependent.
- W3 IS the nonce, a direct message word. The first
  EXPANDED word (t >= 16) that depends on it is W18:
  W16 draws on W0, W1, W9, W14; W17 on W1, W2, W10, W15;
  W18 = sigma1(W16) + W11 + sigma0(W3) + W2, and the t-15
  input is W3. (An earlier revision said W19; corrected
  2026-11-14, indexing only.)
- The block-2 state after rounds 0..2 is a function of
  (midstate, merkle tail, timestamp, nBits) only. From
  round 3 on, every state word is nonce-dependent, so
  nothing later in block 2 and nothing in the outer hash
  is precomputable across nonces.

## 5. The precomputation ceiling (ESTABLISHED, proven)

Per candidate: 192 rounds. Template-invariant across all
nonces of one fixed template:

- Inner block 1: 64 rounds, once per template. Production
  already captures this (the midstate).
- Inner block 2 rounds 0..2: 3 rounds, once per template.

Ceiling: 67 of 192 rounds (about 34.9 percent) are
reusable. Per-nonce work can never fall below 125 rounds
(61 of block 2 plus 64 outer) by precomputation alone. The
outer hash admits zero cross-candidate reuse beyond its
constant initial state and padding words, because its
input is the fully nonce-dependent inner digest.

Production today pays 64 + 128N rounds for N nonces of one
template. The remaining precomputation headroom is exactly
3 rounds in 125 (about 2.4 percent of per-nonce work);
H-03 measured it as below this VM's noise floor
(EXP-002, INCONCLUSIVE), which closes the question
practically without refuting the identity.

Invariance classes (what a field change invalidates), from
../header_and_midstate_analysis.md: nonce-only changes
invalidate nothing precomputed; timestamp or nBits changes
cost the 3-round prefix; merkle root, prevhash, or version
changes invalidate block 1 and cost the full 67 rounds per
new template, still trivial against any nonce range.

## 6. Feed-forward and target comparison (ESTABLISHED)

Each compression adds its output wordwise (mod 2^32) into
the state it started from (the Davies-Meyer style
feed-forward SHA-256 uses). The candidate digest is the
outer compression's state after its own feed-forward,
serialized big-endian per word; the comparison reads those
32 bytes as a little-endian integer against the target.

Two consequences worth registering:

- The feed-forward is part of the function. No
  reformulation may drop or defer it across a compression
  boundary; the inner digest that feeds the outer hash is
  the post-feed-forward state.
- The comparison itself is over the finished digest only.
  Every digest word is a function of all 64 outer rounds
  plus the feed-forward, so no exact partial comparison
  exists (section 8).

## 7. The transformation space

### 7.1 Proven Boolean alternatives (ESTABLISHED equivalence, benefit HYPOTHESIS)

From ../boolean_equivalence.md, each proven three ways
(exhaustive 1-bit proof 8 of 8 rows, 1,000,000-sample
32-bit differential, z3 bit-vector UNSAT):

    Ch_alt(x,y,z)    = z ^ (x & (y ^ z))            3 ops vs 4
    Maj_alt_A(x,y,z) = (x & y) ^ (z & (x ^ y))      4 ops vs 5
    Maj_alt_B(x,y,z) = (x & (y ^ z)) ^ (y & z)      4 ops vs 5

Maj_alt_B's (y & z) term is independent of x and can issue
early. These forms can only matter where rounds are
evaluated outside SHA256RNDS2, which computes its own Ch
and Maj internally: the prefix rounds, a scalar round in a
hand kernel, and every round of a vector multi-buffer
design. Inside the production OpenSSL path they change
nothing, because the round internals are libcrypto's.
Registered as H-06; the X-series adds the vector-specific
and superoptimizer applications (X-027, X-094).

### 7.2 Addition structure (ESTABLISHED properties, HYPOTHESIS applications)

- Mod 2^32 addition is associative and commutative, so the
  T1 tree (h + S1 + Ch + K_t + W_t) may be regrouped
  freely. Pre-adding K_t + W_t is standard and is what the
  SHA-NI message operand carries. Regrouping alone has
  never shown a generated-code difference in this lab and
  is not, by itself, a hypothesis (../round_optimization.md).
- Carry-save and redundant representations (HYPOTHESIS,
  X-021, X-022): a five-operand addition can be evaluated
  as a carry-save tree with one final carry-propagate add,
  shortening the carry chain per round in software vector
  rounds; keeping state words in carry-save form across
  round boundaries is the hardware designer's version of
  the same idea. In SHA-NI rounds none of this is
  reachable (the instruction owns its adds). In vector
  multi-buffer rounds it is a real, untested design axis.
- ADX carry chains (H-18, OPEN, low prior): SHA-256 word
  adds are independent mod 2^32 adds with no cross-word
  carry, so adcx/adox parallelism has little to grip;
  rorx in BMI2 is the more plausible half of that entry.

### 7.3 Schedule reformulations (mixed status)

- MSG1/MSG2 generation (ESTABLISHED as the correct and
  fast construction): the H-02 kernel generates the entire
  schedule with SHA256MSG1 and SHA256MSG2 (whitepaper
  GENA/GENB, alignr supplying the W[i+9] terms), proven
  equivalent to the scalar recurrence by a twin build, and
  worth about 2.6x over the scalar schedule at equal
  rounds (EXP-002).
- Circular 16-word schedule (H-07, OPEN): exact, reduces
  live words in scalar and vector code.
- Partial evaluation of the schedule itself (HYPOTHESIS,
  X-024, X-080): in block 2, schedule inputs W0..W2 and
  W4..W15 are template constants, so expanded words W16
  and W17 are template constants too (W18 is the first
  nonce-dependent one), and the K+W message operands for
  rounds 0..17 can be precomputed whole per template. In
  the outer hash, W9..W14 are zero and W8, W15 are
  constants, so the earliest expanded outer words lose
  terms (X-023). These are exact identities of the same
  class as the midstate, bounded and small; their value is
  that they are free inside a hand kernel.
- GFNI affine forms (HYPOTHESIS, X-020): each schedule
  sigma is a GF(2)-linear map (rotations, shifts, and xors
  are all linear over GF(2)), so sigma0 and sigma1 are each
  expressible as a fixed 32x32 binary matrix action,
  implementable with GFNI affine instructions plus
  shuffles in a vector design. Equivalence is provable by
  the boolean_proof.py pattern extended with the SMT leg.

### 7.4 Rotations and shifts (ESTABLISHED costs, HYPOTHESIS variants)

- In scalar code a rotate by a constant is two shifts and
  an or, or one ror instruction (BMI2 rorx avoids flag
  and input clobbering).
- In AVX2 vector code a 32-bit rotate by a constant is
  shift, shift, or (3 ops); AVX-512 provides vprold (1 op),
  which is one of the two structural reasons the AVX-512
  multi-buffer family outranks the AVX2 one in expectation
  (X-031 vs X-033).
- Inside SHA-NI rounds, rotations are the instruction's
  internal business and not addressable.

### 7.5 State representations (HYPOTHESIS)

- The SHA-NI org form (two __m128i registers holding the
  eight words in the instruction's packing, renamed rather
  than rotated) is ESTABLISHED practice in this lab
  (bal_sha_intrin.c, shani_core.h). Shuffle elimination
  between round pairs by alternating orientation is
  X-012 and X-013.
- Vector lanes as state (multi-buffer): each 32-bit lane
  of a ymm or zmm register holds one word of one hash;
  8 or 16 hashes advance in lockstep. The state per hash
  is identical in structure; the dependency chain per hash
  is unchanged, but 8 or 16 independent chains issue
  together. That is the whole mechanism, and it is why the
  family is an execution hypothesis (Workstream B) with a
  mathematical identity of zero risk: the per-lane
  computation is bit-identical to the scalar one by
  construction, and still must be proven by differential
  test like everything else.
- Bitslicing (SPECULATION trending to refutation, X-029):
  transposing 32 hashes so each register holds one bit
  position across hashes makes rotations free (renaming)
  but turns every addition into a full-adder network;
  SHA-256's density of additions makes the op count
  explode. Registered so it can be bounded analytically
  once, cheaply, and closed.

### 7.6 Partial evaluation summary (ESTABLISHED bounds)

Everything template-invariant is worth exactly 67 rounds
(section 5). Everything else that looks like partial
evaluation is one of: schedule-operand precomputation
(section 7.3, rounds unchanged, operand preparation
moved), or a claim that fails section 8.

## 8. What cannot change (ESTABLISHED, permanent)

- The 192-round structure is the algorithm definition.
  Any equivalent computation graph still evaluates the
  same 192 round functions with the same dependencies;
  equivalence can change instruction mix, issue order
  across independent hashes, and operand preparation, and
  nothing else.
- No reduced-round or statistical shortcut exists at full
  rounds in any evidence this lab has produced. The lab's
  own bias curve (../results/RESEARCH.md): one-bit bias
  about 0.49 at 16 rounds, 0.08 at 20, indistinguishable
  from noise from 24 rounds on, against 64 rounds applied
  twice. Chain winners follow the geometric law. Registry:
  H-24 REJECTED, R-01.
- No lite screen can certify a candidate without the full
  computation: every output bit depends on all rounds
  (R-02).
- No partial target check can skip work: the most
  significant digest word is only known after the final
  outer round and the feed-forward (R-06, H-16, and the
  X-097 closure entry for its remaining variants).
- No schedule sharing across nonces beyond the
  template-fixed prefix: each nonce has a different W3,
  hence a different schedule from W18 on, and a different
  state from round 3 on (../message_schedule_research.md).
- Probabilistic filtering that can miss a valid block, and
  nonce-range skipping without a coverage proof, are
  banned by the programme rules outright, not merely
  unproven.

## 9. Open mathematical questions worth their cost

1. Minimal-op forms of the joint Boolean cone (Ch, Maj,
   S0, S1 evaluated together, sharing subterms) on AVX-512
   and on scalar code, by SMT-guided search (X-027).
2. Whether carry-save state across rounds shortens the
   vector round's critical path enough to measure (X-022).
3. Whether the GFNI form of the sigmas beats shift-based
   rotates anywhere outside the schedule (X-020).
4. The exact operand-precompute boundary in the outer
   hash: which expanded words lose terms from the constant
   padding words, counted once, in writing (X-023).
Each is cheap relative to kernel work and each either
feeds a kernel experiment or closes a recurring proposal.
