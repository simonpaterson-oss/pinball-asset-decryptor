"""PAD-1661: the video mode editor (the stage, the layers and the inspector).

The editor's page is webui/static/js/tabs/vmodes_edit.js; its Python half is webui/tabs/vmodes.py (edit_open,
edit_commit, edit_undo, edit_redo) and its undo history core/video_mode/history.py. These hold:

  * a history step is a diff that takes a document forward and back exactly, types and all;
  * 500 mixed edits made through the tab's own calls, with the app closed and opened again half-way, undo one by
    one back to the empty document (each step back is the document as it was), and redo to the last one;
  * a change that does not check is refused whole: nothing is saved and no step is kept;
  * a file changed outside the editor starts a new history instead of undoing into something that never was;
  * the stage is the engine's own still of the phase: the placed things stand where the game's first steps put
    them, a rewritten place moves in the still, and 300 placed things take a still and their boxes quickly;
  * the engine and compiler hold 1024 placed things (a phase may place 300).
The frame rate while dragging on a 300-thing stage, and laying a phase out with the mouse only and the keyboard
only, are shown in the app itself by scripts/shot_pad1661.py.
"""
import copy
import json
import os
import random
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pinball_decryptor.core.video_mode import compiler, document as D, history as H  # noqa: E402

ENGINE = os.path.join(ROOT, "pinball_decryptor", "core", "video_mode", "engine")
EXAMPLE = os.path.join(ROOT, "pinball_decryptor", "core", "video_mode", "examples", "night_harbour.json")
STAGE300 = os.path.join(ROOT, "tests", "data", "video_mode", "stage_300.json")
JS = os.path.join(ROOT, "pinball_decryptor", "webui", "static", "js", "tabs")

pytestmark = pytest.mark.xdist_group("video_mode_engine")


def node():
    n = shutil.which("node")
    if not n:
        pytest.skip("no Node for the WebAssembly engine")
    return n


# ---- the history's diff --------------------------------------------------------------------------------------
def _mutate(rng, v, depth=0):
    if isinstance(v, dict):
        v = dict(v)
        for k in list(v):
            r = rng.random()
            if r < 0.15:
                del v[k]
            elif r < 0.5:
                v[k] = _mutate(rng, v[k], depth + 1)
        if rng.random() < 0.3:
            v["k%d" % rng.randrange(50)] = _leaf(rng)
        return v
    if isinstance(v, list):
        v = [(_mutate(rng, x, depth + 1) if rng.random() < 0.4 else x) for x in v]
        r = rng.random()
        if r < 0.25 and v:
            del v[rng.randrange(len(v))]
        elif r < 0.5:
            v.insert(rng.randrange(len(v) + 1), _leaf(rng))
        elif r < 0.6 and len(v) > 1:
            rng.shuffle(v)
        return v
    return _leaf(rng) if rng.random() < 0.6 else v


def _leaf(rng):
    return rng.choice([1, 1.0, True, False, None, "a", "b", 0, -2.5, [1, 2], {"x": 1}, {"x": 1.0}, [], {}])


def _strict(a, b):
    return json.dumps(a, sort_keys=False) == json.dumps(b, sort_keys=False) and type(a) is type(b)


def test_a_step_takes_a_document_forward_and_back_exactly():
    rng = random.Random(1661)
    doc = json.load(open(EXAMPLE, encoding="utf-8"))
    for _ in range(300):
        new = _mutate(rng, doc)
        ops = H.diff(doc, new)
        fwd = H.apply(copy.deepcopy(doc), ops, forward=True)
        back = H.apply(copy.deepcopy(new), ops, forward=False)
        assert H.fingerprint(fwd) == H.fingerprint(new)
        assert H.fingerprint(back) == H.fingerprint(doc)
        doc = new


