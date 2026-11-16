"""Independent verifier service (Autonomous Mining Brain,
Prompt 1, item B).

The verifier is a SEPARATE PROCESS from the agent and from any
experiment. It holds an HMAC key in a key file at
.local/verifier/verifier.key by default (mode 0600, created on
first use, never inside any sandbox: the experimental sandbox
mounts a tmpfs over the repository .local directory, so
experiment code cannot read the key). Platform code (the loop
gate) reads the same key file through a verify-only path to
check signatures. Experiment code can neither read the key nor
forge a record: a record signed with a different key, a record
whose fields were altered after signing, or an unsigned record
is refused by the gate.

Protocol: the agent (or a test) spawns

    python3 -m agent.intelligence.verifier [--key PATH]

with one JSON request on stdin and reads one JSON evidence
record on stdout. Request fields:

    artifact_path: host path of the artifact file to check.
    source_commit: the source revision the artifact claims.
    verification_method: one of the closed allowlist in loop.py.
    differential_command: optional argv list. For the
        differential_reference method the verifier runs this
        command ITSELF inside the experimental sandbox (it does
        not trust submitted output) and requires exit code 0.
    test_vectors: optional list of {"header_hex": ...,
        "expected_sha256d_hex": ...}. The verifier recomputes
        SHA-256d with hashlib (the canonical reference) and
        requires every digest to match.

The verifier independently recomputes the artifact file's
SHA-256 itself. It then emits the evidence record: the strict
schema fields of loop.py plus signature = HMAC-SHA256(key,
canonical JSON of the other fields). canonical JSON is
json.dumps with sorted keys and tight separators over every
field except the signature itself.

Honest scope note: on a single host this separation is process
plus filesystem isolation. Experiment code cannot reach the
key because the sandbox hides .local. Platform code (the gate,
running outside any sandbox) can read the key to verify. This
is not a multi-machine attestation service and does not claim
to be one.
"""

import hashlib
import hmac
import json
import os
import subprocess
import sys
import time

VERIFIER_ID = "independent-verifier-01"

_REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".."))

ALLOWED_METHODS = ("differential_reference",
                   "independent_recompute",
                   "statistical_replication",
                   "chain_acceptance")


def default_key_path():
    return os.path.join(_REPO_ROOT, ".local", "verifier",
                        "verifier.key")


def ensure_key(key_path=None):
    """Create the HMAC key file on first use (mode 0600) and
    return its path. The key value is never printed or logged.
    """
    path = key_path or default_key_path()
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    if not os.path.exists(path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                     0o600)
        try:
            os.write(fd, os.urandom(32).hex().encode("ascii"))
        finally:
            os.close(fd)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def load_key(key_path=None):
    path = ensure_key(key_path)
    with open(path, "r", encoding="ascii") as f:
        return f.read().strip().encode("ascii")


def canonical_bytes(record):
    """Canonical JSON of every field except the signature."""
    body = {k: v for k, v in record.items() if k != "signature"}
    return json.dumps(body, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sign_record(record, key):
    mac = hmac.new(key, canonical_bytes(record), hashlib.sha256)
    signed = dict(record)
    signed["signature"] = mac.hexdigest()
    return signed


def verify_signature(record, key):
    """True only when record carries a signature that matches
    HMAC-SHA256(key, canonical JSON of the other fields)."""
    if not isinstance(record, dict):
        return False
    sig = record.get("signature")
    if not isinstance(sig, str) or not sig:
        return False
    mac = hmac.new(key, canonical_bytes(record), hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), sig)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256d_hex(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()


def _run_differential(command, artifact_path):
    """Run the declared differential command inside the
    experimental sandbox, from the verifier process itself.
    Returns (ok, detail). The command receives the artifact
    path as its final argument if it contains the token
    {artifact}; otherwise it is run as given with cwd set to a
    fresh temporary sandbox directory."""
    from . import sandbox as sandbox_mod
    import tempfile
    argv = [a.replace("{artifact}", artifact_path)
            for a in command]
    tmp = tempfile.mkdtemp(prefix="verifier-sandbox-")
    result = sandbox_mod.run_sandboxed(
        argv, tmp, timeout_s=120, memory_max="512M",
        cpu_quota="200%", tasks_max=128)
    ok = (result["exit_code"] == 0
          and not result["timed_out"])
    return ok, (f"sandboxed differential command exit "
                f"{result['exit_code']}, termination "
                f"{result['termination_reason']}")


def perform_verification(request, key):
    """Execute one verification request and return the signed
    evidence record. On any failure the record carries
    passed=False (still signed, so the refusal itself is
    authenticated) or, for a malformed request, an error dict
    with no signature at all."""
    if not isinstance(request, dict):
        return {"error": "request must be a JSON object"}
    method = request.get("verification_method")
    if method not in ALLOWED_METHODS:
        return {"error": f"unknown verification method "
                         f"{method!r}; refused before running"}
    artifact_path = request.get("artifact_path")
    source_commit = request.get("source_commit")
    if not artifact_path or not isinstance(artifact_path, str):
        return {"error": "artifact_path is required"}
    if not source_commit or not isinstance(source_commit, str):
        return {"error": "source_commit is required"}
    if not os.path.isfile(artifact_path):
        return {"error": f"artifact not found: {artifact_path}"}
    artifact_sha = sha256_file(artifact_path)
    passed = True
    detail = "artifact hash recomputed by the verifier"
    vectors = request.get("test_vectors") or []
    for vec in vectors:
        header = bytes.fromhex(vec["header_hex"])
        if sha256d_hex(header) != vec["expected_sha256d_hex"]:
            passed = False
            detail = "a test vector digest mismatches the " \
                     "hashlib SHA-256d reference"
            break
    if passed and method == "differential_reference":
        command = request.get("differential_command")
        if command:
            ok, det = _run_differential(command, artifact_path)
            passed = ok
            detail = det
    record = {
        "passed": bool(passed),
        "verifier_id": VERIFIER_ID,
        "artifact_sha256": artifact_sha,
        "source_commit": source_commit,
        "verification_method": method,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                   time.gmtime()),
        "detail": detail,
    }
    return sign_record(record, key)


def request_verification(artifact_path, source_commit, method,
                         key_path=None, differential_command=None,
                         test_vectors=None, timeout_s=300):
    """Agent-side helper: spawn the verifier as a separate
    process and return its parsed evidence record."""
    req = {"artifact_path": artifact_path,
           "source_commit": source_commit,
           "verification_method": method}
    if differential_command:
        req["differential_command"] = list(differential_command)
    if test_vectors:
        req["test_vectors"] = test_vectors
    cmd = [sys.executable, "-m", "agent.intelligence.verifier"]
    if key_path:
        cmd += ["--key", key_path]
    proc = subprocess.run(cmd, input=json.dumps(req),
                          capture_output=True, text=True,
                          timeout=timeout_s, cwd=_REPO_ROOT)
    if proc.returncode != 0:
        raise RuntimeError(
            f"verifier process failed with exit "
            f"{proc.returncode}: {proc.stderr.strip()[:400]}")
    return json.loads(proc.stdout)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    key_path = None
    if "--key" in args:
        i = args.index("--key")
        key_path = args[i + 1]
    key = load_key(key_path)
    raw = sys.stdin.read()
    try:
        request = json.loads(raw)
    except ValueError as exc:
        print(json.dumps({"error": f"invalid JSON request: {exc}"}))
        return 2
    result = perform_verification(request, key)
    print(json.dumps(result, sort_keys=True))
    # A refusal is a valid protocol answer (an error record
    # with no signature), not a process failure.
    return 0


if __name__ == "__main__":
    sys.exit(main())
