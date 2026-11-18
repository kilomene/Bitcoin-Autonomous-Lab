# Fleet modules: independent audit (Stage 9, plan section F step 4)

Date: 2026-11-18. Auditor: independent; the auditor wrote
none of the audited code. Remote HEAD at audit time:
857384faabf3c3eff8c954b1a77b2c004873edfa. Audited:
mining/fleet_gateway.py, mining/fleet_worker.py, the
section I fixes to both, tests/test_fleet_gateway.py, the
Makefile wiring, the staging evidence in
research/STAGE9/evidence_fleet/, and the soak record in
plan section H against the .local/fleet artifacts.

Scope note: where the coordinator is hosted at activation
(the bind blocker of plan H.4 and H.7) is an open owner
decision. It is outside this verdict's scope. This audit
judges the modules, the fixes, and the evidence, and it
gates activation on defect D-1 below, not on the hosting
decision.

## Overall verdict: PASS WITH NOTES

One defect, D-1, in a file outside the audited set
(mining/coordinator.py, pre-existing at HEAD). D-1 blocks
fleet activation until fixed and re-verified as specified
in the item 5 ruling. D-1 does not block the push of the
fleet file set: the set neither contains nor worsens it,
and nothing in the set runs until the separately gated
cutover (plan F step 5).

## Defects

### D-1 (activation-blocking): coordinator refusal detail discloses the fleet id on the wire

mining/coordinator.py lines 286 to 288 raise
ForeignFleetError with a message formatting both the
presented fleet id and the expected fleet id, and lines
1056 to 1058 place that message in the "detail" field of
the wire response. The fleet id is the fleet's only
admission credential (plan section G: no per-worker
token). Any party that can open a TCP connection to the
coordinator and send one register frame with a guessed id
receives the real fleet id in the refusal. The section I
fix closed the file path (the shipped worker now names
refusals by error code only), but the wire disclosure
itself stands. Ruling and required re-verification:
item 5 below.

## Notes

- N-1: in the staging gateway evidence, the event name
  share_result is emitted by two loggers: the
  StratumClient reader thread (mining/stratum_client.py
  line 368, fields id/accepted/error) and the gateway's
  own _collect_verdicts (fields worker/nonce/id/accepted/
  error). There are 34 such events for 17 submissions.
  The gateway's counters and the EXP-037 totals are
  single-counted and correct (17 submitted, 17 accepted);
  evidence consumers must not sum share_result events
  across the two emitters.
- N-2: plan H.2's declare_job timings (0.026 s first,
  0.004 s and 0.003 s superseding) were re-measured by
  this audit through the same handle_message path at the
  same production width: 0.031 s, 0.077 s, 0.048 s on
  this loaded shared host, with declared_total recomputed
  exactly (see item 7). The superseding figures differ
  from H.2's to the digit; the magnitude and the
  conclusion (viable at pool cadence by a wide margin)
  are corroborated.
- N-3: the staging gateway evidence contains one
  candidate_dropped event (worker w-probe, nonce 12345,
  verdict invalid) timestamped after the queue snapshot
  in summary.json. It is the driver's fabricated probe
  candidate reaching the gateway drain and being rejected
  by the EXP-036 verifier, never submitted. It is the
  verification gate working, not an accounting
  discrepancy; the queue figure submitted=17 counts the
  worker candidates drained before the probe.

## Per-item verdicts

### Item 1, design fidelity: PASS

- Single pool session, identical endpoint resolution:
  mining/fleet_gateway.py lines 114 to 125 call
  resolve_endpoint(args.pool_host, args.pool_port) and
  construct StratumClient(pool_host, pool_port, user,
  "x", ev), the same call and construction as
  mining/mainnet_live.py lines 177 to 182; the
  suggest_difficulty logic mirrors mainnet_live.py
  lines 186 to 189 (solo share_difficulty from the
  endpoint config, else 0.001).
- Every pool job declared: FleetGateway._maybe_declare
  (fleet_gateway.py lines 172 to 215) declares each new
  job generation to the coordinator via declare_job
  with the configured nonce_count, chunk_size and
  n_slots and the job's version and ntime; the
  declared_generation guard prevents re-declaration.
- EXP-036 verification before any submission: the
  gateway passes verifier=self._verify_candidate into
  CoordinatorServer (fleet_gateway.py lines 130 to
  133). CoordinatorServer's candidate_drain dispatch
  (mining/coordinator.py lines 1005 to 1015) drains
  through CandidateQueue.drain, which calls the
  verifier on every non-stale record (coordinator.py
  lines 183 to 207). _verify_candidate
  (fleet_gateway.py lines 148 to 169) rebuilds the
  header with build_header and returns
  verify_candidate's classification, the same EXP-036
  call mining/mainnet_live.py makes at its line 349
  before submitting. The gateway drain additionally
  drops any verdict other than share or block_candidate
  (fleet_gateway.py lines 224 to 231).
