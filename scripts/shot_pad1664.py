"""PAD-1664 proof shots: the video mode editor's storyboard and timeline.

    python scripts/shot_pad1664.py <repo> <out dir> [--prefix after|before] [--light] [--probe]

Serves <repo> on a scratch project holding Night Harbour (scripts/vm_demo_art.py, original placeholder art) and the
timeline's test document, tests/data/video_mode/keyframes.json, as a mode of its own with the same art. Shoots:

  <prefix>_vmodes_timeline.png     the parade phase scrubbed to 6.5 s: the timeline's tracks, keys, waves, sounds and
                                   markers, a drone's motion path on the stage with its keys and handles, the picked
                                   key in the inspector with its easing presets and curve
  <prefix>_vmodes_storyboard.png   the boat chase rebuilt as a storyboard (intro, chase, boss, aim, charge, won or
                                   lost), built in the app from the board itself

``after`` also writes after_timeline_checks.json: scrubbing 60 s (seek times in the page), what the stage draws at
a scrub against what the player draws at that step, a key dragged on the stage and on the timeline (what the
document holds after each), and the boat chase's flow as the storyboard left it. Needs Playwright and the installed
Edge (PAD_PWLIB=C:\\tmp\\pwlib).
"""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import webui_shot  # noqa: E402
import vm_demo_art  # noqa: E402

LAUNCHER = r'''
import sys
sys.path.insert(0, %r)
from pinball_decryptor.webui import host
sys.argv = ["host"] + sys.argv[1:]
sys.exit(host.main())
'''
_SHOT = []


def _arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def _wait(url, ns, ok, what, seconds=60):
    t0 = time.time()
    while time.time() - t0 < seconds:
        s = webui_shot.state(url).get(ns) or {}
        if ok(s):
            return s
        time.sleep(0.4)
    raise SystemExit("timed out waiting for " + what)


def shot(pg, name):
    pg.screenshot(path=os.path.join(_SHOT[0], "%s_%s.png" % (_SHOT[1], name)))


def open_editor(pg, url, slug):
    webui_shot.api(url, "vmodes.select", slug)
    _wait(url, "vmodes", lambda s: s.get("slug") == slug, "the mode " + slug)
    time.sleep(1.0)
    pg.click(".vm-page .pagehead button:has-text('Edit')")
    pg.wait_for_function("window.__vmEditor && window.__vmEditor.ready", timeout=30000)
    time.sleep(0.8)


def settled(pg):
    pg.evaluate("window.__vmEditor.settled()")
    time.sleep(0.25)


def doc(pg):
    settled(pg)
    return pg.evaluate("window.__vmEditor.doc()")


