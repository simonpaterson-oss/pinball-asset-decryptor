"""PAD-1661 proof shots: the video mode editor (the stage, the layers and the inspector).

    python scripts/shot_pad1661.py <repo> <out dir> [--prefix after|before] [--light]

Serves <repo> on a scratch project holding the plan's worked example, Night Harbour, with original placeholder art
(scripts/vm_demo_art.py), and the 300-thing desk. Shoots:

  <prefix>_vmodes_editor.png     after: Night Harbour's boss phase in the editor, the warship selected with its
                                 handles, the layers and the inspector (before: the tab, which had no editor)
  <prefix>_vmodes_editor_multi.png  after: three things selected, the align bar, a snap guide with its distance
  <prefix>_vmodes_editor_empty.png  after: a new mode's empty phase, the empty states
  <prefix>_vmodes_editor_light.png  after: the same as the first in the light theme (with --light)

``after`` also writes after_editor_checks.json: dragging one thing on the 300-thing desk for 3 s (frame times
from requestAnimationFrame), a layout made with the mouse only and one with the keyboard only (what the document
holds after each), and the undo history replayed back to the empty document. Needs Playwright (the user
site-packages one) and the installed Edge.
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


def _arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def _wait(url, ns, ok, what, seconds=60):
    t0 = time.time()
    while time.time() - t0 < seconds:
        s = webui_shot.state(url).get(ns) or {}
        if ok(s):
            return s
        time.sleep(0.5)
    raise SystemExit("timed out waiting for " + what)


_SHOT = []


def shot(pg, name):
    pg.screenshot(path=os.path.join(_SHOT[0], "%s_%s.png" % (_SHOT[1], name)))


def open_editor(pg, url, slug):
    webui_shot.api(url, "vmodes.select", slug)
    _wait(url, "vmodes", lambda s: s.get("slug") == slug, "the mode " + slug)
    time.sleep(1.0)
    pg.click(".vm-page .pagehead button:has-text('Edit')")
    pg.wait_for_function("window.__vmEditor && window.__vmEditor.ready", timeout=30000)
    time.sleep(0.6)


def doc(pg):
    pg.evaluate("window.__vmEditor.settled()")       # every change saved first
    time.sleep(0.2)
    return pg.evaluate("window.__vmEditor.doc()")


def stage_point(pg, x, y):
    """A stage pixel as a page point."""
    return pg.evaluate("([x, y]) => window.__vmEditor.toPage(x, y)", [x, y])


def drag(pg, a, b, steps=12, mods=()):
    for m in mods:
        pg.keyboard.down(m)
    pg.mouse.move(*a)
    pg.mouse.down()
    for i in range(1, steps + 1):
        pg.mouse.move(a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps)
    pg.mouse.up()
    for m in mods:
        pg.keyboard.up(m)


def new_mode_with_art(url, title, slug):
    """A new video mode from the tab, given Night Harbour's pictures (the art copied, the pictures named in its file)
    and nothing else: an empty stage to lay out."""
    webui_shot.api(url, "vmodes.new_mode", title)
    _wait(url, "vmodes", lambda s: s.get("slug") == slug, "the new mode")
    src = os.path.join(_PROJECT[0], "modes", "night-harbour")
    dst = os.path.join(_PROJECT[0], "modes", slug)
    shutil.copytree(os.path.join(src, "art"), os.path.join(dst, "art"))
    with open(os.path.join(src, "video_mode.json"), encoding="utf-8") as f:
        pics = json.load(f)["assets"]["pictures"]
    p = os.path.join(dst, "video_mode.json")
    with open(p, encoding="utf-8") as f:
        doc = json.load(f)
    doc["assets"]["pictures"] = pics
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    webui_shot.api(url, "vmodes.refresh")
    time.sleep(0.5)


def checks_after(pg, url, out):
    res = {"play_from_editor": _PLAY[:]}
    only_keys = "--only-keys" in sys.argv
    # --- the 300-thing desk: drag one thing for 3 s, frame times from requestAnimationFrame
    if not only_keys:
        stage_and_mouse(pg, url, res)
    keys_only(pg, url, res, out)


def stage_and_mouse(pg, url, res):
    open_editor(pg, url, "stage-300")
    pg.evaluate("window.__vmEditor.selectIndex(0)")
    p0 = pg.evaluate("window.__vmEditor.centreOf(0)")
    a = stage_point(pg, *p0)
    pg.evaluate("window.__vmEditor.perfReset()")
    pg.mouse.move(*a)
    pg.mouse.down()
    t0 = time.time()
    k = 0
    while time.time() - t0 < 3.0:
        k += 1
        pg.mouse.move(a[0] + 120 * ((k % 60) / 60.0), a[1] + 40 * (((k // 60) % 2)))
        time.sleep(0.008)
    pg.mouse.up()
    res["desk_300_drag"] = pg.evaluate("window.__vmEditor.perf()")
    shot(pg, "vmodes_editor_desk300")
    pg.keyboard.press("Control+z")
    time.sleep(0.5)
    pg.click(".vme-top button:has-text('Done')")
    time.sleep(0.5)

    # --- a phase laid out from nothing with the mouse only
    new_mode_with_art(url, "Mouse only", "mouse-only")
    open_editor(pg, url, "mouse-only")
    shot(pg, "vmodes_editor_empty")
    stage = pg.query_selector(".vme-stage").bounding_box()
    for i, name in enumerate(["boat", "drone", "drone", "crate"]):
        src = pg.query_selector(".vme-asset[data-id='%s']" % name).bounding_box()
        pg.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
        pg.mouse.down()
        tx = stage["x"] + stage["width"] * (0.25 + 0.17 * i)
        ty = stage["y"] + stage["height"] * (0.6 if i == 0 else 0.3)
        for j in range(1, 11):
            pg.mouse.move(src["x"] + (tx - src["x"]) * j / 10, src["y"] + (ty - src["y"]) * j / 10)
        pg.mouse.up()
        time.sleep(0.25)
    # marquee the three top ones, align their tops, distribute them
    drag(pg, (stage["x"] + stage["width"] * 0.35, stage["y"] + stage["height"] * 0.05),
         (stage["x"] + stage["width"] * 0.98, stage["y"] + stage["height"] * 0.45))
    time.sleep(0.2)
    pg.click(".vme-align button[data-act='top']")
    pg.click(".vme-align button[data-act='dist_x']")
    time.sleep(0.4)
    res["mouse_only"] = doc(pg)["phases"][0].get("place", [])
    pg.click(".vme-top button:has-text('Done')")
    time.sleep(0.5)



def keys_only(pg, url, res, out):
    # --- the same with the keyboard only: the command palette adds, Tab picks, arrows nudge, fields take numbers
    new_mode_with_art(url, "Keys only", "keys-only")
    open_editor(pg, url, "keys-only")
    pg.focus(".vme-stage")
    for name in ["boat", "drone", "drone", "crate"]:
        pg.keyboard.press("Control+k")
        time.sleep(0.15)
        pg.keyboard.type("add " + name)
        pg.keyboard.press("Enter")
        time.sleep(0.25)
    pg.focus(".vme-stage")
    pg.keyboard.press("Tab")            # the frontmost placed thing
    for _ in range(30):
        pg.keyboard.press("Shift+ArrowLeft")
    for _ in range(12):
        pg.keyboard.press("Shift+ArrowDown")
    pg.keyboard.press("Tab")            # the next one
    for _ in range(25):
        pg.keyboard.press("Shift+ArrowRight")
    for _ in range(10):
        pg.keyboard.press("Shift+ArrowUp")
    pg.keyboard.press("Control+d")      # a copy of it, offset
    pg.keyboard.press("Control+a")
    pg.keyboard.press("Control+k")
    time.sleep(0.15)
    pg.keyboard.type("align top")
    pg.keyboard.press("Enter")
    time.sleep(0.4)
    res["keys_only"] = doc(pg)["phases"][0].get("place", [])
    res["keys_gl"] = pg.evaluate("""() => { const c = document.querySelector('.vme-gl'); const gl = c.getContext('webgl2') || c.getContext('webgl');
        return { lost: gl.isContextLost(), canvases: document.querySelectorAll('canvas').length, drawn: window.__vmEditor.ed.drawn, ok: window.__vmEditor.ed.packOk, sync: window.__vmEditor.ed.syncOk, errs: window.__vmEditor.ed.errors, st: window.__vmEditor.ed.status, pc: window.__vmEditor.ed.packCounts, dc: window.__vmEditor.ed.counts(window.__vmEditor.ed.doc) }; }""")
    shot(pg, "vmodes_editor_keys")
    pg.keyboard.press("Escape")

    # --- the undo history back to the empty document, after a reload of the page
    pg.reload()
    pg.wait_for_function("window.__padReady === true", timeout=90000)
    webui_shot.api(url, "ui.select_tab", "vmodes")
    open_editor(pg, url, "keys-only")
    n = 0
    while pg.evaluate("window.__vmEditor.canUndo()") and n < 600:
        pg.keyboard.press("Control+z")
        n += 1
        time.sleep(0.02)
    time.sleep(0.5)
    res["keys_only_undone"] = {"undo_steps": n, "place": doc(pg)["phases"][0].get("place", []),
                               "things": [t["id"] for t in doc(pg).get("things", [])]}
    with open(os.path.join(out, "after_editor_checks.json"), "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({k: (v if k == "desk_300_drag" else (len(v) if isinstance(v, list) else v)) for k, v in res.items()}))


_PROJECT = []
_PLAY = []


def main():
    repo = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2])
    prefix = _arg("--prefix", "after")
    after = prefix == "after"
    light = "--light" in sys.argv
    os.makedirs(out, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="pad1661-")
    project = os.path.join(scratch, "Night Harbour project")
    vm_demo_art.make_mode(os.path.join(project, "modes", "night-harbour"))
    desk = os.path.join(project, "modes", "stage-300")
    os.makedirs(desk, exist_ok=True)
    shutil.copy(os.path.join(repo, "tests", "data", "video_mode", "stage_300.json"), os.path.join(desk, "video_mode.json"))
    shutil.copytree(os.path.join(project, "modes", "night-harbour", "art"), os.path.join(desk, "art"))
    launcher = os.path.join(scratch, "launch1661.py")
    with open(launcher, "w", encoding="utf-8") as f:
        f.write(LAUNCHER % repo)
    settings = os.path.join(scratch, "settings.json")
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"disclaimer_accepted": True, "last_manufacturer": "stern", "theme": "light" if light else "dark",
                   "manufacturers": {"stern": {"extract_output": project, "write_assets": project,
                                               "write_output": scratch}}}, f)
    import site
    env = {"PYTHONPATH": site.getusersitepackages()}
    proc, url = webui_shot.start_server(settings, scratch, app_cmd=[sys.executable, launcher], extra_env=env)
    _SHOT[:] = [out, prefix]
    _PROJECT[:] = [project]
    try:
        webui_shot.api(url, "ui.pick_manufacturer", "stern")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(channel="msedge", args=["--mute-audio"])
            pg = b.new_page(viewport={"width": 1600, "height": 1000})
            pg.on("pageerror", lambda e: print("PAGE ERROR:", e))
            pg.on("console", lambda m: m.type in ("error", "warning") and "Failed to load resource" not in m.text and print("CONSOLE:", m.text[:200]))
            pg.on("response", lambda r: r.status >= 400 and print("HTTP", r.status, r.url[:160]))
            pg.goto(url)
            pg.wait_for_function("window.__padReady === true", timeout=90000)
            webui_shot.api(url, "ui.select_tab", "vmodes")
            _wait(url, "vmodes", lambda s: s.get("modes"), "the modes")
            try:
                pg.click("button:has-text('Hide log')", timeout=3000)
            except Exception:  # noqa: BLE001 - the log is already folded
                pass
            webui_shot.api(url, "vmodes.select", "night-harbour")
            _wait(url, "vmodes", lambda s: s.get("slug") == "night-harbour" and s.get("pictures"), "the pictures")
            time.sleep(2)
            if not after:
                for name in ("vmodes_editor", "vmodes_editor_multi", "vmodes_editor_empty"):
                    shot(pg, name)
                return
            if "--only-keys" in sys.argv:
                checks_after(pg, url, out)
                return
            sfx = "_light" if light else ""
            open_editor(pg, url, "night-harbour")
            pg.evaluate("window.__vmEditor.phase('boss')")
            time.sleep(0.8)
            pg.evaluate("window.__vmEditor.selectIndex(0)")
            time.sleep(0.4)
            shot(pg, "vmodes_editor" + sfx)
            if light:
                return
            # three things picked: the align bar
            pg.evaluate("window.__vmEditor.selectIndex([0, 1, 2])")
            time.sleep(0.4)
            shot(pg, "vmodes_editor_multi")
            # the sight dragged under the warship: it snaps to the warship's left edge, the gap shown
            pg.evaluate("window.__vmEditor.selectIndex(2)")
            time.sleep(0.3)
            c = pg.evaluate("window.__vmEditor.centreOf(2)")
            a = stage_point(pg, *c)
            target = stage_point(pg, 411, 551)
            pg.mouse.move(*a)
            pg.mouse.down()
            for j in range(1, 21):
                pg.mouse.move(a[0] + (target[0] - a[0]) * j / 20, a[1] + (target[1] - a[1]) * j / 20)
                time.sleep(0.02)
            time.sleep(0.3)
            shot(pg, "vmodes_editor_snap")
            pg.mouse.up()
            time.sleep(0.3)
            pg.keyboard.press("Control+z")
            time.sleep(0.5)
            # Play from the editor: the player opens on this phase; Back to editing comes back to the editor
            pg.click(".vme-top button:has-text('Play')")
            pg.wait_for_function("window.__vmPlayer && window.__vmPlayer.ready", timeout=30000)
            time.sleep(0.5)
            card = pg.evaluate("window.__vmPlayer.run.card")
            pg.click(".vmp-top button:has-text('Back to editing')")
            pg.wait_for_function("window.__vmEditor && window.__vmEditor.ready", timeout=30000)
            _PLAY.append({"card_index": card, "back_in_editor": True})
            time.sleep(0.5)
            pg.click(".vme-top button:has-text('Done')")
            time.sleep(0.5)
            checks_after(pg, url, out)
            b.close()
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
