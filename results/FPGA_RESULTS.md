# FPGA aspect: build, simulation and synthesis results (2026-11-13)

Design: fpga/sha256_core.v (iterative SHA-256 compression core,
one round per clock, 64 rounds per block) and
fpga/sha256d_miner.v (double-hash miner: midstate in, tail and
nonce assembled in hardware, target compared in hardware, scans a
nonce range autonomously). Testbench: fpga/tb_miner.v.
Tools: Icarus Verilog 12, Yosys 0.33. No FPGA board is attached to
this VM; the deliverables are the verified RTL and the synthesis
report, stated plainly.

## Simulation proof (Icarus Verilog)

- Core: SHA-256("abc") digest equals the FIPS 180-4 vector
  ba7816bf...f20015ad.
- Miner: given the genesis header's midstate and tail, scanning
  from nonce 2083236891 it stopped at exactly nonce 2083236893
  with the genesis block hash, after exactly 3 hashes. The window
  is honest: the previous nonce meeting the genesis target is
  2083236890 (checked in Python against hashlib), so the genesis
  nonce is provably the first qualifier in the window.
- Every intermediate digest the design produced during debugging
  matched hashlib byte for byte.

Bugs found and fixed on the way: two wrong rotation constants in
the message schedule (19 and 18, initially typed as 14 and 2), a
testbench padding word that truncated the message block, and a
stimulus race (driving start at the posedge the DUT samples),
fixed by driving stimulus on the negedge.

## Synthesis (yosys synth_xilinx, generic 7-series target)

Whole miner (sha256d_miner), from fpga/build/synth_xilinx.log:

| resource | count |
| --- | --- |
| LUTs (LUT1..LUT6) | 2,659 |
| CARRY4 | 147 |
| Flip-flops (FDRE + FDSE) | 2,229 |
| BUFG | 1 |
| Total cells | 6,233 |

One iterative core is small: at 137 cycles per hash, a 100 MHz
clock gives about 0.73 MH/s per core by arithmetic, and the
design leaves room for many parallel cores on a mid-size device.
Those rates are cycle arithmetic, not a board measurement; no
board exists here to measure.
