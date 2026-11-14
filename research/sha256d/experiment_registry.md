# Experiment Registry and Ranked Hypothesis List

Every experiment keeps: id, hypothesis, rationale, baseline,
compiler and flags, machine, correctness result, repeated
benchmarks with median and spread, assembly observations,
decision, and the next question. Failed experiments stay in
the record. The trusted baseline is never overwritten; a
candidate earns production only through the integration rule
(median improvement beyond spread overlap, full differential
correctness, full suite plus a fresh regtest block through the
changed path).

Conditions applying to every entry below, unless an entry says
otherwise: AMD EPYC 9D25 KVM guest, 4 vCPUs capped near 1.5
effective CPUs, live mainnet pool miner and pruned node
contending, gcc 13.3.0, OpenSSL 3.0.13, harness =
experiments/bench_harness.py, accounting per Task 003.9.

## EXP-000: trusted baseline (Stage 3)

- Hypothesis: none; this is the reference measurement.
- Raw data: experiments/exp000_baseline.json.
- Correctness gates inside the harness run: both native
  libraries match hashlib on 20,000 batch digests and re-find
  the genesis nonce by search.
- Production C backend (bal_c_batch2), 1,000,000 hashes/run,
  3 repeats: 1 thread median 1,314,704 H/s (spread 26.9%);
  2 threads median 1,627,792 H/s (spread 12.5%); 4 threads
  median 2,512,762 H/s (spread 82.6%, unstable under the cap).
- Intrinsics backend (bal_i_batch2): 1T 699,926; 2T 848,348;
  4T 1,135,344 H/s. Ratio to production at 2T: about 0.52x.
- Python hashlib fallback: median 304,444 H/s, 1 thread,
  50,000 hashes/run, wide spread (197,609 to 517,731).
- Single-candidate latency: count=1 batch call through ctypes,
  median 31.38 us (production), 31.74 us (intrinsics); p90
  above 1,100 us under contention spikes. Amortized per-hash
  at 1T production: about 0.76 us. The single-call figure is
  boundary overhead, not hash latency; see bottleneck B4.
- Decision: baseline adopted. All future comparisons use this
  harness and must report repeats, median, and spread.

## EXP-001: compiler and flag sweep on production source

- Hypothesis: production flags (-O3 -march=native) leave
  performance on the table that other gcc flag sets recover.
- Method: experiments/compiler_sweep.py builds
  mining/cpu/bal_batch.c under 5 flag sets into .local/shax/,
  verifies 100,000 digests per variant against hashlib plus
  the genesis search, inspects hash_nonce assembly, and
  benchmarks 1M hashes x 3 repeats at 1 and 2 threads.
- Raw data: experiments/exp001_compiler_sweep.json. Full
  write-up: compiler_experiments.md.
- Result (2T medians): production flags 2,347,336 H/s;
  -O2 native 1,472,158 (-37.3%); -O3 generic 2,188,081 (-6.8%);
  -O3 native + LTO 2,195,680 (-6.5%); -O3 native + funroll
  2,050,686 (-12.6%). Every spread overlaps the production
  spread (production spread itself was 70.1% in this session).
- Decision: REJECT all variants; production unchanged.
  No variant's median beat production, and contention spreads
  would have barred integration regardless. The production
  flag set is confirmed adequate; the bottleneck is inside
  OpenSSL's compression and our wrapper shape (B1), not in
  the flags applied to the wrapper.

## Ranked hypotheses (H-01 to H-24)

Benefit classes: marginal (under about 5%), moderate
(5 to 30%), large (over 30%), unknown. Ranked by expected
value on THIS machine: benefit x probability, divided by
effort and risk.

### H-01: Multi-stream interleaved SHA-NI kernel
- Statement: one thread evaluating 2 or 4 independent nonces
  with independent register state chains hides SHA256RNDS2
  latency and beats the OpenSSL-wrapped path end to end.
