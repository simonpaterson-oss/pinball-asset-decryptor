"""The button kinds of the video mode engine (PAD-1663): mash, alternate, tug of war, rhythm, button
sequence, quick dodge and hold shield.

Every kind's starter (the phase the picker makes, kinds_buttons.new_doc) is played to a win by the test
bot and to a loss with no buttons pressed, and both runs are golden replays: the same buttons give the
same draw list hash on the native engine and on WebAssembly. Rhythm is held to its windows (perfect,
good, early, late, miss) to the millisecond the engine can see, to the host's sound calibration, and to a
three-minute chart that never drifts.

Regenerate the goldens after a deliberate change to these kinds:
    python tests/test_video_mode_kinds2.py --regenerate
"""

import json
import os
import re
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinball_decryptor.core.video_mode import compiler, document, kinds_buttons  # noqa: E402
import test_video_mode_engine as te  # noqa: E402  (its runners and helpers)

GOLDEN = os.path.join(te.DATA, "kinds2")
KINDS = list(kinds_buttons.KINDS2)
IDLE_STEPS = 12000


def pack(kind, mutate=None):
    doc, _ = kinds_buttons.new_doc(kind)
    if mutate:
        mutate(doc)
    probs = document.check(doc)
    assert not probs, probs
    res = compiler.compile_doc(doc)
    assert res.ok, res.problems
    return res.pack


def goldens():
    path = os.path.join(GOLDEN, "golden.json")
    if not os.path.exists(path):      # only while --regenerate writes them the first time
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)["runs"]


def inputs_of(spec):
    if spec["inputs"] == "idle":
        return bytes(IDLE_STEPS)
    if spec["inputs"].startswith("random:"):
        _, seed, n = spec["inputs"].split(":")
        return te.random_inputs(int(seed), int(n))
    with open(os.path.join(GOLDEN, spec["inputs"]), "rb") as f:
        return f.read()


def events(out):
    """[(step, type, a, b, c)] from a runner's E lines."""
    return [tuple(int(v) for v in x.split()[1:6]) for x in out.splitlines() if x.startswith("E ")]


# ---- the starters: what the picker makes ----------------------------------------------------------------
@pytest.mark.parametrize("kind", KINDS)
def test_each_starter_checks_compiles_and_plays_its_own_kind(kind):
    doc, files = kinds_buttons.new_doc(kind)
    assert not document.check(doc)
    res = compiler.compile_doc(doc)
    assert res.ok, res.problems
    assert not [n for n in res.notes if "only for now" in n or "never ends" in n or "counted missed" in n], res.notes
    assert (kind == "rhythm") == bool(files)


@pytest.mark.parametrize("kind", KINDS)
def test_the_catalog_matches_the_schema(kind):
    sch = json.load(open(os.path.join(ROOT, "pinball_decryptor", "core", "video_mode", "video_mode.schema.json"),
                         encoding="utf-8"))["$defs"]["k_" + kind]["properties"]
    entry = kinds_buttons.KINDS2[kind]
    assert entry["label"] and entry["blurb"].endswith(".") and entry["buttons"]
    for st in entry["settings"]:
        assert st["name"] in sch, st["name"]
        assert st["help"].endswith(".") or st["help"].endswith(")"), st
        if "min" in st and isinstance(st["default"], (int, float)):
            assert st["min"] <= st["default"] <= st["max"], st
        if st["type"] == "choice":
            assert st["default"] in [c[0] for c in st["choices"]]
    assert entry["group"] == kinds_buttons.GROUP2
    for key in entry["starter"](kinds_buttons._Starter())["phase"]["settings"]:
        assert key in [s["name"] for s in entry["settings"]], key


