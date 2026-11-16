"""Live mining awareness (Master Build Mandate section 4.1D
and Milestone 2).

An Awareness instance sits over the Milestone 1 Agent facade
and assembles one coherent, honest picture of the LIVE mining
system from real sources only:

- the autopilot heartbeat (.local/heartbeat.json, written
  every 5 s by mining/autopilot.py),
- the EvidenceCounter census (.local/evidence-count.json),
- the miner status file (.local/mainnet-status.txt, written
  by mining/mainnet_live.py),
- the tail of the evidence log (evidence/mainnet-live.jsonl),
  whose status events republish the live process's
  MiningStatistics snapshot (the EXP-037 categories),
- the pruned mainnet node, through a READ-ONLY
  getblockchaininfo RPC built from
  .local/mainnet/node-config.json,
- the endpoint config mode (mining/endpoint_config.py over
  .local/mining-endpoint.json).

Hard boundary: this module NEVER starts, stops, restarts or
signals the miner, the autopilot or the node. Every operation
is gated on the existing L1 read-only permission
(inspect_status in permissions.ACTION_REGISTRY) and recorded
in the facade's audit log under the operation name
awareness_observe.

Stage 7: awareness also carries the load-shedding mode
(modes.py). Snapshots report the current mode; observe
cycles feed the mode machine the load average and the
measured miner rate, and honour the mode: Brownout sheds
the rate-observation window, Critical reduces the cycle to
a single snapshot. Mode changes never touch mining.

Honesty rules, inherited from the lab's standing practice:

- A field a source does not carry is reported as absent
  (None plus a named absent_fields entry), never filled in.
- A rate is reported only with the method that produced it.
  Where only share counts are observable, the result says so
  and gives the share rate; a difficulty-weighted implied
  rate is computed only when a share difficulty is actually
  recorded by a source, and is labelled an estimate.
- An unreachable node is reported unreachable, with the
  error, never as a stale height.
"""

import json
import os
import re
import time

from .interface import _HEARTBEAT_STALE_S as HEARTBEAT_STALE_S
from .planning import TaskRecord

_REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".."))
_LOCAL = os.path.join(_REPO_ROOT, ".local")

