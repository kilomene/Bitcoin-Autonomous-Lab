"""ComputeEngine: batch SHA256d nonce search with backend dispatch.

Backends:
- cuda: the compiled gpu/cuda/engine.cu library, used only when it
  loads, reports at least one device, and passes the production
  candidate-path self-test (cuda_production_selftest), whose
  results are re-verified on the CPU. A diagnostic or legacy batch
  success alone never selects CUDA (Task 003.6).
- v512: the AVX-512 16-way multi-buffer CPU kernel
  (mining/cpu/bal_avx512_mb.c, built as .local/cpu/libbal_v512.so),
  integrated 2026-11-14 under the owner's adopted EXP-017 decision
  rule (pooled 3.55x vs the C backend, CI 3.17x to 3.97x,
  significant in every session). Selection is runtime CPUID
  dispatch: the flag-free probe compiled into the library
  (bal_v512_supported) must confirm AVX-512F and AVX-512BW, the
  exact feature set of the kernel's restricted-flag build, and
  the batch must then reproduce hashlib digests exactly. Any
  failure at any step falls back cleanly to the C backend, and
  machines without AVX-512 behave exactly as before. Requesting
  "c" explicitly still selects the C backend alone.
- c: the OpenSSL midstate C library (.local/cpu/libbal_batch.so).
- cpu: hashlib batch search (this machine also has the C SHA-NI
  engine in mining/cpu for the Stratum path).

AVX-512 accounting note: the v512 kernel works in 16-lane waves.
A started wave always completes, so on an early exit the counted
search reports attempted as the real nonces of every completed
wave (wave-exact semantics, as established in EXP-010), while
backend_hashes counts actual lane computations including dummy
lanes in a partial final wave: backend_hashes is the ceiling of
the examined work to whole waves and is never below attempted.
Batch enumeration covers the full range, so unique_coverage
equals the requested count while backend_hashes may exceed it
by the dummy lanes of the final partial wave of each span.

Every candidate from any backend is re-verified on the CPU before it
is returned. A CUDA failure at any point falls back to CPU and the
reason is recorded on the engine (fallback_reason). Nothing about the
GPU is ever claimed from compilation alone: backend selection is a
runtime measurement.

Mining accounting definitions (Task 003.9; these definitions govern
every stats dict produced by this module):

- requested_hashes: hash computations the caller asked for (the
  nonce-range size of the request). A request is not work.
- unique_coverage: distinct nonce values actually covered. For a
  completed full-range enumeration it equals requested_hashes. For
  an early-exit search it is the number of distinct nonces the
  backend actually examined before stopping, which is usually far
  below the request; when that number cannot be measured exactly
  the field is None and a note says why.
- backend_hashes: actual hash computations performed by the
  selected mining backend itself (the CUDA device, the native C
  library, or the Python hashlib enumeration, whichever executed
  the search). Verification and rescan work is NEVER included.
- device_hashes: actual hash computations performed by a CUDA
  device. This is a CUDA-only metric: it is exactly 0 whenever no
  CUDA device executed work, and CPU or C work is never reported
  under it. On a CUDA path, backend_hashes == device_hashes.
- researched_hashes: additional backend computations caused by
  repeating already-covered work, currently the repeats driven by
  CUDA candidate-buffer overflow recovery. Always a subset of
  backend_hashes (on the CUDA path, of device_hashes), never an
  addition to unique coverage.
- overflow_splits: subdivisions of a nonce range caused by
  candidate-buffer overflow during recovery.
- verification_hashes: actual hash computations performed by the
  independent verification and recovery layer: one per candidate
  presented for CPU verification, plus every digest computed by a
  trusted rescan (its enumeration pass and its re-verification of
  each candidate it finds). Never included in backend_hashes or
  device_hashes, so no computation is counted in two categories.
- candidate_count: candidates the backend presented for
  independent verification in this operation.

The identity device_hashes == unique_coverage + researched_hashes
is a property of the CUDA candidate-recovery driver
(collect_candidates_complete and the CudaContext paths built on
it) ONLY, where the wrapped backend is the CUDA device and the
driver accounts every device computation. It does not apply to
CPU or C execution: there device_hashes is 0, and the corresponding
identity is backend_hashes + verification_hashes == total actual
computations, reported per path in the stats.
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
V_LIB_PATH = os.path.join(ROOT, ".local", "cpu", "libbal_v512.so")
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


def tune_v512_threads(engine):
    """Measure this machine for the AVX-512 backend and set
    C_THREADS (the thread argument of every native counted
    call) to its peak, mirroring tune_c_threads: probes several
    thread counts with the real counted MB search over a fixed
    nonce range and keeps the fastest. Runs once per process;
    any failure leaves the safe default in place. Also records
    LAST_PROBE_RATE so span sizing in the live miner reflects
    the selected backend's real rate."""
    global C_THREADS, C_THREADS_TUNED, LAST_PROBE_RATE
    if C_THREADS_TUNED:
        return C_THREADS
    C_THREADS_TUNED = True
    if getattr(engine, "backend", None) != "v512" or not hasattr(
            engine._v_lib, "bal_v_search2"):
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
            out_attempted = ctypes.c_uint64(0)
            out_backend = ctypes.c_uint64(0)
            out_digest = ctypes.create_string_buffer(32)
            t0 = time.time()
            rc = engine._v_lib.bal_v_search2(
                header, 0, probe, n, target_le,
                ctypes.byref(out_nonce), out_digest,
                ctypes.byref(out_attempted),
                ctypes.byref(out_backend))
            dt = time.time() - t0
            if rc in (0, 1) and dt > 0 and probe / dt > best_rate:
                best_n, best_rate = n, probe / dt
        C_THREADS = best_n
        LAST_PROBE_RATE = best_rate
        print(f"full-workforce: AVX-512 search threads auto-tuned "
              f"to {best_n} on this machine "
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


# Task 003.8: public CUDA API validation. The CudaContext boundary
# validates every argument itself, before any backend call; it
# does not rely on ComputeEngine.batch_search or on the C ABI to
# catch bad input. Thread counts are CUDA block sizes, hence the
# documented 1..1024 bound.
CUDA_MAX_THREADS = 1024
MAX_OVERFLOW_SPLIT_DEPTH = 32


def _is_plain_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate_header(header, name="header"):
    """Return the header as bytes, requiring a bytes-like object
    of exactly 80 bytes."""
    if isinstance(header, memoryview):
        raw = header.tobytes()
    elif isinstance(header, (bytes, bytearray)):
        raw = bytes(header)
    else:
        raise TypeError(
            f"{name} must be a bytes-like object, got "
            f"{type(header).__name__}")
    if len(raw) != 80:
        raise ValueError(
            f"{name} must be exactly 80 bytes, got {len(raw)}")
    return raw


def validate_target(target, name="target"):
    """Return the target as an int. Accepts an int in
    [0, 2**256) or exactly 32 raw little-endian bytes (bytes-like);
    rejects everything else, naming the parameter."""
    if isinstance(target, bool):
        raise TypeError(f"{name} must be an int or 32 little-endian "
                        f"bytes, got bool")
    if _is_plain_int(target):
        if not (0 <= target < (1 << 256)):
            raise ValueError(
                f"{name} int out of range [0, 2**256): {target}")
        return target
    if isinstance(target, memoryview):
        raw = target.tobytes()
    elif isinstance(target, (bytes, bytearray)):
        raw = bytes(target)
    else:
        raise TypeError(
            f"{name} must be an int or 32 little-endian bytes, got "
            f"{type(target).__name__}")
    if len(raw) != 32:
        raise ValueError(
            f"{name} bytes must be exactly 32 bytes, got {len(raw)}")
    return int.from_bytes(raw, "little")


def validate_nonce_range(start, count):
    """Subtraction-based nonce-range validation: count is checked
    first, then start is compared against NONCE_SPACE - count, so
    no start + count expression can wrap."""
    if not _is_plain_int(start):
        raise TypeError(
            f"start must be an int, got {type(start).__name__}")
    if not _is_plain_int(count):
        raise TypeError(
            f"count must be an int, got {type(count).__name__}")
    if count < 1:
        raise ValueError(f"count must be at least 1, got {count}")
    if start < 0:
        raise ValueError(f"start must be at least 0, got {start}")
    if count > NONCE_SPACE:
        raise ValueError(
            f"count {count} exceeds the 32-bit nonce space")
    if start > NONCE_SPACE - count:
        raise ValueError(
            f"start {start} exceeds the nonce space for count "
            f"{count} (start must be at most "
            f"{NONCE_SPACE - count})")


def validate_threads(threads, name="threads"):
    if not _is_plain_int(threads):
        raise TypeError(
            f"{name} must be an int, got {type(threads).__name__}")
    if not (1 <= threads <= CUDA_MAX_THREADS):
        raise ValueError(
            f"{name} must be within [1, {CUDA_MAX_THREADS}], got "
            f"{threads}")
    return threads


class CandidateOverflowError(RuntimeError):
    """The bounded candidate buffer overflowed during a single-shot
    search (Task 003.5). The stored records are incomplete: `total`
    is the true candidate count the backend reported. This is a
    RuntimeError subclass so existing error handling keeps working,
    but overflow recovery code catches it specifically."""

    def __init__(self, message, total=None, start=None, count=None):
        super().__init__(message)
        self.total = total
        self.start = start
        self.count = count


def choose_sub_batch(target, count, capacity, safety=8):
    """Largest sub-batch whose EXPECTED candidate count stays at or
    below capacity/safety, using exact integer arithmetic:
    expected = sub * (target + 1) / 2^256 <= capacity / safety.
    Returns a value in [1, count]."""
    if count < 1 or capacity < 1:
        raise ValueError("bad count or capacity")
    sub = (capacity * (1 << 256)) // (safety * (target + 1))
    if sub < 1:
        sub = 1
    return min(sub, count)


def collect_candidates_complete(search_once, target, start, count,
                                capacity, max_chunk=None):
    """Guaranteed-coverage candidate collection (Task 003.5).

    search_once(start, count) performs ONE bounded single-shot
    search returning (candidates, info) and raising
    CandidateOverflowError when the candidate buffer overflowed.
    This driver partitions [start, start+count) into sub-batches
    sized from the target so overflow is unlikely, and whenever a
    sub-range still overflows it splits ONLY that sub-range in
    half and resolves the halves; the overflowing pass's partial
    records are discarded and its hashes are accounted separately
    as re-searched work, never as unique coverage. The leaf
    sub-batches that complete without overflow partition the
    original range exactly: every nonce is covered exactly once,
    no candidate is silently discarded, and the returned list is
    deduplicated by nonce and sorted.

    Accounting (Task 003.8, scoped by Task 003.9): the stats
    distinguish unique_coverage (distinct nonces covered by
    completing leaf sub-batches; equals count on success),
    device_hashes (total hashes the wrapped search actually
    computed, including repeats), backend_hashes (the same total
    under the backend-neutral name; identical here because this
    driver wraps exactly one backend), researched_hashes (the
    repeated part caused by overflow recovery), overflow_splits
    (overflow-driven subdivisions; overflow_events is kept as
    the same count for older callers), candidate_count
    (candidates returned for verification) and requested_hashes
    (the caller's count).

    SCOPE OF THE INVARIANT (Task 003.9): this driver is the CUDA
    candidate-recovery driver; in production search_once is the
    CUDA device search (CudaContext.search), so the wrapped
    computations ARE device computations and the identity
    device_hashes == unique_coverage + researched_hashes holds
    for every completed call. The identity is CUDA-scoped: it
    is a property of this driver accounting, NOT a general law
    of mining statistics. It must never be applied to CPU or C
    backend statistics, where device_hashes is 0 by definition
    and work is reported as backend_hashes plus
    verification_hashes. A caller that ever wraps this driver
    around a non-CUDA backend must remap the totals (report
    them as backend_hashes and set device_hashes to 0); the
    production code never does this.
    Splits are depth-capped at MAX_OVERFLOW_SPLIT_DEPTH (32,
    enough to halve any 32-bit range down to single nonces); a
    backend that still overflows at the cap, or at a single
    nonce, raises an explicit CandidateOverflowError instead of
    looping. max_chunk optionally caps each single-shot size
    (used by CudaContext to respect its device buffer size).

    Returns (candidates, stats) where candidates are (nonce,
    digest) pairs."""
    target = validate_target(target)
    validate_nonce_range(start, count)
    if not _is_plain_int(capacity):
        raise TypeError(
            f"capacity must be an int, got {type(capacity).__name__}")
    if capacity < 1:
        raise ValueError(f"capacity must be at least 1, got {capacity}")
    if max_chunk is not None:
        if not _is_plain_int(max_chunk):
            raise TypeError(
                f"max_chunk must be an int, got "
                f"{type(max_chunk).__name__}")
        if max_chunk < 1:
            raise ValueError(
                f"max_chunk must be at least 1, got {max_chunk}")
    found = {}
    stats = {"sub_batches": 0, "overflow_events": 0,
             "overflow_splits": 0,
             "researched_hashes": 0, "unique_coverage": 0,
             "device_hashes": 0, "backend_hashes": 0,
             "candidate_count": 0, "requested_hashes": count,
             "initial_search_seconds": 0.0,
             "recovery_search_seconds": 0.0,
             "search_seconds": 0.0, "kernel_ms_total": 0.0}
    end = start + count
    stack = []
    pos = start
    sub0 = choose_sub_batch(target, count, capacity)
    if max_chunk is not None:
        sub0 = min(sub0, max_chunk)
    while pos < end:
        n = min(sub0, end - pos)
        stack.append((pos, n, 0))
        pos += n
    while stack:
        s, n, depth = stack.pop()
        stats["device_hashes"] += n
        stats["backend_hashes"] += n
        t0 = time.perf_counter()
        try:
            cands, info = search_once(s, n)
        except CandidateOverflowError:
            dt = time.perf_counter() - t0
            stats["search_seconds"] += dt
            if depth == 0:
                stats["initial_search_seconds"] += dt
            else:
                stats["recovery_search_seconds"] += dt
            stats["overflow_events"] += 1
            stats["researched_hashes"] += n
            if n == 1:
                raise CandidateOverflowError(
                    "single nonce reported more candidates than the "
                    "buffer holds; backend is broken",
                    start=s, count=n)
            if depth >= MAX_OVERFLOW_SPLIT_DEPTH:
                raise CandidateOverflowError(
                    f"overflow split depth cap "
                    f"{MAX_OVERFLOW_SPLIT_DEPTH} reached for range "
                    f"start={s} count={n}; backend is broken",
                    start=s, count=n)
            stats["overflow_splits"] += 1
            half = n // 2
            stack.append((s + half, n - half, depth + 1))
            stack.append((s, half, depth + 1))
            continue
        dt = time.perf_counter() - t0
        stats["search_seconds"] += dt
        if depth == 0:
            stats["initial_search_seconds"] += dt
        else:
            stats["recovery_search_seconds"] += dt
        if info and isinstance(info, dict):
            kms = info.get("kernel_ms")
            if isinstance(kms, (int, float)) and kms:
                stats["kernel_ms_total"] += float(kms)
        stats["sub_batches"] += 1
        stats["unique_coverage"] += n
        for nonce, digest in cands:
            if not (_is_plain_int(nonce) and s <= nonce < s + n):
                raise RuntimeError(
                    f"backend returned candidate nonce {nonce!r} "
                    f"outside the searched range start={s} "
                    f"count={n}")
            if not (isinstance(digest, (bytes, bytearray))
                    and len(digest) == 32):
                raise RuntimeError(
                    f"backend returned a malformed digest for "
                    f"nonce {nonce}")
            found[nonce] = bytes(digest)
    stats["candidate_count"] = len(found)
    return sorted(found.items()), stats


# Genesis header: a fixed, independently known work item for the
# CUDA production self-test (Task 003.6).
SELFTEST_HEADER = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")


def cuda_production_selftest(ctx):
    """Exercise the PRODUCTION candidate-filtering path of a CUDA
    context object (Task 003.6): context work setup and midstate,
    target upload, candidate search, candidate counter, capacity
    handling and overflow recovery, with every returned candidate
    verified on the CPU and the candidate SET compared against an
    independent CPU recount. Returns (ok, reason). A diagnostic or
    legacy batch path is never consulted here, so its success
    cannot authorize CUDA selection."""
    header = SELFTEST_HEADER
    target = 1 << 255
    start, count = 0, 2048
    try:
        cands, _info = ctx.search(header, target, start, count)
    except Exception as exc:
        return False, f"production candidate search failed: {exc}"
    got = {}
    for nonce, digest in cands:
        if not verify_candidate(header, target, nonce, digest):
            return False, (f"production candidate at nonce {nonce} "
                           f"failed CPU verification")
        got[nonce] = digest
    want = {}
    for n in range(start, start + count):
        d = cpu_digest(header, n)
        if int.from_bytes(d, "little") <= target:
            want[n] = d
    if got != want:
        return False, ("production candidate set disagrees with the "
                       "CPU recount")
    # Capacity handling: an all-match target over capacity + 1
    # nonces MUST surface an overflow, never a truncated list.
    try:
        ctx.search(header, (1 << 256) - 1, 0, ctx.CAND_CAP + 1)
        return False, "candidate overflow was not reported"
    except CandidateOverflowError:
        pass
    except Exception as exc:
        return False, f"overflow probe failed unexpectedly: {exc}"
    # And the recovery driver must return every candidate for an
    # all-match range larger than the buffer.
    total = ctx.CAND_CAP + 257
    try:
        all_cands, cstats = ctx.search_complete(
            header, (1 << 256) - 1, 0, total)
    except Exception as exc:
        return False, f"overflow recovery failed: {exc}"
    if len(all_cands) != total or \
            cstats["unique_coverage"] != total:
        return False, "overflow recovery lost candidates or coverage"
    return True, "production candidate path verified against the CPU"


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
        if not _is_plain_int(max_count):
            raise TypeError(
                f"max_count must be an int, got "
                f"{type(max_count).__name__}")
        if not (1 <= max_count <= (1 << 24)):
            raise ValueError(
                f"max_count must be within [1, {1 << 24}], got "
                f"{max_count}")
        self._lib = lib
        self._max_count = max_count
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
        header = validate_header(header)
        target = validate_target(target)
        if self._ctx is None:
            raise RuntimeError("CUDA context is not initialized")
        key = (header, target)
        if self._work_key == key:
            return
        rc = self._lib.bal_cuda_ctx_set_work(
            self._ctx, header, target.to_bytes(32, "little"))
        if rc != 0:
            raise RuntimeError(f"bal_cuda_ctx_set_work failed: {rc}")
        self._work_key = key

    def search(self, header, target, start, count, threads=256):
        """Single-shot bounded search. Returns (candidates, info);
        candidates are raw (nonce, digest) pairs, NOT yet CPU
        verified. Raises CandidateOverflowError when the bounded
        buffer overflowed: the stored records are then incomplete
        and must never be presented as a complete search. All
        arguments are validated at this boundary (Task 003.8)
        before any backend call."""
        header = validate_header(header)
        target = validate_target(target)
        validate_nonce_range(start, count)
        validate_threads(threads)
        if count > self._max_count:
            raise ValueError(
                f"count {count} exceeds this context's max_count "
                f"{self._max_count}; use search_complete for "
                f"larger ranges")
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
        if out_ovf.value or out_count.value > self.CAND_CAP:
            raise CandidateOverflowError(
                f"candidate buffer overflow: {out_count.value} "
                f"candidates exceeded capacity {self.CAND_CAP} for "
                f"range start={start} count={count}; result would "
                f"be truncated and is refused",
                total=out_count.value, start=start, count=count)
        raw = digests.raw
        cands = []
        for i in range(out_count.value):
            nonce = nonces[i]
            if not (start <= nonce < start + count):
                raise RuntimeError(
                    f"CUDA backend returned candidate nonce {nonce} "
                    f"outside the searched range start={start} "
                    f"count={count}")
            cands.append((nonce, raw[32 * i:32 * i + 32]))
        return cands, {"kernel_ms": kernel_ms.value,
                       "candidates_found": out_count.value,
                       "candidate_count": out_count.value,
                       "requested_hashes": count,
                       "unique_coverage": count,
                       "device_hashes": count,
                       "backend_hashes": count,
                       "verification_hashes": 0,
                       "researched_hashes": 0,
                       "overflow_splits": 0}

    def search_complete(self, header, target, start, count,
                        threads=256):
        """Guaranteed-coverage production search (Task 003.5):
        adaptive sub-batching plus split-on-overflow recovery via
        collect_candidates_complete. Returns (candidates, stats)
        with every nonce of the range covered exactly once.

        Task 003.8: every argument is validated HERE, at the
        public API boundary, before set_work or any other backend
        call: header must be a bytes-like object of exactly 80
        bytes; target an int in [0, 2**256) or exactly 32 raw
        little-endian bytes; start and count must satisfy the
        subtraction-based nonce-space rule; threads must be
        within [1, 1024]. Invalid input raises TypeError or
        ValueError naming the offending parameter."""
        header = validate_header(header)
        target = validate_target(target)
        validate_nonce_range(start, count)
        validate_threads(threads)
        self.set_work(header, target)
        return collect_candidates_complete(
            lambda s, n: self.search(header, target, s, n, threads),
            target, start, count, self.CAND_CAP,
            max_chunk=self._max_count)

    def batch_diag(self, header, target, start, count, threads=128):
        """Diagnostic mode: every digest, for self-tests only."""
        header = validate_header(header)
        target = validate_target(target)
        validate_nonce_range(start, count)
        validate_threads(threads)
        if count > self._max_count:
            raise ValueError(
                f"count {count} exceeds this context's max_count "
                f"{self._max_count}")
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
                 c_lib_path=C_LIB_PATH, v_lib_path=V_LIB_PATH):
        self.requested = requested
        self.backend = "cpu"
        self.fallback_reason = None
        self.device_count = 0
        self._lib = None
        self._c_lib = None
        self._v_lib = None
        self.v512_reason = None
        self._v_last_counts = None
        self._cuda_ctx = None
        self.cuda_ctx_reason = None
        self.cuda_fallback_reason = None
        self.fallback_events = []
        self.last_search_stats = None
        if requested in ("auto", "cuda", "cuda-only"):
            self._try_cuda(lib_path)
            self.cuda_fallback_reason = self.fallback_reason
        if self.backend != "cuda" and requested in ("auto", "v512"):
            self._try_v512(v_lib_path)
        if self.backend not in ("cuda", "v512") and requested in (
                "auto", "c", "v512"):
            self._try_c(c_lib_path)
        if requested == "cuda-only" and self.backend != "cuda":
            raise RuntimeError(
                "CUDA-only mode requested but CUDA cannot execute: "
                f"{self.cuda_fallback_reason or self.fallback_reason}")
        if self.backend == "cuda":
            self.fallback_reason = None
        elif self.backend in ("c", "v512"):
            self.fallback_reason = self.cuda_fallback_reason
        if requested == "cuda" and self.backend != "cuda":
            self.fallback_reason = self.fallback_reason or "CUDA requested but unavailable"
        if self.backend == "c":
            tune_c_threads(self)
        elif self.backend == "v512":
            tune_v512_threads(self)

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

    def _try_v512(self, v_lib_path):
        """Runtime CPUID dispatch for the AVX-512 multi-buffer
        backend. The library is loaded (loading never executes
        kernel code), the flag-free probe compiled into it must
        confirm AVX-512F and AVX-512BW, and only then is a
        kernel batch run and checked digest by digest against
        the CPU. Any failure leaves the engine unselected with
        the reason recorded on v512_reason; selection failure
        is never fatal, the C backend is tried next."""
        if not os.path.isfile(v_lib_path):
            self.v512_reason = (f"AVX-512 library not built "
                                f"({v_lib_path})")
            return
        try:
            lib = ctypes.CDLL(v_lib_path)
        except OSError as exc:
            self.v512_reason = f"AVX-512 library failed to load: {exc}"
            return
        if not hasattr(lib, "bal_v512_supported"):
            self.v512_reason = ("AVX-512 library has no CPUID "
                                "probe; refusing to call the kernel")
            return
        lib.bal_v512_supported.restype = ctypes.c_int
        try:
            supported = lib.bal_v512_supported()
        except Exception as exc:
            self.v512_reason = f"AVX-512 CPUID probe failed: {exc}"
            return
        if not supported:
            bits = None
            if hasattr(lib, "bal_v512_feature_bits"):
                lib.bal_v512_feature_bits.restype = ctypes.c_uint
                bits = lib.bal_v512_feature_bits()
            self.v512_reason = (
                "CPUID dispatch: this CPU cannot execute the "
                "AVX-512 multi-buffer kernel (requires AVX-512F "
                f"and AVX-512BW; feature bits {bits})")
            return
        lib.bal_v_batch2.restype = ctypes.c_int
        lib.bal_v_batch2.argtypes = [
            ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
            ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
            ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64)]
        lib.bal_v_search2.restype = ctypes.c_int
        lib.bal_v_search2.argtypes = [
            ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
            ctypes.c_uint, ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64)]
        header = bytes(range(80))
        got = self._v_batch(lib, header, 1 << 255, 0, 256)
        if got is None:
            self.v512_reason = "AVX-512 self-test batch failed"
            return
        for nonce in range(256):
            if got[nonce] != cpu_digest(header, nonce):
                self.v512_reason = "AVX-512 self-test digest mismatch"
                return
        self._v_lib = lib
        self.backend = "v512"
        self.v512_reason = ("selected: CPUID probe confirms "
                            "AVX-512F and AVX-512BW and the batch "
                            "reproduces hashlib digests")

    def _v_batch(self, lib, header, target, start, count):
        pairs = self._v_batch_flagged(lib, header, target, start,
                                      count, want_all=True)
        if pairs is None:
            return None
        digests = [b""] * count
        for nonce, digest in pairs:
            digests[nonce - start] = digest
        return digests

    def _v_batch_flagged(self, lib, header, target, start, count,
                         want_all=False):
        """Run an AVX-512 batch and return (nonce, digest) pairs
        (all of them, or only the target-flagged ones), located
        through the kernel's flags array. The counted ABI's
        actuals (real nonces covered, lane computations
        including dummy lanes) are stashed on
        self._v_last_counts for the caller's accounting."""
        hashes = ctypes.create_string_buffer(32 * count)
        flags = ctypes.create_string_buffer(count)
        target_le = target.to_bytes(32, "little")
        out_attempted = ctypes.c_uint64(0)
        out_backend = ctypes.c_uint64(0)
        rc = lib.bal_v_batch2(header, start, count, C_THREADS,
                              target_le, hashes, flags,
                              ctypes.byref(out_attempted),
                              ctypes.byref(out_backend))
        if rc != 0:
            return None
        self._v_last_counts = (out_attempted.value,
                               out_backend.value)
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

    def _recover_bad_candidate(self, header, target, start, count,
                               native_attempted, source):
        """Task 003.4: a native backend reported a candidate that
        failed independent CPU verification. That is a serious
        backend correctness failure, never an ordinary miss: the
        native search stopped early, so the rest of the range was
        never searched by it. Rescan the affected range with the
        trusted Python hashlib implementation so no nonce of the
        range is silently skipped, record a fallback event, and
        account the rescan work separately. Returns
        (hit, total_attempted)."""
        hit = None
        rescan_attempted = 0
        for i in range(count):
            nonce = start + i
            d = cpu_digest(header, nonce)
            rescan_attempted += 1
            if int.from_bytes(d, "little") <= target:
                hit = (nonce, d)
                break
        self.fallback_events.append({
            "start": start, "count": count,
            "reason": f"{source} candidate failed CPU verification",
            "retried_on": "cpu-hashlib-rescan",
            "native_attempted": native_attempted,
            "rescan_attempted": rescan_attempted})
        return hit, native_attempted + rescan_attempted

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
        exactly the range size.

        Task 003.9: last_search_stats also carries the standard
        accounting fields (definitions in the module docstring):
        requested_hashes, backend_hashes (native backend
        computations only), device_hashes (0 here unless the
        batch path executed on CUDA; CPU and C work is never
        device work), verification_hashes (the candidate
        verification computation, plus trusted-rescan
        computations when a bad candidate forced one),
        unique_coverage (distinct nonces the backend actually
        examined before stopping; None with a
        unique_coverage_note when the exact union of examined
        nonces cannot be measured, for example after a rescan or
        on the legacy uncounted library), candidate_count,
        researched_hashes and overflow_splits. The returned
        "attempted" keeps its Task 001 meaning (total actual
        attempts including any verification rescan) for existing
        callers; backend_hashes is the backend-only part of it."""
        if len(header) != 80 or not (1 <= target < (1 << 256)):
            raise ValueError("bad header or target")
        if not (0 <= start and 0 < count and start + count <= NONCE_SPACE):
            raise ValueError("nonce range out of bounds")
        t0 = time.perf_counter()
        hit = None
        attempted = count  # batch fallback scans everything
        backend_used = self.backend
        rescanned = False
        rescan_attempted = 0
        # Task 003.9 accounting trackers for the final stats dict.
        acct = {"backend_hashes": None, "device_hashes": 0,
                "verification_hashes": 0, "unique_coverage": None,
                "unique_coverage_note": None,
                "candidate_count": 0, "researched_hashes": 0,
                "overflow_splits": 0}
        if self.backend == "v512":
            out_nonce = ctypes.c_uint32(0)
            out_attempted = ctypes.c_uint64(0)
            out_backend = ctypes.c_uint64(0)
            out_digest = ctypes.create_string_buffer(32)
            target_le = target.to_bytes(32, "little")
            rc = self._v_lib.bal_v_search2(
                header, start, count, C_THREADS, target_le,
                ctypes.byref(out_nonce), out_digest,
                ctypes.byref(out_attempted),
                ctypes.byref(out_backend))
            if rc not in (0, 1):
                raise RuntimeError(f"bal_v_search2 returned {rc}")
            # Wave accounting (EXP-010 semantics): attempted is
            # the real nonces of every completed 16-lane wave;
            # backend_hashes is the lane computations behind
            # them, dummy lanes of partial waves included, so
            # backend_hashes >= attempted always.
            attempted = out_attempted.value
            acct["backend_hashes"] = out_backend.value
            acct["unique_coverage"] = attempted
            if rc == 1:
                nonce = out_nonce.value
                digest = out_digest.raw
                acct["candidate_count"] = 1
                acct["verification_hashes"] += 1
                if verify_candidate(header, target, nonce, digest):
                    hit = (nonce, digest)
                else:
                    # Task 003.4 discipline, applied to the MB
                    # backend identically: never a silent miss.
                    native_att = attempted
                    hit, attempted = self._recover_bad_candidate(
                        header, target, start, count, attempted,
                        "native AVX-512 MB (bal_v_search2)")
                    rescan_attempted = attempted - native_att
                    rescanned = True
                    backend_used = "cpu-rescan"
                    acct["verification_hashes"] += rescan_attempted
                    acct["unique_coverage"] = None
                    acct["unique_coverage_note"] = (
                        "backend examined "
                        f"{native_att} distinct nonces and the "
                        "verification rescan re-examined a prefix; "
                        "their exact union is not measurable")
        elif self.backend == "c" and hasattr(self._c_lib, "bal_c_search2"):
            out_nonce = ctypes.c_uint32(0)
            out_attempted = ctypes.c_uint64(0)
            out_digest = ctypes.create_string_buffer(32)
            target_le = target.to_bytes(32, "little")
            rc = self._c_lib.bal_c_search2(
                header, start, count, C_THREADS, target_le,
                ctypes.byref(out_nonce), out_digest,
                ctypes.byref(out_attempted))
            attempted = out_attempted.value
            acct["backend_hashes"] = attempted
            acct["unique_coverage"] = attempted
            if rc == 1:
                nonce = out_nonce.value
                digest = out_digest.raw
                acct["candidate_count"] = 1
                acct["verification_hashes"] += 1
                if verify_candidate(header, target, nonce, digest):
                    hit = (nonce, digest)
                else:
                    # Task 003.4: never a silent ordinary miss.
                    native_att = attempted
                    hit, attempted = self._recover_bad_candidate(
                        header, target, start, count, attempted,
                        "native C (bal_c_search2)")
                    rescan_attempted = attempted - native_att
                    rescanned = True
                    backend_used = "cpu-rescan"
                    # The rescan's computations are verification
                    # work; the exact union of backend-examined
                    # and rescan-examined nonces is not measurable
                    # (the backend's set is scattered across its
                    # thread partitions), so coverage is reported
                    # as unavailable rather than invented.
                    acct["verification_hashes"] += rescan_attempted
                    acct["unique_coverage"] = None
                    acct["unique_coverage_note"] = (
                        "backend examined "
                        f"{native_att} distinct nonces and the "
                        "verification rescan re-examined a prefix; "
                        "their exact union is not measurable")
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
            legacy_verification = 0
            legacy_presented = 0
            if rc == 1:
                nonce = out_nonce.value
                digest = out_digest.raw
                legacy_presented = 1
                legacy_verification += 1
                if verify_candidate(header, target, nonce, digest):
                    hit = (nonce, digest)
                else:
                    # Task 003.4: never a silent ordinary miss.
                    native_att = attempted
                    hit, attempted = self._recover_bad_candidate(
                        header, target, start, count, attempted,
                        "native C (bal_c_search)")
                    rescan_attempted = attempted - native_att
                    rescanned = True
                    backend_used = "cpu-rescan"
                    legacy_verification += rescan_attempted
            legacy_seconds = time.perf_counter() - t0
            self.last_search_stats = {
                "backend": backend_used, "threads": C_THREADS,
                "start": start, "requested": count,
                "requested_hashes": count,
                "attempted": attempted, "counted": False,
                "backend_hashes": count,
                "device_hashes": 0,
                "verification_hashes": legacy_verification,
                "unique_coverage": None,
                "unique_coverage_note": (
                    "legacy bal_c_search does not report attempts; "
                    "backend_hashes is the range size as an upper "
                    "bound (see counted=False) and exact unique "
                    "coverage is unavailable"),
                "candidate_count": legacy_presented,
                "researched_hashes": 0, "overflow_splits": 0,
                "rescanned": rescanned, "rescan_attempted": rescan_attempted,
                "seconds": legacy_seconds, "hit": bool(hit),
                "hashrate": count / legacy_seconds
                if legacy_seconds > 0 else 0.0}
            return hit, attempted, self.last_search_stats["seconds"]
        else:
            cands, _stats = self.batch_search(header, target, start, count)
            backend_used = _stats["backend"]
            acct["backend_hashes"] = _stats["backend_hashes"]
            acct["device_hashes"] = _stats["device_hashes"]
            acct["verification_hashes"] = _stats["verification_hashes"]
            acct["unique_coverage"] = _stats["unique_coverage"]
            acct["candidate_count"] = _stats["candidate_count"]
            acct["researched_hashes"] = _stats["researched_hashes"]
            acct["overflow_splits"] = _stats["overflow_splits"]
            if cands:
                hit = (cands[0]["nonce"],
                       bytes.fromhex(cands[0]["hash"])[::-1])
        seconds = time.perf_counter() - t0
        backend_hashes = acct["backend_hashes"]
        self.last_search_stats = {
            "backend": backend_used,
            "threads": C_THREADS if backend_used in ("c", "v512")
            else 1,
            "start": start, "requested": count,
            "requested_hashes": count,
            "attempted": attempted,
            "counted": True, "seconds": seconds, "hit": bool(hit),
            "backend_hashes": backend_hashes,
            "device_hashes": acct["device_hashes"],
            "verification_hashes": acct["verification_hashes"],
            "unique_coverage": acct["unique_coverage"],
            "unique_coverage_note": acct["unique_coverage_note"],
            "candidate_count": acct["candidate_count"],
            "researched_hashes": acct["researched_hashes"],
            "overflow_splits": acct["overflow_splits"],
            "rescanned": rescanned, "rescan_attempted": rescan_attempted,
            "hashrate": (backend_hashes / seconds
                         if backend_hashes is not None and seconds > 0
                         else attempted / seconds if seconds > 0
                         else 0.0)}
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
        # Preliminary check only: one small legacy batch must match
        # the CPU exactly. Passing this does NOT select CUDA
        # (Task 003.6); it only proves the library loads and the
        # diagnostic path computes. Selection requires the
        # production candidate path self-test below.
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
        # Task 003.6: CUDA is selected ONLY when the production
        # candidate-filtering path (persistent context, midstate
        # work setup, candidate search, counter, capacity and
        # overflow handling) passes its self-test against the CPU.
        if not hasattr(lib, "bal_cuda_ctx_create"):
            self.fallback_reason = (
                "CUDA library has no persistent production context "
                "ABI; a diagnostic batch alone cannot authorize CUDA")
            self.cuda_ctx_reason = self.fallback_reason
            return
        try:
            ctx = CudaContext(lib)
        except Exception as exc:
            self.fallback_reason = f"CUDA production context failed: {exc}"
            self.cuda_ctx_reason = self.fallback_reason
            return
        ok, reason = cuda_production_selftest(ctx)
        if not ok:
            try:
                ctx.close()
            except Exception:
                pass
            self.fallback_reason = f"CUDA production self-test failed: {reason}"
            self.cuda_ctx_reason = self.fallback_reason
            return
        self._cuda_ctx = ctx
        self.cuda_ctx_reason = reason
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
        raw = hashes.raw  # one copy; per-index .raw access is O(n^2)
        return [raw[32 * i:32 * i + 32] for i in range(count)]

    def _check_pairs(self, header, target, start, count, pairs):
        """Validate a backend's candidate pairs for batch_search:
        every pair must be inside the searched range, unique, and
        pass independent CPU verification. Returns
        (clean_pairs, bad_count, verify_count), where verify_count
        is the number of independent verification hash computations
        actually performed (Task 003.9: one per pair that reached
        verify_candidate; pairs rejected by the cheap range or
        duplicate checks cost no hash). Any failure poisons the
        whole enumeration: a backend that lies about one candidate
        may also have mis-flagged others, so callers recover the
        full range with the trusted rescan instead of trusting the
        remaining pairs."""
        clean = []
        seen = set()
        bad = 0
        verify_count = 0
        for nonce, d in pairs:
            if (not _is_plain_int(nonce)
                    or not (start <= nonce < start + count)
                    or nonce in seen):
                bad += 1
                continue
            verify_count += 1
            if not verify_candidate(header, target, nonce, d):
                bad += 1
                continue
            seen.add(nonce)
            clean.append((nonce, d))
        return clean, bad, verify_count

    def _rescan_all_candidates(self, header, target, start, count,
                               source, bad):
        """Task 003.8 fail-closed recovery for batch enumeration:
        rescan the WHOLE affected range with the trusted Python
        hashlib implementation and return every verified
        candidate in it, so after a backend verification failure
        the range is independently covered in full. Records a
        fallback event with the failure count and the rescan
        attempt count. Returns (candidates, rescan_attempted,
        verification_hashes). rescan_attempted counts only the
        enumeration pass (one digest per nonce);
        verification_hashes (Task 003.9) counts every hash
        computation this recovery performed: the enumeration
        digests plus one re-verification computation per
        candidate found. All of it is verification-layer work:
        callers report it under verification_hashes, never under
        backend_hashes or device_hashes."""
        candidates = []
        attempted = 0
        verify_count = 0
        for i in range(count):
            nonce = start + i
            d = cpu_digest(header, nonce)
            attempted += 1
            if int.from_bytes(d, "little") <= target:
                verify_count += 1
                if not verify_candidate(header, target, nonce, d):
                    raise RuntimeError(
                        "trusted CPU rescan produced an invalid "
                        "candidate; refusing to continue")
                candidates.append({"nonce": nonce,
                                   "hash": d[::-1].hex(),
                                   "backend": "cpu-rescan"})
        self.fallback_events.append({
            "start": start, "count": count,
            "reason": f"{bad} {source} candidate(s) failed CPU "
                      f"verification in batch enumeration",
            "retried_on": "cpu-hashlib-rescan",
            "verification_failures": bad,
            "rescan_attempted": attempted})
        return candidates, attempted, attempted + verify_count

    def batch_search(self, header, target, start, count):
        """Return (candidates, stats). Candidates are CPU verified.

        Accounting (Task 003.8, corrected by Task 003.9; full
        definitions in the module docstring): stats carry
        requested_hashes (the caller's count), unique_coverage
        (distinct nonces covered; equals the count on every
        completed call here, because batch enumeration always
        covers the full range), backend_hashes (actual hash
        computations performed by the selected mining backend
        itself; verification and rescan work is NEVER included),
        device_hashes (CUDA device computations only; exactly 0
        on CPU and C paths, where no device work exists),
        researched_hashes (repeats caused by CUDA overflow
        recovery; a subset of device_hashes on the CUDA path),
        verification_hashes (every hash computation performed by
        the independent verification and recovery layer: one per
        candidate presented for verification, plus all trusted
        rescan computations), verification_rescan_hashes (the
        rescan enumeration attempts alone, kept for older
        callers), overflow_splits, candidate_count (candidates
        the backend presented for verification), hashrate
        (backend_hashes per second; on the CUDA path that is
        device_hashes per second, since the device is the
        backend) and coverage_per_second (unique coverage per
        second), plus a coverage_status stating whether the
        range ended fully covered and by whom. The legacy
        "hashes" key is the total of backend_hashes plus
        verification_hashes: every actual computation, each
        counted in exactly one category."""
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
        if self.backend in ("c", "v512"):
            is_v = self.backend == "v512"
            if is_v:
                pairs = self._v_batch_flagged(
                    self._v_lib, header, target, start, count)
            else:
                pairs = self._c_batch_flagged(
                    self._c_lib, header, target, start, count)
            if pairs is None:
                used = "cpu"
            else:
                clean, bad, verify_count = self._check_pairs(
                    header, target, start, count, pairs)
                rescan_attempted = 0
                rescan_verification = 0
                if bad:
                    # Task 003.8: fail closed. The enumeration is
                    # poisoned, so the whole range is independently
                    # re-covered by the trusted CPU rescan; the
                    # backend's pairs are not trusted at all.
                    candidates, rescan_attempted, \
                        rescan_verification = \
                        self._rescan_all_candidates(
                            header, target, start, count,
                            "native AVX-512 MB batch" if is_v
                            else "native C batch", bad)
                    used = "cpu-rescan"
                else:
                    candidates = [
                        {"nonce": nonce, "hash": d[::-1].hex(),
                         "backend": self.backend}
                        for nonce, d in clean]
                seconds = max(time.perf_counter() - t0, 1e-9)
                # Task 003.9: the C batch computed exactly count
                # digests (full-range enumeration by construction).
                # The AVX-512 batch computed the lane count its
                # counted ABI reports: the full range plus the
                # dummy lanes of each span's final partial wave.
                # Verification computations and any rescan work
                # are verification-layer work, reported only under
                # verification_hashes, never inside backend_hashes.
                backend_hashes = (self._v_last_counts[1] if is_v
                                  else count)
                verification_hashes = verify_count + rescan_verification
                return candidates, {
                    "backend": used,
                    "original_backend": self.backend,
                    "hashes": backend_hashes + verification_hashes,
                    "backend_hashes": backend_hashes,
                    "verification_hashes": verification_hashes,
                    "device_hashes": 0,
                    "seconds": seconds,
                    "hashrate": backend_hashes / seconds,
                    "coverage_per_second": count / seconds,
                    "start": start,
                    "requested_hashes": count,
                    "unique_coverage": count,
                    "researched_hashes": 0,
                    "verification_rescan_hashes": rescan_attempted,
                    "overflow_splits": 0,
                    "candidate_count": len(pairs),
                    "verification_failures": bad,
                    "rescanned": bool(bad),
                    "rescan_attempted": rescan_attempted,
                    "coverage_status": (
                        "complete: trusted CPU rescan after "
                        "verification failure" if bad else
                        "complete: full-range enumeration, all "
                        "candidates verified"),
                    "fallback_events": len(self.fallback_events),
                }
        if self.backend == "cuda" and self._cuda_ctx is not None:
            # Production CUDA path: only candidate records cross
            # back; each is CPU verified before it is returned.
            # Task 003.5: search_complete guarantees full coverage
            # across candidate-buffer overflows by adaptive
            # sub-batching and split-on-overflow recovery.
            try:
                pairs, cstats = self._cuda_ctx.search_complete(
                    header, target, start, count)
                clean, bad, verify_count = self._check_pairs(
                    header, target, start, count, pairs)
                rescan_attempted = 0
                rescan_verification = 0
                if bad:
                    # Task 003.8: fail closed, exactly as the CPU
                    # batch path: discard the poisoned enumeration
                    # and independently re-cover the whole range.
                    candidates, rescan_attempted, \
                        rescan_verification = \
                        self._rescan_all_candidates(
                            header, target, start, count,
                            "CUDA", bad)
                    used = "cpu-rescan"
                else:
                    candidates = [
                        {"nonce": nonce, "hash": d[::-1].hex(),
                         "backend": "cuda"} for nonce, d in clean]
                    used = "cuda"
                seconds = max(time.perf_counter() - t0, 1e-9)
                device_hashes = cstats["device_hashes"]
                # Task 003.9: on the CUDA path the device IS the
                # backend, so backend_hashes == device_hashes.
                # CPU verification and rescan computations are
                # verification-layer work and are never added to
                # either device or backend totals.
                verification_hashes = verify_count + rescan_verification
                return candidates, {
                    "backend": used, "original_backend": "cuda",
                    "hashes": device_hashes + verification_hashes,
                    "backend_hashes": device_hashes,
                    "verification_hashes": verification_hashes,
                    "device_hashes": device_hashes,
                    "seconds": seconds,
                    "hashrate": device_hashes / seconds,
                    "coverage_per_second": count / seconds,
                    "start": start, "mode": "candidates_only",
                    "requested_hashes": count,
                    "candidates_found": len(pairs),
                    "candidate_count": cstats["candidate_count"],
                    "verification_failures": bad,
                    "overflow_events": cstats["overflow_events"],
                    "overflow_splits": cstats["overflow_splits"],
                    "researched_hashes": cstats["researched_hashes"],
                    "verification_rescan_hashes": rescan_attempted,
                    "sub_batches": cstats["sub_batches"],
                    "unique_coverage": cstats["unique_coverage"],
                    "rescanned": bool(bad),
                    "rescan_attempted": rescan_attempted,
                    "initial_search_seconds":
                        cstats["initial_search_seconds"],
                    "recovery_search_seconds":
                        cstats["recovery_search_seconds"],
                    "coverage_status": (
                        "complete: trusted CPU rescan after "
                        "verification failure" if bad else
                        "complete: CUDA search_complete, all "
                        "candidates verified"),
                    "fallback_events": len(self.fallback_events),
                }
            except RuntimeError as exc:
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
        digest_source = used
        if digests is None:
            digests = [cpu_digest(header, start + i) for i in range(count)]
            used = "cpu"
            digest_source = "cpu"
        raw_candidates = 0
        bad = 0
        for i, d in enumerate(digests):
            if int.from_bytes(d, "little") <= target:
                raw_candidates += 1
                nonce = start + i
                if verify_candidate(header, target, nonce, d):
                    candidates.append({"nonce": nonce, "hash": d[::-1].hex(),
                                       "backend": used})
                else:
                    bad += 1
        rescan_attempted = 0
        rescan_verification = 0
        if bad:
            # Task 003.8: a digest that meets the target but fails
            # verification is never silently dropped. Legacy CUDA
            # digests are recovered by an independent trusted
            # rescan of the whole range; a failure inside the CPU
            # fallback's own enumeration has no independent
            # implementation left to rescan with, so it is an
            # explicit error, never a false no-hit.
            if digest_source == "cuda":
                candidates, rescan_attempted, rescan_verification = \
                    self._rescan_all_candidates(
                        header, target, start, count,
                        "legacy CUDA batch", bad)
                used = "cpu-rescan"
            else:
                self.fallback_events.append({
                    "start": start, "count": count,
                    "reason": f"{bad} CPU fallback candidate(s) "
                              f"failed CPU verification",
                    "retried_on": "none (explicit error)",
                    "verification_failures": bad})
                raise RuntimeError(
                    f"{bad} CPU fallback candidate(s) failed "
                    f"verification in batch enumeration; refusing "
                    f"to report an incomplete result")
        seconds = max(time.perf_counter() - t0, 1e-9)
        # Task 003.9: the enumeration itself (Python hashlib or
        # the legacy CUDA batch) computed exactly count digests:
        # that is the backend work, and on the legacy CUDA source
        # it is also the device work. Every target-meeting digest
        # cost exactly one verification computation
        # (raw_candidates of them); those and any rescan work are
        # verification-layer computations only.
        backend_hashes = count
        device_hashes = count if digest_source == "cuda" else 0
        verification_hashes = raw_candidates + rescan_verification
        return candidates, {
            "backend": used, "original_backend": digest_source,
            "hashes": backend_hashes + verification_hashes,
            "backend_hashes": backend_hashes,
            "verification_hashes": verification_hashes,
            "device_hashes": device_hashes,
            "seconds": seconds,
            "hashrate": backend_hashes / seconds,
            "coverage_per_second": count / seconds,
            "start": start,
            "requested_hashes": count,
            "unique_coverage": count,
            "researched_hashes": 0,
            "verification_rescan_hashes": rescan_attempted,
            "overflow_splits": 0,
            "candidate_count": raw_candidates,
            "verification_failures": bad,
            "rescanned": bool(rescan_attempted),
            "rescan_attempted": rescan_attempted,
            "coverage_status": (
                "complete: trusted CPU rescan after verification "
                "failure" if rescan_attempted else
                "complete: full-range enumeration, all candidates "
                "verified"),
            "fallback_events": len(self.fallback_events),
        }

    def benchmark_report(self, seconds_hint_batches=3, batch=65536):
        """Benchmark the selected backend on batch_search and
        report ACTUAL work, never requested work (Task 003.9).

        The pre-003.9 benchmark accumulated `hashes += batch`:
        the REQUESTED batch size. That undercounts actual
        computations whenever a backend does more work than
        requested (CUDA overflow recovery recomputes nonces, so
        device_hashes exceeds the request) and it silently folded
        verification work into a single rate. This report instead
        accumulates the per-batch statistics returned by
        batch_search and keeps every category separate
        (definitions in the module docstring):

        - elapsed_seconds: sum of the per-batch monotonic
          elapsed seconds reported by batch_search.
        - requested_hashes: what the caller asked for.
        - unique_coverage and coverage_per_second: distinct
          nonces covered, and that coverage per second.
        - backend_hashes and hashrate: actual computations by
          the selected backend, and that rate. This is the rate
          benchmark() returns.
        - device_hashes and device_hashes_per_second: CUDA
          device computations only; exactly 0 (with a note) when
          no CUDA device executed work. CPU verification work is
          never mixed into the device rate.
        - verification_hashes: independent verification and
          rescan computations, reported as overhead.
        - researched_hashes and researched_share: overflow
          recovery repeats, and their share of backend work, so
          recovery can never silently distort the rates.
        - overflow_splits and candidate_count totals.

        A batch that raises stops the run: the report is marked
        failed with the error and the partial totals of the
        completed batches only, and benchmark() raises instead
        of returning a clean-looking rate. Zero requested
        batches yields an all-zero report, not phantom hashes."""
        # A hard target (hit rate about 1 in 65536) keeps
        # candidate verification from dominating the measurement.
        header = bytes(80)
        target = (1 << 240)
        totals = {"requested_hashes": 0, "unique_coverage": 0,
                  "backend_hashes": 0, "device_hashes": 0,
                  "verification_hashes": 0, "researched_hashes": 0,
                  "overflow_splits": 0, "candidate_count": 0}
        elapsed = 0.0
        runs = []
        failed = False
        error = None
        for _ in range(seconds_hint_batches):
            try:
                _cands, stats = self.batch_search(
                    header, target, 0, batch)
            except Exception as exc:
                failed = True
                error = f"{type(exc).__name__}: {exc}"
                break
            elapsed += stats["seconds"]
            for key in totals:
                totals[key] += stats.get(key, 0) or 0
            runs.append({
                "backend": stats["backend"],
                "seconds": stats["seconds"],
                **{key: stats.get(key, 0) for key in totals}})
        backend_hashes = totals["backend_hashes"]
        device_hashes = totals["device_hashes"]
        report = {
            "backend": self.backend,
            "batches_requested": seconds_hint_batches,
            "batches_completed": len(runs),
            "batch": batch,
            "failed": failed,
            "error": error,
            "elapsed_seconds": elapsed,
            "hashrate": backend_hashes / elapsed if elapsed > 0
            else 0.0,
            "backend_hashes_per_second": backend_hashes / elapsed
            if elapsed > 0 else 0.0,
            "coverage_per_second": totals["unique_coverage"]
            / elapsed if elapsed > 0 else 0.0,
            "device_hashes_per_second": device_hashes / elapsed
            if elapsed > 0 else 0.0,
            "device_hashes_note": (
                None if device_hashes else
                "no CUDA device executed work in this benchmark; "
                "device rate is 0 by definition, not a GPU "
                "measurement"),
            "verification_share": (
                totals["verification_hashes"]
                / (backend_hashes + totals["verification_hashes"])
                if (backend_hashes
                    + totals["verification_hashes"]) > 0 else 0.0),
            "researched_share": (
                totals["researched_hashes"] / backend_hashes
                if backend_hashes > 0 else 0.0),
            "runs": runs,
        }
        report.update(totals)
        return report

    def benchmark(self, seconds_hint_batches=3, batch=65536):
        """Actual backend computations per second, measured over
        batch_search (Task 003.9). This keeps the historical
        float return contract used by the dashboard, the
        autonomous agent and mining/cpu/miner.py, but the number
        is now accumulated from the actual per-batch statistics
        (see benchmark_report), NOT from the requested batch
        size: the old implementation did `hashes += batch`,
        which undercounts whenever overflow recovery or any
        other backend behavior makes actual computations differ
        from the request. Raises RuntimeError when a batch
        fails, instead of returning a clean-looking rate over
        partial work."""
        report = self.benchmark_report(seconds_hint_batches, batch)
        if report["failed"]:
            raise RuntimeError(
                f"benchmark batch failed: {report['error']}")
        return report["hashrate"]

    def describe(self):
        return {
            "backend": self.backend,
            "requested": self.requested,
            "device_count": self.device_count,
            "fallback_reason": self.fallback_reason,
            "cuda_fallback_reason": self.cuda_fallback_reason,
            "c_backend": bool(self._c_lib),
            "v512_backend": bool(self._v_lib),
            "v512_reason": self.v512_reason,
            "native_impl": (
                "avx512-mb" if self.backend == "v512" else
                "openssl-c" if self.backend == "c" else None),
            "c_threads": C_THREADS,
            "c_attempt_counting": bool(
                self._c_lib and hasattr(self._c_lib, "bal_c_search2")),
            "cuda_context": bool(self._cuda_ctx),
            "cuda_context_reason": self.cuda_ctx_reason,
            "fallback_events": self.fallback_events,
            "last_search_stats": self.last_search_stats,
        }
