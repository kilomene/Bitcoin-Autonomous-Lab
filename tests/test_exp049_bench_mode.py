#!/usr/bin/env python3
"""EXP-049 tests: the offline benchmark mode (R-35).

Gates covered here (the Gate 4 paired comparison campaign
lives in research/sha256d/exp049/):

- Gate 1/2 correctness: the mode's self-check verifies the
  production batch path's digests against hashlib byte for
  byte and the genesis candidate against the known genesis
  hash and target, in agreement with a hashlib span scan.
- Gate 3 adversarial, structural: an AST scan of
  mining/bench_mode.py shows its imports are only the
  standard library plus the compute seam and that no
  network, endpoint or submission identifier appears; a
  fresh interpreter's import closure contains no Stratum,
  endpoint, solo-server or miner module; a full bench run
  with the socket layer rigged to raise on any use completes
  and reports a rate; a run in a clean environment from a
  foreign working directory completes with no configuration
  present (Gate 5 shape); the endpoint configuration file's
  hash is unchanged across all of it.
"""

import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), ".."))
BENCH_PATH = os.path.join(ROOT, "mining", "bench_mode.py")
ENDPOINT_CONFIG = os.path.join(
    ROOT, ".local", "mining-endpoint.json")

CHECKS = 0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(f"check {CHECKS} failed: {label}")
    print(f"ok {CHECKS} - {label}")


FORBIDDEN_MODULES = {
    "socket", "urllib", "requests", "http.client",
    "mining.stratum_client", "mining.endpoint_config",
    "mining.solo_server", "mining.solo_mainnet",
    "mining.mainnet_live", "mining.autopilot",
    "mining.candidate_verify", "agent.intelligence.scheduler",
}
FORBIDDEN_IDENTIFIERS = {
    "socket", "StratumClient", "SoloServer", "submit",
    "submit_share", "submitblock", "connect", "endpoint",
    "mining_endpoint", "getblocktemplate",
}
ALLOWED_IMPORT_ROOTS = {
    "argparse", "contextlib", "hashlib", "json", "os",
    "statistics", "struct", "sys", "time", "gpu",
}


def test_ast_structure():
    with open(BENCH_PATH, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imported = set()
    identifiers = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
        elif isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
    roots = {name.split(".")[0] for name in imported}
    check(roots <= ALLOWED_IMPORT_ROOTS,
          f"bench imports only stdlib plus the compute seam "
          f"(found {sorted(imported)})")
    bad = identifiers & FORBIDDEN_IDENTIFIERS
    check(not bad,
          f"no network/endpoint/submission identifier in "
          f"bench_mode AST (found {sorted(bad)})")
    check("gpu.engine" in imported,
          "bench imports the production compute seam")


def test_import_closure():
    code = (
        "import json, sys\n"
        "import mining.bench_mode\n"
        "print(json.dumps(sorted(sys.modules)))\n")
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT,
        capture_output=True, text=True, timeout=300)
    check(proc.returncode == 0,
          f"fresh interpreter imports bench_mode "
          f"(stderr: {proc.stderr.strip()[:200]})")
    modules = set(json.loads(proc.stdout.strip().splitlines()[-1]))
    leaked = modules & FORBIDDEN_MODULES
    check(not leaked,
          f"import closure free of network/submission "
          f"modules (found {sorted(leaked)})")


def test_self_check_and_measure():
    from gpu.engine import ComputeEngine
    from mining import bench_mode
    engine = ComputeEngine()
    result = bench_mode.self_check(engine)
    check(result["batch_digests_verified"] == 1024,
          "self-check verified 1024 batch digests vs hashlib")
    check(result["batch_digests_mismatched"] == 0,
          "self-check zero digest mismatches")
    check(result["genesis_found_by_engine"]
          and result["genesis_found_by_hashlib"],
          "genesis candidate found by engine and by hashlib")
    check(result["genesis_digest_matches"]
          and result["genesis_meets_target"],
          "genesis digest is the genesis hash and meets "
          "the genesis target")
    check(result["passed"], "self-check passes as a whole")
    attempted, wall, rate = bench_mode.measure_once(
        engine, 1 << 18)
    check(attempted == 1 << 18,
          "work unit scans the full fixed span at target 1")
    check(wall > 0 and rate > 0,
          "work unit yields a positive rate")


SOCKET_BLOCK_WRAPPER = '''
import runpy
import socket
import sys

sys.path.insert(0, {root!r})


class _BlockedSocket:
    def __init__(self, *a, **k):
        raise AssertionError("socket use attempted")


def _blocked(*a, **k):
    raise AssertionError("socket use attempted")


socket.socket = _BlockedSocket
socket.create_connection = _blocked
socket.getaddrinfo = _blocked
socket.gethostbyname = _blocked
sys.argv = ["bench_mode", "--repetitions", "1", "--json"]
runpy.run_module("mining.bench_mode", run_name="__main__")
'''


def _run_bench_subprocess(argv_env, cwd, wrapper=False):
    if wrapper:
        with tempfile.NamedTemporaryFile(
                "w", suffix=".py", delete=False) as f:
            f.write(SOCKET_BLOCK_WRAPPER.format(root=ROOT))
            path = f.name
        cmd = [sys.executable, path]
    else:
        cmd = [sys.executable,
               os.path.join(ROOT, "mining", "bench_mode.py"),
               "--repetitions", "1", "--json"]
    proc = subprocess.run(cmd, cwd=cwd, env=argv_env,
                          capture_output=True, text=True,
                          timeout=900)
    return proc


def _parse_report(proc):
    lines = [ln for ln in proc.stdout.splitlines()
             if ln.strip()]
    start = next(i for i, ln in enumerate(lines)
                 if ln.strip() == "{")
    return json.loads("\n".join(lines[start:]))


def test_socket_blocked_run():
    env = dict(os.environ)
    env["BAL_POOL_HOST"] = "invalid.invalid"
    env["BAL_POOL_PORT"] = "1"
    proc = _run_bench_subprocess(env, ROOT, wrapper=True)
    check(proc.returncode == 0,
          f"bench completes with the socket layer rigged "
          f"to raise (rc={proc.returncode}, "
          f"stderr: {proc.stderr.strip()[-300:]})")
    report = _parse_report(proc)
    check(report["self_check"]["passed"],
          "socket-blocked run self-check passed")
    check(report["median_rate_hs"] > 0,
          "socket-blocked run reports a positive rate")
    check(report["backend"] is not None
          and report["threads"] >= 1,
          "socket-blocked run reports backend and threads")


def test_clean_environment_run():
    tmp = tempfile.mkdtemp(prefix="exp049-clean-")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    proc = _run_bench_subprocess(env, tmp, wrapper=False)
    check(proc.returncode == 0,
          f"bench completes with an empty environment from "
          f"a foreign cwd (rc={proc.returncode}, "
          f"stderr: {proc.stderr.strip()[-300:]})")
    report = _parse_report(proc)
    check(bool(report["host"]["cpu_model"]),
          "clean run reports the host CPU model")
    check("category E" in report["category"]
          or report["category"].startswith("E:"),
          "clean run labels its rate category E")


def _endpoint_hash():
    try:
        with open(ENDPOINT_CONFIG, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def main():
    before = _endpoint_hash()
    test_ast_structure()
    test_import_closure()
    test_self_check_and_measure()
    test_socket_blocked_run()
    test_clean_environment_run()
    check(_endpoint_hash() == before,
          "endpoint configuration untouched by every run")
    print(f"ALL {CHECKS} EXP-049 BENCH MODE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
