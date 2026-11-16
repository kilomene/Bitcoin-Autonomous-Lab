# Historical Miner Research: NOVA SHA-X Master Build Mandate, Section 3

Date: 2026-11-15. Scope: source-backed study of the historical
and modern mining codebases listed in section 3 of the Master
Build Mandate, as input to the autonomous mining intelligence
architecture. Method: shallow clones (git clone --depth 1)
into .local/refs-masterbuild/ (outside the pushed tree),
exact HEAD commit recorded per clone, mining-relevant files
read at source level. No cloned code was executed. No code
was copied into this repository. Licence statements below
were read from the licence file inside each clone.

Companion file: HISTORICAL_OPPORTUNITY_REGISTER.md (same
directory), which turns the transferable ideas in this report
into register rows, cross-checked against the existing NOVA
research programme (EXP-011 to EXP-043, Phase 001, the
EXP-030 Phase A matrix).

## Clone inventory and identity verification

| Clone directory | Repository | HEAD commit studied |
|---|---|---|
| (pre-existing) | bitcoin/bitcoin v28.1 tag | 32efe850438ef22e2de39e562af557872a402c31 |
| jgarzik-cpuminer | github.com/jgarzik/cpuminer | 04b9224dbe55265a2c061e272f2c22b4147127c5 |
| pooler-cpuminer | github.com/pooler/cpuminer | 5f02105940edb61144c09a7eb960bba04a10d5b7 |
| m0mchil-poclbm | github.com/m0mchil/poclbm | 2ae15b77df1d17d2ec2748673ba2e8e0a01891c5 |
| Kiv-poclbm | github.com/Kiv/poclbm | 5c6b314b63573b005c647110bdd64431b4ebee7f |
| DiabloMiner | github.com/Diablo-D3/DiabloMiner | 822e17e60d43b6b07d00fdd32b679aca0b9c41ce |
| Phoenix-Miner | github.com/jedi95/Phoenix-Miner | ec8af03cfdf7b0dbf46e2d8561adba66c60ca437 |
| ckolivas-cgminer | github.com/ckolivas/cgminer | b8491c66e7e22f23a9edf095dd1337ee581e88bd |
| kanoi-cgminer | github.com/kanoi/cgminer | d689d3a9057e8852de51d5c7f402ce26cbceaea5 |
| bfgminer | github.com/luke-jr/bfgminer | 866fd36f3a77d181805b899d5d306bd87b01f704 |
| fpga-miner | github.com/fpgaminer/Open-Source-FPGA-Bitcoin-Miner | 72a5e183785afe5c1a53be2a623946981d1c2a6e |
| Avalon-extras | github.com/Canaan-Creative/Avalon-extras | 704b47edb9639eb4e06b8893094e4584cff9001e |
| bmminer-mix | github.com/bitmaintech/bmminer-mix | 7aebcf2c2cb7bd8cafca7f920d30011d0547d16a |
| braiins-bmminer | github.com/braiins/bmminer | 93ad6af550c3f5bf592dedadec1aff5926e7cfd6 |
| braiins-os-fork-davhau | github.com/DavHau/braiins-os (fork, see below) | 572dd48c905abb515a374578b52eeccbdc467286 |
| sgminer | github.com/sgminer-dev/sgminer | 8bf1c1807cca1ca0ec0f87b452e3d1cb395f0b1b |
| ccminer | github.com/tpruvot/ccminer | 6ff4e50987e59a70056324a94ed8667cc0bf598d |
| CudaMiner | github.com/cbuchner1/CudaMiner | 746a7733dda9d2b3466c54c149362e4fb205cc3f |
| stratum-v2 | github.com/stratum-mining/stratum | 2220f62dbdc833a64c53f05bd0fbed3ae611f4d6 |
| ckpool | bitbucket.org/ckolivas/ckpool | e05462e8872400c4ee6e3d8c07a45c10758e5620 |

## Honesty notes: failures and identity corrections

1. bitmaintech/bmminer (the URL in the mandate) could NOT be
   cloned. GitHub returns its not-found behaviour (an
   authentication prompt on a non-interactive clone) for that
   path today, verified twice, including with terminal
   prompts disabled. The repository existed historically:
   Bitmain's own blog and a 2017 CoinDesk article reference
   github.com/bitmaintech/bmminer, including issue 7 of
   September 2016 (the Antbleed report). Bitmain's blog names
   bitmaintech/bmminer-mix as the published source for the
   Antminer S9, T9 and R4 miner. This study therefore reads
   bmminer-mix, clearly labelled as the vendor-announced
   successor source, and does not claim it is the removed
   bmminer tree.
2. braiins/braiins-os (the URL in the mandate) could NOT be
   cloned either; same not-found behaviour, verified twice.
   Braiins documentation from the period instructs cloning
   exactly that URL, so it existed and is no longer public.
   Two labelled substitutes were read instead: (a) a public
   fork, DavHau/braiins-os, whose HEAD commit (572dd48c,
   "Release Firmware", February 2019, authored by a Braiins
   developer) matches the commit cited for that fork in
   public search results; fork provenance beyond that match
   is unverified, and findings from it are marked as
   fork-sourced; (b) braiins/bmminer, the Braiins
   organisation's own public fork of the Bitmain miner,
   cloned from the organisation directly.
3. Kiv/poclbm identity resolved: the mandate listed it as
   "GUIMiner-related". The clone IS GUIMiner: its README.md
   titles it "GUIMiner, a graphical interface for mining
   Bitcoins, by Chris 'Kiv' MacLeod, based on poclbm by
   m0mchil". The file family (Miner.py, OpenCLMiner.py,
   GetworkSource.py, StratumSource.py, phatk.cl) is the
   m0mchil poclbm codebase with a GUI layer and later fixes.
   It is not an independent miner.
4. MicroBT Whatsminer: NO official public source repository
   could be verified. MicroBT distributes closed firmware
   binaries and the WhatsMinerTool application through
   whatsminer.com; no source tree is published. Public
   documentation shows the Whatsminer firmware contains a
   cgminer derivative (its structured error registry includes
   code 800, "Cgminer checksum error"), but no source-level
   study is possible. Section 3.16 records what could and
   could not be verified.
5. Icarus, ZTEX and Block Erupter have no standalone official
   miner repositories of their own in the studied set. They
   are covered at source level through the cgminer and
   BFGMiner driver files (section 3.11), which is where their
   protocol implementations actually live.
6. The Bitaxe family is NOT re-studied here. EXP-030 Phase A
   covered it at pinned commits; section 3.19 summarises
   from research/sha256d/exp030/REPOSITORY_AUDIT.md and
   research/sha256d/exp030/REFERENCE_TO_NOVA_MATRIX.md.

## 3.0 Bitcoin Core (bitcoin/bitcoin), CPU mining history, brief

- URL and identity: github.com/bitcoin/bitcoin, the Bitcoin
  Core project. Version studied: tag v28.1, commit
  32efe850438ef22e2de39e562af557872a402c31, already cloned at
  .local/refs-core/bitcoin-v28.1 and fully audited in
  research/bitcoin_reverse_engineering/ (BITCOIN_CORE_SOURCE_AUDIT.md,
  BITCOIN_MINING_CALL_GRAPH.md, MINING_TEMPLATE_AND_COINBASE_SPECIFICATION.md).
  This section only adds the CPU mining history the mandate
  asks for; the audit files are the authority for v28.1.
