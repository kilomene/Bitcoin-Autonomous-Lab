#!/usr/bin/env python3
"""EXP-031 CPU capability discovery and VM profiler.

Reads every value live from primary sources on this machine
(/proc, /sys, cgroupfs, syscalls, small measured intervals) and
reports each field with its source and an evidence class:

- "measured": obtained by an action this tool performed
  (a timed /proc/stat interval, a perf_event_open trial).
- "read-from-system": read verbatim from a system interface.
  In a guest these are the hypervisor's or container runtime's
  claims, not established physical facts.
- "unknown": the interface exists in principle but exposed no
  usable value here.
- "not-accessible": the interface is absent or permission or
  policy blocks reading it from this environment.

Nothing is inferred: physical host properties that a guest does
not expose are reported as unknown, never guessed from model
names, VM sizes, or benchmark results. Benchmark-derived
capacity estimates live in the separate load probe
(load_probe.py) and in the characterisation report, labelled
as estimates there.

Usage:
    python3 vm_profile.py [--interval 5] [--out PATH] [--quiet]

With no --out, the JSON report is printed to stdout.
Standard library only.
"""
import argparse
import ctypes
import errno
import json
import os
import platform
import re
import struct
import subprocess
import sys
import time

MEASURED = "measured"
READ = "read-from-system"
UNKNOWN = "unknown"
BLOCKED = "not-accessible"


def field(value, evidence, source, note=None):
    out = {"value": value, "evidence": evidence, "source": source}
    if note:
        out["note"] = note
    return out


def read_text(path):
    try:
        with open(path, "r", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def read_first_line(path):
    txt = read_text(path)
    if txt is None:
        return None
    return txt.strip().splitlines()[0] if txt.strip() else ""


def run_cmd(argv, timeout=10):
    try:
        done = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout)
        return done.returncode, done.stdout.strip(), done.stderr.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "", f"{type(exc).__name__}: {exc}"


# ----------------------------------------------------------------
# CPU identity and topology
# ----------------------------------------------------------------

def parse_cpuinfo():
    raw = read_text("/proc/cpuinfo") or ""
    blocks = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        entry = {}
        for line in block.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                entry[key.strip()] = val.strip()
        blocks.append(entry)
    return blocks


def probe_identity(blocks):
    sec = {}
    if not blocks:
        return {"error": field(None, BLOCKED, "/proc/cpuinfo",
                               "cpuinfo unreadable")}
    first = blocks[0]
    sec["vendor"] = field(first.get("vendor_id"), READ, "/proc/cpuinfo")
    sec["model_name"] = field(first.get("model name"), READ,
                              "/proc/cpuinfo")
    fam = first.get("cpu family")
    mod = first.get("model")
    step = first.get("stepping")
    sec["family_model_stepping"] = field(
        {"family": fam, "model": mod, "stepping": step}, READ,
        "/proc/cpuinfo")
    sec["microcode"] = field(first.get("microcode"), READ,
                             "/proc/cpuinfo",
                             "guest-visible microcode string only")
    sec["architecture"] = field(platform.machine(), READ,
                                "platform.machine()")
    sec["kernel"] = field(platform.release(), READ, "platform.release()")
    sec["hostname"] = field(platform.node(), READ, "platform.node()")
    return sec


