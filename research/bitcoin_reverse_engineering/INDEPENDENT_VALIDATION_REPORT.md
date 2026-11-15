# Independent Validation Report

NOVA SHA-X Master Assignment, deliverable 19 (work package BR-017,
independent audit and final validation). Date: 2026-11-15.

Reviewer position: this report was written by an agent that did not
author waves A, B or C of this assignment's deliverables, nor the
Phase A audit, nor Phase 001. Every check below was re-performed
against the pinned sources, the production tree, or the saved raw
outputs, not taken from the documents under review. Outcomes are
CONFIRMED (the claim matches the evidence re-examined),
CORRECTED (the claim was wrong; the correction is stated), or
UNRESOLVED (the evidence available to this review could not settle
it). Defects are listed in section 4 for the parent to disposition;
no other wave's files were modified by this review.

## 1. The checks and their outcomes

### Check 1: the flags form is not in the live search path (wave A/C claim; audit Q1)

Re-performed from production source (gpu/engine.py,
mining/cpu/bal_avx512_flags.c) and from the built library:

- bal_v_batchf2 is called from exactly one production function,
  _vf_batch_flagged (gpu/engine.py line 1385; the call at line
  1401), which is called from the batch_search routing block
  (line 1947) and from the _try_v512flags self-test (line 1337).
- The body of search_first_counted (lines 1459 to 1620, the live
  search path reached from mining/mainnet_live.py line 185 through
  search_first) contains no reference to the flags library,
  _vf_batch_flagged, or bal_v_batchf2.
- The built flags library (.local/cpu/libbal_v512flags.so) exports
  exactly three defined text symbols: bal_v_batchf2,
  bal_v512_supported, bal_v512_feature_bits. There is no search
  entry point in the library.

**Outcome: CONFIRMED.** The flags adoption is batch-scope only, in
the call graph and in the binary.

### Check 2: the probability anchor separation (wave B claim)

The claim: the exact-target anchor 1 - (1 - p(T1))^(2^32) =
0.6321149454 and the difficulty-form anchor 1 - (1 - 2^-32)^(2^32)
= 0.6321205589 are different numbers, differing in the fifth
decimal, and both are pinned separately in
BITCOIN_MINING_PROBABILITY_MODEL.md so a test cannot conflate
them.

Recomputed independently at 40-digit precision (mpmath), not by
rerunning the wave's script:

- Exact-target anchor: 0.632114945433764, which rounds to
  **0.6321149454**. Matches.
- Difficulty-form anchor: 0.632120558871384, which rounds to
  **0.6321205589**. Matches.
- 1 - 1/e: 0.632120558828558, which rounds to 0.6321205588, the
  value the model quotes for it in its section 3. It is a third,
  distinct number, differing from the difficulty-form anchor in
  the tenth decimal place.
- E(T1) / 2^32 recomputed: 1.0000152590218967, matching the
  model's bridge constant exactly.
- The saved RAW_RESULTS output
  (probability_anchors_verify_output.txt) agrees with the model
  document on every anchor this review compared (lines 7, 9, 12,
  13, 31).

**Outcome: CONFIRMED.** The separation is real, the values are
correct, and they are pinned in the right places.

### Check 3: the verified rate table against its experiment reports (wave C claim)

Four entries of HASHRATE_MEASUREMENT_SPECIFICATION.md section 9
were traced to their source reports (the required sample was
three):

- v512 vs production C, pooled 3.55x [3.17, 3.97]: phase6/
  EXPERIMENT_RESULTS.md line 261 ("ratio 3.55x (CI 3.17x to
  3.97x)") and phase6/PHASE6_FINAL_REPORT.md line 233. Match.
- EXP-026 DualMask vs production search, pooled 1.718x
  [1.511, 1.955]: phase6b/EXPERIMENT_RESULTS.md line 182 and
  phase6b/PHASE6B_FINAL_REPORT.md line 150, both carrying the
  ratio, the interval, and "significant in every session". Match.
- EXP-032 entries (AVX2 batch 1.409x [1.340, 1.480]; SHA-NI
  streams-4 batch 2.861x [2.671, 3.089]; production dual search
  vs C search 6.781x [6.154, 7.467]; production SHA-NI intrin
  0.517x [0.497, 0.536] ESTABLISHED NEGATIVE): exp032/
  EXP032_REPORT.md lines 43 to 54 carry all five figures with
  matching intervals and verdicts. Match.
- H-01 streams-4 strided, pooled 2.80x [2.53, 3.09]: phase6/
  EXPERIMENT_RESULTS.md line 266 ("ratio 2.80x (CI 2.53x to
  3.09x)"). Match.

**Outcome: CONFIRMED** for every sampled figure, interval and
verdict label.

### Check 4: the SetCompact era comparison against both source trees (wave B claim)

Re-read in the pinned trees:

- v28.1, src/arith_uint256.cpp lines 175 to 193: nSize = nCompact
  >> 24; mantissa masked to 0x007fffff; shift semantics as
  specified; fNegative reported only when nWord != 0 and the sign
  bit is set; fOverflow by exactly the three size tests the
  specification lists; SetCompact itself rejects nothing.
