"""The text harness (PAD-1657): play a video mode in a terminal, no screen needed.

    python -m pinball_decryptor.core.video_mode.harness MODE.json [--bot | --inputs FILE]
           [--engine native|wasm] [--every SECONDS] [--seed N] [--level N] [--record FILE]

Compiles the document, runs the engine (native vmrun, or the WebAssembly module under
Node), and prints what happened in words, with a picture of the stage drawn in letters
every few seconds. --bot lets the engine's test player play it; the run's draw list hash
is printed last, the number the golden tests hold.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

from . import compiler

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.join(HERE, "engine")
SPS = compiler.SPS
COLS, ROWS = 96, 27

EV = {1: "clip_start", 2: "clip_stop", 3: "phase_start", 4: "phase_won", 5: "phase_lost", 6: "score",
      7: "kill", 8: "pickup", 9: "hurt", 10: "fire", 11: "hit", 12: "finished", 13: "prompt_good",
      14: "prompt_perfect", 15: "prompt_miss"}


def _engine_build_dir():
    sys.path.insert(0, ENGINE_DIR)
    try:
        import build
    finally:
        sys.path.pop(0)
    return build


def native_runner(cache=None):
    """A vmrun built from the current sources (cached by their hash), or None without a compiler."""
    build = _engine_build_dir()
    if not build.native_cc():
        return None
    d = os.path.join(cache or os.path.join(tempfile.gettempdir(), "pad_vmrun"), build.source_hash()[:16])
    exe = os.path.join(d, "vmrun.exe" if os.name == "nt" else "vmrun")
    if not os.path.exists(exe):
        build.build_native(d)
    return [exe]


def wasm_runner():
    node = shutil.which("node")
    if not node:
        return None
    return [node, os.path.join(ENGINE_DIR, "vm_run.mjs"), os.path.join(ENGINE_DIR, "vm_engine.wasm")]


def run_engine(runner, pack_path, args):
    r = subprocess.run(runner + [pack_path] + list(args), capture_output=True, text=True)
    if r.returncode not in (0,):
        raise RuntimeError("the engine stopped (%d): %s%s" % (r.returncode, r.stdout[-400:], r.stderr[-400:]))
    return r.stdout


def parse(out):
    events, cues, dumps, end = [], [], [], {}
    for line in out.splitlines():
        if line.startswith("E "):
            _, s, t, a, b, c = line.split()
            events.append((int(s), int(t), int(a), int(b), int(c)))
        elif line.startswith("C "):
            _, s, snd, op, duck = line.split()
            cues.append((int(s), int(snd), int(op), int(duck)))
        elif line.startswith("D "):
            parts = line.split()
            dumps.append((int(parts[1]), [int(x, 16) for x in parts[2:]]))
        elif line.startswith("END "):
            end = dict(kv.split("=") for kv in line.split()[1:])
    return events, cues, dumps, end


def _s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def entries(words):
    """The draw list's entries from its canonical words."""
    out, i = [], 8
    while i < len(words):
        tag = words[i] & 0xFF
        if tag == 1:
            w = words[i:i + 12]
            out.append({"tag": "quad", "atlas": w[1] & 0xFFFF, "sx": w[2] & 0xFFFF, "sy": w[2] >> 16,
                        "sw": w[3] & 0xFFFF, "sh": w[3] >> 16, "x": _s32(w[4]) / 65536, "y": _s32(w[5]) / 65536,
                        "scale": _s32(w[8]) / 65536, "alpha": (w[0] >> 16) & 0xFF})
            i += 12
        elif tag == 2:
            w = words[i:i + 6]
            out.append({"tag": "box", "x": _s32(w[1]) / 65536, "y": _s32(w[2]) / 65536,
                        "w": _s32(w[3]) / 65536, "h": _s32(w[4]) / 65536, "colour": w[5]})
            i += 6
        else:
            break
    return out


