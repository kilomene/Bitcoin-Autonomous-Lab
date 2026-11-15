# VM Resource Capacity Report

Deliverable: VM_RESOURCE_CAPACITY_REPORT.md (Master
Assignment BR-009, VM and resource capacity).
Date: 2026-11-15. Primary source: EXP-031, CPU and Virtual
Machine Characterisation (research/sha256d/exp031/
CPU_VM_CHARACTERIZATION.md, raw results in its
RAW_RESULTS directory), supplemented by the EXP-028
two-host record and the EXP-032 session conditions. No
benchmark was run for this report.

Standing condition of every EXP-031 measurement: the live
miner (v512dual backend, autopilot-supervised), the pruned
mainnet node in initial block download, and the rest of
the agent environment were running throughout and were
never paused or restarted. Every rate in this report is an
alongside-production rate on a contended shared machine,
not an idle-machine figure. This is deliberate: the
capacity that matters for planning is the capacity the
miner actually gets.

## 1. What the guest claims, and what it delivers

Claimed by the guest (read from system interfaces; in a
guest these are the virtualisation layer's claims, not
physical facts):

- 4 vCPUs: online list 0 to 3, affinity 0 to 3,
  Cpus_allowed_list 0 to 3.
- Topology as presented: 1 package, 4 distinct core ids,
  1 thread per core, 1 NUMA node. Host physical cores:
  unknown; no guest interface exposes them. The CPU model
  string's core count ("126-Core") is the host CPU model
  name, not a count of anything assigned to this guest,
  and is not used as evidence.
- Guest-reported cpu MHz: 1497.749 on all 4 CPUs, a
  nominal TSC-derived figure. No cpufreq policies are
  exposed; the actual core frequency under load is
  unknown and no guest interface measures it.

Delivered (measured by the EXP-031 load probe, production
ComputeEngine on the v512dual backend, fixed range of
16,777,216 nonces per configuration, configurations run
strictly sequentially; the engine's attempted count
equalled the range in every run):

| Run | 1 thread | 2 threads | 4 threads |
|---|---|---|---|
| Run 1 (2026-11-15T09:23:01Z) | 5,185,651 H/s | 9,359,242 H/s (scaling 1.805) | 9,916,365 H/s (scaling 1.912) |
| Run 2 (2026-11-15T09:23:31Z) | 5,497,152 H/s | 11,209,065 H/s (scaling 2.039) | 10,251,609 H/s (scaling 1.865) |

- Thread scaling saturates at about 2 effective CPUs.
  Going from 2 to 4 threads gained nothing in run 1 and
  slightly less than nothing in run 2. The effective-CPU
  estimate (aggregate rate divided by the 1-thread rate,
  labelled estimated wherever used) is 1.81 to 2.04 at 2
  threads and 1.87 to 1.91 at 4 threads.
- Single-thread SHA-256d rate alongside production load:
  5.19 to 5.50M H/s per thread (measured). These are
  category E figures (complete production search through
  ComputeEngine), not isolated-kernel figures.
- Aggregate ceiling alongside production load: about 9.9
  to 11.2M H/s from one engine process, reached at 2
  threads.
- The production thread tuner independently agrees: during
  these very runs it auto-tuned the DualMask search to 2
  threads in run 1 and 4 in run 2, its choices moving with
  the same minute-to-minute variance.
- Run-to-run variance at fixed configuration is large: the
  2-thread rate differed by about 20 percent between runs
  30 seconds apart. Any benchmark on this VM that does not
  use paired, repeated measurement (the EXP-017 protocol)
  will read this variance as signal.

## 2. Contention: the baseline is already busy

Before any probe load (measured, 5-second /proc/stat
intervals):

- Run 1 snapshot: aggregate busy 63.58 percent (user
  48.95, system 12.32, idle 31.01, iowait 5.41, steal
  1.40). Load average 7.47 / 12.53 / 11.51. Context
  switches 15,520 per second.
