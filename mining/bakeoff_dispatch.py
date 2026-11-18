"""Hardened bake-off dispatch input (EXP-052, register
R-23, portfolio NOVA-ER-0012).

The Milestone 4 advisory bake-off
(agent/intelligence/scheduler.py) measures every backend
tier through the real search path and picks the argmax
of medians. It ran live once and its winner margin was
0.8 percent, inside contention noise: an argmax with no
margin rule, no significance test and no doubt
semantics cannot be trusted as a production dispatch
input. This module is the hardened form:

- A decision rule stated in advance (research/sha256d/
  exp052/PREDECLARATION.md): an EXP-017-shaped protocol
  (3 sessions, paired 65,536-hash blocks through the
  production search path, randomised AB/BA order, the
  EXP-017 adjusted bootstrap statistic), and a
  challenger displaces the static dispatch order's
  pick only when its adjusted confidence interval
  clears a 5 percent margin in every session and
  pooled, with the control comparison (static pick
  against itself) certifying that the campaign could
  resolve 5 percent at all.
- A verdict cache keyed by a host fingerprint (CPU
  model, hash of the instruction flags, logical CPU
  count). A fingerprint mismatch voids the verdict:
  that is the re-run trigger on host change, and the
  fallback while no verdict exists for the new host
  is the static order.
- A resolver that returns a ComputeEngine requested
  value plus a reason, and returns "auto" (the static
  order, exactly today's behaviour) on ANY doubt:
  switch off, cache missing, corrupt, stale, schema
  or protocol mismatch, fingerprint mismatch,
  non-finite fields, a cached margin below the
  predeclared margin, an unknown winner, or a winner
  contradicted by the cache's own tier rows. The
  resolver never raises and never measures; dispatch
  never blocks startup on a benchmark.

The seam is mining/mainnet_live.py, which consults
resolve_requested only when the operator enabled the
"bakeoff" section of the endpoint config
(mining/endpoint_config.py, BAKEOFF_DEFAULTS, enabled
False by default). With the switch off this module is
never imported by the live path and nothing changes.

Measurement honesty rules, inherited from the
scheduler and EXP-031: engines are constructed per
tier with an explicit thread count through the
ComputeEngine constructor (Stage 7 instance scoping;
no shared state is set or restored), the engine's
returned attempted count is the authority for work
done and is asserted equal to the block size on every
counted call, rates are category E (complete
production search path), and every record carries the
host fingerprint and a contention note. The live
miner, autopilot and node run throughout; this module
never touches those processes.
"""

import hashlib
import json
import math
import os
import random
import time

_REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), ".."))
_LOCAL = os.path.join(_REPO_ROOT, ".local")

SCHEMA_VERSION = 1
PROTOCOL_ID = "exp052-bakeoff-v1"
PREDECLARED_MARGIN = 0.05
DEFAULT_MAX_AGE_S = 604_800.0
DEFAULT_CACHE_PATH = os.path.join(
    _LOCAL, "bakeoff-dispatch.json")

TIER_ORDER = ["cuda", "v512dual", "v512", "shani",
              "avx2", "c", "hashlib"]
# The backend each requested value denotes. "hashlib"
# denotes the engine's pure-Python tier, whose backend
# name is "cpu". A requested value is eligible on a
# host only when the engine it constructs reports the
# denoted backend; anything else means the tier is not
# really present and the value would silently measure
# a fallback.
DENOTED_BACKEND = {"cuda": "cuda", "v512dual": "v512dual",
                   "v512": "v512", "shani": "shani",
                   "avx2": "avx2", "c": "c",
                   "hashlib": "cpu"}

BENCH_HEADER = bytes(range(80))
BENCH_TARGET = 1
BLOCK_HASHES = 65_536
MEASURE_THREADS = 2
SESSIONS = 3
PAIRS_PER_SESSION = 150
BOOTSTRAP_RESAMPLES = 10_000


# Host fingerprint -------------------------------------------

