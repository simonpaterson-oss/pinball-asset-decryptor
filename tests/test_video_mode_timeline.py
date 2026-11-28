"""PAD-1664: the video mode timeline. Keyframed motion of placed things (motion on bezier paths, scale, turn, alpha,
tint; easing presets or a curve of its own), sounds at set times, and the editor's scrub, which is a replay.

Proved here:
- the document: format 2's tracks and sound track, and every way they can be wrong, in plain words;
- the compiler: tracks, keys, baked curves and timed sounds into the engine's tables, and what it refuses;
- the engine: keyframed things are where their keys say (checked against the same maths in Python, to the pixel),
  a scrub draws exactly what the game draws at that step with nothing pressed, on native and on WebAssembly and in
  any order through the snapshots, and 60 s of timeline scrubs in well under a frame a seek;
- the machine's build: the same goldens from the Spike 2's ARM build of the engine under qemu, where the cross
  compiler and qemu are there (WSL here; the Linux runners).

Golden hashes are in tests/data/video_mode/golden/golden.json (keyframes_idle, keyframes_random) and run on native
and WebAssembly with the rest in test_video_mode_engine.py.
"""
import copy
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_video_mode_engine as te  # noqa: E402

from pinball_decryptor.core.video_mode import compiler, document  # noqa: E402

DATA = te.DATA
KEYFRAMES = os.path.join(DATA, "keyframes.json")
STAGE300 = os.path.join(DATA, "stage_300.json")
ONE = 65536

pytestmark = pytest.mark.xdist_group("video_mode_engine")


def doc_of(path=KEYFRAMES):
    return document.migrate(te.load_json(path))


def problems(doc):
    return document.check(doc)


def dumps(out):
    """{step: [words]} from "D step w0 w1 ..." lines."""
    got = {}
    for line in out.splitlines():
        if line.startswith("D "):
            p = line.split()
            got[int(p[1])] = [int(w, 16) for w in p[2:]]
    return got


def quads(words):
    """The quads of a draw list's words: (x, y, scale_x, turn, tint, alpha) in stage px / degrees."""
    out, i = [], 8
    while i < len(words):
        tag = words[i] & 0xFF
        if tag == 1:
            w = words[i:i + 12]
            sx = w[8] - (1 << 32) if w[8] >= 1 << 31 else w[8]
            t = w[10] - (1 << 32) if w[10] >= 1 << 31 else w[10]
            x = w[4] - (1 << 32) if w[4] >= 1 << 31 else w[4]
            y = w[5] - (1 << 32) if w[5] >= 1 << 31 else w[5]
            out.append((x / ONE, y / ONE, sx / ONE, t / ONE, w[11], (w[0] >> 16) & 0xFF))
            i += 12
        else:
            i += 6
    return out


# ---- the document ---------------------------------------------------------------------
def test_keyframes_document_and_the_format_3_fixture_check_clean():
    assert problems(doc_of()) == []
    assert problems(doc_of(os.path.join(DATA, "format_3.json"))) == []
    assert document.FORMAT >= 3 and doc_of()["format"] == document.FORMAT   # PAD-1666 took format 4


@pytest.mark.parametrize("n", [1, 2])
def test_an_older_file_gains_nothing_and_plays_the_same(n):
    old = te.load_json(os.path.join(DATA, "format_%d.json" % n))
    new = document.migrate(old)
    assert new["format"] == document.FORMAT and all("tracks" not in p and "sound_track" not in p for p in new["phases"])
    old2 = copy.deepcopy(old)
    old2["format"] = document.FORMAT
    assert new == old2


