# Stage 9.4 Independent Audit

Auditor: independent (not the Stage 9.4 builder). Date:
2026-11-18. Subject: research/STAGE9/
AUTONOMOUS_AGENT_GAP_ANALYSIS.md, the B2 change to
mining/engine.py, the B1 and B3 evidence under
research/STAGE9/evidence_94/, and the Makefile change.
Baseline: remote HEAD
9d65efe86f1ed119ea9b11eb3aea098f50f52ad4 (the 9.4 work is
not pushed; this audit does not push).

## Verdict: PASS WITH NOTES

Every material claim in the builder report was verified
independently at source or recomputed from raw evidence.
One minor documentation defect (D-94-1) and one CI
recommendation are recorded. No production defect found.

## 1. Gap claims, sampled at source

(a) MiningController: CONFIRMED. agent/intelligence/
controller.py carries inspect() at line 248, start() 349,
stop() 389, restart() 435, select_backend() 485 and
refresh_job() 535 returning ControlResult status
"unsupported" with honest explanatory detail (read in
full), and recover() at 612. Caller search: the controller
is constructed by the package facade
(agent/intelligence/__init__.py line 85) and by
MiningInterface when wired (interface.py line 223), and
exercised by test suites; no daemon, service, loop or CLI
command invokes start, stop, restart or recover on the
live stack (the only .start()/.stop() call sites in agent/
outside the controller itself are its own internal ones
and a sandbox thread). The C1 verdict (owns the
vocabulary, does not operate it) stands.

(b) Research loop: CONFIRMED. agent/intelligence/loop.py
carries the gated state machine (advance, _check_not_rejected,
validate_integrate_evidence with the independent-verifier
HMAC check and the EXP-017 evidence shape). ExperimentRunner
and OptimisationLoop are instantiated only in tests
(test_agent_intelligence, test_agent_operations,
test_agent_security, test_agent_controller_modes) and in
the Stage 8 demonstration script (see D-94-1); nothing in
production drives them. Registry write-back: the agent
package only reads and parses the registries (memory.py);
no code path writes a verdict into any registry. The C2
verdict stands.

