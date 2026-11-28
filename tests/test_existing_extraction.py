"""The Select card tab's "Existing extraction" box (Simon, DragonRR, 2026-11-28): "Already
have this card extracted? Select the folder and PAD will use it if it is viable".  An empty
folder, another card's extraction, this card's untouched extraction and a modified one each
get their own answer; a viable folder is opened as the project."""

import os

from pinball_decryptor.core import existing_extract as EE
from pinball_decryptor.core import extract_source

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _card(tmp_path, name="godzilla.raw", size=4096):
    p = tmp_path / name
    p.write_bytes(b"\0" * size)
    return str(p)


def _extract(folder, card):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, ".checksums.md5"), "w") as f:
        f.write("d41d8cd98f00b204e9800998ecf8427e *sound/a.wav\n")
    extract_source.write_extract_source(folder, card)
    return folder


def test_empty_folder_has_no_viable_extraction(tmp_path):
    card = _card(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    v = EE.check(card, str(empty))
    assert v["kind"] == EE.NONE
    assert EE.message(v) == "There is no viable extraction in the folder you selected."


def test_missing_folder_is_none(tmp_path):
    assert EE.check(_card(tmp_path), str(tmp_path / "gone"))["kind"] == EE.NONE


def test_this_cards_extraction_is_viable(tmp_path):
    card = _card(tmp_path)
    folder = _extract(str(tmp_path / "proj"), card)
    v = EE.check(card, folder, lambda f: "Godzilla LE 1.16")
    assert v["kind"] == EE.SOURCE and v["folder"] == os.path.normpath(folder)
    msg = EE.message(v)
    assert msg.startswith("The selected folder contains Godzilla LE 1.16, extracted ")


def test_another_cards_extraction_names_its_game(tmp_path):
    card = _card(tmp_path)
    other = _card(tmp_path, "deadpool.raw", 8192)
    folder = _extract(str(tmp_path / "dp"), other)
    v = EE.check(card, folder, lambda f: "Deadpool")
    assert v["kind"] == EE.OTHER
    assert EE.message(v, "Godzilla LE 1.16") == (
        "The selected folder contains Deadpool (deadpool.raw). Please select a valid folder.")


def test_another_card_of_the_same_game_says_so(tmp_path):
    card = _card(tmp_path)
    heisei = _card(tmp_path, "heisei.raw", 8192)
    folder = _extract(str(tmp_path / "h"), heisei)
    v = EE.check(card, folder, lambda f: "Godzilla LE 1.16")
    assert v["kind"] == EE.OTHER
    assert "a different card of the same game" in EE.message(v, "Godzilla LE 1.16")


def test_extraction_without_a_source_record(tmp_path):
    card = _card(tmp_path)
    folder = tmp_path / "old"
    folder.mkdir()
    (folder / ".checksums.md5").write_text("")
    v = EE.check(card, str(folder))
    assert v["kind"] == EE.OTHER
    assert "does not say which card" in EE.message(v)


def test_parent_or_subfolder_finds_the_extraction(tmp_path):
    card = _card(tmp_path)
    folder = _extract(str(tmp_path / "parent" / "proj"), card)
    os.makedirs(os.path.join(folder, "sound"))
    assert EE.check(card, str(tmp_path / "parent"))["folder"] == os.path.normpath(folder)
    assert EE.check(card, os.path.join(folder, "sound"))["folder"] == os.path.normpath(folder)


def test_changes_line():
    assert EE.changes_line([]) == "0 changes since it was extracted."
    assert EE.changes_line([("Replaced images", 12), ("Scenes edits", 3)]) == (
        "Changed since it was extracted: 12 replaced images, 3 scenes edits.")


def test_changes_counts_an_untouched_extraction_as_none(tmp_path):
    card = _card(tmp_path)
    folder = _extract(str(tmp_path / "proj"), card)
    assert EE.changes(folder) == []


def test_select_card_tab_has_the_box():
    js = open(os.path.join(ROOT, "pinball_decryptor", "webui", "static", "js", "tabs",
                           "card.js"), encoding="utf-8").read()
    assert "Already have this card extracted?" in js
    assert "Select the folder and PAD will use it if it is viable" in js
    assert 'call("extract.browse_existing")' in js
    assert 'call("extract.check_existing"' in js
    assert "Viable: PAD is using this extraction" in js
    # the card picker and Go to Extract are unchanged (the tutorial videos)
    assert "Go to Extract" in js


def test_extract_service_rpcs():
    from pinball_decryptor.webui.tabs import extract as X
    for name in ("browse_existing", "check_existing"):
        assert getattr(getattr(X.ExtractTab, name), "_rpc", None) or callable(
            getattr(X.ExtractTab, name))
