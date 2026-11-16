# EXP-050 independent audit: endpoint health policy (R-26)

Date: 2026-11-16. Host: AMD EPYC 9D25 126-Core Processor.
Auditor: independent of the integration author.
Verdict: PASS WITH NOTES. Defects: 0.
The change is cleared for the push step. Live enablement
remains an operator decision, exactly as the integration
report and Entry 6 state; nothing in this audit enables
the policy on the live stack.

## 1. Defaults safety (verified against remote b8b01ed3)

Remote HEAD confirmed b8b01ed323b180c9cfbdb344ec1a921b1be80987
before diffing. Full unified diffs of the three modified
production files were taken against that commit's blobs
and read hunk by hunk.

- mining/autopilot.py: byte-identical to remote. The
  outer backstop is untouched, as claimed.
- mining/endpoint_config.py: the only changes are
  POOL_HEALTH_DEFAULTS (enabled False, fallbacks []),
  the matching pool_health block inside DEFAULT_CONFIG,
  pool_health_config() and pool_policy_endpoints(). No
  existing constant, section or function body changed.
- mining/stratum_client.py: endpoint_policy defaults to
  None; _send gains a defaulted track_pending flag used
  only by submit(); the reader loop's inline reconnect
  block is refactored into _reconnect(), which with no
  policy is step-for-step the historical loop (same
  endpoint, same 1 s sleep, same events, same exception
  tuple); _policy_note_error and _maybe_failback return
  immediately when no policy is attached;
  connect_initial() with no policy is connect() itself.
- mining/mainnet_live.py: the policy is built only in
  pool mode AND only when pool_health_config reports
  enabled; client.connect() is replaced by
  client.connect_initial(), which is connect() when no
  policy was built; the status event gains an
  endpoint_policy field only when a policy exists. Solo
  mode never builds a policy.
- Consumers: the only assignment of endpoint_policy in
  the tree is mainnet_live.py inside the enabled branch.
  Every other StratumClient consumer (stratum_client's
  own main, the EXP-048 harness, tests/test_judgement,
  tests/test_exp034, tests/test_exp037) runs with the
  policy absent. The Stage 8 demo miner does not use
  StratumClient. Config consumers (solo_server,
  solo_mainnet, solo_cutover, awareness) read named keys
  only and are unaffected by the additive pool_health
  key in load_config() output.
- The live .local/mining-endpoint.json: mtime
  2026-11-14, 241 bytes, keys mode / payout_address /
  pool / solo, no pool_health section. Unchanged.

## 2. Policy semantics (read line by line)

mining/endpoint_health.py imports only time: no sockets,
no threads, injectable clock, as claimed.

- Consecutive counting: note_error increments
  consecutive_errors; note_success resets it to 0 and
  clears exhaustion. Below error_threshold the decision
  is "retry"; at the threshold the current endpoint
  advances in configured order and the decision is
  "failover".
- Exhaustion: on the last endpoint at threshold,
  note_error marks exhausted, points back at the
  primary and returns "exhausted"; while exhausted,
  further errors return "retry", so the decision is
  returned exactly once, at the transition, and is
  never dressed as recovery. Recovery is reported only
  by note_success ending an exhausted episode.
- Failback: failback_due() requires off-primary, not
  exhausted, failback_interval_s elapsed since both the
  last switch and the last failed probe, and fewer than
  max_failbacks_per_window completed failbacks inside
  the trailing damping_window_s. The client probes the
  primary with a throwaway subscribe handshake and only
  a probe that answers calls note_failback; a failed
  probe restarts the interval via note_probe_failed.
  Probe-gated, interval-gated and damping-capped, as
  claimed.
- status() reports separated counters (total_errors,
  total_failovers, total_failbacks, errors_by_endpoint,
  consecutive_errors) and no combined total, per the
  EXP-037 rule.
- The suite's fake-clock unit tests pin each of these
  behaviours, including the damping bound returning
  when the window passes and the degenerate
  single-endpoint policy (retry plus one exhaustion
  report). All passed in my run (section 4).

## 3. The claimed defect fix (pending registration)

_submit registration now happens inside _send, under
the id lock, before sendall; the verdict path discards
the id in _handle. The causal order (register, send,
server verdict, discard) makes a discard preceding its
registration impossible. My own probes, written for
this audit against the production client:

