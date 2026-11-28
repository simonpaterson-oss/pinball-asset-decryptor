"""The video mode player in the app (PAD-1659).

The app plays a video mode with the machine's own engine built to WebAssembly (vm_engine.wasm through vm_engine.js),
drawn by a WebGL backend (webui/static/js/tabs/vmodes_play.js). These hold:

- "Start here": the engine started at any card of the flow plays the same, step for step, on WebAssembly and on the
  native build (vmrun --card), so a recording made from a phase replays to the same draw list hash anywhere;
- the calls the player makes on vm_engine.js (startAt, hitBoxes, things, the readouts) and a recorded play's hash
  against the native build's on the same buttons;
- the Video modes tab's side: play_open (the compiled pack, the pictures, fonts, sounds and clips by the engine's
  index, the flow's cards, the machine's budgets), play_save / play_recording;
- the Modes tab: video modes in its list (opening one goes to the Video modes tab) and the wizard's Video mode way;
- the changed browser modules parse.

The in-browser proof (the worked example playing at 60 fps, a replay matching the native hash, 300 things) is
scripts/shot_pad1659.py, run for the ticket's gate.
"""
import base64
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pinball_decryptor.core.video_mode import compiler, harness  # noqa: E402

ENGINE = os.path.join(ROOT, "pinball_decryptor", "core", "video_mode", "engine")
EXAMPLE = os.path.join(ROOT, "pinball_decryptor", "core", "video_mode", "examples", "night_harbour.json")
DESK = os.path.join(ROOT, "tests", "data", "video_mode", "desk_300.json")
JS = os.path.join(ROOT, "pinball_decryptor", "webui", "static", "js", "tabs")

pytestmark = pytest.mark.xdist_group("video_mode_engine")


def _inputs(seed, n):
    rng = random.Random(seed)
    out, held = bytearray(), 0
    for _ in range(n):
        if rng.random() < 0.15:
            held = rng.randrange(8)
        out.append(held | (8 if rng.random() < 0.01 else 0))
    return bytes(out)


_native = []


def native():
    if not _native:
        try:
            _native.append(harness.native_runner(os.path.join(tempfile.gettempdir(), "pad_vmrun_tests")))
        except RuntimeError as e:
            pytest.fail(str(e))
    if not _native[0]:
        pytest.skip("no C compiler for the native engine")
    return _native[0]


def node():
    n = shutil.which("node")
    if not n:
        pytest.skip("no Node for the WebAssembly engine")
    return n


def run(runner, pack, inputs, *args):
    with tempfile.TemporaryDirectory() as td:
        p, q = os.path.join(td, "m.pack"), os.path.join(td, "m.inputs")
        with open(p, "wb") as f:
            f.write(pack)
        with open(q, "wb") as f:
            f.write(inputs)
        r = subprocess.run(runner + [p, "--inputs", q] + [str(a) for a in args], capture_output=True, text=True,
                           timeout=600)
    return r


def end_of(out):
    line = [x for x in out.splitlines() if x.startswith("END ")][-1]
    return dict(kv.split("=") for kv in line.split()[1:])


def pack_of(path):
    res = compiler.compile_file(path)
    assert res.ok, res.problems
    return res.pack


def cards_of(path):
    with open(path, encoding="utf-8") as f:
        return [c["id"] for c in json.load(f)["flow"]["cards"]]


# ---- Start here: the engine at any card, the same on WebAssembly and native ----------------------------------------
@pytest.mark.parametrize("card", range(8))
def test_start_at_card_native_and_wasm_agree(card):
    ids = cards_of(EXAMPLE)
    assert len(ids) == 8
    pack = pack_of(EXAMPLE)
    inputs = _inputs(card + 7, 1800)
    wasm = [node(), os.path.join(ENGINE, "vm_run.mjs"), os.path.join(ENGINE, "vm_engine.wasm")]
    a = run(native(), pack, inputs, "--card", card, "--max", 1800, "--dump", 30, "--seed", 3)
    b = run(wasm, pack, inputs, "--card", card, "--max", 1800, "--dump", 30, "--seed", 3)
    assert a.returncode == 0 and b.returncode == 0, a.stdout[-300:] + b.stdout[-300:] + b.stderr[-300:]
    la = [x.rstrip("\r") for x in a.stdout.splitlines()]
    lb = [x.rstrip("\r") for x in b.stdout.splitlines()]
    assert la == lb
    # it really started at that card: a phase card opens with its PHASE_START, a clip card with its CLIP_START
    first = [x for x in la if x.startswith("E 0 ")][0].split()
    assert first[2] in ("1", "3", "12"), first


