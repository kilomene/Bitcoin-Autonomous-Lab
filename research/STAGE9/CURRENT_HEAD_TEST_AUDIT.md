# Stage 9.3 Current-HEAD Test Audit

Stage: 9.3 (production correctness and test closure, parts B1
and B2 of the Stage 9 brief, plus the B1 CI tail).
Date: 2026-11-18. Builder run, sequential throughout; no
benchmarks or suites were ever run in parallel.

HEAD basis: production source at the Stage 9.1 baseline state
(remote HEAD 883cf281 at audit; Stage 9.1 pushed at cd65b9b2).
At the start of this run the six production hashes spot-checked
against baseline section 7 matched exactly (mining/
mainnet_live.py, mining/autopilot.py, mining/
candidate_verify.py, mining/engine.py, mining/solo_server.py,
gpu/engine.py). One production file changed during this run:
mining/engine.py, by the defect fix in section 4. Its sha256 is
now 7017cea3732959198895349366c227eb357e281c62bd6b067e12a8dd2a32133b
(baseline: ec5f5687453c94d842cd274c054d13aa723296f46f05edfbc02b2b53f8331a5f).
No other production or test file was modified. Nothing was
pushed by this run.

Environment: hostname htch-runtime; CPU AMD EPYC 9D25
126-Core Processor; nproc 4 (about 2 effective, per the
programme's EXP-031 finding); Python 3.12.3; run window
2026-11-18T03:03Z to about 05:22Z. `which iverilog` exits 1
(not installed). The repository has no requirements.txt,
pyproject.toml or setup.py (standard library only) and, before
this run, no .github directory (discrepancy D-10).

Live stack guard: the mainnet stack was never touched by this
run. Heartbeat before (.local/heartbeat.json at
2026-11-18T03:03:17Z): autopilot_pid 2306, miner_pid 2309,
shares_accepted_total 1042, incident_counts {1003: 1, 2001: 1}.
Heartbeat after (2026-11-18T05:21:50Z): autopilot_pid 4878,
miner_pid 4881, miner_state running, shares_accepted_total
1059, incident_counts {1003: 1, 2001: 1}. The pid change was
not caused by this run: miner_uptime_s 4613.8 at the final
check places the restart at about 04:05Z, the moment a service
restart killed this run's own first re-run batch (SIGTERM) and
wiped /tmp; the keeper restored the stack per its design, and
the share count rose monotonically at every check in between
(1042, then 1048, then 1059). All Part 2 work ran on an
isolated regtest datadir (.local/stage9, RPC 18543) created by
this run; the mainnet node, wallet and
.local/mining-endpoint.json were never opened for writing.

## 1. Method (B1)

Targets were discovered from the Makefile: test-all aggregates
51 prerequisites (the plain test target plus 50 named suites).
Execution followed the 2026-11-17 pattern: `make test-all` was
run first (timestamped log); it halted at the first failing
target (test-rtl, target 12 of 51); the remaining 39
prerequisites were then run individually in test-all order.
Every target was executed. Failures were classified as code
defect, environment limitation, or contention flake, and each
failing target was re-run once in isolation (section 3).

## 2. Results (B1)

First-pass totals: 46 PASS, 5 FAIL of 51.
Final state after isolated re-runs: 48 PASS, 3 FAIL.
The three final failures are test-rtl (environment),
test-exp052 (environment) and test-task0039
(contention-sensitive, failed twice). No code defect was found
in any suite failure; the one genuine defect of this run was
found by Part 2 and is recorded in section 4.

Durations for targets 1 to 12 are their spans inside the
single make test-all run (03:04:20Z to 03:16:21Z, 721 s wall);
durations for targets 13 to 51 are their individual runs.
Check counts are the counts the suites print (their own
"checks" totals where given, otherwise the number of "ok"
result lines).

| # | Target | Result | Checks | Duration |
| --- | --- | --- | --- | --- |
| 1 | test | PASS | 4 ok lines, plus bal-miner genesis search FOUND nonce 2083236893 | 1 s (in make run) |
| 2 | test-regtest | PASS | 5 ok lines | 24 s (in make run) |
| 3 | test-engine | PASS | 9 ok lines | 213 s (in make run) |
| 4 | test-pow | PASS | 4 ok lines (incl. 2,509 live regtest headers cross-verified against Core) | 89 s (in make run) |
| 5 | test-gpu | PASS | 6 ok lines (no GPU present; v512dual backend; CUDA error 35 recorded) | 17 s (in make run) |
| 6 | test-gpu-correction | PASS | 6 ok lines | 41 s (in make run) |
| 7 | test-mining | PASS | 4 ok lines | 16 s (in make run) |
| 8 | test-adversarial | PASS | 6 ok lines | 10 s (in make run) |
| 9 | test-deepening | PASS | 6 ok lines | 265 s (in make run) |
| 10 | test-cpu | PASS | 3 ok lines | 24 s (in make run) |
| 11 | test-cpu-correction | PASS | 14 ok lines | 20 s (in make run) |
| 12 | test-rtl | FAIL, environment | none (suite aborted on its iverilog probe) | 1 s (in make run) |
| 13 | test-solo | PASS | 3 ok lines | 12 s |
| 14 | test-solo-vardiff | PASS | 59 ok lines (59/59, no D12 flake this run) | 583 s |
| 15 | test-solo-cutover | PASS | 10 ok lines | 3 s |
| 16 | test-research | PASS | 3 ok lines | 146 s |
| 17 | test-autopilot | PASS | suite total; live portion skipped by design (see below) | 1 s |
| 18 | test-judgement | PASS | 6 ok lines | 1 s |
| 19 | test-installer | PASS | 2 ok lines | 2 s |
| 20 | test-task003 | PASS | 14 ok lines | 109 s |
| 21 | test-task0038 | PASS | 8 ok lines | 179 s |
| 22 | test-task0039 | FAIL, contention-sensitive | 6 ok lines before the failing check | 12 s |
| 23 | test-avx512 | PASS | 6 ok lines | 41 s |
| 24 | test-avx512dual | PASS | 6 ok lines | 64 s |
| 25 | test-mainnet-live | PASS | 8 ok lines | 12 s |
| 26 | test-template-cache | PASS | 33 ok lines | 25 s |
| 27 | test-avx512flags | PASS | 7 ok lines | 69 s |
| 28 | test-exp036 | PASS | 12 ok lines | 3 s |
| 29 | test-exp034 | PASS | 21 ok lines | 96 s |
| 30 | test-exp037 | FAIL then PASS on re-run | 9 ok lines before the failing check; full pass on re-run | 22 s; re-run 49 s |
| 31 | test-exp038 | PASS | 7 ok lines | 3 s |
| 32 | test-probability | PASS | 73 checks | under 1 s |
| 33 | test-exp039 | PASS | 12 ok lines | 49 s |
| 34 | test-exp040 | PASS | 2 ok lines | 20 s |
| 35 | test-agent-intelligence | PASS | 106 checks | 3 s |
| 36 | test-agent-awareness | PASS | 50 checks | 33 s |
| 37 | test-agent-operations | PASS | 10,309 checks | 194 s |
| 38 | test-agent-security | FAIL then PASS on re-run | full pass on re-run: 116 checks | 587 s; re-run 71 s |
| 39 | test-agent-controller | PASS | 72 checks | 22 s |
| 40 | test-stage8 | PASS | 18 checks | 7 s |
| 41 | test-exp049 | PASS | 20 checks | 7 s |
| 42 | test-exp050 | PASS | 40 checks | 14 s |
| 43 | test-exp051 | PASS | 8 ok lines | 5 s |
| 44 | test-exp053 | PASS | suite total (Gate 2 suite) | 8 s |
| 45 | test-exp054 | PASS | suite total (Gate 2 suite) | 31 s |
| 46 | test-exp055 | PASS | 23 checks | 13 s |
| 47 | test-exp057 | PASS | 15 checks | 47 s |
| 48 | test-exp058 | PASS | 10 checks | 2 s |
| 49 | test-exp056 | PASS | 16 checks | 13 s |
| 50 | test-exp052 | FAIL, environment | 42 ok lines before the failing check | 46 s; re-run 7 s, same failure |
| 51 | test-incident-codes | PASS | 34 checks | 17 s |

Expected behaviours verified, not assumed: test-autopilot
printed "SKIP: a live autopilot owns this checkout (pid 2306);
lock verified by its existence" and then ALL AUTOPILOT TESTS
PASSED, exactly the designed live-stack behaviour.
test-solo-vardiff passed 59/59 on its first run; the D12
contention flake recorded on 2026-11-17 did not recur.

## 3. Failures and classification (B1)

test-rtl (environment limitation): the suite aborts with
"AssertionError: /bin/sh: 1: iverilog: not found". iverilog is
not installed on this VM (`which iverilog` exits 1). Identical
to the 2026-11-17 record. Not a code defect; not marked
passed; not skipped silently.

test-exp037 (contention / live-state race; passed on isolated
re-run): test_real_log_matches_brute_force compares the
incremental census of the live evidence log against a
brute-force recount. It failed with last_epoch 1794973221.0
from the counter against 1794973168.0 from the recount: the
live miner appended fresh evidence lines between the two
reads, so the two snapshots legitimately differ. Isolated
re-run: PASS (49 s). The check is deterministic on a static
log (see the cleanroom result in section 6, where it passes
against the tracked, unchanging evidence file).

test-agent-security (contention flake; passed on isolated
re-run): the sandbox limits test failed at item 11, "a memory
hog is killed by the memory limit (reason memory, wall
53.5073)": under the load of the surrounding run the hog did
not reach the memory limit before the wall-clock bound, so
the termination reason differed. First run 587 s; isolated
re-run PASS in 71 s (116 checks). The 8x duration difference
between the two runs is itself the contention signature.

test-task0039 (contention-sensitive; FAILED twice, recorded
as FAIL): test_early_exit_accounting searches the C backend
from 3 nonces before the genesis nonce over a 100,000 range
and asserts the counted attempts stay below 10,000. It failed
with attempted 32519 on the first run and failed again on the
isolated re-run (exit 2, 12 s both times; the re-run log was
lost when the service restart wiped /tmp, the exit and
duration were captured in the re-run batch record). The
exact-accounting identities the suite exists to pin
(backend_hashes == attempted, unique_coverage == attempted,
exactly 1 verification hash, device 0) all passed in both
runs, as did the overflow, split and full-range checks before
the failing one. The failing bound is a promptness heuristic
on a parallel early-exit search: with 8 auto-tuned C threads
racing on a VM whose CPUs are shared with the live miner,
worker sub-batches complete before the stop propagates, and
the overshoot grows with load. The suite passed at this same
source on 2026-11-17. Classification: contention-sensitive
test bound, not a production accounting defect. No code was
changed for it: loosening the bound to make it pass would be
tuning a test to the environment, which this audit does not
do. It is carried in the defects section as an open item for
an owner or auditor decision (for example, running this suite
on a quiet host, or bounding the thread count inside the
check).

test-exp052 (environment limitation: host-instance
fingerprint drift; FAILED deterministically, recorded as
FAIL): Gate 5a resolves the EXP-052 campaign cache and expects
the reason "static:". The resolver instead returned
("auto", "doubt: host fingerprint mismatch ... static order"),
its designed fail-closed fallback. Proven directly against
the live code: the campaign cache fingerprint is
{cpu_model "AMD EPYC 9D25 126-Core Processor", flags_hash
51d3e983ddf6ac93, logical_cpus 4}; this VM instance reports
the same model and count but flags_hash c86584c209897fb5.
host_fingerprint() (a sha256 over the sorted /proc/cpuinfo
flag set) was verified stable across calls on this instance,
so the campaign instance simply exposed a different flag set,
as happens between VM instances of the same CPU model. The
production behaviour is correct and is itself verified by
this outcome: on fingerprint doubt the resolver falls back to
the static order and returns "auto". The check as written can
only pass on the exact instance class that produced the
cache. 42 checks passed before Gate 5a in both runs.
Classification: environment limitation with a test-design
sensitivity note (section 7); no production change made.

## 4. Defect found by Part 2 and fixed

Part 2's first submission was rejected by Bitcoin Core 28.1
with bad-cb-height (evidence preserved in
research/STAGE9/evidence_93/failed_height1_attempt/,
including the Core debug.log lines and the rejected block).
Root cause: mining/engine.py script_num_push encoded the
coinbase height as a push of its CScriptNum bytes for every
value (height 1 became the bytes 01 01). Core's coinbase
prefix check builds the expected prefix with
CScript::operator<<(int64_t), which encodes 1 to 16 as the
single opcodes OP_1 to OP_16 (and 0 as OP_0, -1 as
OP_1NEGATE). Core's own generatetoaddress coinbase at regtest
height 1 carries 51 00, confirming the expected form. For
heights of 17 and above the two encodings coincide, which is
why every historical lab block (heights in the thousands, on
the shared regtest node and in template construction for
mainnet) was unaffected, and why the defect only ever fired
on a fresh chain's first 16 blocks.

Fix (small, production, documented in the code): script_num_push
now mirrors CScript::operator<<(int64_t) exactly: 0 returns
OP_0, -1 returns OP_1NEGATE, 1 to 16 return the single OP_N
byte, and all other values keep the previous minimal
CScriptNum push. The function is the single height encoder
for the production GBT path (mining/engine.py build_coinbase)
and for the solo server, which builds its coinbase through
the same function. No test file was changed.

Post-fix verification: (a) the Part 2 block at regtest
height 1 was accepted by Core (section 5); (b) the neighbour
suites were re-run: test PASS (2 s), and, after the shared
regtest node was restored (see below), test-mining PASS
(35 s), test-template-cache PASS (23 s), test-exp034 PASS
(68 s), test-solo PASS (19 s), test-stage8 PASS (8 s). The
first neighbour batch failed all five node-dependent suites
at node_manager.start() with "bitcoind started but RPC did
not answer in time": the shared regtest node had been stopped
by the 04:05Z service restart, and a stray cleanroom bitcoind
from section 6's simulation was holding port 18443 with
different credentials, so the main node's start could not
bind. The stray process (this run's own) was stopped, the
shared node started (413.6 s to full RPC under load; chain at
height 2515), and all five suites then passed. None of those
five failures was caused by the fix; each traceback terminates
in node_manager.start(), before any mining code runs.

## 5. Candidate and block correctness (B2)

Method: Bitcoin Core 28.1 (binaries at
~/workspace/bitcoin-core-dist/bitcoin-core-28.1/bin/) on a
fresh isolated regtest datadir (.local/stage9/data, RPC
18543, P2P 18544), used as the independent consensus
reference. Construction, search and verification used the
production code path (MiningEngine from mining/engine.py,
ComputeEngine from gpu/engine.py, verify_candidate from
mining/candidate_verify.py). The driver is preserved in the
evidence bundle (b2_run.py, b2_topup4.py). All raw evidence
is in research/STAGE9/evidence_93/.

Regtest target and probability, stated plainly: the template
carried nBits 0x207fffff, which compact-decodes to the
integer target
57896037716911750921221705069588091649609539881711309849342236841432341020672
(0x7fffff followed by 29 zero bytes; decoded_target.txt).
The probability that one hash meets this target is
0.49999994, and the expected number of hashes per block is
2. This is regtest's configurable minimum difficulty
(Core reported difficulty 4.656542373906925e-10). It is not
mainnet-equivalent in any sense: at the programme's worked
example mainnet difficulty of 134,823,837,323,272, the
expected hashes per block are about 5.79e23 (difficulty times
2^32). Nothing in this section is evidence about mainnet
mining speed or mainnet block probability.

Block 1 (the end-to-end bundle), height 1:

- Template: getblocktemplate from Core, 0 transactions,
  coinbasevalue 5,000,000,000 (template_block1.json).
- Construction: MiningEngine.build_candidate at extranonce 0;
  the EXP-025 cached path and build_candidate_uncached agree
  byte for byte. Header is exactly 80 bytes; version, prevhash
  (internal byte order, the reverse of the template display
  hash) and bits all match the template fields.
- Merkle root: recomputed independently from the raw block
  body (txid of the single coinbase transaction, via
  mining.engine.txid_of) and by mining.pow.merkle_root; both
  equal the header's merkle field.
- Witness handling at block 1: the template carried no
  witness transactions (witness_count 0), so the coinbase
  correctly carries no commitment output. Core still served a
  default_witness_commitment for the empty witness set
  (6a24aa21a9ede2f61c3f71d1defd3fa999dfa36953755c690689799962b48bebd836974e8cf9,
  the commitment over the empty set), which the engine does
  not need to include when no transaction carries witness
  data; Core's acceptance of the block is the deciding
  evidence. The witness-carrying case is proven separately
  below.
- Search: ComputeEngine (backend v512dual, selected by CPUID
  probe and digest self-test; CUDA absent, error 35 recorded)
  found nonce 5 after 32 counted attempts at extranonce 0.
  The engine-reported digest equals hashlib SHA-256d of the
  reconstructed header.
- Candidate reconstruction: the 80-byte header rebuilt from
  its six fields alone (version, prevhash, merkle root, time,
  bits, nonce) is byte-identical to the searched header.
- Digest agreement: hashlib (OpenSSL) SHA-256d and the
  from-specification pure-Python SHA-256d
  (mining.pow_engine.double_sha256_pure) agree byte for byte.
- Target handling: compact_decode of nBits 0x207fffff equals
  the template target integer exactly, with negative and
  overflow flags false, and the target is within the regtest
  proof-of-work limit. The integer comparison
  value <= target holds exactly (value
  5a8d6d254ef255972ce50a8f832c1fb99cef69e61839a2550a6f037d72dbc35d
  in display order; verify_candidate.json, computed_digest.txt).
- Production verifier: verify_candidate classified the header
  "block_candidate" with digests_agree true and
  meets_network_target true; check_pow returned ok.
- Submission and acceptance: submitblock returned None
  (accepted for processing; submitblock_response.txt);
  verify_chain_acceptance reported "tip";
  getblockchaininfo showed blocks 1 with bestblockhash equal
  to the block hash (getblockchaininfo_after.json); getblock
  confirmed the block at height 1 with 1 confirmation
  (getblock.json). Block hash:
  5a8d6d254ef255972ce50a8f832c1fb99cef69e61839a2550a6f037d72dbc35d.
  Raw block and header hex: block_hex.txt, header_hex.txt.

Boundary behaviour, exercised in code (boundaries.json):

- MiningEngine.batch_count: (65536, 0) gives 65536;
  (65536, 2^32-1) gives 1; (2^32, 0) gives 4294967296;
  start 2^32 raises ValueError ("batch start outside the
  nonce space").
- gpu.engine.validate_nonce_range: (2^32-1, 2) raises
  ValueError ("start 4294967295 exceeds the nonce space for
  count 2"); (0, 2^32) is accepted.
- Nonce edges are searched and reachable: with the maximum
  target, a one-nonce search at nonce 0 hits nonce 0, and a
  one-nonce search at nonce 2^32-1 hits nonce 4294967295,
  each with exactly 1 counted attempt.
- Extranonce space refusal: MiningEngine construction with
  spaces (0, 2^32+1), (2^32-1, 2) and (-1, 4) each raises
  ValueError; extranonce 2^32-1 builds successfully;
  extranonce 2^32 raises struct.error from the 32-bit pack
  ("'I' format requires 0 <= number <= 4294967295"), so an
  out-of-range extranonce can never silently wrap. The solo
  server's own extranonce2 size refusal ("bad extranonce2
  size") is covered by the test-solo and test-exp034 suites
  in section 2, which pass; it was not re-exercised here.

Witness commitment proof (same isolated chain, completed by
continuation; witness.json, getblock_witness.json): a real
segwit transaction (txid
c58dc8411d7846bb80bc91f77be4f943ae2a76e3ef0a35afc86b06f8dd5ff728)
entered the template at height 145. The production
construction reported witness_count 1; the commitment
recomputed independently from the raw transaction data
(wtxid merkle root over the reserved zero hash plus the
transaction wtxids, double SHA-256 with the reserved value)
is bcb634d89abd83d3ffc8bfb29335306e78eccb3edb8fbe82c66d43a9a973d9b7,
which matches Core's served default_witness_commitment
(6a24aa21a9edbcb634d89abd83d3ffc8bfb29335306e78eccb3edb8fbe82c66d43a9a973d9b7)
and sits in the built coinbase behind the aa21a9ed header.
The block was searched with the production ComputeEngine
(fallback tier, reported backend "cpu"), classified
block_candidate by verify_candidate, submitted with
submitblock (response null) and confirmed in the best chain
at height 145 with 1 confirmation and 2 transactions. Block
hash: 2f62cd4dda6296b8467d303f2e7514539d4c72bc59a90cb5503fc43246a8120b.

Disclosure on how the witness proof was reached: the main
run's witness phase, and three further production-mined
funding attempts, each mined 80 or more blocks through
mine_cycle and then hit a reproducible environment stall:
the isolated node took minutes to connect a block in the
height 80s, so submitblock responses timed out (in one case
the block connected only after a 900 s tip poll; the record
is in witness_run2_timeout.json and witness.json's history
fields). Funding for the final witness run was therefore
completed with Core's own generatetoaddress (Core-mined
funding blocks, used only to mature a coinbase; the stage9
chain stood at height 144 with wallet balance 2200.0 BTC
when the witness steps ran). The funding method does not
bear on the proof: template supply, segwit transaction,
candidate and commitment construction, search, verification,
submission and acceptance were all production path and Core
judged, as itemised above. The same node-stall pattern is
consistent with this VM's known behaviour (the mainnet node
shows multi-minute RPC stalls during initial block download
on the same host), and blocks 1 to 86 of every attempt, plus
blocks 87 to 144 of the final chain, connected normally.

A note on the isolated datadir: across this run's several
node instances, freshly started instances twice reported the
stage9 chain at genesis while later instances reported the
persisted heights (87, then 144). Every evidence item in
this section was captured live from Core within the instance
that produced it, and the block hashes, templates and Core
responses in the bundle are internally consistent. The
datadir itself (.local/stage9) is scratch state created by
this run and carries no ongoing role.

## 6. CI record (B1 tail)

The repository had no CI (no .github directory; discrepancy
D-10). This run adds .github/workflows/test.yml: on push to
main it sets up Python 3.12 and runs a conservative subset of
the Makefile suites. There is no requirements file to install
(the lab is standard library only), and the workflow says so.

The subset was determined empirically, not by assumption:
each candidate suite was run in a cleanroom copy of the
repository (the full tree minus .local, minus every .so,
minus the bal-miner binary), simulating a clean checkout.
Cleanroom results: PASS for test-exp037 (13 s), test-exp038
(2 s), test-probability (under 1 s), test-exp049 (45 s),
test-exp051 (38 s), test-exp053 (11 s), test-exp054 (28 s),
test-exp058 (2 s). FAIL for test-exp050 (its Gate 5 isolated
instance copies the built libraries in .local/cpu, absent in
a clean checkout), test-exp055 and test-exp057 (their Gate 6
portions start a regtest bitcoind via node.node_manager), and
test-incident-codes (its replay reads the live
.local/autopilot.log). test-exp036 was excluded without a
cleanroom run because its test file imports node.node_manager
and a SoloServer node fixture (it requires a Core node).
test-exp052 is excluded as host-keyed (section 3), test-exp056
needs the local z3 virtualenv, and test-rtl needs iverilog.

The workflow therefore runs exactly 8 suites: test-exp037,
test-exp038, test-probability, test-exp049, test-exp051,
test-exp053, test-exp054, test-exp058. The workflow file
carries the full inclusion and exclusion reasoning as
comments and writes a step summary naming what it ran and
what it excluded and why. The YAML was validated locally
(it parses; the top-level "on" key is the standard GitHub
Actions trigger key). The workflow was not triggered by this
run: its first run happens on the parent's push, and per the
standing rule there will be exactly one such run, with any
failure fixed locally first.

## 7. Defects and open items

D-93-1 (FIXED, production): coinbase height encoding for
heights 1 to 16 in mining/engine.py script_num_push used the
push-data form where Core requires the OP_N form; Core 28.1
rejected the resulting block at regtest height 1 with
bad-cb-height. Fixed to mirror CScript::operator<<(int64_t);
proven by Core's acceptance of the height-1 block and by the
neighbour suite re-runs in section 4. New sha256 for
mining/engine.py:
7017cea3732959198895349366c227eb357e281c62bd6b067e12a8dd2a32133b.
The parent should push this fix together with this audit.

D-93-2 (open, test sensitivity): test-task0039's early-exit
promptness bound (attempted below 10,000) fails under
live-miner contention on this VM (observed 32,519) while its
exact-accounting checks pass. Recorded as FAIL in this audit.
Needs an owner or auditor decision: quiet-host run, or a
thread bound inside the check. Not silently adjusted here.

D-93-3 (open, test sensitivity): test-exp052 Gate 5a can only
pass on a host instance whose /proc/cpuinfo flag set hashes
to the campaign cache's fingerprint (51d3e983ddf6ac93); this
instance reports c86584c209897fb5, and the resolver's
fail-closed fallback (the behaviour the gate exists to
protect) is what the run actually verified. Recorded as FAIL
(environment). A future revision could accept the "doubt:"
fallback as a passing outcome when the fingerprint mismatch
is proven, but that is a test-design change for the auditor,
not for this run.

D-93-4 (environment, no action): test-rtl requires iverilog,
absent on this VM and not installed by the new CI workflow.
The suite's failure mode is honest (it aborts naming the
missing tool).

Operational notes from this run (no code impact): a service
restart at about 04:05Z wiped /tmp, losing the first-pass
per-target log files (their salient contents had already
been extracted into the progress log and are reproduced in
section 2) and killing the first re-run batch after two
results; the keeper restored the live stack, whose pids
therefore differ between this audit's before and after
heartbeats. The cleanroom simulation left a stray bitcoind
holding port 18443, which blocked the shared regtest node's
restart until it was identified and stopped; that, and not
the section 4 fix, caused the first post-fix neighbour batch
failures.

## 8. Deliverables of this run

- research/STAGE9/CURRENT_HEAD_TEST_AUDIT.md (this file).
- research/STAGE9/evidence_93/: the Part 2 raw evidence
  bundle (template, header and block hex, decoded target,
  computed digest, verifier output, submitblock response,
  getblock and getblockchaininfo outputs, boundary results,
  witness proof files, the preserved failed height-1 attempt
  under failed_height1_attempt/, the run drivers b2_run.py
  and b2_topup4.py, and summary.json whose every check
  passes, with the witness completion annotated).
- .github/workflows/test.yml: the CI record of section 6.
- mining/engine.py: the section 4 fix (the only source
  change).
- Progress log:
  ~/workspace/goals/bitcoin-autonomous-lab-private-bitcoin-mining-lab/hidden_files/stage9-3-progress.md
