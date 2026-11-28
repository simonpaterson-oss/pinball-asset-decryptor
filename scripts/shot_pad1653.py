"""PAD-1653 proof shots: the Plugins tab at an ordinary window height, scrolled to the end of the
how-it-works guide, and whether the plugin card's border still holds all of it.

    python scripts/shot_pad1653.py <repo> <out dir> --store <plugin store> [--prefix after]

Serves <repo> on a scratch settings folder with a COPY of <plugin store> (a folder holding ``bluetooth/``).
Shoots ``<prefix>_plugins_bottom.png`` and prints the card's bottom against its last child's bottom: a card
that shrank to the window shows ``spill`` > 0.  Needs Playwright (the user site-packages one) and Edge.
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

MEASURE = """() => {
  const card = document.querySelector('.plg-card');
  if (!card) return null;
  const last = [...card.querySelectorAll('.plg-guide > *')].pop() || card;
  const c = card.getBoundingClientRect(), l = last.getBoundingClientRect();
  return {card_bottom: Math.round(c.bottom), content_bottom: Math.round(l.bottom),
          spill: Math.round(l.bottom - c.bottom)};
}"""


def _arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    repo = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2])
    prefix = _arg("--prefix", "after")
    store = os.path.abspath(_arg("--store", ""))
    card = _arg("--card", r"D:\Pinball\images\Stern\spike2\godzilla_pro-1_16_0_spike2.Release.8G.sdcard.raw")
    os.makedirs(out, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="pad1653-")
    project = os.path.join(scratch, "Godzilla Pro")
    os.makedirs(project)
    with open(os.path.join(project, ".extract_source.json"), "w", encoding="utf-8") as f:
        json.dump({"input_path": card, "input_name": os.path.basename(card), "card_version": "1.16.0"}, f)
    plugins = os.path.join(scratch, "plugins")
    shutil.copytree(store, plugins)
    settings = os.path.join(scratch, "settings.json")
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"disclaimer_accepted": True, "last_manufacturer": "stern",
                   "manufacturers": {"stern": {
                       "extract_input": card, "write_original": card,
                       "extract_output": project, "write_assets": project,
                       "write_output": scratch}}}, f)
    import site
    env = {"PYTHONPATH": site.getusersitepackages(), "PAD_PLUGIN_DIR": plugins}
    launcher = os.path.join(scratch, "launch1653.py")
    with open(launcher, "w", encoding="utf-8") as f:
        f.write("import sys\nsys.path.insert(0, %r)\nfrom pinball_decryptor.webui import host\n"
                "sys.argv = ['host'] + sys.argv[1:]\nsys.exit(host.main())\n" % repo)
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
            webui_shot.api(url, "ui.select_tab", "plugins")
            page.wait_for_selector(".plg-guide", timeout=30000)
            time.sleep(2)
            page.evaluate("() => { const pg = document.querySelector('.plg-page'); pg.scrollTop = pg.scrollHeight; }")
            time.sleep(1)
            print("measure:", page.evaluate(MEASURE), flush=True)
            path = os.path.join(out, "%s_plugins_bottom.png" % prefix)
            page.screenshot(path=path)
            print("saved", path, "page errors:", errors, flush=True)
            browser.close()
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
