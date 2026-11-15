# Phase 001, Deliverable 17: Modern CPU Opportunities Mapped from the Genesis Architecture

Project: NOVA SHA-X, Research Phase 001, Wave 4.
Method: take each structural feature of the 0.1.3 mining loop and ask what a modern CPU offers for it, then state, from the NOVA repository audit (research/bitcoin_reverse_engineering/NOVA_REPOSITORY_AUDIT.md) and the EXP-032 record, what NOVA already has in production, what is verified but not deployed, and what remains genuinely open. No new performance claims are made in this deliverable; every rate mentioned is a prior measured result with its pointer. Host facts are from EXP-031 and the audit's environment records.

## 1. The mapping

| Genesis feature (0.1.3) | Modern CPU counterpart | NOVA status |
|---|---|---|
| Scalar Crypto++ Transform, one block at a time, no feature detection | SHA-NI: dedicated round and schedule instructions (sha256rnds2, sha256msg1/2) | Verified as a tier, not dispatched (section 2) |
| One candidate per call, state re-initialised per call | AVX2 8-way multi-buffer: eight independent compressions interleaved | Verified as a tier, not dispatched (section 2) |
| Same, on wider vectors | AVX-512 16-way multi-buffer with ternlog Boolean ops and masked search | In production: backend v512dual (DualMask), fallback v512 (sections 2 and 3) |
| Sequential rounds with macro renaming | Instruction-level parallelism: independent sigma and sum chains across lanes and rounds, superscalar issue | Embodied in the multi-buffer kernels; the round itself is proven at its 28-op vocabulary optimum (EXP-020), production emits 29 (Deliverable 16, H-8) |
| One miner thread, LOWEST priority, todo comment for one thread per processor | Multiple cores / hardware threads | Bounded by the host, not the code: EXP-031 measured about 2 effective CPUs on this VM class regardless of the 4 claimed vCPUs (scaling saturates at 2 threads); rejected_hypotheses.md R-04 records the same ceiling from the miner side |
| Per-call byte-reversal of every word | Boundary conversion once per template; vector byte-shuffle where needed | Production conforms (EXP-027 C3 principle); the per-candidate cost exists only in the historical code (Deliverable 16, H-2) |
| No target-check shortcut (full hash, then compare) | Masked / vector compare inside the search kernel (hit masks returned per batch) | In production in the v512dual search entry points (bal_vd_search2 family, NOVA audit section 2); the flags batch form exists for batch consumers (section 3) |

## 2. Verified but not dispatched: the EXP-032 tiers

EXP-032 (post-EXP-030 programme) verified two fallback tiers under the full EXP-017 protocol, on the recorded hosts:

- **AVX2 multi-buffer batch: 1.409x [1.340, 1.480] versus the production C batch. VERIFIED** as a fallback tier. It is 0.371x of the v512dual batch rate, which is why it matters only where AVX-512 is absent.
- **SHA-NI streams-4 batch: 2.861x [2.671, 3.089] versus the production C batch. VERIFIED** as a fallback tier (0.726x of the v512dual batch). The same experiment established the negative that matters for integration: the production SHA-NI translation unit (mining/cpu/bal_sha_intrin.c) is the older single-stream form and measured 0.517x of the C batch, ESTABLISHED NEGATIVE; the verified streams-4 form exists in research code, not in that unit.

Production dispatch today (NOVA audit sections 1 and 2, verified line by line): CUDA probe (absent on all lab hosts, no GPU has ever produced a hash here), then v512dual, then v512, then the C batch backend, then hashlib. A host with AVX2 or SHA-NI but no AVX-512F+BW therefore falls back to the C batch and never sees the two verified tiers. **This dispatch gap is the single concrete modern-CPU item Phase 001 leaves open**: it is an integration task with verified kernels, gated by correctness differentials, the post-integration audit rule, and a fresh regtest block, and it needs no new benchmark claim beyond the EXP-032 record. Its value is portability of the verified rates to non-AVX-512 hosts, including any future fleet machines of that class; on the current AVX-512 hosts it changes nothing.

