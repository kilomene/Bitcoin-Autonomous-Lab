# Stage 9.6: Performance Gap Report

Stage: NOVA SHA-X Stage 9.6. Basis: remote HEAD
5b4b27a1fb5f09172748be6cdcb34e1dd7dcda11; live
measurements taken 2026-11-18T07:06:35Z to 07:11:23Z on
the live stack (host: AMD EPYC 9D25, the current VM
instance). Raw evidence: research/STAGE9/evidence_96/
(live_observation.json, gap_computation.json,
compute_gap.py). Prior findings cited from the Stage 9.1
closure ledger, the Stage 9.2 promotion decisions
(PRODUCTION_PROMOTION_DECISIONS.md) and the Stage 9.3
audit (CURRENT_HEAD_TEST_AUDIT.md); nothing here
contradicts them.

Result in one line: the live stack sustains about
21.36 MH/s. The standing targets are 500 GH/s (minimum
objective) and 140 TH/s (larger objective); neither may be
lowered, and neither is met. The gap to 500 GH/s is a
factor of about 23,411: it would take about 23,411 systems
of this exact class, running this exact stack, to reach
the minimum objective by replication, and about 6,555,078
for 140 TH/s. No CPU-software path measured or credibly
projected in this programme reaches 500 GH/s on one system
of this class.

## 1. The measured live rate

Method: read the live miner's own status line
(.local/mainnet-status.txt, written by the running miner,
pid 2833, backend v512dual) four times over about
4.5 minutes. The status line reports cumulative hashes and
elapsed seconds for the current run, so each sample gives
a whole-run cumulative average, not an instantaneous
reading:

| Sample (UTC) | Elapsed (s) | Cumulative hashes | Miner-printed rate (H/s) | Cumulative average (H/s) |
| --- | --- | --- | --- | --- |
| 07:06:38Z | 3,753 | 79,458,423,584 | 21,172,085 | 21,171,975 |
| 07:08:01Z | 3,813 | 80,810,681,216 | 21,192,894 | 21,193,465 |
| 07:09:32Z | 3,933 | 83,713,139,584 | 21,285,572 | 21,284,805 |
| 07:11:02Z | 3,992 | 85,259,089,184 | 21,355,505 | 21,357,487 |

Primary figure used throughout: 21,357,487 H/s (about
21.36 MH/s), the cumulative average at the final sample.
It is conservative in a specific, disclosed way: it
includes this run's slower start after the 06:03Z VM
replacement. The interval rate over the sampling window
alone was 24,270,567 H/s ((85,259,089,184 minus
79,458,423,584) / 239 s). Using the interval figure
instead would shrink every gap below by about 12 percent
and change no conclusion; the whole-run average is the
figure a second observer re-reading the same status line
would reproduce. Conditions: the measurement was taken on
the live host under live load (syncing mainnet node,
autopilot, load average about 10 on the 5 minute figure at
first observation). That is deliberate: this report prices
the stack as it actually runs, not a benchmark in
isolation. No new benchmark was run for this stage; the
programme's benchmark record is cited in section 3.

## 2. The gap, computed

Targets (standing, owner-set, unlowered): 500 GH/s
minimum objective; 140 TH/s larger objective. Arithmetic
reproducible in evidence_96/compute_gap.py; output in
gap_computation.json.

- Ratio to 500 GH/s: 500,000,000,000 / 21,357,487
  = about 23,411. The live stack delivers about
  0.0043 percent of the minimum objective.
- Systems to 500 GH/s: about 23,411 systems of this class
  (23,410.99 at the figures above).
- Ratio to 140 TH/s: 140,000,000,000,000 / 21,357,487
  = about 6,555,078.
- Systems to 140 TH/s: about 6,555,078 systems of this
  class (6,555,078.24 at the figures above).
- Expected mainnet waiting time at the live rate and the
  current network difficulty (134,823,837,323,272.66,
  observed live; see MAINNET_READINESS_REPORT.md):
  about 5.7906e23 expected hashes per block, an expected
  wait of about 859,156,780 years. STATISTICAL ESTIMATE,
  expected value at constant difficulty and rate.

