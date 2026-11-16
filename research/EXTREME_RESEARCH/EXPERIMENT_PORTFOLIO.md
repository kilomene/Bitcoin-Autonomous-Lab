# Experiment Portfolio: NOVA SHA-X Extreme Research, Stage 3

Date: 2026-11-15. This portfolio ranks the work that Stage 2
(research/EXTREME_RESEARCH/MATHEMATICAL_OPPORTUNITY_ANALYSIS.md)
left genuinely open, plus the engineering items the roadmap
carries. It is a planning document: nothing here was executed
for this document, no code was changed, and no benchmark was
run.

## Scoring method

Score = (P x B x C) / (R x E), the mandate's prioritisation
heuristic. It is a heuristic, not a law; the assumptions behind
every factor are stated per entry, and any entry whose score is
dominated by a guess is flagged.

- P: probability the entry reaches its own success criterion,
  in (0, 1]. Estimated from the closest measured precedent.
- B: benefit on a 1 to 10 scale. Anchors: 1 is cosmetic; 3
  closes a standing unverified item or a small operational gap;
  5 changes a tier, dispatch or design decision; 7 unblocks a
  programme layer; 10 would be an order-of-magnitude rate
  change (nothing in this portfolio claims 10).
- C: confidence in the existing evidence behind the entry, in
  (0, 1]. 1.0 would mean the result is already measured and
  only execution remains.
- R: correctness and operational risk, 1 to 5. 1 is measurement
  only, no production contact; 2 is isolated code with a full
  fallback; 3 touches production behaviour behind a gate; 4 is
  a new trusted component; 5 would be a change on the
  submission path itself (nothing here is 5).
- E: effort, 1 to 5. 1 is hours; 2 is a day of VM time
  including one EXP-017 campaign; 3 is several days; 4 is a
  week or heavy solver time; 5 is a multi-week build.

Gates refer to the mandate's Part XI: Gate 1 mathematical
correctness, Gate 2 differential verification, Gate 3
adversarial testing, Gate 4 performance verification (EXP-017
where a rate is claimed), Gate 5 operational verification,
Gate 6 regtest acceptance.

EXP number assignment: the next unreserved ID in both existing
registries is EXP-044. EXP-044 was pre-committed to the -mtune
item by the owner declaration and roadmap item F6, so it keeps
that number wherever it ranks. Every other entry that will run
as a measured experiment or a gated build in the EXP series
takes the next number in portfolio order. Entries that continue
an existing identity (the EXP-039 verification, the R-12
decided design) and one pure registry-engineering entry (R-30)
take no new EXP number; their NOVA-ER entry is the tracking
vehicle.

## Block A: the five declared entries

These five were declared to the owner before this portfolio was
written. They appear first, ordered among themselves by score,
with the ordering reasons stated. Two Block B entries score
higher than some Block A entries; Block A still leads because
these items were committed, and because NOVA-ER-0002 in
particular calibrates the measurement instrument every later
benchmark entry depends on.

### NOVA-ER-0001: EXP-039 tier refusal verification on the SHA-less Intel host

- EXP identity: continues EXP-039 (roadmap F7). No new number.
- Research question: does production dispatch on the SHA-less
  Intel Xeon Platinum 8321HC actually refuse the shani tier,
  cascade correctly through avx2, C and hashlib, and never
  execute an unsupported instruction?
- Existing evidence: EXP-039 audit check 3 verified probe
  safety by construction (the probe object code contains zero
  vector and zero SHA instructions, and the probe runs before
  any kernel call), and forced-fallback gates pass on the AMD
  host. Audit note N-1 records that refusal on the incapable
  hardware itself is unexecuted.
- Hypothesis: the tiers refuse and fall back exactly as
  constructed; the suite passes on the Intel host with the
  standing exception of the two known host-shaped environment
  failures in unrelated suites (test-cpu-correction and
  test-task003 SIGILL on that host, proven environmental).
- Derivation: none required; this is a verification task. The
  governing facts are the probe construction and the dispatch
  cascade in gpu/engine.py.
- Expected impact: closes the programme's longest-standing
  UNVERIFIED item and converts fallback correctness on the
  alternating host fleet from construction to execution.
- Implementation cost: none. One suite run when the host
  rotates in.
- Correctness risk: none to production; the run can only reveal
  a defect, which is its purpose.
- Testing requirements: Gate 3 (the suite is the adversarial
  surface: forced tiers, refusal, fallback) and Gate 5 (the
  live miner must come up on the correct tier on that host
  afterwards). Gates 1, 2, 4 and 6 do not apply; no rate is
  claimed.
- Required resources: the Intel host rotation, which arrives
  on the VM replacement cycle without scheduling control; one
  make test-exp039 run plus a dispatch inspection.
- Rollback: not applicable; nothing is changed. A failure
  leaves a defect report, and the fallback order is already
  the production behaviour under test.
- Success criterion: make test-exp039 passes on the Intel
  host, the engine reports the expected tier cascade, and the
  result is recorded against EXP-039 audit note N-1.
- Failure criterion: any tier executes an unsupported
  instruction, any refusal fails to cascade, or the suite
  fails for a reason attributable to the EXP-039 code. That
  outcome is a defect fix task, not a negative result.
- Score: P 0.9 (construction evidence is strong; the residual
  doubt is exactly what the run removes) x B 3 x C 0.85 / (R 1
  x E 1) = 2.30. Not guess-dominated: every factor rests on
  the audit record.

### NOVA-ER-0002: AVX2 batch discrepancy resolution

- EXP identity: EXP-045.
- Research question: why did EXP-032 measure the AVX2
  multi-buffer batch at pooled 1.409x [1.340, 1.480] against
  production C, while EXP-039 measured the byte-identical
  kernel at 1.252x [1.185, 1.322] under the same EXP-017
  protocol, with non-overlapping intervals?
- Existing evidence: both session sets survive; the EXP-039
  audit (note N-2) re-derived its own figures from the raw
  files and confirmed the discrepancy is real; Stage 0 records
  it as discrepancy D5. Candidate causes on record: host state
  and frequency behaviour, session load, build path differences
  (Stage 0 D7 notes the legacy -march=native exception in the
  shared compile helper, though the AVX2 kernel unit itself
  uses restricted flags), and library layout sensitivity of
  the kind EXP-041's control experiment exposed.
