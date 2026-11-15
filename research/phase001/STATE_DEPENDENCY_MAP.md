# Phase 001, Deliverable 10: SHA-256 Internal State Dependency Map

Project: NOVA SHA-X, Research Phase 001, Wave 3.
Subject: for the Bitcoin block header's two SHA-256 chunks, exactly which compression state words depend on the nonce after each round, where the dependence saturates, and the same question for the second SHA-256 pass. Derived from the round equations and verified two independent ways.

Labels: SOURCE FACT (file and line in the verified 0.1.3 tree), PROVEN (derived and checked here, scripts in RAW_RESULTS), STANDARD (FIPS 180 mathematics).

## 1. Method

The round function is the one transcribed in Deliverable 8 from src/sha.cpp lines 132 to 139:

```
T1 = h + S1(e) + Ch(e,f,g) + K[t] + W[t]
T2 = S0(a) + Maj(a,b,c)
(a,b,c,d,e,f,g,h) -> (T1+T2, a, b, c, d+T1, e, f, g)
```

Taint rule: a value is marked nonce-dependent if its defining expression contains the nonce anywhere. XOR, rotations, shifts, Ch, Maj and modular addition all propagate the mark from any input to the output. An unmarked value is therefore provably identical for all nonces (its expression never mentions the nonce); a marked value can differ. The schedule marks come from Deliverable 9. The computation is RAW_RESULTS/taint_analysis.py; the independent numeric confirmation (real genesis header, one nonce bit flipped, per-round state comparison) is RAW_RESULTS/sha256d_layout_verify.py. Both agree exactly, band by band.

## 2. Pass 1, chunk 1 (header bytes 0 to 63): no nonce anywhere

No input word of chunk 1 contains the nonce (the nonce is header byte 76 to 79, in chunk 2), and the incoming state is H(0), a constant. Therefore:

| rounds | a | b | c | d | e | f | g | h |
|---|---|---|---|---|---|---|---|---|---|
| 0 to 63 | . | . | . | . | . | . | . | . |
| after feed-forward | . | . | . | . | . | . | . | . |

(. = provably nonce-independent.) The chunk-1 output state, the quantity the literature calls the midstate, is a pure function of the first 64 header bytes: version, previous block hash, and merkle root bytes 0 to 27. This is a mathematical fact about the construction (STANDARD), independent of implementation. What the 0.1.3 code does with that fact is a separate, implementation question, answered in Deliverable 11: it does nothing, it recomputes chunk 1 from H(0) for every candidate.

## 3. Pass 1, chunk 2 (header bytes 64 to 79 plus padding): the nonce enters at round 3

Schedule marks for this chunk (Deliverable 9): W[3] marked; W[16], W[17] unmarked; W[18..63] all marked. Incoming state (the midstate) unmarked. State marks after each round:

| after rounds | a | b | c | d | e | f | g | h | reading |
|---|---|---|---|---|---|---|---|---|---|
| 0 to 2 | . | . | . | . | . | . | . | . | W[0], W[1], W[2] are merkle tail, nTime, nBits: no nonce yet |
| 3 | N | . | . | . | N | . | . | . | round 3 consumes W[3] = nonce: T1 marked, so new a and new e are marked |
| 4 | N | N | . | . | N | N | . | . | the marked a and e shift into b and f; new a, e marked via T1 and T2 |
| 5 | N | N | N | . | N | N | N | . | only d and h still clean |
| 6 to 63 | N | N | N | N | N | N | N | N | saturated: every state word may depend on the nonce |
| after feed-forward | N | N | N | N | N | N | N | N | output = midstate + final state; the final state is fully marked, so all 8 digest words of pass 1 are nonce-dependent |

Why the spread takes exactly this shape: a marked word can only enter the two computed positions (new a, new e) or shift one position per round along the two chains a->b->c->d and e->f->g->h. The nonce first computes at round 3. The clean survivors at round 5 are d and h, the far ends of the two shift chains, and both are consumed as inputs at round 6 (d into new e, h into T1), closing the map. Saturation after round 6 means: of the 64 rounds of chunk 2, only the first 7 round outputs (after rounds 0 to 6) contain any nonce-independent word at all, and from round 6 on the entire state is a nonce-mixed quantity. There is no round after 6 at which any state word is reusable across nonces.

