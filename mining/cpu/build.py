"""Build the C CPU libraries (.local/cpu/libbal_batch.so and the
experimental .local/cpu/libbal_intrin.so).

Task 001 build correction: a failed build is a failed build.

- A missing compiler, missing OpenSSL development headers, or a
  compiler error is reported clearly with the compiler output
  preserved in the result dict, and build() returns ok=False.
- Running this file as a script exits NON-ZERO when the production
  batch library fails to build or fails its smoke test. The old
  version printed the result dict and exited 0 either way, so the
  installer presented a failed native build as a successful
  optimized installation.
- The built library is smoke-tested before it is reported usable:
  it is loaded with ctypes and must reproduce hashlib digests on
  the genesis header and re-find the genesis nonce through the
  extended search entry point. A library that fails the smoke
  test is not presented as built.
- The SHA-intrinsics library is experimental. It is built and
  reported separately; its failure never fails the production
  build, and it is never selected as the production backend by
  this module.
- The AVX-512 multi-buffer library (bal_avx512_mb.c, the
  EXP-007 kernel integrated as a production backend on
  2026-11-14) is built as its own translation unit with a
  restricted flag set (-mavx512f -mavx512bw, never
  -march=native), linked with the flag-free CPUID probe
  (bal_avx512_probe.c).
- The AVX-512 DualMask library (bal_avx512_dual.c, the
  EXP-026 candidate C2 kernel integrated as a production
  backend on 2026-11-14 under the owner's explicit
  decision) is built exactly the same way, as
  libbal_v512dual.so: its own translation unit, the same
  restricted flag set, the same flag-free probe. Its
  failure is likewise reported loudly and separately and
  never fails the production C build: the engine treats a
  missing or unusable libbal_v512dual.so as "kernel not
  built" and falls back to the single-batch v512 backend.
- The AVX-512 flags batch library (bal_avx512_flags.c,
  the EXP-022 Y-084 flags-only batch integrated on
  2026-11-15 under the owner's explicit decision) is
  built exactly the same way again, as
  libbal_v512flags.so: its own translation unit, the
  same restricted flag set, the same flag-free probe.
  It exports only bal_v_batchf2 (a batch entry point,
  not a search entry point). Its failure is reported
  loudly and separately and never fails the production
  C build: the engine treats a missing or unusable
  libbal_v512flags.so as "flags batch not built" and
  the batch consumers stay on the preserved
  digest-materialising batch. Its failure is reported loudly and
  separately and never fails the production C build: the
  engine simply finds no libbal_v512.so (or a probe answer of
  unsupported) and stays on the OpenSSL C backend. When the
  probe reports the CPU cannot execute the kernel, the build
  still succeeds as "built but not runnable here": selection
  is a runtime decision, not a build outcome.
- When no native library can be built, callers fall back to the
  Python hashlib backend, and ComputeEngine.describe() reports
  backend "cpu" so the fallback is always identified, never
  silently presented as the optimized C path.
"""

import ctypes
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, ".local", "cpu")
LIB = os.path.join(OUT, "libbal_batch.so")
ILIB = os.path.join(OUT, "libbal_intrin.so")
VLIB = os.path.join(OUT, "libbal_v512.so")
VDLIB = os.path.join(OUT, "libbal_v512dual.so")
VFLIB = os.path.join(OUT, "libbal_v512flags.so")
# The exact CPU features the AVX-512 multi-buffer kernel
# requires, and the restricted compiler flags that keep the
# kernel object inside exactly that set. Determined from the
# kernel's intrinsics (see bal_avx512_probe.c) and confirmed
# by an objdump instruction audit of the built object.
V512_FEATURES = ("avx512f", "avx512bw")
V512_FLAGS = ["-mavx512f", "-mavx512bw"]
ALIB = os.path.join(OUT, "libbal_avx2.so")
MLIB = os.path.join(OUT, "libbal_shani.so")
# EXP-039 fallback tiers. The exact CPU features each kernel
# requires, and the restricted compiler flags that keep each
# kernel object inside exactly that set (never -march=native;
# see bal_fallback_probe.c). AVX2 tier: -mavx2. SHA-NI tier:
# -msha -mssse3, dispatched at streams 4 (the EXP-032 design
# point).
AVX2_FLAGS = ["-mavx2"]
SHANI_FLAGS = ["-msha", "-mssse3"]
SHANI_STREAMS = 4
OPENSSL_HEADER = os.path.join(os.sep, "usr", "include", "openssl", "sha.h")

GENESIS_HEADER = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GENESIS_NONCE = 2083236893


