# EXP-056 independent audit: H-033-02 residual cone closure attempt

Auditor: independent (not the author). Date: 2026-11-17.
Host: AMD EPYC 9D25 (a VM replacement interrupted this
audit itself at about 13:28 UTC; host before and after
AMD EPYC 9D25; scratch work was rebuilt, no audit result
affected). Stated remote HEAD: 413608dd4b60ef55d473598258000fde7cc842e2
(confirmed live: the remote tree fetch returned exactly
that HEAD, 1,296 entries). Predeclaration sha256 verified
on disk: 95b39893c5e13fa7559c33dc3696ce05b6e17baadbd5c603f22b4165259b50a6,
pinned in exp056_cone_synth.py (the campaign driver and
the test suite pin it transitively through that module).
Solver: z3 5.4.1 in the lab venv, confirmed.

## Verdict: PASS WITH NOTES, 2 defects

The campaign record is accurate in every verdict,
tally and classification I could recompute or re-run:
the space attacked is exactly the EXP-042 residue, the
canonicalisation excludes nothing (constructively
verified), both UNSAT queries I re-ran reproduce, the
checkpoint accounting recomputes to the second, and
INCONCLUSIVE at the predeclared budget is the
portfolio's own failure criterion, applied without
stretch. The two defects are in the control fixture
and in one rationale sentence: the planted program as
implemented is not the planted program as predeclared
(D-1), and the Stage C non-launch rationale misstates
the driver's slack arithmetic (D-2). Neither touches
any UNSAT verdict or the classification.

## 1. Space exactness and canonicalisation (C1 to C5)

The space definition rests on records I re-read:
H-033-02 (EXP-033 hypothesis registry: a 5-instruction
cone over V = {ADD, LUT(any imm), ROTR(any k), SHR(any
k)}, k in 1..31), H-033-05's EXP-042 update (bounds:
sum by a single ADD of the sum inputs, Boolean output
by a single LUT; out-of-bounds shapes are sum or
Boolean output produced by two or more instructions),
and EXP-042_REPORT.md lines 222 to 234 (the same
residue statement). The EXP-056 encoding matches it
exactly: L = 5 fixed, ops 0..3 are the EXP-033 op
codes with the EXP-033 semantics imported unchanged,
amounts constrained to 1..31, LUT immediate a full
8-bit value, selectors ranging over inputs and prior
instructions only (straight-line), output selectors
free over all 5 instruction values with no
decomposition constraint. Nothing EXP-033 or EXP-042
closed is reopened as a separate question, and
nothing in the declared residue is excluded by
construction: outputs may be any instructions, so sum
by 2+ instructions, Boolean by 2+ instructions, and
mixtures are all inside the Stage A query.

