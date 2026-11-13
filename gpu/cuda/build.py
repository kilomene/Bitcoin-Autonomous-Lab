"""Build the CUDA shared library and the host validation binary.

Artifacts land in .local/cuda/ (gitignored): libbal_cuda.so and
host_sha256. Compilation succeeding is a build fact; it is NOT GPU
evidence. gpu.diagnostics reports the runtime facts separately.
"""

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


def build(log=print):
    os.makedirs(OUT, exist_ok=True)
    result = {"nvcc": find_nvcc(), "lib": None, "host_test": None}
    gpp = shutil.which("g++") or shutil.which("gcc")
    if gpp:
        host_out = os.path.join(OUT, "host_sha256")
        cmd = [gpp, "-O2", "-Wall", "-Wextra", "-Werror",
               "-I", HERE,
               os.path.join(HERE, "host_sha256.cpp"), "-o", host_out]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            result["host_test"] = host_out
        else:
            result["host_error"] = proc.stderr.strip()[-500:]
        log(f"host build: {'ok' if proc.returncode == 0 else 'FAILED'}")
    if result["nvcc"]:
        lib_out = os.path.join(OUT, "libbal_cuda.so")
        cmd = [result["nvcc"], "-O3", "-shared", "-Xcompiler", "-fPIC",
               "-I", HERE, os.path.join(HERE, "engine.cu"),
               "-o", lib_out]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            result["lib"] = lib_out
        else:
            result["cuda_error"] = proc.stderr.strip()[-500:]
        log(f"cuda build: {'ok' if proc.returncode == 0 else 'FAILED'}")
    else:
        log("nvcc not found: CUDA library not built")
    return result


if __name__ == "__main__":
    print(build())
    sys.exit(0)
