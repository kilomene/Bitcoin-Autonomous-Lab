# EXP-034 Post-Integration Audit (Independent)

Auditor: independent agent, not the EXP-034 author.
Date: 2026-11-15. Host during this audit: Intel Xeon
Platinum 8321HC (the VM was replaced after the EXP-034 work
ran on an AMD host), x86_64, cpuinfo carries avx512f but NO
sha or sha_ni flag. Bitcoin Core 28.1, regtest.

Scope: the two production changes shipped by EXP-034:
(1) mining/solo_server.py, the extranonce split offset is
now located in the stripped coinbase bytes;
(2) mining/engine.py, MiningEngine gains the opt-in
extranonce_space parameter, default (0, 64).
Plus the held-PreparedTemplate trust boundary the phase
re-pinned (EXP-025 audit note N-2).

## Verdict: PASS

Zero defects found in either production change. Every claim
in JOB_TEMPLATE_ENGINE.md that this audit re-tested held up
under independently written tests. The auditor's own scripts
were written from the code and the preserved pre-fix bytes,
not adapted from the author's test file; the author's test
file was also run and passes.

## 1. The solo coinbase split defect: reproduced, fix verified

Reconstruction (auditor code, production build_coinbase and
strip_witness, synthetic segwit-bearing template, height
1000, extranonce1 01000000, extranonce2 00000007):

- The pre-fix logic (offset taken from the FULL coinbase,
  applied to the STRIPPED coinbase) lands exactly 2 bytes
  late on a witness-bearing coinbase: at_old == at_new + 2.
- The served scriptSig under the pre-fix logic reproduces
  the preserved pre-fix bytes in RAW_RESULTS exactly:
  b'\x02\xe8\x03/BAL/\xee\xee\x01\x00\x00\x00\x00\x00'
- Corruption anatomy, byte by byte: the last 2 placeholder
  bytes (0xee 0xee) stay inside coinb1; extranonce1 follows;
  only the first 2 bytes of extranonce2 fit inside the
  declared 16-byte scriptSig; extranonce2 bytes 2..3 land
  where the first 2 bytes of the coinbase sequence field
  belong (the 4 bytes at the sequence position read
  00 07 ff ff, the extranonce2 tail over the sequence
  head, not ff ff ff ff); the assembled coinbase
  differs from the constructed coinbase and its txid
  differs from the intended coinbase txid.
- On a witnessless template the pre-fix offset is already
  correct (full == stripped, offsets equal, assembled ==
  intended). This confirms the report's explanation of why
  the empty-mempool solo tests never exercised the defect.

Fix verification (production SoloServer.refresh_job and
validate_share, same templates): on BOTH the segwit-bearing
and the witnessless template, the served coinbase is
byte-identical to the coinbase build_coinbase constructs
with the placeholder replaced by extranonce1 + extranonce2;
the scriptSig is exactly height push + "/BAL/" + en1 + en2;
the sequence field is 0xffffffff intact; the served
coinbase txid equals the build_coinbase txid.

## 2. Auditor regtest end-to-end (witness commitment)

Independent run against the live regtest node (auditor
filled the mempool with bech32 and legacy sends; Core's
template at height 1154 carried 4 transactions and a
default_witness_commitment):

- SoloServer served the job with has_witness True.
- Served coinbase anatomy on the real Core template:
  scriptSig exactly height push + "/BAL/" + en1 + en2,
  sequence 0xffffffff.
- Share scanned to the network target and submitted through
  submit_share. Block accepted: height 1154, hash
  79d8f86d11b4deb7e554de24060d358f3a7bf441cee85871f10d
  fedb56546aea.
- EXP-036 fields on the block record: submit_result None,
  submit_classification "accepted", chain_status "tip",
  chain_verified True, verify_reason "ok". The node tip
  advanced by exactly 1 and getbestblockhash equals the
  record hash.
- Core's own record of the accepted block: coinbase
  scriptSig carries en1 + en2 in the slot, vin sequence is
  4294967295, the witness commitment output is present,
  coinbase value 39,073,913 sats equals the template
  coinbasevalue, merkleroot and transaction order match the
  job construction. The fix therefore holds in the block
  Core accepted, not only in the served share.

## 3. extranonce_space

- Default identity: a default engine (cached) and a
  cache-disabled engine both reproduce the legacy stepping
  byte-for-byte at all 64 rounds, compared against
  build_candidate_uncached as the pre-change reconstruction
  (build_candidate itself is unchanged by the phase; the
  only change is the source of the round range). Compared
  fields: header, body, target, height, fees, tx_count,
  witness_count.
- Default mine_cycle stepping order observed through a
  recording backend: rounds 0, 1, 2 in order. On space
  (32, 32): rounds 32, 33, 34 exactly.
- Disjointness: candidate sets of spaces (0, 32) and
  (32, 32) are disjoint and their union is exactly the
  default 64-round candidate set. Space (64, 64) is
  disjoint from the default set and equals the uncached
  candidates at rounds 64..127.
- Refusals: (2^32-1, 2), (2^32, 1), (0, 0), (-1, 4),
  (0, 2^32+1), (2^31, 2^31+1), (5, -1) each raise
  ValueError at construction. Boundary spaces (2^32-1, 1)
  and (0, 2^32) are accepted.
