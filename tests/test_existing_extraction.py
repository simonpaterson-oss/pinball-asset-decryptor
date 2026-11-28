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
    # Simon's screenshot: the folder said "Godzilla", the card's chip "Godzilla LE"
    v["game"] = "Godzilla"
    assert "a different card of the same game" in EE.message(v, "Godzilla LE")
    v["game"] = "Godzilla 2"
    assert "same game" not in EE.message(v, "Godzilla LE")


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
    assert EE.changes_line([("Replaced videos", 1)]) == (
        "Changed since it was extracted: 1 replaced video.")


def test_box_checks_only_a_typed_path():
    # Simon, 2026-11-28: a Browse… pick went back to the earlier typed path on blur
    js = open(os.path.join(ROOT, "pinball_decryptor", "webui", "static", "js", "tabs",
                           "card.js"), encoding="utf-8").read()
    box = js[js.index("function ExistingBox"):js.index("// ------------------------------------------------------------ the glass")]
    assert "onBlur" not in box and "onCommit" not in box
    assert "useEffect(() => { setTyped(null); }, [shown]);" in box


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


# -- "Yes, tighten it" (Simon): a name-and-size match is checked by content -----------

def test_same_name_and_size_but_other_contents_is_not_viable(tmp_path, monkeypatch):
    card = _card(tmp_path)
    folder = _extract(str(tmp_path / "proj"), card)
    # the folder's record names a card at another path with this card's name and size
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    twin = str(other_dir / "godzilla.raw")
    open(twin, "wb").write(b"\1" * 4096)
    monkeypatch.setattr(EE, "_contents_checks", [lambda c, f: os.path.samefile(c, card)])
    assert EE.check(card, folder)["kind"] == EE.SOURCE
    v = EE.check(twin, folder)
    assert v["kind"] == EE.OTHER and v.get("same_name")
    assert "file name and size" in EE.message(v)


def test_no_contents_check_keeps_the_name_and_size_match(tmp_path, monkeypatch):
    card = _card(tmp_path)
    folder = _extract(str(tmp_path / "proj"), card)
    monkeypatch.setattr(EE, "_contents_checks", [lambda c, f: None])
    assert EE.check(card, folder)["kind"] == EE.SOURCE


def test_stern_registers_its_contents_check():
    import pinball_decryptor.plugins.stern.manufacturer  # noqa: F401
    from pinball_decryptor.plugins.stern.stock_prints import card_matches_project
    assert card_matches_project in EE._contents_checks


def _cards_dir():
    d = os.environ.get("PAD494_CARDS") or ""
    return d if os.path.isdir(d) else ""


def test_real_card_contents(tmp_path):
    import pytest
    d = _cards_dir()
    card = os.path.join(d, "godzilla_le-1_16_0_spike2.Release.8G.sdcard.raw") if d else ""
    folder = os.path.join(d, "Godzilla PREMIUM ORIGINAL V1.16 EXTRACTION") if d else ""
    if not (os.path.isfile(card) and os.path.isfile(os.path.join(folder, ".checksums.md5"))):
        pytest.skip("Godzilla 1.16 card and its extraction not found (PAD494_CARDS)")
    from pinball_decryptor.plugins.stern.stock_prints import card_matches_project
    assert card_matches_project(card, folder) is True


# -- "we need to cover all cards" (Simon): a hash of the whole card file, any maker ------

import pytest

from pinball_decryptor.core import card_hash


@pytest.fixture(autouse=True)
def _own_hash_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(card_hash, "HASH_CACHE", str(tmp_path / "card_hashes.json"))


def _hashed(folder, card):
    _extract(folder, card)
    extract_source.amend_extract_source(folder, card_sha256=card_hash.card_sha256(card))
    return folder


def test_card_hash_is_the_files_sha256_and_cached(tmp_path):
    import hashlib
    card = _card(tmp_path)
    want = hashlib.sha256(open(card, "rb").read()).hexdigest()
    assert card_hash.cached(card) is None
    assert card_hash.card_sha256(card) == want
    assert card_hash.cached(card) == want
    # a changed file is read again
    with open(card, "r+b") as f:
        f.write(b"\1")
    os.utime(card, ns=(1, 1))
    assert card_hash.cached(card) is None
    assert card_hash.card_sha256(card) != want


def test_recorded_hash_confirms_the_card(tmp_path, monkeypatch):
    monkeypatch.setattr(EE, "_contents_checks", [])
    card = _card(tmp_path)
    folder = _hashed(str(tmp_path / "proj"), card)
    assert EE.check(card, folder)["kind"] == EE.SOURCE


def test_recorded_hash_refuses_a_twin_of_the_same_name_and_size(tmp_path, monkeypatch):
    monkeypatch.setattr(EE, "_contents_checks", [])
    card = _card(tmp_path)
    folder = _hashed(str(tmp_path / "proj"), card)
    (tmp_path / "other").mkdir()
    twin = str(tmp_path / "other" / "godzilla.raw")
    open(twin, "wb").write(b"\1" * 4096)
    v = EE.check(twin, folder)
    assert v["kind"] == EE.OTHER and v.get("same_name")


def test_the_hash_wins_over_a_makers_check(tmp_path, monkeypatch):
    monkeypatch.setattr(EE, "_contents_checks", [lambda c, f: True])
    card = _card(tmp_path)
    folder = _hashed(str(tmp_path / "proj"), card)
    (tmp_path / "other").mkdir()
    twin = str(tmp_path / "other" / "godzilla.raw")
    open(twin, "wb").write(b"\1" * 4096)
    assert EE.check(twin, folder)["kind"] == EE.OTHER


def test_renamed_card_with_a_new_date_is_found_by_its_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(EE, "_contents_checks", [])
    card = _card(tmp_path)
    folder = _hashed(str(tmp_path / "proj"), card)
    renamed = str(tmp_path / "my godzilla.raw")
    os.replace(card, renamed)
    os.utime(renamed, (1000000, 1000000))
    assert EE.check(renamed, folder)["kind"] == EE.SOURCE


def test_older_extraction_without_a_hash_needs_the_recorded_date(tmp_path, monkeypatch):
    monkeypatch.setattr(EE, "_contents_checks", [])
    card = _card(tmp_path)
    folder = _extract(str(tmp_path / "proj"), card)
    assert EE.check(card, folder)["kind"] == EE.SOURCE          # same date: a copy
    os.utime(card, (1000000, 1000000))
    v = EE.check(card, folder)
    assert v["kind"] == EE.UNSURE and v["kind"] not in EE.VIABLE
    assert "cannot confirm it is this card" in EE.message(v)
    # a maker's own check still answers for it
    monkeypatch.setattr(EE, "_contents_checks", [lambda c, f: True])
    assert EE.check(card, folder)["kind"] == EE.SOURCE


def test_the_box_is_told_while_the_card_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(EE, "_contents_checks", [])
    card = _card(tmp_path)
    folder = _hashed(str(tmp_path / "proj"), card)
    open(card, "r+b").write(b"\0")          # same bytes, but no longer cached
    os.utime(card, (1000000, 1000000))
    said = []
    assert EE.check(card, folder, say=said.append)["kind"] == EE.SOURCE
    assert said and said[0].startswith("Reading the card to compare")
    said.clear()
    EE.check(card, folder, say=said.append)                     # cached now: nothing read
    assert said == []


def test_extract_records_the_card_hash():
    src = open(os.path.join(ROOT, "pinball_decryptor", "app.py"), encoding="utf-8").read()
    body = src[src.index("def _record_extract_facts"):src.index("def _port_sub_runner")]
    assert "card_hash.card_sha256(in_path)" in body
    assert "amend_extract_source(out_path, card_sha256=digest)" in body


def test_open_project_is_checked_the_same_way():
    src = open(os.path.join(ROOT, "pinball_decryptor", "webui", "tabs", "extract.py"),
               encoding="utf-8").read()
    body = src[src.index("def _existing_follow"):src.index("def _open_folder")]
    assert "self._start_existing_check(card" in body
    js = open(os.path.join(ROOT, "pinball_decryptor", "webui", "static", "js", "tabs",
                           "card.js"), encoding="utf-8").read()
    assert "Not confirmed: the open project may not be this card's extraction" in js
