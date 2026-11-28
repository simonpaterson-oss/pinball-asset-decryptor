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

FORMAT = 4
KIND = "pad-video-mode"
FILE_NAME = "video_mode.json"
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "video_mode.schema.json")



def _format_1_to_2(doc):
    """PAD-1667: sounds gained fade_s, tempo_bpm, beat_offset_s and beats_per_bar, and a rhythm phase's
    tempo_bpm became optional (its music's own).  Nothing a format 1 file holds changes: every field it has
    means what it meant, and the new ones take their defaults when absent (a 1 s fade, no beat grid)."""
    doc["format"] = 2
    return doc


def _format_2_to_3(doc):
    """PAD-1664: a phase gained tracks (keyframed motion of its placed things) and sound_track (sounds at set
    times). A format 2 file has neither, and plays the same without them."""
    doc["format"] = 3
    return doc


def _format_3_to_4(doc):
    """PAD-1666: the HUD's looks and text styles (outline, shadow, gradient, danger colours and zones, count-up, pop),
    multiplier and pop-up parts, particles, a thing's trail, the style's new switches and amounts, and combo.  Nothing
    a format 3 file holds changes meaning; absent fields keep what format 3 played (no multiplier, the old bursts
    as presets)."""
    doc["format"] = 4
    return doc


# n -> function(doc) returning the doc in format n+1.
MIGRATIONS = {1: _format_1_to_2, 2: _format_2_to_3, 3: _format_3_to_4}

TRACK_NEEDS = {"motion": ("x", "y"), "scale": ("v",), "turn": ("v",), "alpha": ("v",), "tint": ("tint",)}
TRACK_RANGE = {"scale": (0, 16), "turn": (-3600, 3600), "alpha": (0, 1)}


def track_problems(phase, base):
    """PAD-1664: a phase's tracks and sound track, beyond what the schema says."""
    out = []
    places = phase.get("place") or []
    seen = {}
    for n, tr in enumerate(phase.get("tracks") or []):
        if not isinstance(tr, dict):
            continue
        p = base + ["tracks", n]
        pl, prop = tr.get("place"), tr.get("prop")
        if isinstance(pl, int) and pl >= len(places):
            out.append((p + ["place"], "names place %d, but the phase places %d thing%s" % (pl, len(places), "" if len(places) == 1 else "s")))
        if (pl, prop) in seen:
            out.append((p, "is a second %s track for place %d (track %d is the first)" % (prop, pl, seen[(pl, prop)])))
        seen.setdefault((pl, prop), n)
        last = None
        for k, key in enumerate(tr.get("keys") or []):
            if not isinstance(key, dict):
                continue
            kp = p + ["keys", k]
            at = key.get("at_s")
            if isinstance(at, (int, float)) and last is not None and round(at * 60) <= round(last * 60):
                out.append((kp + ["at_s"], "is not after the key before it (%g s); keys run in time order, a step apart" % last))
            if isinstance(at, (int, float)):
                last = at
            for need in TRACK_NEEDS.get(prop, ()):
                if need not in key:
                    out.append((kp, "a %s key needs %s" % (prop, need)))
            for other in ("x", "y", "in", "out", "v", "tint"):
                if other in key and other not in TRACK_NEEDS.get(prop, ()) and not (prop == "motion" and other in ("in", "out")):
                    out.append((kp + [other], "is not part of a %s key" % prop))
            lo_hi = TRACK_RANGE.get(prop)
            v = key.get("v")
            if lo_hi and isinstance(v, (int, float)) and not lo_hi[0] <= v <= lo_hi[1]:
                out.append((kp + ["v"], "must be within %g..%g for %s (it is %g)" % (lo_hi[0], lo_hi[1], prop, v)))
            if prop == "scale" and isinstance(v, (int, float)) and v <= 0:
                out.append((kp + ["v"], "must be more than 0"))
            c = key.get("curve")
            if isinstance(c, list) and len(c) == 4 and all(isinstance(q, (int, float)) for q in c):
                if not (0 <= c[0] <= 1 and 0 <= c[2] <= 1):
                    out.append((kp + ["curve"], "x1 and x2 must be within 0..1, so the curve runs forward in time"))
                if "ease" in key:
                    out.append((kp, "has both ease and curve; a curve takes the place of ease, so keep one"))
    return out


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
    for key, kind in (("pictures", "picture"), ("sounds", "sound"), ("fonts", "font"), ("clips", "clip"),
                      ("particles", "particle")):
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
        if phase.get("kind") == "rhythm" and "tempo_bpm" not in settings:     # PAD-1667: the music's own grid
            music = by_kind.get("music", {}).get(settings.get("music"))
            sounds = (doc.get("assets") or {}).get("sounds") or []
            if music is not None and not isinstance(sounds[music[-1]].get("tempo_bpm"), (int, float)):
                out.append((base + ["settings", "tempo_bpm"], 'is not set, and the music "%s" has no tempo_bpm of '
                            'its own to take the beat grid from' % settings.get("music")))
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
        need(part.get("picture"), "picture", ["hud", n, "picture"])
        for i, ph in enumerate(part.get("phases") or []):
            need(ph, "phase", ["hud", n, "phases", i])
    # PAD-1666: particles' pictures, and the bursts and trails that name a particle or a preset
    presets = ("spark", "smoke", "debris", "glow")
    for n, part in enumerate((doc.get("assets") or {}).get("particles") or []):
        if isinstance(part, dict):
            need(part.get("picture"), "picture", ["assets", "particles", n, "picture"])

    def need_particle(name, path):
        if isinstance(name, str) and name != "none" and name not in presets and name not in by_kind.get("particle", {}):
            out.append((path, 'names "%s", but there is no particle with that id (or preset: %s)' % (name, ", ".join(presets))))
    for key, name in ((doc.get("style") or {}).get("bursts") or {}).items():
        need_particle(name, ["style", "bursts", key])
    for n, thing in enumerate(doc.get("things") or []):
        if isinstance(thing, dict) and isinstance(thing.get("trail"), dict):
            need_particle(thing["trail"].get("particles"), ["things", n, "trail", "particles"])
    for n, cue in enumerate(doc.get("cues") or []):
        if isinstance(cue, dict):
            need(cue.get("sound"), "sound", ["cues", n, "sound"])
    for i, phase in enumerate(doc.get("phases") or []):      # PAD-1664: the timeline
        if not isinstance(phase, dict):
            continue
        out.extend(track_problems(phase, ["phases", i]))
        for n, ts in enumerate(phase.get("sound_track") or []):
            if isinstance(ts, dict):
                need(ts.get("sound"), "sound", ["phases", i, "sound_track", n, "sound"])
    for n, snd in enumerate((doc.get("assets") or {}).get("sounds") or []):      # PAD-1667
        if not isinstance(snd, dict):
            continue
        if snd.get("role") != "music":
            for key in ("fade_s", "tempo_bpm", "beat_offset_s", "beats_per_bar"):
                if key in snd:
                    out.append((["assets", "sounds", n, key], "is for music only; this sound is a %s" % snd.get("role")))
        elif "tempo_bpm" not in snd:
            for key in ("beat_offset_s", "beats_per_bar"):
                if key in snd:
                    out.append((["assets", "sounds", n, key], "is part of a beat grid, which needs the music's tempo_bpm"))
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


# ---- the storyboard's "Add a phase" (PAD-1664) ------------------------------------
KIND_WORDS = {
    "chase": ("Chase", "Steer, fire and dodge"), "thrust": ("Thrust flight", "Hold to rise, fly the gaps"),
    "aim": ("Aim and fire", "Hit the targets"), "boss": ("Boss", "Hit the weak spots"),
    "mash": ("Mash", "Mash the button!"), "alternate": ("Alternate", "Left, right, left, right!"),
    "tug": ("Tug of war", "Hold on and pull"), "rhythm": ("Rhythm", "Press on the beat"),
    "sequence": ("Sequence", "Repeat the buttons"), "dodge": ("Dodge", "Dodge the way it says"),
    "shield": ("Shield", "Hold the shield up"), "timing": ("Timing", "Stop it in the window"),
    "defend": ("Defend", "Strike what comes at you"), "catch": ("Catch", "Catch what falls"),
    "runner": ("Runner", "Jump the gaps"), "lander": ("Lander", "Land it gently"),
    "route": ("Route", "Pick the right side"), "pick": ("Pick", "Pick a prize, or cash out"),
    "custom": ("Custom", "Things and rules of your own"),
}


