# Stage 9 Final Audit: NOVA SHA-X Stage 9 Programme

Auditor: independent final auditor (built no stage of this
programme). Date: 2026-11-18.
Subject: the whole of Stage 9 (stages 9.1 to 9.6), all
deliverables under research/STAGE9/, and the production
source they describe.
Baseline: remote HEAD
c44e06f2a462f63f9f59b85d17c3412c29d3ae9a, as established by
the Stage 9.6 push verification (scoped verify plus an
independent full-tree comparison, both clean; final-HEAD
CI run 44258088765 success). See note N-1 on how remote
HEAD is established from this host.
Method: deliverable inventory against the owner
directive; the auditor's own recomputation of block
hashes, difficulty, waiting time and systems-to-target
figures from the raw evidence; sha256 re-taken on the key
production files; independent recounts of the closure
ledger and the promotion table; spot checks that every
correction recorded by a stage audit is present in the
files; and a read-only observation of the live stack.
Nothing was modified except this file. Nothing was
pushed. The live stack was not touched beyond reading
its heartbeat and configuration hashes.

## Verdict: PASS WITH NOTES

No defect was found by this final audit. Every defect
found by the six stage audits was minor and
documentation-grade, and every correction those audits
specified is verified present in the files (section 3).
The material claims of every stage were reproduced by
the stage auditors and, for the samples listed in
section 2, again by this auditor from primary inputs.
The notes in section 7 are verification-scope
limitations and immaterial record wrinkles, not defects
in the work.

## 1. Deliverable completeness: COMPLETE

The owner directive's deliverable list, checked against
the tree at audit time:

| Deliverable | Stage | Present |
| --- | --- | --- |
| REPOSITORY_BASELINE.md | 9.1 | yes |
| EXPERIMENT_CLOSURE_LEDGER.json | 9.1 | yes |
| EXPERIMENT_CLOSURE_REPORT.md | 9.1 | yes |
| PRODUCTION_PROMOTION_DECISIONS.md | 9.2 | yes |
| CURRENT_HEAD_TEST_AUDIT.md | 9.3 | yes |
| AUTONOMOUS_AGENT_GAP_ANALYSIS.md | 9.4 | yes |
| REGTEST_AUTONOMOUS_DISCOVERY_REPORT.md | 9.5 | yes |
| MAINNET_READINESS_REPORT.md | 9.6 | yes |
| PERFORMANCE_GAP_REPORT.md | 9.6 | yes |
| STAGE9_FINAL_AUDIT.md | 9.7 | this file |

Per-stage independent audit records, all present in
research/STAGE9/:

| Audit file | Stage | Verdict recorded |
| --- | --- | --- |
| STAGE9_1_AUDIT.md | 9.1 | PASS WITH NOTES (2 minor defects) |
| STAGE9_2_AUDIT.md | 9.2 | PASS WITH NOTES (2 minor defects) |
| STAGE9_3_AUDIT.md | 9.3 | PASS WITH NOTES (no defect in the fix or the evidence) |
| STAGE9_4_AUDIT.md | 9.4 | PASS WITH NOTES (1 minor defect, D-94-1) |
| STAGE9_5_AUDIT.md | 9.5 | PASS (1 note, N-1) |
| STAGE9_6_AUDIT.md | 9.6 | PASS WITH NOTES (no defects) |

Supporting files also present: the ledger schema
(EXPERIMENT_CLOSURE_LEDGER.schema.json), the ledger
validator (validate_ledger.py), and the evidence bundles
evidence_93/, evidence_94/, evidence_95/ and
evidence_96/. No deliverable is missing.

## 2. Independent reproductions by this auditor

### (a) Stage 9.5 regtest block hashes: MATCH

From the raw header hex in evidence_95/, using hashlib
double SHA-256 only (no lab code), for heights 1, 5
and 8:

- Height 1: recomputed
  510b366a89bf00381e269be0867f99396279cf762081f0a61e511cfd939e7f7a,
  equal to block_1.json; header nonce 40961, equal to
  the recorded nonce; hash at or below the regtest
  target (0x7fffff x 2^232).
- Height 5: recomputed
  0f2df5db3536e0e54fdaaea37fa53abcdfe2e58ca89f7eba2f5cbebed7b2e6bc,
  equal to block_5.json; nonce 65536 matches.
- Height 8: recomputed
  355befc49de42316047b51037ab536ea3451819eff2dc91976ef06b78b65754f,
  equal to block_8.json; nonce 4 matches.
- getblockchaininfo_after.json: chain regtest, blocks 8,
  bestblockhash equal to the height-8 hash. The
  acceptance claim (8 blocks in the best chain) stands
  on the evidence as recorded.

### (b) Stage 9.6 headline arithmetic: MATCH