def _smoke_batch(lib_path):
    """Load the freshly built batch library and verify it against
    hashlib before anyone is told the native backend exists."""
    try:
        lib = ctypes.CDLL(lib_path)
    except OSError as exc:
        return f"built library failed to load: {exc}"
    lib.bal_c_batch.restype = ctypes.c_int
    lib.bal_c_batch.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_uint,
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
    count = 256
    hashes = ctypes.create_string_buffer(32 * count)
    flags = ctypes.create_string_buffer(count)
    target = ((1 << 256) - 1).to_bytes(32, "little")
    rc = lib.bal_c_batch(GENESIS_HEADER, 0, count, 2, target, hashes, flags)
    if rc != 0:
        return f"smoke batch returned {rc}"
    for n in range(count):
        want = hashlib.sha256(hashlib.sha256(
            GENESIS_HEADER[:76] + n.to_bytes(4, "little")).digest()).digest()
        if hashes.raw[32 * n:32 * n + 32] != want:
            return f"smoke digest mismatch at nonce {n}"
    if not hasattr(lib, "bal_c_search2"):
        return "library lacks the bal_c_search2 extended entry point"
    lib.bal_c_search2.restype = ctypes.c_int
    lib.bal_c_search2.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint,
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)]
    nonce = ctypes.c_uint32(0)
    attempted = ctypes.c_uint64(0)
    digest = ctypes.create_string_buffer(32)
    diff1 = (0xFFFF << 208).to_bytes(32, "little")
    rc = lib.bal_c_search2(GENESIS_HEADER, GENESIS_NONCE - 3, 10, 2,
                           diff1, ctypes.byref(nonce), digest,
                           ctypes.byref(attempted))
    if rc != 1 or nonce.value != GENESIS_NONCE:
        return f"smoke search failed: rc={rc} nonce={nonce.value}"
    if not (1 <= attempted.value <= 10):
        return f"smoke search attempted count implausible: {attempted.value}"
    return None


def _compile(cc, source, lib_path, extra, log):
    cmd = [cc, "-O3", "-march=native", "-shared", "-fPIC",
           "-Wno-deprecated-declarations", "-I", HERE,
           os.path.join(HERE, source), "-o", lib_path] + extra
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(f"build FAILED for {source}: compiler exited "
            f"{proc.returncode}")
        if proc.stderr.strip():
            log("compiler output: " + proc.stderr.strip()[-1200:])
        return proc.stderr.strip()[-1200:] or f"compiler exited {proc.returncode}"
    return None


def build(log=print):
    os.makedirs(OUT, exist_ok=True)
    cc = shutil.which("gcc") or shutil.which("cc")
    if not cc:
        log("no C compiler found (gcc/cc): the native CPU library "
            "cannot be built; the Python hashlib fallback will be "
            "used and reported as backend 'cpu'")
        return {"cc": None, "lib": None, "ok": False,
                "error": "no C compiler found"}
    if not os.path.isfile(OPENSSL_HEADER):
        log("OpenSSL development headers not found at "
            f"{OPENSSL_HEADER}: install libssl-dev (or equivalent); "
            "the Python hashlib fallback will be used and reported "
            "as backend 'cpu'")
        return {"cc": cc, "lib": None, "ok": False,
                "error": "missing OpenSSL development headers"}
    err = _compile(cc, "bal_batch.c", LIB, ["-lcrypto", "-lpthread"], log)
    if err is not None:
        return {"cc": cc, "lib": None, "ok": False, "error": err}
    smoke_err = _smoke_batch(LIB)
    if smoke_err is not None:
        log(f"C batch build: compiled but SMOKE TEST FAILED: {smoke_err}")
        return {"cc": cc, "lib": None, "ok": False,
                "error": f"smoke test failed: {smoke_err}"}
    log("C batch build: ok (compiled and smoke-tested against hashlib)")
    return {"cc": cc, "lib": LIB, "ok": True, "error": None}


def build_intrin(log=print):
    """Build the experimental SHA-intrinsics library. Reported
    separately; never a production selection criterion."""
    os.makedirs(OUT, exist_ok=True)
    cc = shutil.which("gcc") or shutil.which("cc")
    if not cc:
        return {"cc": None, "lib": None, "ok": False,
                "error": "no C compiler found"}
    err = _compile(cc, "bal_sha_intrin.c", ILIB,
                   ["-msha", "-lpthread"], log)
    if err is not None:
        return {"cc": cc, "lib": None, "ok": False, "error": err}
    log("SHA-intrinsics build: ok (experimental, not production)")
    return {"cc": cc, "lib": ILIB, "ok": True, "error": None}