def test_a_moved_thing_costs_a_few_numbers_and_an_added_one_costs_that_thing():
    doc = json.load(open(STAGE300, encoding="utf-8"))
    moved = copy.deepcopy(doc)
    moved["phases"][0]["place"][150]["x"] += 5
    ops = H.diff(doc, moved)
    assert ops == [{"p": ["phases", 0, "place", 150, "x"], "a": doc["phases"][0]["place"][150]["x"],
                    "b": moved["phases"][0]["place"][150]["x"]}]
    added = copy.deepcopy(doc)
    added["phases"][0]["place"].insert(7, {"thing": "mine", "x": 1, "y": 2})
    ops = H.diff(doc, added)
    assert len(ops) == 1 and ops[0]["i"] == 7 and ops[0]["a"] == [] and ops[0]["b"] == [{"thing": "mine", "x": 1, "y": 2}]


# ---- the editor's calls --------------------------------------------------------------------------------------
def _empty_project(tmp_path):
    """A project holding one new video mode with Night Harbour's pictures and nothing on its stage."""
    project = tmp_path / "proj"
    md = project / "modes" / "edit-me"
    md.mkdir(parents=True)
    doc = D.new("edit-me", "Edit me")
    doc["assets"]["pictures"] = json.load(open(EXAMPLE, encoding="utf-8"))["assets"]["pictures"]
    D.save(str(md / D.FILE_NAME), doc)
    return project, md, doc


PICS = ["boat", "drone", "mine", "crate", "warship", "sight", "shell", "bolt"]
TEAMS = ["player", "enemy", "enemy_shot", "player_shot", "pickup", "health", "scenery"]


def _edit(rng, doc):
    """One mixed edit as the editor makes them (a whole new document and its label), or None."""
    d = copy.deepcopy(doc)
    ph = d["phases"][0]
    pls = ph.setdefault("place", [])
    things = d["things"]
    kind = rng.choice(["add", "add", "move", "move", "scale", "turn", "hide", "lock", "remove", "reorder", "team",
                       "hitbox", "mover", "title", "guide", "group", "background", "depth", "thing"])
    if kind == "thing" or (kind == "add" and not things) or (kind == "add" and rng.random() < 0.15):
        pid = rng.choice(PICS)
        tid = "%s_%d" % (pid, len(things))
        things.append({"id": tid, "picture": pid, "team": rng.choice(TEAMS)})
        kind = "add"
    if kind == "add":
        pls.append({"thing": rng.choice(things)["id"], "x": rng.randrange(1360), "y": rng.randrange(768)})
    elif not pls and kind in ("move", "scale", "turn", "hide", "lock", "remove", "reorder", "depth", "group"):
        return None
    elif kind == "move":
        p = rng.choice(pls)
        p["x"] = round(p["x"] + rng.uniform(-50, 50), 2)
        p["y"] = round(p["y"] + rng.uniform(-50, 50), 2)
    elif kind == "scale":
        rng.choice(pls)["scale"] = round(rng.uniform(0.2, 3), 3)
    elif kind == "turn":
        rng.choice(pls)["turn"] = round(rng.uniform(-180, 180), 2)
    elif kind in ("hide", "lock"):
        p = rng.choice(pls)
        key = "hidden" if kind == "hide" else "locked"
        if p.get(key):
            del p[key]
        else:
            p[key] = True
    elif kind == "remove":
        del pls[rng.randrange(len(pls))]
        d.get("editor", {}).pop("groups", None)
    elif kind == "reorder":
        rng.shuffle(pls)
        d.get("editor", {}).pop("groups", None)
    elif kind == "depth":
        rng.choice(pls)["depth"] = rng.randrange(-20, 20)
    elif kind == "group":
        if len(pls) < 2:
            return None
        d.setdefault("editor", {})["groups"] = {ph["id"]: [sorted(rng.sample(range(len(pls)), 2))]}
    elif kind == "team" and things:
        rng.choice(things)["team"] = rng.choice(TEAMS)
    elif kind == "hitbox" and things:
        t = rng.choice(things)
        if rng.random() < 0.5:
            t["hitbox"] = {"shape": "circle", "x": 0, "y": 0, "r": rng.randrange(4, 60)}
        else:
            t.pop("hitbox", None)
    elif kind == "mover" and things:
        t = rng.choice(things)
        t["mover"] = rng.choice([{"type": "straight", "speed": rng.randrange(10, 400), "direction": 180},
                                 {"type": "orbit", "radius": 40, "speed": 100},
                                 {"type": "path", "path": [[0, 0], [rng.randrange(20, 300), 0]], "speed": 120}])
    elif kind == "title":
        ph["title"] = "Phase %d" % rng.randrange(100)
    elif kind == "guide":
        g = d.setdefault("editor", {}).setdefault("guides", {})
        g.setdefault("x", []).append(rng.randrange(1360))
    elif kind == "background":
        d["stage"]["background"] = "#%06x" % rng.randrange(1 << 24)
    else:
        return None
    if H.fingerprint(d) == H.fingerprint(doc):
        return None                       # no change (the same team again, say): the editor makes no step of it
    return d, kind