def test_the_starter_beat_is_on_its_grid():
    """The rhythm starter's drum loop: a kick lands on every beat at 60/bpm seconds."""
    import array
    import io
    import wave
    data = kinds_buttons.beat_wav(120, 8)
    with wave.open(io.BytesIO(data)) as w:
        rate = w.getframerate()
        a = array.array("h", w.readframes(w.getnframes()))
    for beat in range(8):
        at = beat * rate // 2
        before = max(abs(v) for v in a[max(0, at - 400):at - 40]) if at else 0
        after = max(abs(v) for v in a[at:at + 480])
        assert after > 8000 and after > 3 * before, (beat, before, after)


# ---- golden replays: a win and a loss for every kind, the same on native and WebAssembly ------------------
@pytest.mark.parametrize("name", sorted(goldens()))
def test_golden_native(name):
    spec = goldens()[name]
    end = te.end_of(te.run(te.native(), pack(spec["kind"]), "--inputs", inputs_of(spec), "--max", spec["max"],
                           "--quiet").stdout)
    assert (end["hash"], int(end["steps"]), int(end["outcome"]), int(end["score"])) == \
        (spec["hash"], spec["steps"], spec["outcome"], spec["score"])


@pytest.mark.parametrize("name", sorted(goldens()))
def test_golden_wasm(name):
    spec = goldens()[name]
    end = te.end_of(te.run(te.wasm(), pack(spec["kind"]), "--inputs", inputs_of(spec), "--max", spec["max"],
                           "--quiet").stdout)
    assert (end["hash"], int(end["steps"]), int(end["outcome"])) == (spec["hash"], spec["steps"], spec["outcome"])


@pytest.mark.parametrize("kind", KINDS)
def test_each_kind_is_won_by_play_and_lost_by_none(kind):
    runs = goldens()
    assert runs[kind + "_win"]["outcome"] == 1 and runs[kind + "_loss"]["outcome"] == 0


@pytest.mark.parametrize("kind", KINDS)
def test_random_buttons_never_leave_bounds(kind):
    out = te.run(te.native(), pack(kind), "--fuzz", 200000, "--seed", 1663).stdout
    assert re.search(r"FUZZ steps=200000 plays=\d+ won=\d+ phases_reached=1 max_things=\d+ ok", out), out


# ---- what each kind asks of the player ---------------------------------------------------------------------
EV_GOOD, EV_PERFECT, EV_MISS = 13, 14, 15


def _rhythm_doc(chart, **settings):
    def mutate(doc):
        doc["phases"][0]["settings"]["chart"] = chart
        doc["phases"][0]["settings"].update(settings)
    return mutate


def _press_at(ms_list, button_bits, total):
    """Inputs pressing at each ms of the music (step k plays at k * 1000 / 60 ms), held one step."""
    buf = bytearray(total)
    for ms, bits in zip(ms_list, button_bits):
        k = int(round(ms * 60 / 1000.0))
        buf[k] |= bits
    return bytes(buf)


@pytest.mark.parametrize("offset", [0, 120])
def test_rhythm_windows_perfect_good_early_late_miss(offset):
    """Six notes a bar apart at 120 bpm (500 ms a beat, the first at beat 4 = 2000 ms); pressed 0, +70, -150,
    +150 and +260 ms off the beat, and the last not at all. With the host's sound heard `offset` ms late,
    the presses are made that much later too, as a player would."""
    chart = [{"beat": 4 + 4 * i, "button": "action"} for i in range(6)]
    p = pack("rhythm", _rhythm_doc(chart))
    off = [0, 70, -150, 150, 260]
    ins = _press_at([2000 + 2000 * i + d + offset for i, d in enumerate(off)], [4] * 5, 1800)
    out = te.run(te.native(), p, "--inputs", ins, "--max", 1800, "--audio-offset", offset).stdout
    got = [(t, a, c) for _, t, a, b, c in events(out) if t in (EV_GOOD, EV_PERFECT, EV_MISS)]
    assert got == [(EV_PERFECT, 2, 0), (EV_GOOD, 2, 0), (EV_GOOD, 2, 1), (EV_GOOD, 2, 2), (EV_MISS, 2, 0),
                   (EV_MISS, 2, 0)], got
    # the same presses on WebAssembly say the same
    assert te.lines(te.run(te.wasm(), p, "--inputs", ins, "--max", 1800, "--audio-offset", offset).stdout) == te.lines(out)


