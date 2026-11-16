# Stage 7 Independent Audit

Auditor: independent agent, not the author of any Stage 7 code.
Date: 2026-11-16. Host: AMD EPYC 9D25 (recorded from
/proc/cpuinfo during the audit), guest with 4 logical CPUs.
Scope: Directive 5 Stage 7, four items landed locally and
unpushed (remote HEAD stated in the brief: d412f14f). Wave 1
item A (D6 integration registry fix), wave 1 item B
(C_THREADS removal), wave 2 (production MiningController and
load-shedding modes). Every claim below is tied to something
the auditor ran or read first-hand.

## Verdict: PASS WITH NOTES

Defects found: 0. Notes: 8 (N-1 to N-8). One auditor
remediation was made (the Makefile target, section 7), as
authorised by the brief. No Stage 7 production code was
changed by the auditor.

## 1. D6 fix: integration registry and memory overlay

Independently recomputed, not taken from the suite:

- Stage 0 registry (research/EXTREME_RESEARCH/
  EXPERIMENT_REGISTRY.json): 97 entries, status counts
  PROVEN 34, INTEGRATED 28, REJECTED 13, NEW 12,
  EXPERIMENTAL 6, UNDER_INVESTIGATION 2, DEFERRED 2.
- ResearchMemory().integrated_ids() returned exactly 28
  distinct ids, set-equal to the Stage 0 INTEGRATED set
  computed live in the same process (EXP-022, EXP-025,
  EXP-026, EXP-034, EXP-036, EXP-037, EXP-038, EXP-039,
  EXP-030-PHASE-E, EXP-030-PHASE-F, PHASE001-H-1,
  PHASE001-H-5, R-01, R-02, R-03, R-04, R-05, R-06, R-07,
  R-08, R-10, R-12, R-13, R-16, R-17, R-18, R-19, R-20).
  Memory stats in that run: 124 indexed, 0 unparsed, 0
  missing sources. The claim "0 to 28" is confirmed.
- Derivation check: integrations.write_registry() was run
  to a temporary path; the regenerated file is byte
  identical to agent/intelligence/integration_registry.json
  (diff empty, count 28). The derived file is not stale.
- REJECTED protection, adversarially constructed by the
  auditor: a temporary narrative source parsing EXP-014 as
  REJECTED plus a temporary integration registry claiming
  EXP-014 as INTEGRATED. The memory kept EXP-014 at
  REJECTED and integrated_ids() did not contain it. The
  control case (same registry, narrative parse not
  REJECTED) did upgrade to INTEGRATED, so the protection is
  the REJECTED check itself (memory.py
  _apply_integration_registry: status-only overlay, skipped
  when the parse is REJECTED), not an accident of the data.
  In the real tree no id carries both a REJECTED and an
  INTEGRATED entry (checked across all 124 entries).
- Loop gate: a fresh OptimisationLoop over the real memory
  refused a hypothesis keyed on EXP-022 at the hypothesise
  to check-prior transition with an INTEGRATED citation,
  and refused EXP-014 with a REJECTED citation. The
  integrated refusal is additive; the rejected refusal is
  unchanged in shape.

Scope clarification (not a defect): registry ids with no
narrative entry are indexed from the registry itself as
INTEGRATED. For those ids there is no narrative parse to
protect, by construction; the Stage 0 registry is their
source of truth, which is the design stated in
integrations.py.

## 2. C_THREADS removal

- Module surface: gpu.engine has no C_THREADS,
  C_THREADS_TUNED or LAST_PROBE_RATE attribute (checked at
  runtime). The only remaining word C_THREADS in importable
  production code is a comment in scheduler.py recording
  that the global is gone, plus the BAL_C_THREADS
  environment variable name and DEFAULT_C_THREADS, which
  are the documented constructor-time inputs.
  mining/mainnet_live.py now reads engine.last_probe_rate
  (line 228), an instance attribute.
- Remaining references to the removed global: the EXP-045
  historical research scripts (research/sha256d/exp045/,
  asserting engine_mod.C_THREADS) and snapshots under
  .local/ (pre-avx512-integration tree, agent-experiments
  bench). Nothing in gpu/, mining/, agent/ or tests/
  imports them; they are inert. See N-7 for the consequence.
