# Hardware aspects: CPU, GPU, FPGA, ASIC

The lab is an all-rounder by the owner's order: the same
double-SHA-256 mining problem is implemented and verified on
every class of hardware the lab can reach, with each aspect's
status stated exactly as it is.

| aspect | where | status |
| --- | --- | --- |
| CPU | mining/cpu/, gpu/engine.py | Built, tuned, fastest path in the lab (about 6.6M H/s end to end on this VM); blocks accepted by Core through it. Results: results/CPU_RESULTS.md |
| GPU | gpu/, docs/CUDA.md | CUDA toolkit installed, kernel and host library compiled and host-validated; this VM has no GPU (CUDA runtime error 35), so no GPU hashes are claimed. The code runs wherever a device exists. |
| FPGA | fpga/ | Verilog miner simulated and proven against the FIPS vector and the genesis header; synthesized for a generic Xilinx 7-series target (2,659 LUTs). No board attached, so no bitstream was programmed. Results: results/FPGA_RESULTS.md |
| ASIC | asic/ | Same RTL synthesized to a gate-level netlist (about 11.1K cells, about 25K gate equivalents estimated); the netlist itself passes the same simulation testbench. Pre-layout only: no PDK, no tapeout. Results: results/ASIC_RESULTS.md |

One design, four substrates: the Python PoW engine defines the
semantics, the C engine accelerates them on CPU, the CUDA engine
mirrors them for GPU, and the Verilog RTL carries them into
FPGA and ASIC flows. Every layer is checked against the layers
above it (hashlib, FIPS vectors, real mainnet headers, the
genesis block).
