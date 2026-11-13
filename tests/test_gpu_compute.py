#!/usr/bin/env python3
"""Task 004 (GPU half) tests: CUDA build, host validation, dispatch.

The honest contract on a machine with no NVIDIA GPU:
- nvcc compiles gpu/cuda/engine.cu into libbal_cuda.so.
- The SAME sha256.h compiled for the host CPU matches hashlib
  exactly (abc vector, genesis hash, FIPS million-byte vector,
  regtest target hit count over 100k nonces computed independently).
- The runtime reports CUDA error 35 (insufficient driver), the
  ComputeEngine selects CPU with that reason recorded, and CPU batch
  results are independently verified.
On a machine WITH a GPU, the engine must select cuda and pass its
self-test; the assertions below accept either world but require the
record to match the hardware.
"""

import hashlib
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gpu import diagnostics
from gpu.cuda.build import build
from gpu.engine import ComputeEngine, cpu_digest


def genesis_header():
    return bytes.fromhex(
        "01000000" + "00" * 32
        + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
        + "29ab5f49" + "ffff001d" + "1dac2b7c")


def main():
    result = build(log=lambda *a: None)
    assert result["nvcc"], "nvcc must be installed (CUDA toolkit)"
    assert result["lib"], result
    assert result["host_test"], result
    print(f"ok: nvcc build produced libbal_cuda.so and host_sha256 "
          f"({result['nvcc']})")

    out = subprocess.run([result["host_test"]], capture_output=True,
                         text=True).stdout.splitlines()
    assert out[0] == hashlib.sha256(b"abc").hexdigest()
    assert out[1] == "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
    assert out[3] == hashlib.sha256(b"a" * 1_000_000).hexdigest()
    target = (0x7FFFFF << 232)
    header = genesis_header()
    expect = 0
    import struct as _s
    for n in range(100000):
        h = header[:76] + _s.pack("<I", n)
        d = hashlib.sha256(hashlib.sha256(h).digest()).digest()
        if int.from_bytes(d, "little") <= target:
            expect += 1
    assert int(out[2]) == expect, (out[2], expect)
    print(f"ok: host build of the CUDA SHA-256 source matches hashlib "
          f"on all vectors ({expect} target hits in 100k nonces)")

    diag = diagnostics.collect()
    eng = ComputeEngine()
    if diag["nvidia_device_nodes"] == 0:
        assert eng.backend == "cpu", eng.describe()
        assert eng.fallback_reason and "35" in eng.fallback_reason, \
            eng.fallback_reason
        print(f"ok: no GPU present; engine on CPU with recorded reason: "
              f"{eng.fallback_reason}")
    else:
        assert eng.backend == "cuda", eng.describe()
        print("ok: GPU present and CUDA backend selected after self-test")

    # Batch bounds are enforced.
    for bad in ((bytes(80), 1 << 200, 0, 0),
                (bytes(79), 1 << 200, 0, 16),
                (bytes(80), 1 << 200, (1 << 32) - 8, 16)):
        try:
            eng.batch_search(*bad)
            raise AssertionError(f"expected ValueError for {bad}")
        except ValueError:
            pass
    print("ok: batch bounds and header length enforced")

    # CPU batch candidates verify independently.
    header = genesis_header()
    cands, stats = eng.batch_search(header, 0x7FFFFF << 232, 0, 8192)
    assert stats["backend"] == eng.backend
    assert cands, "regtest target over 8192 nonces must hit"
    for c in cands:
        assert cpu_digest(header, c["nonce"])[::-1].hex() == c["hash"]
    bench = eng.benchmark()
    assert bench > 10000, bench
    print(f"ok: batch search candidates verified; benchmark "
          f"{bench:,.0f} H/s on backend {eng.backend}")
    print("ALL GPU COMPUTE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
