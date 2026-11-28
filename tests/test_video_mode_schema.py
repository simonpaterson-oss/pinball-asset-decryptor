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
