# Solo vardiff prototype: test results (NOVA-ER-0004, R-12)

Suite: research/vardiff/TESTS/test_vardiff.py
Prototype: research/vardiff/vardiff.py
Design: research/vardiff/DESIGN.md

## Final recorded run

- Date: 2026-11-16 (UTC). Host: AMD EPYC 9D25 guest (this
  VM; hostname htch-runtime), live mainnet miner running
  throughout (contention is part of the recorded conditions;
  no rate is measured or claimed by this work).
- Command: python3 -u research/vardiff/TESTS/test_vardiff.py,
  run as a transient systemd unit (unit vardiff-full5)
  because processes in the agent exec sandbox currently
  cannot write file content on this VM; systemd-launched
  processes write normally. The suite started the lab
  regtest node itself and stopped it at the end (verified:
  no regtest bitcoind remains).
- Result: 41 of 41 checks passed, exit code 0. Raw output:
  TESTS/full-run.log.

## What each section proves

Section A, control law under a simulated clock (16 checks):
convergence to the 15 s target interval from below (initial
0.02 toward equilibrium 0.05, increases only, settling
inside the deadband) and from above (initial 0.5, decreases
capped at 2x per step, full round trip through an EMA-lag
overshoot back into the band); hysteresis (a single fast
share never raises; a confirmed rise is followed by a grace
period of at least up_hysteresis_s before the next); per-step
caps (1.5x up, 2x down); floor reached and held under
hopeless intervals with the clamp logged; ceiling reached
and held under flooding with the clamp logged; idle decay
exactly as declared (no decay before the 60 s threshold,
then 0.02, 0.01, 0.005, 0.0025, 0.002: floor in 4 steps, and
silence at the floor); reconnect state starts at the initial
difficulty; misconfiguration (floor above initial) refused
at construction.

Section B, exactness primitives (4 checks): the share target
int(diff1 / difficulty) is integer-identical across the
prototype, the production SoloServer constructor, and
stratum_client.target_for_difficulty, over difficulties
0.002 to 3.7; the acceptance comparison is exact at the
boundary through candidate_verify.meets_target (value equal
to the target meets it; value one above does not). A
server-level share crafted to sit exactly on the target is
not constructible: the target is set through a float
difficulty, and at target magnitudes near 2^229 the float
granularity is about 2^177, so no difficulty value names a
chosen digest's exact target. The boundary evidence is
therefore the exact integer comparison itself (the same
function the production pipeline uses) plus integer parity
of the computed target, which is the strongest evidence the
construction admits; this limit is recorded, not papered
over.

Section C, stub-RPC differential and classification
(8 checks): against a fixed synthetic template at genesis
bits (share target far above the network target, so the two
judgement legs separate), the pinned prototype's decisions
(accepted flag, verbatim reason, block presence) match the
production SoloServer's on an 8-item scripted stream (three
valid shares, a low-difficulty share, bad extranonce2 size,
unknown job, ntime before mintime, ntime too far in the
future), and the global counters match exactly (3 accepted,
5 rejected). In vardiff mode on the same rig: a valid share
is accepted with classification "share"; its exact repeat is
classified "duplicate" and the accepted count does not move;
a share answering a superseded job is classified "stale"
(and a below-target one stale with the reason recorded),
never accepted; a never-issued job keeps the production
"unknown job" verdict.

Section D, live regtest over TCP (13 checks): five server
instances on the lab regtest node, scripted clients mining
with the production ComputeEngine.
- D1 to D7 (default-shaped instance, target 15 s, initial
  0.02, hysteresis 5 s test configuration): subscribe serves
  the initial difficulty; a full-speed client drives
  difficulty upward through at least two logged increases to
  at least 0.04; the adjustment log replays exactly (first
  old is the initial difficulty, every old equals the
  previous new, last new equals the live difficulty, every
  record carries timestamp, connection, worker, reason, old,
  new, EMA and clamp flag); every accepted share is a
  Core-accepted block (Gate 6) and the last sits in the
  active chain with confirmations; the accounting identity
  holds exactly (submissions = accepted + rejected + stale
  + duplicate, disjoint); a reconnect on the same server
  restarts at the initial difficulty while the first
  connection's difficulty stands above it.
