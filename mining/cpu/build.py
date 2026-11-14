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


if __name__ == "__main__":
    result = build()
    intrin = build_intrin()
    print({"batch": result, "intrin_ok": intrin["ok"]})
    sys.exit(0 if result["ok"] else 1)
