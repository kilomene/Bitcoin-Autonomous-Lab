# EXP-050: Endpoint health policy (NOVA-ER-0010, register R-26)

Date: 2026-11-16. Host: AMD EPYC 9D25 126-Core Processor
(4 logical CPUs in this guest). Directive 5, Stage 9.
Verdict: HYPOTHESIS SUPPORTED at Gate 3 and Gate 5 scope.
The policy is integrated into production behind a config
switch that defaults to disabled; an independent audit is
owed before any push and before live enablement.

## 1. Research question and hypothesis

Does a named endpoint health policy (ordered endpoints, N
consecutive errors before failover, a timed failback retry
of the primary, with damping) keep the pool leg mining
through endpoint failure and recovery without operator
action and without failback flapping?

Hypothesis (predeclared in the portfolio): with damping
counts taken from the poclbm precedent's model, failover
occurs inside one job interval and failback occurs at most
once per damping window under a flapping primary.

Baseline behaviour: a single endpoint. The Stratum
client's reader loop retries that endpoint once a second
forever; if the process dies (for example a DNS failure at
startup, the 2026-11-15 outage), the autopilot restarts
it. There is no second endpoint anywhere in the system.

## 2. Design

The policy is a named, inspectable object,
EndpointHealthPolicy in mining/endpoint_health.py (name
"ordered-failover-damped-failback", version 1), in the
poclbm tolerance-and-failback tradition: ordered servers,
a tolerance count before a server is judged down, a timed
retry of the primary, failback when it answers. One
addition the precedent lacks: a damping window bounding
failbacks, so a marginal primary cannot flap the session.
The parameters are the lab's declared operating point,
not copied constants.

Semantics, exactly as implemented:

- Endpoints are ordered; index 0 is the primary. The
  policy names exactly one current endpoint at all times.
- note_error() counts consecutive failures against the
  current endpoint. Below error_threshold the decision is
  "retry" (the historical same-endpoint retry). At the
  threshold the decision is "failover" and the current
  endpoint advances in order. When the LAST endpoint also
  reaches the threshold the decision is "exhausted",
  returned once, at the transition: the policy marks
  itself exhausted and points back at the primary, and
  from there the historical behaviour is what remains
  (keep retrying the primary; the autopilot restart is
  the outer backstop). Exhaustion is a reported state,
  never a faked recovery.
- note_success() clears the consecutive count and any
  exhaustion, and reports whether the success ended an
  exhausted episode.
- Failback: while off the primary, failback_due() holds
  once failback_interval_s has passed since the last
  switch or failed probe AND fewer than
  max_failbacks_per_window failbacks completed inside
  the trailing damping_window_s. A due failback is an
  attempt, not a switch: the client probes the primary
  with a throwaway subscribe handshake; only a probe that
  answers moves the session (note_failback, charged to
  the damping window); a failed probe restarts the
  interval (note_probe_failed).

Parameter defaults (mining/endpoint_config.py,
POOL_HEALTH_DEFAULTS): enabled false; fallbacks [];
error_threshold 3; failback_interval_s 300;
damping_window_s 1800; max_failbacks_per_window 1;
probe_timeout_s 5.

The policy is pure decision logic: no sockets, no
threads, an injectable clock, a transitions record and a
status() snapshot (separated counters, never summed).

## 3. Production wiring

Configuration is the switch, in the endpoint_config
style of the solo vardiff integration: a pool_health
section in .local/mining-endpoint.json, merged by
pool_health_config(); pool_policy_endpoints() builds the
ordered list (resolved primary first, then well-formed
fallbacks; malformed entries are skipped, never fatal).
Defaults reproduce today's single-endpoint behaviour
exactly, and the degenerate single-endpoint policy is
the rollback surface.