- Case A, verdict during send: a fake socket that
  synchronously delivers an accepting verdict from
  inside sendall. Result: the share_result was logged
  and the pending set was empty afterward. No phantom
  id. Under the pre-fix placement (register after _send
  returned) this exact ordering stranded the id; the
  fix closes it.
- Case B, reset during pending submits: two unanswered
  submits, then _reset_session. Result: exactly one
  submits_unresolved_on_reset event, count 2, the two
  ids; the set cleared; a second reset reported
  nothing. No double reporting.
- Case C, sendall raises: see note N-2.

Across all probes and both Gate 3 runs: zero double
submissions; every submitted share lands in exactly
one of accepted, rejected or unresolved.

## 4. Gates (auditor reruns)

- make test-exp050: ALL 40 CHECKS PASSED on my run,
  including the Gate 5 section (checks 35 to 40).
- Gate 3 harness rerun: the harness writes its results
  JSON next to itself, so it was rerun from a mirrored
  tree under /tmp (imports resolving to the production
  code) to preserve the author's recorded artifact.
  Fresh run: all 7 scenarios PASS. Every assertion
  matches the recorded RAW_RESULTS/gate3_results.json:
  startup failover (1 failover, authorized via
  fallback); startup exhaustion (ConnectionRefusedError,
  exactly 1 exhaustion event); mid-job failover in
  0.07 s against a 4.0 s job interval (recorded run:
  0.084 s; both far inside one interval); failback on
  recovery exactly 1; flapping primary exactly 1
  failback inside the 60 s damping window with 2
  failovers and a live job at the end; mid-session
  exhaustion reported once, recovery on the primary's
  return; S5 accounting submitted 4 = accepted 2 +
  rejected 0 + unresolved 2, double_submits 0.
- Gate 5 from the suite code: tempfile.mkdtemp
  isolation, shutil.copytree byte copies of mining/ and
  gpu/, the built .local/cpu libraries copied, its own
  .local/mining-endpoint.json (policy enabled, stub
  primary and fallback), its own evidence file, BAL_POOL_*
  environment stripped, the copied production
  mainnet_live.py run as a subprocess through start,
  primary death, failover, an accepted share on the
  fallback, failback, and SIGTERM stop. No live path is
  referenced. The claim holds, and the section executed
  green inside my test-exp050 run.

## 5. Registries, Makefile, integration log

- Stage 0 JSON registry: parses; 100 entries at
  b8b01ed3, 101 locally. The only addition is EXP-050
  (status PROVEN); the only changed shared entry is
  R-26 (NEW to INTEGRATED, measured_result rewritten
  to the EXP-050 integration); the other 99 shared
  entries are identical to remote.
- Both markdown registries: pure appends (63 added
  lines, 0 removed in each), the two additions
  byte-identical to each other, each ending at next
  unreserved EXP-051. The JSON registry's EXP-050
  entry agrees.
- Makefile: the diff against remote is exactly the
  test-exp050 target plus test-exp050 appended to
  test-all; test-all names 42 prerequisites, counted.
- Integration log Entry 6 (phase6b log, pure append):
  accurate against everything this audit verified,
  including the defect narrative and the census, and
  it states plainly that the audit was owed and the
  policy stays disabled live. It says only what the
  evidence supports.

## 6. Suites (one at a time, auditor runs)

- test-exp050: 40/40 PASSED.
- test-mainnet-live: PASSED.
- test-solo: PASSED (solo-mined block accepted by Core
  at regtest height 2153 during the run).
- test-judgement: PASSED (an additional direct
  StratumClient consumer).