- Hypothesis: the two figures are both correct under different
  session conditions, and a fingerprinted campaign will
  attribute the difference to named conditions rather than to
  the kernel.
- Derivation: none; the method is the deliverable. Every
  session in the campaign carries a mandatory fingerprint
  (host CPU model, build flags per library, load and steal at
  session start, library hashes), answering Stage 2 question
  Q15 as a by-product.
- Expected impact: restores a single trustworthy number for
  the fallback tier that every non-AVX-512 host depends on,
  and hardens the EXP-017 method against the exact failure
  mode that produced two irreconcilable records.
- Implementation cost: campaign tooling for fingerprint
  capture, then repeated paired sessions under deliberately
  varied named conditions.
- Correctness risk: none; measurement only, against the
  existing differential gates.
- Testing requirements: Gate 2 (kernel differentials must
  re-pass in every build used) and Gate 4 (the campaign is an
  EXP-017 measurement). Gates 1, 3, 5 and 6 do not apply.
- Required resources: this VM, several benchmark windows run
  strictly sequentially; both host types if rotations permit.
- Rollback: not applicable. The registry gains a reconciliation
  note; neither original record is edited.
- Success criterion: the campaign reproduces one of the two
  figures under named fingerprinted conditions and either
  reproduces the other under different named conditions or
  identifies the build or session variable that separates
  them, closing D5 with a stated cause.
- Failure criterion: the campaign reproduces neither figure,
  or the variance remains unattributed after the predeclared
  session budget. That outcome is itself reportable: it would
  set a measured noise floor for all batch comparisons on
  this VM.
- Score: P 0.7 (EXP-041's layout-sensitivity finding makes
  attribution plausible but not certain) x B 4 x C 0.6 (both
  records are solid; the cause is unknown) / (R 1 x E 3) =
  0.56.

### NOVA-ER-0003: EXP-024b design C re-measurement against the current v512 search

- EXP identity: EXP-046.
- Research question: is EXP-024b design C still faster than
  the production single-batch search it would fall back for,
  now that the baseline is today's v512 search build rather
  than the search build of the EXP-024b era?
- Existing evidence: EXP-024b verified design C at pooled
  1.398x [1.242, 1.578] against the then production search,
  every session significant. EXP-026 then integrated the dual
  form (C2, 1.718x against v512 search) as v512dual, and
  design C stands as a certified single-batch fallback form
  in research (Phase 001 H-9: kernel proven, integration an
  owner decision). EXP-032 confirmed flags forms do not
  compete on the search path, which bounds what design C is
  being compared for: the single-batch slot only.
- Hypothesis: design C retains a significant margin over the
  current v512 search in single-batch scope, because neither
  the v512 search build nor the design C form has changed
  since EXP-024b; the re-measurement is expected to confirm
  with a moved baseline, and any change in the margin is
  itself the finding.
- Derivation: pointer to research/sha256d/phase6b/
  EXP024_MASK_SEARCH.md and the EXP-024b confirmation record;
  the mask form and its correctness argument are settled
  there and are not re-derived.
- Expected impact: settles the fallback ranking with current
  evidence, so any future single-batch deployment decision
  (and the H-9 owner decision) rests on a current number.
- Implementation cost: the design C library survives in
  research; the work is harness wiring against the current
  v512 search entry point plus one EXP-017 campaign.
- Correctness risk: low; the form is already differentially
  verified, and the campaign re-runs the standard gates.
- Testing requirements: Gate 2 (full differentials against
  hashlib, planted-hit and no-hit exactness) and Gate 4
  (EXP-017, search scope, category E). Gate 6 (one regtest
  block through the form) if and only if the result is later
  proposed for integration; not part of this entry. Gates 1,
  3 and 5 do not apply.
- Required resources: this VM, one sequential benchmark
  window.
- Rollback: not applicable; nothing integrates from this
  entry. Integration remains the separate H-9 owner decision.
- Success criterion: an EXP-017 verdict for design C against
  the current v512 search, significant or not, recorded with
  session fingerprints.
- Failure criterion: the campaign cannot be completed to the
  protocol (sessions invalid, gates fail). A NOT SIGNIFICANT
  verdict is a result, not a failure; it would retire design
  C's fallback claim honestly.
- Score: P 0.5 (confirmation is likely but the baseline moved
  once already) x B 3 x C 0.7 / (R 1 x E 2) = 0.53.

### NOVA-ER-0004: Solo vardiff implementation (register R-12)

- EXP identity: none; implementation of the decided design
  under register R-12 and EXP-030 matrix M10.
- Research question: does the decided vardiff controller
  (adapt share difficulty toward a target share interval, with
  hysteresis on increases) hold a stable share interval at
  production worker rates on the solo leg, without
  oscillation?
- Existing evidence: the design is decided (M10); EXP-037
  statistics supply the share accounting it drives from; the
  operative state is a fixed difficulty of 0.02 in the staged
  endpoint config, with a latent inconsistency recorded as
  Stage 0 discrepancy D10 (the SoloServer constructor default
  is 0.01). ckpool's stratifier vardiff and the Bitaxe form
  are the studied precedents in the historical register.
- Hypothesis: a controller with the recorded hysteresis holds
  the share interval within its band across step changes in
  worker rate, and never lets difficulty enter candidate
  judging (difficulty is a share criterion only, per EXP-036).
- Derivation: pointer to the M10 decision and the R-12 row;
  the control law is specified there. The one mathematical
  obligation is separation: share difficulty parameterises
  submission accounting only, and verify_candidate's integer
  target test remains the sole consensus judgement.
- Expected impact: the solo leg, once the armed cutover fires,
  produces a stable share flow for accounting at any worker
  rate instead of a flood at low difficulty or silence at
  high difficulty; also removes discrepancy D10.
- Implementation cost: controller in mining/solo_server.py,
  configuration through the endpoint config, unit and
  adversarial tests, one regtest campaign.
- Correctness risk: the named risk is difficulty leaking into
  candidate judging; the design forbids it and Gate 3 tests
  for it directly. Secondary risk is controller oscillation,
  mitigated by the hysteresis in the decided design.
- Testing requirements: Gate 2 (share validation differentials
  unchanged), Gate 3 (oscillation injection, rate steps,
  malformed shares, stale jobs), Gate 5 (solo server start,
  job refresh and recovery with vardiff live), Gate 6
  (regtest blocks accepted through the solo path at adapted
  difficulties). Gate 1 is satisfied by the separation
  argument and its tests; Gate 4 does not apply (no rate is
  claimed).
