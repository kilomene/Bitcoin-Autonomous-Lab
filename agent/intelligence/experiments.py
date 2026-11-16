"""Executable optimisation loop (Master Build Mandate
sections 5 and 14, Milestone 3).

loop.py defines the optimisation cycle as a gated state
machine over records. This module makes the cycle executable:
an ExperimentRunner bound to the Agent facade creates a real
sandbox directory per experiment, runs real commands inside
it, collects the evidence files those commands produce, and
feeds the assembled bundle to the loop's integrate gate.

Boundaries, enforced here and not merely documented:

- The runner NEVER edits production code and NEVER performs
  integration. The integrate transition stays a gated record
  decision in loop.py; attempt_integrate only asks the gate
  and reports its verdict.
- Every path the runner writes to goes through target_path,
  which resolves the path and asserts containment inside the
  experiment's sandbox. Escapes are refused.
- Commands are argv lists executed without a shell. A shell
  string is refused, so no experiment can smuggle shell
  syntax into the runner.
- A hypothesis whose keywords match a REJECTED research
  memory entry is refused at the hypothesise gate by the
  loop itself; the refusal carries the rejection citation.

Evidence files are JSON documents in the sandbox with this
schema (Prompt 1 strict form):

    {"correctness": <verification record>,
     "differential": <verification record>,
     "independent_verification": <signed verification
        record from the verifier service>,
     "exp017": {"sessions": int, "pooled_ratio": float,
                "ci_low": float, "ci_high": float} or null}

where a verification record is the strict schema of loop.py
(passed Boolean, verifier_id, artifact_sha256, source_commit,
verification_method from the allowlist, ISO-8601 timestamp)
and the exp017 confidence interval is for the pooled ratio
itself. assemble_evidence converts it to the loop gate's
form, whose interval is for the relative improvement (ratio
minus 1) and must lie entirely above 0.

Execution (Prompt 1): run_command executes through
agent/intelligence/sandbox.py, real operating-system
isolation (systemd-run scope limits plus unshare namespaces,
repository read-only, credentials hidden, no network). If
isolation is unavailable the command is refused, never run
unsandboxed.

Evidence integrity (Prompt 1): every run, evidence assembly
and gate decision also appends a hash-chained record to an
append-only ledger OUTSIDE the writable sandbox, at
.local/agent-evidence/<experiment_id>.jsonl. verify_ledger
recomputes the chain and reports tampering. Every append
also atomically updates a signed external anchor
(<experiment_id>.anchor.json: experiment id, record count,
last record hash, HMAC-signed with the verifier key), and
verify_ledger checks the ledger against it, so deleting
whole tail records is detected as well (post-audit fix;
a bare hash chain cannot detect tail truncation).
"""

import hashlib
import json
import os
import subprocess
import time
import uuid

from . import sandbox as _sandbox
from . import verifier as _verifier
from .loop import (CHECK_PRIOR, HYPOTHESISE, INTEGRATED, RECORD,
                   LoopRefusal)

_REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".."))

# The recorded remote HEAD at the start of the Autonomous
# Mining Brain mandate; the current source revision
# identifier bound into experiment evidence ledgers.
CURRENT_SOURCE_COMMIT = "18ff4eb070a066dec4424cf9cd4d8282fa9a38b3"


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _gcc_version():
    try:
        out = subprocess.run(["gcc", "--version"],
                             capture_output=True, text=True,
                             timeout=15)
        return out.stdout.splitlines()[0].strip() \
            if out.stdout else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def _cpu_model():
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8",
                  errors="replace") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "unknown"


class SandboxEscape(Exception):
    """A path an experiment tried to use resolves outside its
    sandbox."""


