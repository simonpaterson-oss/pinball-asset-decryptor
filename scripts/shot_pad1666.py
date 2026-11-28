"""PAD-1666 proof shots: the video mode HUD and feel (HUD parts on the stage, text styles, particles, the style
presets).

    python scripts/shot_pad1666.py <repo> <out dir> [--prefix after|before] [--preset arcade]

Serves <repo> on a scratch project holding the plan's worked example, Night Harbour, with original placeholder art
(scripts/vm_demo_art.py). Shoots:

  <prefix>_vmodes_hud_editor.png   the chase phase in the editor (after: the score part picked, its handles and the
                                   HUD inspector with its text style)
  <prefix>_vmodes_hud_style.png    the mode's look (after: the Style inspector with the presets, every effect's
                                   switch and its cost against the machine's budget; before: the phase inspector,
                                   which was all there was)
  <prefix>_vmodes_hud_play.png     the chase playing 4 s in, Action held: shots, kills, the HUD mid-fight

``--preset NAME`` applies a style preset first (after only), and ``after`` writes after_hud_checks.json: the draw
list hash of a fixed play in the page (WebAssembly) and the frame times of 6 s of the particle-heavy play.
Needs Playwright (the user site-packages one) and the installed Edge.
"""
import base64
import json
import os
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


def main():
    repo = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2])
    prefix = _arg("--prefix", "after")
    after = prefix == "after"
    preset = _arg("--preset", "")
    os.makedirs(out, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="pad1666-")
    project = os.path.join(scratch, "Night Harbour project")
    mode_dir = os.path.join(project, "modes", "night-harbour")
    vm_demo_art.make_mode(mode_dir)
    launcher = os.path.join(scratch, "launch1666.py")
    with open(launcher, "w", encoding="utf-8") as f:
        f.write(LAUNCHER % repo)
    settings = os.path.join(scratch, "settings.json")
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"disclaimer_accepted": True, "last_manufacturer": "stern", "theme": "dark",
                   "manufacturers": {"stern": {"extract_output": project, "write_assets": project,
                                               "write_output": scratch}}}, f)
    import site
    env = {"PYTHONPATH": site.getusersitepackages()}
    proc, url = webui_shot.start_server(settings, scratch, app_cmd=[sys.executable, launcher], extra_env=env)
    checks = {}

    def shot(pg, name):
        pg.screenshot(path=os.path.join(out, "%s_%s.png" % (prefix, name)))

    try:
        webui_shot.api(url, "ui.pick_manufacturer", "stern")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(channel="msedge", args=["--mute-audio"])
            pg = b.new_page(viewport={"width": 1600, "height": 1000})
            pg.on("pageerror", lambda e: print("PAGE ERROR:", e))
            pg.on("console", lambda m: m.type in ("error", "warning") and "Failed to load resource" not in m.text
                  and print("CONSOLE:", m.text[:200]))
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
            time.sleep(1.5)
            # ---- the editor
            pg.click(".vm-page .pagehead button:has-text('Edit')")
            pg.wait_for_function("window.__vmEditor && window.__vmEditor.ready", timeout=30000)
            time.sleep(0.8)
            if after and preset:
                pg.evaluate("p => window.__vmEditor.preset(p)", preset)
                pg.evaluate("window.__vmEditor.settled()")
                time.sleep(1.0)
            pg.evaluate("window.__vmEditor.phase('chase')")
            time.sleep(0.8)
            if after:
                pg.evaluate("window.__vmEditor.selectHud('score')")
                time.sleep(0.5)
            shot(pg, "vmodes_hud_editor")
            if after:
                pg.evaluate("window.__vmEditor.showStyle()")
                time.sleep(0.5)
            else:
                pg.evaluate("window.__vmEditor.selectIndex([])")
                time.sleep(0.4)
            shot(pg, "vmodes_hud_style")
            # ---- the player
            pg.keyboard.press("F5")
            pg.wait_for_function("window.__vmPlayer && window.__vmPlayer.ready", timeout=30000)
            # the bot's recorded winning run (this tree's own golden), paused 14 steps after its second kill (the hit-stop's held frames, then the burst flying): the
            # same buttons on both sides, so the pair shows the same moment of play
            with open(os.path.join(repo, "tests", "data", "video_mode", "golden", "night_harbour_bot.inputs"), "rb") as f:
                rec = {"seed": 1, "level": 0, "card": None, "data": base64.b64encode(f.read()).decode("ascii")}
            pg.evaluate("rec => window.__vmPlayer.replay(rec)", rec)
            pg.wait_for_function("window.__vmPlayer.run.kills >= 2", timeout=120000)
            checks["paused_at_step"] = pg.evaluate("""n => new Promise((res) => { const r = window.__vmPlayer.run, s0 = r.e.stepNo();
                const t = () => { if (r.e.stepNo() >= s0 + n) { r.setPaused(true); res(r.e.stepNo()); } else requestAnimationFrame(t); };
                t(); })""", 14)
            time.sleep(0.6)
            shot(pg, "vmodes_hud_play")
            if after:
                pg.evaluate("window.__vmPlayer.run.setPaused(false)")
                pg.evaluate("window.__vmPlayer.perfReset()")
                time.sleep(6.0)
                checks["bot_6s"] = pg.evaluate("window.__vmPlayer.perf()")
            if after:
                with open(os.path.join(out, "after_hud_checks.json"), "w", encoding="utf-8") as f:
                    json.dump(checks, f, indent=2)
            b.close()
    finally:
        webui_shot.stop_server(proc) if hasattr(webui_shot, "stop_server") else proc.kill()


if __name__ == "__main__":
    main()