- Instance isolation, run by the auditor: two ComputeEngine
  instances constructed with threads=1 and threads=4 held
  1 and 4 simultaneously; mutating the first instance to 99
  left the second at 4. Default construction on this host
  selected v512dual (probe rate recorded on the instance),
  confirming the dispatch order is unchanged.
- Scheduler: scheduler._measure builds per-(tier, threads)
  throwaway engines through _engine_at_threads and sets no
  shared state (read line by line; the former set/restore
  of the gpu.engine global is gone). The auditor ran two
  _measure calls concurrently (C tier at 1 and 4 threads,
  16,384 hashes each): both completed, the two cached
  engines held 1 and 4 threads respectively afterwards, and
  neither measurement disturbed the other. See N-2.

## 3. Controller safety (line-by-line read plus adversarial runs)

controller.py was read in full. The signal surface is
exactly two os.kill call sites: pid_alive (signal 0, a
liveness probe) and signal_verified (line 332), the single
signalling primitive. Its only production caller is
recover() at line 672, passing signal.SIGTERM and the miner
pid read from the controller's own fresh inspect().
signal_verified refuses unless (a) the pid equals the pid
the autopilot currently publishes for that kind in
heartbeat.json (or the lock pid for the autopilot kind via
inspect), and (b) the live /proc cmdline of that pid
contains the kind's needle. start and stop send no signals
at all: they go through scripts/autopilot.sh (start, and
the stop file the autopilot polls), and both verify their
postcondition from fresh published state (heartbeat
freshness plus miner_state plus process exit for stop; a
changed miner pid for restart). A verification timeout is
reported as failure with verified False.

Adversarial runs by the auditor against isolated instances
whose heartbeat named a decoy sleep process:

- signal_verified(decoy_pid, SIGTERM, "miner") where the
  heartbeat published the decoy as miner_pid: refused
  (cmdline "sleep 120" does not verify); the decoy was
  still alive afterwards.
- signal_verified with a caller-supplied pid the autopilot
  does not publish: refused; that process was not signalled.
- recover() with the decoy published as both autopilot and
  miner pid, miner_state exited: returned ok False, status
  refused, detail stating nothing was signalled; the decoy
  survived.
- recover() with a dead autopilot pid and no autopilot
  script: returned ok False, status failed, with the script
  error in the detail; nothing was signalled.
- stop() against the decoy instance: returned ok False,
  status failed (autopilot process did not exit inside the
  window); the decoy survived. Stop reports failure, never
  success, when its postcondition does not materialise.
- A controller pointed at an empty directory (no script):
  start() returned ok False, status failed, verified False
  (also covered by the suite).

The suite's own isolated lifecycle (real autopilot copy,
stub miner) passed in the auditor's runs: start verifies,
second start reports already running, a verified miner
signal triggers the watchdog relaunch with a new pid,
restart verifies a pid change, a correctness fault halts
and leaves the miner running, stop verifies the exit, and
autopilot-down recovery restarts and verifies.

Recovery taxonomy, read and exercised: correctness_failure
halts with status halted and no action; restart count at or
beyond CRASH_LOOP_CAP (10) with the miner down halts as a
crash loop (suite fabricates restarts 99; the auditor
confirmed the classification code path in classify_fault);
miner_down waits for the autopilot watchdog first and only
then attempts the verified signal; autopilot_down starts
through the script and verifies.

Live safety: the live stack was only ever read. The
read-only CLI (python3 -m agent.intelligence control-status)
reported autopilot pid verified (cmdline mining/autopilot.py)
and miner pid verified (mining/mainnet_live.py), running
true. No live process was started, stopped, restarted or
signalled by the auditor.

## 4. Honesty of the refused operations

Through MiningInterface against an isolated instance, and
directly against MiningController:

- adjust_workers(3): ok False, status restart_required,
  detail stating the count was NOT applied and why
  (launch-time only). adjust_workers(0): ok False, status
  refused. The isolated instance's .local directory was
  byte-for-byte unchanged (same empty file set before and
  after) and inspect() showed no change.
- refresh_job(): ok False, status unsupported, both through
  the interface and the controller, with the push-driven
  job supply reason.