def _smoke_v512(lib_path):
    """Verify the freshly built AVX-512 library before anyone
    is told it exists. The flag-free probe answers first; only
    when it reports the kernel can execute here are kernel
    entry points called, and then the batch must reproduce
    hashlib digests on the genesis header and the counted
    search must re-find the genesis nonce with wave-exact
    accounting (a started 16-lane wave completes, so the
    attempted count is the ceiling of the examined prefix to
    a whole wave per worker span). Returns (error, supported)
    where error is None on success."""
    try:
        lib = ctypes.CDLL(lib_path)
    except OSError as exc:
        return f"built library failed to load: {exc}", None
    if not hasattr(lib, "bal_v512_supported"):
        return "library lacks the bal_v512_supported probe", None
    lib.bal_v512_supported.restype = ctypes.c_int
    supported = lib.bal_v512_supported()
    if not supported:
        return None, 0
    if not hasattr(lib, "bal_v_batch2"):
        return "library lacks the bal_v_batch2 entry point", 1
    lib.bal_v_batch2.restype = ctypes.c_int
    lib.bal_v_batch2.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]
    count = 256
    hashes = ctypes.create_string_buffer(32 * count)
    flags = ctypes.create_string_buffer(count)
    target = ((1 << 256) - 1).to_bytes(32, "little")
    attempted = ctypes.c_uint64(0)
    backend = ctypes.c_uint64(0)
    rc = lib.bal_v_batch2(GENESIS_HEADER, 0, count, 2, target,
                          hashes, flags, ctypes.byref(attempted),
                          ctypes.byref(backend))
    if rc != 0:
        return f"smoke v512 batch returned {rc}", 1
    for n in range(count):
        want = hashlib.sha256(hashlib.sha256(
            GENESIS_HEADER[:76] + n.to_bytes(4, "little")).digest()).digest()
        if hashes.raw[32 * n:32 * n + 32] != want:
            return f"smoke v512 digest mismatch at nonce {n}", 1
    if attempted.value != count or backend.value != count:
        return (f"smoke v512 batch accounting off: attempted "
                f"{attempted.value} backend {backend.value} "
                f"count {count}", 1)
    if not hasattr(lib, "bal_v_search2"):
        return "library lacks the bal_v_search2 entry point", 1
    lib.bal_v_search2.restype = ctypes.c_int
    lib.bal_v_search2.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]
    nonce = ctypes.c_uint32(0)
    s_attempted = ctypes.c_uint64(0)
    s_backend = ctypes.c_uint64(0)
    digest = ctypes.create_string_buffer(32)
    diff1 = (0xFFFF << 208).to_bytes(32, "little")
    rc = lib.bal_v_search2(GENESIS_HEADER, GENESIS_NONCE - 3, 64, 2,
                           diff1, ctypes.byref(nonce), digest,
                           ctypes.byref(s_attempted),
                           ctypes.byref(s_backend))
    if rc != 1 or nonce.value != GENESIS_NONCE:
        return (f"smoke v512 search failed: rc={rc} "
                f"nonce={nonce.value}", 1)
    # Wave accounting: the winning nonce sits in the first wave
    # of one span; every started wave completes, so attempted
    # is a whole number of waves' worth of real nonces and the
    # backend lane count is a whole number of 16-lane waves.
    if s_backend.value % 16 or not (4 <= s_attempted.value
                                    <= s_backend.value):
        return (f"smoke v512 search accounting implausible: "
                f"attempted {s_attempted.value} backend "
                f"{s_backend.value}", 1)
    return None, 1


