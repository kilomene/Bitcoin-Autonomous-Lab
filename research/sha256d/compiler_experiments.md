# Compiler Experiments

## EXP-001 (2026-11-14): gcc flag sweep on the production source

Question: do flags other than the production set
(-O3 -march=native, from mining/cpu/build.py) make
mining/cpu/bal_batch.c faster on this machine?

Method: experiments/compiler_sweep.py. Five variants built
into .local/shax/ (production untouched), each verified
against hashlib on 100,000 digests plus the genesis search,
then benchmarked with the shared harness: 1,000,000 hashes,
3 repeats, at 1 and 2 threads, live miner and node
contending. Raw data: experiments/exp001_compiler_sweep.json.

Results, 2-thread medians (production tuned thread count):
- prod -O3 -march=native: 2,347,336 H/s (spread 70.1%)
- -O3 -march=native -flto: 2,195,680 H/s (-6.5%)
- -O3 -march=x86-64: 2,188,081 H/s (-6.8%)
- -O3 -march=native -funroll-loops: 2,050,686 H/s (-12.6%)
- -O2 -march=native: 1,472,158 H/s (-37.3%)

1-thread medians told the same story (production flags
1,699,701 H/s, best of the rest). All spreads overlapped.

Assembly cross-check: hash_nonce is 408 instructions with a
416-byte stack frame in every native variant (identical
codegen for the wrapper), 534 instructions and 456 bytes for
the generic build. The compression itself is inside
libcrypto in all variants, so flags on this file can only
rearrange wrapper code. That is the structural reason the
sweep found nothing: there was nothing in this file for the
flags to win.

Decision: REJECT all variants. Production build flags are
unchanged; no production file was modified. The experiment
was worth running precisely because it closes the cheap
hypothesis with evidence and redirects effort to the wrapper
shape and a purpose-built kernel (H-01, H-02).

## Not covered, and why

- clang: not installed on this VM (verified). Registered as
  H-12 rather than silently skipped.
- PGO: feasible with gcc but pointless for this file given
  the assembly finding; if a hand kernel lands (H-02), PGO
  gets re-evaluated on that file, where the hot code is ours.
- -march variants beyond native/generic: the guest exposes
  one fixed feature set; native already enables all of it.

## Standing compiler protocol

For any future candidate file: build with production flags
first, sweep -O2/-O3/LTO/unroll and march generic vs native,
record hash_nonce-equivalent instruction counts and stack,
verify 100k digests, benchmark with the shared harness, and
apply the spread-overlap decision rule from the registry.