class ExperimentRunner:
    """Runs loop.py records as real sandboxed experiments.

    agent: the agent.intelligence.Agent facade. The runner
    uses the facade's loop machine, research memory (through
    the loop), permission checker, audit log and sandbox
    root.
    """

    def __init__(self, agent):
        self.agent = agent
        self.loop = agent.loop()
        self.records = {}
        self.sandboxes = {}
        self._run_counts = {}

    # Creation -------------------------------------------------
    def create_experiment(self, hypothesis, keywords, author,
                          performance_claim=False):
        """Open a loop record and its sandbox directory, then
        advance the record through the hypothesise gate.

        Returns (record, sandbox_path). Raises LoopRefusal
        with the rejection citation when the hypothesis
        matches a REJECTED research memory entry; the record
        is left at the hypothesise state in that case.
        Raises modes.ModeRefusal when the load-shedding mode
        sheds experiment work (Brownout or Critical): no new
        experiment runs start in those modes.
        """
        modes = getattr(self.agent, "modes", None)
        if modes is not None:
            modes.require_allowed(
                "experiment",
                detail="create_experiment refused by the "
                       "load-shedding mode")
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        experiment_id = f"exp-{stamp}-{uuid.uuid4().hex[:6]}"
        sandbox = os.path.join(self.agent.sandbox_root,
                               experiment_id)
        self.agent.checker.require("create_experiment",
                                   sandbox_path=sandbox)
        os.makedirs(sandbox, exist_ok=True)
        record = self.loop.new_record(
            experiment_id, hypothesis, keywords=list(keywords),
            implementation_author=author,
            performance_claim=bool(performance_claim))
        self.records[experiment_id] = record
        self.sandboxes[experiment_id] = sandbox
        self._run_counts[experiment_id] = 0
        self.agent.audit.record(
            "create_experiment", 3,
            {"experiment_id": experiment_id,
             "hypothesis": hypothesis,
             "keywords": list(keywords), "author": author},
            "created")
        self._append_ledger(record, "created", {
            "hypothesis": hypothesis,
            "keywords": list(keywords), "author": author,
            "performance_claim": bool(performance_claim)})
        self.loop.advance(record)  # observe to hypothesise
        # Hypothesise to check prior research: the loop's
        # rejected-hypothesis gate fires here and raises
        # LoopRefusal with the citation on a match.
        self.loop.advance(record)
        return record, sandbox

    def sandbox_of(self, record):
        return self.sandboxes[record.loop_id]

    # Evidence ledger (Prompt 1, item E) -----------------------
    def ledger_path(self, experiment_id):
        return os.path.join(self.agent.local_dir,
                            "agent-evidence",
                            experiment_id + ".jsonl")

    def anchor_path(self, experiment_id):
        return os.path.join(self.agent.local_dir,
                            "agent-evidence",
                            experiment_id + ".anchor.json")

    def _sandbox_file_hashes(self, record):
        sandbox = self.sandbox_of(record)
        hashes = {}
        for root, _dirs, files in os.walk(sandbox):
            for name in sorted(files):
                path = os.path.join(root, name)
                rel = os.path.relpath(path, sandbox)
                try:
                    hashes[rel] = _sha256_file(path)
                except OSError:
                    pass
        return hashes

    def _append_ledger(self, record, kind, data):
        """Append one hash-chained record to the experiment's
        ledger, which lives OUTSIDE the writable sandbox.
        Returns the record hash. Ledger write failures are
        counted on the runner, never raised into the
        experiment (the audit log follows the same rule)."""
        path = self.ledger_path(record.loop_id)
        prev_hash = ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [ln for ln in f if ln.strip()]
            if lines:
                prev_hash = json.loads(lines[-1]).get(
                    "record_hash", "")
        except (OSError, ValueError):
            prev_hash = ""
        entry = {
            "experiment_id": record.loop_id,
            "kind": kind,
            "ts": time.time(),
            "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                    time.gmtime()),
            "source_commit": CURRENT_SOURCE_COMMIT,
            "compiler": "gcc",
            "compiler_version": _gcc_version(),
            "machine_profile": _cpu_model(),
            "prev_hash": prev_hash,
        }
        entry.update(data)
        canonical = json.dumps(entry, sort_keys=True,
                               separators=(",", ":"))
        entry["record_hash"] = hashlib.sha256(
            (prev_hash + canonical).encode("utf-8")).hexdigest()
        written = False
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT
                         | os.O_APPEND, 0o600)
            try:
                os.write(fd, (json.dumps(
                    entry, sort_keys=True) + "\n").encode(
                        "utf-8"))
            finally:
                os.close(fd)
            written = True
        except OSError:
            self._ledger_failures = getattr(
                self, "_ledger_failures", 0) + 1
        if written:
            self._update_anchor(record, entry["record_hash"])
        return entry["record_hash"]

    def _update_anchor(self, record, last_hash):
        """Atomically rewrite the experiment's external
        anchor: experiment_id, the ledger's record count and
        its last record hash, HMAC-signed with the verifier
        key. The anchor lives next to the ledger in
        .local/agent-evidence (outside any sandbox, which
        cannot reach .local at all), and is replaced via a
        temp file plus os.replace so a crash never leaves a
        half-written anchor. verify_ledger checks the ledger
        against this anchor, which is what makes tail
        truncation (deleting whole trailing records, which a
        bare hash chain cannot detect) detectable. Anchor
        failures are counted like ledger failures, never
        raised into the experiment; a stale anchor makes
        verify_ledger fail closed, which is the safe
        direction."""
        path = self.ledger_path(record.loop_id)
        try:
            with open(path, "r", encoding="utf-8") as f:
                count = sum(1 for ln in f if ln.strip())
        except OSError:
            return
        anchor = {"experiment_id": record.loop_id,
                  "record_count": count,
                  "last_record_hash": last_hash}
        apath = self.anchor_path(record.loop_id)
        try:
            key = _verifier.load_key(
                self.agent.verifier_key_path)
            signed = _verifier.sign_record(anchor, key)
            os.makedirs(os.path.dirname(apath), exist_ok=True)
            tmp = apath + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT
                         | os.O_TRUNC, 0o600)
            try:
                os.write(fd, (json.dumps(
                    signed, sort_keys=True) + "\n").encode(
                        "utf-8"))
            finally:
                os.close(fd)
            os.replace(tmp, apath)
        except OSError:
            self._ledger_failures = getattr(
                self, "_ledger_failures", 0) + 1

    def verify_ledger(self, experiment_id):
        """Recompute the hash chain of an experiment ledger
        and check it against the external anchor. Returns
        (ok, detail): ok is True only when every record's
        hash and prev_hash link recompute exactly AND the
        signed anchor (record count and last record hash,
        updated atomically on every append) matches the
        ledger. The chain alone detects edits, reordering
        and middle deletions; the anchor additionally
        detects tail truncation and extension, which a bare
        chain cannot. A missing or unsigned anchor fails
        closed."""
        path = self.ledger_path(experiment_id)
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [ln for ln in f if ln.strip()]
        except OSError:
            return False, f"ledger not found: {path}"
        if not lines:
            return False, "ledger is empty"
        prev_hash = ""
        for i, line in enumerate(lines):
            try:
                entry = json.loads(line)
            except ValueError:
                return False, f"record {i} is not valid JSON"
            recorded = entry.get("record_hash")
            if entry.get("prev_hash") != prev_hash:
                return False, (f"record {i}: prev_hash link "
                               "broken (history rewritten, "
                               "truncated or reordered)")
            body = {k: v for k, v in entry.items()
                    if k != "record_hash"}
            canonical = json.dumps(body, sort_keys=True,
                                   separators=(",", ":"))
            expect = hashlib.sha256(
                (prev_hash + canonical).encode(
                    "utf-8")).hexdigest()
            if recorded != expect:
                return False, (f"record {i}: record_hash "
                               "mismatch (content tampered)")
            prev_hash = recorded
        apath = self.anchor_path(experiment_id)
        try:
            with open(apath, "r", encoding="utf-8") as f:
                anchor = json.load(f)
        except OSError:
            return False, ("evidence anchor missing: tail "
                           "truncation cannot be ruled out")
        except ValueError:
            return False, "evidence anchor is not valid JSON"
        if not isinstance(anchor, dict) or \
                anchor.get("experiment_id") != experiment_id:
            return False, ("evidence anchor experiment_id "
                           "mismatch")
        key = _verifier.load_key(self.agent.verifier_key_path)
        if not _verifier.verify_signature(anchor, key):
            return False, ("evidence anchor signature "
                           "invalid or missing")
        if anchor.get("record_count") != len(lines):
            return False, (
                f"anchor expects "
                f"{anchor.get('record_count')} records but "
                f"the ledger holds {len(lines)}: tail "
                f"records added or removed")
        if anchor.get("last_record_hash") != prev_hash:
            return False, ("anchor last_record_hash does "
                           "not match the ledger head: tail "
                           "truncated or extended")
        return True, (f"{len(lines)} records, chain intact, "
                      "anchor verified")

    # Containment ----------------------------------------------
    def target_path(self, record, rel):
        """Resolve rel inside the experiment's sandbox and
        assert containment. Absolute paths and parent
        traversals that escape are refused with
        SandboxEscape."""
        sandbox = os.path.realpath(self.sandbox_of(record))
        if os.path.isabs(rel):
            target = os.path.realpath(rel)
        else:
            target = os.path.realpath(os.path.join(sandbox, rel))
        if target != sandbox and \
                not target.startswith(sandbox + os.sep):
            raise SandboxEscape(
                f"path {rel!r} resolves to {target!r}, outside "
                f"the experiment sandbox {sandbox!r}")
        return target

    def write_file(self, record, rel, text):
        """Write a text file inside the sandbox (the only
        write helper the runner offers)."""
        path = self.target_path(record, rel)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    # Execution --------------------------------------------------
    def run_command(self, record, argv, timeout_s=120,
                    memory_max=_sandbox.DEFAULT_MEMORY_MAX,
                    cpu_quota=_sandbox.DEFAULT_CPU_QUOTA,
                    tasks_max=_sandbox.DEFAULT_TASKS_MAX,
                    max_output_bytes=_sandbox.DEFAULT_MAX_OUTPUT_BYTES,
                    max_disk_bytes=_sandbox.DEFAULT_MAX_DISK_BYTES):
        """Execute an argv list inside the experimental
        sandbox (agent/intelligence/sandbox.py: systemd-run
        scope limits plus unshare namespaces, repository
        read-only, credentials hidden, no network, restricted
        environment, process-tree termination on timeout).

        Captures stdout and stderr to evidence files in the
        sandbox and records the exit code, wall time,
        termination reason and limits in the loop record's
        history, the audit log and the evidence ledger.
        Returns a result dict. A shell string in place of an
        argv list is refused. When isolation is unavailable,
        sandbox.SandboxUnavailable is raised and nothing runs.
        """
        if isinstance(argv, (str, bytes)) or \
                not isinstance(argv, (list, tuple)) or \
                not argv or \
                not all(isinstance(a, str) for a in argv):
            raise TypeError(
                "argv must be a non-empty list of strings; "
                "shell strings are refused")
        # Load-shedding wind-down (Stage 7): the mode is
        # re-checked at every command boundary, so an
        # experiment in flight when the mode sheds stops at
        # its next command instead of running on.
        modes = getattr(self.agent, "modes", None)
        if modes is not None:
            modes.require_allowed(
                "experiment",
                detail="run_command refused by the "
                       "load-shedding mode; in-flight "
                       "discretionary work winds down at this "
                       "command boundary")
        sandbox = self.sandbox_of(record)
        self.agent.checker.require("run_benchmark")
        idx = self._run_counts[record.loop_id] + 1
        self._run_counts[record.loop_id] = idx
        out_name = f"run{idx:03d}.stdout.txt"
        err_name = f"run{idx:03d}.stderr.txt"
        out_path = self.target_path(record, out_name)
        err_path = self.target_path(record, err_name)
        ran = _sandbox.run_sandboxed(
            list(argv), sandbox, timeout_s=timeout_s,
            memory_max=memory_max, cpu_quota=cpu_quota,
            tasks_max=tasks_max, max_output_bytes=max_output_bytes,
            max_disk_bytes=max_disk_bytes)
        exit_code = ran["exit_code"]
        timed_out = ran["timed_out"]
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(ran["stdout"] or "")
        with open(err_path, "w", encoding="utf-8") as f:
            f.write(ran["stderr"] or "")
        result = {"argv": list(argv), "exit_code": exit_code,
                  "wall_s": ran["wall_s"],
                  "timed_out": timed_out,
                  "termination_reason": ran["termination_reason"],
                  "sandbox_limits": ran["limits"],
                  "stdout_file": out_name,
                  "stderr_file": err_name}
        record.history.append(
            {"ts": time.time(), "event": "run_command",
             "state": record.state, **result})
        self.agent.audit.record(
            "run_benchmark", 2,
            {"experiment_id": record.loop_id, "argv": list(argv),
             "termination_reason": ran["termination_reason"],
             "limits": ran["limits"]},
            "timeout" if timed_out else f"exit_{exit_code}")
        self._append_ledger(record, "run", {
            "argv": list(argv), "exit_code": exit_code,
            "timed_out": timed_out,
            "termination_reason": ran["termination_reason"],
            "wall_s": ran["wall_s"],
            "execution_config": ran["limits"],
            "raw_output_hashes": {
                out_name: _sha256_file(out_path),
                err_name: _sha256_file(err_path)},
            "source_file_hashes":
                self._sandbox_file_hashes(record),
            "artifact_hashes":
                self._sandbox_file_hashes(record)})
        return result

    # Evidence ---------------------------------------------------
    def assemble_evidence(self, record):
        """Collect the experiment's evidence JSON files into
        the bundle loop.validate_integrate_evidence consumes,
        and store it on the record.

        Strict form (Prompt 1): each evidence file may carry
        full verification records under the keys correctness,
        differential and independent_verification, plus an
        exp017 block. Merging is conservative: when several
        files state a correctness or differential record, a
        failing record wins over a passing one (the gate then
        refuses); the independent verification record is taken
        from the last file (in sorted filename order) that
        states it. Nothing is converted into a pass here: the
        records reach the gate exactly as written, and the
        gate applies the strict schema and the verifier
        signature check. The assembly is also appended to the
        evidence ledger.
        """
        from .loop import validate_evidence_record
        sandbox = self.sandbox_of(record)
        files = []
        stated = {"correctness": [], "differential": []}
        verifier = None
        exp017 = None
        for name in sorted(os.listdir(sandbox)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(sandbox, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict) or not (
                    "correctness" in data
                    or "differential" in data
                    or "independent_verification" in data
                    or "exp017" in data):
                continue
            files.append(name)
            for key in ("correctness", "differential"):
                if isinstance(data.get(key), dict):
                    stated[key].append(data[key])
            if isinstance(data.get("independent_verification"),
                          dict):
                verifier = data["independent_verification"]
            if data.get("exp017"):
                exp017 = data["exp017"]
        bundle = {}
        for key in ("correctness", "differential"):
            records = stated[key]
            if records:
                failing = [r for r in records
                           if validate_evidence_record(r)]
                bundle[key] = failing[0] if failing \
                    else records[-1]
        if verifier is not None:
            bundle["independent_verification"] = verifier
        if exp017:
            def _rel(v):
                return v - 1.0 if isinstance(v, (int, float)) \
                    and not isinstance(v, bool) else v
            bundle["exp017_verdict"] = {
                "sessions": exp017.get("sessions"),
                "pooled_ratio": exp017.get("pooled_ratio"),
                "ci_low": _rel(exp017.get("ci_low")),
                "ci_high": _rel(exp017.get("ci_high"))}
        bundle["evidence_files"] = files
        record.evidence.update(bundle)
        record.history.append(
            {"ts": time.time(), "event": "evidence_assembled",
             "state": record.state, "files": files})
        self._append_ledger(record, "evidence", {
            "evidence_files": files,
            "verifier_record": verifier,
            "source_file_hashes":
                self._sandbox_file_hashes(record),
            "artifact_hashes":
                self._sandbox_file_hashes(record)})
        return bundle

    # Gate -------------------------------------------------------
    def walk_to_record(self, record):
        """Advance the record through the chain to the
        record_evidence state, the integrate gate's doorstep.
        The hypothesise gate was already passed at creation."""
        while record.state != RECORD:
            self.loop.advance(record)
        return record

    def attempt_integrate(self, record):
        """Ask the integrate gate. Returns a verdict dict:
        integrated True when the gate passed, otherwise False
        with the missing evidence items named. This runner
        never integrates anything itself; a pass here is a
        record decision only, and production integration
        remains a separate gated act outside this module."""
        if record.state != RECORD:
            raise LoopRefusal(
                f"loop {record.loop_id}: integrate can only be "
                f"attempted from record_evidence, not from "
                f"{record.state}")
        try:
            self.loop.advance(record)
        except LoopRefusal as exc:
            verdict = {"integrated": False,
                       "missing": list(exc.missing),
                       "state": record.state}
            self._append_ledger(record, "decision", {
                "decision": "integrate_refused",
                "integration_status": "not_integrated",
                "missing": list(exc.missing)})
            return verdict
        verdict = {"integrated": record.state == INTEGRATED,
                   "missing": [], "state": record.state}
        self._append_ledger(record, "decision", {
            "decision": "integrate_gate_passed",
            "integration_status": "gate_passed_record_only",
            "missing": []})
        return verdict