def build_v512(log=print):
    """Build the AVX-512 multi-buffer production library.

    The kernel translation unit is compiled with the
    restricted V512_FLAGS set (never -march=native) so the
    rest of the build and every other library stay loadable
    and runnable on machines without AVX-512; the probe
    translation unit is compiled with no vector flags at all.
    A build failure is loud (compiler output preserved in the
    result) but NEVER fails the production C build: the
    engine treats a missing or unusable libbal_v512.so as
    "kernel not built" and stays on the OpenSSL C backend.
    """
    os.makedirs(OUT, exist_ok=True)
    cc = shutil.which("gcc") or shutil.which("cc")
    if not cc:
        log("AVX-512 build FAILED: no C compiler found (gcc/cc); "
            "the engine will use the OpenSSL C backend")
        return {"cc": None, "lib": None, "ok": False,
                "supported": None, "error": "no C compiler found"}
    tmpdir = os.path.join(OUT, ".v512-build")
    os.makedirs(tmpdir, exist_ok=True)
    kernel_obj = os.path.join(tmpdir, "bal_avx512_mb.o")
    probe_obj = os.path.join(tmpdir, "bal_avx512_probe.o")
    base = ["-O3", "-shared", "-fPIC", "-I", HERE]
    cmd = [cc] + base + V512_FLAGS + [
        "-c", os.path.join(HERE, "bal_avx512_mb.c"), "-o", kernel_obj]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(f"AVX-512 build FAILED for bal_avx512_mb.c: compiler "
            f"exited {proc.returncode}; the engine will use the "
            f"OpenSSL C backend")
        if proc.stderr.strip():
            log("compiler output: " + proc.stderr.strip()[-1200:])
        return {"cc": cc, "lib": None, "ok": False,
                "supported": None,
                "error": proc.stderr.strip()[-1200:]
                or f"compiler exited {proc.returncode}"}
    cmd = [cc] + base + [
        "-c", os.path.join(HERE, "bal_avx512_probe.c"), "-o", probe_obj]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(f"AVX-512 build FAILED for bal_avx512_probe.c: "
            f"compiler exited {proc.returncode}; the engine "
            f"will use the OpenSSL C backend")
        if proc.stderr.strip():
            log("compiler output: " + proc.stderr.strip()[-1200:])
        return {"cc": cc, "lib": None, "ok": False,
                "supported": None,
                "error": proc.stderr.strip()[-1200:]
                or f"compiler exited {proc.returncode}"}
    cmd = [cc, "-shared", kernel_obj, probe_obj, "-o", VLIB,
           "-lpthread"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(f"AVX-512 build FAILED at link: compiler exited "
            f"{proc.returncode}; the engine will use the "
            f"OpenSSL C backend")
        if proc.stderr.strip():
            log("compiler output: " + proc.stderr.strip()[-1200:])
        return {"cc": cc, "lib": None, "ok": False,
                "supported": None,
                "error": proc.stderr.strip()[-1200:]
                or f"compiler exited {proc.returncode}"}
    smoke_err, supported = _smoke_v512(VLIB)
    if smoke_err is not None:
        log(f"AVX-512 build: compiled but SMOKE TEST FAILED: "
            f"{smoke_err}; the engine will use the OpenSSL C "
            f"backend")
        return {"cc": cc, "lib": None, "ok": False,
                "supported": supported,
                "error": f"smoke test failed: {smoke_err}"}
    if supported:
        log("AVX-512 multi-buffer build: ok (compiled with "
            "restricted flags, CPUID probe confirms AVX-512F "
            "and AVX-512BW, smoke-tested against hashlib)")
    else:
        log("AVX-512 multi-buffer build: ok (compiled and "
            "loadable; CPUID probe reports this CPU cannot "
            "execute it, so the engine will use the OpenSSL C "
            "backend here)")
    return {"cc": cc, "lib": VLIB, "ok": True,
            "supported": supported, "error": None}


def _smoke_v512dual(lib_path):
    """Verify the freshly built AVX-512 DualMask library
    before anyone is told it exists. Same discipline as
    _smoke_v512, with the audit D-1 rule applied to every
    symbol: existence is checked with hasattr BEFORE any
    argtypes assignment, so an incomplete library produces
    this function's designed error string, never an
    AttributeError. The flag-free probe answers first;
    only when it reports the kernel can execute here are
    kernel entry points called, and then the dual batch
    must reproduce hashlib digests on the genesis header
    and the DualMask counted search must re-find the
    genesis nonce with dual-atomic accounting (a started
    32-lane dual group completes; backend counts are
    whole 16-lane groups). Returns (error, supported)
    where error is None on success."""
    try:
        lib = ctypes.CDLL(lib_path)
    except OSError as exc:
        return f"built library failed to load: {exc}", None
    if not hasattr(lib, "bal_v512_supported"):
        return "library lacks the bal_v512_supported probe", None
    lib.bal_v512_supported.restype = ctypes.c_int
    supported = lib.bal_v512_supported()
    if not supported:
        return None, 0
    if not hasattr(lib, "bal_vd_batch2"):
        return "library lacks the bal_vd_batch2 entry point", 1
    lib.bal_vd_batch2.restype = ctypes.c_int
    lib.bal_vd_batch2.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]
    count = 256
    hashes = ctypes.create_string_buffer(32 * count)
    flags = ctypes.create_string_buffer(count)
    target = ((1 << 256) - 1).to_bytes(32, "little")
    attempted = ctypes.c_uint64(0)
    backend = ctypes.c_uint64(0)
    rc = lib.bal_vd_batch2(GENESIS_HEADER, 0, count, 2, target,
                           hashes, flags, ctypes.byref(attempted),
                           ctypes.byref(backend))
    if rc != 0:
        return f"smoke v512dual batch returned {rc}", 1
    for n in range(count):
        want = hashlib.sha256(hashlib.sha256(
            GENESIS_HEADER[:76] + n.to_bytes(4, "little")).digest()).digest()
        if hashes.raw[32 * n:32 * n + 32] != want:
            return f"smoke v512dual digest mismatch at nonce {n}", 1
    if attempted.value != count or backend.value != count:
        return (f"smoke v512dual batch accounting off: attempted "
                f"{attempted.value} backend {backend.value} "
                f"count {count}", 1)
    if not hasattr(lib, "bal_vd_search2"):
        return "library lacks the bal_vd_search2 entry point", 1
    lib.bal_vd_search2.restype = ctypes.c_int
    lib.bal_vd_search2.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]
    nonce = ctypes.c_uint32(0)
    s_attempted = ctypes.c_uint64(0)
    s_backend = ctypes.c_uint64(0)
    digest = ctypes.create_string_buffer(32)
    diff1 = (0xFFFF << 208).to_bytes(32, "little")
    rc = lib.bal_vd_search2(GENESIS_HEADER, GENESIS_NONCE - 3, 64, 2,
                            diff1, ctypes.byref(nonce), digest,
                            ctypes.byref(s_attempted),
                            ctypes.byref(s_backend))
    if rc != 1 or nonce.value != GENESIS_NONCE:
        return (f"smoke v512dual search failed: rc={rc} "
                f"nonce={nonce.value}", 1)
    # Dual-atomic accounting: the winning nonce sits in a
    # dual group of one span; every started group completes,
    # so the backend lane count is a whole number of 16-lane
    # groups and attempted is the real nonces behind them.
    if s_backend.value % 16 or not (4 <= s_attempted.value
                                    <= s_backend.value <= 64):
        return (f"smoke v512dual search accounting implausible: "
                f"attempted {s_attempted.value} backend "
                f"{s_backend.value}", 1)
    return None, 1


