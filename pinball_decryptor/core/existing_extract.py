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

from . import extract_source

#: the verdicts :func:`check` gives
NONE, ARCHIVED, OTHER, SOURCE, BUILD = "none", "archived", "other", "source", "build"
VIABLE = (SOURCE, BUILD)


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


def check(card, folder, game_of=None):
    """What *folder* holds for *card*: ``{"kind", "folder", "game", "source_name",
    "extracted"}``.

    ``kind`` is :data:`NONE` (no extraction), :data:`ARCHIVED` (a project whose extraction
    was archived), :data:`OTHER` (another card's: ``game`` / ``source_name`` say whose),
    :data:`SOURCE` (extracted from this card) or :data:`BUILD` (this card was built from
    it).  ``folder`` is the extraction folder itself (:func:`resolve`).  *game_of(folder)*
    names the folder's game (the "This project" card's caption); optional."""
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
    return out


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
    if kind == OTHER:
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
