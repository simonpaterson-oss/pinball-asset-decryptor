"""PAD-1654: the video mode document format (video_mode.json, format 1).

The schema file is the one description of the format: the app loads it
(pinball_decryptor/core/video_mode/document.py) and so do these tests.  The
plan (docs/plans/video_mode_maker.md) must name every field it holds."""

import copy
import json
import os
import re

import pytest

from pinball_decryptor.core import video_mode as vm
from pinball_decryptor.core.video_mode import document

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "pinball_decryptor", "core", "video_mode", "examples", "night_harbour.json")
PLAN = os.path.join(ROOT, "docs", "plans", "video_mode_maker.md")
FIXTURES = os.path.join(ROOT, "tests", "data", "video_mode")


def _walk(node, path=()):
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from _walk(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, path + (i,))


def _example():
    with open(EXAMPLE, encoding="utf-8") as f:
        return json.load(f)


# ---- the schema file itself -------------------------------------------------
def test_schema_loads_and_every_ref_resolves():
    sch = vm.schema()
    assert sch["properties"]["format"]["const"] == vm.FORMAT
    assert sch["properties"]["kind"]["const"] == vm.KIND
    refs = [n["$ref"] for _, n in _walk(sch) if isinstance(n.get("$ref"), str)]
    assert refs
    for r in refs:
        document._resolve(r)  # raises if missing


def test_schema_uses_only_keywords_the_app_validator_understands():
    sch = vm.schema()
    for path, node in _walk(sch):
        # skip the maps whose keys are field names, not keywords
        if path and path[-1] in ("properties", "$defs"):
            continue
        for k in node:
            assert k in document.KNOWN_KEYWORDS, "%s at %s" % (k, "/".join(map(str, path)))


def test_every_phase_kind_has_its_settings_and_a_place_in_the_plan():
    sch = vm.schema()
    kinds = sch["$defs"]["phase"]["properties"]["kind"]["enum"]
    for kind in kinds:
        assert "k_" + kind in sch["$defs"], kind
    with open(PLAN, encoding="utf-8") as f:
        plan = f.read()
    for kind in kinds:
        assert "`%s`" % kind in plan, "the plan does not describe the %s kind" % kind


def test_plan_names_every_field_of_the_schema():
    """Drift guard: a field added to the schema is written up in the plan."""
    with open(PLAN, encoding="utf-8") as f:
        plan = f.read()
    named = set(re.findall(r"`([a-z_][a-z0-9_]*)`", plan))
    missing = set()
    for path, node in _walk(vm.schema()):
        if path and path[-1] == "properties":
            missing |= {k for k in node if k not in named}
    assert not missing, "fields the plan does not explain: %s" % sorted(missing)


# ---- the worked example ---------------------------------------------------------
def test_worked_example_is_clean():
    doc = vm.load(EXAMPLE)
    assert vm.check(doc) == []
    assert {p["kind"] for p in doc["phases"]} == {"chase", "boss", "alternate"}


def test_worked_example_in_the_plan_is_the_shipped_file():
    """The plan quotes the example; it must not drift from the file."""
    with open(PLAN, encoding="utf-8") as f:
        plan = f.read()
    assert "pinball_decryptor/core/video_mode/examples/night_harbour.json" in plan
    with open(EXAMPLE, encoding="utf-8") as f:
        ex = json.load(f)
    for phase in ex["phases"]:
        assert '"%s"' % phase["id"] in plan


def test_jsonschema_agrees_when_installed():
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft202012Validator(vm.schema()).validate(_example())


# ---- what the checker says about broken documents ----------------------------------
def _broken(change):
    doc = _example()
    change(doc)
    return vm.check(doc)


