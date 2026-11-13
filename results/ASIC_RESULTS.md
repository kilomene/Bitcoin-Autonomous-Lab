# ASIC aspect: synthesis and netlist verification (2026-11-13)

Flow: asic/flow.sh takes the SAME RTL as the FPGA aspect
(fpga/sha256_core.v, fpga/sha256d_miner.v) through Yosys to a
gate-level netlist (generic CMOS gates via ABC), then simulates
the netlist itself against the same testbench. This is a
pre-layout ASIC design package: there is no PDK, no place and
route, and no tapeout from this VM, and none is claimed.

## Gate-level verification

The synthesized netlist (asic/build/miner_netlist.v, simulated
with Yosys simcells/simlib models in Icarus Verilog) reproduces
the RTL results exactly:

- SHA-256("abc") equals the FIPS vector.
- The miner finds genesis nonce 2083236893 with the genesis hash
  after exactly 3 hashes in the verified window.

## Synthesis numbers (Yosys stat, sha256d_miner)

| item | count |
| --- | --- |
| Total cells | 11,131 |
| Combinational gates | about 8,906 |
| Flip-flops | about 2,225 |
| of which NAND | 2,833 |
| of which XOR + XNOR | 1,714 |
| of which AOI3 + OAI3 | 1,514 |
| of which MUX | 684 |

Gate-equivalent estimate by the usual weights (simple gate 1,
XOR/XNOR 2, MUX 2, AOI/OAI 1.5, flip-flop 6): about 25,000 GE for
the complete iterative miner. That is an estimate from cell
counts, not a library characterization.

## Performance arithmetic (labeled as such)

The design spends 137 cycles per double hash (two 64-round
compressions plus FSM overhead; measured in simulation: 411
cycles for 3 hashes). Hashrate scales linearly with clock and
core count: one core at 500 MHz would be about 3.6 MH/s; real
mining ASICs reach terahashes by unrolling rounds and replicating
this core thousands of times with a pipelined architecture, which
is the documented next step in docs/HARDWARE.md, not a result
claimed here. Timing closure, power and area in silicon all require a PDK
and place and route, which are out of reach of this VM.