def build_v512dual(log=print):
    """Build the AVX-512 DualMask production library.

    Mirrors build_v512 exactly: the kernel translation unit
    is compiled with the restricted V512_FLAGS set (never
    -march=native), the probe translation unit with no
    vector flags at all, and a build failure is loud but
    NEVER fails the production C build: the engine treats
    a missing or unusable libbal_v512dual.so as "kernel
    not built" and falls back to the single-batch v512
    backend (and from there to the OpenSSL C backend).
    """
    os.makedirs(OUT, exist_ok=True)
    cc = shutil.which("gcc") or shutil.which("cc")
    if not cc:
        log("AVX-512 DualMask build FAILED: no C compiler "
            "found (gcc/cc); the engine will use the "
            "single-batch AVX-512 backend")
        return {"cc": None, "lib": None, "ok": False,
                "supported": None, "error": "no C compiler found"}
    tmpdir = os.path.join(OUT, ".v512dual-build")
    os.makedirs(tmpdir, exist_ok=True)
    kernel_obj = os.path.join(tmpdir, "bal_avx512_dual.o")
    probe_obj = os.path.join(tmpdir, "bal_avx512_probe.o")
    base = ["-O3", "-shared", "-fPIC", "-I", HERE]
    cmd = [cc] + base + V512_FLAGS + [
        "-c", os.path.join(HERE, "bal_avx512_dual.c"), "-o", kernel_obj]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(f"AVX-512 DualMask build FAILED for "
            f"bal_avx512_dual.c: compiler exited "
            f"{proc.returncode}; the engine will use the "
            f"single-batch AVX-512 backend")
        if proc.stderr.strip():
            log("compiler output: " + proc.stderr.strip()[-1200:])
        return {"cc": cc, "lib": None, "ok": False,
                "supported": None,
                "error": proc.stderr.strip()[-1200:]
                or f"compiler exited {proc.returncode}"}
    cmd = [cc] + base + [
        "-c", os.path.join(HERE, "bal_avx512_probe.c"), "-o", probe_obj]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(f"AVX-512 DualMask build FAILED for "
            f"bal_avx512_probe.c: compiler exited "
            f"{proc.returncode}; the engine will use the "
            f"single-batch AVX-512 backend")
        if proc.stderr.strip():
            log("compiler output: " + proc.stderr.strip()[-1200:])
        return {"cc": cc, "lib": None, "ok": False,
                "supported": None,
                "error": proc.stderr.strip()[-1200:]
                or f"compiler exited {proc.returncode}"}
    cmd = [cc, "-shared", kernel_obj, probe_obj, "-o", VDLIB,
           "-lpthread"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(f"AVX-512 DualMask build FAILED at link: compiler "
            f"exited {proc.returncode}; the engine will use "
            f"the single-batch AVX-512 backend")
        if proc.stderr.strip():
            log("compiler output: " + proc.stderr.strip()[-1200:])
        return {"cc": cc, "lib": None, "ok": False,
                "supported": None,
                "error": proc.stderr.strip()[-1200:]
                or f"compiler exited {proc.returncode}"}
    smoke_err, supported = _smoke_v512dual(VDLIB)
    if smoke_err is not None:
        log(f"AVX-512 DualMask build: compiled but SMOKE TEST "
            f"FAILED: {smoke_err}; the engine will use the "
            f"single-batch AVX-512 backend")
        return {"cc": cc, "lib": None, "ok": False,
                "supported": supported,
                "error": f"smoke test failed: {smoke_err}"}
    if supported:
        log("AVX-512 DualMask build: ok (compiled with "
            "restricted flags, CPUID probe confirms AVX-512F "
            "and AVX-512BW, smoke-tested against hashlib)")
    else:
        log("AVX-512 DualMask build: ok (compiled and "
            "loadable; CPUID probe reports this CPU cannot "
            "execute it, so the engine will use the "
            "single-batch AVX-512 backend here)")
    return {"cc": cc, "lib": VDLIB, "ok": True,
            "supported": supported, "error": None}


def _smoke_v512flags(lib_path):
    """Verify the freshly built AVX-512 flags batch
    library before anyone is told it exists. Same
    discipline as _smoke_v512dual, with the audit D-1
    rule applied to every symbol: existence is checked
    with hasattr BEFORE any argtypes assignment. The
    flag-free probe answers first; only when it reports
    the kernel can execute here is the flags entry
    called, and then, on the genesis header: at the
    all-ones target every one of 256 flag bits must be
    set and every extracted digest must equal hashlib;
    at a difficulty-1-style target the flag bits must
    equal an independent hashlib recount bit for bit,
    the extracted digests must equal hashlib on the
    flagged lanes, the counted accounting must be
    exact, and the pure flags mode (digests NULL) must
    produce identical bits. Returns (error, supported)
    where error is None on success."""
    try:
        lib = ctypes.CDLL(lib_path)
    except OSError as exc:
        return f"built library failed to load: {exc}", None
    if not hasattr(lib, "bal_v512_supported"):
        return "library lacks the bal_v512_supported probe", None
    lib.bal_v512_supported.restype = ctypes.c_int
    supported = lib.bal_v512_supported()
    if not supported:
        return None, 0
    if not hasattr(lib, "bal_v_batchf2"):
        return "library lacks the bal_v_batchf2 entry point", 1
    lib.bal_v_batchf2.restype = ctypes.c_int
    lib.bal_v_batchf2.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]
    count = 256
    flagbytes = (count + 7) // 8

    def want_digest(n):
        return hashlib.sha256(hashlib.sha256(
            GENESIS_HEADER[:76] + n.to_bytes(4, "little")
        ).digest()).digest()

    def run(target_int, extract=True):
        flagbits = ctypes.create_string_buffer(flagbytes)
        digests = (ctypes.create_string_buffer(32 * count)
                   if extract else None)
        attempted = ctypes.c_uint64(0)
        backend = ctypes.c_uint64(0)
        rc = lib.bal_v_batchf2(
            GENESIS_HEADER, 0, count, 2,
            target_int.to_bytes(32, "little"), flagbits, digests,
            ctypes.byref(attempted), ctypes.byref(backend))
        return rc, flagbits, digests, attempted.value, backend.value

    rc, flagbits, digests, attempted, backend = run((1 << 256) - 1)
    if rc != 0:
        return f"smoke v512flags batch returned {rc}", 1
    if flagbits.raw != b"\xff" * flagbytes:
        return "smoke v512flags all-ones target flag bits wrong", 1
    for n in range(count):
        if digests.raw[32 * n:32 * n + 32] != want_digest(n):
            return f"smoke v512flags digest mismatch at nonce {n}", 1
    if attempted != count or backend != count:
        return (f"smoke v512flags batch accounting off: attempted "
                f"{attempted} backend {backend} count {count}", 1)
    diff1 = 0xFFFF << 208
    rc, flagbits, digests, attempted, backend = run(diff1)
    if rc != 0:
        return f"smoke v512flags diff1 batch returned {rc}", 1
    if attempted != count or backend != count:
        return (f"smoke v512flags diff1 accounting off: attempted "
                f"{attempted} backend {backend} count {count}", 1)
    bits = flagbits.raw
    for n in range(count):
        want = want_digest(n)
        flagged = (bits[n >> 3] >> (n & 7)) & 1
        meets = int.from_bytes(want, "little") <= diff1
        if flagged != (1 if meets else 0):
            return (f"smoke v512flags flag bit mismatch at nonce "
                    f"{n}", 1)
        if meets and digests.raw[32 * n:32 * n + 32] != want:
            return (f"smoke v512flags extracted digest mismatch "
                    f"at nonce {n}", 1)
    rc, pure_bits, _d, _a, _b = run(diff1, extract=False)
    if rc != 0 or pure_bits.raw != bits:
        return "smoke v512flags pure mode bits differ", 1
    return None, 1


