# Post-Integration Audit: AVX-512 Multi-Buffer Production Backend

Date: 2026-11-14. Auditor: independent post-integration audit
(the auditor did not write the integration). Subject: the
production integration recorded in PHASE6_FINAL_REPORT.md,
addendum of 2026-11-14 (ComputeEngine backend "v512",
mining/cpu/bal_avx512_mb.c, mining/cpu/bal_avx512_probe.c,
mining/cpu/build.py, gpu/engine.py selection, mining/
mainnet_live.py status line). Every claim below was
re-derived from the committed tree, the pushed remote tree,
fresh builds, and fresh runs by the auditor. Nothing rests
on the integration report's word.

Overall verdict: PASS WITH NOTES. One latent dispatch
safety defect (D-1), one pre-existing accounting note in a
consumer (N-1), one cosmetic stale docstring (N-2). No
correctness defect found. The deployed miner is running
the audited code now.

## Area 1: the production commit itself. PASS

Method: recursive remote tree fetched through the repo's
own tooling (~/workspace/bin/bal_github.py helpers); local
blob SHAs compared against remote blob SHAs for the whole
tree (302 local entries, 302 remote entries).

- mining/cpu/bal_avx512_mb.c: remote blob SHA equals local.
- mining/cpu/bal_avx512_probe.c: match.
- mining/cpu/build.py: match.
- gpu/engine.py: match.
- mining/mainnet_live.py: match.
- tests/test_avx512_integration.py: match.
- The only differing path in the entire tree is
  evidence/mainnet-live.jsonl, the live evidence log the
  running miner appends to continuously. Expected runtime
  divergence, not an integration discrepancy.
- Kernel identity: the production kernel body (everything
  after the header comment) is byte-identical to
  research/sha256d/extreme_optimization/src/avx512_mb.c,
  verified by direct diff. The only differences in the
  file are the documented production header comment and
  the bal_search.h include path ("bal_search.h" in
  production vs the relative research path), exactly as
  claimed.
- Build flags: build.py's build_v512 compiles the kernel
  TU with V512_FLAGS = ["-mavx512f", "-mavx512bw"] and the
  probe TU with no vector flags; the strings "march=native"
  appear in build.py only in the pre-existing _compile path
  used for the C batch and intrinsics libraries, never in
  the v512 build. Claim confirmed.

## Area 2: dispatch. PASS WITH NOTES (defect D-1)

- (a) Feature set. The auditor compiled the production
  kernel TU fresh with the restricted flags and audited
  the object with objdump. Vector instruction census:
  vprold and vprord (AVX-512F), vpternlogd (AVX-512F),
  vpshufb on zmm (AVX-512BW), kmovd and kmovw (AVX-512F).
  A scan for AVX-512DQ, VBMI, VBMI2, IFMA and BITALG-only
  mnemonics (vpmullq, vpternlogq, vpopcntd/q, vpermi2,
  vpermt2, vpshufbitqmb, vpmadd52luq/huq, and peers)
  found zero. The claimed feature set, AVX-512F plus
  AVX-512BW, is exactly what the compiled object uses.
  The deployed .local/cpu/libbal_v512.so has the identical
  key census (5 vprold, 2 vpshufb, 7 vpternlogd, no
  DQ/VBMI/IFMA mnemonics) and exports exactly
  bal_v_batch2, bal_v_search2, bal_v512_supported and
  bal_v512_feature_bits.
- (b) Probe safety. The probe TU compiles to scalar code
  only: its object contains mov, and, test, shr, sete, or,
  not, cmove and ret, and no vector instruction of any
  width. Neither TU declares a library constructor, so
  loading the library cannot execute kernel code. Engine
  call order in gpu/engine.py _try_v512 (lines 838 to 902):
  file check, ctypes load, hasattr probe check, probe
  call, and only after a positive probe the batch and
  search argtypes and the self-test. No AVX-512 instruction
  can execute before the feature check passes.
- (c) Self-test. _try_v512 runs a 256-nonce batch over
  header bytes(range(80)) and compares every digest
  against cpu_digest, which is hashlib double SHA-256
  (gpu/engine.py line 202). A mismatch or a failed batch
  leaves the backend unselected with the reason recorded.
  The gate is real.
- (d) requested="c" never selects v512: _try_v512 is only
  invoked when requested is "auto" or "v512" (line 740).
  Verified live: ComputeEngine(requested="c") selects "c"
  on this AVX-512 machine.
- Selection on this VM: ComputeEngine() selects "v512"
  with v512_reason "selected: CPUID probe confirms
  AVX-512F and AVX-512BW and the batch reproduces hashlib
  digests", matching the claim.

