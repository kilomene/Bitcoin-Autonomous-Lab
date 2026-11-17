#!/usr/bin/env python3
"""EXP-056 campaign driver: gates, control, and the
staged attack on the H-033-02 residual cone space,
exactly as predeclared in PREDECLARATION.md (sha256
pinned in exp056_cone_synth.py).

Usage:
  exp056_campaign.py gates
  exp056_campaign.py control
  exp056_campaign.py stageA <a_cone|e_cone>
  exp056_campaign.py stageB <a_cone|e_cone>
  exp056_campaign.py stageC
  exp056_campaign.py status

State is checkpointed after every query to
RAW_RESULTS/exp056_checkpoint.json; a restarted
driver resumes and never repeats a completed query.
Solver wall is accounted against the predeclared
6,600 s box across every z3 query. One process at a
time; run under nice -n 19.

No em dash characters anywhere in this file.
"""

import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXP056 = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import exp056_cone_synth as es  # noqa: E402
import exp033_cone_synth as cs  # noqa: E402

SOLVER_BOX_S = 6600.0
SLACK_S = 60.0
RAW = os.path.join(EXP056, "RAW_RESULTS")
PROOFS = os.path.join(EXP056, "PROOFS")
CKPT = os.path.join(RAW, "exp056_checkpoint.json")
SEED = 20261119


def ts():
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def load_ckpt():
    if os.path.exists(CKPT):
        with open(CKPT) as fh:
            return json.load(fh)
    return {"experiment": "EXP-056",
            "predeclaration_sha256":
                es.PREDECLARATION_SHA256,
            "solver_box_s": SOLVER_BOX_S,
            "solver_wall_s": 0.0,
            "campaign_start_wall": time.time(),
            "gates": {}, "control": {},
            "cones": {"a_cone": {}, "e_cone": {}},
            "sat_candidate": None,
            "log": []}


def save_ckpt(ck):
    tmp = CKPT + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(ck, fh, indent=2, default=str)
    os.replace(tmp, CKPT)


def account(ck, wall, label):
    ck["solver_wall_s"] += wall
    ck["log"].append({"ts": ts(), "label": label,
                      "wall_s": round(wall, 1),
                      "solver_wall_total_s":
                          round(ck["solver_wall_s"], 1)})
    save_ckpt(ck)
    print(f"  [account] {label}: {wall:.1f}s, total "
          f"{ck['solver_wall_s']:.1f}s of "
          f"{SOLVER_BOX_S:.0f}s", flush=True)


def budget_allows(ck, timeout_s):
    return ck["solver_wall_s"] + timeout_s <= \
        SOLVER_BOX_S + SLACK_S


def fresh_examples():
    return es.seed_examples(random.Random(SEED))


def write_result(name, obj):
    path = os.path.join(RAW, name)
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, default=str)
    print("wrote", path, flush=True)
    return path


def handle_candidate(ck, cone, prog, outputs, source):
    """The predeclared SAT verification protocol.
    Returns True if the candidate is verified."""
    print(f"*** SAT candidate from {source} for {cone}: "
          f"verifying ***", flush=True)
    res, cex, wall = es.verify_cone_candidate(
        cone, prog, outputs, timeout_ms=600000)
    account(ck, wall, f"verify candidate {cone} {source}")
    if res != "unsat":
        ck["sat_candidate"] = {
            "cone": cone, "source": source,
            "program": prog, "outputs": outputs,
            "verify_verdict": res,
            "counterexample": cex, "verified": False}
        save_ckpt(ck)
        print(f"*** candidate NOT verified: verify "
              f"verdict {res} ***", flush=True)
        return False
    rng = random.Random(20261121)
    target = cs.CONES[cone]["target"]
    bad = 0
    for _ in range(1000000):
        vals = tuple(rng.getrandbits(32) for _ in range(4))
        if es.run_program_canon(prog, outputs, vals) \
                != target(vals):
            bad += 1
    ck["sat_candidate"] = {
        "cone": cone, "source": source, "program": prog,
        "outputs": outputs, "verify_verdict": "unsat",
        "python_differential_1e6_bad": bad,
        "verified": bad == 0}
    save_ckpt(ck)
    write_result(f"exp056_sat_{cone}_{ts()}.json",
                 ck["sat_candidate"])
    print(f"*** candidate verified: {bad == 0} "
          f"(differential bad {bad}) ***", flush=True)
    return bad == 0


