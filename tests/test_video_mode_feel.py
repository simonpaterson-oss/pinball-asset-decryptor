"""The video mode HUD and feel (PAD-1666).

Everything is the engine's (vm_engine.c): words styled from glyphs baked out of the same face (fonts.py), the HUD's
looks, pop-up words, particles from presets, shake, flashes, hit-stop, squash, blink, transitions, CRT. These tests
hold each effect to its switch (every one can be turned off per mode), each style preset to the format and the
machine's budget, the app and the machine to one draw list (native and WebAssembly, every preset), a card's own
glyph table to the baked face, and the editor's HUD parts to the engine's own boxes.
"""
import base64
import copy
import json
import os
import random
import shutil
import subprocess
import tempfile

import pytest

from pinball_decryptor.core.video_mode import compiler, document as D, feel, fonts as F, harness
from tests.test_video_mode_engine import native, wasm, run, random_inputs, end_of

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "pinball_decryptor", "core", "video_mode", "examples", "night_harbour.json")
FIXTURES = os.path.join(ROOT, "tests", "data", "video_mode")
ENGINE = os.path.join(ROOT, "pinball_decryptor", "core", "video_mode", "engine")

pytestmark = pytest.mark.xdist_group("video_mode_engine")
VM_FX = {"shake": 0x001, "flash": 0x002, "particles": 0x004, "hit_stop": 0x008, "crt": 0x010, "squash": 0x020,
         "blink": 0x040, "popups": 0x080, "trails": 0x100, "count_up": 0x200, "pulse": 0x400}


def example():
    return D.load(EXAMPLE)


def compiled(doc):
    c = compiler.compile_doc(doc)
    assert c.ok, c.problems
    return c


def dumps(doc, inputs, n=1, steps=2400):
    """[(step, words)] of a run on the native engine, every n steps."""
    c = compiled(doc)
    out = run(native(), c.pack, "--inputs", inputs, "--seed", 9, "--max", steps, "--dump", n, "--quiet").stdout
    _, _, ds, _ = harness.parse(out)
    return ds, c


def quads(w):
    i = 8
    while i < len(w):
        if w[i] & 0xFF == 1:
            yield w[i:i + 12]
            i += 12
        else:
            i += 6


def boxes(w):
    i = 8
    while i < len(w):
        if w[i] & 0xFF == 1:
            i += 12
        else:
            yield w[i:i + 6]
            i += 6


def s32(v):
    return v - (1 << 32) if v >= 1 << 31 else v


def with_style(doc, **kw):
    d = copy.deepcopy(doc)
    d["style"] = dict(d.get("style") or {}, **kw)
    return d


# a chase where things come at the player: hurts, kills and pick-ups in the first seconds
def busy_inputs():
    rnd = random.Random(1666)
    out = bytearray([0] * 240)              # the intro clip waits for the host's bit
    out[200] = 8
    for _ in range(4000):
        out.append(4 | rnd.choice([0, 0, 0, 1, 2]))     # Action held, the flippers now and then
    return bytes(out)


# ---- the format and the presets ----------------------------------------------------------------------------------
def test_format_3_reads_on_as_format_4_unchanged_but_its_number():
    with open(os.path.join(FIXTURES, "format_3.json"), encoding="utf-8") as f:
        raw = json.load(f)
    doc = D.migrate(raw)
    want = copy.deepcopy(raw)
    want["format"] = 4
    assert doc == want and D.check(doc) == []


@pytest.mark.parametrize("name", sorted(feel.STYLE_PRESETS))
def test_every_style_preset_checks_compiles_and_fits_spike2(name):
    doc = example()
    out = feel.apply_preset(doc, name)
    assert D.check(out) == [], name
    compiled(out)
    assert out["style"]["preset"] == name
    # places, sizes, fonts and values are the maker's: a preset only restyles
    for a, b in zip(doc["hud"], out["hud"]):
        assert (a["id"], a["x"], a["y"], a.get("w"), a.get("h"), a.get("font"), a.get("value")) == \
               (b["id"], b["x"], b["y"], b.get("w"), b.get("h"), b.get("font"), b.get("value"))
    c = feel.costs(out, "spike2")
    assert c["budget"] == 1500 and 0 < c["share"] < 100, c
    assert {r["key"] for r in c["rows"]} >= {"particles", "trails", "text", "popups", "bars", "crt"}