- mining/stratum_client.py: StratumClient gains an
  optional endpoint_policy attribute. None (the default
  for every existing consumer) is the historical
  behaviour, unchanged. With a policy: connect_initial()
  runs the startup path (policy-ordered attempts, a
  failover retargets at once, exhaustion re-raises so a
  dead-everything startup is still the historical process
  exit into the backstop); the reader loop feeds the drop
  and every failed reconnect to the policy and retargets
  on failover with no sleep; between reads it runs the
  failback probe when due. New evidence events:
  endpoint_failover, endpoint_policy_exhausted,
  endpoint_policy_recovered, endpoint_failback,
  endpoint_failback_probe_failed,
  submits_unresolved_on_reset.
- mining/mainnet_live.py: in pool mode with the policy
  enabled in config, it builds the policy, attaches it,
  logs endpoint_policy_enabled with the full parameter
  set, connects via connect_initial(), and carries
  policy.status() in the periodic status event. Solo
  mode never builds a policy.
- mining/autopilot.py: untouched. Its restart remains
  the outer backstop, exactly as the portfolio requires.

Share accounting across a switch (EXP-037 rule):
_send registers every mining.submit id in a pending
set before the bytes leave; a verdict discards it; a
session reset reports the still-pending ids as
submits_unresolved_on_reset, their own category. A share
is therefore submitted to exactly one endpoint, and every
submitted share ends in exactly one recorded category:
accepted, rejected, or unresolved. The categories are
never summed by the code; the Gate 3 harness checks the
identity arithmetically from the separate records.

## 4. Defect found and fixed during the campaign

The first Gate 3 run failed S1 and S5 on bare asserts,
and the event trace showed why: submits_unresolved_on_reset
fired on a healthy drop whose submits had all been
answered. Pending registration sat in submit() AFTER
_send returned, while the reader thread could process a
fast verdict (and discard the id) before the add executed,
stranding a phantom pending id. Registration now happens
inside _send under the id lock, before sendall, so a
discard can never precede the add. The rerun is clean.
This was a defect in the new EXP-050 code, caught by the
experiment's own gate before integration was declared.

A second harness-side finding, not a production defect:
the Gate 5 stub initially served regtest-style nbits
(207fffff), and the production miner's EXP-036 gate
rejected every candidate as target-above-limit against
POW_LIMIT_MAINNET. The stub now serves mainnet-legal
nbits (1d00ffff); the share target is set by
set_difficulty independently, as on a real pool.

## 5. Gates

Gates 1, 2, 4 and 6 do not apply: the change adds no hash
path and no candidate judging (Gate 1/2 surfaces are
untouched; EXP-036 still judges every candidate on the
live path), makes no performance claim (Gate 4), and
submits no blocks (Gate 6).

### Gate 3: fault injection (passed)

Harness: research/sha256d/exp050/exp050_fault_injection.py;
raw results: RAW_RESULTS/gate3_results.json. Two local
stubs judge shares exactly (header rebuilt from job,
extranonce1, extranonce2, nonce; double SHA-256; integer
target compare). Test parameters: error_threshold 2,
failback interval 2 to 3 s, damping window 60 s, stub job
interval 4.0 s.

- S0 startup failover: primary down at start; the client
  authorized on the fallback; exactly 1 failover.
- S0b startup exhaustion: both down; connect_initial
  raised ConnectionRefusedError, the exhaustion event
  fired exactly once. No faked recovery; the backstop
  shape is intact.
- S1 failover mid-job: primary killed with mining under
  way; the first fallback job arrived 0.084 s after the
  kill, inside one job interval (4.0 s) by a factor of
  about 48. Shares: 2 accepted on the primary before the
  kill, 2 accepted on the fallback after; nothing pending.
- S2 failback on recovery: primary restarted; exactly 1
  failback, after the interval; mining resumed on the
  primary (accepted verdict after failback).
- S3 flapping primary: up 4 s / down 2.5 s for 26 s
  against a 60 s damping window with a budget of 1:
  exactly 1 failback, 2 failovers, and the client held a
  job at the end. The damping bound held.
- S4 exhaustion mid-session: both endpoints killed;
  exhaustion reported once, no recovery event while
  everything was down, the client held no job; when the
  primary returned, endpoint_policy_recovered fired and
  mining resumed (accepted verdict).
