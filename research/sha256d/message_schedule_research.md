# Message Schedule Research

## Where the programme stands

Three schedule implementations exist in the lab today:
1. OpenSSL's, inside SHA256_Transform (production). Not
   inspectable as source here, but its output is the
   correctness reference and its speed is the bar.
2. Scalar C full recompute per nonce (bal_sha_intrin.c
   schedule_impl): a 64-word array regenerated for every
   nonce, in plain C, with no SHA256MSG1/MSG2 instructions
   anywhere in the compiled library (objdump: 0 sites).
   This is bottleneck B2 and the proximate cause of the
   intrinsics path running at about 0.52x production.
3. The CUDA shared source (gpu/cuda/kernels/sha256.h) carries
   both a full 64-word compressor and a circular 16-word
   variant (bal_compress_state_circ), host-validated.

## The schedule's structure, and what it permits

W_t for t >= 16 depends on W_{t-16}, W_{t-15}, W_{t-7},
W_{t-2}. Two consequences drive the research:
- Only 16 words are ever live; a circular buffer is exact
  (H-07) and cuts register/stack traffic in scalar code.
- In block 2 of the inner hash, words W4..W15 are constants
  (padding) and W0..W2 are template-fixed, so the schedule
  words that depend only on those can be precomputed per
  template: concretely the generated words up to the first
  nonce-dependent one (see header_and_midstate_analysis.md
  for the state-side statement). In a SHA-NI kernel, the
  schedule is produced by SHA256MSG1/MSG2 operating on
  4-word vectors; the nonce enters the vector containing
  W3, which is why the practical precompute boundary sits
  at a 4-word lane edge, a detail H-02 must handle exactly.

## Research questions, in registry order

- H-02: DONE 2026-11-14 (EXP-002). The MSG1/MSG2 schedule
  (whitepaper GENA/GENB construction, alignr supplying the
  W[i+9] terms) is built, proven equivalent to the scalar
  recurrence by a twin build, and worth about 2.6x over the
  scalar schedule at equal rounds in-session. Zero scalar
  schedule words remain; the only scalar rounds are the
  once-per-template round 2 and the mode-2 variant's
  per-nonce round 3, both state rounds, not schedule.
- H-07: circular vs full schedule inside that kernel,
  decided by stack frame and benchmark, not preference.
- H-01: with 2 or 4 interleaved streams, schedules interleave
  too; the MSG instructions operate per stream, so stream
  count multiplies schedule work exactly as it multiplies
  round work. No sharing between streams is possible: each
  nonce has a different W3 and therefore a different tail
  schedule. Anyone proposing schedule sharing across nonces
  beyond the template-fixed prefix must show which words are
  nonce-independent; the derivation in
  header_and_midstate_analysis.md is the reference.

## Rejected schedule ideas on record

- Precomputing the whole block-2 schedule per template:
  impossible, W3 (nonce) feeds the expanded recurrence from
  W18 on (first expanded word depending on W3; corrected
  from W19, see header_and_midstate_analysis.md), and rounds
  consume W3 at round 3 regardless.
- Skipping schedule words for nonces "unlikely" to win:
  changes the function; banned by the programme rules.
