"""PAD-1678 proof shot: the Plugins tab when the machine carries an older release than this computer.

    python scripts/shot_pad1678.py <repo> <out dir> [--card <raw>] [--prefix after]

Serves <repo> on a scratch project and a scratch settings folder, installs the newest Bluetooth headphones
release (a real download from its author's GitLab project), gives the Network tab a machine address and presses
Check it on the machine.  The machine is a stand-in inside the served app (``remote_send.connect`` answers as
David's Godzilla did on 2026-11-28: v0.3.0 on its card, its helper running, its menu refusing the game program),
so nothing is sent to a real machine.  Shoots ``<prefix>_plugins_machine_behind.png``.

Needs Playwright (the user site-packages one), the installed Edge, the card and gitlab.com.
"""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import webui_shot  # noqa: E402

LAUNCHER = r'''
import sys
sys.path.insert(0, %r)
from pinball_decryptor.core import remote_send


class Machine:
    """David's Godzilla as it was: v0.3.0 on the card, the helper running, the menu not in the game."""

    def sh(self, script, timeout=20, check=True):
        return 0, "on-card\nrelease v0.3.0\nhelper-running\nno-profile\n"

    def close(self):
        pass


remote_send.connect = lambda *a, **k: Machine()
from pinball_decryptor.webui import host
sys.argv = ["host"] + sys.argv[1:]
sys.exit(host.main())
'''
ADDRESS = "192.168.1.40"


def _arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def _plugin(url):
    rows = (webui_shot.state(url).get("plugins") or {}).get("plugins") or []
    return rows[0] if rows else {}


def _wait(url, done, what, seconds=180):
    t0 = time.time()
    while time.time() - t0 < seconds:
        row = _plugin(url)
        if done(row):
            return row
        time.sleep(1)
    raise SystemExit("timed out waiting for " + what + ": " + json.dumps(_plugin(url))[:600])


def main():
    repo = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2])
    prefix = _arg("--prefix", "after")
    card = _arg("--card", r"D:\Pinball\images\Stern\spike2\godzilla_pro-1_16_0_spike2.Release.8G.sdcard.raw")
    os.makedirs(out, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="pad1678-")
    project = os.path.join(scratch, "Godzilla Pro")
    os.makedirs(project)
    with open(os.path.join(project, ".extract_source.json"), "w", encoding="utf-8") as f:
        json.dump({"input_path": card, "input_name": os.path.basename(card), "card_version": "1.16.0"}, f)
    launcher = os.path.join(scratch, "launch1678.py")
    with open(launcher, "w", encoding="utf-8") as f:
        f.write(LAUNCHER % repo)
    settings = os.path.join(scratch, "settings.json")
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"disclaimer_accepted": True, "last_manufacturer": "stern",
                   "manufacturers": {"stern": {
                       "extract_input": card, "write_original": card,
                       "extract_output": project, "write_assets": project,
                       "write_output": scratch}}}, f)
    import site
    env = {"PYTHONPATH": site.getusersitepackages()}
    proc, url = webui_shot.start_server(settings, scratch, app_cmd=[sys.executable, launcher], extra_env=env)
    try:
        webui_shot.api(url, "ui.pick_manufacturer", "stern")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge")
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            page.wait_for_function("window.__padReady === true", timeout=60000)
            time.sleep(3)
            webui_shot.api(url, "network.set_address", ADDRESS)
            webui_shot.api(url, "ui.select_tab", "plugins")
            row = _wait(url, lambda r: r.get("releases_state") not in ("", "loading", None), "the versions list")
            webui_shot.api(url, "plugins.install", "bluetooth", row["tested"])
            row = _wait(url, lambda r: not r.get("busy") and (r.get("installed") or r.get("kind") == "err"),
                        "the install")
            print("installed:", row["installed"], row["kind"], row["note"], flush=True)
            time.sleep(3)                                   # the page's own look at the machine, where it has one
            row = _plugin(url)
            print("by itself:", row.get("machine_release"), row.get("machine_behind"), row.get("machine_note"),
                  flush=True)
            webui_shot.api(url, "plugins.check_machine", "bluetooth")
            row = _wait(url, lambda r: not r.get("busy") and r.get("note") and "machine" in r.get("note"),
                        "the check")
            print("check:", row["kind"], row["note"], flush=True)
            time.sleep(1)
            path = os.path.join(out, "%s_plugins_machine_behind.png" % prefix)
            page.screenshot(path=path)
            print("saved", path, "page errors:", errors, flush=True)
            browser.close()
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
