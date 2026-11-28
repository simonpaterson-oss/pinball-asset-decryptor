"""PAD-1663 proof: the button kinds played in the app's player, and rhythm in time with its music.

    python scripts/shot_pad1663.py <repo> <out dir> [--prefix after|before] [--rhythm-only] [--no-rhythm]

Serves <repo> (the worktree, or a main export for the before shots) on a scratch project holding one video mode
per button kind, each the starter the picker makes (core/video_mode/kinds_buttons.py, always taken from this
script's own tree), and ``rhythm-3min``: a three-minute chart at 128 bpm on an original drum track of the same
length. Edge runs muted at the process (--mute-audio): Web Audio still runs and is timed, nothing is heard.

Shoots <prefix>_play_<kind>.png: the kind's starter in the player, paused partway into the bot's winning buttons
(tests/data/video_mode/kinds2/<kind>_win.inputs, replayed), and <prefix>_player_bar.png (after: the sound
offset and Calibrate; with the calibration panel open, after_calibrate.png).

``after`` also writes after_kinds.json: each kind's winning buttons replayed in the app (the verdict: same hash
as the native build) to a win, and a play with no buttons to a loss; and after_rhythm.json: rhythm-3min played
for its whole three minutes with sound on, at 60 fps and at the machine's 29, by a player in the page that
presses each note's button when its beat is heard by the audio clock (output latency included): every
judgement counted, and the engine's distance from the music sampled every frame. Last, a frame stall test:
the page blocked 150 ms three times, and how many frames the rhythm phase takes to be back on its music.
"""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MINE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, MINE)
import webui_shot  # noqa: E402
from pinball_decryptor.core.video_mode import kinds_buttons, document  # noqa: E402

LAUNCHER = r'''
import sys
sys.path.insert(0, %r)
from pinball_decryptor.webui import host
sys.argv = ["host"] + sys.argv[1:]
sys.exit(host.main())
'''
KINDS = list(kinds_buttons.KINDS2)
SHOT_AT = {"mash": 160, "alternate": 200, "tug": 420, "rhythm": 700, "sequence": 150, "dodge": 265, "shield": 405}
BPM3, NOTES3 = 128, 384
GOLDEN = os.path.join(MINE, "tests", "data", "video_mode", "kinds2")


def _arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def make_project(project):
    for kind in KINDS:
        doc, files = kinds_buttons.new_doc(kind, "kind-" + kind)
        d = os.path.join(project, "modes", "kind-" + kind)
        os.makedirs(d, exist_ok=True)
        kinds_buttons.make_files(d, files)
        document.save(os.path.join(d, "video_mode.json"), doc)
    doc, files = kinds_buttons.new_doc("rhythm", "rhythm-3min")
    s = doc["phases"][0]["settings"]
    s["tempo_bpm"] = BPM3
    s["chart"] = [{"beat": 4 + i, "button": ["left", "action", "right"][i % 3]} for i in range(NOTES3)]
    s["music"] = "long_beat"
    doc["title"] = "Rhythm, three minutes"
    doc["assets"]["sounds"] = [{"id": "long_beat", "file": "sound/long_beat_128.wav", "role": "music", "volume": 0.8, "loop": False}]
    d = os.path.join(project, "modes", "rhythm-3min")
    os.makedirs(os.path.join(d, "sound"), exist_ok=True)
    with open(os.path.join(d, "sound", "long_beat_128.wav"), "wb") as f:
        f.write(kinds_buttons.beat_wav(BPM3, 4 + NOTES3 + 8))
    document.save(os.path.join(d, "video_mode.json"), doc)
    return [round((4 + i) * 60000.0 / BPM3) for i in range(NOTES3)], [[1, 4, 2][i % 3] for i in range(NOTES3)]


def b64(path):
    import base64
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def open_player(pg, url, slug):
    if pg.query_selector(".vmp-top"):
        pg.click(".vmp-top button:has-text('Back to editing')")
        time.sleep(0.8)
    webui_shot.api(url, "vmodes.select", slug)
    t0 = time.time()
    while time.time() - t0 < 30:
        if (webui_shot.state(url).get("vmodes") or {}).get("slug") == slug:
            break
        time.sleep(0.3)
    time.sleep(1.2)
    pg.click(".vm-page .pagehead button:has-text('Play')")
    pg.wait_for_function("window.__vmPlayer && window.__vmPlayer.ready", timeout=60000)
    time.sleep(0.5)


