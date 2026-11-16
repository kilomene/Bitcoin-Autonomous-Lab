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