def _open(w, project):
    w.run(lambda: w.window.write_assets_var.set(str(project)))
    w.drain()
    assert w.call("vmodes.refresh") is True
    info = w.call("vmodes.edit_open")
    assert info["ok"] and info["pack"], info.get("problems")
    return info


def test_500_mixed_edits_undo_back_to_the_empty_document(tmp_path):
    from tests.webui_harness import web_app
    project, md, empty = _empty_project(tmp_path)
    rng = random.Random(500)
    states = []
    with web_app(tmp_path / "a", mfr="stern") as w:
        info = _open(w, project)
        doc = info["doc"]
        states.append(doc)
        assert info["history"]["can_undo"] is False
        while len(states) < 251:
            e = _edit(rng, doc)
            if not e:
                continue
            r = w.call("vmodes.edit_commit", e[0], e[1])
            assert r["ok"], (e[1], r.get("problems"))
            assert r["pack"] and r["history"]["pos"] == len(states)
            doc = e[0]
            states.append(doc)
    # the app closed and opened again: the history is still there
    with web_app(tmp_path / "b", mfr="stern") as w:
        info = _open(w, project)
        assert info["history"]["pos"] == 250 and info["history"]["can_undo"]
        assert H.fingerprint(info["doc"]) == H.fingerprint(states[-1])
        doc = info["doc"]
        while len(states) < 501:
            e = _edit(rng, doc)
            if not e:
                continue
            r = w.call("vmodes.edit_commit", e[0], e[1])
            assert r["ok"], (e[1], r.get("problems"))
            doc = e[0]
            states.append(doc)
        kinds = set()
        for k in range(500, 0, -1):
            r = w.call("vmodes.edit_undo")
            assert r["ok"] and r["pack"], r.get("problems")
            assert H.fingerprint(r["doc"]) == H.fingerprint(states[k - 1]), "undo %d did not give the document back" % k
            kinds.add(r["label"])
        assert w.call("vmodes.edit_undo") == {"ok": False}
        assert H.fingerprint(D.load(str(md / D.FILE_NAME))) == H.fingerprint(empty)
        assert len(kinds) >= 12          # every sort of edit was among them
        for k in range(1, 501):
            r = w.call("vmodes.edit_redo")
            assert r["ok"] and H.fingerprint(r["doc"]) == H.fingerprint(states[k])
        assert w.call("vmodes.edit_redo") == {"ok": False}
        assert H.fingerprint(D.load(str(md / D.FILE_NAME))) == H.fingerprint(states[-1])
        # an undo then a new change: the redo branch is gone, the rest kept
        w.call("vmodes.edit_undo")
        e = _edit(rng, states[499])
        while not e:
            e = _edit(rng, states[499])
        assert w.call("vmodes.edit_commit", e[0], e[1])["ok"]
        st = w.state("vmodes")["history"]
        assert st["pos"] == 500 and st["steps"] == 500 and not st["can_redo"]


def test_a_change_that_does_not_check_is_refused_whole(tmp_path):
    from tests.webui_harness import web_app
    project, md, empty = _empty_project(tmp_path)
    with web_app(tmp_path, mfr="stern") as w:
        info = _open(w, project)
        bad = copy.deepcopy(info["doc"])
        bad["phases"][0]["place"] = [{"thing": "nobody", "x": 1, "y": 1}]
        r = w.call("vmodes.edit_commit", bad, "Add nobody")
        assert r["ok"] is False and any("nobody" in p for p in r["problems"])
        assert H.fingerprint(r["doc"]) == H.fingerprint(empty)
        assert H.fingerprint(D.load(str(md / D.FILE_NAME))) == H.fingerprint(empty)
        assert w.state("vmodes")["history"]["steps"] == 0
        # every picture change on the tab's own page is a step too
        assert w.call("vmodes.remove_picture", "shell") is True
        st = w.state("vmodes")["history"]
        assert st["steps"] == 1 and st["undo_label"] == "Remove a picture"
        r = w.call("vmodes.edit_undo")
        assert r["ok"] and any(p["id"] == "shell" for p in r["doc"]["assets"]["pictures"])
        assert r["pictures"]                # the pictures changed: the page gets them again