def probe_topology(blocks):
    sec = {}
    online = read_first_line("/sys/devices/system/cpu/online")
    sec["online_cpu_list"] = field(online, READ,
                                   "/sys/devices/system/cpu/online")
    try:
        sec["logical_processors_os"] = field(
            os.cpu_count(), READ, "os.cpu_count()")
    except Exception as exc:  # pragma: no cover
        sec["logical_processors_os"] = field(None, UNKNOWN,
                                             f"os.cpu_count(): {exc}")
    try:
        affinity = sorted(os.sched_getaffinity(0))
        sec["sched_getaffinity"] = field(
            {"cpus": affinity, "count": len(affinity)}, MEASURED,
            "os.sched_getaffinity(0) syscall")
    except (AttributeError, OSError) as exc:
        sec["sched_getaffinity"] = field(None, BLOCKED,
                                         f"os.sched_getaffinity: {exc}")
    status = read_text("/proc/self/status") or ""
    cpus_allowed = None
    for line in status.splitlines():
        if line.startswith("Cpus_allowed_list:"):
            cpus_allowed = line.split(":", 1)[1].strip()
    sec["cpus_allowed_list"] = field(cpus_allowed, READ,
                                     "/proc/self/status")
    # Guest-reported topology from sysfs, per CPU.
    per_cpu = {}
    unique_cores = set()
    packages = set()
    cpu_ids = []
    if online and "-" in online:
        lo, hi = online.split("-", 1)
        cpu_ids = list(range(int(lo), int(hi) + 1))
    elif online:
        cpu_ids = [int(x) for x in online.split(",") if x.strip()]
    for cpu in cpu_ids:
        base = f"/sys/devices/system/cpu/cpu{cpu}/topology"
        core_id = read_first_line(f"{base}/core_id")
        pkg = read_first_line(f"{base}/physical_package_id")
        siblings = read_first_line(f"{base}/thread_siblings_list")
        if core_id is not None and pkg is not None:
            unique_cores.add((pkg, core_id))
            packages.add(pkg)
        per_cpu[str(cpu)] = {
            "core_id": core_id,
            "physical_package_id": pkg,
            "thread_siblings_list": siblings,
        }
    sec["sysfs_topology_per_cpu"] = field(
        per_cpu, READ, "/sys/devices/system/cpu/cpu*/topology",
        "topology as the guest kernel presents it; a hypervisor "
        "can synthesise these values")
    sec["guest_reported_physical_cores"] = field(
        len(unique_cores) if unique_cores else None, READ,
        "distinct (physical_package_id, core_id) pairs in sysfs "
        "topology",
        "guest-reported only; NOT established as host physical "
        "cores")
    sec["guest_reported_packages"] = field(
        len(packages) if packages else None, READ,
        "distinct physical_package_id values in sysfs topology")
    sec["host_physical_cores"] = field(
        None, UNKNOWN, "no guest interface exposes host topology",
        "deliberately not inferred from the guest topology or "
        "from the CPU model name")
    rc, out, _err = run_cmd(["lscpu"])
    if rc == 0:
        wanted = {}
        for line in out.splitlines():
            if ":" not in line:
                continue
            key, val = [p.strip() for p in line.split(":", 1)]
            if key in ("Thread(s) per core", "Core(s) per socket",
                       "Socket(s)", "NUMA node(s)"):
                wanted[key] = val
        sec["lscpu_topology_claims"] = field(
            wanted, READ, "lscpu",
            "lscpu restates guest kernel data; same caveat")
    else:
        sec["lscpu_topology_claims"] = field(None, BLOCKED,
                                             "lscpu unavailable")
    return sec


# ----------------------------------------------------------------
# Instruction sets
# ----------------------------------------------------------------

AVX512_SUBSETS = {
    "F": "avx512f", "DQ": "avx512dq", "CD": "avx512cd",
    "BW": "avx512bw", "VL": "avx512vl", "VBMI": "avx512vbmi",
    "VBMI2": "avx512_vbmi2", "IFMA": "avx512ifma",
    "VNNI": "avx512_vnni", "BF16": "avx512_bf16",
    "BITALG": "avx512_bitalg", "VPOPCNTDQ": "avx512_vpopcntdq",
    "VP2INTERSECT": "avx512_vp2intersect",
}

OTHER_ISA = {
    "AVX2": "avx2", "AVX": "avx", "SHA-NI": "sha_ni", "AES": "aes",
    "VAES": "vaes", "GFNI": "gfni", "PCLMULQDQ": "pclmulqdq",
    "VPCLMULQDQ": "vpclmulqdq", "BMI1": "bmi1", "BMI2": "bmi2",
    "ADX": "adx", "FMA": "fma", "SSE4.2": "sse4_2",
    "AVX-VNNI": "avx_vnni", "XSAVE": "xsave",
}


