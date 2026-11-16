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
schema:

    {"correctness_pass": bool,
     "differential_pass": bool,
     "independent_verifier": str or null,
     "exp017": {"sessions": int, "pooled_ratio": float,
                "ci_low": float, "ci_high": float} or null}

where the exp017 confidence interval is for the pooled ratio
itself. assemble_evidence converts it to the loop gate's
form, whose interval is for the relative improvement (ratio
minus 1) and must lie entirely above 0.
"""

import json
import os
import subprocess
import time
import uuid

from .loop import (CHECK_PRIOR, HYPOTHESISE, INTEGRATED, RECORD,
                   LoopRefusal)

_REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".."))


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
        """
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
        self.loop.advance(record)  # observe to hypothesise
        # Hypothesise to check prior research: the loop's
        # rejected-hypothesis gate fires here and raises
        # LoopRefusal with the citation on a match.
        self.loop.advance(record)
        return record, sandbox

    def sandbox_of(self, record):
        return self.sandboxes[record.loop_id]

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
    def run_command(self, record, argv, timeout_s=120):
        """Execute an argv list with cwd inside the sandbox.

        Captures stdout and stderr to evidence files in the
        sandbox and records the exit code and wall time in
        the loop record's history. Returns a result dict.
        A shell string in place of an argv list is refused.
        """
        if isinstance(argv, (str, bytes)) or \
                not isinstance(argv, (list, tuple)) or \
                not argv or \
                not all(isinstance(a, str) for a in argv):
            raise TypeError(
                "argv must be a non-empty list of strings; "
                "shell strings are refused")
        sandbox = self.sandbox_of(record)
        self.agent.checker.require("run_benchmark")
        idx = self._run_counts[record.loop_id] + 1
        self._run_counts[record.loop_id] = idx
        out_name = f"run{idx:03d}.stdout.txt"
        err_name = f"run{idx:03d}.stderr.txt"
        out_path = self.target_path(record, out_name)
        err_path = self.target_path(record, err_name)
        t0 = time.perf_counter()
        timed_out = False
        exit_code = None
        try:
            proc = subprocess.run(
                list(argv), cwd=sandbox, capture_output=True,
                text=True, timeout=timeout_s)
            exit_code = proc.returncode
            stdout, stderr = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout.decode(
                "utf-8", "replace") if isinstance(
                    exc.stdout, (bytes, bytearray)) else \
                (exc.stdout or "")
            stderr = exc.stderr.decode(
                "utf-8", "replace") if isinstance(
                    exc.stderr, (bytes, bytearray)) else \
                (exc.stderr or "")
        wall = time.perf_counter() - t0
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(stdout or "")
        with open(err_path, "w", encoding="utf-8") as f:
            f.write(stderr or "")
        result = {"argv": list(argv), "exit_code": exit_code,
                  "wall_s": round(wall, 4),
                  "timed_out": timed_out,
                  "stdout_file": out_name,
                  "stderr_file": err_name}
        record.history.append(
            {"ts": time.time(), "event": "run_command",
             "state": record.state, **result})
        self.agent.audit.record(
            "run_benchmark", 2,
            {"experiment_id": record.loop_id, "argv": list(argv)},
            "timeout" if timed_out else f"exit_{exit_code}")
        return result

    # Evidence ---------------------------------------------------
    def assemble_evidence(self, record):
        """Collect the experiment's evidence JSON files into
        the bundle loop.validate_integrate_evidence consumes,
        and store it on the record.

        Merging is conservative: correctness and differential
        passes must hold in every evidence file that states
        them; the independent verifier and the EXP-017 block
        are taken from the last file (in sorted filename
        order) that states them non-null.
        """
        sandbox = self.sandbox_of(record)
        files = []
        correctness = None
        differential = None
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
            if not isinstance(data, dict) or \
                    "correctness_pass" not in data or \
                    "differential_pass" not in data:
                continue
            files.append(name)
            cp = data.get("correctness_pass")
            dp = data.get("differential_pass")
            correctness = bool(cp) if correctness is None \
                else (correctness and bool(cp))
            differential = bool(dp) if differential is None \
                else (differential and bool(dp))
            if data.get("independent_verifier"):
                verifier = data["independent_verifier"]
            if data.get("exp017"):
                exp017 = data["exp017"]
        bundle = {}
        if correctness is not None:
            bundle["correctness"] = correctness
        if differential is not None:
            bundle["differential"] = differential
        if verifier:
            bundle["independent_verification"] = {
                "author": verifier, "pass": True}
        if exp017:
            bundle["exp017_verdict"] = {
                "sessions": exp017.get("sessions"),
                "pooled_ratio": exp017.get("pooled_ratio"),
                "ci_low": (exp017.get("ci_low") - 1.0
                           if isinstance(exp017.get("ci_low"),
                                         (int, float)) else None),
                "ci_high": (exp017.get("ci_high") - 1.0
                            if isinstance(exp017.get("ci_high"),
                                          (int, float)) else None)}
        bundle["evidence_files"] = files
        record.evidence.update(bundle)
        record.history.append(
            {"ts": time.time(), "event": "evidence_assembled",
             "state": record.state, "files": files})
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
            return {"integrated": False,
                    "missing": list(exc.missing),
                    "state": record.state}
        return {"integrated": record.state == INTEGRATED,
                "missing": [], "state": record.state}
