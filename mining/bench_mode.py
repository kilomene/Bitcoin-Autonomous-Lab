#!/usr/bin/env python3
"""Offline benchmark mode (EXP-049, register R-35, portfolio
NOVA-ER-0009).

One command prints the host profile and a category E rate
(complete production search path) for the machine this code
finds itself on:

    python3 mining/bench_mode.py [--repetitions N]
                                 [--count N] [--json]
                                 [--output PATH]

Motivation: the lab's hosts alternate (AMD EPYC 9D25 and
Intel Xeon Platinum 8321HC at the time of writing) and every
VM replacement lands on a host with no profile. The agent
scheduler (agent/intelligence/scheduler.py) already measures
through the real search path, but it is an agent-layer tool
with no fixed bench work unit in the production command
surface. This module is that surface.

Structural safety (the point of the design): this module is
the whole mode. Its import graph is the Python standard
library plus gpu.engine (the compute seam), and gpu.engine
itself imports only ctypes, hashlib, os and time. There is
no endpoint resolution here, no Stratum client, no share
handling and no chain interface: nothing in this file's code
path can connect anywhere or present a candidate to anyone.
The property is a build property of the import graph, not a
runtime flag, and tests/test_exp049_bench_mode.py pins it
(AST scan of this file, import-closure check in a fresh
interpreter, and a run with the socket layer rigged to raise
on any use). The mode never reads .local/mining-endpoint.json
and never opens a socket; it also writes nothing except an
optional caller-named JSON report file.

Why a dedicated entry module and not a flag on
mining/mainnet_live.py: mainnet_live imports the Stratum
client and the endpoint configuration at module level, so a
flag inside it would execute with the full submission path
imported into the process and the structural property above
would be false. A separate entry module that imports only
the compute seam keeps the property true by construction.
The live mining path is untouched either way: nothing in
this file is imported by any production module, and the mode
changes no behaviour when it is not invoked.

Fixed bench work unit: the rate measurement runs
ComputeEngine.search_first_counted over a pinned 80-byte
header (bytes(range(80)), byte-identical to the scheduler's
R-35 work unit so the figures are directly comparable) at
target 1 from nonce 0 over a fixed count (default 262,144).
Target 1 is met by a real digest with probability about
2^-256, so the scan covers the full range in practice; the
engine's returned attempted count is the authority for work
done either way, and the rate is attempted hashes over wall
time measured around the call. The reported rate is a
category E rate (complete production search: header in,
target test inside the search, early-exit accounting), never
a kernel or batch figure.

Self-check (runs before any rate is reported, on every
invocation): the production batch path's digests over a
1,024-nonce span are compared byte for byte against hashlib,
and a search over a span containing the genesis nonce must
return a candidate whose hashlib digest is the genesis block
hash and meets the genesis target, in agreement with a
hashlib scan of the same span. A failed self-check exits
nonzero and no rate is presented as trustworthy.
"""

import argparse
import contextlib
import hashlib
import json
import os
import statistics
import struct
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..")))

from gpu.engine import ComputeEngine  # noqa: E402

CATEGORY = ("E: complete production search path "
            "(ComputeEngine.search_first_counted)")

# Fixed bench work unit (rate). Byte-identical header and
# target to agent/intelligence/scheduler.py's R-35 unit
# (BENCH_HEADER / BENCH_TARGET / WORKLOAD_HASHES there),
# restated here so this module imports nothing from the
# agent layer.
RATE_HEADER = bytes(range(80))
RATE_TARGET = 1
RATE_START = 0
DEFAULT_COUNT = 1 << 18
DEFAULT_REPETITIONS = 5

# Correctness fixture: the genesis block header. The nonce
# is 2083236893, the target is the difficulty-1 target from
# bits 0x1d00ffff, and the digest is the genesis block hash
# in internal byte order.
GENESIS_HEADER = bytes.fromhex(
    "01000000"
    "000000000000000000000000000000000000000000000000"
    "0000000000000000"
    "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a"
    "9fb8aa4b1e5e4a"
    "29ab5f49"
    "ffff001d"
    "1dac2b7c")