def test_a_preset_adds_its_pop_up_words_once():
    doc = example()
    doc["hud"] = [h for h in doc["hud"] if h["part"] != "popup"]
    a = feel.apply_preset(doc, "arcade")
    b = feel.apply_preset(a, "retro_pixel")
    assert [h["id"] for h in b["hud"] if h["part"] == "popup"] == ["popups"]
    assert b["style"]["crt"] is True and b["hud"][-1]["on"] == ["kill"]


def test_bursts_and_trails_must_name_a_particle_or_a_preset():
    doc = example()
    doc["style"]["bursts"]["kill"] = "confetti"
    doc["things"][0]["trail"] = {"particles": "glitter"}
    probs = [D.place(p, doc) + ": " + w for p, w in D.reference_problems(doc)]
    assert any("confetti" in p for p in probs) and any("glitter" in p for p in probs), probs


def test_particle_settings_become_the_engines_numbers():
    row = feel.emitter_row(feel.particle({"preset": "spark", "count": 20, "speed": [600, 60], "life_s": 0.5, "drag": 1}))
    count, lo, hi, _dir, spread, life = row[:6]
    assert count == 20 and lo == round(60 * 65536 / 60) and hi == round(600 * 65536 / 60)   # sorted, px a step
    assert spread == 360 * 65536 and life == 30 and row[9] == 65536                          # no drag: all kept
    assert feel.style_bits({}) == 0x001 | 0x002 | 0x004 | 0x020 | 0x040 | 0x080 | 0x100 | 0x200 | 0x400


# ---- every effect, and its switch ------------------------------------------------------------------------------
def _effects(ds, c):
    """What a run's draw lists show of each effect."""
    fonts = c.names["fonts"]
    saw = {"shake": 0, "flash": 0, "squash": 0, "blink": 0, "crt": 0, "particles": 0, "popup_words": set(),
           "score_words": set()}
    for _step, w in ds:
        if w[3] or w[4]:
            saw["shake"] += 1
        if w[5] and w[5] & 0xFF:
            saw["flash"] += 1
        for q in quads(w):
            if q[8] != q[9]:
                saw["squash"] += 1
            if q[1] & 0xFFFF < compiler.FONT_ATLAS_BASE and (q[0] >> 16) & 0xFF == 70:
                saw["blink"] += 1
        bx = list(boxes(w))
        saw["crt"] += sum(1 for b in bx if b[5] & 0xFFFFFF00 == 0 and s32(b[4]) == 2 * 65536 and s32(b[3]) == 1360 * 65536)
        saw["particles"] += sum(1 for b in bx if s32(b[3]) < 80 * 65536 and s32(b[4]) < 80 * 65536 and b[5] & 0xFF)
        for words in harness.picture(w, c.names, fonts)[1]:
            for piece in words.split(" | "):
                if piece.startswith("+"):
                    saw["popup_words"].add(piece)
                if piece.replace(",", "").isdigit():
                    saw["score_words"].add(int(piece.replace(",", "")))
    return saw


def test_every_effect_shows_and_every_switch_turns_it_off():
    doc = with_style(example(), crt=True, hit_stop=True, transition="white_flash")
    # words only on the HUD, so every small box on the stage is a particle (hearts and bars are boxes too)
    doc["hud"] = [h for h in doc["hud"] if h["part"] in ("score", "combo", "multiplier", "counter", "popup", "callout")]
    on, c = dumps(doc, busy_inputs())
    seen = _effects(on, c)
    assert seen["shake"] and seen["flash"] and seen["squash"] and seen["blink"], seen
    assert seen["crt"] >= 192 and seen["particles"] > 50 and seen["popup_words"], seen
    scores = {s for s in seen["score_words"]}
    assert any(s % 100 for s in scores), sorted(scores)[:20]      # the score rolled up through numbers between kills
    off_all = {k: False for k in VM_FX}
    off, c2 = dumps(with_style(doc, **off_all), busy_inputs())
    none = _effects(off, c2)
    assert not none["shake"] and not none["squash"] and not none["blink"] and not none["crt"], none
    assert not none["particles"] and not none["popup_words"], none
    assert not none["flash"], none                                 # the hurt flash and the white-flash way in
    assert all(s % 100 == 0 for s in none["score_words"]), sorted(none["score_words"])[:20]
    for key in ("shake", "squash", "crt", "particles", "popups", "blink"):     # and each alone
        one, c3 = dumps(with_style(doc, **{key: False}), busy_inputs(), n=2, steps=1600)
        s = _effects(one, c3)
        gone = {"popups": "popup_words"}.get(key, key)
        assert not s[gone], (key, s[gone])


