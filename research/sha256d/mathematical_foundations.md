# Mathematical Foundations of Bitcoin SHA-256d (Stage 2)

The consensus computation, unchanged by anything in this
programme:

    block_hash = SHA256( SHA256( header ) ),  header = 80 bytes

A header meets proof of work when the 32-byte result, read as a
little-endian 256-bit integer, is at most the target decoded
from the header's nBits field. Equality meets the target.

## SHA-256 in the form this programme uses

State: eight 32-bit words (a..h). Per round t = 0..63, with
message word W_t and round constant K_t:

    S1 = ROTR6(e) ^ ROTR11(e) ^ ROTR25(e)
    Ch = (e & f) ^ (~e & g)
    T1 = h + S1 + Ch + K_t + W_t            (all adds mod 2^32)
    S0 = ROTR2(a) ^ ROTR13(a) ^ ROTR22(a)
    Maj = (a & b) ^ (a & c) ^ (b & c)
    T2 = S0 + Maj
    (a,b,c,d,e,f,g,h) <- (T1+T2, a, b, c, d+T1, e, f, g)

The compression function is this 64-round map applied to a
64-byte block, added wordwise (mod 2^32) into the running state
(the Davies-Meyer style feed-forward SHA-256 uses).

Message schedule: W_0..W_15 are the block's big-endian words.
For t = 16..63:

    s0 = ROTR7(W_{t-15}) ^ ROTR18(W_{t-15}) ^ SHR3(W_{t-15})
    s1 = ROTR17(W_{t-2}) ^ ROTR10(W_{t-2}) ^ SHR19(W_{t-2})
    W_t = W_{t-16} + s0 + W_{t-7} + s1     (mod 2^32)

Padding: append 0x80, then zeros, then the message bit length
as a 64-bit big-endian integer, closing the final block.

## The three compressions of one Bitcoin candidate

Hashing an 80-byte header takes exactly three compression
function evaluations (192 rounds in total):

1. Inner block 1: header bytes 0..63, compressed into the SHA-256
   initial state. Result: the midstate (see
   header_and_midstate_analysis.md).
2. Inner block 2: header bytes 64..79, then 0x80, then zeros,
   then the 64-bit length 640. Compressed into the midstate.
   Result: the inner digest (32 bytes).
3. Outer block: the inner digest (32 bytes), then 0x80, zeros,
   and the 64-bit length 256. Compressed into the SHA-256
   initial state. Result: the candidate block hash.

There is no fourth compression and no streaming subtlety: both
messages are fixed-length, so both paddings are constants except
for the data words themselves.

## What is provable, what is measurable, what is speculation

Established facts used by this programme:
- The compression and schedule above are FIPS 180-4; the lab's
  implementations are differentially verified against hashlib
  and a from-specification pure Python implementation
  (mining/pow_engine.py).
- Midstate reuse (block 1 once per template) is exact, not an
  approximation: the compression function is a pure function of
  (state, block), and block 1 does not contain the nonce.
- Reduced-round SHA-256 leaks statistical structure that dies
  by round 24 in the lab's own measurements (results/RESEARCH.md,
  research/statistics.py). Full SHA-256d applies 64 rounds
  twice. No statistical shortcut at full rounds exists in any
  evidence this lab has produced or cited; see
  rejected_hypotheses.md.

Hypotheses (tested, never assumed): alternative Boolean forms
(boolean_equivalence.md, proven exact, benefit unmeasured),
schedule representations, multi-stream interleaving, compiler
and codegen choices. Each lives in experiment_registry.md with
its validation method.

Out of bounds, permanently: reduced-round substitution,
probabilistic digest filtering that can miss a valid candidate,
nonce-range skipping without a coverage proof, and any change
to the consensus function itself.
