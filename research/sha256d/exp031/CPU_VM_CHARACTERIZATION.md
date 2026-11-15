# EXP-031: CPU and Virtual Machine Characterisation

Experiment: EXP-031 (EXP-030 programme, Phase C).
Date: 2026-11-15. Hostname: htch-runtime.
Tools: tools/vm_profile.py (capability discovery),
tools/load_probe.py (resource characterisation benchmark).
Raw results (append-only, timestamped):
RAW_RESULTS/profile_20261115T092202Z.json,
RAW_RESULTS/profile_20261115T092244Z.json,
RAW_RESULTS/loadprobe_20261115T092301Z.json,
RAW_RESULTS/loadprobe_20261115T092331Z.json.

Evidence classes used throughout, per the directive:
measured (this tool acted and observed), read-from-system
(read verbatim from a system interface; in a guest these are
the virtualisation layer's claims, not physical facts),
unknown (interface exists, no usable value), not-accessible
(interface absent or blocked). Estimates derived from
measurements are labelled estimated and are never presented
as hardware properties.

Standing condition of every measurement below: the live
miner (v512dual backend, autopilot-supervised), the pruned
mainnet node in initial block download, and the rest of this
agent environment were running throughout and were never
paused or restarted. Every rate is an alongside-production
rate on a contended shared machine, not an idle-machine
figure.

## Verdict: what this VM actually is

Claimed by the guest: 4 vCPUs (online list 0-3, affinity
0-3, Cpus_allowed_list 0-3, all read-from-system).

Measured capacity: thread scaling of the production
SHA-256d engine saturates at about 2 effective CPUs. Across
two load-probe runs, going from 2 to 4 threads gained
nothing (run 1: 9.36M to 9.92M H/s; run 2: 11.21M to
10.25M H/s, slightly worse). The effective-CPU estimate
(aggregate rate divided by the 1-thread rate, labelled
estimated) is 1.81 to 2.04 at 2 threads and 1.87 to 1.91
at 4 threads.

Answers to the directive's three questions:

- CPU-limited? Yes, in effect. Whatever the mechanism, the
  usable compute ceiling is roughly half the claimed vCPU
  count, and it is the binding constraint on mining
  throughput on this machine.
- Oversubscribed? The guest cannot see the host, so host
  oversubscription is unknown. Inside the guest, the
  evidence is consistent with a shared-CPU allocation well
  below 4 dedicated CPUs imposed above the guest: scaling
  stops near 2 effective CPUs while steal stays modest
  (1.4 to 2.7 percent in the measured windows). A cgroup
  quota is NOT visible from inside: /sys/fs/cgroup/cpu.max
  does not exist at the visible cgroup root (own cgroup is
  "0::/"), so the quota value and even its mechanism are
  unknown from guest interfaces. NOVA must plan against the
  measured ceiling, not against the absent file.
- Contending? Yes, heavily, from inside the guest itself.
  Before any probe load, baseline utilisation measured
  61 to 64 percent busy with load averages of 7.0 to 7.5
  (1 minute) and 11.3 to 12.5 (15 minutes) on 4 vCPUs.
  CPU pressure (PSI "some") averaged 79 to 86 percent over
  10-second windows. The contenders are visible: the live
  miner itself, the syncing node's validation bursts
  (iowait hit 24 to 34 percent in several windows), and
  the surrounding agent workload (15,000 to 27,000 context
  switches per second at idle probe time). Steal is real
  but secondary in these windows.

## Identity and topology (all read-from-system)

- Vendor: AuthenticAMD. Model name: AMD EPYC 9D25
  126-Core Processor. Family 26, model 17, stepping 0.
  Microcode (guest-visible string): 0x1000065.
  Architecture: x86_64. Kernel: 7.0.0-44-generic.
- Logical processors: 4 (os.cpu_count, online list,
  affinity syscall measured at 4 CPUs: 0, 1, 2, 3).
- Guest-reported topology: 1 package, 4 distinct core
  ids, thread_siblings_list shows 1 thread per core;
  lscpu restates 1 socket, 4 cores per socket, 1 thread
  per core, 1 NUMA node.
- Host physical cores: unknown. No guest interface
  exposes host topology, and the model name's "126-Core"
  is the host CPU model string, not a count of anything
  assigned to this guest. It is deliberately not used
  as evidence.

## Virtualisation layers (sources disagree; reported verbatim)

- /proc/cpuinfo carries the "hypervisor" flag
  (read-from-system).
- systemd-detect-virt reports: systemd-nspawn. This is
  the innermost layer: this process runs in an nspawn
  container.
- DMI (hypervisor-supplied strings): sys_vendor "Cloud
  Hypervisor", product_name "cloud-hypervisor",
  bios_vendor "cloud-hypervisor".
- lscpu reports: Hypervisor vendor "KVM",
  Virtualization type "full".
- /sys/hypervisor: absent. Container markers: no
  /.dockerenv, no /run/.containerenv, no container
  environment variable; /proc/1/comm is "systemd".

These are three layers named by three sources (container
runtime, DMI firmware strings, kernel CPU vendor data).
The profiler records each claim with its source and does
not merge them into one asserted hypervisor identity.
What matters operationally for NOVA: at least two
boundaries (container, then VM) sit between the mining
process and the host, and restrictions observed below
(perf counters, missing cgroup files) are consistent
with that layering.

## Instruction sets (read-from-system, /proc/cpuinfo flags)

AVX-512 subsets, all present: F, DQ, CD, BW, VL, VBMI,
VBMI2, IFMA, VNNI, BF16, BITALG, VPOPCNTDQ, VP2INTERSECT.
Also present: AVX, AVX2, SHA-NI, AES, VAES, GFNI,
PCLMULQDQ, VPCLMULQDQ, BMI1, BMI2, ADX, FMA, SSE4.2,
AVX-VNNI, XSAVE. 133 flags total in the raw record.

Relevance to kernel dispatch (EXP-032): the production
dispatch requirements are met on this guest with room
to spare. v512dual search and the EXP-022 flags batch
require exactly AVX-512F + AVX-512BW (both present, and
the engine's own CPUID probe selected both during the
load probe). SHA-NI is present, so the streams backend
remains a viable fallback family. VBMI, VBMI2, IFMA and
GFNI are present for research kernels, subject to the
EXP-027 closures on their usefulness. ARM SHA
extensions: not-applicable on x86_64, reported
explicitly as the directive requires.

Caveat: flags in a guest are what the hypervisor chooses
to expose; they are reliable for dispatch decisions
inside this guest (the production probe verifies by
executing, not by trusting flags) and say nothing about
any other host.

## Frequency

- Guest-reported cpu MHz: 1497.749 on all 4 CPUs
  (read-from-system). On this class of guest this is a
  nominal TSC-derived figure.
- cpufreq: no policies exposed (empty
  /sys/devices/system/cpu/cpufreq), no per-CPU cpufreq
  directories. Scaling driver, governor, and min/max
  frequencies: not-accessible.
- Actual core frequency under load: unknown. No guest
  interface measures it. Per-thread hash rates in the
  load probe are the only load evidence and are not a
  frequency.

## cgroup state

- Unified cgroup v2 is the visible hierarchy
  (cgroup2 mount, nsdelegate). No v1 cpu hierarchy is
  mounted (not-accessible).
- Own cgroup: "0::/" (the visible root).
- cpu.max: not present at the visible root. Value:
  unknown. A quota imposed by a parent outside the
  visible namespace cannot be read from here, and the
  measured scaling ceiling (about 2 effective CPUs)
  exists whether or not such a file would name it.
- cpu.max.burst: not present (unknown). memory.max:
  not present (unknown).
- cpu.stat at this level carries only usage counters
  (usage_usec, user_usec, system_usec); it reports no
  nr_periods, nr_throttled or throttled_usec, so cgroup
  throttling counts are unknown from this interface.
- CPU pressure (PSI, read-from-system): "some" avg10
  86.37 in run 1 and 79.30 in run 2; avg300 about 83.
  Tasks in this environment spend most wall time with
  runnable work stalled on CPU availability, from the
  combined in-guest load. "full" is 0.00 throughout.

## Utilisation snapshots (measured, 5-second /proc/stat intervals)

Run 1 (09:22:03Z): aggregate busy 63.58 percent, user
48.95, system 12.32, idle 31.01, iowait 5.41, steal
1.40. Load average 7.47 / 12.53 / 11.51. Context
switches 15,520 per second.
Run 2 (09:22:45Z): aggregate busy 60.85 percent, user
46.50, system 10.65, idle 9.55, iowait 29.60, steal
1.85. Load average 7.04 / 11.80 / 11.31. Context
switches 27,049 per second.

The swing between runs (idle 31 to 10 percent, iowait
5 to 30 percent) is the syncing node's validation
rhythm, and is itself characterisation data: capacity
available to mining on this VM varies minute to minute
with node I/O and CPU bursts.

## Load probe: what NOVA can actually use (measured)

Fixed workload: production ComputeEngine (backend
v512dual, selected by the production probe), fixed
range of 16,777,216 nonces per configuration, target 1
(full scan; attempted count returned by the engine is
the authority and equalled the range in every run).
Configurations run strictly sequentially. Full records:
the two loadprobe JSON files in RAW_RESULTS.

Run 1 (09:23:01Z):
- 1 thread: 5,185,651 H/s; window busy 60.9 percent,
  steal 2.10 percent, iowait 34.1 percent.
- 2 threads: 9,359,242 H/s (scaling 1.805); busy 77.0,
  steal 2.65, iowait 10.7.
- 4 threads: 9,916,365 H/s (scaling 1.912); busy 64.1,
  steal 1.62, iowait 20.8.

Run 2 (09:23:31Z):
- 1 thread: 5,497,152 H/s.
- 2 threads: 11,209,065 H/s (scaling 2.039); steal
  2.00 percent.
- 4 threads: 10,251,609 H/s (scaling 1.865); steal
  1.38 percent.

Interpretation:
- Single-thread SHA-256d rate alongside production
  load: 5.19 to 5.50M H/s per thread (measured).
- Aggregate ceiling alongside production load: about
  9.9 to 11.2M H/s from this probe process, reached at
  2 threads. The fourth and third threads buy nothing
  measurable. Effective CPUs (estimated): about 1.9
  to 2.0, against 4 claimed vCPUs.
- The production thread tuner independently agrees:
  during these very runs it auto-tuned the DualMask
  search to 2 threads in run 1 (probe 13.53M H/s in
  its own short window) and 4 in run 2 (9.58M H/s),
  i.e. its choices move with the same minute-to-minute
  variance.
- Steal under added load stayed in a narrow band
  (1.4 to 2.7 percent) and did not grow from 1 to 4
  threads. In these windows the ceiling behaves more
  like a capacity allocation than like steal bursts;
  the mechanism remains unknown from inside (see
  cgroup section).
- Run-to-run variance at fixed configuration is
  large (2-thread rate differed by about 20 percent
  between runs 30 seconds apart). Any future benchmark
  on this VM that does not use paired, repeated
  measurement (the EXP-017 protocol) will read this
  variance as signal. This confirms, from the resource
  side, why EXP-017 is the programme's decision rule.

## Performance counters

- perf_event_paranoid: 4 (read-from-system), the most
  restrictive setting.
- The perf userspace tool is not installed.
- Real trial (measured): perf_event_open for a
  hardware CPU-cycles counter and for a software
  CPU-clock counter, both from this process (uid 0),
  both failed with errno 13 (Permission denied).
  Hardware performance counters are therefore
  not-accessible from this environment, most plausibly
  at the container capability boundary; the exact
  blocking layer is unknown.
- Consequence for the programme: no cycles, no IPC,
  no cache-miss counters are available here. Kernel
  work must be compared by wall-clock paired
  measurement and instruction-count analysis of the
  compiled code, as EXP-017 and the Phase 6B asm
  audits already do.

## Thermal

- Thermal zones: none exposed (not-accessible).
  Cooling device entries 0 to 3 exist but carry no
  temperature information without zones.
- Per-CPU thermal_throttle counters: absent
  (not-accessible).
- Whether the host throttles, and any temperature of
  anything: unknown from this guest. Sustained-rate
  decay, if ever observed in long benchmarks, cannot
  be attributed to thermals from inside; it would
  have to be reported as unexplained variance.

## Memory and cache (read-from-system)

- Guest-visible memory: MemTotal 8,124,900 kB (about
  7.75 GiB), MemAvailable about 2.1 GiB at probe time,
  swap 1 GiB mostly free. The host may balloon or
  overcommit behind these figures; that is unknown.
- Cache geometry as the guest presents it (cpu0):
  L1d 48 KiB, L1i 32 KiB, L2 1024 KiB, L3 32768 KiB.
  One NUMA node.
- Internal tension worth recording: the cache
  shared_cpu_list fields claim L1 and L2 are shared
  across CPU pairs (0-1), while the topology fields
  claim 1 thread per core with distinct core ids, and
  lscpu reports L1/L2 in 2 instances across 4 CPUs.
  Guest-presented geometry is not self-consistent
  enough to plan cache blocking from; treat cache
  sizes as approximate guest claims, and prefer
  measured working-set behaviour (as in EXP-005 and
  EXP-018) over these numbers.

## Repeatability evidence

Profiler: two runs 42 seconds apart. Of 336 flattened
leaf fields, 282 are byte-identical, including every
identity, topology, instruction-set, virtualisation,
cgroup-structure and thermal field. Every differing
field is either a time-varying measured quantity
(utilisation percentages, PSI averages, load average,
free memory, own-cgroup usage counters, timestamps)
or one of two evidence-class corrections: the tool was
edited between the runs so that cpu.max.burst and
memory.max report unknown (file absent) instead of a
null read-from-system; that edit is disclosed here
rather than hidden, and run 2 carries the corrected
classes.

Load probe: two runs 30 seconds apart reproduce the
scaling shape exactly (saturation at 2 threads,
nothing from 4) while absolute rates move by up to
about 20 percent. The tool is repeatable; the machine's
available capacity is not constant, and the records
show both facts separately.

## Unknown and not-accessible register (complete)

Unknown: host physical core count and host topology;
cgroup CPU quota value and mechanism (cpu.max absent
at the visible root); cpu.max.burst; memory.max;
cgroup throttling counts (not reported at this level);
actual core frequency under load; host temperature
and host throttling state; host oversubscription
ratio; the layer that blocks perf_event_open.
Not-accessible: cgroup v1 cpu hierarchy; per-CPU
cpufreq and scaling governor data; thermal zones and
thermal_throttle counters; hardware performance
counters (trial returned permission denied); the
perf userspace tool (absent).
Not-applicable: ARM SHA extensions (x86_64 machine).

## Bottom line for NOVA planning

Plan this VM as a 4-vCPU guest with about 2 effective
CPUs of usable mining capacity under current load, a
full AVX-512 plus SHA-NI instruction set for dispatch,
about 5.2 to 5.5M H/s per engine thread and about
10 to 11M H/s aggregate from one engine process
alongside the live miner and the syncing node, no
hardware counters, no thermal visibility, no visible
quota file, and minute-scale capacity variance large
enough that only paired repeated measurement means
anything. The gap model must keep using measured
rates from this environment, labelled as measured
under contention, and must not convert the claimed
4 vCPUs into capacity.
