# Follow-up Report: Experiment Batch EXP-004 to EXP-009

Date: 2026-11-14. This is the follow-up report for the
first five recommended experiments of FINAL_RESEARCH_
REPORT.md section 5, plus EXP-009 (pipeline and
interaction study, added by owner instruction during the
batch). Raw benchmark data: benchmarks/exp004_decision.
json, benchmarks/exp005_008_kernels.json, benchmarks/
exp007_confirm.json, benchmarks/exp009_pipeline.json.
Kernels: src/h01_geo.c, src/h01_hsf.c, src/avx512_mb.c,
src/h01_phase.c, src/freq_gate.c. Tests: tests/gates.py
with tests/test_exp005_geo.py, test_exp006_hsf.py,
test_exp007_avx512.py, test_exp008_phase.py.

Machine and conditions for the whole batch: EPYC 9D25
KVM guest, 4 vCPUs capped near 1.5 effective CPUs, live
mainnet pool miner and pruned mainnet node running
throughout. Mainnet node state at batch start: blocks
408,981, headers 975,789, initial block download true,
verification progress 0.0812. Load average ranged from
about 2.4 (the dip used for EXP-004) to about 17 at the
worst neighbour peaks. Every kernel below passed the full
gate set of tests/gates.py (at least 100,000 randomized
SHA-256d differentials versus hashlib per variant,
genesis, boundaries, template variations, target equality
and minus-one, exact accounting) before it was
benchmarked.

## EXP-004 (X-067): integration decision re-run

Method: bench_decision.py methodology extended to 9
round-robin interleaved rounds of 1M hashes, production C
versus H-01 streams=2 and streams=4, at 2 threads and at
1 thread, run at the lowest-contention dip observed in a
load watch (1-minute load 3.92 falling to 2.49; node
still in IBD, so the "quiet window" is relative, and is
recorded as such). Steal covariate (X-070 lite): 2.24
percent of CPU jiffies during the 2-thread configuration,
1.43 percent during the 1-thread configuration. Steal is
not the spread driver; runnable-load fluctuation is.
Predeclared rule, stated in the benchmark script before
the run: integration only if streams=4 minimum exceeds
production maximum at 2 threads.

Result at 2 threads: production median 1,463,346 H/s
(min 584,142, max 2,346,013, spread 120.4 percent);
streams=2 median 2,361,226; streams=4 median 4,212,571
(min 2,057,942, max 5,507,203, spread 81.9 percent).
Streams=4's median is 2.88x production's and its minimum
exceeds production's median by 41 percent, but its
minimum (2,057,942) does not exceed production's maximum
(2,346,013). CRITERION FAILED. At 1 thread: production
median 833,012; streams=4 median 2,553,065 (spread 142.5
percent).

Conclusion: integration NOT justified under the strict
rule. Production is byte-identical. The next precondition
for revisiting is unchanged: a window with the node past
IBD, or a contender whose separation survives this VM's
noise. Claim tier: the streams=4 median advantage is a
VERIFIED IMPROVEMENT under stated conditions (consistent
across four sessions now); the integration claim itself
remains unmade.

## EXP-005: stream geometry sweep

Method: src/h01_geo.c extends the H-01 framework to
streams 1, 2, 3, 4, 6 and a strided assignment mode
(stream si takes span offsets si, si+NS, ...), all gate-
verified per variant, including wave-exact early-exit
accounting for every geometry (for example strided
streams=4 finds the genesis winner at attempted exactly
50,004; blocked streams=6 at exactly 100,000 because the
winner sits at the end of its chunk while the short final
chunk drains). Benchmarks: the combined interleaved
session (benchmarks/exp005_008_kernels.json), 5 rounds of
1M, load rising from 2.82 to 10.86 during the session.

Medians at 2 threads (H/s): blocked s1 1,419,401; s2
2,046,508; s3 1,999,538; s4 2,476,649; s6 2,593,711;
strided s3 3,360,311; strided s4 3,473,271 (spread 52.3
percent, the tightest of the fast group). At 1 thread the
ordering compresses (blocked s3 median 2,105,587 leads
the SHA-NI family) and spreads overlap heavily.

Assembly (objdump): the 2- and 3-stream run bodies stay
standalone with 0 B frame and zero stack ops (347 and 567
instructions). The 4- and 6-stream bodies inline into
walk_span: 4,563 instructions, frame 1,536 B, 790 xmm
stack ops, the spill cost curve made concrete.

Conclusion: the geometry curve is flat-topped from 3 to
6 streams within this VM's noise; strided assignment is
at least as good as blocked at equal count in both
measured counts at 2 threads. Named best geometry:
streams=4 strided at 2 threads, with streams=6 blocked
statistically indistinguishable. Tier: VERIFIED
IMPROVEMENT for strided-over-blocked as a median tendency
in this session; the exact optimum count remains a
PROMISING HYPOTHESIS pending a quieter host.

## EXP-006 (X-006, X-007): hand-scheduled variant