def phase_template(doc, kind, phase_id=None):
    """A new document: ``doc`` with one playable phase of game kind ``kind`` added at the end of its phases, and
    whatever that phase names (things, values, pictures, music) reused from the document where something suits, or
    added as placeholders (a picture whose file does not exist yet is drawn as a placeholder). The flow is left
    alone: the storyboard wires the new phase in. Pure: nothing is read from or written to the disk."""
    if kind not in KIND_WORDS:
        raise VideoModeError(['"%s" is not a game kind' % kind])
    d = copy.deepcopy(doc)
    d.setdefault("assets", {}).setdefault("pictures", [])
    d.setdefault("things", [])
    phases = d.setdefault("phases", [])
    taken = set()
    for key in ("things", "values", "phases"):
        taken |= {x.get("id") for x in d.get(key) or [] if isinstance(x, dict)}
    pics = {p.get("id") for p in d["assets"]["pictures"] if isinstance(p, dict)}

    def fresh(base, pool):
        base = re.sub(r"[^a-z0-9_]", "_", base.lower())[:36] or "x"
        n, out = 1, base
        while out in pool:
            n += 1
            out = "%s_%d" % (base, n)
        pool.add(out)
        return out

    def thing(team, base, size, **extra):
        """The document's first thing of this team (one that moves by itself, when that is asked for), or a new
        placeholder one."""
        for t in d["things"]:
            if isinstance(t, dict) and t.get("team") == team and (not extra.get("mover") or t.get("mover")):
                return t["id"]
        pid = fresh(base, pics)
        d["assets"]["pictures"].append({"id": pid, "file": "art/%s.png" % pid, "frame_w": size[0], "frame_h": size[1]})
        tid = fresh(base, taken)
        t = {"id": tid, "picture": pid, "team": team}
        t.update(extra)
        d["things"].append(t)
        return tid

    def meter(base, goal=100):
        vid = fresh(base, taken)
        d.setdefault("values", []).append({"id": vid, "type": "meter", "start": 0, "min": 0, "max": goal})
        return vid

    pid = phase_id if phase_id and phase_id not in taken else fresh(kind, taken)
    title, objective = KIND_WORDS[kind]
    ph = {"id": pid, "kind": kind, "title": title, "objective": objective, "length_s": 30, "settings": {},
          "place": [], "win": [{"when": "survive_s", "value": 30}], "lose": []}
    s = ph["settings"]
    W, H = 1360, 768
    if kind in ("chase", "thrust"):
        p = thing("player", "player", (96, 48), health=3)
        s["player"] = p
        ph["place"] = [{"thing": p, "x": 240 if kind == "thrust" else 680, "y": 384 if kind == "thrust" else 640}]
        foe = thing("enemy", "enemy", (64, 64), points=100, mover={"type": "straight", "speed": 300, "direction": 180})
        ph["spawns"] = [{"thing": foe, "at_s": 2, "every_s": 3, "count": 8, "x": W + 60, "y": 520 if kind == "chase" else 300}]
        ph["lose"] = [{"when": "health_gone"}]
        ph["length_s"] = 40
        ph["win"] = [{"when": "survive_s", "value": 40}]
    elif kind == "aim":
        s["sight"] = thing("scenery", "sight", (64, 64))
        foe = thing("enemy", "target", (64, 64), points=100)
        ph["place"] = [{"thing": s["sight"], "x": W // 2, "y": H // 2, "depth": 20},
                       {"thing": foe, "x": 400, "y": 300}, {"thing": foe, "x": 960, "y": 300}]
        s.update(move="sweep", sweep_path=[[200, 300], [1160, 300]], sweep_s=3, fire="press")
        ph["win"] = [{"when": "kills", "value": 2}]
        ph["lose"] = [{"when": "time_up"}]
    elif kind == "boss":
        b = thing("enemy", "boss", (320, 160), health=10, points=5000)
        s.update(boss=b, hit_with="sight",
                 weak_points=[{"x": -80, "y": 0, "r": 30, "hits": 2, "open_s": 2, "closed_s": 1.5},
                              {"x": 80, "y": 0, "r": 30, "hits": 2, "open_s": 2, "closed_s": 1.5, "offset_s": 1}])
        s["sight"] = thing("scenery", "sight", (64, 64))
        ph["place"] = [{"thing": b, "x": W // 2, "y": 300}, {"thing": s["sight"], "x": 400, "y": 300, "depth": 20}]
        ph["win"] = [{"when": "boss_down"}]
        ph["lose"] = [{"when": "time_up"}]
        ph["length_s"] = 40
    elif kind in ("mash", "alternate", "tug"):
        s["meter"] = meter({"mash": "power", "alternate": "charge", "tug": "pull"}[kind])
        if kind == "mash":
            s.update(button="action", per_press=6, drain_per_s=10, goal=100)
        elif kind == "alternate":
            s.update(per_pair=9, drain_per_s=12, start_side="either", goal=100)
        else:
            s.update(hold="shown", switch_every_s=3, per_press=5, pull_back_per_s=8, goal=100)
        ph["win"] = [{"when": "goal"}]
        ph["lose"] = [{"when": "time_up"}]
        ph["length_s"] = 12
    elif kind == "rhythm":
        sounds = d["assets"].setdefault("sounds", [])
        music = next((x["id"] for x in sounds if isinstance(x, dict) and x.get("role") == "music"), None)
        if music is None:
            music = fresh("rhythm_music", {x.get("id") for x in sounds if isinstance(x, dict)})
            sounds.append({"id": music, "file": "sound/%s.ogg" % music, "role": "music", "loop": True})
        s.update(music=music, tempo_bpm=120, travel_beats=4,
                 chart=[{"beat": 4 + 2 * i, "button": ["left", "right", "action"][i % 3]} for i in range(24)])
        ph["music"] = music
        ph["win"] = [{"when": "time_up"}]
    elif kind == "sequence":
        s.update(length=4, shown=True, per_press_s=2, rounds=3)
        ph["win"] = [{"when": "time_up"}]
    elif kind == "dodge":
        s.update(buttons=["left", "right"], tell_s=1, window_s=0.8, count=8)
        ph["win"] = [{"when": "time_up"}]
    elif kind == "shield":
        s.update(button="action", tell_s=1, hold_s=1.5, count=6)
        ph["win"] = [{"when": "time_up"}]
    elif kind == "timing":
        s.update(input="press", button="action", sweep_s=1.5, window_from=0.45, window_to=0.6, shrink_pct=10, rounds=5)
        ph["win"] = [{"when": "time_up"}]
    elif kind == "defend":
        s.update({"enemy": thing("enemy", "enemy", (64, 64), points=100), "from": "sides", "speed": 300, "every_s": 1.5,
                  "count": 12, "reach": 200, "let_through": 3})
        ph["win"] = [{"when": "time_up"}]
    elif kind == "catch":
        c = thing("player", "catcher", (128, 48))
        s.update(catcher=c, move="lanes", lanes=3, speed=900, misses_allowed=3)
        ph["place"] = [{"thing": c, "x": W // 2, "y": 680}]
        item = thing("pickup", "prize", (48, 48), points=200)
        ph["spawns"] = [{"thing": item, "at_s": 1, "every_s": 1.5, "count": 15, "x": W // 2, "y": -40, "spread": 400,
                         "mover": {"type": "straight", "speed": 300, "direction": 90}}]
        ph["win"] = [{"when": "time_up"}]
    elif kind == "runner":
        r = thing("player", "runner", (64, 96))
        s.update(runner=r, jump="action", long_jump="both_flippers", jump_px=220, long_jump_px=360, scroll_speed=400, waves=5)
        ph["place"] = [{"thing": r, "x": 300, "y": 600}]
        ph["win"] = [{"when": "time_up"}]
    elif kind == "lander":
        sh = thing("player", "ship", (80, 80))
        s.update(ship=sh, gravity=200, side_thrust=300, up="action", up_thrust=500, fuel_s=20, max_land_speed=120,
                 pads=[{"x": 300, "w": 160, "points": 1000}, {"x": 1000, "w": 100, "points": 3000}])
        ph["place"] = [{"thing": sh, "x": W // 2, "y": 120}]
        ph["win"] = [{"when": "time_up"}]
    elif kind == "route":
        v = thing("player", "vehicle", (96, 96))
        s.update(vehicle=v, fork_count=5, speed=400, speed_up_pct=10)
        ph["place"] = [{"thing": v, "x": W // 2, "y": 640}]
        ph["win"] = [{"when": "time_up"}]
    elif kind == "pick":
        s.update(choices=3, bank_start=0, cash_out="none", rounds=3,
                 outcomes=[{"label": "+500", "weight": 3, "result": "prize", "amount": 500},
                           {"label": "Double", "weight": 1, "result": "double"},
                           {"label": "Bust", "weight": 1, "result": "bust"}])
        ph["win"] = [{"when": "time_up"}]
    phases.append(ph)
    return d
