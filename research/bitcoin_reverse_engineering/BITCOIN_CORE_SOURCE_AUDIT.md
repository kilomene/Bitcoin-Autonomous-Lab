# Bitcoin Core Source Audit (canonical): v28.1

NOVA SHA-X Master Assignment, deliverable 2 (work package BR-002).
This is the canonical named audit. It consolidates and extends
research/bitcoin_core/CORE_SOURCE_AUDIT.md (the Phase A/B foundation
audit), which it cites throughout and does not contradict. PoW and
difficulty evidence lives in research/bitcoin_core/POW_DIFFICULTY_SOURCE.md;
the call graph lives in BITCOIN_MINING_CALL_GRAPH.md in this directory
(consolidated from research/bitcoin_core/MINING_CALL_GRAPH.md).

All file paths and line numbers refer to the pinned v28.1 tree itself.
Nothing here was reconstructed from documentation or memory; every claim
was read from the checked-out source during the Phase A/B audit or
re-verified against the tree during this consolidation.

## 1. Revision record

| Field | Value |
|---|---|
| Repository URL | https://github.com/bitcoin/bitcoin |
| Release tag analysed | v28.1 |
| Exact commit SHA | 32efe850438ef22e2de39e562af557872a402c31 |
| Commit subject | Merge bitcoin/bitcoin#31594: [28.x] 28.1 backports and final changes |
| Commit date | 2025-01-07 13:32:56 -0500 |
| Branch context | 28.x maintenance branch release tag; detached HEAD at the tag |
| Retrieval method | git clone --depth 1 --branch v28.1 (first route tried, succeeded) |
| Retrieval time (UTC) | 2026-11-15 about 17:09 UTC |
| Local location | ~/workspace/bitcoin-autonomous-lab/.local/refs-core/bitcoin-v28.1 (outside the pushed repo tree; .local is excluded from pushes) |
| Tree size on disk | 62 MB (shallow clone, includes .git) |
| Source modified | No. Read-only audit. No build attempted. |
| Master HEAD at retrieval (context only) | a527a0077a0fcae913188410214efe98021c0cca (git ls-remote, 2026-11-15) |

Master was NOT analysed. Master is roughly ten months of development
ahead of this tag and its file layout differs; every line number in this
audit is a v28.1 line number.

### 1.1 Relationship to the deployed binary

Deployed binary: ~/workspace/bitcoin-core-dist/bitcoin-core-28.1/bin/bitcoind,
which prints "Bitcoin Core version v28.1.0". The deployed binary is the
official Bitcoin Core project release build of the same 28.1 release whose
source is pinned above (the release tarball used to install this node was
hash-verified against the project's official SHA256SUMS at install time,
per lab records). The binary was built by the Bitcoin Core project, not
compiled by us from this checkout. The tag name is "v28.1" while the
binary prints "v28.1.0"; these are the same release (28.x tags drop the
trailing zero, the version string does not). Source-level conclusions
therefore describe the code the deployed node was built from, at
release-tag fidelity.

### 1.2 Build configuration and test suites (as shipped in the tree)

- Build system in v28.1 is autotools: configure.ac and Makefile.am at the
  repository root. There is NO top-level CMakeLists.txt in v28.1 (the
  CMake migration landed in later releases). This contradicts the
  Master Assignment's implicit master-era assumption; see section 8.
- Relevant test suites present in src/test/: crypto_tests.cpp (1,273
  lines; includes SHA256D64 differential tests at line 1074),
  pow_tests.cpp (211 lines; includes CheckProofOfWork negative-target and
  overflow-target cases at lines 83 and 93), miner_tests.cpp (661 lines),
  arith_uint256_tests.cpp, merkle_tests.cpp, merkleblock_tests.cpp,
  miniminer_tests.cpp.
- Relevant benchmark present: src/bench/crypto_hash.cpp (SHA256 and
  SHA256D64 benchmarks per implementation variant, lines 141 to 176 and
  registrations at 257 to 260).

## 2. File inventory: mining-relevant surface

Sizes are lines / bytes in the pinned tree. "Directive name" notes where
the Master Assignment's guessed filename differs from the actual v28.1
filename.

### 2.1 SHA-256 implementation (src/crypto/)

