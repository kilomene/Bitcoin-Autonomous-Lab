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


class ComputeEngine:
    def __init__(self, lib_path=LIB_PATH, requested="auto"):
        self.requested = requested
        self.backend = "cpu"
        self.fallback_reason = None
        self.device_count = 0
        self._lib = None
        if requested in ("auto", "cuda"):
            self._try_cuda(lib_path)
        if self.backend != "cuda" and requested == "cuda":
            self.fallback_reason = self.fallback_reason or "CUDA requested but unavailable"

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

    def _cuda_batch(self, lib, header, target, start, count):
        hashes = ctypes.create_string_buffer(32 * count)
        flags = ctypes.create_string_buffer(count)
        target_le = target.to_bytes(32, "little")
        rc = lib.bal_cuda_batch(header, start, count, 128, target_le,
                                hashes, flags)
        if rc != 0:
            return None
        return [hashes.raw[32 * i:32 * i + 32] for i in range(count)]

    def batch_search(self, header, target, start, count):
        """Return (candidates, stats). Candidates are CPU verified."""
        if len(header) != 80:
            raise ValueError("header must be exactly 80 bytes")
        if not (0 <= start and 0 < count <= MAX_BATCH
                and start + count <= NONCE_SPACE):
            raise ValueError("nonce batch out of bounds")
        if not (1 <= target < (1 << 256)):
            raise ValueError("target out of range")
        t0 = time.time()
        digests = None
        used = self.backend
        if self.backend == "cuda":
            digests = self._cuda_batch(self._lib, header, target, start, count)
            if digests is None:
                self.fallback_reason = "CUDA batch failed at runtime; fell back to CPU"
                used = "cpu"
        if digests is None:
            digests = [cpu_digest(header, start + i) for i in range(count)]
            used = "cpu"
        candidates = []
        for i, d in enumerate(digests):
            if int.from_bytes(d, "little") <= target:
                nonce = start + i
                if verify_candidate(header, target, nonce, d):
                    candidates.append({"nonce": nonce, "hash": d[::-1].hex(),
                                       "backend": used})
        seconds = max(time.time() - t0, 1e-9)
        return candidates, {
            "backend": used, "hashes": count, "seconds": seconds,
            "hashrate": count / seconds, "start": start,
        }

    def benchmark(self, seconds_hint_batches=3, batch=8192):
        header = bytes(80)
        target = (1 << 255)
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
        }
