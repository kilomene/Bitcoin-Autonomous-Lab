"""Adaptive CPU scheduler (Master Build Mandate sections
6.2, 6.3 and 14, Milestone 4).

Two historical designs motivate this module, both recorded in
research/master_build/HISTORICAL_OPPORTUNITY_REGISTER.md:

- R-23: a measured bake-off at startup. Benchmark every
  correctness-passing backend tier on the actual host, cache
  the winner, and fall back to the static dispatch order on
  any doubt.
- R-35: an offline benchmark through the REAL search path.
  Every measurement here runs ComputeEngine.search_first_
  counted against a fixed work unit (a fixed 80-byte header,
  target 1, a fixed nonce range), so a reported rate is a
  category E rate (complete production search), never a
  synthetic kernel figure and never mining.

Method, following the EXP-031 load probe precedent
(research/sha256d/exp031/tools/load_probe.py): the thread
count is passed through the ComputeEngine constructor on a
throwaway instance per (tier, thread count) pair (Stage 7:
the former gpu.engine module global C_THREADS is gone, so
no shared state is set or restored), the engine's returned
attempted count is the authority for work done, and the
rate is attempted hashes over wall time measured around
the call. Target 1 is met by a real digest
with probability about 2^-256, so the scan covers the full
range in practice; the attempted count is recorded either
way.

Honesty rules:

- Every result carries the host name, the CPU model, the
  workload size, the category label, and a contention note.
  The live miner, autopilot and node run on this host
  throughout; measurements are taken alongside that load and
  say so. This module never touches those processes.
- A tier that faults during measurement is recorded with its
  fault and excluded from the winner decision, never worked
  around silently.
- The effective-CPU figure is an ESTIMATE from a scaling
  ratio, labelled with its method. It is not a core count.
- The bake-off cache is keyed by CPU model plus a hash of
  the instruction flags, with a timestamp. A cached result
  is returned only when the caller asks for cached behaviour
  and the entry is younger than the caller's maximum age.
"""

import hashlib
import json
import os
import socket
import statistics
import time

_REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".."))
_LOCAL = os.path.join(_REPO_ROOT, ".local")

WORKLOAD_HASHES = 1 << 18
REPETITIONS = 3
BAKEOFF_THREADS = 2
CATEGORY = ("E: complete production search path "
            "(ComputeEngine.search_first_counted)")
# (pin name for the facade interface, ComputeEngine requested
# value) in shipped dispatch order, EXP-039.
TIERS = [("cuda", "cuda"), ("v512dual", "v512dual"),
         ("v512", "v512"), ("shani", "shani"),
         ("avx2", "avx2"), ("c", "c"), ("hashlib", "hashlib")]
TIER_LABEL = {"cuda": "CUDA", "v512dual": "v512dual",
              "v512": "v512", "shani": "shani", "avx2": "avx2",
              "c": "C", "hashlib": "hashlib"}
BENCH_HEADER = bytes(range(80))
BENCH_TARGET = 1


def pick_winner(table):
    """The winning tier of a bake-off table: the eligible,
    non-faulted tier with the highest median rate. Pure
    function over {tier: median_rate} so the ordering logic
    is testable on synthetic tables. None when empty."""
    if not table:
        return None
    return max(sorted(table), key=lambda t: table[t])