def build_v512flags(log=print):
    """Build the AVX-512 flags batch production library.

    Mirrors build_v512dual exactly: the kernel
    translation unit is compiled with the restricted
    V512_FLAGS set (never -march=native), the probe
    translation unit with no vector flags at all, and a
    build failure is loud but NEVER fails the production
    C build: the engine treats a missing or unusable
    libbal_v512flags.so as "flags batch not built" and
    the batch consumers stay on the preserved
    digest-materialising batch.
    """
    os.makedirs(OUT, exist_ok=True)
    cc = shutil.which("gcc") or shutil.which("cc")
    if not cc:
        log("AVX-512 flags batch build FAILED: no C compiler "
            "found (gcc/cc); the batch consumers will use "
            "the preserved digest-materialising batch")
        return {"cc": None, "lib": None, "ok": False,
                "supported": None, "error": "no C compiler found"}
    tmpdir = os.path.join(OUT, ".v512flags-build")
    os.makedirs(tmpdir, exist_ok=True)
    kernel_obj = os.path.join(tmpdir, "bal_avx512_flags.o")
    probe_obj = os.path.join(tmpdir, "bal_avx512_probe.o")
    base = ["-O3", "-shared", "-fPIC", "-I", HERE]
    cmd = [cc] + base + V512_FLAGS + [
        "-c", os.path.join(HERE, "bal_avx512_flags.c"),
        "-o", kernel_obj]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(f"AVX-512 flags batch build FAILED for "
            f"bal_avx512_flags.c: compiler exited "
            f"{proc.returncode}; the batch consumers will "
            f"use the preserved digest-materialising batch")
        if proc.stderr.strip():
            log("compiler output: " + proc.stderr.strip()[-1200:])
        return {"cc": cc, "lib": None, "ok": False,
                "supported": None,
                "error": proc.stderr.strip()[-1200:]
                or f"compiler exited {proc.returncode}"}
    cmd = [cc] + base + [
        "-c", os.path.join(HERE, "bal_avx512_probe.c"),
        "-o", probe_obj]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(f"AVX-512 flags batch build FAILED for "
            f"bal_avx512_probe.c: compiler exited "
            f"{proc.returncode}; the batch consumers will "
            f"use the preserved digest-materialising batch")
        if proc.stderr.strip():
            log("compiler output: " + proc.stderr.strip()[-1200:])
        return {"cc": cc, "lib": None, "ok": False,
                "supported": None,
                "error": proc.stderr.strip()[-1200:]
                or f"compiler exited {proc.returncode}"}
    cmd = [cc, "-shared", kernel_obj, probe_obj, "-o", VFLIB,
           "-lpthread"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(f"AVX-512 flags batch build FAILED at link: "
            f"compiler exited {proc.returncode}; the batch "
            f"consumers will use the preserved "
            f"digest-materialising batch")
        if proc.stderr.strip():
            log("compiler output: " + proc.stderr.strip()[-1200:])
        return {"cc": cc, "lib": None, "ok": False,
                "supported": None,
                "error": proc.stderr.strip()[-1200:]
                or f"compiler exited {proc.returncode}"}
    smoke_err, supported = _smoke_v512flags(VFLIB)
    if smoke_err is not None:
        log(f"AVX-512 flags batch build: compiled but SMOKE "
            f"TEST FAILED: {smoke_err}; the batch consumers "
            f"will use the preserved digest-materialising "
            f"batch")
        return {"cc": cc, "lib": None, "ok": False,
                "supported": supported,
                "error": f"smoke test failed: {smoke_err}"}
    if supported:
        log("AVX-512 flags batch build: ok (compiled with "
            "restricted flags, CPUID probe confirms AVX-512F "
            "and AVX-512BW, smoke-tested against hashlib)")
    else:
        log("AVX-512 flags batch build: ok (compiled and "
            "loadable; CPUID probe reports this CPU cannot "
            "execute it, so the batch consumers will use "
            "the preserved digest-materialising batch here)")
    return {"cc": cc, "lib": VFLIB, "ok": True,
            "supported": supported, "error": None}


def _smoke_avx2(lib_path):
    """Verify the freshly built AVX2 library before anyone
    is told it exists. Same discipline as _smoke_v512, with
    the audit D-1 rule applied to every symbol: existence is
    checked with hasattr BEFORE any argtypes assignment. The
    flag-free probe answers first; only when it reports the
    kernel can execute here are kernel entry points called,
    and then the batch must reproduce hashlib digests on the
    genesis header and the counted search must re-find the
    genesis nonce with group-exact accounting (a started
    8-lane group completes, so the backend lane count is a
    whole number of groups). Returns (error, supported)
    where error is None on success."""
    try:
        lib = ctypes.CDLL(lib_path)
    except OSError as exc:
        return f"built library failed to load: {exc}", None
    if not hasattr(lib, "bal_avx2_supported"):
        return "library lacks the bal_avx2_supported probe", None
    lib.bal_avx2_supported.restype = ctypes.c_int
    supported = lib.bal_avx2_supported()
    if not supported:
        return None, 0
    if not hasattr(lib, "bal_a_batch2"):
        return "library lacks the bal_a_batch2 entry point", 1
    lib.bal_a_batch2.restype = ctypes.c_int
    lib.bal_a_batch2.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]
    count = 256
    hashes = ctypes.create_string_buffer(32 * count)
    flags = ctypes.create_string_buffer(count)
    target = ((1 << 256) - 1).to_bytes(32, "little")
    attempted = ctypes.c_uint64(0)
    backend = ctypes.c_uint64(0)
    rc = lib.bal_a_batch2(GENESIS_HEADER, 0, count, 2, target,
                          hashes, flags, ctypes.byref(attempted),
                          ctypes.byref(backend))
    if rc != 0:
        return f"smoke avx2 batch returned {rc}", 1
    for n in range(count):
        want = hashlib.sha256(hashlib.sha256(
            GENESIS_HEADER[:76] + n.to_bytes(4, "little")).digest()).digest()
        if hashes.raw[32 * n:32 * n + 32] != want:
            return f"smoke avx2 digest mismatch at nonce {n}", 1
    if attempted.value != count or backend.value != count:
        return (f"smoke avx2 batch accounting off: attempted "
                f"{attempted.value} backend {backend.value} "
                f"count {count}", 1)
    if not hasattr(lib, "bal_a_search2"):
        return "library lacks the bal_a_search2 entry point", 1
    lib.bal_a_search2.restype = ctypes.c_int
    lib.bal_a_search2.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]
    nonce = ctypes.c_uint32(0)
    s_attempted = ctypes.c_uint64(0)
    s_backend = ctypes.c_uint64(0)
    digest = ctypes.create_string_buffer(32)
    diff1 = (0xFFFF << 208).to_bytes(32, "little")
    rc = lib.bal_a_search2(GENESIS_HEADER, GENESIS_NONCE - 3, 64, 2,
                           diff1, ctypes.byref(nonce), digest,
                           ctypes.byref(s_attempted),
                           ctypes.byref(s_backend))
    if rc != 1 or nonce.value != GENESIS_NONCE:
        return (f"smoke avx2 search failed: rc={rc} "
                f"nonce={nonce.value}", 1)
    if s_backend.value % 8 or not (4 <= s_attempted.value
                                   <= s_backend.value):
        return (f"smoke avx2 search accounting implausible: "
                f"attempted {s_attempted.value} backend "
                f"{s_backend.value}", 1)
    return None, 1


