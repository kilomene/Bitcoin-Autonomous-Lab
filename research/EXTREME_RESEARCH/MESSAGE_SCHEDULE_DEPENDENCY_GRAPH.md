# Message Schedule and State Dependency Graph

Stage 1 of the NOVA SHA-X Extreme Research mandate. The
complete nonce-dependency structure of SHA-256d over an
80-byte header, consolidated from four prior investigations.
Nothing here is newly claimed; every edge below names its
evidence. Notation: [N] means the quantity may depend on the
nonce, [.] means it provably does not.

Sources:

- EXP-016 (research/sha256d/phase6/MATHEMATICAL_DISCOVERIES.md
  and analysis/exp016_dependency_results.json): bit-level
  influence measurement and the W18 / W19 delta identities.
- Phase 001 Wave 3 (research/phase001/
  STATE_DEPENDENCY_MAP.md, MESSAGE_SCHEDULE_ANALYSIS.md):
  symbolic taint bands per round, numerically confirmed on
  the genesis header.
- EXP-027 (research/sha256d/phase6b/
  EXP027_COMPUTATION_REPRESENTATIONS.md): the outer
  compression dependency census.
- EXP-033 (research/sha256d/exp033/): independent symbolic
  re-verification of the W18 / W19 identities and the W20
  linearity refutation.

## 1. The graph, in text form

```
TEMPLATE (fixed per job)
  version, prev hash, merkle root, nTime, nBits
        |
        v
CHUNK 1 (header bytes 0..63) .................. all [.]
  W[0..63] all [.]  ->  state all [.]
        |
        v  S_mid (midstate, reusable)
CHUNK 2 (header bytes 64..79 + padding)
  loaded words:
    W0  = merkle tail   [.]
    W1  = nTime         [.]
    W2  = nBits         [.]
    W3  = NONCE         [N]   <-- the only nonce input
    W4  = 0x80000000    [.]
    W5..W14 = 0         [.]
    W15 = 640           [.]
  expanded words (recurrence W[t] = s1(W[t-2]) + W[t-7]
                                 + s0(W[t-15]) + W[t-16]):
    W16 [.]   W17 [.]
    W18 [N]   via s0(W3) only; delta exactly sigma0(nonce)
    W19 [N]   via W3 as a direct addend; delta exactly nonce
    W20 [N]   nonlinear onset; delta not XOR-linear
    W21..W63 [N]  full dependence (see table)
  state by round (chunk 2):
    after rounds 0..2   : { }                    all [.]
    after round 3       : {a, e}                 [N]
    after round 4       : {a, b, e, f}           [N]
    after round 5       : {a, b, c, e, f, g}     [N]
    after round 6..63   : {a..h} saturated       [N]
        |
        v  inner digest: all 8 words [N]
OUTER CHUNK (digest + padding)
  W0..W7 = digest words, all [N]
  all 48 computed schedule words depend on the digest
  zero complete rounds are digest-independent
  state saturated from the first rounds
        |
        v  block hash; integer test hash <= target
```

## 2. Schedule edges, with evidence

Recurrence inputs per expanded word, and the measured nonce
influence from EXP-016 (union of nonce bits that can affect
the word; bits fully dependent over the sample):

| Word | Nonce-carrying input | Union bits | Fully dependent bits | Verdict |
|---|---|---|---|---|
| W16 | none (W14, W9, W1, W0) | 0 | 0 | nonce-free |
| W17 | none (W15, W10, W2, W1) | 0 | 0 | nonce-free |
| W18 | sigma0(W3) only | 32 | 16 | first nonce-dependent expanded word |
| W19 | W3 as direct addend | 32 | 1 | directly dependent |
| W20 | sigma1(W18), sigma0(W5), W18 addend chain | 32 | 32 | nonlinear onset |
| W21 | via W19, W20 inputs | 32 | 20 | dependent |
| W22..W63 | recurrence closure | 32 | 32 | fully dependent |

Delta identities (EXP-016, proven, re-verified by EXP-033):

- D_18(n) = sigma0(n) exactly: the change in W18 under a
  nonce change n is sigma0 of the nonce change, with the
  nonce-free terms cancelling. z3: UNSAT for any
  counterexample.
- D_19(n) = n exactly: W19 shifts by exactly the nonce
  delta under integer addition.
- D_20 is NOT XOR-linear: EXP-016 measured a delta-linearity
  violation rate of 1.0 (every sampled case), because W18
  passes through sigma1 and is combined by modular addition
  with a second nonce-dependent term; EXP-033 refuted
  GF(2)-linearity of the W20 delta by a z3 counterexample.
  W20 is the first word whose nonce dependence is genuinely
  nonlinear, and no exact delta shortcut survives past it.

## 3. State edges, with evidence

Phase 001 derived the bands symbolically from the round
equations and confirmed them numerically on the genesis
header by flipping nonce bit 0 (state words differing after
each round match the bands position for position). The
mechanism: a marked word can only enter the two computed
positions (new a via T1 + T2, new e via d + T1) or shift one
position per round along the chains a to b to c to d and
e to f to g to h. The nonce first computes at round 3 (the
round that consumes W3). The clean survivors after round 5
are d and h, the far ends of the two shift chains; both are
consumed as inputs at round 6 (d into new e, h into T1),
which closes the map. Consequence, stated in the Phase 001
record: of the 64 rounds of chunk 2, only the outputs of
rounds 0 to 6 contain any nonce-independent word at all, and
from round 6 on the entire state is a nonce-mixed quantity.
There is no round after 6 at which any state word is
reusable across nonces.

## 4. Outer compression edges, with evidence

Every input word of the outer chunk is a digest word, and
section 3 shows all 8 digest words are nonce-dependent.
EXP-027's census adds the cross-compression form: all 48
computed schedule words of the outer compression depend on
the inner digest, and zero complete outer rounds are
digest-independent (rounds 0 to 7 consume digest words
directly; rounds 8 to 15 consume state already dependent on
them). Phase 001's taint analysis agrees: all 16 loaded
words marked, all 64 expanded words marked, saturation
almost immediate. The outer compression therefore appears in
the graph as a single fully dependent block: no edge enters
it except the completed inner digest, and no edge leaves it
except the final hash.

## 5. Reading of the whole graph

The dependency structure has exactly one narrow waist: the
midstate. Everything above it (chunk 1) is template-fixed;
everything below it is nonce-mixed, with the mixing
provably complete by round 6 of chunk 2 at the state level
and by W20 at the schedule level, and total in the outer
compression. Any proposed optimisation that claims reusable
work below the waist contradicts a named edge above and
must refute that edge's evidence first; any proposal above
the waist is template caching, governed by the EXP-025
identity rules in MERKLE_AND_TRANSACTION_MATHEMATICS.md.
