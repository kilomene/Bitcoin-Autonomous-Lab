# Round Optimization Research

## The round as the unit of work

One candidate costs 125 non-precomputable rounds (61 of inner
block 2 plus 64 outer) plus, in the production path today, the
wrapper work around two OpenSSL Transform calls. Round-level
research therefore splits into three honest targets:

1. The rounds inside SHA256RNDS2 (production compression and
   any direct SHA-NI kernel): the instruction computes two
   rounds including its own Ch and Maj. What remains ours to
   optimize is the surrounding work: schedule supply, state
   shuffling between round pairs, and the partial-round
   bookkeeping for the block-2 prefix.
2. Rounds evaluated outside RNDS2: the block-2 prefix rounds
   (H-03), and every round in a SIMD multi-buffer design
   (H-08, H-09). Here the proven Ch and Maj alternatives
   (boolean_equivalence.md, H-06) apply directly, as do
   rotate implementations (vector ROTR by constant is a
   shuffle-plus-shift-plus-or sequence; rorx in scalar code,
   H-18).
3. Dependency structure: T1 depends on e, f, g, h and the
   round's W and K; T2 on a, b, c. The critical path through
   one round is roughly the S1 chain into T1 into the next
   round's e. Nothing reorders this within one hash: the
   serial chain is intrinsic, which is the mathematical
   reason interleaving independent hashes (H-01) is the
   top-ranked lever rather than any within-round trick.

## State rotation conventions

Implementations differ in whether they physically rotate the
eight state words each round or unroll with renamed registers
(the "state variable rotation" the charter asks about).
OpenSSL's SHA-NI code and the lab intrinsics kernel both use
register renaming by construction of the RNDS2 operand
layout (the cdgh/abef forms documented in bal_sha_intrin.c).
For a hand kernel this is a codegen detail to verify in the
listing (assembly_analysis.md rules), not a source-level
claim.

## Addition arrangement

The round's additions (h + S1 + Ch + K + W for T1) are mod
2^32 and fully associative as integer addition; grouping is
free and compilers already exploit it. Pre-adding K_t + W_t
is standard and is exactly what the SHA-NI message operand
carries. No hypothesis in the registry depends on addition
rearrangement alone; it is recorded here so future proposals
must show a generated-code difference, per the standing
assembly rules.

## What would change the picture

A round implementation that beats OpenSSL's SHA-NI sequence
per round is not expected from source-level rearrangement.
The credible gains are systemic: fewer non-round
instructions per round (wrapper and schedule supply, B1 and
B2), and more rounds in flight per core (interleaving,
multi-buffer). The registry ranks accordingly.

## Stage 5 measurement note (2026-11-14)

Both systemic gains are now measured, in the research tree
(EXP-002, EXP-003). Removing the scalar schedule entirely
(MSG1/MSG2 supply) is worth about 2.6x at equal rounds
in-session, and interleaving independent round chains adds
a further 2.36x per worker at 2 streams. The prefix-round
saving (rounds 0..2 per template) is real arithmetic but
its 2.4 percent effect is under this VM's noise floor: the
three snapshot variants' benchmark spreads fully overlap,
so no per-round claim is made from it here. What the data
does not support is a claim that RNDS2 is throughput-bound
on this core: if it were, interleaving could not have
produced the measured gains. The binding constraint the
measurements actually show is single-chain latency plus
this guest's scheduling noise.