- Required resources: this VM and the regtest node; no
  benchmark window.
- Rollback: the fixed difficulty remains available as a
  configuration value; setting it restores today's behaviour
  exactly, and the endpoint config is the rollback surface.
- Success criterion: share interval stays inside the decided
  band across predeclared rate steps on regtest, with zero
  difficulty influence on candidate verdicts, and D10 closed.
- Failure criterion: sustained oscillation outside the band,
  or any test showing difficulty affecting a candidate
  verdict. The second is a stop-and-fix defect, not a tuning
  issue.
- Score: P 0.85 (decided design, conventional control,
  statistics already in place) x B 4 x C 0.8 / (R 2 x E 3) =
  0.45.

### NOVA-ER-0005: -mtune scheduling of the v512 kernel

- EXP identity: EXP-044 (pre-committed; see the assignment
  note in the scoring method).
- Research question: does building the v512 kernel with
  -mtune=znver3, and separately -mtune=znver4, change its
  measured rate against the production build, in batch and in
  search?
- Existing evidence: EXP-041's census of the -mtune=znver3
  build: the standalone compress body's move count falls from
  64 to 33 at the same 29 ALU operations per round. EXP-041
  explicitly did not benchmark it, and recorded it as a
  different hypothesis from the 29-to-28 operation gap it
  closed as an established null. The same report recorded the
  environment's resolution limit: instruction-identical
  libraries disagreed across session batches by more than a
  3.4 percent effect, so the campaign must be sized for a
  small effect or accept an inconclusive outcome honestly.
- Hypothesis: instruction scheduling, unlike operation count,
  can move elapsed time on this core, because the move
  reduction changes register traffic on the critical chain;
  the expected effect, if any, is small (single-digit
  percent).
- Derivation: none; the mechanism claim is the census delta
  (moves 64 to 33, ALU constant), recorded in the EXP-041
  report, section on the scheduling variant.
- Expected impact: a free, flag-only change to one production
  kernel if it verifies; a clean negative that closes the
  last EXP-041 loose end if it does not.
- Implementation cost: two additional build variants through
  the existing build.py discipline (restricted ISA flags
  unchanged; only the tune target varies), census, then one
  EXP-017 campaign per variant.
- Correctness risk: low. A tune flag cannot change semantics;
  the standard differential gates prove that per build.
- Testing requirements: Gate 2 (full differentials per
  variant, including the 256-nonce dispatch self-test), Gate
  4 (EXP-017 batch category D and search category E, sessions
  sized to the predeclared minimum detectable effect). Gate 6
  (one regtest block through the tuned build) only if a
  variant passes Gate 4 and is proposed for the production
  build flags. Gates 1, 3 and 5 do not apply.
- Required resources: this VM (AMD host; znver tuning is
  meaningless to test on the Intel host), sequential benchmark
  windows.
- Rollback: build flags revert in one line; the production
  library is rebuilt from the unchanged source. Nothing else
  references the variant.
- Success criterion: a variant shows an EXP-017 pooled ratio
  with the CI for relative improvement entirely above 0 in
  every session and pooled, at which point it is proposed for
  the production flags through the normal integration gate.
- Failure criterion: both variants NOT SIGNIFICANT, or the
  campaign cannot resolve below the predeclared effect floor;
  either closes the question as an established null alongside
  EXP-041.
- Score: P 0.35 (EXP-041's null for a structurally larger
  change caps optimism; the mechanism here is genuinely
  different, which keeps P off the floor) x B 4 x C 0.8 (the
  census is objdump fact) / (R 2 x E 2) = 0.28. Flag: P is
  the weak factor; it is an informed estimate from the
  EXP-041 precedent, not a measurement.

## Block B: further entries, ranked by score

### NOVA-ER-0006: Incident code registry (register R-30)

- EXP identity: none; engineering change under register R-30.
- Research question: can every detected fault, recovery action
  and backend refusal in the mining stack carry a stable
  numeric code from an append-only registry, so agent
  reasoning and post-incident audit key on codes instead of
  free text?
- Existing evidence: R-30 is NEW in both registers; the
  Whatsminer public error-code documentation is the studied
  model (documentation-sourced only). Current incident records
  in mining/autopilot.py and mining/mining_statistics.py are
  free text.
- Hypothesis: a coarse, append-only first taxonomy covers the
  observed fault classes (miner death, stale job, node
  disconnect, backend refusal, submission failure) without
  ossifying, because the observed classes are already
  enumerated by the keeper and autopilot records.
- Derivation: not applicable; the design constraint is the
  registry discipline (append-only, coarse first, codes never
  reused), stated in the R-30 row.
- Expected impact: countable fault classes; the awareness
  layer's degradation checks and the Prompt 3 intelligence
  metrics gain a stable key. Benefit is real but small, which
  B reflects.
- Implementation cost: registry file, code emission at the
  existing incident sites, statistics keying, tests.
- Correctness risk: minimal; codes annotate records and
  change no behaviour.
- Testing requirements: Gate 3 (unknown codes refused,
  registry append-only enforced) and Gate 5 (autopilot and
  keeper records carry codes end-to-end). Gates 1, 2, 4 and 6
  do not apply.
- Required resources: this VM; no benchmark window.
- Rollback: code emission is additive; removing the field
  restores prior records byte-for-byte in shape.
- Success criterion: all predeclared incident sites emit
  codes from the registry, and a replay of recorded incident
  classes maps each to exactly one code.
- Failure criterion: a fault class in the records cannot be
  coded without splitting hairs, indicating the taxonomy is
  wrong at its first step; that triggers a taxonomy redesign,
  not more codes.
- Score: P 0.9 x B 2 x C 0.8 / (R 1 x E 1) = 1.44. Note: the
  score is high because the entry is cheap and near-certain,
  not because it is important; the execution sequence treats
  it as fill-in work, not a campaign.

### NOVA-ER-0007: Cross-backend differential fuzzing at scale (register X-096)

- EXP identity: EXP-047.
- Research question: do all seven production backends agree
  digest-for-digest and hit-for-hit with the hashlib reference
  at fuzzing scale, across random headers, boundary nonces,
  unaligned spans and target densities, including densities
  near the solo share difficulty?
