# NOVA Repository Audit (Master Assignment Phase A: Establish the Truth)

Date: 2026-11-15. Auditor role: Phase A truth baseline for the
NOVA SHA-X Master Assignment (owner directive 2026-11-15). This
audit feeds deliverable 15 (NOVA_BITCOIN_CORE_GAP_ANALYSIS.md);
it is not itself that deliverable.

Method: every claim below was verified against the current
source tree at ~/workspace/bitcoin-autonomous-lab, its tests and
its raw artifacts, on the audit host. Previous research reports
were treated as claims to be checked, never as evidence. Where a
report and the source disagree, the source wins and the
disagreement is recorded in section 13.

Audit host (recorded because several results are host-shaped):
AMD EPYC 9D25 (guest, 4 vCPUs visible), Linux 7.0.0-44-generic,
gcc 13.3.0, Python 3.12. CPU flags observed in /proc/cpuinfo:
avx2, avx512f, avx512bw, avx512vl, avx512dq, avx512cd, avx512vbmi,
avx512vbmi2, avx512ifma, avx512vnni, sha_ni, vaes, gfni. No GPU
device exists (no /dev/nvidia* nodes). iverilog is NOT installed
on this host. The deployed Bitcoin Core binary is v28.1.0
(~/workspace/bitcoin-core-dist/bitcoin-core-28.1); no Bitcoin
Core source tree exists anywhere in this repository or home
tree, only the binary distribution and its tarball.

Verdict legend, applied per area:
- VERIFIED AS DOCUMENTED: source matches the written record.
- DIFFERS FROM DOCUMENTATION: source and record disagree in a
  material way; the disagreement is stated exactly.
- MISSING: the Master Assignment requires it; it is not present.
- UNVERIFIABLE: cannot be established from this host or tree.

## 1. CPU backends and SHA-256d implementations

Inventory, all present in source and all built into
.local/cpu/ at audit time (libbal_batch.so, libbal_intrin.so,
libbal_v512.so, libbal_v512dual.so, libbal_v512flags.so all
exist):

| Backend | Source | Entry points | Role in production |
| --- | --- | --- | --- |
| C midstate batch (OpenSSL) | mining/cpu/bal_batch.c | bal_c_batch, bal_c_batch2, bal_c_search, bal_c_search2 (lines 140 to 258) | Fallback search and batch backend "c" |
| SHA-NI intrinsics | mining/cpu/bal_sha_intrin.c | bal_i_batch, bal_i_batch2, bal_i_search, bal_i_search2 (lines 238 to 357) | Research and legacy only. NOT dispatched by ComputeEngine; gpu/engine.py module docstring states this and the dispatch code confirms it. EXP-032 measured it ESTABLISHED NEGATIVE as a batch backend (0.517x of C) |
| AVX-512 multi-buffer (v512) | mining/cpu/bal_avx512_mb.c | bal_v_batch2 (line 358), bal_v_search2 (line 370) | Preserved fallback backend "v512" |
| AVX-512 DualMask (v512dual) | mining/cpu/bal_avx512_dual.c | bal_vd_batch2 (line 617), bal_vd_search2_exp018 (line 629), bal_vd_search2 (line 855) | The selected production backend on AVX-512F+BW hosts |
| AVX-512 flags batch | mining/cpu/bal_avx512_flags.c | bal_v_batchf2 only (line 472) | Batch-scope only; see section 3 (Q1) |
| Python hashlib | gpu/engine.py cpu_digest (line 321) | cpu_digest, verify_candidate (line 326) | Backend "cpu", verification authority, trusted rescan |
| Pure Python SHA-256 | mining/pow_engine.py PureSHA256 | sha256_pure, double_sha256_pure | Independent second implementation used by candidate verification |
| CUDA | gpu/cuda/engine.cu, gpu/cuda/kernels/ | CudaContext in gpu/engine.py (line 662) | Code present and gated by a production self-test; never selected here (no device). Verdict on GPU performance: UNVERIFIABLE on this host, and no GPU rate is claimed anywhere in this audit |
| Standalone C miner | mining/cpu/bal_miner.c (Makefile target bal-miner) | search and bench CLI | Standalone tool; passes the Makefile genesis search test. Not the live path |
| FPGA / ASIC | fpga/sha256_core.v, fpga/sha256d_miner.v, asic/flow.sh | testbench tb_miner.v | Simulation and synthesis artifacts only; no board, no bitstream measurement. test-rtl cannot run on this host (iverilog absent) |

Two more header-level facts verified from source:
- mining/pow.py carries a second, simpler PoW implementation
  (target_from_nbits line 25, block_work_ok line 39) with no
  negative, overflow or above-limit rejection. It is used for
  merkle roots, subsidy and dsha256 plumbing and for the solo
  server's informational job target (mining/solo_server.py
  refresh_job). The strict verifier is
  mining/pow_engine.py check_pow (SetCompact semantics with
  negative, overflow, zero and above-limit reason codes), and
  since EXP-036 every submission decision routes through it via
  mining/candidate_verify.py. The simple decoder never decides
  a submission. VERIFIED AS DOCUMENTED, with the two-decoder
  split worth recording because a reader of pow.py alone would
  miss it.
- mining/cpu/build.py compiles the AVX-512 translation units
  with the restricted flag set V512_FLAGS = [-mavx512f,
  -mavx512bw] (build.py line 85; applied at lines 304, 476, 655),
  never -march=native, and links the flag-free probe
  mining/cpu/bal_avx512_probe.c into each AVX-512 library. The
  C batch library is built with -march=native (build.py line
  140), as is the standalone bal-miner (Makefile CFLAGS). The
  restricted-flag discipline therefore applies exactly to the
  AVX-512 kernels, as documented, and not to the C fallback,
  which is host-built by design.

Verdict for section 1: VERIFIED AS DOCUMENTED.

## 2. The AVX-512 production path, end to end

Dispatch lives in gpu/engine.py ComputeEngine.__init__
(line 840). Order, verified line by line (lines 862 to 897):

1. CUDA, only if requested in (auto, cuda, cuda-only):
   _try_cuda must load the library, find a device, and pass
   cuda_production_selftest with CPU re-verification. Any
   failure records fallback_reason and selection continues.
2. v512dual, if the backend is not already cuda and the request
   allows it: _try_v512dual (line 1099).
3. v512, if not cuda or v512dual: _try_v512 (line 977).
4. C, if none of the above: _try_c (line 899).
5. Python hashlib remains as backend "cpu" if no native library
   selects.
6. Independently of the search selection, if the request is
   auto, v512 or v512dual, _try_v512flags (line 1269) attempts
   the flags batch selection. It never changes the search
   backend.