| File | Lines | Bytes | Status and key content |
|---|---|---|---|
| src/crypto/sha256.h | 53 | 1,514 | Exists. class CSHA256 at line 13; Write line 24, Finalize line 25, Reset line 26; sha256_implementation::UseImplementation flags lines 29 to 38; SHA256AutoDetect declaration line 44; SHA256D64 declaration line 51 |
| src/crypto/sha256.cpp | 783 | 36,561 | Exists. Generic transform, dispatch, self-test, CSHA256 methods, SHA256D64 (see section 3) |
| src/crypto/sha256_sse4.cpp | 1,513 | 43,148 | Exists. namespace sha256_sse4 line 13; 1-way SSE4.1 Transform line 15. This is the single-block SSE4 transform, distinct from the SSE41 D64 file below |
| src/crypto/sha256_sse41.cpp | 321 | 19,370 | Exists. namespace sha256d64_sse41 line 13; Transform_4way line 68 (4-way double-SHA256 of 64-byte inputs only) |
| src/crypto/sha256_avx2.cpp | 329 | 19,940 | Exists. namespace sha256d64_avx2 line 13; Transform_8way line 76 (8-way double-SHA256 of 64-byte inputs only) |
| src/crypto/sha256_x86_shani.cpp | 358 | 16,157 | Exists. Directive name was "sha256_shani.cpp"; actual x86 file is this one. namespace sha256_x86_shani line 79, Transform line 80; namespace sha256d64_x86_shani line 144, Transform_2way line 146 |
| src/crypto/sha256_arm_shani.cpp | 899 | 33,304 | Exists. namespace sha256_arm_shani line 41, Transform line 42; namespace sha256d64_arm_shani line 200, Transform_2way line 201 |

There is no file named sha256_shani.cpp in v28.1. The SHA-NI
implementation is split per architecture: sha256_x86_shani.cpp and
sha256_arm_shani.cpp.

### 2.2 Hashing glue and header

| File | Lines | Bytes | Status and key content |
|---|---|---|---|
| src/hash.h | 229 | 5,911 | Exists. class CHash256 line 24 (its Finalize at line 34 performs the second SHA-256 pass, making CHash256 a double hash); Hash() helpers lines 75 and 84; class HashWriter line 100, HashWriter::GetHash line 115 (double-hash of the serialized stream, body lines 115 to 118), GetSHA256 line 126 (single hash) |
| src/primitives/block.h | 158 | 4,061 | Exists. class CBlockHeader line 21; fields nVersion line 25, hashPrevBlock line 26, hashMerkleRoot line 27, nTime line 28, nBits line 29, nNonce line 30; SERIALIZE_METHODS line 37 (field order is the wire order); GetHash declaration line 54; class CBlock line 68 |
| src/primitives/block.cpp | 30 | 870 | Exists. CBlockHeader::GetHash definition lines 11 to 14: `return (HashWriter{} << *this).GetHash();` |
| src/consensus/merkle.h | 27 | 871 | Exists. BlockMerkleRoot / BlockWitnessMerkleRoot / ComputeMerkleRoot declarations |
| src/consensus/merkle.cpp | 85 | 3,469 | Exists. ComputeMerkleRoot line 45; the pairwise level step calls SHA256D64 at line 56; BlockMerkleRoot line 65; BlockWitnessMerkleRoot line 75 |

### 2.3 Proof of work and 256-bit arithmetic

| File | Lines | Bytes | Status and key content |
|---|---|---|---|
| src/pow.h | 37 | 1,456 | Exists. GetNextWorkRequired line 17, CalculateNextWorkRequired line 18, CheckProofOfWork line 21, PermittedDifficultyTransition line 35 |
| src/pow.cpp | 154 | 5,935 | Exists. Full evidence in POW_DIFFICULTY_SOURCE.md |
| src/arith_uint256.h | 283 | 8,588 | Exists. SetCompact declaration line 271, GetCompact declaration line 272 |
| src/arith_uint256.cpp | 231 | 6,231 | Exists. SetCompact definition line 175, GetCompact line 195 |
| src/consensus/params.h | 156 | 5,847 | Exists. Consensus::Params fields: powLimit line 109, fPowAllowMinDifficultyBlocks line 110, fPowNoRetargeting line 116, nPowTargetSpacing line 117, nPowTargetTimespan line 118, DifficultyAdjustmentInterval() line 123 (returns timespan / spacing) |
| src/kernel/chainparams.cpp | 709 | 35,343 | Exists. CMainParams line 81, CTestNetParams line 207, CTestNet4Params line 308, SigNetParams line 407, CRegTestParams line 523. Per-chain values in POW_DIFFICULTY_SOURCE.md |

### 2.4 Mining, template construction, RPC, validation