AWARENESS_TASK_ID = "live-awareness-observe"
REJECTED_RATIO_THRESHOLD = 0.05
RATE_DROP_FRACTION = 0.25
DEFAULT_RPC_TIMEOUT_S = 30.0
_EVIDENCE_TAIL_BYTES = 512 * 1024


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _parse_ts(ts):
    import calendar
    try:
        return float(calendar.timegm(
            time.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S")))
    except (ValueError, TypeError):
        return None


def _parse_iso_ts(ts):
    """Epoch seconds for the evidence log's ISO timestamps
    (for example 2026-11-16T00:28:34.820129+00:00)."""
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(ts)).timestamp()
    except (ValueError, TypeError):
        return None


_STATUS_PATTERNS = {
    "job_id": re.compile(r"\bjob=(\S+)"),
    "prevhash_prefix": re.compile(r"\bprev=(\S+)"),
    "pool_diff": re.compile(r"\bpool_diff=([0-9.]+)"),
    "session_hashes": re.compile(r"\bhashes=([0-9,]+)"),
    "session_rate_hs": re.compile(r"\brate=([0-9,]+)\s*H/s"),
    "best_share_difficulty": re.compile(r"\bbest=([0-9.]+)"),
    "shares_submitted": re.compile(r"\bshares_submitted=(\d+)"),
    "session_elapsed_s": re.compile(r"^\s*t=\s*([0-9.]+)s",
                                    re.M),
    "worker": re.compile(r"^worker=(\S+)", re.M),
    "pool_endpoint": re.compile(r"^pool=(\S+)", re.M),
    "backend": re.compile(r"^compute backend:\s*(\S+)", re.M),
}
_STATUS_INT_FIELDS = ("session_hashes", "session_rate_hs",
                      "shares_submitted")
_STATUS_FLOAT_FIELDS = ("pool_diff", "best_share_difficulty",
                        "session_elapsed_s")


def parse_status_text(text):
    """Parse the miner status file's text form. Returns a
    dict of the fields found plus absent_fields naming every
    known field the text does not carry."""
    out = {}
    absent = []
    for name, pattern in _STATUS_PATTERNS.items():
        m = pattern.search(text)
        if m is None:
            absent.append(name)
            continue
        raw = m.group(1)
        if name in _STATUS_INT_FIELDS:
            out[name] = int(raw.replace(",", ""))
        elif name in _STATUS_FLOAT_FIELDS:
            out[name] = float(raw)
        else:
            out[name] = raw
    out["absent_fields"] = absent
    return out


def _default_rpc_factory(node_config_path, timeout_s):
    """A read-only mainnet RPC client with a bounded timeout
    and a single attempt. Credentials are read in-process by
    mining/endpoint_config.load_mainnet_rpc and never leave
    it."""
    from mining.endpoint_config import load_mainnet_rpc
    rpc = load_mainnet_rpc(node_config_path)
    return rpc.with_timeout(timeout_s, retries=1)


class Awareness:
    """Live awareness over one Agent facade.

    agent: an agent.intelligence.Agent (checker, audit and
    task registry are taken from it).
    All source paths are injectable for tests. Defaults are
    the repo's real .local files and evidence log.
    rpc_factory: callable(node_config_path, timeout_s) ->
    object with get_blockchain_info(); injectable for tests.
    """

    def __init__(self, agent, heartbeat_path=None,
                 census_path=None, status_path=None,
                 endpoint_path=None, node_config_path=None,
                 evidence_log_path=None, rpc_factory=None,
                 rpc_timeout_s=DEFAULT_RPC_TIMEOUT_S,
                 mode_manager=None):
        self.agent = agent
        self.checker = agent.checker
        self.audit = agent.audit
        # Load-shedding modes (Stage 7, modes.py). Default:
        # the facade's ModeManager when the agent carries
        # one. snapshot() reports the mode; observe_cycle()
        # feeds it real signals (load average, measured
        # miner rate) and honours it: Brownout sheds the
        # rate-observation window, Critical reduces the
        # cycle to a single snapshot.
        self.modes = mode_manager or getattr(
            agent, "modes", None)
        local = agent.local_dir
        self.heartbeat_path = heartbeat_path or os.path.join(
            local, "heartbeat.json")
        self.census_path = census_path or os.path.join(
            local, "evidence-count.json")
        self.status_path = status_path or os.path.join(
            local, "mainnet-status.txt")
        self.endpoint_path = endpoint_path or os.path.join(
            _LOCAL, "mining-endpoint.json")
        self.node_config_path = node_config_path or os.path.join(
            _LOCAL, "mainnet", "node-config.json")
        self.evidence_log_path = evidence_log_path or os.path.join(
            _REPO_ROOT, "evidence", "mainnet-live.jsonl")
        self.rpc_factory = rpc_factory or _default_rpc_factory
        self.rpc_timeout_s = float(rpc_timeout_s)
        self._last_snapshot = None
        self._last_observation = None

    # Permission and audit -------------------------------------
    def _gate(self):
        self.checker.require("inspect_status")

    def _audit(self, outcome, detail=None):
        self.audit.record("awareness_observe", 1, {},
                          outcome, detail=detail)

    # Source readers (each returns (value, read_ms)) -----------
    def _read_heartbeat(self):
        t0 = time.perf_counter()
        data = _read_json(self.heartbeat_path)
        return data, (time.perf_counter() - t0) * 1000.0

    def _read_census(self):
        t0 = time.perf_counter()
        data = _read_json(self.census_path)
        return data, (time.perf_counter() - t0) * 1000.0

    def _read_status_file(self):
        t0 = time.perf_counter()
        try:
            with open(self.status_path, "r", encoding="utf-8",
                      errors="replace") as f:
                text = f.read()
        except OSError:
            text = None
        return text, (time.perf_counter() - t0) * 1000.0

    def _read_evidence_tail(self):
        """The last status event, job event and share result
        in the evidence log tail, or Nones when absent."""
        t0 = time.perf_counter()
        out = {"last_status_event": None, "last_job_event": None,
               "last_share_result": None}
        try:
            size = os.path.getsize(self.evidence_log_path)
            with open(self.evidence_log_path, "rb") as f:
                f.seek(max(0, size - _EVIDENCE_TAIL_BYTES))
                raw = f.read().decode("utf-8", errors="replace")
        except OSError:
            return out, (time.perf_counter() - t0) * 1000.0
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("event")
            if kind == "status":
                out["last_status_event"] = event
            elif kind == "job":
                out["last_job_event"] = event
            elif kind == "share_result":
                out["last_share_result"] = event
        return out, (time.perf_counter() - t0) * 1000.0

    def _read_node(self):
        t0 = time.perf_counter()
        node = {"reachable": False, "blocks": None,
                "headers": None, "initialblockdownload": None,
                "blocks_behind_headers": None, "error": None}
        try:
            rpc = self.rpc_factory(self.node_config_path,
                                   self.rpc_timeout_s)
            info = rpc.get_blockchain_info()
            node["reachable"] = True
            node["blocks"] = info.get("blocks")
            node["headers"] = info.get("headers")
            node["initialblockdownload"] = info.get(
                "initialblockdownload")
            if isinstance(node["blocks"], int) and isinstance(
                    node["headers"], int):
                node["blocks_behind_headers"] = (
                    node["headers"] - node["blocks"])
        except Exception as exc:  # reported, never raised
            node["error"] = (
                f"{type(exc).__name__}: {exc}")[:240]
        return node, (time.perf_counter() - t0) * 1000.0

    def _read_endpoint(self):
        t0 = time.perf_counter()
        from mining.endpoint_config import load_config
        cfg = load_config(self.endpoint_path)
        out = {"mode": cfg.get("mode"),
               "pool_host": (cfg.get("pool") or {}).get("host"),
               "pool_port": (cfg.get("pool") or {}).get("port"),
               "solo_host": (cfg.get("solo") or {}).get("host"),
               "solo_port": (cfg.get("solo") or {}).get("port")}
        return out, (time.perf_counter() - t0) * 1000.0

    # 1. Snapshot ----------------------------------------------
    def snapshot(self):
        """One coherent live picture from the real sources.
        Fields a source does not carry are None and named in
        that section's absent_fields where applicable."""
        self._gate()
        read_ms = {}
        hb, read_ms["heartbeat"] = self._read_heartbeat()
        census, read_ms["census"] = self._read_census()
        status_text, read_ms["status_file"] = \
            self._read_status_file()
        tail, read_ms["evidence_tail"] = self._read_evidence_tail()
        node, read_ms["node_rpc"] = self._read_node()
        endpoint, read_ms["endpoint"] = self._read_endpoint()

        now = time.time()
        if hb is None:
            autopilot = {
                "running": False,
                "note": ("no heartbeat file at "
                         + self.heartbeat_path
                         + "; autopilot not running or never "
                           "started"),
                "autopilot_pid": None, "miner_pid": None,
                "miner_state": None, "miner_uptime_s": None,
                "restarts": None, "heartbeat_age_s": None,
                "evidence_age_s": None,
                "shares_accepted_total": None}
        else:
            hb_epoch = _parse_ts(hb.get("ts"))
            age = (now - hb_epoch) if hb_epoch else None
            running = bool(
                hb.get("miner_state") == "running"
                and age is not None and age < HEARTBEAT_STALE_S)
            autopilot = {
                "running": running,
                "note": ("live heartbeat" if running else
                         "heartbeat present but stale or miner "
                         "not in running state; reporting the "
                         "file as found"),
                "autopilot_pid": hb.get("autopilot_pid"),
                "miner_pid": hb.get("miner_pid"),
                "miner_state": hb.get("miner_state"),
                "miner_uptime_s": hb.get("miner_uptime_s"),
                "restarts": hb.get("restarts"),
                "heartbeat_age_s": age,
                "evidence_age_s": hb.get("evidence_age_s"),
                "shares_accepted_total":
                    hb.get("shares_accepted_total")}
        if census is None:
            census_out = {"present": False, "accepted": None,
                          "rejected": None, "share_results": None,
                          "consistent": None, "last_epoch": None}
        else:
            acc = census.get("accepted")
            rej = census.get("rejected")
            tot = census.get("share_results")
            census_out = {
                "present": True, "accepted": acc, "rejected": rej,
                "share_results": tot,
                "consistent": (
                    acc is not None and rej is not None
                    and tot is not None
                    and acc + rej == tot),
                "last_epoch": census.get("last_epoch")}
        if status_text is None:
            status_out = {"present": False,
                          "absent_fields": sorted(
                              _STATUS_PATTERNS)}
        else:
            status_out = parse_status_text(status_text)
            status_out["present"] = True
        last_status = tail["last_status_event"]
        tail_out = {
            "last_status_event": (
                {"ts": last_status.get("ts"),
                 "hashes": last_status.get("hashes"),
                 "session_rate_hs": last_status.get("rate"),
                 "best_share_difficulty": last_status.get("best"),
                 "submitted": last_status.get("submitted"),
                 "statistics": last_status.get("statistics"),
                 "statistics_errors":
                     last_status.get("statistics_errors")}
                if last_status else None),
            "last_job_event": tail["last_job_event"],
            "last_share_result": tail["last_share_result"]}
        snap = {
            "ts": now,
            "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                    time.gmtime(now)),
            "mode": (self.modes.current()
                     if self.modes is not None else None),
            "autopilot": autopilot,
            "evidence_census": census_out,
            "miner_status_file": status_out,
            "evidence_tail": tail_out,
            "node": node,
            "endpoint": endpoint,
            "read_times_ms": {k: round(v, 3)
                              for k, v in read_ms.items()},
        }
        self._last_snapshot = snap
        self._audit("snapshot", detail={
            "running": autopilot["running"],
            "accepted": census_out["accepted"],
            "node_reachable": node["reachable"]})
        return snap

    # 2. Rate observation ---------------------------------------
    def _sample(self):
        census, _ms = self._read_census()
        tail, _ms2 = self._read_evidence_tail()
        status_text, _ms3 = self._read_status_file()
        pool_diff = None
        if status_text is not None:
            pool_diff = parse_status_text(
                status_text).get("pool_diff")
        last_status = tail["last_status_event"] or {}
        stats = last_status.get("statistics") or {}
        return {
            "wall_ts": time.time(),
            "accepted": (census or {}).get("accepted"),
            "rejected": (census or {}).get("rejected"),
            "share_results": (census or {}).get("share_results"),
            "backend_hashes": stats.get("backend_hashes"),
            "status_event_ts": _parse_iso_ts(
                last_status.get("ts")),
            "status_event_session_rate_hs":
                last_status.get("rate"),
            "pool_diff": pool_diff,
        }

    def rate_observation(self, window_s, sleep=None):
        """Measure the live verified rate across a real
        window by sampling the census and the evidence tail
        twice. The primary figure is the delta of the live
        process's backend_hashes counter (MiningStatistics,
        republished in evidence status events) over the
        interval between the two distinct status events
        bracketing the window. The share rate comes from the
        EvidenceCounter census delta over the wall window.
        The difficulty-weighted figure is an ESTIMATE, given
        only when a pool share difficulty is recorded."""
        self._gate()
        sleep = sleep or time.sleep
        first = self._sample()
        sleep(float(window_s))
        second = self._sample()
        wall = second["wall_ts"] - first["wall_ts"]
        out = {
            "window_requested_s": float(window_s),
            "window_wall_s": wall,
            "shares_delta": None, "share_rate_per_s": None,
            "backend_hashes_delta": None, "backend_rate_hs": None,
            "backend_interval_s": None,
            "implied_difficulty_weighted_rate_hs": None,
            "pool_share_difficulty": second["pool_diff"],
            "method": "",
            "notes": [],
        }
        if first["accepted"] is not None and \
                second["accepted"] is not None and wall > 0:
            out["shares_delta"] = (second["accepted"]
                                   - first["accepted"])
            out["share_rate_per_s"] = out["shares_delta"] / wall
        else:
            out["notes"].append(
                "share counts not observable in one or both "
                "samples; no share rate computed")
        h1 = first["backend_hashes"]
        h2 = second["backend_hashes"]
        t1 = first["status_event_ts"]
        t2 = second["status_event_ts"]
        if h1 is not None and h2 is not None and \
                t1 is not None and t2 is not None and t2 > t1:
            if h2 >= h1:
                out["backend_hashes_delta"] = h2 - h1
                out["backend_interval_s"] = t2 - t1
                out["backend_rate_hs"] = (
                    (h2 - h1) / (t2 - t1))
            else:
                out["notes"].append(
                    "backend_hashes counter decreased between "
                    "samples (miner restart inside the window); "
                    "no backend rate computed")
        else:
            out["notes"].append(
                "no two distinct evidence status events "
                "bracket the window; backend hash accounting "
                "not observable for this window")
        if out["shares_delta"] is not None and \
                out["shares_delta"] > 0 and wall > 0 and \
                second["pool_diff"]:
            out["implied_difficulty_weighted_rate_hs"] = (
                out["shares_delta"] * float(second["pool_diff"])
                * float(2 ** 32) / wall)
        method = (
            "share rate: EvidenceCounter census accepted-share "
            "delta over the wall window. backend rate: delta "
            "of the live process MiningStatistics "
            "backend_hashes counter, republished in evidence "
            "log status events, over the interval between the "
            "two status events bracketing the window.")
        if out["implied_difficulty_weighted_rate_hs"] is not None:
            method += (
                " implied rate: ESTIMATE, accepted-share "
                "delta x pool-assigned share difficulty "
                "(pool_diff in the miner status file) x 2^32 / "
                "wall window; at this window length the share "
                "count is small and Poisson noise dominates "
                "the estimate.")
        else:
            method += (
                " no difficulty-weighted implied rate: no "
                "pool share difficulty recorded by the sampled "
                "sources, or no accepted shares in the window.")
        out["method"] = method
        self._last_observation = out
        self._audit("rate_observation", detail={
            "window_wall_s": wall,
            "backend_rate_hs": out["backend_rate_hs"],
            "shares_delta": out["shares_delta"]})
        return out

    # 3. Degradation check --------------------------------------
    def degradation_check(self, baseline, current=None):
        """Compare the current snapshot and observation
        against a baseline of the same shape (either key may
        be missing; checks whose inputs are absent are listed
        in not_evaluated, never silently passed). Every flag
        names its evidence."""
        self._gate()
        baseline = baseline or {}
        if current is None:
            current = {"snapshot": self._last_snapshot,
                       "observation": self._last_observation}
        snap = current.get("snapshot") or {}
        obs = current.get("observation") or {}
        base_snap = baseline.get("snapshot") or {}
        base_obs = baseline.get("observation") or {}
        flags = []
        not_evaluated = []

        ap = snap.get("autopilot") or {}
        age = ap.get("heartbeat_age_s")
        if age is None and snap:
            not_evaluated.append(
                "heartbeat staleness: current snapshot has no "
                "heartbeat age")
        elif age is not None and (
                age > HEARTBEAT_STALE_S
                or ap.get("running") is False):
            flags.append({
                "flag": "heartbeat_stale",
                "evidence": (
                    f"heartbeat_age_s={age}, running="
                    f"{ap.get('running')}, threshold "
                    f"{HEARTBEAT_STALE_S} s"),
                "detail": "autopilot heartbeat is stale or "
                          "the miner is not in running state"})

        restarts = ap.get("restarts")
        if restarts is None:
            not_evaluated.append(
                "restarts: current snapshot carries no restart "
                "count")
        elif restarts > 0:
            base_restarts = (base_snap.get("autopilot")
                             or {}).get("restarts")
            flags.append({
                "flag": "restarts_present",
                "evidence": (
                    f"restarts={restarts}"
                    + (f", baseline restarts={base_restarts}"
                       if base_restarts is not None else "")),
                "detail": "the autopilot has restarted the "
                          "miner at least once in this session"})

        census = snap.get("evidence_census") or {}
        acc, rej, tot = (census.get("accepted"),
                         census.get("rejected"),
                         census.get("share_results"))
        if acc is None or rej is None or not tot:
            not_evaluated.append(
                "rejected share ratio: census counts absent")
        else:
            ratio = rej / tot
            if ratio > REJECTED_RATIO_THRESHOLD:
                flags.append({
                    "flag": "rejected_ratio_high",
                    "evidence": (
                        f"rejected={rej} of share_results="
                        f"{tot}, ratio {ratio:.4f}, threshold "
                        f"{REJECTED_RATIO_THRESHOLD}"),
                    "detail": "lifetime census rejected share "
                              "ratio above the stated threshold"})

        cur_rate = obs.get("backend_rate_hs")
        base_rate = base_obs.get("backend_rate_hs")
        if cur_rate is None or base_rate is None:
            not_evaluated.append(
                "rate drop: a backend rate is missing on the "
                "current or baseline side")
        elif base_rate > 0 and cur_rate < base_rate * (
                1.0 - RATE_DROP_FRACTION):
            flags.append({
                "flag": "rate_drop",
                "evidence": (
                    f"current backend_rate_hs={cur_rate:.1f}, "
                    f"baseline backend_rate_hs={base_rate:.1f}, "
                    f"drop fraction threshold "
                    f"{RATE_DROP_FRACTION}"),
                "detail": "measured backend rate fell beyond "
                          "the stated fraction against the "
                          "baseline observation"})

        node = snap.get("node") or {}
        base_node = base_snap.get("node") or {}
        if node.get("reachable") is False:
            flags.append({
                "flag": "node_unreachable",
                "evidence": f"node error: {node.get('error')}",
                "detail": "the read-only getblockchaininfo "
                          "RPC did not answer inside the "
                          "bounded timeout"})
        elif node.get("blocks_behind_headers") is None:
            not_evaluated.append(
                "node sync gap: current snapshot has no node "
                "gap figure")
        else:
            gap = node["blocks_behind_headers"]
            base_gap = base_node.get("blocks_behind_headers")
            if base_gap is not None and gap > base_gap:
                flags.append({
                    "flag": "node_falling_behind",
                    "evidence": (
                        f"blocks_behind_headers={gap}, "
                        f"baseline {base_gap}"),
                    "detail": "the node's gap behind its own "
                              "headers grew against the "
                              "baseline"})
            elif base_gap is None and gap > 0:
                flags.append({
                    "flag": "node_falling_behind",
                    "evidence": (
                        f"blocks_behind_headers={gap}, "
                        f"initialblockdownload="
                        f"{node.get('initialblockdownload')}, "
                        "no baseline gap supplied"),
                    "detail": "the node is behind its headers "
                              "(initial block download is the "
                              "known standing state)"})
        result = {"flags": flags, "not_evaluated": not_evaluated,
                  "thresholds": {
                      "heartbeat_stale_s": HEARTBEAT_STALE_S,
                      "rejected_ratio": REJECTED_RATIO_THRESHOLD,
                      "rate_drop_fraction": RATE_DROP_FRACTION}}
        self._audit("degradation_check", detail={
            "flags": [f["flag"] for f in flags]})
        return result

    # 4. Coverage report -----------------------------------------
    def coverage_report(self):
        """What unique coverage can honestly be stated for
        the live pool path, and what cannot."""
        self._gate()
        census, _ms = self._read_census()
        tail, _ms2 = self._read_evidence_tail()
        last_status = tail["last_status_event"] or {}
        stats = last_status.get("statistics") or {}
        can_state = []
        if stats:
            can_state.append(
                "The live process's own MiningStatistics "
                "snapshot (EXP-037 separated categories), as "
                "republished in the evidence log status "
                f"event at {last_status.get('ts')}: "
                f"backend_hashes={stats.get('backend_hashes')}, "
                f"unique_nonces={stats.get('unique_nonces')}, "
                f"unique_coverage={stats.get('unique_coverage')}, "
                f"actual_computations="
                f"{stats.get('actual_computations')}, "
                f"repeated_work={stats.get('repeated_work')}. "
                "These are the miner process's counters for "
                "its current session, not a lifetime census.")
        if census:
            can_state.append(
                "The lifetime pool-verdict census "
                "(EvidenceCounter over the whole evidence "
                f"log): accepted={census.get('accepted')}, "
                f"rejected={census.get('rejected')}, "
                f"share_results={census.get('share_results')}. "
                "Accepted shares are pool verdicts, not blocks.")
        cannot_state = [
            ("Exact searched-position coverage for the pool "
             "path cannot be stated. mining/work_checkpoint.py "
             "serves the GBT path only (its scope boundary: "
             "the Stratum pool path is untouched by it, its "
             "work separation is the pool-assigned job and "
             "extranonce split, ephemeral per session), so no "
             "frontier checkpoint exists for the live pool "
             "miner and no (extranonce, nonce) frontier can "
             "be quoted for it."),
            ("Remaining work cannot be stated for the pool "
             "path: the pool assigns jobs and there is no "
             "finite declared search space per job from this "
             "side of the protocol."),
            ("MiningStatistics snapshots live only inside "
             "the miner process; this layer sees them only as "
             "republished in evidence status events, so a "
             "statistics figure is never fresher than the "
             "last status event."),
        ]
        out = {"can_state": can_state,
               "cannot_state": cannot_state,
               "latest_statistics": stats or None,
               "statistics_event_ts": last_status.get("ts"),
               "census": census}
        self._audit("coverage_report", detail={
            "statistics_event_ts": last_status.get("ts")})
        return out

    # 5. Observe cycle -------------------------------------------
    def _update_mode(self, observation, snap):
        """Feed the load-shedding mode machine the real
        signals this cycle measured: the 1-minute load
        average against EXP-031's effective-CPU estimate,
        and the miner backend rate against the manager's
        standing baseline. Returns the current mode dict,
        or None when no mode manager is wired."""
        if self.modes is None:
            return None
        try:
            load1 = os.getloadavg()[0]
        except (OSError, AttributeError):
            load1 = None
        rate = None
        if observation is not None:
            rate = observation.get("backend_rate_hs")
        if rate is None:
            tail = (snap or {}).get("evidence_tail") or {}
            last_status = tail.get("last_status_event") or {}
            rate = last_status.get("session_rate_hs")
        from .modes import EFFECTIVE_CPUS_EXP031
        return self.modes.update({
            "load1": load1,
            "effective_cpus": EFFECTIVE_CPUS_EXP031,
            "miner_rate_hs": rate,
            "heartbeat_age_s": ((snap or {}).get("autopilot")
                                or {}).get("heartbeat_age_s"),
        })

    def _ensure_awareness_task(self):
        tasks = self.agent.tasks
        rec = tasks.get(AWARENESS_TASK_ID)
        if rec is None:
            rec = tasks.add(TaskRecord(
                task_id=AWARENESS_TASK_ID,
                objective=("Standing live awareness observation "
                           "of the pool mining path (Master "
                           "Build Mandate Milestone 2)"),
                level="task",
                required_evidence=[],
                expected_output=("Operational report per "
                                 "observe cycle: snapshot, "
                                 "rate observation, degradation "
                                 "flags, coverage statement"),
                risk="low",
                resource_budget=("read-only file and RPC "
                                 "reads; no miner contact"),
                success_criteria=("each cycle records its "
                                  "evidence in the audit log "
                                  "and here"),
                failure_criteria=("a cycle that fabricates "
                                  "telemetry or touches the "
                                  "miner")))
        if rec.state in ("planned", "blocked", "failed"):
            try:
                tasks.transition(AWARENESS_TASK_ID, "active")
                rec = tasks.get(AWARENESS_TASK_ID)
            except Exception:
                pass
        return rec

    def observe_cycle(self, window_s=0.0):
        """One full awareness pass. Builds its baseline from
        a snapshot taken at cycle start, measures the rate
        across the window, checks degradation against that
        baseline, reports coverage, writes the cycle into
        the audit log and the standing awareness task, and
        returns the structured operational report."""
        self._gate()
        t_start = time.perf_counter()
        phases = {}
        mode_before = (self.modes.current()
                       if self.modes is not None else None)
        if mode_before is not None and \
                mode_before["mode"] == "critical":
            # CRITICAL: awareness is minimal. One snapshot,
            # no rate window, no coverage pass. The mode is
            # still fed the load signal so recovery can be
            # observed and the exit hysteresis can run.
            snap = self.snapshot()
            mode_after = self._update_mode(
                None, snap)
            report = {
                "kind": "awareness_operational_report",
                "ts_utc": snap["ts_utc"],
                "mode": mode_after,
                "mode_before": mode_before,
                "mode_note": (
                    "critical mode: minimal awareness cycle "
                    "(snapshot only); rate observation and "
                    "coverage shed to protect mining"),
                "snapshot": snap,
                "rate_observation": None,
                "degradation": None,
                "coverage": None,
                "overhead": {
                    "phase_times_s": {},
                    "total_wall_s": round(
                        time.perf_counter() - t_start, 4),
                    "active_overhead_s_excluding_window": 0.0,
                    "observation_window_s": 0.0},
                "task": {"task_id": AWARENESS_TASK_ID,
                         "state": "critical_minimal"},
            }
            self._audit("observe_cycle", detail={
                "mode": "critical",
                "total_wall_s":
                    report["overhead"]["total_wall_s"]})
            return report
        t = time.perf_counter()
        baseline_snap = self.snapshot()
        phases["baseline_snapshot_s"] = time.perf_counter() - t
        base_status = (baseline_snap.get("evidence_tail")
                       or {}).get("last_status_event") or {}
        baseline = {
            "snapshot": baseline_snap,
            "observation": {
                "backend_rate_hs":
                    base_status.get("session_rate_hs"),
                "backend_rate_source": (
                    "miner session-average rate field of the "
                    "baseline evidence status event; the "
                    "degradation rate-drop check compares the "
                    "fresh window measurement against it")}}
        t = time.perf_counter()
        if mode_before is not None and \
                mode_before["mode"] == "brownout":
            # BROWNOUT: the rate-observation window is
            # discretionary measurement and is shed; the
            # rest of the cycle (snapshots, degradation,
            # coverage) continues at reduced cadence.
            observation = {
                "window_requested_s": 0.0,
                "window_wall_s": 0.0,
                "shares_delta": None,
                "share_rate_per_s": None,
                "backend_hashes_delta": None,
                "backend_rate_hs": None,
                "backend_interval_s": None,
                "implied_difficulty_weighted_rate_hs": None,
                "pool_share_difficulty": None,
                "method": ("shed in brownout mode: no rate "
                           "window measured this cycle"),
                "notes": ["rate observation shed by the "
                          "brownout load-shedding mode"]}
        else:
            observation = self.rate_observation(window_s)
        phases["rate_observation_s"] = time.perf_counter() - t
        t = time.perf_counter()
        final_snap = self.snapshot()
        phases["final_snapshot_s"] = time.perf_counter() - t
        current = {"snapshot": final_snap,
                   "observation": observation}
        t = time.perf_counter()
        degradation = self.degradation_check(baseline,
                                             current=current)
        phases["degradation_check_s"] = time.perf_counter() - t
        t = time.perf_counter()
        coverage = self.coverage_report()
        phases["coverage_report_s"] = time.perf_counter() - t
        total_wall = time.perf_counter() - t_start
        active = total_wall - float(window_s)
        rec = self._ensure_awareness_task()
        evidence_item = (
            f"observe_cycle {final_snap['ts_utc']} accepted="
            f"{final_snap['evidence_census'].get('accepted')} "
            f"rejected="
            f"{final_snap['evidence_census'].get('rejected')} "
            f"backend_rate_hs={observation.get('backend_rate_hs')} "
            f"flags={[f['flag'] for f in degradation['flags']]}")
        self.agent.tasks.add_evidence(AWARENESS_TASK_ID,
                                      [evidence_item])
        mode_after = self._update_mode(observation, final_snap)
        report = {
            "kind": "awareness_operational_report",
            "ts_utc": final_snap["ts_utc"],
            "mode": mode_after,
            "mode_before": mode_before,
            "baseline_note": (
                "the degradation baseline was constructed "
                "from the census and evidence status event at "
                "cycle start, inside this same cycle"),
            "snapshot": final_snap,
            "rate_observation": observation,
            "degradation": degradation,
            "coverage": coverage,
            "overhead": {
                "phase_times_s": {k: round(v, 4)
                                  for k, v in phases.items()},
                "total_wall_s": round(total_wall, 4),
                "active_overhead_s_excluding_window":
                    round(max(active, 0.0), 4),
                "observation_window_s": float(window_s)},
            "task": {"task_id": AWARENESS_TASK_ID,
                     "state": self.agent.tasks.get(
                         AWARENESS_TASK_ID).state,
                     "evidence_added": evidence_item},
        }
        self._audit("observe_cycle", detail={
            "total_wall_s": report["overhead"]["total_wall_s"],
            "flags": [f["flag"] for f in degradation["flags"]]})
        return report
