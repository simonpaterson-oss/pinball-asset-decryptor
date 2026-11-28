"""Is a folder the user already has a viable extraction of the picked card?

Simon (DragonRR), 2026-11-28: "We have to cater for people who just want to extract a card
and nothing else" - so the Select card tab keeps its card picker and Go to Extract as they
are, and gets a second box under the card: "Already have this card extracted? Select the
folder and PAD will use it if it is viable".  He listed the answers:

- an empty folder: "There is no viable extraction in the folder you selected."
- another game's extraction: "The selected folder contains Deadpool, please select a valid
  folder."
- this card's untouched extraction: what the folder holds, "0 files changed".
- this card's modified extraction: what is changed.

:func:`check` answers which (it reads the folder's own records and fingerprints the card, so
callers keep it off the UI loop); :func:`changes` counts what the project changed, the
Reset dialog's kinds (:mod:`project_reset`).
"""

import os
import time

from . import extract_source

#: the verdicts :func:`check` gives; UNSURE: the folder names this card's file name and
#: size, but nothing could check its content and the card file's date is not the recorded one
NONE, ARCHIVED, OTHER, SOURCE, BUILD = "none", "archived", "other", "source", "build"
UNSURE = "unsure"
VIABLE = (SOURCE, BUILD)


#: ``fn(card, folder)`` -> True / False / None: does the card hold what the folder was
#: extracted from, by content (a manufacturer registers one; Stern's reads the card's files).
_contents_checks = []


def register_contents_check(fn):
    """Simon, 2026-11-28 ("Yes, tighten it"): a folder matched to the card by its file name
    and size alone - every card for a machine is the same size - is checked by content."""
    if fn not in _contents_checks:
        _contents_checks.append(fn)


def hash_match(card, folder, say=None):
    """Simon, 2026-11-28 ("we need to cover all cards"): True / False when the folder's
    record holds the hash of the whole card file it was extracted from (every Extract keeps
    one, any maker: :mod:`card_hash`), ``None`` when it has none (an older extraction).
    *say(text)* is told while a card not read before is being read."""
    from . import card_hash
    want = (extract_source.read_extract_source(folder) or {}).get("card_sha256")
    if not want:
        return None
    if say is not None and not card_hash.cached(card):
        last = [0.0]

        def _progress(done, total):
            now = time.monotonic()
            if now - last[0] >= 0.5 and total:
                last[0] = now
                say("Reading the card to compare it with the folder's record… %d%%"
                    % (100 * done // total))
        say("Reading the card to compare it with the folder's record…")
        got = card_hash.card_sha256(card, _progress)
    else:
        got = card_hash.card_sha256(card)
    if not got:
        return None
    return got == want


def _same_date(card, folder):
    """Is the card file's modified time the one the folder recorded at extraction?
    (Copying a file in Windows keeps its date; another card of that name rarely has it.)"""
    rec = extract_source.read_extract_source(folder) or {}
    try:
        return rec.get("mtime") is not None and int(os.stat(card).st_mtime) == rec.get("mtime")
    except OSError:
        return False


def contents_match(card, folder, say=None):
    """The whole-card hash's answer (:func:`hash_match`), else the first registered check's,
    or ``None`` when none can tell."""
    got = hash_match(card, folder, say)
    if got is not None:
        return got
    for fn in list(_contents_checks):
        try:
            got = fn(card, folder)
        except Exception:                               # noqa: BLE001
            got = None
        if got is not None:
            return bool(got)
    return None


def _has_baseline(folder):
    return bool(folder) and os.path.isfile(os.path.join(folder, ".checksums.md5"))


def _ancestor(path, levels=3):
    """The nearest folder above *path* (up to *levels*) holding an extraction."""
    cur = path
    for _ in range(levels):
        up = os.path.dirname(cur)
        if not up or up == cur:
            return None
        if _has_baseline(up):
            return up
        cur = up
    return None


def resolve(card, folder):
    """The extraction folder *folder* means: itself when it holds one, else the extraction
    of *card* one level down (a parent picked, as "Extract Both" leaves them), else the one
    it sits inside (a subfolder picked, as the Extract tab's Browse… allows)."""
    folder = os.path.normpath(folder)
    if _has_baseline(folder):
        return folder
    try:
        below = extract_source.find_extract_for(card, [folder])
    except Exception:                                   # noqa: BLE001
        below = None
    if below and _has_baseline(below):
        return os.path.normpath(below)
    up = _ancestor(folder)
    return os.path.normpath(up) if up else folder


def check(card, folder, game_of=None, say=None):
    """What *folder* holds for *card*: ``{"kind", "folder", "game", "source_name",
    "extracted"}``.

    ``kind`` is :data:`NONE` (no extraction), :data:`ARCHIVED` (a project whose extraction
    was archived), :data:`OTHER` (another card's: ``game`` / ``source_name`` say whose),
    :data:`SOURCE` (extracted from this card) or :data:`BUILD` (this card was built from
    it).  ``folder`` is the extraction folder itself (:func:`resolve`).  *game_of(folder)*
    names the folder's game (the "This project" card's caption); optional.  *say(text)* is
    told what is happening while the card is read (:func:`hash_match`)."""
    out = {"kind": NONE, "folder": "", "game": "", "source_name": "", "extracted": ""}
    if not folder or not os.path.isdir(folder):
        return out
    folder = resolve(card, folder)
    out["folder"] = folder
    if not _has_baseline(folder):
        return out
    rec = extract_source.read_extract_source(folder) or {}
    out["source_name"] = str(rec.get("input_name") or "")
    try:
        import time
        out["extracted"] = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(
            os.path.join(folder, extract_source.SIDE_CAR))))
    except OSError:
        pass
    if game_of is not None:
        try:
            out["game"] = game_of(folder) or ""
        except Exception:                               # noqa: BLE001
            out["game"] = ""
    try:
        from . import project_file
        if project_file.has_anchor(folder) and project_file.load_anchor(folder).get("archived"):
            out["kind"] = ARCHIVED
            return out
    except Exception:                                   # noqa: BLE001
        pass
    try:
        rel = extract_source.card_relation(card, folder, measure=True)
    except Exception:                                   # noqa: BLE001
        rel = None
    kind = (rel or {}).get("kind")
    out["kind"] = kind if kind in VIABLE else OTHER
    if kind == SOURCE and not _by_fingerprint(card, folder):
        # matched by the folder's record of the card's name and size: check the content
        got = contents_match(card, folder, say)
        if got is False:
            out["kind"] = OTHER
            out["same_name"] = True
        elif got is None and not _same_date(card, folder):
            # nothing could read the content (an extraction from before the hash, a maker
            # without a check of its own), and the date does not back the name up
            out["kind"] = UNSURE
    elif kind not in VIABLE and _same_size(card, rec) and hash_match(card, folder, say):
        # the very card file under another name (renamed, then its date changed)
        out["kind"] = SOURCE
    return out


