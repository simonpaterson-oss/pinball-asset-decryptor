"""PAD-1658 proof shots: the Video modes tab, its import dialog and its cost report.

    python scripts/shot_pad1658.py <repo> <out dir> [--prefix after|before]

Serves <repo> on a scratch project holding the plan's worked example, Night Harbour, with original placeholder art
(scripts/vm_demo_art.py), and a scratch settings folder. ``after`` shoots ``after_vmodes.png`` (the tab, the boat
picked), ``after_vmodes_import.png`` (a green-screen video being brought in) and ``after_vmodes_cost.png`` (the
cost on Spike 2) and ``after_vmodes_cost_over.png`` (a whole-screen video added: Pack for the card refuses and
names it). ``before`` shoots the same names from a repo without
the tab: the Make group of the rail, on the Modes tab.

Needs Playwright (the user site-packages one) and the installed Edge.
"""
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


def _wait(url, ok, what, seconds=60):
    t0 = time.time()
    while time.time() - t0 < seconds:
        s = webui_shot.state(url).get("vmodes") or {}
        if ok(s):
            return s
        time.sleep(0.5)
    raise SystemExit("timed out waiting for " + what)


def main():
    repo = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2])
    prefix = _arg("--prefix", "after")
    os.makedirs(out, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="pad1658-")
    project = os.path.join(scratch, "Night Harbour project")
    vm_demo_art.make_mode(os.path.join(project, "modes", "night-harbour"))
    src = vm_demo_art.make_sources(os.path.join(scratch, "sources"))
    launcher = os.path.join(scratch, "launch1658.py")
    with open(launcher, "w", encoding="utf-8") as f:
        f.write(LAUNCHER % repo)
    settings = os.path.join(scratch, "settings.json")
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"disclaimer_accepted": True, "last_manufacturer": "stern",
                   "manufacturers": {"stern": {"extract_output": project, "write_assets": project,
                                               "write_output": scratch}}}, f)
    import site
    env = {"PYTHONPATH": site.getusersitepackages()}
    proc, url = webui_shot.start_server(settings, scratch, app_cmd=[sys.executable, launcher], extra_env=env)
    try:
        webui_shot.api(url, "ui.pick_manufacturer", "stern")
        after = prefix == "after"
        webui_shot.api(url, "ui.select_tab", "vmodes" if after else "modes")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(channel="msedge")
            pg = b.new_page(viewport={"width": 1500, "height": 1700})
            pg.goto(url)
            pg.wait_for_function("window.__padReady === true", timeout=90000)
            time.sleep(3)
            if not after:
                for name in ("vmodes", "vmodes_touchup", "vmodes_import", "vmodes_cost", "vmodes_cost_over"):
                    pg.screenshot(path=os.path.join(out, "%s_%s.png" % (prefix, name)))
                return
            _wait(url, lambda s: s.get("pictures"), "the pictures")
            pg.click("text=boat")
            time.sleep(1.5)
            pg.screenshot(path=os.path.join(out, "after_vmodes.png"))
            pg.click("text=Touch up frame")
            time.sleep(2)
            pg.screenshot(path=os.path.join(out, "after_vmodes_touchup.png"))
            pg.keyboard.press("Escape")
            time.sleep(0.8)
            webui_shot.api(url, "vmodes.draft", src["video"], "video", {"length": "1.5", "fps": 12})
            _wait(url, lambda s: s.get("draft") and not s["draft"].get("busy"), "the video draft", 120)
            time.sleep(1.5)
            pg.screenshot(path=os.path.join(out, "after_vmodes_import.png"))
            webui_shot.api(url, "vmodes.add", "runner", 12, True)
            webui_shot.api(url, "vmodes.draft", src["gif"], "gif", {})
            _wait(url, lambda s: s.get("draft") and not s["draft"].get("busy"), "the gif draft")
            webui_shot.api(url, "vmodes.add", "burst", None, None)
            webui_shot.api(url, "vmodes.set_machine", "spike2")
            webui_shot.api(url, "vmodes.pack", False)
            _wait(url, lambda s: s.get("report") and not s.get("packing"), "the cost report", 120)
            time.sleep(1)
            pg.evaluate("document.querySelector('.vm-pack') && document.querySelector('.vm-pack').scrollIntoView()")
            time.sleep(0.8)
            pg.screenshot(path=os.path.join(out, "after_vmodes_cost.png"))
            # a whole-screen video brought in uncut: far more than Spike 2 holds, and Pack for the card says which
            webui_shot.api(url, "vmodes.draft", src["video"], "video", {"length": "1.5", "fps": 24, "cut": "none",
                                                                       "width": 1360})
            _wait(url, lambda s: s.get("draft") and not s["draft"].get("busy"), "the full-screen draft", 120)
            webui_shot.api(url, "vmodes.add", "fullscreen", 24, True)
            webui_shot.api(url, "vmodes.pack", True)
            _wait(url, lambda s: s.get("report") and not s.get("packing"), "the over-budget report", 300)
            time.sleep(1)
            pg.evaluate("document.querySelector('.vm-pack') && document.querySelector('.vm-pack').scrollIntoView()")
            time.sleep(0.8)
            pg.screenshot(path=os.path.join(out, "after_vmodes_cost_over.png"))
            b.close()
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
