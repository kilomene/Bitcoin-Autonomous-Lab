# EXP-030 Programme Final Report

Programme: EXP-030, NOVA SHA-X: Open-Source Mining
Intelligence, CPU Architecture Transformation, Autonomous
Mining and Mathematical Breakthrough Programme.
Owner directive: 2026-11-15 (record:
~/workspace/goals/bitcoin-autonomous-lab-private-bitcoin-mining-lab/files/EXP030_DIRECTIVE_RECORD.md).
Repository: kilomene/Bitcoin-Autonomous-Lab.
Date of this report: 2026-11-15.
Status: all phases A to H are complete. Every production
change the programme made has passed an independent
post-integration audit by an agent other than its author.

This report answers the directive's section 16 questions,
in order, from the phase evidence on disk. Negative results
are stated where they fell. Objectives are not lowered:
the minimum system objective stands at 500 GH/s and the
larger research objective at 140 TH/s. Nothing below
500 GH/s is called success anywhere in this report.

Mission state, stated plainly at the top: the lab's balance
is 0 BTC. No mainnet block has been found. The programme's
actual success criterion (discover, independently verify,
construct and successfully submit a valid Bitcoin block on
mainnet) is NOT yet met. What the programme did achieve is
that every step of that path except the discovery itself is
now implemented, exactly verified, and proven end to end on
regtest through the production code, and that the search
side is measured honestly against the targets.

Phase map: Phase A, reference audit (exp030/
REPOSITORY_AUDIT.md and REFERENCE_TO_NOVA_MATRIX.md).
Phase B, NOVA audit and gap analysis (exp030/
NOVA_GAP_ANALYSIS.md). Phase C, EXP-031 CPU and VM
characterisation (exp031/). Phase D, EXP-032 CPU execution
engine (exp032/). Phase E, EXP-034 job and template engine
(exp034/). Phase F, EXP-036 exact candidate verification
and block submission (exp036/). Phase G, EXP-035
distributed architecture (exp035/). Phase H, EXP-033
mathematics (exp033/). EXP-037 (statistics and probability)
and EXP-038 (autonomous operations) ran under directive
sections 10 and 11 (exp037/, exp038/).

## Q1. What Bitaxe taught us

From the source audit of skot/bitaxe and bitaxeorg/
ESP-Miner at the audited commits (findings B1 to B18):

- The verification shape that matters most: the result
  task rebuilds the exact 80-byte header from the stored
  job, recomputes SHA-256d, and compares with exact
  integer arithmetic (uint256_lte) against the pool target
  and, separately, against the exact network target
  decoded from nBits. Share and block are distinguished
  exactly; floating-point difficulty is used only for
  display and the scoreboard (B9). This is matrix rows M01
  and M02, adopted: it is the pattern EXP-036 formalised
  as NOVA's pipeline.
- The stored job is the unit of trust: results return with
  a slot index and are judged only against the immutable
  job they belong to (B8). Both reference firmwares
  converge on this, and on the same skeleton overall
  (pool tasks, job construction, a slot-keyed job registry,
  a result task that re-derives the header, counter-based
  telemetry, a supervisor that can halt work). That
  convergence is the strongest architectural signal in the
  audit (observation X1).
- Work multiplication without pool traffic: extranonce2
  stepping per job interval (B6), and version rolling in
  two forms (hardware mask on newer chips, software
  increment_bitmask on the BM1397, B7).
- Controller-side midstate: the first-block midstate is
  computed once in software per job (B4), the same exact
  reuse NOVA already practises (67 of 192 rounds reusable
  per template).
- Source-side result filtering with an adaptive
  difficulty mask and a grace period on increases (B10),
  which translates to NOVA as candidate masks (already the
  DualMask form) and as the adaptive solo difficulty
  control loop recorded as matrix row M10 (design note,
  not implemented; see Q6).
- Counter-first telemetry: hashrate is measured from
  worker-owned hash counters in 1 minute, 10 minute and
  1 hour windows, never estimated from shares (B13).
  Adopted as the EXP-037 rule (M11).
- A persistent best-difficulty scoreboard carrying full
  reconstruction context, so any historical best can be
  re-derived and re-verified (B12, M17).
- Supervision and safety policy: staged job activation on
  non-clean notifies (B3), task monitoring, startup
  self-test, and a thermal safe mode with enforced cooling
  and hysteresis resume (B16). The policy translates; the
  mechanisms (DAC-set voltage, PLL ramping, fans) do not.
