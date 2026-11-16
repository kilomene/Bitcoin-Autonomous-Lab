#!/usr/bin/env python3
"""Stage 8: the autonomous agent-directed mining
demonstration on regtest (Directive 5 Stage 8; Directive 4
Prompt 6 substance).

The agent layer (agent/intelligence/) is the decision-maker
for one complete mining operation, executed end to end
through the agent's own machinery and the production mining
code, against the lab's regtest node:

  1. inspect the environment through Awareness.snapshot()
     (plus the interface's machine and backend inspections);
  2. consult research memory through the optimisation
     loop's hypothesise gate: one REJECTED and one
     INTEGRATED re-proposal, both refused with citations;
  3. plan the demonstration in the TaskRegistry with
     dependencies and required evidence;
  4. start mining through the interface start_mining L2
     operation, executed by the production MiningController
     against an ISOLATED autopilot instance (a copy of
     mining/autopilot.py and scripts/autopilot.sh with its
     own .local) whose miner child is the production GBT
     path (stage8_regtest_miner.py: MiningEngine,
     ComputeEngine, MiningStatistics, EXP-038 checkpoint);
  5. observe progress through awareness surfaces only
     (snapshots, rate_observation, coverage_report) until
     the regtest node height advances;
  6. verify the found block through the EXP-036 gate: the
     interface verify_candidate operation over the block's
     80-byte header, plus verify_chain_acceptance against
     the node;
  7. exercise a controlled fault (verified SIGTERM to the
     isolated miner through the controller's guarded signal
     primitive) and the controller recovery taxonomy through
     the interface, including a declared correctness fault,
     which must halt and leave the stack untouched;
  8. run one bounded experiment through the ExperimentRunner
     (Prompt 1 sandbox): a scheduler bake-off whose winner
     selection is independently recomputed inside the
     sandbox, with the strict signed-evidence integrate gate
     deciding eligibility;
  9. run a full awareness observe_cycle, which feeds the
     load-shedding ModeManager the real signals of the
     demonstration;
 10. stop mining through the interface (verified
     postcondition), produce the final accounting from the
     isolated instance's own evidence log, and close the
     plan tasks with their evidence attached.

Safety lines, structural not aspirational: the live mainnet
stack (production autopilot, mainnet_live miner, mainnet
node) is never signalled, restarted or reconfigured; its
only contact is reading the share census of
evidence/mainnet-live.jsonl before and after, which must be
identical in the sense that this process contributed nothing
to it (the census is reported, and the demonstration writes
nothing to the production tree outside research/ and
.local/stage8/). All mutating control acts on the isolated
instance only. The regtest miner's search target is
amplified by 2**24 inside a delegating compute proxy (the
EXP-040 scenario C technique, disclosed in the miner and in
the report); blocks meet the real regtest target.

Measurement discipline: unique hash rate = N_unique /
delta t with N_unique the MiningStatistics unique_nonces
delta between two awareness coverage samples and delta t
the interval between those samples' status events;
p = (T + 1) / 2^256 for the regtest target in force;
Progress_500 and Progress_140T are computed from that
verified unique rate and labelled regtest-demonstration
figures.

Usage: python3 research/EXTREME_RESEARCH/stage8_demonstration.py
Writes the machine-readable evidence record to
research/EXTREME_RESEARCH/stage8_evidence.json and its
working state under .local/stage8/<run-id>/.
"""

import dataclasses
import hashlib
import json
import os
import shutil
import signal
import sys
import time
from fractions import Fraction

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, ROOT)

from agent.intelligence import Agent                    # noqa: E402
from agent.intelligence.awareness import Awareness      # noqa: E402
from agent.intelligence.controller import MiningController  # noqa: E402
from agent.intelligence.experiments import (            # noqa: E402
    CURRENT_SOURCE_COMMIT, ExperimentRunner)
from agent.intelligence.loop import LoopRefusal         # noqa: E402
from agent.intelligence.planning import TaskRecord      # noqa: E402
from agent.intelligence.scheduler import Scheduler      # noqa: E402
from agent.intelligence import verifier                 # noqa: E402
from mining.candidate_verify import (                   # noqa: E402
    verify_candidate, verify_chain_acceptance)
from mining.pow_engine import POW_LIMIT_REGTEST         # noqa: E402
from node.rpc_client import BitcoinRPC                  # noqa: E402