def host_fingerprint():
    """CPU model, a hash of the sorted instruction
    flags, and the logical CPU count, from
    /proc/cpuinfo. The cache key for every verdict:
    any change voids cached verdicts by mismatch."""
    model = None
    flags = set()
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8",
                  errors="replace") as f:
            for line in f:
                if model is None and line.startswith(
                        "model name"):
                    model = line.split(":", 1)[1].strip()
                elif line.startswith("flags"):
                    flags = set(
                        line.split(":", 1)[1].split())
                    if model is not None:
                        break
    except OSError:
        pass
    digest = hashlib.sha256(
        " ".join(sorted(flags)).encode()).hexdigest()[:16]
    return {"cpu_model": model, "flags_hash": digest,
            "logical_cpus": os.cpu_count()}


# Environment covariates (EXP-017 / EXP-054 form) ------------

def _sample_env():
    with open("/proc/stat") as fh:
        fields = fh.readline().split()
    values = [int(x) for x in fields[1:]]
    with open("/proc/loadavg") as fh:
        load = fh.read().split()
    return {"cpu_total_jiffies": sum(values),
            "cpu_steal_jiffies": values[7],
            "load1": float(load[0]),
            "runnable": int(load[3].split("/")[0])}


def _env_interval(first, second):
    total_delta = (second["cpu_total_jiffies"]
                   - first["cpu_total_jiffies"])
    steal_delta = (second["cpu_steal_jiffies"]
                   - first["cpu_steal_jiffies"])
    return {
        "steal_fraction": (steal_delta / total_delta
                           if total_delta > 0 else 0.0),
        "runnable_mean": 0.5 * (first["runnable"]
                                + second["runnable"]),
        "load1_mean": 0.5 * (first["load1"]
                             + second["load1"])}


# Engine construction ------------------------------------------

def _default_engine_factory(requested, threads):
    from gpu.engine import ComputeEngine
    return ComputeEngine(requested=requested,
                         threads=threads)


def probe_tiers(engine_factory=None, threads=MEASURE_THREADS):
    """Construct one engine per requested tier and
    record eligibility by the denotation rule. A tier
    that faults during construction is recorded with
    its fault and excluded, never worked around.
    Returns (rows, engines) with engines keyed by tier
    for the eligible ones."""
    factory = engine_factory or _default_engine_factory
    rows = []
    engines = {}
    for tier in TIER_ORDER:
        try:
            engine = factory(tier, threads)
        except Exception as exc:
            rows.append({"tier": tier, "eligible": False,
                         "resolved_backend": None,
                         "fault": f"{type(exc).__name__}: "
                                  f"{exc}",
                         "correctness": None,
                         "median_rate_hs": None})
            continue
        resolved = getattr(engine, "backend", None)
        eligible = (resolved == DENOTED_BACKEND[tier])
        row = {"tier": tier, "eligible": eligible,
               "resolved_backend": resolved,
               "fault": None if eligible else
                        f"requested {tier!r} resolved to "
                        f"backend {resolved!r}, not the "
                        f"denoted {DENOTED_BACKEND[tier]!r}",
               "correctness": None, "median_rate_hs": None}
        if eligible:
            engines[tier] = engine
        rows.append(row)
    return rows, engines


def static_pick(engine_factory=None, threads=MEASURE_THREADS):
    """The static order's pick on this host: the
    requested value denoting the backend that
    requested "auto" resolves to. Returns
    (tier, backend) or (None, None) when even the
    auto construction fails (total probe failure)."""
    factory = engine_factory or _default_engine_factory
    try:
        engine = factory("auto", threads)
    except Exception:
        return None, None
    backend = getattr(engine, "backend", None)
    for tier in TIER_ORDER:
        if DENOTED_BACKEND[tier] == backend:
            return tier, backend
    return None, backend


# Paired measurement (EXP-017 protocol) ------------------------

def _counted_call(engine, block):
    """One counted block through the production search
    path, with covariates sampled around the call.
    Returns (rate_hs, env, attempted)."""
    first = _sample_env()
    t0 = time.perf_counter()
    _hit, attempted, _secs = engine.search_first_counted(
        BENCH_HEADER, BENCH_TARGET, 0, block)
    wall = time.perf_counter() - t0
    second = _sample_env()
    rate = attempted / wall if wall > 0 else 0.0
    return rate, _env_interval(first, second), attempted


