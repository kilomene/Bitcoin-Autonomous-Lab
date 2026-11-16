# Stage 8 Independent Audit

Date: 2026-11-16. Auditor: independent agent (not the
Stage 8 author). Host during audit: AMD EPYC 9D25 guest
until a VM replacement at about 13:18 UTC, AMD EPYC 9D25
again after (the replacement is an environment event of
this VM, recorded below). Remote HEAD throughout:
78a061e5385e86b953801af51b49bf5d57d72243; Stage 8 is
local and unpushed, and this audit pushed nothing.

## Verdict: PASS WITH NOTES

Defects: 0. Notes: 5 (N-1 to N-5 below). Every material
claim in STAGE8_AUTONOMOUS_DEMONSTRATION.md was tested
against primary sources: the regtest node itself, the
isolated instance's own evidence log, the persisted
TaskRegistry, the agent audit log, the experiment ledger
and its verifier signature, and the controller source.
All recomputations matched.

## What I verified, and how

### Blocks (author claim 2 and 3)

- getblockhash on the regtest node returns, at heights
  1787 to 1790: 000000095e949f...a963415,
  0000007b47dc...f58b2c8, 00000012d1af...0d25112,
  000000228027...ac9a6b780. Height 1787 matches the
  claimed first block hash exactly; height 1790 matches
  the evidence record's last_block. All four sit on the
  best chain (the chain has since advanced past them
  through later suite runs).
- The isolated instance's own evidence log
  (.local/stage8/20261116T124544Z/iso/evidence/
  mainnet-live.jsonl) records exactly these four block
  events with the same hashes and nonces (1787 nonce
  20380859), 4 submitted / 4 accepted / 0 rejected in the
  summed statistics, and the node height delta over the
  run was 1786 to 1790, exactly 4.
- My own call to mining.candidate_verify.verify_candidate
  on the raw 80-byte header of block 1787 returned
  block_candidate, digests_agree True, valid_header True,
  meets_network_target True, value and target identical
  to the evidence record. My own verify_chain_acceptance
  returned (in-chain, True); it was (tip, True) during
  the run, which is the correct earlier reading. The
  interface verdict and the direct verdict in the
  evidence agree field for field.

### Measurements (claim 4): all recompute exactly

- Target from the block itself: T =
  57896037716911750921221705069588091649609539881711309849342236841432341020672
  (nbits 0x207fffff). p = (T + 1) / 2^256 =
  0.4999999403953552 (report: 0.49999994). Expected
  hashes per block 2.0000002384; amplified by 2^24:
  33,554,436. Both match.
- Unique rate: from the isolated log's status events,
  session 1 spans 50.008 s with 37,084,352 unique
  nonces (741,574 H/s) and session 2 spans 54.727 s
  with 31,074,752 (567,817 H/s); summed 68,159,104
  unique, repeated_work 0. The headline window:
  37,084,352 - 20,372,672 = 16,711,680 unique nonces
  over 23.202 s = 720,260 H/s. All figures match the
  report to the digit.
- Progress_500 = 720,260 / 5e11 x 100 = 0.000144
  percent (gap factor 694,194x); Progress_140T =
  0.000000514 percent. Both match, both labelled
  regtest-demonstration figures in the report, and the
  targets are nowhere lowered.

### Machinery routing (claim 1): no back door found

- I read stage8_demonstration.py and
  stage8_regtest_miner.py end to end. Start, stop and
  recovery go through agent.interface operations into
  the production MiningController pointed at the
  isolated instance; the miner child is launched by the
  isolated autopilot (a byte copy of mining/autopilot.py)
  running the production MiningEngine / ComputeEngine
  GBT path. The only search modification is the
  disclosed AmplifiedCompute proxy dividing the search
  target by 2^24 (EXP-040 shape); the network target is
  never modified, and Core accepted all four blocks.
- The persisted TaskRegistry in the run's state
  directory shows all 10 plan tasks in state done, each
  carrying exactly its required evidence; the 11th
  record (live-awareness-observe) is active, as the
  report states.
- The agent audit log for the run (62 entries) shows the
  operations passing through the permission layer:
  start_mining once, stop_mining once, trigger_recovery
  twice, verify_candidate once, create_experiment,
  run_benchmark, loop_advance, awareness_observe. Gate
  refusals for EXP-014 (REJECTED) and EXP-026
  (INTEGRATED) carry their citations in the evidence.

