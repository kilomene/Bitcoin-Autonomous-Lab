# EXP-046: EXP-024b design C re-measurement against today's production search (NOVA-ER-0003)

Experiment: EXP-046 (portfolio identity NOVA-ER-0003).
Date: 2026-11-16. Host: AMD EPYC 9D25 126-Core Processor
(guest, hostname htch-runtime; 4 vCPUs visible, about 2
effective CPUs per EXP-031). Standing condition of every
measurement: the live miner (v512dual backend,
autopilot-supervised, pid 7872 throughout the campaign,
restarts 0, shares accepted 477 at campaign start and
478 at the end, rejected 8 throughout), the pruned
mainnet node in initial block download, and other
agents' work were running throughout and were never
paused, restarted or reconfigured. Load average (1
minute) at session starts rose from 4.11 in the first
session to 20.28 in the eleventh, the heaviest sustained
mix under which any of these kernels has been timed in
this programme; sessions were rotated across comparisons
by round so the rise is shared by all four comparisons
rather than concentrated in one. Research only: no
production file was modified (the gates record and every
session manifest pin the production library and source
hashes; the first and last records agree byte for byte).

## The question

EXP-024b verified design C (the single-batch mask search
bal_v_msearcha2 in libbal_m512.so, adaptive lowest-lane
extraction) at pooled 1.398x [1.242, 1.578] against the
production search of 2026-11-14, and recorded it as a
certified single-batch fallback form, not integrated.
Production search has since changed: the live path is
v512dual (EXP-026 DualMask, bal_vd_search2, verified
1.718x against the v512 search it displaced), and the
v512 single-batch search (bal_v_search2) remains in
production as the tier below it. EXP-046 asks whether
design C still holds any advantage against today's
production search: primarily against v512dual, the
search that actually runs; secondarily against the
current v512 library build, the form design C was
certified against.

## Verdicts (three-tier language)

- Against v512dual at 1 thread: ESTABLISHED NEGATIVE.
  Pooled 0.674x [0.590, 0.768]; the adjusted CI is
  entirely below 0 in every session and pooled. Design
  C is definitively slower than the live production
  search at 1 thread.
- Against v512dual at 2 threads (the primary
  comparison): NOT SIGNIFICANT under the predeclared
  every-session rule, with a uniformly negative
  direction. Pooled 0.750x [0.654, 0.863], entirely
  below 1; sessions 0.823x [0.628, 1.073], 0.727x
  [0.574, 0.934], 0.735x [0.592, 0.920]. Two of three
  sessions are entirely below 0; the first straddles
  0, which is what keeps the formal tier at NOT
  SIGNIFICANT rather than ESTABLISHED NEGATIVE. Every
  point estimate is negative, and the measurement bias
  documented in section 4 favoured design C, so the
  straddle is not evidence of parity.
- Against the current v512 build at 2 threads: NOT
  SIGNIFICANT, direction uniformly positive. Pooled
  1.366x [1.192, 1.569]; sessions 1.470x [1.169,
  1.854], 1.431x [1.117, 1.820], 1.221x [0.956,
  1.557]. The third session straddles 0, so the
  campaign does not certify the lead; net of the
  control phantom (section 4) the residual estimate
  is about 1.15x.

Bottom line: design C holds no advantage against
today's production search. Against the search that
runs (v512dual) it is slower at both thread counts,
formally established at 1 thread. Its EXP-024b
fallback certification is therefore downgraded: it is
no longer a verified improvement over any production
search entry in the current tree. The EXP-024b verdict
itself stands on its own campaign (its control was
clean; section 4), as a statement about the v512
library build of that date. No integration
recommendation arises: there is nothing to integrate,
and production dispatch is unchanged.

## 1. Design (stated before the runs)

Arms, all called directly through ctypes with the
counted search ABI, the exact call shape of the
EXP-024b driver:

- maskC: bal_v_msearcha2 in
  research/sha256d/extreme_optimization/src/
  libbal_m512.so. The file on disk is byte-identical
  to the library EXP-024b measured (sha256
  1566a9d2b807d655f96a0fc5f4b6a1de7478b831707c99cf62a88918bbbc928e,
  matching the EXP-024b gates record), so no rebuild
  was needed and none was made; the kernel source is
  likewise unchanged (sha256 f0686d54...).