- Stale-generation candidates dropped, never submitted:
  two layers. The queue drops records whose generation
  is not the current generation before verification
  (coordinator.py lines 189 to 193), and the gateway
  re-checks freshness against the live client job and
  generation before submitting (fleet_gateway.py lines
  232 to 247, dropped_stale counter).
- Per-worker verdicts in EXP-037 statistics: the
  gateway records pool_shares_submitted,
  pool_shares_accepted and pool_shares_rejected in
  MiningStatistics (the EXP-037 engine,
  mining/mining_statistics.py line 184) with
  worker=rec["worker_id"] (fleet_gateway.py lines 257
  to 258 and 276 to 280). Staging totals: 17 submitted,
  17 accepted, 0 rejected.
- Worker properties: mining/fleet_worker.py holds no
  wallet, pool account or keys (its arguments are the
  gateway address, the fleet id, a worker id and a log
  path; it imports CoordinatorClient, ComputeEngine and
  build_header only, and has no pool client at all, so
  it cannot submit anything itself). It pins
  ComputeEngine(requested="auto", threads=1)
  (fleet_worker.py line 135) and advances its scan by
  the engine's own attempted count (pos += att after
  every search_first_counted call in work_chunk), so a
  completion certifies the whole chunk was examined.

### Item 2, baseline integrity: PASS

sha256 computed by this audit:
mining/coordinator.py
b4215980cac03f0e11a772887cc08a6db37ca46df8032e481175940bae032eff
and mining/aggregation.py
1951a657b1be1968b484514a0defa70e4c10ce93ccc46beb0f0369b74d67c603,
both byte-identical to the Stage 9.1 pins.

### Item 3, Fix 1 (bind must be fatal): PASS

The readiness mechanism is a true bind confirmation,
not a timer and not a race. CoordinatorServer.serve
assigns self._tcp only after srv.bind() and
srv.listen(64) succeed (mining/coordinator.py lines
1093 to 1097); a bind failure raises out of serve
before _tcp exists. The gateway's _serve_coordinator
wrapper thread captures that exception into
_coord_error (fleet_gateway.py lines 307 to 320), and
run() waits on the disjunction (_tcp set, _coord_error
set, or a bounded 10 second deadline) and on failure
logs coordinator_bind_failed and returns exit code 4
before the pool leg starts (fleet_gateway.py lines 322
to 352). The listening claim is keyed to state that
cannot exist before a successful bind.