- v28.1, src/pow.cpp lines 137 to 154: CheckProofOfWork rejects on
  fNegative, zero target, fOverflow, or target above powLimit,
  then rejects hash > target. Equality is accepted. Exactly as
  specified.
- v0.1.3, src/bignum.h lines 257 to 268: CBigNum::SetCompact
  builds the MPI byte string by hand (4-byte length, three
  mantissa bytes, zero padding) and calls BN_mpi2bn, so the sign
  bit becomes a true BIGNUM sign and the mantissa is not masked to
  23 bits before decoding. Exactly as specified.
- v0.1.3, src/bignum.h lines 218 to 231: getuint256 clears the MPI
  sign byte (vch[4] &= 0x7f) and copies at most 32 bytes, so the
  sign is silently dropped and oversize values silently truncate.
  Exactly as specified.

**Outcome: CONFIRMED** on every point of the era comparison,
including the divergence table's three cases.

### Check 5: the Phase 001 verification suite output (Phase 001 claim)

The saved output (research/phase001/RAW_RESULTS/
phase001_verification_output.txt) was re-counted: 36 lines
beginning PASS, 0 lines beginning FAIL, and the closing line
"TOTAL: 36 checks, 36 passed, 0 failed". The suite covers, among
its sections, the from-spec compression implementation against
FIPS vectors and hashlib, the genesis block end to end, SetCompact
vectors across both eras, nonce coverage arithmetic, and the W[18]
taint claims re-run symbolically and by numeric witness (the final
PASS lines, visible in the output, are the taint checks).

**Outcome: CONFIRMED.** The suite's recorded result is 36 of 36,
as claimed. (This review re-counted the recorded output; it did
not re-execute the suite, and says so.)

### Check 6: wave A Core line citations (sampled)

Re-read in the pinned v28.1 tree:

- GBT template cache: the statics pindexPrev, time_start and
  pblocktemplate sit at src/rpc/mining.cpp lines 801 to 803, and
  the rebuild condition (no cache, or tip changed, or transactions
  updated AND more than 5 seconds elapsed) at lines 804 to 805.
  As cited.
- Server coinbase: src/node/miner.cpp line 161 reads exactly
  coinbaseTx.vin[0].scriptSig = CScript() << nHeight << OP_0,
  with the value line (nFees + GetBlockSubsidy) at line 160. As
  cited.
- Testnet4 BIP94: src/pow.cpp lines 66 to 75 read the retarget
  base from the first block of the difficulty period when
  enforce_BIP94 is set. As cited.
- IncrementExtraNonce: a scoped re-grep over src/rpc, src/node,
  src/primitives, src/consensus, src/validation.cpp and
  src/pow.cpp returned zero occurrences, consistent with the Core
  audit's full-tree search, which remains the primary evidence
  for the tree-wide claim.

**Outcome: CONFIRMED** for every sampled citation.

### Check 7: all 19 named deliverables exist

Verified by file inventory after wave D: the 13 wave A to C
deliverables were present before this wave, and deliverables 14
to 19 were produced by it. Full paths:

1. research/bitcoin_reverse_engineering/COMPLETE_BITCOIN_PROTOCOL_MAP.md
2. research/bitcoin_reverse_engineering/BITCOIN_CORE_SOURCE_AUDIT.md
3. research/bitcoin_reverse_engineering/BITCOIN_MINING_CALL_GRAPH.md
4. research/sha256d/SHA256D_MATHEMATICAL_SPECIFICATION.md
5. research/bitcoin_reverse_engineering/BLOCK_HEADER_SERIALIZATION_SPECIFICATION.md
6. research/proof_of_work/PROOF_OF_WORK_AND_DIFFICULTY_SPECIFICATION.md
7. research/bitcoin_reverse_engineering/MINING_TEMPLATE_AND_COINBASE_SPECIFICATION.md
8. research/nonce_search/NONCE_AND_SEARCH_SPACE_MODEL.md
9. research/cpu_architecture/CPU_INSTRUCTION_EXECUTION_REPORT.md
10. research/cpu_architecture/VM_RESOURCE_CAPACITY_REPORT.md
11. research/hashrate/HASHRATE_MEASUREMENT_SPECIFICATION.md
12. research/probability/BITCOIN_MINING_PROBABILITY_MODEL.md
13. research/bitcoin_reverse_engineering/NODE_AND_SUBMISSION_ARCHITECTURE.md
14. research/cryptanalysis/CRYPTANALYSIS_AND_SHORTCUT_RESEARCH.md
15. research/bitcoin_reverse_engineering/NOVA_BITCOIN_CORE_GAP_ANALYSIS.md
16. research/architecture/NOVA_PRODUCTION_MINING_ARCHITECTURE.md
17. research/experiments/EXPERIMENT_REGISTER.md
18. research/MASTER_RESEARCH_FINDINGS.md
19. research/bitcoin_reverse_engineering/INDEPENDENT_VALIDATION_REPORT.md (this file)

**Outcome: CONFIRMED**, 19 of 19.