def do_gates(ck):
    if ck["gates"].get("done"):
        print("gates already done", flush=True)
        return 0
    es.check_predeclaration()
    print("predeclaration hash pinned and verified",
          flush=True)
    rng = random.Random(SEED)
    gates = {"done": False}
    for name, cone in cs.CONES.items():
        bad = 0
        t0 = time.time()
        for _ in range(1000000):
            vals = tuple(rng.getrandbits(32)
                         for _ in range(4))
            if cs.run_program(cone["incumbent"],
                              cone["incumbent_outputs"],
                              vals) != cone["target"](vals):
                bad += 1
        gates[f"{name}_differential_1e6_bad"] = bad
        print(f"{name} incumbent differential 1e6: "
              f"bad {bad} ({time.time() - t0:.1f}s)",
              flush=True)
        assert bad == 0
        t0 = time.time()
        res, _ = cs.verify_program_z3(
            name, cone["incumbent"],
            cone["incumbent_outputs"], timeout_ms=600000)
        wall = time.time() - t0
        account(ck, wall, f"gate z3 verify {name}")
        gates[f"{name}_incumbent_z3"] = res
        print(f"{name} incumbent z3 verify: {res}",
              flush=True)
        assert res == "unsat"
    gates["done"] = True
    ck["gates"] = gates
    save_ckpt(ck)
    write_result(f"exp056_gates_{ts()}.json", gates)
    return 0


def do_control(ck):
    if ck["control"].get("done"):
        print("control already done", flush=True)
        return 0
    examples = fresh_examples()
    ctl = {"done": False, "attempts": []}
    for n_ex, cap_ms in ((16, 900000), (8, 600000)):
        use = examples[:n_ex]
        if not budget_allows(ck, cap_ms / 1000.0):
            ctl["attempts"].append(
                {"examples": n_ex, "verdict": "no_budget"})
            break
        verdict, prog, outputs, wall = es.synth_query(
            es.planted_target, 5, use, cap_ms,
            encoding="A")
        account(ck, wall, f"control synth {n_ex} examples")
        att = {"examples": n_ex, "verdict": verdict,
               "wall_s": round(wall, 1)}
        if verdict == "sat":
            vres, vwall = es.verify_two_programs(
                prog, outputs, es.P5_PROGRAM,
                es.P5_OUTPUTS, timeout_ms=600000)
            account(ck, vwall, "control verify")
            att["verify_verdict"] = vres
            rng = random.Random(20261120)
            bad = 0
            for _ in range(200000):
                vals = tuple(rng.getrandbits(32)
                             for _ in range(4))
                if es.run_program_canon(prog, outputs,
                                        vals) != \
                        es.planted_target(vals):
                    bad += 1
            att["differential_200k_bad"] = bad
            att["program"] = prog
            att["outputs"] = outputs
            ctl["passed"] = (vres == "unsat" and bad == 0)
        elif verdict == "unsat":
            ctl["passed"] = False
            ctl["failed_unsat"] = True
        ctl["attempts"].append(att)
        print(f"control attempt {n_ex} examples: "
              f"{verdict}", flush=True)
        if verdict != "unknown":
            break
    if ctl.get("passed"):
        ctl["done"] = True
    elif ctl.get("failed_unsat"):
        ctl["done"] = True
        ctl["encoding_defect"] = True
    else:
        ctl["done"] = True
        ctl["fallback_plain_encoding"] = True
    ck["control"] = ctl
    save_ckpt(ck)
    write_result(f"exp056_control_{ts()}.json", ctl)
    return 0