| File | Lines | Bytes | Status and key content |
|---|---|---|---|
| src/node/miner.h | 216 | 7,699 | Exists. class BlockAssembler line 139; Options struct line 161; CreateNewBlock declaration line 173; UpdateTime declaration line 207 |
| src/node/miner.cpp | 433 | 18,014 | Exists. UpdateTime line 31; BlockAssembler constructor line 78; resetBlock line 96; CreateNewBlock lines 109 to 188; AddToBlock line 226; addPackageTxs line 295 |
| src/node/block_template_manager.cpp / .h | n/a | n/a | ABSENT in v28.1. There is no block template manager file. Template assembly is BlockAssembler in src/node/miner.cpp, reached through the interfaces::Mining interface (src/interfaces/mining.h line 49; implementation src/node/interfaces.cpp line 912). A src/node/mini_miner.cpp also exists, but it is a fee-estimation helper (MiniMiner), not the template path |
| src/rpc/mining.cpp | 1,128 | 49,102 | Exists. RPC definitions and registration; full trace in BITCOIN_MINING_CALL_GRAPH.md |
| src/validation.cpp | 6,519 | 320,949 | Exists. Relevant entry points: CheckBlockHeader line 3909 (calls CheckProofOfWork at line 3912), CheckBlock line 3999, GenerateCoinbaseCommitment line 4076, ContextualCheckBlockHeader line 4159, ChainstateManager::ProcessNewBlockHeaders line 4388, ChainstateManager::ProcessNewBlock line 4545, TestBlockValidity line 4609 |

## 3. The SHA-256 call path (block header hashing)

Exact chain for hashing one block header, file:line at each hop:

1. src/primitives/block.cpp:11 CBlockHeader::GetHash()
   `return (HashWriter{} << *this).GetHash();`
   The header is serialized by SERIALIZE_METHODS (src/primitives/block.h:37)
   in field order nVersion, hashPrevBlock, hashMerkleRoot, nTime, nBits,
   nNonce, which is exactly the 80-byte wire layout.
2. src/hash.h:115 HashWriter::GetHash()
   Finalizes the CSHA256 context over the serialized bytes into a 32-byte
   result, then resets the context, writes those 32 bytes, and finalizes
   again (hash.h lines 115 to 118). This second pass is what makes the
   result SHA256d rather than SHA256.
3. src/crypto/sha256.cpp:701 CSHA256::Write() buffers input and calls the
   global function pointer Transform (calls at lines 710 and 715) once per
   full 64-byte block; src/crypto/sha256.cpp:727 CSHA256::Finalize()
   appends the 0x80 padding and the big-endian bit length through Write,
   then writes the state out big-endian.
4. The Transform pointer (src/crypto/sha256.cpp:483, default
   sha256::Transform) is bound by SHA256AutoDetect (section 4) to one of:
   - generic scalar: sha256::Transform, src/crypto/sha256.cpp:101
   - x86 SHA-NI: sha256_x86_shani::Transform, src/crypto/sha256_x86_shani.cpp:80
   - x86 SSE4.1: sha256_sse4::Transform, src/crypto/sha256_sse4.cpp:15
   - ARM SHA-NI: sha256_arm_shani::Transform, src/crypto/sha256_arm_shani.cpp:42

Consequences worth stating plainly:

- Block header hashing in Core uses the single-stream CSHA256 path. The
  multi-way double-hash machinery (TransformD64_2way / 4way / 8way) is
  never used for header hashing.
- CSHA256 exposes no midstate API. There is no way through the public
  CSHA256 interface to snapshot or preload the state after the first
  64-byte chunk; Write always starts from the standard initial state set
  by the constructor or Reset (src/crypto/sha256.cpp:696 and 744, both
  calling sha256::Initialize). Any midstate reuse in a mining engine is
  therefore an engine-side construction, not a Core facility. This is the
  single most consequential audit fact for NOVA SHA-X: the reusable
  header state that benchmark category D exploits exists in no Bitcoin
  codebase, 2009 or 2026 (the v0.1.3 miner likewise re-initialised state
  per candidate; Phase 001, MINING_EXECUTION_FLOW.md sections 4 to 6).
