"""PAD-1667 proof shots and the app's half of the sound proof.

    python scripts/shot_pad1667.py <repo> <out dir> [--prefix after|before]

Serves <repo> on a scratch project holding the plan's worked example, Night Harbour, with its original placeholder
art and sounds (scripts/vm_demo_art.py; the served repo's own example document). Shoots:

  <prefix>_vmodes_head.png   the Video modes tab's head (after: Undo and Redo)
  <prefix>_vmodes_sound.png  below the backgrounds (after: the Sound card, Find the beat run on the chase music;
                             before: the Pack card that followed the backgrounds)

``after`` also replays the bot's winning run of Night Harbour (tests/data/video_mode/golden) in the player with the
sound on (Edge runs with --mute-audio: played, never heard) and writes after_cues.json: every sound cue the player
played, by step, with what it did (played, skipped, music starts / changes / stops), beside the native build's
(vmrun) cue lines on the same buttons - the list the emulator's run is held to. Needs Playwright (the user
site-packages one) and the installed Edge.
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import webui_shot  # noqa: E402
import vm_demo_art  # noqa: E402
from shot_pad1659 import LAUNCHER, _arg, _wait  # noqa: E402


def main():
    repo = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2])
    prefix = _arg("--prefix", "after")
    after = prefix == "after"
    os.makedirs(out, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="pad1667-")
    project = os.path.join(scratch, "Night Harbour project")
    md = os.path.join(project, "modes", "night-harbour")
    vm_demo_art.make_mode(md)
    vm_demo_art.make_media(md)
    shutil.copy2(os.path.join(repo, "pinball_decryptor", "core", "video_mode", "examples", "night_harbour.json"),
                 os.path.join(md, "video_mode.json"))
    launcher = os.path.join(scratch, "launch1667.py")
    with open(launcher, "w", encoding="utf-8") as f:
        f.write(LAUNCHER % repo)
    settings = os.path.join(scratch, "settings.json")
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"disclaimer_accepted": True, "last_manufacturer": "stern", "theme": "dark",
                   "manufacturers": {"stern": {"extract_output": project, "write_assets": project,
                                               "write_output": scratch}}}, f)
    import site
    proc, url = webui_shot.start_server(settings, scratch, app_cmd=[sys.executable, launcher],
                                        extra_env={"PYTHONPATH": site.getusersitepackages()})
    try:
        webui_shot.api(url, "ui.pick_manufacturer", "stern")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(channel="msedge", args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"])
            pg = b.new_page(viewport={"width": 1600, "height": 1000})
            pg.goto(url)
            pg.wait_for_function("window.__padReady === true", timeout=90000)
            webui_shot.api(url, "ui.select_tab", "vmodes")
            _wait(url, "vmodes", lambda s: s.get("modes"), "the modes")
            webui_shot.api(url, "vmodes.select", "night-harbour")
            _wait(url, "vmodes", lambda s: s.get("slug") == "night-harbour" and s.get("pictures"), "the pictures")
            time.sleep(2)
            pg.screenshot(path=os.path.join(out, "%s_vmodes_head.png" % prefix), clip={"x": 0, "y": 0, "width": 1600, "height": 260})
            if after:
                _wait(url, "vmodes", lambda s: s.get("sounds") and all((s.get("peaks") or {}).get(r["peaks_key"])
                                                                         for r in s["sounds"]), "the waveforms")
                webui_shot.api(url, "vmodes.find_beat", "chase_music")
                time.sleep(0.5)
                _wait(url, "vmodes", lambda s: not s.get("beat_busy"), "the beat")
                time.sleep(1.5)
            # a tall window, the page scrolled to the backgrounds card: what follows it, whole
            pg.set_viewport_size({"width": 1600, "height": 2400})
            time.sleep(0.8)
            pg.evaluate("""() => { const c = [...document.querySelectorAll('.card')].find((x) => /Backgrounds/.test(x.textContent || ''));
                if (c) c.scrollIntoView({ block: 'start' }); }""")
            time.sleep(1.0)
            main = pg.locator(".vm-page")
            box = main.bounding_box()
            pg.screenshot(path=os.path.join(out, "%s_vmodes_sound.png" % prefix),
                          clip={"x": box["x"], "y": 0, "width": box["width"], "height": 2400})
            pg.set_viewport_size({"width": 1600, "height": 1000})
            time.sleep(0.5)
            if after:
                cue_proof(pg, out, md)
            b.close()
    finally:
        proc.terminate()


def cue_proof(pg, out, md):
    """The bot's winning run, replayed in the player with sound on: its cue log against vmrun's on the same buttons."""
    sys.path.insert(0, os.path.dirname(HERE))
    from pinball_decryptor.core.video_mode.engine import build
    from pinball_decryptor.core.video_mode import compiler as C
    golden = os.path.join(os.path.dirname(HERE), "tests", "data", "video_mode", "golden")
    with open(os.path.join(golden, "golden.json"), encoding="utf-8") as f:
        spec = json.load(f)["runs"]["night_harbour_bot"]
    with open(os.path.join(golden, spec["inputs"]), "rb") as f:
        data = f.read()
    pg.click(".vm-page .pagehead button:has-text('Play')")
    pg.wait_for_function("window.__vmPlayer && window.__vmPlayer.ready", timeout=30000)
    pg.click(".vmp-top button:has-text('Sound off')")
    time.sleep(1.0)
    pg.evaluate("r => window.__vmPlayer.replay(r)", {"data": base64.b64encode(data).decode("ascii"), "seed": spec["seed"],
                                                      "card": -1, "steps": len(data), "hash": spec["hash"]})
    pg.wait_for_function("window.__vmPlayer.verdict()", timeout=240000, polling=500)
    snd = pg.evaluate("window.__vmPlayer.sound()")
    verdict = pg.evaluate("window.__vmPlayer.verdict()")
    scratch = tempfile.mkdtemp(prefix="pad1667-native-")
    exe = build.build_native(scratch)
    pack = os.path.join(scratch, "nh.pack")
    comp = C.compile_file(os.path.join(md, "video_mode.json"))
    with open(pack, "wb") as f:
        f.write(comp.pack)
    inputs = os.path.join(scratch, "bot.inputs")
    with open(inputs, "wb") as f:
        f.write(data)
    lines = subprocess.run([exe, pack, "--inputs", inputs, "--seed", str(spec["seed"]), "--max", str(len(data))],
                           capture_output=True, text=True).stdout.splitlines()
    native = [[int(v) for v in ln.split()[1:]] for ln in lines if ln.startswith("C ")]
    app = [[c["step"], c["sound"], c["op"], c["duck"], c["fade"]] for c in snd["log"]]
    res = {"names": comp.names["sounds"], "steps": len(data), "app_verdict": verdict,
           "same_cues": app == native, "app": snd["log"], "native": native,
           "played": snd["played"], "skipped": snd["skipped"], "music_started": snd["music"], "state": snd["state"]}
    with open(os.path.join(out, "after_cues.json"), "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({k: res[k] for k in ("same_cues", "played", "skipped", "music_started", "state", "steps")}),
          "cues:", len(app), "native:", len(native))


if __name__ == "__main__":
    main()
