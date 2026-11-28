"""PAD-1659 proof shots: a video mode playing in the app, and the video mode kind on the Modes tab.

    python scripts/shot_pad1659.py <repo> <out dir> [--prefix after|before] [--light]

Serves <repo> on a scratch project holding the plan's worked example, Night Harbour, with original placeholder art
(scripts/vm_demo_art.py). Shoots:

  <prefix>_modes_list.png   the Modes tab's list (after: Night Harbour's tile, a Video mode)
  <prefix>_modes_new.png    the New mode wizard's first step (after: a fourth way, Video mode)
  <prefix>_vmodes.png       the Video modes tab's head (after: its Play button)
  <prefix>_vmodes_play.png  after: Night Harbour playing in the app's player, hit boxes on, 4 s into the chase
                            (before: the same tab, which had no player)
  after_vmodes_replay.png   after: that play replayed from its recording, matched; after_replay.json holds the
                            app's hash, the replay's and the native build's (vmrun) on the same buttons

``after`` also writes after_checks.json: the WebGL renderer, a clip playing from the intro, sounds played through
Web Audio (Edge runs with --mute-audio: counted, never heard), the machine's 29 fps rate, and
tests/data/video_mode/desk_300.json (300 things) played 10 s with its frame times (after_vmodes_play_desk300.png). Needs Playwright (the user site-packages one) and the installed Edge.
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


def replay_proof(pg, out, prefix):
    """The play just made, replayed: in the player (it must end on its own hash) and on the native build (vmrun,
    the same C compiled for this PC) from the same card with the same buttons. Writes <prefix>_replay.json."""
    import base64
    import subprocess
    rec = pg.evaluate("window.__vmPlayer.recording()")
    pg.evaluate("r => window.__vmPlayer.replay(r)", rec)
    pg.wait_for_function("window.__vmPlayer.verdict()", timeout=120000)
    verdict = pg.evaluate("window.__vmPlayer.verdict()")
    time.sleep(0.6)
    shot(pg, "vmodes_replay")
    sys.path.insert(0, os.path.dirname(HERE))
    from pinball_decryptor.core.video_mode.engine import build
    from pinball_decryptor.core.video_mode import compiler as C
    scratch = tempfile.mkdtemp(prefix="pad1659-native-")
    exe = build.build_native(scratch)
    md = os.path.join(_PROJECT[0], "modes", "night-harbour")
    pack = os.path.join(scratch, "nh.pack")
    with open(pack, "wb") as f:
        f.write(C.compile_file(os.path.join(md, "video_mode.json")).pack)
    inputs = os.path.join(scratch, "rec.inputs")
    with open(inputs, "wb") as f:
        f.write(base64.b64decode(rec["data"]))
    cmd = [exe, pack, "--inputs", inputs, "--seed", str(rec["seed"]), "--max", str(rec["steps"]), "--quiet"]
    if rec["card"] >= 0:
        cmd += ["--card", str(rec["card"])]
    line = subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines()[-1]
    native = dict(kv.split("=", 1) for kv in line.split()[1:])
    res = {"steps": rec["steps"], "card": rec["card_id"], "app_hash": rec["hash"], "app_replay": verdict,
           "native": native, "same": verdict["same"] and native["hash"] == rec["hash"] and int(native["steps"]) == rec["steps"],
           "action_steps": sum(1 for b in base64.b64decode(rec["data"]) if b & 4)}
    with open(os.path.join(out, "%s_replay.json" % prefix), "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res))


_PROJECT = []
_SHOT = []


def shot(pg, name):
    pg.screenshot(path=os.path.join(_SHOT[0], "%s_%s.png" % (_SHOT[1], name)))


def main():
    repo = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2])
    prefix = _arg("--prefix", "after")
    after = prefix == "after"
    os.makedirs(out, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="pad1659-")
    project = os.path.join(scratch, "Night Harbour project")
    vm_demo_art.make_mode(os.path.join(project, "modes", "night-harbour"))
    if after:
        vm_demo_art.make_media(os.path.join(project, "modes", "night-harbour"))
    if after:
        desk = os.path.join(project, "modes", "desk-300")
        os.makedirs(desk, exist_ok=True)
        shutil.copy(os.path.join(repo, "tests", "data", "video_mode", "desk_300.json"),
                    os.path.join(desk, "video_mode.json"))
    launcher = os.path.join(scratch, "launch1659.py")
    with open(launcher, "w", encoding="utf-8") as f:
        f.write(LAUNCHER % repo)
    settings = os.path.join(scratch, "settings.json")
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"disclaimer_accepted": True, "last_manufacturer": "stern",
                   "theme": "light" if "--light" in sys.argv else "dark",
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
            # muted at the process: Web Audio still runs (and is counted), nothing reaches the speakers
            b = p.chromium.launch(channel="msedge", args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"])
            pg = b.new_page(viewport={"width": 1600, "height": 1000})
            pg.goto(url)
            pg.wait_for_function("window.__padReady === true", timeout=90000)
            # the Modes tab: its list, then the New mode wizard
            webui_shot.api(url, "ui.select_tab", "modes")
            time.sleep(3)
            shot(pg, "modes_list")
            pg.click(".modes-list .hd button:has-text('New mode')")
            time.sleep(1.5)
            shot(pg, "modes_new")
            pg.keyboard.press("Escape")
            time.sleep(0.8)
            # the Video modes tab
            webui_shot.api(url, "ui.select_tab", "vmodes")
            _wait(url, "vmodes", lambda s: s.get("modes"), "the modes")
            webui_shot.api(url, "vmodes.select", "night-harbour")
            _wait(url, "vmodes", lambda s: s.get("slug") == "night-harbour" and s.get("pictures"), "the pictures")
            time.sleep(2)
            shot(pg, "vmodes")
            if not after:
                shot(pg, "vmodes_play")
                return
            pg.click(".vm-page .pagehead button:has-text('Play')")
            pg.wait_for_selector(".vmp-stage canvas", timeout=30000)
            pg.wait_for_function("window.__vmPlayer && window.__vmPlayer.ready", timeout=30000)
            # start at the chase, hit boxes on, and play 4 s holding Action, steering once
            pg.evaluate("window.__vmPlayer.startAt('c_chase')")
            pg.keyboard.press("h")
            pg.keyboard.down("Space")
            time.sleep(2.0)
            pg.keyboard.down("ShiftLeft"); time.sleep(0.12); pg.keyboard.up("ShiftLeft")
            time.sleep(2.0)
            shot(pg, "vmodes_play")
            pg.keyboard.up("Space")
            time.sleep(0.5)
            replay_proof(pg, out, prefix)
            checks = {"renderer": pg.evaluate("""() => { const c = document.querySelector('.vmp-gl');
                const gl = c.getContext('webgl2') || c.getContext('webgl'); const x = gl.getExtension('WEBGL_debug_renderer_info');
                return { webgl2: !!c.getContext('webgl2'), renderer: x ? gl.getParameter(x.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER) }; }""")}
            # sound on, then from the intro: its clip plays, the phase's music and the fire effect sound
            pg.click(".vmp-top button:has-text('Sound off')")
            pg.evaluate("window.__vmPlayer.startAt('c_intro')")
            time.sleep(1.0)
            checks["intro_clip"] = pg.evaluate("window.__vmPlayer.clip()")
            shot(pg, "vmodes_play_clip")
            time.sleep(1.5)
            pg.keyboard.down("Space")
            time.sleep(3.0)
            pg.keyboard.up("Space")
            checks["sound"] = pg.evaluate("window.__vmPlayer.sound()")
            checks["after_intro"] = pg.evaluate("window.__vmPlayer.run.log.slice(-4).map(l => l.say)")
            # the machine's frame rate: the screen drawn about 29 times a second, the engine still 60 steps
            pg.click(".vmp-bar button:has-text('Machine')")
            pg.evaluate("window.__vmPlayer.perfReset()")
            time.sleep(4)
            checks["machine_rate"] = pg.evaluate("window.__vmPlayer.perf()")
            pg.click(".vmp-bar button:has-text('60 fps')")
            # 300 things: the desk
            pg.click(".vmp-top button:has-text('Back to editing')")
            webui_shot.api(url, "vmodes.select", "desk-300")
            time.sleep(2)
            pg.click(".vm-page .pagehead button:has-text('Play')")
            pg.wait_for_function("window.__vmPlayer && window.__vmPlayer.ready", timeout=30000)
            pg.keyboard.press("h")
            time.sleep(2)
            pg.evaluate("window.__vmPlayer.perfReset()")
            time.sleep(10)
            checks["desk_300"] = pg.evaluate("window.__vmPlayer.perf()")
            shot(pg, "vmodes_play_desk300")
            with open(os.path.join(out, "after_checks.json"), "w") as f:
                json.dump(checks, f, indent=1)
            print(json.dumps(checks))
            b.close()
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