Independent reproduction by this audit, with a dummy
fleet id and an unbindable address (192.0.2.1, the
soak's Errno 99 shape): exit code 4 in about 1 second;
evidence events exactly endpoint_selected,
coordinator_up, coordinator_bind_failed with error
"OSError: [Errno 99] Cannot assign requested address";
no coordinator_listening, and no connected or
authorized event (no pool connection was opened). The
suite's loopback half, re-run by this audit (item 8),
proves coordinator_listening is written only when the
port verifiably accepts a connection at that moment.

### Item 4, Fix 2 (fleet id hygiene): PASS

- coordinator_up carries fleet_fp, the first 12 hex
  characters of the id's SHA-256, and no fleet field
  (fleet_gateway.py lines 141 to 145). Verified live in
  the item 3 reproduction: the fingerprint equalled
  sha256(dummy id)[:12] and the dummy id string
  appeared nowhere in the evidence or the stdout.
- The gateway's default --evidence path is
  .local/fleet/fleet-gateway.jsonl (fleet_gateway.py,
  main), and the plan F step 5 cutover command passes
  --evidence .local/fleet/fleet-gateway.jsonl.
- The worker names refusals by error code only:
  fleet_worker.py lines 100 to 112 raise with
  out["error"] and never out["detail"].
- tests/test_fleet_gateway.py re-run by this audit:
  23 checks, ALL PASSED (item 8).
- Independent greps: the suite's dummy ids
  (DUMMYFLEETID, WRONGFLEETID) occur only in
  tests/test_fleet_gateway.py across mining, tests,
  research, scripts, agent and gpu. args.fleet has
  exactly two uses in the gateway (line 132, the
  coordinator constructor; line 142, the fingerprint)
  and exactly one in the worker (line 119, the register
  wire message). The staging evidence contains only
  the staging dummy ids (nova-fleet-staging, other-fleet).
- Sinks enumerated and checked: (1) the gateway
  evidence log and its mirrored stdout: every event
  type the gateway logs was read; none carries the id.
  (2) The gateway status event: the embedded
  coordinator accounting() returns coverage counters
  only (coordinator.py line 742 onward), and queue
  stats are counters and classifications only.
  (3) The coordinator journal and snapshot under the
  state dir: these contain the fleet id by design
  (journal replay re-executes register ops; the
  snapshot stores core state, coordinator.py line
  620). They are safe only under the .local/fleet
  state-dir discipline, which the gateway default and
  plan step 5 both enforce; the discipline is
  load-bearing, as plan section I records.
  (4) Coordinator wire responses: the FOREIGN_FLEET
  detail is the one disclosure (defect D-1); other
  error details (LEASE_ERROR, BAD_REQUEST) carry
  exception text not derived from the id value, and a
  successful register returns only the string
  REGISTERED (coordinator.py lines 284 to 303), so
  (5) the worker log, whose registered event logs that
  return value, carries no id; and (6) worker stdout
  and stderr, closed by the error-code-only raise.

### Item 5, the FOREIGN_FLEET wire residual: RULING, must be root-fixed before activation

The recorded residual is not acceptable as it stands,
for one concrete reason: the detail does not merely
carry the id into a log, it returns the expected fleet
id to the party who just failed admission. The fleet
id is the only admission credential. A refused
registration is therefore a credential oracle: one
frame to the coordinator port yields the secret that
admits the next frame. The acceptance rationale in
plan section I (the coordinator listens only on a
private tailnet path; the ids never reach a file)
answers the file-confidentiality threat, not this one.
Tailnet membership is not fleet membership: any
tailnet device, or any process on any tailnet machine,
could extract the id. The bounded blast radius (the
gateway's EXP-036 verifier still judges every
candidate, so a rogue worker can waste verification
and pollute accounting but cannot forge a share) does
not rescue admission itself.

The fix is small and the timing is free: activation
has not happened, no second machine exists, and the
coordinator is reachable by nobody today. Required
change: in CoordinatorCore.register_worker
(mining/coordinator.py lines 286 to 288), raise
ForeignFleetError naming the worker and the refusal
without either fleet id (for example "worker %s
presented a foreign fleet id"). This audit verified
by grep that no other site in coordinator.py embeds
the id in a message: fleet_id occurs only at
construction, the register comparison, and snapshot
store and restore.

Re-verification the baseline change triggers, exactly:
1. mining/coordinator.py's hash changes; the Stage 9.1
   pinned baseline b4215980... is retired and the new
   hash recorded wherever the pin is asserted.
2. The full test-exp055 suite re-run (23 checks,
   including gate 6, a regtest block through
   coordinator-assigned work): the EXP-055 proof for
   the coordinator module itself. No test pins the
   detail text (this audit grepped tests/ and the
   staging driver for "presented fleet": no matches;
   the only FOREIGN_FLEET assertion in the test tree
   is the error-code-name check in
   tests/test_fleet_gateway.py), so no test edit is
   expected; any assertion on the detail text found
   during the fix must be changed to assert the code
   only.
3. tests/test_fleet_gateway.py re-run (23 checks),
   plus one added check asserting the raw refusal
   response's detail contains neither the presented
   nor the expected id (the current suite checks the
   worker's output files, not the wire detail).
4. The staging evidence in evidence_fleet/ is
   historical and is not re-run; its recorded
   FOREIGN_FLEET detail, with staging dummy ids,
   remains as the record of the pre-fix wire format.

Until 1 to 3 are done, plan F steps 5 and 6 (cutover
and enrollment) are not cleared by this audit.

### Item 6, staging evidence: PASS

Spot-recomputed from research/STAGE9/evidence_fleet/
by this audit, not taken from the plan's word:

- summary.json carries exactly 22 driver checks, every
  one pass=true, and an empty failures list.
- accounting_pre_probes: declared_total =
  unique_coverage = actual_computations = 16,777,216,
  with duplicate_deliveries, repeated_computations,
  stale_reports, not_holder_attempts and reclaims all
  0, and complete true.
- The raw worker logs recompute independently: each of
  w-fleet-a and w-fleet-b completed 8 chunks with
  attempts summing to 8,388,608 per worker,
  16,777,216 in total, matching attempts_equal_declared.
  Candidates 11 and 6, total 17.
- Queue: submitted 17, verified 17, classifications
  share 17, duplicates 0, stale_generation_dropped 0.
  Gateway: 17 share_submitted events, all verdict
  share. Stub oracle: judged 17, accepted 17, rejected
  0, distinct submission keys 17. EXP-037 totals in
  the gateway snapshot: pool_shares_submitted 17,
  pool_shares_accepted 17, pool_shares_rejected 0.
- Probes: candidate replay DUPLICATE, complete replay
  DUPLICATE, NOT_HOLDER on a non-holder completion,
  STALE on a wrong token, and FOREIGN_FLEET on a
  foreign register, all as claimed.
- Subject to notes N-1 and N-3 on reading this
  evidence. No discrepancy found; the staging was not
  re-run.

### Item 7, soak claims (plan section H): PASS, as far as H claims

Verified against .local/fleet/gateway-soak.jsonl and
gateway-soak.stdout (the production fleet id file was
not read):

- endpoint_selected: public-pool.io port 21496, mode
  pool. subscribed with extranonce2_size 8.
  authorized user
  bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3.htch-runtime-fleetgw.
- suggest_difficulty_sent 0.001, then set_difficulty 1:
  the pool's difficulty floor of 1 confirmed for this
  session, as H.3 states.
- Three job_declared events: job 6b502b generation 1
  at 2026-11-18T12:44:17.49Z, job 6b5bc5 generation 2
  at 12:44:47.29Z, job 6b6744 generation 3 at
  12:44:49.09Z, a span of 31.6 seconds, each at
  difficulty 1.0 with nonce_count 2^32, chunk_size
  2^24, n_slots 32 and 32 slices: production width, as
  claimed. Zero submissions (no share events exist).
- H.4's account is confirmed by the same artifacts:
  the pre-fix false coordinator_listening is present
  at 12:44:16.69Z and Errno 99 (Cannot assign requested
  address) is in the stdout.
- declare_job cost: this audit re-ran three
  declarations through CoordinatorServer.handle_message
  at production width against a throwaway state dir:
  declared_total 137,438,953,472 = 32 x 2^32 exactly,
  timings 0.031 s, 0.077 s, 0.048 s (note N-2). H.2's
  closure of the production-width register item
  stands.

### Item 8, Makefile and suite re-runs: PASS

The test-fleet-gateway target exists (Makefile line
167) and is included in the test-all prerequisite list
(Makefile line 170); test-all grows by exactly one
suite. Re-run by this audit, one at a time:

- make test-fleet-gateway: 23 checks, ALL PASSED.
- make test-exp055: 23 checks, ALL PASSED (gate 6:
  regtest block at height 2674 through
  coordinator-assigned work).
- make test-exp057: 15 checks, ALL PASSED (gate 6:
  regtest block at height 2675 through the tier).

### Item 9, hygiene: PASS

- U+2014 count is 0 in mining/fleet_gateway.py,
  mining/fleet_worker.py, tests/test_fleet_gateway.py
  and research/STAGE9/FLEET_ACTIVATION_PLAN.md.
- After-hashes from the fix report all match the files
  on disk: fleet_gateway.py
  63526c51f765c919f0a598d792c79ef2d8872f9eb8190e17393f5dc58536dc25,
  fleet_worker.py
  b3d899ca7e331af1943f3953774b2ed155bcc576d851046b368695b5a690863e,
  tests/test_fleet_gateway.py
  2822554d0dc4dd8107ea49772a678f7f51138d63b02c90696f1333ccb0e36280,
  Makefile
  34c787b3ee1da91a8decd5a67a7fc9f169c54c7dc377dc7521b663794b97a3b9,
  FLEET_ACTIVATION_PLAN.md
  9f9c942b4e675df1d1819363dcb95da2bd8d1b3b0a497a03aa8fe0c48f73b55e.
- The endpoint config .local/mining-endpoint.json
  hashes to
  09b04010e11269c5efe745a964445bfde453724f977e94494b08864f5d8a25ec,
  the post-flip value, untouched by this work.
- Live stack undisturbed: heartbeat at
  2026-11-18T12:56:14Z shows autopilot_pid 4349,
  miner_pid 4352, miner_state running, restarts 0,
  shares_accepted_total 1157: the same processes as
  the fix report's after-state, shares non-decreasing
  from the audit baseline of 1148.

## Push clearance

The fleet file set (mining/fleet_gateway.py,
mining/fleet_worker.py,
research/STAGE9/FLEET_ACTIVATION_PLAN.md,
research/STAGE9/evidence_fleet/,
tests/test_fleet_gateway.py, and the Makefile),
together with this audit file, is CLEARED for its
scoped push.

Activation is a separate gate and is NOT cleared by
this verdict: defect D-1 must be root-fixed in
mining/coordinator.py and re-verified per item 5
before plan F steps 5 and 6 (cutover and enrollment)
are executed, and the coordinator hosting question
remains an open owner decision outside this audit's
scope.
