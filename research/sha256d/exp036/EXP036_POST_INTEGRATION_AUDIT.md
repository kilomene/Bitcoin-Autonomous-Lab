# EXP-036 post-integration audit (independent)

Auditor: independent agent, not the integration author.
Date: 2026-11-15. Scope: the EXP-036 production changes as
they stand on disk: mining/candidate_verify.py (new),
mining/solo_server.py, mining/mainnet_live.py,
tests/test_exp036_verification.py, the Makefile test-exp036
target, and the claims in
research/sha256d/exp036/BLOCK_SUBMISSION_DESIGN.md against
the EXP-036 section of the EXP-030 directive (section 9, the
twelve-step pipeline).

## Verdict: PASS WITH NOTES, zero defects

No defect was found. Every adversarial case in the audit
brief behaves as the directive requires, the design doc's
claims check out against the code line by line, and the
auditor's own regtest blocks through the production solo
path are chain-verified in the recorded fields. Notes N-1
to N-6 below are observations, not defects; none of them
lets an invalid candidate through, misrecords a block, or
puts a float in an acceptance decision.

Environment note: the VM was replaced mid-audit. Evidence
was gathered on two hosts: AMD EPYC 9D25 (first pass) and
Intel Xeon Platinum 8321HC (second pass). The audited code
is pure Python and host-independent; the author's EXP-036
tests and the full auditor suite (including the regtest
proof) were re-run and pass on the second host. The host
change did break one unrelated suite target; see the
full-suite section.

## 1. Fidelity: the twelve steps against the code

1. Recover immutable job. Solo: SoloServer.jobs retains the
   full template server-side; submit_share looks the job up
   by job_id and rejects unknown jobs. Pool:
   mainnet_live reads client.current_job and
   client.job_generation under the client lock. Matches.
2. Recover exact header fields. Solo validate_share rebuilds
   the coinbase from stored coinb1/coinb2, the connection
   extranonce1 and the submitted extranonce2, and the header
   from the template version, previousblockhash and bits
   with the submitted ntime and nonce. Pool: build_header
   from the job and extranonce pair. The extra consistency
   check is real (solo_server.py submit_share): the target
   decoded from the reconstructed header's own nBits must
   equal the job's recorded target, else the candidate is
   classified invalid with reason header-target-mismatch.
   Matches, and the auditor's inflated-target case (audit
   tests) proves the check fires in the opposite tampering
   direction from the author's test.
3. Reconstruct the 80-byte header. The bytes verified are
   the bytes hashed and, on the solo path, the bytes that
   enter the assembled block (res["header"] is reused for
   block assembly). Matches.
4. Compute SHA-256d independently. verify_candidate hashes
   with hashlib (mining.pow.dsha256) and with the pure
   Python mining.pow_engine.double_sha256_pure and requires
   byte agreement; disagreement classifies invalid with
   reason digest-disagreement. Matches.
5. Decode nBits exactly. check_pow's compact_decode, Core
   SetCompact semantics with negative and overflow flags.
   Matches; the auditor's independent decode agrees on all
   300 differential headers.
6. Exact integer compare. meets_target is value <= target;
   block candidacy is check_pow ok AND digests agree. No
   float participates (see section 4). Matches.
7. Reject invalid candidates. Solo: invalid classifications
   are appended to candidates_rejected (exposed in stats()),
   counted rejected for the worker, and submitblock is
   never called (proven against fake Core and on regtest).
   Pool: an unconfirmed candidate is logged
   candidate_rejected and never submitted. Matches.
8. Construct the complete block. Solo: header plus varint
   count plus coinbase (witness re-attached by
   attach_witness when the template carried a commitment)
   plus the template transactions verbatim. Pool: not
   applicable, disclosed in the design doc. Matches.
9. Validate locally. As documented: the exact verification
   of steps 4 to 7 over the precise submitted header, plus
   the server's node gating (chain match, no IBD). There is
   no separate validateblock-style pass; the design doc
   says so plainly. Matches as documented.
10. Submit through the correct interface. Solo: Core
    submitblock via node.rpc_client. Pool: Stratum
    mining.submit via stratum_client, call unchanged.
    Matches.
11. Record the response. Solo block records carry height,
    hash, submit_result (verbatim), submit_classification,
    chain_status, chain_verified, verify_reason and the
    final accepted boolean; an RPC exception during
    submission is captured into the record as rpc-error
    instead of killing the handler. Matches; the auditor's
    raise-injection cases confirm the record survives.
12. Verify acceptance through chain state.
    verify_chain_acceptance: tip, in-chain (confirmations
    >= 1), not-in-chain, unknown. The accepted flag and the
    per-worker block count come from chain state, not the
    submission response. Matches.

Defect-by-defect: Defect 1 (submitblock None treated as
success) is closed; the auditor reproduced the old failure
mode against an orphan fake Core and the record now says
accepted False, chain_status not-in-chain, worker blocks 0.
Defect 2 (check_pow never called by production) is closed;
both production candidate paths route through
verify_candidate, and a caller census over mining/, gpu/,
node/, scripts/ and dashboard/ shows mining.candidate_verify
is used in production only by solo_server.py and
mainnet_live.py. Defect 3 (float difficulty as a test) is
closed; see section 4.