Selection discipline for v512 and v512dual, verified in
_try_v512 and _try_v512dual: the library file must exist; it is
loaded with ctypes (loading executes no kernel code); the
flag-free probe bal_v512_supported must exist (checked with
hasattr BEFORE any argtypes assignment, the audit D-1 rule) and
must return true, confirming exactly AVX-512F and AVX-512BW via
__builtin_cpu_supports; the counted entry points
(bal_v_batch2 and bal_v_search2, or bal_vd_batch2 and
bal_vd_search2) must all be present, checked as a completeness
list before any is called; then a self-test batch must
reproduce hashlib digests exactly. Any failure at any step
leaves the backend unselected with the reason recorded on
v512_reason or v512dual_reason and selection falls through.
The flags selection follows the same shape: probe first,
hasattr on bal_v_batchf2 before argtypes, then a hashlib
self-test in both extract mode and pure flags mode (digests
NULL) with exact accounting.

Thread tuning: after selection, tune_c_threads,
tune_v512_threads or tune_v512dual_threads probes thread counts
with the real counted search over 2^20 nonces and keeps the
measured peak (BAL_C_THREADS env overrides). LAST_PROBE_RATE
feeds the live miner's span sizing.

Live confirmation on this host: the suite's deepening test
observed the dashboard reporting backend v512dual, and every
AVX-512 integration test passed in the suite run (section 11),
so on this AMD host the chain cuda (absent) to v512dual
(selected) is exercised end to end.

Verdict for section 2: VERIFIED AS DOCUMENTED.

## 3. SPECIFIC QUESTION 1: is the EXP-022 flags early exit in the LIVE search path?

