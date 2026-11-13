#!/bin/sh
# FPGA synthesis for the lab RTL: yosys synth_xilinx (generic
# Xilinx 7-series target), resource report only. No board is
# attached to this VM, so no bitstream is programmed here; the
# deliverable is the synthesized design plus its resource counts.
set -e
cd "$(dirname "$0")/.."
mkdir -p fpga/build
cat > fpga/build/synth.ys << 'YS'
read_verilog fpga/sha256_core.v fpga/sha256d_miner.v
synth_xilinx -family xc7 -top sha256d_miner
tee -o fpga/build/synth_xilinx.log stat
write_json fpga/build/miner_xc7.json
YS
yosys -q fpga/build/synth.ys
echo "report: fpga/build/synth_xilinx.log, netlist json: fpga/build/miner_xc7.json"