### Fault step (claim 5)

- controller.signal_verified, read line by line, signals
  only a pid that equals the autopilot-published pid for
  its kind AND whose live /proc cmdline matches the
  kind's needles; anything else raises ControllerRefusal
  and signals nothing. The evidence records
  signal_verified_returned true for the isolated miner
  pid 100761, a watchdog relaunch to pid 106509 with
  heartbeat restarts 1, and recover() classifying
  no-fault (its before and after snapshots are the same
  verified-running inspect, which is exactly what the
  recover() source returns on the no-fault branch).
- The declared correctness fault returned status halted
  with the relaunched stack verified untouched (same pid
  106509, still running). The recover() source confirms
  the correctness branch acts on nothing. One wording
  imprecision is recorded as note N-1.

### Experiment step (claim 6)

- I re-verified the ledger with the production code:
  ExperimentRunner.verify_ledger for
  exp-20261116T124656Z-833485 returned (True, "4 records,
  chain intact, anchor verified").
- I re-verified the verifier signature on the
  independent-verification record in evidence-b.json
  with the run's verifier key: signature valid, and the
  signed artifact_sha256 equals the sha256 of the
  recorded bakeoff.json. The strict gate verdict in the
  evidence is integrated with no missing fields.
- attempt_integrate in experiments.py is, by its own
  source, a record decision only; it writes nothing to
  production. The controller's select_backend remains
  refused as unsupported, so the gate pass had no
  production effect, as claimed. (The audit log's
  select_backend entries are the scheduler's eligibility
  decisions, the Stage 7 note N-1 distinction; none
  starts or pins anything.)

### Modes (claim 7)

- The evidence shows one real observe_cycle: load1
  5.361 over 2.0 effective CPUs gives load ratio
  2.6806640625 (recomputed), above the 1.5 Brownout
  threshold; the rate baseline was set from this first
  observation (628,883 H/s); transitions 0; mode normal
  before and after. Consistent with the 2-consecutive-
  sample entry rule in modes.py. Nothing was forced.

### Autonomy accounting (claim 8)

- Agent-assisted: earned (awareness, EXP-036 verdicts
  and separated statistics carried the operation).
- Agent-controlled on regtest: earned. Start, stop and
  recovery executed through the gated interface and the
  production controller with verified postconditions
  and a complete audit trail, against the production
  mining path.
- Autonomous research and autonomous optimisation:
  the partial grading is honest. The machinery ran as
  designed, and the report states plainly that the
  agenda and the experiment topic were driver-chosen
  and that the gate verdict has no production effect.
- Autonomous production mining: the non-claim is stated
  at full strength in the report, in the final
  trust-gate verdict, and in both edited docs.

### Live stack (claim 9)

- Before the audit: autopilot pid 44878, miner pid
  44884, census 553 accepted / 8 rejected (heartbeat
  count; my own full-log count agreed at the end).
- The claimed run 2 census movement is real and is not
  a demonstration effect: the live log contains an
  accepted share_result at 2026-11-16T12:47:19.508Z,
  inside the run 2 window, with further live shares at
  12:49:53Z and 12:50:09Z, exactly as the report says.
- I never signalled, restarted or reconfigured anything
  live. A VM replacement at about 13:18 UTC killed the
  whole live stack mid-audit (an environment event, the
  third such incident recorded in this stage's history);
  the bal-mainnet-keeper restored it under new pids
  (autopilot 2902, miner 2912). After the audit:
  miner running, restarts 0, census 557 accepted /
  8 rejected by full-log count. No stray isolated or
  demonstration processes remain.

### Suites (claim 10) and the full test-all

- tests/test_stage8_demonstration.py, run by me: PASSED,
  18 checks (via a systemd unit; the exec channel's
  write block was active at that moment, the documented
  environment incident).
- Full make test-all (40 targets), run sequentially
  with -k, in two passes because the VM replacement
  terminated pass 1 at target 14:
  - Pass 2 completed all 40 targets. Passing counts
    observed in the log match the author's claims:
    test-agent-intelligence 106, test-agent-operations
    10,309, test-agent-security 116,
    test-agent-controller 72, test-stage8 18, and
    test-agent-awareness 51 in my pass (the author
    recorded 50; the count is RPC-dependent, standing
    discrepancy D8, and both values are within its
    documented behaviour).
  - Failures in pass 2: test-rtl (iverilog absent;
    pre-existing environment failure), test-task003 and
    test-task0038 (both died only in the ASan/LSan
    sub-run with "LeakSanitizer has encountered a fatal
    error... does not work under ptrace", an artifact
    of running under my systemd audit unit), and
    test-exp040 (ModuleNotFoundError: cryptography,
    absent from the systemd unit's clean environment).
    I re-ran all three directly: ALL PASSED
    (test-task0038 with a fresh regtest block at height
    1897, test-task003 at height 1898, test-exp040 all
    scenarios). None is a code failure.
  - Pass 1 additionally showed test-deepening failing
    on a peer-node best-hash race and test-cpu failing
    on regtest RPC submitblock timeouts (one block
    actually accepted, proven by its duplicate response
    on retry): contention artifacts under the combined
    load of that pass; both passed in pass 2.
  - Corrected tally: 39 of 40 targets pass; the sole
    failure is test-rtl on absent iverilog. No Stage 8
    code is implicated in any failure.

### Scans and docs

- All nine Stage 8 created/modified files scan zero
  U+2014 and zero secret-pattern hits (RPC passwords,
  WIF keys, xprv, private-key blocks, API tokens).
- docs/AGENT_CAPABILITIES.md and
  docs/IMPLEMENTATION_ROADMAP.md (F3 marked DONE,
  original text kept) say only what the evidence
  supports: both state the isolated-instance scope and
  that live mainnet control remains an owner decision.

## Notes

- N-1 (wording precision, step 7): the report says the
  watchdog "relaunched the miner before the controller's
  recover() inspected". The evidence shows recover()'s
  own inspect still saw the pre-kill miner (pid 100761)
  alive and verified, and the relaunch (pid 106509) was
  observed by the driver's poll afterward. The material
  facts all hold (kill only through the verified path,
  no-fault classification, relaunch independently
  evidenced, correctness halt untouched); only the
  causal ordering in that one sentence is imprecise.
- N-2 (measurement independence): the headline unique
  rate's two computations (the driver's coverage-sample
  arithmetic and awareness rate_observation) agree
  exactly because both read the same MiningStatistics
  counters and the same bracketing status events. That
  is a consistency check between two code paths, not
  two independent measurements. The figure itself is
  sound and recomputes from the isolated log.
- N-3 (test-all execution): a single uninterrupted
  40-target pass was not achievable in this audit
  window: pass 1 was terminated by the VM replacement
  and pass 2 ran under systemd units whose execution
  context produced three artifacts, each cleared by a
  direct rerun. The tally above is assembled from one
  complete pass plus those reruns, stated openly.
- N-4 (environment): the audit window contained a full
  VM replacement (about 13:18 UTC) that killed the live
  stack, the regtest node and my first test-all pass.
  The keeper restored the live stack; the suites
  restarted the regtest node through node_manager. No
  audit conclusion depends on the interrupted pass.
- N-5 (run 1): I verified the run 1 evidence record for
  consistency (3 blocks at 1784 to 1786, first block
  hash and nonce as reported, 74,946,144 unique nonces,
  census 539/8 unchanged, step 5 rate fields empty,
  bake-off winner v512dual). Run 1's observability gap
  is genuinely in the record, and the report's account
  of it is accurate.

## Unverified register

- The controller's miner_down recovery branch was not
  exercised by the demonstration (the watchdog won the
  race in both runs). It remains covered by the Stage 7
  suite, which passed in this audit's test-all, and by
  the Stage 7 audit; I did not independently re-prove
  that branch beyond the passing suite.
- Live mode transitions over sustained load remain
  unexercised, as the report states.
- I did not re-run the full demonstration end to end;
  I verified its recorded artifacts against the node,
  the logs and the source, and re-ran its suite, which
  re-executes the same machinery at amplification
  shift 8 (one fresh block verified through the gate
  during my run).
- Everything about mainnet vardiff behaviour, other
  hosts, and the fleet is outside this stage's scope
  and remains as unverified as it was before it.

## Bottom line

Stage 8's claims are accurate, including its refusals
to claim: the agent layer directed a complete regtest
mining operation through its own machinery, the four
blocks and every published figure verify against
primary sources, and autonomous production mining on
mainnet is correctly recorded as NOT demonstrated. The
programme's success criterion (a valid mainnet block)
is unaffected and remains unmet: 0 BTC, no block, 557
accepted pool shares at audit end.