- What does not translate: the serial ASIC protocol, on-chip
  nonce-space partitioning and silicon errata compensation,
  voltage and clock control, and the appliance features
  (display, provisioning). Stratum V2 ships in the
  reference (B18); NOVA remains V1 only (see Q6).

## Q2. What Qaxe taught us

Hardware (shufps/qaxe, findings Q1 to Q6): four-ASIC
boards on one shared core rail and one serial chain. The
transferable lessons are negative-space ones: a shared
resource is a shared failure domain (one chip or power
fault disables the whole board, Q6), so NOVA's design rule
is explicit per-worker and per-VM failure domains (M26);
and the legacy boards' separate supervisor microcontroller
(power-good, reset sequencing, sensing, independent of the
main controller, Q3) validates NOVA's existing supervision
split (autopilot plus outer keeper, M20).

Firmware (shufps/ESP-Miner-NerdQAxePlus, 17 directive
areas audited, weaknesses W1 to W7):

- Positive patterns adopted into the EXP-035 design: the
  complete job registry with clone-on-read, so the stored
  job is never mutated by consumers (areas 1, 2; M05);
  extranonce2 partitioning by worker, (slave_id << 25) |
  counter25, giving up to 128 workers disjoint coinbase
  space by construction (area 3; M06); master-side central
  validation and submission, with workers never submitting
  directly (area 13; M13 as adapted); a persistent worker
  registry with a 10 second telemetry timeout and
  foreign-fleet rejection (area 15; M14); and the starved
  worker rule, drop the assignment and re-register (area
  15; M15).
- The single most valuable lesson is a defect: W1. The
  fork judges nonces and found blocks by floating-point
  difficulty (test_nonce_value, truediffone heritage;
  block detection compares doubles). Near a boundary this
  misjudges candidates in either direction. Matrix row M03
  rejects it, and EXP-036 exists largely to forbid it in
  NOVA: no float participates in any NOVA candidacy or
  acceptance decision (see Q12).
- Further weaknesses recorded so NOVA does not inherit
  them: the duplicate ring is 32 entries keyed only by
  (nonce, version), job-blind, and duplicates are
  submitted to the pool anyway (W2; M12 replaces the key
  with full header identity); registry slot recycling can
  misattribute late results (W3; M04 adds generation
  tags); new-work detection keys on ntime only, so a new
  prevhash inside the same second is missed (W4; EXP-034
  verified no NOVA path has this defect, see Q12); dual
  byte-order fields carried through the job struct are a
  standing endianness bug source (W5; M25 rejects the
  representation, keeps one canonical order); CAN
  multiframe transfer has no payload checksum or total
  length (W7; M31 keeps the framing discipline and adds
  both); and the mining logic carries almost no in-repo
  unit tests (W6).

## Q3. What NerdOCTAXE taught us

Patsch91/NerdOCTAXE-Gamma (findings O1 to O6; audited at
depth 1, a stated limit): doubling from four ASICs to
eight on one board scaled everything except the controller:
six-phase power delivery (O2), per-chip internal
temperature sensing added explicitly at that scale (O3),
and commodity tower cooling repurposed for eight chips
(O4), while keeping one controller, one rail and therefore
one failure domain (O6).

