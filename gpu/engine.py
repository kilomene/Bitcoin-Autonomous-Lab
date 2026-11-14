"""ComputeEngine: batch SHA256d nonce search with backend dispatch.

Backends:
- cuda: the compiled gpu/cuda/engine.cu library, used only when it
  loads, reports at least one device, and passes a self-test batch
  whose results are re-verified on the CPU.
- cpu: hashlib batch search (this machine also has the C SHA-NI
  engine in mining/cpu for the Stratum path).

Every candidate from any backend is re-verified on the CPU before it
is returned. A CUDA failure at any point falls back to CPU and the
reason is recorded on the engine (fallback_reason). Nothing about the
GPU is ever claimed from compilation alone: backend selection is a
runtime measurement.
"""

import ctypes
import hashlib
import os
import time

MAX_BATCH = 1 << 20
NONCE_SPACE = 1 << 32

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB_PATH = os.path.join(ROOT, ".local", "cuda", "libbal_cuda.so")
C_LIB_PATH = os.path.join(ROOT, ".local", "cpu", "libbal_batch.so")
import os as _os
# Full-workforce thread count for the C search. An explicit
# BAL_C_THREADS always wins. Otherwise the engine measures the
# machine it is running on once (tune_c_threads below) and runs
# at that machine's own measured peak: every agent's box is
# different, and full workforce means the maximum of the machine
# under the miner, not a number copied from another agent's VM.
_C_THREADS_ENV = _os.environ.get("BAL_C_THREADS")
C_THREADS = int(_C_THREADS_ENV) if _C_THREADS_ENV else 2
C_THREADS_TUNED = _C_THREADS_ENV is not None
LAST_PROBE_RATE = 0.0  # H/s measured by the last auto-tune probe


def tune_c_threads(engine):
    """Measure this machine and set C_THREADS to its peak.

    Probes several thread counts with the real C search over a
    fixed nonce range and keeps the fastest. Runs once per
    process; any failure leaves the safe default in place.
    """
    global C_THREADS, C_THREADS_TUNED, LAST_PROBE_RATE
    if C_THREADS_TUNED:
        return C_THREADS
    C_THREADS_TUNED = True
    if getattr(engine, "backend", None) != "c" or not hasattr(
            engine._c_lib, "bal_c_search"):
        return C_THREADS
    try:
        header = bytes(range(80))
        target_le = (1).to_bytes(32, "little")
        probe = 1 << 20
        cpus = os.cpu_count() or 2
        best_n, best_rate = C_THREADS, 0.0
        for n in sorted({1, 2, 4, cpus, cpus * 2}):
            if n < 1 or n > 32:
                continue
            out_nonce = ctypes.c_uint32(0)
            out_digest = ctypes.create_string_buffer(32)
            t0 = time.time()
            rc = engine._c_lib.bal_c_search(
                header, 0, probe, n, target_le,
                ctypes.byref(out_nonce), out_digest)
            dt = time.time() - t0
            if rc in (0, 1) and dt > 0 and probe / dt > best_rate:
                best_n, best_rate = n, probe / dt
        C_THREADS = best_n
        LAST_PROBE_RATE = best_rate
        print(f"full-workforce: C search threads auto-tuned to "
              f"{best_n} on this machine "
              f"(probe {best_rate:,.0f} H/s)", flush=True)
    except Exception:
        pass
    return C_THREADS


def cpu_digest(header, nonce):
    h = header[:76] + nonce.to_bytes(4, "little")
    return hashlib.sha256(hashlib.sha256(h).digest()).digest()


def verify_candidate(header, target, nonce, digest):
    """Independent CPU authority for any backend's candidate."""
    if len(header) != 80 or len(digest) != 32:
        return False
    if cpu_digest(header, nonce) != digest:
        return False
    return int.from_bytes(digest, "little") <= target


