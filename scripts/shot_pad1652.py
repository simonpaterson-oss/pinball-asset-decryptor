"""PAD-1652 (PR #55) proof shots: what a Send asks when it changes the kind of card the machine runs.

    python scripts/shot_pad1652.py <repo to run> <out dir>

Runs the app's server from <repo> against a scratch settings folder, with a stand-in machine (no network) that runs
Stern's stock Godzilla Pro 1.16 8 GB card on a 32 GB SD card (a one-game card: no partition 7), and photographs:
  network.png   Network tab: Send an image to the machine... with a multi-boot Godzilla image picked
  testcard.png  Test card tab: Send to machine... (the test card already built)
Each call is made through the page's own rpc module, so its question opens, or its refusal shows, as a click would.
"""
import json
import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import webui_shot  # noqa: E402

GZ = r"D:\Pinball\images\Stern\spike2\godzilla_pro-1_16_0_spike2.Release.8G.sdcard.raw"
MULTI = r"D:\Pinball\images\Stern\spike2\Godzilla Premium 1.16 Heisei Custom V1.6 Orchestral Edition.multi.raw"

HOST = r'''
import sys, types
sys.path.insert(0, %(repo)r)
from pinball_decryptor.core import remote_send as R
from pinball_decryptor.plugins.stern import spike3
from pinball_decryptor.webui import host, testcard_core as tc
from pinball_decryptor.webui import window as W
GZ, MULTI = %(gz)r, %(multi)r

class Stand:
    """A one-game card: the stock Godzilla Pro 8 GB card's partitions, no PAD menu list."""
    def __init__(self):
        with open(GZ, "rb") as f:
            self._lay = {p["index"]: (p["start_lba"], p["sectors"]) for p in spike3.parse_partitions(f)}
    def layout(self):
        return dict(self._lay)
    def sh(self, cmd, check=True, stdin=None, timeout=None):
        return 0, ""
    def close(self):
        pass

R.connect = lambda address, log=None: Stand()
try:
    from pinball_decryptor.core import card_relayout as CR
    def survey(machine, image):
        il = CR.image_layout(image)
        with open(GZ, "rb") as f:
            mbr = f.read(512)
        card = 32 * 10 ** 9 // 512 // 2048 * 2048
        p = CR.plan(machine.layout(), card, mbr, il[3][1], il[7][1], 3 << 30, CR.image_p7_label(image, il))
        return p, 0, 1
    CR.survey = survey
except ImportError:
    pass
_lst = tc.shared()
_lst.source, _lst.out = GZ, ""
_lst.network["ssh"] = True
tc.is_spike3_source = lambda src: False
tc.built_card = lambda lst: r"C:\cards\Godzilla test card.raw"
W.WebWindow.ask_open = lambda self, *a, **k: MULTI
sys.exit(host.main(sys.argv[1:]))
'''


def shoot(repo, out_dir):
    scratch = tempfile.mkdtemp(prefix="pad1652-")
    hostpy = os.path.join(scratch, "host.py")
    with open(hostpy, "w", encoding="utf-8") as f:
        f.write(HOST % {"repo": repo, "gz": GZ, "multi": MULTI})
    settings = os.path.join(scratch, "settings.json")
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"disclaimer_accepted": True, "last_manufacturer": "stern"}, f)
    import site
    proc, url = webui_shot.start_server(
        settings, scratch, app_cmd=[sys.executable, hostpy],
        extra_env={"PYTHONPATH": site.getusersitepackages(), "PAD_UI_NO_RIG": "1",
                   "PYTHONUSERBASE": os.path.join(os.environ.get("APPDATA", ""), "Python")})
    print("repo", repo, "url", url, flush=True)
    try:
        webui_shot.api(url, "ui.pick_manufacturer", "stern")
        webui_shot.api(url, "network.set_address", "192.168.4.130")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge")
            for tab, method, words in (("network", "network.send_image", ("Lay out", "Make ")),
                                       ("testcard", "testcard.send", ("Replace the game", "game would be deleted"))):
                webui_shot.api(url, "ui.select_tab", tab)
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.goto(url)
                page.wait_for_function("window.__padReady === true", timeout=60000)
                time.sleep(2)
                rpc = page.evaluate("performance.getEntriesByType('resource').map(e => e.name)"
                                    ".find(n => n.includes('core/rpc.js'))")
                page.evaluate("u => { import(u).then(m => m.call(%r)); }" % method, rpc)
                page.wait_for_function("ws => ws.some(w => document.body.innerText.includes(w))",
                                       arg=list(words), timeout=120000)
                time.sleep(1.5)
                page.screenshot(path=os.path.join(out_dir, "%s.png" % tab))
                print("shot", tab, flush=True)
                no = page.get_by_role("button", name="No", exact=True)
                if no.count():
                    no.first.click()
                    time.sleep(1)
                page.close()
            browser.close()
    finally:
        proc.terminate()


if __name__ == "__main__":
    repo, out = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
    os.makedirs(out, exist_ok=True)
    shoot(repo, out)