Translated to CPU software (matrix rows M26, M27, M28):
when worker count grows, sensing granularity, supervision
capacity and verifier throughput must be budgeted per
worker, because aggregate-only telemetry hides the sick
worker and an unbounded fleet outgrows its single verified
submission path. EXP-037 adopted per-worker and per-backend
breakdowns recorded alongside totals (M28), and the
EXP-035 design budgets verifier throughput as the fleet
bound (M27). The circuits themselves, and the one-controller
model (the opposite of NOVA's autonomous-agent direction),
do not translate; commodity cooling has no CPU-software
counterpart at all (M29, rejected).

## Q4. Which findings genuinely translate to CPU software

The translation matrix (REFERENCE_TO_NOVA_MATRIX.md) holds
34 rows with a decision each. The ones that genuinely
translate, and where they landed:

- Adopted and now in production through EXP-036: exact
  header reconstruction and exact integer target
  comparison as the only authoritative test (M01, M02).
- Adopted as design and prototype in EXP-035: extranonce2
  partitioning by worker (M06), worker registry with
  heartbeat leases and fleet identity checks (M14),
  starvation re-registration (M15), generation-tagged job
  identity (M04 adapted), duplicate detection keyed by
  full header identity (M12 adapted), central verification
  with a single submission path (M13 adapted),
  length-prefixed wire frames with total length and
  payload checksum (M31 adapted), explicit failure domains
  (M26), verifier-throughput budgeting (M27 adapted), and
  the combined search space of extranonce, BIP320 version
  variants and ntime under one exact accounting (M34
  adapted).
- Adopted in EXP-037: counter-first telemetry (M11) and
  per-worker granularity (M28); persistent candidate and
  best-share records with full job identity (M17) are the
  shape the EXP-035 candidate queue journal implements in
  prototype.
- Adopted in EXP-038: the supervision layering the
  references validate (M20: supervisor never mines, miner
  never supervises itself), already embodied as autopilot
  plus systemd plus the outer keeper, and startup
  self-tests at backend selection (M32, extended pattern).
- Confirmed as already-correct NOVA practice: midstate
  reuse (M08), local extranonce stepping (M07), staged job
  replacement (M16), duplicate-notify suppression (M22),
  clone-on-read job access (M05, as the EXP-034 contract).
- Adapted in spirit inside the existing engine: the
  on-chip ticket mask (M09) is the same idea as the
  AVX-512 opmask candidate compare NOVA already runs in
  v512dual; the reference validates the direction, not the
  mechanism.

Ideas marked Investigate in the matrix (M10 adaptive solo
difficulty, M18 thermal and steal shed policy, M21 load
ramping, M23 Stratum V2, M30 metering discipline, M33
capability profiles) remain investigation items, not
adoptions; EXP-038 dispositioned M10, M18 and M21 as design
notes on unmeasured ground, and none is implemented.

## Q5. Which ideas are rejected

- Floating-point difficulty as an authoritative test
  (M03, weakness W1): rejected outright, forbidden by the
  EXP-036 design, and pinned by a boundary test showing
  float64 cannot distinguish the difficulty-1 target from
  target plus 1 while the integer compare decides them.
- The dual byte-order job representation (M25): rejected;
  one canonical header byte order inside NOVA, transforms
  only at protocol boundaries.
- Deliberately submitting duplicate results (W2's
  practice): rejected; duplicates are detected on full
  header identity and counted, never submitted.
- Registry slot recycling without generation tags (W3 as
  practised by both references): rejected as a semantics;
  the registry idea is kept only with generation identity.
- Commodity cooling and all ASIC mechanisms as mechanisms
  (M29; also the serial ASIC protocol, on-chip nonce
  partitioning and errata compensation, DAC voltage and
  PLL control, CAN transport itself, worker identity
  derived from nonce bits, register-poll telemetry):
  rejected as non-translatable; only their policies or
  principles were carried, as recorded in Q4.
- Inside EXP-035's decisions: dividing the 32-bit nonce
  range as the distribution model (the space is
  multi-dimensional); workers submitting directly to a
  pool or node (one verified submission path only); float
  difficulty anywhere in work accounting; leases surviving
  a coordinator restart (reclaim and re-register is the
  honest semantics); and activating the fleet agents in
  this programme.
- Inside EXP-032: the flags-form search entry is rejected
  for integration (measured, Q8); the production SHA-NI
  intrinsics kernel as a batch backend is an established
  negative (0.517x of the C batch it would replace).
- Inside EXP-033: every examined restructuring direction
  except one named shape is closed (Q10, Q11).

## Q6. What is missing from NOVA

Phase B measured the starting point against the directive's
20 required components: 2 existed, 15 were partial, and 3
were missing outright (Work Lease Manager, Distributed
Agent Coordinator, Candidate Queue). The programme closed
the verification and operations gaps in production (Q12).
What is still missing or partial at programme close,
stated without softening:

- Candidate Queue: still not built in production. EXP-035
  designed it (persist-before-acknowledge journal, dedup
  on full header identity, generation check at drain) and
  prototyped it under research; candidates on the live
  paths are still handled synchronously, and a crash
  between confirmation and submission loses a candidate.
  Candidate recovery across restarts remains open.
- Work Lease Manager and Distributed Agent Coordinator:
  design plus a tested research prototype exist (EXP-035);
  there is no production coordinator service, no wire
  protocol implementation, no persistent coordinator.
  Production integration is deferred behind a measured
  overhead study that has not run (the EXP-035 final
  report's statement of what its results do not show).
- Fleet activation: not done. The roughly 25 agents were
  not activated, contacted or measured. That decision
  remains the owner's.
- Stratum V2: absent entirely. The Stratum adapter is V1
  only on both client and server sides.
- Version rolling and timestamp rolling: absent from every
  production path (EXP-034 re-verified this by execution).
  The only production search-space expansion mechanisms
  are the nonce, the engine extranonce rounds, and the
  solo and pool extranonce pair. EXP-035's design owns
  the expansion work.
- A unified, protocol-independent job model with
  persistent job records and shared job generation
  identifiers: not built. The GBT, Stratum and solo job
  representations remain separate; EXP-034 verified the
  existing machinery rather than unifying it.
- Statistics wiring: mining/mining_statistics.py is a
  production module with pinned accounting rules, but the
  live paths still emit their own counters; record()
  wiring into mainnet_live, the heartbeat and the solo
  server, windowed rate series on the live path, and the
  directive's latency series (verification, template
  construction, job distribution, submission, worker
  recovery) are not done and no numbers are claimed for
  them.
- Smaller recorded items: the PreparedTemplate snapshot
  hardening (version, prevhash, bits at prepare time) is
  recommended by EXP-034 and its audit, not implemented;
  the MiningEngine GBT path was deliberately left as the
  reference implementation rather than unified onto
  candidate_verify; the solo server's configured tag never
  enters its coinbase (documentation defect, audit note
  N-1); adaptive solo difficulty (M10) is a design note
  only and the solo share difficulty remains the
  configured constant 0.02; no disk or memory watch exists
  for the growing evidence log, and no log rotation policy.
- Documentation debt found by Phase B (11 contradictions,
  including docs/ARCHITECTURE.md describing mainnet as
  paused and evidence/SUMMARY.md denying the lab's own
  pool-accepted share) is recorded in NOVA_GAP_ANALYSIS.md
  section 4 and is not fixed by this programme.

## Q7. Actual CPU and VM capacity

EXP-031 characterised the mining VM from primary sources
(tools and raw records under exp031/). The guest claims
4 vCPUs (online list 0 to 3, affinity 0 to 3, all
read-from-system). Measured capacity is about 2 effective
CPUs: production-engine thread scaling saturates at
2 threads (run 1: 9.36M to 9.92M H/s going from 2 to
4 threads; run 2: 11.21M to 10.25M, slightly worse), the
single-thread rate alongside production is 5.19 to 5.50M
H/s, and one engine process aggregates about 9.9 to 11.2M
H/s alongside the live miner and the syncing node. The
guest is heavily contended from inside before any probe
load: baseline utilisation 61 to 64 percent busy, load
average 7.0 to 7.5 on 4 claimed vCPUs, CPU pressure (PSI
"some") 79 to 86 percent, while steal stays modest at 1.4
to 2.7 percent. The ceiling mechanism is unknown from
inside: cpu.max does not exist at the visible cgroup root,
so no quota value can be read, and NOVA plans against the
measured ceiling, not the absent file. Hardware
performance counters are not accessible (perf_event_paranoid
4; perf_event_open returns EPERM even as uid 0), so no
cycles, IPC or cache-miss counters exist here. Thermal
state is not accessible. The EXP-031 host was an AMD EPYC
9D25 guest exposing the full AVX-512 set (F, DQ, CD, BW,
VL, VBMI, VBMI2, IFMA, VNNI, BF16) plus AVX2, SHA-NI, VAES
and GFNI; the programme's later phases ran after a VM
replacement on an Intel Xeon Platinum 8321HC (AVX-512F,
BW, VL, VNNI; no SHA extensions, no VBMI), which the
production restricted-flag builds and CPUID probes absorb
by design. Guest-visible memory is about 7.75 GiB. Host
physical topology, host oversubscription and actual core
frequency under load are unknown and are reported as
unknown in the EXP-031 register.

## Q8. Real production SHA-256d throughput

Three measured figures, each with its conditions, and no
blending of them:

- Live observation (Phase 6B basis, AMD host): the
  production miner on the v512dual backend was observed in
  live sessions at about 20.6M H/s. This is the rate the
  gap model uses.
- EXP-032 protocol measurement (EXP-017 paired method,
  2 threads, contended guest, alongside the live miner):
  complete production search through ComputeEngine,
  v512dual search against production C search, pooled
  6.781x [6.154, 7.467], verified in every session; dual
  search session medians 8.2M to 14.8M H/s. The best
  complete-search median observed in EXP-032 is 14.8M H/s.
- EXP-031 load probe (same contended conditions):
  aggregate about 9.9 to 11.2M H/s from one engine process.

EXP-032's other verdicts, all under the EXP-017 protocol
with 1,358,210 batch digests verified byte-identical
against hashlib before any timing: the new AVX2
multi-buffer kernel is a verified improvement over the
production C batch (pooled 1.409x [1.340, 1.480]) and the
SHA-NI H-01 four-stream kernel is a verified improvement
over the C batch (pooled 2.861x [2.671, 3.089], reaching
0.726x of the v512dual batch); both are fallback-tier
results for hosts without AVX-512 and neither is
integrated, because this host has AVX-512 and no target
host class without it is a current deployment prospect.
The production single-stream SHA-NI intrinsics kernel is
an established negative in batch scope (0.517x of C): the
C batch it loses to runs OpenSSL's MSG-schedule SHA-NI
code, so the schedule machinery, not the round
instructions, is what makes SHA-NI fast. The EXP-022 flags
question is answered negatively three ways: searching
through the flags batch loses to native dual search by
2.565x [2.320, 2.836]; a dedicated flags-form search entry
against the v512 search is 0.967x [0.885, 1.059], not
significant, with any gain bounded at about 1.06x; against
dual search it is 0.493x. In search scope the materialised
digests live in an L1-resident stack array, so there is no
buffer traffic for the flags form to save. No flags search
integration was made; the flags batch keeps its verified
batch-scope role only.

## Q9. Actual unique search coverage

What is exact, and what is not, kept separate:

- Inside a process, ComputeEngine accounting (Task 003.9)
  separates requested hashes, unique coverage, backend
  hashes, repeated work and verification hashes exactly,
  and EXP-037's MiningStatistics holds those categories as
  independent counters that are never summed into a
  combined total (the categories overlap by construction;
  a combined total would double-count).
- EXP-035's controlled campaign (local simulation,
  labelled as such): 60 of 60 trials completed their
  declared space exactly, 609,280 unique positions in
  aggregate, pairwise disjoint with no gaps, under 2,167
  worker deaths, 1,564 worker restarts, 801 coordinator
  restarts, 806 lease expiries and 694 legitimate steals;
  257,020 repeated computations were accounted in their
  own counter and never inside unique coverage; 3,190
  zombie restart replays, 2,088 duplicate deliveries and
  739 not-holder attempts were all rejected and counted.
