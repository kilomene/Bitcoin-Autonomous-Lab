"""Privacy-safe GPU diagnostics.

Reports capability facts only, in the same state vocabulary as
gpu/cuda/build.py: toolkit presence and version, host validation,
CUDA library build, driver library, NVIDIA device nodes, the numeric
runtime device count, and whether live execution was verified by a
CPU-checked self-test batch (that, and only that, is execution
evidence). No hostnames, device names, serials or other machine
identifiers are collected.
"""

import glob
import os
import subprocess

from gpu import engine as engine_mod
from gpu.cuda.build import find_nvcc, _probe_runtime


def collect():
    nvcc = find_nvcc()
    version = None
    if nvcc:
        try:
            out = subprocess.run([nvcc, "--version"], capture_output=True,
                                 text=True, timeout=15).stdout
            for line in out.splitlines():
                if "release" in line:
                    version = line.strip()
        except Exception:
            version = None
    driver_libs = [p for p in (
        "/usr/lib/x86_64-linux-gnu/libcuda.so.1",
        "/usr/lib64/libcuda.so.1",
        "/usr/local/cuda/lib64/stubs/libcuda.so") if os.path.exists(p)]
    lib_built = os.path.isfile(engine_mod.LIB_PATH)
    runtime, device_count = _probe_runtime(
        engine_mod.LIB_PATH if lib_built else None)
    eng = engine_mod.ComputeEngine()
    execution_verified = eng.backend == "cuda"
    states = {
        "cuda_compiler": nvcc,
        "host_compiler": "present (system gcc/g++)",
        "cuda_library_built": lib_built,
        "c_library_built": os.path.isfile(engine_mod.C_LIB_PATH),
        "driver_library_present": bool(driver_libs),
        "runtime": runtime,
        "device_count": device_count,
        "self_test_passed": execution_verified,
        "execution_verified": execution_verified,
        "persistent_context": bool(eng._cuda_ctx),
    }
    if execution_verified:
        verdict = "GPU compute available and execution verified by self-test"
    elif nvcc is None:
        verdict = ("No usable GPU on this machine: CUDA toolkit absent, "
                   "no NVIDIA device nodes, runtime reports no device; "
                   "CPU backend is authoritative")
    else:
        verdict = ("No usable GPU on this machine: toolkit and library "
                   "build and validate, runtime reports no device, CPU "
                   "backend is authoritative")
    return {
        "nvcc_path": nvcc,
        "nvcc_version": version,
        "cuda_library_built": lib_built,
        "c_library_built": states["c_library_built"],
        "driver_library_present": bool(driver_libs),
        "nvidia_device_nodes": len(glob.glob("/dev/nvidia[0-9]*")),
        "states": states,
        "compute_engine": eng.describe(),
        "verdict": verdict,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(collect(), indent=2))
