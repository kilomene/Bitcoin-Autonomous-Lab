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
  (bal_avx512_probe.c). Its failure is reported loudly and
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
# The exact CPU features the AVX-512 multi-buffer kernel
# requires, and the restricted compiler flags that keep the
# kernel object inside exactly that set. Determined from the
# kernel's intrinsics (see bal_avx512_probe.c) and confirmed
# by an objdump instruction audit of the built object.
V512_FEATURES = ("avx512f", "avx512bw")
V512_FLAGS = ["-mavx512f", "-mavx512bw"]
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


if __name__ == "__main__":
    result = build()
    intrin = build_intrin()
    v512 = build_v512()
    print({"batch": result, "intrin_ok": intrin["ok"],
           "v512": v512})
    sys.exit(0 if result["ok"] else 1)