def make_project(repo, scratch):
    project = os.path.join(scratch, "Night Harbour project")
    nh = os.path.join(project, "modes", "night-harbour")
    vm_demo_art.make_mode(nh)
    kf = os.path.join(project, "modes", "keyframes")
    os.makedirs(kf, exist_ok=True)
    shutil.copytree(os.path.join(nh, "art"), os.path.join(kf, "art"))
    with open(os.path.join(repo, "tests", "data", "video_mode", "keyframes.json"), encoding="utf-8") as f:
        d = json.load(f)
    with open(os.path.join(nh, "video_mode.json"), encoding="utf-8") as f:
        d["assets"] = json.load(f)["assets"]                 # the demo art's pictures, with their files
    d["editor"] = {"markers": {"parade": [{"at_s": 4, "label": "Drone at the top"}, {"at_s": 9.5, "label": "Dive"},
                                          {"at_s": 15, "label": "Overshoot"}]}}
    d["phases"][0]["spawns"] = [{"thing": "drone", "at_s": 2, "every_s": 0.75, "count": 6, "x": 1400, "y": 120,
                                 "mover": {"type": "straight", "speed": 240, "direction": 180}},
                                {"thing": "mine", "at_s": 11, "every_s": 1.5, "count": 4, "x": 1400, "y": 700,
                                 "mover": {"type": "straight", "speed": 180, "direction": 180}}]
    with open(os.path.join(kf, "video_mode.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    return project


def checks(pg, repo):
    """What the after shots stand on, measured in the app itself."""
    res = {}
    # 1. scrubbing 60 s: the first seek to the end, then 300 seeks anywhere in the minute (seek + the draw list read)
    res["scrub_60s"] = pg.evaluate("""() => {
      const ed = window.__vmEditor.ed, e = ed.e, t = [];
      e.seekDirty(0);
      let a = performance.now(); e.seek(ed.ph, 3599, 2); e.drawWords(); const first = performance.now() - a;
      let x = 1664;
      for (let i = 0; i < 300; i++) { x = (x * 1103515245 + 12345) & 0x7fffffff; const s = x % 3600;
        a = performance.now(); e.seek(ed.ph, s, 2); e.drawWords(); t.push(performance.now() - a); }
      t.sort((p, q) => p - q);
      return { first_ms: +first.toFixed(2), avg_ms: +(t.reduce((p, q) => p + q, 0) / t.length).toFixed(3),
               p95_ms: +t[Math.floor(t.length * 0.95)].toFixed(3), worst_ms: +t[t.length - 1].toFixed(3), seeks: t.length };
    }""")
    # 2. the stage at a scrub is the game at that step: Start here on the parade's card, nothing pressed, in the app
    res["scrub_is_play"] = pg.evaluate("""() => {
      const ed = window.__vmEditor.ed, e = ed.e, same = [];
      for (const s of [1, 60, 390, 721, 1199]) {
        e.seek(ed.ph, s, 0); const a = Array.from(e.drawWords());
        e.startAt(1, 0, 0); let w = null;
        for (let i = 0; i < 89 + s + 1; i++) { e.step(0); if (i === 89 + s) w = Array.from(e.drawWords()); }
        same.push({ step: s, words: a.length, same: a.length === w.length && a.every((v, i) => v === w[i]) });
      }
      e.seekDirty(0); ed.dirty(true);
      return same;
    }""")
    # 3. the app's engine replays the keyframe golden to the hash the native, WebAssembly and ARM builds give
    gold = json.load(open(os.path.join(repo, "tests", "data", "video_mode", "golden", "golden.json")))["runs"]
    sys.path.insert(0, repo)
    import random as _r
    rng = _r.Random(1664)
    held, inputs = 0, []
    for _ in range(6000):
        if rng.random() < 0.2:
            held = rng.randrange(8)
        inputs.append(held | (8 if rng.random() < 0.01 else 0))
    from pinball_decryptor.core.video_mode import compiler, document
    import base64
    kdoc = document.migrate(json.load(open(os.path.join(repo, "tests", "data", "video_mode", "keyframes.json"), encoding="utf-8")))
    pack = base64.b64encode(compiler.compile_doc(kdoc).pack).decode()
    res["app_replay"] = pg.evaluate("""([pack, inputs, seed, level]) => {
      const ed = window.__vmEditor.ed, e = ed.e, b = Uint8Array.from(atob(pack), (c) => c.charCodeAt(0));
      e.load(b); e.start(seed, level); let n = 0;
      for (const v of inputs) { n++; if (!e.step(v)) break; }
      const h = e.hash(); ed.reloadPack();
      return { hash: h, steps: n };
    }""", [pack, inputs, gold["keyframes_random"]["seed"], gold["keyframes_random"]["level"]])
    res["app_replay"]["golden"] = gold["keyframes_random"]["hash"]
    res["app_replay"]["same_as_native_wasm_arm"] = res["app_replay"]["hash"] == gold["keyframes_random"]["hash"]
    time.sleep(0.5)
    # 4. a key dragged on the stage: the drone's key at 9.5 s moved 100 px left and 60 px down
    pg.evaluate("window.__vmEditor.phase('parade')")
    pg.evaluate("window.__vmEditor.selectIndex(0)")
    pg.evaluate("window.__vmEditor.pickKey(0, 2)")
    pg.evaluate("window.__vmEditor.seek(570)")
    time.sleep(0.5)
    before = doc(pg)["phases"][0]["tracks"][0]["keys"][2]
    a = pg.evaluate("window.__vmEditor.toPage(1240, 300)")
    bpt = pg.evaluate("window.__vmEditor.toPage(1140, 360)")
    pg.mouse.move(*a)
    pg.mouse.down()
    for j in range(1, 16):
        pg.mouse.move(a[0] + (bpt[0] - a[0]) * j / 15, a[1] + (bpt[1] - a[1]) * j / 15)
        time.sleep(0.016)
    pg.mouse.up()
    after = doc(pg)["phases"][0]["tracks"][0]["keys"][2]
    res["stage_key_drag"] = {"before": [before["x"], before["y"]], "after": [after["x"], after["y"]]}
    # 5. a thing dragged at the playhead makes a position key there (the crate at 14 s)
    pg.evaluate("window.__vmEditor.seek(840)")
    pg.evaluate("window.__vmEditor.selectIndex(2)")
    time.sleep(0.4)
    c = pg.evaluate("window.__vmEditor.centreOf(2)")
    a = pg.evaluate("([x, y]) => window.__vmEditor.toPage(x, y)", c)
    pg.mouse.move(*a)
    pg.keyboard.down("Control")                       # Ctrl: placed freely, no snapping
    pg.mouse.down()
    k = pg.evaluate("window.__vmEditor.ed.view.k")
    for j in range(1, 13):
        pg.mouse.move(a[0], a[1] - 60 * k * j / 12)
        time.sleep(0.016)
    pg.mouse.up()
    pg.keyboard.up("Control")
    keys = doc(pg)["phases"][0]["tracks"][4]["keys"]
    res["auto_key"] = {"keys": [[k["at_s"], k["x"], k["y"]] for k in keys], "dragged_from": [790, 600], "by": [0, -60]}
    # 6. undo puts both back
    pg.keyboard.press("Control+z")
    settled(pg)
    pg.keyboard.press("Control+z")
    settled(pg)
    d = doc(pg)
    res["undo_back"] = d["phases"][0]["tracks"][0]["keys"][2]["x"] == before["x"] and len(d["phases"][0]["tracks"][4]["keys"]) == 2
    return res


def storyboard(pg, url, light):
    """The reference's boat chase as a storyboard, made on the board: Night Harbour (intro, chase, boss, charge, won
    or lost) gains an Aim phase between the boss and the charge, put in with the board's own insert."""
    pg.click(".vme-top button:has-text('Done')")
    time.sleep(0.6)
    open_editor(pg, url, "night-harbour")
    pg.click(".vme-top button:has-text('Storyboard')")
    pg.wait_for_function("window.__vmStory && window.__vmStory.ready", timeout=20000)
    time.sleep(0.5)
    if not any(c["id"] == "c_aim" or "aim" in c["id"] for c in pg.evaluate("window.__vmStory.cards()")):
        new_id = pg.evaluate("window.__vmStory.insertPhase('c_boss', 'won', 'aim')")
        settled(pg)
        time.sleep(0.8)
        pg.evaluate("(id) => window.__vmStory.select(id)", new_id)
    time.sleep(0.6)
    shot(pg, "vmodes_storyboard" + ("_light" if light else ""))
    d = doc(pg)
    flow = {c["id"]: {k: c[k] for k in ("card", "phase", "clip", "then", "won", "lost", "tries", "outcome") if k in c}
            for c in d["flow"]["cards"]}
    return {"start": d["flow"]["start"], "cards": flow, "phases": [[p["id"], p["kind"]] for p in d["phases"]],
            "problems": pg.evaluate("window.__vmStory.problems()")}


def main():
    repo = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2])
    prefix = _arg("--prefix", "after")
    light = "--light" in sys.argv
    os.makedirs(out, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="pad1664-")
    project = make_project(repo, scratch)
    launcher = os.path.join(scratch, "launch1664.py")
    with open(launcher, "w", encoding="utf-8") as f:
        f.write(LAUNCHER % repo)
    settings = os.path.join(scratch, "settings.json")
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"disclaimer_accepted": True, "last_manufacturer": "stern", "theme": "light" if light else "dark",
                   "manufacturers": {"stern": {"extract_output": project, "write_assets": project,
                                               "write_output": scratch}}}, f)
    import site
    proc, url = webui_shot.start_server(settings, scratch, app_cmd=[sys.executable, launcher],
                                        extra_env={"PYTHONPATH": site.getusersitepackages()})
    _SHOT[:] = [out, prefix]
    errors = []
    try:
        webui_shot.api(url, "ui.pick_manufacturer", "stern")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(channel="msedge", args=["--mute-audio"])
            pg = b.new_page(viewport={"width": 1600, "height": 1000})
            pg.on("pageerror", lambda e: (errors.append(str(e)), print("PAGE ERROR:", e)))
            pg.on("console", lambda m: m.type in ("error", "warning") and "Failed to load resource" not in m.text and print("CONSOLE:", m.text[:300]))
            pg.goto(url)
            pg.wait_for_function("window.__padReady === true", timeout=90000)
            webui_shot.api(url, "ui.select_tab", "vmodes")
            _wait(url, "vmodes", lambda s: s.get("modes"), "the modes")
            try:
                pg.click("button:has-text('Hide log')", timeout=3000)
            except Exception:  # noqa: BLE001 - the log is already folded
                pass
            open_editor(pg, url, "keyframes")
            pg.evaluate("window.__vmEditor.phase('parade')")
            time.sleep(0.4)
            pg.evaluate("window.__vmEditor.selectIndex(0)")
            pg.evaluate("window.__vmEditor.seek(390)")
            pg.evaluate("window.__vmEditor.pickKey(0, 2)")
            time.sleep(0.8)
            shot(pg, "vmodes_timeline" + ("_light" if light else ""))
            if "--probe" in sys.argv:
                print("errors:", errors)
                return
            res = checks(pg, repo) if prefix == "after" and not light else None
            board = storyboard(pg, url, light)
            if res is not None:
                res["storyboard_flow"] = board
                res["page_errors"] = errors
                with open(os.path.join(out, "after_timeline_checks.json"), "w", encoding="utf-8") as f:
                    json.dump(res, f, indent=2)
                print(json.dumps({k: v for k, v in res.items() if k != "storyboard_flow"}, indent=1)[:3000])
            b.close()
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
