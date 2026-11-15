# Phase 001, Deliverable 9: Complete Message Schedule Analysis

Project: NOVA SHA-X, Research Phase 001, Wave 3.
Subject: the SHA-256 message schedule W[0..63] exactly as Bitcoin v0.1.3 codes it, its dependency structure, and precisely which schedule words depend on the nonce when the input is a Bitcoin block header.

Labels: SOURCE FACT (file and line in the verified 0.1.3 tree), PROVEN (derived here and checked by the scripts in RAW_RESULTS), STANDARD (FIPS 180 mathematics).

## 1. The schedule as coded

The schedule exists only as two macros in src/sha.cpp, consumed by the round macro R (line 132) through the selector `(j ? blk2(i) : blk0(i))`, where j is the outer loop counter stepping 0, 16, 32, 48 (line 148). So rounds 0 to 15 (j = 0) use blk0 and rounds 16 to 63 use blk2.

```cpp
#define blk0(i) (W[i] = data[i])                                          // src/sha.cpp line 21
#define blk2(i) (W[i&15] += s1(W[(i-2)&15]) + W[(i-7)&15] + s0(W[(i-15)&15]))  // src/sha.cpp line 118
```

with the small sigmas (lines 138 to 139):

```cpp
#define s0(x) (rotrFixed(x,7)^rotrFixed(x,18)^(x>>3))
#define s1(x) (rotrFixed(x,17)^rotrFixed(x,19)^(x>>10))
```

and the storage is `word32 W[16]` (line 143), a circular buffer. Three consequences of the coding form that a reader of the standard would not predict:

1. blk0 is defined at line 21, inside the SHA-1 section of the file (it is SHA-1's loading macro), and is reused by SHA-256 (and by the SHA-512 transform at line 526). There is no SHA-256-specific load macro.
2. blk2 is an in-place `+=`: the slot W[i mod 16] still holds W[i-16] when round i begins, so the macro adds the three expansion terms to W[i-16] rather than assigning a sum of four separate terms. The recurrence below is the exact unfolding of that in-place update.
3. All index arithmetic is masked with `&15`, i.e. modulo 16, matching the circular buffer. The indices (i-2), (i-7), (i-15) are read from slots that, at round i, hold W[i-2], W[i-7], W[i-15] respectively (each slot holds the most recent word of its residue class, and all three lags are less than 16, so no slot has been overwritten since the needed word was written; W[i-16] is the slot's own content). PROVEN by construction of the buffer discipline and consistent with the end-to-end genesis reproduction.

## 2. The recurrence in standard form

For a 64-byte block with big-endian words M[0..15] (the values Transform receives after the caller's byte reversal, see Deliverable 8, section 5):

```
W[i] = M[i]                                                        for 0 <= i <= 15
W[i] = s1(W[i-2]) + W[i-7] + s0(W[i-15]) + W[i-16]                 for 16 <= i <= 63
s0(x) = ROTR^7(x)  XOR ROTR^18(x) XOR SHR^3(x)
s1(x) = ROTR^17(x) XOR ROTR^19(x) XOR SHR^10(x)
```

All additions are modulo 2^32. This is exactly the FIPS 180 schedule (STANDARD), with the four-term sum regrouped by the in-place coding as W[i-16] + (s1(W[i-2]) + W[i-7] + s0(W[i-15])); addition is associative and commutative mod 2^32, so the regrouping is a PROVEN exact identity, not an approximation.

Dependency lags: each expanded word depends directly on the words 2, 7, 15 and 16 positions earlier. The dependency graph is a DAG layered by index; W[i] depends transitively on every M[k] with k <= i in its residue reachability, and in fact (section 3) on a rapidly saturating set.

## 3. Nonce dependency: the header case

Setup (SOURCE FACT layout, from src/main.cpp lines 2274 to 2300 and the header format): the first SHA-256 pass over the 80-byte header processes two 64-byte chunks. Chunk 1 is header bytes 0 to 63. Chunk 2 is header bytes 64 to 79 followed by padding. As big-endian words of chunk 2:

| chunk-2 word | content |
|---|---|
| W[0] | merkle root bytes 28 to 31 |
| W[1] | nTime |
| W[2] | nBits |
| W[3] | nNonce |
| W[4] | 0x80000000 (the 0x80 padding byte followed by zeros) |
| W[5..14] | 0 |
| W[15] | 640 (the bit length, written by FormatHashBlocks) |

So the nonce enters the schedule of chunk 2 at exactly one direct position, W[3]. (In chunk 1 the nonce does not appear at all; in the second SHA-256 pass every word is the first-pass digest and hence nonce-dependent, see Deliverable 11.)

Applying the recurrence's dependency lags to the single tainted input W[3] (taint = may-depend-on-nonce, propagated through XOR, rotations, shifts and additions; full method in Deliverable 10):

- Direct hits among the loaded words: only W[3].
- First expanded word reached: W[18], through the lag-15 term s0(W[i-15]) with i = 18. The other lags give W[19] (lag 16, W[i-16] = W[3]), W[10] and W[5] would be the lag-7 and lag-2 hits but those indices are below 16 and are loaded, not expanded.
- W[16] and W[17] do NOT depend on the nonce: their lag sets reach W[14], W[9], W[1], W[0] and W[15], W[10], W[2], W[1], none of which is W[3] or downstream of it.
- From W[18] onward, every schedule word depends on the nonce: W[i] for all i >= 18. The lag-2 term then chains the dependence forward (W[20] reads W[18], W[21] reads W[19], and so on), and no later word can lose the dependence because taint is a union over all four terms.

Precise statement (PROVEN two ways): **the first nonce-dependent expanded schedule word is W[18]; W[16] and W[17] are nonce-independent; every W[i] with i >= 18 is nonce-dependent.**

Proof method 1, symbolic: RAW_RESULTS/taint_analysis.py computes the taint sets from the recurrence. Output: schedule taint for chunk 2 is `...N............` for W[0..15] and `..NNNN...` (positions 18 to 63 set) for W[16..63]; "first nonce-dependent expanded word: W[18]".

Proof method 2, numeric: RAW_RESULTS/sha256d_layout_verify.py builds the real genesis header chunk 2, flips one nonce bit, expands both schedules with the exact s0/s1 above, and lists the differing words: exactly {3} union {18..63}. W[16] and W[17] are bit-identical across the nonce change. A one-bit flip is a witness, not the proof; the proof is the symbolic computation, and the numeric run confirms the symbolic model against the real recurrence on real data.

A finer structural fact, recorded because later phases use it: the nonce enters W[18] through exactly one additive term. W[18] = s1(W[16]) + W[11] + s0(W[3]) + W[2], and for a fixed template every term except s0(W[3]) is a constant, so the entire nonce influence on W[18] is carried by the single term s0(nonce). Likewise W[19] = s1(W[17]) + W[12] + s0(W[4]) + W[3] carries the nonce only through its final additive term, the nonce word itself. (Consistent with the lab's earlier EXP-016 finding.) Beyond W[19], the nonce influence spreads over multiple additive terms per word and no such single-term statement exists. This deliverable's claims are the dependency facts above, which hold regardless of addition carries.

## 4. Computational cost per chunk (operation count, transcribed from the macros)

Counting word operations in the source's own formulation, per 64-byte chunk:

- Loading, rounds 0 to 15: 16 word copies (blk0), zero arithmetic.
- Expansion, rounds 16 to 63 (48 words): each blk2 evaluates s1 (2 rotations + 1 XOR-pair = 3 XORs and 2 rotates, where a rotate is a macro for 2 shifts and 1 OR at source level) and s0 (2 rotates, 1 logical shift, 2 XORs), plus 3 additions in the expression and 1 in-place add: 4 additions per expanded word, 192 additions per chunk for the schedule.
- The schedule cost is inseparable from the round cost in this implementation because blk2 is evaluated inside R(i) on the critical path of round i: the expanded word for round i is computed at the moment round i executes, never earlier. There is no precomputed W array anywhere in the mining path.

These are source-transcribed counts (SOURCE FACT about the code's structure), not cycle measurements; the phase's benchmarking rules forbid presenting them as performance data.

## 5. What the structure implies (analysis, labelled as such)

- Because the schedule is computed just-in-time inside the round macro and the buffer is circular, the implementation carries no reusable schedule state between chunks or between candidates. Every candidate in the 0.1.3 mining loop pays the full schedule cost of both chunks of both passes (see Deliverable 11 for the loop-level accounting).
- The nonce-independence of W[16] and W[17] of chunk 2, and of all of chunk 1, is a mathematical property of the recurrence and the header layout, not of this implementation. Any implementation of Bitcoin SHA-256d faces the same dependency boundary at W[18]. Whether that boundary can be exploited by an exact optimization is a hypothesis-track question (Phase 001 deliverables 15 and 16), not a claim made here.

## 6. Reproduction

Run `python3 research/phase001/RAW_RESULTS/taint_analysis.py` (symbolic) and `python3 research/phase001/RAW_RESULTS/sha256d_layout_verify.py` (numeric, on the genesis header). Expected: first expanded differing word 18; W[16], W[17] identical; all words from 18 on differing.

## 7. Limitations

- Taint is a may-depend analysis over the dependency graph: "nonce-dependent" means the word's expression contains the nonce, so it can change when the nonce changes. It does not assert that every nonce change changes every tainted word (a specific pair of nonces could in principle collide in a given word; the numeric witness shows a one-bit change already separates all of them for the genesis template).
- The analysis covers the nonce as the varying field. nTime also sits in chunk 2 (W[1]) and changes occasionally in the loop; its taint pattern is the same shape shifted by two positions (first expanded word W[16], via lag 15 from W[1]) and is not separately tabulated here.