Defect D-1 (dispatch safety, latent, minor to moderate):
_try_v512 guards the probe symbol with hasattr (line 856)
but then assigns argtypes to lib.bal_v_batch2 (line 876)
and lib.bal_v_search2 (line 882) with no guard and no
try/except. A libbal_v512.so that exports the probe but
not the kernel entry points makes ComputeEngine.__init__
raise AttributeError instead of falling back to the C
backend. Reproducer (auditor-built probe-only library):
ComputeEngine(v_lib_path=<probe-only .so>) raises
"AttributeError: undefined symbol: bal_v_batch2". This
falsifies the integration record's sentence "any failure
at any step falls back cleanly" for this one malformed
library case. Reachability is narrow: the repo's own
build links both objects in a single gcc invocation and
cannot produce a probe-only library, and build failure
leaves any previous complete library in place; triggering
D-1 needs a corrupted or hand-placed library file. If it
ever triggered in the live miner, mainnet_live.py would
crash at engine construction and the autopilot would
restart it into the same crash. The same unguarded
pattern exists in build.py _smoke_v512 (accesses
lib.bal_v_batch2 after the probe check), where the same
malformed library would escape build_v512 as an exception
instead of the designed loud failure dict. Suggested fix:
hasattr checks for both entry points in _try_v512 (the C
path at lines 772 to 790 already guards its optional
symbols this way), recording a v512_reason and returning.
The currently deployed library is complete (nm-verified
above), so D-1 does not affect the running deployment.

## Area 3: correctness through the production API. PASS

Auditor-written probes (not the integration test file),
all through ComputeEngine's public production paths:

- 131,072 randomized differentials: 16 batches of 8,192
  nonces on random 80-byte headers at random starts,
  batch_search at the maximum target, every returned
  digest compared against an independent hashlib
  computation in the auditor's script. Zero mismatches.
- Template variations: 6 random headers at targets
  2^228, 2^236 and 2^244; candidate sets equal to the
  auditor's hashlib recount exactly.
- Boundaries: batches starting at nonce 0 and at
  0xFFFFFFC0 reproduce hashlib for all 64 nonces each,
  including nonce 0xFFFFFFFF.
- Target equality meets (the genesis nonce's own digest
  value as target returns exactly that nonce); target
  minus one misses (empty candidate set).
- Candidate verification: the genesis candidate found by
  search_first_counted passes verify_candidate (the
  independent hashlib authority) and a zero digest fails
  it, as required.
- Fresh re-run of the integration's own suite
  (tests/test_avx512_integration.py) by the auditor: all
  gates passed, including its 196,608 differentials and
  its own regtest block at height 701 (see Area 5 for
  the auditor's separate block at 702).

## Area 4: accounting. PASS WITH NOTES (note N-1)

- Wave semantics verified against an independent
  prediction: the auditor re-implemented bal_partition
  plus the per-span ceiling-to-16 rule and predicted
  backend_hashes for counts 1, 15, 16, 17, 31, 32, 33,
  100, 1000 and 30000. Every prediction matched the
  engine's reported backend_hashes exactly (for example
  count 15 at 8 tuned threads gives 128 lane
  computations: 8 spans, one 16-lane wave each; count
  30000 gives 30080). unique_coverage equalled the
  requested count on every full enumeration;
  device_hashes was exactly 0 throughout.
- Early exit: genesis search from nonce GENESIS_NONCE-3
  reported attempted 16 and backend_hashes 16 (exactly
  one completed wave of real nonces, the wave containing
  the winner), candidate_count 1, verification_hashes 1,
  unique_coverage equal to attempted.
- Full miss: a 30,000-nonce search at target 1 reported
  attempted exactly 30,000 and backend_hashes 30,080.
- Bad candidate, batch path: the auditor wrapped
  _v_batch_flagged in-process to corrupt one presented
  digest. batch_search detected the verification failure
  (verification_failures 1), discarded the enumeration,
  rescanned with the trusted CPU path (backend reported
  "cpu-rescan", rescanned True) and returned a candidate
  set equal to the independent recount. Fail-closed
  confirmed.
- Bad candidate, search path: with verify_candidate
  forced to fail in-process, search_first_counted
  rescanned and still returned the true genesis nonce,
  recorded a fallback event, marked rescanned True and
  set unique_coverage to None with the explanatory note
  rather than inventing a number. Fail-closed confirmed.
- Consumers. mining/autopilot.py counts only accepted
  shares from the evidence JSONL (evidence_stats); it
  consumes no engine hash counters, so there is no
  double counting between autopilot and engine stats.
  mining/mainnet_live.py uses the thin search_first
  wrapper and adds the full requested span to its own
  status counter per call (total_hashes += span).

