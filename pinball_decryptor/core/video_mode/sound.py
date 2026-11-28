"""A video mode's sound (PAD-1667): the rules every place plays it by, and what it costs a machine.

The document's sounds (``assets.sounds``) each have a role: ``music`` beds a phase names as its
``music`` (and a rhythm phase as ``settings.music``), ``effect`` and ``callout`` sounds that the
``cues`` tie to events.  The engine says what to play each step (``VM_SND_PLAY`` / ``MUSIC`` /
``MUSIC_STOP``, with a duck flag and a fade in steps); this module holds the rules the app's
player (Web Audio) and the machine (``pad_mode_assets.h``'s calls and beds) both follow, so what
the editor plays is what the machine plays:

* **One music voice.**  The machine's music is one carrier playing one bed at a time, so a music
  change is the bed playing fading out over the new bed's ``fade_s``, then the new one fading in
  over the same; a stop fades the playing bed out over its own.  The music plays on through a
  phase's result card, a phase tried again and a next phase with the same bed.  A looping bed
  goes back to ``loop_start_s`` at its end.
* **Ducking.**  A sound ducks the music while it plays when it is a callout or any cue of it says
  ``duck_music``: :data:`DUCK_STEPS` volume steps of 1/3 dB (the machine's own dip,
  ``PA_MUSIC_DUCK_STEPS``), down over :data:`DUCK_DOWN_S` and back over :data:`DUCK_UP_S`.
* **One voice for effects and callouts.**  Every call of a mode takes the voice bus: a new one
  fades out the one still sounding (30 ms: the newest event speaks); an effect (priority 3, a call
  that repeats) whose own previous play still sounds is skipped; a callout (priority 4) played
  again starts over.
* **Volumes** are each sound's ``volume`` (0..1; the machine plays its own WAV at the level the
  build wrote it, which is the volume baked in).

:func:`machine_plan` lays the sounds on the machine's route and counts them against its caps;
:func:`beat_grid` is the beat grid a rhythm phase and the timeline read from the music;
:func:`placeholder_wav` makes the stand-in sound of one whose file is not there yet (as pictures
without a file are drawn as placeholders); :func:`peaks` is a sound's waveform for the timeline.
"""
from __future__ import annotations

import io
import math
import os
import re
import struct
import subprocess
import wave

#: a music bed's fade when its fade_s is absent
FADE_S = 1.0
#: the music's dip under a ducking sound: pad_mode_assets.h PA_MUSIC_DUCK_STEPS / _DOWN_MS / _UP_MS
DUCK_STEPS = 28
DUCK_GAIN = 10 ** (-DUCK_STEPS / 3.0 / 20.0)
DUCK_DOWN_S = 0.15
DUCK_UP_S = 0.40
#: a call of the mode's own fades the one still sounding over this (pad_mode_assets.h pa_try)
VOICE_FADE_S = 0.03
#: the voice bus priority of each role's call (pad_mode_assets.h: 3 = a call that repeats)
PRIORITY = {"effect": 3, "callout": 4}
#: what each machine's mode sound route carries for one mode
MACHINES = {
    "spike2": {"label": "Spike 2", "calls": 16, "beds": 6},
    "spike3": {"label": "Spike 3", "calls": 16, "beds": 6},      # the same mode runtime and sound route
    "jjp": {"label": "Jersey Jack", "calls": None, "beds": None},
    "spooky": {"label": "Spooky", "calls": None, "beds": None},
    "dots": {"label": "dot-matrix screens", "calls": None, "beds": None},
}
DEFAULT = "spike2"
#: a call or bed name on the machine (code_modes.CUE_RE)
CUE_RE = re.compile(r"^[a-z][a-z0-9_]{0,14}$")


def sounds(doc):
    return [s for s in ((doc.get("assets") or {}).get("sounds") or []) if isinstance(s, dict)]


def fade_s(snd):
    v = (snd or {}).get("fade_s")
    return float(v) if isinstance(v, (int, float)) else FADE_S


def phase_music(phase):
    """The id of the music a phase plays: its own ``music``, else a rhythm phase's ``settings.music``."""
    m = phase.get("music")
    if not m and phase.get("kind") == "rhythm":
        m = (phase.get("settings") or {}).get("music")
    return m or None