Canonicalisation, attacked constructively with my own
code (not the author's): I implemented the
predeclaration's representative construction
independently (delete semantically dead instructions,
pad to length 5 with LUT 0xF0 copy chains, route one
output through the chain, apply C1 and C2) and ran it
on 84 admissible random programs (lengths 1 to 5, all
op kinds, dead instructions and unordered ADDs
included; admissibility = distinct output selectors
whose values are pairwise distinguishable, the C3
precondition). Result: 84 of 84 representatives were
functionally equivalent to the original (0 failures)
and satisfied C1, C2, C3 and C4 syntactically (0
failures). Targeted probes: fixing an ADD's unread
slot 2 to the canonical 0 preserved values on 20,000
inputs (0 bad), which is the C1/C4 interaction case
(an instruction referenced only through an unread
slot is semantically dead and is removed by the
construction, not silently dropped from the space).
C3's soundness condition holds on the actual seed for
both cones (targets pairwise distinguished, verified
with the driver's own predicate on the predeclared
seed of 16). C5: all_profiles() returns exactly 56
unique profiles, each summing to 5, in the predeclared
order (ADD, then LUT, then ROTR, then SHR, all
descending); the first 12 match the report's Stage B
table entry for entry. I could not construct a program
that C1 to C5 excludes without an equivalent retained
representative.

## 2. Control validity, and defect D-1

The recorded control: synthesis returned SAT at
284.5 s; the found program was proven equivalent to
the planted target (z3 negation UNSAT) and matched on
200,000 differentials. I re-verified the equivalence
independently: my own 200,000 fresh-seed differentials
of the found program against the planted target gave
0 bad, and my own z3 verify_two_programs call on the
found program versus the planted program returned
UNSAT (equivalent). The found program satisfies C1 to
C4 syntactically. The gates' incumbent differentials
are confirmed from the recorded JSONs (1,000,000 per
cone, 0 bad, z3 UNSAT both cones) and by my fresh
250,000-per-cone subsets (0 bad each).

### Defect D-1: the planted program as implemented is not the planted program as predeclared

The predeclaration defines P5 with i4: ADD(i3, i1),
i.e. selector tuple (7, 5), and describes P5 as having
all instructions used and all four op kinds present.
The shipped P5_PROGRAM in exp056_cone_synth.py has i4
with selectors (6, 5), i.e. ADD(i2, i1). Proven, not a
reading difference: z3 negation between the two
programs is SAT in both directions (they are not
equivalent), and concrete differentials differ on
50,000 of 50,000 sampled inputs. Consequences in the
implemented plant: instruction i3 (the only SHR) is
never read and is not an output (perturbing it changed
0 of 20,000 outputs), so the implemented plant's
function is computable by 4 instructions (ROTR, ADD,
LUT, ADD), and the control demonstrated the encoding's
SAT-capability against that easier target, not against
a target that genuinely requires 5 instructions as
predeclared. The report (section 2) and the JSON
registry entry describe the plant as "the predeclared
planted 5-instruction program P5", which is inaccurate
in this detail.

Impact, stated precisely: no UNSAT verdict and not
the INCONCLUSIVE classification depends on the control.
UNSAT soundness rests on C1 to C5 containing a
representative of every length-5 program, which
section 1 verifies independently; the control is a
SAT-side sanity check, and as executed it still
demonstrates that the canonicalised encoding can find
and exactly verify a length-5 all-used program (the
found program is genuinely 5 instructions, all used).
The defect is a predeclaration-to-implementation
deviation in a fixture, verdict-irrelevant, but the
record must be corrected before push (report and
registry wording: the plant as implemented, with the
operand difference and the dead instruction stated),
and if the campaign is ever resumed under a future
predeclaration the control should be re-run against
the corrected plant.

## 3. UNSAT re-runs and checkpoint integrity

I re-ran two Stage B a-cone queries myself from the
shipped driver code and the predeclared seed, at the
campaign's 240 s cap, one at a time:

- Profile 0, (5,0,0,0), the no-LUT profile: UNSAT
  reproduced (my wall 4.9 s; campaign 35.7 s under
  heavier contention; verdicts are the content,
  timings are condition-dependent).
- Profile 1, (4,1,0,0), the one-LUT 4-ADD profile:
  UNSAT reproduced (my wall 33.6 s; campaign 209.9 s).

Checkpoint and resume logic, verified two ways. Code:
verdicts are written only after a query returns
(account, then the per-query record, then save), and
Stage B skips any profile key already in the
checkpoint. Functional test with a fake synth_query
against a temporary checkpoint (the real checkpoint
untouched): with profiles 0 and 1 pre-recorded, the
driver queried profiles 2 to 55 exactly once each and
never repeated 0 or 1; with the fake raising mid-query
(the process-kill shape), no verdict and no solver wall
were recorded for the interrupted query. The campaign
record corroborates the VM-replacement disclosure:
stageA_a.log is 0 bytes with mtime 11:20 UTC (the
killed first attempt, after the control closed at
11:13:59), the checkpoint log contains exactly one
Stage A a-cone entry (the completed 1,502.7 s rerun,
logged 11:53:10), and no partial verdict exists
anywhere in RAW_RESULTS.

## 4. Accounting and the open register

Recomputed from the checkpoint log (30 entries, sum
of per-query wall): gates 4.6 s (2.1 + 2.5), control
284.5 s (synthesis 284.5, verify 0.0), Stage A
3,008.8 s (a-cone 1,502.7, e-cone 1,506.1), Stage B
a-cone 1,669.9 s over 12 profiles, Stage B e-cone
1,551.5 s over 12 profiles. Total 6,519.3 s, equal to
the checkpoint's solver_wall_s to the recorded
precision, of the 6,600 s box (98.8 percent). Campaign
wall: checkpoint opened 2026-11-17T11:06:50Z, last
query closed 13:16:50Z, about 7,800 s, inside the
12,600 s cap. Per-cone Stage B verdicts in the
checkpoint, the stage JSONs and the proofs summary
agree exactly: UNSAT at profiles 0, 1, 2, 3, 7, 8, 9
(the 7 claimed: (5,0,0,0), (4,1,0,0), (4,0,1,0),
(4,0,0,1), (3,0,2,0), (3,0,1,1), (3,0,0,2)), unknown
at 4, 5, 6, 10, 11, 12 profiles queried, none closed,
no SAT candidate. The open register as stated in the
report is exact: 5 queried-unknown profiles per cone,
44 never-queried profiles per cone (indices 12 to 55),
the full-space question above 1,500 s per query open,
Stage C never run.

### Defect D-2: the Stage C non-launch rationale misstates the driver arithmetic

Report section 4 states Stage C was not run because
80.7 s of the box remained, "below the 120 s minimum
the campaign driver requires to launch a Stage C
query". The 80.7 s is the strict remainder
(6,600 - 6,519.3). The shipped do_stageC computes its
cap from the box plus the 60 s slack
(6,600 + 60 - 6,519.3 = 140.7 s), and its launch
minimum applies to that cap: 140.7 is not below 120,
so invoking stageC would have launched an encoding-B
query at a 140.7 s cap rather than refusing. The
non-launch itself is disclosed, Stage C is honestly
recorded as never run and carried in the open
register, and a 140 s query could not have changed
the classification (Stage A needed more than 1,500 s
to return unknown); but the rationale sentence is
wrong about the code and should be corrected before
push.

## 5. Classification mapping

Predeclaration branch 3 (anything else): INCONCLUSIVE
with the budget stated, H-033-02 stays UNPROVEN
BREAKTHROUGH narrowed by the exhausted subspaces,
registry status UNDER_INVESTIGATION. Portfolio
NOVA-ER-0016 failure criterion, verbatim in substance:
another timeout at the predeclared budget, recorded
as inconclusive with the budget stated, and the item
stays UNDER_INVESTIGATION. The report and registries
apply exactly this: verdict INCONCLUSIVE, budget
stated (6,600 s box, 6,519.3 s consumed), H-033-02
status unchanged at UNPROVEN BREAKTHROUGH with a dated
exp056 update note appended to its EXP-033 registry
entry (statement and status fields untouched, verified
in the JSON), EXP-056 registry status
UNDER_INVESTIGATION. No stretch found. Neither closing
branch was available: no cone closed and no candidate
was produced, and the report claims neither.

## 6. Safety and shape

Blob-level diff of the whole local tree against
413608dd (1,296 remote entries): changed files are
exactly Makefile, the JSON registry, the two markdown
registries and the EXP-033 hypothesis registry (the
dated H-033-02 note); new files are exactly the
exp056 set and tests/test_exp056_cones.py; remote-only
files: none. The only other local-only file is
bal-miner, a standing sanctioned exclusion. No
production file differs. Endpoint config
(.local/mining-endpoint.json) mtime still 2026-11-14.
Registries: JSON 108 entries, EXP-056
UNDER_INVESTIGATION, last entries EXP-057, EXP-058,
EXP-056; the two markdown EXP-056 appends are
byte-identical (9,349 characters), closing with next
unreserved ID EXP-059 and EXP-052 noted as the
standing reservation. Makefile test-all lists 49
targets including test-exp056 (which invokes the lab
venv python, as the report's judgment call 4 states).
U+2014 count over the exp056 set, test file, Makefile
and registries: 0. Secret-pattern scan over the same
set: 0 hits.

## 7. Suites (run one at a time)

- make test-exp056: 16 checks, ALL PASSED.
- make test-exp055: 23 checks, ALL PASSED (its Gate 6
  produced regtest block 2388, continuing the author's
  recorded 2387).

## Notes

- N-1: The accounted box counts completed queries
  only. Two disclosed exclusions sit outside the
  6,519.3 s: the killed Stage A attempt (about 380 s,
  no verdict; budget section and judgment call 3) and
  a pre-campaign build-time smoke test (30.7 s,
  planted target only, no cone target; judgment call
  2). Total z3 wall attributable to the experiment is
  therefore about 6,930 s against the predeclaration's
  "every z3 query" wording. Both exclusions are
  explicit in the record, neither produced a verdict,
  and the accounted campaign alone reached 98.8
  percent of the box, so the INCONCLUSIVE branch is
  unaffected; a future predeclaration should state the
  completed-queries rule expressly.
- N-2: The inter-cone Stage B split (a-cone stopped
  by the operator after 12 profiles so the e-cone
  received the same depth) is an operator decision the
  predeclaration did not fix; it is disclosed as
  judgment call 1, and the a-cone end-of-stage file is
  flagged inside itself as materialised from the
  checkpoint (verified: the flag is present and its
  contents equal the checkpoint records).
- N-3: The control's found program uses three op
  kinds (ROTR, ADD, LUT; no SHR). The predeclaration's
  "all four op kinds present" describes the plant, not
  the found program, so this alone is no deviation;
  with D-1, the plant's effective kind coverage is
  also three, not four.
- N-4: C4 as encoded counts reads through any
  selector slot, including slots an op does not
  semantically use, so the encoded space is a superset
  of the truly all-used space. That is the sound
  direction for an UNSAT claim and is the direction
  the predeclaration argues; my battery confirms the
  padding construction lands inside the encoded space.

## UNVERIFIED register (auditor's own)

- The remaining 12 UNSAT profile verdicts (7 closed
  profiles per cone = 14, of which I re-ran 2, both
  a-cone): UNVERIFIED by re-run; they rest on the
  campaign record, the verified encoding, and the
  verified checkpoint machinery.
- Stage A full-space unknowns: not re-run (1,500 s
  each); nothing about them is independently verified
  beyond the instrument and record checks above.
- The killed attempt's about-380 s wall: corroborated
  in shape (0-byte log, timestamps) but not measurable
  exactly; UNVERIFIED as a number.
- The corrected-plant control (D-1): not run; the
  encoding's SAT-capability against a genuinely
  5-instruction plant remains UNVERIFIED at the
  predeclared strength.
- Everything the author lists as open stays open:
  the 5 unknown and 44 unqueried profiles per cone,
  the full-space question above 1,500 s per query,
  encoding B, vocabularies larger than V, lengths
  below 5 in the residual generality, other hosts.
- Live deployment or production consequence: none
  exists and none was attempted; no production code
  was modified by the experiment or by this audit.

## Bottom line

The predeclared claims survive adversarial checking:
the attacked space is exactly the EXP-042 residue,
the canonicalisation provably excludes nothing, the
UNSAT verdicts I re-ran reproduce, the accounting
recomputes exactly, and the classification is the
portfolio's own failure criterion applied as written.
PASS WITH NOTES, 2 defects (D-1 control plant deviates
from the predeclaration, its function 4-instruction
computable, record wording inaccurate; D-2 Stage C
rationale misstates the driver's slack arithmetic).
Both are documentation-and-fixture level and
verdict-irrelevant; both should be corrected in the
record before push, as with EXP-057 and EXP-058.