def picture(words, names, fonts):
    """The stage drawn in letters, and the words on it."""
    grid = [[" "] * COLS for _ in range(ROWS)]
    letters = {}
    texts = {}
    for e in entries(words):
        if e["tag"] == "box":
            continue
        if e["atlas"] >= compiler.FONT_ATLAS_BASE:
            fi = e["atlas"] - compiler.FONT_ATLAS_BASE
            f = fonts[fi] if fi < len(fonts) else None
            if not f:
                continue
            cw = max(1, int(round(f["size"] * 0.6)))
            ch = chr(32 + (e["sx"] // cw) + 16 * (e["sy"] // f["size"]))
            texts.setdefault(round(e["y"]), []).append((e["x"], ch, cw * e["scale"]))
            continue
        name = names["pictures"][e["atlas"]] if e["atlas"] < len(names["pictures"]) else "?"
        if e["sw"] >= 400:   # a background layer: too big to letter
            continue
        c = letters.setdefault(name, name[0].upper() if name[0].upper() not in letters.values() else name[0])
        col, row = int(e["x"] * COLS / 1360), int(e["y"] * ROWS / 768)
        if 0 <= col < COLS and 0 <= row < ROWS:
            grid[row][col] = c
    lines = ["+" + "-" * COLS + "+"] + ["|" + "".join(r) + "|" for r in grid] + ["+" + "-" * COLS + "+"]
    words_on = []
    for y in sorted(texts):
        run, last = "", None
        for x, ch, adv in sorted(texts[y]):
            if last is not None and x - last > 4 * adv:     # far apart: another piece of text
                words_on.append(run)
                run = ""
            elif last is not None and x - last > 1.5 * adv:  # a space's width between: a space
                run += " "
            run += ch
            last = x
        words_on.append(run)
    key = "  ".join("%s=%s" % (v, k) for k, v in sorted(letters.items()))
    return lines, [w.strip() for w in words_on if w.strip()], key


def describe(ev, names):
    s, t, a, b, c = ev
    when = "%3d:%05.2f" % (s // (SPS * 60), (s % (SPS * 60)) / SPS)
    th = lambda i: names["things"][i] if 0 <= i < len(names["things"]) else "#%d" % i
    ph = lambda i: names["phases"][i] if 0 <= i < len(names["phases"]) else "#%d" % i
    kind = EV.get(t, str(t))
    text = {
        "clip_start": lambda: "clip %s plays" % names["clips"][a],
        "clip_stop": lambda: "clip %s %s" % (names["clips"][a], "skipped" if b else "ended"),
        "phase_start": lambda: "phase %s starts%s" % (ph(a), " (try %d)" % (b + 1) if b else ""),
        "phase_won": lambda: "phase %s WON, %.1f s left, health %d" % (ph(a), b / SPS, c),
        "phase_lost": lambda: "phase %s LOST, %d tries left" % (ph(a), b),
        "kill": lambda: "%s down, +%d" % (th(a), b),
        "pickup": lambda: "picked up %s (%d so far)" % (th(a), b),
        "hurt": lambda: "hit! health %d" % a,
        "hit": lambda: "weak point %d hit, %d to go" % (a, b) if c == 0 else "hit",
        "finished": lambda: "FINISHED: %s, score %s%s" % ("won" if a else "lost", format(b, ","), ", no hit taken" if c else ""),
    }.get(kind, lambda: "%s %d %d %d" % (kind, a, b, c))()
    return "%s  %s" % (when, text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode")
    ap.add_argument("--bot", action="store_true", help="let the test player play it")
    ap.add_argument("--inputs", help="a recorded run: one byte of buttons a step")
    ap.add_argument("--record", help="write the run's buttons here")
    ap.add_argument("--engine", choices=["native", "wasm"], default=None)
    ap.add_argument("--every", type=float, default=5.0, help="draw the stage every this many seconds (0: never)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--level", type=int, default=0)
    ap.add_argument("--all-events", action="store_true", help="also list fire and score events")
    a = ap.parse_args(argv)
    res = compiler.compile_file(a.mode)
    for n in res.notes:
        print("note:", n)
    if not res.ok:
        for p in res.problems:
            print("problem:", p)
        return 1
    runner = (native_runner() if a.engine != "wasm" else None) or (wasm_runner() if a.engine != "native" else None)
    if not runner:
        print("no engine to run: install a C compiler or Node")
        return 2
    with tempfile.TemporaryDirectory(prefix="pad_vm_") as td:
        pack = os.path.join(td, "mode.pack")
        with open(pack, "wb") as f:
            f.write(res.pack)
        args = ["--seed", str(a.seed), "--level", str(a.level)]
        if a.bot:
            args.append("--bot")
        if a.inputs:
            args += ["--inputs", a.inputs]
        if a.record:
            args += ["--record", a.record]
        if a.every > 0:
            args += ["--dump", str(max(1, int(a.every * SPS)))]
        out = run_engine(runner, pack, args)
    events, cues, dumps, end = parse(out)
    fonts = res.names["fonts"]
    di = 0
    for ev in events + [(10 ** 9, 0, 0, 0, 0)]:
        while di < len(dumps) and dumps[di][0] <= ev[0]:
            lines, words, key = picture(dumps[di][1], res.names, fonts)
            print("\n-- step %d (%.1f s) --  %s" % (dumps[di][0], dumps[di][0] / SPS, key))
            print("\n".join(lines))
            if words:
                print("words: " + " | ".join(words))
            di += 1
        if ev[0] >= 10 ** 9:
            break
        if not a.all_events and EV.get(ev[1]) in ("fire", "score"):
            continue
        print(describe(ev, res.names))
    print("\nEND after %s steps (%.1f s): outcome %s, score %s, hash %s" % (
        end.get("steps"), int(end.get("steps", 0)) / SPS, {"1": "won", "0": "lost"}.get(end.get("outcome"), "unfinished"),
        end.get("score"), end.get("hash")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
