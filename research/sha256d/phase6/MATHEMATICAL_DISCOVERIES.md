# Phase 6, Mathematical Discoveries

Scope: exact mathematical structure of SHA-256d as
it bears on computation-graph research. Every result
here is labelled by its evidence class: PROVEN
(formal proof artifact in proofs/), DERIVED
(symbolic computation, reproducible from src/),
MEASURED (differential experiment), or CONJECTURE.
Nothing in this document is a performance claim.

## MD-1. Nonce dependency in block 2, derived exactly (EXP-016)

Status: DERIVED and PROVEN in parts. Tool:
src/nonce_dependency.py. Raw results:
analysis/exp016_dependency_results.json. Proof
results: proofs/exp016_z3_results.json. Date:
2026-11-14.

### Question

Fix a block-2 template (the standard mining shape:
112-byte header, nonce in word W3 of block 2, all
other words fixed). For every schedule word W_t,
t >= 16, and every state word after every round,
determine exactly how the word depends on the 32-bit
nonce n: independent (IND), integer-affine
n -> C + n mod 2^32 (AFF), XOR-linear in n (LIN), or
genuinely nonlinear (NONLIN); and, for the delta map
D_t(n) = W_t(n) - W_t(0) mod 2^32, whether D_t is
XOR-linear, which is the form Y-065's proposed
separation W_t = C_t + L_t(n) requires.

### Method (reproducible)

Four legs, all in src/nonce_dependency.py:

1. A pure-Python reference SHA-256, verified
   bit-exact against hashlib on random messages and
   on the header, inner, and outer shapes used by
   the production miner. The derivation is only as
   good as this leg; it passes.
2. Sound per-bit influence masks. Each bit is
   tracked as the set of nonce bits that may
   influence it. XOR, rotations, shifts, Ch, Maj and
   the small sigmas are exact set operations
   (rotations and shifts permute the sets). Integer
   addition uses the standard sound carry bound:
   output bit i may depend on every input bit at
   positions <= i from both operands, because a
   carry generated at any lower position can reach
   it. A mask is therefore an over-approximation:
   a bit shown independent is independent; a bit
   shown dependent may depend. Completeness claims
   below are stated in terms of these masks and are
   cross-checked by leg 3's sampling.
3. Sampled functional classification. For three
   random templates, each word is evaluated at many
   nonces and classified: IND if constant; AFF if
   word(n) - word(0) equals n for all samples; LIN
   if the map is GF(2)-affine; NONLIN otherwise.
   Separately, the delta map D_t is tested for
   XOR-linearity on 300 random pairs per word:
   violation rate = fraction of pairs with
   D(n1 xor n2) != D(n1) xor D(n2).
4. z3 bit-vector proofs for the boundary cases
   (solver in the repo-local z3 environment):
   round-3 a and e are exactly C + n; the W18 delta
   is exactly sigma0(n); the W19 delta is exactly n;
   and the W20 delta is NOT XOR-linear, shown by a
   satisfying counterexample that leg 4 then
   re-verifies numerically in the reference
   implementation.

### Schedule words: the derivation

Definitions: s0(x) = ROTR7(x) xor ROTR18(x) xor
SHR3(x); s1(x) = ROTR17(x) xor ROTR19(x) xor
SHR10(x); W_t = s1(W_{t-2}) + W_{t-7} + s0(W_{t-15})
+ W_{t-16} mod 2^32. The nonce is W3 itself.

- W16 (inputs W0, W1, W9, W14) and W17 (inputs W1,
  W2, W10, W15): no nonce input. IND. (Consistent
  with the established precomputation boundary.)
- W18 = s1(W16) + W11 + s0(W3) + W2. Only s0(W3)
  (the W_{t-15} slot) carries the nonce, and s0 is
  XOR-linear. The
  delta is exact: D_18(n) = s0(n). z3: UNSAT for
  the negation (proven). Raw sampled class: NONLIN
  as a raw function, because the word is a constant
  plus s0(n) under integer addition; the delta,
  which is what a separation uses, is exactly
  XOR-linear. Influence mask: union 32 nonce bits,
  16 bits fully dependent.
- W19 = s1(W17) + W12 + s0(W4) + W3, with the nonce
  entering as W3 itself through the W_{t-16} slot:
  W19 = (nonce-free terms) + n under integer
  addition, so D_19(n) = n exactly. Sampled class
  AFF; z3: UNSAT for the negation (proven).
  Influence mask: union 32 bits, 1 bit fully
  dependent (bit 31, reached only through the carry
  chain), exactly the signature of a bare addition.
- W20 = s1(W18) + W13 + s0(W5) + W4. Here the
  nonce-dependent word W18 passes through an
  integer addition and then s1 mixes the sum's bits
  across positions. The carry coupling inside that
  addition makes the delta genuinely nonlinear:
  delta-linearity violation rate 1.0 (every one of
  300 sampled pairs violates), and z3 produced a
  concrete counterexample, verified numerically in
  the reference implementation: for the recorded
  template, n1 = 539234578, n2 = 1283462784 give
  D_20(n1 xor n2) = 43171369 while
  D_20(n1) xor D_20(n2) = 3724592575. W20 is also
  the first schedule word whose influence mask is
  fully dependent on all 32 bits (32 of 32).
- W21 onward: violation rate 1.0 at every word
  tested (W21 to W25); masks are full (W21 has 20
  fully-dependent bits by the sound bound, 32 from
  W22). No later word recovers a linear or affine
  delta: each recurrence step adds at least one
  more carry-coupled addition of an already
  nonlinear word.

