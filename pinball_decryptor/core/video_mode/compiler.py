"""The video mode compiler (PAD-1657): video_mode.json -> the packed form the engine reads.

The engine (engine/vm_engine.c) reads only this packed form: ids resolved to indexes,
seconds to steps (60 a second), pixels a second to 16.16 fixed point a step, colours to
0xRRGGBBAA, the chase's lanes and every path's length worked out here. So the C side
never parses JSON or does float arithmetic, and the same pack plays bit-identically on the
machine, in WebAssembly and in the tests.

    result = compile_doc(doc, mode_dir)
    result.problems   every reason it cannot be played, "place: what" in plain words
    result.notes      what plays differently from the document today (not errors)
    result.pack       the bytes (None when there are problems)

The pack's layout is the engine's vm_load; the codes below mirror vm_engine.h's enums
(tests/test_video_mode_engine.py holds the two together).
"""
import math
import os
import struct

from . import document
from . import feel
from . import sound as SND

ONE = 65536
SPS = 60
NONE = -0x80000000
PACK_MAGIC = 0x31504D56
PACK_VERSION = 3                 # 2 (PAD-1667): a phase's music fade, a cue's fade; 3 (PAD-1666): the HUD's looks
                                 # and text styles, fonts' outline and gradient glyphs, particles, the feel
END_MAGIC = 0x21444E45
FONT_ATLAS_BASE = 1000      # placeholder glyph atlases sit after the pictures' (PAD-1658 packs both)
GLYPHS = 95

# ---- codes shared with vm_engine.h (same order) ----
TEAMS = ["player", "enemy", "enemy_shot", "player_shot", "pickup", "health", "scenery"]
MOVERS = ["none", "straight", "lanes", "free", "thrust", "path", "home", "scroll", "orbit"]
EASINGS = ["linear", "in", "out", "in_out", "back_out", "bounce_out", "elastic_out", "step"]
KINDS = ["chase", "thrust", "aim", "boss", "mash", "alternate", "tug", "rhythm", "sequence",
         "dodge", "shield", "timing", "defend", "catch", "runner", "lander", "route", "pick", "custom"]
WHENS = ["time_up", "survive_s", "score", "kills", "pickups", "goal", "health_gone", "misses",
         "boss_down", "hits", "accuracy", "ammo_out", "landed", "crashed", "cashed_out", "busted"]
CARDS = ["clip", "phase", "end"]
HUD_PARTS = ["health", "meter", "score", "combo", "timer", "lives", "progress", "prompts",
             "callout", "counter", "text", "multiplier", "popup"]
ALIGNS = ["auto", "left", "centre", "right"]
LOOKS = ["default", "bar", "pips", "hearts", "ring", "number", "glyphs"]
TRANSITIONS = ["cut", "fade", "white_flash", "wipe", "iris"]
BUTTONS = ["left", "right", "action"]
CUE_ON = ["fire", "hit", "kill", "pickup", "hurt", "prompt_good", "prompt_perfect", "prompt_miss",
          "phase_start", "phase_won", "phase_lost", "won", "lost"]
SKIP_CLIPS = ["none", "double_flip", "action"]
# the fixed strings, in the engine's VM_S_* order
FIXED_STRINGS = ["CLEAR!", "FAILED", "TRY AGAIN", "< STEER >", "ACTION  FIRE", "LEFT", "RIGHT",
                 "ACTION", "MASH ACTION!", "BOSS DOWN!", "HOLD ACTION",
                 "UP", "DOWN", "FIRE", "THRUST", "MOVE"]
PLAYED_KINDS = {"chase", "thrust", "boss", "mash", "alternate", "custom"}
UNPLAYED_WHENS = {"accuracy", "landed", "cashed_out", "busted"}

# ---- the engine's table sizes (vm_engine.h VM_MAX_*) ----
LIMITS = {
    "strings": 256, "string_bytes": 8192, "fonts": 8, "pictures": 96, "animations": 192,
    "frames": 2048, "values": 48, "things": 96, "movers": 192, "path_points": 1024,
    "phases": 32, "layers": 128, "places": 1024, "spawns": 256, "conditions": 256,
    "weak_points": 64, "attacks": 64, "cards": 96, "hud": 64, "cues": 64, "particles": 20, "sounds": 64,
    "clips": 32, "tracks": 256, "keys": 4096, "curves": 128, "timed_sounds": 256,
}
CURVE_PTS = 33
TRACK_PROPS = ["motion", "scale", "turn", "alpha", "tint"]
LIMIT_WORDS = {
    "strings": "texts", "string_bytes": "bytes of text", "fonts": "fonts", "pictures": "pictures",
    "animations": "animations", "frames": "animation frames", "values": "values", "things": "things",
    "movers": "movers", "path_points": "path points", "phases": "phases",
    "layers": "background layers", "places": "placed things", "spawns": "spawns",
    "conditions": "win and lose conditions", "weak_points": "weak points", "attacks": "boss attacks",
    "cards": "storyboard cards", "hud": "HUD parts", "particles": "particle kinds", "cues": "sound cues", "sounds": "sounds",
    "clips": "clips", "tracks": "timeline tracks", "keys": "keyframes", "curves": "easing curves of their own",
    "timed_sounds": "sounds on the timeline",
}


