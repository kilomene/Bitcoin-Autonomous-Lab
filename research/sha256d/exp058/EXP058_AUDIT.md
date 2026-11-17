# EXP-058 independent audit: PID control for worker count and span size

Auditor: independent (not the author). Date: 2026-11-17.
Host: AMD EPYC 9D25 (confirmed from /proc/cpuinfo).
Stated remote HEAD: 5ec7914d2839f88868c26b51f7ab6478acea84a5.
Predeclaration sha256 verified on disk:
ef3b69a5d2a3c9eb6270e143d1248e4c95940c70ede047ea3d69b6037f07c78d,
matching the value pinned in exp058_campaign.py and
exp058_gate5.py. The test suite pins it transitively
(it calls the campaign driver's check_predeclaration).

## Verdict: PASS WITH NOTES, 1 defect

Every predeclared gate result reproduces under
independent recomputation and re-run, the shipped
gains equal the predeclared gains exactly, the
disabled-by-default and latching-fallback claims hold
against adversarial probing, and the step_up miss and
its structural explanation are both real. One minor
documentation defect: the report and the JSON registry
state the fault-gain oscillation trip at sample 22;
the raw record of both campaign runs, and my own
reproduction, say sample 25 (defect D-1, verdict
irrelevant, correct before push). The classification
mapping stretch is real but disclosed in the report
itself and conservative in direction (note N-1).

## 1. Predeclaration integrity and gains

- sha256 of PREDECLARATION.md on disk equals the
  briefed value and the constant pinned in both
  drivers (verified by direct hash and by the suite's
  check 1).
- Shipped gains in mining/pid_control.py:
  SPAN_GAINS = PIDGains(kp=0.35, ki=0.06, kd=0.10);
  WORKER_GAINS = PIDGains(kp=0.8, ki=0.04, kd=0.0).
  These equal the predeclaration's recorded selection
  exactly. A live AdaptiveWorkController and one built
  through make_work_controller({"pid_enabled": True})
  both carry exactly these gain objects. No gain
  differs anywhere I could reach.

## 2. Disabled-by-default: auditor probes

I fed a disabled controller and a bare StepPolicy the
same 600-sample hostile sequence (intervals uniform in
0.2 to 6.0 s, None losses, NaN, +inf, negative, zero,
and 1e308 intervals, steal up to 40 percent). Result:
zero divergences in (workers, span) across all 600
samples, every returned mode was "disabled", no trip
was ever recorded. A disabled controller fed 10 samples
at 99 percent steal also never tripped. The factory
default (make_work_controller() with no config) is
disabled and returns the step command (2 workers, span
2^23). The disabled path is exactly the step policy;
the PID loops do not run.

## 3. Fallback latching: auditor probes

- Signal loss: trips at the 6th consecutive lost
  sample (Trip(sample=16) after 10 good samples and 6
  losses, matching the campaign's sample-56 shape),
  latches: 30 subsequent good samples all returned
  mode "step" with tripped=True. reset() restored PID
  mode with trips cleared.
- Non-finite: NaN, +inf, -inf, -1.0 and 0.0 intervals
  each tripped immediately with reason
  nonfinite_signal. Non-numeric interval types (str,
  bool, list) also trip as nonfinite_signal rather
  than raising.
- Intermittent loss (5 lost, 1 good, repeated 6
  times): no trip; the loss counter resets on a good
  sample, as designed. A second streak of 6 losses
  after an intervening good sample trips.
- Steal: 2-sample bursts at 30 percent repeated never
  trip; the 3rd consecutive sample above 25 percent
  trips host_distress (Trip(sample=8) in my probe,
  campaign: sample 53 against its window start at 50,
  "by the 3rd distressed sample" as predeclared).
  Steal of exactly 25.0 for 20 samples never trips
  (the rule is strictly above 25). NaN, +inf, negative,
  string and None steal values cause no crash and no
  distress trip.
- Oscillation: the predeclared fault scenario (10x
  span Kp through the campaign plant) trips with
  reason oscillation (see D-1 for the sample number).
  An open-loop slam (alternating 0.4 s / 10.0 s
  intervals) trips at sample 17 at both 10x and the
  selected gains. A slow drive alternating 40-sample
  blocks of extreme intervals produced no trip and no
  instability (the controller saturated stably); a
  limit cycle with period longer than the predeclared
  40-sample detector window is outside the detector's
  stated definition (note N-2).

## 4. Bounds and gain validation: auditor probes

- 3,000 samples of extreme intervals (10^-3 to 10^4 s,
  1e-12, 1e12) with steal up to 24 percent: every
  command stayed within workers [1, 4] and span
  [2^20, 2^26] as integers (the run tripped on
  oscillation at sample 33 and latched to the step
  policy, itself in bounds).
- Windup attempts: 500 samples of constant 0.01 s
  intervals drove the controller to the rails (4
  workers, span 2^26) and 500 samples of 500 s
  intervals to the opposite rails (1 worker, span
  2^20), in bounds throughout, integral state within
  its clamp, no trip (constant error is not
  oscillation, correctly).
- PIDGains validation battery (11 cases: NaN, +inf,
  -inf in each position, a negative in each position,
  all-zero, string, None, bool): all raise ValueError.
  Valid edge gains (single nonzero term; 1e308 values)
  are accepted.

## 5. Gate 3 recomputation

Recomputed from the rows of
campaign_20261117T104627Z.json with my own code:

- inband_true_after20: nominal 1.0000, step_down
  0.9857, step_up 1.0000, ramp_down 1.0000, burst_dip
  0.8286. All equal the stored tallies exactly.
- Worker changes recomputed: 0 in every capacity
  scenario, equal to stored. Step baseline changes
  2, 3, 2, 3, 3 and final workers 2, 1, 2, 1, 1, as
  reported (baseline ends at 1 worker in three
  scenarios).
- step_up miss is real: no row at any sample has
  workers >= 3 (maximum workers 2 across all 160
  rows); only the workers_reach_3_by_80 check is
  false; every other step_up check is true.
- Structural explanation verified numerically against
  the disclosed plant fit: E(2, C) = 1.9200 at both
  C = 2.0 and C = 3.2 (min(n, C) saturates at n = 2),
  per-worker rate 5,127,746 H/s in both cases,
  equilibrium span for T = 2.0 s identical at
  10,255,492 (log2 23.2899, saturation +0.0966,
  inside the neutral zone) in both cases. The plant
  fit itself checks against EXP-031: E(2, 2) = 1.920
  vs measured mean 1.922; E(4, 2) = 1.862 vs measured
  mean 1.889 (inside the measured spread). At n = 2
  the interval signal genuinely carries no information
  distinguishing C = 2.0 from C = 3.2 in this fit, so
  the outer loop has nothing to act on. The claim
  "interval-only cascade cannot observe spare
  capacity" is sound for this signal and fit.
- Both retained campaign runs (104607Z and 104627Z)
  carry identical verdicts and identical trip records.

## Defect D-1: report and registry state the fault-gain trip at sample 22; the record says 25 (minor, documentation)

EXP058_REPORT.md states in the Gate 3 table and again
in judgment call 3 that the 10x-Kp fault controller
"tripped on oscillation at sample 22", and the JSON
registry's EXP-058 measured_result repeats "at sample
22". Both campaign JSONs of record state
fault_trip sample 25, and my independent reproduction
of the campaign's fault scenario (standalone and
in-sequence) trips at sample 25. The predeclared bound
is only "before sample 160", so no gate result or
verdict is affected; the figure is a transcription
error in the prose, likely from an earlier build-time
run. Correct the three places (report table, judgment
call 3, registry measured_result) to 25 before push.

## 6. Gate 5 honesty

Recomputed from gate5_20261117T104657Z.json:

- status RUN, verdict true, 60 of 60 rows present,
  every mode "pid", trips null, backend v512dual.
- Quiet window: loadavg_at_start 1-minute value 7.97,
  at or under the predeclared maximum 9.0, as
  reported. loadavg_at_end 12.86, as reported (the
  condition gates the start only, per predeclaration).
- In-band fraction after sample 15, recomputed:
  36 of 45 samples with |e| <= 0.30 = 0.800 exactly.
  The bound (at least 0.80) is met with zero margin,
  and the report states it that way.
- Workers 2 in every row; span range 9,695,762 to
  23,877,035; interval range 0.908 to 3.0525 s; steal
  maximum 3.268 percent; mean rate 8,920,543 H/s. All
  equal the report's figures.
- Separate workload: exp058_gate5.py builds its own
  ComputeEngine in the driver process and actuates it
  via engine.c_threads and the search span; it never
  imports or signals the live miner, autopilot or
  solo server (note N-3 on the wording).

## 7. Safety and production diff

- No live path imports the component: a search over
  mining/, gpu/ and agent/ finds pid_control referenced
  only by mining/pid_control.py itself. Importers are
  the exp058 drivers and the test suite only.
- .local/mining-endpoint.json mtime is still
  2026-11-14.
- Blob-level diff of the whole local tree against the
  tree of 5ec7914d (1,440 entries, not truncated),
  with the standing exclusions: differences are
  exactly the allowed set (mining/pid_control.py, the
  exp058 set in full, tests/test_exp058_pid_control.py,
  Makefile, the three registries) plus sanctioned
  exclusions (evidence/mainnet-live.jsonl differs,
  bal-miner local-only, __pycache__ throughout, the
  exp055 gate5_state/gate6_state churn and four
  regenerated gate6 records from suite reruns). No
  remote-only files; no production code outside the
  allowed set differs.

## 8. Suites (run one at a time, in this order)

- make test-exp058: 10 checks, ALL PASSED.
- make test-exp055: 23 checks, ALL PASSED (its Gate 6
  produced regtest block 2386 during my run).

## 9. Registries, Makefile, scans

- JSON registry: 107 entries; EXP-058 present with
  status EXPERIMENTAL; last entries EXP-054, EXP-055,
  EXP-057, EXP-058. EXP-052 and EXP-056 are not
  entries (reserved, as required).
- The two markdown registries: the EXP-058 appends are
  byte-identical (3,375-byte identical tails), each
  closing with "Next unreserved ID: EXP-059" and the
  EXP-052 / EXP-056 reservations noted.
- Makefile: test-all lists 48 targets, ending
  test-exp055, test-exp057, test-exp058.
- U+2014 count over the exp058 set, pid_control.py,
  the test file, Makefile and registries: 0.
- Secret scan over the same set: 0 hits.

## Notes

- N-1 (classification mapping): the predeclaration's
  three branches do not literally cover the observed
  outcome. PROVEN requires all Gate 3 bounds (step_up
  missed one); the PROMISING branch as written
  requires all Gate 3 bounds met AND Gate 5 not run
  (Gate 5 was run and passed); the NEGATIVE branch is
  scoped to nominal failures, sustained oscillation or
  repeated nominal trips (none occurred). PROMISING
  HYPOTHESIS is therefore a mapping stretch, but the
  report discloses the gap explicitly (judgment call
  6), the direction is conservative (it claims less
  than the Gate 5 pass might invite), the registry
  status EXPERIMENTAL matches the PROMISING branch,
  and the step_up property is separately and correctly
  labelled an established negative for this signal
  choice. I accept the classification as disclosed;
  the parent may wish to record the mapping gap as a
  predeclaration-writing lesson for later experiments.
- N-2: the oscillation detector's 40-sample window is
  a predeclared definition; oscillation with a period
  longer than the window is outside it by construction
  (my 80-sample-period drive saturated stably rather
  than oscillating, so no unsafe behaviour was
  observed, but the detector alone would not catch a
  genuine slow limit cycle; the span and worker rails
  bound its amplitude in any case).
- N-3: Gate 5 wording: the predeclaration says "a
  separate process runs the production ComputeEngine";
  in the driver the engine runs in-process inside the
  Gate 5 driver process. The separation that matters
  (a distinct process from the live miner, which is
  never signalled or observed except through
  contention) holds; the wording is loose, not false.
- N-4: AdaptiveWorkController.update raises ValueError
  out of the call if dt is 0, negative or non-finite
  (through PIDController). dt is an internal caller
  parameter counted in samples (default 1.0), not a
  measured signal, so this is a programming-error
  surface, not a signal path; recorded for exactness.
- N-5: the test suite pins the predeclaration hash
  transitively through the campaign driver rather than
  carrying its own constant. The pin is enforced (suite
  check 1 fails if the file changes), but a direct
  constant in the suite would be harder to bypass.

## UNVERIFIED register (auditor's own)

- Actuation against the live production miner:
  UNVERIFIED and not attempted (inherited; Gate 5
  actuated a side workload in the driver process).
- Any hash-rate effect of PID control: UNVERIFIED by
  design; no rate claim exists to audit.
- Worker scale-up under spare capacity: not merely
  unverified; shown structurally unreachable for an
  interval-only cascade under the disclosed plant fit
  (section 5). Behaviour of a probe or rate-signal
  design: UNVERIFIED, not attempted.
- Other hosts, including Intel: UNVERIFIED. All work
  here is the AMD EPYC 9D25 host.
- Real fleet conditions, long-horizon behaviour
  (hours to days), plant behaviour beyond the EXP-031
  fit points: UNVERIFIED (inherited).
- Gate 5 reproducibility: one 60-sample trial at one
  quiet window; I verified its recorded raw results
  and did not re-run it (a re-run would need its own
  quiet window and would contend with the live stack).
- The D-1 correction: UNVERIFIED, not yet made; this
  audit does not modify the report or registries.

## Bottom line

The predeclared claims survive adversarial checking:
gains are exactly as recorded before any trial, the
disabled path is bit-for-bit the step policy under
hostile inputs, the fallback latches and only an
operator reset releases it, actuation bounds hold
under windup and extreme inputs, Gate 3 tallies
recompute exactly, the step_up miss is real and its
structural explanation is numerically sound, and
Gate 5's raw record matches its report to the last
figure, including the zero-margin 0.800. PASS WITH
NOTES, 1 minor defect (D-1: trip sample stated as 22
in the report and registry; the record says 25),
5 notes. Correct D-1 before push; nothing else blocks
the push of this research record.