def _smoke_shani(lib_path):
    """Verify the freshly built SHA-NI multi-stream library
    before anyone is told it exists. Same discipline as
    _smoke_avx2 (audit D-1: hasattr before argtypes). The
    H-01 ABI reports out_attempted only: the kernel hashes
    no dummy lanes, so attempted is exact (== count on a
    completed batch). The search smoke re-finds the genesis
    nonce at streams 4 and checks the returned digest
    against hashlib. Returns (error, supported)."""
    try:
        lib = ctypes.CDLL(lib_path)
    except OSError as exc:
        return f"built library failed to load: {exc}", None
    if not hasattr(lib, "bal_shani_supported"):
        return "library lacks the bal_shani_supported probe", None
    lib.bal_shani_supported.restype = ctypes.c_int
    supported = lib.bal_shani_supported()
    if not supported:
        return None, 0
    if not hasattr(lib, "bal_m_batch2"):
        return "library lacks the bal_m_batch2 entry point", 1
    lib.bal_m_batch2.restype = ctypes.c_int
    lib.bal_m_batch2.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_int, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint64)]
    count = 256
    hashes = ctypes.create_string_buffer(32 * count)
    flags = ctypes.create_string_buffer(count)
    target = ((1 << 256) - 1).to_bytes(32, "little")
    attempted = ctypes.c_uint64(0)
    rc = lib.bal_m_batch2(GENESIS_HEADER, 0, count, 2,
                          SHANI_STREAMS, target, hashes, flags,
                          ctypes.byref(attempted))
    if rc != 0:
        return f"smoke shani batch returned {rc}", 1
    for n in range(count):
        want = hashlib.sha256(hashlib.sha256(
            GENESIS_HEADER[:76] + n.to_bytes(4, "little")).digest()).digest()
        if hashes.raw[32 * n:32 * n + 32] != want:
            return f"smoke shani digest mismatch at nonce {n}", 1
    if attempted.value != count:
        return (f"smoke shani batch accounting off: attempted "
                f"{attempted.value} count {count}", 1)
    if not hasattr(lib, "bal_m_search2"):
        return "library lacks the bal_m_search2 entry point", 1
    lib.bal_m_search2.restype = ctypes.c_int
    lib.bal_m_search2.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_int, ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint64)]
    nonce = ctypes.c_uint32(0)
    s_attempted = ctypes.c_uint64(0)
    digest = ctypes.create_string_buffer(32)
    diff1 = (0xFFFF << 208).to_bytes(32, "little")
    rc = lib.bal_m_search2(GENESIS_HEADER, GENESIS_NONCE - 3, 64, 2,
                           SHANI_STREAMS, diff1,
                           ctypes.byref(nonce), digest,
                           ctypes.byref(s_attempted))
    if rc != 1 or nonce.value != GENESIS_NONCE:
        return (f"smoke shani search failed: rc={rc} "
                f"nonce={nonce.value}", 1)
    want = hashlib.sha256(hashlib.sha256(
        GENESIS_HEADER[:76]
        + GENESIS_NONCE.to_bytes(4, "little")).digest()).digest()
    if digest.raw != want:
        return "smoke shani search digest mismatch", 1
    if not (1 <= s_attempted.value <= 64):
        return (f"smoke shani search accounting implausible: "
                f"attempted {s_attempted.value}", 1)
    return None, 1