- The one specialised double-hash path Core does have is SHA256D64
  (src/crypto/sha256.h:51; src/crypto/sha256.cpp:751), which computes
  double-SHA256 of exact 64-byte inputs in bulk (8-way AVX2, 4-way
  SSE4.1, 2-way SHA-NI, or the 1-way TransformD64Wrapper at
  sha256.cpp:444, which hard-codes the two padding blocks for a 64-byte
  message). Its only production caller is the Merkle tree level step,
  src/consensus/merkle.cpp:56 (ComputeMerkleRoot). Its other callers are
  the benchmark (src/bench/crypto_hash.cpp) and the unit test
  (src/test/crypto_tests.cpp:1074). SHA256D64 is a Merkle optimisation,
  not a mining kernel.

## 4. Runtime dispatch and fallback behaviour

Dispatch is a one-time global selection, not per-call branching:

- Entry point: SHA256AutoDetect(), src/crypto/sha256.cpp:587. In the
  production binaries its caller is the kernel context initialisation,
  src/kernel/context.cpp:19. (All other callers are bench code.)
- It first resets all pointers to the generic implementation
  (sha256.cpp:591 to 594), so the fallback at every level is the portable
  scalar code.
- Feature detection on x86 uses GetCPUID (sha256.cpp, HAVE_GETCPUID block
  starting at line 598): CPUID leaf 1 ECX bit 19 for SSE4, leaf 7 EBX
  bit 5 for AVX2, leaf 7 EBX bit 29 for SHA-NI, plus XCR0 AVX enablement
  via AVXEnabled() before any AVX2 use.
- Selection order on x86 (sha256.cpp:626 to 652):
  1. If SHA-NI present: Transform = sha256_x86_shani::Transform,
     TransformD64 = wrapper over it, TransformD64_2way =
     sha256d64_x86_shani::Transform_2way, reported name
     "x86_shani(1way,2way)"; SSE4 and AVX2 D64 ways are then disabled.
  2. Else if SSE4 present: Transform = sha256_sse4::Transform,
     TransformD64 = wrapper over it ("sse4(1way)"), and if compiled with
     ENABLE_SSE41, TransformD64_4way = sha256d64_sse41::Transform_4way.
  3. Independently, if AVX2 + AVX + enabled AVX: TransformD64_8way =
     sha256d64_avx2::Transform_8way is added (only reachable when SHA-NI
     did not take over, per the disabling in step 1).
- On ARM, detection uses getauxval HWCAP_SHA2 / HWCAP2_SHA2 on Linux or
  the hw.optional.arm.FEAT_SHA256 sysctl on Apple platforms
  (sha256.cpp:655 to 687); selection sets the arm_shani 1-way and 2-way
  functions.
- Compile-time gates: the whole optimised block is skipped if
  DISABLE_OPTIMIZED_SHA256 is defined, and per-file availability is
  gated by ENABLE_SSE41, ENABLE_AVX2, ENABLE_X86_SHANI, ENABLE_ARM_SHANI
  macros set by the build system based on compiler support.
- Safety net: SHA256AutoDetect ends with assert(SelfTest()) at
  sha256.cpp:690. SelfTest (sha256.cpp:488) verifies the selected
  Transform over 0 to 8 blocks and every non-null TransformD64 way
  against the generic implementation's known outputs. A miscompiled or
  misdetected optimised path therefore aborts in debug/assert builds at
  startup rather than hashing wrongly.
- SHA256D64 (sha256.cpp:751) consumes the selected ways largest first:
  8-way while at least 8 blocks remain, then 4-way, then 2-way, then the
  1-way TransformD64 for the remainder (lines 753 to 783).

## 5. Which hashing path does mining use?

Two different answers, both source-verified:

- External mining (the production model): Core does not hash candidates
  at all. getblocktemplate hands the header fields to an external miner,
  and the returned block is validated on submission. The only header
  hashing Core performs in this model is verification: CheckBlockHeader
  (src/validation.cpp:3909) calls CheckProofOfWork(block.GetHash(),
  block.nBits, ...) at validation.cpp:3912, which runs the generic
  HashWriter/CSHA256 path of section 3. There is no specialised mining
  hash path in Core 28.1.
- Internal generation (regtest only): the generate family of RPCs uses
  GenerateBlock (src/rpc/mining.cpp:133), a single-threaded loop that
  increments block.nNonce and calls CheckProofOfWork(block.GetHash(), ...)
  per candidate (rpc/mining.cpp:138 to 141), again the generic path. See
  BITCOIN_MINING_CALL_GRAPH.md for the full picture, including what
  happens on nonce exhaustion (no extranonce increment exists in this
  revision).

## 6. Template engine and RPC surface (summary; detail in the call graph)