## 3. In production: the AVX-512 line

- Backend v512dual (kernel mining/cpu/bal_avx512_dual.c, DualMask C2 form): EXP-017 pooled 1.718x versus the production v512 search and 1.444x versus its strongest ingredient; integrated under the audit rule (audit PASS WITH NOTES, zero defects); live pool rates recorded in the programme record. Dispatch requires CPUID AVX-512F plus BW exactly, and the libraries are built with restricted -mavx512f -mavx512bw (never -march=native) so the binaries survive host replacement (NOVA audit section 3).
- Backend v512 (mining/cpu/bal_avx512_mb.c): EXP-017 pooled 3.55x versus production C; retained as the fallback AVX-512 form.
- The EXP-022 flags batch (bal_v_batchf2) is selected independently of the search backend and serves batch consumers only; the NOVA audit's Q1 verdict is definitive that flags are NOT in the live search path. It is recorded here so this deliverable's production inventory matches the audit exactly.
- EXP-028 verified the AVX-512 F+BW kernel family on both host classes the lab has run (AMD EPYC 9D25 with the full AVX-512 feature set, Intel Xeon Platinum 8321HC with F/BW/VL/VNNI and no SHA extensions), which is why the restricted-flag build discipline matters: the same binaries are correct on both, and the probe, not the build host, decides.

## 4. Instruction-level parallelism and the round bound

The genesis loop's rounds are a serial dependency chain per candidate; the modern answer is width, not depth: many candidates' chains interleaved so the pipeline stays full. That answer is fully exploited by the multi-buffer design, and EXP-020 bounds what remains: the joint round-plus-schedule cost is proven optimal at 28 vector operations within the searched vocabulary (ternlog, rotates, adds), production emits 29, and EXP-027 plus EXP-033 closed the examined outside-vocabulary representations at their stated bounds. The honest residual ILP items are therefore exactly: the 29 versus 28 codegen gap (Deliverable 16, H-8), and the inconclusive E2 shape (Deliverable 15 section 5). No other ILP opportunity is claimed, because the searches that would have found one have been run and recorded.

## 5. Multiple cores

The 0.1.3 todo (one thread per processor) is implemented in NOVA's runners in the ordinary way: worker processes and threads scan disjoint nonce and extranonce ranges under the autopilot (NOVA audit sections 10 and 11). The binding constraint is the host: EXP-031's characterization of this VM class (4 claimed vCPUs, about 2 effective, baseline 61 to 64 percent busy from internal load, perf counters inaccessible) means thread-count tuning is an empirical per-host setting, and claims of linear scaling are prohibited by the evidence. Fleet-scale distribution is EXP-035's territory: the lease and candidate-queue prototype is proven in simulation (60 of 60 trials, exact disjoint coverage) and its multi-machine overhead is explicitly UNVERIFIED; no fleet activation is part of this phase, and the directive reserves that decision to the owner.

## 6. What remains genuinely open (complete list)

1. Dispatch integration of the two verified EXP-032 tiers (AVX2 multi-buffer, SHA-NI streams-4) for non-AVX-512 hosts, replacing the negative single-stream SHA-NI unit's role. Engineering, verified inputs, audit-gated.
2. The 29 versus 28 codegen gap (H-8). Engineering with a bounded ceiling.
3. E2. Mathematical, inconclusive, small ceiling (Deliverable 15).
4. Category F (end-to-end) measurement does not exist yet, so no modern-CPU claim can currently be stated at pipeline scope; the framework is Deliverable 18's design.

Everything else in the genesis-to-modern mapping is either in production, verified and awaiting the integration decision in item 1, or closed with a pointer in Deliverables 15 and 16.

## 7. Limitations

- All rates cited are prior EXP-017 measurements on their recorded hosts; this deliverable ran no benchmarks, per the wave rule.
- GPU is absent from this mapping deliberately: no lab host has a GPU device, the CUDA probe has never selected a backend, and no GPU hash rate may be claimed (NOVA audit section 1).