- Across restarts on the GBT path, EXP-038's work
  checkpoint makes coverage exact by construction: the
  frontier advances only after a batch returns without a
  hit, so unfinished work is never recorded as completed;
  the independent audit's 24-configuration restart
  campaign found coverage pairwise disjoint and
  union-complete in every configuration.
- Live mainnet coverage: the verified live figures are
  the evidence log's. The EXP-037 phase census found 247
  accepted shares where the old tail-window heartbeat
  counter reported 222 (25 silently dropped); the
  independent audit's brute-force census shortly after
  found 248 accepted, 8 rejected, 256 share_result events.
  The evidence log is the primary record and the fixed
  EvidenceCounter now counts it whole. There is no single
  audited lifetime unique-hash total for the live pool
  miner across all of its sessions and restarts, and this
  report does not invent one: on the pool path, separation
  between sessions is the pool's per-connection
  extranonce1, and pre-EXP-038 restarts on the GBT path
  repeated work without a system-level record (Phase B
  gap 3). Unique coverage claims in this programme are
  made only where the accounting exists to back them.

## Q10. Which mathematical hypotheses remain promising

Almost none, and the report keeps the tiers strict.
EXP-033 attacked the one sub-space EXP-027 had left
explicitly open (non-sharing cross-round graph
restructuring) and closed it at the bounds stated in Q11.
Exactly one shape remains unrefuted: E2, routing the Sigma
output through the Maj (resp. Ch) value so the Boolean
instruction sits inside the Sigma sub-DAG (hypotheses
H-033-02 and H-033-05). Its status is UNPROVEN BREAKTHROUGH:
the full-cone CEGIS attack at L = 5 was INCONCLUSIVE (the
solver returned unknown at timeout), which is not evidence
for the shape and not a proof against it. It is the only
hypothesis in the programme labelled promising, and
promising here means only "not yet refuted at a stated
bound", nothing more. Everything else examined (the E1
correlation-exploitation shape for both cones, W20
schedule linearity, outer-hash precomputation, comparison
early exit, representation deferral across the round
boundary) is an established negative or a refutation, in
Q11. EXP-020's residual (production emits 29 vector ops
against the proven 28-op vocabulary optimum) is a compiler
codegen gap, not a mathematical hypothesis.

