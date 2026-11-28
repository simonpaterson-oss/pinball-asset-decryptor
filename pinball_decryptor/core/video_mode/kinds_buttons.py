"""The button kinds of the video mode maker (PAD-1663): mash, alternate, tug of war, rhythm, button
sequence, quick dodge and hold shield.

The entries are in the shape of the kind catalog (core/video_mode/kinds.py, PAD-1662), which takes them in
with ``KINDS.update(KINDS2)`` and lists them under ``GROUP2``: a label and group, one plain sentence, the
words its prompts use, its settings as the inspector shows them, and a starter (``starter_<kind>(st)``, using
only the catalog's ``st.id``, ``st.value`` and ``st.done``) that makes it playable the moment it is picked.
The engine draws the cabinet's three buttons itself (vm_kinds2.c), so none of these needs a picture. The
rhythm starter brings music: an original drum loop at its own tempo, in the starter's ``sounds`` and
``files`` (``make_files`` writes it; PAD ships no game content).

The module stands alone, so ``new_doc(kind)`` here makes a one-phase mode of a kind the way the picker does;
the golden replays (tests/test_video_mode_kinds2.py) play exactly these.
"""

import copy
import io
import math
import struct
import wave

from . import document

GROUP2 = "Buttons and timing"


def S(name, label, type_, default, help_, **kw):
    d = {"name": name, "label": label, "type": type_, "default": default, "help": help_}
    d.update(kw)
    return d


def CH(*pairs):
    return [list(p) for p in pairs]


BTN = CH(("left", "Left flipper"), ("right", "Right flipper"), ("action", "Action button"))
PER_S = dict(min=0, max=500, step=1, unit="/s")


# ---- the starters ---------------------------------------------------------------------------------------
def _meter_hud(st, value):
    return {"id": st.id("meter_bar"), "part": "meter", "x": 380, "y": 120, "w": 600, "h": 28, "value": value,
            "look": "bar", "colour": "#f2c14e", "accent": "#f0705f"}


def _timer_hud(st):
    return {"id": st.id("clock"), "part": "timer", "x": 28, "y": 56, "font": "hud", "colour": "#ffffff"}


def _combo_hud(st):
    return {"id": st.id("combo"), "part": "combo", "x": 1120, "y": 18, "font": "hud", "colour": "#f2c14e"}


def starter_mash(st):
    m = st.value("power", start=0, min=0, max=100)
    return st.done({
        "id": "mash", "kind": "mash", "title": "Mash it!", "objective": "Hit Action as fast as you can", "length_s": 10,
        "settings": {"meter": m, "button": "action", "per_press": 6, "drain_per_s": 15, "goal": 100},
        "win": [{"when": "goal"}], "lose": [{"when": "time_up"}]}, hud=[_meter_hud(st, m), _timer_hud(st)])


def starter_alternate(st):
    m = st.value("charge", start=0, min=0, max=100)
    return st.done({
        "id": "alternate", "kind": "alternate", "title": "Full power", "objective": "Left, right, left, right!", "length_s": 10,
        "settings": {"meter": m, "per_pair": 8, "drain_per_s": 12, "start_side": "either", "goal": 100},
        "win": [{"when": "goal"}], "lose": [{"when": "time_up"}]}, hud=[_meter_hud(st, m), _timer_hud(st)])


def starter_tug(st):
    m = st.value("pull", start=50, min=0, max=100)
    return st.done({
        "id": "tug", "kind": "tug", "title": "Pull away!", "objective": "Hold the flipper it names and mash Action", "length_s": 40,
        "settings": {"meter": m, "hold": "shown", "switch_every_s": 4, "per_press": 2, "pull_back_per_s": 8,
                     "shake_every_s": 5, "shake_pairs": 4, "goal": 100},
        "win": [{"when": "goal"}], "lose": [{"when": "time_up"}]}, hud=[_meter_hud(st, m), _timer_hud(st)])


RHYTHM_BPM, RHYTHM_BARS = 120, 24


