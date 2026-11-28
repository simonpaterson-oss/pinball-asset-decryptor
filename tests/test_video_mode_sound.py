"""PAD-1667: a video mode's sound - music per phase with fades, effects on events, ducking, the beat grid, and the
machine's route (core/video_mode/sound.py, the engine's cues, the tab's Sound card, the player's Web Audio rules,
pad_mode_assets.h's pa_music_change / noduck, vm_sound.h)."""
import copy
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import wave

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pinball_decryptor.core import video_mode as vm  # noqa: E402
from pinball_decryptor.core.video_mode import compiler, harness, sound as SND  # noqa: E402

EXAMPLE = os.path.join(ROOT, "pinball_decryptor", "core", "video_mode", "examples", "night_harbour.json")
FIXTURES = os.path.join(ROOT, "tests", "data", "video_mode")
GOLDEN = os.path.join(FIXTURES, "golden")
ENGINE = os.path.join(ROOT, "pinball_decryptor", "core", "video_mode", "engine")
JS = os.path.join(ROOT, "pinball_decryptor", "webui", "static", "js", "tabs")
SDK = os.path.join(ROOT, "tools", "spike2_emu", "modes", "sdk")

pytestmark = pytest.mark.xdist_group("video_mode_engine")
PLAY, MUSIC, STOP = 0, 1, 2


def example():
    return vm.load(EXAMPLE)


_native = []


def native():
    if not _native:
        _native.append(harness.native_runner(os.path.join(tempfile.gettempdir(), "pad_vmrun_tests")))
    if not _native[0]:
        pytest.skip("no C compiler for the native engine")
    return _native[0]


def cues_of(doc, inputs=None, bot=True, seed=1):
    comp = compiler.compile_doc(doc, None)
    assert comp.ok, comp.problems
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "m.pack")
        with open(p, "wb") as f:
            f.write(comp.pack)
        args = ["--seed", str(seed)]
        if inputs is not None:
            ip = os.path.join(td, "in")
            with open(ip, "wb") as f:
                f.write(inputs)
            args += ["--inputs", ip, "--max", str(len(inputs))]
        elif bot:
            args += ["--bot", "--max", "200000"]
        out = harness.run_engine(native(), p, args)
    events, cues, _d, end = harness.parse(out)
    return comp, events, cues, end


def golden_inputs():
    with open(os.path.join(GOLDEN, "golden.json"), encoding="utf-8") as f:
        spec = json.load(f)["runs"]["night_harbour_bot"]
    with open(os.path.join(GOLDEN, spec["inputs"]), "rb") as f:
        return f.read(), spec


# ---- format 2 ---------------------------------------------------------------------------------------------------------
def test_format_2_reads_format_1_unchanged_but_its_number():
    with open(os.path.join(FIXTURES, "format_1.json"), encoding="utf-8") as f:
        raw = json.load(f)
    doc = vm.migrate(raw)
    assert doc["format"] == vm.FORMAT and vm.FORMAT >= 2      # format 3 (PAD-1664) adds nothing a format 1 file holds
    raw2 = copy.deepcopy(raw)
    raw2["format"] = vm.FORMAT
    assert doc == raw2
    assert vm.check(doc) == []


def test_sound_fields_are_checked_in_plain_words():
    doc = example()
    snd = {s["id"]: s for s in doc["assets"]["sounds"]}
    snd["zap"]["tempo_bpm"] = 120
    snd["boss_music"].pop("tempo_bpm")
    out = vm.check(doc)
    assert any("tempo_bpm" in p and "music only" in p for p in out), out
    assert any("beat_offset_s" in p and "needs the music's tempo_bpm" in p for p in out), out
    doc = example()
    {s["id"]: s for s in doc["assets"]["sounds"]}["chase_music"]["fade_s"] = 11
    assert any("fade_s" in p for p in vm.check(doc))