Note N-1 (accounting, low severity, pre-existing): the
mainnet_live.py status counter therefore reports
requested nonces, not the engine's exact attempted
counts, on any span where the search exits early, and
the remainder of a hit span is counted again as the
scan resumes after the found nonce. A diff against the
pre-integration backup (.local/pre-avx512-integration/)
shows the integration changed mainnet_live.py only by
adding the backend line and logging it; the span
counting is unchanged pre-existing behaviour, identical
in kind on the C backend. The engine's exact counted
stats (last_search_stats) exist and are truthful; the
live status file's "hashes" figure is a requested-work
figure. Not introduced by this integration; recorded so
the figure is never read as an exact attempt count.

Note N-2 (cosmetic): the mainnet_live.py module docstring
still describes the runner as "(C midstate batch,
early-exit search)". The backend is now selected at
runtime and is printed in the status file itself, but the
docstring line is stale.

## Area 5: fallback behaviour and fresh regtest block. PASS

All fallback tests ran in a scratch copy under /tmp (the
production tree was never edited in place):

- (a) Probe forced to fail (auditor-built library: real
  kernel object linked with a probe variant returning 0):
  ComputeEngine selects "c", records the CPUID reason,
  and finds the genesis nonce through the C backend.
- (a2) Library present but lacking the probe symbol (the
  C batch library passed as the v512 path): the engine
  refuses to call the kernel ("no CPUID probe"), selects
  "c", mines correctly.
- (c) No library at all (nonexistent path): engine
  imports and runs, selects "c" with reason "AVX-512
  library not built", mines correctly.
- (b) Broken MB translation unit in the scratch tree
  (deliberate syntax error appended): build_v512 returns
  ok=False with the compiler output preserved and
  produces no libbal_v512.so; the production C build in
  the same tree still returns ok=True; a ComputeEngine
  constructed in that tree then selects "c" and mines
  correctly. Degradation is loud and the C path is
  intact.
- Fresh regtest block by the auditor, through the
  production MiningEngine with backend "v512" selected:
  height 702, hash
  7aa935cd59b84fb816ff814c2c844f49db26d80ca97d374e9ba11b359d320886,
  submitblock accepted, Core best-block hash matches,
  getblock confirms height 702. This is a new block
  beyond the integration's heights 630 and 700 and
  beyond height 701 from the auditor's fresh run of the
  integration suite.

## Live deployment verification (from the outside)

Two reads, at 2026-11-14T15:43:49Z and 15:47:18Z:

- Autopilot status and .local/heartbeat.json: autopilot
  pid 6003, miner pid 89317 (the pid in the integration
  record), miner_state running, restarts 1,
  shares_accepted_total 60, heartbeat timestamps fresh
  at both reads (evidence_age_s 32.7 then 1.2).
- .local/mainnet-status.txt shows "compute backend:
  v512 (native impl: avx512-mb; ...)" and the hash
  counter advanced from 2,550,136,832 (session t=211s)
  to 5,351,931,904 (session t=452s) between the reads,
  at a session rate of about 11.8M to 12.1M H/s.
- The mainnet node was not restarted: getblockchaininfo
  at 15:47Z shows blocks 411,674 of 975,813 headers,
  initial block download still true, up from 411,570 at
  the integration's own verification. Sync undisturbed.
- Nothing was restarted by the auditor.

## Defect and note register

- D-1: dispatch safety, latent, minor to moderate.
  Unguarded kernel entry point access in _try_v512
  (gpu/engine.py lines 876 and 882) and the same pattern
  in build.py _smoke_v512: a probe-only or kernel-less
  libbal_v512.so raises AttributeError out of
  ComputeEngine construction instead of falling back to
  C. Reproducer and suggested fix in Area 2. Not
  reachable from the repo's own build output; the
  deployed library is complete.
- N-1: accounting, low, pre-existing. mainnet_live.py
  status counter counts requested spans, not exact
  attempts. Unchanged by the integration.
- N-2: cosmetic. Stale backend wording in the
  mainnet_live.py docstring.

No other discrepancies found. In particular, the
integration record's factual claims about file identity,
flags, feature set, self-test, fallback for missing and
unsupported libraries, gate counts, regtest heights 630
and 700, deployment pid and node state all reproduced
under independent re-derivation.

## Resolution of D-1 and N-2 (2026-11-14, fix pass)

