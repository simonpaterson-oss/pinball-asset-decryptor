"""PAD-1667 emulator proof: a video mode's sound on the machine, cue for cue with the app.

    python scripts/proof_pad1667_rig.py <out_dir> [--slot N]

Night Harbour (the plan's worked example) with its original placeholder sounds (scripts/vm_demo_art.py) is put on
James Bond LE 1.06 as a C code mode, ``vmsound``: the video mode engine itself (vm_engine.c) steps once a tick, 60 a
second, on the bot's winning run (tests/data/video_mode/golden), and each step's sound cues go through the mode's own
sound route (vm_sound.h over pad_mode_assets.h): effects and the callout as its calls, the two music beds as its
music. Its sounds are the machine's files the build side writes (core/video_mode/sound.machine_files: 48 kHz WAVs,
each bed baked to keep its loop point).

The app (served headless from this tree) builds it with Try it on rig slot N (never David's own), hidden and muted;
a game is started, then Start mode now. Saved in <out_dir>: mode.log (the engine's cues by step and pm_ms, the
own-sound lines, and the runtime's sound log - "[pad] sound <request>" with its ms, every request the game's sound
worker took), the .assets file, and rig_cues.json: the cues the rig played by step against the native build's on
the same buttons (vmrun), each call's carrier request found in the sound log within a tick or two of its step's
time, and each music change's start.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)
import webui_shot  # noqa: E402
import vm_demo_art  # noqa: E402
from proof_pad1030_rig import LAUNCHER, CARD, RIG_HELPER, win_to_wsl  # noqa: E402

SLUG = "vmsound"
RIGSH_WIN = r"C:\tmp\pad1667_rig.sh"
RIGSH = "/mnt/c/tmp/pad1667_rig.sh"
ENGINE = os.path.join(REPO, "pinball_decryptor", "core", "video_mode", "engine")
GOLDEN = os.path.join(REPO, "tests", "data", "video_mode", "golden")

MODE_C = r'''/* vmsound.c - PAD-1667 rig proof: Night Harbour's sound, played by the video mode engine on the bot's winning run.
 * Start mode now (dump/vmsound.start) starts it; it steps the engine once a tick (60 a second) on the recorded
 * buttons and plays each step's sound cues through the mode's own sounds (vm_sound.h). */
#include "pad_mode.h"
#include "vm_engine.c"
#include "vm_sound.h"
#include "vm_proof_data.h"

#define FOLDER "vmsound"
static struct pa_assets own = { .folder = FOLDER };
static struct vm_sound snd = { &own, VM_NAMES, VM_NSOUNDS, 0, 0, 0, 0 };
static vm_engine E;
static unsigned long step, t0;
static int running;

static void start(const char *why)
{
    int err;
    if (running) return;
    err = vm_load(&E, VM_PACK, (uint32_t)sizeof VM_PACK);
    if (err) { pm_log("vmsound: the pack did not load (%d at word %d)", err, (int)E.err_at); return; }
    vm_start(&E, VM_SEED, 0);
    step = 0; running = 1; t0 = pm_ms();
    pm_log("vmsound: started (%s) at %lu ms: %u steps of the bot's run", why, t0, (unsigned)sizeof VM_INPUTS);
    vm_sound_start(&snd);
}
static void stop(const char *why)
{
    if (!running) return;
    running = 0;
    vm_sound_end(&snd);
    pm_log("vmsound: ended (%s) after %lu steps at %lu ms, outcome %d, hash %08x%08x", why, step, pm_ms(),
           (int)E.outcome, (unsigned)(E.hash >> 32), (unsigned)E.hash);
}
static void on_init(void)
{
    pa_load(&own);
    pm_log("vmsound: ready on %s %s", pm_game(), pm_version());
}
static void on_tick(void)
{
    pa_tick(&own);
    if (pm_trigger(FOLDER ".start")) start("trigger file");
    if (pm_trigger(FOLDER ".stop")) stop("trigger file");
    if (!running) return;
    if (step < sizeof VM_INPUTS) {          /* one engine step a tick: the engine's own 60 a second */
        int more = vm_step(&E, VM_INPUTS[step]);
        vm_sound_cues(&snd, &E, step);
        step++;
        if (!more) stop("the video mode finished");
    } else {
        stop("out of recorded buttons");
    }
}
static const struct pm_mode vmsound = { .name = "vmsound", .init = on_init, .tick = on_tick };
PM_REGISTER(vmsound);
'''


def rig(*args, timeout=120, tries=6):
    """A rig tool on the proof's slot; WSL that does not answer (a busy PC) is tried again."""
    for k in range(tries):
        try:
            r = subprocess.run(["wsl", "-d", "PAD-Runtime", "-u", "root", "--", "bash", RIGSH] + list(args),
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            r = None
        if r is not None and "Wsl/Service" not in (r.stdout or "") + (r.stderr or "").replace(chr(0), ""):
            return r.returncode, (r.stdout or "") + (r.stderr or "")
        time.sleep(15)
    return 1, "(WSL did not answer)"


def c_bytes(name, data, ctype="uint8_t"):
    rows = [", ".join("0x%02x" % b for b in data[i:i + 24]) for i in range(0, len(data), 24)]
    return "static const %s %s[] __attribute__((aligned(4))) = {\n    %s\n};\n" % (ctype, name, ",\n    ".join(rows))


def make_mode(project, slot_dir):
    """The vmsound code mode in the project: the engine's sources, the pack, the bot's buttons, the machine's sound
    files and assets.json. Returns (doc, plan, names, inputs, seed)."""
    from pinball_decryptor.core.video_mode import compiler as C, document as D, sound as SND
    demo = os.path.join(slot_dir, "night-harbour")
    vm_demo_art.make_mode(demo)
    vm_demo_art.make_media(demo)
    doc = D.load(os.path.join(demo, "video_mode.json"))
    comp = C.compile_doc(doc, demo)
    assert comp.ok, comp.problems
    folder = os.path.join(project, "modes", SLUG)
    os.makedirs(folder, exist_ok=True)
    for f in ("vm_engine.c", "vm_engine.h", "vm_tables.h", "vm_sound.h"):
        shutil.copy2(os.path.join(ENGINE, f), os.path.join(folder, f))
    plan, fields = SND.machine_files(doc, demo, folder)
    names = SND.machine_names(doc, plan)
    with open(os.path.join(GOLDEN, "golden.json"), encoding="utf-8") as f:
        spec = json.load(f)["runs"]["night_harbour_bot"]
    with open(os.path.join(GOLDEN, spec["inputs"]), "rb") as f:
        inputs = f.read()
    with open(os.path.join(folder, "vm_proof_data.h"), "w", encoding="utf-8", newline="\n") as f:
        f.write("/* GENERATED by scripts/proof_pad1667_rig.py: Night Harbour's pack, the bot's buttons, the sounds' names */\n")
        f.write("#define VM_SEED %du\n#define VM_NSOUNDS %d\n" % (int(spec["seed"]), len(names)))
        f.write("static const char *const VM_NAMES[%d] = { %s };\n" % (len(names), ", ".join('"%s"' % n for n in names)))
        f.write(c_bytes("VM_PACK", comp.pack))
        f.write(c_bytes("VM_INPUTS", inputs))
    with open(os.path.join(folder, SLUG + ".c"), "w", encoding="utf-8", newline="\n") as f:
        f.write(MODE_C)
    assets = dict({"format": 1, "name": "NIGHT HARBOUR SOUND", "seconds": 120, "screen": False}, **fields)
    with open(os.path.join(folder, "assets.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(assets, f, indent=1)
    return doc, comp, plan, names, inputs, spec


def native_cues(comp, inputs, seed):
    from pinball_decryptor.core.video_mode.engine import build
    scratch = tempfile.mkdtemp(prefix="pad1667-native-")
    exe = build.build_native(scratch)
    pack = os.path.join(scratch, "nh.pack")
    with open(pack, "wb") as f:
        f.write(comp.pack)
    ip = os.path.join(scratch, "bot.inputs")
    with open(ip, "wb") as f:
        f.write(inputs)
    out = subprocess.run([exe, pack, "--inputs", ip, "--seed", str(seed), "--max", str(len(inputs))],
                         capture_output=True, text=True).stdout.splitlines()
    return [[int(v) for v in ln.split()[1:]] for ln in out if ln.startswith("C ")], out[-1]


def check(log, assets_txt, native, names):
    """The rig's cues against the native build's, and each one heard in the sound log."""
    cue_re = re.compile(r"vm sound: step (\d+) at (\d+) ms: cue (-?\d+) (\S+) op (\d+) duck (\d+) fade (\d+) -> (.+)$")
    snd_re = re.compile(r"^\s*(\d+) \[pad\] sound (\d+) ")
    rig_cues, heard = [], []
    for line in log.splitlines():
        m = cue_re.search(line)
        if m:
            rig_cues.append([int(m.group(i)) for i in (1, 3, 5, 6, 7)] + [int(m.group(2)), m.group(8)])
        m = snd_re.search(line)
        if m:
            heard.append((int(m.group(1)), int(m.group(2))))
    calls = {}
    for line in assets_txt.splitlines():
        p = line.split()
        if p[:1] == ["call"] and len(p) >= 3:
            calls[p[1]] = int(p[2])
        if p[:1] == ["music"] and len(p) >= 2:
            calls["(music)"] = int(p[1])
    for m in re.finditer(r"own sound: call (\w+) \((\d+)\) played", log):     # the carriers, as the mode says
        calls.setdefault(m.group(1), int(m.group(2)))
    m = re.search(r"own sound: music (\d+) ", log)
    if m:
        calls.setdefault("(music)", int(m.group(1)))
    same = [c[:5] for c in rig_cues] == native
    t0 = rig_cues[0][5] - rig_cues[0][0] * 1000 / 60.0 if rig_cues else 0
    rows, late = [], []
    for c in rig_cues:
        step, snd, op, duck, fade, ms, said = c
        name = names[snd] if 0 <= snd < len(names) else ""
        req = calls.get(name) if op == 0 else calls.get("(music)")
        want = t0 + step * 1000 / 60.0
        hit = next((t for t, r in heard if r == req and want - 40 <= t <= want + 400), None) if req and op == 0 else None
        rows.append({"step": step, "sound": name, "op": op, "ms": ms, "drift_ms": round(ms - want, 1), "request": req,
                     "heard_ms": hit, "heard_after_ms": None if hit is None else round(hit - want, 1), "said": said})
        if abs(ms - want) > 20:
            late.append(step)
    return {"same_cues_as_native": same, "rig_cues": len(rig_cues), "native_cues": len(native),
            "steps_off_the_60hz_clock": late, "calls": calls, "rows": rows}


def main():
    out_dir = os.path.abspath(sys.argv[1])
    slot = sys.argv[sys.argv.index("--slot") + 1] if "--slot" in sys.argv else ""
    if slot not in ("1", "2", "3", "4", "5"):        # never the base rig (an empty or 0 slot is David's own)
        print("refused: --slot must be a rig slot of 1 to 5 taken for PAD-1667, not %r" % slot)
        return 2
    os.makedirs(out_dir, exist_ok=True)
    with open(RIGSH_WIN, "w", encoding="utf-8", newline="\n") as f:
        f.write(RIG_HELPER.replace("PAD-1030-check", "PAD-1667") % {"slot": slot, "rig": win_to_wsl(os.path.join(REPO, "tools", "spike2_emu"))})
    scratch = tempfile.mkdtemp(prefix="pad1667rig-")
    project = os.path.join(scratch, "Bond LE 1.06 Extract")
    os.makedirs(project)
    with open(os.path.join(project, ".extract_source.json"), "w", encoding="utf-8") as f:
        json.dump({"input_path": CARD, "input_name": os.path.basename(CARD), "card_version": "1.06"}, f)
    doc, comp, plan, names, inputs, spec = make_mode(project, scratch)
    native, native_end = native_cues(comp, inputs, spec["seed"])
    print("plan:", plan["words"], "names:", names, "native cues:", len(native), native_end, flush=True)
    real = os.path.expandvars(r"%APPDATA%\pinball_decryptor\settings.json")
    with open(real, encoding="utf-8") as f:
        codes = json.load(f).get("preview_codes", [])
    launcher = os.path.join(scratch, "launch1667.py")
    with open(launcher, "w", encoding="utf-8") as f:
        f.write(LAUNCHER % REPO)
    settings = os.path.join(scratch, "settings.json")
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"disclaimer_accepted": True, "last_manufacturer": "stern", "preview_codes": codes,
                   "emulate_card": CARD, "manufacturers": {"stern": {"extract_output": project, "write_assets": project}}}, f)
    cfgdir = os.path.join(scratch, "cfg", "pinball_decryptor")      # a rig run is always muted
    os.makedirs(cfgdir, exist_ok=True)
    with open(os.path.join(cfgdir, "audio_ctl.json"), "w", encoding="utf-8") as f:
        json.dump({"gain": 0.0, "muted": True}, f)
    import site
    tmp = os.path.join(scratch, "tmp")
    os.makedirs(tmp, exist_ok=True)
    env = {"PYTHONPATH": site.getusersitepackages(), "TEMP": tmp, "TMP": tmp, "PAD_UI_NO_RIG": "",
           "PAD_UI_NO_PREREQS": "1", "PAD_SLOT": slot, "PAD_TICKET": "", "PAD_LABEL": "PAD-1667",
           "PAD_HIDDEN": "1", "PAD_AUDIO": "0"}
    proc, url = webui_shot.start_server(settings, scratch, app_cmd=[sys.executable, launcher], extra_env=env)
    print("server", url.split("?")[0], "scratch", scratch, flush=True)
    try:
        webui_shot.api(url, "ui.pick_manufacturer", "stern")
        webui_shot.api(url, "ui.select_tab", "modes")
        time.sleep(3)
        webui_shot.api(url, "modes.select", SLUG, "code")
        time.sleep(2)
        print("rig before:", rig("ps")[1].strip() or "(nothing running)", flush=True)
        webui_shot.api(url, "modes.tryit")
        t0, last, ts = time.time(), None, {}
        while time.time() - t0 < 3600:
            ts = (webui_shot.state(url).get("modes", {}) or {}).get("tryit") or {}
            now = (ts.get("state"), (ts.get("reason") or "")[:300])
            if now != last:
                print("%5ds tryit %s" % (time.time() - t0, now), flush=True)
                last = now
            if ts.get("state") in ("live", "ended", "failed"):
                break
            time.sleep(10)
        if (ts.get("state") or "") != "live":
            return 2
        time.sleep(90)
        for k in ("coin", "game"):
            print(k, rig(k)[1].strip()[-200:], flush=True)
        time.sleep(25)
        rig("plunge")
        time.sleep(10)
        webui_shot.api(url, "modes.start_now")
        n_steps = len(inputs)
        time.sleep(n_steps / 60.0 + 15)                 # the run, and its music's fade after it
        assets_txt = rig("assets")[1]
        log = rig("modelog")[1]
        with open(os.path.join(out_dir, "assets.txt"), "w", encoding="utf-8") as f:
            f.write(assets_txt)
        with open(os.path.join(out_dir, "mode.log"), "w", encoding="utf-8") as f:
            f.write(log)
        res = check(log, assets_txt, native, names)
        res.update({"plan": plan["words"], "names": names, "native_end": native_end})
        with open(os.path.join(out_dir, "rig_cues.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)
        print(json.dumps({k: res[k] for k in ("same_cues_as_native", "rig_cues", "native_cues", "steps_off_the_60hz_clock", "calls")}), flush=True)
        for line in log.splitlines():
            if "vmsound" in line or "own sound: music" in line:
                print("   ", line[:200], flush=True)
        return 0
    finally:
        try:
            webui_shot.api(url, "ui.select_tab", "emulate")
            st = webui_shot.state(url).get("emulate", {})
            if st.get("up") or st.get("running"):
                webui_shot.api(url, "emulate.toggle")
                time.sleep(20)
        except Exception as e:                        # noqa: BLE001
            print("stop:", e, flush=True)
        proc.terminate()
        print("rig after:", rig("ps")[1].strip() or "(nothing running)", flush=True)


def recheck(out_dir, native_json):
    """The check again on a saved run: <out_dir>/mode.log against the native cues in an after_cues.json."""
    with open(os.path.join(out_dir, "mode.log"), encoding="utf-8") as f:
        log = f.read()
    with open(native_json, encoding="utf-8") as f:
        nat = json.load(f)
    from pinball_decryptor.core.video_mode import document as D, sound as SND
    doc = D.load(os.path.join(REPO, "pinball_decryptor", "core", "video_mode", "examples", "night_harbour.json"))
    names = SND.machine_names(doc, SND.machine_plan(doc))
    res = check(log, "", nat["native"], names)
    with open(os.path.join(out_dir, "rig_cues.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    if "--recheck" in sys.argv:
        r = recheck(sys.argv[1], sys.argv[sys.argv.index("--recheck") + 1])
        print(json.dumps({k: r[k] for k in ("same_cues_as_native", "rig_cues", "native_cues", "steps_off_the_60hz_clock", "calls")}))
        sys.exit(0)
    sys.exit(main() or 0)
