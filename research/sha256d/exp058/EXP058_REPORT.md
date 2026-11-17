# EXP-058 report: PID control for worker count and span size

Date: 2026-11-17. Experiment: EXP-058, portfolio
NOVA-ER-0018, register R-32. Predeclaration:
PREDECLARATION.md in this directory, sha256
ef3b69a5d2a3c9eb6270e143d1248e4c95940c70ede047ea3d69b6037f07c78d,
written before the campaign ran and pinned in every
driver. Raw record: RAW_RESULTS/
(campaign_20261117T104627Z.json, the campaign of
record; campaign_20261117T104607Z.json, the first full
run, retained; gate5_20261117T104657Z.json).

## Verdict: Gate 3 one bound missed, Gate 5 PASS

Classification: **PROMISING HYPOTHESIS** (registry
status EXPERIMENTAL). Gate 3 met every stability bound
in every scenario, and Gate 5 (the supervised actuated
live trial) passed, but one predeclared Gate 3 bound
was missed: in the step_up scenario the worker count
never rose to 3. The predeclaration's verdict mapping
reserves PROVEN for "Gate 3 all bounds met AND Gate 5
passed", and its ESTABLISHED NEGATIVE branch is scoped
to nominal-scenario failures, sustained oscillation or
repeated nominal fallback trips, none of which
occurred. The step_up outcome falls between those
branches (a mapping gap, disclosed in the judgment
calls); the conservative reading is applied.

The headline finding is a precisely characterised
limitation, not a tuning failure: **an interval-only
cascade cannot observe spare capacity.** At 2 workers
the per-worker rate is already the uncontended rate
for any capacity C >= 2 (the EXP-031 plant fit has
E(2, C) = 1.92 flat in C above 2, matching the EXP-031
measurements), so the equilibrium span (2^23.29) and
its saturation (+0.097, inside the neutral zone) are
identical at C = 2.0 and C = 3.2. No interval signal
distinguishes the two states, so the outer loop
correctly sees nothing to act on. Worker scale-up
requires a probing element (which the production step
tuner has and this PID design deliberately lacks) or a
second signal, such as aggregate rate against a
ceiling estimate. For the worker-reach property at
this signal choice, the result is an ESTABLISHED
NEGATIVE; for every stability property, the bounds
held, offline and live.

No rate claim is made anywhere in this experiment
(portfolio rule: a rate claim would need its own
EXP-017 entry). Simulation rates are plant-model
outputs; live rates are descriptive trial telemetry.

## What was built

- mining/pid_control.py (new additive component at
  the autopilot seam; nothing in the live paths
  imports it): PIDGains with construction-time
  validation (non-finite, negative or all-zero gains
  raise ValueError, so a mis-configured controller
  cannot be built); a discrete PIDController with
  integral clamping and conditional anti-windup;
  StepPolicy, the retained step policy in code (the
  baseline and the fallback); and
  AdaptiveWorkController, the cascaded controller.
  It ships DISABLED by default: enabled=False always
  returns the step-policy command, exactly today's
  behaviour, and one configuration value
  (pid_enabled) is the whole rollback surface.
- The cascade: the inner span loop (velocity form)
  drives the span-interval error
  e = (T_target - T_measured) / T_target, T_target =
  2.0 s, by moving log2(span) within [2^20, 2^26];
  the outer worker loop (absolute form) reads span
  saturation with a neutral zone (|sat| <= 0.25) and
  actuates the integer worker count in [1, 4] by at
  most 1, only past a 0.6 threshold and a 6-sample
  dwell. Steal is monitored, not a PID input (EXP-031
  showed it insensitive to thread count here).
- The fallback latches onto the step policy and
  records the trip (sample, reason): signal loss
  (6th consecutive lost sample), non-finite signal
  (immediate), oscillation (4 worker-command
  reversals or 16 material span-velocity sign
  changes in a rolling 40-sample window), host
  distress (steal > 25 percent for 3 samples).

## Gain selection record (from EXP-031, before any trial)

