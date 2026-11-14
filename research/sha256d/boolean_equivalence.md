# Boolean Equivalence: Ch and Maj Alternative Forms (Stage 4, pulled forward)

Status: equivalence PROVEN for three alternative forms.
Performance benefit: NOT YET MEASURED. The forms below are
registered as hypotheses (H-03) for implementation experiments;
nothing here claims a speedup.

## The forms

Reference (FIPS 180-4):
    Ch(x,y,z)  = (x & y) ^ (~x & z)
    Maj(x,y,z) = (x & y) ^ (x & z) ^ (y & z)

Proven-equivalent alternatives:
    Ch_alt(x,y,z)   = z ^ (x & (y ^ z))
    Maj_alt_A(x,y,z) = (x & y) ^ (z & (x ^ y))
    Maj_alt_B(x,y,z) = (x & (y ^ z)) ^ (y & z)

## Proof method and results

Ch and Maj are bitwise: each output bit depends only on the
same-position input bits. A word identity built from AND, OR,
XOR, NOT therefore holds for all 32-bit inputs if and only if
the 1-bit identity holds on all 8 input rows. That makes an
8-row exhaustive check a complete proof, not a sample.

tools/boolean_proof.py runs three independent checks, and on
2026-11-14 all three passed for all three forms:
1. Exhaustive 1-bit proof: 8 of 8 rows each. PASS.
2. Randomized 32-bit differential: 1,000,000 samples, fixed
   seed, against the reference forms. PASS (guards against
   transcription slips between bit forms and word code).
3. z3 bit-vector solver: the negation of each identity is
   UNSAT. PASS (z3 installed at $0 in a workspace venv solely
   for this check; the script degrades gracefully without it).

Reproduce: python3 research/sha256d/tools/boolean_proof.py

## Instruction-cost reasoning (hypotheses, not measurements)

Counting bitwise operations at source level:
- Ch reference: 2 AND, 1 NOT, 1 XOR = 4 ops, and the NOT sits
  on the critical path before the second AND.
- Ch_alt: 2 XOR, 1 AND = 3 ops, no NOT. On x86 this maps to
  xor, and, xor with a shorter dependency chain into T1.
  This is also the form most optimizing compilers already
  synthesize from the reference, which is why any gain must be
  measured in generated code, not assumed from source.
- Maj reference: 3 AND, 2 XOR = 5 ops.
- Maj_alt_A: 2 AND, 2 XOR = 4 ops. Maj_alt_B: 2 AND, 2 XOR =
  4 ops, different dependency shape (the (y & z) term is
  independent of x and can issue early).

Where these could matter: a scalar or SHA-NI implementation
where Ch and Maj are computed in vector registers alongside
SHA256RNDS2 (which internally computes its own Ch/Maj for the
two rounds it performs, so these forms only apply to code
that evaluates rounds outside the SHA-NI round instruction,
for example the block-2 prefix rounds, a pure SIMD multi-buffer
design, or the outer hash in a hand-written kernel). Where
they cannot matter: the production OpenSSL path, whose round
internals are inside libcrypto and not ours to restyle.

Next step: H-03 in the registry. Any adoption requires a
candidate implementation, differential correctness against
hashlib at 100k+ hashes, assembly comparison, and a harness
benchmark whose median improvement exceeds the spread.
