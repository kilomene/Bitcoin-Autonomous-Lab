# CPU Execution Research

Everything in this document is either a measurement from
this lab's experiment records (cited) or reasoning from
instruction semantics and the compiled listings, and the
two are labelled. perf counters are unavailable in this
guest (../cpu_microarchitecture.md: perf absent,
perf_event_paranoid 4), so cycles per hash, IPC, and port
utilization are never reported as measured; wall-clock
throughput with repeats and spread is the evidence
standard.

## 1. The machine, as it matters here (measured)

AMD EPYC 9D25 (family 26), KVM guest, 4 vCPUs exposed as
4 cores x 1 thread, 1 NUMA node, capped near 1.5 effective
CPUs on a shared host. Probe record:
../tools/machine_probe_2026-11-14.json (load average 1m
8.66 at probe; single-stream copy 2.739 GB/s under
contention; /proc/cpuinfo frequency constant at
1497.75 MHz, no cpufreq sysfs, so real core clock and
boost behaviour are unobservable from inside).

Instruction sets present (probe): sha_ni, bmi1, bmi2, adx,
avx, avx2, and a wide AVX-512 set (f, dq, cd, bw, vl,
vbmi, vbmi2, ifma, vnni, bitalg, vpopcntdq, bf16,
vp2intersect), plus vaes and gfni. Toolchain: gcc 13.3.0,
no clang, OpenSSL 3.0.13.

## 2. SHA-NI as observed in this lab

### 2.1 Instruction semantics (from source and listings)

- SHA256RNDS2 computes two rounds per instruction. Its
  operands carry the state in the org-form packing the
  lab's kernels use (../experiments/h02_shani/shani_core.h,
  mining/cpu/bal_sha_intrin.c): two __m128i registers hold
  the eight state words, and the message operand supplies
  K+W for the two rounds in its low 64 bits. The old cur
  becomes the next prev, so the state rotation is exact
  with no data movement.
- SHA256MSG1 and SHA256MSG2 generate the schedule. In the
  whitepaper construction the H-02 kernel follows, each
  group of 4 words sits in one vector; MSG1 forms partial
  sums for the group four ahead, and MSG2, with an
  alignr-supplied W[i+9] term, completes the group three
  ahead. Per compression the H-02 hot path issues 12 MSG1
  and 12 MSG2 (measured in the compiled listing,
  ../assembly_analysis.md).
- Per nonce, the H-02 hot function hash_p1 executes 63
  SHA256RNDS2 (31 block-2 pairs plus 32 outer pairs), 24
  MSG1, 24 MSG2, in 494 instructions total, stack frame
  0 B, 0 calls (measured, EXP-002 assembly record).

### 2.2 The schedule is not a detail (measured)

The single clearest execution result in the programme:
at identical rounds, a kernel whose schedule is generated
by MSG1/MSG2 runs about 2.6x faster than the same kernel
with a scalar C schedule (EXP-002 same-session 2-thread
medians: MSG kernel 1,966,395 H/s, scalar twin 751,524
H/s). The pre-existing intrinsics library
(mining/cpu/bal_sha_intrin.c) contains zero MSG
instructions and recomputed the schedule in scalar C per
nonce; it measured about 0.52x production in EXP-000 and
its deficit is structural (R-05). Any future SHA-NI work
in this lab starts from the MSG schedule as a given.

### 2.3 Single chains are latency-bound here (measured)

Evidence, all from EXP-003 (per-worker, 1 thread, same
session, medians): streams=1 1,064,406 H/s; streams=2
2,515,315 H/s (2.36x); streams=4 3,298,604 H/s. If
SHA256RNDS2 throughput (instructions retired per cycle)
were the binding constraint, interleaving independent
chains could not multiply per-worker throughput: the same
instructions would retire at the same rate. Gains of this
size are only possible when a single chain stalls on the
serial dependency T1(t) to T1(t+1), and other chains'
instructions fill the stalls. Conclusion: on this core,
the binding constraint for a single hash chain is round
latency plus issue of the surrounding schedule and shuffle
work, not RNDS2 retire bandwidth. The absolute floor
framing makes the same point: a nonce needs about 63
RNDS2; even at an impossible one RNDS2 retired per cycle
and nothing else executed, that is 63 cycles per hash
(see PERFORMANCE_ROADMAP.md for the full ceiling
arithmetic).

Reasoning, labelled: published latency figures for
SHA256RNDS2 on Intel cores are multiple cycles, and the
round chain consumes its output serially, so one chain
issues at most one RNDS2 per latency window. This lab does
not cite a vendor latency number as a measurement; the
stream-scaling curve above is the measurement, and it is
sufficient.

### 2.4 Register pressure is the stream ceiling (measured)

x86-64 gives 16 architectural xmm registers, and the SHA
instructions are 128-bit forms addressing only those 16.
Per stream, a SHA-NI kernel needs 2 state vectors plus
about 4 schedule vectors live, plus K and scratch. At
4 streams the compiler inlined everything into one
2,985-instruction function with a 1,056 B stack frame and
365 xmm stack operations (EXP-003 assembly record): the
spills are the price, and on this core the price is worth
paying (streams=4 has the highest medians). At more
streams the spill traffic grows faster than the remaining
latency win; where the cliff sits is X-002, X-003, X-005.