Recorded in full in the predeclaration, derived from
the EXP-031 loadprobe record (R1 = 5,341,402 H/s mean
1-thread rate; E(2) mean 1.922, E(4) mean 1.889;
steal band 1.4 to 2.7 percent; about 20 percent
run-to-run variance at fixed configuration). Sample
period 5 s (production heartbeat cadence), gains per
sample: span loop Kp = 0.35, Ki = 0.06, Kd = 0.10
(plant gain de/d(log2 span) = -ln 2 at the operating
point; a 20 percent interval error needs 0.29 log2 of
total correction; integral time about 6 samples);
worker loop Kp = 0.8, Ki = 0.04, Kd = 0 (integral
time 20 samples; worker changes are the expensive
actuation). No gain was changed after the
predeclaration was hashed.

## Gate 3: offline campaign against the EXP-031 plant

Deterministic seeded simulation (seed 20261117, 160
samples per scenario, measurement noise sigma 10
percent as predeclared). Bounds are evaluated on the
true interval error; measured-error statistics are
recorded in the campaign JSON (nominal in-band
fraction on the measured error is 0.82, a property of
the predeclared noise: sigma 10 percent on T is sigma
0.10 on e, so the 0.15 band is 1.5 sigma wide).

| scenario | verdict | PID worker changes | PID in-band (true, after 20) | step baseline changes | step baseline in-band |
|---|---|---|---|---|---|
| nominal | PASS | 0 | 1.000 | 2 | 0.000 |
| step_down (C 2.0 to 1.1) | PASS | 0 | 0.986 | 3 | 0.000 |
| step_up (C 2.0 to 3.2) | FAIL (reach bound only) | 0 | 1.000 | 2 | 0.000 |
| ramp_down (C 2.0 to 1.2) | PASS | 0 | 1.000 | 3 | 0.186 |
| burst_dip (C 0.8, 15 samples) | PASS | 0 | 0.829 | 3 | 0.086 |
| signal_loss | PASS | held 5 samples, tripped at the 6th, latched | | | |
| gain_faults | PASS | all 4 construction faults raised; non-finite sample tripped immediately; 10x-Kp controller tripped on oscillation at sample 25 | | | |
| host_distress | PASS | tripped at the 3rd distressed sample, latched | | | |

step_up detail: return-to-band, in-band after the
step (1.000), change-count and zero-trip checks all
pass; only workers_reach_3_by_80 fails, for the
observability reason in the verdict section. The
annex (seeds 1 and 2, recorded, not bound-evaluated)
reproduces the same shape in nominal, step_down and
step_up: zero worker changes, in-band 0.97 to 1.00,
no trips.

Two comparison facts worth stating plainly. The step
baseline holds a constant +18 percent interval error
in the nominal scenario (its fixed mid span at the
EXP-031 operating point gives T = 1.64 s against the
2.0 s target, inside its own 25 percent threshold, so
it never acts; in-band fraction 0.000 at the 0.15
band), and under noise it chatters (2 to 3 worker
changes per scenario, ending at 1 worker in three
scenarios). The PID held the true interval error in
band essentially throughout with zero worker changes
in every scenario at the selected gains: the span
loop alone absorbs the capacity steps the plant
contains, which is the smoothness the portfolio
hypothesis asked about, at the cost of the scale-up
blindness recorded above.

## Gate 5: supervised live trial (actuated, trial workload only)

The quiet-window condition was met (1-minute load
average 7.97 at start, against the predeclared
maximum 9.0; EXP-031's standing baseline was 7.0 to
7.5). The trial ran 60 samples against a separate
ComputeEngine process (backend v512dual, target 1
full scans, the EXP-031 load-probe pattern); the live
miner, autopilot, node and endpoint config were
untouched. Results: all 60 samples completed; every
command in bounds; no NaN; zero fallback trips;
worker count 2 throughout (the live capacity is the
same about-2-effective-CPUs the plant assumes); span
adapted continuously between 9,695,762 and 23,877,035
nonces; measured intervals 0.91 to 3.05 s; |e| <=
0.30 for exactly 0.800 of samples after sample 15
(the predeclared bound is at least 0.80: met, with no
margin to spare, and stated that way); steal stayed
inside the EXP-031 band (maximum 3.3 percent). The
1-minute load average rose to 12.86 by the end of the
trial (the trial's own load plus the surrounding
stack; the condition gates the start, as
predeclared, and the rise is recorded here). Mean
trial rate 8.92M H/s is descriptive telemetry only.