def probe_isa(blocks):
    sec = {}
    flags = set()
    if blocks:
        flags = set((blocks[0].get("flags") or "").split())
    sec["flag_source_count"] = field(len(flags), READ,
                                     "/proc/cpuinfo flags")
    sec["avx512_subsets"] = field(
        {name: (flag in flags) for name, flag in
         AVX512_SUBSETS.items()}, READ, "/proc/cpuinfo flags")
    sec["other_extensions"] = field(
        {name: (flag in flags) for name, flag in OTHER_ISA.items()},
        READ, "/proc/cpuinfo flags")
    arch = platform.machine()
    if arch in ("aarch64", "arm64"):
        sec["arm_sha_extensions"] = field(
            {name: (flag in flags) for name in
             ("sha1", "sha2", "sha512", "sm3", "sm4")}, READ,
            "/proc/cpuinfo Features (ARM)")
    else:
        sec["arm_sha_extensions"] = field(
            "not-applicable", READ,
            f"platform.machine() = {arch}",
            "ARM SHA extensions exist only on ARM hosts; reported "
            "explicitly instead of omitted")
    sec["full_flag_list"] = field(sorted(flags), READ,
                                  "/proc/cpuinfo flags")
    return sec


# ----------------------------------------------------------------
# Frequency
# ----------------------------------------------------------------

def probe_frequency(blocks):
    sec = {}
    mhz = []
    for block in blocks:
        val = block.get("cpu MHz")
        if val:
            try:
                mhz.append(float(val))
            except ValueError:
                pass
    sec["cpuinfo_mhz_samples"] = field(
        mhz, READ, "/proc/cpuinfo 'cpu MHz'",
        "guest-reported instantaneous value; on this class of "
        "guest it is a nominal TSC-derived figure, not a measured "
        "core frequency under load")
    policy_dirs = []
    base = "/sys/devices/system/cpu/cpufreq"
    if os.path.isdir(base):
        policy_dirs = sorted(os.listdir(base))
    sec["cpufreq_policies"] = field(
        policy_dirs, READ, "/sys/devices/system/cpu/cpufreq",
        "empty means no scaling policy is exposed to the guest")
    per_cpu_freq = {}
    for cpu in range(len(blocks)):
        path = f"/sys/devices/system/cpu/cpu{cpu}/cpufreq"
        per_cpu_freq[str(cpu)] = os.path.isdir(path)
    if any(per_cpu_freq.values()):
        sec["per_cpu_cpufreq"] = field(per_cpu_freq, READ,
                                       "sysfs cpufreq presence")
    else:
        sec["per_cpu_cpufreq"] = field(
            None, BLOCKED,
            "/sys/devices/system/cpu/cpu*/cpufreq absent",
            "scaling driver, governor, and min/max frequencies "
            "are not accessible from this guest")
    sec["measured_frequency_under_load"] = field(
        None, UNKNOWN, "no guest interface measures actual core "
        "frequency; benchmark rates in the load probe are the "
        "only load evidence and are not a frequency")
    return sec


# ----------------------------------------------------------------
# cgroup and container / VM restrictions
# ----------------------------------------------------------------

