# Stage 9.3 Independent Audit

Auditor: independent (not the Stage 9.3 builder).
Date: 2026-11-18.
Subject: research/STAGE9/CURRENT_HEAD_TEST_AUDIT.md, the
mining/engine.py fix, the evidence bundle in
research/STAGE9/evidence_93/, and
.github/workflows/test.yml.
Method: source reading, surviving-log cross-checks, one
auditor re-run of a cheap suite, live fingerprint
recomputation, and a from-scratch recomputation of the B2
evidence using only hashlib and manual byte parsing (no lab
code imported). Suites were never run in parallel and the
live mainnet stack was not disturbed.

## Verdict: PASS WITH NOTES

No defect was found in the production fix or in the B2
evidence. The three final suite failures are exactly the
three the report names, and both contested classifications
(environment for test-exp052, contention-sensitive for
test-task0039) are honest, for the reasons itemised below.
The open items are the builder's own D-93-2 and D-93-3,
which need owner decisions, plus one minor evidence gap
(NOTE-3).

## Item 1. Suite accounting: CONFIRMED

- The report's per-target table has 51 rows. Its five
  first-pass failures are test-rtl, test-task0039,
  test-exp037, test-agent-security and test-exp052, giving
  46 PASS / 5 FAIL, and after the isolated re-runs 48 PASS /
  3 FAIL. The progress log states the same totals and the
  same five names.
- Surviving durable logs agree: hidden_files/stage93-logs/
  reruns2.tsv records test-agent-security exit 0 in 71 s and
  test-exp052 exit 2 in 7 s; the agent-security re-run log
  ends "ALL AGENT SECURITY TESTS PASSED (116 checks)"; the
  exp052 re-run log ends at the Gate 5a assertion, matching
  the report. postfix2.tsv records the five post-fix
  neighbour suites at exit 0 with the exact durations the
  report gives (35, 23, 68, 19, 8 s). cleanroom.tsv records
  exactly the 8 passes and 4 failures of report section 6.
- test-rtl: `which iverilog` exits 1 on this VM, verified
  by the auditor. Environment failure, honestly recorded.
- Auditor re-run: `make test-probability` passed, 73
  checks, exit 0, under 1 s, matching the table entry.
- The three final failures are exactly test-rtl (iverilog
  missing), test-exp052 (Gate 5a host fingerprint) and
  test-task0039 (early-exit bound). Confirmed.

## Item 2. test-exp052 classification: HONEST (environment)

- Code path read in mining/bakeoff_dispatch.py:
  host_fingerprint() (line 105) hashes the sorted
  /proc/cpuinfo flag set with sha256 (first 16 hex chars)
  alongside cpu_model and logical_cpus; validate_cache
  (lines 446 to 451) returns failure with the reason
  "host fingerprint mismatch (host changed or cache
  foreign)" on any fingerprint inequality;
  resolve_requested (lines 571 to 572) maps that to
  ("auto", "doubt: {reason}; static order"). The
  fail-closed fallback is real and exactly as described.
- Live recomputation by the auditor: this instance reports
  cpu_model "AMD EPYC 9D25 126-Core Processor",
  logical_cpus 4, flags_hash c86584c209897fb5, stable
  across repeated calls. The campaign records under
  research/sha256d/exp052/RAW_RESULTS/sessions/ carry
  flags_hash 51d3e983ddf6ac93. Same model and CPU count,
  different flag set, as the report states.
- Judgement: the environment classification is honest.
  The production code did precisely what it was designed
  to do on fingerprint doubt (fall back to the static
  order and say why), and that behaviour is itself what
  the run verified. This is not a code defect in disguise.
  The only weakness is test design (a gate that can only
  pass on one host instance class), which the builder
  already records as D-93-3.

## Item 3. test-task0039 classification: HONEST; auditor verdict stated

- The test (tests/test_task0039_accounting.py lines 281 to
  305) searches from 3 nonces before the genesis nonce
  over 100,000 and asserts, in order: the hit is the
  genesis nonce; backend_hashes == attempted;
  attempted < 10,000 (the failing bound);
  unique_coverage == attempted; device_hashes == 0;
  verification_hashes == 1; candidate_count == 1. The
  miss case asserts an exact count of 30,000 with zero
  verification work.
- The search (gpu/engine.py search_first_counted, line
  1854) takes its attempted count from the native
  library's per-worker reporting, so attempted is actual
  completed work, not an estimate.
- Auditor verdict: the classification "contention-
  sensitive, exact accounting intact" is honest, and the
  bound failure cannot hide a real early-exit defect.
  Three reasons. (a) If early exit were broken, attempted
  would be the full 100,000; the observed 32,519 proves
  the stop propagates and the search halts early, only
  with parallel overshoot. (b) Every assertion that would
  expose an accounting defect (backend_hashes ==
  attempted, unique_coverage == attempted, exactly 1
  verification hash, exact 30,000 on the miss) passed in
  both runs. (c) The overshoot mechanism (8 auto-tuned C
  threads completing in-flight sub-batches before the
  stop is observed, on a VM shared with the live miner)
  is consistent with the suite passing at this same
  source on 2026-11-17 and with the 8x duration swing
  seen in test-agent-security in the same window.
  The failure is a promptness heuristic bound, not a
  correctness signal. It remains an open FAIL (D-93-2)
  and this audit does not reclassify it as a pass.