def _rhythm(doc, settings, music_tempo=True):
    doc = copy.deepcopy(doc)
    snd = {s["id"]: s for s in doc["assets"]["sounds"]}
    if not music_tempo:
        for k in ("tempo_bpm", "beat_offset_s", "beats_per_bar"):
            snd["boss_music"].pop(k, None)
    ph = next(p for p in doc["phases"] if p["id"] == "charge")
    ph.update(kind="rhythm", settings=dict({"music": "boss_music", "chart": [{"beat": 1, "button": "left"}]}, **settings))
    ph.pop("music", None)
    return doc, ph


def test_a_rhythm_phase_reads_its_beat_grid_from_its_music():
    doc, ph = _rhythm(example(), {})
    assert vm.check(doc) == []
    g = SND.beat_grid(doc, ph)
    assert g == {"music": "boss_music", "bpm": 96.0, "offset_s": 0.0, "per_bar": 4}
    comp = compiler.compile_doc(doc, None)
    assert comp.ok
    # its own tempo wins over the music's
    doc2, ph2 = _rhythm(example(), {"tempo_bpm": 140, "offset_ms": 250})
    assert SND.beat_grid(doc2, ph2)["bpm"] == 140 and SND.beat_grid(doc2, ph2)["offset_s"] == 0.25
    # neither has one: said plainly
    doc3, _ = _rhythm(example(), {}, music_tempo=False)
    assert any("tempo_bpm" in p and "beat grid" in p for p in vm.check(doc3))
    # a rhythm phase plays its settings' music
    assert SND.phase_music(ph) == "boss_music"


# ---- the engine's music rules -------------------------------------------------------------------------------------------
def test_music_changes_only_when_the_bed_changes_with_its_fade():
    doc = example()
    comp, events, cues, end = cues_of(doc, *golden_inputs()[:1])
    names = comp.names["sounds"]
    music = [(s, names[snd], op, fade) for s, snd, op, _d, fade in cues if op != PLAY]
    # chase's bed fades in over its 1 s, boss's takes over over its 1.5 s, the charge has none: boss's fades out
    assert [(n, op, f) for _s, n, op, f in music] == [("chase_music", MUSIC, 60), ("boss_music", MUSIC, 90),
                                                     ("boss_music", STOP, 90)]
    # each at its phase's start: the music plays on through the result cards between
    starts = [s for s, t, a, _b, _c in events if t == 3]       # VM_EV_PHASE_START
    assert [s for s, _n, _op, _f in music] == starts[:3]


def test_a_phase_tried_again_and_a_next_phase_on_the_same_bed_play_on():
    doc = example()
    for ph in doc["phases"]:
        ph["music"] = "chase_music"
    comp, _e, cues, _end = cues_of(doc, *golden_inputs()[:1])
    ops = [(op, comp.names["sounds"][snd]) for _s, snd, op, _d, _f in cues if op != PLAY]
    assert ops[0] == (MUSIC, "chase_music") and all(o != (MUSIC, "chase_music") for o in ops[1:])
    # random buttons lose phases and try them again: still one music cue a change
    import random
    rng = random.Random(5)
    inputs = bytes(rng.choice([0, 1, 2, 4, 8]) for _ in range(20000))
    _c, events, cues, _end = cues_of(example(), inputs)
    seq = [snd for _s, snd, op, _d, _f in cues if op == MUSIC]
    assert all(a != b for a, b in zip(seq, seq[1:]))


def test_a_cutscene_and_the_end_stop_the_music():
    doc = example()                                  # the charge plays the boss's music too
    next(p for p in doc["phases"] if p["id"] == "charge")["music"] = "boss_music"
    comp, events, cues, end = cues_of(doc, *golden_inputs()[:1])
    stops = [(s, comp.names["sounds"][snd], f) for s, snd, op, _d, f in cues if op == STOP]
    clip_starts = [s for s, t, *_ in events if t == 1]           # VM_EV_CLIP_START
    assert stops and stops[-1][1] == "boss_music" and stops[-1][2] == 90
    assert stops[-1][0] in clip_starts                            # the won clip stops it


