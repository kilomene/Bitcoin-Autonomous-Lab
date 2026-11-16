# Stage 8: Autonomous Agent-Directed Mining Demonstration

Date: 2026-11-16. Host: AMD EPYC 9D25 guest (AVX-512F/BW,
SHA-NI present), about 2 effective CPUs (EXP-031), heavily
contended throughout (live mainnet miner, keeper and test
suites sharing the VM; 1-minute load average between about
5 and about 20 across the runs).

Scope: Directive 5 Stage 8 (Directive 4 Prompt 6 substance):
an integrated demonstration in which the agent layer
(agent/intelligence/) is the decision-maker for a complete
mining operation on REGTEST, executed end to end through the
agent's own machinery: awareness, research memory and the
gated optimisation loop, the TaskRegistry planner, the
permissions-gated typed interface, the production
MiningController (Stage 7), and the EXP-036 verification
gate, against the real regtest node and the production
MiningEngine / ComputeEngine code.

Driver: research/EXTREME_RESEARCH/stage8_demonstration.py.
Miner child for the isolated instance:
research/EXTREME_RESEARCH/stage8_regtest_miner.py.
Machine-readable evidence (run 2, the recorded
demonstration): research/EXTREME_RESEARCH/
stage8_evidence.json. Run 1 evidence preserved at
research/EXTREME_RESEARCH/stage8_evidence_run1.json.
Suite: tests/test_stage8_demonstration.py (Makefile target
test-stage8, appended to test-all, which now names 40
targets).

Work is local only; nothing was pushed. Remote HEAD remains
78a061e5385e86b953801af51b49bf5d57d72243 (Stage 7).

## Safety posture, and how it was kept

- The live mainnet stack (production autopilot, miner and
  mainnet node) was never signalled, restarted, stopped or
  reconfigured. The demonstration's only contact with it was
  reading evidence/mainnet-live.jsonl.
- Share census (accepted / rejected, full-log count of
  evidence/mainnet-live.jsonl): run 1 window 539 / 8 before
  and 539 / 8 after (unchanged). Run 2 window 544 / 8 before
  and 545 / 8 after: the +1 is the live miner's own pool
  share, accepted at 2026-11-16T12:47:19Z inside the run 2
  window (further live shares at 12:49:53Z and 12:50:09Z,
  after the window, show the cadence). It is not a
  demonstration effect: every mutating operation the
  demonstration performed targeted the isolated instance,
  and the demonstration's miner mined regtest blocks to a
  bcrt1 address recorded in the isolated instance's own
  evidence log. Census at report time: 551 / 8, the live
  miner having continued throughout.
- All mutating control ran against an ISOLATED autopilot
  instance (copied mining/autopilot.py and
  scripts/autopilot.sh, own .local, own evidence directory)
  under .local/stage8/<run-id>/iso/, exactly the Stage 7
  controller-suite isolation pattern. The only signal sent
  anywhere went through MiningController.signal_verified to
  the isolated miner pid it had itself verified.

## Environment incidents during this stage (recorded, not hidden)

1. The exec write block of 2026-11-15 recurred (about
   12:05 UTC): processes launched from the agent exec
   channel could create files but not write contents
   (0-byte results, exit 120), while systemd-launched
   processes wrote normally. Both demonstration runs and
   all six suite runs were therefore launched as systemd
   units (unit files written through the file tool;
   systemd-run itself refused exec sessions with "Failed to
   connect to bus" during this window, so units were
   started with systemctl). This is an environment property
   of the VM, not a property of the code under test.
