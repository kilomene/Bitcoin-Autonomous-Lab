#!/usr/bin/env python3
"""FPGA and ASIC aspect tests.

- Simulates the Verilog RTL (fpga/) with Icarus Verilog: the core
  must reproduce the FIPS SHA-256("abc") digest, and the miner
  must find the genesis nonce as the first qualifying nonce in
  its window with the genesis hash.
- Runs the FPGA synthesis (yosys synth_xilinx) if its report is
  missing and checks the miner's resource counts are sane.
- Runs the ASIC flow (gate-level synthesis) if its netlist is
  missing, then simulates the GATE-LEVEL NETLIST against the same
  testbench: pre-layout functional verification of the ASIC design.
"""

import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")


def run(cmd, timeout=600):
    p = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True,
                       text=True, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


def main():
    rc, out = run("iverilog -o /tmp/bal_tb_rtl.vvp fpga/sha256_core.v "
                  "fpga/sha256d_miner.v fpga/tb_miner.v && "
                  "timeout 120 vvp /tmp/bal_tb_rtl.vvp")
    assert rc == 0 and "ALL RTL TESTS PASSED" in out, out[-2000:]
    print("ok: RTL simulation: core matches FIPS abc vector; miner "
          "found the genesis nonce (first qualifier, 3 hashes)")

    if not os.path.exists(os.path.join(ROOT, "fpga/build/synth_xilinx.log")):
        rc, out = run("./fpga/synth.sh", timeout=900)
        assert rc == 0, out[-2000:]
    log = open(os.path.join(ROOT, "fpga/build/synth_xilinx.log")).read()
    tail = log[log.rindex("=== sha256d_miner ==="):]
    assert "LUT6" in tail and "FDRE" in tail, tail[-500:]
    print("ok: FPGA synthesis report present (yosys synth_xilinx, xc7)")

    if not os.path.exists(os.path.join(ROOT, "asic/build/miner_netlist.v")):
        rc, out = run("./asic/flow.sh", timeout=900)
        assert rc == 0, out[-2000:]
    rc, out = run("iverilog -o /tmp/bal_tb_net.vvp "
                  "/usr/share/yosys/simlib.v /usr/share/yosys/simcells.v "
                  "asic/build/miner_netlist.v fpga/tb_miner.v && "
                  "timeout 300 vvp /tmp/bal_tb_net.vvp")
    assert rc == 0 and "ALL RTL TESTS PASSED" in out, out[-2000:]
    print("ok: ASIC gate-level netlist simulation: same testbench, "
          "same FIPS and genesis results")
    print("ALL RTL ASPECT TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
