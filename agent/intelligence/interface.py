"""Typed mining-engine interface (Master Build Mandate
sections 4.1D and 11).

Dataclass requests and responses over the EXISTING production
surfaces, reused and never rebuilt:

- status: mining/autopilot.py's own state files (the heartbeat
  it writes every 5 s and the EvidenceCounter census file).
  autopilot.py exposes no importable status function (its
  --status flag simply prints the heartbeat file), so this
  module parses the same two files the flag prints from.
- candidate verification: mining/candidate_verify.py.
- probability: mining/probability.py.
- backend probing and dispatch: gpu/engine.py ComputeEngine.
- checkpoint frontier: mining/work_checkpoint.py.

Every operation passes the permission check and writes an audit
record. Milestone 1 boundary: NO operation here starts, stops
or restarts the live miner, autopilot or node. start/stop exist
as L2 specifications executed only through an injectable
controller callable; the default controller raises
NotImplementedError, so the permission path is fully testable
while production stays untouched.

Telemetry honesty: when the heartbeat file is missing or stale,
inspect_status says so and reports running=False. It never
fabricates a figure the files do not contain.
"""

import calendar
import json
import os
import time
from dataclasses import dataclass, field

from .permissions import ACTION_REGISTRY, Level

_REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".."))
_LOCAL = os.path.join(_REPO_ROOT, ".local")

# Canonical dispatch order, as shipped in gpu/engine.py by
# EXP-039: CUDA, v512dual, v512, shani, avx2, C, hashlib.
DISPATCH_ORDER = ["CUDA", "v512dual", "v512", "shani", "avx2",
                  "C", "hashlib"]
_PIN_MAP = {"cuda": "cuda", "v512dual": "v512dual",
            "v512": "v512", "shani": "shani", "avx2": "avx2",
            "c": "c", "hashlib": None, "auto": "auto"}
_HEARTBEAT_STALE_S = 120.0


@dataclass
class StatusRequest:
    pass


@dataclass
class StatusResponse:
    running: bool
    note: str
    autopilot_pid: int = None
    miner_pid: int = None
    miner_state: str = None
    miner_uptime_s: float = None
    restarts: int = None
    shares_accepted_total: int = None
    evidence_age_s: float = None
    heartbeat_age_s: float = None
    evidence_accepted: int = None
    evidence_rejected: int = None
    evidence_share_results: int = None
    heartbeat: dict = None


@dataclass
class MachineResponse:
    model_name: str
    logical_cpus: int
    flags: list
    has_sha_ni: bool
    has_avx2: bool
    has_avx512f: bool
    cgroup_cpu_max: str = None
    effective_cpus_estimate: float = None
    effective_cpus_note: str = ("Not estimated by this call. "
                                "EXP-031 measured about 2 "
                                "effective CPUs on this guest; "
                                "see research/sha256d/exp031.")


@dataclass
class BackendsResponse:
    dispatch_order: list
    selected: str
    requested: str
    fallback_reason: str = None
    tier_reasons: dict = field(default_factory=dict)


@dataclass
class BackendSelection:
    requested: str
    selected: str
    eligible: bool
    note: str


@dataclass
class CandidateResponse:
    classification: str
    reason: str
    digests_agree: bool
    valid_header: bool
    meets_network_target: bool
    meets_share_target: bool
    value: int = None
    target: int = None
    nbits: int = None
    digest_hex: str = None


@dataclass
class ProbabilityResponse:
    difficulty: float
    hashrate_hs: float
    expected_hashes: float
    expected_seconds: float
    median_seconds: float
    p90_seconds: float
    prob_at_least_one: float = None
    seconds: float = None


@dataclass
class CheckpointResponse:
    path: str
    exists: bool
    note: str
    complete: bool = None
    frontier_extranonce: int = None
    frontier_nonce: int = None
    identity_prefix: str = None