def test_rhythm_calibration_moves_the_judging_not_the_chart():
    """Presses exactly on the beat are perfect with no offset, and 'late by the offset' is perfect with it:
    an offset the player was not told about (presses on the beat, offset 120) makes every one late."""
    chart = [{"beat": 4 + 2 * i, "button": "left"} for i in range(5)]
    p = pack("rhythm", _rhythm_doc(chart))
    ins = _press_at([2000 + 1000 * i for i in range(5)], [1] * 5, 1200)
    kinds = lambda off: [(t, c) for _, t, a, b, c in events(te.run(te.native(), p, "--inputs", ins, "--max", 1200,
                                                                   "--audio-offset", off).stdout)
                         if t in (EV_GOOD, EV_PERFECT, EV_MISS)]
    assert kinds(0) == [(EV_PERFECT, 0)] * 5
    assert kinds(120) == [(EV_GOOD, 1)] * 5          # early: heard 120 ms after the engine thinks


def test_rhythm_held_note_must_be_held_to_its_end():
    chart = [{"beat": 4, "button": "right", "hold_beats": 2}, {"beat": 10, "button": "right", "hold_beats": 2}]
    p = pack("rhythm", _rhythm_doc(chart))
    ins = bytearray(1000)
    for k in range(120, 120 + 64):                   # 2000 ms, held 1066 ms: past its 1000 ms end
        ins[k] = 2
    for k in range(300, 300 + 20):                   # 5000 ms, let go after 333 ms: dropped
        ins[k] = 2
    out = te.run(te.native(), p, "--inputs", bytes(ins), "--max", 1000).stdout
    got = [t for _, t, a, b, c in events(out) if t in (EV_GOOD, EV_PERFECT, EV_MISS)]
    assert got == [EV_PERFECT, EV_PERFECT, EV_MISS], got


def test_rhythm_three_minutes_stays_on_the_beat():
    """A three-minute chart at 128 bpm (a beat is 468.75 ms, so its notes fall between steps): the bot
    presses on the step nearest each note and every one of 384 notes, the last one three minutes in, is
    still perfect, on native and on WebAssembly. The engine times each note from the music's start, never
    from the note before, so nothing builds up."""
    chart = [{"beat": 4 + i, "button": ["left", "action", "right"][i % 3]} for i in range(384)]

    def mutate(doc):
        doc["phases"][0]["settings"].update({"chart": chart, "tempo_bpm": 128})
    p = pack("rhythm", mutate)
    out = te.run(te.native(), p, "--bot", "--max", 13000).stdout
    ev = events(out)
    per = [e for e in ev if e[1] == EV_PERFECT]
    assert len(per) == 384 and not [e for e in ev if e[1] in (EV_GOOD, EV_MISS)]
    assert per[-1][0] / 60.0 > 180, per[-1]
    assert te.end_of(out)["outcome"] == "1"
    assert te.lines(te.run(te.wasm(), p, "--bot", "--max", 13000).stdout) == te.lines(out)


