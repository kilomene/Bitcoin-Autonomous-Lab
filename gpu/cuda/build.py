"""Build the CUDA shared library and the host validation binaries.

Task 002 state vocabulary: every build and runtime fact is reported
separately and with its own name. A successful compilation is NOT
GPU execution; a successful host validation is NOT GPU execution; a
device count is NOT correct GPU hashing. Execution is only ever
reported by gpu.engine after a live self-test batch matches the CPU.

States reported in the result dict under "states":
  host_compiler:        path or None
  host_build:           "ok" | "failed" | "unavailable"
  cuda_compiler:        path or None
  cuda_build:           "ok" | "failed" | "unavailable"
  cuda_library:         path or None
  runtime:              "device_available" | "no_device" |
                        "runtime_error_<code>" | "library_not_built" |
                        "library_load_failed"
  device_count:         int or None
  execution_verified:   always False from this module

Exit status: 0 only when everything requested succeeded. The full
build (default) requires the host build AND the CUDA library build;
a missing CUDA compiler is therefore a failed full build (exit 1),
reported as such. --host-only requests just the host validation
build. Compiler output is preserved in the result on failure.
"""

import ctypes
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, ".local", "cuda")

NVCC_CANDIDATES = [
    os.environ.get("BAL_NVCC", ""),
    "/usr/local/cuda/bin/nvcc",
    "/usr/local/cuda-12.9/bin/nvcc",
    shutil.which("nvcc") or "",
]


def find_nvcc():
    for c in NVCC_CANDIDATES:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def _probe_runtime(lib_path):
    """Ask the built library for a device count. This establishes at
    most runtime and device presence, never execution correctness."""
    if not lib_path or not os.path.isfile(lib_path):
        return "library_not_built", None
    try:
        lib = ctypes.CDLL(lib_path)
        lib.bal_cuda_device_count.restype = ctypes.c_int
        n = lib.bal_cuda_device_count()
    except Exception:
        return "library_load_failed", None
    if n < 0:
        return f"runtime_error_{-n}", None
    if n == 0:
        return "no_device", 0
    return "device_available", n


def build(log=print, require_cuda=True):
    os.makedirs(OUT, exist_ok=True)
    result = {"nvcc": find_nvcc(), "lib": None, "host_test": None,
              "host_checks": None}
    states = {"host_compiler": None, "host_build": "unavailable",
              "cuda_compiler": result["nvcc"], "cuda_build": "unavailable",
              "cuda_library": None, "runtime": "library_not_built",
              "device_count": None, "execution_verified": False}
    gpp = shutil.which("g++") or shutil.which("gcc")
    states["host_compiler"] = gpp
    if gpp:
        for src, out_name, key, extra in (
                ("host_sha256.cpp", "host_sha256", "host_test", []),
                ("host_checks.cpp", "host_checks", "host_checks",
                 ["-pthread"])):
            out_path = os.path.join(OUT, out_name)
            cmd = [gpp, "-O2", "-Wall", "-Wextra", "-Werror",
                   "-I", HERE, os.path.join(HERE, src),
                   "-o", out_path] + extra
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode == 0:
                result[key] = out_path
            else:
                states["host_build"] = "failed"
                result.setdefault("host_error", proc.stderr.strip()[-800:])
            log(f"host build {src}: "
                f"{'ok' if proc.returncode == 0 else 'FAILED'}")
        if result["host_test"] and result["host_checks"]:
            states["host_build"] = "ok"
    if result["nvcc"]:
        lib_out = os.path.join(OUT, "libbal_cuda.so")
        cmd = [result["nvcc"], "-O3", "-shared", "-Xcompiler", "-fPIC",
               "-I", HERE, os.path.join(HERE, "engine.cu"),
               "-o", lib_out]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            result["lib"] = lib_out
            states["cuda_build"] = "ok"
            states["cuda_library"] = lib_out
        else:
            states["cuda_build"] = "failed"
            result["cuda_error"] = (proc.stderr or proc.stdout).strip()[-800:]
        log(f"cuda build: {'ok' if proc.returncode == 0 else 'FAILED'}")
    else:
        log("nvcc not found: CUDA library not built "
            "(state cuda_build=unavailable)")
    lib_candidate = result["lib"]
    if not lib_candidate:
        stale = os.path.join(OUT, "libbal_cuda.so")
        if os.path.isfile(stale):
            lib_candidate = stale  # probe what exists, label honestly
    runtime, n = _probe_runtime(lib_candidate)
    states["runtime"] = runtime
    states["device_count"] = n
    result["states"] = states
    result["ok"] = (states["host_build"] == "ok"
                    and (states["cuda_build"] == "ok" or not require_cuda))
    return result


if __name__ == "__main__":
    host_only = "--host-only" in sys.argv
    res = build(require_cuda=not host_only)
    print(res)
    sys.exit(0 if res["ok"] else 1)
