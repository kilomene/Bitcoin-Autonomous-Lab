# Phase 6B Open Problems

Opened 2026-11-14 with Assignment A. Problems are
stated as questions with their current evidence
state; nothing here is a result.

1. Search-path mask value. EXP-022 removed the batch
   epilogue and gained 1.82x in batch scope; the
   production search path's avoidable work (full
   digest materialisation plus scalar comparison per
   group) is a different cost in a different shape.
   Whether it is worth a certifiable margin is open.
   Owner: EXP-024.

2. Cache identity completeness. The EXP-023
   prototype's fingerprint omits fields its cached
   objects depend on (witness data, serialisations,
   ordering, fees, flags). The complete dependency
   set and a layered identity that survives
   adversarial mutation are open. Owner: EXP-025.

3. Beyond the closed vocabulary. EXP-020 closed the
   round at 28 vector ops inside
   {VPADDD, VPTERNLOGD, classic bitwise, VPROLD,
   VPSRLD}. GFNI affine forms and VPSHUFB rotations
   sat outside that vocabulary. Whether any
   outside-vocabulary representation beats the
   incumbent on cost, and then on rate, is open.
   Owner: EXP-027.

4. Combination value. EXP-018 (residency) and
   EXP-020 (op count) each improved a proxy and not
   the rate. Whether a costed combination of the
   phase's ingredients beats its best ingredient is
   open, and the cost model that predicts it does not
   yet exist. Owner: EXP-026.

5. Measurement environment. Every rate in the
   programme is measured on a contended shared VM
   whose host changes across replacements (flags
   included). The EXP-017 protocol controls for load
   within a session; it cannot make rates portable
   across hosts. A quiet, characterised measurement
   host remains an open resource problem, and all
   cross-host comparisons must carry their host
   records.

6. Portability breadth. No ARM machine, no Intel SHA
   host and no GPU are available to the programme.
   EXP-028's per-architecture claims will remain
   SPECIFIED, UNVERIFIED for those families until
   hardware exists. The GPU gates from Tasks 002,
   003 and 003.8 remain UNVERIFIED for the same
   reason.

7. Distributed accounting at scale. The standing
   separations (unique coverage, actual, repeated,
   verification, submissions) are defined; whether
   coordination overhead stays small as worker count
   grows is unmeasured at every scale. Owner:
   EXP-029.

8. The gap itself. PERFORMANCE_GAP_MODEL.md puts
   500 GH/s at about 44,900 live-system equivalents
   or 25,000 model-planning cores, and 140 TH/s at
   280 times that. No measured result in the
   programme changes the order of these numbers.
   Closing the gap needs either a Track B per-unit
   result outside the model band or deployment
   resources the programme does not have; the model
   states the arithmetic and promises neither.

## Closing update: 2026-11-15 (Phase 6B close)

Disposition of the problems above, by number:

1. ANSWERED. The search-path mask form is worth a
   certifiable margin: EXP-024b verified design C
   at 1.398x, and the combined DualMask form
   (EXP-026, 1.718x) is integrated as v512dual.
2. ANSWERED as a correctness question. The complete
   dependency set is derived and the repaired
   layered identity survives adversarial mutation
   (EXP-025, ACCEPTED). What remains open is only
   the owner's integration decision, recorded in
   PHASE6B_FINAL_REPORT.md section 8.
3. ANSWERED at the stated scopes, one sub-space
   open. EXP-027 closed the named
   outside-vocabulary spaces with proofs and
   costings. Still open: non-sharing cross-round
   graph restructuring, blocked on search-space
   size. This is the phase's one remaining
   breakthrough-shaped question.
4. ANSWERED. A costed combination beat its best
   ingredient: DualMask at 1.444x over mask C
   (EXP-026), with the cost model filed before
   compilation.
5. STILL OPEN. No quiet measurement host exists;
   every rate still carries its host and contention
   record.
6. PARTIALLY ANSWERED. AVX-512 F+BW is verified on
   two hosts (EXP-028). Still open: AVX2 (specified,
   unverified; named the highest-value unbuilt
   family, a build is the EXP-030 candidate), Intel
   SHA and ARMv8 (specified, unverified, no
   hardware), and the GPU gates (unverified, no
   GPU).
7. PARTIALLY ANSWERED. Allocator coverage is proven
   by test at prototype scale (EXP-029); whether
   coordination overhead stays small as worker
   count grows across machines is still unmeasured
   at every multi-machine scale. UNVERIFIED.
8. STILL OPEN, restated at the new basis.
   PERFORMANCE_GAP_MODEL.md section 6 puts
   500 GH/s at about 24,000 live-system equivalents
   on the post-integration observation (20.6 MH/s)
   or 25,000 model-planning cores, and 140 TH/s at
   280 times that. The order of the numbers is
   unchanged by Phase 6B.