## Judgment calls and build-time disclosures

1. Saturation deadband: the predeclaration describes
   the worker loop acting on saturation "near the
   floor / ceiling"; the implementation gives that a
   neutral zone (|sat| <= 0.25). A build smoke test
   showed why it is required: the equilibrium
   saturation at the optimal worker count is +0.097,
   not zero, so a deadband-free integral chases it
   into a slow limit cycle (a worker change at about
   sample 28 in the smoke run). The recorded gains
   are unchanged.
2. Integral accounting: the PID loops count dt in
   samples, as the predeclaration's per-sample gain
   derivation assumes, and the integral state limits
   are set so the integral TERM respects the
   predeclaration's clamps (1.0 log2 span, 1.0
   worker). Both are accounting completions of the
   predeclared numbers, not re-tunings.
3. Oscillation detector: span-velocity sign changes
   are counted only between material moves
   (|delta log2 span| >= 0.15 per sample). Raw
   per-sample sign changes of a continuous loop are
   regulation dither (about 95 per 160 samples at
   corrections of a few hundredths of a log2, in the
   nominal campaign record as span_reversals, with
   span_material_reversals 0); the fault-gain loop
   slams the +/- 0.5 clamp on alternate samples and
   trips the material detector at sample 25.
4. Metrics definition: Gate 3 stability bounds are
   evaluated on the plant's true interval error (the
   regulated quantity), with measured-error
   statistics recorded alongside. At the predeclared
   noise level a bound on the measured error would
   be a bound on the noise itself.
5. The campaign driver gained the
   span_material_reversals metric after the first
   full run; the campaign was re-run unchanged
   otherwise and the second run (104627Z) is the
   campaign of record. The first run (104607Z) is
   retained in RAW_RESULTS.
6. Verdict mapping gap: the predeclaration's
   mapping did not anticipate "all stability bounds
   met, one actuation-reach bound missed, Gate 5
   passed". PROMISING HYPOTHESIS is the conservative
   reading and is applied; the component is not
   proposed for live-miner integration on this
   record.

## Suites

Run one at a time: make test-exp058, 10 checks, ALL
PASSED (predeclaration pin, gain faults, default-off,
Gate 3 regression scenarios, fallback mechanics; the
step_up known miss is asserted as stability-bounds
plus recorded miss, and Gate 5 is not in the suite
because it is load-gated). The change is fully
additive (new module, new drivers, new test; no
shared production code touched), so one neighbour
was run: make test-exp055, 23 checks, ALL PASSED.
Makefile test-all goes from 47 to 48 targets.

## UNVERIFIED register

- Actuation against the live production miner (the
  controller setting the real miner's threads or
  spans): UNVERIFIED and not attempted; integration
  is a separate step. Gate 5 actuated a trial
  workload beside production only.
- Any hash-rate effect of PID control: UNVERIFIED by
  design; no rate claim is made, and one would need
  its own EXP-017 entry.
- Worker scale-up under spare capacity: not merely
  unverified but shown structurally unreachable for
  an interval-only cascade (see verdict); a design
  with a probe element or a rate signal is future
  work, not attempted here.
- Behaviour on other hosts, including Intel:
  UNVERIFIED. All measurement is the AMD EPYC 9D25
  host.
- Behaviour under real fleet conditions (multiple
  machines, real network): UNVERIFIED; no other
  machine was contacted.
- The plant model beyond the EXP-031 points it was
  fitted to (capacities far outside 0.8 to 3.2,
  backends other than v512dual): UNVERIFIED.
- Long-horizon behaviour (hours to days of
  continuous control, integral behaviour across
  template changes and job refreshes): UNVERIFIED;
  the live trial is 60 samples over about 2 minutes.
- An independent audit of EXP-058 is owed before any
  push, as with every Stage 9 experiment.
