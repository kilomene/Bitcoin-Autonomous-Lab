#!/bin/sh
# ASIC flow for the lab RTL: yosys synthesis to a gate-level
# netlist (generic CMOS cells), then functional simulation of the
# NETLIST against the same genesis testbench. Pre-layout only:
# no PDK, no place and route, timing is an estimate, stated as such.
set -e
cd "$(dirname "$0")/.."
mkdir -p asic/build
cat > asic/build/synth.ys << 'YS'
read_verilog fpga/sha256_core.v fpga/sha256d_miner.v
hierarchy -top sha256d_miner -check
proc; opt; fsm; opt; memory; opt; techmap; opt
abc -g AND,OR,XOR,XNOR,NAND,NOR,MUX,AOI3,OAI3
clean
tee -o asic/build/synth.log stat
write_verilog -noattr asic/build/miner_netlist.v
YS
yosys -q asic/build/synth.ys
# simcells/simlib ship with yosys for gate-level simulation.
SIMLIB=/usr/share/yosys/simlib.v
SIMCELLS=/usr/share/yosys/simcells.v
iverilog -o asic/build/tb_netlist.vvp "$SIMLIB" "$SIMCELLS" \
    asic/build/miner_netlist.v fpga/tb_miner.v
echo "netlist written: asic/build/miner_netlist.v"
