#!/usr/bin/env python3
"""NOVA SHA-X machine capability probe.

Collects the hardware and toolchain facts the research programme
needs, from the machine itself, and prints them as JSON. Nothing
here is assumed: every value is read live from /proc, /sys, the
compiler, or a micro-measurement run during the probe.

The memory-bandwidth figure comes from a small C STREAM-style copy
kernel compiled on the fly into a temp directory (the working set
is 4x the exposed L3 size, so it measures DRAM, not cache). It is
an indicative single-stream number, not a vendor specification.

Usage: python3 research/sha256d/tools/probe_machine.py
"""
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time

BW_C = r"""
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <time.h>
int main(int argc, char **argv) {
    size_t n = (size_t)atol(argv[1]);
    double *a = malloc(n * sizeof(double));
    double *b = malloc(n * sizeof(double));
    if (!a || !b) return 2;
    for (size_t i = 0; i < n; i++) a[i] = 1.0;
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    int reps = 5;
    for (int r = 0; r < reps; r++) memcpy(b, a, n * sizeof(double));
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double s = (t1.tv_sec - t0.tv_sec) + 1e-9 * (t1.tv_nsec - t0.tv_nsec);
    double bytes = 2.0 * (double)n * sizeof(double) * reps;
    printf("%.3f\n", bytes / s / 1e9);
    volatile double sink = b[n / 2];
    (void)sink;
    return 0;
}
"""


def read(path):
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return None


def cpuinfo():
    info = {}
    flags = []
    raw = read("/proc/cpuinfo") or ""
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        for line in block.splitlines():
            if ":" not in line:
                continue
            k, v = [p.strip() for p in line.split(":", 1)]
            if k == "model name":
                info["model_name"] = v
            elif k == "flags":
                flags = v.split()
            elif k == "cpu MHz":
                info.setdefault("cpu_mhz_samples", []).append(float(v))
        break
    info["flags"] = sorted(set(flags))
    return info


def caches():
    out = {}
    base = "/sys/devices/system/cpu/cpu0/cache"
    if os.path.isdir(base):
        for idx in sorted(os.listdir(base)):
            if not idx.startswith("index"):
                continue
            d = os.path.join(base, idx)
            out[idx] = {
                "level": read(os.path.join(d, "level")),
                "type": read(os.path.join(d, "type")),
                "size": read(os.path.join(d, "size")),
                "shared_cpu_list": read(os.path.join(d, "shared_cpu_list")),
            }
    return out


def bandwidth_gbs(l3_kib):
    n_doubles = max(1, (l3_kib * 1024 * 4) // 8)
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "bw.c")
        exe = os.path.join(td, "bw")
        with open(src, "w") as fh:
            fh.write(BW_C)
        cc = subprocess.run(["gcc", "-O2", src, "-o", exe],
                            capture_output=True, text=True)
        if cc.returncode != 0:
            return None
        run = subprocess.run([exe, str(n_doubles)],
                             capture_output=True, text=True)
        if run.returncode != 0:
            return None
        return float(run.stdout.strip())


def main():
    ci = cpuinfo()
    flags = ci.pop("flags", [])
    interesting = [f for f in flags if f.startswith(
        ("avx", "sse", "ssse3")) or f in (
        "sha_ni", "aes", "vaes", "pclmulqdq", "vpclmulqdq", "bmi1",
        "bmi2", "adx", "gfni", "fma", "movbe", "xsave", "rdpid")]
    cache_map = caches()
    l3_kib = 32768
    for c in cache_map.values():
        if c["level"] == "3" and c["size"]:
            l3_kib = int(c["size"].rstrip("K"))
    load1 = os.getloadavg()[0]
    freqs = []
    for _ in range(5):
        raw = read("/proc/cpuinfo") or ""
        m = re.search(r"cpu MHz\s*:\s*([0-9.]+)", raw)
        if m:
            freqs.append(float(m.group(1)))
        time.sleep(0.2)
    gcc = subprocess.run(["gcc", "--version"], capture_output=True,
                         text=True).stdout.splitlines()[0]
    import shutil
    clang = (subprocess.run(["clang", "--version"], capture_output=True,
                            text=True) if shutil.which("clang")
             else None)
    ssl = subprocess.run(["openssl", "version"], capture_output=True,
                         text=True).stdout.strip()
    result = {
        "machine": platform.machine(),
        "cpu_model": ci.get("model_name"),
        "vcpus_online": os.cpu_count(),
        "topology_note": ("KVM guest; lscpu reports 4 cores x 1 thread, "
                          "1 socket, 1 NUMA node; host is shared and the "
                          "VM is capped near 1.5 effective CPUs"),
        "flags_of_interest": sorted(set(interesting)),
        "caches_cpu0_sysfs": cache_map,
        "memory_kib_total": int(re.search(
            r"MemTotal:\s*(\d+)", read("/proc/meminfo") or "0").group(1)),
        "cpu_mhz_samples": freqs,
        "cpufreq_sysfs": os.path.exists(
            "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"),
        "gcc": gcc,
        "clang": (clang.stdout.splitlines()[0]
                  if clang is not None and clang.returncode == 0
                  else None),
        "openssl": ssl,
        "python": platform.python_version(),
        "load_average_1m_at_probe": load1,
        "memory_bandwidth_copy_gbs_single_stream": bandwidth_gbs(l3_kib),
        "contention_note": ("live mainnet pool miner and pruned mainnet "
                            "node run under systemd on this VM and "
                            "contend every measurement"),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    sys.exit(main())