def test_start_at_a_card_that_is_not_there_is_refused():
    pack = pack_of(EXAMPLE)
    wasm = [node(), os.path.join(ENGINE, "vm_run.mjs"), os.path.join(ENGINE, "vm_engine.wasm")]
    for runner in (native(), wasm):
        r = run(runner, pack, b"\0" * 10, "--card", 8)
        assert r.returncode == 3 and "LOADERR" in r.stdout, r.stdout


def test_start_at_card_is_not_the_start_but_the_rest_is_the_same():
    """Starting at the flow's own start card is exactly vm_start: same hash as no --card."""
    pack = pack_of(EXAMPLE)
    inputs = _inputs(5, 900)
    a = run(native(), pack, inputs, "--max", 900)
    b = run(native(), pack, inputs, "--card", cards_of(EXAMPLE).index("c_intro"), "--max", 900)
    assert end_of(a.stdout) == end_of(b.stdout)


# ---- the calls the player makes on vm_engine.js --------------------------------------------------------------------
PLAYER_JS = r'''
import { readFileSync } from "node:fs";
import { VideoModeEngine, IN } from "%(js)s";
const vm = await VideoModeEngine.create(readFileSync(%(wasm)s));
const out = {};
out.load = vm.load(readFileSync(%(pack)s));
out.bad = vm.startAt(1, 0, 99);
out.started = vm.startAt(%(seed)d, 0, %(card)d);
out.card0 = vm.card();
const inputs = readFileSync(%(inputs)s);
let maxThings = 0, maxHits = 0, badHit = 0, steps = 0, phaseT = 0, dropped = 0;
for (let i = 0; i < inputs.length; i++) {
  const more = vm.step(inputs[i]);
  steps++;
  const h = vm.hitBoxes(), n = vm.things();
  if (h.length %% 6) badHit++;
  for (let k = 0; k < h.length; k += 6) {
    if (h[k] < 0 || h[k] > 6 || (h[k + 1] !== 0 && h[k + 1] !== 1) || h[k + 4] < 0) badHit++;
  }
  if (h.length / 6 > n) badHit++;
  maxThings = Math.max(maxThings, n); maxHits = Math.max(maxHits, h.length / 6);
  phaseT = Math.max(phaseT, vm.phaseT()); dropped += vm.dropped();
  if (!more) break;
}
Object.assign(out, { steps, maxThings, maxHits, badHit, phaseT, dropped, hash: vm.hash(), stepNo: vm.stepNo(),
                     phaseLen: vm.phaseLen(), IN });
console.log(JSON.stringify(out));
'''