def starter_rhythm(st):
    music = st.id("beat")
    fname = "sound/%s_%d.wav" % (music, RHYTHM_BPM)
    st.sound(music, file=fname, role="music", volume=0.8, loop=False)
    st.files[fname] = ["beat", {"bpm": RHYTHM_BPM, "beats": 4 + RHYTHM_BARS * 4 + 8}]
    return st.done({
        "id": "rhythm", "kind": "rhythm", "title": "On the beat", "objective": "Press each button as it reaches the line",
        "settings": {"music": music, "tempo_bpm": RHYTHM_BPM, "offset_ms": 0, "travel_beats": 2, "perfect_ms": 45,
                     "good_ms": 100, "chart": rhythm_chart(RHYTHM_BARS)},
        "win": [{"when": "accuracy", "value": 70}], "lose": [{"when": "misses", "value": 16}]}, hud=[_combo_hud(st)])


def starter_sequence(st):
    return st.done({
        "id": "sequence", "kind": "sequence", "title": "Remember it", "objective": "Watch the run, then enter it",
        "settings": {"length": 4, "shown": False, "flash_s": 2, "per_press_s": 1.5, "rounds": 3},
        "win": [{"when": "goal"}], "lose": [{"when": "misses", "value": 3}]}, hud=[_combo_hud(st)])


def starter_dodge(st):
    return st.done({
        "id": "dodge", "kind": "dodge", "title": "Dodge!", "objective": "Press the button it warns you of",
        "settings": {"buttons": ["left", "right", "action"], "tell_s": 0.8, "window_s": 0.6, "count": 8},
        "win": [{"when": "goal"}], "lose": [{"when": "misses", "value": 3}]},
        hud=[_combo_hud(st)])


def starter_shield(st):
    return st.done({
        "id": "shield", "kind": "shield", "title": "Shields up", "objective": "Hold Action while each attack lasts",
        "settings": {"button": "action", "tell_s": 0.8, "hold_s": 1.2, "count": 5},
        "win": [{"when": "goal"}], "lose": [{"when": "misses", "value": 3}]}, hud=[_combo_hud(st)])