class Compiled:
    def __init__(self, pack=None, problems=(), notes=(), names=None):
        self.pack = pack
        self.problems = list(problems)
        self.notes = list(notes)
        self.names = names or {}     # the index -> id tables, for the harness's words

    @property
    def ok(self):
        return self.pack is not None and not self.problems


def fx(v):
    return int(round(float(v) * ONE))


def per_step(px_s):
    return int(round(float(px_s) * ONE / SPS))


def per_step2(px_s2):
    return int(round(float(px_s2) * ONE / (SPS * SPS)))


def steps(seconds):
    return int(round(float(seconds) * SPS))


def colour(c, default=0xFFFFFFFF):
    if not isinstance(c, str) or not c.startswith("#"):
        return default
    h = c[1:]
    if len(h) == 6:
        h += "ff"
    try:
        return int(h, 16)
    except ValueError:
        return default


def bake_curve(c):
    """A CSS cubic-bezier(x1, y1, x2, y2) as CURVE_PTS heights (16.16) at even steps across 0..1: the engine reads
    it straight between them, so the C side never solves a cubic (PAD-1664)."""
    x1, y1, x2, y2 = (float(v) for v in c)

    def bz(a, b, t):
        m = 1 - t
        return 3 * m * m * t * a + 3 * m * t * t * b + t * t * t

    out = []
    for i in range(CURVE_PTS):
        u = i / (CURVE_PTS - 1)
        lo, hi = 0.0, 1.0
        for _ in range(60):             # x(t) rises with t when x1, x2 are within 0..1
            mid = (lo + hi) / 2
            if bz(x1, x2, mid) < u:
                lo = mid
            else:
                hi = mid
        y = bz(y1, y2, (lo + hi) / 2)
        out.append(max(-2 * ONE, min(3 * ONE, int(round(y * ONE)))))
    out[0], out[-1] = 0, ONE
    return out


def png_size(path):
    """(w, h) from a PNG's header, or None."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


class _Pack:
    def __init__(self):
        self.w = []

    def put(self, *vals):
        for v in vals:
            v = int(v)
            if v > 0x7FFFFFFF:
                v -= 1 << 32
            if not -0x80000000 <= v <= 0x7FFFFFFF:
                raise OverflowError(v)
            self.w.append(v)

    def table(self, rows):
        self.put(len(rows))
        for r in rows:
            self.put(*(r if isinstance(r, (list, tuple)) else [r]))


def placeholder_font(size, index):
    """Monospace metrics until PAD-1658 bakes the real face: a glyph a cell of a 16-wide grid."""
    adv = fx(size * 0.6)
    cell_w = max(1, int(round(size * 0.6)))
    glyphs = []
    for i in range(GLYPHS):
        c = 32 + i
        if c == 32:
            glyphs.append((adv, 0, 0, 0, 0, 0, 0, -1, -1, 0, 0, -1, -1))
        else:
            glyphs.append((adv, 0, 0, (i % 16) * cell_w, (i // 16) * size, cell_w, size, -1, -1, 0, 0, -1, -1))
    return {"size": size, "line_h": fx(size * 1.25), "atlas": FONT_ATLAS_BASE + index, "texel": ONE, "ow": 0,
            "glyphs": glyphs}


def compile_doc(doc, mode_dir=None, sizes=None, fonts=None):
    """Compile a document (already migrated to the current format).

    sizes: {picture id: (w, h)} of each picture file, when known; otherwise read from the
    PNG in mode_dir, else a placeholder size (noted). fonts: {font id: metrics} from the
    font packer (PAD-1658); otherwise monospace placeholder metrics."""
    try:
        doc = document.migrate(doc)
    except document.VideoModeError as e:
        return Compiled(problems=e.problems)
    probs = document.check(doc)
    if probs:
        return Compiled(problems=probs)
    return _Compiler(doc, mode_dir, sizes or {}, fonts or {}).run()


def compile_file(path, sizes=None, fonts=None):
    try:
        doc = document.load(path)
    except document.VideoModeError as e:
        return Compiled(problems=e.problems)
    return compile_doc(doc, os.path.dirname(os.path.abspath(path)), sizes, fonts)


class _Compiler:
    def __init__(self, doc, mode_dir, sizes, fonts):
        self.doc = doc
        self.mode_dir = mode_dir
        self.sizes = sizes
        self.fonts_in = fonts
        self.problems = []
        self.notes = []
        self.strings = list(FIXED_STRINGS)
        self.movers = []
        self.path = []

    def where(self, path, what):
        return "%s: %s" % (document.place(path, self.doc), what)

    def note(self, path, what):
        self.notes.append(self.where(path, what))

    def problem(self, path, what):
        self.problems.append(self.where(path, what))

    def string(self, s):
        s = s or ""
        if s in self.strings:
            return self.strings.index(s)
        self.strings.append(s)
        return len(self.strings) - 1

    # ---- the pieces ----
    def run(self):
        d = self.doc
        a = d.get("assets", {})
        self.pics = a.get("pictures", [])
        self.pic_ix = {p["id"]: i for i, p in enumerate(self.pics)}
        self.sound_ix = {s["id"]: i for i, s in enumerate(a.get("sounds", []))}
        self.sound_by_id = {s["id"]: s for s in a.get("sounds", [])}
        self.clip_ix = {c["id"]: i for i, c in enumerate(a.get("clips", []))}
        self.font_list = a.get("fonts", [])
        self.font_ix = {f["id"]: i for i, f in enumerate(self.font_list)}
        self.values = d.get("values", [])
        self.value_ix = {v["id"]: i for i, v in enumerate(self.values)}
        self.things = d.get("things", [])
        self.kind_ix = {t["id"]: i for i, t in enumerate(self.things)}
        self.phases = d.get("phases", [])
        self.phase_ix = {p["id"]: i for i, p in enumerate(self.phases)}
        flow = d.get("flow", {})
        self.cards = flow.get("cards", [])
        self.card_ix = {c["id"]: i for i, c in enumerate(self.cards)}

        fonts = self.build_fonts()
        pics, anims, frames = self.build_pictures()
        values = self.build_values()
        self.build_emitters()
        kinds = self.build_kinds()
        phases, layers, places, spawns, conds, settings, weak, atk = self.build_phases()
        cards = self.build_cards()
        hud, callout_font, title_font = self.build_hud(fonts)
        cues = self.build_cues()
        self.check_limits(fonts, pics, anims, frames, values, kinds, phases, layers, places, spawns,
                          conds, weak, atk, cards, hud, cues)
        for k, n in (("tracks", len(self.tracks)), ("keys", len(self.keys)), ("curves", len(self.curves)),
                     ("timed_sounds", len(self.tsnds))):
            if n > LIMITS[k]:
                self.problems.append("the document has %d %s; the engine holds up to %d" % (n, LIMIT_WORDS[k], LIMITS[k]))
        if self.problems:
            return Compiled(problems=self.problems, notes=self.notes)

        st = d.get("style", {})
        style = feel.style_bits(st)
        stage = d.get("stage", {})
        p = _Pack()
        p.put(PACK_MAGIC, PACK_VERSION, 0)
        p.put(SPS, stage.get("width", 1360), stage.get("height", 768), colour(stage.get("background"), 0x000000FF),
              int(d.get("seed", 1)) & 0x7FFFFFFF, style, TRANSITIONS.index(st.get("transition", "cut")),
              SKIP_CLIPS.index(d.get("entry", {}).get("skip_clips", "none")),
              int(d.get("levels", {}).get("speed_step_pct", 0)), self.card_ix[flow["start"]],
              len(self.sound_ix), len(self.clip_ix), callout_font, title_font)
        p.put(*self.bursts)
        p.put(*(feel.style_numbers(st) + feel.combo_numbers(d)))
        p.put(len(self.strings))
        for s in self.strings:
            b = s.encode("utf-8")
            p.put(len(b))
            b += b"\0" * (-len(b) % 4)
            for i in range(0, len(b), 4):
                p.put(struct.unpack("<I", b[i:i + 4])[0])
        p.put(len(fonts))
        for f in fonts:
            p.put(f["size"], f["line_h"], f["atlas"], f["texel"], f.get("ow", 0))
            for g in f["glyphs"]:
                p.put(*g)
        for t in (pics, anims, frames, values, kinds, self.movers, self.path, phases, layers, places,
                  spawns, conds, settings, weak, atk, cards, hud, cues, self.emitters, self.tracks, self.keys, self.curves,
                  self.tsnds):
            p.table(t)
        p.put(END_MAGIC)
        p.w[2] = len(p.w)
        pack = struct.pack("<%di" % len(p.w), *p.w)
        names = {"things": [t["id"] for t in self.things], "phases": [ph["id"] for ph in self.phases],
                 "sounds": list(self.sound_ix), "clips": list(self.clip_ix),
                 "pictures": [pc["id"] for pc in self.pics], "values": [v["id"] for v in self.values],
                 "fonts": fonts, "place0": [ph[7] for ph in phases], "track_keys": self.track_keys,
                 "emitters": sorted(self.emit_ix, key=self.emit_ix.get)}
        return Compiled(pack, [], self.notes, names)

    def build_fonts(self):
        out = []
        for i, f in enumerate(self.font_list):
            m = self.fonts_in.get(f["id"]) or placeholder_font(int(round(f.get("size", 28))), i)
            out.append(m)
        if not out:
            out.append(placeholder_font(28, 0))
        return out

    def build_pictures(self):
        pics, anims, frames = [], [], []
        self.anim_ix = {}
        for i, pc in enumerate(self.pics):
            where = ["assets", "pictures", i]
            size = self.sizes.get(pc["id"])
            if size is None and self.mode_dir and pc.get("file"):
                size = png_size(os.path.join(self.mode_dir, pc["file"]))
            n = int(pc.get("frames", 1))
            if pc.get("frame_w"):
                fw, fh = int(pc["frame_w"]), int(pc.get("frame_h", pc["frame_w"]))
                cols = max(1, size[0] // fw) if size else n
                if size and cols * fw > size[0]:
                    cols = 1
                if size and ((n + cols - 1) // cols) * fh > size[1]:
                    self.problem(where, "the sheet is %dx%d but %d frames of %dx%d do not fit in it" % (size[0], size[1], n, fw, fh))
            elif size:
                fw, fh, cols = int(size[0]), int(size[1]), 1
            else:
                hb = pc.get("hitbox") or {}
                if hb.get("shape") == "circle":
                    fw = fh = int(round(2 * hb.get("r", 32)))
                elif hb.get("shape") == "box":
                    fw, fh = int(round(hb.get("w", 64))), int(round(hb.get("h", 64)))
                else:
                    fw, fh = 64, 64
                fw, fh, cols = max(1, fw), max(1, fh), 1
                self.note(where, "no picture file yet, so it is drawn as a %dx%d placeholder" % (fw, fh))
            anchor = pc.get("anchor", [0.5, 0.5])
            pics.append([i, fw, fh, cols, n, 0, 0, fx(anchor[0]), fx(anchor[1]), ONE] + self.hitbox(pc.get("hitbox")))
            first_anim = len(anims)
            for j, an in enumerate(pc.get("animations", [])):
                fr = [int(x) for x in an.get("frames", [0])]
                bad = [x for x in fr if x >= n]
                if bad:
                    self.problem(where + ["animations", j], "frame %d is past the sheet's %d frames" % (bad[0], n))
                self.anim_ix[(pc["id"], an["id"])] = len(anims)
                anims.append([fx(an.get("fps", 12)), 1 if an.get("loop", True) else 0, len(frames), max(1, len(fr))])
                frames.extend(fr or [0])
            del first_anim
        return pics, anims, frames

    @staticmethod
    def hitbox(h):
        if not h:
            return [-1, 0, 0, 0, 0]
        if h.get("shape") == "circle":
            return [1, fx(h.get("x", 0)), fx(h.get("y", 0)), fx(h.get("r", 0)), 0]
        return [0, fx(h.get("x", 0)), fx(h.get("y", 0)), fx(h.get("w", 0)), fx(h.get("h", 0))]

    def build_values(self):
        out = []
        for v in self.values:
            lo, hi = v.get("min", 0), v.get("max", 100 if v.get("type", "meter") == "meter" else 999999)
            start = min(max(v.get("start", lo), lo), hi)
            out.append([0 if v.get("type", "meter") == "meter" else 1, fx(start), fx(lo), fx(hi),
                        per_step(v.get("drain_per_s", 0))])
        return out

    def mover(self, m, where):
        """A mover record's index, or -1."""
        if not m:
            return -1
        t = m.get("type", "none")
        speed = m.get("speed", 0)
        path0, npath, turn, radius = len(self.path), 0, 0, 0
        if t == "path":
            pts = m.get("path", [])
            if len(pts) < 2:
                self.problem(where + ["path"], "a path needs at least two points")
                return -1
            cum = 0.0
            for k, pt in enumerate(pts):
                if k:
                    cum += math.hypot(pt[0] - pts[k - 1][0], pt[1] - pts[k - 1][1])
                self.path.append([fx(pt[0]), fx(pt[1]), fx(cum)])
            npath = len(pts)
            if cum <= 0:
                self.problem(where + ["path"], "every point of the path is in the same place")
        elif t == "home":
            turn = fx(m.get("turn_per_s", 90) / SPS)
        elif t == "orbit":
            r = float(m.get("radius", 0))
            radius = fx(r)
            turn = fx(math.degrees(speed / r) / SPS) if r > 0 else 0
        rec = [MOVERS.index(t), per_step(speed), fx(m.get("direction", 0)), path0, npath,
               EASINGS.index(m.get("easing", "linear")), 1 if m.get("loop") else 0,
               self.kind_ix.get(m.get("target"), -1), turn, radius]
        self.movers.append(rec)
        return len(self.movers) - 1

    def build_kinds(self):
        out = []
        counters = {v["id"]: i for i, v in enumerate(self.values) if v.get("type") == "counter"}
        for i, t in enumerate(self.things):
            pc = t["picture"]
            anim = self.anim_ix.get((pc, t["animation"]), -1) if t.get("animation") else -1
            counter = -1
            if t.get("team") == "pickup":   # a counter named after the pickup counts it (crate -> crates)
                counter = counters.get(t["id"] + "s", counters.get(t["id"], -1))
            out.append([self.pic_ix[pc], anim, fx(t.get("scale", 1)), TEAMS.index(t.get("team", "scenery")),
                        int(t.get("health", 0)), int(t.get("points", 0)),
                        1 if t.get("blend") == "add" else 0, int(t.get("depth", 0)),
                        self.mover(t.get("mover"), ["things", i, "mover"]), counter] + self.hitbox(t.get("hitbox"))
                       + self.trail(t.get("trail"), ["things", i, "trail"]))
        return out

    # ---- the feel (PAD-1666) ----
    def emitter(self, name, where):
        """The emitter a burst or trail names: a particle of the document's, else a preset; -1 for none."""
        if not name or name == "none":
            return -1
        if name in self.emit_ix:
            return self.emit_ix[name]
        spec = self.particles.get(name)
        if spec is None and name not in feel.PARTICLE_PRESETS:
            self.problem(where, "names a particle the document does not have: %s" % name)
            return -1
        p = feel.particle(spec if spec is not None else name)
        pic = self.pic_ix.get(p.get("picture"), -1) if p.get("picture") else -1
        if p.get("picture") and pic < 0:
            self.problem(where, "the particle %s names a picture the document does not have: %s" % (name, p["picture"]))
        self.emitters.append(feel.emitter_row(p, pic))
        self.emit_ix[name] = len(self.emitters) - 1
        return self.emit_ix[name]

    def build_emitters(self):
        self.particles = {p["id"]: p for p in (self.doc.get("assets") or {}).get("particles") or []}
        self.emitters, self.emit_ix = [], {}
        for pid in self.particles:      # the document's own first, in order, so the editor's index is theirs
            self.emitter(pid, ["assets", "particles"])
        for name in feel.PRESET_NAMES:  # then every preset, so the editor can preview any (16 words each)
            self.emitter(name, ["style"])
        bursts = dict(feel.DEFAULT_BURSTS)
        bursts.update((self.doc.get("style") or {}).get("bursts") or {})
        self.bursts = [self.emitter(bursts.get(k), ["style", "bursts", k]) for k in feel.BURSTS]

    def trail(self, tr, where):
        if not tr or not tr.get("particles"):
            return [-1, 0]
        return [self.emitter(tr["particles"], where), max(1, min(600, steps(tr.get("every_s", 0.1)) or 1))]

    def lane_band(self, ph):
        """The chase's rows: from the lowest background layer's top to the stage's bottom."""
        h = self.doc.get("stage", {}).get("height", 768)
        ys = [float(l.get("y", 0)) for l in ph.get("background", []) if float(l.get("y", 0)) > 0]
        top = max(ys) if ys else h / 2.0
        return fx(top), fx(h)

    def cond(self, c):
        of = c.get("of")
        return [WHENS.index(c["when"]),
                steps(c.get("value", 0)) if c["when"] == "survive_s" else int(round(c.get("value", 0))),
                self.kind_ix.get(of, -1) if of in self.kind_ix else -1,
                self.value_ix.get(of, -1) if of in self.value_ix and of not in self.kind_ix else -1]

    def build_tracks(self, ph, where, kind):
        """PAD-1664: the phase's timeline into the track, key, curve and timed sound tables."""
        stage = self.doc.get("stage", {})
        W, H = float(stage.get("width", 1360)), float(stage.get("height", 768))
        player = (ph.get("settings") or {}).get("player") if kind in ("chase", "thrust") else None
        places = ph.get("place", [])
        t0, tk = len(self.tracks), []
        for n, tr in enumerate(ph.get("tracks", [])):
            tw = where + ["tracks", n]
            prop = tr["prop"]
            if prop == "motion" and tr["place"] < len(places) and places[tr["place"]].get("thing") == player:
                self.note(tw, "moves the phase's player by keys: its steering does nothing while the keys run")
            k0 = len(self.keys)
            tk.append(k0)
            for j, key in enumerate(tr["keys"]):
                ease, curve = EASINGS.index(key.get("ease", "linear")), -1
                if key.get("curve"):
                    baked = bake_curve(key["curve"])
                    t = tuple(baked)
                    if t not in self.curve_ix:
                        self.curve_ix[t] = len(self.curves)
                        self.curves.append(baked)
                    curve = self.curve_ix[t]
                a = b = ox = oy = ix = iy = 0
                if prop == "motion":
                    x, y = float(key["x"]), float(key["y"])
                    if not (-W <= x <= 2 * W and -H <= y <= 2 * H):
                        self.problem(tw + ["keys", j], "is %g, %g: more than a stage's width or height off the stage, "
                                                       "past where the engine keeps things" % (x, y))
                    a, b = fx(x), fx(y)
                    ox, oy = (fx(v) for v in key.get("out", (0, 0)))
                    ix, iy = (fx(v) for v in key.get("in", (0, 0)))
                elif prop == "tint":
                    a = colour(key["tint"])
                    a = a - (1 << 32) if a >= 1 << 31 else a
                else:
                    a = fx(key["v"])
                self.keys.append([steps(key["at_s"]), a, b, ease, curve, ox, oy, ix, iy])
            self.tracks.append([tr["place"], TRACK_PROPS.index(prop), k0, len(self.keys) - k0])
        s0 = len(self.tsnds)
        for ts in ph.get("sound_track", []):
            self.tsnds.append([steps(ts["at_s"]), self.sound_ix[ts["sound"]]])
        self.track_keys.append(tk)
        return [t0, len(self.tracks) - t0, s0, len(self.tsnds) - s0]

    def build_phases(self):
        phases, layers, places, spawns, conds, settings, weak, atk = [], [], [], [], [], [], [], []
        self.tracks, self.keys, self.curves, self.curve_ix, self.tsnds, self.track_keys = [], [], [], {}, [], []
        for i, ph in enumerate(self.phases):
            where = ["phases", i]
            kind = ph["kind"]
            s = ph.get("settings", {})
            if kind not in PLAYED_KINDS:
                self.note(where, "a %s phase plays its things, spawns and conditions only for now; "
                                 "its own play comes with the game kinds (PAD-1662, PAD-1663)" % kind)
            if ph.get("rules"):
                self.note(where + ["rules"], "rule cards are kept but not played yet (PAD-1665)")
            if ph.get("bomb"):
                self.note(where + ["bomb"], "the screen-clear bomb is not played yet (PAD-1662)")
            for side in ("win", "lose"):
                for j, c in enumerate(ph.get(side, [])):
                    if c["when"] in UNPLAYED_WHENS:
                        self.note(where + [side, j], "'%s' never ends the phase until its game kind lands" % c["when"])
            rec = [0] * 32
            if kind == "chase":
                top, bot = self.lane_band(ph)
                fire = s.get("fire", "action")
                rec[0] = self.kind_ix.get(s.get("player"), -1)
                rec[1] = ["lanes", "free", "hold"].index(s.get("steer", "lanes"))
                rec[2] = int(s.get("lanes", 3))
                rec[3] = per_step(s.get("steer_speed", 1200))
                rec[4] = 1 if fire == "action" and s.get("shot") else 0
                rec[5] = self.kind_ix.get(s.get("shot"), -1)
                rec[6] = max(1, int(round(SPS / s["fire_per_s"]))) if s.get("fire_per_s") else 10
                rec[7] = int(s.get("ammo", 0))
                rec[8] = int(s.get("gears", 1))
                rec[9] = BUTTONS.index(s["gear_button"]) if s.get("gear_button") in BUTTONS else -1
                rec[10] = per_step(s.get("scroll_speed", 0))
                rec[11] = int(s.get("health", 0))
                rec[12] = steps(s.get("hurt_blink_s", 1.0))
                rec[13], rec[14] = top, bot
            elif kind == "thrust":
                rec[0] = self.kind_ix.get(s.get("player"), -1)
                rec[1] = BUTTONS.index(s.get("thrust_button", "action"))
                fb = s.get("fire_button", "none")
                rec[2] = BUTTONS.index(fb) if fb in BUTTONS and s.get("shot") else -1
                rec[3] = self.kind_ix.get(s.get("shot"), -1)
                rec[4] = int(s.get("ammo", 0))
                rec[5] = per_step2(s.get("gravity", 1800))
                rec[6] = per_step2(s.get("thrust", 3600))
                rec[7] = per_step(s.get("max_fall", 900))
                rec[8] = per_step(s.get("scroll_speed", 0))
                rec[9] = int(s.get("health", 0))
                rec[10] = 10
                rec[12] = 60
            elif kind == "boss":
                rec[0] = self.kind_ix.get(s.get("boss"), -1)
                rec[1] = 1 if s.get("hit_with", "sight") == "shots" else 0
                rec[2] = self.kind_ix.get(s.get("sight"), -1)
                rec[3] = len(weak)
                for w in s.get("weak_points", []):
                    weak.append([fx(w.get("x", 0)), fx(w.get("y", 0)), fx(w.get("r", 30)), int(w.get("hits", 1)),
                                 steps(w.get("open_s", 2)), steps(w.get("closed_s", 1)), steps(w.get("offset_s", 0))])
                rec[4] = len(weak) - rec[3]
                rec[5] = len(atk)
                for a in s.get("attacks", []):
                    atk.append([self.kind_ix[a["thing"]], steps(a.get("every_s", 3)), 0 if a.get("aim", "player") == "player" else 1])
                rec[6] = len(atk) - rec[5]
                rec[7] = int(s.get("stages", 1))
                rec[8] = per_step(900)
                shots = [k for k, t in enumerate(self.things) if t.get("team") == "player_shot"]
                rec[9] = shots[0] if shots else -1
                rec[10] = 10
                if rec[1] == 0 and rec[2] < 0:
                    self.problem(where + ["settings"], "a boss hit with the sight needs a sight thing")
                if rec[1] == 1 and rec[9] < 0:
                    self.problem(where + ["settings"], "a boss hit with shots needs a thing on the player_shot team to fire")
                if rec[4] == 0:
                    self.note(where + ["settings"], "a boss without weak points cannot be brought down")
            elif kind == "rhythm":
                # PAD-1667: the beat grid, from the phase's own tempo_bpm / offset_ms or else its music's (the kind's
                # own play is PAD-1663's): beats a minute x1000, the first beat in ms, beats a bar
                g = SND.beat_grid(self.doc, ph)
                if g:
                    rec[0], rec[1], rec[2] = int(round(g["bpm"] * 1000)), int(round(g["offset_s"] * 1000)), g["per_bar"]
            elif kind in ("mash", "alternate"):
                m = self.value_ix.get(s.get("meter"), -1)
                if m < 0:
                    self.problem(where + ["settings", "meter"], "names no value")
                    m = 0
                v = self.values[m] if self.values else {}
                drain = s.get("drain_per_s", v.get("drain_per_s", 0))
                goal = fx(s.get("goal", v.get("max", 100)))
                rec[0] = m
                if kind == "mash":
                    rec[1] = BUTTONS.index(s.get("button", "action"))
                    rec[2] = fx(s.get("per_press", 5))
                    rec[3] = per_step(drain)
                    rec[4] = goal
                    rec[5] = per_step(s.get("rival_per_s", 0))
                else:
                    rec[1] = fx(s.get("per_pair", 5))
                    rec[2] = per_step(drain)
                    rec[3] = ["left", "right", "either"].index(s.get("start_side", "either"))
                    rec[4] = goal
            settings.append(rec)
            bg0 = len(layers)
            for l in ph.get("background", []):
                layers.append([self.pic_ix[l["picture"]], per_step(l.get("speed", 0)), fx(l.get("y", 0)),
                               1 if l.get("tile") else 0, int(round(255 * float(l.get("alpha", 1))))])
            pl0 = len(places)
            stage = self.doc.get("stage", {})
            W, H = float(stage.get("width", 1360)), float(stage.get("height", 768))
            for j, pl in enumerate(ph.get("place", [])):
                if not (-W <= float(pl.get("x", 0)) <= 2 * W and -H <= float(pl.get("y", 0)) <= 2 * H):
                    self.problem(where + ["place", j], "is more than a stage's width or height off the stage, past where "
                                                      "the engine keeps things")
                places.append([self.kind_ix[pl["thing"]], fx(pl.get("x", 0)), fx(pl.get("y", 0)), fx(pl.get("scale", 1)),
                               fx(pl.get("turn", 0)), int(pl["depth"]) if "depth" in pl else NONE, 1 if pl.get("hidden") else 0])
            sp0 = len(spawns)
            for j, sp in enumerate(ph.get("spawns", [])):
                lane = int(sp["lane"]) if "lane" in sp else -1
                if lane >= 0 and kind == "chase" and lane >= int(s.get("lanes", 3)):
                    self.problem(where + ["spawns", j, "lane"], "lane %d is past the chase's %d lanes (lanes count from 0)" % (lane, int(s.get("lanes", 3))))
                spawns.append([self.kind_ix[sp["thing"]], steps(sp.get("at_s", 0)), steps(sp.get("every_s", 0)),
                               int(sp.get("count", 1)), fx(sp["x"]) if "x" in sp else NONE, fx(sp["y"]) if "y" in sp else NONE,
                               fx(sp.get("spread", 0)), lane, self.mover(sp.get("mover"), where + ["spawns", j, "mover"])])
            w0 = len(conds)
            for c in ph.get("win", []):
                conds.append(self.cond(c))
            l0 = len(conds)
            for c in ph.get("lose", []):
                conds.append(self.cond(c))
            ramp = ph.get("ramp", {})
            phases.append([KINDS.index(kind), self.string(ph.get("title", ph["id"])), self.string(ph.get("objective", "")),
                           steps(ph.get("length_s", 0)), self.sound_ix.get(SND.phase_music(ph), -1),
                           bg0, len(layers) - bg0, pl0, len(places) - pl0, sp0, len(spawns) - sp0,
                           w0, l0 - w0, l0, len(conds) - l0, 1 if ph.get("layout") == "fixed" else 0,
                           fx(ramp.get("speed_from", 1)), fx(ramp.get("speed_to", ramp.get("speed_from", 1))), i,
                           steps(SND.fade_s(self.sound_by_id.get(SND.phase_music(ph))))]
                          + self.build_tracks(ph, where, kind))
        return phases, layers, places, spawns, conds, settings, weak, atk

    def build_cards(self):
        out = []
        clips = self.doc.get("assets", {}).get("clips", [])
        for c in self.cards:
            if c["card"] == "clip":
                ci = self.clip_ix[c["clip"]]
                out.append([0, ci, self.card_ix[c["then"]], 0, 1, 1 if clips[ci].get("skippable") else 0])
            elif c["card"] == "phase":
                out.append([1, self.phase_ix[c["phase"]], self.card_ix[c["won"]], self.card_ix[c["lost"]],
                            int(c.get("tries", 1)), 0])
            else:
                out.append([2, 1 if c.get("outcome") == "won" else 0, 0, 0, 1, 0])
        return out

    def build_hud(self, fonts):
        out = []
        callout_font = title_font = -1
        sizes = [f["size"] for f in fonts]
        for n, h in enumerate(self.doc.get("hud", [])):
            mask = 0
            for pid in h.get("phases", []):
                if pid in self.phase_ix:
                    mask |= 1 << self.phase_ix[pid]
            font = self.font_ix.get(h.get("font"), -1)
            if h["part"] == "callout" and font >= 0:
                callout_font = font
            zones = []
            for z in (h.get("zones") or [])[:4]:
                a, b = sorted((float(z.get("from", 0)), float(z.get("to", 1))))
                zones += [fx(max(0.0, min(1.0, a))), fx(max(0.0, min(1.0, b))), colour(z.get("colour"), 0xF0705FFF)]
            zones += [0, 0, 0] * (4 - len(zones) // 3)
            on = 0
            for ev in h.get("on") or ([] if h["part"] != "popup" else ["kill"]):
                if ev in CUE_ON:
                    on |= 1 << CUE_ON.index(ev)
            pic = self.pic_ix.get(h.get("picture"), -1) if h.get("picture") else -1
            if h.get("picture") and pic < 0:
                self.problem(["hud", n, "picture"], "names a picture the document does not have: %s" % h["picture"])
            low = h.get("low", 0.34 if h.get("danger") else 0)
            out.append([HUD_PARTS.index(h["part"]), fx(h.get("x", 0)), fx(h.get("y", 0)), fx(h.get("w", 0)), fx(h.get("h", 0)),
                        self.value_ix.get(h.get("value"), -1), LOOKS.index(h.get("look", "default")), font,
                        colour(h.get("colour")) if h.get("colour") else 0, colour(h.get("accent")) if h.get("accent") else 0,
                        self.string(h["text"]) if h.get("text") else -1, mask,
                        ALIGNS.index(h.get("align", "auto")),
                        colour(h.get("outline")) if h.get("outline") else 0,
                        colour(h.get("shadow")) if h.get("shadow") else 0,
                        colour(h.get("gradient")) if h.get("gradient") else 0,
                        colour(h.get("danger")) if h.get("danger") else 0, fx(max(0.0, min(1.0, float(low)))),
                        ] + zones + [
                        max(0, min(600, steps(h.get("count_up", 0)))), 1 if h.get("pop") else 0, on,
                        fx(h.get("rise", 60)), max(0, min(600, steps(h.get("life_s", 0.8)))), pic])
        if callout_font < 0:
            callout_font = sizes.index(max(sizes))
        title_font = sizes.index(min(sizes))
        return out, callout_font, title_font

    def build_cues(self):
        # PAD-1667: a sound ducks the music wherever it plays when it is a callout or any cue of it says duck_music
        # (the machine ducks per call, not per event), so every cue of it carries the same flag
        duck = SND.ducks(self.doc)
        return [[CUE_ON.index(c["on"]), self.sound_ix[c["sound"]], 1 if duck.get(c["sound"]) else 0]
                for c in self.doc.get("cues", [])]

    def check_limits(self, fonts, pics, anims, frames, values, kinds, phases, layers, places, spawns,
                     conds, weak, atk, cards, hud, cues):
        have = {"strings": len(self.strings), "string_bytes": sum(len(s.encode("utf-8")) for s in self.strings),
                "fonts": len(fonts), "pictures": len(pics), "animations": len(anims), "frames": len(frames),
                "values": len(values), "things": len(kinds), "movers": len(self.movers),
                "path_points": len(self.path), "phases": len(phases), "layers": len(layers),
                "places": len(places), "spawns": len(spawns), "conditions": len(conds),
                "weak_points": len(weak), "attacks": len(atk), "cards": len(cards), "hud": len(hud),
                "cues": len(cues), "sounds": len(self.sound_ix), "clips": len(self.clip_ix),
                "particles": len(self.emitters)}
        for k, n in have.items():
            if n > LIMITS[k]:
                self.problems.append("the document has %d %s; the engine holds up to %d" % (n, LIMIT_WORDS[k], LIMITS[k]))
        for s in self.strings:
            if len(s.encode("utf-8")) > 1024:
                self.problems.append("a text is longer than 1024 bytes: %s..." % s[:30])
