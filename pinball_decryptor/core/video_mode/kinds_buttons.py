"""The button kinds of the video mode maker (PAD-1663): mash, alternate, tug of war, rhythm, button
sequence, quick dodge and hold shield.

Each entry is in the shape of the kind catalog the picker and the inspector read (kinds.py, PAD-1662):
its label and group, one plain sentence, the words its prompts use, its settings as the inspector shows
them, and a starter: the values, HUD parts and phase that make it playable the moment it is picked. The
engine draws the cabinet's three buttons itself (vm_kinds2.c), so none of these needs a picture; the
rhythm's starter brings an original drum loop at its own tempo, written by ``make_files`` (PAD ships no
game content).

``new_doc(kind)`` is a one-phase document of a kind, the way the picker makes one: the golden replays
(tests/test_video_mode_kinds2.py) play exactly these.
"""

import io
import math
import struct
import wave

from . import document



def _s(name, label, type_, default, help_, **kw):
    out = {"name": name, "label": label, "type": type_, "default": default, "help": help_, "advanced": False}
    out.update(kw)
    return out


_BUTTON_CHOICES = [["left", "Left flipper button"], ["right", "Right flipper button"], ["action", "Action button"]]

KINDS2 = {
    "mash": {
        "label": "Mash", "group": "Button skill",
        "blurb": "Hit a button as fast as you can to fill a meter before it drains, or before a rival fills theirs.",
        "buttons": {"action": "Mash"},
        "settings": [
            _s("meter", "Meter", "value", None, "The meter the presses fill."),
            _s("button", "Button", "button", "action", "The button to mash.", choices=_BUTTON_CHOICES),
            _s("per_press", "Each press adds", "number", 6, "How much one press fills.", min=0, max=100, step=0.5),
            _s("drain_per_s", "Drains", "number", 15, "How much the meter loses every second.", min=0, max=500, unit="/s"),
            _s("goal", "Goal", "number", 100, "Fill it to here to win.", min=1, max=10000),
            _s("rival_per_s", "Rival", "number", 0, "A rival filling its own bar this fast; first to the goal wins. 0: no rival.",
               min=0, max=500, unit="/s", advanced=True),
        ],
        "curve": True,
    },
    "alternate": {
        "label": "Alternate", "group": "Button skill",
        "blurb": "Left, right, left, right: each pair of flipper presses charges the meter.",
        "buttons": {"left": "Left", "right": "Right"},
        "settings": [
            _s("meter", "Meter", "value", None, "The meter each left and right pair fills."),
            _s("per_pair", "Each pair adds", "number", 8, "How much one left and right pair fills.", min=0, max=100, step=0.5),
            _s("drain_per_s", "Drains", "number", 12, "How much the meter loses every second.", min=0, max=500, unit="/s"),
            _s("start_side", "Start with", "choice", "either", "Which flipper the run must start on.",
               choices=[["either", "Either flipper"], ["left", "Left flipper"], ["right", "Right flipper"]]),
            _s("goal", "Goal", "number", 100, "Fill it to here to win.", min=1, max=10000),
        ],
        "curve": True,
    },
    "tug": {
        "label": "Tug of war", "group": "Button skill",
        "blurb": "Hold the flipper the screen names and mash Action to pull away, and shake off what grabs you "
                 "with left, right, left, right.",
        "buttons": {"left": "Hold / shake", "right": "Hold / shake", "action": "Pull"},
        "settings": [
            _s("meter", "Meter", "value", None, "The tug: full wins, empty loses. It starts part way up."),
            _s("hold", "Hold", "choice", "shown", "The flipper to hold while pulling.",
               choices=[["shown", "The one the screen names"], ["left", "Always the left"], ["right", "Always the right"]]),
            _s("switch_every_s", "Switches every", "number", 4, "How often the named flipper changes sides.", min=0, max=60, unit="s"),
            _s("per_press", "Each pull adds", "number", 2, "How much one Action press pulls, while the named flipper is held.",
               min=0, max=100, step=0.5),
            _s("pull_back_per_s", "Pulls back", "number", 8, "How much the other side pulls back every second; twice that while it has you.",
               min=0, max=500, unit="/s"),
            _s("shake_every_s", "Grabbed every", "number", 5, "How often the second threat takes hold. 0: never.", min=0, max=60, unit="s"),
            _s("shake_pairs", "Shake off with", "int", 4, "Left and right pairs it takes to shake it off.", min=0, max=50),
            _s("goal", "Goal", "number", 100, "Pull it to here to win.", min=1, max=10000),
        ],
        "curve": True,
    },
    "rhythm": {
        "label": "Rhythm", "group": "Button skill",
        "blurb": "Buttons travel down to the line in time with the music; press each as it lands. Early, good and perfect.",
        "buttons": {"left": "Left", "right": "Right", "action": "Action"},
        "settings": [
            _s("music", "Music", "music", None, "The music the chart is played to."),
            _s("tempo_bpm", "Tempo", "number", 120, "Beats a minute. Tap it in on the music, or take its beat grid.",
               min=30, max=300, unit="bpm"),
            _s("offset_ms", "First beat at", "number", 0, "Where the first beat falls in the music.", min=-2000, max=2000, unit="ms"),
            _s("travel_beats", "Notes appear", "number", 2, "How many beats ahead a note shows up.", min=0.5, max=16, step=0.5, unit="beats"),
            _s("perfect_ms", "Perfect within", "number", 45, "A press this close to the beat is perfect.", min=0, max=500, unit="ms"),
            _s("good_ms", "Good within", "number", 100, "A press this close is good; up to twice this is early or late.",
               min=0, max=500, unit="ms"),
            _s("chart", "Chart", "chart", [], "The notes: on which beat, which button, and how many beats to hold."),
        ],
        "curve": False,
    },
    "sequence": {
        "label": "Button sequence", "group": "Button skill",
        "blurb": "A run of left, right and Action to enter in time, shown on screen or flashed once to remember.",
        "buttons": {"left": "Left", "right": "Right", "action": "Action"},
        "settings": [
            _s("buttons", "Run", "buttons", [], "A fixed run of buttons; leave it empty for a new random run each play."),
            _s("length", "Random length", "int", 4, "How many buttons a random run starts with; it grows one a round.", min=1, max=32),
            _s("shown", "Shown", "bool", False, "On: the run stays on screen. Off: it flashes, then you enter it from memory."),
            _s("flash_s", "Flashed for", "number", 2, "How long the run shows before it hides.", min=0, max=30, step=0.25, unit="s"),
            _s("per_press_s", "Time a press", "number", 1.5, "How long you have for each button.", min=0.2, max=10, step=0.1, unit="s"),
            _s("rounds", "Rounds", "int", 3, "Runs to get right to win.", min=1, max=20),
        ],
        "curve": False,
    },
    "dodge": {
        "label": "Quick dodge", "group": "Button skill",
        "blurb": "A warning shows which way it is coming, then press that button in a short window. Too early, too late or the wrong one is a hit.",
        "buttons": {"left": "Dodge", "right": "Dodge", "action": "Dodge"},
        "settings": [
            _s("buttons", "Buttons", "buttons", ["left", "right", "action"], "The buttons a warning may name."),
            _s("tell_s", "Warning for", "number", 0.8, "How long the warning shows before the window opens.", min=0, max=5, step=0.05, unit="s"),
            _s("window_s", "Window", "number", 0.6, "How long you have to press.", min=0.05, max=10, step=0.05, unit="s"),
            _s("count", "Attacks", "int", 8, "Attacks to get through.", min=1, max=99),
        ],
        "curve": True,
    },
    "shield": {
        "label": "Hold shield", "group": "Button skill",
        "blurb": "A warning, then hold the button for as long as the attack lasts. Let go early and it lands.",
        "buttons": {"action": "Shield"},
        "settings": [
            _s("button", "Button", "button", "action", "The button that holds the shield up.", choices=_BUTTON_CHOICES),
            _s("tell_s", "Warning for", "number", 0.8, "How long the warning shows before the attack.", min=0, max=5, step=0.05, unit="s"),
            _s("hold_s", "Hold for", "number", 1.2, "How long each attack lasts.", min=0.05, max=30, step=0.05, unit="s"),
            _s("count", "Attacks", "int", 5, "Attacks to block.", min=1, max=99),
        ],
        "curve": True,
    },
}