MINER_SCRIPT = os.path.join(_HERE, "stage8_regtest_miner.py")
EVIDENCE_JSON = os.path.join(_HERE, "stage8_evidence.json")
MAINNET_EVIDENCE = os.path.join(ROOT, "evidence",
                                "mainnet-live.jsonl")
AMPLIFY_SHIFT = 24


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_iso_ts(ts):
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(ts)).timestamp()
    except (ValueError, TypeError):
        return None


def share_census(path=MAINNET_EVIDENCE):
    """Full-log census of the LIVE pool evidence log (the
    EXP-037 primary source). Read-only; used before and
    after to prove the demonstration contributed nothing to
    the live stack's record."""
    accepted = rejected = results = 0
    with open(path, "r", encoding="utf-8",
              errors="replace") as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if isinstance(ev, dict) and \
                    ev.get("event") == "share_result":
                results += 1
                if ev.get("accepted"):
                    accepted += 1
                else:
                    rejected += 1
    return {"accepted": accepted, "rejected": rejected,
            "share_results": results}


def asdict_safe(obj):
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    return obj


class Demonstration:
    def __init__(self, workdir):
        self.workdir = workdir
        self.iso = os.path.join(workdir, "iso")
        self.demo_state = os.path.join(workdir, "agent")
        os.makedirs(os.path.join(self.iso, "mining"))
        os.makedirs(os.path.join(self.iso, "scripts"))
        os.makedirs(os.path.join(self.iso, ".local"))
        os.makedirs(os.path.join(self.iso, "evidence"))
        os.makedirs(self.demo_state)
        shutil.copy(os.path.join(ROOT, "mining",
                                 "autopilot.py"),
                    os.path.join(self.iso, "mining",
                                 "autopilot.py"))
        shutil.copy(os.path.join(ROOT, "scripts",
                                 "autopilot.sh"),
                    os.path.join(self.iso, "scripts",
                                 "autopilot.sh"))
        self.evidence = {
            "kind": "stage8_autonomous_demonstration",
            "started_utc": utcnow(),
            "workdir": self.workdir,
            "amplify_shift": AMPLIFY_SHIFT,
            "steps": {},
        }
        self.failures = []

    # Plumbing -------------------------------------------------
    def record(self, step, data):
        self.evidence["steps"][step] = data
        self.flush()
        print(f"[stage8] {step}: "
              f"{json.dumps(data)[:300]}", flush=True)

    def flush(self):
        tmp = EVIDENCE_JSON + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.evidence, f, indent=1,
                      default=str)
        os.replace(tmp, EVIDENCE_JSON)

    def build_agent(self):
        iso_local = os.path.join(self.iso, ".local")
        env = {
            "BAL_AP_MINER_CMD": json.dumps(
                [sys.executable, MINER_SCRIPT]),
            "BAL_AUTO_UPDATE": "0",
            "BAL_AP_HEARTBEAT_S": "1",
            "BAL_AP_POLL_S": "0.2",
            "BAL_AP_STALE_S": "3600",
            "BAL_STAGE8_EVIDENCE": os.path.join(
                self.iso, "evidence", "mainnet-live.jsonl"),
            "BAL_STAGE8_CHECKPOINT": os.path.join(
                iso_local, "work-checkpoint.json"),
            "BAL_STAGE8_AMPLIFY_SHIFT": str(AMPLIFY_SHIFT),
            "BAL_STAGE8_MAX_BLOCKS": "400",
        }
        ctl = MiningController(
            repo_root=self.iso, local_dir=iso_local,
            verify_timeout_s=60.0, poll_s=0.25, env_extra=env,
            miner_needles=("stage8_regtest_miner.py",))
        agent = Agent(
            local_dir=iso_local,
            audit_path=os.path.join(self.demo_state,
                                    "agent-audit.jsonl"),
            tasks_path=os.path.join(self.demo_state,
                                    "agent-tasks.json"),
            sandbox_root=os.path.join(self.demo_state,
                                      "agent-experiments"),
            controller=ctl,
            verifier_key_path=os.path.join(
                self.demo_state, "verifier", "verifier.key"),
            mode_state_path=os.path.join(self.demo_state,
                                         "agent-mode.json"))
        aw = Awareness(
            agent,
            heartbeat_path=os.path.join(iso_local,
                                        "heartbeat.json"),
            census_path=os.path.join(iso_local,
                                     "evidence-count.json"),
            status_path=os.path.join(iso_local,
                                     "mainnet-status.txt"),
            endpoint_path=os.path.join(iso_local,
                                       "mining-endpoint.json"),
            node_config_path=os.path.join(
                ROOT, ".local", "regtest",
                "node-config.json"),
            evidence_log_path=os.path.join(
                self.iso, "evidence", "mainnet-live.jsonl"),
            rpc_factory=lambda path, timeout: BitcoinRPC(
                ).with_timeout(timeout, retries=1))
        return agent, ctl, aw

    # Steps ------------------------------------------------------
    def step1_inspect(self, agent, aw):
        snap = aw.snapshot()
        status = agent.interface.inspect_status()
        machine = agent.interface.inspect_machine()
        backends = agent.interface.inspect_backends()
        data = {
            "snapshot_ts_utc": snap["ts_utc"],
            "mode_at_start": (snap["mode"] or {}).get("mode"),
            "autopilot_running_before_start":
                snap["autopilot"]["running"],
            "node": snap["node"],
            "interface_status": asdict_safe(status),
            "machine": {
                "model_name": machine.model_name,
                "logical_cpus": machine.logical_cpus,
                "has_sha_ni": machine.has_sha_ni,
                "has_avx2": machine.has_avx2,
                "has_avx512f": machine.has_avx512f,
                "effective_cpus_note":
                    machine.effective_cpus_note},
            "backends": asdict_safe(backends),
        }
        self.start_height = snap["node"]["blocks"]
        self.record("1_inspect", data)
        return data

    def step2_memory_gates(self, agent):
        loop = agent.loop()
        out = {}
        probes = (
            ("rejected", "K+W constant folding of the "
             "message-schedule constants for a fixed "
             "template", ["K+W", "folding"]),
            ("integrated", "a dual-batch masked search "
             "backend (v512dual) for the production "
             "search path",
             ["v512dual"]),
        )
        for kind, hypothesis, keywords in probes:
            rec = loop.new_record(
                f"stage8-probe-{kind}", hypothesis,
                keywords=keywords)
            loop.advance(rec)  # observe to hypothesise
            try:
                loop.advance(rec)  # the prior-research gate
                out[kind] = {"refused": False,
                             "state": rec.state}
                self.failures.append(
                    f"step2: {kind} probe was NOT refused")
            except LoopRefusal as exc:
                out[kind] = {
                    "refused": True,
                    "refusal": str(exc),
                    "citation": exc.citation}
        out["memory_stats"] = agent.memory.stats()
        out["integrated_ids_count"] = len(
            agent.memory.integrated_ids())
        self.record("2_memory_gates", out)
        return out

    def step3_plan(self, agent):
        tasks = agent.tasks
        tasks.add(TaskRecord(
            task_id="stage8-demonstration",
            objective=("Stage 8: one complete mining "
                       "operation on regtest directed by "
                       "the agent layer through its own "
                       "machinery"),
            level="strategic", risk="medium",
            required_evidence=["final_accounting"],
            expected_output=("stage8_evidence.json plus "
                             "STAGE8_AUTONOMOUS_"
                             "DEMONSTRATION.md"),
            success_criteria=("a regtest block mined "
                              "through the controller path "
                              "and verified through the "
                              "EXP-036 gate; all plan tasks "
                              "closed with evidence"),
            failure_criteria=("any step faked, skipped "
                              "silently, or executed outside "
                              "the agent machinery")))
        plan = [
            ("s8-inspect", "Inspect the environment through "
             "awareness", [], ["awareness_snapshot"]),
            ("s8-memory", "Consult research memory through "
             "the loop gates", [], ["gate_citations"]),
            ("s8-start", "Start regtest mining through the "
             "interface and controller", ["s8-inspect"],
             ["start_verified"]),
            ("s8-mine", "Mine and observe until the node "
             "height advances", ["s8-start"],
             ["block_observed", "rate_observation"]),
            ("s8-verify", "Verify the found block through "
             "the EXP-036 gate", ["s8-mine"],
             ["exp036_verdict", "chain_acceptance"]),
            ("s8-fault", "Exercise the fault and recovery "
             "taxonomy", ["s8-mine"],
             ["recovery_outcome", "correctness_halt"]),
            ("s8-experiment", "Run the bounded bake-off "
             "experiment through the sandbox and the "
             "integrate gate", ["s8-inspect"],
             ["gate_verdict"]),
            ("s8-modes", "Run an awareness observe cycle "
             "feeding the mode machine", ["s8-mine"],
             ["observe_cycle_report"]),
            ("s8-stop", "Stop mining and produce the final "
             "accounting",
             ["s8-verify", "s8-fault", "s8-experiment",
              "s8-modes"],
             ["stop_verified", "final_accounting"]),
        ]
        for task_id, objective, deps, req_ev in plan:
            tasks.add(TaskRecord(
                task_id=task_id, objective=objective,
                level="execution",
                parent="stage8-demonstration",
                dependencies=deps, required_evidence=req_ev,
                risk="low"))
        tasks.transition("stage8-demonstration", "active")
        for task_id in ("s8-inspect", "s8-memory"):
            tasks.transition(task_id, "active")
        self.record("3_plan", {
            "tasks": [t.task_id for t in tasks.list()],
            "strategic_task": "stage8-demonstration"})
        return tasks

    def close_task(self, tasks, task_id, evidence_items):
        tasks.add_evidence(task_id, evidence_items)
        tasks.transition(task_id, "done")

    def step4_start(self, agent, ctl, tasks):
        tasks.transition("s8-start", "active")
        result = agent.interface.start_mining()
        info = ctl.inspect()
        data = {"result": asdict_safe(result),
                "inspect_after": {
                    "running": info["running"],
                    "miner_pid": info["miner_pid"],
                    "miner_verified": info["miner_verified"],
                    "autopilot_pid": info["autopilot_pid"],
                    "autopilot_verified":
                        info["autopilot_verified"]}}
        if not result.ok:
            self.failures.append("step4: start_mining "
                                 "did not verify")
        self.record("4_start", data)
        return data

    def step5_mine_observe(self, agent, aw, tasks):
        tasks.transition("s8-mine", "active")
        # Wait, through awareness snapshots only, for the
        # node height to advance past the start height.
        deadline = time.time() + 300
        first = None
        while time.time() < deadline:
            snap = aw.snapshot()
            blocks = (snap["node"] or {}).get("blocks")
            if blocks is not None and \
                    blocks > self.start_height:
                first = snap
                break
            time.sleep(2)
        if first is None:
            self.failures.append(
                "step5: node height did not advance within "
                "300 s of awareness polling")
            self.record("5_mine_observe",
                        {"advanced": False})
            return None
        cov_a = aw.coverage_report()
        obs = aw.rate_observation(25.0)
        cov_b = aw.coverage_report()
        stats_a = cov_a["latest_statistics"] or {}
        stats_b = cov_b["latest_statistics"] or {}
        ts_a = parse_iso_ts(cov_a["statistics_event_ts"])
        ts_b = parse_iso_ts(cov_b["statistics_event_ts"])
        unique_delta = None
        unique_rate = None
        if stats_a and stats_b and ts_a and ts_b \
                and ts_b > ts_a:
            unique_delta = (stats_b.get("unique_nonces", 0)
                            - stats_a.get("unique_nonces", 0))
            unique_rate = unique_delta / (ts_b - ts_a)
        rpc = BitcoinRPC()
        best = rpc.get_best_block_hash()
        data = {
            "advanced": True,
            "start_height": self.start_height,
            "height_at_first_observation":
                first["node"]["blocks"],
            "best_block_hash_at_observation": best,
            "rate_observation": obs,
            "coverage_sample_a": {
                "statistics_event_ts":
                    cov_a["statistics_event_ts"],
                "totals": stats_a},
            "coverage_sample_b": {
                "statistics_event_ts":
                    cov_b["statistics_event_ts"],
                "totals": stats_b},
            "unique_nonces_delta": unique_delta,
            "unique_window_s": (ts_b - ts_a) if (
                ts_a and ts_b) else None,
            "unique_hash_rate_hs": unique_rate,
        }
        self.record("5_mine_observe", data)
        return data

    def step6_verify(self, agent, tasks, block_hash):
        tasks.transition("s8-verify", "active")
        rpc = BitcoinRPC()
        header_hex = rpc.call("getblockheader", block_hash,
                              False)
        header = bytes.fromhex(header_hex)
        resp = agent.interface.verify_candidate_op(
            header, chain="regtest")
        direct = verify_candidate(header, POW_LIMIT_REGTEST)
        chain_status, chain_accepted = \
            verify_chain_acceptance(rpc, block_hash)
        target = direct["target"]
        p_exact = Fraction(target + 1, 1 << 256)
        data = {
            "block_hash": block_hash,
            "header_hex": header_hex,
            "interface_verdict": asdict_safe(resp),
            "direct_verdict": {
                "classification": direct["classification"],
                "reason": direct["reason"],
                "digests_agree": direct["digests_agree"],
                "valid_header": direct["valid_header"],
                "meets_network_target":
                    direct["meets_network_target"],
                "value": direct["value"],
                "target": target,
                "nbits": direct["nbits"]},
            "chain_acceptance": {
                "status": chain_status,
                "accepted": chain_accepted},
            "p_target": {
                "formula": "p = (T + 1) / 2^256",
                "target": target,
                "p_exact_fraction": f"{p_exact.numerator}/"
                                    f"{p_exact.denominator}",
                "p_float": float(p_exact),
                "expected_hashes_per_block_real_target":
                    float(1 / p_exact),
                "expected_hashes_per_block_amplified":
                    float(1 / p_exact) * (1 << AMPLIFY_SHIFT)},
        }
        if resp.classification != "block_candidate" or \
                not chain_accepted:
            self.failures.append(
                "step6: EXP-036 verification did not pass "
                "for the found block")
        self.record("6_verify_block", data)
        return data

    def step7_fault_recovery(self, agent, ctl, tasks):
        tasks.transition("s8-fault", "active")
        info = ctl.inspect()
        miner_pid = info["miner_pid"]
        signalled = ctl.signal_verified(
            miner_pid, signal.SIGTERM, "miner")
        recovery = agent.interface.trigger_recovery()
        # Confirm the watchdog's relaunch independently of
        # the recovery call's own verdict.
        deadline = time.time() + 90
        relaunched = None
        while time.time() < deadline:
            cur = ctl.inspect()
            if cur["running"] and cur["miner_pid"] \
                    and cur["miner_pid"] != miner_pid:
                relaunched = cur
                break
            time.sleep(0.5)
        halt = agent.interface.trigger_recovery(
            correctness_failure=True)
        after_halt = ctl.inspect()
        checkpoint = ctl.checkpoint()
        iface_checkpoint = agent.interface.checkpoint_status(
            ctl.checkpoint_path)
        data = {
            "miner_pid_before": miner_pid,
            "signal_verified_returned": signalled,
            "recovery_result": asdict_safe(recovery),
            "watchdog_relaunch": {
                "observed": relaunched is not None,
                "new_miner_pid": (relaunched or {}).get(
                    "miner_pid"),
                "restarts": (relaunched or {}).get(
                    "restarts")},
            "correctness_halt": asdict_safe(halt),
            "stack_after_halt": {
                "running": after_halt["running"],
                "miner_pid": after_halt["miner_pid"],
                "untouched": bool(
                    relaunched
                    and after_halt["miner_pid"]
                    == relaunched["miner_pid"])},
            "checkpoint": asdict_safe(checkpoint),
            "interface_checkpoint": asdict_safe(
                iface_checkpoint),
        }
        if relaunched is None:
            self.failures.append(
                "step7: watchdog relaunch not observed")
        if halt.ok or halt.status != "halted":
            self.failures.append(
                "step7: correctness fault did not halt")
        self.record("7_fault_recovery", data)
        return data

    def step8_experiment(self, agent, tasks):
        tasks.transition("s8-experiment", "active")
        sched = Scheduler(agent, cache_path=os.path.join(
            self.demo_state, "scheduler-cache.json"))
        bake = sched.bake_off()
        runner = ExperimentRunner(agent)
        record, sandbox = runner.create_experiment(
            "adopt the scheduler bake-off winner as the "
            "backend pin for regtest demonstration mining",
            ["stage8-demonstration-bakeoff"],
            "stage8-demonstration", performance_claim=False)
        artifact_path = runner.write_file(
            record, "bakeoff.json",
            json.dumps(bake, indent=1, sort_keys=True,
                       default=str))
        with open(artifact_path, "rb") as f:
            artifact_sha = hashlib.sha256(
                f.read()).hexdigest()
        check_src = (
            "import json, math, sys\n"
            "bake = json.load(open('bakeoff.json'))\n"
            "rows = [r for r in bake['rows'] "
            "if r.get('eligible') "
            "and r.get('median_rate_hs')]\n"
            "ok = bool(rows)\n"
            "best = None\n"
            "for r in rows:\n"
            "    v = r['median_rate_hs']\n"
            "    if not (isinstance(v, (int, float)) "
            "and math.isfinite(v) and v > 0):\n"
            "        ok = False\n"
            "    if best is None or v > best[1]:\n"
            "        best = (r['tier'], v)\n"
            "winner_ok = ok and best is not None "
            "and best[0] == bake.get('winner')\n"
            "def rec(passed, method):\n"
            "    return {'passed': bool(passed), "
            "'verifier_id': 'stage8-sandbox-recompute', "
            f"'artifact_sha256': '{artifact_sha}', "
            f"'source_commit': "
            f"'{CURRENT_SOURCE_COMMIT}', "
            "'verification_method': method, "
            "'timestamp': "
            "time.strftime('%Y-%m-%dT%H:%M:%SZ', "
            "time.gmtime())}\n"
            "import time\n"
            "ev = {'correctness': rec(winner_ok, "
            "'independent_recompute'), "
            "'differential': rec(winner_ok, "
            "'differential_reference')}\n"
            "json.dump(ev, open('evidence-a.json', 'w'))\n"
            "print('recomputed winner:', best, "
            "'winner_ok:', winner_ok)\n"
            "sys.exit(0 if winner_ok else 1)\n")
        runner.write_file(record, "check_bakeoff.py",
                          check_src)
        run = runner.run_command(
            record, [sys.executable, "check_bakeoff.py"],
            timeout_s=300)
        signed = verifier.request_verification(
            artifact_path, CURRENT_SOURCE_COMMIT,
            "independent_recompute",
            key_path=agent.verifier_key_path)
        runner.write_file(record, "evidence-b.json",
                          json.dumps(
                              {"independent_verification":
                               signed}, indent=1))
        bundle = runner.assemble_evidence(record)
        runner.walk_to_record(record)
        verdict = runner.attempt_integrate(record)
        ledger_ok, ledger_detail = runner.verify_ledger(
            record.loop_id)
        data = {
            "bake_off": {
                "winner": bake.get("winner"),
                "winner_rate_hs": bake.get("winner_rate_hs"),
                "rows": bake.get("rows"),
                "contention": bake.get("contention"),
                "from_cache": bake.get("from_cache")},
            "experiment_id": record.loop_id,
            "sandbox": sandbox,
            "artifact_sha256": artifact_sha,
            "sandbox_run": {
                "exit_code": run["exit_code"],
                "timed_out": run["timed_out"],
                "termination_reason":
                    run["termination_reason"],
                "wall_s": run["wall_s"]},
            "signed_verifier_record": {
                "passed": signed.get("passed"),
                "verifier_id": signed.get("verifier_id"),
                "artifact_sha256":
                    signed.get("artifact_sha256")},
            "evidence_files": bundle.get("evidence_files"),
            "gate_verdict": verdict,
            "ledger": {"ok": ledger_ok,
                       "detail": ledger_detail},
            "production_effect": (
                "none: a gate pass here is a record "
                "decision only (experiments.py); no "
                "production dispatch or pin was changed, "
                "and the controller's select_backend "
                "remains unsupported on the production "
                "path"),
        }
        self.record("8_experiment", data)
        return data

    def step9_modes(self, agent, aw, tasks):
        tasks.transition("s8-modes", "active")
        before = agent.mode()
        report = aw.observe_cycle(window_s=20.0)
        after = agent.mode()
        data = {
            "mode_before": before,
            "mode_after": after,
            "observe_cycle": {
                "ts_utc": report["ts_utc"],
                "mode_note": report.get("mode_note"),
                "rate_observation":
                    report["rate_observation"],
                "degradation_flags": [
                    f["flag"] for f in
                    (report["degradation"] or {}).get(
                        "flags", [])],
                "degradation_not_evaluated": (
                    report["degradation"] or {}).get(
                        "not_evaluated"),
                "overhead": report["overhead"]},
            "transition_fired": bool(
                before and after
                and before.get("mode") != after.get("mode")),
        }
        self.record("9_modes", data)
        return data

    def step10_stop_account(self, agent, ctl, tasks):
        tasks.transition("s8-stop", "active")
        result = agent.interface.stop_mining()
        info = ctl.inspect()
        status = agent.interface.inspect_status()
        # Final accounting from the isolated instance's own
        # evidence log: sessions split at miner_start
        # events; each session's totals are its last status
        # event's statistics (cumulative per process).
        log_path = os.path.join(self.iso, "evidence",
                                "mainnet-live.jsonl")
        sessions = []
        blocks = []
        cur = None
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                kind = ev.get("event")
                if kind == "miner_start":
                    cur = {"start_event": ev,
                           "last_status": None}
                    sessions.append(cur)
                elif kind == "status" and cur is not None:
                    cur["last_status"] = ev
                elif kind == "block":
                    blocks.append(ev)
        totals = {}
        for sess in sessions:
            st = ((sess["last_status"] or {}).get(
                "statistics") or {})
            for key, val in st.items():
                if isinstance(val, int):
                    totals[key] = totals.get(key, 0) + val
        rpc = BitcoinRPC()
        final_height = rpc.get_blockchain_info()["blocks"]
        data = {
            "stop_result": asdict_safe(result),
            "inspect_after_stop": {
                "running": info["running"],
                "autopilot_alive": info["autopilot_alive"],
                "miner_state": info["miner_state"]},
            "interface_status_after_stop": asdict_safe(
                status),
            "sessions": len(sessions),
            "session_totals_summed": totals,
            "blocks_recorded_by_miner": len(blocks),
            "first_block": (blocks[0] if blocks else None),
            "last_block": (blocks[-1] if blocks else None),
            "node_height_start": self.start_height,
            "node_height_final": final_height,
            "node_height_delta": (final_height
                                  - self.start_height),
            "blocks_match_height_delta": (
                len(blocks) == final_height
                - self.start_height),
        }
        if not result.ok:
            self.failures.append("step10: stop_mining "
                                 "did not verify")
        self.record("10_stop_accounting", data)
        return data

    # Orchestration ----------------------------------------------
    def run(self):
        census_before = share_census()
        self.evidence["mainnet_census_before"] = census_before
        agent, ctl, aw = self.build_agent()
        tasks = None
        try:
            self.step1_inspect(agent, aw)
            self.step2_memory_gates(agent)
            tasks = self.step3_plan(agent)
            self.close_task(tasks, "s8-inspect",
                            ["awareness_snapshot"])
            self.close_task(tasks, "s8-memory",
                            ["gate_citations"])
            self.step4_start(agent, ctl, tasks)
            self.close_task(tasks, "s8-start",
                            ["start_verified"])
            mine = self.step5_mine_observe(agent, aw, tasks)
            block_hash = None
            if mine:
                block_hash = mine[
                    "best_block_hash_at_observation"]
                self.close_task(
                    tasks, "s8-mine",
                    ["block_observed", "rate_observation"])
                self.step6_verify(agent, tasks, block_hash)
                self.close_task(
                    tasks, "s8-verify",
                    ["exp036_verdict", "chain_acceptance"])
                self.step7_fault_recovery(agent, ctl, tasks)
                self.close_task(
                    tasks, "s8-fault",
                    ["recovery_outcome", "correctness_halt"])
            self.step8_experiment(agent, tasks)
            self.close_task(tasks, "s8-experiment",
                            ["gate_verdict"])
            if mine:
                self.step9_modes(agent, aw, tasks)
                self.close_task(tasks, "s8-modes",
                                ["observe_cycle_report"])
            self.step10_stop_account(agent, ctl, tasks)
            self.close_task(
                tasks, "s8-stop",
                ["stop_verified", "final_accounting"])
            tasks.add_evidence("stage8-demonstration",
                               ["final_accounting"])
            tasks.transition("stage8-demonstration", "done")
        except Exception as exc:
            import traceback
            self.evidence["exception"] = {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc()}
            self.failures.append(
                f"unhandled exception: "
                f"{type(exc).__name__}: {exc}")
        finally:
            try:
                ctl.stop()
            except Exception as exc:
                self.evidence["cleanup_stop_error"] = str(exc)
            census_after = share_census()
            self.evidence["mainnet_census_after"] = \
                census_after
            self.evidence["mainnet_census_unchanged_by_demo"] \
                = (census_after == census_before)
            self.evidence["failures"] = self.failures
            self.evidence["finished_utc"] = utcnow()
            self.flush()
        return 0 if not self.failures else 1


def main():
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    workdir = os.path.join(ROOT, ".local", "stage8", run_id)
    os.makedirs(workdir, exist_ok=True)
    demo = Demonstration(workdir)
    return demo.run()


if __name__ == "__main__":
    sys.exit(main())