## Item 4. The fix (mining/engine.py script_num_push): CORRECT

- sha256 of mining/engine.py is
  7017cea3732959198895349366c227eb357e281c62bd6b067e12a8dd2a32133b,
  matching the report. Baseline files spot-checked by the
  auditor are unchanged: mining/mainnet_live.py
  c8071ce1..., mining/autopilot.py 3cfafc20...,
  mining/candidate_verify.py 35467c95...,
  mining/solo_server.py b094832a..., gpu/engine.py
  bfe605cb..., all equal to baseline section 7. Only
  engine.py changed.
- The function (mining/engine.py lines 53 to 84) mirrors
  CScript::operator<<(int64_t) exactly: 0 returns OP_0
  (0x00), -1 returns OP_1NEGATE (0x4f), 1 to 16 return the
  single byte 0x50 + value (OP_1 = 0x51 to OP_16 = 0x60),
  and every other value falls through to the previous
  minimal CScriptNum push. Auditor-executed checks:
  encodings for 0, -1, 1, 2, 15, 16 match the expected
  bytes, and for all values 17 to 4999, for large heights
  (840000, 976342, 2^31 - 1) and for other negatives
  (-2, -16, -17, -100), the new encoding is byte-identical
  to an independent implementation of the pre-fix
  encoding. No behaviour changed outside heights 0 to 16
  (and -1, which no coinbase uses).
- Single encoder: script_num_push is called at exactly
  one production site, mining/engine.py line 141 inside
  build_coinbase. The GBT path builds through
  build_coinbase, and the solo server imports
  build_coinbase from mining.engine (mining/
  solo_server.py line 536, used at line 558). The only
  other reference is a test import
  (tests/test_exp034_job_template.py line 459).
- Preserved failure evidence: failed_height1_attempt/
  submitblock_response.txt records 'bad-cb-height' with
  classification rejected, and debug_reject.txt carries
  Core's lines "AcceptBlock: bad-cb-height, block height
  mismatch in coinbase". The auditor parsed the failed
  block's coinbase from its block_hex.txt: the scriptSig
  begins 01 01 (push-data form) followed by "/BAL/".
  The post-fix block's coinbase begins 51 (OP_1)
  followed by "/BAL/", and Core accepted it (item 5).

## Item 5. B2 evidence: INDEPENDENTLY RECOMPUTED, ALL PASS

The auditor's recomputation (hashlib double-SHA256 and a
hand-written transaction parser; no lab code) ran 25
checks, all passing:

- Compact decode of 0x207fffff from scratch equals
  decoded_target.txt and the template target integer
  exactly; negative and overflow flags false.
- Probability: (target + 1) / 2^256 = 0.49999994, so the
  expected hashes per block are 2.0000002. The report's
  disclosure (probability 0.49999994, expected 2 hashes
  per block at 0x207fffff) is arithmetically right, and
  the report states plainly that this is regtest minimum
  difficulty, not mainnet-equivalent.
- Block 1: block hash recomputed from block_hex.txt is
  5a8d6d254ef255972ce50a8f832c1fb99cef69e61839a2550a6f037d72dbc35d,
  equal to getblock.json (height 1, 1 confirmation, nonce
  5 matching the header) and to getblockchaininfo_after
  (chain regtest, blocks 1, bestblockhash equal). The
  header is the first 80 bytes of the block; the block
  parses to exactly one transaction, fully consumed; the
  merkle root recomputed from the raw body equals the
  coinbase txid and the header field
  (9304bb3abc0f7d268b3b57d6a0099ff1ff339d8256ca4a845ae229aad8532d3e);
  the hash integer is below the target;
  submitblock_response.txt records acceptance (None).
  summary.json carries 29 checks, all ok, and
  verify_candidate.json records block_candidate with
  digests_agree and meets_network_target true.
- Witness block: getblock_witness.json shows height 145,
  1 confirmation, 2 transactions, hash
  2f62cd4dda6296b8467d303f2e7514539d4c72bc59a90cb5503fc43246a8120b.
  The auditor recomputed the block merkle root from the
  raw transaction hexes (matches), the segwit txid
  (matches witness.json), and the witness commitment:
  wtxid merkle root over the reserved zero hash and the
  transaction wtxid, double-SHA256 with the 32-byte zero
  reserved value taken from the coinbase witness, gives
  bcb634d89abd83d3ffc8bfb29335306e78eccb3edb8fbe82c66d43a9a973d9b7
  in the internal byte order in which it sits in the
  coinbase behind the aa21a9ed header. This equals
  witness.json's recomputed_commitment, and
  6a24aa21a9ed plus that value equals Core's served
  default_witness_commitment recorded in witness.json.
  The commitment output is physically present in the
  coinbase bytes.