def stageA_plain(ck, cone):
    """The predeclared C0 fallback: the plain EXP-033
    encoding, EXP-042 style, per-query 1,500 s."""
    state = ck["cones"][cone].setdefault("stageA_plain",
                                         {})
    if state.get("done"):
        return 0
    if not budget_allows(ck, 1500.0):
        state["done"] = True
        state["verdict"] = "no_budget"
        save_ckpt(ck)
        return 0
    orig = cs.synth_query

    def synth_timed(c, L, examples):
        return orig(c, L, examples, timeout_ms=1500000)

    cs.synth_query = synth_timed
    rng = random.Random(20261118)
    t0 = time.time()
    res = cs.cegis(cone, 5, rng)
    wall = time.time() - t0
    cs.synth_query = orig
    account(ck, wall, f"stageA plain {cone}")
    state["done"] = True
    state["verdict"] = res["verdict"]
    state["result"] = {k: v for k, v in res.items()
                        if k != "examples"}
    if res["verdict"] == "unsat_no_program":
        ck["cones"][cone]["closed"] = True
        ck["cones"][cone]["closed_by"] = "stageA_plain"
    if res["verdict"] == "program_found_and_proven":
        prog, _ = es.canonicalize_program(
            [tuple(p) for p in res["program"]],
            res["outputs"])
        handle_candidate(ck, cone, prog,
                          tuple(res["outputs"]),
                          "stageA_plain")
    save_ckpt(ck)
    write_result(f"exp056_stageA_plain_{cone}_{ts()}.json",
                 state)
    return 0


def do_stageA(ck, cone):
    if ck.get("sat_candidate"):
        print("campaign stopped: SAT candidate recorded",
              flush=True)
        return 0
    if ck["cones"][cone].get("closed"):
        print(f"{cone} already closed", flush=True)
        return 0
    if ck["control"].get("fallback_plain_encoding"):
        return stageA_plain(ck, cone)
    state = ck["cones"][cone].setdefault("stageA", {})
    if state.get("done"):
        print(f"stageA {cone} already done", flush=True)
        return 0
    target = cs.CONES[cone]["target"]
    examples = list(state.get("examples",
                              fresh_examples()))
    if not es.targets_pairwise_distinguished(target,
                                              examples):
        raise AssertionError("C3 condition fails on seed")
    iterations = state.get("iterations", [])
    for it in range(len(iterations), 3):
        if not budget_allows(ck, 1500.0):
            iterations.append({"iteration": it,
                                 "verdict": "no_budget"})
            break
        verdict, prog, outputs, wall = es.synth_query(
            target, 5, examples, 1500000, encoding="A")
        account(ck, wall,
                f"stageA {cone} iter {it}")
        rec = {"iteration": it, "verdict": verdict,
               "wall_s": round(wall, 1),
               "examples": len(examples)}
        iterations.append(rec)
        state["iterations"] = iterations
        state["examples"] = examples
        save_ckpt(ck)
        print(f"stageA {cone} iter {it}: {verdict}",
              flush=True)
        if verdict == "unsat":
            ck["cones"][cone]["closed"] = True
            ck["cones"][cone]["closed_by"] = "stageA"
            state["done"] = True
            save_ckpt(ck)
            break
        if verdict == "unknown":
            state["done"] = True
            save_ckpt(ck)
            break
        # sat: verify exactly.
        res, cex, vwall = es.verify_cone_candidate(
            cone, prog, outputs, timeout_ms=600000)
        account(ck, vwall, f"stageA {cone} verify")
        rec["verify_verdict"] = res
        if res == "unsat":
            handle_candidate(ck, cone, prog, outputs,
                             "stageA")
            state["done"] = True
            save_ckpt(ck)
            break
        if res == "sat":
            if cs.CONES[cone]["target"](cex) == \
                    es.run_program_canon(prog, outputs,
                                         cex):
                rec["verify_inconsistent"] = True
                state["done"] = True
                save_ckpt(ck)
                break
            examples.append(tuple(cex))
            state["examples"] = examples
            save_ckpt(ck)
            continue
        state["done"] = True
        save_ckpt(ck)
        break
    else:
        state["done"] = True
        save_ckpt(ck)
    write_result(f"exp056_stageA_{cone}_{ts()}.json",
                 ck["cones"][cone].get("stageA", {}))
    return 0