Definitive answer: NO. The flags form is integrated into the
batch enumeration surface only. It is not in, and cannot be
reached from, the live search path. This matches what the
integration record claims (PRODUCTION_INTEGRATION_LOG.md Entry
3 is titled "EXP-022 flags batch adopted for the engine batch
consumers"), and it contradicts any reading of the adoption as
a search-path change. The gpu/engine.py module docstring
(lines 75 to 99) states the same boundary: "This is a
BATCH-scope change only: the search entry points, the search
dispatch order and every search accounting figure are
untouched, and no search rate changes."

The exact live call path, traced from source:

1. mining/mainnet_live.py line 185: the live miner calls
   engine.search_first(header, target, nonce, span) on a
   ComputeEngine constructed with defaults (line 143).
2. gpu/engine.py line 1451: search_first is a thin wrapper over
   search_first_counted (line 1459).
3. search_first_counted dispatches on the selected backend:
   - backend v512dual: calls self._vd_lib.bal_vd_search2
     directly (native counted search, dual-atomic accounting).
   - backend v512: calls self._v_lib.bal_v_search2 directly.
   - backend c: calls bal_c_search2, or legacy bal_c_search.
   - otherwise (backend cpu, or cuda without a context): falls
     back to batch_search and takes its first candidate.
   No branch of search_first_counted references the flags
   library, _vf_batch_flagged, or bal_v_batchf2.
4. The flags entry bal_v_batchf2 is called from exactly one
   production function, _vf_batch_flagged (gpu/engine.py line
   1385, call at line 1401), which is called from exactly one
   place, batch_search (line 1894; routing block at lines 1937
   to 1950), and only when the selected backend is v512 or
   v512dual AND the flags library was selected. A repository
   wide caller search confirms no other production caller of
   _vf_batch_flagged or bal_v_batchf2 exists (only tests, the
   build smoke test in mining/cpu/build.py, and research
   benchmarks).
5. The flags library itself exports no search entry point:
   mining/cpu/bal_avx512_flags.c exports only bal_v_batchf2
   plus the probe symbols, a fact the independent flags audit
   verified from the built .so (phase6b/
   FLAGS_POST_INTEGRATION_AUDIT.md section 1: "No search entry
   point exists in the library").

Who actually consumes batch_search in production today:
- gpu/benchmark.py run_benchmark and ComputeEngine.benchmark /
  benchmark_report (gpu/engine.py lines 2196 and 2297), which
  is what the dashboard (dashboard/server.py line 105) and the
  autonomous agent (agent/autonomous.py line 87) call for their
  benchmark figure.
- MiningEngine does NOT mine through batch_search:
  mine_cycle calls search_first_counted (mining/engine.py
  lines 720 to 724). The agent's mining therefore runs on the
  native search entries, not the flags batch.
- The search_first_counted fallback for backend cpu also
  reaches batch_search, but the flags routing block requires
  backend v512 or v512dual, so on the cpu backend the flags
  path is not taken either.

One correction to the integration record, minor but exact:
Entry 3's consumer trace says batch_search's "callers include
gpu/benchmark.py (benchmark_report), the dashboard and agent
engines built on ComputeEngine, and the test suites". From
current source, the dashboard and the agent reach batch_search
only indirectly, through ComputeEngine.benchmark(), for a
benchmark number; neither mines through it. The statement is
not false, but it reads broader than the current call graph.
The flags adoption's real production surface is: the benchmark
pipeline, the test suites, and any direct batch_search caller.
The live miner's rate is entirely unaffected by the flags
library, positively or negatively.

Independent corroboration: EXP-032 (research/sha256d/exp032/
EXP032_REPORT.md and the registry record) measured the flags
question on the real search path three ways and closed it
ESTABLISHED NEGATIVE (flags batch used as search is 2.565x
slower than the native dual search; a dedicated flags search
entry is not significant against the v512 search, pooled
0.967x, CI [0.885, 1.059]). No flags search integration was
made, and this audit confirms from source that none exists.

Verdict for Q1: the research record is VERIFIED AS DOCUMENTED
(batch scope only); any claim that flags speed up the live
search would DIFFER FROM the source, and no such claim exists
in the production code or the integration log.

## 4. SPECIFIC QUESTION 2: the EXP-023/EXP-025 template cache fingerprint in production

The production implementation is the EXP-025 repaired design
in mining/engine.py (cache section header at lines 151 to 210,
code at lines 217 to 460). It is a layered identity: three
layer keys plus the family key, combined as
identity = dsha256(tx_key || coinbase_key || header_key).
Every field below is taken from the key-construction source.

family_key (TemplateFamily.__init__, lines 228 to 240):
dsha256 over the domain string "bal/template-cache/family/v1"
plus, in order:
- payout address (length-prefixed UTF-8)
- payout scriptPubKey bytes (length-prefixed; from
  validateaddress via address_script_pubkey)
- chain name string (length-prefixed; from
  getblockchaininfo)
- halving interval as u64 (150 for regtest, 210000 otherwise)

tx_key (_tx_layer_key, lines 279 to 289): dsha256 over the
domain "bal/template-cache/tx/v1" plus:
- transaction count (varint)
- for every transaction, IN TEMPLATE ORDER: txid (32 bytes,
  internal byte order), wtxid (32 bytes), fee (signed 64-bit,
  from the template's per-transaction "fee" field, defaulting
  to 0 exactly as the uncached path does)
- default_witness_commitment string (length-prefixed; the
  empty byte string when absent). Keyed as a validation input
  even though it is not itself cached data.

coinbase_key (_coinbase_layer_key, lines 290 to 300): dsha256
over the domain "bal/template-cache/coinbase/v1" plus:
- family_key (32 bytes)
- height (u64)
- coinbasevalue (signed 64-bit)
- coinbaseaux flags bytes (length-prefixed; from
  coinbaseaux.flags hex, empty when absent)
- witness commitment (32 bytes; the computed commitment, or
  32 zero bytes when there is none)
- commitment presence byte (0x01 when a commitment exists,
  0x00 when not)

header_key (_header_layer_key, lines 302 to 309): dsha256 over
the domain "bal/template-cache/header/v1" plus:
- version (signed 32-bit, from the template)
- previousblockhash (the 32 bytes of the hex string as
  written, NOT byte-reversed)
- bits (the raw bytes of the bits hex string)
- target (the template's "target" field encoded as TEXT,
  exactly as Core served it; a purely textual change to that
  string would change the key without changing the numeric
  target, which is over-keying in the safe direction)

identity (template_identity, lines 311 to 335):
dsha256(tx_key || coinbase_key || header_key), computed only
after the full validation pass (_derive_tx_pass, lines 242 to
277: every transaction's txid recomputed from its raw data and
compared with Core's, wtxids computed, fees summed, witness
commitment recomputed and cross-checked against
default_witness_commitment) and the coinbasevalue equals
subsidy plus fees check, identical to the uncached path.

What the fingerprint does NOT cover, verified from source:
- mintime and curtime. Deliberately excluded (code comment at
  lines 204 to 210). No cached object depends on them:
  PreparedTemplate.build (lines 386 to 430) assembles the
  header time per build from the template in use
  (max(mintime + 1, min(now, curtime))). A template that
  differs only in time fields has the same identity and
  correctly reuses the prepared work, because the time is
  read live, never cached.
- The five live-read fields generally: build() reads version,
  previousblockhash, bits, mintime and curtime from the
  template object passed (or held) at build time, while
  height, value, flags, commitment, target, the merkle levels
  and the transaction body come from the prepared snapshot.
  version, previousblockhash and bits ARE in header_key, so a
  sibling template differing in them is refused; but in the
  mine_cycle steps path the loop holds the template object
  itself, so a mutation of that held object between steps
  would be read live without any identity recheck. This is
  the held-object mutation boundary the EXP-034 audit pinned;
  this audit re-confirms it from source. No production code
  mutates a held template, so the boundary is a documented
  design limit, not an observed defect.
- Every other getblocktemplate field is neither keyed nor
  read by the construction, so it cannot change any output
  byte: longpollid, expires, sizelimit, weightlimit,
  sigoplimit, capabilities, vbavailable and other
  versionbits fields, coinbaseaux fields other than flags,
  and the per-transaction depends, sigops and weight fields
  (transaction order itself IS keyed, through the ordered
  txid list). Raw transaction bytes enter the identity only
  through txid and wtxid, which are double SHA-256 of the
  stripped and full serialisations; completeness therefore
  rests on SHA-256 collision resistance, the same assumption
  Bitcoin places on txids, exactly as the code comment states.

Cache bounds and fallback, verified:
- TemplateCache (lines 432 to 460): keyed by (family_key,
  identity); max_entries 128 with FIFO eviction of the oldest
  entry; counters prepares, hits, identity_checks.
- Serving rule: any serve that takes a template recomputes
  its identity from scratch with full validations and raises
  TemplateError on mismatch (TemplateCache.get, and again in
  PreparedTemplate.build for a sibling template). It never
  silently serves.
- The steps exception: mine_cycle prepares once (identity
  verified at prepare time) and steps extranonces off the
  prepared entry with template=None, because the loop holds
  the object. This is the shape EXP-025 verified.
- Fallback: MiningEngine(use_template_cache=False), the
  default-off constructor flag, routes build_candidate to
  build_candidate_uncached (lines 558 to 623), the original
  construction preserved unchanged and used as the
  differential reference in tests/test_template_cache.py.
- mine_cycle uses the steps fast path only when
  build_candidate has not been overridden by a caller or
  subclass (checked at lines 690 to 697); otherwise the
  override is called per round, as before the integration.

Verdict for Q2: VERIFIED AS DOCUMENTED. The fingerprint is
complete over the construction's actual dependency set; the
only uncovered inputs are the time fields (by design, read
live) and fields the construction never reads.

## 5. SPECIFIC QUESTION 3: EXP-024 and Phase 6B state vs production code

What the research tree records (research/sha256d/phase6b/
EXP024_MASK_SEARCH.md, EXPERIMENT_RESULTS.md,
PHASE6B_FINAL_REPORT.md, and both registries):

- EXP-024 design B (the predeclared primary mask-search
  design): FAILED its criterion (pooled 1.169x, 1 of 3
  sessions significant).
- EXP-024 design E (span scan): ESTABLISHED NEGATIVE for
  search (about 6.16x slower).
- EXP-024b design C (single-batch mask search): VERIFIED
  IMPROVEMENT in search scope (pooled 1.398x, every session
  significant), explicitly recorded as NOT INTEGRATED, with
  DualMask as the integrated form and design C as "the
  certified single-batch fallback" (experiment_registry.md,
  EXP-024b entry: "Not integrated; EXP-026 DualMask remains
  the leading integration candidate, C is the certified
  single-batch fallback").
- EXP-026 C1 TernMask: ESTABLISHED NEGATIVE. C2 DualMask:
  VERIFIED IMPROVEMENT (pooled 1.718x vs production search,
  1.444x vs its strongest ingredient) and INTEGRATED as
  backend v512dual (integration addendum in
  experiment_registry.md; PRODUCTION_INTEGRATION_LOG.md
  Entry 1; DUALMASK_POST_INTEGRATION_AUDIT.md PASS WITH
  NOTES, zero defects).

What production actually contains, verified from source:
- v512dual IS present and selected exactly as recorded:
  mining/cpu/bal_avx512_dual.c exports bal_vd_batch2,
  bal_vd_search2_exp018 and bal_vd_search2; ComputeEngine
  dispatch tries it immediately after CUDA (section 2).
- Design C is NOT in production. The production dual library
  exports no single-batch mask-search entry; the mask-search
  forms (bal_v_msearch* entries) exist only in research code
  (research/sha256d/extreme_optimization/src/
  avx512_mb_mask_search.c). The production fallback chain is
  v512dual, then v512, then C, then hashlib. There is no
  production code path that could serve design C.
- Therefore the phrase "certified single-batch fallback"
  describes a research certification status (design C is the
  form to integrate if a single-batch fallback is ever
  needed), not a production fallback that exists today. The
  registry itself says "Not integrated", so the record is
  accurate; the audit flags the phrase only because a casual
  reader could mistake it for deployed code.

Verdict for Q3: VERIFIED AS DOCUMENTED, with the one wording
risk above recorded. Production matches the research record
on every material point: DualMask integrated, design C
verified and not integrated, designs B and E negative and
absent.

## 6. Mining engine, templates, coinbase, merkle, search space

Template acquisition (mining/engine.py): MiningEngine.
get_template (line 529) calls getblocktemplate with rules
["segwit"]; wait_template (line 532) implements the GBT
longpoll with a timeout-extended RPC client. VERIFIED.
One usage fact the Phase B gap analysis recorded and this
audit re-confirms: wait_template has no production caller.
agent/autonomous.py drives mine_cycle, which calls
get_template fresh each cycle; the Stratum paths key
freshness on prevhash and job generation instead.

Coinbase and merkle (mining/engine.py build_coinbase line
117, build_candidate_uncached lines 558 to 623,
PreparedTemplate lines 337 to 430): BIP34 height push, the
"/BAL/" marker, the extranonce as a 4-byte little-endian
integer appended after the marker, coinbaseaux flags
appended when present, payout output plus the BIP141 witness
commitment output (aa21a9ed header over dsha256(witness root
|| reserved value)) when any transaction has a witness.
Template transactions are re-parsed; txid (dsha256 of the
stripped serialisation) and wtxid (dsha256 of the full
serialisation) are recomputed and a txid mismatch rejects
the template. coinbasevalue must equal subsidy plus fees or
the template is rejected. Merkle root: the uncached path
computes merkle_root([coinbase txid] + txids) via
mining/pow.py; the cached path precomputes the tree levels
over [zero || txids] and folds the coinbase txid in per
extranonce step (root_with_coinbase, line 373). VERIFIED AS
DOCUMENTED; byte-identity between the paths is gated by
tests/test_template_cache.py and the EXP-034 audit's
independent recomputation.

Nonce search (mine_cycle, lines 640 to 789): per extranonce
round, batches of batch_count(batch_size, start) (the final
batch clamped to the 32-bit space, line 625) are searched
through search_first_counted; total_hashes accumulates the
backend's reported attempted count, never the requested
size. A hit is assembled into a full block, submitted with
submitblock, and counted accepted only when submitblock
returns None AND the node's best block hash equals the
block hash. VERIFIED.

Search-space management: extranonce_space (MiningEngine
constructor, lines 463 to 510) is an opt-in (first, count)
window over the 32-bit coinbase extranonce rounds mine_cycle
steps, validated to lie inside the 32-bit range, default
(0, 64) exactly the historical behaviour. Two engines with
the same payout and template and the default space build
byte-identical candidates; disjoint spaces are the caller's
(coordinator's) responsibility, and no production coordinator
assigns them yet (EXP-035 is prototype only; section 15,
item 4).
Timestamp rolling and BIP320 version rolling do not exist on
any path: the header version is taken from the template as
served, and the header time is the template-bounded curtime
computation described in section 4. Recorded as a genuine
gap in section 14.

## 7. Candidate verification and block submission

mining/candidate_verify.py (203 lines) is the single
verification stage, VERIFIED AS DOCUMENTED:
- verify_candidate recomputes SHA-256d twice, with hashlib
  (mining/pow.py dsha256) and with the independent pure
  Python implementation (mining/pow_engine.py
  double_sha256_pure), and requires byte agreement.
- The target is decoded from the header's own nBits with
  Core SetCompact semantics (pow_engine.compact_decode and
  check_pow): negative, overflow, zero and above-limit
  targets are rejected with reason codes; the comparison is
  exact integer value <= target. A repository grep of the
  module confirms no float operation decides anything in it;
  float difficulty appears only in display and statistics
  contexts elsewhere (for example mainnet_live.difficulty_of,
  used for logging and best-difficulty tracking, never for a
  submission decision).
- Classification is one of block_candidate, share,
  below_target, invalid; meets_network_target (check_pow ok
  and digests agree) alone decides block candidacy;
  meets_share_target applies the caller-supplied share
  target under the same validity conditions.
- classify_submit_result records the verbatim submitblock
  return alongside its class; verify_chain_acceptance
  decides acceptance from chain state (tip, or in-chain with
  at least one confirmation), returning "unknown" and not
  accepted when chain state cannot be read.

Submission paths:
- GBT path (MiningEngine.mine_cycle): submitblock plus the
  best-block equality check, as above. It predates
  candidate_verify and applies the same acceptance standard
  inline rather than calling verify_chain_acceptance; the
  standard is equivalent (tip equality), the code is not
  shared. Recorded as a consistency note, not a defect.
- Pool path (mining/mainnet_live.py): every search hit is
  reconstructed into a full header and passed through
  verify_candidate (line 206) with POW_LIMIT_MAINNET and the
  pool share target; submission via client.submit (line 229)
  happens only when the backend digest matches both
  recomputations, the header target is legal, the exact
  share comparison passes, and the job generation is still
  the freshest. Block candidacy in the evidence log comes
  from meets_network_target alone.
- Solo path (mining/solo_server.py submit_share, line 351):
  validate_share (line 302) rebuilds the exact block from
  coinb1, extranonce1, extranonce2, coinb2 and the merkle
  branch, checks the share against the server difficulty,
  then routes the header through verify_candidate (line
  374); failures are recorded in candidates_rejected and
  never submitted. A network-target candidate is assembled
  into the full block (witness re-attached), submitted with
  submitblock, and recorded accepted only when
  verify_chain_acceptance confirms tip or in-chain; the
  verbatim submitblock result, its classification and the
  chain status are all stored on the block record. The
  EXP-036 defect (submitblock None treated as success) is
  closed in source, not merely in the report.
- Solo job construction (refresh_job, line 228): the
  coinbase is built with the engine's own builder with an
  8-byte extranonce placeholder, the STRIPPED coinbase is
  served, and the split offset is located in the stripped
  bytes (lines 262 to 270, with the EXP-034 finding recorded
  in the comment). The served scriptSig therefore carries
  "/BAL/" plus the 8-byte extranonce slot. One documentation
  nuance: the solo server's coinbase carries the engine
  builder's "/BAL/" marker; no "/BAL-solo/" tag exists in
  the served bytes, exactly as the EXP-034 audit recorded.
  refresh_job takes the job target from the simple decoder
  (pow.py target_from_nbits) for bookkeeping; the
  authoritative judgement of any share still goes through
  check_pow inside verify_candidate.
- Solo freshness (JobRefresher, line 451): polls the node
  every 2 s, rebuilds the job when the served prevhash no
  longer matches the node's best block hash or the job ages
  past 120 s, and refuses to serve while the node is in
  initial block download, on the wrong chain, or
  unreachable (check_node gate inside refresh_job).

Stratum client (mining/stratum_client.py): build_header
(line 118) assembles the 80-byte header with the wordswap
prevhash mode the live runner uses; incoming jobs pass
validate_job plus duplicate and stale-echo guards
(template_validated, template_rejected, template_duplicate
evidence events, lines 255 to 310) before they can
supersede current work, and every accepted job bumps
job_generation, which is what mainnet_live checks before
submitting.

Verdict for sections 6 and 7: VERIFIED AS DOCUMENTED.

## 8. Bitcoin Core integration points

- node/rpc_client.py: typed JSON-RPC wrapper with retries
  and explicit errors; credentials from .local configs,
  never from source.
- node/node_manager.py: regtest node lifecycle (setup,
  start, stop, status). NOTE: it contains no wallet handling
  at all, which matters for the suite finding in section 11.
- node/peer_node.py: second peered regtest node used by the
  deepening tests.
- MiningEngine and SoloServer consume getblocktemplate,
  submitblock, getbestblockhash, getblockheader,
  validateaddress and getblockchaininfo through that client.
- scripts/setup-bitcoin-core.sh installs the Core 28.1
  distribution with SHA256SUMS verification; the mainnet
  node runs from ~/workspace/bitcoin-core-dist with its
  datadir under .local/mainnet (pruned, prune=550).
- No Core source checkout exists locally (see header), so
  every Core-behaviour claim in the repo rests on the 28.1
  binary's observed behaviour and the lab's differential
  tests, not on Core source reading. That is the correct
  starting fact for Master Assignment Phase B.

Verdict: VERIFIED, with the no-source-tree fact recorded as
a Phase B input, not a defect of the current tree.

## 9. Benchmark inventory and category map

Categories per the Master Assignment: A ordinary SHA-256;
B ordinary double SHA-256 of arbitrary data; C exact 80-byte
header SHA-256d; D mining kernel with reusable header state
and target comparison; E complete production search
(candidate construction, work management, result handling);
F end-to-end pipeline (template acquisition, construction,
submission).

Every benchmark harness in the tree, and what it measures:

| Harness | Measures | Category |
| --- | --- | --- |
| gpu/benchmark.py (ComputeEngine.benchmark_report / benchmark) | batch_search over a fixed 80-byte header (bytes(80), target 2^240), full enumeration with in-kernel target comparison, Task 003.9 accounting | D |
| Makefile bench (./bal-miner bench) | standalone bal_miner.c scan of a fixed header | C/D |
| mining/cpu/miner.py benchmark() | ComputeEngine.benchmark per backend plus a raw hashlib loop | D (and the hashlib loop is B-shaped: double SHA-256 of a header-shaped input, timed as a reference) |
| research/sha256d/experiments/bench_harness.py | counted batch2 entries on the genesis header, plus latency of count-1 calls | C/D |
| research/sha256d/experiments/h02_shani/bench_h01.py, bench_h02.py, bench_decision.py | SHA-NI kernel batches on header inputs | C/D |
| research/sha256d/extreme_optimization/benchmarks/bench_exp004 to exp011 | kernel variants, batch and search forms | D, with exp009_pipeline (below) reaching into E components |
| bench_exp009_pipeline.py | candidate construction cost (build_candidate against a stub RPC), span-size interaction of the production search, candidate confirmation cost, GBT round trip, and a stub-RPC mine_cycle wall-time split | E components, measured separately and labelled as such in its own docstring; it is not an F rate |
| research/sha256d/phase6/benchmarks/exp017_paired_bench.py and the phase6/phase6b paired benches (exp018, exp020 to exp026, exp022f, exp024, exp024b) | the EXP-017 paired protocol; each run declares its arm: batch arms are D, search arms through ComputeEngine.search_first_counted on real headers are E | D or E per arm, declared in each harness |
| research/sha256d/phase6b/benchmarks/exp025_paired_bench.py | candidate construction rate of the template cache (steps and family shapes) | construction component of E; its reports label it a candidate-construction rate, never a hash rate |
| research/sha256d/exp032/exp032_paired_bench.py | batch arms (AVX2, SHA-NI, flags) and search arms through the real ComputeEngine, including production v512dual search vs C search | D and E, labelled per arm in EXP032_REPORT.md |
| research/sha256d/exp031/tools/load_probe.py | search_first_counted under controlled load, for VM characterisation | E (as a load probe, not a rate claim) |
| dashboard and agent benchmark figure | ComputeEngine.benchmark() | D |

Category coverage verdicts:
- A (ordinary single SHA-256): NO harness in the tree
  measures single SHA-256 throughput as a headline number,
  and none presents one as a mining rate. Correctly absent.
- B: present only as reference loops inside larger
  harnesses; never presented as mining throughput.
- F (end-to-end pipeline rate): NO benchmark measures F as
  a rate, anywhere. End-to-end correctness is proven by
  regtest tests (functional, un-timed), which is the honest
  state: F is validated, not benchmarked. The Master
  Assignment asks for an F benchmark; today it is MISSING
  as a measurement (section 15, item 2).

Mislabel findings (places where one category's number is
presented as another's):
1. README.md, CPU aspect: "End to end engine rate
   6,617,558 H/s, MEASURED, suite benchmark" and the status
   table's "Suite peak CPU rate 6.62 MH/s end to end". The
   figure is a batch_search (category D) suite benchmark
   from the C-backend era. Calling a D measurement "end to
   end" presents it as E. It is also two backend generations
   stale (v512 and v512dual postdate it). DIFFERS.
2. No other mislabel was found. In particular: the
   EXP-025 steps figure (pooled 23.02x) is labelled a
   candidate-construction rate in every source and report
   that carries it, including the production code comment
   (mining/engine.py lines 195 to 200); the EXP-022 flags
   figures are labelled batch-scope in the registry, the
   integration log and the gpu/engine.py docstring; EXP-032
   labels batch and search arms separately and reports the
   production search comparison as its headline; the live
   miner's status rate is computed from search_first
   attempted counts (a genuine E rate) by
   mainnet_live.call_attempts.

## 10. Telemetry and statistics (EXP-037 and EXP-038)

- mining/autopilot.py EvidenceCounter (line 107): streams
  the whole evidence log once, then advances incrementally
  over appended bytes only, persisting (offset, accepted,
  rejected and share_result counts, last event epoch, SHA-256
  head fingerprint) atomically to .local/evidence-count.json;
  partial final lines are never consumed; rotation,
  truncation, corrupt state and a missing log all fall back
  to a recount or zero. One undetectable replacement shape
  (same head bytes, larger file) is documented in the code,
  not hidden. VERIFIED as the EXP-037 audit recorded.
- mining/mining_statistics.py (188 lines): the directive
  section 10 categories plus the EXP-035 accounting
  categories as separated counters, per-worker and
  per-backend breakdowns, unknown categories and negative
  counts refused, and snapshot() deliberately has NO
  combined total (the categories overlap by construction).
  Honest limitation recorded in its own docstring and
  confirmed by caller search: the module does not reach
  into the live paths; callers must record. No live path
  calls record() today, so the engine exists and is tested
  (test-exp037 passes) but is not yet wired into the live
  miner. DIFFERS from any reading of EXP-037 as live
  telemetry; the EXP-037 final report itself lists this
  under not-done, so the research record is accurate and
  the gap is a production-wiring gap.
- mining/probability.py (68 lines): expected_hashes =
  D times 2^32, expected_seconds = (D times 2^32) / R,
  prob_at_least_one = 1 - exp(-R t / (D times 2^32)),
  adopted from the previously orphaned research/probability.py
  (which still exists at research/probability.py; the
  production module is the reachable home, and its docstring
  states the adoption). Note a second expected-hashes
  formula exists in mining/pow_engine.py (expected_hashes =
  2^256 // (target + 1), the exact-integer form); the two
  are consistent (difficulty D corresponds to target about
  2^256 / (D times 2^32)) but they are different functions
  in different modules, worth one line in the probability
  deliverable. The Master Assignment's percentile outputs
  (median, 90th, 95th, 99th) are NOT implemented in
  mining/probability.py: MISSING (section 15, item 3).
- mining/work_checkpoint.py (170 lines): exact (extranonce,
  nonce) frontier over mine_cycle's lexicographic walk,
  keyed by the template's layered identity plus the
  extranonce space plus the curtime basis; atomic writes;
  the frontier advances only after a batch returns without
  a hit, so unfinished work is never recorded complete.
  Opt-in via MiningEngine checkpoint_path (default None,
  behaviour identical when off); the only production caller
  is agent/autonomous.py (WORK_CHECKPOINT_PATH under
  .local). VERIFIED.
- Autopilot heartbeat: .local/heartbeat.json every 5 s with
  miner state, uptime, restarts and the EvidenceCounter
  totals; watchdog polls the miner child every 1 s with a
  300 s hung window; self-update check every 900 s (inert in
  this checkout, which has no .git directory). Constants in
  mining/autopilot.py match docs/AUTOPILOT.md.

## 11. Tests: inventory and the audit suite run

Makefile test-all (line 96) lists exactly 30 targets:
test, test-regtest, test-engine, test-pow, test-gpu,
test-gpu-correction, test-mining, test-adversarial,
test-deepening, test-cpu, test-cpu-correction, test-rtl,
test-solo, test-solo-cutover, test-research, test-autopilot,
test-judgement, test-installer, test-task003, test-task0038,
test-task0039, test-avx512, test-avx512dual,
test-mainnet-live, test-template-cache, test-avx512flags,
test-exp036, test-exp034, test-exp037, test-exp038.

The audit ran every target individually on the audit host
(make stops at the first failure, so a single make test-all
cannot report the full state; per-target runs can). The
live miner, autopilot, mainnet node and solo cutover were
not touched; the suite's own regtest node (datadir
.local/regtest) is the only node the tests use.

Result as run, cold: 27 of 30 pass. The three failures:

1. test-regtest (tests/test_regtest_integration.py):
   FAILED with RPC getnewaddress error -18 "Requested
   wallet does not exist or is not loaded".
2. test-engine (tests/test_intelligence_engine.py):
   FAILED with RPC createwallet error -4 "Wallet file
   verification failed... Database already exists".
   Root cause of both, proven during the audit: the
   suite's persisted regtest datadir holds the bal-regtest
   wallet on disk (listwalletdir shows it) but the node
   starts with listwallets empty, and these two tests are
   the only wallet consumers whose helpers create the
   wallet but never load it (their ensure_wallet /
   wallet_rpc call createwallet only). Five later tests
   (test_mining_engine.py line 34, test_adversarial.py
   line 31, test_deepening.py line 30, test_cpu_aspect.py
   line 21, test_solo_server.py line 32) call loadwallet
   first, which is why they pass and why, once the wallet
   had been loaded as a side effect of the later targets,
   re-running test-regtest and test-engine unchanged gave
   ALL REGTEST TESTS PASSED and ALL INTELLIGENCE ENGINE
   TESTS PASSED. Classification: environment-state failure
   (persisted datadir plus unloaded wallet) exposing a
   real, minor test-helper robustness defect in exactly
   two test files. It is not a production code failure.
   With the wallet loaded the suite state is 29 of 30.
3. test-rtl (tests/test_rtl_aspects.py): FAILED with
   "iverilog: not found" (the test's own assertion error
   surfaces the missing binary). iverilog is not installed
   on this host (verified: which iverilog is empty).
   Classification: environment failure. The FPGA claims in
   the docs rest on historical runs on hosts that had the
   tool; they are UNVERIFIABLE on this host today.

All other 27 targets passed, including every target that
exercises code changed by EXP-034, EXP-036, EXP-037 and
EXP-038, all three AVX-512 integration suites (v512,
v512dual, flags), the template cache suite, the solo
server and solo cutover suites, and test-cpu-correction,
which SIGILLed on the earlier SHA-less Intel host and
passes here because this AMD host has sha_ni: direct
evidence that that failure class is host-shaped, exactly
as recorded. The deepening test additionally observed the
live dashboard path reporting backend v512dual and a peer
node syncing the regtest chain.

## 12. Build, deployment and supervision

- mining/cpu/build.py builds the five native libraries into
  .local/cpu/ with per-library smoke tests and loud,
  separate failures (a failed AVX-512 build never fails the
  C build). All five libraries are present and load.
- Makefile builds the standalone bal-miner with
  -march=native (host-local tool, not a shipped kernel).
- Supervision: mining/autopilot.py (single-instance flock,
  heartbeat, watchdog, crash backoff 1 s capped at 30 s,
  24 h session rotation, self-update inert without .git);
  systemd units scripts/bal-autopilot.service and
  scripts/bal-bitcoind.service, reinstalled after VM
  replacements by scripts/autopilot.sh; the outer keeper
  and the solo cutover watcher run as goal crons outside
  the repo. scripts/solo_cutover.py implements check, fire
  (with live Stratum smoke test, endpoint flip, miner-child
  restart through the autopilot, and server-side share
  verification) and automatic rollback; the endpoint mode
  lives in .local/mining-endpoint.json via
  mining/endpoint_config.py (mode "pool" at audit time).
- The solo service unit (scripts/bal-solo.service) is
  installed only at cutover fire time, by design.

Verdict: VERIFIED AS DOCUMENTED.

## 13. Documentation contradictions (doc vs code)

Material contradictions found, each checked against source.
Historical documents that are explicitly dated snapshots
(docs/EVIDENCE.md's 2026-11-13 session record, the README
status log) are listed only where they are presented as
current state.

1. README.md, Testing section and installer text: "make
   test-all runs 15 suites; all must print PASSED" and
   "tests/: 15 suites". The Makefile's test-all lists 30
   targets (section 11). DIFFERS, by a factor of two.
2. README.md, CPU aspect: the production miner is described
   as "a C batch engine... through OpenSSL's SHA-NI code
   path", with a 2026-11-14 update naming the AVX-512 MB
   kernel (v512) as the production backend. The current
   production backend is v512dual (DualMask, integrated
   2026-11-14 after the update was written); README never
   mentions v512dual, the template cache, candidate_verify,
   or EXP-030 anywhere. Its rate table (6.62 MH/s peak) is
   the C-era suite figure. DIFFERS (staleness presented as
   current description).
3. README.md, benchmark category: the 6,617,558 H/s figure
   labelled "End to end engine rate" is a category D batch
   measurement (see section 9, mislabel 1). DIFFERS.
4. README.md, status at a glance (dated 2026-11-13 but
   presented as the current status): worker shown as
   bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3.bal1. Since
   2026-11-14 every entry point defaults its worker to the
   machine hostname (mining/autopilot.py default_worker);
   this VM mines as htch-runtime. The README's own status
   log records that change, so the file contradicts itself.
   DIFFERS.
5. README.md, repository map: "research/: statistics and
   probability engine". research/ in fact holds the whole
   SHA-X programme (research/sha256d with its registries
   and the exp030 to exp038 trees) plus probability.py and
   statistics.py. DIFFERS by omission.
6. docs/ARCHITECTURE.md, decision 2: "Regtest first,
   mainnet paused... The earlier Stratum CPU mining code is
   preserved under mining/ but paused by owner
   instruction." Mainnet pool mining has been live and
   owner-ordered since 2026-11-13 (mining/mainnet_live.py,
   supervised by the autopilot), and the solo cutover is
   armed. DIFFERS; this is the oldest standing contradiction
   in the tree (already recorded by the EXP-030 Phase B gap
   analysis, still unfixed).
7. docs/ARCHITECTURE.md, module map: "gpu/: research gate.
   No implementation until Core integration is proven...
   Current VM has no GPU", and mining/ described as pow.py,
   bal_miner.c, stratum_client.py and wallet_gen.py. In
   code, gpu/engine.py IS the production ComputeEngine
   hosting every CPU backend, and mining/ holds the GBT
   engine, solo server, autopilot, candidate verifier,
   statistics, probability and checkpoint modules, none of
   which the map mentions. bal_miner.c is called "the
   SHA-NI CPU engine"; the production kernels are the
   bal_avx512*.c and bal_batch.c translation units.
   DIFFERS.
8. docs/ARCHITECTURE.md, repository visibility: "The repo
   stays private until the owner resolves that in one
   message." The repository is public (the owner flipped
   it on 2026-11-13; the audit's push verification recorded
   private: false). DIFFERS.
9. evidence/SUMMARY.md: "Evidence level reached: E2... No
   share has been accepted by a pool yet, so no E3 claim
   is made anywhere in this repository." The same
   directory's evidence/mainnet-live.jsonl contains the
   pool-accepted shares (first at 2026-11-13 18:59:51 UTC;
   the EXP-037 full-log census counted 248 accepted), and
   README and docs/EVIDENCE.md both record E3. SUMMARY.md
   summarises only the three pre-E3 session logs of
   2026-11-13 and was never updated. DIFFERS.
10. docs/MINING_ENGINE.md: describes the ComputeEngine's
    midstate C backend (bal_batch.c, OpenSSL SHA-NI) as the
    engine's advance, with no mention of the AVX-512
    backends, DualMask, the flags batch, the template
    cache or candidate verification. DIFFERS by omission
    (a Task 003-era document presented without a date
    boundary).
11. PRODUCTION_INTEGRATION_LOG.md Entry 3's consumer
    trace reads broader than the current call graph for
    batch_search (section 3 of this audit). Minor; the
    entry's scope claim itself (batch consumers only) is
    exact.
12. docs/EVIDENCE.md is a correct record of the
    2026-11-13 first share but is not a contradiction; it
    is listed here only to note it has never been extended
    past session 1, while the evidence log it points to
    now holds the full census. No action implied beyond
    the gap list.

Non-contradictions worth recording, because earlier gap
analyses flagged them and they are now closed: the
heartbeat share counter defect (EXP-037, fixed and
re-verified in section 10); the solo submitblock None
defect (EXP-036, closed in source); the solo coinbase
split-offset defect (EXP-034, closed in source).

## 14. Research directory: inventory vs the required structure

What exists today under research/:
- research/sha256d/: the entire SHA-X programme to date:
  17 markdown files at its root (baseline, mathematical
  foundations, header and midstate analysis, boolean
  equivalence, message schedule, round optimisation,
  compiler experiments, microarchitecture, mining
  pipeline, statistics, rejected hypotheses, roadmap,
  findings, a README, and experiment_registry.md), a
  second registry at extreme_optimization/
  EXPERIMENT_REGISTRY.md, and the
  phase trees: experiments/ (EXP-000 to EXP-023 era,
  bench_harness, h02_shani), extreme_optimization/
  (EXP-004 to EXP-029 sources, benchmarks, proofs),
  phase6/, phase6b/ (EXP-017 to EXP-029 records, audits,
  integration log), exp030/ (reference audit, matrix, gap
  analysis, final report), exp031/ (VM characterisation),
  exp032/, exp033/, exp034/, exp035/, exp036/, exp037/,
  exp038/, plus tools/.
- research/probability.py and research/statistics.py at the
  research root (the probability module is the research
  original of mining/probability.py).
- None of the Master Assignment's 19 named deliverable
  files exists yet, under any directory. Partial analogues
  exist for several (the EXP-030 Phase B gap analysis for
  deliverable 15, EXP-031 for deliverable 10, EXP-037 for
  deliverables 11 and 12), but each deliverable remains to
  be produced and verified under this programme.

Required structure (Master Assignment section 14) vs the
tree at audit start: research/sha256d/ existed; the other
14 directories did not. As instructed, this audit created
the missing directories, each with a one-line README.md
stating its purpose per the directive, and moved or
renamed nothing:
research/bitcoin_reverse_engineering/ (this audit's home),
research/bitcoin_core/, research/proof_of_work/,
research/nonce_search/, research/cpu_architecture/,
research/hashrate/, research/probability/,
research/node_integration/, research/cryptanalysis/,
research/experiments/, research/benchmarks/,
research/formal_proofs/, research/architecture/,
research/phase_reports/.

## 15. Gap list against the Master Assignment's desired architecture

Mapped to the work packages (BR-001 to BR-017). Only gaps
this audit established from source are listed; Phase B to H
work is noted as not started, not as failed.

1. BR-002 (Core source audit): no Bitcoin Core source
   checkout exists; the exact-revision source investigation
   (v28.1 tag, files, line ranges) has not begun. All 19
   deliverables are absent (section 14).
2. BR-010 (honest hashrate): no category F benchmark exists
   (section 9). Category A is unmeasured by design. The
   dashboard and agent benchmark figure is category D and
   is displayed under the bare label "benchmark"
   (dashboard/server.py line 58), which invites the same
   misreading as README mislabel 1.
3. BR-011 (probability): mining/probability.py lacks the
   directive's percentile outputs (median, 90th, 95th,
   99th), probability-over-horizon helpers beyond days,
   and any network-target (as opposed to difficulty) input
   form. Two expected-hashes formulations coexist
   (probability.py and pow_engine.py) without a recorded
   equivalence note.
4. BR-007 / BR-015 (search space, distributed): no
   production coordinator assigns extranonce_space windows;
   EXP-035's lease manager, coordinator and candidate
   queue are research prototypes under
   research/sha256d/exp035/, proven in-process only.
   Version rolling and timestamp rolling are absent on
   every path, so the search space per template is nonce
   times the extranonce window only. wait_template
   (longpoll) has no production caller.
5. BR-016 (integrated engine): mining/mining_statistics.py
   is not wired into any live path (no production caller
   of record()); EXP-032's verified AVX2 and SHA-NI
   multi-stream kernels are not integrated as dispatch
   tiers for non-AVX-512 hosts (the SHA-NI production TU
   that IS present, bal_sha_intrin.c, is the older
   single-stream form EXP-032 measured negative; the
   verified H-01 streams form exists only in research
   code). Hosts without AVX-512 therefore fall back to C
   or hashlib, exactly as before EXP-032.
6. BR-012 (node and submission): MiningEngine's acceptance
   check is inline and equivalent to, but not shared with,
   candidate_verify.verify_chain_acceptance; there is no
   candidate queue between search and submission on any
   path (a found candidate is submitted synchronously);
   no reorg re-check follows an accepted block; Stratum V2
   is absent (V1 only, as documented).
7. BR-009 (VM capacity): EXP-031 characterised one host
   shape; the audit host differs from the EXP-032 host
   record only in being the same AMD model, while an
   intervening Intel host (no SHA-NI) is on record. No
   production code consumes VM intelligence: dispatch is
   pure CPUID, with no effective-CPU or steal awareness.
   That is a defensible design, but the directive's
   environment report is a point sample, not a standing
   mechanism.
8. Documentation debt: the 11 contradictions in section 13,
   of which the ARCHITECTURE.md staleness (items 6 to 8)
   and the README suite count and backend description
   (items 1 to 4) are the ones a new reader hits first.
9. Test robustness: two test helpers (test_regtest and
   test-engine) lack the loadwallet step five sibling
   tests have (section 11); on a cold persisted regtest
   datadir, make test-all fails at target 2 of 30 and
   reports nothing about the remaining 28.

## 16. Most consequential findings (closing summary)

1. The flags question is settled, in the owner's favour
   and exactly as the integration record states: the
   EXP-022 flags form serves batch enumeration only. The
   live miner's search path (mainnet_live to search_first
   to the native bal_vd_search2) contains no flags code,
   and the flags library exports no search entry. Any
   future claim of a flags search gain must first reckon
   with EXP-032's measured negative on that exact path.
2. The template cache fingerprint is complete. Every
   field of every layer was read from production source;
   the only inputs outside the identity are the time
   fields, which are read live per build by design, and
   getblocktemplate fields the construction never reads.
   The one real boundary is the held-object mutation
   surface in the mine_cycle steps path (five live-read
   fields on an object the loop holds), documented in
   code and confirmed here; no production code crosses it.
3. Production matches the Phase 6B record on every
   material point: DualMask integrated and selected,
   design C verified and genuinely not integrated (the
   words "certified single-batch fallback" describe a
   research status, not deployed code), the negative
   designs absent. The research tree's integrity, which
   the Master Assignment ordered verified rather than
   assumed, holds.
4. The suite state is better than a cold make test-all
   suggests and worse than the README claims: 27 of 30
   targets pass cold, 29 of 30 once the regtest wallet is
   loaded, and the thirtieth (test-rtl) needs a tool this
   host does not have. The two cold failures share one
   proven root cause (a persisted, unloaded regtest
   wallet plus two test helpers that never load it), and
   the README's "15 suites" is half the true count.
5. The documentation layer is the weakest part of the
   repository. ARCHITECTURE.md still says mainnet is
   paused and the repo is private; the README still
   describes a C/SHA-NI production miner, a bal1 worker
   and a 15-suite test-all, and labels a batch benchmark
   "end to end"; evidence/SUMMARY.md still denies the E3
   the evidence log proves. None of this touches
   production correctness, but a reader who trusts the
   docs over the code will misunderstand the system, which
   is precisely what Phase A exists to prevent.
6. The honest ceilings are unchanged and re-verified:
   no GPU exists here and no GPU figure is measurable;
   the verified fallback tiers from EXP-032 (AVX2,
   SHA-NI streams) are not integrated, so non-AVX-512
   hosts gain nothing from them yet; there is no
   category F benchmark, no production coordinator, no
   version or timestamp rolling, and no Bitcoin Core
   source tree yet for Phase B. The targets stand where
   the directive put them: 500 GH/s minimum, 140 TH/s
   larger objective, neither claimed, neither lowered.
