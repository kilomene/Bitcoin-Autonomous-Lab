# CPU Microarchitecture Profile (Stage 1)

Measured 2026-11-14 on the live lab VM with
tools/probe_machine.py. Raw output:
tools/machine_probe_2026-11-14.json. Reproduce any time with:

    python3 research/sha256d/tools/probe_machine.py

Nothing in this profile is assumed; where the hypervisor hides a
fact, that is stated.

## Processor as exposed

- Model: AMD EPYC 9D25 126-Core Processor (family 26, model 17),
  KVM full virtualization.
- vCPUs: 4 online, topology as exposed: 4 cores x 1 thread,
  1 socket, 1 NUMA node. No SMT sibling is exposed.
- Effective capacity: the VM is capped near 1.5 shared CPUs on a
  contended host. Load average (1m) recorded by the probe
  session saved in tools/machine_probe_2026-11-14.json was
  8.66, from the live mainnet miner, the syncing mainnet node,
  and host neighbours we cannot see. The EXP-000 baseline
  sessions later the same day ran under still heavier
  contention (load average above 10, noted qualitatively in
  baseline_performance.md): load on this host drifts between
  sessions, so each measurement must cite its own session.
  Every benchmark in this programme must be read with that
  ceiling. (Reconciliation, Stage 5 authorization 2026-11-14:
  an earlier revision of this file quoted a load of 10.7 for
  the probe session. No saved measurement supports 10.7 as
  the probe-session value; the JSON record, 8.66, is the
  sourced figure, and the above-10 observation belongs to
  the separate baseline sessions.)
- Frequency: /proc/cpuinfo reports 1497.75 MHz in every sample
  taken (5 samples over 1 s). No cpufreq sysfs is exposed, so
  scaling behaviour, boost states, and throttling cannot be
  observed from inside the guest. The constant reading is
  consistent with a host-side cap, not a measured core clock.
- Caches as exposed by sysfs (per cpu0, shared lists noted):
  L1d 48 KiB (shared 0-1), L1i 32 KiB (shared 0-1), L2 1 MiB
  (shared 0-1), L3 32 MiB (shared 0-3). lscpu aggregates these
  as L1d 96 KiB, L1i 64 KiB, L2 2 MiB, L3 32 MiB across
  instances. A SHA-256 worker's hot state is far below L1 size;
  cache capacity is not a mining constraint here.
- Memory: 8,124,900 KiB total (about 7.7 GiB usable class),
  1 GiB swap.
- Memory bandwidth micro-measurement: STREAM-style memcpy over a
  128 MiB working set (4x L3), single stream, 5 repetitions:
  2.739 GB/s as recorded by the probe session in
  tools/machine_probe_2026-11-14.json, under the contention
  above. This is a floor estimate on a capped, shared VM, not
  the silicon's capability. (Reconciliation, Stage 5
  authorization 2026-11-14: an earlier revision quoted about
  4.0 GB/s. No saved probe output supports that figure; the
  JSON record, 2.739 GB/s, is the only sourced measurement
  and replaces it.)

## Instruction sets that matter for SHA-256

Present (from /proc/cpuinfo flags, verified by the probe):
sha_ni, aes, vaes, gfni, vpclmulqdq, bmi1, bmi2, adx, fma,
movbe, avx, avx2, and a wide AVX-512 set: avx512f, avx512dq,
avx512cd, avx512bw, avx512vl, avx512ifma, avx512vbmi,
avx512_vbmi2, avx512_vnni, avx512_bitalg, avx512_vpopcntdq,
avx512_bf16, avx512_vp2intersect, plus avx_vnni.

Consequences:
- SHA-NI is present and is what OpenSSL dispatches to; it is the
  incumbent to beat.
- ADX (adox/adcx) is present, relevant to multi-precision style
  addition chains, marginally relevant to SHA-256 round adds.
- AVX-512 byte-shuffle machinery (vbmi2 includes vprold-style
  rotates via avx512vl + vbmi2 permutations) makes a 4-way or
  8-way multi-buffer SHA-256 conceivable; whether it beats
  SHA-NI on this core is an experiment (H-05, H-06), not a
  prior.
- vaes/gfni do not apply to SHA-256 rounds directly.

## Toolchain

- gcc 13.3.0 (Ubuntu 24.04). clang: NOT installed on this VM
  (checked PATH and /usr/bin); compiler comparisons are
  gcc-only until a clang appears, which limits EXP-001's sweep
  to gcc flag variants.
- OpenSSL 3.0.13 (libcrypto carries the SHA-NI compression:
  128 sha256rnds2 sites by objdump count).
- Python 3.12.3. CUDA toolkit 12.9.86 exists repo-locally
  (.local/cuda129) but there is no GPU; out of scope here.
- perf counters: not usable in this guest (documented in
  Task 001: perf absent, perf_event_paranoid 4). IPC, cycles
  per hash, and cache-miss rates are therefore unmeasured in
  this programme until the environment changes; wall-clock
  throughput with repeats and spreads is the evidence standard.

## What this profile selects for

1. SHA-NI first: any new CPU path must beat OpenSSL's SHA-NI
   compression as wrapped by bal_batch.c, measured end to end.
2. Few threads, well fed: the cap punishes oversubscription;
   2 threads is the tuned production setting.
3. Latency-chain thinking: with about 125 compression rounds
   per nonce and a serial round dependency, interleaving
   independent streams (H-01) is the classic lever and the
   registry's top hypothesis.
4. Zero faith in nominal specs: the 126-core host name, the
   4 exposed vCPUs, and the 1.5-CPU effective cap are three
   different numbers; only the third one mines.