An architectural note (reasoning from the ISA): the
AVX-512 register file (32 vector registers) is not
available to the SHA instructions, which have no EVEX
forms. Register relief for SHA-NI streams cannot come
from AVX-512 encoding. It can only come from better
allocation (X-006, X-007) or from the vector multi-buffer
family, whose instructions do have EVEX forms (section 3).

### 2.5 The production wrapper cost (measured)

Production per-nonce work is two OpenSSL SHA256_Transform
calls. The wrapper that builds the blocks and calls them,
hash_nonce in mining/cpu/bal_batch.c, compiles to 408
instructions with a 416 B stack frame (EXP-001 objdump),
for 125 rounds of real work. The compression itself is
inside libcrypto (128 sha256rnds2 sites there, 0 in the
lab's library). OpenSSL's Transform API takes whole
blocks from a state, so it cannot express the block-2
prefix snapshot (H-03) or any cross-phase overlap. The
incumbent is optimal-class compression behind a
general-purpose streaming interface; the measured gap to
the hand kernels (decision run medians, EXP-003) is the
size of that mismatch on this machine.

## 3. The untested family: vector multi-buffer SHA-256

Structure: N independent hashes advance in lockstep, one
per 32-bit lane of a vector register (AVX2 ymm: 8 lanes;
AVX-512 zmm: 16 lanes). Every round operation is a vector
operation applied to all lanes at once: rotates, the
proven Ch and Maj alternative forms, adds, and a vector
message schedule (each lane schedules its own hash's
words). Per-lane results are bit-identical to scalar
SHA-256 by construction.

Honest expectations, labelled as reasoning:

- Cost shape: a software round costs on the order of tens
  of vector ops (three rotates for S1, three for S0, the
  Boolean functions, a five-operand add tree), versus
  half an RNDS2 instruction per round in the SHA-NI path,
  but each vector op does 8 or 16 rounds' worth of one
  round-step. Per hash-equivalent, the instruction count
  lands in the same few-hundred range as the H-02 hot
  function's measured 494. There is no order-of-magnitude
  argument either way; the family's fate is an experiment
  (X-031 to X-034), which is exactly why it ranks as the
  largest untested family.
- AVX-512 advantages over AVX2 here: vprold makes each
  rotate one op instead of three; 32 registers ease the
  schedule's live range; mask registers handle partial
  waves without dummy lanes (X-042). AVX-512 risks:
  frequency behaviour of sustained 512-bit work is
  unobservable in this guest (no cpufreq, host cap), so a
  long-run decay measurement (X-041, X-085) must accompany
  any prototype result.
- Historical position: multi-buffer was the standard
  high-performance software SHA design before SHA-NI
  shipped, and was largely set aside when dedicated round
  instructions arrived. Wide vectors with native rotates
  are the modern condition that reopens it
  (REVERSE_ENGINEERING.md, section 5).
- What it cannot do: reduce the per-hash dependency
  chain. Each lane's chain is the same 125 rounds deep;
  the width is parallelism, not a shortcut.

## 4. Hand assembly: what it can and cannot buy

compiler output for the H-01 kernels already interleaves
streams; what a compiler has not done, and hand scheduling
could (X-006, X-007): explicit register assignment that
keeps the hottest schedule vectors resident across the
wave, spill slots laid out so a wave's spill traffic
touches as few cache lines as possible, and RNDS2/MSG
issue ordering chosen from the listing rather than hoped
for from the scheduler. What hand assembly cannot buy:
more registers, lower RNDS2 latency, or a shorter round
chain. The honest prior is a moderate gain on the current
best kernel, at high implementation and verification
cost, which is its rank in the roadmap.

## 5. Dispatch and runtime selection (design)

The lab already selects by measurement, not by flag
guessing: ComputeEngine (gpu/engine.py) tries CUDA only
after a production-path self-test, then the C library,
then Python, and tune_c_threads probes the C search at
several thread counts on the machine it starts on and
keeps the measured peak. The extension this programme
designs for:

- Probe candidates in a fixed ladder at startup (H-01
  stream counts, H-02, production C, vector multi-buffer
  when present), each behind the same genesis self-test
  the C path already uses, and keep the measured winner
  per machine (X-082).
- Fallback must be structural, not hopeful: a candidate
  that fails its self-test or is absent is skipped, and
  the reason is recorded, exactly as ComputeEngine records
  fallback_reason today (X-084).
- Selection granularity can include span length: a kernel
  with higher template setup cost wins only on long spans
  (X-083); measure the crossover instead of assuming it.
- Fleet note: dispatch is per machine by design (each
  agent's box differs); nothing in this programme ships a
  global thread or stream count.

## 6. Threads versus streams (measured summary)

- Threads scale into the VM cap: EXP-000 production
  medians 1T 1,314,704; 2T 1,627,792; 4T 2,512,762 with
  82.6 percent spread at 4T. Past the tuned count, threads
  buy contention-shaped variance (R-04).
- Streams scale into the register file: 2.36x at 2
  streams, more at 4, cliff unlocated (section 2.4).
- The two multiply only until the cap binds: EXP-003
  2-thread totals (2,022,309 / 3,171,230 / 3,481,103 for
  streams 1 / 2 / 4) grow much less than the per-worker
  figures, because 2 workers already oversubscribe the
  roughly 1.5 effective CPUs. On an uncapped machine the
  mix would differ; that is a dispatch question (X-073),
  not a defect.
