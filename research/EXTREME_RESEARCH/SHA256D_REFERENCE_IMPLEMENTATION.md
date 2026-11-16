# SHA-256d Reference Implementation

Stage 1 of the NOVA SHA-X Extreme Research mandate. This
document describes the reference implementation at
`tools/sha256d_reference.py`: a pure Python SHA-256 and
SHA-256d written from the mathematical model in
SHA256_COMPLETE_MATHEMATICAL_MODEL.md, for use as an
independent correctness oracle in research. It is not a
production component and is never called by the mining path.

## 1. Independence

The implementation imports only `math`, `struct` and (in the
tools that use it) the sibling research modules. It does not
import or call any production code: not gpu/engine.py, not
the C kernels, not mining/*.py. Two deliberate design choices
keep it independent in substance, not just in imports:

- The constants are derived, not copied. H(0) and K are
  computed at import time from the first primes by exact
  integer arithmetic (isqrt over p x 2^64 for the square
  roots, an exact integer cube root over p x 2^96 for the
  cube roots), following the derivation Phase 001 verified
  against the v0.1.3 source
  (research/phase001/SHA256_CONSTANTS_AND_TABLES.md). A
  transcription error in a pasted table is therefore
  impossible in this file, and the self-check below pins the
  derived values (IV[0] = 6a09e667, K[0] = 428a2f98,
  K[63] = c67178f2).
- The compression is written as a direct transcription of
  the round equations: a rotating register assignment
  mirroring the state transition in the model document, an
  explicit 64-word schedule built by the recurrence, and an
  explicit feed-forward addition.

Relationship to existing code, stated plainly: the
repository already contains a pure Python SHA-256 inside
production, mining/pow_engine.py (PureSHA256), which
EXP-036's candidate_verify uses as its independent digest.
This research implementation is a second, separately written
oracle on the research side of the tree. The Stage 1
differential run (SHA256D_DIFFERENTIAL_VERIFICATION.md)
exercises both: its part C routes verdicts through
verify_candidate, whose independent digest is pow_engine's,
while parts A, B and D compare this implementation against
hashlib and the production kernels directly.

## 2. API

- `IV`, `K`: the derived constant tuples.
- `compress(state, block)`: one compression over exactly 64
  bytes, returning the post-feed-forward state. Exposed
  deliberately: the dependency and midstate work needs the
  raw transition, not just whole hashes.
- `sha256(message)`: full SHA-256 with FIPS padding.
- `sha256d(message)`: SHA-256(SHA-256(message)).
- `midstate(first_64_bytes)`: Compress(IV, block) for
  exactly one block; the reusable state for an 80-byte
  header's first chunk (see SHA256D_PIPELINE_RECONSTRUCTION.md).
- `sha256_from_midstate(state, remaining)`: finishes a
  SHA-256 whose first block produced `state`, with padding
  computed against the full message length. Part D of the
  differential run proves the split equals the whole over
  the test corpus.

## 3. Self-check

Running the file executes three FIPS 180-4 example vectors
(the empty string, "abc", and the 56-byte two-block example)
and prints the derived constants. Recorded output from the
Stage 1 run:

```
sha256 len=0 OK
sha256 len=3 OK
sha256 len=56 OK
IV[0]=6a09e667 K[0]=428a2f98 K[63]=c67178f2
```

## 4. Performance character

Pure Python, written for legibility of the mathematics. On
this VM it hashed the 998,164-byte mainnet block at height
450,170 (2,095 transactions, full TXID tree) in roughly 43
seconds wall as part of the header tool. That is an oracle's
speed, not a miner's; the mandate for this stage forbids
benchmarks, and none are reported. Any performance question
belongs to the production kernels and the EXP-017 protocol,
not to this file.