def beat_grid(doc, phase):
    """A rhythm phase's beat grid, read from its own settings where it sets them and otherwise from its
    music: ``{"music", "bpm", "offset_s", "per_bar"}``, or None when neither has a tempo."""
    s = phase.get("settings") or {}
    mid = phase_music(phase)
    snd = next((x for x in sounds(doc) if x.get("id") == mid), {})
    bpm = s.get("tempo_bpm", snd.get("tempo_bpm"))
    if not isinstance(bpm, (int, float)) or bpm <= 0:
        return None
    off = s["offset_ms"] / 1000.0 if isinstance(s.get("offset_ms"), (int, float)) else float(snd.get("beat_offset_s", 0) or 0)
    return {"music": mid, "bpm": float(bpm), "offset_s": off, "per_bar": int(snd.get("beats_per_bar", 4) or 4)}


def sound_grid(snd):
    """A music bed's own beat grid (the timeline's lines), or None."""
    bpm = (snd or {}).get("tempo_bpm")
    if not isinstance(bpm, (int, float)) or bpm <= 0:
        return None
    return {"bpm": float(bpm), "offset_s": float(snd.get("beat_offset_s", 0) or 0),
            "per_bar": int(snd.get("beats_per_bar", 4) or 4)}


def ducks(doc):
    """{sound id: True} for every sound that ducks the music: a callout, or one a cue plays with duck_music."""
    out = {s["id"]: s.get("role") == "callout" for s in sounds(doc) if "id" in s}
    for c in doc.get("cues") or []:
        if isinstance(c, dict) and c.get("duck_music") and c.get("sound") in out:
            out[c["sound"]] = True
    return out


def used(doc):
    """(music ids in the order phases first play them, other sound ids in the order cues first name them)."""
    music, other = [], []
    for ph in doc.get("phases") or []:
        m = phase_music(ph) if isinstance(ph, dict) else None
        if m and m not in music:
            music.append(m)
    for c in doc.get("cues") or []:
        sid = c.get("sound") if isinstance(c, dict) else None
        if sid and sid not in other and sid not in music:
            other.append(sid)
    return music, other


def machine_name(sid, taken):
    """The sound's name on the machine: 1 to 15 lower-case letters, digits or _, starting with a letter, and
    not one already taken (nor "music", the own bed's name)."""
    base = re.sub(r"[^a-z0-9_]+", "_", str(sid).lower()).strip("_") or "sound"
    if not base[0].isalpha():
        base = "s_" + base
    base = base[:15]
    name, n = base, 2
    while name in taken or name == "music":
        tail = "_%d" % n
        name = base[:15 - len(tail)] + tail
        n += 1
    taken.add(name)
    return name


def machine_plan(doc, machine=DEFAULT):
    """How the mode's sounds go on the machine's mode sound route, and what that leaves.

    ``{"machine", "label", "calls": [{"id", "name", "role", "priority", "duck", "file"}],
    "music": {"id", "name", "file"} or None, "beds": [{"id", "name", "file"}],
    "unused": [ids], "count": {"calls", "calls_max", "beds", "beds_max"}, "problems": [str], "words": str}``

    The first music a phase plays is the mode's own music, every other music bed a further bed by name; each
    effect and callout a cue plays is a call.  A sound nothing plays is left off the card."""
    m = MACHINES.get(machine) or MACHINES[DEFAULT]
    by_id = {s["id"]: s for s in sounds(doc) if "id" in s}
    music, other = used(doc)
    duck = ducks(doc)
    taken = set()
    plan = {"machine": machine if machine in MACHINES else DEFAULT, "label": m["label"], "calls": [], "music": None,
            "beds": [], "unused": [], "problems": []}
    for i, mid in enumerate(music):
        s = by_id.get(mid) or {}
        row = {"id": mid, "name": "music" if i == 0 else machine_name(mid, taken), "file": s.get("file", ""),
               "fade_ms": int(round(fade_s(s) * 1000))}
        if i == 0:
            plan["music"] = row
        else:
            plan["beds"].append(row)
    for sid in other:
        s = by_id.get(sid) or {}
        role = s.get("role", "effect")
        if role == "music":
            continue
        plan["calls"].append({"id": sid, "name": machine_name(sid, taken), "role": role,
                              "priority": PRIORITY.get(role, 4), "duck": bool(duck.get(sid)), "file": s.get("file", "")})
    plan["unused"] = [sid for sid in by_id if sid not in music and sid not in other]
    nc, nb = len(plan["calls"]), len(plan["beds"])
    plan["count"] = {"calls": nc, "calls_max": m["calls"], "beds": nb, "beds_max": m["beds"]}
    if m["calls"] is not None and nc > m["calls"]:
        plan["problems"].append("%d effects and callouts are cued: %s plays %d a mode. Cue fewer sounds (one sound "
                                "can serve several events)." % (nc, m["label"], m["calls"]))
    if m["beds"] is not None and nb > m["beds"]:
        plan["problems"].append("%d pieces of music: %s plays its own music and %d more beds a mode. Let phases "
                                "share music." % (nb + 1, m["label"], m["beds"]))
    plan["words"] = plan_words(plan)
    return plan


