# EXP-058 predeclaration (written before the campaign runs)

Written: 2026-11-17, before any EXP-058 campaign, simulation
or live-trial measurement was taken. This file's sha256 is
pinned in the campaign driver, the Gate 5 driver and the
test suite. EXP-058 is portfolio NOVA-ER-0018 (register
R-32): PID control for worker count and span size. It
follows EXP-057 (NOVA-ER-0017) in the Stage 9 portfolio
order. EXP-052 stays reserved for NOVA-ER-0012 and
EXP-056 for NOVA-ER-0016.

## Question and hypothesis

Does a PID loop driven by a measured error signal adapt
worker count (engine search threads) and span size (nonces
per search call) on this contended VM more smoothly than
the existing step behaviour, without oscillation?

Existing step behaviour, the baseline and the retained
fallback: gpu/engine.py tune_c_threads, tune_v512_threads
and tune_v512dual_threads probe candidate thread counts
once at start, pick the peak rate, and hold that count
until the next restart or re-probe. It is a one-shot step
decision: it cannot react when the VM's usable capacity
moves, and EXP-031 recorded the production tuner choosing
2 threads in one run and 4 in another, 30 seconds apart,
under the same nominal conditions.

Portfolio hypothesis: conservative gains with the step
policy retained as fallback hold the rate within noise of
the best fixed configuration while removing throttle and
collapse cycles. Per the portfolio, NO rate claim is made
in this experiment: any rate claim would need its own
EXP-017 entry. Simulation rates are plant-model outputs,
labelled as such, never measurements.

## EXP-031 signals used (recorded evidence, cited)

From research/sha256d/exp031/CPU_VM_CHARACTERIZATION.md
and its RAW_RESULTS loadprobe files (two runs, production
ComputeEngine, backend v512dual, 16,777,216 nonces per
configuration, alongside the live miner and the syncing
node):

- 1-thread rate: 5,185,651 H/s (run 1), 5,497,152 H/s
  (run 2). Mean R1 = 5,341,402 H/s.
- Scaling E(n) = aggregate rate / 1-thread rate:
  E(2) = 1.805 and 2.039 (mean 1.922); E(4) = 1.912 and
  1.865 (mean 1.889). Saturation at about 2 effective
  CPUs against 4 claimed vCPUs.
- Steal: 1.4 to 2.7 percent across all windows; it did
  NOT grow from 1 to 4 threads. The ceiling behaves like
  a capacity allocation, not like steal bursts.
- Baseline guest busy 61 to 64 percent, load average
  7.0 to 7.5 (1 minute) with the live stack running.
  That is this VM's normal standing condition.
- Run-to-run variance at fixed configuration is large:
  the 2-thread rate differed by about 20 percent between
  runs 30 seconds apart. Capacity varies minute to
  minute with the node's validation rhythm.

## Design fixed here

- The controller is a new additive component,
  mining/pid_control.py, at the autopilot seam: a
  supervisor would call update(signals) once per control
  sample and receive a Command (worker count, span size,
  mode). It is NOT wired into mining/autopilot.py,
  mining/mainnet_live.py or any live path in this
  experiment, and it ships DISABLED by default: a
  controller built with enabled=False always returns the
  step-policy command, which is exactly today's
  behaviour. Enabling it is a separate, later,
  operator-visible step, not part of EXP-058.
- Two cascaded loops driven by one measured signal, the
  span completion interval (the share-interval analogue
  for this engine: the wall time one span of nonces
  takes to search):
  - Inner span loop (fast): error
    e = (T_target - T_measured) / T_target, with
    T_target = 2.0 s. A velocity-form PID outputs the
    per-sample change in log2(span), clamped to
    +/- 0.5, with span clamped to [2^20, 2^26] nonces.
  - Outer worker loop (slow): its error signal is the
    inner loop's span saturation,
    sat = (log2(span_cmd) - log2(span_mid)) / 3 in
    [-1, 1]. Sustained saturation near the floor means
    capacity per worker is scarce even at the smallest
    spans, so desired workers fall; sustained saturation
    near the ceiling means intervals stay fast at the
    largest spans, so desired workers rise. An
    absolute-form PID produces continuous desired
    workers u in [1, 4] around the base of 2; the
    actuated integer count changes by at most 1, only
    when |u - n| >= 0.6, and only after a dwell of 6
    samples since the last change.
- Steal is a monitored signal and a fallback input, not
  a PID input (EXP-031 showed it insensitive to thread
  count on this VM): steal above 25 percent for 3
  consecutive samples (ten times the EXP-031 band)
  trips the fallback as host distress.
- Fallback (the retained step policy, in code as
  StepPolicy): a threshold relief stepper. If the
  interval error exceeds +/- 25 percent for 3
  consecutive samples it steps worker count by 1 in the
  relieving direction and resets span to mid, with a
  5-sample cooldown. The fallback LATCHES: once tripped,
  the controller stays on the step policy until an
  operator reset. Trips, with sample index and reason,
  are recorded. Trip conditions, fixed here:
  signal loss (more than 5 consecutive missing or
  invalid samples), a non-finite signal at any sample
  (immediate), oscillation (4 or more worker-command
  direction reversals within a rolling 40-sample
  window, or 16 or more span-velocity sign changes
  within a rolling 40-sample window), host distress
  (steal rule above).