def measure_session(engine_a, engine_b, pairs_count,
                    rng, block=BLOCK_HASHES):
    """One session of paired blocks: arm A is the
    static pick, arm B the challenger (for the control,
    a second instance of the static pick). Pair order
    randomised per pair. Pairs whose attempted count
    differs from the block size are voided and counted,
    never recorded. Returns the session dict in the
    EXP-017 analyzer's input shape."""
    pairs = []
    voided = 0
    for _ in range(pairs_count):
        b_first = rng.random() < 0.5
        if b_first:
            rate_b, env_b, att_b = _counted_call(
                engine_b, block)
            rate_a, env_a, att_a = _counted_call(
                engine_a, block)
        else:
            rate_a, env_a, att_a = _counted_call(
                engine_a, block)
            rate_b, env_b, att_b = _counted_call(
                engine_b, block)
        if att_a != block or att_b != block or \
                rate_a <= 0 or rate_b <= 0:
            voided += 1
            continue
        pairs.append({
            "a": {"rate_hs": rate_a, "env": env_a},
            "b": {"rate_hs": rate_b, "env": env_b},
            "b_first": b_first,
            "log_ratio_b_over_a": math.log(rate_b / rate_a)})
    return {"pairs": pairs, "voided_pairs": voided}


def seed_for(name):
    """Deterministic per-comparison seed (sha256 of the
    comparison name; never the salted built-in hash,
    the EXP-053 lesson)."""
    digest = hashlib.sha256(
        f"EXP-052:{name}".encode()).digest()
    return int.from_bytes(digest[:8], "little") % (2 ** 31)


# Decision rule (pure) ------------------------------------------

def decide(analysis, margin=PREDECLARED_MARGIN):
    """Apply the predeclared displacement rule to an
    analysis dict (per-comparison per-session and
    pooled adjusted CIs, plus the control's pooled
    adjusted CI). Pure function over plain data so the
    rule is testable on synthetic tables.

    A challenger qualifies iff the control pooled CI
    lies entirely within plus or minus log(1 + margin)
    (the campaign could resolve the margin) and the
    challenger's adjusted CI lower bound exceeds
    log(1 + margin) in every session and pooled. The
    winner is the qualifier with the highest pooled
    adjusted point estimate; no qualifier means the
    verdict is STATIC (winner None)."""
    bound = math.log(1.0 + margin)
    reasons = []
    control = analysis.get("control") or {}
    ctrl_ci = ((control.get("pooled") or {})
               .get("adjusted") or {}).get("ci95")
    control_ok = bool(ctrl_ci) and ctrl_ci[0] >= -bound \
        and ctrl_ci[1] <= bound
    if not control_ok:
        reasons.append(
            "control pooled adjusted CI "
            f"{ctrl_ci} not entirely within plus or "
            f"minus log(1 + margin) = {bound:.4f}: the "
            "campaign cannot resolve the margin, so no "
            "challenger can be certified")
    qualified = []
    for name, comp in sorted(
            (analysis.get("comparisons") or {}).items()):
        tier = comp.get("challenger")
        per = comp.get("per_session") or []
        pooled = (comp.get("pooled") or {}).get(
            "adjusted") or {}
        pooled_ci = pooled.get("ci95")
        session_ok = bool(per) and all(
            ((s.get("adjusted") or {}).get("ci95")
             or [None, None])[0] is not None
            and s["adjusted"]["ci95"][0] > bound
            for s in per)
        pooled_ok = bool(pooled_ci) and \
            pooled_ci[0] > bound
        if control_ok and session_ok and pooled_ok:
            qualified.append(
                (tier, pooled.get("mean_log_ratio")))
            reasons.append(
                f"{tier}: adjusted CI lower bound above "
                f"the margin in every session and pooled "
                f"(pooled {pooled_ci}); qualifies")
        else:
            reasons.append(
                f"{tier}: does not qualify (control_ok="
                f"{control_ok}, every-session={session_ok}"
                f", pooled={pooled_ok}, pooled CI "
                f"{pooled_ci})")
    winner = None
    if qualified:
        winner = max(qualified,
                     key=lambda item: item[1])[0]
    return {"winner": winner, "qualified":
            [t for t, _est in qualified],
            "control_ok": control_ok, "reasons": reasons}


# Verdict cache ---------------------------------------------------

_CACHE_KEYS = {"schema", "protocol", "campaign_id",
               "timestamp", "fingerprint", "static_pick",
               "winner", "margin", "tiers", "decision"}
_FINGERPRINT_KEYS = {"cpu_model", "flags_hash",
                     "logical_cpus"}