def probe_cgroup():
    sec = {}
    self_cg = read_text("/proc/self/cgroup")
    sec["proc_self_cgroup"] = field(
        self_cg.strip() if self_cg else None, READ,
        "/proc/self/cgroup")
    is_v2 = os.path.exists("/sys/fs/cgroup/cgroup.controllers")
    is_v1 = os.path.isdir("/sys/fs/cgroup/cpu")
    sec["cgroup_versions_visible"] = field(
        {"v2_unified": is_v2, "v1_hierarchy": is_v1}, READ,
        "/sys/fs/cgroup layout")
    if is_v2:
        cpu_max = read_first_line("/sys/fs/cgroup/cpu.max")
        if cpu_max is None:
            sec["cpu_max"] = field(
                None, UNKNOWN,
                "/sys/fs/cgroup/cpu.max not present at the "
                "visible cgroup root",
                "no quota file is visible at this level; a quota "
                "can still be imposed by a parent cgroup outside "
                "the visible namespace, which this process "
                "cannot read")
        else:
            parts = cpu_max.split()
            quota = None
            if parts and parts[0] != "max":
                try:
                    quota = int(parts[0]) / int(parts[1])
                except (ValueError, ZeroDivisionError,
                        IndexError):
                    quota = None
            sec["cpu_max"] = field(
                {"raw": cpu_max, "effective_cpus": quota}, READ,
                "/sys/fs/cgroup/cpu.max")
        burst = read_first_line("/sys/fs/cgroup/cpu.max.burst")
        sec["cpu_max_burst"] = field(
            burst, READ if burst is not None else UNKNOWN,
            "/sys/fs/cgroup/cpu.max.burst",
            None if burst is not None else
            "file not present at the visible cgroup root")
        stat_raw = read_text("/sys/fs/cgroup/cpu.stat") or ""
        stat = {}
        for line in stat_raw.splitlines():
            parts = line.split()
            if len(parts) == 2:
                stat[parts[0]] = parts[1]
        sec["cpu_stat"] = field(
            stat, READ, "/sys/fs/cgroup/cpu.stat",
            "nr_throttled / throttled_usec present only when "
            "the kernel reports them at this level")
        pressure = read_text("/proc/pressure/cpu")
        sec["cpu_pressure"] = field(
            pressure.strip() if pressure else None, READ,
            "/proc/pressure/cpu",
            "PSI 'some' measures tasks stalled on CPU; it "
            "includes contention from runnable-task overload, "
            "not only quota throttling")
        mem_max = read_first_line("/sys/fs/cgroup/memory.max")
        sec["memory_max"] = field(
            mem_max, READ if mem_max is not None else UNKNOWN,
            "/sys/fs/cgroup/memory.max",
            None if mem_max is not None else
            "file not present at the visible cgroup root; "
            "guest-visible memory total is in the memory_cache "
            "section")
    if is_v1:
        v1 = {}
        for name in ("cpu.cfs_quota_us", "cpu.cfs_period_us",
                     "cpu.stat"):
            v1[name] = read_text(f"/sys/fs/cgroup/cpu/{name}")
        sec["v1_cpu_files"] = field(v1, READ,
                                    "/sys/fs/cgroup/cpu/*")
    else:
        sec["v1_cpu_files"] = field(
            None, BLOCKED, "/sys/fs/cgroup/cpu does not exist",
            "no cgroup v1 cpu hierarchy is mounted")
    return sec


