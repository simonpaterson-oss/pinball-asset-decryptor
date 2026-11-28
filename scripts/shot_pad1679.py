"""PAD-1679 proof shot: the Video modes tab's cost report on Spike 2, against the budgets PAD-1655 measured.

    python scripts/shot_pad1679.py <repo> <out dir> [--prefix after|before]

Serves <repo> on a scratch project holding the plan's worked example, Night Harbour (scripts/vm_demo_art.py), brings
in the same video and gif as scripts/shot_pad1658.py, packs for Spike 2 and shoots ``<prefix>_vmodes_cost.png``.
Before and after run the same steps, so the pair shows only what the cost report says differently.

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
from shot_pad1658 import LAUNCHER, _arg, _wait  # noqa: E402


def main():
    repo = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2])
    prefix = _arg("--prefix", "after")
    os.makedirs(out, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="pad1679-")
    project = os.path.join(scratch, "Night Harbour project")
    vm_demo_art.make_mode(os.path.join(project, "modes", "night-harbour"))
    src = vm_demo_art.make_sources(os.path.join(scratch, "sources"))
    launcher = os.path.join(scratch, "launch1679.py")
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
        webui_shot.api(url, "ui.select_tab", "vmodes")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(channel="msedge")
            pg = b.new_page(viewport={"width": 1500, "height": 1700})
            pg.goto(url)
            pg.wait_for_function("window.__padReady === true", timeout=90000)
            _wait(url, lambda s: s.get("pictures"), "the pictures")
            webui_shot.api(url, "vmodes.draft", src["video"], "video", {"length": "1.5", "fps": 12})
            _wait(url, lambda s: s.get("draft") and not s["draft"].get("busy"), "the video draft", 120)
            webui_shot.api(url, "vmodes.add", "runner", 12, True)
            webui_shot.api(url, "vmodes.draft", src["gif"], "gif", {})
            _wait(url, lambda s: s.get("draft") and not s["draft"].get("busy"), "the gif draft")
            webui_shot.api(url, "vmodes.add", "burst", None, None)
            webui_shot.api(url, "vmodes.set_machine", "spike2")
            webui_shot.api(url, "vmodes.pack", False)
            st = _wait(url, lambda s: s.get("report") and not s.get("packing"), "the cost report", 120)
            time.sleep(1)
            pg.evaluate("document.querySelector('.vm-pack') && document.querySelector('.vm-pack').scrollIntoView()")
            time.sleep(0.8)
            pg.screenshot(path=os.path.join(out, "%s_vmodes_cost.png" % prefix))
            if isinstance(st, dict) and st.get("report"):
                r = st["report"]
                print("memory", r.get("memory"), "card", r.get("card"), "card_pictures", r.get("card_pictures"))
            b.close()
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