- Existing evidence: every integration ran differentials at
  the 100k to 500k scale (EXP-039: 124,351 digests per kernel;
  EXP-022: 491,520; EXP-041: 648,000 across variants), and
  Stage 1 verified the production batch path over 49,288
  cases. X-096 is EXPERIMENTAL and untested as a standing,
  larger, cross-backend campaign rather than a per-integration
  gate.
- Hypothesis: no mismatches exist; the campaign's value is
  the scale and the cross-backend shape (every backend
  against every other through the ComputeEngine seam), which
  no single integration gate covered.
- Derivation: none; the reference is hashlib plus the Stage 1
  independent reconstruction tool.
- Expected impact: raises the correctness floor under every
  future integration; any mismatch found is a critical defect
  caught before it can matter.
- Implementation cost: a fuzz driver over the existing seam;
  CPU time is the main cost.
- Correctness risk: none to production; the campaign is
  read-only against the libraries.
- Testing requirements: Gate 2 is the entry. Gate 3 applies
  in its input dimension (malformed spans, partial batches,
  spans ending exactly at 2^32). Gates 1, 4, 5 and 6 do not
  apply.
- Required resources: this VM, run in benchmark gaps; it is
  not a timing measurement, but the standing one-at-a-time
  rule for heavy CPU work still applies.
- Rollback: not applicable.
- Success criterion: the predeclared case count completes
  with zero mismatches across all backends, recorded as a
  standing evidence file.
- Failure criterion: any mismatch. That is a defect report
  with a minimal reproducing case, and it blocks the affected
  backend's tier until fixed.
- Score: P 0.85 (success means completing clean; the prior
  gates make a mismatch unlikely but the scale is new) x B 3
  x C 0.7 / (R 1 x E 2) = 0.89.

### NOVA-ER-0008: Category F end-to-end measurement at production difficulty (solo and pool pipelines)

- EXP identity: EXP-048.
- Research question: what is the end-to-end cost per block of
  the solo and pool pipelines at production difficulty, and
  what is their non-search overhead in absolute milliseconds?
- Existing evidence: EXP-040 built the category F harness and
  measured the GBT pipeline at regtest difficulty (0.065 s
  empty, 0.215 s loaded, 3.299 s amplified at 2^24 search
  amplification; non-search overhead about 44 ms empty and
  about 206 ms loaded per block; verification 2.5 to 3.9 ms
  per candidate). Stage 0 records the standing gap: nothing
  at production difficulty for any pipeline, and no
  end-to-end figure at any difficulty for solo or pool.
- Hypothesis: the transferable overhead figures (milliseconds
  per block) for solo and pool will be of the same order as
  the GBT pipeline's, with the solo path's share handling at
  adapted difficulty the largest single stage; the amplified
  method transfers without modification of production code.
- Derivation: pointer to research/sha256d/exp040/ and its
  design (harness-side wrapping only, zero production
  changes; amplification applied in the compute proxy only,
  blocks still meet the real target).
- Expected impact: completes the benchmark category map
  (BR-010) for all three pipelines and gives the solo
  cutover's operating cost before it fires.
- Implementation cost: harness extension to the solo server
  and to a local pool-protocol stub; three sessions per
  scenario, sequential.
- Correctness risk: low; the method never touches production
  code, and every produced block passes the EXP-036 gate in
  the harness, as in EXP-040.
- Testing requirements: Gate 4 in its category F form (the
  measurement protocol of EXP-040, reported as time per block
  and overhead milliseconds, never as a hash rate) and Gate 6
  in harness scope (every timed run ends in exactly one
  Core-accepted regtest block). Gates 1, 2, 3 and 5 do not
  apply beyond the harness's own checks.
- Required resources: this VM, the regtest node, sequential
  windows; the live miner's contention is recorded in every
  manifest, as EXP-040 did.
- Rollback: not applicable; research harness only.
- Success criterion: category F figures for solo and pool
  with the amplification factor stated, all runs accepted,
  and the hashrate specification updated.
- Failure criterion: a pipeline cannot be instrumented
  without production changes; that boundary is reported
  rather than crossed.
- Score: P 0.9 (the method is proven on one pipeline) x B 4 x
  C 0.7 / (R 1 x E 3) = 0.84.

### NOVA-ER-0009: Offline benchmark mode in the production binary (register R-35)

- EXP identity: EXP-049.
- Research question: can the production search path run a
  fixed bench work unit with no network and no submission
  path compiled into the mode, reporting the category E rate
  and the host profile in one command?
- Existing evidence: R-35 is EXPERIMENTAL by partial analogue:
  the Master Build scheduler measures through the real search
  path (262,144 hashes per repetition) but is an agent-layer
  tool with no fixed bench work unit. EXP-031's host profiles
  and the alternating VM replacements are the operational
  motivation: after every replacement the new host currently
  has no one-command profile.
- Hypothesis: a fixed work unit through search_first_counted
  reproduces the research harness's category E figures within
  session noise, making the mode a trustworthy profiling
  surface.
- Derivation: none; the safety property is structural (no
  submission path in the mode) and is a build property, not a
  runtime flag.
- Expected impact: feeds NOVA-ER-0012 (bake-off hardening) and
  every future host profile; removes dependence on research
  harnesses for routine measurement.
- Implementation cost: a mode in the engine's command surface,
  the fixed work unit, and a comparison campaign against the
  research harness.