- Gain faults are construction faults: PIDGains rejects
  non-finite, negative or all-zero gains with
  ValueError, so a mis-configured controller cannot be
  built. A runtime non-finite error trips the fallback
  through the signal path above.
- Rollback: the component is additive and default-off.
  One configuration value (enabled=False, the default)
  restores the step policy, which remains in code.
  Nothing in the live paths imports the component.

## Gain selection from EXP-031 signals (recorded before any trial)

Sample period dt = 5 s, the production heartbeat cadence.
Scenario length 160 samples.

Plant fit used for gain derivation and for the Gate 3
simulation, fitted to the six EXP-031 loadprobe points
above and disclosed as a model, not a measurement:
E(n, C) = min(n, C) * (1 - 0.04 * max(0, min(n, C) - 1))
* (1 - 0.015 * max(0, n - C)), aggregate rate
R = R1 * E(n, C), per-worker rate R / n, span interval
T = span / (R / n). Check against EXP-031 means:
E(1, 2) = 1.000 (definition), E(2, 2) = 1.920 (measured
mean 1.922), E(4, 2) = 1.862 (measured mean 1.889, inside
the measured run spread 1.865 to 1.912).

Span loop gains. At the operating point T is
proportional to span, so de/d(log2 span) = -ln 2 =
-0.693: a 20 percent interval error (the EXP-031 noise
scale) needs a total log2 correction of 0.20 / 0.693 =
0.29. Kp_span = 0.35 gives a first-sample correction of
0.35 * 0.20 = 0.07 log2 (about 5 percent of span) for
that error: firm but far from the +/- 0.5 clamp.
Ki_span = 0.06 gives an integral time of
Kp / Ki = about 6 samples (30 s), inside the
minute-scale capacity variation EXP-031 observed and
slow enough to average the measurement noise
(sigma 10 percent, below). Kd_span = 0.10 on the error
difference damps the step response. Integral clamp:
1.0 log2 of accumulated correction.

Worker loop gains. Worker changes are the expensive
actuation (the production tuner spends seconds probing
each count), so this loop is the slow one: Kp_w = 0.8,
Ki_w = 0.04 (integral time 20 samples, 100 s),
Kd_w = 0. Integral clamp: 1.0 worker of accumulated
contribution, so u stays within [2 - 1.8, 2 + 1.8]
before the [1, 4] clamp and can reach each integer
threshold (0.6 past the current count) only under
sustained saturation, as designed.

Measurement noise in the simulation: multiplicative,
sigma 10 percent on each interval sample (half the
20 percent run-to-run spread EXP-031 recorded at fixed
configuration, because a control sample aggregates
several spans).

No gain is tuned after seeing trial results. Any change
to these numbers after this file is hashed is a
deviation and must be disclosed as one in the report,
with the campaign re-run.

## Gates, fixed in advance (Gates 1, 2, 4 and 6 do not apply)

- Gate 3 (offline campaign against the recorded-signal
  plant, in full): deterministic seeded simulation,
  160 samples per scenario, the step policy run through
  the same scenarios as the baseline. Scenarios and
  their predeclared stability bounds:
  - nominal: C = 2.0 constant. Bounds: worker count
    settles at 2 and changes at most twice after sample
    20; span stays inside [2^20, 2^26]; zero fallback
    trips; |e| <= 0.15 for at least 90 percent of
    samples after sample 20.
  - step_down: C steps 2.0 to 1.1 at sample 40 (a node
    validation burst analogue). Bounds: |e| returns to
    <= 0.15 within 12 samples of the step and stays
    there for at least 90 percent of the remaining
    samples; at most 4 worker changes in the whole
    scenario; zero fallback trips.
  - step_up: C steps 2.0 to 3.2 at sample 40. Bounds:
    same interval bounds as step_down; worker count
    reaches 3 by sample 80; at most 4 worker changes;
    zero fallback trips.
  - ramp_down: C ramps 2.0 to 1.2 over samples 40 to
    80. Bounds: |e| <= 0.25 for at least 90 percent of
    samples after sample 50; at most 4 worker changes;
    zero fallback trips.
  - burst_dip: C dips to 0.8 for samples 60 to 75, then
    returns to 2.0. Bounds: |e| returns to <= 0.15
    within 15 samples of the dip ending; at most 5
    worker changes; zero fallback trips.
  - signal_loss: interval samples missing for samples
    50 to 65. Bounds: commands hold unchanged during
    the first 5 lost samples; the fallback trips with
    reason signal_loss at the 6th lost sample and
    latches; no NaN or out-of-bounds command is ever
    emitted.
  - gain_faults: (a) constructing PIDGains with NaN,
    infinite, negative or all-zero gains raises
    ValueError in every case; (b) a non-finite interval
    sample at sample 30 trips the fallback immediately
    with reason nonfinite_signal; (c) a controller
    built with Kp_span ten times the selected value
    (3.5) in the nominal scenario is EXPECTED to trip
    the oscillation fallback: success is the trip
    happening, with reason oscillation, before sample
    160. This scenario tests the safety net, not the
    tuning.
  - host_distress: steal forced to 30 percent for
    samples 50 to 60 with C nominal. Bounds: fallback
    trips with reason host_distress by the 3rd
    distressed sample and latches.
  Smoothness comparison, recorded for every scenario:
  worker changes, span direction reversals, samples in
  the |e| <= 0.15 band, for the PID controller and for
  the step policy baseline on identical scenario and
  seed. These are plant-model outputs; no rate claim
  is made from them.