def build_cache_record(fingerprint, static_tier, winner,
                       tier_rows, decision,
                       campaign_id, margin=
                       PREDECLARED_MARGIN, timestamp=None):
    return {
        "schema": SCHEMA_VERSION, "protocol": PROTOCOL_ID,
        "campaign_id": campaign_id,
        "timestamp": (time.time() if timestamp is None
                      else timestamp),
        "fingerprint": dict(fingerprint),
        "static_pick": static_tier, "winner": winner,
        "margin": margin, "tiers": tier_rows,
        "decision": decision}


def write_cache(path, record):
    """Atomic write (tmp file plus os.replace), the
    scheduler cache pattern."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=1, sort_keys=True)
    os.replace(tmp, path)
    return path


def _reject_constant(value):
    raise ValueError(f"non-finite JSON constant {value}")


def _is_finite_number(value):
    return isinstance(value, (int, float)) and \
        not isinstance(value, bool) and \
        math.isfinite(value)


def validate_cache(data, fingerprint, now=None,
                   max_age_s=DEFAULT_MAX_AGE_S,
                   min_margin=PREDECLARED_MARGIN):
    """Strict validation of a cache record against the
    current host fingerprint. Returns (ok, reason,
    winner): winner is the certified requested value,
    or None for a valid STATIC verdict. Any failure is
    doubt: ok False with the reason."""
    if now is None:
        now = time.time()
    else:
        try:
            now = float(now)
        except (TypeError, ValueError):
            return False, (f"current time {now!r} is "
                           "not a number"), None
    if not isinstance(data, dict):
        return False, "cache is not a JSON object", None
    if set(data.keys()) != _CACHE_KEYS:
        return False, ("cache schema keys mismatch: "
                       f"{sorted(data.keys())}"), None
    if data["schema"] != SCHEMA_VERSION:
        return False, (f"cache schema version "
                       f"{data['schema']!r} != "
                       f"{SCHEMA_VERSION}"), None
    if data["protocol"] != PROTOCOL_ID:
        return False, (f"cache protocol "
                       f"{data['protocol']!r} != "
                       f"{PROTOCOL_ID!r}"), None
    if not isinstance(data["campaign_id"], str) or \
            not data["campaign_id"]:
        return False, "cache campaign_id invalid", None
    if not _is_finite_number(data["timestamp"]):
        return False, "cache timestamp not finite", None
    age = now - float(data["timestamp"])
    if age < -300.0:
        return False, "cache timestamp in the future", None
    if age > max_age_s:
        return False, (f"cache stale: age {age:.0f} s "
                       f"beyond max {max_age_s:.0f} s"), None
    try:
        current_fp = dict(fingerprint)
    except (TypeError, ValueError):
        return False, (f"current host fingerprint "
                       f"{fingerprint!r} is not a "
                       "mapping"), None
    fp = data["fingerprint"]
    if not isinstance(fp, dict) or \
            set(fp.keys()) != _FINGERPRINT_KEYS:
        return False, "cache fingerprint schema invalid", None
    if fp != current_fp:
        return False, ("host fingerprint mismatch "
                       "(host changed or cache foreign): "
                       f"cache {fp} vs current "
                       f"{current_fp}"), None
    if data["static_pick"] not in DENOTED_BACKEND:
        return False, (f"cache static_pick "
                       f"{data['static_pick']!r} unknown"), None
    winner = data["winner"]
    if winner is not None and winner not in DENOTED_BACKEND:
        return False, f"cache winner {winner!r} unknown", None
    if not _is_finite_number(data["margin"]):
        return False, "cache margin not finite", None
    if float(data["margin"]) < min_margin:
        return False, (f"cache margin "
                       f"{data['margin']} below the "
                       f"predeclared {min_margin}"), None
    tiers = data["tiers"]
    if not isinstance(tiers, list) or not tiers:
        return False, "cache tiers invalid", None
    for row in tiers:
        if not isinstance(row, dict) or \
                row.get("tier") not in DENOTED_BACKEND:
            return False, "cache tier row invalid", None
        rate = row.get("median_rate_hs")
        if rate is not None and not _is_finite_number(rate):
            return False, ("cache tier rate not finite "
                           f"for {row.get('tier')}"), None
    if winner is not None:
        winner_row = None
        for row in tiers:
            if row.get("tier") == winner:
                winner_row = row
                break
        if winner_row is None:
            return False, (f"cache winner {winner!r} "
                           "has no tier row"), None
        if winner_row.get("eligible") is not True:
            return False, (f"cache winner {winner!r} "
                           "is not eligible in its own "
                           "tier row"), None
        if winner_row.get("resolved_backend") != \
                DENOTED_BACKEND[winner]:
            return False, (f"cache winner {winner!r} "
                           "resolved to backend "
                           f"{winner_row.get('resolved_backend')!r} "
                           "in its tier row, not the "
                           "denoted "
                           f"{DENOTED_BACKEND[winner]!r}"), None
    if not isinstance(data["decision"], dict):
        return False, "cache decision invalid", None
    return True, "cache valid", winner


def read_cache(path, fingerprint, now=None,
               max_age_s=DEFAULT_MAX_AGE_S,
               min_margin=PREDECLARED_MARGIN):
    """Read and validate a cache file. Returns
    (ok, reason, winner). Never raises: every failure
    is doubt."""
    if not isinstance(path, (str, os.PathLike)):
        return False, (f"cache path {path!r} is not a "
                       "filesystem path"), None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f, parse_constant=
                             _reject_constant)
    except (OSError, ValueError) as exc:
        return False, f"cache unreadable: {exc}", None
    return validate_cache(data, fingerprint, now=now,
                          max_age_s=max_age_s,
                          min_margin=min_margin)


# Dispatch resolver ----------------------------------------------

def resolve_requested(bakeoff_cfg=None, cache_path=None,
                      fingerprint=None, now=None):
    """The dispatch seam's only question: which
    requested value should the production engine be
    constructed with? Returns (requested, reason).

    "auto" is the static order and is returned whenever
    anything is in doubt, with the reason saying why.
    With the switch disabled (the default) the cache
    is never read and the answer is exactly today's
    behaviour. Never raises, never measures."""
    try:
        cfg = dict(bakeoff_cfg or {})
    except (TypeError, ValueError):
        return "auto", ("doubt: bake-off configuration "
                        f"{bakeoff_cfg!r} is not a "
                        "mapping; static order")
    if not cfg.get("enabled", False):
        return "auto", ("disabled: bake-off dispatch is "
                        "off; static order (today's "
                        "behaviour)")
    path = cache_path or cfg.get("cache_path") or \
        DEFAULT_CACHE_PATH
    max_age = cfg.get("max_age_s", DEFAULT_MAX_AGE_S)
    try:
        max_age = float(max_age)
    except (TypeError, ValueError):
        return "auto", ("doubt: bake-off max_age_s "
                        f"{max_age!r} is not a number")
    if not math.isfinite(max_age) or max_age <= 0:
        return "auto", ("doubt: bake-off max_age_s "
                        f"{max_age!r} is not positive and "
                        "finite")
    margin = cfg.get("margin", PREDECLARED_MARGIN)
    try:
        margin = float(margin)
    except (TypeError, ValueError):
        return "auto", ("doubt: bake-off margin "
                        f"{margin!r} is not a number")
    if not math.isfinite(margin) or margin < 0:
        return "auto", ("doubt: bake-off margin "
                        f"{margin!r} is not finite and "
                        "non-negative")
    min_margin = max(PREDECLARED_MARGIN, margin)
    if fingerprint is not None:
        fp = fingerprint
    else:
        # DEF-9.2-1 (Stage 9 fixes batch, 2026-11-18): the
        # fingerprint resolution is guarded so a host where
        # host_fingerprint() raises resolves to the doubt
        # verdict instead of propagating an exception into
        # miner startup, keeping the resolver's documented
        # never-raises contract.
        try:
            fp = host_fingerprint()
        except Exception as exc:
            return "auto", ("doubt: host fingerprint "
                            f"unavailable ({exc}); "
                            "static order")
    ok, reason, winner = read_cache(
        path, fp, now=now, max_age_s=max_age,
        min_margin=min_margin)
    if not ok:
        return "auto", f"doubt: {reason}; static order"
    if winner is None:
        return "auto", ("static: the bake-off verdict "
                        "for this host confirms the "
                        "static order")
    return winner, (f"winner: bake-off verdict for this "
                    f"host selects {winner} (margin "
                    f"{PREDECLARED_MARGIN} cleared under "
                    f"{PROTOCOL_ID})")