- dual: bal_vd_search2 in .local/cpu/libbal_v512dual.so
  (sha256 15e22614...), today's production library,
  built by mining/cpu/build.py from
  mining/cpu/bal_avx512_dual.c with the restricted
  flags -mavx512f -mavx512bw.
- v512: bal_v_search2 in .local/cpu/libbal_v512.so
  (sha256 6dfd8d42...), today's production single-batch
  library from mining/cpu/bal_avx512_mb.c, same flags.

Comparisons (search scope, density 0 throughout:
target_int 0, the mainnet-like case where essentially
every span misses and attempted == 65,536 on every
call, asserted by the driver):

  maskC_vs_v512dual_search_d0_t2   primary, 2 threads
  maskC_vs_v512_search_d0_t2       secondary, 2 threads
  maskC_vs_v512dual_search_d0_t1   primary at 1 thread
  control_maskC_vs_maskC_d0_t2     control, same entry
                                   point in both arms

Density 0 is the only timed density, by design: on an
early exit the three kernels publish the winner at
different group granularities and their attempted
counters legitimately differ (section 2), so a
hit-density rate would compare accounting conventions,
not work. EXP-024b's verdict was likewise a density-0
verdict, which keeps the two campaigns comparable.

Protocol for every comparison: EXP-017, unchanged. 3
sessions, 120 paired 65,536-hash blocks per session,
randomised AB or BA order per pair, steal and
runnable-load covariates sampled around every counted
call, verdicts from the adjusted statistic computed by
the imported exp017_analyze code (exp046_analyze.py).
Sessions ran strictly one at a time, rotated by round
(all four comparisons' first sessions, then their
second, then their third). Total: 12 sessions, 1,440
pairs, 188,743,680 timed hashes.

Verdict rule, declared in advance (the adopted EXP-017
rule plus its mirror): VERIFIED IMPROVEMENT requires
the adjusted CI entirely above 0 in every session and
pooled; ESTABLISHED NEGATIVE requires it entirely
below 0 in every session and pooled; anything else is
NOT SIGNIFICANT. The control carries no verdict; it
calibrates the same-arm null under the campaign's
conditions.

Discard rule, declared in advance (as in EXP-045): a
session whose data shows a contention-spike corruption
signature (an arm median collapsed relative to its
sibling sessions, or a failed coverage assertion) is
discarded and rerun, and the discard recorded.
Outcome: no session met the criterion. All 12 sessions
completed 120 of 120 pairs with coverage assertions
passing, including the round-3 sessions that started
at load1 17.90 to 20.28. Zero discards.

## 2. Correctness gates (all pass before any timing)

exp046_gates.py, record RAW_RESULTS/
gates_20261116T074032Z.json. Any failure would have
stopped the experiment as a correctness failure; none
occurred.

- G1 differentials: each library's counted batch form
  (bal_v_mbatch2, bal_vd_batch2, bal_v_batch2) over
  262,144 digests (genesis at starts 0 and 65,536 at
  2 threads; a random header at the unaligned start
  12,345 at 2 threads; genesis on the span ending
  exactly at 2^32 at 1 thread), byte-identical to
  hashlib. Total 786,432 digests, zero mismatches.
- G2 candidate-set equivalence at 1 thread: all three
  search entries against a hashlib recount on 36 spans
  at target densities 0, about 2^-16, about 2^-8 and 1,
  including starts 0 and 1, unaligned starts, the
  single last nonce 2^32-1, and spans ending exactly
  at 2^32. On every span with a recount hit (23 of 36)
  each kernel returned the recount's first qualifying
  nonce with its exact digest; on every miss, rc 0
  with attempted == count.
- G3 multi-thread checks: density-0 accounting exact
  at 2 threads on plain and boundary spans for all
  three; the genesis nonce re-found at 2 threads by
  all three with the exact digest; density-1 hits at
  2 threads carry exact digests for the returned
  nonce (the winning nonce itself under an all-meet
  target at 2 threads is a race outcome by design,
  per the production self-test comment in
  gpu/engine.py, so validity rather than identity is
  asserted there).