def _parse_ts(ts):
    try:
        return float(calendar.timegm(
            time.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S")))
    except (ValueError, TypeError):
        return None


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _default_engine_factory(requested="auto"):
    from gpu.engine import ComputeEngine
    return ComputeEngine(requested=requested)


def _engine_selected_name(engine):
    backend = getattr(engine, "backend", None)
    if backend == "cpu" or backend is None:
        return "hashlib"
    if backend == "cuda":
        return "CUDA"
    if backend == "c":
        return "C"
    return backend


class MiningInterface:
    """The package's typed interface to the mining system.

    checker: a permissions.PermissionChecker.
    audit: an audit.AuditLog.
    local_dir: directory holding heartbeat.json and
    evidence-count.json (default the repo .local).
    engine_factory: callable(requested) -> ComputeEngine-like
    object; injectable for tests.
    controller: callable(action) for start/stop; the default
    raises NotImplementedError (Milestone 1 wires no live
    control).
    """

    def __init__(self, checker, audit, local_dir=None,
                 engine_factory=None, controller=None):
        self.checker = checker
        self.audit = audit
        self.local_dir = local_dir or _LOCAL
        self.engine_factory = engine_factory or \
            _default_engine_factory
        self.controller = controller
        self._engines = {}

    # Internal helpers -------------------------------------------
    def _gate(self, name, inputs_summary):
        spec = ACTION_REGISTRY.get(name)
        level = int(spec.level) if spec else None
        try:
            self.checker.require(name)
        except Exception as exc:
            self.audit.record(name, level, inputs_summary,
                              "permission_denied", detail=str(exc))
            raise
        return level

    def _done(self, name, level, inputs_summary, outcome="ok",
              detail=None):
        self.audit.record(name, level, inputs_summary, outcome,
                          detail=detail)

    def _engine(self, requested):
        if requested not in self._engines:
            self._engines[requested] = self.engine_factory(
                requested)
        return self._engines[requested]

    # L1 operations ----------------------------------------------
    def inspect_status(self, request=None):
        name = "inspect_status"
        if request is not None:
            # Prompt 1, item D: an operational operation can
            # never carry a shell or code payload.
            from .permissions import assert_no_shell_payload
            assert_no_shell_payload(name, request)
        level = self._gate(name, {})
        hb_path = os.path.join(self.local_dir, "heartbeat.json")
        ev_path = os.path.join(self.local_dir,
                               "evidence-count.json")
        hb = _read_json(hb_path)
        ev = _read_json(ev_path) or {}
        if hb is None:
            resp = StatusResponse(
                running=False,
                note=("no heartbeat file at " + hb_path +
                      "; autopilot not running or never "
                      "started"),
                evidence_accepted=ev.get("accepted"),
                evidence_rejected=ev.get("rejected"),
                evidence_share_results=ev.get("share_results"))
            self._done(name, level, {}, outcome="not_running")
            return resp
        hb_epoch = _parse_ts(hb.get("ts"))
        age = (time.time() - hb_epoch) if hb_epoch else None
        running = bool(
            hb.get("miner_state") == "running"
            and age is not None and age < _HEARTBEAT_STALE_S)
        note = "live heartbeat" if running else (
            "heartbeat present but stale or miner not in "
            "running state; reporting the file as found")
        resp = StatusResponse(
            running=running, note=note,
            autopilot_pid=hb.get("autopilot_pid"),
            miner_pid=hb.get("miner_pid"),
            miner_state=hb.get("miner_state"),
            miner_uptime_s=hb.get("miner_uptime_s"),
            restarts=hb.get("restarts"),
            shares_accepted_total=hb.get("shares_accepted_total"),
            evidence_age_s=hb.get("evidence_age_s"),
            heartbeat_age_s=age,
            evidence_accepted=ev.get("accepted"),
            evidence_rejected=ev.get("rejected"),
            evidence_share_results=ev.get("share_results"),
            heartbeat=hb)
        self._done(name, level, {},
                   outcome="ok" if running else "not_running")
        return resp

    def inspect_machine(self):
        name = "inspect_machine"
        level = self._gate(name, {})
        model = "unknown"
        flags = set()
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8",
                      errors="replace") as f:
                for line in f:
                    if line.startswith("model name") \
                            and model == "unknown":
                        model = line.split(":", 1)[1].strip()
                    elif line.startswith("flags"):
                        flags.update(
                            line.split(":", 1)[1].split())
        except OSError:
            pass
        cpu_max = None
        for cand in ("/sys/fs/cgroup/cpu.max",
                     "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    cpu_max = f.read().strip()
                break
            except OSError:
                continue
        interesting = sorted(
            f for f in flags
            if f.startswith(("sse", "avx", "sha", "vbmi",
                             "bmi", "gfni", "vpclmulqdq")))
        resp = MachineResponse(
            model_name=model,
            logical_cpus=os.cpu_count() or 0,
            flags=interesting,
            has_sha_ni=("sha_ni" in flags),
            has_avx2=("avx2" in flags),
            has_avx512f=("avx512f" in flags),
            cgroup_cpu_max=cpu_max)
        self._done(name, level, {})
        return resp

    def inspect_backends(self):
        name = "inspect_backends"
        level = self._gate(name, {})
        engine = self._engine("auto")
        reasons = {}
        for tier, attr in (("v512dual", "v512dual_reason"),
                           ("v512", "v512_reason"),
                           ("shani", "shani_reason"),
                           ("avx2", "avx2_reason"),
                           ("CUDA", "cuda_fallback_reason")):
            if hasattr(engine, attr):
                reasons[tier] = getattr(engine, attr)
        resp = BackendsResponse(
            dispatch_order=list(DISPATCH_ORDER),
            selected=_engine_selected_name(engine),
            requested="auto",
            fallback_reason=(getattr(engine, "fallback_reason",
                                     None)
                             if hasattr(engine, "fallback_reason")
                             else None),
            tier_reasons=reasons)
        self._done(name, level, {})
        return resp

    def verify_candidate_op(self, header, chain="main",
                            share_target=None):
        name = "verify_candidate"
        level = self._gate(name, {"chain": chain,
                                  "header_len": len(header)
                                  if header else 0})
        from mining.candidate_verify import (
            pow_limit_for_chain, verify_candidate)
        if isinstance(header, str):
            header = bytes.fromhex(header)
        result = verify_candidate(
            bytes(header), pow_limit_for_chain(chain),
            share_target=share_target)
        digest = result.get("digest")
        resp = CandidateResponse(
            classification=result["classification"],
            reason=result["reason"],
            digests_agree=result["digests_agree"],
            valid_header=result["valid_header"],
            meets_network_target=result["meets_network_target"],
            meets_share_target=result["meets_share_target"],
            value=result.get("value"),
            target=result.get("target"),
            nbits=result.get("nbits"),
            digest_hex=digest.hex() if isinstance(
                digest, (bytes, bytearray)) else None)
        self._done(name, level, {"chain": chain},
                   outcome=resp.classification)
        return resp

    def estimate_probability(self, hashrate_hs, difficulty,
                             seconds=None):
        name = "estimate_probability"
        level = self._gate(name, {"hashrate_hs": hashrate_hs,
                                  "difficulty": difficulty,
                                  "seconds": seconds})
        from mining import probability as prob
        resp = ProbabilityResponse(
            difficulty=float(difficulty),
            hashrate_hs=float(hashrate_hs),
            expected_hashes=prob.expected_hashes(difficulty),
            expected_seconds=prob.expected_seconds(
                hashrate_hs, difficulty),
            median_seconds=prob.median_seconds(
                hashrate_hs, difficulty),
            p90_seconds=prob.percentile_seconds(
                hashrate_hs, difficulty, 90),
            prob_at_least_one=(
                prob.prob_at_least_one(hashrate_hs, difficulty,
                                       seconds)
                if seconds else None),
            seconds=seconds)
        self._done(name, level, {"hashrate_hs": hashrate_hs,
                                 "difficulty": difficulty})
        return resp

    def checkpoint_status(self, path=None):
        name = "checkpoint_status"
        level = self._gate(name, {"path": path})
        if not path:
            resp = CheckpointResponse(
                path="", exists=False,
                note=("no checkpoint path given; pass the "
                      "GBT path checkpoint file (agent/"
                      "autonomous.py WORK_CHECKPOINT_PATH) to "
                      "read a frontier"))
            self._done(name, level, {"path": path},
                       outcome="no_path")
            return resp
        from mining.work_checkpoint import WorkCheckpoint
        cp = WorkCheckpoint(path)
        data = cp._load() if hasattr(cp, "_load") else None
        note = getattr(cp, "last_note", "")
        if data is None:
            resp = CheckpointResponse(path=path, exists=False,
                                      note=note)
            self._done(name, level, {"path": path},
                       outcome="no_checkpoint")
            return resp
        identity = data.get("identity")
        resp = CheckpointResponse(
            path=path, exists=True, note=note,
            complete=data.get("complete"),
            frontier_extranonce=data.get("frontier_extranonce"),
            frontier_nonce=data.get("frontier_nonce"),
            identity_prefix=(str(identity)[:16]
                             if identity else None))
        self._done(name, level, {"path": path})
        return resp

    # L2 operations ----------------------------------------------
    def select_backend(self, pin="auto"):
        name = "select_backend"
        level = self._gate(name, {"pin": pin})
        key = str(pin).lower()
        if key not in _PIN_MAP:
            raise ValueError(
                f"unknown backend pin {pin!r}; expected one of "
                f"{sorted(_PIN_MAP)}")
        requested = _PIN_MAP[key]
        if requested is None:
            resp = BackendSelection(
                requested=pin, selected="hashlib", eligible=True,
                note=("hashlib is the always-eligible pure "
                      "Python fallback; no engine constructed"))
            self._done(name, level, {"pin": pin})
            return resp
        engine = self._engine(requested)
        selected = _engine_selected_name(engine)
        want = {"cuda": "CUDA", "c": "C"}.get(requested,
                                             requested)
        if requested == "auto":
            want = selected
        resp = BackendSelection(
            requested=pin, selected=selected,
            eligible=(selected == want),
            note=("eligible backend for the pin, decided by "
                  "the ComputeEngine probe; mining was not "
                  "started"
                  if selected == want else
                  "pin not eligible on this machine; the "
                  "dispatch cascaded to " + selected))
        self._done(name, level, {"pin": pin},
                   outcome=resp.selected)
        return resp

    def _controlled(self, name, action):
        level = self._gate(name, {"action": action})
        if self.controller is None:
            self._done(name, level, {"action": action},
                       outcome="not_implemented",
                       detail=("Milestone 1 wires no live "
                               "control; inject a controller "
                               "to execute"))
            raise NotImplementedError(
                f"{name}: Milestone 1 does not wire live "
                "mining control; the operation is specified "
                "and permission-checked, and executes only "
                "through an injected controller")
        result = self.controller(action)
        self._done(name, level, {"action": action})
        return result

    def start_mining(self):
        return self._controlled("start_mining", "start")

    def stop_mining(self):
        return self._controlled("stop_mining", "stop")