def probe_virtualization():
    sec = {}
    blocks_flags = ""
    raw = read_text("/proc/cpuinfo") or ""
    m = re.search(r"^flags\s*:\s*(.*)$", raw, re.M)
    if m:
        blocks_flags = m.group(1)
    sec["hypervisor_flag"] = field(
        "hypervisor" in blocks_flags.split(), READ,
        "/proc/cpuinfo flags")
    rc, out, err = run_cmd(["systemd-detect-virt"])
    sec["systemd_detect_virt"] = field(
        out if rc == 0 else None, READ,
        "systemd-detect-virt",
        "reports the innermost virtualisation layer it "
        "detects" + ("" if rc == 0 else f"; stderr: {err}"))
    dmi = {}
    for name in ("sys_vendor", "product_name", "product_version",
                 "bios_vendor"):
        val = read_first_line(f"/sys/devices/virtual/dmi/id/{name}")
        if val is not None:
            dmi[name] = val
    sec["dmi"] = field(
        dmi if dmi else None, READ if dmi else BLOCKED,
        "/sys/devices/virtual/dmi/id/*",
        "DMI strings are supplied by the hypervisor")
    rc, out, _err = run_cmd(["lscpu"])
    hv = {}
    if rc == 0:
        for line in out.splitlines():
            if ":" not in line:
                continue
            key, val = [p.strip() for p in line.split(":", 1)]
            if key in ("Hypervisor vendor", "Virtualization type"):
                hv[key] = val
    sec["lscpu_hypervisor_claims"] = field(
        hv if hv else None, READ if hv else BLOCKED, "lscpu")
    sec["sys_hypervisor_dir"] = field(
        os.path.isdir("/sys/hypervisor"), READ, "/sys/hypervisor",
        "present mainly under Xen; absence is not evidence of "
        "bare metal")
    markers = {
        "dockerenv": os.path.exists("/.dockerenv"),
        "containerenv": os.path.exists("/run/.containerenv"),
        "container_env_var": os.environ.get("container"),
        "init_is_systemd_container_hint":
            read_first_line("/proc/1/comm"),
    }
    sec["container_markers"] = field(markers, READ,
                                     "filesystem and /proc/1/comm")
    sec["layering_note"] = field(
        "sources above are reported verbatim and can name "
        "different layers (container runtime inside a VM); "
        "this tool does not merge them into a single claim",
        READ, "synthesis rule of this tool")
    return sec


# ----------------------------------------------------------------
# Utilisation and steal, measured over an interval
# ----------------------------------------------------------------

def read_proc_stat():
    raw = read_text("/proc/stat") or ""
    cpus = {}
    extra = {}
    for line in raw.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "cpu" or re.fullmatch(r"cpu\d+", parts[0]):
            vals = [int(x) for x in parts[1:11]]
            keys = ("user", "nice", "system", "idle", "iowait",
                    "irq", "softirq", "steal", "guest",
                    "guest_nice")
            cpus[parts[0]] = dict(zip(keys, vals))
        elif parts[0] in ("ctxt", "processes", "procs_running",
                          "procs_blocked"):
            extra[parts[0]] = int(parts[1])
    return cpus, extra


def probe_utilisation(interval):
    sec = {}
    cpus0, extra0 = read_proc_stat()
    t0 = time.time()
    time.sleep(interval)
    cpus1, extra1 = read_proc_stat()
    wall = time.time() - t0
    sec["interval_seconds"] = field(round(wall, 3), MEASURED,
                                    "monotonic wall clock")
    pct = {}
    for name in cpus1:
        if name not in cpus0:
            continue
        deltas = {k: cpus1[name][k] - cpus0[name][k]
                  for k in cpus1[name]}
        total = sum(deltas.values())
        if total <= 0:
            continue
        entry = {k: round(100.0 * v / total, 2)
                 for k, v in deltas.items()}
        entry["busy_percent"] = round(
            100.0 * (total - deltas["idle"] - deltas["iowait"])
            / total, 2)
        pct[name] = entry
    sec["cpu_time_percent"] = field(
        pct, MEASURED, "/proc/stat sampled twice",
        "guest-internal accounting: 'steal' is time the "
        "hypervisor ran something else while this guest had "
        "runnable work; idle and busy are as the guest kernel "
        "sees them")
    sec["context_switches_per_second"] = field(
        round((extra1.get("ctxt", 0) - extra0.get("ctxt", 0))
              / wall, 1) if wall > 0 else None, MEASURED,
        "/proc/stat ctxt delta")
    sec["processes_forked_per_second"] = field(
        round((extra1.get("processes", 0)
               - extra0.get("processes", 0)) / wall, 1)
        if wall > 0 else None, MEASURED,
        "/proc/stat processes delta")
    loadavg = read_first_line("/proc/loadavg")
    sec["loadavg"] = field(loadavg, READ, "/proc/loadavg",
                           "1/5/15 minute averages plus running/"
                           "total threads and last pid")
    uptime = read_first_line("/proc/uptime")
    sec["uptime"] = field(uptime, READ, "/proc/uptime",
                          "uptime seconds and summed idle seconds")
    return sec


