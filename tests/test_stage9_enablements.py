"""Stage 9 enablements suite (2026-11-18).

Owner decision 2026-11-18: enable all five (EXP-052
bake-off dispatch, EXP-057 aggregation tier, EXP-058 PID
controller, EXP-050 endpoint health, EXP-051 prefetch) and
accept EXP-047 first-publisher-wins as production search
semantics. This suite pins what the enablements workstream
actually changed, per item, at the level the change was
made. The full record is
research/STAGE9/ENABLEMENTS_REPORT.md.

- EXP-051 (enabled in code): the agent path
  (agent/autonomous.py AutonomousMiner) constructs its
  MiningEngine with use_prefetch=True by default, and
  use_prefetch=False restores the historical construction
  exactly. The engine's own default is unchanged.
- EXP-057 (runner built): mining/aggregation_mainnet.py
  loads a fleet deployment file fail-closed and defaults
  to port 3334, never the solo cutover's 3333.
- EXP-052 (armed, switch pending): the deployment verdict
  cache planted at .local/bakeoff-dispatch.json validates
  under this host's fingerprint and the resolver, fed the
  live config's own merge path with the bakeoff section
  enabled on a COPY, returns the campaign's STATIC
  verdict. The live endpoint config itself is untouched
  by this workstream (mode still "pool", no bakeoff or
  pool_health section written by us); the check below
  pins that, and is expected to be updated when the
  operator performs the switch flip.
- EXP-050 (armed, switch pending): the same merge path
  with pool_health enabled on a COPY builds the policy
  exactly as mining/mainnet_live.py builds it, over the
  single live endpoint; on one endpoint the policy's
  decisions are observe-only (retry, retry, exhausted,
  pointing back at the primary; failback never due).
- EXP-058 (NOT enabled, by record): the controller's own
  switch exists and works in isolation, and no live
  production module imports mining/pid_control. The
  EXP-058 record does not propose live-miner actuation;
  this suite pins that the workstream did not wire it in
  anyway.
- EXP-047 (documentation): the completion report carries
  the dated owner-acceptance addendum and the experiment
  registry records the acceptance.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CHECKS = 0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    if not cond:
        print(f"FAIL: {label}", flush=True)
        sys.exit(1)
    print(f"ok {CHECKS}: {label}", flush=True)


class _FakeRPC:
    def get_blockchain_info(self):
        return {"chain": "regtest"}


class _FakeCompute:
    backend = "cpu"
    fallback_reason = "fake"

    def benchmark(self):
        return 0.0


class _FakeStore:
    def record_event(self, kind, entry):
        pass

    def record_mining_cycle(self, result):
        pass

    def mining_summary(self):
        return {}


def exp051_agent_default():
    from agent.autonomous import AutonomousMiner
    miner = AutonomousMiner(_FakeRPC(), "bc1qexample",
                            store=_FakeStore(),
                            compute=_FakeCompute())
    check(miner.use_prefetch is True,
          "EXP-051: agent path defaults to prefetch enabled")
    check(miner.engine.use_prefetch is True,
          "EXP-051: agent MiningEngine has use_prefetch=True")
    check(miner.engine.prefetch_queue is not None,
          "EXP-051: agent MiningEngine constructed its "
          "PrefetchQueue")
    miner.close()
    off = AutonomousMiner(_FakeRPC(), "bc1qexample",
                          store=_FakeStore(),
                          compute=_FakeCompute(),
                          use_prefetch=False)
    check(off.engine.use_prefetch is False
          and off.engine.prefetch_queue is None,
          "EXP-051: use_prefetch=False restores the "
          "historical agent construction (no queue)")
    from mining.engine import MiningEngine
    eng = MiningEngine(_FakeRPC(), "bc1qexample",
                       compute=_FakeCompute())
    check(eng.use_prefetch is False
          and eng.prefetch_queue is None,
          "EXP-051: MiningEngine's own default is unchanged "
          "(opt-in at the engine level)")


def exp057_runner():
    from mining import aggregation_mainnet as runner
    check(runner.DEFAULT_PORT == 3334
          and runner.DEFAULT_PORT != 3333,
          "EXP-057: tier runner defaults to port 3334, "
          "never the solo cutover port 3333")
    with tempfile.TemporaryDirectory() as td:
        missing = os.path.join(td, "nope.json")
        try:
            runner.load_deployment(missing)
            raised = False
        except OSError:
            raised = True
        check(raised, "EXP-057: missing deployment file "
                      "fails closed (OSError)")
        bad = os.path.join(td, "bad.json")
        with open(bad, "w") as f:
            json.dump({"fleet_id": "f1", "workers": []}, f)
        try:
            runner.load_deployment(bad)
            raised = False
        except ValueError:
            raised = True
        check(raised, "EXP-057: deployment enrolling no "
                      "workers fails closed (ValueError)")
        good = os.path.join(td, "good.json")
        with open(good, "w") as f:
            json.dump({"fleet_id": "f1",
                       "operator_token": "op",
                       "workers": [{"worker_id": "w1",
                                    "token": "t1"}]}, f)
        dep = runner.load_deployment(good)
        check(dep["fleet_id"] == "f1"
              and dep["workers"][0]["worker_id"] == "w1",
              "EXP-057: a well-formed deployment file loads")


def _live_config_copy_with(section, values):
    """The live endpoint config's raw contents, copied to a
    temp file with one section's values set on the COPY.
    The live file is never written."""
    from mining import endpoint_config
    with open(endpoint_config.CONFIG_PATH) as f:
        raw = json.load(f)
    raw.setdefault(section, {}).update(values)
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(raw, f)
    return path


def exp052_armed():
    from mining import endpoint_config
    from mining.bakeoff_dispatch import (DEFAULT_CACHE_PATH,
                                         resolve_requested)
    check(os.path.exists(DEFAULT_CACHE_PATH),
          "EXP-052: deployment verdict cache is planted at "
          ".local/bakeoff-dispatch.json")
    path = _live_config_copy_with("bakeoff", {"enabled": True})
    try:
        cfg = endpoint_config.load_config(path)
        merged = endpoint_config.bakeoff_config(cfg)
        check(merged["enabled"] is True,
              "EXP-052: merge path honours the bakeoff "
              "section on a config copy")
        requested, reason = resolve_requested(merged)
        check(requested == "auto"
              and reason.startswith("static:"),
              "EXP-052: resolver returns the planted "
              "campaign's STATIC verdict for this host "
              f"(got {requested!r}, {reason!r})")
    finally:
        os.unlink(path)
    with open(endpoint_config.CONFIG_PATH) as f:
        live_raw = json.load(f)
    check(live_raw.get("mode") == "pool"
          and "bakeoff" not in live_raw
          and "pool_health" not in live_raw,
          "EXP-052/050: the live endpoint config is "
          "untouched by this workstream (mode pool, no "
          "switch sections written); the flip is the "
          "operator's scripted write, recorded in the "
          "enablements report")


def exp050_armed():
    from mining import endpoint_config
    from mining.endpoint_health import EndpointHealthPolicy
    path = _live_config_copy_with("pool_health",
                                  {"enabled": True})
    try:
        cfg = endpoint_config.load_config(path)
        health = endpoint_config.pool_health_config(cfg)
        check(health["enabled"] is True,
              "EXP-050: merge path honours the pool_health "
              "section on a config copy")
        host, port, mode, _ = endpoint_config.resolve_endpoint(
            path=path)
        check(mode == "pool",
              "EXP-050: the live config still resolves to "
              "pool mode")
        endpoints = endpoint_config.pool_policy_endpoints(
            cfg, host, port)
        check(endpoints == [(host, port)],
              "EXP-050: with no fallbacks named, the policy "
              "endpoint list is exactly the live primary")
        policy = EndpointHealthPolicy(
            endpoints,
            error_threshold=health["error_threshold"],
            failback_interval_s=health["failback_interval_s"],
            damping_window_s=health["damping_window_s"],
            max_failbacks_per_window=
                health["max_failbacks_per_window"],
            probe_timeout_s=health["probe_timeout_s"])
        check(policy.current == (host, port)
              and policy.on_primary
              and not policy.failback_due(),
              "EXP-050: the armed policy sits on the "
              "primary; failback is never due on it")
        decisions = [policy.note_error() for _ in range(3)]
        check(decisions == ["retry", "retry", "exhausted"]
              and policy.current == (host, port)
              and policy.exhausted,
              "EXP-050: on a single endpoint the policy "
              "observes and reports (retry, retry, "
              "exhausted, back at the primary); failover "
              "has no target and stays inert")
        info = policy.note_success()
        check(info["was_exhausted"] and not policy.exhausted,
              "EXP-050: a success on the primary is "
              "recorded as the recovery it is")
        status = policy.status()
        check(status["total_errors"] == 3
              and status["errors_by_endpoint"]
                  == {f"{host}:{port}": 3},
              "EXP-050: the policy records health against "
              "the live endpoint (errors_by_endpoint)")
    finally:
        os.unlink(path)


def exp058_not_wired():
    from mining.pid_control import (Signals, make_work_controller)
    off = make_work_controller({})
    cmd = off.update(Signals(2.0, 0.0))
    check(cmd.mode == "disabled",
          "EXP-058: default configuration is the disabled "
          "controller (step policy, today's behaviour)")
    on = make_work_controller({"pid_enabled": True})
    cmd = on.update(Signals(2.0, 0.0))
    check(cmd.mode == "pid",
          "EXP-058: the controller's own switch works in "
          "isolation (the mechanism is intact)")
    root = os.path.join(os.path.dirname(__file__), "..")
    for rel in ("mining/autopilot.py", "mining/mainnet_live.py",
                "mining/engine.py", "agent/autonomous.py",
                "mining/fleet_gateway.py"):
        with open(os.path.join(root, rel)) as f:
            src = f.read()
        check("pid_control" not in src,
              f"EXP-058: {rel} does not import the PID "
              f"controller (not wired into any live path, "
              f"per the EXP-058 record)")


def exp047_documented():
    root = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(
            root, "research", "sha256d", "exp047",
            "EXP047_COMPLETION_REPORT.md")) as f:
        report = f.read()
    check("Owner acceptance (2026-11-18)" in report
          and "first-publisher-wins" in report,
          "EXP-047: the completion report carries the "
          "dated owner-acceptance addendum")
    with open(os.path.join(
            root, "research", "EXTREME_RESEARCH",
            "EXPERIMENT_REGISTRY.json")) as f:
        reg = json.load(f)
    entries = reg if isinstance(reg, list) \
        else reg.get("entries") or reg.get("experiments")
    entry = next(e for e in entries if e.get("id") == "EXP-047")
    check("2026-11-18" in entry["measured_result"]
          and "first-publisher-wins" in entry["measured_result"],
          "EXP-047: the experiment registry records the "
          "owner acceptance, dated 2026-11-18")


def main():
    exp051_agent_default()
    exp057_runner()
    exp052_armed()
    exp050_armed()
    exp058_not_wired()
    exp047_documented()
    print(f"Stage 9 enablements suite: {CHECKS} checks, "
          f"ALL PASSED", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