def plan_words(plan):
    """The plan in one line for the page: what it uses and what is left."""
    c = plan["count"]
    music = (1 if plan["music"] else 0) + c["beds"]
    if c["calls_max"] is None:
        return ("%d sounds (effects and callouts) and %d music beds. How many a mode can carry on %s is set when "
                "video modes come to it." % (c["calls"], music, plan["label"]))
    left_c, left_b = max(0, c["calls_max"] - c["calls"]), max(0, c["beds_max"] - c["beds"])
    return ("On %s: %d of %d sounds (effects and callouts) and %d of %d music beds (its own and %d more); "
            "%d sounds and %d more beds left." % (plan["label"], c["calls"], c["calls_max"], music, c["beds_max"] + 1,
                                                  c["beds_max"], left_c, left_b))


def code_assets(plan):
    """The plan as a code mode's ``assets.json`` sound fields (``music``, ``beds``, ``calls``), for the build that
    carries a video mode onto the card (:mod:`...plugins.stern.code_modes`)."""
    out = {"music": plan["music"]["file"] if plan["music"] else "", "beds": {}, "calls": {}}
    for b in plan["beds"]:
        out["beds"][b["name"]] = b["file"]
    for c in plan["calls"]:
        out["calls"][c["name"]] = {"wav": c["file"], "priority": c["priority"], "duck": c["duck"]}
    return out


# ---- placeholder sounds ---------------------------------------------------------------------------
RATE = 22050


def _wav(samples):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(struct.pack("<%dh" % len(samples), *[max(-32767, min(32767, int(v * 32767))) for v in samples]))
    return b.getvalue()


def _rng(seed):
    x = (seed * 2654435761 + 1) & 0xFFFFFFFF
    while True:
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        yield (x / 0xFFFFFFFF) * 2 - 1