def do_stageB(ck, cone):
    if ck.get("sat_candidate"):
        print("campaign stopped: SAT candidate recorded",
              flush=True)
        return 0
    if ck["cones"][cone].get("closed"):
        print(f"{cone} already closed", flush=True)
        return 0
    target = cs.CONES[cone]["target"]
    examples = fresh_examples()
    if not es.targets_pairwise_distinguished(target,
                                              examples):
        raise AssertionError("C3 condition fails on seed")
    state = ck["cones"][cone].setdefault("stageB",
                                         {"profiles": {}})
    profiles = es.all_profiles()
    for idx, profile in enumerate(profiles):
        key = str(idx)
        if key in state["profiles"]:
            continue
        if ck["cones"][cone].get("closed") or \
                ck.get("sat_candidate"):
            break
        if not budget_allows(ck, 240.0):
            print("stageB: solver box exhausted at "
                  f"profile {idx}", flush=True)
            break
        verdict, prog, outputs, wall = es.synth_query(
            target, 5, examples, 240000, encoding="A",
            profile=profile)
        account(ck, wall,
                f"stageB {cone} profile {idx} {profile}")
        state["profiles"][key] = {
            "profile": profile, "verdict": verdict,
            "wall_s": round(wall, 1)}
        print(f"stageB {cone} profile {idx} {profile}: "
              f"{verdict}", flush=True)
        if verdict == "unsat":
            closed = state.setdefault("closed_profiles",
                                      [])
            closed.append(idx)
        elif verdict == "sat":
            save_ckpt(ck)
            res, cex, vwall = es.verify_cone_candidate(
                cone, prog, outputs, timeout_ms=600000)
            account(ck, vwall, f"stageB {cone} verify")
            state["profiles"][key]["verify_verdict"] = res
            if res == "unsat":
                handle_candidate(ck, cone, prog, outputs,
                                 f"stageB profile {idx}")
            else:
                state["profiles"][key][
                    "unproven_candidate"] = True
            save_ckpt(ck)
            if ck.get("sat_candidate"):
                break
        save_ckpt(ck)
    write_result(f"exp056_stageB_{cone}_{ts()}.json",
                 {"closed_profiles":
                      state.get("closed_profiles", []),
                  "profiles_done":
                      len(state.get("profiles", {}))})
    return 0


def do_stageC(ck):
    for cone in ("a_cone", "e_cone"):
        if ck.get("sat_candidate"):
            break
        if ck["cones"][cone].get("closed"):
            continue
        state = ck["cones"][cone].setdefault("stageC",
                                             {})
        if state.get("done"):
            continue
        remaining = SOLVER_BOX_S + SLACK_S - \
            ck["solver_wall_s"]
        cap_s = min(1200.0, remaining)
        if cap_s < 120.0:
            print("stageC: insufficient box remains",
                  flush=True)
            break
        target = cs.CONES[cone]["target"]
        examples = fresh_examples()
        verdict, prog, outputs, wall = es.synth_query(
            target, 5, examples, int(cap_s * 1000),
            encoding="B")
        account(ck, wall, f"stageC {cone} encoding B")
        state["done"] = True
        state["verdict"] = verdict
        state["wall_s"] = round(wall, 1)
        print(f"stageC {cone}: {verdict}", flush=True)
        if verdict == "unsat":
            ck["cones"][cone]["closed"] = True
            ck["cones"][cone]["closed_by"] = "stageC"
        elif verdict == "sat":
            save_ckpt(ck)
            handle_candidate(ck, cone, prog, outputs,
                             "stageC")
        save_ckpt(ck)
    return 0


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "status"
    ck = load_ckpt()
    if stage == "gates":
        return do_gates(ck)
    if stage == "control":
        return do_control(ck)
    if stage == "stageA":
        return do_stageA(ck, sys.argv[2])
    if stage == "stageB":
        return do_stageB(ck, sys.argv[2])
    if stage == "stageC":
        return do_stageC(ck)
    print(json.dumps(
        {"solver_wall_s": round(ck["solver_wall_s"], 1),
         "solver_box_s": SOLVER_BOX_S,
         "gates": ck["gates"],
         "control": {k: v for k, v in
                     ck["control"].items()
                     if k != "attempts"},
         "cones": ck["cones"],
         "sat_candidate": ck["sat_candidate"]},
        indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
