# Phase 001, Deliverable 19: Independent Correctness Verification

Project: NOVA SHA-X, Research Phase 001, Wave 4.
Artifact under report: RAW_RESULTS/phase001_verification.py, a self-contained Python suite written for this deliverable. Output of the reported run: RAW_RESULTS/phase001_verification_output.txt.

## 1. Result

**36 checks, 36 passed, 0 failed. Exit code 0.** Runtime about 1.2 seconds on this host. No check failed at any point: the suite passed in full on its first execution, and the output file records a second full run after two cosmetic cleanups to the suite (removal of a dead conditional expression and a dead stub loop; no check logic changed), which also passed 36 of 36. There are no failures to analyse; this section exists because the wave rule requires failures to be reported rather than edited away, and the honest report is that there were none.

## 2. What the suite is, and why it is independent

The suite does not trust the wave 1 to 3 documents. It re-implements, from the equations and algorithms those documents transcribed, and then checks the implementations against anchors that do not come from the documents: FIPS published vectors, the genesis block's asserted hash and merkle root (constants printed in the original source, src/main.cpp lines 24 and 1479), hashlib as an independent SHA-256, and the modern arith_uint256 semantics from the v28.1 source audit. Where the documents and the suite disagree, the suite would have failed; it did not.

The from-spec SHA-256 at the suite's centre is a transcription of the 0.1.3 compression as reconstructed in Deliverable 8: the circular W[16] schedule buffer with the in-place blk2 update, the rotating-window T[8] state addressed through the a(i) to h(i) index functions, the 0.1.3 macro forms of Ch and Maj, the S0/S1/s0/s1 definitions of Deliverable 8, and the K table of Deliverable 7. It is not hashlib with extra steps: hashlib appears only as a cross-check oracle.

## 3. Section by section: what each result proves

**Section 1 (6 checks): the compression reconstruction is SHA-256.** Four FIPS vectors (empty, "abc", the 56-byte and 112-byte standard messages) pass against the from-spec implementation; the from-spec implementation agrees with hashlib on 120 seeded random messages of lengths 0 to 199; the 0.1.3 Ch and Maj macro forms agree with the textbook forms on 100,000 random triples. Together these pin Deliverable 8's equations: a transcription error in any rotate amount, macro form, buffer indexing or feed-forward step would fail the vectors.

**Section 2 (2 checks): the double hash.** SHA-256d of the empty input equals the published vector 5df6e0e2...c9456; the from-spec double hash agrees with hashlib's double hash at the padding boundary lengths 55, 56, 64, 119 and 128 bytes, which is where framing errors live.

**Section 3 (1 check): the 0.1.3 framing arithmetic.** A byte-exact re-implementation of FormatHashBlocks (main.cpp lines 2138 to 2151) yields 2 blocks for an 80-byte input and 1 block for a 32-byte input, matching the miner's nBlocks0 = 2 and nBlocks1 = 1.

**Section 4 (9 checks): the genesis anchors, end to end.** The coinbase is rebuilt byte by byte from the Deliverable 5 construction (204 bytes, checked); its txid is the asserted merkle root (single-transaction tree); the 80-byte header assembled from the Deliverable 6 field values equals the known header hex byte for byte, and its field offsets decode back to the source values; the header's SHA-256d equals the asserted genesis hash by three independent routes: hashlib, the from-spec implementation, and a reconstruction of the 0.1.3 miner's own path (FormatHashBlocks framing plus BlockSHA256's little-endian word-reversal discipline over the from-spec Transform). The manual framing is byte-identical to standard FIPS padding for both passes. The BuildMerkleTree odd-node rule is executed on a synthetic three-leaf tree and equals H(H(A||B) || H(C||C)), confirming Deliverable 5's clamping analysis.

**Section 5 (4 checks): SetCompact, both eras.** Eleven encodings (the Deliverable 12 vector table, including the sign-bit encoding 0x1e80ffff, the overflow encodings 0x2200ffff and 0x2300ffff, the sub-3-size encodings and the zero encoding) match the expected values in all five components: 0.1.3 signed Bignum value, 0.1.3 getuint256 value, modern decoded value, modern negative flag, modern overflow flag. The two decodings agree exactly on every historically valid encoding. GetCompact(SetCompact(x)) round trips for the genesis encoding and 0x1b0404cb. The genesis hash is below the genesis target by direct integer comparison.

**Section 6 (3 checks): the probability anchors.** Expected hashes at the proof-of-work limit target 2^224 - 1 equal exactly 2^32 (exact Fraction arithmetic); at the difficulty-1 target T1 the expectation matches 2^256/(T1+1) with E/2^32 = 1.0000152590218967 to 1e-12; the probability of at least one success in 2^32 trials at T1 equals 0.6321149454 to 1e-9. These pin Deliverable 12 section 8's numbers, including the correction that E = 2^32 is exact at the limit target, not at T1.

**Section 7 (5 checks): nonce coverage.** Per-template candidates equal 2^32 - 1; total coverage equals (2^32 - 1) x E for E in {1, 64, 2^16, 2^32}; housekeeping gates per full space equal 16,384; and an executable width-reduced model of the loop's control flow (start at 1, hash, pre-increment, gate on the mask, break on wrap to 0) enumerates exactly 255 candidates with 4 gates at 8 bits and 4,095 candidates with 64 gates at 12 bits, with nonce 0 never hashed in either. These pin Deliverable 13 sections 2 and 3.

**Section 8 (6 checks): the W[18] taint claims, re-run.** A symbolic taint execution of the Deliverable 9 schedule and the Deliverable 10 compression (transcribed from RAW_RESULTS/taint_analysis.py) reproduces: first nonce-dependent expanded word exactly W[18]; W[16] and W[17] clean, all W[i>=18] tainted; state bands empty for rounds 0 to 2, {a,e} at round 3, {a,b,e,f} at round 4, {a,b,c,e,f,g} at round 5, saturated from round 6; pass 2 fully tainted from round index 3; chunk 1 free of taint. A numeric witness on the real genesis header (one nonce bit flipped) shows the differing schedule words are exactly {3} union {18..63}.

## 4. What this verification does NOT establish

- It does not formally verify the C++ original. The from-spec implementation is a transcription anchored by FIPS vectors, hashlib agreement and the genesis asserts; a preprocessor-level divergence in the original macros that happened to agree on all anchors is not excluded by testing, only made implausible by the anchor density.
- The 0.1.3 SetCompact emulation follows OpenSSL's MPI format as documented and as Deliverable 12 derived it; OpenSSL source is not in the 0.1.3 tree, so the MPI byte-format step is verified against known-good values (including the genesis round trip exercised by the original code itself) rather than against OpenSSL source.
- The loop model is width-reduced control flow; the full-width counts are arithmetic identities whose inputs (start 1, mask 0x3ffff, wrap break) are the cited source lines.
- The suite performs no regtest acceptance and no mining: Phase 001's regtest evidence lives in the production audits of the EXP-030 era, and this phase's rule was verification of the reconstruction, not new block production.
- The suite makes no performance statement of any kind.

## 5. Reproduction

```
python3 research/phase001/RAW_RESULTS/phase001_verification.py
```
Exit code 0 if and only if every check passes. Output of the reported run: RAW_RESULTS/phase001_verification_output.txt (36 PASS lines, TOTAL: 36 checks, 36 passed, 0 failed).
