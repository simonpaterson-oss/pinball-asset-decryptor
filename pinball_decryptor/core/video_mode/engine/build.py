"""Builds the video mode engine three ways (PAD-1657).

    python build.py wasm            vm_engine.wasm beside this file (committed: the app has no compiler)
    python build.py native OUTDIR   vmrun, the native runner, for tests and the text harness
    python build.py arm OUTDIR      vm_engine.o with mode.so's own flags (-nostdlib, armhf), checked
                                    for calls the mode rules ban

A compiler is found in this order: $VM_CC; zig from the ziglang wheel or PATH (one toolchain
for every target, Windows included); cc / gcc / clang. WebAssembly needs zig or a clang
with the wasm32 target. vm_engine.wasm.sha holds the hash of the sources it was built from,
so a test can say plainly when the committed module is older than the C.
"""
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = ["vm_engine.c"]
SOURCES = ["vm_engine.h", "vm_engine.c", "vm_tables.h", "vm_bot.h", "vm_bot.c", "vm_wasm.c"]
WASM = os.path.join(HERE, "vm_engine.wasm")
CFLAGS = ["-std=gnu17", "-O2", "-Wall", "-Wextra", "-Wno-unused-parameter", "-Werror=implicit-function-declaration"]
# the libc a mode may not call (tools/spike2_emu/modes/sdk/build_mode.sh): the engine must call none
BANNED = ("malloc", "calloc", "realloc", "free", "posix_memalign", "memalign", "valloc", "pthread_",
          "sleep", "usleep", "nanosleep", "select", "poll", "epoll_", "printf", "fprintf", "puts",
          "fopen", "fread", "fwrite", "fclose", "system", "popen", "fork", "exec", "wait", "signal",
          "sigaction", "sin", "cos", "atan2", "sqrt", "pow", "exp")


def source_hash():
    h = hashlib.sha256()
    for name in SOURCES:
        with open(os.path.join(HERE, name), "rb") as f:
            h.update(name.encode() + b"\0" + f.read().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def zig():
    """[zig] as a command, or None."""
    if os.environ.get("VM_ZIG"):
        return [os.environ["VM_ZIG"]]
    try:
        import ziglang  # noqa: F401  (the pip wheel: pip install ziglang)
        exe = os.path.join(os.path.dirname(ziglang.__file__), "zig.exe" if os.name == "nt" else "zig")
        if os.path.exists(exe):
            return [exe]
    except ImportError:
        pass
    z = shutil.which("zig")
    return [z] if z else None


def native_cc():
    """A C compiler for this machine, as a command list, or None."""
    if os.environ.get("VM_CC"):
        return os.environ["VM_CC"].split()
    for name in ("cc", "gcc", "clang"):
        p = shutil.which(name)
        if p:
            return [p]
    z = zig()
    return z + ["cc"] if z else None


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        raise RuntimeError("build failed: %s\n%s%s" % (" ".join(cmd), r.stdout, r.stderr))
    return r


def build_native(outdir, cc=None, extra=()):
    cc = cc or native_cc()
    if not cc:
        raise RuntimeError("no C compiler (cc, gcc, clang or zig) on this machine")
    os.makedirs(outdir, exist_ok=True)
    exe = os.path.join(outdir, "vmrun.exe" if os.name == "nt" else "vmrun")
    run(cc + CFLAGS + list(extra) + ["-o", exe] + [os.path.join(HERE, n) for n in ("vm_engine.c", "vm_bot.c", "vm_cli.c")])
    return exe


def build_wasm(out=WASM):
    z = zig()
    if z:
        cmd = z + ["cc", "--target=wasm32-freestanding", "-O2", "-nostdlib", "-fno-builtin",
                   "-Wl,--no-entry", "-Wl,-z,stack-size=1048576"]
    else:
        c = shutil.which("clang")
        if not c:
            raise RuntimeError("WebAssembly needs zig (pip install ziglang) or clang with the wasm32 target")
        cmd = [c, "--target=wasm32", "-O2", "-nostdlib", "-fno-builtin", "-Wl,--no-entry",
               "-Wl,-z,stack-size=1048576", "-Wl,--initial-memory=8388608"]
    run(cmd + CFLAGS + ["-o", out] + [os.path.join(HERE, n) for n in ("vm_engine.c", "vm_bot.c", "vm_wasm.c")])
    with open(out + ".sha", "w", newline="\n") as f:
        f.write(source_hash() + "\n")
    return out


def build_arm(outdir, cc="arm-linux-gnueabihf-gcc", nm=None):
    """The object the mode runtime links, under mode.so's flags; returns (path, undefined symbols)."""
    os.makedirs(outdir, exist_ok=True)
    obj = os.path.join(outdir, "vm_engine.o")
    run([cc, "-std=gnu17", "-marm", "-mfloat-abi=hard", "-fno-stack-protector", "-fPIC", "-fvisibility=hidden",
         "-O2", "-nostdlib", "-funwind-tables", "-Wall", "-Wextra", "-Wno-unused-parameter",
         "-Werror=implicit-function-declaration", "-c", "-o", obj, os.path.join(HERE, "vm_engine.c")])
    nm = nm or (cc[:-3] + "nm" if cc.endswith("gcc") else "nm")
    out = run([nm, "--undefined-only", obj]).stdout
    undefined = sorted({line.split()[-1] for line in out.splitlines() if line.strip()})
    banned = [s for s in undefined if any(s == b or (b.endswith("_") and s.startswith(b)) for b in BANNED)]
    if banned:
        raise RuntimeError("the engine calls what a mode may not: %s" % ", ".join(banned))
    return obj, undefined


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "wasm"
    if what == "wasm":
        print(build_wasm())
    elif what == "native":
        print(build_native(sys.argv[2]))
    elif what == "arm":
        print(build_arm(sys.argv[2]))
    else:
        sys.exit("python build.py wasm | native OUTDIR | arm OUTDIR")
