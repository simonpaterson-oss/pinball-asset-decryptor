"""PAD-1664, the storyboard: Add a phase makes a playable phase of any of the 19 game kinds (document.phase_template),
with the placeholder things it needs, that checks and compiles once the page wires it into the flow."""
import copy
import json
import os

import pytest

from pinball_decryptor.core.video_mode import compiler, document

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "pinball_decryptor", "core", "video_mode", "examples", "night_harbour.json")
KINDS = list(document.KIND_WORDS)


def night_harbour():
    with open(EXAMPLE, encoding="utf-8") as f:
        return document.migrate(json.load(f))


def wire_after_first_phase(doc, pid):
    """As the storyboard's "+" on the first phase's WON wire does: the new card goes in between, its lost to the
    lost end."""
    cards = doc["flow"]["cards"]
    first = next(c for c in cards if c["card"] == "phase")
    lost = next(c["id"] for c in cards if c.get("outcome") == "lost")
    cid = "c_" + pid
    cards.append({"id": cid, "card": "phase", "phase": pid, "won": first["won"], "lost": lost})
    first["won"] = cid
    return doc


def test_the_template_covers_every_game_kind_of_the_schema():
    assert sorted(KINDS) == sorted(document.schema()["$defs"]["phase"]["properties"]["kind"]["enum"])


@pytest.mark.parametrize("base", ["night_harbour", "new"])
@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_checks_and_compiles_once_wired(kind, base):
    doc = night_harbour() if base == "night_harbour" else document.new("fresh", "Fresh")
    before = copy.deepcopy(doc)
    out = document.phase_template(doc, kind)
    assert doc == before, "the document given is left alone"
    assert out["flow"] == before["flow"], "the flow is the page's to wire"
    ph = out["phases"][-1]
    assert ph["kind"] == kind and ph["title"] and ph["objective"] and len(out["phases"]) == len(before["phases"]) + 1
    wire_after_first_phase(out, ph["id"])
    assert document.check(out) == []
    res = compiler.compile_doc(out)
    assert res.ok, res.problems


@pytest.mark.parametrize("kind", KINDS)
def test_the_same_kind_twice_keeps_every_id_unique(kind):
    doc = document.phase_template(document.new("fresh", "Fresh"), kind)
    wire_after_first_phase(doc, doc["phases"][-1]["id"])
    doc = document.phase_template(doc, kind)
    wire_after_first_phase(doc, doc["phases"][-1]["id"])
    ids = [p["id"] for p in doc["phases"]]
    assert len(ids) == len(set(ids)) == 3
    assert document.check(doc) == [] and compiler.compile_doc(doc).ok


def test_suitable_things_are_reused_not_copied():
    doc = night_harbour()
    out = document.phase_template(doc, "chase")
    assert out["phases"][-1]["settings"]["player"] == "player_boat"
    assert len(out["things"]) == len(doc["things"])


def test_an_unknown_kind_is_refused_in_plain_words():
    with pytest.raises(document.VideoModeError) as e:
        document.phase_template(night_harbour(), "pinball")
    assert '"pinball" is not a game kind' in str(e.value)
