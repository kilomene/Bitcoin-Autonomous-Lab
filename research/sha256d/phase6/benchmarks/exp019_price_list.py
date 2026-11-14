#!/usr/bin/env python3
"""EXP-019 price list driver and analyzer (Y-002, Y-001).

Compiles src/exp019_price_micro.c, runs its self-verification
(100,000 random vectors, 1,600,000 lanes, every form checked
against scalar modular addition), audits the emitted runner
loops with objdump, then runs three independent sessions of
the paired microbenchmark: for every pipeline separation
0..15, every repeat runs all five forms once in randomized
order over identical data and identical chain state, so a
candidate and the current serial form pair within a repeat.

Raw sessions are append-only under benchmarks/exp019/. The
analysis writes analysis/exp019_price_list.json (the path
named in the EXP-019 scaffold) plus a timestamped copy in
benchmarks/exp019/. Statistics: per separation and form,
the paired ratio candidate / current_serial of ns per
vector op, summarized as the mean log ratio with a 95
percent percentile bootstrap interval (10,000 resamples)
and the median ns per vector op of each form.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "exp019")
SRC = os.path.join(ROOT, "research/sha256d/phase6/src/"
                          "exp019_price_micro.c")
ANALYSIS_PATH = os.path.join(
    ROOT, "research/sha256d/phase6/analysis/"
          "exp019_price_list.json")
BINARY = "/tmp/exp019_price_micro_driver"
CC_CMD = ["gcc", "-O3", "-mavx512f", "-mavx512bw",
          "-Wall", "-Wextra", "-o", BINARY, SRC]
ITERATIONS = 8192
REPEATS = 21
SESSIONS = 3
SEPARATIONS = list(range(16))
FORMS = ["current_serial", "balanced_tree", "cs1_resolved",
         "csfull_resolved", "sigma_led_cs1"]
BOOT = 10_000


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def node_info():
    cli = os.path.normpath(os.path.join(
        ROOT, "../bitcoin-core-dist/bitcoin-core-28.1/bin/"
              "bitcoin-cli"))
    datadir = os.path.join(ROOT, ".local/mainnet")
    try:
        out = subprocess.run(
            [cli, f"-datadir={datadir}", "getblockchaininfo"],
            capture_output=True, text=True, timeout=8)
        if out.returncode != 0:
            return {"rpc_status": "error",
                    "detail": (out.stderr or out.stdout
                               ).strip()[:200]}
        info = json.loads(out.stdout)
        return {"rpc_status": "ok", "blocks": info["blocks"],
                "headers": info["headers"],
                "initialblockdownload":
                    info["initialblockdownload"],
                "verificationprogress":
                    info["verificationprogress"]}
    except Exception as exc:
        return {"rpc_status": "unavailable",
                "detail": f"{type(exc).__name__}: {exc}"[:200]}


def loadavg():
    with open("/proc/loadavg") as fh:
        return [float(x) for x in fh.read().split()[:3]]


def assembly_audit():
    out = subprocess.run(["objdump", "-d", "--no-show-raw-insn",
                          BINARY], capture_output=True,
                         text=True, check=True).stdout
    audit = {}
    current = None
    for line in out.splitlines():
        if "<run_" in line and ">:" in line:
            current = line.split("<run_")[1].split(">")[0]
            audit[current] = {"vpaddd": 0, "vpternlogd": 0,
                              "vpslld": 0}
        elif current in audit:
            for mnemonic in ("vpaddd", "vpternlogd", "vpslld"):
                if mnemonic in line:
                    audit[current][mnemonic] += 1
    return audit


def run_session(session_index, stamp):
    session_id = f"{stamp}_exp019_price_s{session_index}"
    path = os.path.join(OUT_DIR, f"session_{session_id}.json")
    suffix = 2
    while os.path.exists(path):
        session_id = (f"{stamp}_exp019_price_s{session_index}"
                      f"_r{suffix}")
        path = os.path.join(OUT_DIR, f"session_{session_id}.json")
        suffix += 1
    seed_base = int.from_bytes(
        hashlib.sha256(session_id.encode()).digest()[:8],
        "little")
    record = {
        "experiment": "EXP-019",
        "kind": "price_list_microbenchmark",
        "session_id": session_id,
        "session_index": session_index,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "iterations_per_block": ITERATIONS,
        "repeats_per_separation": REPEATS,
        "separations": SEPARATIONS,
        "forms": FORMS,
        "load_average_at_start": loadavg(),
        "node_at_start": node_info(),
        "blocks": [],
    }
    for separation in SEPARATIONS:
        seed = seed_base + separation
        out = subprocess.run(
            [BINARY, "bench", str(separation + 1),
             str(ITERATIONS), str(REPEATS), str(seed)],
            capture_output=True, text=True, check=True).stdout
        for line in out.splitlines():
            block = json.loads(line)
            block["session_id"] = session_id
            record["blocks"].append(block)
    record["finished_utc"] = datetime.now(timezone.utc).isoformat()
    record["load_average_at_end"] = loadavg()
    record["node_at_end"] = node_info()
    with open(path, "w") as fh:
        json.dump(record, fh, indent=1)
    return session_id, record


def paired_ratios(sessions):
    """(separation, form) -> list of paired log ratios vs
    current_serial, pairing on (session, separation, repeat)."""
    ref = {}
    vals = {}
    for sess in sessions:
        for block in sess["blocks"]:
            key = (block["session_id"], block["separation"],
                   block["repeat"])
            if block["form"] == "current_serial":
                ref[key] = block["ns_per_vector_op"]
            else:
                vals.setdefault(
                    (block["separation"], block["form"]),
                    []).append((key, block["ns_per_vector_op"]))
    out = {}
    for (separation, form), entries in vals.items():
        logs = [np.log(v / ref[key]) for key, v in entries]
        out.setdefault(separation, {})[form] = np.array(logs)
    return out


def median_rates(sessions):
    med = {}
    for sess in sessions:
        for block in sess["blocks"]:
            med.setdefault((block["separation"], block["form"]),
                           []).append(block["ns_per_vector_op"])
    return {key: float(np.median(v)) for key, v in med.items()}


def bootstrap_ci(logs, rng):
    n = len(logs)
    idx = rng.integers(0, n, size=(BOOT, n))
    means = logs[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(np.exp(lo)), float(np.exp(hi))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    subprocess.run(CC_CMD, check=True)
    verify = json.loads(subprocess.run(
        [BINARY, "verify"], capture_output=True, text=True,
        check=True).stdout.strip())
    assert verify["mismatches"] == 0, verify
    audit = assembly_audit()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sessions = []
    session_ids = []
    for i in range(1, SESSIONS + 1):
        sid, rec = run_session(i, stamp)
        session_ids.append(sid)
        sessions.append(rec)
        print("session done:", sid, "blocks:", len(rec["blocks"]),
              flush=True)

    ratios = paired_ratios(sessions)
    medians = median_rates(sessions)
    rng = np.random.default_rng(19019)
    table = []
    for separation in SEPARATIONS:
        row = {"separation": separation,
               "actual_recurrence_use":
                   {0: "fused round T1 consumption",
                    1: "sigma1 input at t+2",
                    6: "direct addend at t+7",
                    14: "sigma0 input at t+15",
                    15: "direct addend at t+16"}.get(
                        separation, "intermediate separation"),
               "median_ns_per_vector_op": {
                   form: medians[(separation, form)]
                   for form in FORMS},
               "relative_to_current_serial": {}}
        for form in FORMS[1:]:
            logs = ratios[separation][form]
            lo, hi = bootstrap_ci(logs, rng)
            row["relative_to_current_serial"][form] = {
                "pairs": int(len(logs)),
                "ratio_mean_log": float(np.exp(logs.mean())),
                "ci95": [lo, hi],
                "fraction_pairs_faster_than_current":
                    float(np.mean(logs < 0)),
            }
        table.append(row)

    analysis = {
        "experiment": "EXP-019",
        "kind": "price_list",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"path": os.path.relpath(SRC, ROOT),
                   "sha256": sha256_file(SRC)},
        "binary_sha256": sha256_file(BINARY),
        "compiler_command": " ".join(CC_CMD),
        "verification": verify,
        "assembly_audit_runner_loops": audit,
        "sessions": session_ids,
        "iterations_per_block": ITERATIONS,
        "repeats_per_separation": REPEATS,
        "price_list": table,
    }
    with open(ANALYSIS_PATH, "w") as fh:
        json.dump(analysis, fh, indent=1)
    copy_path = os.path.join(
        OUT_DIR, f"analysis_{stamp}.json")
    with open(copy_path, "w") as fh:
        json.dump(analysis, fh, indent=1)
    print("analysis written:", ANALYSIS_PATH)
    for row in table:
        rel = row["relative_to_current_serial"]
        print(row["separation"],
              {f: round(rel[f]["ratio_mean_log"], 3)
               for f in rel})


if __name__ == "__main__":
    sys.exit(main())