# ----------------------------------------------------------------
# Thermal
# ----------------------------------------------------------------

def probe_thermal():
    sec = {}
    zones = []
    zbase = "/sys/class/thermal"
    if os.path.isdir(zbase):
        zones = sorted(d for d in os.listdir(zbase)
                       if d.startswith("thermal_zone"))
    zone_data = {}
    for zone in zones:
        ztype = read_first_line(f"{zbase}/{zone}/type")
        temp = read_first_line(f"{zbase}/{zone}/temp")
        zone_data[zone] = {"type": ztype, "temp_millideg": temp}
    if zones:
        sec["thermal_zones"] = field(zone_data, READ,
                                     "/sys/class/thermal")
    else:
        sec["thermal_zones"] = field(
            None, BLOCKED, "/sys/class/thermal has no "
            "thermal_zone entries",
            "no temperature sensor is exposed to this guest; "
            "host thermal state and throttling are not "
            "accessible")
    cooling = []
    if os.path.isdir(zbase):
        cooling = sorted(d for d in os.listdir(zbase)
                         if d.startswith("cooling_device"))
    sec["cooling_devices"] = field(
        cooling, READ, "/sys/class/thermal",
        "cooling device entries without thermal zones carry "
        "no temperature information")
    throttle = {}
    for cpu in range(os.cpu_count() or 0):
        path = (f"/sys/devices/system/cpu/cpu{cpu}/"
                "thermal_throttle")
        throttle[str(cpu)] = os.path.isdir(path)
    sec["per_cpu_thermal_throttle_counters"] = field(
        throttle if any(throttle.values()) else None,
        READ if any(throttle.values()) else BLOCKED,
        "/sys/devices/system/cpu/cpu*/thermal_throttle",
        "absent in this guest, so package/core throttle "
        "counts are not accessible")
    return sec


# ----------------------------------------------------------------
# Performance counters: real perf_event_open trial
# ----------------------------------------------------------------

PERF_TYPE_HARDWARE = 0
PERF_TYPE_SOFTWARE = 1
PERF_COUNT_HW_CPU_CYCLES = 0
PERF_COUNT_SW_CPU_CLOCK = 0
__NR_perf_event_open = 298  # x86_64


def perf_trial(counter_type, config):
    """Open one counter for this process, run a busy loop,
    read the count. Returns (fd_ok, count, errno_str)."""
    attr = bytearray(128)
    struct.pack_into("I", attr, 0, counter_type)
    struct.pack_into("I", attr, 4, 128)
    struct.pack_into("Q", attr, 8, config)
    flags = 0
    flags |= 1 << 5   # exclude_kernel
    flags |= 1 << 6   # exclude_hv
    struct.pack_into("Q", attr, 32, flags)
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.syscall(__NR_perf_event_open,
                      bytes(attr), 0, -1, -1, 0)
    if fd < 0:
        err = ctypes.get_errno()
        return False, None, f"errno {err} ({os.strerror(err)})"
    try:
        total = 0
        for i in range(2_000_000):
            total += i * i
        data = os.read(fd, 8)
        count = struct.unpack("Q", data)[0]
        return True, count, f"busy-loop sink {total}"
    except OSError as exc:
        return True, None, f"read failed: {exc}"
    finally:
        os.close(fd)