GENESIS_NONCE = 2083236893
GENESIS_TARGET = 0xFFFF * (1 << 208)
GENESIS_DIGEST = bytes.fromhex(
    "000000000019d6689c085ae165831e934ff763ae46a2a6c172"
    "b3f1b60a8ce26f")[::-1]

SELF_CHECK_COUNT = 1024
SELF_CHECK_START = 12345
GENESIS_SPAN_START = GENESIS_NONCE - 500
GENESIS_SPAN_COUNT = 1000

# CPU flags reported in the host profile: the ones the
# production dispatch actually keys on, plus close relatives.
PROFILE_FLAGS = ("sha_ni", "avx2", "avx512f", "avx512bw",
                 "avx512vl", "avx512vbmi", "avx512vbmi2",
                 "avx512ifma", "avx512vnni", "sse4_1", "ssse3")


def cpu_digest(header, nonce):
    """Reference double SHA-256 of the header with the
    nonce written at offset 76, little-endian. hashlib only;
    this is the independent reference for every check in
    this module."""
    h = bytearray(header)
    struct.pack_into("<I", h, 76, nonce)
    return hashlib.sha256(
        hashlib.sha256(bytes(h)).digest()).digest()


def backend_label_reason(desc):
    """(label, reason) for the selected backend, mirroring
    the wording of mining/mainnet_live.py's backend_reason
    helper (Stage 6 D9 fix). Reimplemented here in miniature
    because importing mainnet_live would import the Stratum
    client into the mode, which the structural property
    forbids."""
    backend = desc.get("backend")
    if backend == "v512dual":
        return "AVX-512 DualMask", desc.get("v512dual_reason")
    if backend == "v512":
        return "AVX-512 MB", desc.get("v512_reason")
    if backend == "shani":
        return "SHA-NI streams", desc.get("shani_reason")
    if backend == "avx2":
        return "AVX2 MB", desc.get("avx2_reason")
    if backend == "cuda":
        return "CUDA", desc.get("cuda_context_reason")
    if backend == "c":
        return ("C batch",
                "the C batch library loaded and its self-test "
                "digests matched")
    return "pure Python", desc.get("fallback_reason")