def _same_size(card, rec):
    try:
        return rec.get("size") is not None and os.path.getsize(card) == rec.get("size")
    except OSError:
        return False


def _by_fingerprint(card, folder):
    """Did the project's own history (PAD-427 lineage) place the card by its fingerprint?"""
    try:
        hit = extract_source._lineage_hit(folder, card, measure=True)
    except Exception:                                   # noqa: BLE001
        hit = None
    return bool(hit) and hit[0] in ("source", "rev")


def changes(folder):
    """``[(label, n), ...]`` of what the project in *folder* changed since it was extracted,
    the Reset dialog's kinds with a count (none: ``[]``)."""
    from . import project_reset as PR
    from .checksums import all_changed
    try:
        changed = all_changed(folder, quick=True)
    except Exception:                                   # noqa: BLE001
        changed = None
    counts = PR.counts(folder, changed)
    return [(PR.LABELS[k], int(counts.get(k) or 0)) for k in PR.KEYS if counts.get(k)]


def message(verdict, card_caption=""):
    """The line the Select card tab shows for *verdict* (``{"kind", ...}``, :func:`check`)."""
    kind = verdict.get("kind")
    game = verdict.get("game") or ""
    name = verdict.get("source_name") or ""
    if kind == NONE:
        return "There is no viable extraction in the folder you selected."
    if kind == ARCHIVED:
        return ("The selected folder is an archived project: its extraction was removed. "
                "Please select another folder, or extract into it again.")
    if kind == UNSURE:
        return ("The selected folder was extracted from a card with this card's file name and "
                "size (%s), but PAD cannot confirm it is this card: the card file's date is not "
                "the one recorded when it was extracted. Extract this card again to be sure."
                % name)
    if kind == OTHER:
        if verdict.get("same_name"):
            return ("The selected folder was extracted from a card with this card's file name "
                    "and size (%s), but its files are not this card's. Please select a valid "
                    "folder." % name)
        if not name:
            return ("The selected folder holds an extraction, but it does not say which card "
                    "it came from. Please select a valid folder.")
        whose = "%s (%s)" % (game, name) if game else name
        # "Godzilla" (the folder's) and "Godzilla LE" (the card's chip) are one game
        a, b = (card_caption or "").lower(), game.lower()
        same = bool(a and b) and (a == b or a.startswith(b + " ") or b.startswith(a + " "))
        return ("The selected folder contains %s%s. Please select a valid folder."
                % (whose, ", a different card of the same game" if same else ""))
    what = game or name or "this card"
    if kind == BUILD:
        return "This card was built from the project in this folder (%s)." % what
    when = verdict.get("extracted")
    return "The selected folder contains %s%s." % (what, ", extracted " + when if when else "")


def changes_line(rows):
    """``"0 changes since it was extracted"`` or ``"Changed since it was extracted: ..."``."""
    if not rows:
        return "0 changes since it was extracted."
    def _one(label, n):
        label = label[:1].lower() + label[1:]
        if n == 1 and label.endswith("s"):          # "1 modes" (Simon's screenshot)
            label = label[:-1]
        return "%d %s" % (n, label)
    return "Changed since it was extracted: " + ", ".join(_one(l, n) for l, n in rows) + "."