def probe_perf():
    sec = {}
    paranoid = read_first_line(
        "/proc/sys/kernel/perf_event_paranoid")
    sec["perf_event_paranoid"] = field(
        paranoid, READ, "/proc/sys/kernel/perf_event_paranoid",
        "higher is more restrictive for unprivileged users; "
        "this tool runs as uid 0 in this environment")
    rc, _out, _err = run_cmd(["which", "perf"])
    sec["perf_tool_installed"] = field(
        rc == 0, READ, "which perf")
    if platform.machine() == "x86_64":
        ok, count, note = perf_trial(PERF_TYPE_HARDWARE,
                                     PERF_COUNT_HW_CPU_CYCLES)
        sec["trial_hardware_cycles"] = field(
            {"opened": ok, "count": count, "detail": note},
            MEASURED, "perf_event_open syscall via ctypes",
            "a real open attempt from this process, not a "
            "documentation claim")
        ok2, count2, note2 = perf_trial(PERF_TYPE_SOFTWARE,
                                        PERF_COUNT_SW_CPU_CLOCK)
        sec["trial_software_cpu_clock"] = field(
            {"opened": ok2, "count": count2, "detail": note2},
            MEASURED, "perf_event_open syscall via ctypes")
    else:
        sec["trial_hardware_cycles"] = field(
            None, UNKNOWN,
            "trial implemented for x86_64 syscall number only")
    return sec


# ----------------------------------------------------------------
# Memory and cache
# ----------------------------------------------------------------

def probe_memory_cache():
    sec = {}
    meminfo = {}
    raw = read_text("/proc/meminfo") or ""
    for line in raw.splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            if key in ("MemTotal", "MemAvailable", "MemFree",
                       "SwapTotal", "SwapFree", "HugePages_Total",
                       "Hugepagesize"):
                meminfo[key] = val.strip()
    sec["meminfo"] = field(meminfo, READ, "/proc/meminfo",
                           "guest-visible memory; the host may "
                           "balloon or overcommit behind this")
    caches = {}
    cpu0 = "/sys/devices/system/cpu/cpu0/cache"
    if os.path.isdir(cpu0):
        for idx in sorted(os.listdir(cpu0)):
            if not idx.startswith("index"):
                continue
            base = f"{cpu0}/{idx}"
            caches[idx] = {
                "level": read_first_line(f"{base}/level"),
                "type": read_first_line(f"{base}/type"),
                "size": read_first_line(f"{base}/size"),
                "shared_cpu_list": read_first_line(
                    f"{base}/shared_cpu_list"),
            }
    sec["cpu0_cache_indexes"] = field(
        caches if caches else None,
        READ if caches else BLOCKED,
        "/sys/devices/system/cpu/cpu0/cache/index*",
        "cache geometry as the guest kernel presents it")
    nodes = []
    nbase = "/sys/devices/system/node"
    if os.path.isdir(nbase):
        nodes = sorted(d for d in os.listdir(nbase)
                       if re.fullmatch(r"node\d+", d))
    sec["numa_nodes"] = field(nodes, READ,
                              "/sys/devices/system/node")
    return sec


# ----------------------------------------------------------------
# Main
# ----------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="EXP-031 CPU/VM capability profiler")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="utilisation sampling interval "
                             "in seconds (default 5)")
    parser.add_argument("--out", default=None,
                        help="write JSON to this path instead "
                             "of stdout")
    args = parser.parse_args()

    blocks = parse_cpuinfo()
    report = {
        "tool": "exp031/vm_profile.py",
        "generated_utc": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "evidence_classes": {
            "measured": "obtained by an action of this tool",
            "read-from-system": "read verbatim from a system "
                                "interface; in a guest these "
                                "are claims of the virtualisation "
                                "layer, not physical facts",
            "unknown": "interface exists but exposed no "
                       "usable value",
            "not-accessible": "interface absent or blocked "
                              "from this environment",
        },
        "identity": probe_identity(blocks),
        "topology": probe_topology(blocks),
        "instruction_sets": probe_isa(blocks),
        "frequency": probe_frequency(blocks),
        "cgroup": probe_cgroup(),
        "virtualization": probe_virtualization(),
        "utilisation": probe_utilisation(args.interval),
        "thermal": probe_thermal(),
        "perf_counters": probe_perf(),
        "memory_cache": probe_memory_cache(),
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