D-1 RESOLVED. gpu/engine.py _try_v512 now checks, after a
positive CPUID probe and before any argtypes assignment,
that both kernel entry points exist (hasattr on
bal_v_batch2 and bal_v_search2, mirroring the C path's
guards on its optional symbols). A library missing either
is rejected as a whole: v512_reason names the missing
entry point(s), _try_v512 returns, and selection falls
back to the C backend. mining/cpu/build.py _smoke_v512
gained the matching guard for bal_v_batch2 (its
bal_v_search2 access was already guarded): it now
returns its designed error tuple ("library lacks the
bal_v_batch2 entry point", 1) instead of letting an
AttributeError escape build_v512.

Regression evidence, before and after: with the audit's
probe-only library (the real probe translation unit
linked alone), ComputeEngine construction raised
"AttributeError: undefined symbol: bal_v_batch2" at the
argtypes assignment before the fix, and _smoke_v512
raised the same AttributeError. After the fix, the same
library is rejected with v512_reason "AVX-512 library is
incomplete: missing kernel entry point(s) bal_v_batch2,
bal_v_search2; rejecting the library as a whole and
falling back", the engine selects "c" and mines the
genesis nonce exactly (2083236893). A second malformed
variant (probe plus a bal_v_batch2 stub, no
bal_v_search2) is likewise rejected naming bal_v_search2
alone and falls back to C and genesis. A permanent
regression gate, test_incomplete_library_fallback in
tests/test_avx512_integration.py (part of make
test-avx512 and test-all), builds stub-probe fake
libraries so the guard is exercised on every machine,
and asserts clean fallback, named missing symbols,
genesis mining on the C backend, and the smoke test's
error return. Full test-all after the fix: 20 of 21
targets pass; the only failure is test-rtl (iverilog
absent from this VM, pre-existing environment,
unchanged). Normal dispatch on this VM is unaffected:
ComputeEngine() still selects "v512" with the complete
library and its self-test passes, and the integration
suite mined a fresh regtest block at height 703 during
the fix verification run.

Deployment note: the live miner and autopilot were NOT
restarted for this fix. The deployed library is complete
(nm-verified in Area 2), so D-1 is unreachable in the
current deployment; the fix takes effect on the next
natural miner restart.

N-2 RESOLVED. The mining/mainnet_live.py module
docstring no longer describes the runner as "(C midstate
batch, early-exit search)"; it now describes the runtime
dispatched backend (AVX-512 multi-buffer where the CPUID
probe confirms it, otherwise the C midstate batch;
early-exit search).

N-1 NOT CHANGED. The mainnet_live.py status counter span
accounting is pre-existing behaviour awaiting the
owner's word; this pass left the code exactly as the
audit recorded it.

## Resolution addendum: N-1 fixed (2026-11-14)

N-1 RESOLVED, on the owner's order to complete
everything. mining/mainnet_live.py no longer adds the
requested span to its status counter. A new helper,
call_attempts(engine, hit, start), returns the exact
attempts of each search_first call from the engine's
counted stats (last_search_stats["attempted"], the
field Area 4 verified as exact), and the scan loop
accumulates that value. If a call path ever leaves
no stats, the helper counts only what the result
itself proves: a hit proves every nonce from the span
start through the winner was examined, and a miss
without stats proves no countable partial work, so
0. The requested span size is never counted. Every
other status field is unchanged; the displayed
session rate now derives from exact attempts instead
of requested nonces. Historical session rates in
earlier evidence files were computed on the inflated
counter; they are left exactly as recorded and must
not be read as exact attempt rates.

Regression gate: tests/test_mainnet_live_accounting.py
(make test-mainnet-live, part of test-all) drives the
production engine on the auto and C backends. An
early-exit search (genesis header, winner 3 nonces
into a 100,000 nonce span) advances the counter by
exactly the attempted count (16 under the v512 wave
accounting, 4 under C), not the span. A full-miss
span advances it by exactly the span size, which
equals the attempted count. The no-stats fallback is
asserted directly against both a hit and a miss.
Full test-all after the fix: 21 of 22 targets pass;
the only failure is test-rtl (iverilog absent from
this VM, pre-existing environment, unchanged).
Environment note: the first test-all run after the
2026-11-14 VM reboot halted at test-regtest because
the regtest node's bal-regtest wallet existed on
disk but was not loaded; loading it restored the
pre-reboot state and the suite then ran clean. No
code was changed for that.

Deployment note: the live miner and autopilot were
NOT restarted for this fix. The running miner (pid
3741, restored by the keeper at 16:10 UTC after the
reboot) still executes the pre-fix runner, so its
status line still shows requested nonces; the fix
takes effect on the next natural miner restart
through the autopilot and keeper cycle.

With this addendum, every note in this audit is
resolved: D-1 (dispatch guard), N-1 (status counter
accounting), N-2 (docstring).