KINDS2 = {
    "mash": {
        "label": "Mash", "group": GROUP2,
        "blurb": "Hit a button as fast as you can to fill a meter before it drains, or before a rival fills theirs.",
        "buttons": {"left": "", "right": "", "action": "Mash"}, "curve": False, "starter": starter_mash,
        "settings": [
            S("meter", "Meter", "value", None, "The meter the presses fill."),
            S("button", "Button", "button", "action", "The button to mash.", choices=BTN),
            S("per_press", "Each press adds", "number", 6, "How much one press fills.", min=0, max=100, step=0.5),
            S("drain_per_s", "Drains", "number", 15, "How much the meter loses every second.", **PER_S),
            S("goal", "Goal", "number", 100, "Fill it to here to win.", min=1, max=10000, step=1),
            S("rival_per_s", "Rival", "number", 0, "A rival filling its own bar this fast; first to the goal wins. 0: no rival.",
              advanced=True, **PER_S),
        ]},
    "alternate": {
        "label": "Alternate", "group": GROUP2,
        "blurb": "Left, right, left, right: each pair of flipper presses charges the meter.",
        "buttons": {"left": "Left", "right": "Right", "action": ""}, "curve": False, "starter": starter_alternate,
        "settings": [
            S("meter", "Meter", "value", None, "The meter each left and right pair fills."),
            S("per_pair", "Each pair adds", "number", 8, "How much one left and right pair fills.", min=0, max=100, step=0.5),
            S("drain_per_s", "Drains", "number", 12, "How much the meter loses every second.", **PER_S),
            S("start_side", "Start with", "choice", "either", "Which flipper the run must start on.",
              choices=CH(("either", "Either flipper"), ("left", "Left flipper"), ("right", "Right flipper"))),
            S("goal", "Goal", "number", 100, "Fill it to here to win.", min=1, max=10000, step=1),
        ]},
    "tug": {
        "label": "Tug of war", "group": GROUP2,
        "blurb": "Hold the flipper the screen names and mash Action to pull away, and shake off what grabs you with left, right, left, right.",
        "buttons": {"left": "Hold, or shake", "right": "Hold, or shake", "action": "Pull"}, "curve": False, "starter": starter_tug,
        "settings": [
            S("meter", "Meter", "value", None, "The tug: full wins, empty loses. It starts part way up."),
            S("hold", "Hold", "choice", "shown", "The flipper to hold while pulling.",
              choices=CH(("shown", "The one the screen names"), ("left", "Always the left"), ("right", "Always the right"))),
            S("switch_every_s", "Switches every", "seconds", 4, "How often the named flipper changes sides.", min=0, max=60, step=0.5),
            S("per_press", "Each pull adds", "number", 2, "How much one Action press pulls while the named flipper is held.",
              min=0, max=100, step=0.5),
            S("pull_back_per_s", "Pulls back", "number", 8, "How much the other side pulls back every second; twice that while it has you.", **PER_S),
            S("shake_every_s", "Grabbed every", "seconds", 5, "How often the second threat takes hold. 0: never.", min=0, max=60, step=0.5),
            S("shake_pairs", "Shake off with", "int", 4, "Left and right pairs it takes to shake it off.", min=0, max=50),
            S("goal", "Goal", "number", 100, "Pull it to here to win.", min=1, max=10000, step=1),
        ]},
    "rhythm": {
        "label": "Rhythm", "group": GROUP2,
        "blurb": "Buttons travel down to the line in time with the music; press each as it lands, for early, good or perfect.",
        "buttons": {"left": "On the beat", "right": "On the beat", "action": "On the beat"}, "curve": False,
        "starter": starter_rhythm,
        "settings": [
            S("music", "Music", "music", None, "The music the chart is played to."),
            S("tempo_bpm", "Tempo", "number", 120, "Beats a minute. Tap it in on the music, or leave it to the music's own beat grid.",
              min=30, max=300, step=0.1, unit="bpm"),
            S("offset_ms", "First beat at", "number", 0, "Where the first beat falls in the music.", min=-2000, max=2000, step=1, unit="ms"),
            S("travel_beats", "Notes show", "number", 2, "How many beats ahead a note appears.", min=0.5, max=16, step=0.5, unit="beats"),
            S("perfect_ms", "Perfect within", "number", 45, "A press this close to the beat is perfect.", min=0, max=500, step=5, unit="ms"),
            S("good_ms", "Good within", "number", 100, "A press this close is good; up to twice this is early or late.",
              min=0, max=500, step=5, unit="ms"),
            S("chart", "Chart", "list", [], "The notes: on which beat, which button, and how many beats to hold it.",
              fields=["beat", {"name": "button", "type": "button"}, "hold_beats"]),
        ]},
    "sequence": {
        "label": "Button sequence", "group": GROUP2,
        "blurb": "A run of left, right and Action to enter in time, shown on screen or flashed once to remember.",
        "buttons": {"left": "In the run", "right": "In the run", "action": "In the run"}, "curve": False,
        "starter": starter_sequence,
        "settings": [
            S("buttons", "Run", "buttons", [], "A fixed run of buttons; leave it empty for a new random run each play."),
            S("length", "Random length", "int", 4, "How many buttons a random run starts with; it grows one a round.", min=1, max=32),
            S("shown", "Stays shown", "bool", False, "On: the run stays on screen. Off: it flashes, then you enter it from memory."),
            S("flash_s", "Flashed for", "seconds", 2, "How long the run shows before it hides.", min=0, max=30, step=0.25),
            S("per_press_s", "Time a press", "seconds", 1.5, "How long you have for each button.", min=0.2, max=10, step=0.1),
            S("rounds", "Rounds", "int", 3, "Runs to get right to win.", min=1, max=20),
        ]},
    "dodge": {
        "label": "Quick dodge", "group": GROUP2,
        "blurb": "A warning shows where it comes from, then press that button in a short window; too early, too late or the wrong one is a hit.",
        "buttons": {"left": "Dodge", "right": "Dodge", "action": "Dodge"}, "curve": False, "starter": starter_dodge,
        "settings": [
            S("buttons", "Buttons", "buttons", ["left", "right", "action"], "The buttons a warning may name."),
            S("tell_s", "Warning for", "seconds", 0.8, "How long the warning shows before the window opens.", min=0, max=5, step=0.05),
            S("window_s", "Window", "seconds", 0.6, "How long there is to press.", min=0.05, max=10, step=0.05),
            S("count", "Attacks", "int", 8, "Attacks to get through.", min=1, max=99),
        ]},
    "shield": {
        "label": "Hold shield", "group": GROUP2,
        "blurb": "A warning, then hold the button for as long as the attack lasts; let go early and it lands.",
        "buttons": {"left": "", "right": "", "action": "Hold"}, "curve": False, "starter": starter_shield,
        "settings": [
            S("button", "Button", "button", "action", "The button that holds the shield up.", choices=BTN),
            S("tell_s", "Warning for", "seconds", 0.8, "How long the warning shows before the attack.", min=0, max=5, step=0.05),
            S("hold_s", "Hold for", "seconds", 1.2, "How long each attack lasts.", min=0.05, max=30, step=0.05),
            S("count", "Attacks", "int", 5, "Attacks to block.", min=1, max=99),
        ]},
}