- Run 2 snapshot: aggregate busy 60.85 percent (user
  46.50, system 10.65, idle 9.55, iowait 29.60, steal
  1.85). Load average 7.04 / 11.80 / 11.31. Context
  switches 27,049 per second.
- Baseline utilisation is therefore 61 to 64 percent busy
  on 4 claimed vCPUs, with load averages of 7.0 to 7.5
  (1 minute) and 11.3 to 12.5 (15 minutes). CPU pressure
  (PSI "some") averaged 79 to 86 percent over 10-second
  windows; "full" was 0.00 throughout.
- The contenders are visible: the live miner itself, the
  syncing node's validation bursts (the swing between
  runs, idle 31 to 10 percent and iowait 5 to 30 percent,
  is the node's validation rhythm), and the surrounding
  agent workload (15,000 to 27,000 context switches per
  second at idle probe time).
- Steal is real but secondary: 1.4 to 2.7 percent in the
  measured windows, and it did not grow from 1 to 4
  threads under added load. In these windows the ceiling
  behaves more like a capacity allocation than like steal
  bursts. The mechanism is unknown from inside: /sys/fs/
  cgroup/cpu.max does not exist at the visible cgroup
  root (own cgroup is "0::/"), so the quota value and
  even its mechanism cannot be read from the guest.

Answers to the capacity questions, as EXP-031 recorded
them:

- CPU-limited? Yes, in effect. The usable compute ceiling
  is roughly half the claimed vCPU count, and it is the
  binding constraint on mining throughput on this machine.
- Oversubscribed? The guest cannot see the host, so host
  oversubscription is unknown. Inside the guest, the
  evidence is consistent with a shared-CPU allocation
  well below 4 dedicated CPUs imposed above the guest.
- Contending? Yes, heavily, from inside the guest itself.

## 3. Virtualisation layers

Sources disagree and are reported verbatim, not merged:

- /proc/cpuinfo carries the "hypervisor" flag.
- systemd-detect-virt reports systemd-nspawn: this
  process runs in an nspawn container, the innermost
  layer.
- DMI (hypervisor-supplied strings): sys_vendor "Cloud
  Hypervisor", product_name "cloud-hypervisor".
- lscpu reports hypervisor vendor "KVM", virtualization
  type "full".
- /sys/hypervisor is absent; /proc/1/comm is "systemd".

Operationally: at least two boundaries (container, then
VM) sit between the mining process and the host, and the
restrictions observed in this report (perf counters,
missing cgroup files) are consistent with that layering.

## 4. Instruction set available to dispatch

On the EXP-031 host (AMD EPYC 9D25 guest): AVX-512F, DQ,
CD, BW, VL, VBMI, VBMI2, IFMA, VNNI, BF16, BITALG,
VPOPCNTDQ, VP2INTERSECT, plus AVX, AVX2, SHA-NI, AES,
VAES, GFNI, PCLMULQDQ, VPCLMULQDQ, BMI1, BMI2, ADX, FMA,
SSE4.2, AVX-VNNI, XSAVE (133 flags in the raw record). The
production dispatch requirements are met with room to
spare: the engine's own CPUID probe selected v512dual
during the load probe.

Caveat: flags in a guest are what the hypervisor chooses
to expose. They are reliable for dispatch decisions inside
this guest (the production probe verifies by executing a
self-test, not by trusting flags) and say nothing about
any other host.

## 5. Host alternation across replacements

This VM is replaced frequently, and the replacement may
carry a different CPU. Two host shapes are characterised
in the programme record:

- AMD EPYC 9D25: full AVX-512 set including VBMI, VBMI2,
  IFMA, plus SHA-NI and GFNI. This is the EXP-031 and
  EXP-032 host, and the host at the time of this report.
- Intel Xeon Platinum 8321HC: AVX-512F, BW, VL, VNNI. No
  SHA extensions, no VBMI. On record from EXP-028: the
  same restricted-flag production build selected v512 and
  kept mining there, while research libraries built with
  -march=native or SHA instructions faulted with SIGILL.
  The audit-era test record adds the same shape from the
  other side: test-cpu-correction and test-task003 SIGILL
  on the Intel host because they exercise the -msha
  intrinsics library, and pass on the AMD host. These are
  environment failures, host-shaped, not code defects.

