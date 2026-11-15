#!/usr/bin/env python3
"""EXP-043 shared helpers: statistics and session manifests.

Research only. No production code is imported or touched by
the EXP-043 study; the only lab imports are the EXP-035
research prototype modules (lease_manager, candidate_queue).
"""

import json
import os
import platform
import statistics
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
EXP035 = os.path.join(os.path.dirname(HERE), "exp035")
if EXP035 not in sys.path:
    sys.path.insert(0, EXP035)

RAW = os.path.join(HERE, "RAW_RESULTS")
FLEET = "nova-fleet-exp043"


def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def loadavg():
    try:
        with open("/proc/loadavg") as fh:
            parts = fh.read().split()
        return [float(parts[0]), float(parts[1]),
                float(parts[2])]
    except OSError:
        return None


def manifest(kind):
    cpu = "unknown"
    try:
        with open("/proc/cpuinfo") as fh:
            for line in fh:
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    return {
        "experiment": "EXP-043",
        "kind": kind,
        "when_utc": stamp(),
        "host_node": os.uname().nodename,
        "cpu_model": cpu,
        "os_cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "loadavg_at_start": loadavg(),
    }


def dist(samples_ns):
    """Distribution summary of nanosecond samples."""
    if not samples_ns:
        return {"n": 0}
    s = sorted(samples_ns)
    n = len(s)

    def pct(p):
        idx = min(n - 1, max(0, int(round(p * (n - 1)))))
        return s[idx]

    return {
        "n": n,
        "median_ns": int(statistics.median(s)),
        "p95_ns": int(pct(0.95)),
        "max_ns": int(s[-1]),
        "mean_ns": int(statistics.fmean(s)),
    }


def write_result(kind, payload):
    os.makedirs(RAW, exist_ok=True)
    name = "%s_%s.json" % (kind, stamp())
    path = os.path.join(RAW, name)
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True)
    return path
