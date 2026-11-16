#!/usr/bin/env python3
"""Prompt 1 adversarial security tests for the agent
intelligence package (Autonomous Mining Brain, Prompt 1):
strict evidence schema, independent verifier service,
experimental sandbox isolation and limits, operational /
experimental separation, and the hash-chained evidence
ledger.

Demonstrates the mandate's 13 acceptance items, numbered in
the test functions below:

1.  {"result": "false"} cannot pass a gate.
2.  "true" (string) and 1 (int) cannot substitute for
    Boolean True.
3.  NaN and infinity in statistical evidence rejected;
    inverted confidence interval rejected.
4.  A forged verifier identity or signature is rejected.
5.  Evidence bound to a different source commit or artifact
    hash is rejected.
6.  A sandboxed experiment cannot write outside its sandbox.
    Post-audit (defect D-1): the auditor's exact attacks in
    general form (writes to /etc, the home directory and
    /usr/local/share, a write through an in-sandbox symlink,
    reads of /etc/shadow, a host-only marker and the
    verifier key, host /proc visibility, payload uid) are
    permanent regression tests in test_sandbox_escape_paths.
    The evidence ledger's signed external anchor is tested
    in test_ledger_anchor (tail truncation to 2 and to 0
    records detected; a forged anchor rejected).
7.  It cannot read production secrets.
8.  It cannot access the host network by default.
9.  It cannot modify production files.
10. A timed-out process tree is terminated.
11. CPU and memory limits are enforced.
12. A failed security check refuses execution.
13. A sandbox failure does not terminate the production
    miner.

Run: python3 tests/test_agent_security.py
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import types

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from agent.intelligence import Agent
from agent.intelligence import sandbox as sandbox_mod
from agent.intelligence import verifier
from agent.intelligence.experiments import (
    CURRENT_SOURCE_COMMIT, ExperimentRunner)
from agent.intelligence.interface import MiningInterface, \
    StatusRequest
from agent.intelligence.loop import (
    OptimisationLoop, validate_integrate_evidence)
from agent.intelligence.permissions import (
    ACTION_REGISTRY, Level, PermissionChecker, PermissionError,
    assert_no_shell_payload)

CHECKS = 0
REPO = os.path.abspath(ROOT)


def check(cond, msg):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(msg)


def raises(exc_type, fn, msg):
    global CHECKS
    CHECKS += 1
    try:
        fn()
    except exc_type as exc:
        return exc
    raise AssertionError(msg + " (no exception raised)")


def make_agent(tmp):
    return Agent(local_dir=tmp,
                 audit_path=os.path.join(tmp, "a.jsonl"),
                 tasks_path=os.path.join(tmp, "t.json"),
                 sandbox_root=os.path.join(tmp, "sandbox"))


def vrec(verifier_id, artifact_sha, commit=CURRENT_SOURCE_COMMIT,
         method="differential_reference", passed=True):
    return {"passed": passed, "verifier_id": verifier_id,
            "artifact_sha256": artifact_sha,
            "source_commit": commit,
            "verification_method": method,
            "timestamp": "2026-11-15T00:00:00Z"}


def heartbeat_pids():
    path = os.path.join(REPO, ".local", "heartbeat.json")
    with open(path) as f:
        hb = json.load(f)
    return hb.get("autopilot_pid"), hb.get("miner_pid"), hb


# Items 1, 2, 3: strict evidence schema ------------------------

def test_evidence_schema(tmp):
    key_path = os.path.join(tmp, "vkey", "verifier.key")
    key = verifier.load_key(key_path)
    art = "b" * 64
    loop = OptimisationLoop(memory=None)
    rec = loop.new_record("SEC-SCHEMA", "schema probe",
                          implementation_author="agent-a",
                          performance_claim=True)
    indep = verifier.sign_record(
        vrec(verifier.VERIFIER_ID, art,
             method="independent_recompute"), key)
    good = {"correctness": vrec("agent-a", art),
            "differential": vrec("agent-a", art),
            "independent_verification": indep,
            "exp017_verdict": {"sessions": 3,
                               "pooled_ratio": 1.4,
                               "ci_low": 0.24, "ci_high": 0.58}}
    rec.evidence.update(good)
    check(validate_integrate_evidence(
        rec, verifier_key_path=key_path) == [],
        "a fully valid strict bundle passes the gate")

    # Item 1: {"result": "false"} must never pass.
    rec.evidence["correctness"] = {"result": "false"}
    missing = validate_integrate_evidence(
        rec, verifier_key_path=key_path)
    check(any("correctness" in m for m in missing),
          'item 1: {"result": "false"} cannot pass')
    # Item 2a: the string "true" is not Boolean True.
    bad = vrec("agent-a", art)
    bad["passed"] = "true"
    rec.evidence["correctness"] = bad
    missing = validate_integrate_evidence(
        rec, verifier_key_path=key_path)
    check(any("correctness" in m for m in missing),
          'item 2: passed="true" (string) is refused')
    # Item 2b: the integer 1 is not Boolean True.
    bad = vrec("agent-a", art)
    bad["passed"] = 1
    rec.evidence["correctness"] = bad
    missing = validate_integrate_evidence(
        rec, verifier_key_path=key_path)
    check(any("correctness" in m for m in missing),
          "item 2: passed=1 (int) is refused")
    # A bare Boolean is not a verification record either.
    rec.evidence["correctness"] = True
    missing = validate_integrate_evidence(
        rec, verifier_key_path=key_path)
    check(any("correctness" in m for m in missing),
          "a bare True is not a verification record")
    rec.evidence["correctness"] = vrec("agent-a", art)
    # Unknown verification method refused.
    bad = vrec("agent-a", art)
    bad["verification_method"] = "self_attestation"
    rec.evidence["differential"] = bad
    missing = validate_integrate_evidence(
        rec, verifier_key_path=key_path)
    check(any("differential" in m for m in missing),
          "unknown verification method is refused")
    rec.evidence["differential"] = vrec("agent-a", art)
    # Item 3: NaN, infinity, inverted CI, bad sessions.
    for verdict, label in (
            ({"sessions": 3, "pooled_ratio": float("nan"),
              "ci_low": 0.2, "ci_high": 0.5}, "NaN ratio"),
            ({"sessions": 3, "pooled_ratio": 1.4,
              "ci_low": 0.2, "ci_high": float("inf")},
             "infinite CI bound"),
            ({"sessions": 3, "pooled_ratio": 1.4,
              "ci_low": 0.58, "ci_high": 0.24},
             "inverted CI"),
            ({"sessions": 2, "pooled_ratio": 1.4,
              "ci_low": 0.2, "ci_high": 0.5},
             "fewer than 3 sessions"),
            ({"sessions": "3", "pooled_ratio": 1.4,
              "ci_low": 0.2, "ci_high": 0.5},
             "sessions as a string")):
        rec.evidence["exp017_verdict"] = verdict
        missing = validate_integrate_evidence(
            rec, verifier_key_path=key_path)
        check(any("EXP-017" in m for m in missing),
              f"item 3: {label} is rejected")
    rec.evidence["exp017_verdict"] = good["exp017_verdict"]
    check(validate_integrate_evidence(
        rec, verifier_key_path=key_path) == [],
        "restored valid bundle passes again")


# Items 4, 5: verifier service, forgery, binding ---------------

def test_verifier_service(tmp):
    key_path = os.path.join(tmp, "vkey2", "verifier.key")
    artifact = os.path.join(tmp, "artifact.bin")
    with open(artifact, "wb") as f:
        f.write(b"verified artifact contents\n")
    art_sha = hashlib.sha256(
        b"verified artifact contents\n").hexdigest()
    signed = verifier.request_verification(
        artifact, CURRENT_SOURCE_COMMIT,
        "independent_recompute", key_path=key_path)
    check(signed["passed"] is True
          and signed["artifact_sha256"] == art_sha
          and signed["verifier_id"] == verifier.VERIFIER_ID
          and "signature" in signed,
          "verifier service returns a signed passing record")
    loop = OptimisationLoop(memory=None)
    rec = loop.new_record("SEC-VER", "verifier probe",
                          implementation_author="agent-a")
    rec.evidence.update({
        "correctness": vrec("agent-a", art_sha),
        "differential": vrec("agent-a", art_sha),
        "independent_verification": signed})
    check(validate_integrate_evidence(
        rec, verifier_key_path=key_path) == [],
        "gate accepts the genuine verifier record")
    # Item 4a: forged verifier identity (signature now wrong).
    forged = dict(signed)
    forged["verifier_id"] = "independent-verifier-99"
    rec.evidence["independent_verification"] = forged
    missing = validate_integrate_evidence(
        rec, verifier_key_path=key_path)
    check(any("signature" in m for m in missing),
          "item 4: forged verifier identity is rejected")
    # Item 4b: record signed with a different key.
    other_key = verifier.load_key(
        os.path.join(tmp, "other", "verifier.key"))
    wrong = verifier.sign_record(
        vrec(verifier.VERIFIER_ID, art_sha,
             method="independent_recompute"), other_key)
    rec.evidence["independent_verification"] = wrong
    missing = validate_integrate_evidence(
        rec, verifier_key_path=key_path)
    check(any("signature" in m for m in missing),
          "item 4: a record signed with a different key is "
          "rejected")
    # Item 4c: unsigned record.
    unsigned = dict(signed)
    del unsigned["signature"]
    rec.evidence["independent_verification"] = unsigned
    missing = validate_integrate_evidence(
        rec, verifier_key_path=key_path)
    check(any("signature" in m for m in missing),
          "item 4: an unsigned record is rejected")
    # Item 4d: self-verification by the author, even signed
    # with a key the author controls, is not independent.
    rec.evidence["independent_verification"] = \
        verifier.sign_record(
            vrec("agent-a", art_sha,
                 method="independent_recompute"),
            verifier.load_key(key_path))
    missing = validate_integrate_evidence(
        rec, verifier_key_path=key_path)
    check(any("other" in m for m in missing),
          "item 4: verifier_id equal to the author is "
          "rejected as not independent")
    rec.evidence["independent_verification"] = signed
    # Item 5a: bundle records bound to different artifacts.
    rec.evidence["correctness"] = vrec("agent-a", "c" * 64)
    missing = validate_integrate_evidence(
        rec, verifier_key_path=key_path)
    check(any("binding mismatch" in m for m in missing),
          "item 5: records bound to different artifacts are "
          "rejected")
    rec.evidence["correctness"] = vrec("agent-a", art_sha)
    # Item 5b: expected binding on the loop record itself.
    rec2 = loop.new_record(
        "SEC-VER2", "binding probe",
        implementation_author="agent-a",
        artifact_sha256=art_sha,
        source_commit="some-other-commit")
    rec2.evidence.update(rec.evidence)
    missing = validate_integrate_evidence(
        rec2, verifier_key_path=key_path)
    check(any("different source_commit" in m for m in missing),
          "item 5: evidence bound to a different source "
          "commit than expected is rejected")
    # Item 12 (gate half): unknown method refused by the
    # verifier before anything runs.
    refused = verifier.request_verification(
        artifact, CURRENT_SOURCE_COMMIT, "bogus_method",
        key_path=key_path)
    check("error" in refused and "signature" not in refused,
          "item 12: the verifier refuses an unknown method "
          "and issues no record")
    # Differential vectors: the verifier recomputes SHA-256d
    # itself against the hashlib reference.
    header = bytes(range(80))
    expect = hashlib.sha256(
        hashlib.sha256(header).digest()).hexdigest()
    ok_rec = verifier.request_verification(
        artifact, CURRENT_SOURCE_COMMIT,
        "differential_reference", key_path=key_path,
        test_vectors=[{"header_hex": header.hex(),
                       "expected_sha256d_hex": expect}])
    check(ok_rec["passed"] is True,
          "verifier accepts a correct differential vector")
    bad_rec = verifier.request_verification(
        artifact, CURRENT_SOURCE_COMMIT,
        "differential_reference", key_path=key_path,
        test_vectors=[{"header_hex": header.hex(),
                       "expected_sha256d_hex": "0" * 64}])
    check(bad_rec["passed"] is False and "signature" in bad_rec,
          "verifier signs a failing record for a wrong vector")


# Item D: operational / experimental separation -----------------

def test_separation(tmp):
    for name, spec in ACTION_REGISTRY.items():
        check(spec.shell is False,
              f"spec {name} carries shell=False")
        if spec.level == Level.L3:
            check(spec.kind == "experimental",
                  f"L3 spec {name} is kind=experimental")
        else:
            check(spec.kind == "operational",
                  f"spec {name} is kind=operational")
    raises(PermissionError,
           lambda: assert_no_shell_payload(
               "start_mining", {"command": "rm -rf /"}),
           "a command payload through an operational spec is "
           "refused")
    check(assert_no_shell_payload(
        "start_mining", {"action": "start"}) is not None,
        "a clean typed payload passes the payload guard")
    raises(TypeError, lambda: StatusRequest(command="ls"),
           "request dataclasses reject extra fields")
    agent = make_agent(tmp)
    payload = types.SimpleNamespace(command="ls")
    raises(PermissionError,
           lambda: agent.interface.inspect_status(
               request=payload),
           "MiningInterface refuses a shell payload on an "
           "operational operation")


# Items 6, 7, 8, 9: sandbox isolation ---------------------------

def test_sandbox_isolation(tmp):
    agent = make_agent(tmp)
    runner = ExperimentRunner(agent)
    record, _sandbox = runner.create_experiment(
        "sandbox isolation probe",
        ["zzz-novel-sec", "sandbox", "isolation"], "agent-test")
    ok_probe, detail = sandbox_mod.probe_isolation()
    check(ok_probe, f"sandbox probe passes on this host: "
                    f"{detail}")
    # gcc works inside the sandbox.
    runner.write_file(record, "t.c",
                      "#include <stdio.h>\n"
                      "int main(){printf(\"sbx-hello\\n\");"
                      "return 0;}\n")
    r = runner.run_command(
        record, ["gcc", "-O2", "-o", "t", "t.c"], timeout_s=60)
    check(r["exit_code"] == 0, "gcc compiles inside the sandbox")
    r = runner.run_command(record, ["./t"], timeout_s=30)
    check(r["exit_code"] == 0 and "sbx-hello" in
          open(os.path.join(runner.sandbox_of(record),
                            r["stdout_file"])).read(),
          "the compiled program runs inside the sandbox")
    # python3 hashlib differential inside the sandbox.
    expect = hashlib.sha256(
        hashlib.sha256(b"bal-differential").digest()
        ).hexdigest()
    r = runner.run_command(
        record, [sys.executable, "-c",
                 "import hashlib\n"
                 "print(hashlib.sha256(hashlib.sha256("
                 "b'bal-differential').digest()).hexdigest())\n"],
        timeout_s=30)
    out = open(os.path.join(runner.sandbox_of(record),
                            r["stdout_file"])).read()
    check(r["exit_code"] == 0 and expect in out,
          "python3 hashlib SHA-256d differential inside the "
          "sandbox matches the host reference")
    # Item 6 + 9: writes outside the sandbox.
    engine = os.path.join(REPO, "mining", "engine.py")
    with open(engine, "rb") as f:
        engine_before = hashlib.sha256(f.read()).hexdigest()
    marker = f"/tmp/bal-sbx-marker-{os.getpid()}"
    code = (
        "import sys\n"
        "results = []\n"
        f"for path in ({marker!r}, {engine!r}):\n"
        "    try:\n"
        "        open(path, 'a').write('x')\n"
        "        results.append('WROTE:' + path)\n"
        "    except OSError as e:\n"
        "        results.append('BLOCKED:' + type(e).__name__)\n"
        "print('\\n'.join(results))\n")
    r = runner.run_command(record, [sys.executable, "-c", code],
                           timeout_s=30)
    out = open(os.path.join(runner.sandbox_of(record),
                            r["stdout_file"])).read()
    check(not os.path.exists(marker),
          "item 6: a write to host /tmp does not land on the "
          "host (namespace tmpfs only)")
    with open(engine, "rb") as f:
        engine_after = hashlib.sha256(f.read()).hexdigest()
    check(engine_before == engine_after,
          "item 9: production file mining/engine.py is "
          "unchanged after a sandboxed write attempt")
    check("WROTE:" + engine not in out,
          "item 9: the production write attempt did not "
          "succeed inside the sandbox either")
    # Item 7: production secrets are unreadable.
    secrets = [
        os.path.join(REPO, ".local", "mainnet", "bitcoin.conf"),
        os.path.join(os.path.dirname(REPO),
                     "bitcoin-autonomous-lab-secrets",
                     "lab-wallet.json"),
        os.path.join(os.path.expanduser("~"), ".ssh",
                     "id_ed25519")]
    code = (
        "import sys\n"
        f"paths = {secrets!r}\n"
        "for p in paths:\n"
        "    try:\n"
        "        open(p).read()\n"
        "        print('READ:' + p)\n"
        "    except OSError:\n"
        "        print('BLOCKED:' + p)\n")
    r = runner.run_command(record, [sys.executable, "-c", code],
                           timeout_s=30)
    out = open(os.path.join(runner.sandbox_of(record),
                            r["stdout_file"])).read()
    check("READ:" not in out and out.count("BLOCKED:") == 3,
          "item 7: node config, wallet secrets and SSH keys "
          "are all unreadable inside the sandbox")
    # Item 8: no network by default.
    code = (
        "import socket\n"
        "for host in ('1.1.1.1', '8.8.8.8'):\n"
        "    s = socket.socket()\n"
        "    s.settimeout(3)\n"
        "    try:\n"
        "        s.connect((host, 53))\n"
        "        print('NETOK:' + host)\n"
        "    except OSError:\n"
        "        print('NETBLOCKED:' + host)\n")
    r = runner.run_command(record, [sys.executable, "-c", code],
                           timeout_s=30)
    out = open(os.path.join(runner.sandbox_of(record),
                            r["stdout_file"])).read()
    check("NETOK:" not in out and out.count("NETBLOCKED:") == 2,
          "item 8: outbound TCP connects fail inside the "
          "sandbox network namespace")
    return runner, record


# Item 6 (general form, post-audit D-1): the private root -----

def test_sandbox_escape_paths(tmp):
    """The Prompt 1 auditor's exact attacks, as permanent
    regression tests. The first sandbox build enumerated a
    few covered paths and left the rest of the host
    filesystem exposed; the rebuilt sandbox replaces the
    root filesystem via pivot_root, so host paths are absent
    or read-only and the payload runs as uid 65534. Every
    marker is verified absent from the HOST side afterwards.
    """
    agent = make_agent(tmp)
    runner = ExperimentRunner(agent)
    record, _sandbox = runner.create_experiment(
        "sandbox escape paths probe",
        ["zzz-novel-sec6", "sandbox", "escape"], "agent-test")
    rand = f"{os.getpid()}{int(time.time()) % 100000}"
    _auto_pid, miner_pid, _hb = heartbeat_pids()
    # A host-only marker file at a random path outside the
    # sandbox, planted by the test on the host.
    host_marker = os.path.join(
        tmp, f"host-only-{rand}.txt")
    with open(host_marker, "w") as f:
        f.write("host only marker content\n")
    verifier.load_key()  # ensure the production key exists
    vkey = verifier.default_key_path()
    memory_md = os.path.join(os.path.expanduser("~"),
                             "MEMORY.md")
    with open("/etc/hostname", "rb") as f:
        hostname_before = hashlib.sha256(f.read()).hexdigest()
    code = (
        "import os\n"
        "print('UID', os.getuid(), os.geteuid(), "
        "os.getgid())\n"
        "def w(p):\n"
        "    try:\n"
        "        open(p, 'w').write('PWNED')\n"
        "        print('WROTE', p)\n"
        "    except OSError as e:\n"
        "        print('WRITE_BLOCKED', p, type(e).__name__)\n"
        "def r(p):\n"
        "    try:\n"
        "        open(p, 'rb').read()\n"
        "        print('READ', p)\n"
        "    except OSError as e:\n"
        "        print('READ_BLOCKED', p, "
        "type(e).__name__)\n"
        f"w('/etc/bal-esc-{rand}')\n"
        f"w('/home/hatch/bal-esc-{rand}')\n"
        f"w('/usr/local/share/bal-esc-{rand}')\n"
        "w('/etc/hostname')\n"
        "os.symlink('/etc', 'esc-link')\n"
        f"w('esc-link/bal-esc-{rand}')\n"
        "r('/etc/shadow')\n"
        f"r({host_marker!r})\n"
        f"r({vkey!r})\n"
        "r('/source/.local/verifier/verifier.key')\n"
        f"r({memory_md!r})\n"
        f"print('HOSTPID_VISIBLE', "
        f"os.path.exists('/proc/{miner_pid}'))\n"
        "leaks = []\n"
        "for p in os.listdir('/proc'):\n"
        "    if not p.isdigit() or p == str(os.getpid()):\n"
        "        continue\n"
        "    try:\n"
        "        c = open('/proc/' + p + '/cmdline', "
        "'rb').read()\n"
        "    except OSError:\n"
        "        continue\n"
        "    if b'mainnet_live' in c or b'autopilot' in c "
        "or b'bitcoind' in c:\n"
        "        leaks.append(p)\n"
        "print('HOST_CMDLINE_LEAKS', leaks)\n")
    r = runner.run_command(record, [sys.executable, "-c", code],
                           timeout_s=60)
    out = open(os.path.join(runner.sandbox_of(record),
                            r["stdout_file"])).read()
    check("UID 65534 65534 65534" in out,
          "D-1: the payload runs as uid/euid/gid 65534, "
          "never as root")
    check("WROTE" not in out
          and out.count("WRITE_BLOCKED") == 5,
          "D-1: writes to /etc, /home/hatch, "
          "/usr/local/share, /etc/hostname and through an "
          "in-sandbox symlink to /etc are all blocked")
    check("\nREAD " not in "\n" + out
          and out.count("READ_BLOCKED") == 5,
          "D-1: /etc/shadow, the host-only marker, the "
          "verifier key (by host path and via /source/.local) "
          "and the host MEMORY.md are all unreadable")
    check("HOSTPID_VISIBLE False" in out,
          "D-1: the host miner pid is not visible in the "
          "sandbox /proc (fresh procfs, own pid namespace)")
    check("HOST_CMDLINE_LEAKS []" in out,
          "D-1: no host miner, autopilot or bitcoind cmdline "
          "is enumerable from inside the sandbox")
    # Host-side verification: nothing landed on the host.
    for path in (f"/etc/bal-esc-{rand}",
                 f"/home/hatch/bal-esc-{rand}",
                 f"/usr/local/share/bal-esc-{rand}"):
        check(not os.path.exists(path),
              f"D-1: host side confirms no file at {path}")
    with open("/etc/hostname", "rb") as f:
        hostname_after = hashlib.sha256(f.read()).hexdigest()
    check(hostname_before == hostname_after,
          "D-1: host /etc/hostname is byte-identical after "
          "the in-sandbox write attempt")
    # id(1) agrees: the payload uid is non-zero.
    r = runner.run_command(record, ["id", "-u"], timeout_s=30)
    out = open(os.path.join(runner.sandbox_of(record),
                            r["stdout_file"])).read()
    check(out.strip() == "65534",
          "D-1: id -u inside the sandbox reports 65534")


# Items 10, 11: limits and process-tree termination -------------

def test_sandbox_limits(tmp):
    agent = make_agent(tmp)
    runner = ExperimentRunner(agent)
    record, _s = runner.create_experiment(
        "sandbox limits probe",
        ["zzz-novel-sec2", "sandbox", "limits"], "agent-test")
    # Item 10: a timed-out process tree is terminated.
    marker = f"bal-hb-child-{os.getpid()}"
    child = ("import time\n"
             "while True:\n"
             "    open('hb.txt', 'a').write('x\\n')\n"
             "    time.sleep(0.2)\n")
    parent = ("import subprocess, sys, time\n"
              f"subprocess.Popen([sys.executable, '-c', "
              f"{child!r}, '--', '{marker}'])\n"
              "time.sleep(60)\n")
    r = runner.run_command(record, [sys.executable, "-c", parent],
                           timeout_s=3)
    check(r["timed_out"] and r["termination_reason"] == "timeout",
          "item 10: the run times out with the reason recorded")
    hb_path = os.path.join(runner.sandbox_of(record), "hb.txt")
    n1 = open(hb_path).read().count("x")
    time.sleep(1.5)
    n2 = open(hb_path).read().count("x")
    check(n1 > 0 and n1 == n2,
          "item 10: the spawned child's heartbeats stopped "
          "after the timeout (whole tree terminated)")
    procs = subprocess.run(["pgrep", "-f", marker],
                           capture_output=True, text=True)
    check(procs.returncode != 0,
          "item 10: no surviving process carries the child "
          "marker")
    # Item 11a: memory limit enforced by the watchdog.
    hog = ("blocks = []\n"
           "while True:\n"
           "    b = bytearray(64 << 20)\n"
           "    for i in range(0, len(b), 4096):\n"
           "        b[i] = 1\n"
           "    blocks.append(b)\n")
    r = runner.run_command(record, [sys.executable, "-c", hog],
                           timeout_s=60, memory_max="128M")
    check(r["termination_reason"] == "memory"
          and r["wall_s"] < 30,
          "item 11: a memory hog is killed by the memory "
          f"limit (reason {r['termination_reason']}, wall "
          f"{r['wall_s']})")
    # Item 11b: a CPU hog is bounded by its CPU/time budget
    # and the termination is recorded.
    r = runner.run_command(
        record, [sys.executable, "-c",
                 "while True:\n    pass\n"],
        timeout_s=3, cpu_quota="50%")
    check(r["timed_out"] and r["termination_reason"] == "timeout",
          "item 11: a CPU hog runs only to its time budget "
          "with the termination reason recorded")


# Item 12: failed security checks refuse execution ---------------

def test_refusals_and_ledger(tmp):
    agent = make_agent(tmp)
    runner = ExperimentRunner(agent)
    record, _s = runner.create_experiment(
        "ledger probe",
        ["zzz-novel-sec3", "ledger"], "agent-test")
    r = runner.run_command(record, [sys.executable, "-c",
                                    "print('ledger run')"],
                           timeout_s=30)
    check(r["exit_code"] == 0, "ledger experiment run succeeds")
    ok, detail = runner.verify_ledger(record.loop_id)
    check(ok, f"evidence ledger verifies: {detail}")
    # Tamper: rewrite a middle record; the chain must break.
    path = runner.ledger_path(record.loop_id)
    with open(path) as f:
        lines = f.readlines()
    check(len(lines) >= 2, "ledger holds multiple records")
    entry = json.loads(lines[0])
    entry["kind"] = "forged"
    lines[0] = json.dumps(entry, sort_keys=True) + "\n"
    with open(path, "w") as f:
        f.writelines(lines)
    ok, detail = runner.verify_ledger(record.loop_id)
    check(not ok, "item 12: a tampered evidence ledger is "
                  f"detected ({detail})")
    # Sandbox unavailability refuses execution outright.
    saved = sandbox_mod._probe_cache
    sandbox_mod._probe_cache = (False, "test-forced failure")
    try:
        raises(sandbox_mod.SandboxUnavailable,
               lambda: runner.run_command(
                   record, [sys.executable, "-c", "print(1)"],
                   timeout_s=10),
               "item 12: with isolation unavailable, execution "
               "is refused, never run unsandboxed")
    finally:
        sandbox_mod._probe_cache = saved


# Ledger anchor: tail truncation is detected -------------------

def test_ledger_anchor(tmp):
    agent = make_agent(tmp)
    runner = ExperimentRunner(agent)
    record, _s = runner.create_experiment(
        "ledger anchor probe",
        ["zzz-novel-sec7", "ledger", "anchor"], "agent-test")
    for _ in range(2):
        r = runner.run_command(
            record, [sys.executable, "-c",
                     "print('anchor run')"], timeout_s=60)
        check(r["exit_code"] == 0,
              "anchor experiment run succeeds")
    ok, detail = runner.verify_ledger(record.loop_id)
    check(ok, f"a genuine ledger verifies against its "
              f"anchor: {detail}")
    apath = runner.anchor_path(record.loop_id)
    check(os.path.exists(apath),
          "the anchor file exists next to the ledger")
    with open(apath) as f:
        anchor = json.load(f)
    check(anchor.get("record_count") == 3
          and anchor.get("experiment_id") == record.loop_id
          and "signature" in anchor,
          "the anchor carries the experiment id, the record "
          "count and a signature")
    path = runner.ledger_path(record.loop_id)
    with open(path) as f:
        lines = f.readlines()
    check(len(lines) == 3, "the ledger holds three records")
    # Tail truncation to 2 records: the bare hash chain
    # would still verify; the anchor must catch it.
    with open(path, "w") as f:
        f.writelines(lines[:2])
    ok, detail = runner.verify_ledger(record.loop_id)
    check(not ok and "anchor" in detail,
          f"tail truncation to 2 records is detected via "
          f"the anchor ({detail})")
    # Tail truncation to 0 records.
    with open(path, "w") as f:
        f.write("")
    ok, detail = runner.verify_ledger(record.loop_id)
    check(not ok, "tail truncation to 0 records is detected")
    # A forged anchor (count edited, signature invalidated)
    # is rejected.
    record2, _s2 = runner.create_experiment(
        "ledger anchor forge probe",
        ["zzz-novel-sec8", "ledger", "anchor", "forge"],
        "agent-test")
    ok, detail = runner.verify_ledger(record2.loop_id)
    check(ok, f"a second genuine ledger verifies: {detail}")
    apath2 = runner.anchor_path(record2.loop_id)
    with open(apath2) as f:
        anchor2 = json.load(f)
    anchor2["record_count"] = 99
    with open(apath2, "w") as f:
        json.dump(anchor2, f)
    ok, detail = runner.verify_ledger(record2.loop_id)
    check(not ok and "anchor" in detail,
          f"a forged anchor is rejected ({detail})")


def main():
    pids_before = heartbeat_pids()
    tmp = tempfile.mkdtemp(prefix="agent-security-")
    test_evidence_schema(tmp)
    test_verifier_service(tmp)
    test_separation(tmp)
    test_sandbox_isolation(tmp)
    test_sandbox_escape_paths(tmp)
    test_sandbox_limits(tmp)
    test_refusals_and_ledger(tmp)
    test_ledger_anchor(tmp)
    # Item 13: the production miner survived every failure
    # above, untouched.
    auto_pid, miner_pid, hb = heartbeat_pids()
    check((auto_pid, miner_pid) == pids_before[:2],
          "item 13: autopilot and miner pids are identical "
          "before and after the sandbox failure tests "
          f"({pids_before[:2]} vs {(auto_pid, miner_pid)})")
    check(hb.get("miner_state") == "running",
          "item 13: the miner is still running")
    print(f"ALL AGENT SECURITY TESTS PASSED ({CHECKS} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
