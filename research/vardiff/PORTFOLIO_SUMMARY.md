# Portfolio summary: NOVA-ER-0004 solo vardiff (register R-12)

Verdict: SUCCESS at prototype scope. The decided vardiff
design (EXP-030 matrix M10) is implemented as a research
prototype in research/vardiff/vardiff.py, verified through
Gates 1 to 3 and 6 (41 of 41 checks, TEST_RESULTS.md), with
no production file modified and nothing integrated. The
portfolio failure criterion did not occur. One element of
the success criterion, closing discrepancy D10, is by
construction out of reach of a no-production-edits task and
is carried into the Stage 6 path in DESIGN.md section 9;
everything else in the criterion is demonstrated.

## Against the entry's stated criteria

Success criterion: "share interval stays inside the decided
band across predeclared rate steps on regtest, with zero
difficulty influence on candidate verdicts, and D10
closed."

- Interval inside the band across rate steps: MET at the
  level this stage can prove. The control law converges
  into the deadband [12 s, 18.75 s] around the 15 s target
  from below and from above under a simulated clock with
  predeclared step structure (Section A), and on live
  regtest the three directional behaviours are demonstrated
  with real mining: a fast client is raised, a duty-cycled
  slow client is lowered, a flooding client is clamped at
  the ceiling, a silent client decays to the floor
  (Section D). The live runs show direction, band entry and
  the bounds under this VM's contention; they are not a
  rate-stepped stability campaign, and the summary does not
  claim one. The full stepped campaign belongs with the
  Stage 6 integration gates, where the portfolio already
  places Gate 3 and Gate 5.
- Zero difficulty influence on candidate verdicts: MET.
  Separation is by construction (verify_candidate judges
  the network target; difficulty parameterises only the
  share leg) and is tested three ways: the pinned
  differential reproduces production decisions verbatim on
  a scripted stream; the stub rig separates the share and
  network legs and classifies each correctly; live, blocks
  mined at adapted (raised) difficulties are accepted by
  Core exactly as at the initial difficulty, and a stale
  share's block is judged and accepted on the network
  target alone.
- D10 closed: NOT MET, and not closable within this task's
  hard rule (no production edits). The prototype documents
  D10 (DESIGN.md section 2), adopts the operative 0.02 as
  its initial difficulty, and specifies the closure as
  step 3 of the Stage 6 integration path (endpoint config
  as the single source of the initial difficulty).

Failure criterion: "sustained oscillation outside the band,
or any test showing difficulty affecting a candidate
verdict." Neither occurred. One real oscillation WAS found
and fixed during verification: the first control-law draft
hunted at equilibrium (68 adjustments in 120 simulated
shares) because it had no deadband; the deadband is now
part of the law and the settled trace is silent in band.
That is recorded in TEST_RESULTS.md run history, item 1.

## Hypothesis check

The entry's hypothesis: a controller with the recorded
hysteresis holds the share interval within its band across
step changes in worker rate, and never lets difficulty
enter candidate judging. Supported on both halves by the
evidence above, with the live-evidence caveat stated.

## What this unlocks and what remains

- The prototype is the Gate 2/3/6 evidence base for the
  Stage 6 integration specified in DESIGN.md section 9
  (optional vardiff component in mining/solo_server.py,
  endpoint-config parameters, D10 closure, pinned mode as
  the rollback surface). No EXP number is consumed by this
  prototype; per the portfolio, EXP identity is assigned at
  integration candidacy.
- Remaining before integration: the rate-stepped stability
  campaign on regtest at production-shaped worker rates,
  two-client interference on one server, an Intel-host run
  of the suite (this run is AMD EPYC 9D25 only), and the
  independent post-integration audit the standing rule
  requires.
- Rollback posture is unchanged and verified: pinned mode
  is production-identical by construction (it delegates to
  the production submit_share) and by differential test.

## Appendix, 2026-11-16: integrated into production

Status update only; everything above is the prototype
record and is unchanged. R-12 was integrated into
production on 2026-11-16 (Stage 6, item 2), exactly along
the DESIGN.md section 9 path this summary pointed to:
VarDiffController and the per-connection machinery now
live in mining/solo_server.py behind the optional
SoloServer vardiff parameter, the parameters live in
mining/endpoint_config.py, and mining/solo_mainnet.py
wires the controller when the endpoint config enables it.
Discrepancy D10 is closed in the same change: the
constructor default is gone and the endpoint config value
0.02 is the single source of the initial difficulty. The
endpoint config defaults vardiff to disabled, so the
armed solo cutover keeps today's fixed-difficulty
behaviour until an operator enables it after the
independent post-integration audit, which remains owed.

Production evidence: tests/test_solo_vardiff.py (make
test-solo-vardiff), 59 of 59 checks passed on 2026-11-16
on AMD EPYC 9D25: the 41 prototype checks ported to the
production classes, the Gate 2 differential against a
pristine pre-integration copy of solo_server.py from
remote HEAD 3ebbaeb2 (identical jobs, decisions and
counters with vardiff off), Gate 3 adversarial, the
EXP-036 separation at unit and server level, Gate 5 with
vardiff live, and Gate 6 regtest blocks accepted by Core
through both the vardiff-active and pinned default paths
(blocks 1658 to 1679 on the best chain in the recorded
run). Two live convergence instances are declared at
decisive settings (a 60 s target for the fast client, a
heavier duty cycle for the slow client), for a recorded
reason: re-run on this VM on 2026-11-16 under load
average about 16, the prototype's own suite fails its
original two convergence checks while the production
server behaves identically to the prototype, so the
original instances were calibrated to lighter contention
than this VM currently offers. Full record:
research/sha256d/phase6b/PRODUCTION_INTEGRATION_LOG.md,
Entry 5. Still not verified, unchanged from above:
anything on mainnet, two-client interference on one
server, the rate-stepped stability campaign, any other
host.
