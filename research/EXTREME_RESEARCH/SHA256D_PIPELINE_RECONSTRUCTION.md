# SHA-256d Pipeline Reconstruction

Stage 1 of the NOVA SHA-X Extreme Research mandate. The
three-compression structure of SHA-256d over an 80-byte
Bitcoin header, stated exactly, with the reusable-work
accounting and its limits. The compression model itself is
in SHA256_COMPLETE_MATHEMATICAL_MODEL.md; the dependency
evidence is in MESSAGE_SCHEDULE_DEPENDENCY_GRAPH.md.
Phase 001 reconstructed the same pipeline from the Bitcoin
v0.1.3 source (research/phase001/SHA256D_RECONSTRUCTION.md);
this document consolidates that with the EXP-016, EXP-027
and Phase 6 results.

## 1. The three compressions

SHA-256d(header) = SHA-256(SHA-256(header)) over an 80-byte
header expands to exactly three 64-round compressions:

1. Inner compression 1: header bytes 0 to 63.
2. Inner compression 2: header bytes 64 to 79 plus padding.
3. Outer compression: the 32-byte inner digest plus padding.

192 rounds in total. There is no fourth compression and no
partial one: 80 bytes pads to 128 (two blocks), 32 bytes
pads to 64 (one block).

## 2. Inner compression 1 and the midstate

Bytes 0 to 63 are: version (4), previous block hash (32),
and the first 28 bytes of the Merkle root. None of them
depends on the nonce, the time rolling, or anything else
that varies inside one search over one template. The state
after this compression,

S_mid = Compress(IV, header[0:64]),

is the midstate: computed once per template and reused for
every nonce. Phase 001 noted the historical contrast: the
v0.1.3 miner reused NO midstate (BlockSHA256 calls InitState
fresh for every candidate, recomputing these 64 rounds per
nonce); every NOVA production kernel reuses it.

## 3. Inner compression 2: where the nonce lives

Bytes 64 to 79 are: the last 4 bytes of the Merkle root,
nTime, nBits, and the nonce, followed by padding (0x80,
zeros, and the 64-bit length 640). The 16 loaded schedule
words are therefore:

- W0 = Merkle root bytes 28 to 31 (big-endian load)
- W1 = nTime
- W2 = nBits
- W3 = the nonce
- W4 = 0x80000000 (the padding bit in place)
- W5..W14 = 0
- W15 = 640 (the bit length)

The nonce is exactly one loaded word, W3. It is first
consumed in round 3, where the state words a and e become
nonce-dependent; rounds 0 to 2 produce a state with no
nonce-dependent word. The expanded schedule stays
nonce-free through W17; W18 is the first nonce-dependent
expanded word. Full dependency structure:
MESSAGE_SCHEDULE_DEPENDENCY_GRAPH.md.

Time rolling and version rolling change W1 and the block-1
words respectively, not W3: a time or version change is a
new template (new midstate), while a nonce change is not.

## 4. Outer compression: zero reuse

The outer input is the inner digest exactly as produced
(8 big-endian words), padded with 0x80000000 at W8 and
length 256 at W15. EXP-027's dependency census
(research/sha256d/phase6b/EXP027_COMPUTATION_REPRESENTATIONS.md)
established: all 48 computed schedule words of the outer
compression depend on the inner digest (its message words 0
to 7 ARE the digest, and the recurrence propagates the
dependence), and zero complete outer rounds are
digest-independent. No part of the outer compression can be
computed before the inner finishes, and no part is reusable
across candidates. Cross-compression partial execution is
refuted by dependency, exactly.

## 5. Endianness and the target comparison

Three different byte conventions meet in this pipeline, and
the Stage 1 tool (tools/header_reconstruction.py) verifies
all three against Core on real blocks:

- Header scalar fields (version, time, bits, nonce) are
  little-endian in the serialization.
- The two 32-byte hashes in the header (previous hash,
  Merkle root) are stored in internal byte order; their
  display form is the byte reversal. SHA-256 itself loads
  message words big-endian and emits the digest as
  big-endian words.
- The proof-of-work comparison treats the final digest as a
  little-endian 256-bit integer (equivalently, the reversed
  display hex read as a big integer) and requires
  hash <= target, with the target decoded from nBits by
  integer arithmetic only. Equality accepts (Core
  CheckProofOfWork rejects only value > target).

## 6. Reusable-work accounting, stated with its limits

Conventional accounting for one template with midstate
reuse, as derived and differentially verified in Phase 6
(research/sha256d/phase6/MATHEMATICAL_DISCOVERIES.md):

- 67 of 192 rounds are template-reusable: the 64 rounds of
  inner compression 1, plus rounds 0 to 2 of inner
  compression 2, whose outputs contain no nonce-dependent
  word.
- 125 of 192 rounds are the conventional per-nonce
  remainder: rounds 3 to 63 of compression 2, and all 64
  outer rounds.

Two cautions are part of the record and are repeated here
because they bound what this accounting means:

1. The 67 figure counts rounds whose complete output state
   is template-fixed. Production kernels execute rounds 0
   to 2 of compression 2 per nonce anyway, because the
   nonce enters the same compression; the accounting is
   about what is reusable in principle in the conventional
   graph, not about what any given kernel skips.
2. The 125-round remainder is NOT a proven universal lower
   bound on equivalent computations. Phase 6's own
   correction (research/sha256d/phase6/OPEN_PROBLEMS.md,
   OP-1) states this explicitly: whether any equivalent
   computation graph evaluates SHA-256d with materially
   fewer primitive operations is an open problem, settled
   piecewise by EXP-020 (round optimum within its
   vocabulary), EXP-027, EXP-033 and EXP-042 (named spaces
   closed at stated bounds), never by the accounting alone.

## 7. Summary

Per candidate, the irreducible-by-construction work is:
finish compression 2 from the midstate with one substituted
word (W3), then run the outer compression in full. Every
production backend in this repository implements exactly
that split, and the Stage 1 differential run
(SHA256D_DIFFERENTIAL_VERIFICATION.md) confirms the
production batch path and this reconstruction agree digest
for digest over 49,288 cases including the boundary nonces
0, 1 and 2^32 - 1.