- G4 boundary refusals: spans with start + count >
  2^32, and spans with start == 2^32, are refused
  with rc -2 and zero accounting by all three kernels,
  uniformly. Spans ending exactly at 2^32 are valid
  (G1 to G3 exercise them).

One accounting observation, re-confirmed with numbers:
on the genesis span at 2 threads (hit at offset 1000),
the attempted counters at publication were 16 (maskC),
32 (dual) and 1016 (v512, backend 1024). Each kernel
publishes the winner at its own group granularity and
counts accordingly; the returned nonce and digest are
exact in all three. This is the documented behaviour
difference behind the density-0-only timing design.

## 3. Results

Adjusted ratios, maskC over the reference (EXP-017
statistic; full per-session detail in RAW_RESULTS/
analysis_20261116T075040Z.json). Arm medians are the
per-session median call rates.

Primary, vs v512dual, 2 threads:

| Session | dual median | maskC median | Adjusted ratio |
|---|---|---|---|
| 074115Z | 11.451M H/s | 8.324M H/s | 0.823x [0.628, 1.073] |
| 074304Z | 7.370M H/s | 5.740M H/s | 0.727x [0.574, 0.934] |
| 074449Z | 8.622M H/s | 6.947M H/s | 0.735x [0.592, 0.920] |
| Pooled | | | 0.750x [0.654, 0.863] |

Primary at 1 thread, vs v512dual:

| Session | dual median | maskC median | Adjusted ratio |
|---|---|---|---|
| 074209Z | 9.742M H/s | 6.332M H/s | 0.635x [0.507, 0.788] |
| 074351Z | 10.053M H/s | 6.408M H/s | 0.645x [0.515, 0.807] |
| 074549Z | 9.185M H/s | 5.715M H/s | 0.746x [0.592, 0.953] |
| Pooled | | | 0.674x [0.590, 0.768] |

Secondary, vs v512, 2 threads:

| Session | v512 median | maskC median | Adjusted ratio |
|---|---|---|---|
| 074141Z | 6.721M H/s | 8.784M H/s | 1.470x [1.169, 1.854] |
| 074323Z | 6.322M H/s | 8.074M H/s | 1.431x [1.117, 1.820] |
| 074517Z | 5.358M H/s | 6.263M H/s | 1.221x [0.956, 1.557] |
| Pooled | | | 1.366x [1.192, 1.569] |

Control, maskC vs maskC, 2 threads:

| Session | arm A median | arm B median | Adjusted ratio |
|---|---|---|---|
| 074237Z | 5.427M H/s | 8.010M H/s | 1.318x [1.039, 1.652] |
| 074418Z | 6.098M H/s | 6.846M H/s | 1.079x [0.855, 1.375] |
| 074614Z | 5.403M H/s | 7.129M H/s | 1.202x [0.943, 1.560] |
| Pooled | | | 1.186x [1.033, 1.362] |

Reading the tables:

- The dual form's advantage over design C is large
  and consistent: at 1 thread the medians separate
  cleanly in every session (dual 9.19M to 10.05M
  against maskC 5.72M to 6.41M), and the verdict is
  ESTABLISHED NEGATIVE. At 2 threads the separation
  narrows (the single-batch form scales slightly
  better across the two effective CPUs) but the
  direction never reverses.
- Against v512 the pooled point estimate, 1.366x, is
  close to EXP-024b's 1.398x against the v512 build
  of that date: design C's standing against the
  single-batch form is essentially where it was. What
  changed is not design C and not v512; it is that
  production search moved up a tier to the dual form,
  which design C does not reach.
- Absolute rates in this campaign sit well below the
  EXP-024b campaign's (maskC medians 5.7M to 8.8M
  here against 9.2M to 13.5M there), the expected
  signature of the heavier co-runner mix (load1 at
  session starts 4.11 to 20.28 here). Per EXP-045's
  lesson, the absolute values are condition draws;
  the paired ratios are the results.

## 4. The control, and what it does to the reading