- S5 unresolved accounting: primary configured to never
  answer submits; 2 submits pending at the kill were
  reported as unresolved on reset (count 2, their own
  event); after failover, 2 submits accepted on the
  fallback. Recorded categories: submitted 4, accepted
  2, rejected 0, unresolved 2; zero shares submitted to
  both endpoints.

### Gate 5: isolated instance (passed)

Production suite tests/test_exp050_endpoint_health.py,
Gate 5 section: byte copies of the mining/ and gpu/
trees plus the built .local/cpu libraries in a temp
directory, its own .local/mining-endpoint.json (primary
stub A, fallback stub B, policy enabled with threshold
2, failback interval 5 s, damping 60 s), its own
evidence file. The production mainnet_live.py ran the
full sequence: start and mine on the primary; primary
killed, failover event and fallback job followed, the
process alive throughout (no restart, no operator
action); an accepted share on the fallback through the
full production path (ComputeEngine search, EXP-036
confirmation, submit, stub verdict); primary restored,
failback event and primary job followed; stop by SIGTERM
(the autopilot's stop shape). The live tree's evidence
and status files were never touched by the instance.

## 6. Suites

Run one at a time on this host, 2026-11-16:

- make test-exp050: 40 checks, ALL PASSED (policy units
  with a fake clock, config pins, condensed Gate 3,
  Gate 5).
- make test-mainnet-live: ALL PASSED.
- make test-solo: ALL PASSED.
- make test-solo-vardiff: 59/59 checks passed.

Full test-all was not run for this change; the four
suites above cover every touched surface (stratum
client, endpoint config, mainnet_live, and the solo
suites that drive the same client).

## 7. Live stack

Never restarted, signalled or reconfigured. The live
.local/mining-endpoint.json still carries no enabled
policy (the suite pins pool_health_config enabled false
against the live config read). Share census from
evidence/mainnet-live.jsonl (full-log count of
share_result events): 609 accepted / 8 rejected before,
613 accepted / 8 rejected after; the +4 delta is the
live miner's own shares during the campaign window.

## 8. UNVERIFIED register

- Failover against the real public-pool.io endpoint
  (all injection ran against local stubs).
- Any real second endpoint: none exists in the live
  configuration, so the fallback leg has only ever
  pointed at a stub.
- Live enablement: the policy is disabled in the live
  config; enabling it is an operator decision after the
  independent audit.
- The Intel Xeon Platinum 8321HC host (host-gated; the
  policy and client are host-agnostic Python, but
  unmeasured there).
- Two-client behaviour against one fallback endpoint,
  and failback probe behaviour against a pool that
  answers subscribe but never authorizes (the probe
  judges subscribe only; a failback into such an
  endpoint would accrue errors and fail over again,
  damped, but this exact shape was not injected).

## 9. Files

Created: mining/endpoint_health.py;
tests/test_exp050_endpoint_health.py;
research/sha256d/exp050/exp050_fault_injection.py,
EXP050_REPORT.md, RAW_RESULTS/gate3_results.json.
Modified: mining/endpoint_config.py (pool_health
defaults, pool_health_config, pool_policy_endpoints),
mining/stratum_client.py (optional policy wiring,
connect_initial, failback probe, unresolved accounting,
pending registration inside _send), mining/mainnet_live.py
(policy construction and status), Makefile (test-exp050
target, appended to test-all; test-all now names 42
targets). Registry updates: EXP-050 records in
research/sha256d/experiment_registry.md and
research/sha256d/extreme_optimization/EXPERIMENT_REGISTRY.md
(next unreserved EXP-051 in both); the Stage 0 JSON
registry gained the EXP-050 entry (PROVEN) and R-26
moved NEW to INTEGRATED; production integration log
Entry 6 appended. Byte scans: zero U+2014 and zero
secret-pattern hits across every created and edited
file.

## 10. Rollback

Set pool_health enabled false (or remove the section) in
the endpoint config and restart the miner: the client
runs with endpoint_policy None and every behaviour is
the pre-EXP-050 one. The degenerate single-endpoint
configuration (enabled, no fallbacks) is also a valid
rollback state: it adds only the exhaustion report to
the historical retry.