- Correctness risk: the named risk is confusability with
  mining; mitigated by construction (no endpoint resolution,
  no submission symbols in the mode's path) and tested for.
- Testing requirements: Gate 2 (mode output digests match the
  reference), Gate 3 (mode cannot be made to submit: no
  network syscalls in a traced run), Gate 4 (agreement with
  the harness under EXP-017 pairing), Gate 5 (mode runs after
  a fresh VM replacement with no configuration). Gate 1 and
  Gate 6 do not apply.
- Required resources: this VM; one short benchmark window for
  the Gate 4 comparison.
- Rollback: the mode is additive; removing it restores the
  prior command surface.
- Success criterion: one command on a fresh host prints the
  host profile and a category E rate that agrees with the
  research harness within the paired CI.
- Failure criterion: the mode's figures disagree with the
  harness beyond noise, or the no-submission property cannot
  be structurally guaranteed; either stops the entry.
- Score: P 0.8 x B 4 x C 0.7 / (R 2 x E 2) = 0.56.

### NOVA-ER-0010: Endpoint health policy (register R-26)

- EXP identity: EXP-050.
- Research question: does a named endpoint health policy
  (ordered endpoints, N consecutive errors before failover, a
  timed failback retry of the primary, with damping) keep the
  pool leg mining through endpoint failure and recovery
  without operator action and without failback flapping?
- Existing evidence: R-26 is NEW. Current behaviour is a
  single endpoint with autopilot restart on failure; the
  2026-11-15 outage record shows the failure shape this
  addresses (pool DNS failure stopping the miner until
  supervision restarted it). The poclbm tolerance and failback
  model is the studied precedent.
- Hypothesis: with damping counts taken from the precedent,
  failover occurs inside one job interval and failback occurs
  at most once per damping window under a flapping primary.
- Derivation: none; the policy object and its parameters are
  the design surface, recorded in the R-26 row.
- Expected impact: the pool leg survives the most common
  observed outage class on its own; policy becomes inspectable
  and tunable by the agent layer.
- Implementation cost: policy object in the miner and
  autopilot seam, fault-injection tests against a local
  stratum stub.
- Correctness risk: a policy bug could starve mining or flap;
  bounded by keeping the autopilot's existing restart as the
  outer backstop, unchanged.
- Testing requirements: Gate 3 (failover, failback, flapping
  injection), Gate 5 (live start, stop and recovery through
  the policy). Gates 1, 2, 4 and 6 do not apply.
- Required resources: this VM and a local stratum stub; no
  benchmark window.
- Rollback: policy configuration reverts to the single
  endpoint behaviour, which is the degenerate policy.
- Success criterion: predeclared fault scenarios pass with
  mining resuming inside the stated bounds and no flap storm.
- Failure criterion: any scenario leaves the miner stopped
  while a healthy endpoint exists, or failback cycles exceed
  the damping bound.
- Score: P 0.8 x B 3 x C 0.6 / (R 2 x E 2) = 0.36.

### NOVA-ER-0011: Prepared-work prefetch queue (register R-33)

- EXP identity: EXP-051.
- Research question: does a prefetch queue between the
  template engine and the search threads, keyed to template
  identity with a starvation counter, measurably remove
  template-transition idle time on the GBT and solo paths?
- Existing evidence: R-33 is NEW. EXP-040 priced the stages
  (GBT 38.0 ms, prepare 19.7 ms, submit 99.9 ms at loaded
  regtest difficulty; non-search overhead 206.3 ms per loaded
  block) but built no mechanism. The EXP-025 identity
  discipline governs queue keying: entries drop on identity
  change.
- Hypothesis: at regtest and solo difficulties the queue
  removes most of the prepare-side bubble; at mainnet
  difficulty the effect is nil and the entry claims nothing
  there.
- Derivation: none; the governing rule is the EXP-025
  invalidation table (Stage 1, MERKLE_AND_TRANSACTION_MATHEMATICS.md
  section 6).
- Expected impact: smoother solo and regtest operation and a
  measured starvation counter that makes template-transition
  cost visible permanently.
- Implementation cost: queue in the engine-to-search seam,
  identity keying, counter wiring into EXP-037 statistics.
- Correctness risk: the named risk is serving stale work;
  mitigated by identity keying and drop-on-change, tested
  adversarially.
- Testing requirements: Gate 3 (template change mid-queue,
  identity mismatch, queue exhaustion), Gate 4 in category F
  form (before and after overhead per block through the
  EXP-040 harness), Gate 5, Gate 6 (regtest blocks through
  the queued path). Gates 1 and 2 are inherited from EXP-025
  and EXP-036 and are re-run, not re-derived.
- Required resources: this VM, the regtest node, one category
  F window.
- Rollback: the synchronous handoff remains the fallback
  behind a configuration switch.
- Success criterion: category F overhead per block falls by a
  predeclared margin at loaded regtest difficulty with zero
  stale serves in the adversarial suite.
- Failure criterion: any stale serve, or no measurable
  overhead reduction; the counter alone does not justify the
  mechanism.
- Score: P 0.6 x B 4 x C 0.7 / (R 2 x E 3) = 0.28.

### NOVA-ER-0012: Bake-off hardening into production dispatch (register R-23)

- EXP identity: EXP-052.
- Research question: can the advisory scheduler bake-off be
  hardened into a production dispatch input that picks the
  empirically fastest tier per host, with a minimum margin
  over the static order, re-runs on host change, and falls
  back to the static order on any doubt, without ever picking
  a worse tier outside noise?
- Existing evidence: R-23 is NEW as a production feature. The
  Milestone 4 advisory bake-off exists and ran live once:
  shani nominal winner over v512 by 0.8 percent, inside
  contention noise, which is precisely why a margin rule is
  the core of this entry. EXP-031 host profiles and
  NOVA-ER-0009's bench mode are the supporting instruments.
- Hypothesis: with an EXP-017-shaped median protocol and a
  margin set above the measured noise floor (NOVA-ER-0002's
  attribution work informs the floor), the hardened bake-off
  never underperforms the static order beyond noise across
  host rotations.
- Derivation: none; the decision rule is the deliverable, and
  it must be stated before any run, in the EXP-017 style.
- Expected impact: correct tier choice on hosts the lab has
  never seen, including both alternating VMs, decided by
  measurement rather than by the static table.
- Implementation cost: promotion of the scheduler path into
  the dispatch seam, margin and caching rules, host-change
  detection, campaign across rotations.
- Correctness risk: a wrong pick costs rate silently; the
  margin rule, the static fallback and the probe gates
  (unchanged) bound it. The C_THREADS shared-global defect
  must be fixed or worked around before concurrent
  measurement is trusted; that dependency is recorded in the
  execution sequence.
- Testing requirements: Gate 3 (corrupt cache, changed host,
  probe failure all fall back), Gate 4 (the bake-off protocol
  itself is EXP-017-shaped), Gate 5 (dispatch uses the cached
  winner at live start; static order on any doubt). Gates 1,
  2 and 6 do not apply beyond the existing per-tier gates,
  which are re-run.
- Required resources: both host types across rotations; the
  entry completes only after at least one rotation of each
  kind or an explicit partial verdict.
- Rollback: a configuration switch restores pure static
  dispatch; the cache file is inert when ignored.
- Success criterion: across the observed rotations the chosen
  tier is never worse than the static choice beyond the
  predeclared noise bound, and every doubt path falls back.
- Failure criterion: any rotation where the bake-off pick
  measurably underperforms the static pick; the feature
  stays advisory in that case, which is today's state.
- Score: P 0.5 (the one live margin was noise; the margin
  rule is untested) x B 5 x C 0.6 / (R 3 x E 3) = 0.17. Tied
  with NOVA-ER-0013; ranked first because its evidence base
  is measured rather than estimated.

### NOVA-ER-0013: Prefix sharing inside the dual-batch walker (register Y-098, Phase 001 H-6)

- EXP identity: EXP-053.
- Research question: does chunk-2 prefix sharing (rounds 0 to
  2, nonce-independent) pay when built as one ingredient of
  the production dual-batch walker, rather than as the
  standalone form EXP-013 measured?
- Existing evidence: the prefix facts are a proven identity
  (Stage 1 dependency graph: state after rounds 0 to 2 has no
  nonce-dependent word). EXP-013 measured the standalone form
  with ratios straddling 1.0, neither accepted nor refuted;
  Phase 001 H-6 and Stage 0 keep the item UNDER_INVESTIGATION
  for the combination only. EXP-027's C7 discussion bounds
  the plausible gain to the three prefix rounds of chunk 2.
- Hypothesis: inside the dual walker, where the two batches
  already share setup, the shared prefix removes duplicated
  work the standalone form could not amortise, yielding a
  small significant gain.
- Derivation: pointer to MESSAGE_SCHEDULE_DEPENDENCY_GRAPH.md
  sections 1 and 3 for the independence proof; the ceiling is
  arithmetic: at most 3 of 125 per-nonce rounds, before
  overheads.
- Expected impact: bounded above by about 2.4 percent of the
  per-nonce round count, realistically far less after
  overheads; the entry's main value is closing the last
  UNDER_INVESTIGATION kernel item either way.
- Implementation cost: a combined walker variant in
  research, full gates, one EXP-017 campaign against
  v512dual.
- Correctness risk: low; the identity is proven and the
  differential gates are standard.
- Testing requirements: Gate 2 (full differentials), Gate 4
  (EXP-017 against v512dual, sessions sized to a sub-2
  percent minimum detectable effect, with EXP-041's
  resolution warning stated in advance). Gate 6 only if a
  gain verifies and integration is proposed. Gates 1, 3 and
  5 do not apply.
- Required resources: this VM, one long sequential benchmark
  window (small-effect sizing).
- Rollback: research variant only; production is untouched
  unless the full integration gate passes separately.
- Success criterion: an EXP-017 verdict, significant or not,
  that moves H-6 out of UNDER_INVESTIGATION.
- Failure criterion: the campaign cannot resolve the effect
  at the predeclared session budget; that outcome is recorded
  as a resolution limit, as EXP-041 did, and the item is
  retired as unresolvable on this VM rather than left open.
- Score: P 0.25 (EXP-013 straddling 1.0 is the direct
  precedent) x B 4 x C 0.5 / (R 1 x E 3) = 0.17. Flag:
  guess-dominated. P and the expected effect size are
  estimates around a measured null-straddling precedent.

### NOVA-ER-0014: Dual-batch interleave granularity sweep (register Y-043)

- EXP identity: EXP-054.
- Research question: is the production dual-batch interleave
  granularity the best point on its own curve, or does a
  finer or coarser interleave of the two batches measure
  better through the real search path?
- Existing evidence: Y-043 is NEW and untested. The dual form
  itself is verified (EXP-026 C2) and integrated; EXP-018's
  residency work and EXP-005's geometry curve (flat top
  between 2 and 4 streams on the SHA-NI family) are the
  neighbouring measurements. No granularity sweep of the
  production walker exists.
