# Memory and Cache Research

Standing conclusion, with its evidence: on this machine,
SHA-256d mining is compute and latency bound, not memory
bound. This document records what mining actually moves,
the measured bandwidth it moves it against, and the three
places memory behaviour still touches performance (spill
traffic, digest stores, instruction cache), each with the
experiment that would settle its remaining question.

## 1. What a mining worker actually touches

Per template (once): the 80-byte header, the 32-byte
midstate, and in a hand kernel the prefix state and any
precomputed message operands (a few hundred bytes at
most).

Per nonce, steady state:

- Block-2 construction: in the production wrapper, a
  64-byte block assembled on the stack plus a 64-byte
  outer block (mining/cpu/bal_batch.c hash_nonce; 416 B
  stack frame measured, EXP-001). In the H-02 kernel, the
  block lives in registers; the hot function has a 0 B
  stack frame and 43 memory references, mostly the K
  stream and the digest store (EXP-002 assembly).
- Output: the batch entry points write 32 bytes of digest
  plus 1 flag byte per nonce (bal_c_batch2 output layout).
  At the best measured per-worker rate (3,298,604 H/s,
  EXP-003), digest stores run at about 106 MB/s. The
  search entry points write only the winner.
- Working set: state and schedule vectors in registers,
  plus stack spill slots at high stream counts (below).
  Nothing per nonce leaves L1 in the SHA-NI kernels
  except the digest store stream.

## 2. Measured bandwidth versus mining's demand

The probe's STREAM-style copy over a 128 MiB working set
measured 2.739 GB/s single-stream under contention
(../tools/machine_probe_2026-11-14.json; a floor estimate
on a capped shared VM, not the silicon's capability).
Mining's largest steady stream, batch digest stores at
the best measured rate, is about 106 MB/s, roughly
4 percent of that floor. Even the naive full-rate case
is three orders below any plausible DRAM limit. Cache
capacities as exposed (L1d 48 KiB, L1i 32 KiB, L2 1 MiB,
L3 32 MiB per the probe) are far above the per-worker
working set. There is no configuration of this workload,
at any rate this programme can plausibly reach on one
core, in which DRAM bandwidth binds. Increasing RAM
capacity or bandwidth would change nothing; the mandate's
instruction not to assume otherwise is satisfied by
measurement here.

## 3. Where memory behaviour does touch performance

### 3.1 Register spill traffic (the real memory cost)

At 4 streams the inlined H-01 hot function has a 1,056 B
stack frame and 365 xmm stack operations per wave
function invocation class (EXP-003 assembly record). The
spill area is L1-resident (the frame is about 1 KiB), so
this is not a bandwidth cost; it is an issue-slot and
load-latency cost inside the hot loop. It is also the
measured reason streams stop scaling: latency hiding wins
while spill slots are cheap, then loses. Later evidence
in the same direction, added by the Phase 6 correction:
the geometry walker's 4 and 6 stream bodies carry a
1,536-byte frame with 790 xmm stack operations (EXP-005);
the hand-scheduled variant proved the schedule's store
and reload round trip costs what the spills it removed
had cost (EXP-006); and the dual-batch MB body moves its
state through memory 48 times per body (EXP-011).
Register and stack traffic is not a footnote in this
programme; in three separate kernel families it is the
quantity that decided the result. Open questions,
one experiment each: X-007 (spill slot layout in one
cache line, hand-scheduled), X-057 (rolled versus unrolled
stream body), X-047 (aliasing and alignment annotations
to cut reloads).

### 3.2 Digest store traffic on the batch path

32 MB of stores per 1M-nonce batch is the one real memory
stream in the system, and most batch callers never read
the digests (search-style callers want flags or a
winner). Options, in increasing invasiveness: streaming
(non-temporal) stores for the digest buffer (X-053);
prefix-only digest stores with full digest materialized
for near misses (X-111); candidates-only output, which is
the pre-existing H-04, carried as a cross-reference and
not re-registered here. At currently measured rates the
ceiling on all three is the 106 MB/s stream's cache
pollution, a few percent at most; they become interesting
only if per-worker rates rise several-fold, which is why
H-04 stays open but unranked near the top.

### 3.3 Instruction cache

The 4-stream inlined hot function is 2,985 instructions
(EXP-003), on the order of 12 KB of code at typical
encoding lengths, against a 32 KiB L1i shared between two
vCPUs as exposed. It fits, but it fits alongside the rest
of the worker loop, and unroll-heavy variants (X-109)
push toward the edge. Code layout and cold-path eviction
(X-051) and a rolled-body variant (X-057) are the two
cheap probes. No I-cache miss data exists (perf counters
unavailable); any claim here is by wall clock A/B or not
at all.

## 4. Alignment, pages, and placement (audited, mostly closed)

- Template-side structures (header, midstate, operand
  tables) are a few hundred bytes; aligning them to one
  cache line is free and is X-058, a tidy-up, not a
  research question.
- The 32 MB batch output buffer is the only allocation
  where page placement could matter; H-19 in the H-series
  registry already owns alignment and page placement for
  the production path, and this tree does not duplicate
  it. If H-04 lands, the question mostly evaporates.
- NUMA: the guest exposes one node; there is nothing to
  place. Pinning is a scheduling question, owned by H-10.

## 5. What would change the conclusion

The compute-bound conclusion is a statement about SHA-NI
kernels at MH/s scale on this class of core. It would
need re-examination if: a multi-buffer vector kernel made
state traffic (not compute) the visible cost in its
assembly record; a fleet design moved templates or lanes
across sockets; or rates rose by two orders of magnitude
on one socket, at which point digest stores alone would
approach the measured copy floor. UPDATE (Phase 6,
2026-11-14): the first condition has occurred (EXP-011,
see the correction note at the head of this document),
so for the multi-buffer family the conclusion is
reopened by this document's own criterion. Workstream
C's job is now both: keep the spill, store, and I-cache
accounts current in each new kernel's experiment entry,
and pursue the reopened state-traffic questions
(Y-023, Y-029, Y-054) as research, not only audit.