def test_a_file_changed_outside_starts_a_new_history(tmp_path):
    from tests.webui_harness import web_app
    project, md, empty = _empty_project(tmp_path)
    with web_app(tmp_path, mfr="stern") as w:
        info = _open(w, project)
        d = copy.deepcopy(info["doc"])
        d["things"] = [{"id": "boat", "picture": "boat", "team": "player"}]
        d["phases"][0]["place"] = [{"thing": "boat", "x": 100, "y": 100}]
        assert w.call("vmodes.edit_commit", d, "Add boat")["ok"]
        hand = D.load(str(md / D.FILE_NAME))
        hand["title"] = "Changed by hand"
        D.save(str(md / D.FILE_NAME), hand)
        w.call("vmodes.refresh")
        st = w.state("vmodes")["history"]
        assert st == {"can_undo": False, "can_redo": False, "undo_label": "", "redo_label": "", "steps": 0, "pos": 0}
        assert w.call("vmodes.edit_undo") == {"ok": False}
        assert D.load(str(md / D.FILE_NAME))["title"] == "Changed by hand"


# ---- the stage is the engine's still -------------------------------------------------------------------------
NODE_STILL = r"""
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const [eng, wasm, nh, nhCard, s300] = process.argv.slice(2);
const { VideoModeEngine } = await import(pathToFileURL(eng).href);
const vm = await VideoModeEngine.create(readFileSync(wasm));
const out = {};
// Night Harbour's boss phase: the still against the game's own first steps of that phase
if (vm.load(readFileSync(nh))) throw new Error("load");
const phase = 1;
if (!vm.editStill(phase, 0)) throw new Error("still");
const still = vm.placeBoxes();
const noTitle = vm.drawWords().length;
vm.editStill(phase, 1);
const withTitle = vm.drawWords().length;
vm.startAt(1, 0, Number(nhCard));
for (let i = 0; i < 18; i++) vm.step(0);
out.boss = { still, played: vm.placeBoxes(), state: vm.state(), noTitle, withTitle };
// a place rewritten in the loaded tables moves in the next still (phase 1's places start after phase 0's)
const base = 1;    // the chase places one thing
vm.placeSet(base + 0, 780, 330, 1.5, 30, null, false);
vm.editStill(phase, 0);
out.moved = vm.placeBoxes()[0];
vm.placeSet(base + 0, 780, 330, 1, 0, null, true);
vm.editStill(phase, 0);
out.hidden = vm.placeBoxes()[0];
out.hits = vm.hitBoxes().length / 6;
// 300 placed things: the still and its boxes, timed
if (vm.load(readFileSync(s300))) throw new Error("load 300");
const t0 = performance.now();
let n = 0;
for (let k = 0; k < 600; k++) {
  vm.placeSet(k % 300, 100 + (k % 50), 200, 1, 0, null, false);
  vm.editStill(0, 0); vm.drawWords(); n = vm.placeBoxes().filter((b) => b.alive).length;
}
out.s300 = { alive: n, ms: (performance.now() - t0) / 600 };
console.log(JSON.stringify(out));
"""


