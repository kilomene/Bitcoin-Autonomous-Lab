# EXP-045 disassembly comparison: research-built vs
# production-built AVX2 library

Libraries (sha256 recorded in every EXP-045 session
manifest; both files byte-identical to the ones the
historical campaigns measured):

- research: research/sha256d/exp032/libbal_avx2.so
  sha256 91d0a1b8bf490b1810bac6f856ac28e50934868bc2b39bfda34af2c274b4b2b0
  built by exp032/build.sh: gcc -O3 -mavx2 -shared -fPIC
  -Wall -Wextra, single translation unit (src/avx2_mb.c),
  -lpthread.
- production: .local/cpu/libbal_avx2.so
  sha256 81a6ca188df1ea1e78ceee88c7228eee9a38127177609d7ffc42ab8b74a8ff73
  built by mining/cpu/build.py build_avx2: kernel TU
  (mining/cpu/bal_avx2_mb.c) compiled separately with
  gcc -O3 -mavx2 -shared -fPIC, flag-free probe TU
  (bal_fallback_probe.c) compiled with no vector flags,
  the two objects linked with -lpthread.

Kernel sources differ only in the header comment block
(a comment-stripped diff of exp032/src/avx2_mb.c against
mining/cpu/bal_avx2_mb.c shows exactly one differing
line, the opening comment line). Full disassemblies:
disasm_research_lib.txt and disasm_production_lib.txt
in this directory (objdump -d --no-show-raw-insn).

## Per-function instruction comparison

Normalisation: addresses, RIP-relative displacements and
call targets replaced by placeholders; opcodes, registers
and immediates compared exactly.

| function | research insns | production insns | sequence |
|---|---|---|---|
| bal_a_batch2 | 41 | 41 | IDENTICAL |
| a_worker | 44 | 44 | IDENTICAL |
| a_compress8 | 163 | 163 | identical except RIP-relative constant-pool displacements |
| a_run | 718 | 718 | identical except RIP-relative constant-pool displacements |
| a_walk.constprop.0 (hot loop) | 2380 | 2380 | identical except RIP-relative constant-pool displacements |
| bal_a_search2 | 151 | 152 | identical except displacements, plus one trailing nopw padding in production |

Every difference inside the kernel functions is a
RIP-relative displacement value (the constant pool sits
at a different offset because the production library
also contains the probe functions bal_avx2_supported,
bal_avx2_feature_bits, bal_shani_supported,
bal_shani_feature_bits and __cpu_indicator_init, which
the research library does not contain). No opcode,
register allocation, immediate, instruction order or
instruction count differs anywhere in the batch path.
The compiled kernel code is instruction-identical; only
its placement inside the library file differs.

## Placement (link layout)

| function | research addr | mod 64 | production addr | mod 64 |
|---|---|---|---|---|
| a_compress8 | 0x11e0 | 32 | 0x22c0 | 0 |
| a_walk.constprop.0 | 0x1560 | 32 | 0x2640 | 0 |
| a_worker | 0x4f40 | 0 | 0x6020 | 32 |
| a_run | 0x4ff0 | 48 | 0x60d0 | 16 |
| bal_a_batch2 | 0x5e10 | 16 | 0x6ef0 | 48 |

Note the direction: the production library places the
hot function a_walk.constprop.0 at a 64-byte boundary
while the research library places it at 32 mod 64. If
entry alignment of the hot function were the mechanism
behind the historical gap, the naive expectation would
favour the production build, which is the one that
measured slower in EXP-039. The paired sessions in this
experiment arbitrate the question directly.