# ---- the starters ---------------------------------------------------------------------------------------
def _hud(p, meter=None, extra=()):
    out = [
        {"id": p + "score", "part": "score", "x": 1332, "y": 18, "font": p + "hud", "colour": "#ffffff"},
        {"id": p + "combo", "part": "combo", "x": 1120, "y": 18, "font": p + "hud", "colour": "#f2c14e"},
        {"id": p + "callout", "part": "callout", "x": 680, "y": 200, "font": p + "big", "colour": "#f2c14e", "accent": "#1b1d1f"},
        {"id": p + "prompts", "part": "prompts", "x": 0, "y": 640, "w": 1360, "h": 120, "look": "glyphs",
         "font": p + "hud", "colour": "#e8edf4", "accent": "#e5483b"},
    ]
    if meter:
        out.append({"id": p + "meter_bar", "part": "meter", "x": 380, "y": 120, "w": 600, "h": 28, "value": meter,
                    "look": "bar", "colour": "#f2c14e", "accent": "#f0705f"})
    out.extend(extra)
    return out


def _fonts(p):
    return [{"id": p + "hud", "face": "card:default", "size": 28}, {"id": p + "big", "face": "card:default", "size": 64}]


def rhythm_chart(bars, first_beat=4, seed=1663):
    """An original starter chart: a four-beat pattern per bar that grows busier, with a held note now
    and then, on the beats of `bars` bars from `first_beat`."""
    pats = [
        [(0, "action")], [(0, "left"), (2, "right")], [(0, "left"), (1, "action"), (2, "right")],
        [(0, "left"), (1, "right"), (2, "left"), (3, "action")], [(0, "action", 2), (2, "left"), (3, "right")],
        [(0, "right"), (0.5, "left"), (1, "action"), (2, "right"), (3, "left")],
    ]
    out, x = [], seed
    for bar in range(bars):
        level = min(len(pats) - 1, bar // 4 + (1 if bar % 4 == 3 else 0))
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        pat = pats[max(0, level - (x >> 16) % 2)]
        for n in pat:
            note = {"beat": first_beat + bar * 4 + n[0], "button": n[1]}
            if len(n) > 2:
                note["hold_beats"] = n[2]
            out.append(note)
    return out


def starter(kind, p=""):
    """The values, sounds, fonts, HUD and phase that make a `kind` phase playable, ids under prefix `p`.
    files: the files it needs written beside the document (make_files)."""
    sounds, files, values, hud_extra = [], {}, [], []
    meter = None
    if kind in ("mash", "alternate", "tug"):
        meter = p + ("pull" if kind == "tug" else "power")
        values.append({"id": meter, "type": "meter", "start": 50 if kind == "tug" else 0, "min": 0, "max": 100})
    if kind == "mash":
        ph = {"kind": "mash", "title": "Mash it!", "objective": "Hit Action as fast as you can", "length_s": 10,
              "settings": {"meter": meter, "button": "action", "per_press": 6, "drain_per_s": 15, "goal": 100},
              "win": [{"when": "goal"}], "lose": [{"when": "time_up"}]}
        hud_extra.append({"id": p + "timer", "part": "timer", "x": 28, "y": 18, "font": p + "hud", "colour": "#ffffff"})
    elif kind == "alternate":
        ph = {"kind": "alternate", "title": "Full power", "objective": "Left, right, left, right!", "length_s": 10,
              "settings": {"meter": meter, "per_pair": 8, "drain_per_s": 12, "start_side": "either", "goal": 100},
              "win": [{"when": "goal"}], "lose": [{"when": "time_up"}]}
        hud_extra.append({"id": p + "timer", "part": "timer", "x": 28, "y": 18, "font": p + "hud", "colour": "#ffffff"})
    elif kind == "tug":
        ph = {"kind": "tug", "title": "Pull away!", "objective": "Hold the flipper it names and mash Action", "length_s": 40,
              "settings": {"meter": meter, "hold": "shown", "switch_every_s": 4, "per_press": 2, "pull_back_per_s": 8,
                           "shake_every_s": 5, "shake_pairs": 4, "goal": 100},
              "win": [{"when": "goal"}], "lose": [{"when": "time_up"}]}
        hud_extra.append({"id": p + "timer", "part": "timer", "x": 28, "y": 18, "font": p + "hud", "colour": "#ffffff"})
    elif kind == "rhythm":
        bpm, bars = 120, 24
        music = p + "beat"
        fname = "sound/%sbeat_%d.wav" % (p, bpm)
        sounds.append({"id": music, "file": fname, "role": "music", "volume": 0.8, "loop": False})
        files[fname] = ("beat", {"bpm": bpm, "beats": 4 + bars * 4 + 8})
        ph = {"kind": "rhythm", "title": "On the beat", "objective": "Press each button as it reaches the line",
              "settings": {"music": music, "tempo_bpm": bpm, "offset_ms": 0, "travel_beats": 2, "perfect_ms": 45,
                           "good_ms": 100, "chart": rhythm_chart(bars)},
              "win": [{"when": "accuracy", "value": 70}], "lose": [{"when": "misses", "value": 16}]}
    elif kind == "sequence":
        ph = {"kind": "sequence", "title": "Remember it", "objective": "Watch the run, then enter it",
              "settings": {"length": 4, "shown": False, "flash_s": 2, "per_press_s": 1.5, "rounds": 3},
              "win": [{"when": "goal"}], "lose": [{"when": "misses", "value": 3}]}
    elif kind == "dodge":
        ph = {"kind": "dodge", "title": "Dodge!", "objective": "Press the button it warns you of",
              "settings": {"buttons": ["left", "right", "action"], "tell_s": 0.8, "window_s": 0.6, "count": 8},
              "win": [{"when": "goal"}], "lose": [{"when": "misses", "value": 3}]}
    elif kind == "shield":
        ph = {"kind": "shield", "title": "Shields up", "objective": "Hold Action while each attack lasts",
              "settings": {"button": "action", "tell_s": 0.8, "hold_s": 1.2, "count": 5},
              "win": [{"when": "goal"}], "lose": [{"when": "misses", "value": 3}]}
    else:
        raise KeyError(kind)
    ph["id"] = p + kind
    return {"pictures": [], "things": [], "values": values, "sounds": sounds, "fonts": _fonts(p),
            "hud": _hud(p, meter, hud_extra), "phase": ph, "files": files}


def new_doc(kind, slug=None):
    """A one-phase document of `kind`, as the picker makes it; (doc, files to write)."""
    st = starter(kind)
    doc = document.new(slug or ("%s-starter" % kind), KINDS2[kind]["label"])
    doc["assets"] = {"pictures": [], "sounds": st["sounds"], "fonts": st["fonts"]}
    if not st["sounds"]:
        del doc["assets"]["sounds"]
    if st["values"]:
        doc["values"] = st["values"]
    doc["hud"] = st["hud"]
    doc["phases"] = [st["phase"]]
    doc["flow"]["cards"][0]["phase"] = st["phase"]["id"]
    return doc, st["files"]


# ---- the files a starter brings: original, made here --------------------------------------------------------
def beat_wav(bpm, beats, rate=48000):
    """An original drum loop: a kick on every beat, a hat between, a snare on 2 and 4. 16-bit mono WAV
    bytes; the first beat is at 0 s, so a chart's beat n is at n * 60 / bpm seconds."""
    n = int(round(rate * beats * 60.0 / bpm)) + rate // 2
    buf = [0.0] * n
    step = rate * 60.0 / bpm
    x = 1663

    def noise():
        nonlocal x
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        return ((x >> 8) & 0xFFFF) / 32768.0 - 1.0

    for b in range(beats):
        at = int(round(b * step))
        for i in range(int(rate * 0.18)):           # kick: a falling sine
            t = i / rate
            if at + i < n:
                buf[at + i] += 0.8 * math.exp(-t * 22) * math.sin(2 * math.pi * (50 + 90 * math.exp(-t * 40)) * t)
        if b % 2 == 1:                              # snare on 2 and 4
            for i in range(int(rate * 0.14)):
                t = i / rate
                if at + i < n:
                    buf[at + i] += 0.35 * math.exp(-t * 30) * (noise() + 0.5 * math.sin(2 * math.pi * 190 * t))
        h = int(round(at + step / 2))
        for i in range(int(rate * 0.03)):           # hat between beats
            if h + i < n:
                buf[h + i] += 0.12 * math.exp(-i / rate * 120) * noise()
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", max(-32767, min(32767, int(v * 26000)))) for v in buf))
    return out.getvalue()


def make_files(mode_dir, files):
    """Write the files a starter brings (relative paths under the mode's folder); ones already there are kept."""
    import os
    made = []
    for rel, (what, args) in files.items():
        path = os.path.join(mode_dir, *rel.split("/"))
        if os.path.exists(path):
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if what == "beat":
            data = beat_wav(args["bpm"], args["beats"])
        else:
            raise ValueError(what)
        with open(path, "wb") as f:
            f.write(data)
        made.append(rel)
    return made