class CudaContext:
    """Persistent CUDA execution context (Task 002 production path).

    Buffers live on the device across batches; a production search
    uploads work once per header (midstate, tail, target), then each
    batch returns only candidate records. Overflow of the bounded
    candidate array raises: a truncated candidate list is never
    presented as a complete search.
    """

    CAND_CAP = 4096

    def __init__(self, lib, max_count=MAX_BATCH):
        self._lib = lib
        self._ctx = None
        self._work_key = None
        lib.bal_cuda_ctx_create.restype = ctypes.c_int
        lib.bal_cuda_ctx_create.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p)]
        lib.bal_cuda_ctx_destroy.restype = ctypes.c_int
        lib.bal_cuda_ctx_destroy.argtypes = [ctypes.c_void_p]
        lib.bal_cuda_ctx_set_work.restype = ctypes.c_int
        lib.bal_cuda_ctx_set_work.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        lib.bal_cuda_ctx_search.restype = ctypes.c_int
        lib.bal_cuda_ctx_search.argtypes = [
            ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32,
            ctypes.c_uint, ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_float)]
        lib.bal_cuda_ctx_batch_diag.restype = ctypes.c_int
        lib.bal_cuda_ctx_batch_diag.argtypes = [
            ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32,
            ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
            ctypes.c_char_p, ctypes.c_char_p]
        handle = ctypes.c_void_p()
        rc = lib.bal_cuda_ctx_create(max_count, self.CAND_CAP,
                                     ctypes.byref(handle))
        if rc != 0 or not handle.value:
            raise RuntimeError(f"bal_cuda_ctx_create failed: {rc}")
        self._ctx = handle

    def close(self):
        if self._ctx:
            rc = self._lib.bal_cuda_ctx_destroy(self._ctx)
            self._ctx = None
            if rc != 0:
                raise RuntimeError(f"bal_cuda_ctx_destroy failed: {rc}")

    def set_work(self, header, target):
        key = (header, target)
        if self._work_key == key:
            return
        rc = self._lib.bal_cuda_ctx_set_work(
            self._ctx, header, target.to_bytes(32, "little"))
        if rc != 0:
            raise RuntimeError(f"bal_cuda_ctx_set_work failed: {rc}")
        self._work_key = key

    def search(self, header, target, start, count, threads=256):
        """Returns (candidates, info). candidates are raw
        (nonce, digest) pairs, NOT yet CPU verified."""
        self.set_work(header, target)
        out_count = ctypes.c_uint32(0)
        out_ovf = ctypes.c_uint32(0)
        kernel_ms = ctypes.c_float(0.0)
        nonces = (ctypes.c_uint32 * self.CAND_CAP)()
        digests = ctypes.create_string_buffer(32 * self.CAND_CAP)
        rc = self._lib.bal_cuda_ctx_search(
            self._ctx, start, count, threads,
            ctypes.byref(out_count), ctypes.byref(out_ovf),
            nonces, digests, ctypes.byref(kernel_ms))
        if rc != 0:
            raise RuntimeError(f"bal_cuda_ctx_search failed: {rc}")
        if out_ovf.value:
            raise RuntimeError(
                f"candidate buffer overflow: {out_count.value} "
                f"candidates exceeded capacity {self.CAND_CAP} for "
                f"range start={start} count={count}; result would "
                f"be truncated and is refused")
        raw = digests.raw
        cands = [(nonces[i], raw[32 * i:32 * i + 32])
                 for i in range(out_count.value)]
        return cands, {"kernel_ms": kernel_ms.value,
                       "candidates_found": out_count.value}

    def batch_diag(self, header, target, start, count, threads=128):
        """Diagnostic mode: every digest, for self-tests only."""
        hashes = ctypes.create_string_buffer(32 * count)
        flags = ctypes.create_string_buffer(count)
        rc = self._lib.bal_cuda_ctx_batch_diag(
            self._ctx, start, count, threads, header,
            target.to_bytes(32, "little"), hashes, flags)
        if rc != 0:
            return None
        raw = hashes.raw
        return [raw[32 * i:32 * i + 32] for i in range(count)]