## Q11. What new computational representations were discovered

None that reduces work, and the honest content of this
answer is the closures and the exact minima:

- E-graph equality saturation over the two-round round
  function (word level, rules R1 to R6, no unsound
  bitwise-through-ADD rule): the rounds-only case
  converged at round 8 with per-root extraction costs
  identical before and after; the joint case reached its
  class cap with costs identical and extraction at
  baseline. Saturation soundness was verified inductively
  (380,520 enode evaluations, 0 mismatches). No cheaper
  graph exists in that rewrite system: ESTABLISHED
  NEGATIVE for non-sharing cross-round restructuring at
  those bounds.
- Sigma minima proven exactly: over V = {ADD, LUT(any
  imm), ROTR, SHR}, Sigma0 and Sigma1 each need exactly
  4 instructions given the produced word and arbitrary
  independent side values (CEGIS UNSAT at iteration 0;
  4-instruction incumbents z3-proven exact, 200,000
  differentials each, 0 mismatches). Cone-conditioned
  synthesis with the operand pool (s, T1, T2, a, b) and
  s = T1 + T2 enforced returned UNSAT at iteration 0 for
  both cones, excluding the correlation-exploitation
  shape E1: each cone costs 6 instructions, matching the
  incumbents, unless shape E2 (Q10) exists.