def _player_js(tmp_path, pack, inputs, card, seed=1):
    (tmp_path / "m.pack").write_bytes(pack)
    (tmp_path / "m.inputs").write_bytes(inputs)
    src = PLAYER_JS % {"js": "file:///" + os.path.join(ENGINE, "vm_engine.js").replace("\\", "/"),
                       "wasm": json.dumps(os.path.join(ENGINE, "vm_engine.wasm")),
                       "pack": json.dumps(str(tmp_path / "m.pack")), "inputs": json.dumps(str(tmp_path / "m.inputs")),
                       "card": card, "seed": seed}
    (tmp_path / "p.mjs").write_text(src, encoding="utf-8")
    r = subprocess.run([node(), str(tmp_path / "p.mjs")], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_player_calls_and_a_recording_match_native(tmp_path):
    """What the player does with a recording (startAt the card, step the buttons, read the hash) gives the native
    build's hash on the same buttons: the replay check David's done-when asks for."""
    pack = pack_of(EXAMPLE)
    card = cards_of(EXAMPLE).index("c_chase")
    inputs = bytes([4] * 200 + [5] * 30 + [4] * 300 + [6] * 30 + [4] * 400) + _inputs(11, 1200)
    got = _player_js(tmp_path, pack, inputs, card)
    assert got["load"] == 0 and got["bad"] is False and got["started"] is True and got["card0"] == card
    assert got["badHit"] == 0 and got["maxHits"] >= 3 and got["maxThings"] >= got["maxHits"]
    assert got["phaseLen"] > 0 and got["phaseT"] > 0 and got["dropped"] == 0
    nat = run(native(), pack, inputs[:got["steps"]], "--card", card, "--max", got["steps"], "--quiet")
    end = end_of(nat.stdout)
    assert end["hash"] == got["hash"] and int(end["steps"]) == got["steps"]


def test_player_holds_300_things_with_their_hit_boxes(tmp_path):
    pack = pack_of(DESK)
    got = _player_js(tmp_path, pack, _inputs(3, 900), 0)
    assert got["badHit"] == 0 and got["maxThings"] >= 300 and got["dropped"] == 0
    nat = run(native(), pack, _inputs(3, 900)[:got["steps"]], "--card", 0, "--max", got["steps"], "--quiet")
    assert end_of(nat.stdout)["hash"] == got["hash"]


# ---- the Video modes tab's side ------------------------------------------------------------------------------------
def _project(tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import vm_demo_art
    sys.path.pop(0)
    project = tmp_path / "proj"
    md = project / "modes" / "night-harbour"
    vm_demo_art.make_mode(str(md))
    vm_demo_art.make_media(str(md), ffmpeg="")       # the effects only: no ffmpeg needed
    return project, md


def test_play_open_save_and_recordings(tmp_path):
    from tests.webui_harness import web_app
    project, md = _project(tmp_path)
    with web_app(tmp_path, mfr="stern") as w:
        w.run(lambda: w.window.write_assets_var.set(str(project)))
        w.drain()
        assert w.call("vmodes.refresh") is True
        assert w.state("vmodes")["slug"] == "night-harbour"
        info = w.call("vmodes.play_open")
        assert info["problems"] == []
        assert base64.b64decode(info["pack"]) == pack_of(str(md / "video_mode.json"))
        assert os.path.isfile(info["engine_js"]) and os.path.isfile(info["engine_wasm"])
        comp = compiler.compile_file(str(md / "video_mode.json"))
        assert [p["id"] for p in info["pictures"]] == comp.names["pictures"]
        assert all(p["path"] and os.path.isfile(p["path"]) for p in info["pictures"])
        assert [f["atlas"] for f in info["fonts"]] == [f["atlas"] for f in comp.names["fonts"]]
        assert [c["id"] for c in info["cards"]] == cards_of(str(md / "video_mode.json"))
        chase = next(c for c in info["cards"] if c["id"] == "c_chase")
        assert chase["card"] == "phase" and chase["kind"] == "chase"
        snd = {s["id"]: s for s in info["sounds"]}
        assert [s["id"] for s in info["sounds"]] == comp.names["sounds"]
        assert snd["zap"]["path"].endswith("zap.wav") and os.path.isfile(snd["zap"]["path"])
        assert snd["chase_music"]["loop"] is True and snd["chase_music"]["loop_start_s"] == 4.0
        assert [c["id"] for c in info["clips"]] == comp.names["clips"]
        m = info["machine"]
        assert m["key"] == "spike2" and m["things"] == 300 and m["quads"] == 1500 and m["draw_calls"] == 16
        assert info["recordings"] == []
        # what the pictures cost, worked out off the page's thread
        t0 = time.time()
        while not w.state("vmodes").get("play_mem") and time.time() - t0 < 60:
            time.sleep(0.05)
            w.drain()
        mem = w.state("vmodes")["play_mem"]
        assert mem and 0 < mem["used"] <= mem["budget"] == 48 * 1024 * 1024
        # a recording kept, listed, and read back; a name that is not one is refused
        data = bytes([4] * 120 + [1] * 5)
        name = w.call("vmodes.play_save", base64.b64encode(data).decode(), {"seed": 1, "card": 1, "card_id": "c_chase",
                                                                           "steps": len(data), "hash": "ab", "x": 9})
        assert name and (md / "replays" / (name + ".inputs")).read_bytes() == data
        meta = json.loads((md / "replays" / (name + ".json")).read_text(encoding="utf-8"))
        assert meta["card_id"] == "c_chase" and "x" not in meta and meta["made"]
        back = w.call("vmodes.play_recording", name)
        assert base64.b64decode(back["data"]) == data and back["steps"] == len(data) and back["name"] == name
        assert w.call("vmodes.play_recording", "../video_mode") is None
        assert w.call("vmodes.play_recording", "nothing-here") is None
        assert [r["name"] for r in w.call("vmodes.play_open")["recordings"]] == [name]


def test_play_open_says_what_does_not_compile(tmp_path):
    from tests.webui_harness import web_app
    project, md = _project(tmp_path)
    doc = json.loads((md / "video_mode.json").read_text(encoding="utf-8"))
    doc["flow"]["start"] = "no_such_card"
    (md / "video_mode.json").write_text(json.dumps(doc), encoding="utf-8")
    with web_app(tmp_path, mfr="stern") as w:
        w.run(lambda: w.window.write_assets_var.set(str(project)))
        w.drain()
        w.call("vmodes.refresh")
        info = w.call("vmodes.play_open")
        assert info["problems"] and "pack" not in info


def test_placeholder_pictures_are_the_compilers_size(tmp_path):
    """A picture with no file yet plays as a placeholder of the size the compiler gave it, so the engine's source
    boxes land inside it."""
    from tests.webui_harness import web_app
    project, md = _project(tmp_path)
    os.remove(md / "art" / "mine.png")
    os.remove(md / "art" / "drone.png")
    with web_app(tmp_path, mfr="stern") as w:
        w.run(lambda: w.window.write_assets_var.set(str(project)))
        w.drain()
        w.call("vmodes.refresh")
        info = w.call("vmodes.play_open")
        pics = {p["id"]: p for p in info["pictures"]}
        doc = json.loads((md / "video_mode.json").read_text(encoding="utf-8"))
        src = {p["id"]: p for p in doc["assets"]["pictures"]}
        for pid in ("mine", "drone"):
            p, d = pics[pid], src[pid]
            assert p["path"] == ""
            if d.get("frame_w"):
                assert (p["fw"], p["fh"]) == (d["frame_w"], d.get("frame_h", d["frame_w"]))
            assert p["h"] == p["fh"] * int(d.get("frames", 1))


# ---- the Modes tab: video modes in the list, and the wizard's way -------------------------------------------------
def test_modes_tab_lists_and_makes_video_modes(tmp_path):
    from tests.webui_harness import web_app
    project, _ = _project(tmp_path)
    with web_app(tmp_path, mfr="stern") as w:
        w.run(lambda: w.window.write_assets_var.set(str(project)))
        w.drain()
        tab = w.window.service("modes")
        rows = w.run(tab._video_rows)
        assert [(r["slug"], r["kind"], r["name"]) for r in rows] == [("night-harbour", "video", "Night Harbour")]
        w.run(tab._publish_rows)
        w.drain()
        assert any(r["kind"] == "video" and r["slug"] == "night-harbour" for r in w.state("modes")["rows"])
        # picking it opens it on the Video modes tab
        assert w.call("modes.select", "night-harbour", "video") is True
        w.drain()
        assert w.state("shell")["tab"] == "vmodes" and w.state("vmodes")["slug"] == "night-harbour"
        # the wizard's Video mode way
        slug = w.call("modes.new_video_mode", "Sky Run")
        w.drain()
        assert slug == "sky-run" and (project / "modes" / "sky-run" / "video_mode.json").is_file()
        assert w.state("vmodes")["slug"] == "sky-run" and w.state("shell")["tab"] == "vmodes"
        assert any(r["slug"] == "sky-run" for r in w.state("modes")["rows"] if r["kind"] == "video")
        assert w.call("modes.new_video_mode", "  ") is None


def test_a_broken_video_mode_is_listed_to_fix(tmp_path):
    from tests.webui_harness import web_app
    project = tmp_path / "proj"
    (project / "modes" / "bad").mkdir(parents=True)
    (project / "modes" / "bad" / "video_mode.json").write_text("{not json", encoding="utf-8")
    with web_app(tmp_path, mfr="stern") as w:
        w.run(lambda: w.window.write_assets_var.set(str(project)))
        w.drain()
        rows = w.run(w.window.service("modes")._video_rows)
        assert rows and rows[0]["chip"] == "to fix" and rows[0]["name"] == "bad"


# ---- the browser modules parse ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["vmodes_play.js", "vmodes.js", "modes_new.js", "modes.js"])
def test_browser_modules_parse(tmp_path, name):
    n = node()
    src = open(os.path.join(JS, name), encoding="utf-8").read()
    mod = tmp_path / (name[:-3] + ".mjs")
    mod.write_text(src, encoding="utf-8")
    got = subprocess.run([n, "--check", str(mod)], capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr


def test_wizard_offers_the_video_mode_way():
    src = open(os.path.join(JS, "modes_new.js"), encoding="utf-8").read()
    assert 'key: "video"' in src and 'call("modes.new_video_mode"' in src
    assert 'if (key === "video") return "";' in src         # needs a project, not a card