- test-exp037: PASSED (the statistics consumer of the
  client's share-verdict hook).
- test-solo-vardiff: 58/59 in three consecutive runs,
  the same single check failing each time: D4 Gate 6.
  See note N-3 for the full characterization; the
  failure is not attributable to this change.
- Full test-all (42 targets) was not run: the change
  surface (stratum client, endpoint config,
  mainnet_live, solo consumers of both) is covered by
  the six suites above, and two targets carry known
  environment failures (test-rtl: iverilog absent;
  test-autopilot: empty-lock precondition while the
  live stack is up). Recorded in the unverified
  register.

## 7. Scans

Byte scans over all 13 created or edited files
(mining/endpoint_health.py, endpoint_config.py,
stratum_client.py, mainnet_live.py, Makefile,
tests/test_exp050_endpoint_health.py, the exp050
report, harness and results JSON, both markdown
registries, the JSON registry, the integration log):
U+2014 count 0 in every file; secret-pattern scan
(PEM headers, xprv, GitHub and AWS token shapes,
rpcpassword assignments, generic secret assignments,
WIF-shaped strings) returned zero hits.

## 8. Live stack

Never restarted, signalled or reconfigured. Share
census from evidence/mainnet-live.jsonl (full-log
count of share_result events): 613 accepted / 8
rejected before the audit, 614 / 8 after; the delta
is the live miner's own share during the audit
window. Balance 0 BTC, no block.

## Notes

- N-1: the "historical behaviour exactly" framing is
  overstated in one observable respect for
  policy-absent consumers: the pending-submit
  bookkeeping is always on, so a session reset with
  unanswered submits now emits a
  submits_unresolved_on_reset evidence event where
  the pre-change client logged nothing. Wire
  behaviour, reconnect timing and verdict handling
  are unchanged; the delta is one additive evidence
  event, and it is the accounting improvement the
  integration set out to make. Relatedly, a future
  solo_cutover set_mode flip would persist the
  disabled-default pool_health section into the live
  config file (enabled false; behaviour-neutral).
- N-2: residual accounting case, characterized, not
  a defect: if sendall itself raises (broken pipe),
  submit() propagates the exception exactly as
  pre-change and no "submit" event is logged, but the
  id stays in the pending set and is reported as
  unresolved at the next reset. An evidence-level
  identity of the form (submit events) = (verdicts) +
  (unresolved) can therefore be off by the number of
  send-failed submits. No share is double-submitted,
  silently lost or falsely accepted; the classification
  is honest (the attempt was made; no verdict can
  arrive). The Gate 3 identity is computed over
  stub-received submissions and is unaffected.
- N-3: test-solo-vardiff D4, in detail. The check
  demands that every share the vardiff server accepts
  in scenario D-A also becomes a best-chain block.
  My three runs: run 1, 58/59 (D4 only); run 2, D4
  failed with 1 accepted block against 7 accepted
  shares and six solo-server lines "BLOCK NOT
  ACCEPTED ... submitblock said 'inconclusive',
  chain state not-in-chain" at built heights 2191,
  2194, 2199, 2217, 2238, 2255; run 3, D4 failed with
  6 accepted blocks against 7 shares and one such
  line. The mechanism: a block built on a template
  whose tip has already advanced is a fork block and
  Core answers inconclusive; the built heights in
  run 2 gap by 3 to 21 while the scenario itself
  accepted a single block, so the tip was being
  advanced concurrently from outside the scenario
  (the shared regtest node; load average 9 to 18
  throughout my runs, with other work on this VM).
  With nothing running, the same node held height
  2330 across a 25 s sample. Attribution to EXP-050
  is excluded on code paths: the suite's Worker is a
  raw-socket client defined in the test file; its
  only stratum_client imports are build_header and
  target_for_difficulty, neither touched by the diff;
  mining/solo_server.py is untouched by this change
  (mtime 2026-11-16 08:52, before the campaign); the
  endpoint_config diff leaves every solo surface
  unchanged. The author's recorded 59/59 stands for
  its run; this suite's live sections have a
  documented history of load-shaped failures (Stage 6
  run 1: 57/59 at load about 16; run 3: TIME_WAIT bind
  death), and D10 and D18, the run's other two Gate 6
  checks, passed in all three of my runs.
- N-4: EndpointHealthPolicy.note_failback() does not
  itself re-check failback_due(); the gating lives in
  the client's _maybe_failback, which checks due and
  probes before calling it. Enforced in the shipped
  wiring; a future direct caller of the policy must
  honour the same order.

## Unverified register

- The author's section 8 register stands in full:
  failover against the real public-pool.io, any real
  second endpoint, live enablement, the Intel Xeon
  Platinum 8321HC host, two-client behaviour against
  one fallback, and the subscribe-answers-but-never-
  authorizes probe shape.
- Full test-all (42 targets) on this tree state.
- A 59/59 test-solo-vardiff run inside this audit's
  window (three runs, 58/59 each; note N-3).
- Behaviour of the degenerate enabled single-endpoint
  configuration on the live stack (unit-verified and
  Gate 3-verified against stubs; never run live).