- The auditor ran evidence_96/compute_gap.py: its
  output equals gap_computation.json field for field.
- Independent recomputation from primary inputs
  (nbits 0x17021673; 85,259,089,184 hashes over
  3,992 s): difficulty 134,823,837,323,272.66; sustained
  rate 21,357,487.27 H/s; expected hashes per block
  5.7906e23; expected waiting time 859,156,780 years
  (labelled a statistical estimate in both reports);
  systems to 500 GH/s 23,410.99 (reported as about
  23,411); systems to 140 TH/s 6,555,078.24 (reported
  as about 6,555,078). Every figure matches the
  reports.

### (c) Production file sha256: MATCH

Re-taken by this auditor and compared with the values
the stage reports claim:

| File | sha256 at final audit | Claimed value |
| --- | --- | --- |
| mining/engine.py | 866936fd6d41ebcc3a5ecbde886b0a5aa27ee6ad5483025ddf0b3f1635f1ec | post-9.4 value, matches |
| mining/mainnet_live.py | c8071ce1286c2bc3350afb05a624fd6fd2b16cb1f17808a86cbe922072e3218c | baseline section 7, matches |
| mining/autopilot.py | 3cfafc209f4c4e8a965fe6247c05529df45efcf10687fcdeef7a147e3c1ac60a | baseline section 7, matches |
| mining/bakeoff_dispatch.py | fc211512d3097781413e2bfb7b11210664eb347335573c1c6f59ba7656993c10 | baseline section 7, matches |
| mining/coordinator.py | b4215980cac03f0e11a772887cc08a6db37ca46df8032e481175940bae032eff | baseline section 7, matches |
| gpu/engine.py | bfe605cbb155b59f6b9857e7643348a0a6504160197a663c86d5859911365d46 | baseline section 7, matches |

The engine.py value chain is fully accounted for: the
9.1 baseline recorded ec5f5687453c94d842cd274c054d13aa
723296f46f05edfbc02b2b53f8331a5f; Stage 9.3's BIP34 fix
changed it to 7017cea3732959198895349366c227eb357e281c
62bd6b067e12a8dd2a32133b (verified by the 9.3 auditor);
Stage 9.4's StatusPublisher addition changed it to the
current value above (verified by the 9.4 auditor and
again here). No other audited production file changed
across the programme.

### (d) Counts: MATCH

- Closure ledger: 109 records, 109 unique ids, computed
  disposition counts INTEGRATED 30,
  PROVEN_NOT_INTEGRATED 44, REJECTED 15, EXPERIMENTAL
  8, UNDER_INVESTIGATION 4, DEFERRED 7, INCONCLUSIVE 1,
  summing to 109 and equal to the ledger's own
  disposition_counts field.
- Promotion table (PRODUCTION_PROMOTION_DECISIONS.md
  section 4): this auditor recounted all 109 rows (111
  pipe lines including header and separator; every
  ledger id appears exactly once). Classes: ADD TO
  PRODUCTION 28, KEEP AS RESEARCH 41, KEEP DISABLED /
  EXPERIMENTAL 18, DO NOT ADD 15, DEFER 7. Sum 109.
  Matches the Stage 9.2 record exactly.

## 3. Cross-stage consistency and corrections

No stage contradicts an earlier audited stage without a
dated correction. Every correction specified by a stage
audit was spot-checked in place by this auditor:

- 9.1 (ledger records EXP-050 and EXP-051): the records
  now carry affects_production_path true and a basis
  that describes the conditional default-off wiring
  (EXP-050's EndpointHealthPolicy behind a default-off
  flag; EXP-051's prefetch imported unconditionally and
  wired behind use_prefetch=False), and
  EXPERIMENT_CLOSURE_REPORT.md section 6 is the dated
  "Corrections (2026-11-18, per STAGE9_1_AUDIT.md)"
  record. Present as specified; no disposition or count
  changed.
- 9.2 (tracing narrative): PRODUCTION_PROMOTION_DECISIONS.md
  now names mining/cpu/miner.py (line 133) as the third
  MiningEngine constructor and states that only the
  agent path is live-relevant, and both section 1 and
  the EXP-034 row now say three helpers
  (address_script_pubkey, build_coinbase, strip_witness)
  at two deferred import sites. A dated "Corrections
  (2026-11-18)" section closes the file. Present as
  specified.
- 9.3 (CI subset): CURRENT_HEAD_TEST_AUDIT.md carries a
  dated "Corrections (2026-11-18)" section recording
  that the first CI run failed (run 44245744149), the
  root cause (test-exp051 Gate 6 needs bitcoind; the
  cleanroom missed the host dependency class, also
  present in exp053, exp054 and exp058), and the
  reduction of the clean-runner subset. The workflow
  file at final audit runs exactly the 4 suites
  (test-exp037, test-exp038, test-probability,
  test-exp049), as the 9.4 and 9.6 audits independently
  confirmed by reading it. The 9.3 audit's description
  of an 8-suite workflow was true at its audit time and
  the change is documented, not silent.