- Template assembly is exactly one component: BlockAssembler in
  src/node/miner.cpp (class at src/node/miner.h:139; CreateNewBlock at
  miner.cpp:109 to 188), reached only through the interfaces::Mining
  abstraction (src/interfaces/mining.h:49; node implementation
  src/node/interfaces.cpp:912). There is no block_template_manager in
  this revision, and src/node/mini_miner.cpp (MiniMiner) is a
  fee-estimation helper, not part of the template path.
- The mining RPC surface is registered by RegisterMiningRPCCommands
  (src/rpc/mining.cpp:1109 to 1128): getnetworkhashps (line 108),
  getmininginfo (413), prioritisetransaction (465),
  getprioritisedtransactions (502), getblocktemplate (569), submitblock
  (998), submitheader (1070), plus the hidden regtest generation family
  generatetodescriptor (215), generate (253), generatetoaddress (260),
  generateblock (301). The getblockchaininfo / getblock /
  getblockheader / getchaintips / getblockhash family named in the
  Master Assignment lives in src/rpc/blockchain.cpp, not in the mining
  file; those are read-only chain queries outside the template and
  submission path.
- Template caching lives in the RPC layer, not in the assembler: static
  pindexPrev and pblocktemplate at rpc/mining.cpp:801 to 803, rebuilt
  only on a new tip or a mempool change older than 5 seconds
  (rpc/mining.cpp:804 to 805). Full treatment in
  NODE_AND_SUBMISSION_ARCHITECTURE.md.

## 7. Submission pipeline (summary; detail in the call graph)

submitblock (src/rpc/mining.cpp:998) decodes the block, pre-checks for
duplicates, registers a validation-interface listener, and calls
interfaces::Mining::processNewBlock, which reaches
ChainstateManager::ProcessNewBlock (src/validation.cpp:4545). That runs
CheckBlock (validation.cpp:3999; CheckBlockHeader at 3909 with
CheckProofOfWork at 3912; CheckMerkleRoot at 3918), then AcceptBlock
(validation.cpp:4566), whose contextual header check
(ContextualCheckBlockHeader, validation.cpp:4159) requires the header's
nBits to equal GetNextWorkRequired for its position, and whose
ConnectBlock / ActivateBestChain step (ActivateBestChain at
validation.cpp:3439) makes the block the tip only if it connects and its
chain carries the most accumulated work (nChainWork comparisons, e.g.
validation.cpp:3607). The RPC maps the outcome to BIP22 result strings;
a null return means processed, not proven to be in the best chain. The
client-side rule this imposes is stated in
NODE_AND_SUBMISSION_ARCHITECTURE.md section 3.

## 8. Contradictions of the Master Assignment's assumptions

The assignment's guessed source layout was wrong in five places. Each is
recorded here so no later deliverable repeats the guess:

1. There is no src/crypto/sha256_shani.cpp. SHA-NI is split per
   architecture (sha256_x86_shani.cpp, sha256_arm_shani.cpp), and there
   are two distinct SSE4-era files: sha256_sse4.cpp (1-way Transform)
   and sha256_sse41.cpp (4-way D64).
2. There is no block_template_manager (no src/node/block_template_manager.cpp
   or .h) in v28.1. BlockAssembler behind interfaces::Mining is the
   whole template engine.
3. IncrementExtraNonce does not exist anywhere in the v28.1 tree
   (verified by full search of src/). Extranonce is entirely client-side
   in this revision; the server coinbase scriptSig is exactly
   CScript() << nHeight << OP_0 (src/node/miner.cpp:161).
4. v28.1 is autotools-only. There is no top-level CMakeLists.txt; the
   CMake build system belongs to later releases (master), which the
   assignment correctly warned is not the deployed version.
5. The chain-query RPCs the assignment grouped with mining
   (getblockchaininfo and relatives) live in src/rpc/blockchain.cpp,
   not src/rpc/mining.cpp.

Two further findings contradict common expectations rather than the
assignment text, and are recorded for the same reason:

6. SHA256D64, the closest thing Core has to a mining-style multi-buffer
   double hash, serves the Merkle tree only (production caller
   src/consensus/merkle.cpp:56). It is never used for header hashing.
7. SetCompact never rejects anything (src/arith_uint256.cpp:175 to 193);
   all rejection lives in CheckProofOfWork (src/pow.cpp:137 to 154).
   Any reimplementation that puts rejection inside the decoder diverges
   from Core's structure, even if its accept/reject outcomes agree.