- Rationale: SHA-NI round pairs have multi-cycle latency and
  the round chain is serial per nonce; interleaving is the
  standard cure and the flags (sha_ni) are present.
- Expected benefit: large. Difficulty: high. Risk: medium
  (register pressure, schedule bookkeeping per stream).
- Validation: prototype in the research tree, differential
  vs hashlib at 100k+, harness benchmark at 1/2/4 streams,
  assembly spill check. Status: OPEN, top priority.

### H-02: Direct single-stream SHA-NI kernel with real schedule instructions
- Statement: a from-scratch SHA-NI kernel using SHA256MSG1
  and SHA256MSG2 for the schedule closes most of the
  intrinsics path's 2x gap (bottleneck B2) even before
  interleaving.
- Rationale: the current intrinsics kernel has 0 sha256msg
  sites and recomputes the schedule in scalar C per nonce.
- Expected benefit: moderate to large. Difficulty: medium.
  Risk: low to medium. Validation: same protocol as H-01;
  it is also H-01's stepping stone. Status: OPEN.

### H-03: Block-2 prefix precomputation (rounds 0..2)
- Statement: precomputing the block-2 state after round 2 per
  template (canonical ceiling, header_and_midstate_analysis)
  saves 3 of 125 per-nonce rounds, about 2.4%.
- Rationale: exact identity; bounded and proven above. The
  intrinsics path currently snapshots after round 1 due to
  RNDS2 pairing; a single scalar round 2 or a repacked layout
  reaches the ceiling. OpenSSL's whole-block Transform API
  cannot express it in the production path.
- Expected benefit: marginal. Difficulty: medium (in a new
  kernel, low). Risk: low. Validation: differential tests
  plus micro-benchmark inside the H-02 kernel. Status: OPEN,
  bundled with H-02.

### H-04: Candidates-only batch output
- Statement: a batch entry point that writes only flags (or
  candidate records) instead of all 32-byte digests cuts
  store traffic 32x on the enumeration path.
- Rationale: batch2 currently writes count x 32 bytes of
  digests that search-style callers never read; at 1M nonces
  that is 32 MB of stores per batch through a contended
  memory system.
- Expected benefit: marginal to moderate. Difficulty: low.
  Risk: low. Validation: new entry point alongside the old,
  differential flags vs existing batch, harness benchmark.
  Status: OPEN.

### H-05: Fewer Python/ctypes crossings, larger spans (h)
- Statement: end-to-end mining throughput rises when batch
  spans grow and per-call overhead (B4: 31 us per crossing)
  is amortized; there is an optimum against template
  freshness.
- Rationale: measured boundary overhead is about 40x one
  hash's amortized cost.