Numeric confirmation (sha256d_layout_verify.py, genesis header, nonce bit 0 flipped): state words differing after round 3 are exactly {a, e}; after round 4, {a, b, e, f}; after round 5, {a, b, c, e, f, g}; from round 6 on, all 8. The empirical bands match the symbolic bands position for position.

## 4. Pass 2 (the 32-byte pass-1 digest plus padding): total dependence

Every input word of pass 2 is a pass-1 digest word, and section 3 shows all 8 digest words are nonce-dependent. Hence all 16 loaded schedule words are marked, all 64 expanded words are marked, and the state saturates almost immediately:

| after rounds | state marks |
|---|---|
| 0 | a and e marked (T1 and T2 both read marked words from the start), the shifted copies still trace to the marked incoming state |
| 3 | all 8 state words marked (taint_analysis.py: "state fully tainted from round: 3"; the incoming state itself is already fully marked, so in substance pass 2 has no nonce-independent quantity at any point) |

Precisely: the incoming state to pass 2 is H(0) (constant), but every W is marked, so T1 is marked at round 0, and by round 3 every register position holds a value whose expression contains a digest word. No part of pass 2 is reusable across candidates. Combined with section 2, the complete reusability picture for one template is:

| component | reusable across nonces? | rounds of compression |
|---|---|---|
| pass 1 chunk 1 | yes, entirely (output is the midstate) | 64 |
| pass 1 chunk 2, rounds 0 to 2 state | the state entering round 3 is reusable, but it is just the midstate evolved by 3 fixed rounds; the schedule words W[16], W[17] are also reusable | (part of chunk 2's 64) |
| pass 1 chunk 2, rounds 3 to 63 | no | 61 of 64 |
| pass 2, all | no | 64 |

Total accounting, stated exactly: full SHA-256d of the header costs 3 chunk compressions (2 in pass 1, 1 in pass 2) = 192 rounds. Reusing the chunk-1 midstate removes exactly the 64 chunk-1 rounds, leaving 128 rounds whose inputs depend on the nonce and which cannot be precomputed for a fixed template. These are accounting identities over the dependency map (PROVEN from the map), not performance claims: how much wall-clock a round costs is a benchmarking question outside this wave.

## 5. Dependence on the other mutable fields (for completeness)

The same method applied to nTime (chunk-2 W[1]) gives first schedule contact at W[16] (lag 15) and first state contact at round 1; applied to nBits (W[2]), first state contact at round 2 and first expanded schedule word W[17]. The nonce is the only field whose first contact is as late as round 3 / W[18], because it sits deepest in the chunk. These are one-line corollaries of the lag structure, included so the map is complete for every field the mining loop mutates (src/main.cpp: nNonce every candidate, nTime every 262144 candidates, see Deliverable 11).

## 6. Reproduction

`python3 research/phase001/RAW_RESULTS/taint_analysis.py` prints the schedule strings and the round bands for all three chunks. `python3 research/phase001/RAW_RESULTS/sha256d_layout_verify.py` prints the empirical per-round difference sets on the genesis header. Expected agreement: bands { } rounds 0 to 2, {a,e} round 3, {a,b,e,f} round 4, {a,b,c,e,f,g} round 5, all 8 from round 6; saturation round 6 in both.

## 7. Limitations

- Taint is may-depend: marked words can differ, unmarked words cannot. The numeric witness shows the marked words do differ for a one-bit nonce change on the genesis template, but the map itself is the symbolic statement and does not depend on that witness.
- The map tracks dependence on the nonce value, not on any algebraic structure of that dependence (which terms, which carries). The finer structure is Deliverable 9, section 3, and the hypothesis track.
- Nothing here measures speed. The statement "64 of 192 rounds are nonce-independent" is a dependency accounting identity; converting it into a throughput claim requires the benchmarking framework of a later deliverable and the EXP-017 paired protocol the lab uses for integration decisions.