- 9.4 (D-94-1): AUTONOMOUS_AGENT_GAP_ANALYSIS.md
  carries a dated "Corrections (2026-11-18)" section,
  and the C1 and C2 enumerations now include
  tests/test_agent_controller_modes.py and
  research/EXTREME_RESEARCH/stage8_demonstration.py.
  Present as specified; no verdict changed.

## 4. The programme's final position, stated plainly

- Research closure is achieved for the 109-record
  register: every record carries exactly one
  disposition, verified against both registries and
  against current source.
- Production promotion is decided for every record:
  28 ADD TO PRODUCTION, 41 KEEP AS RESEARCH, 18 KEEP
  DISABLED / EXPERIMENTAL, 15 DO NOT ADD, 7 DEFER. The
  central tracing finding stands: the live pool miner
  (mining/mainnet_live.py) never imports
  mining/engine.py, so a family of INTEGRATED records
  is live on the GBT and agent path only.
- Current-HEAD correctness is established: the full
  suite stands at 48 PASS / 3 FAIL, the three failures
  classified as non-code (test-rtl: iverilog absent,
  environment; test-exp052: Gate 5a host-fingerprint
  fail-closed, environment; test-task0039: early-exit
  promptness bound under contention, exact accounting
  intact). The one genuine code defect found by the
  programme (BIP34 coinbase height encoding) was fixed
  in Stage 9.3 and re-proved against Core in Stage
  9.5. CI runs the 4-suite clean-runner subset and is
  green at the final HEAD.
- Autonomous regtest discovery is demonstrated: in
  Stage 9.5 the agent selected its backend itself,
  fetched fresh templates, searched, submitted and
  confirmed 8 consecutive blocks into an isolated
  regtest best chain, with one disclosed verification
  shim in the submission path.
- Autonomous mainnet operation is NOT demonstrated and
  is NOT claimed anywhere in the programme. The Stage
  9.4 classifications stand: C1 agent-assisted, C2
  agent-assisted, C3 agent-controlled inside the
  package when driven and inactive in live production,
  C4 agent-controlled at protocol level on one host,
  deployed nowhere.