(c) Coordinator importers: CONFIRMED zero live importers.
A repo-wide import search finds mining.coordinator imported
only by tests/test_exp055_coordinator.py, the EXP-055
research scripts, and the B1 scratch scripts under
.local/stage9/b1/. The strings "coordinator" do not appear
at all in mining/mainnet_live.py, mining/autopilot.py,
mining/solo_server.py, agent/autonomous.py or
agent/intelligence/*.py.

(d) DEF-9.2-4 premise: CONFIRMED. The pool path publishes
status every 10 s (mining/mainnet_live.py, the
"now - last_log > 10" block at about line 390, writing the
STATUS file). DEF-9.2-4 is recorded in
PRODUCTION_PROMOTION_DECISIONS.md (line 676) as the GBT
path lacking any such publisher; the GBT path's only
publisher is the new B2 class verified in section 2.

## 2. B2 code change (mining/engine.py)

sha256 CONFIRMED:
866936fd6d41ebcc3a5ecbde886b0a5aa27eeae6ad5483025ddf0b3f1635f1ec.

Diff reviewed in full at source:
- StatusPublisher (line 492) is a daemon thread; its run
  loop catches every sink exception, counts it on
  self.errors, and continues; publication cannot break
  the cycle.
- Constructor defaults (line 562): status_publish=False,
  status_interval_s=10.0, status_sink=None; the default
  sink appends to a bounded deque (maxlen 1024).
- mine_cycle (line 858) is a thin wrapper: with the flag
  off it is a plain pass-through to _mine_cycle (line
  885); with it on, the thread is started before the
  cycle and stopped and joined in a finally block, on
  every exit path including exceptions. Thread lifetime
  is owned by the wrapper, as claimed.
- Enablement: status_publish=True appears only in
  tests/test_status_publisher.py and in a comment. The
  three MiningEngine constructions in the tree
  (mining/cpu/miner.py, mining/testnet4_attempt.py,
  agent/autonomous.py) pass no status flag. No live
  config enables it.
- .local/mining-endpoint.json untouched, sha256
  d741cde3c6224406f46f3bae138fb174eb1d780725bcb94baff4e14a8670c7d3,
  matching the expected value.

Auditor re-runs (one at a time): tests/test_status_publisher.py
PASSED all 5 checks, including check 2's proof that the
enabled and disabled cycle results are identical and
check 5's exception path. Neighbour make test-exp038
PASSED.

## 3. B1 evidence (independent processes, fencing)

Recomputed from the raw worker JSONL logs, not from the
summary JSON:
- Phase A: 16 completion records, total hashes exactly
  131,072; per slice the [lo, hi) intervals are pairwise
  disjoint and cover [0, 65536) exactly; all 16 lease ids
  unique; all complete_result values OK; zero duplicate
  completed chunks; candidate counts sum to 28, matching
  the coordinator summary (28 submitted, 0 duplicates, 28
  verified on drain). Checkpoints show the partition
  invariant and the accounting identity holding at every
  checkpoint.
- Phase B: the sequence in the logs is exactly as
  claimed. w1_result.json: progress OK on lease L1
  (token 1), then complete_after_stall STALE and
  progress_after_stall STALE. b1_phase_b.json records
  not_holder_attempt NOT_HOLDER at the after_not_holder
  checkpoint (not_holder_attempts 1), expire_result [L1]
  with reclaims 1, the takeover completion under lease L2
  with token 2 (strictly larger than 1), and
  duplicate_replay DUPLICATE; final accounting complete
  with unique_coverage 8192 of 8192 declared,
  stale_reports 2, duplicate_deliveries 1.
- Independent OS processes: CONFIRMED. Distinct pids
  throughout (Phase A coordinator 18890, workers 18904
  and 18905; Phase B coordinator 19069, stalled
  incarnation 19080, takeover incarnation 19135), and the
  driver (.local/stage9/b1/drive.py) launches the
  coordinator and workers with subprocess.Popen over TCP;
  worker.py speaks the wire protocol through
  CoordinatorClient. Not threads in one process.

## 4. B3 evidence (load-aware deferral)

- Ambient (b3_ambient_mode.json): CONFIRMED. CRITICAL
  entered on the second sample and held for all 7
  samples; load1 17.21 down to 15.30, ratio 8.60 to 7.65
  against effective_cpus 2.0, production thresholds.
- Deferral run 2 (b3_load_deferral.json): CONFIRMED.
  Transitions: NORMAL to BROWNOUT at 48.2 s (ratio
  0.503), to CRITICAL at 96.3 s (0.440), step-down to
  BROWNOUT at 190.2 s and to NORMAL at 250.3 s, late
  re-entry to BROWNOUT at 262.3 s (ratio 0.699) still in
  effect at run end; arc_verdict INCOMPLETE, final mode
  brownout. Gated worker: 153 deferred checks over a
  318.4 s span, 56 batches before the shed window, 19
  after, control worker 229 batches inside the shed
  window. Probe ratio range recomputed from the samples:
  0.224 to 3.656 over 85 samples, as reported.
- Both disclosed blemishes verified in the raw records:
  exactly one gated batch (batch 56) started inside the
  shed window, 0.4 s after the recorded transition
  (cooperative boundary semantics, as designed and as
  documented); and the late BROWNOUT re-entry at 262 s
  had not cleared at run end, which is why the demo's
  strict verdict reads INCOMPLETE. Both are recorded in
  the builder report, not hidden.
- Run 1 kept as flawed: CONFIRMED. b3_load_deferral_run1_flawed.json
  shows both workers' 24-batch quotas exhausted by about
  t=18 s, before the hog window opened at t=36 s, with
  zero deferrals; the mode arc (BROWNOUT at 116 s, back
  at 180 s) is present. The disclosure in the report
  matches the record.
- Label judgement: "prototype-grade, agent-controlled
  inside the package, inactive in live production" is
  FAIR. The demo drives the production ModeManager with
  production thresholds (only the exposed exit_window_s
  timing knob shortened, disclosed), the workers and
  hogs are real processes, and nothing was wired into
  the live miner.

## 5. Autonomy classifications

- C1 agent-assisted: FAIR (section 1a).
- C2 agent-assisted: FAIR (section 1b). The machinery is
  enforced and complete; no driver exists; integration
  and registry update are human or external acts.
- C3 agent-controlled in-package only: FAIR. B3 proves
  the gates genuinely refuse and defer work across
  processes when a driver feeds the mode machine; no
  always-on driver exists in production, and the load
  channel's miscalibration on this host is disclosed in
  the report and confirmed by the ambient evidence.
- C4 agent-controlled at protocol level on one host,
  deployed nowhere: FAIR (sections 1c and 3). No
  overstatement found in any of the four; the Part C
  UNVERIFIED register (multi-machine, real job source
  over the wire, live enablement, calibration) is
  complete against the evidence presented.

## 6. Makefile and CI

- test-all now has 52 prerequisites (counted), including
  test-status-publisher; the target runs
  python3 tests/test_status_publisher.py. CONFIRMED.
- CI subset unchanged: .github/workflows/test.yml still
  runs exactly the 4 cleanroom suites (test-exp037,
  test-exp038, test-probability, test-exp049).
  CONFIRMED.
- Recommendation only: test-status-publisher is a
  plausible future addition to that subset. Its own
  imports are stdlib plus in-repo modules, it uses a
  stub RPC and a fake compute, and it touches no node,
  no .local state and no host-specific path. It does,
  however, import mining.engine, which transitively
  imports gpu.engine; import behaviour on a tree without
  .local was not cleanroom-tested in this audit. Per the
  Stage 9.3 discipline, run it in the cleanroom first
  and add it only if it passes there.

## 7. Hygiene and live stack guard

- U+2014 count: zero in
  research/STAGE9/AUTONOMOUS_AGENT_GAP_ANALYSIS.md and
  zero in tests/test_status_publisher.py.
- Live stack: heartbeat before this audit
  (2026-11-18T06:36:51Z) autopilot 2830, miner 2833,
  shares 1069; after (2026-11-18T06:39:27Z) same pids,
  shares 1071. Non-decreasing against the stage-start
  1066 and undisturbed by this audit.

## Defects

- D-94-1 (minor, documentation precision): the C1 and C2
  caller enumerations are incomplete. C2 lists the
  ExperimentRunner's test invocations as
  test_agent_intelligence.py, test_agent_operations.py
  and test_agent_security.py, omitting
  tests/test_agent_controller_modes.py (line 479), and
  neither C1 nor C2 mentions
  research/EXTREME_RESEARCH/stage8_demonstration.py,
  which constructs both a MiningController (line 213)
  and an ExperimentRunner (line 567). That script is a
  human-run Stage 8 demonstration against isolated
  instances, not a production path, so the material
  claims (no daemon, no CLI operation, nothing in
  production) stand unchanged. Correction is a wording
  fix to the two enumerations; no code or verdict is
  affected.

No other defects. Nothing was pushed by this audit and
no production code was modified by the auditor.