- The consumption census proves every produced word is
  bitwise-consumed in the very next round and
  arithmetically consumed 3 rounds later, so no
  bitwise-free window exists: carry-save and redundant
  representation deferral across the round boundary is an
  ESTABLISHED NEGATIVE.
- Header mathematics re-derived: W18 is the first
  nonce-dependent expanded schedule word (W16 and W17 are
  nonce-free; 46 of 48 expanded words are
  nonce-dependent); block-2 state is nonce-free after
  3 rounds, with dependence first appearing in a and e
  after round 4. The delta identities D(W18) =
  sigma0(nonce) and D(W19) = nonce, and round-3 affinity
  of a and e in the nonce, are VERIFIED (100,000 samples
  plus z3 UNSAT with fully symbolic template words).
  W20 delta GF(2)-linearity is REFUTED by a z3
  counterexample, numerically re-verified: there is no
  linear schedule representation past W19.
- The 67 of 192 per-template and 125 per-nonce accounting
  was re-derived and is restated as conventional
  accounting, explicitly NOT a proven lower bound.
- The outer hash admits no precomputation: 48 of 48
  computed schedule words and 64 of 64 rounds are
  digest-dependent, 0 digest-independent rounds, and
  comparison early exit saves no rounds. ESTABLISHED
  NEGATIVE for outer precomputation and for exact
  representation changes of the double hash within every
  representation examined.

No VERIFIED IMPROVEMENT is claimed from EXP-033: nothing
was benchmarked, and a proven identity or minimum is a
mathematical result, not a speedup.

## Q12. What has been implemented and independently verified

Production changes, each followed by an independent
post-integration audit by a different agent than the
author, per the standing rule:

- EXP-036 (Phase F): new production component
  mining/candidate_verify.py. Every candidate is verified
  by two independent SHA-256d implementations required to
  agree, with pow_engine.check_pow's exact integer
  verdict (Core SetCompact semantics) deciding block
  candidacy; no float operations exist in the file. The
  solo server no longer treats a submitblock return of
  None as success: acceptance requires chain confirmation
  (tip or in-chain), and block records carry the verbatim
  submit result, its classification, chain status and the
  verified flag. The float-derived pool target was demoted
  to a share criterion only, with a boundary test pinning
  its blindness at target versus target plus 1. Audit:
  PASS WITH NOTES, zero defects; the auditor's own
  300-header differentials across 12 nBits encodings all
  matched an independent model, and its regtest blocks
  (1070, 1123) recorded chain_status tip. Author-side
  regtest proofs: block 1028 through the fixed solo path,
  block 1029 through the pre-existing solo suite.