def _build_fallback_tier(log, label, source, probe_source,
                         flags, lib_path, tmpname, smoke,
                         fallback_note):
    """Shared builder for the EXP-039 fallback tiers. The
    kernel translation unit is compiled with the tier's
    restricted flag set (never -march=native), the probe
    translation unit with no vector flags at all, and a
    build failure is loud but NEVER fails the production C
    build: the engine treats a missing or unusable library
    as "kernel not built" and falls back to the next tier.
    """
    os.makedirs(OUT, exist_ok=True)
    cc = shutil.which("gcc") or shutil.which("cc")
    if not cc:
        log(f"{label} build FAILED: no C compiler found "
            f"(gcc/cc); {fallback_note}")
        return {"cc": None, "lib": None, "ok": False,
                "supported": None, "error": "no C compiler found"}
    tmpdir = os.path.join(OUT, tmpname)
    os.makedirs(tmpdir, exist_ok=True)
    kernel_obj = os.path.join(
        tmpdir, os.path.splitext(source)[0] + ".o")
    probe_obj = os.path.join(
        tmpdir, os.path.splitext(probe_source)[0] + ".o")
    base = ["-O3", "-shared", "-fPIC", "-I", HERE]
    for src, obj, extra in ((source, kernel_obj, flags),
                            (probe_source, probe_obj, [])):
        cmd = [cc] + base + extra + [
            "-c", os.path.join(HERE, src), "-o", obj]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            log(f"{label} build FAILED for {src}: compiler "
                f"exited {proc.returncode}; {fallback_note}")
            if proc.stderr.strip():
                log("compiler output: " + proc.stderr.strip()[-1200:])
            return {"cc": cc, "lib": None, "ok": False,
                    "supported": None,
                    "error": proc.stderr.strip()[-1200:]
                    or f"compiler exited {proc.returncode}"}
    cmd = [cc, "-shared", kernel_obj, probe_obj, "-o", lib_path,
           "-lpthread"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(f"{label} build FAILED at link: compiler exited "
            f"{proc.returncode}; {fallback_note}")
        if proc.stderr.strip():
            log("compiler output: " + proc.stderr.strip()[-1200:])
        return {"cc": cc, "lib": None, "ok": False,
                "supported": None,
                "error": proc.stderr.strip()[-1200:]
                or f"compiler exited {proc.returncode}"}
    smoke_err, supported = smoke(lib_path)
    if smoke_err is not None:
        log(f"{label} build: compiled but SMOKE TEST FAILED: "
            f"{smoke_err}; {fallback_note}")
        return {"cc": cc, "lib": None, "ok": False,
                "supported": supported,
                "error": f"smoke test failed: {smoke_err}"}
    if supported:
        log(f"{label} build: ok (compiled with restricted "
            f"flags, CPUID probe confirms the feature set, "
            f"smoke-tested against hashlib)")
    else:
        log(f"{label} build: ok (compiled and loadable; CPUID "
            f"probe reports this CPU cannot execute it, so "
            f"the engine will use the next tier here)")
    return {"cc": cc, "lib": lib_path, "ok": True,
            "supported": supported, "error": None}


def build_avx2(log=print):
    """Build the AVX2 multi-buffer fallback library
    (EXP-039). Restricted -mavx2 flags; flag-free probe."""
    return _build_fallback_tier(
        log, "AVX2 multi-buffer", "bal_avx2_mb.c",
        "bal_fallback_probe.c", AVX2_FLAGS, ALIB,
        ".avx2-build", _smoke_avx2,
        "the engine will use the OpenSSL C backend")


def build_shani(log=print):
    """Build the SHA-NI multi-stream fallback library
    (EXP-039). Restricted -msha -mssse3 flags; flag-free
    probe."""
    return _build_fallback_tier(
        log, "SHA-NI multi-stream", "bal_shani_streams.c",
        "bal_fallback_probe.c", SHANI_FLAGS, MLIB,
        ".shani-build", _smoke_shani,
        "the engine will use the next fallback tier")


if __name__ == "__main__":
    result = build()
    intrin = build_intrin()
    v512 = build_v512()
    v512dual = build_v512dual()
    v512flags = build_v512flags()
    avx2 = build_avx2()
    shani = build_shani()
    print({"batch": result, "intrin_ok": intrin["ok"],
           "v512": v512, "v512dual": v512dual,
           "v512flags": v512flags, "avx2": avx2,
           "shani": shani})
    sys.exit(0 if result["ok"] else 1)