- The success criterion (a real, independently
  verified, submitted, accepted mainnet block) is NOT
  met. Live evidence at Stage 9.6, kept in three
  separate categories: 1,082 pool-accepted shares at
  audit time (1,085 at this auditor's read-only check),
  zero network-target candidates ever, zero accepted
  mainnet blocks, balance 0 BTC. Shares are not blocks
  and not earnings, and no report in the programme
  presents them as such.
- Neither performance target is met, and neither was
  lowered: at the measured sustained rate of
  21,357,487 H/s, reaching 500 GH/s takes about 23,411
  systems of this class and 140 TH/s about 6,555,078;
  the expected waiting time for one block at the live
  rate is about 859,156,780 years, a statistical
  estimate. No CPU-software path measured or credibly
  projected in this programme reaches 500 GH/s on one
  system of this class.
- The live stack is still mining on public-pool.io.
  The solo cutover is armed and correctly waiting: the
  node is still in initial block download (Stage 9.6
  recorded 471,150 of 976,395 headers), the cutover
  marker file does not exist, and the endpoint config
  is unchanged in pool mode (sha256
  d741cde3c6224406f46f3bae138fb174eb1d780725bcb94baff4e14a8670c7d3,
  re-verified by this auditor).

## 5. Open register, carried at the weight the stages give it

Owner decisions outstanding (none is a defect in the
work; each is recorded here exactly as the stages left
it):

1. Fleet activation for mining (EXP-035 / EXP-055
   deployment). Not done; must not be done without the
   owner's word. All coordination proof is one-host.
2. EXP-052 live enablement of the bake-off dispatch
   switch. The campaign verdict is STATIC by dominance
   (PROMISING HYPOTHESIS); the Intel rotation, the
   second AMD rotation and the measured-winner gate
   remain outstanding.
3. EXP-057 stratum aggregation deployment, and EXP-058
   PID controller live actuation. Both proven only at
   the level the stages record; deployment is gated.
4. EXP-050 endpoint health and EXP-051 prefetch live
   enablement (both wired, default-off, never run
   live; EXP-050 enablement needs a real second
   endpoint).
5. DEF-9.2-1 (unguarded host_fingerprint() call at the
   bakeoff resolver seam, mining/bakeoff_dispatch.py
   lines 566 to 567) and DEF-9.2-2 (unconditional
   prefetch import, mining/engine.py line 26): minor
   hardening items, documented and unfixed by owner
   decision; DEF-9.2-1 must be fixed before any
   bakeoff enablement.
6. Registry repair application from Stage 9.2 (R-23,
   R-27, R-32, R-33, R-35 status updates, the D-02,
   D-03, D-04 and D-06 text fixes, and the proposed
   enablement annotation field): prepared, not applied.
7. D-93-2 (test-task0039 early-exit bound: quiet-host
   run or a thread bound; the bound must not be
   silently loosened) and D-93-3 (test-exp052 Gate 5a
   host-keyed design: accepting the proven doubt
   fallback as a pass would be a test-design change).
8. EXP-047 search semantics: accept
   first-publisher-wins as documented production
   semantics, or fund a minimum reduction in the search
   context.
9. In-loop GBT candidate verification (Stage 9.5 gap
   1): the agent path relies on Core's submitblock
   verdict by design; whether the production verifier
   moves inside the cycle is an owner decision.
10. test-status-publisher admission to the CI subset:
    plausible per the 9.4 audit recommendation, but it
    needs its own cleanroom run first because it
    transitively imports gpu.engine.
11. The keeper rule's application during initial block
    download. The rule itself was decided by the owner
    on 2026-11-17 (keep restart on RPC silence).
    Restarts under that rule have been held since
    21:06 PST that day, because the literal rule loops
    during sync (each restart went RPC-silent again
    within about 15 to 17 minutes). Whether to
    reinstate the literal rule or let the held position
    stand is the owner's open decision. This audit does
    not reclassify it.
12. Host-gated checks that no stage could run on the
    hosts provided: the EXP-039 Intel-host refusal
    check and the EXP-052 Intel rotation (item 2),
    awaiting a rotation to the Intel Xeon 8321HC host
    class.

Recorded as not run, and not a defect: the paired
EXP-017 AVX2 re-measure proposed for the D-05 /
DEF-9.2-5 discrepancy (EXP-032 pooled 1.409x vs
EXP-039 pooled 1.252x on byte-identical kernels) is an
owner-directed item only. It was not directed, so it
was not run, and the discrepancy remains open exactly
as Stages 9.1, 9.2 and 9.6 record it.

## 6. Defects found by this final audit

None.

## 7. Notes (verification scope and immaterial items)

- N-1 (verification scope): the local checkout has no
  .git, so the remote HEAD value c44e06f2... is
  established by the Stage 9.6 push verification record
  (scoped verify plus independent full-tree comparison,
  both clean) and by the file-hash substitution this
  audit re-performed in section 2(c). This is the
  method every stage used, and it held at every stage.
  The HEAD string itself is UNVERIFIED by direct local
  git inspection, because that inspection is impossible
  from this host.
- N-2 (verification scope): CI conclusions (including
  final-HEAD run 44258088765, success) are carried from
  the stages' push records. The workflow file itself
  was read directly by the 9.4 and 9.6 auditors and by
  this auditor; the run conclusions were not
  independently re-queried from GitHub by this audit.
- N-3 (evidence, from the 9.3 audit's NOTE-3): the
  test-task0039 isolated re-run log was lost in a /tmp
  wipe during a service restart. Its result rests on
  the contemporaneous progress log; the first-pass
  failure is independently anchored, and the 9.3
  auditor's source-level verdict does not depend on
  the lost file. Carried forward unchanged.
- N-4 (immaterial): the Stage 9.5 audit header counts
  36 evidence files in evidence_95/; the disk
  enumeration at push time and at this audit is 37
  files. Every material evidence file (all 8 block and
  header files, both run records, the decision log,
  the submit responses, the verification record) was
  recomputed or read in full by the 9.5 auditor, and
  the push verified all 37 blob hashes. The off-by-one
  is in a parenthetical count only.
- N-5 (live counters move): between Stage 9.6's build
  and this audit the share counter rose 1,082 to 1,085
  and the node continued advancing, all in the
  expected direction for a live stack. At this
  auditor's read-only check: autopilot pid 2830, miner
  pid 2833, miner state running, restarts 0.
- N-6 (hygiene): a byte scan for the U+2014 character
  over the entire research/STAGE9/ tree (reports,
  audits, ledger, evidence) returns zero files. This
  audit file was written without the character.

## Bottom line

Stage 9 closes as audited. The register is closed, the
promotion decisions are taken, current-HEAD correctness
is established with three classified non-code failures,
autonomous regtest discovery is demonstrated, and the
mainnet position is stated without inflation: the stack
is correct, tested, supervised and mining valid work on
public-pool.io, and the success criterion is unmet at a
measured rate roughly 23,411 systems short of the
minimum objective. Everything still open is an owner
decision, a host-gated check, or a statistical wait,
and each is carried in section 5 at exactly the weight
the stages gave it.
