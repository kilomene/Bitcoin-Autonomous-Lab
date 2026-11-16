# Research Opportunity Register (Master Build Mandate, section 17)

Date: 2026-11-15. This is the consolidated, living register for the
NOVA SHA-X programme. It SUPERSEDES the seed register
(research/master_build/RESEARCH_OPPORTUNITY_REGISTER_SEED.md) as the
living register; the seed file is left untouched as the record of the
Milestone 0 mapping pass. Every row below keeps its decision evidence
from its source; no decision was invented or reworded in the merge.

Sources merged:

- The Milestone 0 seed: 247 rows (X-series 116, Y-series 108,
  EXP-033 hypotheses 14, Phase 001 hypotheses 9), themselves mapped
  from research/sha256d/extreme_optimization/HYPOTHESIS_REGISTRY.md,
  HYPOTHESIS_REGISTRY_Y.md, research/sha256d/exp033/
  HYPOTHESIS_REGISTRY.json and research/phase001/
  MATHEMATICAL_OPTIMIZATION_HYPOTHESES.md under the seed's stated
  mapping rules.
- The historical opportunity register: 35 rows (R-01 to R-35) from
  research/master_build/HISTORICAL_OPPORTUNITY_REGISTER.md, each
  backed by research/master_build/HISTORICAL_MINER_RESEARCH.md.

Status vocabulary (mandate section 17): NEW, UNDER_INVESTIGATION,
EXPERIMENTAL, PROVEN, INTEGRATED, REJECTED, DEFERRED.

Historical rows used ALREADY COVERED and NEW. In this register the
ALREADY COVERED rows are mapped by what the coverage is: INTEGRATED
when production code carries the idea, PROVEN when a proof or a
verified prototype campaign carries it, DEFERRED when the recorded
decision is to not implement it now (R-12, R-21). The historical
status text is preserved verbatim at the head of each such row's
decision evidence. R-23, R-24 and R-35 were NEW in the historical
register and are EXPERIMENTAL here because this build implemented
them as advisory or partial components (noted per row). R-28 was NEW
and is DEFERRED here because its own row gates it on an owner Core
version decision.

Deduplication: two historical rows restate seed hypotheses and are
merged into them, citing both sources: R-01 (midstate reuse) into
H-1, and R-02 (chunk-2 prefix precomputation) into H-6. All other
historical rows stand as their own rows. Cross-references that are
related but not duplicates: R-33 (prepared-work prefetch queue)
against X-056 and Y-035 (next-template prefetch and header prefetch);
R-05 (screen then exact test) against H-033-12 (partial outer digest
comparison, a different and rejected idea).

Total rows: 280 (247 seed rows, 35 historical rows, 2 merged).

## EXP-033 hypotheses (H-033-01 to H-033-14)

Source: research/sha256d/exp033/HYPOTHESIS_REGISTRY.json via the seed
register. Related experiment for all rows: EXP-033, plus EXP-042 where
the decision says so.