BROKEN = [
    ("unknown field", lambda d: d.update(colour="red"), 'colour: is not a field this format knows'),
    ("stage not 1360", lambda d: d["stage"].update(width=1920), "stage > width: must be 1360 (it is 1920)"),
    ("unknown phase kind", lambda d: d["phases"][0].update(kind="racing"), 'phases[0] "chase" > kind: must be one of'),
    ("chase without its player", lambda d: d["phases"][0]["settings"].pop("player"), 'phases[0] "chase" > settings: is missing player'),
    ("boss setting on a chase", lambda d: d["phases"][0]["settings"].update(weak_points=[]), "settings > weak_points: is not a field this format knows"),
    ("circle hitbox without r", lambda d: d["assets"]["pictures"][3]["hitbox"].pop("r"), 'assets > pictures[3] "drone" > hitbox: is missing r'),
    ("file climbing out", lambda d: d["assets"]["pictures"][0].update(file="../../secret.png"), 'is not allowed here'),
    ("missing picture", lambda d: d["things"][0].update(picture="nope"), 'things[0] "player_boat" > picture: names "nope", but there is no picture with that id'),
    ("missing animation", lambda d: d["things"][0].update(animation="spin"), 'the picture "boat" has no animation with that id'),
    ("frame past the end", lambda d: d["assets"]["pictures"][2]["animations"][0]["frames"].append(9), "frame 9 is past the picture's 4 frames"),
    ("effect used as music", lambda d: d["phases"][0].update(music="zap"), 'names "zap", but there is no music sound with that id'),
    ("duplicate thing", lambda d: d["things"].append(copy.deepcopy(d["things"][0])), 'the id "player_boat" is already used at things[0]'),
    ("thing and value share an id", lambda d: d["values"][0].update(id="drone"), 'the id "drone" is already used'),
    ("unknown win target", lambda d: d["phases"][0]["win"][1].update(of="kraken"), 'no thing or value with that id'),
    ("dangling flow", lambda d: d["flow"]["cards"][1].update(won="nowhere"), 'names "nowhere", but there is no flow card with that id'),
    ("unreachable card", lambda d: d["flow"]["cards"][3].update(lost="c_won") or d["flow"]["cards"][2].update(won="c_won"), 'cards[3] "c_charge": cannot be reached from the start card'),
    ("endless loop", lambda d: d["flow"]["cards"][1].update(won="c_chase", lost="c_chase"), "loops for ever: no way from here reaches an end card"),
    ("no winning end", lambda d: d["flow"]["cards"][6].update(outcome="lost"), "flow: has no end card for a win"),
    ("phase card missing lost", lambda d: d["flow"]["cards"][1].pop("lost"), 'cards[1] "c_chase": is missing lost'),
    ("award for no phase", lambda d: d["pays"]["awards"][1].pop("phase"), "does not say which phase"),
    ("health as text", lambda d: d["things"][0].update(health="6"), 'health: should be integer (it is "6")'),
]


@pytest.mark.parametrize("name,change,expect", BROKEN, ids=[b[0] for b in BROKEN])
def test_broken_documents_are_told_in_plain_words(name, change, expect):
    probs = _broken(change)
    assert any(expect in p for p in probs), probs


# ---- versions ---------------------------------------------------------------------
def test_newer_format_is_refused_in_plain_words():
    doc = _example()
    doc["format"] = vm.FORMAT + 1
    with pytest.raises(vm.VideoModeError) as e:
        vm.migrate(doc)
    assert "saved by a newer PAD" in str(e.value)


@pytest.mark.parametrize("bad", [{"kind": "pad-video-mode"}, {"format": 1}, {"format": "1", "kind": "pad-video-mode"}, []])
def test_not_a_video_mode_is_refused(bad):
    with pytest.raises(vm.VideoModeError):
        vm.migrate(bad)


def test_migrate_leaves_the_input_alone():
    doc = _example()
    before = json.dumps(doc, sort_keys=True)
    out = vm.migrate(doc)
    assert json.dumps(doc, sort_keys=True) == before
    assert out == doc and out is not doc


def test_every_older_format_has_a_migration_and_a_frozen_fixture():
    """The rule for later versions: a step per format, a fixture per format, kept for good."""
    assert sorted(document.MIGRATIONS) == list(range(1, vm.FORMAT))
    for n in range(1, vm.FORMAT + 1):
        path = os.path.join(FIXTURES, "format_%d.json" % n)
        assert os.path.exists(path), "frozen fixture for format %d" % n
        doc = vm.load(path)
        assert doc["format"] == vm.FORMAT


def test_bad_json_names_the_line(tmp_path):
    p = tmp_path / "video_mode.json"
    p.write_text('{"format": 1,\n "kind": }', encoding="utf-8")
    with pytest.raises(vm.VideoModeError) as e:
        vm.load(str(p))
    assert "line 2" in str(e.value)


def test_dumps_round_trips():
    doc = vm.load(EXAMPLE)
    assert json.loads(document.dumps(doc)) == doc
    assert document.dumps(doc).endswith("}\n")