def test_a_sound_ducks_wherever_it_plays_when_any_cue_or_its_role_says():
    doc = example()
    doc["cues"].append({"on": "kill", "sound": "zap", "duck_music": True})
    comp, _e, cues, _end = cues_of(doc, *golden_inputs()[:1])
    names = comp.names["sounds"]
    duck = {}
    for _s, snd, op, d, _f in cues:
        if op == PLAY:
            duck.setdefault(names[snd], set()).add(d)
    assert duck["zap"] == {1}             # the fire cue too: the machine ducks per call
    assert duck["go_now"] == {1}          # a callout
    assert duck["boom"] == {0}


def test_golden_runs_kept_their_play_only_the_cues_changed():
    with open(os.path.join(GOLDEN, "golden.json"), encoding="utf-8") as f:
        runs = json.load(f)["runs"]
    assert (runs["night_harbour_bot"]["steps"], runs["night_harbour_bot"]["outcome"],
            runs["night_harbour_bot"]["score"]) == (3101, 1, 33000)


# ---- the machine ---------------------------------------------------------------------------------------------------------
def test_machine_plan_of_the_example():
    p = SND.machine_plan(example())
    assert p["music"] == {"id": "chase_music", "name": "music", "file": "sound/chase.ogg", "fade_ms": 1000}
    assert p["beds"] == [{"id": "boss_music", "name": "boss_music", "file": "sound/boss.ogg", "fade_ms": 1500}]
    assert [(c["name"], c["priority"], c["duck"]) for c in p["calls"]] == [
        ("zap", 3, False), ("boom", 3, False), ("ouch", 3, False), ("chime", 3, False), ("go_now", 4, True)]
    assert p["count"] == {"calls": 5, "calls_max": 16, "beds": 1, "beds_max": 6} and p["problems"] == []
    assert p["words"] == ("On Spike 2: 5 of 16 sounds (effects and callouts) and 2 of 7 music beds (its own and 6 "
                          "more); 11 sounds and 5 more beds left.")
    assert SND.machine_names(example(), p) == ["music", "boss_music", "zap", "boom", "ouch", "chime", "go_now"]
    assert SND.code_assets(p)["calls"]["go_now"] == {"wav": "sound/go_now.wav", "priority": 4, "duck": True}
    assert "set when video modes come to it" in SND.machine_plan(example(), "jjp")["words"]


def test_machine_plan_says_when_a_mode_needs_more_than_the_route_carries():
    doc = example()
    for i in range(14):
        doc["assets"]["sounds"].append({"id": "fx%d" % i, "file": "sound/fx.wav", "role": "effect"})
        doc["cues"].append({"on": "kill", "sound": "fx%d" % i})
    for i in range(7):
        doc["assets"]["sounds"].append({"id": "bed%d" % i, "file": "sound/b.ogg", "role": "music", "loop": True})
        doc["phases"].append(dict(copy.deepcopy(doc["phases"][2]), id="extra%d" % i, music="bed%d" % i))
    p = SND.machine_plan(doc)
    assert p["count"]["calls"] == 19 and p["count"]["beds"] == 8
    assert any("19 effects and callouts" in x and "16 a mode" in x for x in p["problems"])
    assert any("9 pieces of music" in x for x in p["problems"])
    # names stay what the machine takes: 15 characters at most, unique, never "music"
    names = SND.machine_names(doc, p)
    assert all(n == "" or re.fullmatch(r"[a-z][a-z0-9_]{0,14}", n) for n in names) and len(set(names)) == len(names)


def test_machine_names_are_safe_and_unique():
    taken = set()
    assert SND.machine_name("Big-Boom!", taken) == "big_boom"
    assert SND.machine_name("big boom", taken) == "big_boom_2"
    assert SND.machine_name("9lives", taken) == "s_9lives"
    assert SND.machine_name("music", taken) == "music_2"
    assert len(SND.machine_name("a" * 40, taken)) == 15