| ID | Hypothesis | Mandate status | Decision / evidence |
|---|---|---|---|
| H-033-01 | A cheaper graph for the two-round round function exists within the word-level rewrite system R1 to R6. | REJECTED | E-graph equality saturation found no cheaper graph; extraction costs identical before and after; soundness 380,520 enode evaluations, 0 mismatches. ESTABLISHED NEGATIVE at the stated bounds. |
| H-033-02 | A 5-instruction straight-line program over V = {ADD, LUT, ROTR, SHR} computes a full round cone, against the proven 6-instruction incumbents. | UNDER_INVESTIGATION | Full-cone CEGIS at L=5 inconclusive in EXP-033 (600 s timeout) and again in EXP-042 (1,500 s and 1,400 s per cone). Narrowed by H-033-03, H-033-04, H-033-13, H-033-14 and closed for the E2 shape by EXP-042; open only for shapes outside EXP-042's stated bounds (sum or Boolean output produced by two or more instructions). |
| H-033-03 | Sigma0 is computable in 3 instructions over V given arbitrary independent side values. | REJECTED | CEGIS UNSAT at iteration 0; the 4-instruction incumbent is proven exact; minimum is exactly 4. |
| H-033-04 | Sigma1 is computable in 3 instructions over V given arbitrary independent side values. | REJECTED | CEGIS UNSAT at iteration 0; minimum is exactly 4, as for Sigma0. |
| H-033-05 | A 5-instruction cone exists via the shapes the Sigma bound does not cover: (E1) exploiting the s = T1 + T2 correlation, (E2) routing the Sigma output through the Maj/Ch value. | REJECTED | E1 excluded by EXP-033 (H-033-13, H-033-14). E2 REFUTED by EXP-042 decomposition synthesis: z3 UNSAT for both cones at the stated bounds (straight-line over V, cone length 5, sum by a single ADD, Boolean output by a single LUT). The cone minimum over V is exactly 6 under those bounds. |
| H-033-06 | The conventional implementation computes 67 of 192 round slots per template, as conventional accounting. | PROVEN | VERIFIED as accounting (re-derived in EXP-033 scope 2). Explicitly not a lower bound. |
| H-033-07 | The schedule delta identities D(W18) = sigma0(nonce) and D(W19) = nonce hold exactly. | PROVEN | VERIFIED: 100,000 of 100,000 samples and z3 UNSAT for the negation; consistent with EXP-016. |
| H-033-08 | After 3 rounds of the second inner block, state words a and e are integer-affine in the nonce with slope 1. | PROVEN | VERIFIED in EXP-033 scope 2 (affinity dies by S_8 per EXP-016; no work reduction follows). |
| H-033-09 | D(W20) is GF(2)-linear in the nonce delta, so the schedule admits a linear representation past W19. | REJECTED | REFUTED by a z3 counterexample, numerically re-verified (EXP-016, EXP-033). |
| H-033-10 | Some part of the outer SHA-256 compression is digest-independent and precomputable. | REJECTED | ESTABLISHED NEGATIVE: 48 of 48 computed schedule words and 64 of 64 rounds are digest-dependent; 0 independent rounds. |
| H-033-11 | A redundant (carry-save) representation of a produced state word can defer resolution across the round boundary. | REJECTED | ESTABLISHED NEGATIVE: every round addition has deferral distance exactly 0 (EXP-027, confirmed in EXP-033). |
| H-033-12 | Comparing a partial outer digest against the target can abandon a trial before all 64 outer rounds complete, saving work. | REJECTED | ESTABLISHED NEGATIVE in EXP-033 scope 2: comparison early exit saves no rounds. |
| H-033-13 | Sigma1(e') is computable in 3 instructions over V by exploiting the correlation e' = d + T1. | REJECTED | Cone-conditioned synthesis UNSAT (16 cone-realizable examples). |
| H-033-14 | Sigma0(a') is computable in 3 instructions over V by exploiting the correlation a' = T1 + T2. | REJECTED | Cone-conditioned synthesis UNSAT (16 cone-realizable examples). |

## Phase 001 hypotheses (H-1 to H-9)

Source: research/phase001/MATHEMATICAL_OPTIMIZATION_HYPOTHESES.md via
the seed register. H-1 and H-6 also carry their merged historical
register rows (R-01 and R-02), cited in the decision column.

| ID | Hypothesis | Mandate status | Related experiments | Decision / evidence |
|---|---|---|---|---|
| H-1 | Midstate reuse (the optimisation the original miner skipped). | INTEGRATED | EXP-002, EXP-007 lineage | Proven identity and exact optimisation; in production: every production kernel consumes a prepared first-block state (gpu/engine.py backends; mining/engine.py PreparedTemplate). Closed. Merged historical row R-01 (compute the chunk-1 midstate once per template and reuse it for every nonce; jgarzik/cpuminer cpu-miner.c, pooler/cpuminer sha2.c): ALREADY COVERED: Phase 001 H-1; production since the first C backend; re-verified EXP-023, EXP-025 (research/master_build/HISTORICAL_OPPORTUNITY_REGISTER.md). |
| H-2 | The 56 per-candidate byte-reversals of the 0.1.3 miner are a recoverable cost. | REJECTED | EXP-027 | Closed as an explained historical artifact: the reversals are a property of the 0.1.3 API shape and are absent from the production path; there is nothing to recover. |
| H-3 | Rotating-window state representation (register renaming by rotation). | EXPERIMENTAL | EXP-018, EXP-027 | Identity proven. Its measurable form (register-resident dual-batch) achieved residency but no significant rate (EXP-018); the distinct rotated-domain form was refuted in EXP-027. No integration as a standalone item. |
| H-4 | Circular schedule buffer. | PROVEN | EXP-027, EXP-032 | Proven identity; whether each engine uses it is decided per engine by EXP-027 and EXP-032. Closed as a hypothesis. |
| H-5 | Padding precomputation. | INTEGRATED | Phase 001 verification suite | Proven identity and exact optimisation; present in both the 0.1.3 reconstruction and the production kernels (fixed padding is folded into template preparation). Closed. |
| H-6 | Chunk-2 prefix sharing (rounds 0 to 2) as a rate improvement. | EXPERIMENTAL | EXP-013, EXP-027 | Facts proven (prefix is nonce-independent); the rate claim is open only as a combination ingredient. EXP-013 measured ratios straddling 1.0. No standalone integration. Merged historical row R-02 (precompute the nonce-independent prefix of chunk 2, rounds 0 to 2, once per template; pooler/cpuminer sha2.c sha256d_prehash): ALREADY COVERED: registry H-03; EXP-023 family; in production kernels (research/master_build/HISTORICAL_OPPORTUNITY_REGISTER.md). The seed status EXPERIMENTAL stands for the rate claim as a standalone item; the underlying prefix facts are proven and the precomputation itself is in the production kernels. |
| H-7 | K+W folding. | REJECTED | EXP-014 | Refuted: no gain as implemented; closed. |
| H-8 | The 29 vs 28 vector-op codegen gap (EXP-020) is worth closing for rate. | REJECTED | EXP-020, EXP-041 | Phase 001 carried this as open engineering. EXP-041 has since decided it: the 28-op forms are an ESTABLISHED NULL under EXP-017 on this VM, and the production DualMask search body already emits 28. Closed; the one-line intrinsic diff is recorded in the EXP-041 report as not applied and not recommended. |
| H-9 | Single-batch mask search (EXP-024 design C) should be integrated. | EXPERIMENTAL | EXP-024, EXP-024b | Kernel VERIFIED (pooled 1.398x, EXP-024b); integration value unproven against the dual-batch production form, and production kept v512dual. Stands as the certified single-batch fallback; integration is an owner decision, not an open measurement. |

## X-series (X-001 to X-116)

Source: research/sha256d/extreme_optimization/HYPOTHESIS_REGISTRY.md via the seed register. Decision text quotes the registry's dated status lines, truncated; the full text stands in the source file.

| ID | Hypothesis | Mandate status | Related experiments | Decision / evidence |
|---|---|---|---|---|
| X-001 | Three-stream interleave | EXPERIMENTAL | EXP-005 | Status update 2026-11-14 (EXP-005): MEASURED. Three streams built and gate-verified; medians sit on the flat top of the geometry curve (blocked s3 1,999,538 at 2 threads; strided s3 3,360,311). both 2 streams (less latency hidden) and 4 streams (fewer spills) per worker on this core. register spills |
| X-002 | Six-stream interleave with a spill budget | EXPERIMENTAL | EXP-005 | Status update 2026-11-14 (EXP-005): MEASURED. Six streams built and gate-verified (blocked s6 median 2,593,711 at 2 threads); the spill budget is spent in the inlined walk body (frame 1,536 B, 790 xmm stack ops shared with s4). gain over 4 streams because the core remains latency-bound at 4. stalls; |
| X-003 | Eight-stream interleave, to locate the cliff | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-004 | Strided versus blocked nonce assignment | EXPERIMENTAL | EXP-005 | Status update 2026-11-14 (EXP-005): MEASURED. Strided assignment (mode 1) meets or beats blocked at counts 3 and 4 at 2 threads in the combined session. takes nonces congruent to s mod streams) rather than in blocked chunks changes throughput measurably through wave remainder and store patterns. con |
| X-005 | Wave size decoupled from stream count | EXPERIMENTAL | EXP-005 | Status update 2026-11-14 (EXP-005): MEASURED in part. Wave dispatch remains coupled to stream count in the geo build (greedy 6/4/3/2/1 partial waves); the decoupled wave-size question stays open, low priority after the flat geometry curve. slots (double-buffered waves) beats waves of exactly the str |
| X-006 | Hand-scheduled assembly, 2 streams, explicit allocation | REJECTED | EXP-006 | EXP-006: schedule-first variant cut spill ops 790 to 117 but did not improve throughput; negative result (experiment_registry.md EXP-004 to EXP-009 summary). |
| X-007 | Hand-scheduled assembly, 4 streams, spill layout | EXPERIMENTAL | EXP-006 | EXP-006 covered X-006/X-007: the inline-assembly pair was not built because the 2-stream compiler body already has a 0 B frame and zero stack ops (experiment_registry.md EXP-004 to EXP-009 summary). |
| X-008 | Intra-nonce phase overlap at the block boundary | EXPERIMENTAL | none recorded | Status: untested. |
| X-009 | Cross-nonce phase pipelining in one worker | REJECTED | EXP-008 | EXP-008: cross-nonce phase pipelining matched a second same-phase stream and lost to deeper interleaving; the phase premium is not supported on this core. |
| X-010 | Schedule-ahead distance in the SHA-NI kernel | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| X-011 | K+W operand preparation overlap | EXPERIMENTAL | none recorded | Status: untested. |
| X-012 | Alternating state orientation between round pairs | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-013 | Alternate RNDS2 operand packing | EXPERIMENTAL | none recorded | Status: untested. |
| X-014 | Branchless winner handling inside the wave loop | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-015 | Target comparison overlapped with the next nonce | EXPERIMENTAL | none recorded | Status: untested. |
| X-016 | Inline the batch hot path | EXPERIMENTAL | none recorded | Status: untested. |
| X-017 | Hot-loop alignment and code placement | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-018 | Search-shaped benchmarking of kernels | EXPERIMENTAL | none recorded | Status: untested. |
| X-019 | Five-stream interleave (odd counts) | EXPERIMENTAL | none recorded | Status: untested. |
| X-020 | GFNI affine forms of the schedule sigmas | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| X-021 | Carry-save addition tree for T1 in vector rounds | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-022 | Carry-save state across round boundaries | EXPERIMENTAL | none recorded | Status: untested. |
| X-023 | Outer-hash schedule partial evaluation | EXPERIMENTAL | none recorded | Status: untested. |
| X-024 | Template-fixed message operands, rounds 0 to 17 | NEW | none recorded | Registry entry carries no dated status update; registration status: tested. |
| X-025 | Extranonce-major iteration geometry | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-026 | Timestamp as the fast loop variable (refutation expected) | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-027 | Superoptimized joint Boolean cone | NEW | none recorded | Registry entry carries no dated status update; registration status: tested. |
| X-028 | Addition-tree reassociation under a port model | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-029 | Bitsliced SHA-256 (analytic bound, refutation expected) | NEW | none recorded | Registry entry carries no dated status update; registration status: tested. |
| X-030 | Feed-forward folded into the target comparison | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-031 | AVX-512 16-way multi-buffer SHA-256d | INTEGRATED | EXP-007 | Built as EXP-007 (AVX-512 16-way multi-buffer); the kernel lineage was integrated as production backend v512 under the EXP-017 rule (integration record, experiment_registry.md) and survives in mining/cpu/bal_avx512_mb.c. |
| X-032 | AVX-512 8-way multi-buffer | EXPERIMENTAL | EXP-007 | Status update 2026-11-14 (EXP-007): NOT BUILT. Note this entry is the 8-lane AVX-512 form; the AVX2 form discussed in EXP-007 shares its register-file logic. The 16-way result decided the family ranking first; remains for narrower machines. pair avoided; 8 active lanes in zmm or 8 in ymm with AVX-51 |
| X-033 | AVX2 8-way multi-buffer | EXPERIMENTAL | none recorded | Status: untested. |
| X-034 | 128-bit 4-way multi-buffer (control) | EXPERIMENTAL | none recorded | Status: untested. |
| X-035 | Hybrid phases: SHA-NI block 2, vector outer hash | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-036 | Vector rotate by shuffle versus vprold | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-037 | AVX-512 IFMA applicability (refutation expected) | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-038 | AVX-512 VNNI applicability (refutation expected) | EXPERIMENTAL | none recorded | Status: untested (analysis entry). |
| X-039 | Lane refill by gather versus register transpose | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-040 | Multi-buffer lanes bound to different templates | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-041 | Sustained AVX-512 frequency behaviour | EXPERIMENTAL | EXP-007 | EXP-007 gate: AVX-512 frequency gate inconclusive under contention; no catastrophic AVX-512 penalty found. |
| X-042 | Mask-predicated partial waves | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-043 | Clang build of the hand kernels | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-044 | Profile-guided optimization of the H-01 kernel | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-045 | Flag sweep restricted to the research kernels | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| X-046 | Manual intrinsic reordering in H-02 source | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-047 | Aliasing and alignment annotations in H-01 | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-048 | SMT-verified peephole pass over the hot function | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-049 | Parameterized kernel generator and sweep driver | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-050 | Link-time optimization across the research kernels | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-051 | Hot and cold section split | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-052 | Vector width preference tuning for multi-buffer | EXPERIMENTAL | none recorded | Status: untested. |
| X-053 | Non-temporal stores for the batch digest buffer | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-054 | Ring-buffer output with consumer overlap | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-055 | Interleaved digest and flag layout | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-056 | Next-template prefetch during the span tail | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-057 | Rolled versus unrolled stream body | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-058 | Single-cache-line template struct | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-059 | Candidate construction caching in MiningEngine | INTEGRATED | EXP-009 | Priced by EXP-009 (one validateaddress plus one getblockchaininfo RPC per build_candidate call); the caching it named was built by EXP-023 (Y-077) and integrated through EXP-025 into mining/engine.py (TemplateCache). |
| X-060 | Incremental merkle spine per extranonce | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-061 | In-place extranonce patching of the coinbase | EXPERIMENTAL | none recorded | Status: untested. |
| X-062 | Event-driven span preemption | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-063 | Verification overlap at dense targets | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-064 | Template double-buffering in mine_cycle | EXPERIMENTAL | none recorded | Status: untested. |
| X-065 | Stratum extranonce2 pre-generation | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-066 | Evidence and status I/O off the mining loop | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-067 | Quiet-window integration decision re-run | DEFERRED | EXP-004, EXP-010 | Decision re-runs EXP-004 and EXP-010 both failed the predeclared beyond-spread criterion; the underlying integration question was later settled by adopting the EXP-017 statistic (EXP-017 record), so the re-run itself is superseded. |
| X-068 | Drift across VM replacements | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-069 | Session fingerprinting of benchmark records | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-070 | Steal-time covariate | EXPERIMENTAL | EXP-000, EXP-003, EXP-004 | Status update 2026-11-14 (EXP-004): APPLIED in lite form. Steal was 2.24 percent of jiffies during the 2-thread decision config; runnable-load fluctuation, not steal, drives the spreads. /proc/stat) during each benchmark run and regressing measured rate against steal explains a majority of the sessi |
| X-071 | Minimum detectable effect sizing | EXPERIMENTAL | none recorded | Status: untested. |
| X-072 | Paired-run ratio design | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-073 | Thread and stream mix under the cap | EXPERIMENTAL | none recorded | Status: untested. |
| X-074 | Three worker threads for the H-01 kernel | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-075 | Stop-flag granularity in multi-stream search | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| X-076 | Chunk-claim size sweep in the research kernel | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| X-077 | Heterogeneous workers | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-078 | Alternative MSG grouping (GENC-style) | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-079 | Pre-rotated schedule copies to cut alignr use | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-080 | Nonce-affine decomposition of the block-2 schedule | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-081 | Best-so-far return from search | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-082 | Measured dispatch ladder, extended | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-083 | Span-length crossover for kernel selection | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-084 | Fallback ladder equivalence verification | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-085 | Sustained-rate decay of the fast kernels | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-086 | Lock-free winner publication | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| X-087 | False sharing in per-worker counters | EXPERIMENTAL | none recorded | Status: untested. |
| X-088 | Vectorized target comparison for batch consumers | EXPERIMENTAL | none recorded | Status: untested. |
| X-089 | Target-specialized exact comparator | EXPERIMENTAL | none recorded | Status: untested. |
| X-090 | Pre-swapped header storage for the OpenSSL wrapper | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-091 | Superoptimizer search over inter-pair shuffles | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-092 | Peephole equivalence pass on shipped binaries | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-093 | Genetic search over stream interleave orders | EXPERIMENTAL | none recorded | Status: untested. |
| X-094 | Logic minimization of the joint Ch/Maj cone | NEW | none recorded | Registry entry carries no dated status update; registration status: tested. |
| X-095 | Bayesian optimization over kernel parameters | EXPERIMENTAL | none recorded | Status: untested. |
| X-096 | Cross-backend differential fuzzing at scale | EXPERIMENTAL | none recorded | Status: untested. |
| X-097 | Partial-state target early abort (formal closure) | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-098 | Winner-cluster start offsets (formal closure) | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-099 | Meet-in-the-middle split of SHA-256d (formal closure) | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-100 | Nonce-chosen schedule cheapening (formal closure) | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-101 | Kernel-level ntime rolling inside the search loop | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-102 | Producer-consumer phase pipeline across threads | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-103 | Self-contained template setup in the research lib | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-104 | Multi-template single-call search | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| X-105 | Dual-target flags in-kernel | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-106 | Wave-granularity work stealing between workers | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| X-107 | Cross-machine ranking portability (blocked on hardware) | EXPERIMENTAL | none recorded | Status: untested, blocked on a second machine. |
| X-108 | Steal-aware yielding (speculative) | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-109 | Fully unrolled block-2 body versus rolled | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-110 | Outer K-stream built during block 2 | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-111 | Prefix-only digest stores in batch mode | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-112 | Vectorized merkle root for large templates | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-113 | Coinbase txid caching across templates | EXPERIMENTAL | none recorded | Status: untested. |
| X-114 | Function placement in the shipped miner binary | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-115 | Stream count selected per span length | NEW | none recorded | Registry entry carries no dated status update; registration status: untested. |
| X-116 | Schedule prefetch distance in multi-buffer | EXPERIMENTAL | none recorded | Status: untested. |

