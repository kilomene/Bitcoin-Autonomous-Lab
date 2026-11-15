#!/usr/bin/env python3
"""EXP-028 dispatch specification, executable form.

This is the reference logic the roadmap document
(EXP028_CPU_ARCHITECTURES.md) specifies. It mirrors the
production ComputeEngine order (gpu/engine.py) and
generalises it per architecture family:

  order (first whose full gate chain passes wins):
    1. cuda            (only where a device exists; this
                        programme has none, UNVERIFIED)
    2. avx512-mb       (probe bits F+BW, library complete,
                        hashlib self-test) [production v512]
    3. shani-streams   (probe SHA+SSE4.1+SSE4.2, library
                        complete, self-test) [research]
    4. avx2-mb         (probe AVX2, library complete,
                        self-test) [SPECIFIED, UNVERIFIED:
                        no kernel built, X-032]
    5. arm-sha2/neon   (non-x86 only; OS capability probe)
                        [SPECIFIED, UNVERIFIED: no machine]
    6. c-openssl       (library complete, self-test)
    7. hashlib         (portable floor, always available)

Rules, all load-bearing:
  * A probe bit alone never selects a backend. Selection
    requires, in order: probe predicate true, library
    present AND complete (every required symbol, the D-1
    regression pattern: check completeness BEFORE any
    argtypes assignment or call), then a self-test batch
    whose every digest equals hashlib double SHA-256.
  * Any failure at any step records a reason and falls
    through to the next backend. Selection never raises
    for an optional backend; only an explicit request for
    exactly one backend may raise when it cannot be met
    (production behaviour for requested="cuda-only").
  * No kernel entry point is ever executed speculatively
    to test support. Detection is probe-only.
  * The selected backend, the probe bits, the host model
    and the thread count are recorded with every result,
    so cross-machine comparisons stay honest.
"""

F, BW, DQ, VL, VBMI, VBMI2, IFMA, VNNI = 0, 1, 2, 3, 4, 5, 6, 7
AVX2, SHA, SSE41, SSE42, BMI1, BMI2, ADX, AES = 8, 9, 10, 11, 12, 13, 14, 15

BIT_NAMES = {0: "avx512f", 1: "avx512bw", 2: "avx512dq",
             3: "avx512vl", 4: "avx512vbmi", 5: "avx512vbmi2",
             6: "avx512ifma", 7: "avx512vnni", 8: "avx2",
             9: "sha", 10: "sse4.1", 11: "sse4.2", 12: "bmi1",
             13: "bmi2", 14: "adx", 15: "aes"}


def _has(bits, *idx):
    return all((bits >> i) & 1 for i in idx)


# Each family: (name, probe predicate over feature bits,
# required library symbols). The symbol lists are the
# completeness contract checked before any call.
FAMILIES = [
    ("avx512-mb", lambda b: _has(b, F, BW),
     ("bal_v512_supported", "bal_v_batch2", "bal_v_search2")),
    ("shani-streams", lambda b: _has(b, SHA, SSE41, SSE42),
     ("bal_m_batch2m", "bal_m_search2m")),
    ("avx2-mb", lambda b: _has(b, AVX2),
     ("bal_a_batch2", "bal_a_search2")),
    ("c-openssl", lambda b: True,
     ("bal_batch2", "bal_search2")),
]


def select_backend(feature_bits, libraries, self_test,
                   requested="auto"):
    """Return (backend_name, reasons).

    libraries: {family_name: set_of_symbols_present} or
    None when the library file is absent.
    self_test: {family_name: bool} result of the hashlib
    differential self-test for that family's library.
    """
    reasons = []
    if requested not in ("auto", "hashlib"):
        order = [f for f in FAMILIES if f[0] == requested]
        if not order:
            raise ValueError(f"unknown backend {requested!r}")
    else:
        order = FAMILIES
    if requested == "hashlib":
        return "hashlib", ["explicit hashlib request"]
    for name, probe_ok, symbols in order:
        if not probe_ok(feature_bits):
            reasons.append(f"{name}: probe predicate false")
            continue
        present = libraries.get(name)
        if present is None:
            reasons.append(f"{name}: library absent")
            continue
        missing = [s for s in symbols if s not in present]
        if missing:
            reasons.append(f"{name}: library incomplete, "
                           f"missing {missing}")
            continue
        if not self_test.get(name, False):
            reasons.append(f"{name}: hashlib self-test failed")
            continue
        reasons.append(f"{name}: selected")
        return name, reasons
    reasons.append("hashlib: portable floor selected")
    return "hashlib", reasons