Consequences: EXP-031's numbers characterise the AMD
shape. The Intel shape's effective-CPU count has not been
load-probed to the same depth, and no figure in this
report should be read as measured on the Intel host
unless it says so. A benchmark campaign spanning a host
change is two campaigns; pooling across the change is
prohibited (HASHRATE_MEASUREMENT_SPECIFICATION, section
6).

## 6. Memory, cache, disk, thermal, counters

Memory (read from system): MemTotal 8,124,900 kB (about
7.75 GiB); MemAvailable about 2.1 GiB at probe time; swap
1 GiB, mostly free. The host may balloon or overcommit
behind these figures; that is unknown.

Cache geometry as the guest presents it (cpu0): L1d
48 KiB, L1i 32 KiB, L2 1024 KiB, L3 32768 KiB, one NUMA
node. The guest's own fields are not self-consistent (the
shared_cpu_list fields claim L1 and L2 are shared across
CPU pairs 0-1 while the topology fields claim 1 thread per
core with distinct core ids). Treat cache sizes as
approximate guest claims; prefer measured working-set
behaviour over these numbers for any cache-blocking
decision.

Disk: EXP-031 did not characterise storage. Point
observation at the time of this report (2026-11-15, this
host): the workspace filesystem is 150 GB total with
about 47 GB free (69 percent used). The mining workload
is not disk-bound in any measurement on record; the
pruned mainnet node's disk use is bounded by its
prune=550 configuration. No storage performance claim is
made.

Thermal: no thermal zones are exposed, per-CPU
thermal_throttle counters are absent. Whether the host
throttles, and the temperature of anything, is unknown
from this guest. Sustained-rate decay, if ever observed
in long benchmarks, cannot be attributed to thermals from
inside; it would have to be reported as unexplained
variance.

Performance counters: not accessible. perf_event_paranoid
is 4 (the most restrictive setting); the perf userspace
tool is not installed; a real trial of perf_event_open
for a hardware cycles counter and a software CPU-clock
counter, both from uid 0, failed with errno 13
(Permission denied). No cycles, IPC or cache-miss counters
are available here. Kernel work must be compared by
wall-clock paired measurement and instruction-count
analysis of the compiled code, as EXP-017 and the op-count
censuses already do.

## 7. Repeatability evidence

Profiler: two runs 42 seconds apart. Of 336 flattened leaf
fields, 282 are byte-identical, including every identity,
topology, instruction-set, virtualisation, cgroup-structure
and thermal field. Every differing field is either a
time-varying measured quantity or one disclosed
evidence-class correction in the tool between runs.

Load probe: two runs 30 seconds apart reproduce the
scaling shape exactly (saturation at 2 threads, nothing
from 4) while absolute rates move by up to about 20
percent. The tool is repeatable; the machine's available
capacity is not constant, and the records show both facts
separately.

## 8. What capacity planning may and may not conclude

May conclude, from this characterisation:

- Plan this VM as a 4-vCPU guest with about 2 effective
  CPUs of usable mining capacity under current load.
- Plan per-VM mining throughput on the measured contended
  bases in section 9, labelled as contended, never on the
  claimed vCPU count and never on an idle-machine figure
  that does not exist.
- Treat thread count as a measured per-host setting (the
  production tuner already does), not as a direction of
  improvement: more threads than the tuned count buy
  contention-shaped variance on this VM class.
- Treat the instruction set as a dispatch input verified
  by probe at runtime, because the host alternates
  (section 5).

May not conclude:

- That 4 vCPUs of capacity exist. They do not, measurably.
- That any per-VM rate is a hardware property. Every rate
  here is a contended measurement alongside a live miner,
  a syncing node and an agent workload; the same VM
  quieter would read higher, and no quieter reading
  exists in this programme.