## Y-series (Y-001 to Y-108)

Source: research/sha256d/extreme_optimization/HYPOTHESIS_REGISTRY_Y.md via the seed register. Decision text quotes the registry's dated status lines, truncated; the full text stands in the source file.

| ID | Hypothesis | Mandate status | Related experiments | Decision / evidence |
|---|---|---|---|---|
| Y-001 | Carry-save generation of the multi-buffer message schedule | REJECTED | EXP-019 | Status (2026-11-14, EXP-019): REJECTED as a work reduction on this instruction set, at the pricing level. The engine was not built: its design point (Y-002) failed the price gate, and the recurrence bounds deferral to separation 1 (sigma1 consumes W[t] for W[t+2]; a sigma cannot consume a redundant |
| Y-002 | Four-input schedule addition via one carry-save level, costed against the add tree | REJECTED | EXP-019 | Status (2026-11-14, EXP-019): REJECTED as a cheaper materialization; the experiment's own success (a measured per-distance winner table) is delivered, and the winner at every relevant distance is the incumbent add tree. Resolved carry-save costs 5 instructions and a 4-stage chain (one level) or 7 an |
| Y-003 | Balanced T1 addition tree under a measured vector port model | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-004 | Bitsliced schedule, vector rounds (hybrid representation) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-005 | Target comparison in the transposed domain | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-006 | Sixteen-bit split addition with carry prediction in the vector kernel | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-007 | Double-density sub-lane representation (two 16-bit halves per lane) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-008 | GFNI affine decomposition search for Ch and Maj | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-009 | Arithmetic form of Maj as an addition identity (closure candidate) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-010 | Sigma functions via VBMI2 permutes plus ternlog | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-011 | Per-byte table-driven rounds (closure candidate) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-012 | Sparse-share decomposition of the nonce word | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-013 | Joint (Ch, Maj) cone search with shared intermediates | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-014 | SAT-guided rewriting of one full round, rotations and adds included | PROVEN | EXP-012, EXP-020 | EXP-020: supported as an instrument, negative as a discovery on the round cone (experiment_registry.md EXP-020). |
| Y-015 | Equality saturation (e-graph) over the round expression | PROVEN | EXP-020 | EXP-020: supported as an instrument, negative as a discovery on the round cone (experiment_registry.md EXP-020). |
| Y-016 | Genetic search over schedule-generation instruction sequences | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-017 | Joint small-sigma search (s0 and s1 sharing rotations) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-018 | Learned ranking to prune rewrite search | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-019 | Automatic proof obligations per transformation | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-020 | IFMA-domain add/XOR identities (closure candidate) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-021 | Fused (S1, Ch) cone search | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-022 | Partial evaluation of the outer-block schedule in MB | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-023 | Register-resident dual-batch MB (full unroll) | EXPERIMENTAL | EXP-018 | EXP-018: register residency achieved, rate not significant under EXP-017 (pooled 1.087x, CI contains the null pooled); PROMISING HYPOTHESIS tier, not integrated as its own kernel; its dual-batch shape is an ingredient of EXP-026 C2. |
| Y-024 | Triple-batch MB interleave (spill cliff locator) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-025 | Schedule-ahead distance sweep in MB | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-026 | Heterogeneous-width batching (zmm batch plus ymm batch in one worker) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-027 | Two 8-lane half-width batches interleaved | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-028 | Mask-predicated partial groups (closure candidate) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-029 | In-register transpose between block 2 and the outer hash | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-030 | Group-strided nonce assignment for finer search granularity | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-031 | Fused outer-of-n with block-2-of-n+1 in the vector family | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-032 | Vectorized block-1 for short-span amortization | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-033 | Register-resident schedule ring via full unroll (single batch) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-034 | Sigma rotations by shift pairs under port pressure | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-035 | Next-template header prefetch during the span tail | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-036 | In-vector top-word target pre-filter for search | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-037 | Heterogeneous worker: SHA-NI streams fused with an MB batch in one thread | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-038 | Shared schedule builder for SHA-NI streams | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-039 | MB lanes as the schedule engine for SHA-NI streams | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-040 | Adaptive stream count across a span (drain-down geometry) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-041 | Per-stream hit channels (finer stop granularity) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-042 | Two workers sharing one MB batch ring (closure candidate) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-043 | Dual-batch interleave granularity sweep | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-044 | Multi-template streams in one worker | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-045 | Ping-pong wave double-buffering in H-01 | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-046 | Kernel-family partitioning of the nonce space by range shape | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-047 | Bounded superoptimizer for one SHA-NI round pair | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-048 | Superoptimizer for the MB T1 addition chain under a port model | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-049 | Enumerated register assignment for the unrolled 2-stream kernel | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-050 | Measured uop latency table as the scheduling ground truth | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-051 | Source-parameter sweep for the MB compress (unroll, inline, ring placement) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-052 | Assembly-profile regression gate for research kernels | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-053 | Hot/cold layout for the MB walker | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-054 | Superoptimized digest extraction for MB groups | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-055 | State rematerialization in the MB round (closure candidate) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-056 | Schedule generation distance in a single MB batch | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-057 | One-round-ahead Boolean precompute for Ch | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-058 | Carry-select T1 addition in the vector kernel | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-059 | Schedule word rematerialization versus ring storage | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-060 | Feed-forward folded into the final round | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-061 | Alternating state orientation in the MB round | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-062 | Stall-proxy instrumentation for dependency audits | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-063 | Operand order forcing for bypass-friendly T2 | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-064 | Split-zmm dual batch (two 8-lane batches in one zmm's halves) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-065 | Nonce-affine schedule decomposition in MB (rounds 18 and up) | REJECTED | none recorded | EXP-016: REFUTED as a work reduction, proof grade (z3 plus sampled classification). |
| Y-066 | Schedule delta compression for multi-template search | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-067 | Outer schedule staging during block-2 tail rounds | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-068 | SHA-NI schedule engine feeding vector rounds (shared prefix) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-069 | Block schedule generation (16-word jumps) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-070 | Constant-addend folding inside the schedule recurrence | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-071 | Next-template schedule during current search | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-072 | Nonce-incremental schedule update for rolled templates | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-073 | Sparsity-exploiting scalar schedule for template setup | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-074 | Reduced-window schedule formulation (closure candidate) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-075 | Round-3 delta decomposition for a deeper prefix | REJECTED | none recorded | EXP-016: REFUTED as a work reduction, proof grade. |
| Y-076 | Extranonce-dimension midstate amortization in the solo shape | REJECTED | EXP-023 | EXP-023: REJECTED as specified; its named cache target changes with every extranonce step and the named cost does not exist in the code. |
| Y-077 | Two-level midstate cache for job families | INTEGRATED | EXP-017, EXP-023 | EXP-023 VERIFIED at the data level; the repaired design was integrated through EXP-025 into mining/engine.py (TemplateCache, layered dsha256 identity). |
| Y-078 | Outer-state reuse across nonces (closure candidate) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-079 | Snapshot-depth decision table by template field | PROVEN | EXP-023 | EXP-023: VERIFIED TABLE for all 32 field subsets plus two boundary rows. |
| Y-080 | Register-passed outer input in the SHA-NI family | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-081 | Template setup cost share at production spans (pricing) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-082 | Warm-start schedule for ntime rolls in the kernel walker | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-083 | Byte-domain nonce counter for MB group setup | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-084 | Flags-only MB batch via mask registers | INTEGRATED | EXP-017, EXP-022 | EXP-022 VERIFIED IMPROVEMENT in batch scope; adopted by owner decision into the production batch path (gpu/engine.py batch_search routing to bal_v_batchf2 in mining/cpu/bal_avx512_flags.c). Batch scope only; never the search path. |
| Y-085 | Orientation parity carried in the H-01 walker | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-086 | Consumer-shaped digest layout (word-7-first AoS) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-087 | IFMA 52-bit packing for paired additions (closure candidate) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-088 | Boolean work on the floating-point vector pipes (speculative) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-089 | Constant schedule tables in cache (closure candidate) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-090 | Gray-code nonce order for delta-sparse schedules | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-091 | Per-word target thresholds for the in-vector filter | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-092 | Endian-free whole-kernel formulation (closure candidate) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-093 | Share plus dual-batch (EXP-013 inside EXP-011) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-094 | Explicit ternlog plus full unroll (codegen guarantee) | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-095 | K+W folding plus schedule-addend folding | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-096 | MB champion plus flags-only batch at integration shape | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-097 | Heterogeneous worker pair under the VM cap | REJECTED | EXP-017, EXP-021 | EXP-021: heterogeneous worker pair is an ESTABLISHED NEGATIVE; mixed pool reproduced below the homogeneous MB pool. |
| Y-098 | Prefix sharing inside the dual-batch walker | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-099 | Best kernel plus the X-059 pipeline fix, repriced end to end | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-100 | Pairwise interaction matrix over the verified set | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-101 | Steal-normalized decision statistic | PROVEN | EXP-017 | EXP-017: the paired measurement stack; adopted by owner decision 2026-11-14 as the programme integration decision rule. |
| Y-102 | Fine-grained paired interleaving (100k blocks) | PROVEN | EXP-017 | EXP-017: part of the measurement stack adopted as the programme decision rule. |
| Y-103 | Equal-pair control methodology (the ternlog pair as instrument) | PROVEN | EXP-017 | EXP-017: part of the measurement stack adopted as the programme decision rule. |
| Y-104 | Node-sync interaction with kernel benchmarks | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-105 | Confirmation path repricing at MB rates | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-106 | Template freshness cost at MB rates | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-107 | Solo-server accounting overhead at MB worker rates | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |
| Y-108 | Pinned benchmark manifest for every record | NEW | none recorded | Registry entry carries no status line; UNVERIFIED, treated as not yet investigated. |

## Historical opportunities (R-01 to R-35)

Source: research/master_build/HISTORICAL_OPPORTUNITY_REGISTER.md,
backed by research/master_build/HISTORICAL_MINER_RESEARCH.md. R-01 and
R-02 are merged into H-1 and H-6 above and are not repeated here; the
remaining 33 rows stand below. Columns: the idea, its source, the NOVA
component it touches, and the decision evidence (the historical status
text first, then the expected value and risk from the source row).

| ID | Idea | Mandate status | Source | NOVA component | Decision / evidence |
|---|---|---|---|---|---|---|
| R-03 | Pre-extend the message schedule for nonce-independent words | PROVEN | pooler/cpuminer, sha2.c sha256d_preextend | gpu/engine.py kernels | ALREADY COVERED: EXP-016 (W18 is the first nonce-dependent expanded word); production Expected value: Avoids recomputing fixed schedule words per nonce Risk: None; exact identity |
| R-04 | Multi-way interleaved batch hashing (4-way SSE2, 8-way AVX2 forms) | INTEGRATED | jgarzik/cpuminer, sha256_4way.c; pooler/cpuminer, sha2.c scanhash_sha256d_8way | gpu/engine.py | ALREADY COVERED: EXP-011, EXP-026 (DualMask integrated), EXP-032, EXP-039 (AVX2 tier integrated) Expected value: The whole SIMD throughput ladder Risk: None |
| R-05 | Cheap first-word screen, then an exact full 256-bit target test as the only authority | INTEGRATED | pooler/cpuminer, sha2.c (Htarg screen) and util.c fulltest | mining/candidate_verify.py | ALREADY COVERED: EXP-036 (verify_candidate, integer only, no float anywhere in the file); screens exist in production search masks, EXP-024, EXP-026 Expected value: Screening saves work; exactness is never delegated to the screen Risk: A screen treated as authority would be a consensus bug |
| R-06 | Return candidate nonces only from the search device, never bulk digests | INTEGRATED | m0mchil/poclbm, phatk.cl search kernel output discipline | gpu/engine.py search path | ALREADY COVERED: registry H-04; EXP-024 and EXP-026 mask search integrated as v512dual Expected value: Cuts result data movement to near zero Risk: None |
| R-07 | Runtime CPU feature probing with per-tier backends behind one scan interface | INTEGRATED | jgarzik/cpuminer, cpu-miner.c backend selection; pooler/cpuminer, sha256_use_4way and sha256_use_8way | gpu/engine.py | ALREADY COVERED: EXP-028, EXP-039 (flag-free probe, dispatch order CUDA, v512dual, v512, shani, avx2, C, hashlib) Expected value: One engine, correct kernel on every host Risk: Executing an unsupported instruction is a hard crash |
| R-08 | Long-poll work refresh with per-thread restart flags so stale work is abandoned inside a span | INTEGRATED | jgarzik/cpuminer, cpu-miner.c restart_threads; pooler/cpuminer, GBT longpoll handling | mining/mainnet_live.py, mining/autopilot.py | ALREADY COVERED: production GBT longpoll monitoring; autopilot watchdog at 1 s poll Expected value: Fresh templates reach search threads in seconds Risk: Restart storms on a flapping endpoint |
| R-09 | Hand workers explicit nonce ranges (base plus size) cut from a work unit, ranges dying with their unit | PROVEN | jedi95/Phoenix-Miner, WorkQueue.py NonceRange, getRangeFromUnit, isRangeStale | mining/engine.py, coordinator design | ALREADY COVERED and strengthened: EXP-029 allocator proofs; EXP-035 leases; EXP-038 crash-honest frontiers Expected value: Deterministic, disjoint distribution Risk: Ranges without completion accounting falsely claim coverage |
| R-10 | Fixed registry of immutable jobs, cloned on read, results resolved to jobs by id | INTEGRATED | Bitaxe firmware via EXP-030 matrix M04, M05 | mining/engine.py job model | ALREADY COVERED: EXP-030 M04, M05 decisions; EXP-034 job and template engine (generation-tagged identity) Expected value: Kills job mutation races and stale result attribution Risk: Slot recycling ambiguity in the original |
| R-11 | Partition extranonce2 by worker id bits plus a per-worker counter | PROVEN | Qaxe firmware via EXP-030 matrix M06 | coordinator design | ALREADY COVERED: EXP-035 work distribution design (slot shifted left 25, 25-bit counter) Expected value: Disjoint coinbase space by construction Risk: Partition exhaustion at extreme worker counts |
| R-12 | Adapt share difficulty toward a target share interval, with hysteresis on increases | DEFERRED | Bitaxe firmware via EXP-030 matrix M10; ckpool, src/stratifier.c vardiff | mining/solo_server.py | ALREADY COVERED as a decided design (M10, EXP-037 statistics); production state: solo share difficulty is still fixed at 0.02, implementation remains open and is tracked here so it is not lost Expected value: Stable share flow for accounting at any hashrate Risk: Oscillation without hysteresis; difficulty is not a consensus value and must stay out of candidate judging |
| R-13 | Coordinator re-verifies every worker candidate exactly before submission; workers never submit directly | INTEGRATED | Qaxe firmware via EXP-030 matrix M13; ckpool, src/stratifier.c share validation | mining/candidate_verify.py | ALREADY COVERED: EXP-036 verification component; EXP-035 coordinator design Expected value: One verified submission path for the whole fleet Risk: Verifier throughput bounds fleet size (matrix M27 budgeting) |
| R-14 | Suppress duplicate candidates and shares keyed by full work identity | PROVEN | Qaxe firmware via EXP-030 matrix M12; luke-jr/bfgminer, miner.c stratum_share table | mining/mining_statistics.py, coordinator design | ALREADY COVERED: EXP-035 duplicate detection and accounting (892 injected duplicates all detected in its campaign) Expected value: Duplicated work never counts as coverage Risk: A too-small dedup window admits duplicates |
| R-15 | Treat version rolling, extranonce and nonce as one combined, exactly accounted search space | PROVEN | Bitaxe hardware note via EXP-030 matrix M34; ckolivas/cgminer, work rolls (roll-ntime lineage) | mining/engine.py, coordinator design | ALREADY COVERED: EXP-034 and EXP-035 combined space design; EXP-038 frontier keys include extranonce space Expected value: Correct coverage claims across all rolling dimensions Risk: Double counting one dimension against another |
| R-16 | Detect stale work and refuse to submit stale shares by default | INTEGRATED | ckolivas/cgminer, cgminer.c stale_work, opt_submit_stale | mining/stratum_client.py, mining/solo_server.py | ALREADY COVERED: EXP-034 template identity; EXP-036 submit classification; solo cutover verification counts server-side Expected value: No wasted submissions; honest accounting Risk: Over-eager staleness discards valid near-tip work |
| R-17 | Stage non-clean job updates and swap at a search boundary instead of tearing live work | INTEGRATED | Bitaxe firmware via EXP-030 matrix M16; ckolivas/cgminer work expiry discipline | mining/engine.py | ALREADY COVERED: EXP-025 cache identity discipline; EXP-034 safe job replacement Expected value: No torn reads of job state mid-search Risk: Staging delays urgent clean jobs if misapplied |
| R-18 | Per-worker counters (hashes, candidates, errors) in fixed time windows as the only hashrate source | INTEGRATED | Bitaxe firmware via EXP-030 matrix M11; Canaan Avalon farm-manager status reports | mining/mining_statistics.py | ALREADY COVERED: EXP-037 (EvidenceCounter, separated statistics, no combined total) Expected value: Honest, luck-independent telemetry Risk: Counter overhead in the hot loop if done naively |
| R-19 | Backend self-test against known vectors at selection and at worker start; refuse on failure | INTEGRATED | Bitaxe firmware via EXP-030 matrix M32; BFGMiner ZTEX capability readback via libztex.c | gpu/engine.py | ALREADY COVERED: production hashlib self-test at dispatch (256-nonce check); EXP-039 D-1 guarded probes; EXP-028 simulated capability profiles Expected value: A broken backend never mines silently Risk: Self-test bugs could refuse a good backend |
| R-20 | Separate supervisor that never mines and a miner that never supervises itself | INTEGRATED | Qaxe supervisor MCU via EXP-030 matrix M20; ckolivas/cgminer watchdog thread | mining/autopilot.py plus the keeper cron | ALREADY COVERED: autopilot plus keeper layering, proven live by repeated keeper restarts Expected value: Supervision survives miner death Risk: Supervisor complexity |
| R-21 | Support Stratum V2 with Noise encryption for external pools, and model precomputed-root jobs as a distinct job type | DEFERRED | Bitaxe firmware via EXP-030 matrix M23, M24; stratum-mining/stratum, sv2 subprotocols | mining/stratum_client.py, mining/engine.py job model | ALREADY COVERED as investigated and sequenced (M23 Investigate, M24 Adapt); not implemented, by recorded decision Expected value: Protocol currency; correct caching for both job types Risk: Real implementation cost; no current NOVA need (own solo server is V1) |
| R-22 | Pipeline the compression function so independent nonce lanes hide round latency | INTEGRATED | fpgaminer/Open-Source-FPGA-Bitcoin-Miner, src/sha256_transform.v | gpu/engine.py kernels | ALREADY COVERED as the software analogue: EXP-003 multi-stream, EXP-011 and EXP-026 interleaved multi-buffer; the hardware mechanism itself is non-transferable Expected value: The SIMD interleave strategy itself Risk: None at the concept level |
| R-23 | Startup measured bake-off: benchmark every correctness-passing backend on the actual host at first start, cache the winner in the host capability profile, fall back to the static dispatch order on any doubt | EXPERIMENTAL | luke-jr/bfgminer, driver-cpu.c and README.CPU (--algo auto and fastauto) | gpu/engine.py dispatch; EXP-031 capability profiles | NEW Expected value: Picks the empirically fastest tier on hosts the lab has never seen, including the alternating AMD and Intel VMs of EXP-031; closes the EXP-039 note N-1 refusal gap empirically instead of by construction Risk: Benchmark noise on a contended VM could pick a worse tier; mitigate with EXP-017-shaped medians, a minimum margin over the static choice, and re-runs on host change Build state, 2026-11-15: implemented in this build as the Milestone 4 scheduler bake-off (agent/intelligence/scheduler.py), advisory only; production dispatch is unchanged (research/master_build/MILESTONE345_BUILD.md). |
| R-24 | Per-operation privilege enforcement on the agent control interface: every operation carries a privilege class (read, operate, administer) enforced at the transport, modelled on a proven command table | EXPERIMENTAL | ckolivas/cgminer, api.c command table (mutating commands flagged privileged: restart, quit, switchpool, enablepool, save, hotplug) | agent/interface.py | NEW Expected value: Turns the mandate's authority levels from convention into mechanism; the Antbleed history (report section 3.13) is the counterexample of an unprivileged control surface Risk: Over-broad privilege classes could block legitimate recovery actions; classes must be designed with the recovery paths first Build state, 2026-11-15: the mechanism exists in the agent package as per-operation ActionSpecs with levels enforced by PermissionChecker (agent/intelligence/permissions.py, Milestone 1); there is no network transport in the agent layer yet, so transport-level enforcement remains open. |
| R-25 | Quota-based allocation across multiple template and endpoint sources, quotas forward-looking, a dead source's quota dropped until it recovers, all-zero quotas falling back to failover | NEW | ckolivas/cgminer, miner.h enum pool_strategy (POOL_LOADBALANCE, POOL_BALANCE), README quota semantics | mining/endpoint_config.py, coordinator design | NEW Expected value: Lets a future fleet split work between its own solo server and external pools by policy instead of a binary switch Risk: Quota bugs could starve the solo leg or double-assign space; needs EXP-035 lease integration, never a replacement for it |
| R-26 | Endpoint health policy as a named object: ordered endpoints, N consecutive errors before failover, a timed failback retry of the primary | NEW | m0mchil/poclbm, poclbm.py options (tolerance, failback) and Switch.py | mining/mainnet_live.py, mining/autopilot.py | NEW Expected value: The pool leg survives endpoint failure and recovery without operator action; policy is inspectable and tunable by the agent Risk: Failback flapping on a marginal endpoint; needs damping counts, which the source's tolerance parameter already models |
| R-27 | A stratum-speaking aggregation tier between fleet workers and upstream endpoints: one process holds few upstream connections, fans workbases out, validates shares, and keeps per-worker accounting | NEW | ckpool, src/ckpool.c proxy and passthrough modes, src/stratifier.c, src/connector.c; luke-jr/bfgminer stratum server mode | new component beside mining/solo_server.py | NEW Expected value: Fleet scale without one upstream connection per worker; a single point where EXP-036 verification and EXP-037 accounting attach to stratum traffic Risk: A new trusted component; must inherit EXP-035 fleet identity checks, not ckpool's open pool trust model |
| R-28 | Push-based template supply from the node via Bitcoin Core's multiprocess mining IPC, with GBT retained as fallback | DEFERRED | ckpool, README-SOLOMINING.md and src/generator.c (IPC preferred, GBT fallback) | mining/engine.py template source | NEW Expected value: Templates arrive on new-block events with no polling or longpoll latency; matches Core's own direction Risk: Requires a Core version and build change (multiprocess bitcoin-node, Core 32 era) while NOVA pins bitcoind 28.1; a node upgrade is an owner-level infrastructure decision, so this row is gated, not scheduled |
| R-29 | Stratum V2 job declaration client: the miner proposes its own self-built template to the pool for approval | NEW | stratum-mining/stratum, sv2/subprotocols job-declaration | mining/stratum_client.py (future SV2 work) | NEW Expected value: Template sovereignty on external pools; the pool cannot silently censor transactions from NOVA-built templates Risk: Depends on R-21's SV2 base and on pools that support declaration; identity handling for proposed templates must extend the EXP-025 fingerprint |
| R-30 | Stable numeric incident code registry: every detected fault, recovery action and backend refusal carries a durable code from a registry file, keyed into statistics and audit | NEW | MicroBT Whatsminer public error-code documentation (documentation-sourced only; no source exists to study, report section 3.19) | mining/mining_statistics.py, mining/autopilot.py incident records | NEW Expected value: Agent reasoning and post-incident audit can key on codes instead of free text; recurring fault classes become countable Risk: A badly designed taxonomy ossifies; codes must be append-only and coarse at first |
| R-31 | Signed release chain for fleet software: versioned builds, a signing key, a feed of signed manifests, staged rollout with refusal on signature failure | NEW | Braiins OS via fork mirror DavHau/braiins-os, bb.py, keys/, build-release.sh, upgrade/ | mining/autopilot.py self-update path | NEW Expected value: The fleet gains a verifiable update mechanism; today the autopilot self-update is inert on this VM and there is no fleet update story at all Risk: Key management is a security-critical design task; a bad rollout bricks workers, so staging and rollback must be designed before any signing |
| R-32 | PID closed-loop control for worker count and span size, driven by a measured error signal (steal time or share interval error), replacing step changes | NEW | Braiins braiins/bmminer, fancontrol.c PID loop (hardware target, software shape) | mining/autopilot.py, adaptive scheduler (mandate milestone 4) | NEW Expected value: Smooth adaptation on contended VMs instead of throttle and collapse cycles; matrix M21 flagged ramping as Investigate but no controller was designed Risk: A mis-tuned loop oscillates; needs EXP-031 signal data and conservative gains, with the step policy retained as fallback |
| R-33 | Prepared-work prefetch queue between the template engine and the search threads, with a starvation counter, so a template change never leaves search threads idle | NEW | ckolivas/cgminer staged work queue (cgminer.c); jedi95/Phoenix-Miner, WorkQueue.py fetchRange staging | mining/engine.py, gpu/engine.py seam | NEW Expected value: Removes template-transition bubbles from the production path; EXP-040 measured per-stage costs but no prefetch mechanism was built Risk: Prefetched work ages; the queue must key every entry to template identity and drop on change (EXP-025 discipline) |
| R-34 | Hotplug-style worker attach and detach on a running coordinator: a worker joins, is capability-checked and leased work, or drains and leaves, without coordinator restart | NEW | ckolivas/cgminer, api.c hotplug command and device hotplug handling | coordinator design (EXP-035 follow-on) | NEW Expected value: Fleet membership becomes an operation, not a deployment event; matches how VM workers actually appear and disappear Risk: Drain semantics must never falsely complete work; EXP-038 frontier rules govern the leaving path |
| R-35 | A first-class offline benchmark mode in the production binary: run the real search path against a fixed bench work unit with no network, report the category E rate and the host profile | EXPERIMENTAL | tpruvot/ccminer, ccminer.cpp --benchmark mode (opt_benchmark) | gpu/engine.py command line surface | NEW Expected value: After every VM replacement the new host is profiled in one command through the production path, feeding R-23 and EXP-031 profiles; today benchmarks live only in research harnesses Risk: A benchmark mode must never be confusable with mining; fixed work unit, no submission path compiled into the mode Build state, 2026-11-15: implemented in this build as the scheduler's fixed-work-unit measurement through the real search path (agent/intelligence/scheduler.py, 262,144 hashes per repetition; research/master_build/MILESTONE345_BUILD.md); it is an agent-side profiling mode, not yet a production binary mode. |

## Standing open items

Carried from the seed register's standing items, unchanged in substance:

1. H-033-02 residual generality (see the EXP-033 table): the only open
   mathematical shape, covered only by an inconclusive full-cone CEGIS.
   Status UNDER_INVESTIGATION.
2. EXP-041 -mtune=znver3 scheduling variant: unbenchmarked, no experiment
   ID yet (next unreserved: EXP-044). Status NEW, as an engineering
   measurement, not a hypothesis about SHA-256.
3. EXP-028 ARMv8 SHA2 and NEON dispatch: specified, never executed on ARM
   hardware. Status NEW with an UNVERIFIED flag; no rates exist.
4. EXP-024b design C integration: verified kernel awaiting an owner
   decision (H-9 above). Status EXPERIMENTAL in this register because
   the kernel result is proven but the integration question is the item.
5. Multi-machine coordination (EXP-035 productionisation): the design
   and prototypes are PROVEN at prototype level by EXP-035 and EXP-043;
   the production build is an engineering item tracked in
   docs/IMPLEMENTATION_ROADMAP.md, not a research hypothesis. This
   build added a single-machine ResourceRegistry
   (agent/intelligence/resources.py); the wire protocol and persistent
   coordinator remain unbuilt.
