# Phase 6B Final Report

Status: COMPLETE. Phase 6B closed 2026-11-15
(Assignment H). This report follows the 8-point
structure fixed in advance by the stub version of
this file at phase open (2026-11-14), per the
directive section 15 and the phase's own rules.
Full records: phase6b/EXPERIMENT_RESULTS.md and the
per-experiment files; integration record:
phase6b/PRODUCTION_INTEGRATION_LOG.md Entry 1;
post-integration audit:
phase6b/DUALMASK_POST_INTEGRATION_AUDIT.md.

Mission reminder, unchanged at close: 500 GH/s is
the minimum system objective and 140 TH/s is the
larger objective. Nothing below 500 GH/s is called
success anywhere in this report. Phase 6B produced
one verified kernel improvement, integrated it, and
closed several research spaces with proofs. The gap
to both objectives remains fleet-scale (section 6).

## Assignment A: audit (context for everything below)

The phase opened with a full repository audit
(CURRENT_PRODUCTION_AUDIT.md): local tree equal to
remote head 2bc63b49a16b15d899d4eab85379f9b957015dcf
except the live evidence log; production dispatch
(v512) confirmed from source end to end; the
EXP-025 input (the EXP-023 prototype's 8-field
fingerprint against its full dependency set)
confirmed from source. Four findings, all
documentation or tooling grade, no production
correctness defect:

- B6-A1 (tooling): the push helper's VERIFY step is
  blind under research/ (its MANAGED_PREFIXES omits
  research/, fpga/ and asic/), so remote-only or
  stale files there are invisible to it. Handled at
  this phase's push by an independent full-tree
  comparison (see the push record appended to this
  report's closing note).
- B6-A2 (cosmetic): two addenda in the Phase 6
  POST_INTEGRATION_AUDIT.md undercount the test
  suite by one target each. No verdict changes.
- B6-A3 (cosmetic): the solo cutover marker and
  status files are absent, which is the mechanism's
  armed default, not a fault.
- B6-A4 (cosmetic): a stale gpu/engine.py docstring
  sentence about the Stratum path. Fixed during the
  DualMask integration pass (integration log,
  Entry 1).

## 1. What was proven (proof artifacts named)

- The EXP-023 cache prototype is unsafe as written.
  Against the unmodified prototype, with its
  fingerprint unchanged in every case: five stale
  serves (middle transaction replaced; witness-only
  change with txid fixed; middle reorder;
  coinbaseaux flags change; target change) and two
  validation bypasses (fee raised with coinbasevalue
  fixed; wrong default_witness_commitment), where
  production raises. Record:
  phase6b/benchmarks/exp025/defect_demo_
  20261115T051355Z.json (EXP-025).
- The EXP-025 repaired cache identity is complete
  against the construction's full dependency set
  (dependency matrix derived field by field from
  mining/engine.py and mining/pow.py). 19
  adversarial invalidation cases pass three ways
  each; 1,320 randomised differential cases are
  byte-identical to uncached build_candidate;
  positive controls show reuse happens only under
  identical identity. Record:
  phase6b/benchmarks/exp025/gates_
  20261115T051501Z.json.
- Outside-vocabulary representation closures
  (EXP-027; proofs in phase6b/proofs/,
  exp027_proofs and exp027_vocab_search records):
  the four sigma maps are GF(2)-linear (z3 UNSAT),
  but every Sigma0 output byte depends on all four
  input bytes, refuting every single-instruction
  per-byte affine form (counterexample pair filed);
  Ch and Maj are non-affine (z3 SAT counterexamples,
  numerically rechecked); the carry-save compressor
  identity holds (z3 UNSAT, 1,000,000-triple
  differential) and every round addition has
  deferral distance exactly 0; the 52-bit IFMA
  accumulation form is exact (z3 UNSAT) but costs
  more; a hash-consing census finds 0 nontrivial
  subterms shared across the round boundary, and
  the outer compression has 0 digest-independent
  rounds (all 48 computed schedule words depend on
  the inner digest).
- Distributed allocator coverage (EXP-029): over
  120 randomised trials with worker death, duplicate
  delivery, work stealing and coordinator restart
  injected, the completed intervals union exactly
  to the declared range and are pairwise disjoint
  in every trial; 20,474 repeated computations are
  all accounted and none fall inside unique
  coverage. Record: phase6b/benchmarks/exp029/
  allocator_tests_20261115T061200Z.json.
- Cross-host dispatch (EXP-028): the AVX-512 F+BW
  family is verified (dispatch and correctness) on
  two hosts, AMD EPYC 9D25 and Intel Xeon Platinum
  8321HC; the generalised flag-free probe mask
  agreed bit for bit with /proc/cpuinfo on this
  host. Record: phase6b/benchmarks/exp028/
  probe_20261115T060117Z.json.

## 2. What was measured (evidence classes stated)

All kernel ratios below are reproducibly measured
under the EXP-017 protocol (paired blocks,
randomised order, adjusted CI) unless stated
otherwise. Raw session files: phase6b/benchmarks/
exp024/, exp024b/, exp025/, exp026/, exp027/,
exp028/, exp029/.

- EXP-024 (mask search): the predeclared primary,
  design B vs production search at density 0,
  2 threads, measured pooled 1.169x [1.031, 1.327]
  but significant in only 1 of 3 sessions: the
  criterion failed (section 4). The batch form
  reproduced EXP-022 in batch scope: flags batch vs
  production batch pooled 1.649x [1.466, 1.860],
  every session significant (batch scope only, not
  a search rate).
- EXP-024b (design C predeclared as primary):
  pooled 1.398x [1.242, 1.578] vs production search,
  significant in every session and pooled, pairs
  won 68.3 percent: VERIFIED IMPROVEMENT (search
  scope). Supporting 1-thread figure 1.463x. The
  same-process B/C interleave measured C over B at
  1.011x, pairs won 50.0 percent, null in every
  session (see section 4 for what this closes).
- EXP-025 (cache): steps500 pooled 23.02x
  [20.22, 25.93], every session significant:
  VERIFIED on the candidate-construction path. This
  is a per-extranonce-step candidate-construction
  rate. It is not a hash rate and is never used as
  one in this report or in the gap model.
  family500 pooled 1.083x, significant in 1 of 3
  sessions: NOT VERIFIED. One full identity
  recomputation costs about 79 percent of one
  uncached build at 500 transactions (measured
  medians, 3.573 ms vs 4.499 ms).
- EXP-026 (DualMask): C2 vs production search
  pooled 1.718x [1.511, 1.955], every session
  significant: VERIFIED IMPROVEMENT (search scope).
  C2 vs its strongest single ingredient (mask C)
  pooled 1.444x [1.288, 1.618]; C2 at 1 thread
  pooled 1.967x.
- EXP-029 overhead: measured, local in-process
  prototype only (460,929 unique/s at 1 worker,
  493,484 at 4 workers, chunk 10,000, over 120,000
  hashlib nonces on this contended guest). These
  price thread contention here; they are not
  distributed-system results.
- Live system observations (measured, single live
  session observations under contention, not
  benchmarks): 11.15 MH/s on v512 (Assignment A
  window); 20.6 to 21.5 MH/s on v512dual after
  integration (integration log and audit reads).
  The verified kernel-scope ratio remains the
  EXP-026 1.718x; live readings are not a
  controlled system-level ratio.

## 3. What was integrated

One integration: EXP-026 candidate C2 (DualMask)
as production backend "v512dual", on the owner's
explicit decision of 2026-11-14 ("Integrate
DualMask after EXP-024b finishes"). Record:
PRODUCTION_INTEGRATION_LOG.md Entry 1.

- Kernel mining/cpu/bal_avx512_dual.c, byte-identical
  to the research source after the documented
  rename mapping (independently re-verified by the
  audit, Area 1). Dispatch order: CUDA, v512dual,
  v512 (preserved untouched), C. Build uses the
  restricted flags -O3 -mavx512f -mavx512bw, never
  -march=native; objdump census shows zero
  AVX-512DQ, VBMI or IFMA mnemonics.
- Gates through the production path, all before
  live deployment: 197,616 randomised differentials
  vs hashlib, 0 mismatches; candidate-set
  equivalence exact; accounting parity exact against
  an independent simulation; forced fallback three
  ways lands on v512; full suite 23 of 24 targets,
  the only failure being test-rtl on absent iverilog
  (pre-existing environment failure, unchanged);
  fresh regtest blocks accepted by Core at heights
  830 and 877.
- Deployment: miner child restarted through the
  autopilot only; first pool-accepted share on the
  new backend at 2026-11-15T06:57:29Z; 205 accepted
  shares at audit time.
- Independent post-integration audit
  (DUALMASK_POST_INTEGRATION_AUDIT.md): verdict
  PASS WITH NOTES, zero defects. The auditor's own
  work included 121,400 fresh differentials (0
  mismatches), an independent accounting simulation,
  four forced-fallback constructions, and a fresh
  regtest block accepted at height 910 (a further
  block at 911 in the suite run). Notes N-1 to N-3
  are cosmetic or observational (an explained
  two-event backend_selected log pattern, thread
  tuner nondeterminism inherited from v512, and a
  heartbeat share-count lag that caught up; the
  evidence log is the primary source).

Nothing else from Phase 6B is integrated. Two
verified items remain owner decisions (section 8
of the closing summary in EXPERIMENT_RESULTS.md
and the open decisions restated at the end of this
report).

## 4. What was rejected (with the rejecting evidence)

- EXP-024 design B as the predeclared primary:
  criterion not met (significant in 1 of 3
  sessions). The follow-up interleave then closed
  the attribution question: the EXP-024 B/C
  divergence was a per-process layout and
  scheduling effect, not code (C over B 1.011x,
  null in every session, pairs won exactly
  50.0 percent). Adaptive extraction, the B/C
  design difference, adds nothing measurable at
  density 0; the mask compare form shared by B
  and C is what EXP-024b verified.
- EXP-024 scan arm (designs D/E, span-complete
  mask collection): ESTABLISHED NEGATIVE for
  search; median time to candidate 6.16x slower
  than early exit.
- EXP-026 C1 TernMask: pooled 0.764x vs its own
  strongest ingredient; an established negative as
  a combination. Its explicit ternlog cones
  produced no distinct codegen over the mask
  kernel.
- EXP-026 candidates C3 (register schedule ring),
  C4 (phase pipelining) and C5 (hand-scheduled
  assembly): killed at the written cost model,
  before compilation, with quantified reasons
  (spill cost over 32 zmm; EXP-008 parity;
  EXP-006 negative).
- The EXP-023 cache prototype as written: proven
  unsafe (section 1). It must never be integrated
  in that form; only the EXP-025 repaired identity
  is a candidate.
- EXP-027 candidate spaces, each ESTABLISHED
  NEGATIVE at its stated scope: GFNI affine forms
  for Ch, Maj and single-instruction Sigma0
  (refuted); GFNI sigma networks (costed out:
  floor 11 ops, construction 35, incumbent 4);
  pure VPSHUFB rotations (exhaustive search, 0
  survivors) and the mixed shuffle form (exact but
  4 ops vs 1 VPROLD, measured 2.00x the price);
  rotated and byte-swapped state (addition does
  not commute, counterexamples filed); carry-save
  beyond the schedule (deferral distance 0);
  Kogge-Stone lookahead (about 18 ops per add vs
  1 VPADDD); delayed carry (refuted by the
  distance-0 result); the IFMA accumulation form
  (exact, 5 ops vs 4); unrolled direct schedule
  form (259,905 tree nodes at W63 vs the
  recurrence DAG's 384 ops); GF(2)-linear schedule
  forms (refuted by EXP-016's W20 result).

## 5. What remains unproven

- Non-sharing cross-round graph restructuring
  (EXP-027's one open sub-space; blocker:
  search-space size). Class: UNPROVEN
  BREAKTHROUGH territory. No result, positive or
  negative, exists.
- Distributed scaling beyond this host (EXP-029):
  allocator coverage is proven by test and the
  roadmap is specified, but multi-machine overhead,
  propagation latency and linear scaling are
  UNVERIFIED and carry no numbers.
- AVX2 multi-buffer backend, Intel SHA backend and
  ARMv8 SHA2 plus NEON backend (EXP-028): SPECIFIED,
  UNVERIFIED, no rates. AVX2 is the highest-value
  unbuilt family.
- The EXP-025 family-shape cache gain: NOT
  VERIFIED (1.083x, 1 of 3 sessions). Only the
  steps shape is verified.
- GPU execution (inherited): the GPU gates from
  Tasks 002, 003 and 003.8 remain UNVERIFIED; no
  GPU exists on this machine.
- Any per-core rate outside the Phase 6 model band:
  no Phase 6B result measures or proves one
  (section 7).

## 6. The updated gap (every figure's class stated)

Source: PERFORMANCE_GAP_MODEL.md (Assignment A
initial version, Assignment G update section 5,
and the post-integration note appended at this
close). Objectives at full height: 500 GH/s
minimum; 140 TH/s larger, equal to 280 times
500 GH/s (derived arithmetic).

Production basis before the DualMask integration
(Assignment G headline; live observation 11.15 MH/s,
class: measured observation):

- 500 GH/s: about 44,900 live-system equivalents
  (5.0e11 / 11.15e6 = 44,843); 25,000 model planning
  cores at 20 MH/s per core (class: theoretical).
- 140 TH/s: about 12.56 million live-system
  equivalents; 7.0 million planning cores
  (theoretical).

Post-integration observation basis (production now
runs v512dual; live session rates observed 20.6 to
21.5 MH/s, class: measured observation, single live
sessions under contention, not a benchmark):

- 500 GH/s at 20.6 MH/s: 5.0e11 / 20.6e6 = 24,272,
  about 24,000 such systems (at 21.5 MH/s, 23,256).
- 140 TH/s at 20.6 MH/s: 1.4e14 / 20.6e6 =
  6,796,117, about 6.80 million such systems.
- Planning-core counts are unchanged (25,000 and
  7.0 million; class: theoretical), because the
  per-core model band did not change.

The verified kernel-scope DualMask ratio (1.718x,
reproducibly measured) and the observation-based
equivalents above are different kinds of figure
and are not interchangeable: the equivalents are
arithmetic from single live observations, not a
controlled system-level measurement of the ratio.
Either way, both objectives remain fleet-scale.
A 1.718x kernel gain divides the counts by about
1.7; it does not change the order of magnitude of
the gap.

## 7. What breakthrough would change the order of magnitude

Stated as research questions, not promises:

- Does there exist an exact computation graph for
  SHA-256d whose per-core rate sits outside the
  Phase 6 ceiling model band (6 to 25 MH/s per
  physical core, theoretical)? Every graph inside
  the searched vocabularies is now priced: the
  round is optimal at 28 vector ops within the
  EXP-020 vocabulary, and EXP-027 closed the named
  outside-vocabulary forms at their stated scopes.
  The one unsearched region is non-sharing
  cross-round restructuring (section 5).
- Does any exact sharing exist between rounds or
  between the three compressions of SHA-256d that
  the censuses missed? The measured answer so far
  is no (0 shared subterms across the round
  boundary; 0 digest-independent outer rounds;
  state affinity dead by S_8 per EXP-016). A
  positive answer, if one exists, is the shape a
  per-unit breakthrough would have to take.
- Absent a per-unit breakthrough, can deployment
  scale (units, not rate) be made real at the
  fleet counts in section 6? EXP-029 proves the
  accounting core; the scaling itself is
  UNVERIFIED and is a resources question, not a
  software result.

## 8. Recommended future research directions

1. EXP-030 candidate: build the AVX2 multi-buffer
   backend (EXP-028's highest-value unbuilt family),
   gated and benchmarked under the same rules, to
   widen the verified portability set.
2. A bounded method for the non-sharing cross-round
   restructuring search (EXP-027's open sub-space),
   so the last unsearched region gets a stated
   scope and a result, positive or negative.
3. Owner decision (a): integrate the EXP-025
   repaired cache into mining/engine.py. The
   recommendation is ready (ACCEPTED repair;
   steps shape VERIFIED 23.02x as a
   candidate-construction rate); integration needs
   its own gates and post-integration audit, and
   must use the repaired identity, never the
   EXP-023 prototype.
4. Owner decision (b): adopt the EXP-022 flags
   output shape for the engine's batch consumers
   (VERIFIED in batch scope at 1.82x in EXP-022,
   reproduced at 1.649x in EXP-024; batch scope
   only, no search-rate claim).
5. A second machine, when one exists, to run
   EXP-029's multi-machine verification and to give
   EXP-028's specified families (Intel SHA, ARM)
   target hardware; and a quiet, characterised
   measurement host to retire the contention caveat
   carried by every rate in this phase.

## Closing note

Phase 6B is complete: Assignments A to H executed
in the directive's order, EXP-024 to EXP-029 plus
EXP-024b closed, one integration executed and
independently audited, and this report filed. The
push of the complete Phase 6B tree to
kilomene/Bitcoin-Autonomous-Lab, with the
independent full-tree verification required by
finding B6-A1, is recorded in the push note
appended below at push time.

## Push note (appended 2026-11-15, Assignment H)

The Phase 6B tree was pushed with
/home/hatch/workspace/bin/bal_github.py (contents
API, one commit per file). Against the Assignment A
baseline 2bc63b49a16b15d899d4eab85379f9b957015dcf:
183 files changed (171 added, 12 modified, 0
removed), remote head after the push
59dec1091b39f3cd37f43884c19939669fc4bb8a, repo
confirmed public. Independent full-tree comparison
(the B6-A1 method: the helper's local_files() and
remote_tree() machinery used read-only across the
whole tree, including research/): local 579 files,
remote 579 files, 0 missing, 0 remote-only, and
exactly one differing file,
evidence/mainnet-live.jsonl, which differs because
the live miner keeps appending to it (expected
runtime churn, not a push defect). This note is
the only content change made after that
verification; it was pushed immediately after
being appended, and the full-tree comparison was
re-run as the final check (its outcome is stated
in the Assignment H closing message, since a file
cannot contain the verification of its own final
form).