def test_the_stage_is_the_engines_still_of_the_phase(tmp_path):
    doc = json.load(open(EXAMPLE, encoding="utf-8"))
    comp = compiler.compile_doc(doc)
    assert comp.ok and comp.names["place0"] == [0, 1, 4]
    card = [c["id"] for c in doc["flow"]["cards"]].index("c_boss")
    s300 = compiler.compile_doc(json.load(open(STAGE300, encoding="utf-8")))
    assert s300.ok
    (tmp_path / "nh.pack").write_bytes(comp.pack)
    (tmp_path / "s300.pack").write_bytes(s300.pack)
    (tmp_path / "still.mjs").write_text(NODE_STILL, encoding="utf-8")
    r = subprocess.run([node(), str(tmp_path / "still.mjs"), os.path.join(ENGINE, "vm_engine.js"),
                        os.path.join(ENGINE, "vm_engine.wasm"), str(tmp_path / "nh.pack"), str(card),
                        str(tmp_path / "s300.pack")], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    boss = out["boss"]
    places = doc["phases"][1]["place"]
    assert len(boss["still"]) == len(places) == 3
    for b, p in zip(boss["still"], places):
        assert b["alive"] and (b["x"], b["y"]) == (p["x"], p["y"])
    # the game's own 18 first steps of the phase (still on its title card) leave every placed thing where the
    # still shows it, its frame the same size
    assert boss["state"] == 2 and boss["played"] == boss["still"]
    assert boss["withTitle"] > boss["noTitle"]      # the title card is words over the stage, only when asked
    m = out["moved"]
    assert (m["x"], m["y"], m["turn"]) == (780, 330, 30)
    w0 = boss["still"][0]["x1"] - boss["still"][0]["x0"]
    assert abs((m["x1"] - m["x0"]) - 1.5 * w0) < 0.01
    assert out["hidden"]["alive"] and out["hidden"]["hidden"]
    assert out["s300"]["alive"] == 300
    assert out["s300"]["ms"] < 4.0, out["s300"]        # well inside a 16.7 ms frame (about 0.5 ms in Edge)


def test_the_engine_holds_1024_placed_things():
    doc = json.load(open(STAGE300, encoding="utf-8"))
    one = doc["phases"][0]
    for n in range(1, 4):
        doc["phases"].append(dict(copy.deepcopy(one), id="stage_%d" % n))
    total = sum(len(p["place"]) for p in doc["phases"])
    assert total == 1200
    comp = compiler.compile_doc(doc)
    assert not comp.ok and any("placed things" in p for p in comp.problems)
    doc["phases"][-1]["place"] = doc["phases"][-1]["place"][:124]
    assert sum(len(p["place"]) for p in doc["phases"]) == 1024
    comp = compiler.compile_doc(doc)
    assert comp.ok, comp.problems[:3]
    h = open(os.path.join(ENGINE, "vm_engine.h"), encoding="utf-8").read()
    assert "#define VM_MAX_PLACES     1024" in h


def test_stage_300_is_made_by_its_script(tmp_path):
    src = os.path.join(ROOT, "tests", "data", "video_mode", "make_stage_300.py")
    shutil.copy(src, tmp_path / "make_stage_300.py")
    shutil.copy(os.path.join(ROOT, "tests", "data", "video_mode", "desk_300.json"), tmp_path / "desk_300.json")
    subprocess.run([sys.executable, str(tmp_path / "make_stage_300.py")], check=True, timeout=60)
    assert (tmp_path / "stage_300.json").read_text(encoding="utf-8") == open(STAGE300, encoding="utf-8").read()
    assert D.check(json.load(open(STAGE300, encoding="utf-8"))) == []


# ---- the page ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["vmodes_edit.js", "vmodes_play.js", "vmodes.js", "vmodes_hud.js"])
def test_browser_modules_parse(tmp_path, name):
    src = open(os.path.join(JS, name), encoding="utf-8").read()
    mod = tmp_path / (name[:-3] + ".mjs")
    mod.write_text(src, encoding="utf-8")
    r = subprocess.run([node(), "--check", str(mod)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr


def test_the_editor_keeps_the_design_languages_shortcuts():
    src = open(os.path.join(JS, "vmodes_edit.js"), encoding="utf-8").read()
    for keys in ("Ctrl Z / Ctrl Shift Z", "Ctrl C / Ctrl V / Ctrl D", "Arrows / Shift arrows", "Ctrl G / Ctrl Shift G",
                 "Ctrl A", "Ctrl wheel / Ctrl 0 / Ctrl 1", "Ctrl K / Ctrl P", "F5", "H"):
        assert '["%s"' % keys in src, keys
    tab = open(os.path.join(JS, "vmodes.js"), encoding="utf-8").read()
    assert "VideoModeEditor" in tab and ">Edit<//>" in tab