def test_rhythm_starts_its_music_from_the_top_even_when_it_was_playing():
    """Music plays on across phases (PAD-1667), but a rhythm phase's chart is timed from its music's start: a
    phase before it on the same bed is stopped and the bed started again, on the rhythm phase's first step."""
    def mutate(doc):
        doc["values"] = [{"id": "power", "type": "meter", "start": 0, "min": 0, "max": 100}]
        mash = {"id": "warm", "kind": "mash", "music": "beat", "length_s": 2, "settings": {"meter": "power"},
                "win": [{"when": "time_up"}], "lose": [{"when": "health_gone"}]}
        doc["phases"].insert(0, mash)
        cards = doc["flow"]["cards"]
        cards.insert(0, {"id": "c_warm", "card": "phase", "phase": "warm", "won": cards[0]["id"], "lost": cards[0]["id"]})
        doc["flow"]["start"] = "c_warm"
    out = te.run(te.native(), pack("rhythm", mutate), "--inputs", bytes(800), "--max", 800).stdout
    cues = [tuple(int(v) for v in x.split()[1:5]) for x in out.splitlines() if x.startswith("C ")]
    starts = [c for c in cues if c[2] == 1]
    assert len(starts) == 2 and starts[0][0] == 0, cues          # the warm-up's bed, then the rhythm's again
    k = cues.index(starts[1])
    assert cues[k - 1][2] == 2 and cues[k - 1][0] == starts[1][0] and cues[k - 1][1] == starts[1][1], cues


def test_the_machine_has_its_measured_sound_calibration():
    """vm_sound.h starts a mode with the machine's sound offset: measured on the emulator at 14 ms (the bed's request
    taken 13 ms after its cue, started at 14), under one step, overridable per build."""
    h = open(os.path.join(te.ENGINE, "vm_sound.h"), encoding="utf-8").read()
    m = re.search(r"#ifndef VM_SOUND_AUDIO_OFFSET_MS\s+#define VM_SOUND_AUDIO_OFFSET_MS (\d+)\s+#endif", h)
    assert m and 0 < int(m.group(1)) < 17
    assert "vm_set_audio_offset(e, VM_SOUND_AUDIO_OFFSET_MS)" in h


@pytest.mark.parametrize("kind", ["tug", "rhythm", "sequence", "dodge", "shield"])
def test_the_editors_scrub_sees_a_button_kind_as_played(kind):
    """PAD-1664's timeline scrub: the WebAssembly side jumps between snapshots of the play state, the native one
    plays each time from the phase's start. Back and forth over a button kind's phase they draw the same, so the
    kind's own state (its beat, its notes, its grab) is part of the snapshot."""
    p = pack(kind)
    at = "60,400,250,900,30,700"
    a = te.run(te.native(), p, "--seek", 0, "--at", at, "--endless").stdout
    b = te.run(te.wasm(), p, "--seek", 0, "--at", at, "--endless").stdout
    da = [x for x in a.splitlines() if x.startswith("D ")]
    assert len(da) == 6 and da == [x for x in b.splitlines() if x.startswith("D ")]


def test_tug_needs_the_named_flipper_held():
    """Mashing Action alone pulls nothing; with the named flipper held it pulls."""
    def mutate(doc):
        doc["phases"][0]["settings"].update({"hold": "left", "shake_every_s": 0})
    p = pack("tug", mutate)
    mash = bytes([4 if i % 8 == 0 else 0 for i in range(3000)])
    held = bytes([(4 if i % 8 == 0 else 0) | 1 for i in range(3000)])
    assert te.end_of(te.run(te.native(), p, "--inputs", mash, "--max", 3000).stdout)["outcome"] == "0"
    assert te.end_of(te.run(te.native(), p, "--inputs", held, "--max", 3000).stdout)["outcome"] == "1"


def test_tug_grab_is_shaken_off_by_alternating():
    """While grabbed, the mash does nothing until the flippers are alternated for its pairs."""
    p = pack("tug")
    out = te.run(te.native(), p, "--bot", "--max", 5000).stdout
    ev = events(out)
    shaken = [e for e in ev if e[1] == EV_GOOD]
    assert shaken and shaken[0][0] > 90 + 5 * 60, ev    # the first grab comes 5 s into the play


def test_sequence_wrong_button_is_a_miss_and_the_run_is_shown_again():
    p = pack("sequence")
    out = te.run(te.native(), p, "--inputs", bytes([1 if i % 30 == 0 else 0 for i in range(3000)]), "--max", 3000).stdout
    ev = events(out)
    assert [e[1] for e in ev].count(EV_MISS) == 3 and te.end_of(out)["outcome"] == "0"