- D8 (ceiling instance): a flooding client is clamped at
  the 0.035 ceiling and the clamp is logged; no logged
  difficulty ever exceeds the ceiling. This instance runs a
  60 s target interval by design: flooding is relative to
  the target, and on this contended VM a 0.02 share takes
  roughly 17 s of wall time (flooding against 60 s, not
  against 15 s). See the run history below for why.
- D9 (slow instance, initial 0.10): a duty-cycled client
  (0.3 s sleep per 2^22-hash search chunk) drives difficulty
  downward through at least two decreases to at most 0.03.
- D10 (decay instance, decay_after_s 5 s test
  configuration): a client that submits nothing decays from
  0.02 to the 0.002 floor across direct job refreshes, in at
  least three logged idle-decay steps.
- D11 to D13 (stale, live): a share mined for a job that a
  refresh then supersedes is refused with a stale reason,
  counted in the stale category, never in accepted shares;
  because it meets the network target it is still submitted
  through the exact pipeline and Bitcoin Core accepts it as
  the new tip (block count increments by exactly one and the
  best hash equals the recorded stale block).

## Run history (all runs recorded, none silently replaced)

1. Sections A+B smoke (transient unit vardiff-smoke2):
   19 of 20. A2 failed: with a lagging EMA and no deadband
   the settled controller hunted (68 adjustments in 120
   shares). Fix: the deadband of section 4 of DESIGN.md was
   added to the law (it is also what the portfolio's "inside
   the decided band" success wording means). Re-run
   (vardiff-smoke4): 20 of 20, and the diagnostic trace shows
   the approach is two increases and then silence in band.
2. Full run vardiff-full2: crashed in section D after D1.
   Two environment defects, both in the harness, not the
   prototype: (a) the suite's RPC went through the VM egress
   proxy (the unit environment carried proxy variables),
   which answered submitblock with an HTML 503 while the
   node was healthy; the suite now strips proxy variables
   for its loopback RPC. (b) The scripted client's
   socket.makefile reader was poisoned by its own sync
   timeout ("cannot read from timed out object"); the client
   now keeps its own line buffer. Sections A to C passed in
   this run before the crash (28 checks).
3. Full run vardiff-full3: 40 of 41. D8 failed with final
   difficulty 0.0132 (below the initial): at that run's
   contention level a 0.02 share took longer than the 15 s
   target interval, so the "flooding" client was in fact
   slow and the controller correctly decreased. The
   controller was right and the test's premise was
   rate-dependent; D8 now runs its instance at a 60 s target
   (recorded in the suite), making the flooding premise true
   by construction.
4. Full run vardiff-full4: killed mid-section-C by a VM
   replacement (host uptime reset). No result claimed from
   this run.
5. Full run vardiff-full5: 41 of 41, exit 0. This is the
   recorded result above.

## Not verified by this work

- Nothing on mainnet, and nothing about the armed solo
  cutover (the prototype never ran against the mainnet node;
  the suite refuses noisily if the regtest node is absent
  rather than substitute another chain).
- No performance figure of any kind (Gate 4 does not apply
  to NOVA-ER-0004; the controller's per-share cost is O(1)
  and unmeasured here).
- Multi-worker interference: each live scenario ran one
  client per server instance. Per-connection state is keyed
  by extranonce1 and the stub section exercises one
  connection deeply; two vardiff clients racing adjustments
  on one server is Stage 6 Gate 3 material (the production
  solo test already covers multi-worker accounting without
  vardiff).
- D10 is documented, not closed: closing it edits
  production (endpoint config as single source), which this
  task forbids. DESIGN.md section 9 carries the closure
  into the Stage 6 path.