2. The primary regtest node died in the about 12:05 UTC
   runtime restart. Its settings.json was left at 0 bytes
   by the same incident, and bitcoind refused to start
   ("Settings file could not be read ... does not contain
   valid JSON"). Following Core's own prescribed remedy,
   the corrupt file was preserved as
   settings.json.corrupt-20261116 in the same directory and
   the node was restarted as the systemd unit
   bal-regtest-node. The block index rolled back to height
   1783 (blocks 1784 to 1830, mined by Stage 7 audit test
   runs, exist in the block files but not in the index; the
   node is self-consistent at 1783). All heights in this
   report are post-repair heights. The bal-regtest and
   bal-watchonly wallets were reloaded explicitly; the
   demonstration miner's ensure_wallet would have loaded
   bal-regtest on its own in any case.
3. Run 1 exposed a real observability gap (next section);
   the miner was fixed and run 2 is the recorded
   demonstration.

## The two runs

Run 1 (2026-11-16T12:33:42Z to about 12:38:24Z): all ten
steps executed, zero failures recorded, 3 regtest blocks
(heights 1784 to 1786; first block height 1784, hash
00000028eea8192b0f6dfdac311593f062a64822d767c2a1d49798b4f50be167,
nonce 54476361), 74,946,144 unique nonces across two miner
sessions, bake-off winner v512dual at 10,257,280 H/s,
EXP-036 verification passed, fault and halt behaviour as in
run 2. BUT both awareness rate windows (25 s in step 5,
20 s in step 9) returned no rate: the GBT miner published
statistics only when a search cycle completed, and under
this contention a cycle ran for minutes, so no two distinct
status events bracketed either window. The mandated
measurement (unique hash rate through the awareness
surfaces) was therefore NOT obtained in run 1.

Fix: the miner gained a StatusPublisher thread that
republishes the MiningStatistics totals every 10 s, the
cadence mining/mainnet_live.py uses on the pool path. The
production GBT path itself (MiningEngine and its other
callers) has no equivalent publisher; that remains future
work and is listed under Limitations.

Run 2 (2026-11-16T12:45:44Z to 12:47:50Z), with the
publisher: every measurement below is from run 2 unless
stated. Zero failures, no exception.

## Step-by-step outcomes (run 2)

1. Inspect. The agent's awareness snapshot opened the run:
   mode normal; regtest node reachable, blocks 1786,
   headers 1786, not in initial block download; the
   isolated autopilot not yet running; the interface's
   status view agreed (not running). The agent also probed
   the production backends through its interface (the
   dispatch selected v512dual on this host).
2. Research-memory gates. Two probe hypotheses were pushed
   through the optimisation loop's hypothesise gate and
   both were refused with citations, which is the evidence
   the gate works: "K+W constant folding..." refused citing
   EXP-014 (REJECTED), and "a dual-batch masked search
   backend (v512dual)..." refused citing EXP-026
   (INTEGRATED). Neither probe advanced past the gate.
3. Plan. A TaskRegistry plan of 10 tasks was created: the
   strategic task stage8-demonstration (required evidence:
   final_accounting) and execution tasks s8-inspect,
   s8-memory, s8-start, s8-mine, s8-verify, s8-fault,
   s8-experiment, s8-modes, s8-stop, each with named
   required evidence and dependencies (start after inspect,
   mine after start, verify and fault after mine, stop
   after verify/fault/experiment/modes). All 10 closed in
   state done with their required evidence attached (the
   persisted registry is in the run's state directory; an
   11th record, live-awareness-observe, is the awareness
   layer's own bookkeeping task and stays active by
   design).
4. Start. agent.interface.start_mining() (L2, permission
   gated, audit logged) drove the production
   MiningController against the isolated instance: result
   ok, verified, "autopilot and miner verified running
   from the heartbeat". The miner child is the Stage 8
   regtest miner: production MiningEngine over the real
   ComputeEngine (backend v512dual), GBT against the
   regtest node, paying the lab regtest wallet.
5. Mine and observe. Progress was observed only through
   awareness snapshots and the statistics surfaces. The
   chain advanced from 1786; first block observed at
   height 1787. Measurements in the next section.
6. Verify. The block at height 1787 (hash
   000000095e949f9ad251676d73c26f4b402a4c19535b4b2caf5052448a963415,
   nonce 20380859, found after 20,372,672 attempted hashes
   in its cycle) was verified three ways, all agreeing:
   the interface's EXP-036 operation classified it
   block_candidate (digests agree between hashlib and the
   pure-Python reference, meets the network target);
   a direct mining.candidate_verify.verify_candidate call
   returned the identical verdict and value; and
   verify_chain_acceptance against the node returned
   ("tip", accepted True): best-chain membership by hash
   equality.
7. Fault and recovery. The isolated miner was killed
   through the controller's verified signal path
   (signal_verified returned True; no unverified pid was
   ever signalled). recover()'s own inspect still saw
   the pre-kill miner (pid 100761) alive and verified, so
   recover() classified the state as no fault and
   reported ok with nothing recovered; the isolated
   autopilot's watchdog relaunched the miner afterward,
   observed by the driver's poll and independently
   evidenced (new miner pid 106509, heartbeat restarts 1). The controller's
   miner_down recovery branch was therefore not the branch
   exercised here; it is covered end to end by the Stage 7
   suite on the same isolation pattern. A declared
   correctness fault was then exercised:
   trigger_recovery(correctness_failure=True) returned
   status halted, and the relaunched stack was verified
   untouched (still running, same pid). The miner's work
   checkpoint was read back through the controller: a
   frontier exists (extranonce 0, nonce 18808832) and is
   honestly incomplete, i.e. unfinished work is recorded
   as unfinished.
8. Bounded experiment. The agent ran the scheduler
   bake-off on this machine (7 tiers, 262,144-hash
   workloads, 3 repetitions, 2 threads): winner v512 at a
   median 3,437,058 H/s, v512dual second at 3,316,866 H/s
   (a 3.6 percent margin, inside the contention noise the
   run rows show; run 1's bake-off picked v512dual at
   10,257,280 H/s; no dispatch conclusion is drawn from
   either). The result was then put through the
   ExperimentRunner as a bounded experiment: an independent
   recompute of the winner from the recorded rows ran
   inside the Prompt 1 OS sandbox (exit 0, 11.5 s wall),
   the verifier service signed the evidence, and the
   strict evidence gate returned integrated (no missing
   fields) with the hash-chained ledger verified (4
   records, chain intact, anchor verified). Production
   effect: NONE, by design and stated in the evidence: the
   gate decides eligibility for the record; no backend pin
   mechanism exists in the production miner (the
   controller's select_backend is refused as unsupported),
   so nothing in production dispatch changed.
9. Modes. One awareness observe_cycle ran against the
   relaunched miner with real signals: backend rate
   628,883 H/s over the 20 s window; degradation flag
   restarts_present (the deliberate step 7 fault, correctly
   visible); the mode machine consumed load1 5.361 over
   2.0 effective CPUs (load ratio 2.681, above the Brownout
   threshold of 1.5) and set its rate baseline from this
   first observation (rate ratio 1.0). Mode before and
   after: normal. NO transition fired, and the evidence
   shows why: mode entry requires 2 consecutive qualifying
   samples and this was the first sample. Nothing was
   forced synthetically in the production path; synthetic
   transition drives are covered by the Stage 7 suite.
10. Stop and accounting. interface.stop_mining() returned
    ok and verified (autopilot process exited, heartbeat no
    longer reports a running miner); a final inspect
    confirmed the isolated instance down. Final accounting
    from the isolated instance's own evidence log: 2 miner
    sessions; summed session totals (summed across
    sessions, never merged into a single miner's counters):
    backend_hashes 68,159,104; unique_nonces 68,159,104;
    actual_computations 68,159,104; unique_coverage
    68,026,368; repeated_work 0; blocks_submitted 4,
    blocks_accepted 4, blocks_rejected 0. The miner
    recorded 4 blocks and the node height delta over the
    run was exactly 4 (1786 to 1790): the counts match.

## Measurements (formulas applied, everything labelled)

All figures in this section are REGTEST-DEMONSTRATION
figures from the production code path under heavy
contention. None is a mainnet result.

Target probability. The regtest target in force (nbits
0x207fffff) is T =
57896037716911750921221705069588091649609539881711309849342236841432341020672.
p = (T + 1) / 2^256 = 0.49999994 per hash. Expected hashes
per block at the true target: 2.0000002384. The
demonstration miner's compute proxy divides the search
target by 2^24 (the EXP-040 amplification harness), giving
an amplified expectation of 33,554,436 hashes per block;
the network target itself is never modified, and every
block found is a genuine regtest block (Core accepted all
4). Observed draws (20.4M, and session totals below) are
consistent with that expectation.

Unique hash rate (the mandated measurement). From two
awareness coverage samples bracketing a window inside
session 1: unique_nonces rose 20,372,672 to 37,084,352, a
delta of 16,711,680 unique nonces over 23.202 s of
status-event timestamps:
unique rate = 16,711,680 / 23.202 = 720,260 H/s.
The awareness rate_observation over its own 25 s window
computed the identical figure (720,260 H/s) from the same
counters independently. Repeated computations in the
window: 0 (reported separately, never added).

Session rates (same formula, miner_start to last status
event of each session): session 1: 37,084,352 unique over
50.0 s = 741,574 H/s, 1 block. Session 2 (after the fault
relaunch): 31,074,752 unique over 54.7 s = 567,817 H/s,
3 blocks. Summed: 68,159,104 unique over 104.7 s of summed
session spans = 650,994 H/s. Step 9's observe cycle
measured 628,883 H/s over its own window. These are
contended figures: the same backend's standalone probes on
this VM measure 9 to 38 MH/s; the demonstration shared the
VM with the live mainnet miner and the rest of the stack,
and the numbers say so.

Progress toward the targets (from the headline verified
unique rate, 720,260 H/s):
Progress_500 = 720,260 / 500,000,000,000 x 100 =
0.000144 percent of 500 GH/s (gap factor 694,194x).
Progress_140T = 720,260 / 140,000,000,000,000 x 100 =
0.000000514 percent of 140 TH/s.
Both targets stand at full height; this demonstration is
an intermediate systems result, not a performance claim.

## Autonomy levels: what this demonstration evidences

- Agent-assisted: EVIDENCED. The agent's inspection,
  verification and accounting surfaces carried the
  operation's information flow (awareness snapshots,
  EXP-036 verdicts, separated statistics), with the
  demonstration driver as the operator.
- Agent-controlled: EVIDENCED on regtest. Start, stop and
  recovery operations executed through the
  permissions-gated interface and the production
  MiningController, with verified postconditions and an
  audit trail, against an isolated instance running the
  production mining path.
- Autonomous research: PARTIALLY EVIDENCED. The
  research-memory gate consultations and the evidence-
  gated planning machinery operated exactly as designed
  (two cited refusals; a 10-task plan closed on evidence).
  The demonstration's agenda, however, was set by the
  driver script, not originated by the agent's own
  strategy loop. The machinery of autonomous research ran;
  self-directed agenda-setting was not demonstrated.
- Autonomous optimisation: PARTIALLY EVIDENCED. A real
  measurement (bake-off), a sandboxed independent
  recompute, verifier-signed evidence and a strict-gate
  decision all ran end to end. The experiment topic was
  chosen by the driver, and the gate's favourable verdict
  has no production effect by design (no pin mechanism
  exists), so no optimisation was autonomously integrated
  into production.
- Autonomous production mining: NOT DEMONSTRATED. The live
  mainnet stack was never under agent control at any
  point; it ran untouched and was only read. A regtest run
  cannot evidence mainnet production autonomy, and this
  report does not claim it.

## Limitations, at full strength

- Regtest only, with the search target amplified inside
  the compute proxy (EXP-040 harness shape). The blocks
  are real regtest blocks; nothing here measures mainnet
  difficulty behaviour.
- The controller's miner_down recovery branch was not the
  branch exercised: the autopilot watchdog relaunched the
  miner in both runs, and recover() honestly classified
  no-fault on the state its inspect observed. The branch
  itself is covered by the Stage 7 suite, not by this
  demonstration.
- No mode transition fired. One observe_cycle produced one
  qualifying load sample; entry requires two consecutive
  samples. Live mode behaviour over sustained load remains
  unexercised on any real stack.
- Rates are contention-dominated (roughly 0.57 to
  0.74 MH/s unique against standalone probes of 9 to
  38 MH/s for the same backend) and are single-host,
  single-run figures. The bake-off winner differed between
  the two runs with margins inside noise.
- The awareness observability gap found in run 1 is fixed
  only in the demonstration miner. The production GBT path
  still publishes statistics per completed cycle (the pool
  path republishes every 10 s), so awareness rate windows
  over a production GBT miner can still starve the same
  way. Recorded as future work, not fixed here.
- The regtest chain this stage ran on had just been
  rolled back to 1783 by an environment incident (above);
  heights are post-repair and the pre-repair blocks 1784
  to 1830 are not in the index.
- Everything ran under the exec write block incident;
  launches went through systemd units. No conclusion in
  this report depends on that, but the run procedure did.

## Suites run after the work (one at a time, via systemd units)

- test-stage8: PASSED, 18 checks (gate refusals with
  citations; interface-driven start/stop on an isolated
  instance with the real Stage 8 miner at amplification
  shift 8; EXP-036 verification of a found block;
  correctness-fault halt; accounting separation).
- test-agent-intelligence: PASSED, 106 checks.
- test-agent-controller: PASSED, 72 checks.
- test-agent-awareness: PASSED, 50 checks (the count is 50
  or 51 depending on whether the node RPC answers during
  the run; standing discrepancy D8).
- test-agent-operations: PASSED, 10,309 checks.
- test-agent-security: PASSED, 116 checks.
The full make test-all was not run in this stage, per the
stage brief; it is the independent audit's step. test-all
now names 40 targets including test-stage8.

## Files created or modified

Created: research/EXTREME_RESEARCH/stage8_demonstration.py,
research/EXTREME_RESEARCH/stage8_regtest_miner.py,
research/EXTREME_RESEARCH/stage8_evidence.json (run 2),
research/EXTREME_RESEARCH/stage8_evidence_run1.json
(run 1, preserved), tests/test_stage8_demonstration.py,
this report.
Modified: Makefile (test-stage8 target, test-all now 40),
docs/AGENT_CAPABILITIES.md (Stage 8 record),
docs/IMPLEMENTATION_ROADMAP.md (F3 marked done with the
Stage 7/8 evidence, original text kept).
Scans: every created/modified file scanned for U+2014
(zero) and for secret patterns (zero hits).

## Final trust-gate verdict

Proven by this stage, with evidence a checker can repeat:
the agent layer can direct a complete mining operation on
regtest entirely through its own machinery, with
permission gating and audit, memory-gate refusals that cite
their grounds, a plan that closes only on evidence,
verified start/stop through the production controller,
blocks verified through the EXP-036 gate and the chain
itself, separated accounting in which unique work,
repeated work and blocks are never conflated, a fault
taxonomy that halts on correctness faults and never
signals an unverified process, and a strict signed
evidence gate deciding an experiment's eligibility. Not
proven: mainnet production authority (never exercised),
self-originated research agendas, production effect from
the optimisation gate, live mode transitions, and anything
about any other machine or the fleet. The success
criterion of the programme (a valid mainnet block) is
unaffected by this stage and remains unmet; the live stack
mined on undisturbed throughout (551 accepted shares at
report time, 0 BTC, no block).