def test_beds_are_baked_to_keep_their_loop_point():
    rate = 100
    samples = [i / 1000.0 for i in range(300)]                 # 3 s
    out = SND.bake_bed(samples, rate, 1.0, 10.0)
    assert out[:300] == samples and len(out) >= 1000
    assert out[300:500] == samples[100:300] and out[500:700] == samples[100:300]
    doc = example()
    # the boss: 40 s, two tries, each with its cards
    assert SND.bed_seconds(doc, "boss_music") == pytest.approx(2 * 43.0)
    assert SND.bed_seconds(doc, "chase_music") == pytest.approx(48.0)


def test_machine_files_are_written_for_every_sound_the_plan_carries(tmp_path):
    doc = example()
    plan, fields = SND.machine_files(doc, str(tmp_path / "nothing"), str(tmp_path / "out"))
    assert set(fields["calls"]) == {"zap", "boom", "ouch", "chime", "go_now"}
    assert fields["calls"]["zap"]["priority"] == 3 and fields["calls"]["go_now"]["duck"] is True
    for f in [fields["music"]] + list(fields["beds"].values()) + [c["wav"] for c in fields["calls"].values()]:
        with wave.open(str(tmp_path / "out" / f)) as w:
            assert w.getframerate() == 48000 and w.getnchannels() == 2
            secs = w.getnframes() / float(w.getframerate())
        if f == fields["music"]:
            assert secs >= SND.bed_seconds(doc, "chase_music")


def test_machine_files_need_no_ffmpeg(tmp_path, monkeypatch):
    """No ffmpeg on the computer (PAD-1684: the Linux CI runner): the machine still gets 48 kHz stereo WAVs, as
    long as its mono source, and no stray _mono_ files are left behind."""
    monkeypatch.setattr(SND, "_ffmpeg", lambda: str(tmp_path / "no-such-ffmpeg"))
    doc = example()
    plan, fields = SND.machine_files(doc, str(tmp_path / "nothing"), str(tmp_path / "out"))
    names = [fields["music"]] + list(fields["beds"].values()) + [c["wav"] for c in fields["calls"].values()]
    assert sorted(os.listdir(str(tmp_path / "out"))) == sorted(set(names))
    for f in names:
        with wave.open(str(tmp_path / "out" / f)) as w:
            assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (48000, 2, 2)
            secs = w.getnframes() / 48000.0
        if f == fields["music"]:
            assert secs >= SND.bed_seconds(doc, "chase_music")