# ---- a mode of one kind, as the picker makes it (the catalog's add_phase does this for any document) ---------
class _Starter:
    """The catalog's starter builder, as much of it as these starters use (ids unique in a new mode)."""

    def __init__(self):
        self.taken, self.ids, self.values, self.sounds, self.files = set(), {}, [], [], {}

    def id(self, want):
        if want not in self.ids:
            got, n = want, 2
            while got in self.taken:
                got, n = "%s_%d" % (want, n), n + 1
            self.taken.add(got)
            self.ids[want] = got
        return self.ids[want]

    def value(self, vid, **kw):
        v = {"id": self.id(vid), "type": "meter"}
        v.update(kw)
        self.values.append(v)
        return v["id"]

    def sound(self, sid, **fields):
        s = {"id": self.id(sid)}
        s.update(fields)
        self.sounds.append(s)
        return s["id"]

    def done(self, phase, hud=()):
        phase["id"] = self.id(phase["id"])
        return {"pictures": [], "things": [], "values": self.values, "phase": phase, "hud": list(hud), "art": {},
                "sounds": self.sounds, "files": self.files}


BASE_FONTS = [{"id": "hud", "face": "card:default", "size": 28}, {"id": "big", "face": "card:default", "size": 64}]


def base_hud():
    return [{"id": "hp", "part": "health", "x": 28, "y": 22, "w": 180, "h": 22, "look": "pips", "colour": "#5ee07a"},
            {"id": "progress", "part": "progress", "x": 380, "y": 22, "w": 600, "h": 6, "colour": "#e9eae7"},
            {"id": "score", "part": "score", "x": 1332, "y": 18, "font": "hud", "colour": "#ffffff"},
            {"id": "prompts", "part": "prompts", "x": 0, "y": 728, "w": 1360, "h": 40, "look": "glyphs"},
            {"id": "callout", "part": "callout", "x": 680, "y": 200, "font": "big", "colour": "#f2c14e", "accent": "#1b1d1f"}]


def new_doc(kind, slug=None, title=None):
    """A whole mode of one ``kind`` phase; (doc, files to write beside it)."""
    st = KINDS2[kind]["starter"](_Starter())
    doc = document.new(slug or "%s-starter" % kind, title or KINDS2[kind]["label"])
    doc["stage"]["background"] = "#05080f"
    doc["assets"] = {"pictures": [], "fonts": copy.deepcopy(BASE_FONTS)}
    if st.get("sounds"):
        doc["assets"]["sounds"] = st["sounds"]
    if st["values"]:
        doc["values"] = st["values"]
    ph = st["phase"]
    doc["hud"] = base_hud() + [dict(h, phases=[ph["id"]]) for h in st["hud"]]
    doc["phases"] = [ph]
    doc["flow"]["cards"][0]["phase"] = ph["id"]
    return doc, st.get("files", {})


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