- Funding disclosure: witness.json's funding_method names
  Bitcoin Core generatetoaddress, used only to mature a
  coinbase, and the report's section 5 discloses the same
  plus the height-80s node stalls and the four failed
  production-mined funding attempts. The disclosure is
  present and honest: nothing in the proof path
  (template, construction, commitment, search,
  verification, submission, acceptance) depended on the
  funding method. One trivial wording wrinkle: the
  funding_blocks_core field reads 0 while the disclosure
  describes Core-mined funding; the adjacent funding_note
  explains the funding had completed in a previous
  attempt, so the record is internally consistent.
  Noted, not a defect.

## Item 6. CI workflow: CONFIRMED

- .github/workflows/test.yml parses as YAML (the top-level
  "on" key reads as boolean True under YAML 1.1, the
  standard GitHub Actions trigger key; GitHub parses it
  correctly).
- The run step executes exactly the 8 suites of the
  report's cleanroom list: test-exp037, test-exp038,
  test-probability, test-exp049, test-exp051, test-exp053,
  test-exp054, test-exp058. cleanroom.tsv independently
  shows those 8 passing and test-exp050, test-exp055,
  test-exp057 and test-incident-codes failing in the
  cleanroom, matching the exclusion reasons in the file's
  header comments.
- Exclusions are documented by category (Core binaries,
  .local state, z3 venv, iverilog, host-keyed fingerprint,
  live-stack state, timing-sensitive suites). The workflow
  references no secrets, installs nothing beyond Python
  3.12 via actions/setup-python@v5, and uses only
  actions/checkout@v4 otherwise. Nothing in it would fail
  structurally on a clean runner. It was not triggered by
  the builder or by this audit.

## Item 7. Live stack guard: CONFIRMED

- Builder's record: heartbeat shares 1042 before
  (2026-11-18T03:03:17Z) and 1059 after
  (2026-11-18T05:21:50Z), non-decreasing, with the pid
  change attributed to the 04:05Z service restart and
  keeper restore, not to the run. The progress log
  corroborates the intermediate value 1048 at 04:01Z.
- Auditor's own guard: heartbeat before the auditor's
  re-run (05:24:32Z) showed autopilot 4878, miner 4881,
  shares 1060; after (05:24:52Z and again 05:28:04Z)
  shares 1060, miner_state running. Non-decreasing
  throughout.
- .local/mining-endpoint.json sha256 is
  d741cde3c6224406f46f3bae138fb174eb1d780725bcb94baff4e14a8670c7d3,
  unchanged.

## Item 8. Long dash scan: CONFIRMED ZERO

- grep for U+2014 over CURRENT_HEAD_TEST_AUDIT.md and
  .github/workflows/test.yml returns 0 matches in both
  files. This audit file was also written without the
  character.

## Notes

- NOTE-1 (open, owner decision; builder's D-93-2):
  test-task0039 remains a recorded FAIL. The bound is a
  promptness heuristic that fails under live-miner
  contention while exact accounting passes. Options are
  the builder's: a quiet-host run, or a thread bound
  inside the check. This audit agrees it must not be
  silently loosened.
- NOTE-2 (open, owner decision; builder's D-93-3):
  test-exp052 Gate 5a is host-instance-keyed. A future
  test revision could accept the proven "doubt:"
  fail-closed fallback as a passing outcome; that is a
  test-design change, not a production change.
- NOTE-3 (minor, evidence): the test-task0039 isolated
  re-run log was lost when the 04:05Z service restart
  wiped /tmp. Its exit code and duration rest on the
  progress log's contemporaneous record. The builder
  discloses the loss plainly; the first-pass failure is
  independently anchored in the progress log's runner
  record (attempted 32519 vs bound 10000), and the
  auditor's source-level verdict in item 3 does not
  depend on the lost log. No other claim in the report
  depends on a lost file: every other re-run and
  post-fix result has a surviving durable log.
- NOTE-4 (observation, no action): the report's
  statement that the witness datadir twice showed
  genesis on fresh instances is disclosed by the builder
  and does not affect the evidence, since every B2 item
  was captured live from the instance that produced it
  and the bundle is internally consistent under the
  auditor's recomputation.

## Bottom line

Stage 9.3's claims stand. The one production change is a
correct, minimal, single-site fix for a real defect that
Core's bad-cb-height rejection exposed, proven by Core's
acceptance at regtest heights 1 and 145 and by the
neighbour suites. The suite record (48 PASS, 3 FAIL) and
both contested classifications are honest. The fix, this
audit, the builder report, the evidence bundle and the CI
workflow are ready to be pushed together.