- select_backend: two distinct, both honest, operations
  share this name. See N-1. The controller's select_backend
  (the applying operation) returned ok False, status
  unsupported, stating no pin can be honoured by the
  current production path and pointing at the interface
  decision. The interface's select_backend (the L2
  eligibility decision, spec mutates_production False)
  returned a BackendSelection with eligible True for v512,
  v512dual, auto, c and hashlib on this host and started
  nothing. Neither applies a pin; neither claims an effect
  it did not have.
- checkpoint(): honestly reports no GBT checkpoint on the
  pool path, and reads the real frontier when a
  WorkCheckpoint file exists (suite-verified, frontier
  nonce 12345 round trip).

## 5. Modes

The auditor drove ModeManager directly with synthetic
signals and a fake clock, independent of the suite:

- Entry: one sample at load_ratio 2.0 held NORMAL; the
  second consecutive sample entered BROWNOUT
  (ENTRY_CONFIRM_SAMPLES 2 confirmed).
- Oscillation: alternating clear (0.5) and trigger (2.0)
  samples held BROWNOUT across three cycles; no flap.
- Exit: a clear held 299 s of the 300 s window held
  BROWNOUT; at 300 s it stepped down exactly one level.
- Escalation and step-down: two samples at 3.5 entered
  CRITICAL directly; a sustained clear stepped CRITICAL to
  BROWNOUT, and a second sustained clear stepped BROWNOUT
  to NORMAL. Never two levels at once.
- Rate trigger: first observed rate 20 MH/s became the
  baseline; two samples at 14 MH/s (ratio 0.70) entered
  BROWNOUT. Absent signals held the mode (absence is not
  recovery), per _clear_for_current returning False when
  both ratios are None.
- Thresholds in code match the brief: load ratios 1.5 and
  3.0 against EFFECTIVE_CPUS_EXP031 2.0, rate ratios 0.75
  and 0.50, clear ratios 1.2 and 0.85, exit window 300 s.