- Hypothesis: the curve is flat near the production point, by
  analogy with EXP-005; a peak elsewhere would be a surprise
  worth having.
- Derivation: none; this is a parameter measurement, with the
  EXP-005 geometry record as the prior.
- Expected impact: either confirms the production point with
  evidence or finds a better one at zero design cost.
- Implementation cost: parameterised research build of the
  walker, several EXP-017 comparisons.
- Correctness risk: none beyond the standard gates per point.
- Testing requirements: Gate 2 per point, Gate 4 (EXP-017
  per candidate point against the production point, with a
  multiple-comparison correction stated in advance). Gates
  1, 3, 5 and 6 do not apply.
- Required resources: this VM, multiple sequential windows.
- Rollback: research builds only.
- Success criterion: a measured curve with a verdict at the
  production point (confirmed or displaced).
- Failure criterion: session budget exhausted without a
  resolvable curve; recorded as a resolution limit.
- Score: P 0.3 x B 4 x C 0.4 / (R 1 x E 3) = 0.16. Flag:
  guess-dominated. C is low because the analogy to EXP-005
  crosses kernel families.

### NOVA-ER-0015: Production wire protocol and persistent coordinator (roadmap F1)

- EXP identity: EXP-055.
- Research question: can the EXP-035 distribution design be
  built as a persistent coordinator with a wire protocol that
  meets proof obligations P1 to P6 at the protocol level,
  passes a randomised fault campaign at the EXP-035 standard,
  and has its overhead measured before any scaling claim?
- Existing evidence: EXP-035 design and prototype PROVEN
  in-process (60 of 60 trials, exact coverage under deaths,
  restarts, expiries and steals); EXP-043 overhead baselines
  and its two named prototype defects (unpruned lease table,
  unbounded snapshot cost) which this build must carry in as
  fixes; the single-machine ResourceRegistry
  (agent/intelligence/resources.py) supplies the local
  semantics. Roadmap F1 states the gates.
- Hypothesis: the protocol-level build preserves the
  prototype's exactness properties; the open risk is
  overhead and the two known defects, not the design.
- Derivation: pointer to research/sha256d/exp035/
  WORK_DISTRIBUTION_DESIGN.md and PROOFS/PROOF_OBLIGATIONS.md
  (P1 to P6).
- Expected impact: unblocks every fleet item (R-25, R-27,
  R-34, and the owner-gated F2) and converts Q7 from
  unmeasurable to measurable.
- Implementation cost: the largest in this portfolio: a
  coordinator process, protocol, persistence, campaign
  harness.
- Correctness risk: high by portfolio standards; a
  coordinator bug can falsely complete work. The EXP-038
  frontier rules and the campaign standard are the
  mitigation, and activation on real machines stays owner
  gated (F2) regardless of this entry's result.