# ---- every game kind, as the survey of real machines added them (section 1b) ----
KIND_SETTINGS = {
    "chase": {"player": "player_boat", "steer": "hold", "ammo": 20, "gears": 5, "gear_button": "action"},
    "thrust": {"player": "player_boat", "thrust_button": "action", "fire_button": "right", "ammo": 30},
    "aim": {"sight": "sight", "fire": "auto", "move": "steer", "ammo": 20},
    "boss": {"boss": "warship", "weak_points": [{"x": 0, "y": 0, "r": 30}]},
    "mash": {"meter": "charge", "button": "action", "rival_per_s": 8, "goal": 100},
    "alternate": {"meter": "charge", "per_pair": 9, "goal": 100},
    "tug": {"meter": "charge", "hold": "shown", "shake_pairs": 6},
    "rhythm": {"music": "chase_music", "tempo_bpm": 120, "chart": [{"beat": 1, "button": "left"}]},
    "sequence": {"length": 5, "flash_s": 2, "per_press_s": 1},
    "dodge": {"buttons": ["left", "right"], "tell_s": 0.8, "window_s": 0.6, "count": 6},
    "shield": {"button": "action", "tell_s": 1, "hold_s": 2, "count": 3},
    "timing": {"input": "hold_release", "button": "left", "sweep_s": 1.5, "window_from": 0.4, "window_to": 0.6, "shrink_pct": 10, "rounds": 3},
    "defend": {"enemy": "drone", "from": "sides", "speed": 300, "every_s": 1, "count": 20, "reach": 200, "let_through": 2},
    "catch": {"catcher": "player_boat", "move": "lanes", "lanes": 3, "misses_allowed": 4},
    "runner": {"runner": "player_boat", "jump": "left", "long_jump": "both_flippers", "jump_px": 120, "long_jump_px": 240, "waves": 3},
    "lander": {"ship": "player_boat", "gravity": 200, "side_thrust": 300, "up": "both_flippers", "up_thrust": 500, "fuel_s": 20,
               "pads": [{"x": 300, "w": 120, "points": 50}, {"x": 900, "w": 60, "points": 100}]},
    "route": {"vehicle": "player_boat", "forks": ["left", "left", "right"], "speed": 400, "speed_up_pct": 5},
    "pick": {"choices": 3, "cash_out": "action", "bank_start": 250000, "rounds": 8,
             "outcomes": [{"label": "Double", "weight": 3, "result": "double"}, {"label": "Bust", "weight": 1, "result": "bust"}]},
    "custom": {},
}


def test_every_kind_is_in_the_table():
    assert sorted(KIND_SETTINGS) == sorted(vm.schema()["$defs"]["phase"]["properties"]["kind"]["enum"])


@pytest.mark.parametrize("kind", sorted(KIND_SETTINGS))
def test_a_phase_of_each_kind_checks_clean(kind):
    doc = _example()
    ph = doc["phases"][2]
    ph.update(kind=kind, settings=KIND_SETTINGS[kind], layout="fixed", ramp={"speed_from": 1, "speed_to": 1.4},
              bomb={"button": "action", "uses": 1})
    assert vm.check(doc) == []


NEW_BROKEN = [
    ("lander without pads", "lander", lambda s: s.pop("pads"), "settings: is missing pads"),
    ("lander pad with no width", "lander", lambda s: s["pads"][0].pop("w"), "pads[0]: is missing w"),
    ("defend names no thing", "defend", lambda s: s.update(enemy="kraken"), 'names "kraken", but there is no thing with that id'),
    ("pick with one outcome", "pick", lambda s: s["outcomes"].pop(), "outcomes: needs at least 2"),
    ("pick of four", "pick", lambda s: s.update(choices=4), "choices: must be at most 3 (it is 4)"),
    ("route fork upwards", "route", lambda s: s["forks"].append("up"), 'must be one of "left", "right"'),
    ("timing window past the bar", "timing", lambda s: s.update(window_to=1.5), "window_to: must be at most 1"),
    ("runner long jump on a fourth button", "runner", lambda s: s.update(long_jump="start"), "long_jump: must be one of"),
]


@pytest.mark.parametrize("name,kind,change,expect", NEW_BROKEN, ids=[b[0] for b in NEW_BROKEN])
def test_broken_new_kinds_are_told_in_plain_words(name, kind, change, expect):
    doc = _example()
    settings = copy.deepcopy(KIND_SETTINGS[kind])
    change(settings)
    doc["phases"][2].update(kind=kind, settings=settings)
    probs = vm.check(doc)
    assert any(expect in p for p in probs), probs


SURVEY_BROKEN = [
    ("extra ball of nothing", lambda d: d["pays"]["awards"][3].pop("of"), "does not say what"),
    ("extra ball of a ghost", lambda d: d["pays"]["awards"][3].update(of="ghost"), 'names "ghost", but there is no thing with that id'),
    ("pay per an unknown value", lambda d: d["pays"]["awards"][5].update(per="bullets"), 'names "bullets", but there is no value with that id'),
    ("operator shrinks below a quarter", lambda d: d["operator"].update(length_pct_min=10), "length_pct_min: must be at least 25"),
    ("unknown skip", lambda d: d["entry"].update(skip_clips="tilt"), "skip_clips: must be one of"),
    ("layout made up", lambda d: d["phases"][0].update(layout="shuffled"), "layout: must be one of"),
]


@pytest.mark.parametrize("name,change,expect", SURVEY_BROKEN, ids=[b[0] for b in SURVEY_BROKEN])
def test_survey_fields_are_checked(name, change, expect):
    probs = _broken(change)
    assert any(expect in p for p in probs), probs


def test_example_uses_the_survey_lessons():
    doc = _example()
    assert doc["entry"]["declinable"] and doc["operator"]["can_turn_off"]
    assert doc["pays"]["floor"] > 0
    whens = {a["when"] for a in doc["pays"]["awards"]}
    assert {"collected", "flawless"} <= whens
    assert {p.get("layout") for p in doc["phases"]} >= {"fixed", "per_play"}