## 2. Auditor's own adversarial evidence

Audit tests: research/sha256d/exp036/EXP036_AUDIT_TESTS.py,
written independently of the author's tests (own fake Core,
own compact decode from the Core spec, own expected-model).
All pass, on both hosts.

- Differentials: 300 random headers across 12 nBits values
  (including negative 0x01800001, overflow 0x2200FFFF and
  0x2300FFFF, zero 0x1D000000, above-limit and small-size
  encodings), both pow limits, three share-target settings.
  verify_candidate matches the independent model on every
  field (classification, reason, digest, value, target,
  meets_network_target, meets_share_target, valid_header).
  Class mix: 9 block_candidate, 1 share, 104 below_target,
  186 invalid. 79-byte and 81-byte headers classify invalid
  with reason header-length.
- Boundary: for the difficulty-1 target, the regtest limit
  and 2^240: meets_target(T, T) is True and
  meets_target(T + 1, T) is False, while float(T) equals
  float(T + 1) and the float difficulties DIFF1 / T and
  DIFF1 / (T + 1) are the identical double. A float judge
  (directive-rejected pattern W1) cannot decide the
  boundary; the integer compare does. An nBits ladder
  around a real winning header matches the independent
  model on every rung (nBits is part of the hashed header,
  so a fixed-hash straddle does not exist; the equality
  boundary is pinned arithmetically, as above).
- Mutated header: one flipped merkle bit and one flipped
  nonce bit each change the digest, and the exact
  confirmation predicate mainnet_live applies (backend
  digest equals verify_candidate digest AND digests_agree)
  rejects a digest claimed for the unmutated header.
- Solo against the auditor's fake Core:
  - submitblock None but the block never enters the chain:
    NOT recorded accepted (accepted False, chain_verified
    False, chain_status not-in-chain, worker blocks 0,
    record kept in blocks_found).
  - submitblock "duplicate" with the block confirmed as
    tip: accepted True, classification duplicate, verbatim
    result kept. (A positive case the author's tests do
    not cover.)
  - Rejection strings "inconclusive", "high-hash" and
    "duplicate-invalid": accepted False, verbatim value in
    submit_result, classification as documented.
  - RPC raises on submitblock: classification rpc-error,
    chain_status unknown, candidate record preserved, no
    block counted.
  - RPC raises on the chain read after a landed submit:
    chain_status unknown, accepted False, record preserved.
    The fail-closed bias the design doc discloses is real.
  - Overflow (0x2200FFFF, a different encoding than the
    author's test used), zero-target and negative-target
    candidates: rejected by exact verification with zero
    submitblock calls.
  - Inflated recorded job target (job target tampered to
    2^256 - 1, header honest): rejected as
    header-target-mismatch, zero submitblock calls. The
    recorded target cannot override the header's exact
    nBits.
  - Share is not a block: a candidate meeting the server
    share target but failing the exact nBits network check
    (mainnet bits job) is accepted as a share only:
    submitblock never called, blocks_found empty, worker
    blocks 0, worker accepted 1.
- verify_chain_acceptance unit cases: tip; in-chain with
  5 confirmations; fork block (confirmations -1) rejected;
  zero confirmations rejected; getblockheader error -5 is
  not-in-chain; a non -5 header error is unknown and not
  accepted; getbestblockhash raising is unknown and not
  accepted.
- classify_submit_result extra values: unknown reject
  strings and a non-string result both classify rejected.

## 3. Regtest proof (auditor's own, real node)

Through the production SoloServer against the lab regtest
node, twice (once per host):

- Negative: a job tampered to overflow nBits 0x2300FFFF
  with a winning nonce per the fast compare is rejected
  with reason overflow-target; blocks_found stays empty;
  the node tip and height do not move.
- Positive, AMD host: block at height 1070, hash
  5a7d9bd8f295d05dfffe2023b5a6372862e0fe93555f64271eca5a4a85f8d238,
  recorded chain_status tip, chain_verified True,
  submit_result None, getblockheader confirmations 1.
- Positive, Intel host: block at height 1123, hash
  09a08ff7670ff79898d8c459864f0007b7885814ed9be3e7e17a35f45b5bfe96,
  chain_status tip, confirmations 1.

The author's tests/test_exp036_verification.py was run by
the auditor and passes on both hosts (its own regtest
blocks landed at heights 1065 and later).

## 4. Float and scope audit

Grep plus line reading over the three changed production
files:

- mining/candidate_verify.py: no float literal, no float
  conversion, no division anywhere in the module. Every
  comparison is on integers or bytes.
- mining/solo_server.py: no float anywhere in the file.
  Acceptance decisions read only verify_candidate outputs
  and verify_chain_acceptance. (Note N-1 concerns the
  share target's construction, not an acceptance decision
  for blocks.)
- mining/mainnet_live.py: floats appear only in
  difficulty_of (display and statistics: the status line,
  the best-difficulty tracker, evidence fields),
  target_for_difficulty (the pool's share criterion; its
  docstring states it is never a consensus test), and the
  suggest_difficulty protocol parameter. The confirmation
  predicate is hash_match AND valid_header AND
  meets_share_target AND template fresh, all from
  verify_candidate; is_block_candidate in the evidence log
  is meets_network_target, check_pow's verdict alone. No
  float decides block candidacy or acceptance.

Pool submission behaviour: for any candidate that passes
exact verification, the submission is the same
client.submit(job, en2, found) call as before, with the
same arguments. The EXP-036 gate only withholds submission
from candidates that fail exact recomputation (digest
disagreement, illegal target) or whose template went
stale, which is the integration's stated purpose; ordinary
share flow is otherwise unchanged.

mining/engine.py is untouched: it does not import
candidate_verify, its mtime (2026-11-15 07:43 UTC) predates
the EXP-036 files (09:37 to 09:38 UTC), and its mine_cycle
still applies the reference standard the design doc cites
(submitblock None AND getbestblockhash equals the block
hash, engine.py lines 667 to 670).

## 5. Test suite state (auditor's runs)

- tests/test_exp036_verification.py: PASS (both hosts).
- Auditor's EXP036_AUDIT_TESTS.py: PASS (both hosts,
  including the regtest section).