class ComputeEngine:
    def __init__(self, lib_path=LIB_PATH, requested="auto",
                 c_lib_path=C_LIB_PATH):
        self.requested = requested
        self.backend = "cpu"
        self.fallback_reason = None
        self.device_count = 0
        self._lib = None
        self._c_lib = None
        self._cuda_ctx = None
        self.cuda_ctx_reason = None
        self.cuda_fallback_reason = None
        self.fallback_events = []
        self.last_search_stats = None
        if requested in ("auto", "cuda", "cuda-only"):
            self._try_cuda(lib_path)
            self.cuda_fallback_reason = self.fallback_reason
        if self.backend != "cuda" and requested in ("auto", "c"):
            self._try_c(c_lib_path)
        if requested == "cuda-only" and self.backend != "cuda":
            raise RuntimeError(
                "CUDA-only mode requested but CUDA cannot execute: "
                f"{self.cuda_fallback_reason or self.fallback_reason}")
        if self.backend == "cuda":
            self.fallback_reason = None
        elif self.backend == "c":
            self.fallback_reason = self.cuda_fallback_reason
        if requested == "cuda" and self.backend != "cuda":
            self.fallback_reason = self.fallback_reason or "CUDA requested but unavailable"
        if self.backend == "c":
            tune_c_threads(self)

    def _try_c(self, c_lib_path):
        if not os.path.isfile(c_lib_path):
            return
        try:
            lib = ctypes.CDLL(c_lib_path)
        except OSError:
            return
        lib.bal_c_batch.restype = ctypes.c_int
        lib.bal_c_batch.argtypes = [
            ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint32,
            ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
            ctypes.c_char_p]
        if hasattr(lib, "bal_c_search"):
            lib.bal_c_search.restype = ctypes.c_int
            lib.bal_c_search.argtypes = [
                ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint32,
                ctypes.c_uint, ctypes.c_char_p,
                ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p]
        if hasattr(lib, "bal_c_search2"):
            lib.bal_c_search2.restype = ctypes.c_int
            lib.bal_c_search2.argtypes = [
                ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                ctypes.c_uint, ctypes.c_char_p,
                ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
                ctypes.POINTER(ctypes.c_uint64)]
        if hasattr(lib, "bal_c_batch2"):
            lib.bal_c_batch2.restype = ctypes.c_int
            lib.bal_c_batch2.argtypes = [
                ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
                ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)]
        header = bytes(range(80))
        got = self._c_batch(lib, header, 1 << 255, 0, 256)
        if got is None:
            return
        for nonce in range(256):
            if got[nonce] != cpu_digest(header, nonce):
                return
        self._c_lib = lib
        self.backend = "c"

    def _c_batch(self, lib, header, target, start, count):
        pairs = self._c_batch_flagged(lib, header, target, start, count,
                                      want_all=True)
        if pairs is None:
            return None
        digests = [b""] * count
        for nonce, digest in pairs:
            digests[nonce - start] = digest
        return digests

    def _c_batch_flagged(self, lib, header, target, start, count,
                         want_all=False):
        """Run a C batch and return only the flagged (nonce, digest)
        pairs, located through the C flags array at C speed. This is
        the production path: Python never rescans every digest."""
        hashes = ctypes.create_string_buffer(32 * count)
        flags = ctypes.create_string_buffer(count)
        target_le = target.to_bytes(32, "little")
        rc = lib.bal_c_batch(header, start, count, C_THREADS, target_le,
                             hashes, flags)
        if rc != 0:
            return None
        raw = hashes.raw
        flag_bytes = flags.raw
        if want_all:
            return [(start + i, raw[32 * i:32 * i + 32])
                    for i in range(count)]
        out = []
        pos = 0
        while True:
            i = flag_bytes.find(b"\x01", pos)
            if i < 0:
                break
            out.append((start + i, raw[32 * i:32 * i + 32]))
            pos = i + 1
        return out

    def search_first(self, header, target, start, count):
        """Early-exit search: returns (nonce, digest) or None.
        Thin wrapper over search_first_counted for callers that do
        not need the actual attempt count."""
        hit, _attempted, _seconds = self.search_first_counted(
            header, target, start, count)
        return hit

    def search_first_counted(self, header, target, start, count):
        """Early-exit search that reports ACTUAL work.

        Returns (hit, attempted, seconds) where hit is
        (nonce, digest) or None, attempted is the number of hash
        attempts actually completed (reported per worker by the
        native library through bal_c_search2; on an early exit it
        is usually far below the requested range size), and
        seconds is measured on a monotonic clock. The result is
        also recorded on self.last_search_stats together with the
        backend, thread count and requested range, so callers can
        account and report honestly. The fallback batch path scans
        the full range by construction, so its attempted count is
        exactly the range size."""
        if len(header) != 80 or not (1 <= target < (1 << 256)):
            raise ValueError("bad header or target")
        if not (0 <= start and 0 < count and start + count <= NONCE_SPACE):
            raise ValueError("nonce range out of bounds")
        t0 = time.perf_counter()
        hit = None
        attempted = count  # batch fallback scans everything
        backend_used = self.backend
        if self.backend == "c" and hasattr(self._c_lib, "bal_c_search2"):
            out_nonce = ctypes.c_uint32(0)
            out_attempted = ctypes.c_uint64(0)
            out_digest = ctypes.create_string_buffer(32)
            target_le = target.to_bytes(32, "little")
            rc = self._c_lib.bal_c_search2(
                header, start, count, C_THREADS, target_le,
                ctypes.byref(out_nonce), out_digest,
                ctypes.byref(out_attempted))
            attempted = out_attempted.value
            if rc == 1:
                nonce = out_nonce.value
                digest = out_digest.raw
                if verify_candidate(header, target, nonce, digest):
                    hit = (nonce, digest)
                # else: C said hit but CPU disagrees: trust CPU,
                # hit stays None and the attempts still count.
            elif rc == 0:
                hit = None
            else:
                raise RuntimeError(f"bal_c_search2 returned {rc}")
        elif self.backend == "c" and hasattr(self._c_lib, "bal_c_search"):
            # Legacy library without attempt reporting: the count
            # is not measurable, so report the range size and mark
            # the stat as an upper bound via counted=False.
            out_nonce = ctypes.c_uint32(0)
            out_digest = ctypes.create_string_buffer(32)
            target_le = target.to_bytes(32, "little")
            rc = self._c_lib.bal_c_search(header, start, count,
                                          C_THREADS, target_le,
                                          ctypes.byref(out_nonce),
                                          out_digest)
            if rc == 1:
                nonce = out_nonce.value
                digest = out_digest.raw
                if verify_candidate(header, target, nonce, digest):
                    hit = (nonce, digest)
            self.last_search_stats = {
                "backend": backend_used, "threads": C_THREADS,
                "start": start, "requested": count,
                "attempted": attempted, "counted": False,
                "seconds": time.perf_counter() - t0, "hit": bool(hit)}
            return hit, attempted, self.last_search_stats["seconds"]
        else:
            cands, _stats = self.batch_search(header, target, start, count)
            backend_used = _stats["backend"]
            if cands:
                hit = (cands[0]["nonce"],
                       bytes.fromhex(cands[0]["hash"])[::-1])
        seconds = time.perf_counter() - t0
        self.last_search_stats = {
            "backend": backend_used,
            "threads": C_THREADS if backend_used == "c" else 1,
            "start": start, "requested": count, "attempted": attempted,
            "counted": True, "seconds": seconds, "hit": bool(hit),
            "hashrate": attempted / seconds if seconds > 0 else 0.0}
        return hit, attempted, seconds

    def _try_cuda(self, lib_path):
        if not os.path.isfile(lib_path):
            self.fallback_reason = f"CUDA library not built ({lib_path})"
            return
        try:
            lib = ctypes.CDLL(lib_path)
        except OSError as exc:
            self.fallback_reason = f"CUDA library failed to load: {exc}"
            return
        lib.bal_cuda_device_count.restype = ctypes.c_int
        try:
            n = lib.bal_cuda_device_count()
        except Exception as exc:  # ctypes call itself failed
            self.fallback_reason = f"CUDA device query failed: {exc}"
            return
        if n < 0:
            self.fallback_reason = (f"CUDA runtime error {-n} "
                                    f"(no usable NVIDIA device/driver)")
            return
        if n == 0:
            self.fallback_reason = "CUDA reports zero devices"
            return
        lib.bal_cuda_batch.restype = ctypes.c_int
        lib.bal_cuda_batch.argtypes = [
            ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint32,
            ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
            ctypes.c_char_p]
        # Self-test: one small batch must match the CPU exactly.
        header = bytes(range(80))
        target = (1 << 255)
        got = self._cuda_batch(lib, header, target, 0, 256)
        if got is None:
            self.fallback_reason = "CUDA self-test batch failed"
            return
        for nonce in range(256):
            if got[nonce] != cpu_digest(header, nonce):
                self.fallback_reason = "CUDA self-test digest mismatch"
                return
        self._lib = lib
        self.device_count = n
        self.backend = "cuda"
        self.fallback_reason = None
        # Persistent context: verified separately through the
        # diagnostic path (midstate kernel) against the CPU. If it
        # cannot be created or verified, the legacy batch path stays
        # in use and the reason is recorded; CUDA is never claimed
        # from the context's mere existence.
        if hasattr(lib, "bal_cuda_ctx_create"):
            try:
                ctx = CudaContext(lib)
                diag = ctx.batch_diag(header, target, 0, 256)
                if diag is None or any(
                        diag[i] != cpu_digest(header, i)
                        for i in range(256)):
                    ctx.close()
                    self.cuda_ctx_reason = ("persistent context "
                                            "diagnostic mismatch")
                else:
                    self._cuda_ctx = ctx
            except Exception as exc:
                self.cuda_ctx_reason = f"persistent context failed: {exc}"
        else:
            self.cuda_ctx_reason = "library has no persistent context ABI"

    def _cuda_batch(self, lib, header, target, start, count):
        hashes = ctypes.create_string_buffer(32 * count)
        flags = ctypes.create_string_buffer(count)
        target_le = target.to_bytes(32, "little")
        rc = lib.bal_cuda_batch(header, start, count, 128, target_le,
                                hashes, flags)
        if rc != 0:
            return None
        raw = hashes.raw  # one copy; per-index .raw access is O(n^2)
        return [raw[32 * i:32 * i + 32] for i in range(count)]

    def batch_search(self, header, target, start, count):
        """Return (candidates, stats). Candidates are CPU verified."""
        if len(header) != 80:
            raise ValueError("header must be exactly 80 bytes")
        if not (0 <= start and 0 < count <= MAX_BATCH
                and start + count <= NONCE_SPACE):
            raise ValueError("nonce batch out of bounds")
        if not (1 <= target < (1 << 256)):
            raise ValueError("target out of range")
        t0 = time.perf_counter()
        candidates = []
        used = self.backend
        if self.backend == "c":
            pairs = self._c_batch_flagged(self._c_lib, header, target,
                                          start, count)
            if pairs is None:
                used = "cpu"
            else:
                for nonce, d in pairs:
                    if verify_candidate(header, target, nonce, d):
                        candidates.append({"nonce": nonce,
                                           "hash": d[::-1].hex(),
                                           "backend": "c"})
                seconds = max(time.perf_counter() - t0, 1e-9)
                return candidates, {
                    "backend": used, "hashes": count, "seconds": seconds,
                    "hashrate": count / seconds, "start": start,
                }
        if self.backend == "cuda" and self._cuda_ctx is not None:
            # Production CUDA path: only candidate records cross
            # back; each is CPU verified before it is returned.
            try:
                pairs, info = self._cuda_ctx.search(header, target,
                                                    start, count)
                for nonce, d in pairs:
                    if verify_candidate(header, target, nonce, d):
                        candidates.append({"nonce": nonce,
                                           "hash": d[::-1].hex(),
                                           "backend": "cuda"})
                seconds = max(time.perf_counter() - t0, 1e-9)
                return candidates, {
                    "backend": "cuda", "hashes": count,
                    "seconds": seconds, "hashrate": count / seconds,
                    "start": start, "mode": "candidates_only",
                    "kernel_ms": info["kernel_ms"],
                    "candidates_found": info["candidates_found"],
                    "fallback_events": len(self.fallback_events),
                }
            except RuntimeError as exc:
                if "overflow" in str(exc):
                    raise  # truncated results are never softened
                self.fallback_reason = f"CUDA context failed: {exc}"
                self.fallback_events.append(
                    {"start": start, "count": count,
                     "reason": str(exc), "retried_on": "cpu"})
                used = "cpu"
        digests = None
        if self.backend == "cuda" and used == "cuda":
            digests = self._cuda_batch(self._lib, header, target, start, count)
            if digests is None:
                self.fallback_reason = "CUDA batch failed at runtime; fell back"
                self.fallback_events.append(
                    {"start": start, "count": count,
                     "reason": "legacy CUDA batch returned failure",
                     "retried_on": "cpu"})
                used = "cpu"
        if digests is None:
            digests = [cpu_digest(header, start + i) for i in range(count)]
            used = "cpu"
        for i, d in enumerate(digests):
            if int.from_bytes(d, "little") <= target:
                nonce = start + i
                if verify_candidate(header, target, nonce, d):
                    candidates.append({"nonce": nonce, "hash": d[::-1].hex(),
                                       "backend": used})
        seconds = max(time.perf_counter() - t0, 1e-9)
        return candidates, {
            "backend": used, "hashes": count, "seconds": seconds,
            "hashrate": count / seconds, "start": start,
            "fallback_events": len(self.fallback_events),
        }

    def benchmark(self, seconds_hint_batches=3, batch=65536):
        # A hard target (hit rate about 1 in 65536) keeps candidate
        # verification from dominating the measurement; this measures
        # raw batch hashing throughput of the selected backend.
        header = bytes(80)
        target = (1 << 240)
        total = 0.0
        hashes = 0
        for _ in range(seconds_hint_batches):
            _, stats = self.batch_search(header, target, 0, batch)
            total += stats["seconds"]
            hashes += batch
        return hashes / max(total, 1e-9)

    def describe(self):
        return {
            "backend": self.backend,
            "requested": self.requested,
            "device_count": self.device_count,
            "fallback_reason": self.fallback_reason,
            "cuda_fallback_reason": self.cuda_fallback_reason,
            "c_backend": bool(self._c_lib),
            "c_threads": C_THREADS,
            "c_attempt_counting": bool(
                self._c_lib and hasattr(self._c_lib, "bal_c_search2")),
            "cuda_context": bool(self._cuda_ctx),
            "cuda_context_reason": self.cuda_ctx_reason,
            "fallback_events": self.fallback_events,
            "last_search_stats": self.last_search_stats,
        }