def test_machine_wav_resamples_and_doubles_to_stereo(tmp_path):
    p = str(tmp_path / "x.wav")
    SND._write_machine_wav(p, [0.0, 0.5, 1.0, 0.5] * 2756, 11025)
    with wave.open(p) as w:
        assert (w.getframerate(), w.getnchannels()) == (48000, 2)
        n = w.getnframes()
        raw = w.readframes(n)
    assert n == round(4 * 2756 * 48000 / 11025.0)
    vals = struct.unpack("<%dh" % (len(raw) // 2), raw)
    assert vals[0::2] == vals[1::2] and max(vals) > 32000


def test_a_non_wav_sound_without_ffmpeg_says_it_could_not_be_read(tmp_path, monkeypatch):
    monkeypatch.setattr(SND, "_ffmpeg", lambda: str(tmp_path / "no-such-ffmpeg"))
    src = tmp_path / "a.mp3"
    src.write_bytes(b"ID3 not really")
    with pytest.raises(ValueError, match="could not be read"):
        SND.decode(str(src))


def test_code_mode_call_that_does_not_duck_says_noduck(tmp_path):
    from pinball_decryptor.plugins.stern import code_modes as CM
    spec = CM.CodeAssets(name="X", calls={"zap": {"wav": "zap.wav", "priority": 3, "duck": False}, "go": "go.wav"})
    used = [{"slug": "x", "key": "call:zap", "request": 10, "ms": 200}, {"slug": "x", "key": "call:go", "request": 11, "ms": 500}]
    from pinball_decryptor.plugins.stern import mode_project as MP
    text = CM.runtime_text("x", spec, MP.GODZILLA_PRO_1_15, own_sounds=used)
    assert "call   zap 10 200 3 noduck" in text.splitlines()
    assert "call   go 11 500 4" in text.splitlines()
    assert spec.call_noduck() == {"zap"}


def test_sdk_reads_noduck_and_changes_music_with_a_fade():
    src = open(os.path.join(SDK, "pad_mode_assets.h"), encoding="utf-8").read()
    assert 'pa_is(w, "noduck")' in src and "!a->calls[i].noduck" in src
    assert "static PA_UNUSED int pa_music_change(struct pa_assets *a, const char *name, unsigned ms)" in src
    glue = open(os.path.join(ENGINE, "vm_sound.h"), encoding="utf-8").read()
    for want in ("pa_call(s->own, name)", "pa_music_change(s->own, name, vm_sound_ms(c->fade))",
                 "pa_music_change(s->own, 0, vm_sound_ms(c->fade))", "pa_music_change(s->own, 0, 0)"):
        assert want in glue


SDK_HARNESS = r'''
#include <stdio.h>
#include <string.h>
static unsigned long now_ms;
static int active[4096], ducked[4096];
static unsigned pointed[4096];
static char logbuf[64][200]; static int nlog;
unsigned long pm_ms(void) { return now_ms; }
void pm_log(const char *f, ...) { __builtin_va_list a; __builtin_va_start(a, f); if (nlog < 64) vsnprintf(logbuf[nlog++], 200, f, a); __builtin_va_end(a); }
int pm_snprintf(char *b, unsigned long n, const char *f, ...) { __builtin_va_list a; int r; __builtin_va_start(a, f); r = vsnprintf(b, n, f, a); __builtin_va_end(a); return r; }
long pm_read_file(const char *p, char *b, unsigned long n) {
    static const char t[] = "music  125 618\nbed    boss 619\ncall   zap 1251 200 3 noduck\ncall   go 1252 900 4\n";
    if (!strstr(p, "/dump/")) return -1;
    memcpy(b, t, sizeof t); return (long)sizeof t - 1; }
int pm_sound(unsigned r) { active[r] = 1; return 1; }
int pm_sound_active(unsigned r) { return active[r]; }
int pm_sound_fade(unsigned r, unsigned ms) { int was = active[r]; active[r] = 0; (void)ms; return was; }
int pm_sound_duck(unsigned r, unsigned steps, unsigned ms) { (void)ms; if (!active[r]) return 0; ducked[r] = (int)steps; return 1; }
int pm_sound_sid(unsigned r, unsigned sid) { pointed[r] = sid; return 1; }
int pm_sound_swap(unsigned r, const unsigned char *a, const unsigned char *b, int p, unsigned ms) { (void)r; (void)a; (void)b; (void)p; (void)ms; return 1; }
int pm_sound_priority(unsigned r, int p, int s) { (void)r; (void)p; (void)s; return 4 << 8; }
int pm_sound_priority_stock(unsigned r) { (void)r; return 4 << 8; }
int pm_sound_playing(unsigned *reqs, unsigned *buses, int max) { int n = 0; unsigned r; for (r = 0; r < 4096 && n < max; r++) if (active[r]) { reqs[n] = r; buses[n++] = r == 125 ? 1 : 2; } return n; }
int pm_in_game(void) { return 1; }
int pm_backdrop(const char *n) { (void)n; return 1; }
int pm_backdrop_once(const char *n) { (void)n; return 1; }
int pm_block_rules_keep(const unsigned char *ns, int n) { (void)ns; (void)n; return 1; }
void pm_callout(unsigned id) { (void)id; }
unsigned pm_callout_id(const char *role) { (void)role; return 0; }
int pm_clip(const char *n) { (void)n; return 1; }
'''


def test_sdk_music_change_and_noduck_on_the_desk(tmp_path):
    """pad_mode_assets.h compiled for this PC against stand-ins of the runtime's sound calls: a call marked noduck
    leaves the music up, pa_music_change fades out, quiet, starts the bed again and fades it in."""
    gcc = shutil.which("gcc") or shutil.which("cc")
    if not gcc or sys.platform == "win32":
        pytest.skip("gcc on Linux")
    main = r'''
#include "pad_mode_assets.h"
static struct pa_assets own = { .folder = "t" };
int main(void) {
    int i, ok = 1;
    pa_load(&own); pa_start(&own);
    ok &= active[125] == 1;
    pa_music_change(&own, 0, 400);                     /* quiet */
    ok &= active[125] == 0 && pa_music.hushed;
    for (i = 0; i < 10; i++) { now_ms += 17; pa_tick(&own); }
    ok &= active[125] == 0;                            /* not started again while quiet */
    pa_music_change(&own, "boss", 1500);               /* from quiet: at once, fading in */
    ok &= pointed[125] == 619;
    for (i = 0; i < 4; i++) { now_ms += 17; pa_tick(&own); }
    ok &= active[125] == 1 && ducked[125] == 0;        /* pulled down as it started, then ramped up */
    pa_call(&own, "zap"); now_ms += 17; pa_tick(&own);
    ok &= ducked[125] == 0;                            /* noduck: the music stays up */
    active[1251] = 0;
    pa_call(&own, "go"); now_ms += 17; pa_tick(&own);
    ok &= ducked[125] == 28;                           /* the callout ducks it */
    printf("ok=%d hushed=%d duck=%d\n", ok, pa_music.hushed, ducked[125]);
    return ok ? 0 : 1;
}
'''
    c = tmp_path / "t.c"
    c.write_text(SDK_HARNESS + "\n" + main, encoding="utf-8")
    exe = tmp_path / "t"
    r = subprocess.run([gcc, "-std=gnu17", "-w", "-I", SDK, str(c), "-o", str(exe)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    got = subprocess.run([str(exe)], capture_output=True, text=True)
    assert got.returncode == 0, got.stdout + got.stderr


# ---- placeholders, waveforms and the beat -----------------------------------------------------------------------------
def test_placeholder_sounds_are_the_same_every_time():
    doc = example()
    for i, s in enumerate(doc["assets"]["sounds"]):
        a, b = SND.placeholder_wav(s, i), SND.placeholder_wav(s, i)
        assert a == b and a[:4] == b"RIFF"
        with wave.open(io.BytesIO(a)) as w:
            secs = w.getnframes() / float(w.getframerate())
        if s["role"] == "music":
            assert secs > float(s.get("loop_start_s", 0)) + 2


@pytest.mark.parametrize("bpm,off", [(128, 0.0), (96, 0.5), (140, 0.2), (122.5, 0.3)])
def test_find_the_beat_reads_the_tempo_and_first_beat(bpm, off):
    data = SND.placeholder_wav({"role": "music", "tempo_bpm": bpm, "beat_offset_s": off, "loop_start_s": 4.0}, 2)
    with wave.open(io.BytesIO(data)) as w:
        rate, raw = w.getframerate(), w.readframes(w.getnframes())
    import struct
    smp = [v / 32768.0 for v in struct.unpack("<%dh" % (len(raw) // 2), raw)]
    got = SND.find_beat(smp, rate)
    assert abs(got["bpm"] - bpm) <= 0.25
    beat = 60.0 / bpm
    d = (got["offset_s"] - off) % beat
    assert min(d, beat - d) <= 0.012
    assert SND.find_beat([0.0] * 50000, 22050) is None


def test_peaks_of_a_wav(tmp_path):
    p = tmp_path / "s.wav"
    p.write_bytes(SND.placeholder_wav({"role": "effect"}, 0))
    pk = SND.peaks(str(p), 100)
    assert len(pk["peaks"]) == 100 and 0.2 < pk["seconds"] < 0.3
    assert all(-1 <= lo <= hi <= 1 for lo, hi in pk["peaks"]) and max(hi for _lo, hi in pk["peaks"]) > 0.2


# ---- one voice: the rules the player and the machine follow ----------------------------------------------------------
def test_cue_log_skips_an_effect_still_sounding_and_restarts_a_callout():
    info = {0: {"role": "music"}, 1: {"role": "effect", "seconds": 0.5}, 2: {"role": "callout", "seconds": 1.0}}
    cues = [(0, 0, MUSIC, 0, 60), (10, 1, PLAY, 0, 0), (20, 1, PLAY, 0, 0), (50, 1, PLAY, 0, 0),
            (60, 2, PLAY, 1, 0), (70, 2, PLAY, 1, 0), (80, 0, STOP, 0, 60)]
    assert [d for *_x, d in SND.cue_log(cues, info)] == ["starts", "played", "skipped", "played", "played", "played", "stops"]


def _sounds_class():
    src = open(os.path.join(JS, "vmodes_play.js"), encoding="utf-8").read()
    a = src.index("const SND = {")
    b = src.index("// ---- the run: engine, clock, buttons, clips, recording")
    return src[a:b]


def test_player_sounds_follow_the_same_rules(tmp_path):
    """The player's Sounds class (sound off: the same log, nothing heard) on the bot's run gives what cue_log says."""
    node = shutil.which("node")
    if not node:
        pytest.skip("no Node")
    doc = example()
    inputs, spec = golden_inputs()
    comp, _e, cues, _end = cues_of(doc, inputs)
    secs = {"zap": 0.25, "boom": 0.6, "ouch": 0.3, "chime": 0.45, "go_now": 0.5}
    lst = [{"role": s["role"], "volume": s.get("volume", 1), "seconds": secs.get(s["id"], 0)} for s in doc["assets"]["sounds"]]
    js = tmp_path / "t.mjs"
    js.write_text("const mediaUrl = (p) => p;\n" + _sounds_class() + r'''
const list = %s, cues = %s;
const s = new Sounds(list);
for (const [step, sound, op, duck, fade] of cues) s.cue({ sound, op, duck, fade }, step);
console.log(JSON.stringify(s.log.map((x) => [x.step, x.sound, x.op, x.did])));
''' % (json.dumps(lst), json.dumps(cues)), encoding="utf-8")
    got = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr
    log = [tuple(x) for x in json.loads(got.stdout)]
    want = SND.cue_log(cues, {i: {"role": x["role"], "seconds": x["seconds"]} for i, x in enumerate(lst)})
    assert log == [tuple(x) for x in want]
    assert any(d == "skipped" for *_x, d in want)      # fire at 6 a second outruns a 0.25 s zap


# ---- the tab ---------------------------------------------------------------------------------------------------------
def _project(tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import vm_demo_art
    sys.path.pop(0)
    project = tmp_path / "proj"
    md = project / "modes" / "night-harbour"
    vm_demo_art.make_mode(str(md))
    vm_demo_art.make_media(str(md), ffmpeg="")
    for f in ("chase.ogg", "boss.ogg"):              # the beds play their placeholders
        if (md / "sound" / f).exists():
            (md / "sound" / f).unlink()
    return project, md


def test_sound_card_edits_undo_and_redo(tmp_path):
    from tests.webui_harness import web_app
    project, md = _project(tmp_path)
    doc_path = md / "video_mode.json"
    with web_app(tmp_path, mfr="stern") as w:
        w.run(lambda: w.window.write_assets_var.set(str(project)))
        w.drain()
        assert w.call("vmodes.refresh") is True
        st = w.state("vmodes")
        rows = {r["id"]: r for r in st["sounds"]}
        assert rows["chase_music"]["missing"] and rows["chase_music"]["path"].endswith(".wav")     # its placeholder
        assert not rows["zap"]["missing"] and rows["zap"]["machine"] == "zap" and rows["zap"]["priority"] == 3
        assert rows["go_now"]["duck"] and rows["chase_music"]["grid"]["bpm"] == 128
        assert st["sound_plan"]["count"]["calls"] == 5 and not st["history"]["can_undo"]
        assert [p["music"] for p in st["music_phases"]] == ["chase_music", "boss_music", ""]
        before = doc_path.read_text(encoding="utf-8")
        assert w.call("vmodes.set_sound", "chase_music", {"tempo_bpm": 100, "fade_s": 2.5, "volume": 0.5}) is True
        d = json.loads(doc_path.read_text(encoding="utf-8"))
        s = {x["id"]: x for x in d["assets"]["sounds"]}["chase_music"]
        assert (s["tempo_bpm"], s["fade_s"], s["volume"]) == (100, 2.5, 0.5)
        assert w.state("vmodes")["history"]["can_undo"] is True
        assert w.state("vmodes")["history"]["undo_label"] == "Change a sound"
        assert w.call("vmodes.set_sound", "zap", {"id": "laser"}) is True
        d = json.loads(doc_path.read_text(encoding="utf-8"))
        assert {"on": "fire", "sound": "laser"} in d["cues"]
        assert w.call("vmodes.set_phase_music", "charge", "boss_music") is True
        assert w.call("vmodes.set_cues", [{"on": "won", "sound": "go_now", "duck_music": True},
                                          {"on": "nope", "sound": "go_now"}]) is True
        assert json.loads(doc_path.read_text(encoding="utf-8"))["cues"] == [{"on": "won", "sound": "go_now", "duck_music": True}]
        assert w.call("vmodes.remove_sound", "boom") is True             # nothing plays it now
        for _ in range(5):
            assert w.call("vmodes.edit_undo")["ok"] is True
        assert json.loads(doc_path.read_text(encoding="utf-8")) == json.loads(before)
        assert not w.state("vmodes")["history"]["can_undo"]
        assert w.call("vmodes.edit_redo")["ok"] is True
        assert {x["id"]: x for x in json.loads(doc_path.read_text(encoding="utf-8"))["assets"]["sounds"]}["chase_music"]["tempo_bpm"] == 100
        # a sound brought in: copied into sound/, an effect when short
        src = tmp_path / "Big Hit.wav"
        src.write_bytes(SND.placeholder_wav({"role": "effect"}, 3))
        assert w.call("vmodes.add_sound_file", str(src)) is True
        d = json.loads(doc_path.read_text(encoding="utf-8"))
        new = d["assets"]["sounds"][-1]
        assert new == {"id": "big_hit", "file": "sound/Big_Hit.wav", "role": "effect", "volume": 1.0}
        assert (md / "sound" / "Big_Hit.wav").is_file()
        # play_open hands each sound its length, its duck and a placeholder where its file is missing
        info = w.call("vmodes.play_open")
        snd = {x["id"]: x for x in info["sounds"]}
        assert snd["chase_music"]["placeholder"] and os.path.isfile(snd["chase_music"]["path"])
        assert snd["go_now"]["duck"] and 0.1 < snd["zap"]["seconds"] < 2


@pytest.mark.parametrize("name", ["vmodes_sound.js"])
def test_sound_card_module_parses(tmp_path, name):
    node = shutil.which("node")
    if not node:
        pytest.skip("no Node")
    mod = tmp_path / (name[:-3] + ".mjs")
    mod.write_text(open(os.path.join(JS, name), encoding="utf-8").read(), encoding="utf-8")
    got = subprocess.run([node, "--check", str(mod)], capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr
