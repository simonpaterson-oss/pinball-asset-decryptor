"""A video mode document: <project>/modes/<slug>/video_mode.json (PAD-1654).

The format is written down once, in video_mode.schema.json beside this file;
docs/plans/video_mode_maker.md explains each field.  This module is the one
reader the app has:

    doc = load(path)            # read, migrate an older format, check; raises VideoModeError
    problems = check(doc)       # every problem, in plain words, with its place

check() runs the schema (a small validator for the JSON Schema keywords the
schema uses, so the app needs no extra package) and then what a schema cannot
say: every id is unique, every reference names something that exists, the
flow starts somewhere real, reaches an end from every card, and every card is
reachable.

Versions.  "format" is a whole number.  Any change to what a file may hold
bumps it, even an added optional field (the schema refuses unknown keys, so an
older PAD would refuse such a file anyway, and a plain refusal beats a silent
drop).  A newer PAD reads an older file by running MIGRATIONS[n] for each step
n -> n+1 in turn: pure functions, never touching the disk, each with a frozen
fixture under tests/data/video_mode/format_<n>.json that is kept for good.  An
older PAD refuses a newer file in plain words and never writes it.
"""

import copy
import json
import os
import re

FORMAT = 1
KIND = "pad-video-mode"
FILE_NAME = "video_mode.json"
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "video_mode.schema.json")

# n -> function(doc) returning the doc in format n+1.  Empty while format 1 is the only one.
MIGRATIONS = {}


class VideoModeError(ValueError):
    """A document that cannot be used; .problems holds every reason."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems) if self.problems else "not a video mode")


_schema = None


def schema():
    global _schema
    if _schema is None:
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            _schema = json.load(f)
    return _schema


# ---- places ----------------------------------------------------------------
def place(path, doc=None):
    """'phases[1] "boss" > settings > weak_points[0] > r' from a path list.

    A list item that has an id is named by it, so a message points at the
    thing the author sees rather than at a count."""
    out = []
    node = doc
    for step in path:
        if isinstance(step, int):
            label = "[%d]" % step
            item = node[step] if isinstance(node, list) and step < len(node) else None
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                label += ' "%s"' % item["id"]
            out[-1:] = [(out[-1] if out else "") + label]
            node = item
        else:
            out.append(str(step))
            node = node.get(step) if isinstance(node, dict) else None
    return " > ".join(out) if out else "the document"


# ---- the schema subset -------------------------------------------------------
_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}
_IGNORED = {"$schema", "$id", "$defs", "$comment", "title", "description", "default", "examples"}
KNOWN_KEYWORDS = _IGNORED | {
    "$ref", "type", "enum", "const", "required", "properties", "additionalProperties",
    "items", "minItems", "maxItems", "minimum", "maximum", "exclusiveMinimum",
    "minLength", "maxLength", "pattern", "allOf", "if", "then",
}


def _resolve(ref):
    if not ref.startswith("#/"):
        raise ValueError("only local references: %s" % ref)
    node = schema()
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _shown(v):
    s = json.dumps(v)
    return s if len(s) <= 40 else s[:37] + "..."


def _validate(value, sch, path, out):
    if "$ref" in sch:
        _validate(value, _resolve(sch["$ref"]), path, out)
    for k in sch:
        if k not in KNOWN_KEYWORDS:
            raise ValueError("schema keyword %r is not understood by this validator" % k)
    if "type" in sch:
        kinds = sch["type"] if isinstance(sch["type"], list) else [sch["type"]]
        if not any(_TYPES[t](value) for t in kinds):
            out.append((path, "should be %s (it is %s)" % (" or ".join(kinds), _shown(value))))
            return
    if "const" in sch and value != sch["const"]:
        out.append((path, "must be %s (it is %s)" % (_shown(sch["const"]), _shown(value))))
    if "enum" in sch and value not in sch["enum"]:
        out.append((path, "must be one of %s (it is %s)" % (", ".join(_shown(e) for e in sch["enum"]), _shown(value))))
    if _TYPES["number"](value):
        if "minimum" in sch and value < sch["minimum"]:
            out.append((path, "must be at least %s (it is %s)" % (sch["minimum"], value)))
        if "maximum" in sch and value > sch["maximum"]:
            out.append((path, "must be at most %s (it is %s)" % (sch["maximum"], value)))
        if "exclusiveMinimum" in sch and value <= sch["exclusiveMinimum"]:
            out.append((path, "must be more than %s (it is %s)" % (sch["exclusiveMinimum"], value)))
    if isinstance(value, str):
        if "minLength" in sch and len(value) < sch["minLength"]:
            out.append((path, "must not be empty" if sch["minLength"] == 1 else "is too short"))
        if "maxLength" in sch and len(value) > sch["maxLength"]:
            out.append((path, "is longer than %d characters" % sch["maxLength"]))
        if "pattern" in sch and not re.search(sch["pattern"], value):
            out.append((path, "%s is not allowed here" % _shown(value)))
    if isinstance(value, list):
        if "minItems" in sch and len(value) < sch["minItems"]:
            out.append((path, "needs at least %d" % sch["minItems"]))
        if "maxItems" in sch and len(value) > sch["maxItems"]:
            out.append((path, "holds %d, the most is %d" % (len(value), sch["maxItems"])))
        if "items" in sch:
            for i, item in enumerate(value):
                _validate(item, sch["items"], path + [i], out)
    if isinstance(value, dict):
        for k in sch.get("required", []):
            if k not in value:
                out.append((path, "is missing %s" % k))
        props = sch.get("properties", {})
        for k, v in value.items():
            if k in props:
                _validate(v, props[k], path + [k], out)
            elif sch.get("additionalProperties") is False:
                out.append((path + [k], "is not a field this format knows"))
            elif isinstance(sch.get("additionalProperties"), dict):
                _validate(v, sch["additionalProperties"], path + [k], out)
    for sub in sch.get("allOf", []):
        _validate(value, sub, path, out)
    if "if" in sch:
        probe = []
        _validate(value, sch["if"], path, probe)
        if not probe and "then" in sch:
            _validate(value, sch["then"], path, out)


def schema_problems(doc):
    out = []
    _validate(doc, schema(), [], out)
    return [(p, m) for p, m in out]


# ---- what a schema cannot say -----------------------------------------------
# Where references live and what they must name.  Kinds are the lists ids are
# collected from: 'picture', 'sound', 'music' (a sound whose role is music),
# 'font', 'clip', 'value', 'thing', 'phase', 'card'.
_SETTING_REFS = {
    "chase": {"player": "thing", "shot": "thing"},
    "thrust": {"player": "thing", "shot": "thing"},
    "aim": {"sight": "thing", "heat": "value"},
    "boss": {"boss": "thing", "sight": "thing"},
    "mash": {"meter": "value"},
    "alternate": {"meter": "value"},
    "tug": {"meter": "value"},
    "rhythm": {"music": "music"},
    "defend": {"enemy": "thing"},
    "catch": {"catcher": "thing"},
    "runner": {"runner": "thing"},
    "lander": {"ship": "thing"},
    "route": {"vehicle": "thing"},
}
_PER_BUILTIN = ("time_left_s", "health_left", "ammo_left")


def _ids(doc):
    """{kind: {id: path}} and a list of duplicate problems.

    An id is unique within its own list (a picture and the thing drawn with
    it may share a name), except that things and values share one namespace:
    a win condition's "of" and a rule's target may name either."""
    seen, dupes, by_kind = {}, [], {}

    def add(kind, item, path):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            return
        i = item["id"]
        space = ("actor" if kind in ("thing", "value") else kind, i)
        if space in seen:
            dupes.append((path + ["id"], 'the id "%s" is already used at %s' % (i, place(seen[space], doc))))
            return
        seen[space] = path
        by_kind.setdefault(kind, {})[i] = path
        if kind == "sound" and item.get("role") == "music":
            by_kind.setdefault("music", {})[i] = path

    assets = doc.get("assets") or {}
    for key, kind in (("pictures", "picture"), ("sounds", "sound"), ("fonts", "font"), ("clips", "clip")):
        for n, item in enumerate(assets.get(key) or []):
            add(kind, item, ["assets", key, n])
    for key, kind in (("values", "value"), ("things", "thing"), ("phases", "phase"), ("hud", "hud")):
        for n, item in enumerate(doc.get(key) or []):
            add(kind, item, [key, n])
    for n, item in enumerate((doc.get("flow") or {}).get("cards") or []):
        add("card", item, ["flow", "cards", n])
    return by_kind, dupes


def reference_problems(doc):
    by_kind, out = _ids(doc)

    def need(value, kind, path, what=None):
        if value is None or not isinstance(value, str):
            return
        if value not in by_kind.get(kind, {}):
            names = {"music": "music sound", "card": "flow card"}
            out.append((path, 'names "%s", but there is no %s with that id' % (value, what or names.get(kind, kind))))

    pictures = {p.get("id"): p for p in (doc.get("assets") or {}).get("pictures") or [] if isinstance(p, dict)}
    for n, pic in enumerate((doc.get("assets") or {}).get("pictures") or []):
        if not isinstance(pic, dict):
            continue
        count = pic.get("frames", 1)
        for a, anim in enumerate(pic.get("animations") or []):
            for f, frame in enumerate(anim.get("frames") or [] if isinstance(anim, dict) else []):
                if isinstance(frame, int) and isinstance(count, int) and frame >= count:
                    out.append((["assets", "pictures", n, "animations", a, "frames", f],
                                "frame %d is past the picture's %d frame%s" % (frame, count, "" if count == 1 else "s")))
    for n, thing in enumerate(doc.get("things") or []):
        if not isinstance(thing, dict):
            continue
        need(thing.get("picture"), "picture", ["things", n, "picture"])
        anim = thing.get("animation")
        pic = pictures.get(thing.get("picture"))
        if isinstance(anim, str) and isinstance(pic, dict):
            if anim not in {a.get("id") for a in pic.get("animations") or [] if isinstance(a, dict)}:
                out.append((["things", n, "animation"], 'names "%s", but the picture "%s" has no animation with that id' % (anim, pic.get("id"))))
        mover = thing.get("mover")
        if isinstance(mover, dict):
            need(mover.get("target"), "thing", ["things", n, "mover", "target"])
    for n, phase in enumerate(doc.get("phases") or []):
        if not isinstance(phase, dict):
            continue
        base = ["phases", n]
        need(phase.get("music"), "music", base + ["music"])
        for i, layer in enumerate(phase.get("background") or []):
            if isinstance(layer, dict):
                need(layer.get("picture"), "picture", base + ["background", i, "picture"])
        settings = phase.get("settings") if isinstance(phase.get("settings"), dict) else {}
        for key, kind in _SETTING_REFS.get(phase.get("kind"), {}).items():
            need(settings.get(key), kind, base + ["settings", key])
        if phase.get("kind") == "boss":
            for i, att in enumerate(settings.get("attacks") or []):
                if isinstance(att, dict):
                    need(att.get("thing"), "thing", base + ["settings", "attacks", i, "thing"])
        for key in ("place", "spawns"):
            for i, item in enumerate(phase.get(key) or []):
                if isinstance(item, dict):
                    need(item.get("thing"), "thing", base + [key, i, "thing"])
        for key in ("win", "lose"):
            for i, cond in enumerate(phase.get(key) or []):
                if isinstance(cond, dict) and cond.get("of") is not None:
                    of = cond["of"]
                    if not any(of in by_kind.get(k, {}) for k in ("thing", "value")):
                        out.append((base + [key, i, "of"], 'names "%s", but there is no thing or value with that id' % of))
    for n, part in enumerate(doc.get("hud") or []):
        if not isinstance(part, dict):
            continue
        need(part.get("value"), "value", ["hud", n, "value"])
        need(part.get("font"), "font", ["hud", n, "font"])
        for i, ph in enumerate(part.get("phases") or []):
            need(ph, "phase", ["hud", n, "phases", i])
    for n, cue in enumerate(doc.get("cues") or []):
        if isinstance(cue, dict):
            need(cue.get("sound"), "sound", ["cues", n, "sound"])
    for n, award in enumerate((doc.get("pays") or {}).get("awards") or []):
        if isinstance(award, dict):
            need(award.get("phase"), "phase", ["pays", "awards", n, "phase"])
            if award.get("when") == "phase_won" and "phase" not in award:
                out.append((["pays", "awards", n], "pays when a phase is won, but does not say which phase"))
            if award.get("when") == "collected":
                if "of" not in award:
                    out.append((["pays", "awards", n], "pays when something is collected, but does not say what"))
                need(award.get("of"), "thing", ["pays", "awards", n, "of"])
            per = award.get("per")
            if isinstance(per, str) and per not in _PER_BUILTIN:
                need(per, "value", ["pays", "awards", n, "per"])

    flow = doc.get("flow") or {}
    cards = [c for c in flow.get("cards") or [] if isinstance(c, dict)]
    by_id = {c.get("id"): c for c in cards}
    need(flow.get("start"), "card", ["flow", "start"])
    for n, card in enumerate(flow.get("cards") or []):
        if not isinstance(card, dict):
            continue
        p = ["flow", "cards", n]
        need(card.get("clip"), "clip", p + ["clip"])
        need(card.get("phase"), "phase", p + ["phase"])
        for key in ("then", "won", "lost"):
            need(card.get(key), "card", p + [key])
            if card.get(key) == card.get("id") and card.get("card") == "clip":
                out.append((p + [key], "a clip cannot lead to itself"))
    if flow.get("start") in by_id and not out:
        # every card reachable from the start, and an end reachable from every card
        nexts = {c["id"]: [c[k] for k in ("then", "won", "lost") if c.get(k) in by_id] for c in cards if "id" in c}
        seen, todo = set(), [flow["start"]]
        while todo:
            c = todo.pop()
            if c not in seen:
                seen.add(c)
                todo.extend(nexts.get(c, []))
        for n, card in enumerate(flow.get("cards") or []):
            if isinstance(card, dict) and card.get("id") not in seen:
                out.append((["flow", "cards", n], "cannot be reached from the start card"))
        ends = {c["id"] for c in cards if c.get("card") == "end"}
        if not ends:
            out.append((["flow"], "has no end card, so the video mode could never finish"))
        else:
            good = set(ends)
            changed = True
            while changed:
                changed = False
                for c, nx in nexts.items():
                    if c not in good and any(x in good for x in nx):
                        good.add(c)
                        changed = True
            for n, card in enumerate(flow.get("cards") or []):
                if isinstance(card, dict) and card.get("id") in seen and card.get("id") not in good:
                    out.append((["flow", "cards", n], "loops for ever: no way from here reaches an end card"))
        if "won" not in {c.get("outcome") for c in cards if c.get("card") == "end"}:
            out.append((["flow"], "has no end card for a win"))
    return out


# ---- the API ------------------------------------------------------------------
def migrate(doc):
    """Bring an older document up to FORMAT.  Returns a new dict."""
    if not isinstance(doc, dict):
        raise VideoModeError(["a video mode file holds a JSON object"])
    if doc.get("kind") != KIND:
        raise VideoModeError(["this is not a video mode file (its kind is %s)" % _shown(doc.get("kind"))])
    fmt = doc.get("format")
    if not isinstance(fmt, int) or isinstance(fmt, bool) or fmt < 1:
        raise VideoModeError(["the file's format number is missing or wrong (%s)" % _shown(fmt)])
    if fmt > FORMAT:
        raise VideoModeError(["this video mode was saved by a newer PAD (format %d; this PAD reads up to %d). Update PAD to open it." % (fmt, FORMAT)])
    doc = copy.deepcopy(doc)
    while doc["format"] < FORMAT:
        step = MIGRATIONS[doc["format"]]
        doc = step(doc)
    return doc


def check(doc):
    """Every problem with a current-format document, as 'place: what' strings."""
    probs = schema_problems(doc)
    if not probs:
        probs = reference_problems(doc)
    return ["%s: %s" % (place(p, doc), m) for p, m in probs]


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise VideoModeError(["%s is not valid JSON (line %d, column %d: %s)" % (os.path.basename(path), e.lineno, e.colno, e.msg)])
    doc = migrate(raw)
    probs = check(doc)
    if probs:
        raise VideoModeError(probs)
    return doc


def dumps(doc):
    """The file's text: two-space indent, keys in the order given, a final newline."""
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def save(path, doc):
    """Check ``doc`` and write it to ``path`` (a whole file, swapped in at once). A document
    with problems is refused with every one of them and nothing is written."""
    probs = check(doc)
    if probs:
        raise VideoModeError(probs)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(dumps(doc))
    os.replace(tmp, path)
    return path


def new(slug, title):
    """The smallest document that checks: one empty phase, won after 20 seconds."""
    return {
        "format": FORMAT, "kind": KIND, "id": slug, "title": title[:40],
        "stage": {"width": 1360, "height": 768, "steps_per_second": 60, "background": "#000000"},
        "assets": {"pictures": []}, "things": [],
        "phases": [{"id": "main", "kind": "custom", "settings": {}, "win": [{"when": "survive_s", "value": 20}],
                    "lose": [{"when": "time_up"}]}],
        "flow": {"start": "c_main", "cards": [
            {"id": "c_main", "card": "phase", "phase": "main", "won": "e_won", "lost": "e_lost"},
            {"id": "e_won", "card": "end", "outcome": "won"},
            {"id": "e_lost", "card": "end", "outcome": "lost"}]},
    }