BAD = [
    ("place past the list", lambda p: p["tracks"][0].update(place=9), 'tracks[0] > place: names place 9, but the phase places 6 things'),
    ("two motion tracks", lambda p: p["tracks"].append(copy.deepcopy(p["tracks"][0])), "is a second motion track for place 0 (track 0 is the first)"),
    ("keys out of order", lambda p: p["tracks"][0]["keys"][2].update(at_s=3), "keys[2] > at_s: is not after the key before it (4 s)"),
    ("keys in one step", lambda p: p["tracks"][0]["keys"][1].update(at_s=0.005), "keys[1] > at_s: is not after the key before it (0 s)"),
    ("motion without y", lambda p: p["tracks"][0]["keys"][1].pop("y"), "a motion key needs y"),
    ("v on motion", lambda p: p["tracks"][0]["keys"][1].update(v=2), "keys[1] > v: is not part of a motion key"),
    ("handle on scale", lambda p: p["tracks"][2]["keys"][0].update(out=[1, 2]), "keys[0] > out: is not part of a scale key"),
    ("alpha above 1", lambda p: p["tracks"][5]["keys"][0].update(v=1.5), "keys[0] > v: must be within 0..1 for alpha (it is 1.5)"),
    ("scale of 0", lambda p: p["tracks"][2]["keys"][0].update(v=0), "keys[0] > v: must be more than 0"),
    ("tint as v", lambda p: p["tracks"][6]["keys"][0].update(v=1, tint=None) or p["tracks"][6]["keys"][0].pop("tint"), "a tint key needs tint"),
    ("curve backwards", lambda p: p["tracks"][3]["keys"][0].update(curve=[1.5, 0, 0.5, 1]), "x1 and x2 must be within 0..1"),
    ("ease and curve", lambda p: p["tracks"][3]["keys"][0].update(ease="in"), "has both ease and curve"),
    ("unknown prop", lambda p: p["tracks"][0].update(prop="colour"), "prop: must be one of"),
    ("sound not there", lambda p: p["sound_track"][0].update(sound="nope"), 'sound_track[0] > sound: names "nope", but there is no sound with that id'),
    ("a key's unknown field", lambda p: p["tracks"][0]["keys"][0].update(speed=3), "speed: is not a field this format knows"),
]


@pytest.mark.parametrize("name,spoil,says", BAD, ids=[b[0] for b in BAD])
def test_a_wrong_timeline_is_refused_in_plain_words(name, spoil, says):
    doc = doc_of()
    spoil(doc["phases"][0])
    got = problems(doc)
    assert any(says in g for g in got), got


# ---- the compiler -----------------------------------------------------------------------
def test_tracks_compile_into_the_engines_tables():
    res = compiler.compile_doc(doc_of())
    assert res.ok, res.problems
    parade = doc_of()["phases"][0]
    k0 = res.names["track_keys"]
    assert k0[0] == [0, 5, 7, 11, 14, 16, 19, 22, 25, 26, 27] and k0[1] == [28, 32]
    assert sum(len(t["keys"]) for p in doc_of()["phases"] for t in p.get("tracks", [])) == 35
    assert len(parade["tracks"]) == 11