- EXP-034 (Phase E): a real defect found and fixed in
  mining/solo_server.py. refresh_job located the
  extranonce split offset in the full coinbase and applied
  it to the stripped coinbase; with a witness commitment
  (effectively every mainnet template) the 2-byte segwit
  marker shifted the offset, corrupting the served
  scriptSig and overwriting the coinbase sequence field.
  It stayed hidden because every existing solo test mines
  an empty mempool. The solo server was never live, so no
  live work was served this way; had the armed cutover
  fired before the fix, it would have served corrupted
  coinbases on effectively every mainnet template (audit
  note N-3). Also in EXP-034: the template cache survived
  11 new adversarial cases with only safe over-keying
  findings; job construction was verified byte-for-byte
  against Core (engine block 1105, solo block 1104,
  coinbase value 39,079,798 sats); a confirmed two-engine
  extranonce collision was fixed with the opt-in
  MiningEngine extranonce_space parameter, default
  (0, 64) byte-identical to historical behaviour. Audit:
  PASS, zero defects; the auditor reproduced the pre-fix
  corruption byte for byte and mined its own regtest block
  1154 on a real Core segwit template through the fixed
  path, chain_status tip.
- EXP-037 (sections 10): the heartbeat share counter
  defect is fixed in production mining/autopilot.py
  (EvidenceCounter: whole-log incremental census with
  persisted offset and head fingerprint; see Q9). The fix
  reaches the live heartbeat at the autopilot's next
  natural restart; nothing was restarted for it.
  mining/mining_statistics.py holds all directive
  section 10 categories plus the EXP-035 accounting
  categories as separated counters with per-worker and
  per-backend breakdowns and no combined total;
  mining/probability.py adopts the previously orphaned
  research formulas into production reach, pinned to
  anchors and cross-checked identical to the research
  originals.
- EXP-038 (section 11): mining/work_checkpoint.py records
  an exact (extranonce, nonce) frontier for the GBT path,
  keyed by the template's EXP-025 layered identity plus
  extranonce space plus curtime basis, written atomically;
  MiningEngine's opt-in checkpoint_path defaults off and
  is behaviour-identical when off; agent/autonomous.py
  enables it in production. Joint audit of EXP-037 and
  EXP-038: PASS WITH NOTES, zero defects (auditor census,
  4,000-record statistics reconciliation, exact-rational
  probability checks, and the 24-configuration restart
  campaign of Q9).
- Research-only deliveries, verified by their own gates
  but deliberately not integrated: EXP-032's AVX2 and
  SHA-NI fallback kernels (Q8) and EXP-035's lease manager
  and candidate queue prototype (Q6, Q9).
- Suite truth at programme close: the Makefile test-all
  target lists 30 prerequisites; the state is 27 of 30.
  The 3 failures are environment failures only: test-rtl
  (iverilog not installed on this VM), test-cpu-correction
  and test-task003 (killed by SIGILL because they compile
  and run the -msha intrinsics library and the current
  Intel host has no SHA extension; both passed on the
  earlier AMD host). Every target exercising changed
  production files passes.

Pre-programme integrations the phases built on (EXP-025
template cache, audited PASS WITH NOTES, zero defects;
EXP-022 flags batch adoption, audited PASS WITH NOTES,
zero defects) were completed under owner decisions before
EXP-030 opened and are inputs to this programme, not
outputs of it.

## Q13. Can NOVA construct and submit a valid block

On regtest: yes, proven end to end through the production
paths, repeatedly, by authors and by independent auditors:
solo blocks 1028, 1029, 1104, 1154 (1154 on a real segwit
template with witness commitment, coinbase sequence field
intact, EXP-036 record fields chain_status tip and
chain_verified true), engine block 1105 with merkle root,
transaction order, coinbase value, payout script and
witness commitment all matching Core's record, plus the
auditor-run suite blocks 1155 to 1157. Construction,
exact verification, submission and chain-confirmed
acceptance all run through the same production code that
will serve mainnet.

On mainnet: not yet, and the distinction is the whole
point. The lab's own solo server is staged behind the
armed cutover, which fires only when the lab's pruned
mainnet node finishes syncing; at the last watcher check
(2026-11-15 06:44 PST) the node stood at 437,564 of
975,969 headers, so the cutover has not fired and the
endpoint configuration remains in pool mode. The live
miner works on public-pool.io, which is solo-style: it
pays only on a full block, and no block has been found.
Balance: 0 BTC. The success criterion (a real mainnet
block, discovered, independently verified, constructed,
submitted and accepted) remains unmet, and nothing in
this report presents regtest acceptance as mainnet
success.

## Q14. What prevents the next major performance increase

Four things, in the order the evidence puts them:

1. The mathematics is fenced in. The full round sits at
   its vocabulary optimum (28 vector ops per steady-state
   round, EXP-020, with production emitting 29 as a
   codegen gap); EXP-027 closed the named
   outside-vocabulary spaces; EXP-033 closed the last open
   sub-space at its stated bounds. The only unfenced shape
   (E2, Q10) is unproven and, even if it exists, is worth
   at most one instruction per cone. No examined exact
   representation reduces total SHA-256d work.
2. This machine delivers about 2 effective CPUs of its
   4 claimed vCPUs under heavy baseline contention
   (EXP-031), with no performance counters to optimise
   against. Per-core gains on the current kernels are
   bounded by the instruction-count models, which the
   production kernels already approach.
3. Scale has no production substrate yet. The coordinator,
   lease manager and candidate queue exist as an audited
   design and a tested prototype (EXP-035), not as running
   services; multi-machine overhead and scaling are
   unmeasured; and fleet activation is the owner's
   decision, deliberately not taken in this programme.
4. The remaining gap is multiplicative, not incremental
   (Q15, Q16): it is closed by fleets of machines running
   verified kernels under exact coordination, or by a
   mathematical result of a kind this programme searched
   for and did not find, not by another few percent on one
   VM.

## Q15. The measured gap to 500 GH/s

500 GH/s is 500,000M H/s. On the live-observation basis
(about 20.6M H/s per system, v512dual, Phase 6B): about
24,000 such systems (500,000 / 20.6 is about 24,272). On
the EXP-032 contended complete-search basis (best session
median 14.8M H/s): about 33,800 such VMs (500,000 / 14.8
is about 33,784). Both figures are arithmetic on measured
single-system rates, labelled theoretical: no fleet of
that size exists, coordination overhead at that scale is
unmeasured, and per-system rates on other hosts will
differ. The gap is stated, not closed.

## Q16. The measured gap to 140 TH/s

140 TH/s is 140,000,000M H/s. On the live-observation
basis (about 20.6M H/s per system): about 6.8 million such
systems (140,000,000 / 20.6 is about 6,796,000). On the
EXP-032 contended basis (14.8M H/s): about 9.5 million
such VMs (140,000,000 / 14.8 is about 9,459,000). Same
labelling as Q15: theoretical arithmetic on measured
rates, with coordination overhead unmeasured. The larger
objective stands at full height alongside the minimum.

## Unverified register (programme level)

- Multi-machine coordination overhead, template and lease
  propagation latency, and linear scaling with worker
  count: UNVERIFIED. Everything in EXP-035 ran in-process
  on this one VM; no numbers exist and none are claimed.
- Fleet behaviour of the roughly 25 agents: UNVERIFIED
  and unattempted; the agents were not activated.
- AVX2 and SHA-NI fallback rates on genuinely AVX2-only or
  SHA-NI-only hosts: UNVERIFIED beyond correctness; the
  ratios in Q8 are this host's.
- The latency series of directive section 10
  (verification, template construction, job distribution,
  submission, worker recovery): unmeasured.
- Solo "in-chain" acceptance is checked at the instant of
  submission; no path re-checks found blocks against later
  reorgs. On regtest this is fully exercised; on mainnet
  it is a record-keeping caveat, disclosed in the EXP-036
  design document.
- The first mainnet template through the fixed solo path
  will arrive only when the armed cutover fires; the
  EXP-034 fix is proven on regtest segwit templates, not
  yet on a live mainnet template.

## Closing statement

EXP-030 set out to learn from the open-source miners,
measure this machine honestly, harden the path that turns
a candidate into a submitted and accepted block, design
the fleet architecture without activating it, and attack
the mathematics at the one point it was still open. All
of that is done and audited. The programme's negative
results are as much its product as its fixes: a solo
coinbase corruption that would have met mainnet was found
and removed before the cutover could fire; the
float-difficulty pattern the Qaxe fork lives by is
forbidden and pinned by test; the heartbeat's headline
share count no longer silently drops shares; restarts on
the GBT path can no longer silently repeat work or claim
unfinished work as done; and the search for a cheaper
exact SHA-256d now has proofs, not opinions, on nearly
every side. The mission itself is unfinished by its own
definition: no mainnet block, 0 BTC, and gaps of roughly
24,000 systems to 500 GH/s and 6.8 million systems to
140 TH/s on the best measured live basis. Those numbers,
and the targets they are measured against, stand
unchanged.