- Testing requirements: Gates 2 and 3 at the protocol level
  (differential accounting against an independent model;
  death, restart, expiry, steal and duplicate injection),
  Gate 4 in overhead form (per-position cost against the
  EXP-043 baselines), Gate 5 (coordinator restart with
  in-flight leases), Gate 6 (a regtest block produced
  through coordinator-assigned work). Gate 1 is the P1 to P6
  proof obligations themselves.
- Required resources: this VM for the build and campaign;
  a second machine only for the optional two-machine
  overhead measurement, which does not activate any fleet
  mining.
- Rollback: the coordinator is a new component beside the
  existing paths; not deploying it is the rollback. The
  single-machine registry remains the local behaviour.
- Success criterion: all F1 gates pass as stated in the
  roadmap, with overhead figures recorded.
- Failure criterion: any campaign trial with inexact
  coverage, or overhead that makes the design unusable at
  the measured scale; either returns the design to EXP-035
  status with the failure recorded.
- Score: P 0.6 x B 7 x C 0.6 / (R 4 x E 5) = 0.13.

### NOVA-ER-0016: H-033-02 residual cone closure attempt

- EXP identity: EXP-056.
- Research question: do 5-instruction round cones exist
  outside EXP-042's stated bounds (sum or Boolean output
  produced by two or more instructions), the residual
  generality of H-033-02?
- Existing evidence: EXP-033 closed the named sub-shapes;
  EXP-042 refuted E2 and fixed the cone minimum at exactly 6
  under its bounds. The full-cone CEGIS instrument timed out
  at 600 s (EXP-033) and at 1,500 s and 1,400 s per cone
  (EXP-042). Nothing about the residual shapes is known
  either way.
- Hypothesis: none directional. The entry buys information:
  either a SAT construction (which would reopen the round
  optimum story legitimately, as a new discovery, not a
  reopening of a rejected item) or an UNSAT closure of the
  last open mathematical shape in the programme.
- Derivation: pointer to research/sha256d/exp042/
  EXP042_REPORT.md for the decomposition encoding this entry
  extends, and to the EXP-033 hypothesis registry for the
  exact residual statement.
- Expected impact: mathematical completeness of the round
  result. By EXP-041's evidence, even a SAT result would not
  be expected to change elapsed time on this core; B is set
  for knowledge value, not rate.
- Implementation cost: solver time is the cost: larger
  budgets, alternative encodings (bit-blasting bounds,
  symmetry breaking), run in idle windows inside the Prompt
  1 sandbox discipline.
- Correctness risk: none to production; a SAT candidate is
  only believed after the standard exact verification over
  symbolic cone inputs, as in EXP-042's gates.
- Testing requirements: Gate 1 is the entry (proof or
  verified construction). Gates 2 to 6 do not apply unless a
  construction emerges, in which case it re-enters the
  portfolio as a new item with its own gates.
- Required resources: this VM's idle CPU only; strictly
  time-boxed, lowest scheduling priority, never displacing a
  benchmark window.
- Rollback: not applicable.
- Success criterion: a definitive SAT with verified
  candidate, or UNSAT at the full residual generality,
  either closing H-033-02.
- Failure criterion: another timeout at the predeclared
  budget; recorded as inconclusive with the budget stated,
  and the item stays UNDER_INVESTIGATION honestly.
- Score: P 0.15 (two prior timeouts at this instrument) x B 6
  x C 0.5 / (R 1 x E 4) = 0.11. Flag: guess-dominated. P is
  an estimate about solver behaviour, the least reliable
  factor in this portfolio.

### NOVA-ER-0017: Stratum aggregation tier (register R-27)

- EXP identity: EXP-057.
- Research question: can a stratum-speaking aggregation tier
  hold few upstream connections, fan workbases out to fleet
  workers, validate shares through EXP-036, and keep
  per-worker accounting through EXP-037, without becoming a
  trust hole?
- Existing evidence: R-27 is NEW; no component exists beside
  mining/solo_server.py. The ckpool proxy lineage is the
  studied design. EXP-043's loopback figures are the only
  overhead evidence for anything in this direction.
- Hypothesis: the solo server's job and validation machinery
  generalises to the aggregation role; the genuinely new
  work is fleet identity, which must inherit EXP-035's
  checks rather than ckpool's open pool trust model.
- Derivation: none; the identity requirements are the
  design's core and are stated in the R-27 row.
- Expected impact: fleet scale without one upstream
  connection per worker, and a single attachment point for
  verification and accounting on stratum traffic.
- Implementation cost: a new component, second only to
  NOVA-ER-0015 in size; strictly after it, since worker
  identity and leases are F1 semantics.
- Correctness risk: a new trusted component on the share
  path; bounded by routing every candidate through
  verify_candidate and by keeping submission authority out
  of the tier until separately gated.
- Testing requirements: Gates 2, 3 and 5 in full (share
  validation differentials, identity spoofing and stale work
  injection, restart behaviour), Gate 6 (regtest blocks
  through the tier). Gate 4 in overhead form against
  EXP-043 baselines. Gate 1 does not apply.
- Required resources: this VM; multi-machine claims wait for
  the same conditions as NOVA-ER-0015.
- Rollback: the tier is additive; workers return to direct
  endpoints by configuration.
- Success criterion: the tier serves predeclared worker
  counts with exact accounting and zero unverified
  submissions in the fault campaign.
- Failure criterion: any identity or accounting gap in the
  campaign; the tier does not deploy in that case.
- Score: P 0.5 x B 6 x C 0.4 (design precedent only, no
  local prototype) / (R 4 x E 5) = 0.06. Flag:
  guess-dominated on C.

### NOVA-ER-0018: PID control for worker count and span size (register R-32)

- EXP identity: EXP-058.
- Research question: does a PID loop driven by a measured
  error signal (steal time or share interval error) adapt
  worker count and span size on this contended VM more
  smoothly than the autopilot's step changes, without
  oscillation?
- Existing evidence: R-32 is NEW; no controller has been
  designed. EXP-031 supplies the signal data (about 2
  effective CPUs under a 4 vCPU claim, 61 to 64 percent
  baseline busy). The bmminer fan-control PID is the studied
  shape, from a hardware target.
