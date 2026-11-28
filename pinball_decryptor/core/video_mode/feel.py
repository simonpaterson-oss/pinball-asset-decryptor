"""The HUD and feel of a video mode (PAD-1666): particle presets, the style presets, and what each effect costs.

Everything here becomes numbers the engine reads (compiler.py packs them), so the machine and the app's player
show the same effects from the same rules; nothing is drawn by a backend of its own.

    feel.PARTICLE_PRESETS     spark, smoke, debris, glow: a particle's settings in the document's units
    feel.particle(spec)       a document particle (a preset and what it changes) -> every setting filled in
    feel.emitter_row(p, ...)  -> the engine's vm_emitter words
    feel.style_bits(style)    the effect switches (vm_engine.h VM_FX_*)
    feel.STYLE_PRESETS        arcade, comic, clean, retro_pixel: the whole HUD and feel at once
    feel.apply_preset(doc, name) -> a new document with the preset's HUD looks, text styles and feel
    feel.costs(doc, machine)  each effect's draw list entries at its worst, against the machine's budget
"""
import copy
import math

from . import budgets as B

SPS = 60
ONE = 65536

# ---- particles ------------------------------------------------------------------------------------------------------
#: units: count (made at once), speed px/s [lo, hi], direction and spread in degrees (spread is the whole fan),
#: life_s, size and size_end in px, gravity px/s/s (down is +), drag (the share of speed kept after a second),
#: colour and colour_end ("#rrggbbaa"), blend (normal or add), glow (1 plain box, 2-3 nested boxes, a soft edge),
#: streak (a streak along its speed: px of length per px a step of speed)
PARTICLE_PRESETS = {
    "spark": {"count": 14, "speed": [180, 480], "direction": 0, "spread": 360, "life_s": 0.45, "size": 5, "size_end": 1,
              "gravity": 600, "drag": 0.2, "colour": "#fff3b0ff", "colour_end": "#ff8a3d00", "blend": "add", "glow": 1,
              "streak": 2.5},
    "smoke": {"count": 8, "speed": [20, 70], "direction": -90, "spread": 120, "life_s": 1.2, "size": 18, "size_end": 56,
              "gravity": -40, "drag": 0.5, "colour": "#9a9ea6b0", "colour_end": "#4a4e5600", "blend": "normal", "glow": 2,
              "streak": 0},
    "debris": {"count": 12, "speed": [120, 360], "direction": -90, "spread": 300, "life_s": 0.8, "size": 7, "size_end": 4,
               "gravity": 1100, "drag": 0.6, "colour": "#c9b8a0ff", "colour_end": "#6b5a48ff", "blend": "normal",
               "glow": 1, "streak": 0},
    "glow": {"count": 10, "speed": [30, 120], "direction": 0, "spread": 360, "life_s": 0.6, "size": 10, "size_end": 28,
             "gravity": -60, "drag": 0.3, "colour": "#9ff5c0ff", "colour_end": "#2ad1ff00", "blend": "add", "glow": 3,
             "streak": 0},
}
PRESET_NAMES = tuple(PARTICLE_PRESETS)
#: which happening throws which burst (vm_engine.h VM_BURST_*), and the burst each throws by default
BURSTS = ("kill", "hurt", "pickup", "hit", "fire", "boss")
DEFAULT_BURSTS = {"kill": "spark", "hurt": "debris", "pickup": "glow", "hit": "spark", "fire": "none", "boss": "smoke"}


def particle(spec):
    """A particle as the document has it (``{"preset": "spark", "count": 20, ...}``, or a preset's name) with every
    setting filled in from its preset."""
    if isinstance(spec, str):
        spec = {"preset": spec}
    out = dict(PARTICLE_PRESETS.get(spec.get("preset") or "spark", PARTICLE_PRESETS["spark"]))
    out.update({k: v for k, v in spec.items() if k not in ("id", "preset")})
    return out


def _colour(c, default=0xFFFFFFFF):
    from .compiler import colour
    return colour(c, default)