class Scheduler:
    """Measured backend selection and thread configuration.

    agent: the agent.intelligence.Agent facade (machine and
    backend inspection and permissions come from Milestone
    1). cache_path: injectable; default
    .local/agent-scheduler.json. engine_factory:
    callable(requested) returning a ComputeEngine; default
    is the facade interface's factory.
    """

    def __init__(self, agent, cache_path=None,
                 engine_factory=None):
        self.agent = agent
        self.cache_path = cache_path or os.path.join(
            agent.local_dir, "agent-scheduler.json")
        self.engine_factory = engine_factory or \
            agent.interface.engine_factory
        self._engines = {}
        self._measure_engines = {}
        self._profile = None

    # Internals --------------------------------------------------
    def _engine(self, requested):
        if requested not in self._engines:
            self._engines[requested] = self.engine_factory(
                requested)
        return self._engines[requested]

    def _contention_note(self):
        status = self.agent.interface.inspect_status()
        if status.running:
            return ("live miner running on this host during "
                    "measurement (miner pid "
                    f"{status.miner_pid}); rates are contended "
                    "figures alongside production load")
        return ("autopilot heartbeat does not report a "
                "running miner; rates measured without that "
                "load")

    def _context(self):
        machine = self.agent.interface.inspect_machine()
        return {"host": socket.gethostname(),
                "cpu_model": machine.model_name,
                "logical_cpus": machine.logical_cpus,
                "flags": list(machine.flags),
                "contention": self._contention_note(),
                "category": CATEGORY,
                "workload_hashes": WORKLOAD_HASHES}

    def _engine_at_threads(self, requested, threads):
        """A ComputeEngine for one (tier, thread count) pair,
        cached per pair. The thread count goes through the
        factory as a constructor argument when the factory
        accepts one (the production factory does); a factory
        that only accepts the tier gets an instance whose own
        c_threads attribute is set instead. Either way the
        count lives on that instance alone: nothing shared is
        set or restored."""
        key = (requested, threads)
        if key not in self._measure_engines:
            import inspect
            factory = self.engine_factory
            try:
                params = inspect.signature(factory).parameters
                accepts = ("threads" in params or any(
                    p.kind == inspect.Parameter.VAR_KEYWORD
                    for p in params.values()))
            except (TypeError, ValueError):
                accepts = False
            if accepts:
                engine = factory(requested, threads=threads)
            else:
                engine = factory(requested)
                engine.c_threads = threads
                engine.c_threads_tuned = True
            self._measure_engines[key] = engine
        return self._measure_engines[key]

    def _measure(self, requested, threads, repetitions,
                 count):
        """Median rate of the real search path for one tier
        at one thread count. Returns (median_rate, runs) with
        each run's attempted count and wall time recorded."""
        engine = self._engine_at_threads(requested, threads)
        runs = []
        for _ in range(repetitions):
            t0 = time.perf_counter()
            _hit, attempted, _secs = \
                engine.search_first_counted(
                    BENCH_HEADER, BENCH_TARGET, 0, count)
            wall = time.perf_counter() - t0
            runs.append({
                "attempted": attempted,
                "wall_s": round(wall, 4),
                "rate_hs": (attempted / wall
                            if wall > 0 else 0.0)})
        rates = [r["rate_hs"] for r in runs]
        return statistics.median(rates), runs

    # Machine profile --------------------------------------------
    def machine_profile(self):
        """Milestone 1 inspect_machine plus an effective-CPU
        probe: the fixed workload through the production
        auto-dispatch engine at 1 and 2 threads, medians of
        3 repetitions each. The scaling ratio (2-thread rate
        over 1-thread rate) is reported as the effective-CPU
        evidence: an estimate with its method stated, in the
        EXP-031 sense (this guest claims 4 vCPUs and delivers
        about 2 effective CPUs)."""
        if self._profile is not None:
            return self._profile
        self.agent.checker.require("run_benchmark")
        ctx = self._context()
        machine = self.agent.interface.inspect_machine()
        rate1, runs1 = self._measure(
            "auto", 1, REPETITIONS, WORKLOAD_HASHES)
        rate2, runs2 = self._measure(
            "auto", 2, REPETITIONS, WORKLOAD_HASHES)
        ratio = (rate2 / rate1) if rate1 > 0 else None
        self._profile = {
            "host": ctx["host"],
            "cpu_model": machine.model_name,
            "logical_cpus": machine.logical_cpus,
            "flags": list(machine.flags),
            "has_sha_ni": machine.has_sha_ni,
            "has_avx2": machine.has_avx2,
            "has_avx512f": machine.has_avx512f,
            "cgroup_cpu_max": machine.cgroup_cpu_max,
            "contention": ctx["contention"],
            "category": CATEGORY,
            "workload_hashes": WORKLOAD_HASHES,
            "probe_backend": getattr(
                self._engine("auto"), "backend", None),
            "rate_1_thread_hs": rate1,
            "rate_2_threads_hs": rate2,
            "runs_1_thread": runs1,
            "runs_2_threads": runs2,
            "effective_cpus_estimate": ratio,
            "effective_cpus_method": (
                "estimate: median 2-thread search rate "
                "divided by median 1-thread search rate over "
                f"{WORKLOAD_HASHES} hashes x {REPETITIONS} "
                "repetitions through the production search "
                "path; a scaling ratio, not a core count"),
        }
        return self._profile

    # Bake-off -----------------------------------------------------
    def _cache_key(self, machine):
        flags = " ".join(sorted(machine.flags))
        digest = hashlib.sha256(flags.encode()).hexdigest()[:16]
        return f"{machine.model_name}|{digest}"

    def _read_cache(self):
        try:
            with open(self.cache_path, "r",
                      encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def _write_cache(self, key, machine, result):
        entry = {"key": key, "cpu_model": machine.model_name,
                 "flags_hash": key.rsplit("|", 1)[-1],
                 "timestamp": time.time(),
                 "bake_off": result}
        parent = os.path.dirname(os.path.abspath(
            self.cache_path))
        os.makedirs(parent, exist_ok=True)
        tmp = self.cache_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=1, sort_keys=True)
        os.replace(tmp, self.cache_path)
        return entry

    def bake_off(self, use_cache=False, max_age_s=None):
        """Measure every eligible tier and pick the winner
        (design R-23). Ineligible tiers are skipped with the
        Milestone 1 eligibility reason recorded. With
        use_cache and a caller-supplied max_age_s, a cache
        entry for this host younger than the maximum age is
        returned instead of re-measuring."""
        self.agent.checker.require("run_benchmark")
        machine = self.agent.interface.inspect_machine()
        key = self._cache_key(machine)
        if use_cache and max_age_s is not None:
            cached = self._read_cache()
            if cached and cached.get("key") == key:
                age = time.time() - float(
                    cached.get("timestamp") or 0)
                if age < max_age_s:
                    result = dict(cached["bake_off"])
                    result["from_cache"] = True
                    result["cache_age_s"] = round(age, 1)
                    return result
        # Load-shedding gate (Stage 7): a bake-off is
        # discretionary measurement work. Serving a fresh
        # cache entry (above) costs nothing and stays
        # allowed; actually measuring is refused in Brownout
        # and Critical modes.
        modes = getattr(self.agent, "modes", None)
        if modes is not None:
            modes.require_allowed(
                "bake_off",
                detail="bake_off measurement refused by the "
                       "load-shedding mode")
        ctx = self._context()
        rows = []
        table = {}
        for pin, requested in TIERS:
            label = TIER_LABEL[pin]
            selection = self.agent.interface.select_backend(
                pin)
            if not selection.eligible:
                rows.append({"tier": label, "eligible": False,
                             "reason": selection.note,
                             "selected_instead":
                                 selection.selected})
                continue
            try:
                median, runs = self._measure(
                    requested, BAKEOFF_THREADS, REPETITIONS,
                    WORKLOAD_HASHES)
            except Exception as exc:
                rows.append({"tier": label, "eligible": True,
                             "fault": f"{type(exc).__name__}: "
                                      f"{exc}"})
                continue
            table[label] = median
            rows.append({"tier": label, "eligible": True,
                         "median_rate_hs": median,
                         "runs": runs})
        winner = pick_winner(table)
        result = {
            "host": ctx["host"], "cpu_model": ctx["cpu_model"],
            "logical_cpus": ctx["logical_cpus"],
            "contention": ctx["contention"],
            "category": CATEGORY,
            "workload_hashes": WORKLOAD_HASHES,
            "threads": BAKEOFF_THREADS,
            "repetitions": REPETITIONS,
            "rows": rows, "winner": winner,
            "winner_rate_hs": table.get(winner),
            "from_cache": False,
            "measured_at": time.time(),
        }
        self._write_cache(key, machine, result)
        self.agent.audit.record(
            "run_benchmark", 2, {"kind": "bake_off"},
            f"winner_{winner}")
        return result

    # Thread sweep -------------------------------------------------
    def thread_sweep(self, tier=None, threads=(1, 2, 4)):
        """Measure one tier at several thread counts with the
        same workload shape and return the table plus the
        argmax recommendation. Defaults to the bake-off
        winner (served from the cache when fresh entries are
        allowed by the caller through bake_off arguments;
        here a fresh cached winner is reused when present)."""
        self.agent.checker.require("run_benchmark")
        if tier is None:
            cached = self._read_cache()
            machine = self.agent.interface.inspect_machine()
            if cached and cached.get("key") == \
                    self._cache_key(machine) and \
                    cached.get("bake_off", {}).get("winner"):
                tier = cached["bake_off"]["winner"]
            else:
                tier = self.bake_off()["winner"]
        req = {TIER_LABEL[p]: r for p, r in TIERS}[tier]
        ctx = self._context()
        rows = []
        table = {}
        fault = None
        for n in threads:
            try:
                median, runs = self._measure(
                    req, n, REPETITIONS, WORKLOAD_HASHES)
            except Exception as exc:
                fault = f"{type(exc).__name__}: {exc}"
                rows.append({"threads": n, "fault": fault})
                continue
            table[n] = median
            rows.append({"threads": n,
                         "median_rate_hs": median,
                         "runs": runs})
        best = pick_winner({str(k): v for k, v in table.items()})
        result = {
            "host": ctx["host"], "cpu_model": ctx["cpu_model"],
            "contention": ctx["contention"],
            "category": CATEGORY,
            "workload_hashes": WORKLOAD_HASHES,
            "repetitions": REPETITIONS,
            "tier": tier, "rows": rows,
            "recommended_threads": (int(best)
                                    if best is not None else None),
            "recommended_rate_hs": (table.get(int(best))
                                    if best is not None
                                    else None),
            "fault": fault,
        }
        self.agent.audit.record(
            "run_benchmark", 2,
            {"kind": "thread_sweep", "tier": tier},
            f"threads_{result['recommended_threads']}")
        return result