def test_dodge_too_early_counts_against_you():
    """Pressing all the time, every button: each press in a tell is too early, so it is lost."""
    p = pack("dodge")
    out = te.run(te.native(), p, "--inputs", bytes([7 if i % 2 else 0 for i in range(4000)]), "--max", 4000).stdout
    assert te.end_of(out)["outcome"] == "0"


def test_shield_held_all_along_blocks_everything():
    p = pack("shield")
    out = te.run(te.native(), p, "--inputs", bytes([4] * 4000), "--max", 4000).stdout
    ev = events(out)
    assert [e[1] for e in ev].count(EV_PERFECT) == 5 and EV_MISS not in [e[1] for e in ev]
    assert te.end_of(out)["outcome"] == "1"


@pytest.mark.parametrize("kind,want", [("alternate", {530, 830}), ("tug", "held"), ("mash", {680})])
def test_prompts_are_the_cabinets_buttons_in_their_places(kind, want):
    """The glyphs are the cabinet's buttons where they sit on it: the left flipper button left of Action,
    the right one right of it (150 px either side of the stage's middle), drawn from boxes, no art."""
    from pinball_decryptor.core.video_mode import harness
    out = te.run(te.native(), pack(kind), "--bot", "--dump", 1, "--quiet", "--max", 200).stdout
    _, _, dumps, _ = harness.parse(out)
    step, words = dumps[150]                          # well into the play, past the title card
    discs = {round(e["x"] + e["w"] / 2) for e in harness.entries(words)
             if e["tag"] == "box" and 58 <= e["w"] <= 70 and e["h"] < 10 and e["y"] > 600}   # the prompts strip
    got = {x for x in discs if 400 < x < 960}
    if want == "held":                                # tug: Action, and the flipper it names full size
        assert 680 in got and len(got & {530, 830}) == 1, (step, sorted(discs))
    else:
        assert got == want, (step, sorted(discs))


# ---- regenerate -------------------------------------------------------------------------------------------
def regenerate():
    exe = te.harness.native_runner(os.path.join(tempfile.gettempdir(), "pad_vmrun_tests"))
    assert exe, "a C compiler is needed to regenerate the goldens"
    os.makedirs(GOLDEN, exist_ok=True)
    runs = {}
    import subprocess
    with tempfile.TemporaryDirectory() as td:
        for kind in KINDS:
            pk = os.path.join(td, kind + ".pack")
            with open(pk, "wb") as f:
                f.write(pack(kind))
            rec = os.path.join(GOLDEN, kind + "_win.inputs")
            subprocess.run(exe + [pk, "--bot", "--record", rec, "--quiet", "--max", "20000"], check=True, capture_output=True)
            for how, inputs, mx in (("win", kind + "_win.inputs", 20000), ("loss", "idle", IDLE_STEPS)):
                spec = {"kind": kind, "inputs": inputs, "max": mx}
                inp = os.path.join(td, "in")
                with open(inp, "wb") as f:
                    f.write(inputs_of(spec))
                out = subprocess.run(exe + [pk, "--inputs", inp, "--max", str(mx), "--quiet"], check=True,
                                     capture_output=True, text=True).stdout
                end = te.end_of(out)
                spec.update(hash=end["hash"], steps=int(end["steps"]), outcome=int(end["outcome"]), score=int(end["score"]))
                runs["%s_%s" % (kind, how)] = spec
                print(kind, how, end)
    with open(os.path.join(GOLDEN, "golden.json"), "w", newline="\n") as f:
        json.dump({"about": "PAD-1663 golden replays of the button kinds' starters: a win (the bot's buttons) and a loss "
                            "(none). Regenerate: python tests/test_video_mode_kinds2.py --regenerate",
                   "runs": runs}, f, indent=2)
        f.write("\n")


if __name__ == "__main__" and "--regenerate" in sys.argv:
    regenerate()