def emitter_row(p, picture=-1):
    """vm_emitter: count, speed_lo, speed_hi, dir, spread, life, size0, size1, gravity, drag, col0, col1, blend,
    picture, layers, stretch."""
    lo, hi = (p["speed"] if isinstance(p["speed"], (list, tuple)) else (p["speed"], p["speed"]))
    lo, hi = sorted((max(0.0, float(lo)), max(0.0, float(hi))))
    drag_s = min(1.0, max(0.0001, float(p.get("drag", 1))))
    life = max(1, min(600, int(round(float(p.get("life_s", 0.5)) * SPS))))
    return [max(0, min(128, int(p.get("count", 10)))),
            int(round(min(lo, 12000) * ONE / SPS)), int(round(min(hi, 12000) * ONE / SPS)),
            int(round(float(p.get("direction", 0)) * ONE)), int(round(min(720.0, max(0.0, float(p.get("spread", 360)))) * ONE)),
            life, int(round(min(512.0, max(0.0, float(p.get("size", 6)))) * ONE)),
            int(round(min(512.0, max(0.0, float(p.get("size_end", p.get("size", 6))))) * ONE)),
            int(round(max(-57000.0, min(57000.0, float(p.get("gravity", 0)))) * ONE / (SPS * SPS))),
            min(ONE, int(round(drag_s ** (1.0 / SPS) * ONE))),
            _colour(p.get("colour"), 0xFFFFFFFF), _colour(p.get("colour_end") or p.get("colour"), 0xFFFFFF00),
            1 if p.get("blend") == "add" else 0, picture, max(1, min(3, int(p.get("glow", 1)))),
            int(round(max(0.0, min(16.0, float(p.get("streak", 0)))) * ONE))]


# ---- the style --------------------------------------------------------------------------------------------------------
#: vm_engine.h VM_FX_*: (bit, the style switch, on when the document leaves it out)
SWITCHES = (
    (0x001, "shake", True), (0x002, "flash", True), (0x004, "particles", True), (0x008, "hit_stop", False),
    (0x010, "crt", False), (0x020, "squash", True), (0x040, "blink", True), (0x080, "popups", True),
    (0x100, "trails", True), (0x200, "count_up", True), (0x400, "pulse", True),
)
#: what each switch is called in the app, and what it does
SWITCH_WORDS = {
    "shake": ("Screen shake", "The stage shakes on hits, hurts and a boss going down."),
    "flash": ("Flashes", "A red flash when hurt, a white one when a boss goes down and between phases."),
    "particles": ("Particles", "Bursts on kills, hits, pick-ups and hurts."),
    "trails": ("Trails", "Things that leave a trail of particles."),
    "hit_stop": ("Hit-stop", "The game holds still for a few frames on a hit, so it lands."),
    "squash": ("Squash and stretch", "A thing that is hit wobbles."),
    "blink": ("Damage blink", "The player blinks while it cannot be hurt again."),
    "popups": ("Pop-up words", "Words like +500 rise from where something happened."),
    "count_up": ("Count-up", "The score and counters roll up to their new number."),
    "pulse": ("Pulse and pop", "A part in danger pulses; a number that changed pops."),
    "crt": ("CRT", "Scan lines and a darker edge, like an old screen."),
}
TRANSITIONS = ("cut", "fade", "white_flash", "wipe", "iris")


def style_bits(style):
    style = style or {}
    bits = 0
    for bit, key, default in SWITCHES:
        if style.get(key, default):
            bits |= bit
    return bits


def style_numbers(style):
    """shake_pct, hitstop_steps, trans_steps, crt_alpha: the amounts the switches turn on."""
    style = style or {}
    return [int(round(max(0.0, min(4.0, float(style.get("shake_amount", 1)))) * 100)),
            max(0, min(30, int(style.get("hit_stop_frames", 3)))),
            max(1, min(240, int(round(float(style.get("transition_s", 0.3)) * SPS)))),
            int(round(max(0.0, min(1.0, float(style.get("crt_strength", 0.35)))) * 255))]


def combo_numbers(doc):
    """combo_steps, combo_every, combo_max: kills this close chain a combo; every `every` of them adds 1 to the
    multiplier, up to `max` (no `combo`: kills score their points, as before format 3)."""
    c = doc.get("combo") or {}
    return [max(1, min(6000, int(round(float(c.get("window_s", 1.5)) * SPS)))),
            max(0, min(1000, int(c.get("every", 0)))), max(1, min(100, int(c.get("max", 5))))]