The control did not come back null. The same entry
point in both arms measured a pooled phantom of
+0.170 log ratio (1.186x [1.033, 1.362]) in arm B's
favour, with the first control session entirely above
0. EXP-024b's identical control, same driver shape and
same statistic, measured -0.045 [-0.163, 0.077]: the
phantom is a property of this campaign's conditions
(a load average that climbed through every round),
not of the harness. Two checks support that reading:
the analyzer's injected-effect validation on the
control data recovered an injected +0.2 log ratio at
+0.1999 mean with the true value inside the central
range, so the statistic machinery is unbiased on this
data; and the old min/max rule recorded 0 of 3 control
sessions passing a phantom, so the phantom lives in
the adjusted paired statistic's residuals under a
strongly non-stationary load, not in gross session
corruption.

Consequences, applied symmetrically and without
changing any formal tier:

- maskC was arm B in every named comparison, so every
  maskC figure in section 3 is flattered by roughly
  the phantom's size at 2 threads. The primary
  comparison's pooled deficit (0.750x measured) is, if
  anything, understated. The t1 ESTABLISHED NEGATIVE
  has no t1 control, and no quantitative transfer of
  the t2 phantom is claimed; the verdict there rests
  on all three sessions clearing the bar unaided.
- The secondary comparison's pooled 1.366x, net of
  the 1.186x phantom, leaves a residual of about
  1.15x: a real but uncertified lead over the current
  v512 build, consistent with EXP-024b's cleaner
  measurement of the same relationship.

## 5. What is now the defensible statement

- Design C vs the live production search (v512dual):
  slower, ESTABLISHED NEGATIVE at 1 thread (0.674x
  [0.590, 0.768]) and uniformly negative at 2 threads
  (pooled 0.750x [0.654, 0.863]; formal tier NOT
  SIGNIFICANT on one straddling session). Superseded.
- Design C vs the current v512 single-batch build:
  point estimate still ahead (pooled 1.366x [1.192,
  1.569]) but NOT SIGNIFICANT in this campaign, and
  about 1.15x net of the campaign's control phantom.
  EXP-024b's VERIFIED verdict stands for the library
  build and conditions it measured; EXP-046 does not
  renew the certification against today's build.
- The fallback-form certification recorded in
  EXP-024b is updated accordingly: design C is a
  historically verified single-batch form, not a
  currently verified improvement over any production
  search entry. Should a future host lack the dual
  form's requirements, the choice between v512 and
  design C on that host would need its own campaign;
  nothing in this one certifies design C for that
  role today.
- Production dispatch is unchanged and no integration
  is recommended. EXP-026's DualMask remains the
  production search; this experiment closes the
  question NOVA-ER-0003 opened.

## 6. Limitations

- One campaign, one host, one day, under the heaviest
  load mix in the programme's record (load1 4.11 to
  20.28 at session starts). The formal tiers are
  statements under those conditions; the t2 primary's
  straddling session is a precision limit, not a
  suggestion that the ranking reverses under lighter
  load (the t1 comparison, the least contention-
  sensitive shape, is the one that cleared the
  strictest bar).
- The control phantom (+0.170 pooled) bounds the
  precision of every 2-thread figure in this campaign
  at roughly that size in arm B's favour. Effects
  smaller than the phantom cannot be certified from
  this campaign in either direction; the secondary
  comparison's residual lead is reported as an
  estimate, not a verdict.
- Timed densities: density 0 only, for the accounting
  reason in sections 1 and 2. Candidate behaviour at
  hit densities is gate-verified for correctness
  (G2, G3) but not rate-measured, here or in
  EXP-024b's verdict.
- The comparison is against the production libraries
  as built and on disk today (hashes pinned in every
  manifest). A future production rebuild of either
  comparator re-opens the measurement in principle;
  the design C side cannot change, since its library
  is a frozen research artifact.

## 7. Artifacts

- EXP046_REPORT.md (this file).
- exp046_gates.py; RAW_RESULTS/
  gates_20261116T074032Z.json (786,432 differentials,
  candidate equivalence on 36 spans x 3 kernels, all
  gates pass).
- exp046_paired_bench.py; 12 session files under
  RAW_RESULTS/sessions/ (each with host, library and
  source sha256 manifest, load at start and end,
  miner heartbeat snapshots, coverage assertion).
- exp046_analyze.py; RAW_RESULTS/
  analysis_20261116T075040Z.json.
- Discards: none (section 1).
- No production file was modified; the live miner,
  autopilot and node were never touched (miner pid
  7872, restarts 0, shares accepted 477 to 478 across
  the campaign, before and after).
