# EXP-034: Autonomous Job and Template Engine

Date: 2026-11-15. Phase E of the EXP-030 programme (directive
section 7). Scope: independent verification of the integrated
EXP-025 template cache against the directive's adversarial
standard; an end-to-end audit of job construction on the GBT
engine path and the solo server path; extranonce space
separation between engines; and template freshness on all
three production paths.

Method: a new adversarial test file,
tests/test_exp034_job_template.py (Makefile target
test-exp034, wired into test-all), designed for this audit and
not a rerun of the EXP-025 integration gates in
tests/test_template_cache.py. It combines synthetic-template
cases (stub RPC), fake-node freshness probes, and live regtest
checks against Bitcoin Core 28.1 (node tip 1101 at start; the
run mined solo block 1104 and engine block 1105). Raw output:
RAW_RESULTS/exp034_test_run_2026-11-15.txt. No throughput
benchmarks were run (not this phase's scope). Nothing live was
restarted; the endpoint config and the solo cutover marker
were not touched.

Two production changes came out of this phase, both small,
both flagged in sections 3 and 4 below: a correctness fix to
the solo server's coinbase split (a real defect, found by
test C3) and an opt-in extranonce_space parameter on
MiningEngine (default behaviour byte-identical).

## 1. Template cache: independent adversarial verification

The EXP-025 standard is that a cached serve must be
byte-identical to the uncached construction for every valid
template, must refuse (TemplateError) every invalid one, and
must never serve one template's prepared work under another
template's identity. The earlier gates covered the EXP-023
defect cases D1 to D7, ordering, fees, and a 1,320-case
differential campaign. The eleven cases here probe what that
set did not:

VERIFIED (all in section A of the test file):

- Height-only change (subsidy equal across the boundary, so
  coinbasevalue is untouched): the coinbase layer key binds
  the height, the sibling serve is refused, a new entry is
  prepared, output byte-identical to uncached. Height was not
  in the EXP-025 case list.
- Same-count transaction replacement with a different fee and
  coinbasevalue adjusted to match (valid): new identity,
  byte-identical output. (Covered in combination with the
  fee and value cases; the tx layer keys txid, wtxid and fee
  per transaction in order.)
- mintime is a per-build input and is NOT keyed, as designed:
  raising mintime to curtime serves under the same identity
  and the header time becomes mintime + 1 on both paths,
  byte-identical. curtime behaviour was already covered by
  EXP-025; the mintime leg was not.
- Extranonce stepping anatomy: consecutive steps of a
  prepared entry differ only through the coinbase and its
  merkle root; version, prevhash, time and bits are constant;
  the body tail is the template transactions verbatim.
- Cache bound: the cache caps at 128 entries over 330
  prepares, evicts oldest-first, an evicted identity
  re-prepares as a miss, a resident one hits, and a
  PreparedTemplate object already held by a caller survives
  eviction of its dict entry and keeps building
  byte-identical candidates (this is the property the
  mine_cycle steps shape relies on).
- Equal-content sibling (deep copy, different object) serves
  under the prepared identity with no new prepare.

Safe over-keying (identity changes, output bytes do not; the
safe direction, recorded so nobody "optimises" it away):

- A default_witness_commitment field appearing on a template
  with no witness transactions: the field string is keyed
  even though no commitment is computed, so the identity
  changes and a fresh entry is prepared; every output byte is
  identical.
- A dwc string padded with an extra byte: the cross-check is
  a substring check (the computed commitment must appear in
  the field), mirrored exactly from the uncached path, so the
  padded string validates on both paths; because the full
  string is keyed, it prepares rather than serves.
- A case-only change to the target hex string: the header
  layer keys the target STRING, not the decoded integer, so
  the identity changes while the target value and every
  output byte stay the same.

Robustness in the other direction (identity correctly does
NOT change): fields Core returns that construction never
reads (per-transaction weight, vsize, depends; template
longpollid, capabilities) are neither keyed nor used, and a
missing coinbaseaux object behaves as empty flags on both
paths. Core adding fields cannot poison the cache.

The held-object trust boundary (pinned, not a live defect):
the steps path reads version, previousblockhash, bits,
mintime and curtime from the held template object at build
time, and everything else (merkle levels, transaction bytes,
coinbase inputs, target, height, value) from the verified
prepare. Section A9 mutates the held dict in place and shows
exactly that split: version, prevhash and bits follow the
mutation into the emitted header; a transaction mutation
moves neither root nor body. This is the boundary the
EXP-025 audit recorded as note N-2, re-verified independently
here. No production caller mutates the object (mine_cycle
takes it fresh from the RPC and holds it privately for one
cycle), so nothing live is exposed; the recommendation
stands that a future hardening snapshot version, prevhash
and bits into PreparedTemplate at prepare time (all three
are identity-keyed, so a snapshot can only ever equal what a
legitimate serve would read). Not implemented here: it
changes audited code beyond this phase's fix budget, and the
parent should schedule it deliberately.