"Systems of this class" means a full replica: a VM of this
size (4 vCPUs visible, about 2 effective, section 3)
running this stack at this sustained rate. Replication is
the only scaling path the programme has actually measured
end to end, and even it is only proven on one host: the
coordination layer that would run 23,411 replicas as one
fleet is proven at protocol level on a single host (Stage
9.4 B1), its multi-machine behaviour is UNVERIFIED, and
fleet activation is an owner-gated decision (Stage 9.2,
EXP-035 and EXP-055). The systems figures are therefore
arithmetic, not a deployment plan.

## 3. Where the ceiling comes from

Two independent ceilings stack, and both are measured,
not conjectured.

Ceiling 1, the host: the guest delivers about 2 effective
CPUs although 4 vCPUs are visible (EXP-031: estimates 1.87
to 2.04 effective CPUs; production ComputeEngine on
v512dual measured 1T 5.19M/5.50M H/s in that study). The
live miner's about 21.36 MH/s is what the production
dispatch extracts from roughly 2 effective CPUs shared
with a syncing node and the rest of the live stack. More
threads do not help past the delivered CPUs; that is a
property of the VM, not of the code.

Ceiling 2, the kernel: the production SHA-256d kernel
family sits close to its instruction-count bound. The full
round is closed at a vocabulary optimum of 28 vector ops
per steady-state round, proven by SMT lower bound within
the searched vocabulary (EXP-020); production v512 emits
29. Closing that one-op gap is an ESTABLISHED NEGATIVE
twice over: the source and flag forms that would reach 28
ops are not significantly faster on this VM (EXP-041,
established null), and the compiler tuning route to the
same end is also null (EXP-044). The kernel family
therefore sits within about 1.5x of its instruction-count
bound: even a perfect kernel inside this vocabulary buys
at most a small multiple, against a gap factor of about
23,411. The remaining named structural opening, the
H-033-02 five-instruction cone shapes, was attacked by
EXP-056 and is INCONCLUSIVE at its predeclared budget
(the solver ran 6,519.3 s of its 6,600 s budget; 7 of 56
op-kind profiles per cone closed UNSAT, no SAT
construction; a budget result, not an impossibility
proof, and not a projected speedup of any size, let alone
four orders of magnitude).

Nothing in either ceiling is a tuning problem. The first
is the size of the machine; the second is the measured
shape of SHA-256d computation in the vocabularies this
programme has searched, with the searches' bounds stated
in their records.

## 4. The performance register, by tier

Classification rule (programme standing): VERIFIED
IMPROVEMENT means reproduced measurement under the EXP-017
protocol (3+ sessions, paired blocks, adjusted bootstrap
CI entirely above 0 in every session and pooled, full
correctness gates). PROMISING HYPOTHESIS means real but
incomplete evidence. UNPROVEN BREAKTHROUGH /
ESTABLISHED NEGATIVE covers everything else, labelled
which.

VERIFIED IMPROVEMENT:

- v512 backend (the AVX-512 multi-buffer kernel): pooled
  3.55x against the production C backend under EXP-017.
  Integrated; a production dispatch tier (gpu/engine.py).
- v512dual (DualMask): pooled 1.718x against v512 search
  under EXP-017. Integrated; the first CPU tier in the
  production dispatch and the backend the live miner is
  running now (observed in the status line this window).
- EXP-022 AVX-512 flags: pooled 1.441x, BATCH SCOPE ONLY.
  Verified for the batch path; the live pool search uses
  search_first, not the batch entry, so this gain is not
  in the live rate and must not be added to it (Stage 9.2
  flag F-5).
- Fallback tiers (EXP-039 dispatch; EXP-032 measurements):
  AVX2 MB batch pooled 1.409x and SHA-NI streams-4 batch
  pooled 2.861x against their baselines, verified as batch
  figures on their tiers. Two cautions ride with these:
  the AVX2 kernel was measured at 1.409x by EXP-032 and
  1.252x by EXP-039 on byte-identical code with
  non-overlapping intervals (Stage 9.2 defect DEF-9.2-5;
  unresolved; a paired EXP-017 re-measure is proposed for
  Stage 9.7 if directed), and the EXP-039 refusal check on
  a SHA-less Intel host remains host-gated and UNVERIFIED.

PROMISING HYPOTHESIS:

- EXP-052 bake-off dispatch: campaign verdict STATIC by
  dominance (v512dual dominates; every challenger pooled
  negative against it in log-ratio terms: v512 minus
  0.6264, shani minus 0.8221, avx2 minus 1.4638, C minus
  1.9559, hashlib minus 3.9732). The dispatch machinery works and
  its resolver fails closed correctly (proven again
  incidentally by the Stage 9.3 test-exp052 outcome), but
  the campaign's own control interval was wider than the
  5 percent certification margin, rotations to a second
  host class are outstanding, and no live enablement
  exists. Even a certified outcome here selects among
  existing kernels; it does not raise the ceiling in
  section 3.
- EXP-058 PID control: ships disabled; PROMISING
  HYPOTHESIS for its control behaviour; its step_up
  scale-up leg is an ESTABLISHED NEGATIVE for the
  interval-only cascade, and any hash-rate effect of the
  controller is UNVERIFIED.
- EXP-050 endpoint health and EXP-051 prefetch: measured
  harness effects (prefetch cut loaded template overhead
  from 389.7 ms to 167.3 ms in its study), both default-off
  and UNVERIFIED for live enablement and for any effect at
  mainnet difficulty. These are latency and overhead
  results, not hash-rate results.

UNPROVEN BREAKTHROUGH / ESTABLISHED NEGATIVE:

- ESTABLISHED NEGATIVE: EXP-024b design C against
  v512dual (EXP-046 pooled 0.674x at 1T); EXP-053
  (pooled minus 0.0017); the 28-op gap closure routes
  (EXP-041, EXP-044, section 3); EXP-054's displacement
  hypothesis (flat granularity curve, G=1 stands).
- UNPROVEN / INCONCLUSIVE: H-033-02 cone shapes under
  EXP-056 (INCONCLUSIVE at budget, section 3); any
  multi-machine or fleet hash-rate claim (coordination
  proven on one host only); any GPU figure (no GPU exists
  on this host; the dispatch records CUDA error 35, and no
  GPU result has ever been claimed or may be).
- UNVERIFIED, stated for completeness: the live rate's
  behaviour on the Intel Xeon Platinum 8321HC host class
  (no SHA extensions, no VBMI) at current HEAD; the
  refusal-tier behaviour there is exactly the host-gated
  EXP-039 item above.

## 5. The plain statement

No CPU-software path measured in this programme reaches
500 GH/s on one system of this class, and none credibly
projected does either. The strongest verified kernel gains
in the programme's history are single-digit multiples
(3.55x, then 1.718x, compounding to the current stack);
the kernel is within about 1.5x of its instruction-count
bound; the host delivers about 2 effective CPUs. The
distance to the minimum objective is a factor of about
23,411. Closing it would require either replication at a
fleet scale whose coordination is UNVERIFIED beyond one
host and whose activation is owner-gated, hardware
outside this programme's CPU-software-only constraint
(excluded by the programme's own rules), or a break in
SHA-256d computation itself, for which this programme has
no evidence: its closure results (EXP-020, EXP-027,
EXP-033, EXP-042) close the named spaces at their stated
bounds, and the one residue (H-033-02) is inconclusive,
not promising. Exact SHA-256d and full consensus rules
are preserved in everything above: no figure in this
report comes from probabilistic skipping, reduced work,
or any consensus deviation, and none is proposed.

The targets stand: 500 GH/s minimum objective, 140 TH/s
larger objective, unmet and unlowered. What the programme
has actually built toward them is a correct, tested,
supervised stack mining valid work at about 21.36 MH/s,
with an honest price on the distance: about 23,411 of
these systems for the minimum objective, about 6,555,078
for the larger one, and an expected mainnet waiting time
at the single-system rate of about 8.59e8 years
(STATISTICAL ESTIMATE). Those are the numbers; this report
does not soften them.

## Evidence index (research/STAGE9/evidence_96/)

- live_observation.json: rate samples with timestamps,
  process and heartbeat state, difficulty observation and
  its nbits source, node state, and the statistics census
  behind the candidate and block counts.
- gap_computation.json: compute_gap.py output on the
  observed inputs (samples, sustained rate used, interval
  rate, expected hashes and wait, systems to both
  targets).
- compute_gap.py: the arithmetic, reproducible.