### Check 8: zero long dash across the wave A to D deliverables

A byte-level scan for the long dash character (U+2014) over the 19
deliverable files returned zero occurrences. (The scan was run
over the 18 completed files before this report was finalised and
re-run over all 19, this file included, at closing; both runs are
recorded in the wave's working notes.)

**Outcome: CONFIRMED.**

### Check 9: no category violations in the deliverables

- Every occurrence of the EXP-025 steps500 figure (pooled 23.02x)
  in the wave documents was read in context (5 occurrences across
  the audit, the measurement specification, the architecture
  deliverable and this wave's register): each labels it a
  candidate-construction rate, never a hash rate.
- The throughput gap figures (about 24,272 and about 33,800
  systems to 500 GH/s; about 6.8 million and about 9.5 million to
  140 TH/s) appear only as system counts under stated bases and
  assumptions (VM_RESOURCE_CAPACITY_REPORT.md section 9 and the
  documents citing it), never as measured performance. The
  measurement specification's table explicitly excludes the
  theoretical model-band figures, and no theoretical aggregate
  (per-core model bands, planning core counts) is presented as a
  measurement in any wave A to D deliverable.
- Pool shares are nowhere presented as blocks; the success
  criterion is stated NOT MET in the gap analysis, the
  architecture deliverable and the master findings.

**Outcome: CONFIRMED.**

## 2. Outcome counts

- CONFIRMED: 9 checks (checks 1 to 9), covering 6 sampled rate
  figures with intervals, 4 probability anchors and constants, 4
  SetCompact source points, 4 Core line citations, 36 suite
  results, 19 file existences, and 5 construction-rate labellings.
- CORRECTED: 0.
- UNRESOLVED: 0.

No decisive claim sampled by this review failed against its
evidence. That is a statement about the sample, not a blanket
certification of every sentence in 19 documents; the unsampled
remainder inherits the audits' own verification, which this review
found reliable exactly where it tested it.

## 3. What this review did not do

- It did not re-execute the Phase 001 verification suite or the
  probability script; it re-counted the former's recorded output
  and independently recomputed the latter's anchors at higher
  precision.
- It did not run any benchmark, and it re-verified no rate by
  measurement; rate checks were document-to-report traces.
- It did not re-audit production code beyond the flags call graph
  and the library symbol table; the production audit of record
  remains the Phase A audit and the per-integration audits
  (EXP-034, EXP-036, EXP-037/038).
- It did not check the two standing registries line by line
  against the unified register (deliverable 17); it sampled the
  verdicts it cited.

## 4. Defect and observation list (for parent disposition)

No material defect was found. The following are recorded however
small, per this review's instructions:

- **OBS-1 (precision trap, handled correctly, recorded so it
  stays handled).** Three distinct numbers live within 6e-6 of
  each other in the probability material: 0.6321149454 (exact
  target), 0.6321205588 (1 - 1/e) and 0.6321205589 (difficulty
  form). The model documents pin each correctly, but a future
  editor "correcting" one into another would introduce a real
  error while appearing to fix one. Recommendation: keep the
  model's section 8 warning verbatim in any future summary.
- **OBS-2 (placement).** VM_RESOURCE_CAPACITY_REPORT.md sits
  under research/cpu_architecture/. The Master Assignment's
  structure defines no VM directory, so the placement is
  defensible, but a reader following the assignment's directory
  list will not look there. Recommendation: a one-line pointer in
  research/benchmarks/README.md or the research index, at the
  parent's convenience. Not a content defect.
- **OBS-3 (sourcing style).** In the measurement specification's
  rate table, the H-01 streams-4 entry is sourced to "EXP-017
  decision set (EXP-003/005 family)" rather than to one report
  file. The figure traces cleanly (this review found it at
  phase6/EXPERIMENT_RESULTS.md line 266), so this is a
  traceability style note, not an error.
- **OBS-4 (scope note on check 6).** The tree-wide absence of
  IncrementExtraNonce rests on the Core audit's full-tree search;
  this review's re-grep covered the mining-relevant directories
  and found zero, which is consistent but narrower. Recorded so
  the strength of the evidence is stated exactly.
- **OBS-5 (carried, not new).** The 11 documentation
  contradictions of the Phase A audit (gap analysis section 4)
  remain unfixed, and two test helpers (test-regtest,
  test-engine) still lack the loadwallet step five sibling tests
  have. Both are already recorded in the audit and the gap
  analysis; this review re-lists them only so the closing report
  of the assignment carries the complete open list in one place.

## 5. Closing statement

Waves A to D, taken together, satisfy the Master Assignment's
deliverable list: 19 of 19 named deliverables exist, are grounded
in the pinned sources and the programme's raw records, carry their
tiers and scopes, and state the unmet success criterion plainly.
The independent sample in section 1 found the decisive claims
accurate at every point tested. The open frontier is exactly
where the documents say it is: E2 unproven, two verified tiers
undispatched, one benchmark category unbuilt, statistics unwired,
probability percentiles unimplemented, distribution unbuilt in
production, 11 documents contradicting the code they describe,
and no block. Balance: 0 BTC.