- History in brief: the original client mined on CPU inside
  the node itself (the v0.1.3 miner is reconstructed in
  research/phase001/: BitcoinMiner in src/main.cpp, no
  midstate reuse, nonce 0 never hashed). CPU mining left the
  reference client as external miners took over (getwork,
  then getblocktemplate in BIP 22/23). In v28.1 the only
  in-tree nonce loop is the regtest GenerateBlock path
  (src/rpc/mining.cpp); production header hashing is
  CBlockHeader::GetHash through CSHA256 with runtime
  SHA256AutoDetect (scalar, SSE4, AVX2, SHA-NI D64 variants),
  and the D64 machinery is used in production only by the
  Merkle tree, never for header hashing (see the Core audit).
- Useful today: the exact template, coinbase and submission
  semantics NOVA already codes against (EXP-034, EXP-036);
  the GBT template caching rule (rebuild on new tip or a
  mempool change older than 5 seconds, nTime refreshed
  between rebuilds) is the reference behaviour for NOVA's
  template engine.
- New since the audit, found via ckpool (section 3.18):
  current Core offers a multiprocess mining IPC interface
  (Cap'n Proto) that template consumers can prefer over GBT.
  NOVA pins Core 28.1 bitcoind, which does not expose it.
  Carried to the opportunity register as a new item.
- Licence: MIT (Core's COPYING). Reproduction requirements:
  none for reading; NOVA treats Core as the consensus
  reference and never copies its mining code.

## 3.1 jgarzik/cpuminer (Garzik cpuminer, "minerd")

- URL and identity: github.com/jgarzik/cpuminer, Jeff
  Garzik's multi-threaded CPU miner, the first widely used
  external CPU miner (2010 to 2011 era). HEAD studied:
  04b9224d (tip of the archived master).
- Relevant source paths: cpu-miner.c (miner, work fetch,
  submission), miner.h, sha256_generic.c (portable C),
  sha256_4way.c (tcatm's 4-way SSE2), sha256_sse2_amd64.c,
  sha256_via.c (VIA Padlock), sha256_cryptopp.c, util.c
  (JSON-RPC, fulltest lives in the util lineage).
- Exact functions and algorithms: work arrives by the
  getwork RPC and INCLUDES a server-computed midstate
  (work->midstate parsed from JSON in cpu-miner.c, struct
  work field midstate[32]); the scan functions receive
  (midstate, data + 64) and hash only the second chunk plus
  the outer hash: scanhash_c (sha256_generic.c),
  scanhash_sse2_64, ScanHash_4WaySSE2 (sha256_4way.c,
  DoubleBlockSHA256 over NPAR interleaved lanes),
  scanhash_via, scanhash_cryptopp, scanhash_asm32. Backend
  chosen at runtime from a CPU capability option. Long
  polling thread plus a work_restart flag array
  (restart_threads() sets work_restart[i].restart = 1) so
  search threads abandon stale work between spans.
- What it does: getwork-era pooled and solo CPU mining with
  pluggable SHA-256 backends behind one scanhash signature.
- Useful today: the backend seam itself (one scanhash
  interface, many implementations, runtime selection) is
  exactly NOVA's gpu/engine.py ComputeEngine dispatch shape,
  and the per-thread restart flag is the ancestor of every
  stale-work mechanism since.
- Obsolete: getwork itself (removed from Core), server-side
  midstate delivery (modern templates make the client build
  the whole header), the Crypto++ and VIA backends.
- Hardware-specific: SSE2 and Padlock assembly paths.
- CPU-adaptable: already CPU; the transferable content is
  architectural, and NOVA has it (EXP-028, EXP-039 dispatch).
- Agent architecture value: low beyond the seam and the
  restart flag pattern, both already in NOVA.
- Throughput value: none directly; its fastest backend is
  roughly two orders of magnitude below the production
  v512dual path.
- Cannot transfer: getwork work format and its trust model
  (the server precomputed the midstate; the miner never saw
  the full header, so it could not verify its own work).
- Licence: GPLv2 (COPYING). The 4-way file carries a Satoshi
  MIT header comment from its Bitcoin source origin, but the
  repository licence is GPLv2; treat the repo as GPLv2.
- Reproduction or testing: builds with autotools against
  libcurl and jansson; not needed for NOVA, reading only.

## 3.2 pooler/cpuminer (Pooler's cpuminer, the maintained fork)

- URL and identity: github.com/pooler/cpuminer, Poolers
  fork of Garzik's miner, maintained for years as the
  reference CPU miner and the origin of the cpuminer-multi
  lineage. HEAD studied: 5f021059.
- Relevant source paths: cpu-miner.c (GBT client, coinbase
  construction, submission), sha2.c (the SHA-256d scan
  family), sha2-x64.S and siblings, scrypt.c, util.c
  (fulltest at util.c:839).
- Exact functions and algorithms: this is the first miner in
  the set that builds its own work from getblocktemplate:
  gbt_work_decode parses height, version, previousblockhash,
  curtime, bits, transactions, coinbaseaux and coinbasevalue,
  builds the coinbase (with a configurable coinbase_sig),
  computes the Merkle root, and assembles the 80-byte header
  client-side. GBT long polling via longpollid and
  longpolluri. The scan core, scanhash_sha256d (sha2.c:587),
  is a compact catalogue of exact optimisations: it computes
  the chunk-1 midstate itself (sha256_transform over the
  first 64 bytes), precomputes a "prehash" of the
  nonce-independent prefix of chunk 2 (sha256d_prehash over
  pdata + 16), pre-extends the message schedule
  (sha256d_preextend), then iterates sha256d_ms per nonce.
  A cheap first-word screen (swab32(hash[7]) <= Htarg) gates
  the exact fulltest(hash, ptarget) 256-bit comparison.
  Wider variants scanhash_sha256d_4way and
  scanhash_sha256d_8way (AVX and AVX2 era) are selected by
  sha256_use_4way() and sha256_use_8way() CPU probes.
- What it does: full GBT CPU mining, solo or pooled, plus
  scrypt; the direct ancestor of NOVA's own GBT path shape.
- Useful today: gbt_work_decode is the historical proof that
  client-side template construction is the correct split;
  the prehash and preextend functions are the same exact
  amortisations NOVA proved independently (midstate plus
  chunk-2 prefix: registry H-03, EXP-023 family; schedule
  pre-extension: EXP-016 delta analysis).
- Obsolete: scrypt support (out of scope), the getwork
  fallback path, 32-bit assembly variants.
- Hardware-specific: the .S schedule implementations.
- CPU-adaptable: it is the CPU reference; nothing to port.
- Agent architecture value: the workio thread split (one IO
  thread fetching and submitting, N scan threads, a shared
  g_work under g_work_lock with work_copy) is the same
  producer and consumer discipline NOVA's autopilot and
  engine use.
- Throughput value: none beyond confirming NOVA's
  amortisation set is complete at this level; its 8-way AVX2
  batch is the class EXP-032 and EXP-039 measured and
  integrated properly (pooled 1.409x and 1.252x over
  production C in their respective campaigns).
- Cannot transfer: its nonce partitioning (contiguous ranges
  per thread from a shared counter, no identity or lease
  discipline) is weaker than EXP-029 and EXP-035 and must
  not be copied.
- Licence: GPLv2 (COPYING).
- Reproduction or testing: autotools build; the sha2.c scan
  functions are self-contained and could be differential
  tested, but NOVA already exceeds them; reading only.


## 3.3 m0mchil/poclbm (the original poclbm)

- URL and identity: github.com/m0mchil/poclbm, m0mchil's
  PyOpenCL bitcoin miner (2011), the first widely used GPU
  miner and the origin of the phatk kernel family. HEAD
  studied: 2ae15b77 (April 2013).
- Relevant source paths: poclbm.py (entry, pool list),
  OpenCLMiner.py (device loop), Miner.py (base class, rate
  accounting), GetworkSource.py, StratumSource.py,
  Switch.py (pool switching), phatk.cl (the kernel),
  sha256.py (a pure Python SHA-256 used for verification
  and fallback).
- Exact functions and algorithms: the OpenCL kernel
  `search` in phatk.cl receives the precomputed first-chunk
  state words as scalar kernel arguments (state0 and
  following) and each work item derives its nonce from its
  global id plus a base; the host side runs
  OpenCLMiner.mining_thread with nonce_generator handing out
  nonce blocks, load_kernel compiling phatk with vector
  width defines, and patch(data) fixing up work. Results
  come back as candidate nonces only, which the host
  re-verifies in Python before submission. Pool behaviour
  is explicit policy: multiple servers, a tolerance of N
  consecutive connection errors before using a fallback, and
  a failback timer that retries the primary pool.
- What it does: getwork and early Stratum GPU mining with
  host-side verification of device candidates.
- Useful today: two durable patterns. First, the device
  returns candidates only, never bulk digests: the same
  data-movement discipline as NOVA's mask-first search
  (H-04, EXP-024, EXP-026). Second, pool failover as a
  written policy (tolerance count plus failback interval),
  which NOVA's single-endpoint pool leg does not yet have
  as a policy object; carried to the register as NEW.
- Obsolete: getwork source, OpenCL 1.x assumptions, the
  Python host loop as a performance path.
- Hardware-specific: phatk.cl is tuned for AMD VLIW GPUs of
  2011; nothing in it runs on a CPU competitively.
- CPU-adaptable: the kernel's state-as-arguments trick is
  the GPU form of passing a midstate; NOVA's kernels take
  the midstate the same way.
- Agent architecture value: the Switch and tolerance policy
  is a small, complete example of an endpoint health policy
  an agent can reason about and tune.
- Throughput value: none for CPU.
- Cannot transfer: the kernel itself, and its habit of
  trusting pool-supplied work without template identity.
- Licence: the LICENSE file states "public domain".
- Reproduction or testing: needs PyOpenCL and a GPU of the
  era; reading only.

## 3.4 Kiv/poclbm (GUIMiner)

- URL and identity: github.com/Kiv/poclbm. Verified identity
  (see honesty notes): this is GUIMiner by Chris 'Kiv'
  MacLeod, a fork of m0mchil's poclbm adding a wxPython GUI,
  preset pool lists and bundled miner backends (it also
  wraps puddinpop's rpcminer and the ufasoft miner). HEAD
  studied: 5c6b314b (January 2014).
- Relevant source paths: guiminer.py (GUI and orchestration),
  and the inherited poclbm files (Miner.py, OpenCLMiner.py,
  GetworkSource.py, StratumSource.py, phatk.cl at the same
  paths as section 3.3, with local modifications).
- Exact functions and algorithms: no new mining algorithm;
  the deltas over 3.3 are the GUI, per-pool presets, summary
  statistics presentation and small fixes to the inherited
  files (file-by-file diff against the m0mchil clone shows
  every shared file differs, none structurally).
- What it does: makes pooled GPU and CPU mining usable by
  non-technical operators.
- Useful today: one lesson only, and it is for the agent
  layer: GUIMiner won adoption by shipping curated,
  known-good configuration (pool presets) instead of raw
  options. The NOVA analogue is curated, validated endpoint
  and backend profiles rather than free-form configuration.
- Obsolete: the GUI stack and the preset pool list itself.
- Hardware-specific: nothing new.
- CPU-adaptable: nothing new over 3.3.
- Agent architecture value: the preset idea, recorded in
  the register as part of the endpoint profile item.
- Throughput value: none.
- Cannot transfer: the code (a fork with mixed provenance)
  and the preset list (dead pools).
- Licence: LICENSE.txt in the clone is GPLv3, which differs
  from the upstream poclbm public-domain statement; the
  fork's licensing is internally inconsistent, a further
  reason to treat it as read-only reference.
- Reproduction or testing: none appropriate; reading only.

## 3.5 Diablo-D3/DiabloMiner (DiabloMiner)

- URL and identity: github.com/Diablo-D3/DiabloMiner,
  Patrick McFarland's Java OpenCL miner (2010 to 2013), one
  of the two original GPU miners. HEAD studied: 822e17e6;
  the README at HEAD states the program is unmaintained and
  does not support the current miner protocol.
- Relevant source paths: src/main/java/com/diablominer/
  DiabloMiner/DiabloMiner.java (entry and execution),
  NetworkState/JSONRPCNetworkState.java and WorkState.java
  (work acquisition), DeviceState/ (device abstraction),
  src/main/resources/DiabloMiner.cl (kernel).
- Exact functions and algorithms: a Java host drives JOCL;
  WorkState holds the current work unit and its age;
  JSONRPCNetworkState performs getwork with long polling
  and swaps WorkState atomically on new work; the kernel
  takes the precomputed state the same way phatk does.
  Devices are modelled behind HardwareType and DeviceState
  classes, an early device-abstraction layer.
- What it does: cross-platform GPU mining in the getwork
  era, notable for running anywhere Java and OpenCL ran.
- Useful today: the clean split between NetworkState (work
  supply), WorkState (the unit and its freshness) and
  DeviceState (execution) is the same three-way split NOVA
  uses between endpoint, template engine and backend.
- Obsolete: getwork, JOCL, the kernel.
- Hardware-specific: the OpenCL kernel and its AMD tuning.
- CPU-adaptable: nothing computational.
- Agent architecture value: the state-class separation is a
  tidy reference for interface boundaries; already reflected
  in NOVA's module split.
- Throughput value: none.
- Cannot transfer: everything protocol and kernel side.
- Licence: GPLv3 (LICENSE).
- Reproduction or testing: Maven build, era OpenCL; reading
  only.

## 3.6 jedi95/Phoenix-Miner (Phoenix)

- URL and identity: github.com/jedi95/Phoenix-Miner, the
  Phoenix miner by jedi95 and CFSworks (2011 to 2012), a
  poclbm descendant known for its work-queue design and the
  phatk2 kernel. HEAD studied: ec8af03c (January 2012).
  Not to be confused with the later, unrelated Ethereum
  miner of the same name.
- Relevant source paths: WorkQueue.py (WorkUnit, NonceRange,
  WorkQueue), Miner.py (connection and failover logic),
  KernelInterface.py, kernels/phatk, kernels/phatk2,
  kernels/poclbm, phoenix.py (entry; MIT licence header).
- Exact functions and algorithms: WorkQueue.getRangeFromUnit
  and fetchRange hand each device a NonceRange (unit, base,
  size; default fetch size 0x10000) cut from a WorkUnit;
  isRangeStale rejects ranges whose unit has been superseded;
  Miner implements connection callbacks (onWork, onLongpoll,
  onBlock) and a failoverCheck loop over multiple servers;
  X-Roll-Ntime support extends a unit's life by rolling the
  timestamp instead of refetching.
- What it does: pooled GPU mining with explicit range
  allocation and staleness discipline, the clearest early
  statement of both.
- Useful today: NonceRange is the direct ancestor of the
  lease objects in EXP-029 and EXP-035; its staleness rule
  (a range dies with its unit) is the rule EXP-034 and
  EXP-038 express through template identity. Both already
  covered in NOVA, at higher rigour.
- Obsolete: the Twisted-based networking as a model, the
  kernels, getwork-era work units.
- Hardware-specific: phatk and phatk2 kernels.
- CPU-adaptable: the range allocator concept only; covered.
- Agent architecture value: fetchRange sizing (how much work
  to stage per device) is a tunable the agent layer can own;
  NOVA treats span sizing under H-05 and H-14.
- Throughput value: none directly.
- Cannot transfer: kernel code and the assumption that a
  range, once handed out, needs no completion accounting
  (NOVA's EXP-038 frontier exists precisely because ranges
  need crash-honest accounting).
- Licence: MIT, stated in the header of phoenix.py and
  Miner.py; there is no separate LICENSE file in the clone.
- Reproduction or testing: Python 2 era code; reading only.

## 3.7 ckolivas/cgminer (cgminer, Con Kolivas)

- URL and identity: github.com/ckolivas/cgminer, Con
  Kolivas's cgminer, the dominant miner of the GPU, FPGA
  and early ASIC eras and the architectural template for
  almost everything after it. Version at HEAD: 4.11.1
  (configure.ac), HEAD b8491c66 (December 2018); by then it
  is an ASIC-only miner, the CPU and GPU code having been
  removed in the 4.x line.
- Relevant source paths: cgminer.c (core: work queues,
  stratum, pool strategies, watchdog), miner.h (struct work,
  enum pool_strategy at miner.h:298), api.c (the monitoring
  and control API), driver-*.c (about 30 device drivers,
  including driver-icarus.c, driver-blockerupter.c,
  driver-avalon*.c, driver-bitmain.c), util.c.
- Exact functions and algorithms: work is a struct work with
  a staged queue; stale_work() decides share and work
  staleness, opt_submit_stale controls whether stale shares
  are submitted at all; work expiry combines rolltime and a
  maximum scan time (expiry taken as two thirds of the scan
  window). Pool management is a strategy enum: POOL_FAILOVER,
  POOL_ROTATE, POOL_LOADBALANCE, POOL_BALANCE (quota-based;
  a dead pool's quota is dropped until it is re-enabled, and
  all-zero quotas fall back to failover). The API (api.c)
  exposes read commands (summary, devs, pools) and marks
  mutating commands (restart, quit, switchpool, enablepool,
  save, hotplug) as privileged in its command table, a
  concrete read versus write privilege split enforced per
  command. A watchdog thread tracks device liveness
  (LIFE_DEAD state) and the miner re-initialises or retires
  sick devices. Stratum support includes extranonce
  subscription and version rolling (work->rolls).
- What it does: runs fleets of heterogeneous mining devices
  against multiple pools with health management, an operator
  API and hotplug; the operations layer is the product, the
  hashing having moved into the devices.
- Useful today: three operations patterns NOVA can still
  learn from. (1) The API privilege bit per command is a
  proven enforcement shape for the mandate's authority
  levels; NOVA's agent interface does not yet enforce
  privilege per operation at the transport. Register: NEW.
  (2) Quota-based allocation across endpoints (load balance
  with forward-looking quotas) generalises NOVA's binary
  pool versus solo endpoint choice. Register: NEW. (3) The
  watchdog's device liveness states (alive, sick, dead) map
  onto EXP-035 worker health, which has leases but not a
  named liveness ladder with automatic re-initialisation
  attempts; the ladder itself is covered by the EXP-035 and
  EXP-038 recovery design, the re-initialisation attempt
  policy is folded into the register's hotplug item.
- Obsolete: the device drivers as code (hardware gone), the
  curses UI, getwork support.
- Hardware-specific: all driver-*.c files, ADL and GPIO
  control, fan and voltage handling.
- CPU-adaptable: the operations layer is device-agnostic and
  is the adaptable part; nothing in the hash path is (this
  tree has no CPU hash path left).
- Agent architecture value: high. cgminer is the proof that
  a miner's durable value migrates to its operations layer:
  health, allocation, API, recovery. That is precisely the
  layer the Master Build Mandate asks the NOVA agent to be.
- Throughput value: indirect only, through allocation and
  uptime, never through hashing.
- Cannot transfer: driver code, the assumption of trusted
  local devices (fleet workers in NOVA are not trusted;
  EXP-036 verification exists because of that difference),
  and float difficulty accounting in its statistics
  (total_diff_accepted and friends), which NOVA forbids as
  an authority (EXP-036, matrix M03).
- Licence: GPLv3 (COPYING).
- Reproduction or testing: builds with autotools; device
  paths cannot be exercised without the hardware; reading
  only.

## 3.8 kanoi/cgminer (Kano's cgminer fork)

- URL and identity: github.com/kanoi/cgminer, Kano's fork of
  cgminer, still maintained (HEAD d689d3a9 is a 2026 commit
  for GekkoScience devices). Version at HEAD: 4.13.6.
- Relevant source paths: same layout as 3.7; a file-level
  diff against the ckolivas clone shows the core files
  (cgminer.c, api.c, driver set) all carry fork changes,
  concentrated in device support (GekkoScience Compac and
  R606, Bitfury) and in pool and API fixes.
- Exact functions and algorithms: no new mining algorithm;
  the fork's content is continued maintenance: newer device
  drivers, protocol fixes, and the same strategy, API and
  watchdog architecture as 3.7.
- What it does: keeps the cgminer operations architecture
  alive for current small USB ASICs.
- Useful today: evidence that the 3.7 operations patterns
  are stable enough to maintain for a further decade; no
  additional transferable mechanism over 3.7 was found.
- Obsolete, hardware-specific, CPU-adaptable, throughput:
  as 3.7.
- Agent architecture value: maintenance posture only: a
  single-maintainer fork that tracks protocol reality is
  the model for keeping NOVA's stratum client current.
- Cannot transfer: as 3.7.
- Licence: GPLv3 (COPYING).
- Reproduction or testing: as 3.7; reading only.

## 3.9 luke-jr/bfgminer (BFGMiner)

- URL and identity: github.com/luke-jr/bfgminer, Luke
  Dashjr's BFGMiner 5.5.0 (configure.ac; HEAD 866fd36f,
  October 2021), the other great operations-layer miner,
  forked from cgminer in 2012 and developed independently
  since, with a modular driver and processor model.
- Relevant source paths: miner.c (core, stratum server
  state), driver-cpu.c (cpu_scanhash at driver-cpu.c:809),
  driver-icarus.c, driver-ztex.c and libztex.c,
  driver-erupter.c, driver-stratum.c, driver-getwork.c,
  work2d.c (two-dimensional work: work split across devices
  and processors), api.c and the RPC protocol documented in
  README.RPC.
- Exact functions and algorithms: three things stand out.
  (1) CPU mining survives here as a first-class driver, and
  its algorithm selection is a startup MEASUREMENT:
  README.CPU documents --algo auto and fastauto, which
  benchmark the candidate SHA-256 implementations at
  startup and pick the fastest that works (the candidate
  list is the cpuminer lineage: c, 4way, via, cryptopp,
  sse2_32, sse2_64, sse4_64). (2) BFGMiner can itself act as
  a stratum server and proxy (driver-stratum.c, a stratum
  server port, and a stratum_share hash table in miner.c
  tracking submitted shares until the pool answers, which
  is duplicate and unmatched-share bookkeeping). (3) The
  device model splits devices into processors, and work2d
  allocates a work unit across processors, with drivers like
  Icarus routing a returned nonce to its owning processor
  (icarus_proc_for_nonce, driver-icarus.c).
- What it does: heterogeneous device mining with the most
  complete protocol surface of the era (GBT, getwork,
  stratum client, stratum server, proxy) behind one driver
  API.
- Useful today: the startup bake-off is a genuinely
  different selection rule from NOVA's CPUID-probe dispatch:
  NOVA proves tiers offline under EXP-017 and dispatches by
  feature flags (EXP-039); BFGMiner measures on the actual
  machine at first start. On a VM whose host alternates
  between AMD and Intel parts (EXP-031, EXP-039 note N-1),
  a short measured selection, cached into the host
  capability profile, would close the refusal-behaviour gap
  empirically. Register: NEW, highest CPU-side value in this
  study. The stratum-server mode is the ancestor of the
  ckproxy aggregation idea (section 3.18).
- Obsolete: getwork driver, OpenCL driver for modern use,
  scrypt and altcoin drivers (out of scope).
- Hardware-specific: the device drivers other than
  driver-cpu.c.
- CPU-adaptable: driver-cpu.c's selection policy, not its
  kernels (all pre-AVX2 era).
- Agent architecture value: the processor abstraction (a
  device is a set of independently schedulable processors)
  is a cleaner fleet unit than a whole worker; EXP-035
  leases already treat sub-worker spaces, so this is
  confirmatory.
- Throughput value: the bake-off protects throughput on
  unfamiliar hosts; it does not raise the ceiling.
- Cannot transfer: the kernels, and the proxy's trust model
  (it relays pool work without template identity checks).
- Licence: GPLv3 (COPYING).
- Reproduction or testing: autotools build; CPU driver could
  be built, but its benchmark methodology is what transfers,
  not the binary; reading only.


## 3.10 fpgaminer/Open-Source-FPGA-Bitcoin-Miner

- URL and identity: github.com/fpgaminer/
  Open-Source-FPGA-Bitcoin-Miner, fpgaminer's 2011 project,
  the first open FPGA miner (about 109 MH/s on a Terasic
  DE2-115 in the README's configuration). HEAD studied:
  72a5e183.
- Relevant source paths: src/fpgaminer_top.v (top level:
  work register, nonce counter, result output),
  src/sha256_transform.v and src/sha-256-functions.v (the
  compression core), src/uart_comm.v (host link),
  cores/unoptimized/ (a second, simpler core), projects/
  (per-board builds, including the ZTEX merge project
  X5000_ztexmerge and X6000_ztex_comm4).
- Exact functions and algorithms: the transform core is a
  fully unrolled, pipelined SHA-256: one round per pipeline
  stage, the message schedule computed ahead of the state
  path, two transforms chained for SHA-256d with the
  midstate loaded from the host. The host sends the midstate
  and the chunk-2 tail; the board sweeps the nonce in
  hardware and returns winning nonces over UART.
- What it does: fixed-function pipelined hashing with a
  minimal host protocol: work in, nonces out.
- Useful today: the discipline of the boundary (the device
  holds no template logic; the host owns work construction
  and verification) is the same boundary NOVA keeps between
  engine and backend. The pipelining itself is the hardware
  form of latency hiding that EXP-003 and EXP-011 pursue in
  SIMD by interleaving independent streams.
- Obsolete: the boards, the UART protocol, the Namecoin
  support.
- Hardware-specific: everything in the tree; it is Verilog.
- CPU-adaptable: only the abstract point that independent
  nonce lanes hide round latency, which NOVA's multi-buffer
  kernels already embody (EXP-011, EXP-026).
- Agent architecture value: none beyond the boundary rule.
- Throughput value: none for CPU software; NOVA's own FPGA
  aspect (RTL simulation, Yosys synthesis) already covers
  this ground and is further along.
- Cannot transfer: the unrolled pipeline as a mechanism;
  CPUs cannot spend area on 64 physical round units, and
  the EXP-027 and EXP-033 closures bound what restructuring
  can win in software.
- Licence: GPLv3 (LICENSE.txt).
- Reproduction or testing: needs FPGA toolchains and boards;
  reading only.

## 3.11 Icarus, ZTEX and Block Erupter (through cgminer and BFGMiner drivers)

- Identity: none of the three has a standalone official
  miner repository in the studied set; their protocol
  implementations live in the cgminer and BFGMiner driver
  files, which is where this study reads them. Icarus was a
  2012 FPGA board (ngzhang); ZTEX was a line of FPGA boards
  from ZTEX GmbH whose miner firmware was distributed with
  the cgminer and BFGMiner ecosystem; Block Erupter was
  ASICMiner's USB ASIC line (Friedcat), the first USB ASIC
  miners.
- Icarus (ckolivas-cgminer/driver-icarus.c, bfgminer/
  driver-icarus.c): the work packet is the midstate plus
  the chunk-2 tail (ICARUS_WORK_DATA_OFFSET 64 in a
  76-plus byte packet); the board returns a 32-bit nonce;
  a per-revision nonce_mask (0x7fffffff or 0xffffffff in
  driver-icarus.c) records that some revisions only sweep
  part of the nonce space, so coverage accounting must be
  per-device, not assumed. BFGMiner's version routes the
  returned nonce to the owning processor
  (icarus_proc_for_nonce). Transferable: coverage claims
  must come from what a worker actually sweeps, a rule
  EXP-035 and EXP-038 already enforce through frontiers;
  and partial-range workers are a real historical case, not
  an edge case.
- ZTEX (bfgminer/driver-ztex.c and libztex.c): notably,
  the ckolivas cgminer HEAD tree contains NO ZTEX files at
  all; support survived in BFGMiner. libztex discovers
  boards over USB, uploads the FPGA firmware image to the
  board at startup (the miner carries the bitstream), reads
  per-board capabilities and clock limits, and submits work
  per board with per-board error counting. Transferable:
  the worker carries and provisions its own execution
  image and reports capabilities before receiving work,
  the same shape as NOVA's backend self-test and capability
  profile at worker start (EXP-031, EXP-039); the
  provisioning half (pushing the image) is what a fleet
  update mechanism would need, see the register's signed
  update item.
- Block Erupter (ckolivas-cgminer/driver-blockerupter.c,
  bfgminer/driver-erupter.c): in ckolivas cgminer the
  driver is disabled by default and its configure help
  literally calls it a "BROKEN DRIVER"; BFGMiner's
  driver-erupter.c is the maintained one. The device is a
  fixed-protocol USB ASIC: work in, nonce out, minimal
  state. Transferable: an honest negative lesson: a driver
  shipped but known-broken and off by default is worse than
  no driver; NOVA's fail-closed backend discipline
  (self-test or refusal, EXP-039) is the correct opposite.
- Licences: the driver files inherit their host projects'
  GPLv3. ZTEX's original firmware distribution terms could
  not be verified from these clones; only the BFGMiner-side
  code was read.
- What could not be verified: no official standalone
  repositories or licences for Icarus or ZTEX miner
  software were found inside the studied clones; claims
  beyond the driver sources would be speculation.

## 3.12 Canaan-Creative/Avalon-extras

- URL and identity: github.com/Canaan-Creative/Avalon-extras,
  Canaan's official extras repository for the Avalon line
  (the first commercial ASIC miners, 2013 onward). HEAD
  studied: 704b47ed.
- Relevant source paths: this is NOT a miner. It contains
  cgminer-patches/ (the Avalon driver as patches against
  cgminer 3.8 and 4.3 era trees; the driver itself later
  landed upstream as cgminer's driver-avalon*.c, present in
  the 3.7 clone), farm-manager/ (a Raspberry Pi based farm
  status and management stack: status-report, www, utils),
  scripts/ (per-generation build, factory and reflash
  scripts for Avalon 1 through 8), openwrt-patches/, and
  test-data/.
- Exact functions and algorithms: no hashing code. The
  transferable content is operational: factory test and
  reflash automation per hardware generation, and a farm
  manager that collects per-device status reports into a
  web view.
- What it does: everything around the miner: manufacturing,
  provisioning, fleet status.
- Useful today: the farm-manager pattern (each device emits
  a structured status report; a collector renders fleet
  health) is the pattern EXP-037 statistics and the NOVA
  dashboard implement; already covered. The per-generation
  provisioning scripts reinforce the ZTEX observation in
  3.11: provisioning is part of the mining system, not an
  afterthought.
- Obsolete: the OpenWrt patches and the device generations.
- Hardware-specific: nearly everything.
- CPU-adaptable: nothing computational.
- Agent architecture value: fleet status collection shape;
  covered by EXP-037.
- Throughput value: none.
- Cannot transfer: the patches (superseded upstream) and
  the factory flows (no factory exists here).
- Licence: UNLICENSE (public domain dedication) at the
  root; individual subdirectories may vary and were not all
  audited.
- Reproduction or testing: none appropriate; reading only.

## 3.13 Bitmain bmminer (via bitmaintech/bmminer-mix, labelled successor source)

- Identity: see honesty note 1. The mandate's URL,
  github.com/bitmaintech/bmminer, is not publicly clonable
  today. The source read is github.com/bitmaintech/
  bmminer-mix, HEAD 7aebcf2c (October 2019), which Bitmain's
  own blog names as the published source for the Antminer
  S9, T9 and R4 miner software. Findings below are from
  bmminer-mix and are labelled as such.
- Relevant source paths: cgminer.c (a cgminer 4.9-era fork
  at the core), driver-btm-c5.c (the Bitmain driver;
  bitmain_scanhash is the job dispatch thread function,
  bitmain_api_stats exposes per-chain statistics through
  the cgminer API), clement-bitmain.c, A1-*.h (board
  selection inherited from the Bitmine A1 lineage).
- Exact functions and algorithms: bmminer is cgminer with
  the device layer replaced by Bitmain chain boards: jobs
  are broadcast to chains, each chain's ASICs sweep a nonce
  partition, and results return with chain and chip
  identity, so error rates are attributable per chip. The
  operations surface is cgminer's (API, watchdog, pool
  strategies) plus Bitmain's frequency and voltage handling.
- What it does: runs an Antminer; historically important
  because its 2016 issue tracker is where the Antbleed
  backdoor was reported and because its covert AsicBoost
  support drove the BIP 320 version-rolling standardisation
  that NOVA's combined search space (EXP-034, EXP-035,
  matrix M34) now treats as a first-class dimension.
- Useful today: per-chip error attribution is the ASIC form
  of per-worker telemetry granularity (matrix M28); covered.
  The version-rolling history is already NOVA doctrine.
- Obsolete: the fork as a codebase (superseded by later
  Antminer firmware).
- Hardware-specific: the entire driver and board layer.
- CPU-adaptable: nothing computational.
- Agent architecture value: a security lesson with direct
  agent relevance: a miner that accepts unauthenticated
  remote control (Antbleed was an unauthenticated shutdown
  endpoint in the firmware lineage) is an agent-safety
  failure; NOVA's authority levels and the register's
  privileged-API item exist to prevent the same class.
- Throughput value: none for CPU.
- Cannot transfer: driver code, AsicBoost in its covert
  form (the overt, BIP 320 form is what NOVA models).
- Licence: GPLv3 (COPYING in bmminer-mix).
- Reproduction or testing: needs Antminer hardware; reading
  only.

## 3.14 Braiins OS (via labelled fork mirror and braiins/bmminer)

- Identity: see honesty note 2. The mandate's URL,
  github.com/braiins/braiins-os, is not publicly clonable
  today. Read instead: (a) DavHau/braiins-os, a public fork
  whose HEAD (572dd48c, February 2019) is a Braiins release
  commit; (b) braiins/bmminer (HEAD 93ad6af5, June 2019),
  the Braiins organisation's own miner fork. Braiins OS is
  the alternative Antminer firmware from the Slush Pool
  team, built on OpenWrt; its later miner, BOSminer, is a
  from-scratch Rust stratum client, and the autotuning
  Braiins OS+ product is partly proprietary. Neither of
  those later components is in the studied trees, and no
  claim is made about their internals.
- Relevant source paths (fork mirror): bb.py (the Braiins
  build system extending OpenWrt's), configs/default.yml
  (which pulls the organisation's cgminer and bmminer
  packages), package/mining/ (bmminer, cgminer,
  cgminer_monitor, miner_tools packages), keys/ (release
  signing keys, test and test.pub in the fork), upgrade/
  and build-release.sh (release and upgrade machinery),
  docs/ (developer guide). In braiins/bmminer: fancontrol.c
  (a PID fan controller: PID_KP, PID_KI, PID_KD constants,
  duty limits, a warmup floor), construct.c, and the
  cgminer core.
- Exact functions and algorithms: two mechanisms matter.
  (1) Signed, versioned firmware releases with a feed
  server: bb.py builds per-target images, signs releases
  with the project key, and devices upgrade from the feed;
  the release process is code, not a manual ritual.
  (2) Closed-loop thermal control: fancontrol.c runs a PID
  loop on temperature error instead of threshold steps.
- What it does: replaces the whole miner software stack
  (OS, miner, monitoring, updates) as one managed product.
- Useful today: (1) maps to NOVA's weakest operational
  point: the autopilot self-update path is inert on this
  VM (no git checkout), and a fleet will need exactly
  Braiins' pattern: signed manifests, a feed, per-target
  builds, staged rollout. Register: NEW. (2) The PID loop
  is the control-theory form of the load-ramping that
  matrix M21 flagged as Investigate; a PID controller on a
  measurable error signal (steal time, share interval
  error) for worker count and span control was not itself
  studied in NOVA. Register: NEW, linked to M21.
- Obsolete: the S9-era target support and the OpenWrt
  versions in the fork.
- Hardware-specific: fan control as such, NAND and SD
  layouts, the board targets.
- CPU-adaptable: the update chain and the control loop
  shape; nothing computational.
- Agent architecture value: high for operations: Braiins OS
  is the clearest proof that mining software is a managed
  fleet product (provisioning, signing, telemetry, remote
  operation), which is the mandate's direction for the
  agent layer.
- Throughput value: autotuning is the famous Braiins OS+
  feature, but it is not in the studied source and no
  throughput claim is made from it.
- Cannot transfer: the proprietary autotuner (not studied,
  not available), the hardware control loops as code.
- Licences: GPLv3 (LICENSE in the fork mirror; COPYING in
  braiins/bmminer).
- Reproduction or testing: building the firmware needs the
  OpenWrt toolchain and target hardware; reading only.

## 3.15 sgminer-dev/sgminer (sgminer)

- URL and identity: github.com/sgminer-dev/sgminer, the
  community fork of cgminer that kept GPU mining alive for
  altcoins after cgminer dropped GPUs. Version at HEAD:
  5.1.1 (configure.ac), HEAD 8bf1c180 (July 2015).
- Relevant source paths: algorithm/ (per-algorithm kernel
  and setup files: darkcoin, fresh, fuguecoin and more),
  algorithm.c and algorithm.h (the algorithm registry),
  plus the inherited cgminer core (api.c, adl.c, driver
  files).
- Exact functions and algorithms: sgminer's one structural
  idea is a runtime algorithm registry: each algorithm
  registers its kernel, its work construction quirks and
  its scan function, and pools can switch algorithms per
  connection. The SHA-256d path is inherited cgminer.
- What it does: multi-algorithm GPU mining.
- Useful today: almost nothing for NOVA, by design: the
  mandate fixes exact SHA-256d only, so a pluggable hash
  algorithm registry contradicts scope. Recorded here so
  the register can state that exclusion explicitly rather
  than rediscover it.
- Obsolete: the altcoin kernels (several are for dead
  coins), ADL support.
- Hardware-specific: all kernels.
- CPU-adaptable: nothing.
- Agent architecture value: a negative reference: generality
  NOVA must not buy.
- Throughput value: none.
- Cannot transfer: the registry idea itself (out of scope),
  all kernels.
- Licence: GPLv3 (COPYING).
- Reproduction or testing: reading only.

## 3.16 tpruvot/ccminer and cbuchner1/CudaMiner (the CUDA miners)

- URLs and identity: github.com/tpruvot/ccminer (Tanguy
  Pruvot's ccminer, version 2.3.1 at HEAD 6ff4e509, January
  2019) and github.com/cbuchner1/CudaMiner (Christian
  Buchner's CudaMiner, HEAD 746a7733, April 2014, the
  original CUDA miner, scrypt-focused in its later life).
- Relevant source paths: ccminer.cpp (work loop, stratum,
  API; scanhash_sha256d dispatch and an explicit --benchmark
  offline mode), cuda_checkhash.cu and the per-architecture
  kernel files in ccminer; sha256.cu and the per-generation
  kernel families (fermi_kernel.cu, kepler_kernel.cu,
  nv_kernel.cu, salsa_kernel.cu for scrypt) in CudaMiner.
- Exact functions and algorithms: both are cgminer-lineage
  hosts driving CUDA kernels per GPU generation, with
  kernel autotuning of launch configuration in CudaMiner's
  lineage and a first-class offline benchmark mode in
  ccminer (opt_benchmark: run the real scan path against a
  fixed work unit with no pool).
- What they do: NVIDIA GPU mining; for SHA-256d they are a
  footnote (both ecosystems centred on scrypt and later
  altcoins), which is itself a finding: after 2013, open
  mining development followed altcoins, and SHA-256d
  innovation moved into closed ASIC firmware.
- Useful today: one operational idea: a production binary
  with a built-in offline benchmark mode. NOVA's benchmarks
  live in research harnesses (EXP-017, EXP-040); after every
  VM replacement the host changes, and a one-command
  production-path benchmark would profile the new host
  immediately. Register: NEW.
- Obsolete: the kernels for modern purposes, the altcoin
  support.
- Hardware-specific: all CUDA code; NOVA has no GPU and the
  mandate forbids adding a GPU dependency.
- CPU-adaptable: the benchmark mode concept only.
- Agent architecture value: autotuning's measurement loop
  (try configurations, keep the fastest measured) is the
  GPU form of the BFGMiner bake-off in 3.9; same register
  item.
- Throughput value: none for CPU.
- Cannot transfer: kernels, CUDA runtime assumptions.
- Licences: GPLv3 (ccminer LICENSE.txt; CudaMiner
  LICENSE.txt).
- Reproduction or testing: needs NVIDIA hardware; reading
  only.

## 3.17 stratum-mining/stratum (Stratum V2 reference implementation)

- URL and identity: github.com/stratum-mining/stratum, the
  Stratum protocol project's own repository. HEAD studied:
  2220f62d. Note the repository's current shape: it now
  holds the low-level crates only; the application-level
  roles moved to the companion sv2-apps repository, per its
  README.
- Relevant source paths: sv2/ subcrates: binary-sv2
  (binary codec), framing-sv2, codec-sv2, noise-sv2 (Noise
  protocol encryption), channels-sv2 (standard and extended
  channels), parsers-sv2, subprotocols/ (common-messages,
  mining, template-distribution, job-declaration);
  sv1/ (a Stratum V1 implementation); stratum-core/ with
  stratum-translation (the V1 to V2 translator utilities).
- Exact functions and algorithms: SV2 replaces JSON text
  with framed binary messages over an encrypted Noise
  channel; the mining subprotocol splits work into channels
  (a standard channel receives pool-built jobs with a
  precomputed Merkle root; an extended channel lets the
  miner roll its own extranonce); the template-distribution
  subprotocol streams block templates; the job-declaration
  subprotocol lets a miner propose a self-built template to
  the pool for approval, which is the protocol's answer to
  pool transaction censorship.
- What it does: defines and implements the successor to the
  Stratum V1 protocol NOVA's pool leg speaks today.
- Useful today: NOVA's position is already recorded:
  matrix M23 (support SV2 with Noise for external SV2
  pools: Investigate, sequenced after the V1 and Core
  paths) and M24 (the job model must accept precomputed
  root jobs as a distinct type: Adapt). Those stand. The
  piece the EXP-030 matrix did NOT cover is job
  declaration: miner-proposed templates are a different
  subprotocol with different trust and identity
  requirements from the mining channel. Register: NEW for
  job declaration; M23 and M24 items marked covered.
- Obsolete: nothing; this is the live protocol frontier.
- Hardware-specific: nothing.
- CPU-adaptable: protocol code is CPU-agnostic; a Rust
  dependency decision would be NOVA's, not this study's.
- Agent architecture value: template distribution as a
  stream (rather than polled GBT) changes the agent's job
  freshness model; see also the Core IPC item from ckpool
  in 3.18.
- Throughput value: lower per-message overhead than V1
  JSON; material only at fleet scale, not measured here
  and not claimed.
- Cannot transfer: nothing conceptually; implementation
  effort and the sv2-apps split are the real costs.
- Licences: dual Apache 2.0 and MIT (LICENSE-APACHE,
  LICENSE-MIT, LICENSE.md).
- Reproduction or testing: cargo workspace; interop testing
  would need an SV2 endpoint or the translator proxy;
  reading only here.

## 3.18 ckpool (ckolivas/ckpool, from Bitbucket)

- URL and identity: bitbucket.org/ckolivas/ckpool, Con
  Kolivas's pool software, cloned successfully from
  Bitbucket as instructed. HEAD studied: e05462e8 (November
  2026). Modes documented in its READMEs: pool, solo
  (README-SOLOMINING.md), passthrough, proxy and redirector
  (README-CKPOOL_MODES.md, README-CKPROXY.md).
- Relevant source paths: src/stratifier.c (work generation,
  share validation, per-worker difficulty), src/generator.c
  (template acquisition from the node), src/connector.c
  (client connections), src/bitcoin.c (node RPC), src/
  ckpool.c (process and mode management), src/sv2_bridge.c
  and sv2_*.c (a Stratum V2 bridge), src/sha2.c plus
  sha256_x86_shani.c and sha256_arm_shani.c (share checking
  hashes, the x86 file being the Bitcoin Core lineage
  implementation).
- Exact functions and algorithms: the stratifier builds
  workbases from templates, fans them out as stratum
  notifies, validates every submitted share by recomputing
  its hash exactly, tracks per-worker statistics, and
  adjusts each worker's difficulty toward a target share
  rate (vardiff). The generator prefers the node's fastest
  template source: per README-SOLOMINING.md, current
  ckpool prefers Bitcoin Core's multiprocess mining IPC
  interface for templates and new-block notification, with
  GBT as the fallback. Solo mode points the whole stack at
  one user's address; proxy and passthrough modes aggregate
  many downstream miners into few upstream connections.
- What it does: it is the server half of everything the
  miner sections above speak to, including a complete solo
  mining stack of exactly the kind NOVA's solo_server.py
  implements a small version of.
- Useful today: three items. (1) Vardiff toward a target
  share interval: the same control loop as matrix M10;
  NOVA's solo share difficulty is still fixed at 0.02, so
  this is covered as a decided design (M10) with the
  implementation still open, and ckpool's stratifier is
  the most complete open reference for it. (2) The proxy
  and passthrough aggregation tier: a fleet of NOVA workers
  would connect to one aggregation point that holds few
  upstream connections and keeps per-worker accounting;
  EXP-035 designed a coordinator, not a stratum-speaking
  aggregation tier. Register: NEW. (3) The Core mining IPC
  preference: push-based templates from a multiprocess
  Core instead of GBT polling and longpoll. NOVA runs
  bitcoind 28.1, which has no IPC interface; adopting it
  means a Core upgrade decision. Register: NEW, gated.
- Obsolete: the passthrough mode's original use case
  (rented hash rate aggregation) is not NOVA's; the
  mechanism still is.
- Hardware-specific: nothing.
- CPU-adaptable: the whole stack is CPU software.
- Agent architecture value: ckpool is the reference for
  what the coordinator's server side must do at scale:
  workbase lifecycle, share validation, per-worker
  difficulty, dead-workbase retirement. EXP-035 covers the
  lease logic; ckpool covers the stratum-facing half.
- Throughput value: none directly; it protects effective
  throughput by keeping work fresh and shares countable.
- Cannot transfer: its trust model for downstream miners
  is a pool's (any paying worker is welcome); NOVA's
  coordinator must keep EXP-035's fleet identity checks.
  Also its C codebase as code: NOVA reads designs, it does
  not adopt codebases.
- Licence: GPLv3 (COPYING).
- Reproduction or testing: builds with autotools against a
  node; the solo quickstart in README-SOLOMINING.md targets
  Core 32.x; reading only here.

## 3.19 MicroBT Whatsminer: what could and could not be verified

- Verified: MicroBT (Shenzhen MicroBT Electronics) sells
  the Whatsminer ASIC line; official firmware is
  distributed as closed binaries through whatsminer.com
  with the WhatsMinerTool management application; product
  manuals and support documentation are public. Public
  documentation of the firmware's structured error registry
  (a numeric code per fault class: fan, power, temperature,
  hashboard, network, firmware) shows error code 800 defined
  as a cgminer checksum error, which establishes that the
  firmware's mining software derives from cgminer.
- NOT verified: any official source repository (none was
  found on GitHub or elsewhere public); the mining
  software's version, modifications, job handling, or
  verification behaviour; any licence under which source is
  available (none is published).
- Consequence for this study: no source-level claims about
  Whatsminer are made. The single transferable item is at
  documentation level: a stable numeric incident code
  registry, so every fault an autonomous agent detects,
  classifies and recovers from carries a durable code that
  statistics and audit can key on. NOVA's incident records
  are free text today. Register: NEW, marked
  documentation-sourced.
- What cannot transfer: everything else about the product.

## 3.20 Bitaxe family (summary from EXP-030 Phase A, not re-studied)

Per the mandate and the task instruction, this family is
summarised from research/sha256d/exp030/REPOSITORY_AUDIT.md
and research/sha256d/exp030/REFERENCE_TO_NOVA_MATRIX.md,
which audited it at pinned commits: skot/bitaxe 942bbd97,
bitaxeorg/ESP-Miner e3cfbb3b, bitaxeorg/bitaxeGamma
f04c421e, shufps/qaxe be1a4a07, shufps/
ESP-Miner-NerdQAxePlus 3f738849, Patsch91/
NerdOCTAXE-Gamma ebe52cf6. That set includes NerdMiner's
successor line (the Qaxe and NerdQAxe firmware is the
ESP-Miner-NerdQAxePlus tree); BitMaker-hub/NerdMiner_v2
itself (an ESP32 display miner) was not separately audited
in Phase A and is not audited here; its mining core is the
same ESP-Miner lineage at much smaller scale.

The Phase A findings, in one paragraph: the firmware keeps
a fixed-size registry of immutable ASIC jobs (M04), clones
jobs on read (M05), rebuilds the exact header and
recomputes SHA-256d before submitting anything (M01, the
shape EXP-036 adopted), distinguishes share from block by
exact integer target comparison (M02), computes the
midstate once per job (M08), adapts its on-chip difficulty
mask toward a target share interval with hysteresis (M10),
counts hashrate from worker-owned counters in 1m, 10m and
1h windows (M11), stages non-clean job updates to a cycle
boundary (M16), suppresses duplicate job notifies by id
(M22), and speaks both Stratum V1 and V2, with SV2 standard
channel jobs carrying a precomputed Merkle root (M23, M24).
The Qaxe fork contributes the extranonce2 partition by
worker (M06, adopted into EXP-035), central master
verification of slave results (M13), slave liveness by
telemetry timeout with a persistent registry and a foreign
fleet check (M14), starved-slave re-registration (M15), and
the programme's standing negative example: judging nonces
by floating point difficulty (M03, rejected; EXP-036
forbids it). All 34 matrix rows carry decisions, and the
register in the companion file marks the corresponding
ideas ALREADY COVERED with their matrix references.


## 4. Cross-cutting synthesis

Four conclusions survive the whole set:

1. The hash path converged early and never moved again.
   Every computational idea in the historical miners that
   still matters (midstate reuse, chunk-2 prefix
   precomputation, schedule pre-extension, multi-way
   interleaving, candidates-only result return, first-word
   screening before an exact compare) was present by 2012,
   and NOVA has independently proved, measured and either
   integrated or rejected every one of them (EXP-011 to
   EXP-043). This study found no missed hash-path mechanism.
   That is a strong completeness signal for the SHA-X
   programme, stated with its boundary: the studied set is
   the open-source record; closed ASIC firmware (3.13,
   3.19) could not be searched for mechanisms.

2. The durable innovation moved to the operations layer.
   What cgminer, BFGMiner, Braiins OS and ckpool kept
   improving for a decade was not hashing but operations:
   health ladders, allocation strategies, privilege-split
   control APIs, signed update chains, aggregation tiers,
   per-worker difficulty control. That is exactly the layer
   the Master Build Mandate builds next, and it is where
   every genuinely new register item in the companion file
   sits.

3. Verification discipline is the through-line of the
   failures. The studied failures are all verification or
   trust failures, not hashing failures: Qaxe's float
   judging (M03), the broken-by-default Block Erupter
   driver (3.11), Antbleed's unauthenticated control
   endpoint (3.13), GUIMiner's inconsistent licensing
   (3.4). NOVA's fail-closed pattern (EXP-036 exact
   verification, EXP-039 self-test or refusal, EXP-035
   identity checks) is the historically correct posture,
   and the register's new items preserve it.

4. Two protocol frontiers are real and unsolved in NOVA:
   Stratum V2 job declaration (3.17) and push-based
   template supply, whether by SV2 template distribution
   or Core's mining IPC (3.17, 3.18). Both are gated on
   decisions outside this study (a Core version decision;
   a pool ecosystem decision) and are registered as NEW
   with those gates named, not as recommendations.

## 5. Licence summary (as read in the clones)

| Project | Licence |
|---|---|
| Bitcoin Core v28.1 | MIT |
| jgarzik/cpuminer | GPLv2 |
| pooler/cpuminer | GPLv2 |
| m0mchil/poclbm | Public domain (LICENSE file) |
| Kiv/poclbm (GUIMiner) | GPLv3 text shipped; inconsistent with upstream, see 3.4 |
| DiabloMiner | GPLv3 |
| Phoenix-Miner | MIT (file headers; no LICENSE file) |
| cgminer (both forks) | GPLv3 |
| BFGMiner | GPLv3 |
| Open-Source-FPGA-Bitcoin-Miner | GPLv3 |
| Avalon-extras | UNLICENSE (root) |
| bmminer-mix | GPLv3 |
| Braiins OS fork mirror; braiins/bmminer | GPLv3 |
| sgminer | GPLv3 |
| ccminer; CudaMiner | GPLv3 |
| stratum-mining/stratum | Apache 2.0 and MIT dual |
| ckpool | GPLv3 |

Standing rule for NOVA, unchanged by this study: designs
and mechanisms may be learned from any of these; code may
not be copied out of the GPL trees into the lab, and the
two permissively licensed sources (Core, Phoenix) are
still treated as references, not donors, because NOVA's
implementations are already its own.

## 6. What this study did not do

It did not execute any cloned code, build any clone, or
benchmark anything. It did not re-audit the Bitaxe family
(EXP-030 Phase A stands). It could not study bitmaintech/
bmminer or braiins/braiins-os at their mandate URLs (both
no longer public) and says so wherever their labelled
substitutes are used. It could not study Whatsminer at
source level at all. Performance statements about NOVA in
this report cite the existing experiment record; no new
performance claim is made.
