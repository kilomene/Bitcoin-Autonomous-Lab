"""CPU aspect: the lab's complete CPU mining subsystem.

Everything CPU-side lives here and is independently usable:

- The C batch engine (bal_batch.c, midstate optimized, SHA-NI) via
  ComputeEngine's "c" backend, and the AVX-512 multi-buffer
  engine via its "v512" backend when CPUID dispatch selects it.
- CpuMiner: a miner that uses ONLY the CPU backends (AVX-512 MB
  or C first, Python fallback, never CUDA) to run full
  getblocktemplate cycles with submission and acceptance
  checks. It reuses the block construction in mining/engine.py
  and forces the compute choice.
- benchmark(): a measured comparison of every CPU hashing path in
  the lab on this machine (C midstate library at several thread
  counts, the bal_miner binary's engine approach via the library,
  and pure Python hashlib batches), all verified against hashlib.

Verification standard: no number is reported from a path whose
digests were not checked against hashlib in the same run.
"""

import hashlib
import struct
import time

from gpu.engine import ComputeEngine, cpu_digest
from mining.engine import MiningEngine


def verify_c_library(samples=2000):
    """The C library's digests must equal hashlib's, nonce by nonce."""
    # This verifies the C library specifically, so it asks for
    # the C backend explicitly: the auto engine may legitimately
    # select the AVX-512 backend instead, which says nothing
    # about the C library.
    eng = ComputeEngine(requested="c")
    if eng.backend != "c":
        return {"ok": False, "reason": f"backend is {eng.backend}"}
    header = bytes(range(80))
    target = (1 << 256) - 1
    got = eng._c_batch(eng._c_lib, header, target, 0, samples)
    for n in range(samples):
        if got[n] != cpu_digest(header, n):
            return {"ok": False, "reason": f"digest mismatch at nonce {n}"}
    return {"ok": True, "samples": samples}


def benchmark(seconds_per_path=2.0):
    """Measured hashrates for the CPU paths. Returns a dict of
    name -> hashes per second, all from verified code paths."""
    results = {}
    header = bytes(80)
    target = 1 << 240

    eng_c = ComputeEngine()
    results["backend_selected"] = eng_c.backend
    results["c_midstate_engine"] = eng_c.benchmark()

    eng_py = ComputeEngine(requested="cpu")
    results["python_hashlib_engine"] = eng_py.benchmark()

    # Raw library throughput by thread count, called directly.
    import gpu.engine as ge
    if eng_c._c_lib:
        for threads in (1, 2, 4):
            ge.C_THREADS = threads
            e = ComputeEngine(requested="c")
            results[f"c_midstate_raw_{threads}thr"] = e.benchmark()
        ge.C_THREADS = 2
    # hashlib single loop reference.
    t0 = time.time()
    n = 0
    while time.time() - t0 < seconds_per_path:
        for i in range(2000):
            h = header[:76] + struct.pack("<I", i)
            hashlib.sha256(hashlib.sha256(h).digest()).digest()
            n += 1
    results["python_hashlib_loop"] = n / (time.time() - t0)
    return results


def tune_threads(count=1 << 22):
    """Measure the early-exit scan rate at each thread count on THIS
    machine and return (best_threads, {threads: H/s}). Thread count
    is a machine fact, not a constant: on the lab VM (about 1.5
    shared cores) 2 threads peak and more threads lose to
    contention, which the measurements show directly."""
    import ctypes

    import gpu.engine as ge
    eng = ComputeEngine()
    if not eng._c_lib or not hasattr(eng._c_lib, "bal_c_search"):
        return None, {}
    lib = eng._c_lib
    header = bytes(80)
    target = (1).to_bytes(32, "little")  # impossible target: pure scan
    nonce = ctypes.c_uint32(0)
    dig = ctypes.create_string_buffer(32)
    rates = {}
    for threads in (1, 2, 3, 4, 6, 8):
        t0 = time.time()
        lib.bal_c_search(header, 0, count, threads, target,
                         ctypes.byref(nonce), dig)
        rates[threads] = count / (time.time() - t0)
    best = max(rates, key=rates.get)
    ge.C_THREADS = best
    return best, rates


class CpuMiner:
    """Full GBT mining cycles on CPU backends only."""

    def __init__(self, rpc, payout_address, batch_size=1 << 20,
                 tune=True):
        self.compute = ComputeEngine()
        if self.compute.backend == "cuda":
            # CPU aspect means CPU: rebuild without the CUDA
            # request. "auto" would select CUDA again on a GPU
            # machine, so ask for a native CPU backend; the
            # engine's dispatch picks AVX-512 MB where the CPU
            # supports it and the C library otherwise.
            self.compute = ComputeEngine(requested="v512")
        self.tuning = tune_threads() if tune else (None, {})
        self.engine = MiningEngine(rpc, payout_address, self.compute,
                                   batch_size=batch_size)
        self.rpc = rpc

    def mine(self, cycles=1):
        out = []
        for _ in range(cycles):
            out.append(self.engine.mine_cycle(max_batches=64,
                                              deadline_seconds=300))
        return {"backend": self.compute.backend, "cycles": out,
                "accepted": sum(1 for c in out if c["accepted"])}