def test_hit_stop_holds_the_play_still_for_its_frames():
    base = with_style(example(), hit_stop=False)
    held = with_style(example(), hit_stop=True, hit_stop_frames=6)
    a = end_of(run(native(), compiled(base).pack, "--bot", "--quiet").stdout)
    b = end_of(run(native(), compiled(held).pack, "--bot", "--quiet").stdout)
    assert int(b["steps"]) > int(a["steps"]) and a["outcome"] == b["outcome"] == "1"


def test_the_combo_multiplies_kill_points():
    doc = example()
    doc["combo"] = {"window_s": 100, "every": 1, "max": 3}       # every kill in one long combo adds 1, up to x3
    out = run(native(), compiled(doc).pack, "--bot", "--quiet").stdout
    flat = run(native(), compiled(dict(doc, combo={"every": 0})).pack, "--bot", "--quiet").stdout
    assert int(end_of(out)["score"]) > int(end_of(flat)["score"])


@pytest.mark.parametrize("name", sorted(feel.STYLE_PRESETS))
def test_every_preset_plays_the_same_on_the_machine_engine_and_in_the_app(name):
    """The match check: the same pack and buttons give the same draw list hash natively and in WebAssembly."""
    pack = compiled(feel.apply_preset(example(), name)).pack
    ins = busy_inputs()
    a = end_of(run(native(), pack, "--inputs", ins, "--seed", 3, "--max", 2500, "--quiet").stdout)
    b = end_of(run(wasm(), pack, "--inputs", ins, "--seed", 3, "--max", 2500, "--quiet").stdout)
    assert a["hash"] == b["hash"] and a["steps"] == b["steps"], (name, a, b)


def test_particles_hold_the_spike2_budget_at_their_worst():
    """Four bursts of the heaviest preset at once and every trail stay inside the engine's 3072 entries, and the
    preset styles inside the machine's 1500 a frame by the cost report."""
    doc = with_style(example(), bursts={k: "glow" for k in feel.BURSTS})
    ds, _c = dumps(doc, busy_inputs(), n=1, steps=2000)
    worst = max(len(list(quads(w))) + len(list(boxes(w))) for _s, w in ds)
    assert worst < 1500, worst
    for name in feel.STYLE_PRESETS:
        assert feel.costs(feel.apply_preset(example(), name))["total"] < 1500