- Hypothesis: conservative gains with the step policy
  retained as fallback hold the rate within noise of the best
  fixed configuration while removing throttle and collapse
  cycles.
- Derivation: none yet; gain selection from EXP-031 signals
  is part of the work and must be recorded before any live
  trial.
- Expected impact: smoother adaptation on the VM class the
  lab actually runs on; bounded, because the ceiling is the
  same 2 effective CPUs.
- Implementation cost: controller in the autopilot seam,
  offline tuning against recorded signals, supervised live
  trial.
- Correctness risk: a mis-tuned loop oscillates against the
  live miner; mitigated by the retained step-policy fallback
  and by offline tuning first.
- Testing requirements: Gate 3 (signal loss, step
  disturbances, gain faults), Gate 5 (live trial under
  supervision with automatic fallback). Gates 1, 2, 4 and 6
  do not apply; any rate claim would need its own EXP-017
  entry and is not made here.
- Required resources: this VM; EXP-031 signal recordings.
- Rollback: one configuration value restores the step
  policy, which remains in code.
- Success criterion: predeclared stability bounds held
  across disturbance scenarios, with no fallback trips in
  the nominal scenario.
- Failure criterion: sustained oscillation or repeated
  fallback trips; the step policy stays, with the data
  recorded.
- Score: P 0.4 x B 3 x C 0.4 / (R 3 x E 3) = 0.05. Flag:
  guess-dominated on P and C; no local precedent exists.

## Gated and blocked items (no rank, no score)

These are real items that cannot be scheduled by score
because a decision or a resource outside this programme
gates them. They are recorded so they are not lost.

- Roadmap F2, fleet activation: OWNER DECISION. Nothing in
  this portfolio activates, contacts or measures another
  machine for mining.
- Roadmap F5 and register R-28, Core multiprocess IPC
  template supply: DEFERRED on an owner decision about the
  Bitcoin Core version (the lab pins 28.1; the IPC route is
  a Core 32 era build).
- Roadmap F4, candidate verification inside the GBT cycle:
  OWNER DECISION. The evidence that the two verdicts agree
  already exists (Master Build Milestone 6); the choice is
  architectural, not experimental.
- Register R-21 and R-29, Stratum V2 and job declaration:
  DEFERRED by recorded decision; revisit only if an external
  pool requires SV2. The lab's own solo server is V1.
- Register R-25 (quota allocation) and R-34 (hotplug worker
  attach and detach): NEW but strictly dependent on
  NOVA-ER-0015 (F1); they take EXP numbers when F1 lands.
- Register R-31, signed release chain for fleet software:
  NEW; its key management design must precede any build, and
  it only matters alongside a fleet. Design work may start
  without F2; deployment may not.
- EXP-028 ARMv8 SHA2 and NEON dispatch: specified, never
  executed; blocked on ARM hardware that does not exist in
  this environment. No rates exist and none are estimated.

## Recommended execution sequence

Ranking is by score; execution order also respects
dependencies and the standing rule that benchmark campaigns
on this VM run strictly one at a time (parallel runs corrupt
the EXP-017 statistics on this shared-CPU guest).

1. NOVA-ER-0002 (EXP-045, AVX2 discrepancy) first among the
   benchmarks, despite ranking second in Block A: it
   calibrates the instrument (fingerprinted sessions) that
   NOVA-ER-0003 and NOVA-ER-0005 depend on for believable
   small-effect verdicts.
2. NOVA-ER-0001 (EXP-039 refusal) executes whenever the Intel
   host next rotates in. It waits for no one and blocks
   nothing; it is host-gated, not sequence-gated.
3. NOVA-ER-0003 (EXP-046, design C re-measurement) next in
   the benchmark queue, on the fingerprinted protocol from
   step 1.
4. NOVA-ER-0005 (EXP-044, -mtune) after it, sized for a small
   effect using the noise floor measured in step 1.
5. NOVA-ER-0004 (solo vardiff) is code work, not a benchmark;
   it proceeds in parallel with the benchmark queue, but its
   regtest campaign slots between benchmark campaigns, never
   during one. NOVA-ER-0008 should take its solo-pipeline
   baseline before vardiff lands, so the pair forms a before
   and after record; if scheduling forces a choice, the
  baseline measurement wins.
6. NOVA-ER-0007 (EXP-047, fuzzing) runs in benchmark gaps. It
   is not a timing measurement, but it is heavy CPU work and
   obeys the one-at-a-time rule.
7. NOVA-ER-0008 (EXP-048, category F) after the vardiff
   baseline note in step 5 is resolved.
8. NOVA-ER-0009 (EXP-049, offline bench mode) before
   NOVA-ER-0012: the hardened bake-off consumes the bench
   mode's fixed work unit and host profile.
9. NOVA-ER-0010 (EXP-050, endpoint health) and NOVA-ER-0006
   (incident codes) are independent code work; they fill
   engineering time between campaigns. NOVA-ER-0006's high
   score does not earn it a campaign slot.
10. NOVA-ER-0011 (EXP-051, prefetch queue) after EXP-048,
    whose harness is its Gate 4 instrument.
11. NOVA-ER-0012 (EXP-052, bake-off hardening) after
    NOVA-ER-0009 and after the C_THREADS shared-global defect
    is fixed or formally worked around; it completes only
    across host rotations, so it runs as a standing item, not
    a campaign.
12. NOVA-ER-0013 (EXP-053) and NOVA-ER-0014 (EXP-054) take
    the remaining benchmark windows in score order, with
    their guess-dominated flags attached to any report.
13. NOVA-ER-0015 (EXP-055, F1 coordinator) is the next
    engineering programme after the above; NOVA-ER-0017
    (EXP-057, aggregation tier) follows it strictly.
    NOVA-ER-0018 (EXP-058, PID control) may proceed any time
    after EXP-031 signal review, but its live trial waits
    for a quiet window.
14. NOVA-ER-0016 (EXP-056, H-033-02 residual) runs last and
    only in otherwise idle solver windows, time-boxed, never
    displacing any item above.

Dependencies, collected: 0003 and 0005 depend on 0002's
fingerprint protocol; 0008's solo baseline precedes 0004's
integration; 0012 depends on 0009 and on the C_THREADS fix;
0011 depends on 0008's harness; 0017 depends on 0015; R-25
and R-34 depend on 0015; 0001 depends only on the Intel host
rotation; 0016 depends on nothing and feeds nothing.