def replay_to(pg, kind, step):
    """Replay the bot's winning buttons and pause at `step` (the frame it lands on)."""
    with open(os.path.join(GOLDEN, kind + "_win.inputs"), "rb") as f:
        n = len(f.read())
    rec = {"data": b64(os.path.join(GOLDEN, kind + "_win.inputs")), "seed": 1, "card": -1, "steps": n, "hash": "", "audio_offset": 0}
    pg.evaluate("r => window.__vmPlayer.replay(r)", rec)
    pg.wait_for_function("s => window.__vmPlayer.run.e.stepNo() >= s", arg=step, timeout=60000)
    pg.evaluate("window.__vmPlayer.run.setPaused(true)")
    time.sleep(0.3)


RHYTHM_DRIVER = r"""
([notes, bits]) => {
  const P = window.__vmPlayer, r = P.run;
  const d = { i: 0, counts: { good: 0, perfect: 0, miss: 0, early: 0, late: 0 }, drift: [], held: 0, frames: 0, firstMs: null, lastMs: null };
  window.__drv = d;
  const ev = r.event.bind(r);
  r.event = (e) => {
    if (e.type === 14) d.counts.perfect++;
    else if (e.type === 13) { if (e.c === 1) d.counts.early++; else if (e.c === 2) d.counts.late++; else d.counts.good++; }
    else if (e.type === 15) d.counts.miss++;
    ev(e);
  };
  const fr = r.frame.bind(r);
  r.frame = (now) => {
    // a player who presses on the beat they hear: the music's position by the audio clock, less nothing else
    // (the engine already allows for this computer's output latency, r.offset)
    if (d.held) { r.keys &= ~d.held; d.held = 0; }
    const pos = r.sounds.musicPos();
    if (pos != null && d.i < notes.length) {
      const heard = pos * 1000 - r.sounds.latencyMs();
      if (heard >= notes[d.i] - 8) { r.keys |= bits[d.i]; d.held = bits[d.i]; d.i++; }
    }
    fr(now);
    d.frames++;
    if (r.drift && pos != null && pos > 2) {
      d.drift.push(r.drift.ms);
      if (d.firstMs == null) d.firstMs = r.drift.ms;
      d.lastMs = r.drift.ms;
    }
  };
}
"""


def rhythm_run(pg, url, fps_label, notes, bits):
    open_player(pg, url, "rhythm-3min")
    if pg.query_selector(".vmp-top button:has-text('Sound off')"):
        pg.click(".vmp-top button:has-text('Sound off')")
    pg.click(".vmp-bar button:has-text('%s')" % fps_label)
    pg.evaluate("window.__vmPlayer.run.restart(null)")
    pg.evaluate(RHYTHM_DRIVER, [notes, bits])
    pg.evaluate("window.__vmPlayer.perfReset()")
    t0 = time.time()
    pg.wait_for_function("window.__vmPlayer.done()", timeout=260000, polling=1000)
    wall = time.time() - t0
    d = pg.evaluate("""() => { const d = window.__drv, a = d.drift.map(Math.abs);
        return { counts: d.counts, pressed: d.i, frames: d.frames, samples: a.length,
                 max_abs_drift_ms: Math.max(...a), mean_abs_drift_ms: a.reduce((x, y) => x + y, 0) / a.length,
                 first_ms: d.firstMs, last_ms: d.lastMs }; }""")
    d["done"] = pg.evaluate("window.__vmPlayer.done()")
    d["perf"] = pg.evaluate("window.__vmPlayer.perf()")
    d["sync"] = pg.evaluate("window.__vmPlayer.sync()")
    d["sound"] = pg.evaluate("window.__vmPlayer.sound()")
    d["wall_s"] = round(wall, 1)
    return d


def stall_test(pg, url):
    """Block the page 150 ms three times during the rhythm phase: how far the engine falls from the music, and
    in how many frames it is back within a step of it."""
    open_player(pg, url, "rhythm-3min")
    if pg.query_selector(".vmp-top button:has-text('Sound off')"):
        pg.click(".vmp-top button:has-text('Sound off')")
    pg.click(".vmp-bar button:has-text('60 fps')")
    pg.evaluate("window.__vmPlayer.run.restart(null)")
    time.sleep(6)
    out = []
    for _ in range(3):
        res = pg.evaluate("""() => new Promise((done) => {
            const r = window.__vmPlayer.run, t = performance.now();
            while (performance.now() - t < 150) { /* a stalled frame */ }
            const seen = []; let k = 0;
            const look = () => { seen.push(r.drift ? r.drift.ms : null); if (++k < 30) requestAnimationFrame(look); else done(seen); };
            requestAnimationFrame(look); })""")
        back = next((i for i, v in enumerate(res) if v is not None and abs(v) <= 17), None)
        out.append({"drift_after_ms": res[:8], "frames_to_within_a_step": back})
        time.sleep(3)
    return out