Verdict for the cache: VERIFIED. No stale serve, no
validation bypass, and no silent identity confusion was
found under any case constructed; the identity is in three
places stricter than the output requires, never looser.

## 2. Job construction against Bitcoin Core

Engine path (test B3): on a real GBT with 6 mempool
transactions (legacy and segwit mixed), cached and uncached
constructions are byte-identical, and the block mine_cycle
mined (regtest height 1105) matches Core's own record on
every checked field: the merkle root (recomputed
independently from the block's coinbase txid plus the
template txids), the transaction order (coinbase first, then
template order), the coinbase value (39,079,798 sats, exactly
the template coinbasevalue), the payout script, and the
witness commitment output (present, equal to the template's
default_witness_commitment).

Solo path (tests B1, B2): on a 6-transaction template the
merkle branch served to workers has depth 3, and the header
the worker-side builder (mining/stratum_client.build_header,
wordswap mode) assembles from coinb1, extranonce1,
extranonce2, coinb2 and the branch is byte-identical to the
header the server computes from the full transaction list.
A share driven through submit_share produced a block Core
accepted at height 1104, with Core's merkleroot and
transaction order matching the job construction and
EXP-036 chain verification recorded on the block record.

Coinbase anatomy across paths (test C3), relevant to
section 3: the engine coinbase scriptSig is the BIP34 height
push, the marker "/BAL/", and the 4-byte extranonce (plus
coinbaseaux flags when Core supplies them). The solo
coinbase scriptSig is the height push, "/BAL/", extranonce1
(4 bytes, per connection) and extranonce2 (4 bytes, per
share). The solo server's own configured tag (default
b"/BAL-solo/") never enters the coinbase it builds: the
tag parameter is stored and unused, and the coinbase
carries the engine builder's marker. Recorded as a
documentation defect in SoloServer (the attribute implies a
separation that does not exist), not a correctness defect.

## 3. DEFECT FOUND AND FIXED: solo coinbase split offset

Found by test C3's scriptSig anatomy assertion, on its first
run. In SoloServer.refresh_job, the extranonce split offset
was located in the FULL coinbase returned by build_coinbase
and then applied to the STRIPPED coinbase:

    at = coinbase.index(marker) + len(b"/BAL/")
    stripped, has_witness = strip_witness(coinbase)
    coinb1 = stripped[:at]
    coinb2 = stripped[at + 8:]

When the coinbase carries a witness commitment, the full
form has the 2-byte segwit marker and flag ahead of the
input, so the offset lands 2 bytes late in the stripped
form. Consequences, all verified from the pre-fix test
output (served scriptSig was height push + "/BAL/" + the
bytes 0xee 0xee + extranonce1 + only the first 2 bytes of
extranonce2, inside a declared 16-byte scriptSig):

- coinb1 retained the last 2 placeholder bytes (0xee 0xee);
- the final 2 bytes of extranonce2 fell outside the
  scriptSig and overwrote the first 2 bytes of the coinbase
  sequence field;
- the served coinbase was therefore never the coinbase the
  builder constructed, on any template with a witness
  commitment (on mainnet, effectively every template).

Worker and server stayed consistent with each other (both
concatenate the same coinb1 and coinb2), and the BIP34
height push and the witness commitment output survive the
shift, so a block found this way would very likely still
have been accepted by Core; the damage is to the extranonce
model (2 of the 8 slot bytes frozen, 2 relocated into the
sequence) and to any external worker reasoning about the
coinbase. The existing solo tests never exercised it: they
mine on an empty mempool, whose templates carry no witness
commitment, where full and stripped forms coincide and the
offset is correct. The solo server is not yet live (the
cutover is armed and the mainnet node is still syncing), so
no live work was ever served this way.

Fix (mining/solo_server.py, flagged production change): the
marker is now located in the stripped bytes, with a comment
recording why:

    stripped, has_witness = strip_witness(coinbase)
    at = stripped.index(marker) + len(b"/BAL/")

For witnessless coinbases stripped == coinbase, so behaviour
there is byte-identical to before; for witness coinbases the
split is now exact. Coverage: test C3 asserts the assembled
scriptSig byte for byte; test B1 asserts worker/server header
agreement on a segwit template; test B2 mines a block
through the fixed path; the pre-existing test-solo and
test-exp036 suites stay green (section 6).

