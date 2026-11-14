# Mining Pipeline Optimization (Stage 7 audit notes)

Scope: everything between a block template existing and a
block being accepted, audited against the current code. Hash
throughput is covered elsewhere; this is about not wasting it.

## The path as it stands (code-cited)

1. Template acquisition: mining/engine.py uses
   getblocktemplate with longpoll (wait_template), and the
   live Stratum runner (mining/mainnet_live.py) receives pool
   jobs with a generation counter. Observation: longpoll is
   already implemented; template polling waste is not a
   current cost.
2. Template validation: the live miner validates every pool
   template before spending hashes (Task: validate_job with
   nbits decode and ntime sanity), and MiningEngine rebuilds
   and re-verifies template transactions (txid recomputation,
   coinbasevalue check against subsidy plus fees). Cost: per
   template, negligible against any nonce range.
3. Candidate construction: coinbase, merkle root, and header
   are rebuilt per extranonce round in MiningEngine; the
   midstate makes template-side rebuilds cheap (67 rounds of
   precompute, header_and_midstate_analysis.md).
4. Search: spans sized from the measured probe rate to about
   1 second of work in the live miner, so a fresher template
   preempts within about a second; MiningEngine clamps every
   batch to the remaining nonce space (Task 003.2) and uses
   the counted search (Task 001), so reported work is actual.
5. Candidate confirmation: every search hit is recomputed
   with hashlib, checked against pool and network targets,
   and confirmed still-fresh before submission. Cost per
   candidate: one Python double hash plus comparisons,
   about 3.5 to 5.7 us of verification-class work measured
   across Tasks 003/003.8 for the C-verified path. At mainnet
   difficulty this cost is paid about never; at regtest
   targets the accounting separates it as verification_hashes
   (Task 003.9).
6. Submission and acceptance: MiningEngine counts a block as
   mined only when submitblock returns null AND the node's
   best block equals the submitted hash. The solo server path
   (mining/solo_server.py) was proven on regtest block 390
   and serves low-difficulty shares so workers stay visible.

## Findings

F1. No structural waste found in the template-to-submission
    path at current rates. The costs that exist (verification
    per candidate, 1 s preemption granularity, boundary
    overhead per batch) are measured, bounded, and small
    against a 1.6 MH/s hash rate.
F2. The pipeline's real exposure is upstream of it: stale
    work during the roughly 1 s span window when the chain
    tip moves. Expected stale fraction is about the span
    length over the inter-block time (1 s / 600 s, about
    0.17% on mainnet), which H-14 can tune but not remove.
F3. When the lab's own node finishes syncing and the solo
    server becomes the work source, GBT latency replaces
    pool latency; the same span and freshness logic applies.
    No pipeline change is queued ahead of that event; the
    accounting definitions already distinguish the work
    classes the cutover will report.

## Registered follow-ups

H-05 (span and crossing economics), H-13 (timestamp rolling),
H-14 (span vs freshness optimum), H-15 (partitioning). All
are marginal-class at current rates and none justifies
touching the live miner mid-flight; they are Stage 7 work
to schedule after Stage 5 produces a faster kernel, because
a faster kernel changes every one of these tradeoffs.