def main():
    repo = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2])
    prefix = _arg("--prefix", "after")
    after = prefix == "after"
    os.makedirs(out, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="pad1663-")
    project = os.path.join(scratch, "Button kinds project")
    notes, bits = make_project(project)
    launcher = os.path.join(scratch, "launch1663.py")
    with open(launcher, "w", encoding="utf-8") as f:
        f.write(LAUNCHER % repo)
    settings = os.path.join(scratch, "settings.json")
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"disclaimer_accepted": True, "last_manufacturer": "stern", "theme": "dark",
                   "manufacturers": {"stern": {"extract_output": project, "write_assets": project, "write_output": scratch}}}, f)
    import site
    proc, url = webui_shot.start_server(settings, scratch, app_cmd=[sys.executable, launcher],
                                        extra_env={"PYTHONPATH": site.getusersitepackages()})
    shot = lambda pg, name: pg.screenshot(path=os.path.join(out, "%s_%s.png" % (prefix, name)))
    try:
        webui_shot.api(url, "ui.pick_manufacturer", "stern")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(channel="msedge", args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"])
            pg = b.new_page(viewport={"width": 1600, "height": 1000})
            pg.goto(url)
            pg.wait_for_function("window.__padReady === true", timeout=90000)
            webui_shot.api(url, "ui.select_tab", "vmodes")
            time.sleep(2)
            kinds = {}
            if "--rhythm-only" not in sys.argv:
                for kind in KINDS:
                    open_player(pg, url, "kind-" + kind)
                    replay_to(pg, kind, SHOT_AT[kind])
                    shot(pg, "play_" + kind)
                    if kind == "mash":
                        pg.screenshot(path=os.path.join(out, "%s_player_bar.png" % prefix), clip={"x": 0, "y": 880, "width": 1600, "height": 120})
                    pg.evaluate("window.__vmPlayer.run.setPaused(false)")
                    if not after:
                        continue
                    # the win: the bot's buttons replayed to the end; the app's hash against the recorded native one
                    spec = json.load(open(os.path.join(GOLDEN, "golden.json")))["runs"][kind + "_win"]
                    rec = {"data": b64(os.path.join(GOLDEN, kind + "_win.inputs")), "seed": 1, "card": -1,
                           "steps": spec["steps"], "hash": spec["hash"], "audio_offset": 0}
                    pg.evaluate("r => window.__vmPlayer.replay(r)", rec)
                    pg.wait_for_function("window.__vmPlayer.verdict()", timeout=120000)
                    win = {"verdict": pg.evaluate("window.__vmPlayer.verdict()"), "outcome": pg.evaluate("window.__vmPlayer.run.e.outcome()")}
                    # the loss: a live play, nobody at the buttons
                    pg.evaluate("window.__vmPlayer.run.restart(null)")
                    pg.wait_for_function("window.__vmPlayer.done()", timeout=120000)
                    loss = pg.evaluate("window.__vmPlayer.done()")
                    kinds[kind] = {"win": win, "loss": loss, "golden": spec}
                    print(kind, json.dumps(kinds[kind])[:300], flush=True)
                if after:
                    with open(os.path.join(out, "after_kinds.json"), "w") as f:
                        json.dump(kinds, f, indent=1)
                    pg.click(".vmp-bar button:has-text('Calibrate')")
                    time.sleep(0.6)
                    shot(pg, "calibrate")
                    pg.keyboard.press("Escape")
            if after and "--no-rhythm" not in sys.argv:
                res = {"bpm": BPM3, "notes": NOTES3, "chart_s": round(notes[-1] / 1000.0, 1)}
                res["fps60"] = rhythm_run(pg, url, "60 fps", notes, bits)
                print("60 fps", json.dumps(res["fps60"])[:400], flush=True)
                res["machine29"] = rhythm_run(pg, url, "Machine", notes, bits)
                print("29 fps", json.dumps(res["machine29"])[:400], flush=True)
                res["stalls"] = stall_test(pg, url)
                print("stalls", res["stalls"], flush=True)
                with open(os.path.join(out, "after_rhythm.json"), "w") as f:
                    json.dump(res, f, indent=1)
            b.close()
    finally:
        proc.terminate()
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    main()