## 4. Extranonce space separation

The Phase B flag is confirmed, precisely:

- Two MiningEngine instances with the same payout address,
  fed the same template, build byte-identical candidates at
  every one of the 64 extranonce rounds mine_cycle steps
  (test C1, byte-for-byte on header and body). Same coinbase,
  same headers, same nonce scan order: two such engines
  running concurrently duplicate each other's work exactly,
  hash for hash. This is the default configuration of the
  GBT path (the autonomous agent and the CPU aspect miner
  both construct MiningEngine this way).
- The only separation the GBT path had is the payout script:
  a different payout address changes the coinbase and
  separates the spaces (test C2). Nothing else does: no
  worker identity, instance id, or tag enters the engine
  coinbase.
- Engine versus solo server do not collide in the default
  configuration: the solo scriptSig is 4 bytes longer
  (8-byte extranonce slot against the engine's 4-byte
  extranonce, flags empty), so no solo coinbase can equal
  any engine coinbase for any extranonce values (test C3).
  The theoretical edge: if Core supplied a coinbaseaux flags
  string of exactly 4 bytes, the lengths would coincide, and
  a solo share whose extranonce1 equalled an engine round
  and whose extranonce2 equalled the flags bytes would
  reproduce an engine coinbase. Core's flags are empty in
  every template observed here; recorded for completeness,
  not treated as a live risk.
- Pool path: separation is the pool's per-connection
  extranonce1 plus the runner's per-session extranonce2
  counter (mining/mainnet_live.py), as Phase B recorded;
  unchanged by this phase.

Fix (mining/engine.py, flagged production change):
MiningEngine gains an opt-in extranonce_space=(first_round,
round_count) constructor parameter, default (0, 64), which
is the historical behaviour exactly. mine_cycle steps the
configured rounds; build_candidate is unchanged and still
takes an absolute extranonce. Out-of-range spaces (beyond
the 32-bit extranonce) are refused at construction. Test C4
proves: engines configured (0, 32) and (32, 32) build
disjoint candidate sets whose union is the default set; the
default attribute is (0, 64); mine_cycle observed through a
recording compute backend steps exactly the configured
rounds (32, 33, 34 for a (32, 32) engine; 0, 1 for the
default). All pre-existing engine consumers construct with
defaults, so no live behaviour changes until a coordinator
assigns spaces; assigning, persisting and leasing those
spaces is EXP-035's work, and this parameter is the hook it
should use. The design, for EXP-035: partition the 32-bit
extranonce as high bits = worker or instance identifier
(the Qaxe CAN pattern from Phase A, extranonce2 =
(slave_id << 25) | counter), low bits = the round counter,
with the coordinator recording which space each worker
holds so duplicated work is provably impossible rather than
merely unlikely.

## 5. Template freshness

Solo JobRefresher (test D1, fake node): new-work detection
keys on the node's best block hash compared with the served
template's previousblockhash, polled every 2 s in
production, plus a 120 s maximum job age. Behaviour proven:
an unmoved tip and a young job produce no refresh (mere
passage of time, and with it any ntime movement, does not
trigger one); a tip move triggers a refresh on the next
poll; the age cap refreshes even with an unmoved tip. A
refresh replaces the job table wholesale (self.jobs =
{new job}), which is the cancellation semantics: a share
submitted for a superseded job id is rejected as
"unknown job" (proven). There is no grace window for
in-flight shares on the old job; on the solo path that is
acceptable (shares are cheap and the worker is notified of
the new job by broadcast), and it is now documented rather
than implicit.

GBT MiningEngine (test D2): freshness granularity is the
mine_cycle boundary. get_template is fetched once per
cycle; a tip change arriving mid-cycle does NOT invalidate
the work in flight (the probe flips the template after the
first batch and every subsequent header still carries the
old prevhash); the next cycle picks the new template up.
The stale window is bounded by the cycle budget
(max_batches batches or deadline_seconds, defaults 200 and
120 s). wait_template (GBT longpoll) exists on the engine
but has no production caller anywhere in the tree (grep
over mining/, agent/, gpu/, scripts/: only the definition),
so the autonomous path's real freshness is per-cycle
fetch, not longpoll. That is the weakest freshness story of
the three paths and the report records it plainly: wiring
longpoll (or a mid-cycle prevhash check against
getbestblockhash every N batches) is a small, well-defined
improvement for EXP-038 to schedule; it was not made here
because it changes the mining loop's timing behaviour,
which deserves its own gate.