- Caller census (whole tree, .local excluded):
  extranonce_space appears only in mining/engine.py and
  tests/test_exp034_job_template.py. Production
  constructions of MiningEngine: mining/cpu/miner.py line
  129 (3 positional args plus batch_size keyword),
  agent/autonomous.py line 37 (3 positional args), and the
  stood-down mining/testnet4_attempt.py line 69 (3
  positional args plus batch_size keyword). None passes
  extranonce_space, by keyword or by position (the
  parameter is sixth; no caller passes more than three
  positional arguments). No subclass of MiningEngine exists
  in the tree. The default therefore governs every live
  path, and no live behaviour changed.

## 4. Cache trust boundary (EXP-025 note N-2), re-verified

Auditor mutation campaign on a held PreparedTemplate
(build with template=None, the mine_cycle steps shape),
extending the author's A9 to the full field set:

- Follow the mutation into the emitted header (live reads
  from the held object): version, previousblockhash, bits,
  mintime, curtime. Each mutation moved exactly its own
  header field and nothing else (time mutations moved the
  header time to mintime + 1 and to the lowered curtime
  respectively, matching the uncached path's time rule).
- Do NOT follow (prepare-time snapshots): height,
  coinbasevalue, target, coinbaseaux flags,
  default_witness_commitment, and transaction data.
  Mutating any of these left header, body, target and
  height byte-identical.

The boundary is exactly the five live-read header and time
fields, and it matches the EXP-034 report text ("reads
version, previousblockhash, bits, mintime and curtime from
the held template object at build time, and everything
else from the verified prepare") and the original EXP-025
audit note N-2. The documented statement is accurate. The
report's recommendation (snapshot version, prevhash and
bits into PreparedTemplate at prepare time as a deliberate
future hardening) remains a recommendation, not a defect:
no production caller mutates the held object, and
mine_cycle holds it privately for one cycle.

## 5. Suite state, as run by the auditor

Passing (auditor runs, this host):
- tests/test_exp034_job_template.py, run directly: ALL
  PASSED (its own regtest section mined solo block 1155
  and engine block 1156 during the auditor's run).
- make test-template-cache: PASSED (regtest block 1157).
- make test-solo: PASSED.
- make test-mining: PASSED.
- make test-engine: PASSED.
- make test-pow: PASSED (1,165 live regtest headers
  cross-verified against Core).
- make test-exp036: PASSED.
- make test-mainnet-live: PASSED.
- make test-autopilot: PASSED (it observed the live
  autopilot, pid 2895, holding this checkout's lock and
  skipped its restart drill accordingly).
- make test-solo-cutover: PASSED.

Environment failures, observed first-hand by the auditor,
none caused by the changes under audit:
- make test-rtl: fails with "iverilog: not found".
  iverilog is not installed on this VM. Pre-existing.
- make test-cpu-correction: killed by SIGILL ("Illegal
  instruction"). The test builds and runs the C
  SHA-intrinsics library (mining/cpu/build.py build_intrin,
  libbal_intrin.so, compiled with -msha) and this host's
  cpuinfo has no SHA flag, so the first SHA instruction
  faults.
- make test-task003: killed by SIGILL, same mechanism:
  tests/test_task003_corrections.py compiles
  mining/cpu/bal_sha_intrin.c with -msha (its lines 143
  and 150) and runs the binaries. It does import
  MiningEngine, but the EXP-034 engine change is pure
  Python (a range source in mine_cycle plus a constructor
  check) and cannot raise SIGILL; the fault is in the
  native intrinsics binaries, and the process died before
  printing any test output. On the earlier AMD host with
  SHA-NI these targets passed (author's full-suite record
  in RAW_RESULTS, consistent with the EXP-036 audit's
  independent observation of the same SIGILL pattern).
  Neither failing target exercises the solo split code at
  all, and the targets that do exercise both changed files
  (test-exp034, test-solo, test-mining, test-template-cache,
  test-exp036) all pass.

Nothing live was restarted by the auditor: at audit close
the heartbeat shows autopilot pid 2895 and miner pid 2913
with continuous uptime and restarts 0, the same processes
that were live when the audit began. No benchmarks were
run. Nothing was pushed.

## Notes (not defects)

- N-1: The solo server's configured tag (default
  b"/BAL-solo/") still never enters the coinbase it builds,
  as the EXP-034 report records. The auditor confirms the
  served coinbase carries the engine builder's "/BAL/"
  marker. Documentation defect only; the coinbase is
  exactly the constructed one.
- N-2: mine_cycle's in-cycle freshness window and the
  absence of version and timestamp rolling, recorded by
  EXP-034 as gaps for EXP-035 and EXP-038, are outside the
  two changes under audit and were not re-litigated here.
- N-3: The pre-fix solo code was never live (the cutover
  is armed and the mainnet node is still syncing), and the
  auditor's reproduction confirms the defect needed a
  witness-bearing template, which mainnet templates
  effectively always are. Had the cutover fired before
  this fix, the solo server would have served coinbases
  whose extranonce slot and sequence field were corrupted
  on every job. The fix removes that risk entirely, and
  the first mainnet template will exercise the fixed path.
