# Bottleneck Analysis: the Production Path, End to End

Scope: the two live production execution paths (the GBT
path through mining/engine.py and the pool path through
mining/mainnet_live.py) and the kernels under them. Every
cost is either measured (cited) or labelled reasoning.
Shares are stated against the EXP-000 baseline rate
(production C, 2 threads, median 1,627,792 H/s; amortized
about 0.61 us per hash at that configuration, 0.76 us at
1 thread).

## 1. The path, stage by stage

1. Work acquisition. GBT with longpoll
   (mining/engine.py wait_template) on the node path;
   Stratum job notifications with a generation counter on
   the pool path (mining/stratum_client.py). Cost: per
   template. Measured verdict of the Stage 7 audit: no
   polling waste; longpoll is implemented and used
   (../mining_pipeline_optimization.md).
2. Template validation and candidate construction.
   mining/engine.py build_candidate re-parses every
   template transaction, recomputes txid and wtxid
   (strip_witness plus dsha256 per tx), cross-checks the
   witness commitment and coinbasevalue against subsidy
   plus fees, and resolves the payout script through a
   validateaddress RPC call. Cost: per candidate
   construction, and construction happens once per
   extranonce step (mine_cycle loops extranonce 0..63 per
   template). The pool path builds its header in
   mining/stratum_client.py build_header (Python hashlib
   coinbase and merkle branch per job round) after
   validate_job checks the job.
3. Midstate and prefix preparation. Production: block 1
   compressed once per search call inside the C library
   (compute_midstate in mining/cpu/bal_batch.c), 64 rounds
   amortized over the span. The block-2 prefix (3 rounds)
   is not taken by any production path (the OpenSSL
   whole-block API cannot express it).
4. Search. ComputeEngine (gpu/engine.py) dispatches:
   CUDA only after its production-path self-test, else
   the C library (bal_c_search2 counted early-exit, or
   bal_c_batch2 enumeration), else Python hashlib. Spans
   in the live pool runner are sized to about one second
   of measured rate so a fresher job preempts within
   about a second; MiningEngine clamps batches to the
   remaining nonce space (batch_count, Task 003.2).
5. Candidate confirmation. Every hit is recomputed
   independently (hashlib in mining/mainnet_live.py;
   verify_candidate in gpu/engine.py), checked against
   pool and network targets, and confirmed still-fresh
   before submission. Measured cost: about 3.5 to 5.7 us
   of verification-class work per candidate (Tasks 003
   and 003.8), accounted separately as verification_hashes
   (Task 003.9).
6. Submission and acceptance. submitblock via RPC on the
   node path, counted as mined only when the call returns
   null and the node's best block equals the submitted
   hash (mining/engine.py); Stratum submit on the pool
   path; the solo server (mining/solo_server.py) assembles
   full blocks from winning shares and submits the same
   way (proven on regtest block 390).
7. Supervision. mining/autopilot.py (heartbeat 5 s,
   watchdog poll 1 s, hung window 300 s, session rotation
   24 h, self-update checks) plus systemd units and the
   outer keeper. Not a throughput cost; historically the
   largest source of recovered work in this lab was
   uptime, not rate (../statistical_mining_analysis.md).

## 2. Where the time goes

Hashing is the overwhelming cost, by construction of the
measurements: inside a batch, one hash costs about
0.61 to 0.76 us amortized (EXP-000), while every other
stage is per template, per span, or per candidate:

- Per span (about 1 second of work, millions of hashes):
  one Python to C boundary crossing, median 31.38 us for
  a whole call (EXP-000). Amortized over a 1M-nonce span:
  about 0.003 percent. Boundary overhead is a small-span
  disease only; at the live span sizes it is noise.
- Per template: GBT round trip, validation, construction,
  and the 64-round midstate. All trivial against a nonce
  range (a template lives about 44 minutes of nonce space
  at 1.63 MH/s).
- Per candidate: 3.5 to 5.7 us of verification. At
  mainnet targets candidates effectively never occur; at
  regtest targets this is real and is why verification
  overlap is X-063.
- Inside the hash itself (the 0.61 to 0.76 us): 125
  rounds of compression plus, in the production path,
  the wrapper work around two OpenSSL Transform calls.
  The wrapper's compiled shape is 408 instructions with
  a 416 B stack frame per nonce call path (EXP-001)
  against a hand kernel's 494 instructions total with a
  0 B frame (EXP-002). This internal split, compression
  versus everything around it, is where all measured
  kernel gains so far have come from: the MSG schedule
  (about 2.6x over scalar at equal rounds, EXP-002) and
  latency hiding by interleaving (2.36x at 2 streams,
  EXP-003) both attack the "around", not the rounds.