def placeholder_wav(snd, index=0):
    """A stand-in for a sound whose file is not there yet, made here (PAD ships no game content): an effect a
    short pitched blip, a callout a two-note chime, a music bed four bars of a bass and click on its own beat
    grid (120 a minute when it has none), long enough to reach past its loop point.  The same sound and index
    always give the same bytes."""
    role = (snd or {}).get("role", "effect")
    out = []
    if role == "music":
        g = sound_grid(snd) or {"bpm": 120.0, "offset_s": 0.0, "per_bar": 4}
        beat = 60.0 / g["bpm"]
        bars = 4
        length = g["offset_s"] + bars * g["per_bar"] * beat
        loop = float(snd.get("loop_start_s", 0) or 0)
        while length < loop + 2 * g["per_bar"] * beat:
            length += g["per_bar"] * beat
        root = 55.0 * 2 ** ((index % 5) / 12.0)
        noise = _rng(index + 7)
        n = int(length * RATE)
        for i in range(n):
            t = i / RATE
            k = (t - g["offset_s"]) / beat
            b = int(math.floor(k)) if k >= 0 else -1
            ph = (k - b) * beat if b >= 0 else 1e9
            strong = b >= 0 and b % g["per_bar"] == 0
            note = root * (1.5 if (b // g["per_bar"]) % 2 else 1.0)
            v = 0.32 * math.sin(2 * math.pi * note * t) * (0.6 + 0.4 * math.exp(-ph * 3))
            v += 0.10 * math.sin(2 * math.pi * note * 2.01 * t)
            if ph < 0.05:
                v += (0.55 if strong else 0.3) * next(noise) * (1 - ph / 0.05)
            out.append(v)
        fade = int(0.01 * RATE)
        for i in range(min(fade, len(out))):
            out[i] *= i / fade
    elif role == "callout":
        notes = (660.0 * 2 ** ((index % 4) / 12.0), 880.0 * 2 ** ((index % 4) / 12.0))
        for j, f in enumerate(notes):
            for i in range(int(0.32 * RATE)):
                t = i / RATE
                out.append(0.5 * math.sin(2 * math.pi * f * t) * math.exp(-t * 6) * min(1.0, t / 0.005))
    else:
        f0 = 300.0 + 140.0 * (index % 6)
        noise = _rng(index + 1)
        for i in range(int(0.22 * RATE)):
            t = i / RATE
            f = f0 * (1.8 - 3.2 * t)
            v = 0.45 * math.sin(2 * math.pi * f * t) + (0.25 * next(noise) if index % 2 else 0.0)
            out.append(v * math.exp(-t * 14) * min(1.0, t / 0.003))
    return _wav(out)


# ---- the waveform ---------------------------------------------------------------------------------
def _ffmpeg():
    from ..audio import find_ffmpeg
    return find_ffmpeg() or "ffmpeg"


def decode(path):
    """(mono float samples, rate) of a sound file: a WAV read here, anything else through ffmpeg."""
    try:
        with wave.open(path, "rb") as w:
            ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
        if width == 2:
            vals = struct.unpack("<%dh" % (len(raw) // 2), raw)
            scale = 32768.0
        elif width == 1:
            vals = [b - 128 for b in raw]
            scale = 128.0
        else:
            raise wave.Error("width %d" % width)
        mono = [sum(vals[i:i + ch]) / (ch * scale) for i in range(0, len(vals) - ch + 1, ch)]
        return mono, rate
    except (wave.Error, EOFError, struct.error):
        pass
    rate = 11025
    r = subprocess.run([_ffmpeg(), "-v", "error", "-i", path, "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
                       capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0 or not r.stdout:
        raise ValueError("the sound could not be read: %s" % (r.stderr.decode("utf-8", "replace").strip()[-200:] or "no audio"))
    raw = r.stdout[:len(r.stdout) // 2 * 2]
    return [v / 32768.0 for v in struct.unpack("<%dh" % (len(raw) // 2), raw)], rate


def peaks(path, n=800):
    """A sound's waveform for the timeline: {"seconds", "peaks": [[min, max], ...] (n columns, -1..1)}."""
    samples, rate = decode(path)
    if not samples:
        return {"seconds": 0.0, "peaks": []}
    n = max(1, min(int(n), len(samples)))
    per = len(samples) / float(n)
    out = []
    for i in range(n):
        seg = samples[int(i * per):max(int(i * per) + 1, int((i + 1) * per))]
        out.append([round(min(seg), 4), round(max(seg), 4)])
    return {"seconds": len(samples) / float(rate), "peaks": out}


def seconds(path):
    """How long a sound file plays, or 0 when it cannot be read."""
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, EOFError, OSError):
        pass
    try:
        samples, rate = decode(path)
        return len(samples) / float(rate)
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0.0


def file_of(mode_dir, snd):
    """The sound's file in the mode folder, or "" when it names none or it is not there."""
    f = (snd or {}).get("file")
    if not f or not mode_dir:
        return ""
    p = os.path.join(mode_dir, *str(f).split("/"))
    return p if os.path.isfile(p) else ""


# ---- the beat -------------------------------------------------------------------------------------
ENV_HZ = 200


def find_beat(samples, rate, lo=60.0, hi=200.0):
    """The beat of a piece of music: ``{"bpm", "offset_s", "confidence"}`` (confidence 0..1, how much the beat stands
    out), or None when it is too short or has no beat to find.  The onsets (rises in loudness) are matched against
    themselves one beat later for every tempo from ``lo`` to ``hi`` a minute, in tenths; a tempo and its double score
    alike, so the one nearer 120 is kept; the first beat is where the onsets line up best with that grid."""
    hop = max(1, int(rate / ENV_HZ))
    fr = rate / float(hop)                        # the envelope's own rate (22050 / 110 is 200.45, not 200)
    win = max(hop, int(rate * 0.023))
    # the loudness of the change from sample to sample (a percussive hit stands out, a bass note's own wave does not),
    # over 23 ms windows every 5 ms
    acc, run = [0.0], 0.0
    for i in range(1, len(samples)):
        run += abs(samples[i] - samples[i - 1])
        acc.append(run)
    env = [(acc[i + win] - acc[i]) / win for i in range(0, len(acc) - win, hop)]
    if len(env) < fr * 3:
        return None
    ons = [0.0] + [max(0.0, env[i] - env[i - 1]) for i in range(1, len(env))]
    mean = sum(ons) / len(ons)
    ons = [max(0.0, o - mean) for o in ons]
    total = sum(o * o for o in ons)
    if total <= 0:
        return None

    def score(bpm):
        lag = 60.0 * fr / bpm
        s = 0.0
        for k in (1, 2, 4, 8):
            L = lag * k
            a, f = int(L), L - int(L)
            n = len(ons) - a - 1
            if n <= 0:
                continue
            s += sum(ons[i] * (ons[i + a] * (1 - f) + ons[i + a + 1] * f) for i in range(n)) / n
        return s
    cands = [(score(b / 10.0), b / 10.0) for b in range(int(lo * 10), int(hi * 10) + 1, 5)]
    best_s, best = max(cands)
    # a tempo and its half / double line up alike: keep the one nearer 120 when it scores nearly as well
    for alt in (best / 2, best * 2):
        if lo <= alt <= hi:
            s = score(alt)
            if s >= 0.85 * best_s and abs(alt - 120) < abs(best - 120):
                best, best_s = alt, s
    fine = [(score(best + d / 100.0), best + d / 100.0) for d in range(-60, 61, 2)]
    best_s, best = max(fine)
    whole = float(round(best))                    # most music is a whole number a minute
    if abs(whole - best) <= 0.5 and score(whole) >= 0.97 * best_s:
        best = whole
    period = 60.0 * fr / best
    phases = []
    for p in range(int(period)):
        k, s = 0, 0.0
        while p + k * period < len(ons):
            s += ons[int(p + k * period)]
            k += 1
        phases.append((s, p))
    top, p = max(phases)
    avg = sum(s for s, _ in phases) / len(phases)
    conf = max(0.0, min(1.0, (top - avg) / top)) if top > 0 else 0.0
    # a window's loudness rises from when it first takes the hit in: the hit is half a window on
    off = (p + win / 2.0 / hop) % period / fr
    if off > period / fr - 0.02:                  # a hair before the next beat is the beat at 0
        off = max(0.0, off - period / fr)
    return {"bpm": round(best, 2), "offset_s": round(off, 3), "confidence": round(conf, 2)}


def beat_of(path):
    """:func:`find_beat` of a sound file (the first 60 s)."""
    samples, rate = decode(path)
    return find_beat(samples[:int(rate * 60)], rate)


# ---- the machine's files --------------------------------------------------------------------------
#: a phase with no length plays this long for a bed's baking
OPEN_PHASE_S = 120.0
BED_MAX_S = 300.0


def bed_seconds(doc, sid):
    """How long a bed may have to play without a break: every phase on it, each try, with its title and result
    cards (the music plays on through them and through a phase tried again), capped at :data:`BED_MAX_S`."""
    tries = {}
    for c in (doc.get("flow") or {}).get("cards") or []:
        if isinstance(c, dict) and c.get("card") == "phase":
            tries[c.get("phase")] = max(tries.get(c.get("phase"), 1), int(c.get("tries", 1) or 1))
    total = 0.0
    for ph in doc.get("phases") or []:
        if isinstance(ph, dict) and phase_music(ph) == sid:
            length = float(ph.get("length_s") or 0) or OPEN_PHASE_S
            total += (length + 3.0) * tries.get(ph.get("id"), 1)
    return min(BED_MAX_S, max(total, 10.0))


def bake_bed(samples, rate, loop_start_s, seconds):
    """A bed as the machine plays it: the machine's music loops a record from its start, so the loop point is baked
    in - the whole file once, then the part from the loop point again and again until it outlasts ``seconds``."""
    out = list(samples)
    a = int(max(0.0, float(loop_start_s or 0)) * rate)
    body = samples[a:] if a < len(samples) else samples
    if not body:
        return out
    while len(out) < seconds * rate:
        out.extend(body)
    return out


def _write_wav(path, samples, rate):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % len(samples), *[max(-32767, min(32767, int(v * 32767))) for v in samples]))


def machine_files(doc, mode_dir, out_dir, machine=DEFAULT, placeholder=None):
    """Write the machine's sound files for a video mode into ``out_dir``: a 48 kHz stereo WAV for each sound the
    plan carries (a sound without its file: its placeholder), each sound at its own ``volume``, each bed baked
    (:func:`bake_bed`). Returns ``(plan, fields)``: the plan, and the code mode ``assets.json`` sound fields naming
    the files (``music``, ``beds``, ``calls``) - the music's names and call names are the plan's."""
    plan = machine_plan(doc, machine)
    by_id = {s["id"]: s for s in sounds(doc) if "id" in s}
    order = [s["id"] for s in sounds(doc) if "id" in s]
    os.makedirs(out_dir, exist_ok=True)
    ff = _ffmpeg()

    def make(sid, bed):
        snd = by_id[sid]
        src = file_of(mode_dir, snd)
        if src:
            samples, rate = decode(src)
        else:
            data = (placeholder or placeholder_wav)(snd, order.index(sid))
            with wave.open(io.BytesIO(data)) as w:
                rate, raw = w.getframerate(), w.readframes(w.getnframes())
            samples = [v / 32768.0 for v in struct.unpack("<%dh" % (len(raw) // 2), raw)]
        vol = float(snd.get("volume", 1.0))
        samples = [v * vol for v in samples]
        if bed:
            samples = bake_bed(samples, rate, snd.get("loop_start_s") if snd.get("loop", True) else None,
                               bed_seconds(doc, sid))
        name = re.sub(r"[^0-9A-Za-z_]+", "_", sid)[:40] + ".wav"
        mono = os.path.join(out_dir, "_mono_" + name)
        _write_wav(mono, samples, rate)
        out = os.path.join(out_dir, name)
        r = subprocess.run([ff, "-v", "error", "-y", "-i", mono, "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", out],
                           capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0:
            os.remove(mono)
        else:
            os.replace(mono, out)
        return name

    fields = {"music": "", "beds": {}, "calls": {}}
    if plan["music"]:
        fields["music"] = make(plan["music"]["id"], True)
    for b in plan["beds"]:
        fields["beds"][b["name"]] = make(b["id"], True)
    for c in plan["calls"]:
        fields["calls"][c["name"]] = {"wav": make(c["id"], False), "priority": c["priority"], "duck": c["duck"]}
    return plan, fields


def machine_names(doc, plan):
    """The machine name of each of the engine's sounds, in the engine's order ("" for one the plan leaves off)."""
    named = {}
    if plan["music"]:
        named[plan["music"]["id"]] = plan["music"]["name"]
    for r in plan["beds"] + plan["calls"]:
        named[r["id"]] = r["name"]
    return [named.get(s.get("id"), "") for s in sounds(doc)]


def cue_log(cues, info, sps=60):
    """What each sound cue does under the machine's rules, in step time: the player's log and the rig's are held
    to this.  ``cues``: ``[(step, sound, op, duck, fade)]`` as the engine gives them; ``info``: per sound index
    ``{"role", "seconds"}``.  Returns ``[(step, sound, op, did)]``: did is ``played`` or ``skipped`` (an effect
    whose previous play still sounds) for a sound, ``starts`` / ``changes`` / ``stops`` for the music."""
    out, until, music = [], {}, -1
    for step, snd, op, _duck, _fade in cues:
        if op == 1:
            out.append((step, snd, op, "changes" if music >= 0 else "starts"))
            music = snd
        elif op == 2:
            out.append((step, snd, op, "stops"))
            music = -1
        else:
            now = step / float(sps)
            meta = info.get(snd) or {}
            if meta.get("role") != "callout" and until.get(snd, -1.0) > now:
                out.append((step, snd, op, "skipped"))
                continue
            until[snd] = now + float(meta.get("seconds") or 0)
            out.append((step, snd, op, "played"))
    return out