def test_curves_bake_from_0_to_1_and_overshoot_where_the_curve_does():
    lin = compiler.bake_curve([0, 0, 1, 1])
    assert lin[0] == 0 and lin[-1] == ONE and all(abs(v - round(i * ONE / 32)) <= 2 for i, v in enumerate(lin))
    back = compiler.bake_curve([0.7, -0.6, 0.3, 1.6])
    assert min(back) < 0 and max(back) > ONE and len(back) == compiler.CURVE_PTS
    ease = compiler.bake_curve([0.42, 0, 0.58, 1])        # CSS ease-in-out: half way at half time
    assert abs(ease[16] - ONE // 2) < 40


def test_compiler_refuses_keys_too_far_off_the_stage():
    doc = doc_of()
    doc["phases"][0]["tracks"][0]["keys"][1]["x"] = 4000
    res = compiler.compile_doc(doc)
    assert not res.ok and any("tracks[0] > keys[1]: is 4000, 180: more than a stage's width" in p for p in res.problems), res.problems


def test_compiler_refuses_more_keys_than_the_engine_holds_across_phases():
    doc = doc_of()
    base = doc["phases"][0]
    keys = [{"at_s": j * 0.05, "v": 1} for j in range(200)]
    doc["phases"] = []
    for n in range(4):
        ph = copy.deepcopy(base)
        ph["id"] = "p%d" % n
        ph["tracks"] = [{"place": i, "prop": prop, "keys": copy.deepcopy(keys)} for i in range(6) for prop in ("scale", "alpha")][:6]
        doc["phases"].append(ph)
    doc["flow"] = {"start": "c0", "cards": [{"id": "c%d" % n, "card": "phase", "phase": "p%d" % n,
                                             "won": "c%d" % (n + 1) if n < 3 else "e", "lost": "e"} for n in range(4)]
                   + [{"id": "e", "card": "end", "outcome": "won"}]}
    doc["hud"] = [h for h in doc["hud"] if not h.get("phases")]
    doc["pays"]["awards"] = [a for a in doc["pays"].get("awards", []) if not a.get("phase")]
    assert problems(doc) == []
    res = compiler.compile_doc(doc)        # 4 phases x 6 tracks x 200 keys = 4800 > 4096
    assert not res.ok and any("4800 keyframes; the engine holds up to 4096" in p for p in res.problems), res.problems


def test_a_motion_track_on_the_player_is_noted():
    doc = doc_of(te.EXAMPLE)
    chase = doc["phases"][0]
    i = next(n for n, p in enumerate(chase["place"]) if p["thing"] == chase["settings"]["player"])
    chase["tracks"] = [{"place": i, "prop": "motion", "keys": [{"at_s": 0, "x": 200, "y": 600}, {"at_s": 2, "x": 300, "y": 600}]}]
    res = compiler.compile_doc(doc)
    assert res.ok and any("its steering does nothing while the keys run" in n for n in res.notes), res.notes


# ---- the engine: keyed things are where the keys say -------------------------------------------
def ease_py(kind, t):
    """compiler.EASINGS in floats: the reference the engine's fixed point is held to."""
    import math
    t = min(1.0, max(0.0, t))
    if kind == "in":
        return t * t
    if kind == "out":
        return 1 - (1 - t) ** 2
    if kind == "in_out":
        return 2 * t * t if t < 0.5 else 1 - 2 * (1 - t) ** 2
    if kind == "back_out":
        c1, c3 = 1.70158, 2.70158
        return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2
    if kind == "bounce_out":
        n1, d1 = 7.5625, 2.75
        if t < 1 / d1:
            return n1 * t * t
        if t < 2 / d1:
            t -= 1.5 / d1
            return n1 * t * t + 0.75
        if t < 2.5 / d1:
            t -= 2.25 / d1
            return n1 * t * t + 0.9375
        t -= 2.625 / d1
        return n1 * t * t + 0.984375
    if kind == "elastic_out":
        return t if t in (0, 1) else 2 ** (-10 * t) * math.sin((10 * t - 0.75) * 2 * math.pi / 3) + 1
    if kind == "step":
        return 0.0 if t < 1 else 1.0
    return t


def expect(track, step):
    """Where a track puts its property at a play step, in floats."""
    keys = track["keys"]
    at = [round(k["at_s"] * 60) for k in keys]
    if step <= at[0]:
        s, w = 0, 0.0
    elif step >= at[-1]:
        s, w = len(keys) - 1, 0.0
    else:
        s = max(i for i in range(len(keys) - 1) if at[i] <= step)
        u = (step - at[s]) / (at[s + 1] - at[s])
        if keys[s].get("curve"):
            y = compiler.bake_curve(keys[s]["curve"])
            f = u * 32
            i = min(31, int(f))
            w = (y[i] + (y[i + 1] - y[i]) * (f - i)) / ONE
        else:
            w = ease_py(keys[s].get("ease", "linear"), u)
    k0 = keys[s]
    if w == 0:
        if track["prop"] == "motion":
            return (k0["x"], k0["y"])
        if track["prop"] == "tint":
            a = int((k0["tint"] + "ff")[1:9], 16)
            return tuple((a >> sh) & 255 for sh in (24, 16, 8, 0))
        return k0["v"]
    k1 = keys[s + 1]
    if track["prop"] == "motion":
        def bz(p0, p1, p2, p3):
            m = 1 - w
            return m ** 3 * p0 + 3 * m * m * w * p1 + 3 * m * w * w * p2 + w ** 3 * p3
        o, i_ = k0.get("out", (0, 0)), k1.get("in", (0, 0))
        dx, dy = k1["x"] - k0["x"], k1["y"] - k0["y"]
        if not any(o):                                   # a missing handle: a third of the way along the line
            o = (dx / 3, dy / 3)
        if not any(i_):
            i_ = (-dx / 3, -dy / 3)
        return (bz(k0["x"], k0["x"] + o[0], k1["x"] + i_[0], k1["x"]), bz(k0["y"], k0["y"] + o[1], k1["y"] + i_[1], k1["y"]))
    if track["prop"] == "tint":
        a, b = int((k0["tint"] + "ff")[1:9], 16), int((k1["tint"] + "ff")[1:9], 16)
        return tuple(((a >> sh) & 255) + (((b >> sh) & 255) - ((a >> sh) & 255)) * w for sh in (24, 16, 8, 0))
    return k0["v"] + (k1["v"] - k0["v"]) * w


def test_keyed_things_are_where_their_keys_say_at_every_second():
    doc = doc_of()
    parade = doc["phases"][0]
    pack = compiler.compile_doc(doc).pack
    steps = list(range(0, 1200, 37)) + [240, 570, 900, 1080]
    got = dumps(te.run(te.native(), pack, "--seek", 0, "--at", ",".join(map(str, sorted(set(steps))))).stdout)
    checked = 0
    for step, words in got.items():
        qs = quads(words)
        # the parade's quads come after the background's tiles, in depth order; find each placed thing by its tracks
        for tr in parade["tracks"]:
            pl = parade["place"][tr["place"]]
            want = expect(tr, step)
            if tr["prop"] == "motion":
                near = min(qs, key=lambda q: (q[0] - want[0]) ** 2 + (q[1] - want[1]) ** 2)
                assert abs(near[0] - want[0]) < 0.6 and abs(near[1] - want[1]) < 0.6, (step, pl["thing"], near, want)
            elif tr["prop"] in ("scale", "turn"):
                continue       # test_turn_and_scale_keys_reach_the_draw_list
            elif tr["prop"] == "alpha":
                xs = [q for q in qs if abs(q[0] - pl["x"]) < 0.01 and abs(q[1] - pl["y"]) < 0.01]
                assert xs and abs(xs[0][5] - want * 255) <= 1.01, (step, xs[0][5], want * 255)
            elif tr["prop"] == "tint":
                xs = [q for q in qs if abs(q[0] - pl["x"]) < 0.01 and abs(q[1] - pl["y"]) < 0.01]
                t = xs[0][4]
                for n, sh in enumerate((24, 16, 8, 0)):
                    assert abs(((t >> sh) & 255) - max(0, min(255, want[n]))) <= 1.01, (step, hex(t), want)
            checked += 1
    assert checked > 200


def test_turn_and_scale_keys_reach_the_draw_list():
    doc = doc_of()
    parade = doc["phases"][0]
    pack = compiler.compile_doc(doc).pack
    got = dumps(te.run(te.native(), pack, "--seek", 0, "--at", "150,420,700").stdout)
    turn_tr = parade["tracks"][3]                 # the crate turned by a curve; it also slides on a straight track
    slide = parade["tracks"][4]
    scale_tr = parade["tracks"][2]
    mine = parade["place"][1]
    for step, words in got.items():
        qs = quads(words)
        x, y = expect(slide, step)
        crate = min(qs, key=lambda q: (q[0] - x) ** 2 + (q[1] - y) ** 2)
        assert abs(crate[3] - expect(turn_tr, step)) < 0.05, (step, crate, expect(turn_tr, step))
        at_mine = [q for q in qs if abs(q[0] - mine["x"]) < 0.01 and abs(q[1] - mine["y"]) < 0.01]
        assert at_mine
        scales = {round(q[2], 3) for q in at_mine}
        want = expect(scale_tr, step)
        assert any(abs(s / want - round(s / want)) < 0.01 or abs(s - want) < 0.01 for s in scales), (step, scales, want)


# ---- the engine: scrubbing is replaying ----------------------------------------------------------
@pytest.mark.parametrize("phase,card", [(0, 0), (1, 1)])
def test_a_scrub_draws_what_the_game_draws_at_that_step(phase, card):
    """Start here on the phase's card and press nothing: after the title card's 90 steps, play step S is the run's
    step 89 + S. The seek draws the same list, word for word, on native and WebAssembly (in any order there, through
    its snapshots)."""
    pack = compiler.compile_doc(doc_of()).pack
    real = dumps(te.run(te.native(), pack, "--card", card, "--dump", 1, "--quiet", "--max", 1290).stdout)
    at = [0, 1, 2, 59, 60, 61, 119, 120, 333, 600, 777, 1100]
    if phase == 1:
        at = [s for s in at if s < 1100]    # the boss phase is lost at play step 1139 with nothing pressed
    nat = dumps(te.run(te.native(), pack, "--seek", phase, "--at", ",".join(map(str, at))).stdout)
    shuffled = at[:]
    random.Random(7).shuffle(shuffled)
    wa = dumps(te.run(te.wasm(), pack, "--seek", phase, "--at", ",".join(map(str, shuffled))).stdout)
    for s in at:
        assert nat[s] == real[89 + s], s
        assert wa[s] == nat[s], s


def test_an_endless_scrub_runs_past_the_phases_end():
    pack = compiler.compile_doc(doc_of()).pack
    real = te.run(te.native(), pack, "--card", 1, "--max", 4000).stdout
    ended = [l for l in real.splitlines() if l.startswith("E ") and l.split()[2] in ("4", "5")]
    assert ended, "the boss phase ends by itself with nothing pressed"
    end_step = int(ended[0].split()[1]) - 89
    late = end_step + 300
    a = dumps(te.run(te.native(), pack, "--seek", 1, "--at", late, "--endless").stdout)[late]
    b = dumps(te.run(te.wasm(), pack, "--seek", 1, "--at", late, "--endless").stdout)[late]
    assert a == b and a[2] > 0     # still drawing the phase


def test_sixty_seconds_of_timeline_scrub_instantly():
    """The plan's bar: scrubbing 60 s of timeline is instant. The first seek to the end makes a snapshot a second
    (one replay of the minute); after that any seek plays at most 59 steps from the one before it."""
    rng = random.Random(1664)
    for path, phase in ((KEYFRAMES, 0), (STAGE300, 0)):
        pack = compiler.compile_doc(doc_of(path)).pack
        at = [3599] + [rng.randrange(3600) for _ in range(300)]
        out = te.run(te.wasm(), pack, "--seek", phase, "--at", ",".join(map(str, at)), "--endless", "--time").stdout
        m = dict(kv.split("=") for kv in out.split("SEEKTIME")[1].split())
        assert float(m["first_ms"]) < 400, (path, out)      # measured here: ~10 ms (keyframes), ~14 ms (300 things)
        assert float(m["rest_avg_ms"]) < 2, (path, out)     # measured here: ~0.07 ms, ~0.11 ms
        print(path, out.strip())


def test_timed_sounds_play_at_their_seconds():
    pack = compiler.compile_doc(doc_of()).pack
    out = te.run(te.native(), pack, "--card", 0, "--max", 1300).stdout
    names = compiler.compile_doc(doc_of()).names["sounds"]
    cues = [(int(l.split()[1]) - 89, names[int(l.split()[2])]) for l in out.splitlines()
            if l.startswith("C ") and l.split()[3] == "0"]
    want = [(round(t["at_s"] * 60) + 1, t["sound"]) for t in doc_of()["phases"][0]["sound_track"]]
    assert [c for c in cues if c in want] == want, cues


# ---- the machine's build -----------------------------------------------------------------------------------------
def _wsl_arm():
    if sys.platform.startswith("linux"):
        ok = shutil.which("arm-linux-gnueabihf-gcc") and shutil.which("qemu-arm-static")
        return ["bash", "-c"] if ok else None
    if os.name == "nt" and shutil.which("wsl"):
        try:
            r = subprocess.run(["wsl", "-e", "bash", "-c", "command -v arm-linux-gnueabihf-gcc && command -v qemu-arm-static"],
                               capture_output=True, text=True, timeout=60)
        except Exception:  # noqa: BLE001 - no WSL to speak of
            return None
        return ["wsl", "-e", "bash", "-c"] if r.returncode == 0 else None
    return None


def _wsl_path(p):
    if os.name != "nt":
        return p
    p = os.path.abspath(p).replace("\\", "/")
    return "/mnt/%s%s" % (p[0].lower(), p[2:])


def test_the_spike2_arm_build_plays_the_keyframe_goldens_the_same():
    """The engine as mode.so builds it (armhf, hard float), linked into a runner and run under qemu: the same hash
    as native and WebAssembly for the keyframe goldens, and the same scrub."""
    sh = _wsl_arm()
    if not sh:
        pytest.skip("needs the Spike 2 cross compiler and qemu-arm-static (WSL Ubuntu here)")
    eng = _wsl_path(te.ENGINE)
    with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(__file__))) as td:
        pack = compiler.compile_doc(doc_of()).pack
        with open(os.path.join(td, "kf.pack"), "wb") as f:
            f.write(pack)
        spec = te.golden_runs()["keyframes_random"]
        _, args = te.run_args(spec)
        with open(os.path.join(td, "kf.inputs"), "wb") as f:
            f.write(args[1])
        t = _wsl_path(td)
        script = ("set -e; O=$(mktemp -d); F='-std=gnu17 -O2 -marm -mfloat-abi=hard -fno-stack-protector'; "
                  "arm-linux-gnueabihf-gcc $F -c %(e)s/vm_engine.c -o $O/e.o; "
                  "arm-linux-gnueabihf-gcc -std=gnu17 -O2 -static -I%(e)s %(e)s/vm_cli.c %(e)s/vm_bot.c $O/e.o -o $O/vmrun; "
                  "qemu-arm-static $O/vmrun %(t)s/kf.pack --inputs %(t)s/kf.inputs --seed %(s)d --level %(l)d --max %(m)d --quiet | tail -1; "
                  "qemu-arm-static $O/vmrun %(t)s/kf.pack --max 6000 --quiet | tail -1; "
                  "qemu-arm-static $O/vmrun %(t)s/kf.pack --seek 0 --at 0,61,600,1199; rm -rf $O"
                  % {"e": eng, "t": t, "s": spec["seed"], "l": spec["level"], "m": spec["max"]})
        r = subprocess.run(sh + [script], capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, r.stdout[-500:] + r.stderr[-500:]
        ends = [te.end_of(l) for l in r.stdout.splitlines() if l.startswith("END ")]
        assert ends[0]["hash"] == spec["hash"], (ends[0], spec)
        assert ends[1]["hash"] == te.golden_runs()["keyframes_idle"]["hash"]
        nat = dumps(te.run(te.native(), pack, "--seek", 0, "--at", "0,61,600,1199").stdout)
        assert dumps(r.stdout) == nat