- Neighbouring targets: test-solo PASS, test-solo-cutover
  PASS, test-mainnet-live PASS, test-pow PASS (1067 live
  regtest headers cross-verified at the time of that run),
  test-engine PASS.
- Full suite (make test-all, 27 targets): the first 11
  targets pass; make stops at test-rtl, which fails with
  "iverilog: not found", the known pre-existing environment
  failure (the RTL simulator is not installed on this VM),
  unrelated to EXP-036. The 15 targets after test-rtl were
  run individually: 14 PASS (test-solo, test-solo-cutover,
  test-research, test-autopilot, test-judgement,
  test-installer, test-task0038, test-task0039, test-avx512,
  test-avx512dual, test-mainnet-live, test-template-cache,
  test-avx512flags, test-exp036). test-task003 FAILS with
  SIGILL (exit 132, reproduced standalone) after the
  mid-audit VM replacement moved the lab from AMD EPYC
  9D25 to Intel Xeon Platinum 8321HC: the test exercises
  native intrinsics binaries, and the replacement host
  lacks extensions the old host had (the failure mode
  EXP-028 recorded for -march=native builds). The test
  imports none of the EXP-036 files (it uses gpu.engine,
  mining.cpu.build and mining.engine), the production
  restricted-flag AVX-512 targets all pass on the new host,
  and the failure is an environment event, not an EXP-036
  regression. Honest total: 25 of 27 targets pass; the two
  failures are test-rtl (pre-existing, iverilog absent) and
  test-task003 (host replacement SIGILL, unrelated).

## 6. Notes (not defects)

- N-1: SoloServer's share_target is computed as
  int(diff1 / share_difficulty), a float division, so the
  share target carries float64 rounding (pre-existing code,
  not introduced by EXP-036). It is a share criterion only;
  block candidacy never reads it as a network test. An
  exact rational computation would be tidier.
- N-2: On the pool path the share target derives from the
  pool's float difficulty (int(DIFF1_TARGET / diff)), so
  its low bits are float-rounded. The pool re-judges every
  submitted share, and block candidacy is check_pow alone.
  Disclosed in the design doc; no change recommended.
- N-3: gpu/engine.py has a pre-existing local helper also
  named verify_candidate (backend digest checking). It is
  unrelated to mining.candidate_verify; the shared name
  could confuse a future reader of grep results.
- N-4: On the solo block path, submit_share returns
  accepted True (the share met the network target) even
  when the block record's accepted flag is False (block
  not chain-accepted). The Stratum reply therefore accepts
  the share while stats() and the record carry the honest
  block verdict. This matches the design intent (the
  author's orphan test asserts the same shape), but a
  reader of the return value alone could misread it.
- N-5: verify_chain_acceptance treats getblockheader
  confirmations >= 1 as in-chain. Core returns -1 for
  blocks outside the active chain, so the test is sound;
  a confirmations value of 0, which Core does not produce
  for an active-chain block, is also treated as not
  accepted (fail-closed).
- N-6: The design doc's stated gaps were re-verified as
  accurate: no candidate queue (EXP-038 owns recovery),
  no post-hoc reorg re-check of found blocks, Stratum V2
  absent, the pool path cannot construct a block (inherent
  to pooled mining, and a pool share acceptance is never
  recorded as a block), and the flaky-RPC bias toward
  unknown (never claim an unverified block). None of these
  is a defect of this integration.

## 7. Auditor's constraints honoured

No throughput benchmarks were run. The live miner, the
autopilot and both nodes were not restarted. Nothing was
pushed. The auditor modified no production code; the only
files written by the audit are this report and
EXP036_AUDIT_TESTS.py.