# ---- the fonts --------------------------------------------------------------------------------------------------
def _card_project(tmp_path):
    """A project with a glyph table as the Stern plugin extracts one: a few letters as slices, with metrics."""
    from PIL import Image, ImageDraw
    proj = tmp_path / "proj"
    st = proj / "images" / "scene_textures"
    gdir = st / "glyphs" / "radimg_HudFont_256x256_1"
    gdir.mkdir(parents=True)
    rows = []
    for k, ch in enumerate("AEOS05X+"):
        im = Image.new("RGBA", (30, 40), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle((4, 4, 25, 35), fill=(255, 255, 255, 255))
        rel = "scene_textures/glyphs/radimg_HudFont_256x256_1/%d.png" % ord(ch)     # from the project's images/
        im.save(proj / "images" / rel)
        rows.append("\t".join([rel, "scene_textures/radimg_HudFont_256x256_1.png", str(ord(ch)), str(k * 32), "0",
                               "30", "40", "HudFont", "0", "30", "40", "0", "34", "32", "radimg_HudFont_256x256_1"]))
    (st / "glyph_images.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return proj


def test_a_card_font_bakes_from_the_games_own_glyph_table(tmp_path):
    proj = _card_project(tmp_path)
    md = proj / "modes" / "m"
    md.mkdir(parents=True)
    doc = {"assets": {"fonts": [{"id": "hud", "face": "card:default", "size": 40}, {"id": "big", "face": "card:HudFont", "size": 80}]}}
    baked = F.bake(str(md), doc)
    for fid, size in (("hud", 40), ("big", 80)):
        b = baked[fid]
        assert not b.stand_in and b.source == "card:HudFont", (fid, b.source)
        a = b.glyphs[ord("A")]
        assert a["fill"] is not None and a["outline"] is not None and a["ramp"] is not None
        assert a["outline"].size == (a["fill"].size[0] + 2 * b.ow, a["fill"].size[1] + 2 * b.ow)
        assert a["fill"].size == a["ramp"].size
        assert abs(a["adv"] - 32 * size / 40.0 * (40.0 / (b.line or 40))) < 40     # the game's advance, scaled
    # the gradient ramp runs down the line: dark at the top of a letter, light at its foot
    r = baked["big"].glyphs[ord("E")]["ramp"].split()[3]
    assert r.getpixel((r.size[0] // 2, 1)) < r.getpixel((r.size[0] // 2, r.size[1] - 2))
    # the same glyphs reach the machine's pack (fill, outline and ramp) and the app's sheet
    files, metrics = F.sheets(str(md), doc, str(tmp_path / "sheets"))
    row = metrics["big"]["glyphs"][ord("A") - 32]
    assert row[5] > 0 and row[9] > 0 and row[11] >= 0          # fill, outline and ramp boxes in the sheet
    assert files["big"]["source"] == "card:HudFont" and os.path.isfile(files["big"]["path"])
    c = compiler.compile_doc(example(), fonts={"hud": metrics["hud"], "big": metrics["big"]})
    assert c.ok, c.problems
    items, _meta, probs = __import__("pinball_decryptor.core.video_mode.pack", fromlist=["bake_fonts"]).bake_fonts(str(md), doc)
    assert not probs and {it.index for it in items if it.owner == "font:hud"} >= {65, 1065, 2065}


def test_a_font_with_no_face_on_the_card_bakes_a_stand_in(tmp_path):
    files, metrics = F.sheets(None, {"assets": {"fonts": [{"id": "f", "face": "card:nothing", "size": 30}]}}, str(tmp_path))
    assert files["f"]["stand_in"] and metrics["f"]["glyphs"][ord("A") - 32][5] > 0
    again, _ = F.sheets(None, {"assets": {"fonts": [{"id": "f", "face": "card:nothing", "size": 30}]}}, str(tmp_path))
    assert again["f"]["path"] == files["f"]["path"]                 # made once per look of the fonts


# ---- the editor: HUD parts on the stage are the engine's own boxes ---------------------------------------------
NODE_HUD = r"""
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const [eng, wasm, nh, hudIndex] = process.argv.slice(2);
const { VideoModeEngine } = await import(pathToFileURL(eng).href);
const vm = await VideoModeEngine.create(readFileSync(wasm));
if (vm.load(readFileSync(nh))) throw new Error("load");
const out = {};
vm.editStill(0, 0);
out.plain = vm.hudBoxes();
vm.editStill(0, 2);
out.sample = vm.hudBoxes();
out.words = vm.drawWords().length;
const i = Number(hudIndex), b = out.sample[i];
vm.hudSet(i, 300, 400, 0, 0);
vm.editStill(0, 2);
out.moved = vm.hudBoxes()[i];
out.count = vm.hudCount();
vm.editStill(0, 2);
const before = vm.drawWords().length;
out.burst = vm.editBurst(0, 680, 384, 10);
out.burstWords = vm.drawWords().length - before;
console.log(JSON.stringify(out));
"""


def test_the_editor_picks_hud_parts_by_the_engines_own_boxes(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("no Node for the WebAssembly engine")
    doc = example()
    c = compiled(doc)
    (tmp_path / "nh.pack").write_bytes(c.pack)
    (tmp_path / "hud.mjs").write_text(NODE_HUD, encoding="utf-8")
    score = [h["id"] for h in doc["hud"]].index("score")
    r = subprocess.run([node, str(tmp_path / "hud.mjs"), os.path.join(ENGINE, "vm_engine.js"), os.path.join(ENGINE, "vm_engine.wasm"),
                        str(tmp_path / "nh.pack"), str(score)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["count"] == len(doc["hud"])
    plain = {doc["hud"][k]["id"] for k, b in enumerate(out["plain"]) if b["drawn"]}
    assert not plain & {"combo", "mult", "prompts", "popups"} and "score" in plain, plain   # sample parts: only in the sample
    drawn = {doc["hud"][k]["id"]: b for k, b in enumerate(out["sample"]) if b["drawn"]}
    # the sample still shows every part of the chase: the combo, the multiplier, the prompts, a pop-up
    assert {"hp", "progress", "combo", "mult", "score", "crates_n", "prompts", "popups"} <= set(drawn), sorted(drawn)
    s = drawn["score"]
    assert 1332 - 2 <= s["x1"] <= 1332 + 8 and s["x0"] < s["x1"] - 40      # right-aligned at x 1332 (its shadow past it)
    m = out["moved"]
    assert abs(m["x0"] - 300) < 30 and abs(m["y0"] - 400) < 30                          # moved where it was put
    assert out["burst"] and out["burstWords"] > 0                                       # the preview drew particles


def test_the_editor_tab_gives_the_feel_and_applies_a_preset_as_one_step(tmp_path):
    from tests.webui_harness import web_app
    project = tmp_path / "proj"
    md = project / "modes" / "night-harbour"
    md.mkdir(parents=True)
    shutil.copy(EXAMPLE, md / D.FILE_NAME)
    with web_app(tmp_path, mfr="stern") as w:
        w.run(lambda: w.window.write_assets_var.set(str(project)))
        w.drain()
        assert w.call("vmodes.refresh") is True
        info = w.call("vmodes.edit_open")
        assert info["ok"] and info["pack"], info.get("problems")
        assert [p["key"] for p in info["presets"]] == list(feel.STYLE_PRESETS)
        assert {s["key"] for s in info["switches"]} == set(VM_FX)
        assert info["feel"]["budget"] == 1500 and info["emitters"][:1] == ["wake"]
        assert set(info["emitters"]) >= set(feel.PRESET_NAMES)
        fonts = info["fonts"]
        assert fonts and all(os.path.isfile(f["path"]) for f in fonts)   # baked sheets, not the stand-in grid
        r = w.call("vmodes.edit_preset", "retro_pixel")
        assert r["ok"] and r["doc"]["style"]["preset"] == "retro_pixel" and r["doc"]["style"]["crt"] is True
        assert r["history"]["undo_label"] == "Style: Retro pixel"
        assert D.load(str(md / D.FILE_NAME))["style"]["preset"] == "retro_pixel"
        u = w.call("vmodes.edit_undo")
        assert u["ok"] and u["doc"]["style"]["preset"] == "comic"
        assert w.call("vmodes.edit_preset", "glitter")["ok"] is False


# ---- the button kinds (PAD-1663) and pop-up words --------------------------------------------------------------
def test_a_modes_own_pop_up_on_presses_takes_the_place_of_the_judge_word():
    """PAD-1663's kinds say PERFECT / GOOD / MISS themselves; a mode that adds pop-up words on presses shows those
    instead, rising from the player, never both (the rule agreed between the two tickets)."""
    from pinball_decryptor.core.video_mode import kinds_buttons
    from tests.test_video_mode_kinds2 import _press_at

    def run_words(with_popup):
        doc, _ = kinds_buttons.new_doc("rhythm")
        doc["phases"][0]["settings"]["chart"] = [{"beat": 4 + 4 * i, "button": "action"} for i in range(3)]
        if with_popup:
            font = ((doc.get("assets") or {}).get("fonts") or [{}])[0].get("id")
            part = {"id": "nice", "part": "popup", "x": 680, "y": 300, "text": "NICE", "on": ["prompt_perfect", "prompt_good"]}
            if font:
                part["font"] = font
            doc.setdefault("hud", []).append(part)
        assert D.check(doc) == []
        c = compiled(doc)
        ins = _press_at([2000 + 2000 * i for i in range(3)], [4] * 3, 900)
        out = run(native(), c.pack, "--inputs", ins, "--max", 900, "--dump", 1, "--quiet").stdout
        _, _, ds, _ = harness.parse(out)
        seen = set()
        for _s, w in ds:
            for line in harness.picture(w, c.names, c.names["fonts"])[1]:
                seen.update(line.split(" | "))
        return seen
    plain, own = run_words(False), run_words(True)
    assert "PERFECT" in plain and "NICE" not in plain, sorted(plain)
    assert "NICE" in own and "PERFECT" not in own, sorted(own)