Reasoning, labelled: with perf counters unavailable, no
finer split (cycles per stage inside the compression) can
be measured in this guest; the programme's splits come
from assembly accounting and differential builds (the
scalar twin), which is the strongest evidence available
here.

## 3. Duplicated and wasted work found in the code

W1. Candidate construction repeats per extranonce
    (mining/engine.py): build_candidate re-verifies every
    template transaction and repeats the validateaddress
    RPC on each of up to 64 extranonce invocations per
    template, although only the coinbase changes. The
    merkle root is also recomputed over all txids per
    invocation instead of along the coinbase spine.
    Registered: X-059, X-060, X-061. Impact class today:
    small (per extranonce round, not per nonce), growing
    with any kernel speedup.
W2. The live pool runner counts requested work as done
    work in its own status line (mining/mainnet_live.py):
    it calls the uncounted search_first and adds the full
    span to total_hashes even when the search exited
    early on a hit. The evidence-grade counters elsewhere
    (autopilot reads the evidence log; ComputeEngine's
    counted path exists and is used by mining/engine.py)
    are unaffected, but the runner's printed rate
    overstates on hit spans. This is the Task 001
    leftover, flagged in the correction record and
    deliberately untouched by the kernel tasks. Fix
    direction: use search_first_counted and add its
    attempted figure. Recorded here so the fix is a
    pipeline task, not a drive-by.
W3. The batch enumeration path writes digests nobody
    reads (mining/cpu/bal_batch.c bal_c_batch2): 32 bytes
    per nonce, 32 MB per 1M batch, for search-style
    callers that consume only flags. Registered as H-04
    in the H-series (cross-reference; not duplicated in
    the X registry), with X-053 and X-111 as the
    keep-the-writes variants.
W4. Startup probing spends real hashes
    (gpu/engine.py tune_c_threads): the tuner runs the
    real search over 2^20 nonces at up to five thread
    counts per process start, and ComputeEngine's CUDA
    self-test does its own work. One-time per process and
    honestly reported as probe rate; noted so the cost
    is visible, not because it matters.
W5. Two C libraries carry parallel scaffolding
    (mining/cpu/bal_batch.c and bal_sha_intrin.c share
    bal_search.h by design, which limits the duplication
    to the per-library hash functions; the intrinsics
    library's scalar schedule makes its copy the
    expensive one to run, R-05.) No action: the intrinsics
    library is a kept artifact, and the research kernels
    supersede it as candidates.
W6. The standalone miner does the naive thing on purpose
    (mining/cpu/bal_miner.c): full 192-round hashing
    through the streaming SHA256() API with no midstate,
    plus per-nonce best-hash tracking in search mode. It
    is a diagnostic and cross-check tool, slowest by
    design; the waste is documented so nobody mistakes
    its rates for the engine's.

## 4. Architectural inefficiencies (structural, not bugs)

A1. The production compression sits behind a
    general-purpose streaming API. Whole-block Transform
    calls cannot express the block-2 prefix snapshot
    (3 rounds per nonce, H-03), operand precomputation
    (X-024), or cross-phase overlap (X-008, X-009). This
    single fact is the architectural reason a hand kernel
    exists at all.
A2. The dispatch ladder stops at library granularity.
    Selection today is CUDA versus C versus Python, plus
    a thread count. Stream count, span class, and family
    (vector multi-buffer, when it exists) are not yet
    selectable dimensions (X-082, X-083, X-115).
A3. The VM cap inverts normal scaling intuition, and the
    code's tuning predates the stream kernels: the tuned
    thread count (2) was measured for the OpenSSL path.
    Worker and stream mix for the stream kernels is
    unmeasured (X-073, X-074).
A4. Freshness is enforced by polling granularity (about
    1 s spans) although the job-arrival side is already
    event-driven (Stratum reader, GBT longpoll). The
    stale-work exposure is small (about 0.17 percent) and
    bounded; X-062 closes the asymmetry when it is worth
    doing.
A5. Accounting is exact in the engine and approximate
    in one runner (W2). The programme's credibility rests
    on the Task 003.9 definitions; any surface that
    reports rate should be on the counted path.

## 5. What is not a bottleneck (measured, so it stays closed)

- Memory bandwidth: digest stores at the best measured
  rate are about 106 MB/s against a 2.739 GB/s measured
  copy floor (MEMORY_AND_CACHE_RESEARCH.md).
- Template acquisition latency: longpoll and job events
  already deliver work at the rate the chain produces
  it.
- Verification cost at real targets: candidates are too
  rare for 5 us to matter; it binds only at regtest
  densities, where it is measured and registered.
- The node: pruned Core under the solo server pattern
  served regtest block 390 end to end; GBT cost is per
  template.