- Gates actually refuse: in BROWNOUT the suite's facade
  test shows ExperimentRunner.create_experiment raising
  ModeRefusal, Scheduler.bake_off raising ModeRefusal, and
  the loop transition into isolated_implementation raising
  LoopRefusal; in CRITICAL, run_command refuses at the next
  command boundary (the wind-down recheck in
  experiments.run_command). The auditor re-ran that suite
  in full (section 8). Awareness in CRITICAL returns a
  minimal snapshot-only cycle (suite-verified; the
  auditor also read observe_cycle's critical branch).
- No mining impact: modes.py contains no signal, subprocess
  or process-control code at all (grep-verified); a
  transition only persists its own JSON state, writes an
  audit record, and invokes registered callbacks, each
  wrapped so a callback exception cannot propagate. The
  mode gate in loop.py, experiments.py and scheduler.py can
  only refuse agent-side discretionary work. Nothing in a
  transition path touches the miner, autopilot or node.

## 6. Permissions, gates and the Prompt 1 evidence gate

- Registry: ACTION_REGISTRY holds 24 specs (11 L1, 10 L2,
  3 L3), matching the brief. Every controller operation is
  present at the claimed level: inspect_status L1,
  checkpoint_status L1, start_mining L2, stop_mining L2,
  restart_mining L2, select_backend L2, adjust_workers L2,
  refresh_job L2, trigger_recovery L2, all kind operational
  and shell False. The controller's _gate calls use exactly
  those names; the interface gates before delegating and
  writes an audit record for each controlled call (the
  suite asserts start_mining and stop_mining appear in the
  audit log; the auditor's own interface calls produced
  audit records with outcomes restart_required and
  unsupported).
- L1 refusal, run by the auditor: a PermissionChecker at L1
  refused start_mining and adjust_workers through the
  interface with PermissionError naming the required L2.
- Prompt 1 strict gate, probed by the auditor: an evidence
  bundle whose independent record was schema-valid but
  unsigned was refused by validate_integrate_evidence with
  exactly one missing item, the invalid signature. Records
  with passed as the string "false" or the integer 1 were
  refused as not Boolean. The full security suite passed
  (section 8), so the gate's behaviour is unchanged by
  Stage 7. loop.py's new mode gate sits before the evidence
  gates in advance() and can only add refusals for the
  three discretionary states; it does not alter
  validate_integrate_evidence.

## 7. Auditor remediation (Makefile, authorised by the brief)

tests/test_agent_controller_modes.py had no Makefile
target, so make test-all did not cover it. The auditor
added, following the existing target style:

    test-agent-controller:
        python3 tests/test_agent_controller_modes.py

and appended test-agent-controller to the test-all
dependency list. test-all now names 39 targets (38 existing
plus this one). This change is an auditor remediation, not
an author change, and it is the only file the auditor
modified besides this report.

## 8. Full regression (strictly sequential)

Host AMD EPYC 9D25. The auditor ran make test-all, which
passed 11 targets in order (test, test-regtest, test-engine,
test-pow, test-gpu, test-gpu-correction, test-mining,
test-adversarial, test-deepening, test-cpu,
test-cpu-correction) and then stopped at test-rtl, as make
does on first failure. The remaining 27 targets were then
run one at a time in Makefile order. Results the auditor
personally observed:

- Passed (37 of 39): all of the above 11, plus test-solo,
  test-solo-vardiff (59 of 59), test-solo-cutover,
  test-research, test-judgement, test-installer,
  test-task003, test-task0038, test-task0039, test-avx512,
  test-avx512dual, test-mainnet-live, test-template-cache,
  test-avx512flags, test-exp036, test-exp034, test-exp037,
  test-exp038, test-probability (73 checks), test-exp039,
  test-exp040, test-agent-intelligence (106 checks),
  test-agent-awareness (51 checks this run; the node RPC
  answered, so the conditional check ran: discrepancy D8
  behaving exactly as recorded), test-agent-operations
  (10,309 checks), test-agent-security (116 checks),
  test-agent-controller (72 checks, run three times by the
  auditor: directly, in the sequential pass, and in the
  systemd rerun below; 72 every time).
- test-rtl FAILED: iverilog not found. Pre-existing
  environment failure (no Verilog simulator on this host),
  unrelated to Stage 7, which touches no RTL.
- test-autopilot FAILED (exit 2): confirmed as the known
  environment precondition failure, not a Stage 7 defect.
  Evidence: .local/autopilot.lock was a 0-byte file during
  the run (the live autopilot holds the flock but leaves
  the file empty, verified by listing), so the suite's skip
  branch, which reads a pid from that file, raised
  ValueError, was caught, and did not skip. The suite then
  observed the LIVE heartbeat (its failure message shows
  autopilot_pid 3788, the live autopilot, miner running)
  instead of a stub miner restart, and its assertion
  failed. Stage 7 changed no autopilot code and no part of
  this path.
- Interruption and rerun, recorded honestly: the first
  sequential pass reached test-agent-security when a
  runtime restart at about 12:05 UTC killed the pass and
  the exec file-write block recurred (shell and Python
  writes from the exec sandbox failed with Operation not
  permitted / 0-byte files; reads were unaffected). The
  keeper restored the live stack under new pids. The
  auditor reran test-agent-security and
  test-agent-controller through a systemd unit
  (systemd-launched processes write normally): security
  116 checks PASSED, controller 72 checks PASSED. Both
  suites therefore have clean, complete, auditor-observed
  passes.

## 9. Live safety and shares

Live controller use was read-only only (status and mode
CLIs, file reads). The auditor never started, stopped,
restarted or signalled the live miner, autopilot or node.

- Before: 2026-11-16 11:37 UTC, heartbeat autopilot 3788,
  miner 3817, shares_accepted_total 528; evidence census
  accepted 528, rejected 8.
- After: 2026-11-16 12:10 UTC, heartbeat autopilot 44878,
  miner 44884, shares_accepted_total 536; census accepted
  536, rejected 8.
- The pid changes are environment, per the brief: the
  original miner was restarted once by its own autopilot
  under load (restarts 1, miner 24966 at 11:44 UTC), and
  the runtime restart at about 12:05 UTC replaced the
  autopilot, whose keeper-restored successor (44878)
  launched miner 44884. The orphaned miner 24966 exited on
  its own between the auditor's 12:06 and 12:10 checks; the
  auditor did not signal it. Shares advanced 528 to 536
  across the audit; rejected stayed 8. No mainnet block is
  claimed; the success criterion is untouched by Stage 7.

## 10. Scans

Every Stage 7 changed file the auditor inspected (the
integrations, memory, loop, controller, modes, permissions,
interface, scheduler, experiments, awareness, __init__ and
__main__ modules, gpu/engine.py, mining/mainnet_live.py,
mining/cpu/miner.py, the load_probe tool, the four migrated
test files, the new controller/modes suite, and the
Makefile) scans clean for the U+2014 character (zero hits)
and contains no credential, key or RPC secret material
(grep for rpcpassword, private key and WIF patterns: no
hits in the Stage 7 production files).

## Notes

- N-1: select_backend names two operations. The interface
  operation is an eligibility decision (mutates nothing,
  documented in its spec); the controller operation is the
  application of a pin and refuses as unsupported. Both are
  honest, but a reader of the Stage 7 claim "select_backend
  refused as unsupported" should know it is the controller
  result; through the interface the same name returns a
  BackendSelection. A future rename of one of them would
  remove the ambiguity.
- N-2: scheduler._measure_engines is a plain dict with no
  lock. Concurrent calls for the SAME (tier, threads) key
  could both construct an engine and one would overwrite
  the other; the values are identical in thread count, so
  the race is benign, and different keys (the case the
  brief asked about) do not interfere, as measured. No
  shared production state is mutated either way.
- N-3: MiningController gates only when constructed with a
  checker (its _gate is a no-op when checker is None). The
  shipped wiring is safe: the Agent facade passes its
  checker and audit to the default controller, and
  MiningInterface gates independently before delegating, so
  both production entry paths enforce permissions and write
  audit records (with the facade wiring, a controlled call
  is audited at both layers). A future caller constructing
  a bare controller and invoking it directly would bypass
  the permission layer; the type is documented as taking
  optional wiring, and this audit records the property so
  it is a known, not a silent, surface.
- N-4: ModeManager._save swallows OSError silently, so a
  persistence failure (for example during an exec write
  block) leaves the in-memory mode correct but the on-disk
  state stale, with no signal. The fail direction is safe
  (the live mode still gates work), but a counter or audit
  note on save failure would make it visible.
- N-5: test-agent-security now reports 116 checks, up from
  the Prompt 1 era 112. The suite grew; the auditor
  observed 116 passing and no Prompt 1 check was removed
  or weakened that this audit probed (section 6).
- N-6: the default ComputeEngine thread probe returned
  different tuned counts (1, 2, 4, 8) across constructions
  during the audit, under heavy and varying test load. That
  is the per-instance probe measuring a contended machine,
  as designed; it is recorded here so nobody mistakes the
  variance for shared-state leakage, which section 2
  disproved directly.
- N-7: the EXP-045 historical scripts under
  research/sha256d/exp045/ still assert the removed
  gpu.engine.C_THREADS global and would fail if re-run
  today. They were deliberately not migrated (brief) and
  are inert, but they are no longer runnable as-is; a
  future EXP-045 reproduction must port them to the
  constructor threads argument first.
- N-8: plain make test-all still halts at the first
  failing target (test-rtl on this host), so the new
  test-agent-controller target, being last, is only reached
  by a full make run on a host where every earlier target
  passes, or by running the remaining targets individually
  as this audit did. That is make semantics, not a Stage 7
  defect, but it means CI-style coverage of the new suite
  depends on the rtl environment being fixed or the target
  being invoked directly.

## Left unverified

- Behaviour on any other host (the SHA-less Intel host and
  AVX2-only hosts remain host-gated, as before; nothing in
  Stage 7 changes that register).
- The controller's start/stop/restart against the LIVE
  stack: deliberately never exercised; only the isolated
  real-autopilot copy was driven, plus read-only live
  status.
- Multi-machine anything: Stage 7 is single-machine, and
  no fleet agent was activated.
- The security and controller suites' first sequential-pass
  attempt was interrupted by the runtime restart (section
  8); their verdicts rest on the clean systemd reruns and,
  for the controller suite, two additional direct passes.
