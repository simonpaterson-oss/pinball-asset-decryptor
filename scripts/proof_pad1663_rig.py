"""PAD-1663 emulator proof: a rhythm video mode in time with its music on the machine, for three minutes.

    python scripts/proof_pad1663_rig.py <out_dir> --slot N

rhythm-3min (scripts/shot_pad1663.py: 384 notes at 128 bpm on an original three-minute drum track) is put on James
Bond LE 1.06 as a C code mode, ``vmrhythm``, the way PAD-1667's proof put Night Harbour there: the video mode engine
(vm_engine.c, the button kinds with it) steps once a tick, 60 a second, on the bot's winning buttons for the chart
(recorded natively), and its sound cues go through the mode's own sound route (vm_sound.h): the drum track as the
mode's own music bed. The rig's screen draws at its own lower rate the whole time.

Saved in <out_dir>: mode.log and rhythm.json:
  - the engine's steps against the machine's 60 a second clock (pm_ms), every 60th step logged: none may drift;
  - the music: the step that cued it, when the game's sound worker took the bed's request ("[pad] sound <n>") and
    when the mode saw it start: the machine's audio offset, what vm_set_audio_offset is for;
  - the judgements the rig's engine made (perfect / good / miss) and its end, against the native build's.
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
import proof_pad1667_rig as P  # noqa: E402  (its rig helper, launcher, card and C byte tables)
import shot_pad1663  # noqa: E402

SLUG = "vmrhythm"
ENGINE = P.ENGINE

MODE_C = r'''/* vmrhythm.c - PAD-1663 rig proof: a three-minute rhythm video mode, played by the video mode engine on the bot's
 * winning buttons. Start mode now (dump/vmrhythm.start) starts it; it steps the engine once a tick (60 a second) and
 * plays its sound cues through the mode's own sounds (vm_sound.h). */
#include "pad_mode.h"
#include "vm_engine.c"
#include "vm_sound.h"
#include "vm_proof_data.h"

#define FOLDER "vmrhythm"
static struct pa_assets own = { .folder = FOLDER };
static struct vm_sound snd = { &own, VM_NAMES, VM_NSOUNDS, 0, 0, 0, 0 };
static vm_engine E;
static unsigned long step, t0;
static int running, perfect, good, early, late, miss;

static void start(const char *why)
{
    int err;
    if (running) return;
    err = vm_load(&E, VM_PACK, (uint32_t)sizeof VM_PACK);
    if (err) { pm_log("vmrhythm: the pack did not load (%d at word %d)", err, (int)E.err_at); return; }
    vm_set_audio_offset(&E, VM_AUDIO_OFFSET_MS);
    vm_start(&E, VM_SEED, 0);
    step = 0; running = 1; t0 = pm_ms(); perfect = good = early = late = miss = 0;
    pm_log("vmrhythm: started (%s) at %lu ms: %u steps of the bot's buttons, audio offset %d ms", why, t0,
           (unsigned)sizeof VM_INPUTS, (int)VM_AUDIO_OFFSET_MS);
    vm_sound_start(&snd);
}
static void stop(const char *why)
{
    if (!running) return;
    running = 0;
    vm_sound_end(&snd);
    pm_log("vmrhythm: ended (%s) after %lu steps at %lu ms, outcome %d, score %d, perfect %d good %d early %d late %d miss %d, hash %08x%08x",
           why, step, pm_ms(), (int)E.outcome, (int)E.score, perfect, good, early, late, miss,
           (unsigned)(E.hash >> 32), (unsigned)E.hash);
}
static void on_init(void)
{
    pa_load(&own);
    pm_log("vmrhythm: ready on %s %s", pm_game(), pm_version());
}
static void on_tick(void)
{
    int i;
    pa_tick(&own);
    if (pm_trigger(FOLDER ".start")) start("trigger file");
    if (pm_trigger(FOLDER ".stop")) stop("trigger file");
    if (!running) return;
    if (step < sizeof VM_INPUTS) {          /* one engine step a tick: the engine's own 60 a second */
        int more = vm_step(&E, VM_INPUTS[step]);
        vm_sound_cues(&snd, &E, step);
        for (i = 0; i < E.nevents; i++) {
            const vm_event *v = &E.events[i];
            if (v->type == VM_EV_PROMPT_PERFECT) perfect++;
            else if (v->type == VM_EV_PROMPT_GOOD) { if (v->c == 1) early++; else if (v->c == 2) late++; else good++; }
            else if (v->type == VM_EV_PROMPT_MISS) miss++;
        }
        if (step % 60 == 0) pm_log("vmrhythm: step %lu at %lu ms, song %d ms", step, pm_ms(), (int)((E.song_steps * 1000) / 60));
        step++;
        if (!more) stop("the video mode finished");
    } else {
        stop("out of recorded buttons");
    }
}
static const struct pm_mode vmrhythm = { .name = "vmrhythm", .init = on_init, .tick = on_tick };
PM_REGISTER(vmrhythm);
'''


def make_mode(project, scratch, offset_ms):
    """The vmrhythm code mode in the project. Returns (comp, names, inputs, native END line, native counts)."""
    from pinball_decryptor.core.video_mode import compiler as C, document as D, sound as SND
    from pinball_decryptor.core.video_mode.engine import build
    src = os.path.join(scratch, "src")
    shot_pad1663.make_project(src)
    demo = os.path.join(src, "modes", "rhythm-3min")
    doc = D.load(os.path.join(demo, "video_mode.json"))
    comp = C.compile_doc(doc, demo)
    assert comp.ok, comp.problems
    exe = build.build_native(os.path.join(scratch, "native"))
    pack = os.path.join(scratch, "r.pack")
    with open(pack, "wb") as f:
        f.write(comp.pack)
    rec = os.path.join(scratch, "bot.inputs")
    out = subprocess.run([exe, pack, "--bot", "--record", rec, "--max", "20000", "--audio-offset", str(offset_ms)],
                         capture_output=True, text=True).stdout.splitlines()
    with open(rec, "rb") as f:
        inputs = f.read()
    counts = {"perfect": sum(1 for x in out if x.startswith("E ") and x.split()[2] == "14"),
              "miss": sum(1 for x in out if x.startswith("E ") and x.split()[2] == "15")}
    folder = os.path.join(project, "modes", SLUG)
    os.makedirs(folder, exist_ok=True)
    for f in ("vm_engine.c", "vm_engine.h", "vm_kinds2.c", "vm_tables.h", "vm_sound.h"):
        shutil.copy2(os.path.join(ENGINE, f), os.path.join(folder, f))
    plan, fields = SND.machine_files(doc, demo, folder)
    names = SND.machine_names(doc, plan)
    with open(os.path.join(folder, "vm_proof_data.h"), "w", encoding="utf-8", newline="\n") as f:
        f.write("/* GENERATED by scripts/proof_pad1663_rig.py: rhythm-3min's pack, the bot's buttons, the sounds' names */\n")
        f.write("#define VM_SEED 1u\n#define VM_NSOUNDS %d\n#define VM_AUDIO_OFFSET_MS %d\n" % (len(names), offset_ms))
        f.write("static const char *const VM_NAMES[%d] = { %s };\n" % (len(names), ", ".join('"%s"' % n for n in names)))
        f.write(P.c_bytes("VM_PACK", comp.pack))
        f.write(P.c_bytes("VM_INPUTS", inputs))
    with open(os.path.join(folder, SLUG + ".c"), "w", encoding="utf-8", newline="\n") as f:
        f.write(MODE_C)
    assets = dict({"format": 1, "name": "RHYTHM THREE MINUTES", "seconds": 200, "screen": False}, **fields)
    with open(os.path.join(folder, "assets.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(assets, f, indent=1)
    return comp, names, inputs, out[-1], counts


def check(log):
    step_re = re.compile(r"vmrhythm: step (\d+) at (\d+) ms, song (\d+) ms")
    cue_re = re.compile(r"vm sound: step (\d+) at (\d+) ms: cue (-?\d+) (\S+) op (\d+)")
    req_re = re.compile(r"^\s*(\d+) \[pad\] sound (\d+) ")
    start_re = re.compile(r"^\s*(\d+) \[vmrhythm\] own sound: music (\d+) started")
    steps = [tuple(int(m.group(i)) for i in (1, 2, 3)) for m in map(step_re.search, log.splitlines()) if m]
    cues = [(int(m.group(1)), int(m.group(2)), m.group(4), int(m.group(5))) for m in map(cue_re.search, log.splitlines()) if m]
    reqs = [(int(m.group(1)), int(m.group(2))) for m in map(req_re.search, log.splitlines()) if m]
    starts = [(int(m.group(1)), int(m.group(2))) for m in map(start_re.search, log.splitlines()) if m]
    res = {"logged_steps": len(steps)}
    if steps:
        s0, t0, _ = steps[0]
        drift = [round(t - (t0 + (s - s0) * 1000.0 / 60), 1) for s, t, _ in steps]
        res.update(first_step_ms=t0, last_step=steps[-1][0], seconds=round((steps[-1][1] - t0) / 1000.0, 1),
                   clock_drift_ms_max=max(map(abs, drift)), clock_drift_ms_last=drift[-1],
                   steps_off_the_60hz_clock=[s for (s, _, _), d in zip(steps, drift) if abs(d) > 20])
    music = [c for c in cues if c[3] == 1]
    if music:
        step, ms = music[-1][0], music[-1][1]          # the rhythm phase's own start of its music (the last op 1)
        req = next((t for t, n in reqs if t >= ms - 5), None)
        st = next((t for t, n in starts if t >= ms - 5), None)
        res.update(music_cue_step=step, music_cue_ms=ms, music_request_ms=req, music_started_ms=st,
                   audio_offset_request_ms=None if req is None else req - ms,
                   audio_offset_started_ms=None if st is None else st - ms)
    m = re.search(r"vmrhythm: ended \(([^)]*)\) after (\d+) steps at (\d+) ms, outcome (-?\d+), score (\d+), perfect (\d+) good (\d+) "
                  r"early (\d+) late (\d+) miss (\d+), hash (\w+)", log)
    if m:
        res["end"] = {"why": m.group(1), "steps": int(m.group(2)), "outcome": int(m.group(4)), "score": int(m.group(5)),
                      "perfect": int(m.group(6)), "good": int(m.group(7)), "early": int(m.group(8)), "late": int(m.group(9)),
                      "miss": int(m.group(10)), "hash": m.group(11)}
    res["cues"] = cues
    return res


def main():
    out_dir = os.path.abspath(sys.argv[1])
    slot = sys.argv[sys.argv.index("--slot") + 1] if "--slot" in sys.argv else ""
    offset = int(sys.argv[sys.argv.index("--offset") + 1]) if "--offset" in sys.argv else 0
    if slot not in ("1", "2", "3", "4", "5"):        # never the base rig (an empty or 0 slot is David's own)
        print("refused: --slot must be a rig slot of 1 to 5 taken for PAD-1663, not %r" % slot)
        return 2
    os.makedirs(out_dir, exist_ok=True)
    with open(P.RIGSH_WIN, "w", encoding="utf-8", newline="\n") as f:
        f.write(P.RIG_HELPER.replace("PAD-1030-check", "PAD-1663") % {"slot": slot, "rig": P.win_to_wsl(os.path.join(REPO, "tools", "spike2_emu"))})
    scratch = tempfile.mkdtemp(prefix="pad1663rig-")
    project = os.path.join(scratch, "Bond LE 1.06 Extract")
    os.makedirs(project)
    with open(os.path.join(project, ".extract_source.json"), "w", encoding="utf-8") as f:
        json.dump({"input_path": P.CARD, "input_name": os.path.basename(P.CARD), "card_version": "1.06"}, f)
    comp, names, inputs, native_end, native_counts = make_mode(project, scratch, offset)
    print("names:", names, "native:", native_end, native_counts, flush=True)
    real = os.path.expandvars(r"%APPDATA%\pinball_decryptor\settings.json")
    with open(real, encoding="utf-8") as f:
        codes = json.load(f).get("preview_codes", [])
    launcher = os.path.join(scratch, "launch1663.py")
    with open(launcher, "w", encoding="utf-8") as f:
        f.write(P.LAUNCHER % REPO)
    settings = os.path.join(scratch, "settings.json")
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"disclaimer_accepted": True, "last_manufacturer": "stern", "preview_codes": codes,
                   "emulate_card": P.CARD, "manufacturers": {"stern": {"extract_output": project, "write_assets": project}}}, f)
    cfgdir = os.path.join(scratch, "cfg", "pinball_decryptor")      # a rig run is always muted
    os.makedirs(cfgdir, exist_ok=True)
    with open(os.path.join(cfgdir, "audio_ctl.json"), "w", encoding="utf-8") as f:
        json.dump({"gain": 0.0, "muted": True}, f)
    import site
    tmp = os.path.join(scratch, "tmp")
    os.makedirs(tmp, exist_ok=True)
    env = {"PYTHONPATH": site.getusersitepackages(), "TEMP": tmp, "TMP": tmp, "PAD_UI_NO_RIG": "",
           "PAD_UI_NO_PREREQS": "1", "PAD_SLOT": slot, "PAD_TICKET": "", "PAD_LABEL": "PAD-1663",
           "PAD_HIDDEN": "1", "PAD_AUDIO": "0"}
    proc, url = webui_shot.start_server(settings, scratch, app_cmd=[sys.executable, launcher], extra_env=env)
    print("server", url.split("?")[0], "scratch", scratch, flush=True)
    try:
        webui_shot.api(url, "ui.pick_manufacturer", "stern")
        webui_shot.api(url, "ui.select_tab", "modes")
        time.sleep(3)
        webui_shot.api(url, "modes.select", SLUG, "code")
        time.sleep(2)
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
            print(k, P.rig(k)[1].strip()[-200:], flush=True)
        time.sleep(25)
        P.rig("plunge")
        time.sleep(10)
        webui_shot.api(url, "modes.start_now")
        time.sleep(len(inputs) / 60.0 + 20)
        log = P.rig("modelog")[1]
        with open(os.path.join(out_dir, "mode.log"), "w", encoding="utf-8") as f:
            f.write(log)
        res = check(log)
        res.update({"names": names, "native_end": native_end, "native_counts": native_counts, "audio_offset_set_ms": offset})
        with open(os.path.join(out_dir, "rhythm.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)
        print(json.dumps({k: v for k, v in res.items() if k != "cues"}), flush=True)
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


if __name__ == "__main__":
    if "--recheck" in sys.argv:
        with open(os.path.join(sys.argv[1], "mode.log"), encoding="utf-8") as f:
            print(json.dumps({k: v for k, v in check(f.read()).items() if k != "cues"}))
        sys.exit(0)
    sys.exit(main() or 0)