Result (schedule): a separation W_t = C_t + L_t(n)
with L_t cheap exists exactly for t = 18 and t = 19,
and at neither word does it save work: forming W18
still costs its defining addition, and W19's affine
form is the addition itself. From W20 the nonce's
influence is carry-coupled and complete.

### State words: the derivation

Write S_r for the state (a, b, c, d, e, f, g, h)
after r rounds of block 2 (S_0 is the midstate;
the nonce word W3 is consumed by round r = 3, using
0-based round indexing throughout this document).

- S_0 to S_3: all eight words IND (the nonce has
  not been consumed yet; this is the established
  prefix).
- S_4 (after the round that consumes W3): a and e
  are AFF, exactly C + n mod 2^32; z3 UNSAT proofs
  for both words. The other six words are IND (they
  are the shifted midstate). Influence: union 32
  bits, 1 fully-dependent bit (bit 31 via carries).
  The single-bit flip signature measured on a and e
  is the addition signature: diagonal mean 1.0,
  below-diagonal max 0.0, above-diagonal mean 0.066
  (occasional carry propagation upward, never
  downward influence).
- S_5: a and e NONLIN (round 4 applies Ch, Maj,
  Sigma0, Sigma1 to the affine pair; the Boolean
  functions act bit-wise on carry-mixed bits, and
  the result is no longer affine in n by either
  sampled class or structure). b and f are AFF:
  they are the previous round's a and e, shifted
  into place unmodified. c, d, g, h IND. The a and
  e influence masks jump to 26 fully-dependent
  bits.
- S_6: c and g become AFF (the same unmodified
  copies, one shift later); d, h still IND; the
  rest NONLIN. a and e reach 32 fully-dependent
  mask bits.
- S_7: d and h become AFF (last unmodified copies);
  everything else NONLIN. Empirical sensitivity
  (every state bit observed to flip under some
  single-bit nonce flip, 12 samples per input bit,
  three templates) is complete for the whole state
  at S_7.
- S_8: all eight words NONLIN. The last AFF words
  (d, h) are consumed by round 7's computation.
- S_9: the sound influence masks are complete: all
  eight words, all 32 bits fully dependent. From
  here to round 63 every word is NONLIN with full
  masks; nothing about the dependence structure
  changes again.

Two distinct "completeness" rounds, kept distinct
because the programme has conflated such pairs
before: functional nonlinearity is complete at
S_8 (no affine or linear structure survives in any
word); provable full bit-dependence by the sound
mask bound is complete at S_9; observed bit
sensitivity completes earlier, at S_7, because
sampling sees actual flips that the sound bound
only certifies one round later for the last two
words.

### Verdict on Y-065 (nonce-affine schedule decomposition)

DEAD as a work reduction. The decomposition it
needs exists exactly where it saves nothing (W18,
W19) and fails provably at the first word where it
would matter (W20, by z3 counterexample verified
numerically, and by a 1.0 sampled violation rate).
The mechanism's hope was that the carry correction
between base and delta evaluation would be small,
structured, or shared. The derivation shows the
correction is not a correction term: it is the
full carry behaviour of the additions themselves,
which is the computation. There is no residual
sense in which the schedule splits into a shared
nonce-free part plus a cheap nonce part beyond
W19. Tier: the closure is ESTABLISHED (proof plus
measurement), not a judgement call.

### Verdict on Y-075 (round-3 state delta decomposition)

DEAD as a work reduction. The (base, delta)
representation is exact at exactly one point, S_4,
where delta = (n, 0, 0, 0, n, 0, 0, 0) added to the
base's a and e: that is the already-known
precomputation boundary, restated. Propagating the
delta symbolically past S_4 is what the hypothesis
proposed; the derivation shows the very next round
consumes the affine pair through Ch, Maj, Sigma0
and Sigma1 and produces fresh words nonlinear in
n. The AFF words visible at S_5 to S_7 are not
propagated deltas; they are the S_4 words sitting
in shifted registers awaiting their own
consumption. A delta engine would have to track a
nonlinear correction from round 4 onward, which is
the full computation with extra bookkeeping. Tier:
ESTABLISHED closure, same evidence class as Y-065.

### What this derivation does not close

It closes nonce-structured decompositions of the
schedule and the early state. It does not address:
restructurings that do not separate by the nonce at
all (whole-graph algebraic identities, alternative
addition networks for the five-operand sums,
different intermediate quantities); the outer hash,
whose input is the full inner digest and has no
single varying word; or multi-nonce joint
structure beyond noting that from S_8 every word
of every nonce's state is fully and nonlinearly
mixed, which is consistent with, but does not
prove, the absence of cross-nonce sharing.
Those remain Workstream A open problems
(OPEN_PROBLEMS.md).

## MD-2. Established results carried into Phase 6 (not re-derived)

- Boolean cone minima: Ch costs 3 classic Boolean
  ops, Maj costs 4; VPTERNLOGD immediates are unique
  (Ch 0xCA, Maj 0xE8, XOR3 0x96). PROVEN three ways
  (exhaustive evaluation, 1M-sample differential,
  z3 UNSAT), EXP-012 and proofs/boolean_cone_search.
- Alternative Ch and Maj forms (Ch_alt, Maj_alt_A,
  Maj_alt_B) are exactly equivalent. PROVEN,
  ../mathematical_foundations.md.
- Precomputation ceiling: 67 of 192 rounds are
  template-reusable (64 of block 1, 3 of block 2).
  DERIVED and differentially verified; the boundary
  is where MD-1 begins.
- Reduced-round bias: no exploitable bias survives
  past round 24 in this lab's chi-square and
  avalanche measurements. MEASURED
  (../results/RESEARCH.md), and the reason R-01
  stands rejected.