- Expected benefit: marginal (already partly exploited by
  the live miner's 1 s spans). Difficulty: low. Risk: low
  (stale work if oversized). Validation: end-to-end regtest
  mining rate vs span size sweep. Status: OPEN.

### H-06: Ch and Maj reformulations in a hand kernel (c)
- Statement: the proven forms in boolean_equivalence.md
  (Ch_alt 3 ops vs 4, Maj alternatives 4 ops vs 5, shorter
  dependency chains) speed up rounds evaluated outside
  SHA256RNDS2 (prefix rounds, SIMD designs).
- Rationale: equivalence proven three ways in this pass.
- Expected benefit: marginal, and zero inside OpenSSL or
  inside RNDS2 rounds. Difficulty: low where applicable.
  Risk: none to correctness (proven), only wasted effort.
  Validation: assembly diff plus harness benchmark in the
  H-02 kernel context. Status: OPEN, proof complete.

### H-07: Circular 16-word schedule in the CPU C path (d)
- Statement: a circular schedule reduces register and stack
  pressure versus a 64-word array in a hand-written CPU
  kernel (the CUDA source already carries both variants).
- Rationale: 16 live words instead of 64; known technique.
- Expected benefit: marginal to moderate in a scalar kernel;
  irrelevant to the OpenSSL path. Difficulty: medium.
  Risk: low. Validation: variant in the H-02 kernel,
  differential + benchmark + stack-frame comparison.
  Status: OPEN.

### H-08: AVX2 4-way multi-buffer SHA-256 (f)
- Statement: four independent hashes in 256-bit lanes with
  vectorized schedule and rounds beat scalar SHA-NI
  throughput per core.
- Rationale: avx2 present; multi-buffer is a proven design
  family. Counterweight: SHA-NI already does 2 rounds per
  instruction on dedicated hardware.
- Expected benefit: unknown, plausibly negative against
  SHA-NI. Difficulty: high. Risk: medium. Validation:
  prototype, differential, harness. Status: OPEN, ranked
  below the SHA-NI line on prior evidence.

### H-09: AVX-512 multi-buffer SHA-256 (g)
- Statement: the exposed AVX-512 set (f, dq, bw, vl, vbmi2,
  ifma) supports 8-way (or 4-way 512-bit) multi-buffer with
  vector rotates, possibly beating AVX2 width economics.
- Rationale: flags verified present in the guest.
- Expected benefit: unknown. Difficulty: high. Risk: medium
  (frequency and cap behaviour of wide vectors in a shared
  guest is unobservable from inside). Validation: as H-08
  plus a check that wide-vector use does not degrade the
  co-running miner. Status: OPEN.

### H-10: Thread affinity and pinning under the cap (i)
- Statement: pinning worker threads to vCPUs reduces
  migration noise and spread on this VM.
- Rationale: spreads of 27 to 83% in EXP-000 suggest
  scheduling noise dominates some configurations.
- Expected benefit: marginal, mostly variance reduction.
  Difficulty: low. Risk: low (could also pin us onto a busy
  host core). Validation: harness runs with and without
  taskset, spread comparison over more repeats. Status: OPEN.

### H-11: Dynamic chunking for load balance
- Statement: splitting spans into small chunks with atomic
  work claiming smooths the imbalance when host contention
  varies mid-span.
- Rationale: the cap makes per-thread speed time-varying;
  static partitions strand slow chunks.
- Expected benefit: marginal to moderate under contention,
  zero on a quiet machine. Difficulty: medium. Risk: low.
  Validation: harness variant under induced load. Status: OPEN.

### H-12: Compiler programme continued: clang and PGO (e, remainder)
- Statement: clang's codegen or profile-guided optimization
  of the wrapper beats gcc -O3 native.
- Rationale: EXP-001 exhausted the cheap gcc flag space and
  found nothing; clang is not installed here and PGO was not
  tried. Prior probability is low because the hot loop is in
  libcrypto.
- Expected benefit: marginal. Difficulty: low (PGO) to
  medium (obtaining clang at $0). Risk: none (measurement
  only). Validation: EXP-001 protocol extended. Status: OPEN.

### H-13: Timestamp rolling economics (m)
- Statement: rolling nTime extends a template's useful life
  without a new getblocktemplate, at a re-precompute cost of
  3 rounds (prefix state) per roll.
- Rationale: invariance classes in
  header_and_midstate_analysis.md; relevant when the nonce
  space per template is exhausted or GBT is slow.
- Expected benefit: marginal at CPU rates (the 2^32 nonce
  space lasts about 44 minutes at 1.6 MH/s, and longpoll
  already refreshes templates), larger for faster future
  backends. Difficulty: low. Risk: medium (consensus time
  rules must be respected exactly). Validation: regtest
  mining with rolled timestamps accepted by Core. Status: OPEN.

### H-14: Span size vs template freshness (j)
- Statement: there is a measurable optimum span where stale
  work losses balance boundary overhead.
- Rationale: B4 overhead argues large; chain-tip changes
  argue small; the live miner uses about 1 s spans today.
- Expected benefit: marginal. Difficulty: low. Risk: low.
  Validation: regtest and live-miner log analysis across
  span settings. Status: OPEN.

### H-15: Extranonce vs nonce partitioning for multi-worker coverage (l)
- Statement: for N workers on one template, partitioning by
  nonce range beats extranonce-per-worker (which forces a
  new midstate per worker) unless workers are on separate
  machines or templates.
- Rationale: midstate cost is 64 rounds once per template;
  partitioning is free and exact. The lab already partitions
  by worker name per machine on the pool path.
- Expected benefit: marginal (mostly a design guardrail).
  Difficulty: low. Risk: low. Validation: accounting audit
  with Task 003.9 definitions. Status: OPEN.

### H-16: Early target pre-check (k)
- Statement: some cheap partial evaluation could reject most
  candidates before the full outer hash completes.
- Analysis: the target compares the FULL outer digest, whose
  every word depends on all 64 outer rounds and the
  feed-forward. The comparison order (most significant word
  first) does not create a shortcut, because the most
  significant digest word is only known after the final
  round. No exact partial check is known; this entry exists
  to record the argument and catch any future proposal
  against it.
- Expected benefit: none expected (likely refutation).
  Difficulty: low (argument), high (any real counterexample
  would be a research result). Risk: high if misapplied
  (probabilistic filtering is banned). Status: OPEN as an
  analysis item only; no implementation authorized without
  an exactness proof.

### H-17: Dual-template interleaving
- Statement: interleaving two templates' nonces in one
  thread (two midstates) hides latency like H-01 while also
  diversifying template staleness.
- Rationale: same latency logic as H-01 with a pipeline
  benefit; costs a second state set.
- Expected benefit: unknown, subsumed by H-01 if streams
  already saturate. Difficulty: medium. Risk: low.
  Validation: after H-01 results. Status: OPEN, deferred.

### H-18: ADX/BMI2-assisted round arithmetic
- Statement: adcx/adox parallel carry chains or BMI2
  rotates (rorx) shave instructions in a scalar kernel.
- Rationale: adx and bmi2 are present; SHA-256 adds are
  mod 2^32 without carries between words, so the carry-chain
  benefit is doubtful; rorx could cut rotate sequences in
  non-SHA-NI code.
- Expected benefit: marginal to none. Difficulty: medium.
  Risk: low. Validation: micro-kernel comparison. Status: OPEN.

### H-19: Output buffer alignment and page placement
- Statement: aligning batch output buffers to cache lines or
  using large pages measurably changes batch throughput.
- Rationale: 32 MB of digest stores per 1M batch is the one
  real memory stream in the system.
- Expected benefit: marginal. Difficulty: low. Risk: none.
  Validation: harness A/B with aligned allocator. Status:
  OPEN, largely moot if H-04 lands.

### H-20: GPU research track (Stage 10)
- Blocked: no NVIDIA GPU exists on this VM (Tasks 002/003
  gates remain UNVERIFIED). The CUDA design work (midstate,
  candidate filtering, persistent context) is ready to
  measure the day hardware appears. Status: BLOCKED on
  hardware, research-only until then.

### H-21: FPGA pipelined compression research (Stage 10)
- The lab has RTL and a simulated netlist (fpga/, asic/);
  no board exists. Research questions (round pipelining,
  timing closure) are documented in results/FPGA_RESULTS.md
  and results/ASIC_RESULTS.md. Status: BLOCKED on hardware.

### H-22: ASIC datapath research (Stage 10)
- Pre-layout design package exists; no PDK or tapeout path
  at $0. Research-only. Status: BLOCKED.

### H-23: Hybrid CPU plus accelerator work split (Stage 10)
- Depends on H-20 to H-22 having a real second device.
  Status: BLOCKED on hardware.

### H-24: Statistical or reduced-round shortcut at full rounds
- REJECTED, settled by prior lab evidence: reduced-round
  bias is measurable at 16 to 20 rounds and dead by round 24
  (results/RESEARCH.md), winners follow the geometric law,
  and full SHA-256d is 64 rounds twice. See
  rejected_hypotheses.md. Status: REJECTED, do not relitigate
  without new evidence of a different kind.
