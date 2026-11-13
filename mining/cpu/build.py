"""Build the C batch library (.local/cpu/libbal_batch.so)."""

import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, ".local", "cpu")
LIB = os.path.join(OUT, "libbal_batch.so")


def build(log=print):
    os.makedirs(OUT, exist_ok=True)
    cc = shutil.which("gcc") or shutil.which("cc")
    if not cc:
        log("no C compiler: C batch library not built")
        return {"cc": None, "lib": None}
    cmd = [cc, "-O3", "-march=native", "-shared", "-fPIC",
           "-Wno-deprecated-declarations",
           os.path.join(HERE, "bal_batch.c"), "-o", LIB,
           "-lcrypto", "-lpthread"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    ok = proc.returncode == 0
    log(f"C batch build: {'ok' if ok else 'FAILED'}")
    return {"cc": cc, "lib": LIB if ok else None,
            "error": None if ok else proc.stderr.strip()[-400:]}


if __name__ == "__main__":
    print(build())