Method: technique (a), software-pipelined schedule
build, combined with technique (b), fused K reuse:
src/h01_hsf.c expands every stream's full MSG schedule
into a stack-resident W array first (the GENA/GENB
sequence transcribed from the core with rounds removed),
then runs rounds over the stored schedule, the K vector
for each group loaded once and shared by all streams.
Gate-verified for streams 2, 3, 4.

Assembly: the whole hot path inlines into one body of
1,374 instructions with 117 xmm stack ops (versus 790 in
the geo library's inlined body) and a 2,752 B frame
dominated by the deliberate W storage (6 streams x 16
vectors = 1,536 B) rather than by spills.

Benchmarks (same combined session, medians at 2
threads): hsf s2 1,903,147 versus geo s2 2,046,508; hsf
s3 2,223,113 versus geo s3 1,999,538; hsf s4 1,887,981
versus geo s4 blocked 2,476,649. Schedule-first is at
parity at 2 to 3 streams and clearly behind at 4.

Conclusion: negative result with a mechanism. Cutting
spill operations by 6.7x did not buy time: the W-array
store/load round trip costs about what the spills cost,
and at 2 streams the compiler's interleaved body already
has a 0 B frame and zero stack ops, so there was nothing
to recover. Technique (c), an inline-assembly stream
pair, was therefore not built: its premise (spill
traffic binds at the pair level) is refuted by the
0-spill 2-stream body and by technique (a)'s outcome.
Tier: hand-scheduled assembly remains a PROMISING
HYPOTHESIS with a weakened premise; the schedule-first
form itself is measured and rejected as a champion.

## EXP-007 (X-031, gated on X-041): AVX-512 multi-buffer

Gate X-041 first: src/freq_gate.c alternates scalar and
AVX-512 fixed-work throughput blocks (no perf counters
exist). Two runs, both contention-dominated: run 1 block
rates unstable in both loop types (scalar drift +51
percent, AVX-512 drift -33 percent across blocks); run 2
scalar rates rose 1.72 to 2.35 Gops/s (+36 percent)
while AVX-512 block rates stayed flat at 1.0 to 1.3
Gvecops/s (drift -6 percent). No catastrophic AVX-512
penalty is visible, and the multi-buffer kernel below
posts the best medians of the batch, so the gate passes
with eyes open: rates are reported as measured, and the
flat AVX-512 response while scalar rose is recorded as
an unresolved observation (internal throughput bound and
mild frequency drag are both consistent with it; a
quieter host is required to separate them).

Prototype: src/avx512_mb.c, 16 lanes in zmm registers,
transposed state, vector schedule with vprold rotates,
midstate broadcast, outer phase fed directly from the
inner state vectors. Full gate set passed, including
lane semantics: partial final groups compute dummy lanes
that are never stored and never counted as coverage
(attempted 100,003 with backend 100,016 on the partial-
group probe; sub-group and 2^32 group-edge cases exact).
The 8-way AVX2 variant was not built: the 16-way result
(below) made the family's ranking question decisive
first, and AVX2 rotates cost three vector ops each where
vprold costs one, so the 8-way's prior is strictly worse
on this CPU; it remains registered under X-032 for
machines without AVX-512.

Benchmarks: combined session median at 2 threads
6,526,467 H/s (min 2,379,216, max 9,331,180, spread
106.5 percent), the fastest contender; at 1 thread
median 1,986,785 with the widest swings of the session.
Confirmation run (new session, heavier load, 7 rounds):
median 3,195,024 versus geo s4 strided 2,323,591 and
production 1,035,433. Assembly: v_compress16 is a compact
111-instruction loop body; the walk body carries the
multi-buffer tax (frame 4,096 B, 883 xmm stack ops from
the stack-resident schedule ring and state arrays).

Conclusion: the multi-buffer family reorders the ranking
on this CPU. Tier: VERIFIED IMPROVEMENT on a median
basis at 2 threads, reproduced across two interleaved
sessions under stated contention; no separation claim,
and its variance is the widest measured, so any future
integration decision needs its own decision run under
the same strict rule as EXP-004.

## EXP-008 (X-009): cross-nonce phase pipelining

Method: src/h01_phase.c fuses the block-2 compression of
nonce n+1 with the outer compression of nonce n in one
worker (run_mixed applies every group step to both
streams). Declared accounting: attempted counts
completed digests; on an early exit the co-computed
block 2 of the next nonce is real work that produced no
digest and is not counted (asserted exactly: genesis
probe attempted == 50,001). Full gate set passed.

Assembly: the fused body inlines into walk_span_pipe:
673 instructions, 63 SHA256RNDS2, frame 576 B, 74 xmm
stack ops (two live streams: 12 message/state vectors
plus temporaries).

Benchmarks (combined session): median 1,665,271 H/s at
1 thread and 2,104,688 at 2 threads. That is parity with
the 2-stream same-phase kernel (2,046,508 at 2 threads)
and well below the 4-stream and multi-buffer contenders.

Conclusion: phase diversity buys nothing measurable
beyond a second chain on this core; the two phases'
instruction mixes are too similar (both are the same
round machinery) for port complementarity to appear.
Tier: the phase-premium claim is not supported here
(measured); X-009 stays a PROMISING HYPOTHESIS only for
cores with demonstrably different phase costs.

## EXP-009: pipeline and interaction study

Measurement only; no production code changed.

(a) Candidate construction (X-059, measured). Against a
zero-latency counting stub RPC, build_candidate costs a
median of 0.018 ms per call at 0 template transactions,
0.126 ms at 10, 0.921 ms at 100, and 8.919 ms at 500
(marginal cost about 17.8 us per transaction, the txid
and wtxid re-verification). The stub recorded exactly
one validateaddress and one getblockchaininfo RPC per
call. Against the real regtest node (2-transaction
template), the same call costs a median of 4.447 ms, of
which validateaddress alone is a 3.963 ms median round
trip: at small templates the repeated validateaddress
RPC is the largest single cost in the pipeline, larger
than all Python re-verification until roughly 250
transactions. Per template, the mine_cycle extranonce
loop multiplies everything by up to 64: worst case at
500 transactions is about 571 ms of construction plus
about 285 ms of validateaddress latency per template
(stub and real-RPC figures respectively, not additive
across setups). Against a mainnet template lifetime of
about 600 s that is about 0.1 percent; against regtest's
fast blocks it is material. GBT intake itself: 1.06 ms
median per getblocktemplate round trip.

(b) Span-size interaction. The median-based first pass
was noise-dominated and is superseded by a min-based
redo (minimum times over 7 repeats per size, the
contention-resistant statistic): at best-case times,
per-hash cost at span 4,096 is not higher than at
4,194,304 for production, geo s4, or avx512_mb16 (small-
span minimum rates meet or exceed large-span rates:
for example avx512_mb16 minimum-time rates of 9.54M,
13.18M, 12.17M H/s at spans 4,096, 16,384, 65,536
against 6.80M at 4,194,304). Per-call fixed overhead is
therefore below the resolution of these methods (bound:
under about 10 us per call), and its share at the
MiningEngine batch of 65,536 is under 0.1 percent for
every kernel, best case. Larger spans mostly buy
exposure to contention drift, not overhead relief.

(c) Wall-time split. A real MiningEngine mine_cycle
against the stub (0-transaction template, hard target,
24 batches of 65,536): search 99.958 percent of wall,
build_candidate 0.006 percent, everything else 0.036
percent. With construction costs from (a), the split
stays search-dominated at every realistic template size
on mainnet timing; construction only becomes visible
when templates churn at regtest speed with hundreds of
transactions.

(d) Interactions. Kernel choice does not change the
optimal span anywhere in the measured range: every
kernel's overhead knee is far below 65,536, so the
engine's fixed batch and mainnet_live's one-second
sizing (2^20 to 2^24 at current rates) are both safely
placed for the champion kernels too. The one interaction
that does bind is candidate confirmation at high kernel
rates: hashlib confirmation costs a median of 1.1 us per
candidate, and at a regtest-easy target (about one
candidate per 256 hashes) a 6.5M H/s kernel generates
about 25,000 candidates per second, about 2.8 percent of
one core in Python confirmation alone. Confirmation cost
scales with kernel rate; search cost does not care.
Tier: parts (a) and the validateaddress finding are
VERIFIED IMPROVEMENT-grade measurements (of knowledge:
they price X-059 exactly); the span conclusion is a
measured negative (no interaction) under stated methods.

## Batch conclusions, by tier

VERIFIED IMPROVEMENT (measured, reproduced, conditions
stated):
- MSG schedule over scalar schedule (EXP-002, prior).
- Stream interleaving over single-chain SHA-NI
  (EXP-003, EXP-005 geometry map added).
- Strided assignment at least equal to blocked at equal
  stream count (EXP-005, this session's medians).
- AVX-512 16-way multi-buffer: fastest medians measured
  on this VM at 2 threads in two interleaved sessions
  (EXP-007). Not integrated: it has never faced the
  strict decision rule, and EXP-004 shows what this VM
  does to separation claims.
- X-059 priced: validateaddress per build_candidate call
  is about 4 ms of RPC latency; per-transaction
  re-verification about 17.8 us (EXP-009).

PROMISING HYPOTHESIS:
- Hand-scheduled assembly past the stream kernels
  (premise weakened by EXP-006).
- Phase pipelining on other cores (unsupported here,
  EXP-008).
- AVX2 8-way multi-buffer for non-AVX-512 machines
  (X-032, untested).
- A future integration decision for the multi-buffer
  kernel under the strict rule, in a post-IBD window.

UNPROVEN BREAKTHROUGH:
- Everything beyond the per-core ceiling narrative.
  Nothing in this batch moves the 500 GH/s or 140 TH/s
  arithmetic of PERFORMANCE_ROADMAP.md; the batch's best
  median (6.53M H/s at 2 threads) is a per-worker figure
  on a capped, contended guest.

Integration: none. EXP-004's predeclared criterion
failed, so production is byte-identical, no test-all run
and no integration regtest block were owed, and the
research kernels remain separate libraries.