Stratum client (test D3): the pool path's guards are the
strongest of the three. An accepted notify increments
job_generation and supersedes work in progress; an exact
duplicate (job id, prevhash, ntime) is logged and ignored;
a notify for the same prevhash with a regressed ntime is
rejected as a stale echo; and, the direct W4 comparison, a
notify for a NEW prevhash with an OLDER ntime is accepted
as new work. New-work detection is prevhash-keyed, with
ntime used only as a regression guard within one tip and a
plus/minus 2-hour sanity window in validate_job.

W4 verdict: the Qaxe firmware weakness Phase A flagged
(new-work detection keyed on ntime only; a new prevhash
inside the same second is not flagged as new work) is NOT
present in any NOVA path. The solo refresher keys on the
tip hash itself, the Stratum client keys on prevhash
change, and the engine keys on cycle-boundary refetch.
NOVA does better than the reference pattern on all three,
with the engine's in-cycle window the one bounded
exception above.

Version and timestamp rolling: absent from production, as
Phase B recorded for component 15, and re-verified here by
evidence rather than reading alone: across a full
mine_cycle the header version never varies (test D2 asserts
a single version across all recorded headers), the Stratum
client submits the job's version and ntime verbatim, and
the solo server validates ntime against the template
mintime and a 2-hour future bound but no miner-side rolling
exists on any path. The only production search-space
expansion mechanisms are the nonce, the engine extranonce
rounds, and the solo/pool extranonce pair. Directive
section 7 lists version rolling and timestamp rolling as
job-model features; they remain a genuine gap, owned by
EXP-035's search-space expansion work, and nothing in this
phase claims them.

## 6. Test and suite state

New: tests/test_exp034_job_template.py, 21 checks across
sections A, B, C, D, all passing (raw output in
RAW_RESULTS/). Makefile target test-exp034 added and wired
into test-all (28 targets).

Neighbouring suites re-run after both production changes,
all passing: test-template-cache, test-mining, test-solo,
test-exp036, test-mainnet-live, test-autopilot,
test-solo-cutover, test-pow.

Full suite: 25 of the 28 test-all targets pass, including
every suite that exercises the two changed files. The three
failures are all environment, none is caused by this phase
(full accounting in RAW_RESULTS/full_suite_2026-11-15.txt):
test-rtl (iverilog is not installed on this VM; pre-existing
and acknowledged); test-cpu-correction and test-task003,
both killed by SIGILL because they build and run the SHA
intrinsics library and the VM's current host (Intel Xeon
Platinum 8321HC, after a VM replacement) has no SHA
extension in its cpuinfo flags. The earlier programme work
ran on an AMD host with SHA-NI, where the suite passed with
only test-rtl failing. These two targets cannot execute on
this host at all; they are reported, not hidden, and
nothing in the EXP-034 diff touches the code they run.

## 7. Verified versus unproven

VERIFIED by execution in this phase:
- The EXP-025 cache identity refuses or re-prepares on
  every adversarial change constructed, including the new
  height, fee-with-value, and representation cases; cached
  output is byte-identical to uncached in every valid case,
  synthetic (sections A, C) and real (section B).
- Cache bound, eviction order, and held-entry survival.
- Engine and solo job construction against Core on regtest,
  including merkle roots, transaction order, coinbase
  value, payout script, witness commitment, branch versus
  full-root agreement, and two accepted blocks (1104 solo,
  1105 engine).
- The solo coinbase split defect (pre-fix bytes preserved
  in RAW_RESULTS) and its fix.
- The two-engine extranonce collision, byte for byte, and
  the disjointness of the new extranonce_space fix.
- Freshness behaviour of all three paths, including the
  W4 comparison.

DOCUMENTED FROM CODE, NOT EXECUTED (labelled as such):
- The 4-byte-flags engine/solo coinbase collision edge
  (requires a flags value Core does not produce in observed
  templates).
- The claim that the pre-fix solo coinbase would still have
  produced Core-acceptable blocks (reasoned from BIP34 and
  BIP141 structure; the pre-fix code was never run against a
  node with a segwit template before being fixed, by
  design).

UNPROVEN / NOT DONE, honestly:
- No protocol-independent job model, persistent job
  records, or shared job generation identifiers were built;
  the three job representations remain separate (Phase B
  component 6). EXP-034 verified the existing machinery;
  the unification remains EXP-035/036 prerequisite work.
- Version rolling and timestamp rolling remain absent.
- The PreparedTemplate header-field snapshot hardening is
  recommended, not implemented.
- No mainnet template was used: every live check is
  regtest, and the solo fix will first meet a mainnet
  template at the armed cutover.
