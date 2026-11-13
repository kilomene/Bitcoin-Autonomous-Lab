"""Privacy-safe GPU diagnostics.

Reports capability facts only: toolkit presence and version, whether
the lab CUDA library is built, whether a CUDA driver library exists,
whether NVIDIA device nodes exist, and the numeric result of asking
the runtime for a device count. No hostnames, device names, serials
or other machine identifiers are collected.
"""

import glob
import os
import subprocess

from gpu import engine as engine_mod
from gpu.cuda.build import find_nvcc


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
    eng = engine_mod.ComputeEngine()
    return {
        "nvcc_path": nvcc,
        "nvcc_version": version,
        "cuda_library_built": os.path.isfile(engine_mod.LIB_PATH),
        "c_library_built": os.path.isfile(engine_mod.C_LIB_PATH),
        "driver_library_present": bool(driver_libs),
        "nvidia_device_nodes": len(glob.glob("/dev/nvidia[0-9]*")),
        "compute_engine": eng.describe(),
        "verdict": ("GPU compute available" if eng.backend == "cuda"
                    else "No usable GPU on this machine: toolkit and "
                         "library build and validate, runtime reports "
                         "no device, CPU backend is authoritative"),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(collect(), indent=2))