- Gate 5 (live trial under supervision, with automatic
  fallback): the controller actuates a TRIAL workload,
  never the live miner: a separate process runs the
  production ComputeEngine (v512dual, target 1 full
  scans, the EXP-031 load-probe pattern) while the
  controller sets its thread count and span (search
  range size) once per measured sample, the measured
  interval being the real wall time of one span search.
  The live miner, autopilot, node and endpoint config
  are untouched and unobserved except through the
  contention they cause, which is the point of the
  trial. Automatic fallback is armed identically to
  Gate 3; on any trip the trial engine reverts to the
  step-policy command (2 threads, span 2^23) for the
  remainder of the trial. Quiet-window condition,
  fixed here: the trial starts only if the 1-minute
  load average is <= 9.0 at start (EXP-031's standing
  baseline was 7.0 to 7.5 with the live stack up).
  Trial length: 60 samples. Success bounds: the trial
  completes all 60 samples; every command inside
  bounds; no NaN; |e| <= 0.30 for at least 80 percent
  of samples after sample 15 (a looser band than
  Gate 3, because live contention is not the plant);
  any fallback trip is recorded with its reason and is
  a Gate 5 failure unless the trip condition is itself
  observed in the live signals (a genuine signal loss
  or distress window), in which case the trip is the
  designed behaviour and is reported as such.
  If the quiet-window condition is not met when Gate 5
  is attempted, Gate 5 is recorded NOT RUN with the
  observed load figures, the actuated live trial joins
  the UNVERIFIED register, and the classification is
  capped as stated in the verdict mapping. A shadow
  substitute is NOT claimed as Gate 5.

## Verdict mapping, predeclared

- Gate 3 all bounds met AND Gate 5 run and passed:
  EXP-058 is COMPLETE, classification PROVEN for the
  controller stability properties measured (offline
  scenarios against the EXP-031 plant, and one
  supervised actuated trial of a side workload on this
  VM). No rate claim. Live-miner integration remains a
  separate step and is UNVERIFIED.
- Gate 3 all bounds met AND Gate 5 not run (quiet
  window unmet): EXP-058 is COMPLETE as an
  offline-validated component, classification PROMISING
  HYPOTHESIS, registry status EXPERIMENTAL. The
  actuated live trial is UNVERIFIED.
- Gate 3 any bound missed in the nominal scenario, or
  sustained oscillation, or repeated fallback trips in
  nominal conditions: EXP-058 is ESTABLISHED NEGATIVE
  for this design at these gains, registry status
  REJECTED, the step policy stays, and the data is
  recorded. A defect found and fixed during the build,
  before the campaign of record runs, is ordinary
  build work and is recorded in the report's judgment
  calls; a defect found by a gate is a gate failure
  unless the gate's own text above says otherwise.

## Hard lines and scope

- No other machine is contacted. Fleet activation is
  owner-gated (roadmap F2) and is not performed.
- The live miner, autopilot, solo server and endpoint
  config are untouched; .local/mining-endpoint.json is
  not read or written by any driver here. Gate 5's
  trial workload is a separate process beside
  production, the EXP-031 load-probe pattern, and it
  never signals the production processes.
- Exact SHA-256d only; the trial workload uses the
  production engine with target 1 (full scans), so no
  share validation path is exercised or touched; where
  validation would apply, EXP-036 is the only route.
- Production files change only by addition:
  mining/pid_control.py is new, and the Makefile and
  the three registries gain the EXP-058 entries.
- Host: AMD EPYC 9D25 (confirmed from /proc/cpuinfo at
  build start). No GPU exists and none is claimed.
  Results on other hosts are UNVERIFIED.

## UNVERIFIED register (predeclared, stands regardless of outcome)

- Actuation against the live production miner (the
  controller setting the real miner's threads or
  spans): UNVERIFIED and not attempted; integration is
  a separate step.
- Any hash-rate effect of PID control: UNVERIFIED by
  design; no rate claim is made anywhere in this
  experiment, and one would need its own EXP-017 entry.
- Behaviour on other hosts, including Intel:
  UNVERIFIED. All measurement is the AMD EPYC 9D25
  host.
- Behaviour under real fleet conditions (multiple
  machines, real network): UNVERIFIED; no other
  machine is contacted.
- The plant model beyond the EXP-031 points it was
  fitted to (capacities far outside 0.8 to 3.2,
  other backends than v512dual): UNVERIFIED; the
  model is a disclosed fitting, not a measurement.
- Long-horizon behaviour (hours to days of continuous
  control, integral behaviour across template
  changes): UNVERIFIED; trials here are minutes.