- That fleet throughput scales linearly from a per-VM
  rate without an efficiency factor. The counts in
  section 9 assume sustained rates with no thermal or
  contention decay and 100 percent fleet efficiency; a
  real deployment multiplies counts by 1/efficiency.
  Multi-machine overhead, propagation latency and linear
  scaling are UNVERIFIED in this programme (EXP-035
  proved its allocator design in-process only; EXP-029
  proved coverage by property test, with no multi-machine
  run).
- That the ceiling mechanism is known. It is not: no
  quota file is visible, steal is modest, and the report
  records the ceiling as measured behaviour with an
  unknown mechanism.

## 9. Gap arithmetic to the targets

Targets stand at full height: 500 GH/s minimum system
objective, 140 TH/s larger objective (140 TH/s is 280
times 500 GH/s). The counts below are arithmetic from
measured per-VM rates. They are system counts, never
achieved performance, and no part of either target is
claimed.

Basis 1: the live miner's post-DualMask session rate,
20.6M H/s (measured observation: live session rates of
20.6 to 21.5M H/s observed on the AMD host after the
EXP-026 integration, single live sessions under
contention, not a benchmark; category E observation).

- 500 GH/s: 5.0e11 / 20.6e6 = 24,272, about 24,000 such
  systems. At the 21.5M H/s end of the observed range:
  23,256.
- 140 TH/s: 1.4e14 / 20.6e6 = 6,796,117, about 6.80
  million such systems.

Basis 2: the best complete production search rate
measured under the EXP-017 protocol in EXP-032, session
median 14.8M H/s (2 threads, contended, alongside the
live miner itself; category E, AMD host).

- 500 GH/s: 5.0e11 / 14.8e6 = about 33,800 such VMs.
- 140 TH/s: 1.4e14 / 14.8e6 = about 9.5 million such VMs.

The two bases answer different questions and are not
interchangeable: basis 1 is what the running system
sustains as observed; basis 2 is what a controlled paired
measurement of the same search path reads while the
system also runs. Both are stated so neither can be
quoted without its conditions. For completeness, the
EXP-031 load probe's own aggregate (9.9 to 11.2M H/s from
a second engine process alongside the live miner) would
give about 45,000 to 50,000 systems for 500 GH/s; it is
recorded here as the most conservative basis, not used as
a headline because the probe process shares the VM with
the miner it would be added to.

What would change these counts: a verified per-core rate
outside the current families' envelope, or a deployment
of fleet scale. Neither exists. EXP-032's verified gains
(AVX2 1.409x, SHA-NI streams 2.861x, both over the C
fallback, batch scope) are fallback gains for other host
classes and narrow no part of the gap on AVX-512 hosts.
The binding constraints remain the ones EXP-020 and
EXP-027 established (the round at its vocabulary optimum,
the closed representation spaces) plus this VM's roughly
2 effective CPUs.

## 10. Unknown and not-accessible register (from EXP-031)

Unknown: host physical core count and host topology;
cgroup CPU quota value and mechanism (cpu.max absent at
the visible root); cpu.max.burst; memory.max; cgroup
throttling counts; actual core frequency under load; host
temperature and host throttling state; host
oversubscription ratio; the layer that blocks
perf_event_open.
Not accessible: cgroup v1 cpu hierarchy; per-CPU cpufreq
and scaling governor data; thermal zones and
thermal_throttle counters; hardware performance counters
(trial returned permission denied); the perf userspace
tool (absent).
Not applicable: ARM SHA extensions (x86_64 machine).

## 11. Bottom line

This VM is a 4-vCPU guest delivering about 2 effective
CPUs under a 61 to 64 percent busy baseline, with a full
AVX-512 plus SHA-NI instruction set on the AMD host shape
and AVX-512F/BW only on the Intel host shape, about 7.75
GiB of guest memory, no hardware counters, no thermal
visibility, no visible quota file, and minute-scale
capacity variance large enough that only paired repeated
measurement means anything. Capacity planning must use
the measured contended rates, labelled as such, and must
not convert claimed vCPUs into capacity.