def host_profile():
    """Host profile from /proc/cpuinfo and the cgroup tree.
    No configuration is read: this works on a fresh host with
    an empty home and an empty environment."""
    model = None
    flags = set()
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8",
                  errors="replace") as f:
            for line in f:
                if model is None and line.startswith(
                        "model name"):
                    model = line.split(":", 1)[1].strip()
                elif line.startswith("flags"):
                    flags = set(
                        line.split(":", 1)[1].split())
                    if model is not None:
                        break
    except OSError:
        pass
    cpu_max = None
    for path in ("/sys/fs/cgroup/cpu.max",
                 "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cpu_max = f.read().strip()
            break
        except OSError:
            continue
    uname = os.uname()
    return {
        "hostname": uname.nodename,
        "os": f"{uname.sysname} {uname.release}",
        "machine": uname.machine,
        "cpu_model": model,
        "logical_cpus": os.cpu_count(),
        "flags_relevant": {name: (name in flags)
                           for name in PROFILE_FLAGS},
        "cgroup_cpu_max": cpu_max,
        "load_average": list(os.getloadavg()),
    }


def self_check(engine):
    """Gate 1/2 correctness for the mode, run on the mode's
    own engine before any rate is reported. Returns a dict;
    'passed' is True only when every comparison agrees."""
    result = {"batch_digests_verified": 0,
              "batch_digests_mismatched": 0,
              "genesis_found_by_engine": False,
              "genesis_found_by_hashlib": False,
              "genesis_nonce": None,
              "genesis_digest_matches": False,
              "genesis_meets_target": False}
    candidates, _stats = engine.batch_search(
        RATE_HEADER, (1 << 256) - 1,
        SELF_CHECK_START, SELF_CHECK_COUNT)
    seen = set()
    for cand in candidates:
        nonce = cand["nonce"]
        seen.add(nonce)
        digest = bytes.fromhex(cand["hash"])[::-1]
        if digest == cpu_digest(RATE_HEADER, nonce):
            result["batch_digests_verified"] += 1
        else:
            result["batch_digests_mismatched"] += 1
    if len(seen) != SELF_CHECK_COUNT:
        # A full-target batch must enumerate the whole span;
        # anything missing is a mismatch of the span itself.
        result["batch_digests_mismatched"] += (
            SELF_CHECK_COUNT - len(seen))
    hit, _attempted, _secs = engine.search_first_counted(
        GENESIS_HEADER, GENESIS_TARGET,
        GENESIS_SPAN_START, GENESIS_SPAN_COUNT)
    hashlib_hits = [
        n for n in range(GENESIS_SPAN_START,
                         GENESIS_SPAN_START + GENESIS_SPAN_COUNT)
        if int.from_bytes(cpu_digest(GENESIS_HEADER, n),
                          "little") <= GENESIS_TARGET]
    result["genesis_found_by_hashlib"] = bool(hashlib_hits)
    if hit is not None:
        nonce, digest = hit
        result["genesis_found_by_engine"] = True
        result["genesis_nonce"] = nonce
        result["genesis_digest_matches"] = (
            digest == cpu_digest(GENESIS_HEADER, nonce)
            and digest == GENESIS_DIGEST)
        result["genesis_meets_target"] = (
            int.from_bytes(digest, "little") <= GENESIS_TARGET)
    result["passed"] = (
        result["batch_digests_mismatched"] == 0
        and result["batch_digests_verified"] == SELF_CHECK_COUNT
        and result["genesis_found_by_engine"]
        == result["genesis_found_by_hashlib"]
        and result["genesis_digest_matches"]
        and result["genesis_meets_target"])
    return result


def measure_once(engine, count):
    """One bench work unit: a fixed span through the
    production search path. Returns (attempted, wall_s,
    rate_hs) with the wall measured around the call and the
    attempted count taken from the engine, the same
    convention as the scheduler's measure."""
    t0 = time.perf_counter()
    _hit, attempted, _secs = engine.search_first_counted(
        RATE_HEADER, RATE_TARGET, RATE_START, count)
    wall = time.perf_counter() - t0
    rate = attempted / wall if wall > 0 else 0.0
    return attempted, wall, rate


def measure_rate(engine, repetitions, count):
    """Median rate over repetitions of the work unit, with
    every run recorded."""
    runs = []
    for _ in range(repetitions):
        attempted, wall, rate = measure_once(engine, count)
        runs.append({"attempted": attempted,
                     "wall_s": round(wall, 4),
                     "rate_hs": rate})
    median = statistics.median(r["rate_hs"] for r in runs)
    return median, runs


def effective_cpu_estimate(count):
    """Effective-CPU estimate by the EXP-031 / scheduler
    method: the median search rate at 2 threads divided by
    the median at 1 thread, each over 3 repetitions of the
    work unit on engines constructed with explicit thread
    counts (which skip the tuning probe). An estimate from a
    scaling ratio, labelled as such; not a core count."""
    eng1 = ComputeEngine(threads=1)
    rate1, _runs1 = measure_rate(eng1, 3, count)
    eng2 = ComputeEngine(threads=2)
    rate2, _runs2 = measure_rate(eng2, 3, count)
    ratio = rate2 / rate1 if rate1 > 0 else None
    return {"rate_1_thread_hs": rate1,
            "rate_2_threads_hs": rate2,
            "effective_cpus_estimate": ratio,
            "method": ("estimate: median 2-thread search rate "
                       "divided by median 1-thread search rate "
                       "over the fixed work unit; a scaling "
                       "ratio, not a core count")}


def run_bench(repetitions=DEFAULT_REPETITIONS,
              count=DEFAULT_COUNT):
    """The full bench: construct the production engine
    exactly as the production miner does (auto dispatch, no
    arguments), self-check it, then measure. Returns the
    report dict; 'self_check.passed' False means no rate in
    the report is to be trusted."""
    engine = ComputeEngine()
    desc = engine.describe()
    label, reason = backend_label_reason(desc)
    check = self_check(engine)
    report = {
        "mode": "offline-benchmark (EXP-049, R-35)",
        "timestamp_utc": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "category": CATEGORY,
        "work_unit": {
            "header": "bytes(range(80)) (pinned fixture)",
            "target": RATE_TARGET,
            "start": RATE_START,
            "count": count,
            "repetitions": repetitions},
        "host": host_profile(),
        "backend": desc.get("backend"),
        "backend_label": label,
        "backend_reason": reason,
        "threads": desc.get("c_threads"),
        "threads_tuned": desc.get("c_threads_tuned"),
        "self_check": check,
        "contention_note": (
            "measured on the live host as found; if the "
            "production miner is running, this rate is a "
            "contended figure alongside it"),
    }
    if check["passed"]:
        median, runs = measure_rate(engine, repetitions, count)
        report["runs"] = runs
        report["counted_hashes"] = sum(
            r["attempted"] for r in runs)
        report["wall_s_total"] = round(
            sum(r["wall_s"] for r in runs), 4)
        report["median_rate_hs"] = median
        report["effective_cpu"] = effective_cpu_estimate(count)
    return report


def format_text(report):
    lines = []
    host = report["host"]
    lines.append("Offline benchmark (EXP-049, R-35)")
    lines.append(f"Host: {host['hostname']} / "
                 f"{host['cpu_model']} / "
                 f"{host['logical_cpus']} logical CPUs")
    flags = ", ".join(
        f"{k}={'yes' if v else 'no'}"
        for k, v in host["flags_relevant"].items())
    lines.append(f"Flags: {flags}")
    lines.append(f"Backend: {report['backend_label']} "
                 f"({report['backend']}), "
                 f"{report['threads']} threads")
    lines.append(f"Reason: {report['backend_reason']}")
    check = report["self_check"]
    lines.append(
        f"Self-check: {'PASSED' if check['passed'] else 'FAILED'} "
        f"({check['batch_digests_verified']} digests verified "
        f"against hashlib, "
        f"{check['batch_digests_mismatched']} mismatched; "
        f"genesis candidate "
        f"{'verified' if check['genesis_digest_matches'] else 'NOT verified'})")
    if check["passed"]:
        lines.append(f"Category: {report['category']}")
        lines.append(
            f"Rate (median of "
            f"{report['work_unit']['repetitions']} runs of "
            f"{report['work_unit']['count']} hashes): "
            f"{report['median_rate_hs']:,.0f} H/s")
        lines.append(f"Counted hashes: "
                     f"{report['counted_hashes']:,}")
        eff = report["effective_cpu"]
        lines.append(
            f"Effective CPUs (estimate, scaling ratio): "
            f"{eff['effective_cpus_estimate']:.2f} "
            f"(1 thread {eff['rate_1_thread_hs']:,.0f} H/s, "
            f"2 threads {eff['rate_2_threads_hs']:,.0f} H/s)")
    lines.append(f"Note: {report['contention_note']}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline benchmark mode: host profile "
                    "and a category E rate through the "
                    "production search path. No network, no "
                    "endpoint configuration, nothing "
                    "submitted anywhere.")
    parser.add_argument("--repetitions", type=int,
                        default=DEFAULT_REPETITIONS)
    parser.add_argument("--count", type=int,
                        default=DEFAULT_COUNT)
    parser.add_argument("--json", action="store_true",
                        help="print the report as JSON")
    parser.add_argument("--output", default=None,
                        help="also write the report JSON to "
                             "this path")
    args = parser.parse_args(argv)
    if args.repetitions < 1:
        parser.error("--repetitions must be at least 1")
    if not (0 < args.count <= (1 << 32)):
        parser.error("--count out of range")
    if args.json:
        # The engine prints its thread-tuning line to stdout
        # during construction; keep stdout pure JSON.
        with contextlib.redirect_stdout(sys.stderr):
            report = run_bench(args.repetitions, args.count)
    else:
        report = run_bench(args.repetitions, args.count)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1, sort_keys=True)
    if args.json:
        print(json.dumps(report, indent=1, sort_keys=True))
    else:
        print(format_text(report))
    return 0 if report["self_check"]["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
