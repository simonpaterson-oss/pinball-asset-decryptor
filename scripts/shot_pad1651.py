"""PR #54 review (PAD-1651) proof shots: the Modes tab's co-op "Style picked" list (a fourth place, Alternative Modes)
and the Service menu tab's Online Co-op row.

    python scripts/shot_pad1651.py <repo> <out_dir> <before|after>

(Made from shot_pad1639_coop.py and shot_pad1639.py.) Serves <repo> (preview on) on a scratch project made from the
Godzilla LE 1.16 card with co-op play on (preset characters) and online co-op set up (the Kaiju War example), and
writes <kind>_coop_style.png (the co-op panel, "Style picked" shown open as a list box; after: Alternative Modes
picked) and <kind>_svcmenu.png (the Service menu tab, Co-op Play ticked; after: Online Co-op ticked too).

Needs Playwright (the user site-packages one), the installed Edge and the card in D:\\Pinball\\images\\Stern\\spike2.
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

CARD = r"D:\Pinball\images\Stern\spike2\godzilla_le-1_16_0_spike2.Release.8G.sdcard.raw"
LAUNCHER = r'''
import sys
sys.path.insert(0, %r)
from pinball_decryptor.core import preview
preview.enabled = lambda feature: True
from pinball_decryptor.webui import host
sys.argv = ["host"] + sys.argv[1:]
sys.exit(host.main())
'''
OPEN_LIST = """() => {
  const sel = document.querySelector('.modes-coop-style select[data-k="place"]')
      || [...document.querySelectorAll('.modes-coop-style select')].pop();
  if (!sel) return 0;
  sel.size = sel.options.length;
  sel.style.height = 'auto';
  sel.closest('.field').style.height = 'auto';
  return [...sel.options].map(o => o.text).join(' | ');
}"""


def main():
    repo = os.path.abspath(sys.argv[1])
    out_dir = os.path.abspath(sys.argv[2])
    kind = sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="pad1651-")
    project = os.path.join(scratch, "project")
    os.makedirs(project)
    with open(os.path.join(project, ".extract_source.json"), "w", encoding="utf-8") as f:
        json.dump({"input_path": CARD, "input_name": os.path.basename(CARD), "card_version": "1.16.0"}, f)
    sys.path.insert(0, repo)
    from pinball_decryptor.plugins.stern import online_coop as OC
    OC.save(project, url="http://203.0.113.10:8090/", campaign="Kaiju War", machine="Dave",
            design=OC.EXAMPLES["kaiju_war"])
    OC.save(project, team="Team King Ghidorah", on=True)
    launcher = os.path.join(scratch, "launch1651.py")
    with open(launcher, "w", encoding="utf-8") as f:
        f.write(LAUNCHER % repo)
    settings = os.path.join(scratch, "settings.json")
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"disclaimer_accepted": True, "last_manufacturer": "stern",
                   "manufacturers": {"stern": {
                       "extract_input": CARD, "write_original": CARD,
                       "extract_output": project, "write_assets": project,
                       "write_output": scratch}}}, f)
    import site
    proc, url = webui_shot.start_server(
        settings, scratch, app_cmd=[sys.executable, launcher],
        extra_env={"PYTHONPATH": site.getusersitepackages()})
    try:
        webui_shot.api(url, "ui.pick_manufacturer", "stern")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge")
            page = browser.new_page(viewport={"width": 1500, "height": 2000})
            page.goto(url)
            page.wait_for_function("window.__padReady === true", timeout=60000)
            time.sleep(2)
            webui_shot.api(url, "ui.select_tab", "modes")
            time.sleep(6)
            webui_shot.api(url, "modes.set_coop", True)
            time.sleep(3)
            page.get_by_role("button", name="Characters…").dispatch_event("click")
            page.wait_for_selector("text=Co-op characters", timeout=180000)
            webui_shot.api(url, "modes.coop_chars_preset")
            page.wait_for_selector(".modes-coop-ch-row", timeout=180000)
            webui_shot.api(url, "modes.coop_chars_pick", True)
            time.sleep(2)
            page.keyboard.press("Escape")
            time.sleep(2)
            webui_shot.api(url, "modes.set_coop_style", "characters")
            if kind == "after":
                print("place", webui_shot.api(url, "modes.set_coop_place", "alt"), flush=True)
            time.sleep(3)
            print("list", page.evaluate(OPEN_LIST), flush=True)
            page.mouse.move(1490, 5)
            time.sleep(1.5)
            panel = page.locator(".modes-coop").first
            panel.evaluate("e => e.scrollIntoView({block: 'center'})")
            time.sleep(1)
            box = panel.bounding_box()
            top = max(0, box["y"] - 60)
            clip = {"x": 0, "y": top, "width": min(1500, box["x"] + box["width"] + 300),
                    "height": min(2000 - top, box["height"] + 120)}
            page.screenshot(path=os.path.join(out_dir, "%s_coop_style.png" % kind), clip=clip)
            print("shot coop_style", flush=True)
            page.set_viewport_size({"width": 1500, "height": 1000})
            for key in ("coop_play", "online_coop"):
                try:
                    print(key, webui_shot.api(url, "svcmenu.set_row", key, True), flush=True)
                except Exception as e:                  # noqa: BLE001 - main has no such row
                    print("no %s row:" % key, e, flush=True)
            webui_shot.api(url, "ui.select_tab", "svcmenu")
            time.sleep(6)
            hide = page.get_by_text("Hide log")
            if hide.count():
                hide.first.click()
                time.sleep(1)
            row = page.get_by_text("Co-op Play", exact=True).first
            if row.count():
                page.evaluate("(el) => el.scrollIntoView({block: 'start'})", row.element_handle())
                page.mouse.wheel(0, -120)
            page.mouse.move(3, 990)                     # no hover tooltip over a row
            time.sleep(1.5)
            page.screenshot(path=os.path.join(out_dir, "%s_svcmenu.png" % kind))
            print("shot svcmenu", flush=True)
            browser.close()
    finally:
        proc.terminate()
        time.sleep(2)
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    main()
