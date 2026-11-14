# proofs/

Formal proof scripts and solver outputs for X-series
mathematical claims. The established pattern is
../tools/boolean_proof.py: an exhaustive 1-bit proof where
the identity is purely bitwise, a randomized 32-bit
differential (1,000,000 samples), and a z3 bit-vector UNSAT
check of the negated identity. All three legs are required
before an identity is called proven in this programme.

Proof obligations live with their hypotheses in
../HYPOTHESIS_REGISTRY.md and are summarized in
../MATHEMATICAL_DISCOVERY.md.