# ---- the style presets --------------------------------------------------------------------------------------------
#: Each sets the feel (style, combo) and, per HUD part kind, its look and text style. A starting point: the maker's
#: own changes after it are kept until another preset is applied.
STYLE_PRESETS = {
    "arcade": {
        "label": "Arcade", "about": "Loud and bright: outlined numbers with a gold fill, big bursts, white flashes.",
        "style": {"shake": True, "shake_amount": 1.2, "flash": True, "particles": True, "trails": True, "hit_stop": True,
                  "hit_stop_frames": 3, "squash": True, "blink": True, "popups": True, "count_up": True, "pulse": True,
                  "crt": False, "transition": "white_flash", "transition_s": 0.25,
                  "bursts": {"kill": "spark", "hurt": "debris", "pickup": "glow", "hit": "spark", "fire": "none",
                             "boss": "smoke"}},
        "combo": {"window_s": 1.5, "every": 5, "max": 5},
        "text": {"colour": "#ffffff", "outline": "#101214", "shadow": "", "gradient": "#ffb020"},
        "accent": "#ffd23f", "danger": "#ff4b3a",
        "parts": {"health": {"look": "pips", "colour": "#5ee07a"}, "lives": {"look": "pips"},
                  "meter": {"look": "bar"}, "timer": {"look": "ring"}},
        "popup": {"text": "+{n}", "on": ["kill", "pickup"], "colour": "#ffd23f", "outline": "#101214",
                  "gradient": "#ff8a3d", "rise": 70, "life_s": 0.8},
    },
    "comic": {
        "label": "Comic", "about": "Ink outlines and drop shadows, hearts for health, an iris between phases.",
        "style": {"shake": True, "shake_amount": 1.0, "flash": True, "particles": True, "trails": True, "hit_stop": True,
                  "hit_stop_frames": 4, "squash": True, "blink": True, "popups": True, "count_up": True, "pulse": True,
                  "crt": False, "transition": "iris", "transition_s": 0.35,
                  "bursts": {"kill": "spark", "hurt": "debris", "pickup": "glow", "hit": "spark", "fire": "none",
                             "boss": "debris"}},
        "combo": {"window_s": 1.5, "every": 4, "max": 4},
        "text": {"colour": "#ffe14d", "outline": "#000000", "shadow": "#000000a0", "gradient": "#ff7a1a"},
        "accent": "#ffe14d", "danger": "#e8202a",
        "parts": {"health": {"look": "hearts", "colour": "#e8202a"}, "lives": {"look": "hearts", "colour": "#e8202a"},
                  "meter": {"look": "bar"}, "timer": {"look": "number"}},
        "popup": {"text": "+{n}", "on": ["kill", "pickup", "hit"], "colour": "#ffffff", "outline": "#000000",
                  "shadow": "#000000a0", "rise": 50, "life_s": 0.7},
    },
    "clean": {
        "label": "Clean", "about": "Quiet and modern: plain white type with a soft shadow, thin bars, fades.",
        "style": {"shake": True, "shake_amount": 0.5, "flash": False, "particles": True, "trails": False,
                  "hit_stop": False, "hit_stop_frames": 2, "squash": False, "blink": True, "popups": True,
                  "count_up": True, "pulse": True, "crt": False, "transition": "fade", "transition_s": 0.4,
                  "bursts": {"kill": "glow", "hurt": "glow", "pickup": "glow", "hit": "glow", "fire": "none",
                             "boss": "glow"}},
        "combo": {"window_s": 2.0, "every": 0, "max": 1},
        "text": {"colour": "#f4f5f2", "outline": "", "shadow": "#00000070", "gradient": ""},
        "accent": "#8fd3ff", "danger": "#ff6b5e",
        "parts": {"health": {"look": "bar", "colour": "#f4f5f2"}, "lives": {"look": "pips"},
                  "meter": {"look": "bar"}, "timer": {"look": "number"}},
        "popup": {"text": "+{n}", "on": ["kill"], "colour": "#f4f5f2", "shadow": "#00000070", "rise": 40,
                  "life_s": 0.6},
    },
    "retro_pixel": {
        "label": "Retro pixel", "about": "An old screen: scan lines, hard boxes, pips, wipes between phases.",
        "style": {"shake": True, "shake_amount": 1.0, "flash": True, "particles": True, "trails": True,
                  "hit_stop": True, "hit_stop_frames": 2, "squash": False, "blink": True, "popups": True,
                  "count_up": False, "pulse": True, "crt": True, "crt_strength": 0.35, "transition": "wipe",
                  "transition_s": 0.3,
                  "bursts": {"kill": "debris", "hurt": "debris", "pickup": "debris", "hit": "debris", "fire": "none",
                             "boss": "debris"}},
        "combo": {"window_s": 1.5, "every": 5, "max": 3},
        "text": {"colour": "#9dff7a", "outline": "#0b2a0b", "shadow": "", "gradient": ""},
        "accent": "#ffcc33", "danger": "#ff5533",
        "parts": {"health": {"look": "pips", "colour": "#9dff7a"}, "lives": {"look": "pips"},
                  "meter": {"look": "pips"}, "timer": {"look": "number"}},
        "popup": {"text": "+{n}", "on": ["kill"], "colour": "#ffcc33", "outline": "#0b2a0b", "rise": 30,
                  "life_s": 0.5},
    },
}
TEXT_PARTS = {"score", "combo", "multiplier", "counter", "timer", "text", "callout", "prompts", "popup"}
NUMBER_PARTS = {"score", "counter"}


def _set(d, key, value):
    if value:
        d[key] = value
    else:
        d.pop(key, None)


def apply_preset(doc, name):
    """A new document with style preset ``name``: its feel, its combo and its look on every HUD part (looks, colours,
    text styles, danger colours), and a pop-up part when there is none. Places, sizes, fonts and values are kept."""
    pre = STYLE_PRESETS.get(name)
    if pre is None:
        raise ValueError("No style preset %r; they are %s." % (name, ", ".join(STYLE_PRESETS)))
    d = copy.deepcopy(doc)
    st = copy.deepcopy(pre["style"])
    st["preset"] = name
    d["style"] = st
    d["combo"] = dict(pre["combo"])
    t = pre["text"]
    for h in d.get("hud", []):
        part = h.get("part")
        if part in TEXT_PARTS:
            if part != "popup":
                _set(h, "colour", t["colour"] if part not in ("callout", "combo") else pre["accent"])
            _set(h, "outline", t["outline"])
            _set(h, "shadow", t["shadow"])
            _set(h, "gradient", t["gradient"] if part in ("score", "callout", "combo", "multiplier") else "")
            if part in NUMBER_PARTS:
                h["count_up"] = 0.5
                h["pop"] = True
            if part in ("combo", "multiplier"):
                h["pop"] = True
            if part == "callout":
                h.pop("accent", None)
        look = pre["parts"].get(part)
        if look:
            for k, v in look.items():
                h[k] = v
        if part in ("health", "lives", "timer") or (part == "meter" and not h.get("zones")):
            h["danger"] = pre["danger"]
            h.setdefault("low", 0.34)
        if part == "prompts":   # a held button's word lights in the accent (white when the words are that colour)
            h["accent"] = pre["accent"] if pre["accent"].lower() != str(h.get("colour", "")).lower() else "#ffffff"
    pops = [h for h in d.get("hud", []) if h.get("part") == "popup"]
    p = pre["popup"]
    if not pops:
        fonts = [f["id"] for f in (d.get("assets") or {}).get("fonts") or []]
        ids = {h.get("id") for h in d.get("hud", [])}
        new = {"id": "popups" if "popups" not in ids else "popups_2", "part": "popup", "x": 680, "y": 300}
        if fonts:
            new["font"] = fonts[0]
        d.setdefault("hud", []).append(new)
        pops = [new]
    for h in pops:
        h["text"] = p["text"]
        h["on"] = list(p["on"])
        h["colour"] = p["colour"]
        for k in ("outline", "shadow", "gradient"):
            _set(h, k, p.get(k, ""))
        h["rise"] = p["rise"]
        h["life_s"] = p["life_s"]
    return d


# ---- what each effect costs --------------------------------------------------------------------------------------
def _passes(h):
    """Quads a glyph takes: the fill, and one more each for an outline, a shadow and a gradient."""
    return 1 + bool(h.get("outline")) + bool(h.get("shadow")) + bool(h.get("gradient"))


def _sample_chars(h):
    part = h.get("part")
    text = h.get("text") or ""
    if part == "score":
        return max(len(text.replace("{n}", "")) + 9, 9)      # 9,999,999
    if part in ("counter", "timer", "combo", "multiplier"):
        return len(text.replace("{n}", "")) + 3 if text else 4
    if part == "popup":
        return len((text or "+{n}").replace("{n}", "")) + 5
    if part == "callout":
        return 24
    if part == "prompts":
        return 18
    return len(text) or 8


def costs(doc, machine=None):
    """Each effect's draw list entries (quads and boxes) at its worst in one frame, against the machine's budget
    for a frame: [{"key", "label", "entries", "on", "share"}], and the totals. The engine holds 3072 entries; the
    machine's own budget is the plan's "Quads drawn a frame" row."""
    m = B.machine(machine)
    budget = m.get("quads") or 1500
    st = doc.get("style") or {}
    on = {key: bool(st.get(key, default)) for _bit, key, default in SWITCHES}
    rows = []

    def row(key, label, n, active=True):
        rows.append({"key": key, "label": label, "entries": int(n), "on": bool(active),
                     "share": round(100.0 * n / budget, 1) if budget else 0.0})

    # particles: the pool, as the bursts fill it (a burst a happening; four at once is a busy frame)
    parts = {p.get("id"): particle(p) for p in (doc.get("assets") or {}).get("particles") or []}
    bursts = dict(DEFAULT_BURSTS)
    bursts.update(st.get("bursts") or {})
    worst = 0
    for key in BURSTS:
        name = bursts.get(key)
        if not name or name == "none":
            continue
        p = parts.get(name) or particle(name)
        worst = max(worst, p["count"] * p.get("glow", 1))
    row("particles", "Particles (four bursts at once)", min(512 * 3, worst * 4), on["particles"])
    trail = 0
    for t in doc.get("things", []):
        tr = t.get("trail")
        if tr:
            p = parts.get(tr.get("particles")) or particle(tr.get("particles") or "smoke")
            alive = p["count"] * max(1.0, p["life_s"] / max(1.0 / SPS, float(tr.get("every_s", 0.1))))
            trail += alive * p.get("glow", 1) * 3     # about three of a kind on the stage
    row("trails", "Trails", min(512 * 3, trail), on["trails"] and on["particles"])
    text = 0
    for h in doc.get("hud", []):
        if h.get("part") in TEXT_PARTS and h.get("part") != "popup":
            text += _sample_chars(h) * _passes(h)
    row("text", "HUD words, with their outline, shadow and gradient", text)
    pop = 0
    for h in doc.get("hud", []):
        if h.get("part") == "popup":
            alive = min(24, int(math.ceil(float(h.get("life_s", 0.8)) * 4)))   # about four a second
            pop += alive * _sample_chars(h) * _passes(h)
    row("popups", "Pop-up words", pop, on["popups"])
    bars = 0
    for h in doc.get("hud", []):
        look = h.get("look", "")
        if h.get("part") in ("health", "lives"):
            n = 8 if h.get("part") == "health" else 5
            bars += n * 7 if look == "hearts" else 24 if look == "ring" else 7 if look == "bar" else n
        elif h.get("part") in ("meter", "progress"):
            bars += 24 if look == "ring" else 10 if look == "pips" else 7
            bars += 2 * len(h.get("zones") or [])
        elif h.get("part") == "timer" and look == "ring":
            bars += 24
    row("bars", "Bars, pips, hearts and rings", bars)
    row("crt", "CRT scan lines and edge", 208, on["crt"])
    row("transition", "Transition between phases", 4)
    total = sum(r["entries"] for r in rows if r["on"])
    return {"machine": m["key"], "label": m["label"], "budget": budget, "rows": rows, "total": total,
            "share": round(100.0 * total / budget, 1) if budget else 0.0, "engine_entries": 3072}
