"""Reproducible GPU benchmark harness (Task 002, Phase 9).

Measurement discipline:
- Warmup batch first, then repeated measured batches; the report
  gives median and spread, never a single best run.
- End-to-end batch time uses a monotonic host clock
  (time.perf_counter inside ComputeEngine.batch_search).
- Rates follow the Task 003.8 accounting definitions: hashrate is
  ACTUAL backend hash computations per second (on the CUDA path,
  device_hashes per second, including overflow-recovery repeats),
  and unique coverage per second is reported separately as
  coverage_per_second. The two are never conflated.
- Kernel-only time comes from CUDA events and is reported ONLY when
  a batch actually executed on CUDA (stats carry kernel_ms). It is
  never mixed into or compared against end-to-end numbers.
- When no CUDA device exists, the harness still runs and reports
  the fallback backend's numbers, labelled as NOT GPU measurements.
  A CPU-versus-GPU comparison is produced only when a batch really
  executed on CUDA under equivalent work and boundaries; otherwise
  the comparison field says exactly why it is not comparable yet.
"""

import statistics
import time

from gpu.engine import ComputeEngine


def run_benchmark(batches=5, batch=65536, engine=None):
    eng = engine or ComputeEngine()
    header = bytes(80)
    target = (1 << 240)
    # Warmup (unmeasured).
    eng.batch_search(header, target, 0, batch)
    runs = []
    for _ in range(batches):
        t0 = time.perf_counter()
        cands, stats = eng.batch_search(header, target, 0, batch)
        wall = time.perf_counter() - t0
        runs.append({
            "backend": stats["backend"],
            "hashes": stats["hashes"],
            "backend_hashes": stats.get("backend_hashes",
                                        stats["hashes"]),
            "device_hashes": stats.get("device_hashes"),
            "unique_coverage": stats.get("unique_coverage", batch),
            "coverage_per_second": stats.get(
                "coverage_per_second", stats["hashrate"]),
            "researched_hashes": stats.get("researched_hashes", 0),
            "overflow_splits": stats.get("overflow_splits", 0),
            "candidate_count": stats.get("candidate_count",
                                         len(cands)),
            "seconds": stats["seconds"],
            "wall_seconds": wall,
            "hashrate": stats["hashrate"],
            "candidates": len(cands),
            "kernel_ms": stats.get("kernel_ms"),
            "fallback_events": stats.get("fallback_events", 0),
        })
    rates = [r["hashrate"] for r in runs]
    coverage_rates = [r["coverage_per_second"] for r in runs]
    executed_on_cuda = any(r["backend"] == "cuda" for r in runs)
    return {
        "backend": eng.backend,
        "requested": eng.requested,
        "device_count": eng.device_count,
        "cuda_fallback_reason": eng.cuda_fallback_reason,
        "batch": batch,
        "batches": batches,
        "measurement_scope": "end-to-end batch (monotonic host clock)",
        "kernel_timing": ("CUDA events" if executed_on_cuda
                          else "unavailable: no CUDA execution occurred"),
        "is_gpu_measurement": executed_on_cuda,
        "label": ("GPU end-to-end measurement" if executed_on_cuda
                  else "NOT a GPU measurement: fallback backend "
                       "executed the work"),
        "median_hashrate": statistics.median(rates),
        "min_hashrate": min(rates),
        "max_hashrate": max(rates),
        "hashrate_definition": (
            "actual backend hash computations per second "
            "(device_hashes per second on the CUDA path)"),
        "median_coverage_per_second": statistics.median(
            coverage_rates),
        "coverage_definition": (
            "unique nonce coverage per second, reported separately "
            "from actual hash computations"),
        "runs": runs,
        "cpu_vs_gpu_comparison": (
            "available in runs above (cuda batches) against a CPU "
            "engine run under the same batch and boundaries"
            if executed_on_cuda else
            "not comparable yet: no CUDA device executed any batch "
            "on this machine"),
    }


if __name__ == "__main__":
    import json
    import sys
    batches = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    print(json.dumps(run_benchmark(batches=batches), indent=2))
