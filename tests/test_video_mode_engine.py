"""The video mode engine and its compiler (PAD-1657).

The engine is one plain C core (pinball_decryptor/core/video_mode/engine) built native for
these tests and to WebAssembly for the app (vm_engine.wasm, committed). The golden runs
hold both to the same draw list hash, run by run, so the editor plays what the machine
plays. Native tests need a C compiler (cc, gcc, clang, or zig via VM_ZIG / the ziglang
wheel); WebAssembly tests need Node. Each skips without its tool.

Regenerate the goldens after a deliberate change to the engine or the compiler:
    python tests/test_video_mode_engine.py --regenerate
"""
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pinball_decryptor.core.video_mode import compiler, document, harness  # noqa: E402

ENGINE = os.path.join(ROOT, "pinball_decryptor", "core", "video_mode", "engine")
sys.path.insert(0, ENGINE)
import build  # noqa: E402
import gen_tables  # noqa: E402

sys.path.pop(0)

DATA = os.path.join(ROOT, "tests", "data", "video_mode")
GOLDEN = os.path.join(DATA, "golden")
EXAMPLE = os.path.join(ROOT, "pinball_decryptor", "core", "video_mode", "examples", "night_harbour.json")
DESK = os.path.join(DATA, "desk_300.json")
HEADER = os.path.join(ENGINE, "vm_engine.h")

pytestmark = pytest.mark.xdist_group("video_mode_engine")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def random_inputs(seed, n):
    """Buttons mashed at random, and now and then the host saying a clip ended."""
    rng = random.Random(seed)
    out = bytearray()
    held = 0
    for _ in range(n):
        if rng.random() < 0.2:
            held = rng.randrange(8)
        out.append(held | (8 if rng.random() < 0.01 else 0))
    return bytes(out)


# ---- runners ----------------------------------------------------------------
_native = []


def native():
    if not _native:
        try:
            _native.append(harness.native_runner(os.path.join(tempfile.gettempdir(), "pad_vmrun_tests")))
        except RuntimeError as e:   # a compiler that would not build it is a failure, not a skip
            pytest.fail(str(e))
    if not _native[0]:
        pytest.skip("no C compiler for the native engine")
    return _native[0]


def wasm():
    r = harness.wasm_runner()
    if not r:
        pytest.skip("no Node for the WebAssembly engine")
    return r


def run(runner, pack, *args, check=True):
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "m.pack")
        with open(p, "wb") as f:
            f.write(pack)
        args = list(args)
        for i, a in enumerate(args):
            if isinstance(a, bytes):    # inputs given as bytes
                q = os.path.join(td, "in%d" % i)
                with open(q, "wb") as f:
                    f.write(a)
                args[i] = q
        r = subprocess.run(runner + [p] + [str(a) for a in args], capture_output=True, text=True, timeout=600)
    if check:
        assert r.returncode == 0, r.stdout[-500:] + r.stderr[-500:]
    return r


def pack_of(path):
    res = compiler.compile_file(path)
    assert res.ok, res.problems
    return res.pack


def golden_runs():
    path = os.path.join(GOLDEN, "golden.json")
    return load_json(path)["runs"] if os.path.exists(path) else {}


def run_args(spec):
    doc = os.path.join(ROOT, spec["doc"])
    if spec["inputs"].startswith("random:"):
        _, seed, n = spec["inputs"].split(":")
        inputs = random_inputs(int(seed), int(n))
    else:
        with open(os.path.join(GOLDEN, spec["inputs"]), "rb") as f:
            inputs = f.read()
    return pack_of(doc), ["--inputs", inputs, "--seed", spec["seed"], "--level", spec["level"], "--max", spec["max"]]


def end_of(out):
    line = [x for x in out.splitlines() if x.startswith("END ")][-1]
    return dict(kv.split("=") for kv in line.split()[1:])


def lines(out):
    return [x.rstrip("\r") for x in out.splitlines() if x[:2] in ("E ", "C ", "D ", "EN")]


# ---- the codes and limits the compiler shares with the C -------------------------
def header_enum(first):
    """The names of the enum whose first member is `first`, in order."""
    text = open(HEADER, encoding="utf-8").read()
    m = re.search(r"enum\s*\{([^}]*\b%s\b[^}]*)\}" % re.escape(first), text)
    assert m, first
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    return [x.split("=")[0].strip() for x in body.split(",") if x.strip()]


@pytest.mark.parametrize("first,prefix,names", [
    ("VM_TEAM_PLAYER", "VM_TEAM_", compiler.TEAMS),
    ("VM_MV_NONE", "VM_MV_", compiler.MOVERS),
    ("VM_EASE_LINEAR", "VM_EASE_", compiler.EASINGS),
    ("VM_K_CHASE", "VM_K_", compiler.KINDS),
    ("VM_W_TIME_UP", "VM_W_", compiler.WHENS),
    ("VM_CARD_CLIP", "VM_CARD_", compiler.CARDS),
    ("VM_HUD_HEALTH", "VM_HUD_", compiler.HUD_PARTS),
    ("VM_LOOK_DEFAULT", "VM_LOOK_", compiler.LOOKS),
    ("VM_TR_CUT", "VM_TR_", compiler.TRANSITIONS),
    ("VM_BTN_LEFT", "VM_BTN_", compiler.BUTTONS),
    ("VM_ON_FIRE", "VM_ON_", compiler.CUE_ON),
])
def test_compiler_codes_match_the_engine(first, prefix, names):
    want = [n[len(prefix):].lower() for n in header_enum(first)]
    alias = {"survive": "survive_s"}
    assert [alias.get(w, w) for w in want] == names


def test_fixed_strings_match_the_engine():
    assert header_enum("VM_S_CLEAR")[:-1] == ["VM_S_%s" % n for n in (
        "CLEAR", "FAILED", "TRY_AGAIN", "STEER", "FIRE", "LEFT", "RIGHT", "ACTION", "MASH", "BOSS_DOWN", "HOLD")]
    assert len(compiler.FIXED_STRINGS) == len(header_enum("VM_S_CLEAR")) - 1


def test_compiler_limits_match_the_engine():
    text = open(HEADER, encoding="utf-8").read()
    caps = {k: int(v) for k, v in re.findall(r"#define VM_MAX_(\w+)\s+(\d+)", text)}
    pairs = {"strings": "STRINGS", "string_bytes": "STRBYTES", "fonts": "FONTS", "pictures": "PICTURES",
             "animations": "ANIMS", "frames": "FRAMES", "values": "VALUES", "things": "KINDS", "movers": "MOVERS",
             "path_points": "PATHPTS", "phases": "PHASES", "layers": "LAYERS", "places": "PLACES",
             "spawns": "SPAWNS", "conditions": "CONDS", "weak_points": "WEAKPTS", "attacks": "ATTACKS",
             "cards": "CARDS", "hud": "HUD", "cues": "CUES", "sounds": "SOUNDS", "clips": "CLIPS"}
    for py, c in pairs.items():
        assert compiler.LIMITS[py] == caps[c], py
    assert caps["SETTINGS"] >= compiler.LIMITS["phases"]


# ---- the compiler ---------------------------------------------------------------------
def test_night_harbour_compiles_the_same_every_time():
    a, b = compiler.compile_file(EXAMPLE), compiler.compile_file(EXAMPLE)
    assert a.ok and a.pack == b.pack
    assert a.pack[:4] == b"VMP1" and a.pack[-4:] == b"END!"
    assert int.from_bytes(a.pack[8:12], "little") * 4 == len(a.pack)
    # the placeholder art is noted, nothing else: every kind it uses plays
    assert all("placeholder" in n for n in a.notes), a.notes


def _doc():
    return document.migrate(load_json(EXAMPLE))


def test_compiler_problems_say_where_in_plain_words():
    d = _doc()
    d["phases"][0]["spawns"][1]["lane"] = 5
    d["phases"][1]["settings"].pop("sight")
    res = compiler.compile_doc(d)
    assert not res.ok and res.pack is None
    assert 'phases[0] "chase" > spawns[1] > lane: lane 5 is past the chase\'s 3 lanes (lanes count from 0)' in res.problems
    assert 'phases[1] "boss" > settings: a boss hit with the sight needs a sight thing' in res.problems


def test_compiler_refuses_what_the_engine_cannot_hold():
    d = _doc()
    for i in range(100):
        d["things"].append({"id": "extra_%d" % i, "picture": "mine", "team": "scenery"})
    res = compiler.compile_doc(d)
    assert "the document has 109 things; the engine holds up to 96" in res.problems


def test_compiler_passes_on_the_checkers_problems():
    d = _doc()
    d["phases"][0]["spawns"][0]["thing"] = "no_such_thing"
    res = compiler.compile_doc(d)
    assert not res.ok and any("no_such_thing" in p for p in res.problems)


def test_compiler_notes_what_does_not_play_yet():
    d = _doc()
    d["phases"][2]["kind"] = "custom"
    d["phases"][2]["settings"] = {}
    d["phases"][2]["win"] = [{"when": "accuracy", "value": 50}]
    d["phases"][0]["rules"] = [{"when": {"event": "phase_starts"}, "then": [{"do": "score", "value": 10}]}]
    probs = document.check(d)
    assert not probs, probs
    res = compiler.compile_doc(d)
    assert res.ok, res.problems
    assert any("'accuracy' never ends the phase" in n for n in res.notes)
    assert any("rule cards are kept but not played yet (PAD-1665)" in n for n in res.notes)


def test_lanes_are_rows_across_the_sea():
    """The chase's lanes split the band from the lowest background layer to the stage's foot."""
    res = compiler.compile_file(EXAMPLE)
    c = compiler._Compiler(_doc(), None, {}, {})
    c.run()
    top, bot = c.lane_band(_doc()["phases"][0])
    assert (top, bot) == (300 * 65536, 768 * 65536)
    assert res.ok


# ---- the WebAssembly module is built from these sources -------------------------------
def test_committed_wasm_is_built_from_the_current_sources():
    with open(build.WASM + ".sha") as f:
        stamp = f.read().strip()
    assert stamp == build.source_hash(), (
        "vm_engine.wasm is older than the engine's C: run python pinball_decryptor/core/video_mode/engine/build.py wasm")
    with open(build.WASM, "rb") as f:
        assert f.read(4) == b"\0asm"


# ---- golden replays: same document + inputs = same draw list hash, everywhere ---------
@pytest.mark.parametrize("name", sorted(golden_runs()))
def test_golden_native(name):
    spec = golden_runs()[name]
    pack, args = run_args(spec)
    end = end_of(run(native(), pack, *(args + ["--quiet"])).stdout)
    assert (end["hash"], int(end["steps"]), int(end["outcome"]), int(end["score"])) == \
        (spec["hash"], spec["steps"], spec["outcome"], spec["score"])


@pytest.mark.parametrize("name", sorted(golden_runs()))
def test_golden_wasm(name):
    spec = golden_runs()[name]
    pack, args = run_args(spec)
    end = end_of(run(wasm(), pack, *(args + ["--quiet"])).stdout)
    assert (end["hash"], int(end["steps"]), int(end["outcome"]), int(end["score"])) == \
        (spec["hash"], spec["steps"], spec["outcome"], spec["score"])


def test_native_and_wasm_say_the_same_thing_every_step():
    """Not just the hash: every event, sound cue and dumped draw list, line for line."""
    spec = golden_runs()["night_harbour_bot"]
    pack, args = run_args(spec)
    a = lines(run(native(), pack, *(args + ["--dump", "97"])).stdout)
    b = lines(run(wasm(), pack, *(args + ["--dump", "97"])).stdout)
    assert len(a) > 100 and a == b


def test_the_bot_plays_the_same_on_both():
    pack = pack_of(EXAMPLE)
    a = end_of(run(native(), pack, "--bot", "--quiet").stdout)
    b = end_of(run(wasm(), pack, "--bot", "--quiet").stdout)
    assert a == b and a["outcome"] == "1"


# ---- the worked example plays start to finish in the text harness -------------------
def test_night_harbour_plays_start_to_finish_in_the_text_harness():
    native()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = harness.main([EXAMPLE, "--bot", "--every", "1", "--engine", "native"])
    out = buf.getvalue()
    assert rc == 0, out
    order = ["clip intro plays", "phase chase starts", "drone down", "picked up crate", "phase chase WON",
             "phase boss starts", "weak point 0 hit", "warship down", "phase boss WON", "phase charge starts",
             "phase charge WON", "clip won_clip plays", "FINISHED: won"]
    at = [out.find(s) for s in order]
    assert all(x >= 0 for x in at) and at == sorted(at), list(zip(order, at))
    assert "Chase | Reach the warship" in out          # the title card, read back off the glyph quads
    assert re.search(r"CRATES [1-4] ", out) and "BOSS DOWN!" in out and "LEFT | RIGHT" in out
    assert "Warship | Hit the weak spots" in out and "Full speed | Left, right, left, right!" in out
    assert "outcome won" in out


def test_draw_list_keeps_the_contract():
    pack = pack_of(EXAMPLE)
    _, _, dumps, _ = harness.parse(run(native(), pack, "--bot", "--dump", "31", "--quiet").stdout)
    assert len(dumps) > 50
    names = compiler.compile_file(EXAMPLE).names
    for step, w in dumps:
        assert (w[0], w[1]) == (0x314C4456, step)
        es = harness.entries(w)
        assert len(es) == w[2]                                   # every entry parses, nothing left over
        assert w[7] == 1                                          # cover_game
        depths = [x for x in (((y[1] >> 16) ^ 0x8000) - 0x8000 for y in _quad_words(w)) if -1000 <= x <= 1000]
        assert depths == sorted(depths), step                    # things in depth order
        for e in es:
            if e["tag"] == "quad":
                assert e["atlas"] < len(names["pictures"]) or e["atlas"] >= compiler.FONT_ATLAS_BASE


def _quad_words(w):
    i = 8
    while i < len(w):
        if w[i] & 0xFF == 1:
            yield w[i:i + 12]
            i += 12
        else:
            i += 6


# ---- bounds: random buttons for a million steps, and broken packs ---------------------
def test_a_million_random_steps_never_leave_bounds():
    for path, n in ((EXAMPLE, 1000000), (DESK, 200000)):
        out = run(native(), pack_of(path), "--fuzz", n, "--seed", 1657).stdout
        m = re.search(r"FUZZ steps=%d plays=\d+ won=(\d+) phases_reached=(\d+) max_things=\d+ ok" % n, out)
        assert m, out
        if path == EXAMPLE:   # every phase played, some plays won (the desk cannot be won)
            assert int(m.group(1)) > 0 and int(m.group(2)) == 7, out


def test_broken_packs_are_refused_not_run():
    pack = bytearray(pack_of(EXAMPLE))
    rng = random.Random(1657)
    refused = 0
    with tempfile.TemporaryDirectory() as td:
        for k in range(120):
            bad = bytearray(pack)
            for _ in range(rng.randrange(1, 4)):
                i = rng.randrange(12, len(bad) - 4) & ~3
                bad[i:i + 4] = rng.choice([0xFFFFFFFF, 0x7FFFFFFF, 0x80000000, rng.randrange(1 << 32), 1000, 97]).to_bytes(4, "little")
            if k % 10 == 0:
                bad = bad[:rng.randrange(0, len(bad))]
            r = run(native(), bytes(bad), "--fuzz", 3000, "--seed", k, check=False)
            assert r.returncode in (0, 3), (k, r.returncode, r.stdout[-300:], r.stderr[-300:])
            refused += r.returncode == 3
    assert refused >= 20


@pytest.mark.skipif(not sys.platform.startswith("linux") or not shutil.which("gcc"), reason="sanitizers: gcc on Linux")
def test_fuzz_under_the_address_and_undefined_behaviour_sanitizers():
    with tempfile.TemporaryDirectory() as td:
        try:
            exe = build.build_native(td, cc=["gcc"], extra=["-O1", "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=all"])
        except RuntimeError as e:
            pytest.skip("gcc has no sanitizers here: %s" % str(e)[-200:])
        for path in (EXAMPLE, DESK):
            out = run([exe], pack_of(path), "--fuzz", 150000, "--seed", 3).stdout
            assert " ok" in out, out


# ---- the budget: a step with 300 things on the desk -------------------------------------
def test_a_step_with_300_things_costs_well_under_a_millisecond():
    out = run(native(), pack_of(DESK), "--bench", 6000).stdout
    m = dict(kv.split("=") for kv in out.split()[1:])
    assert int(m["max_things"]) >= 300 and int(m["steps_at_300"]) > 3000, out
    assert float(m["us_per_step_at_300"]) < 500, out    # measured: ~33 us on a desktop x86


@pytest.mark.skipif(not shutil.which("arm-linux-gnueabihf-gcc"), reason="needs the Spike 2 cross compiler")
def test_engine_object_keeps_the_mode_rules():
    with tempfile.TemporaryDirectory() as td:
        obj, undefined = build.build_arm(td)
    # only what mode.so already allows: libgcc's division helpers, the unwinder, memset/memcpy
    allowed = re.compile(r"^(__aeabi_\w+|__gnu_\w+|memset|memcpy|memmove)$")
    assert [u for u in undefined if not allowed.match(u)] == [], undefined


# ---- the integer tables are what the generator makes --------------------------------
def test_tables_are_what_gen_tables_writes(tmp_path, monkeypatch):
    out = tmp_path / "vm_tables.h"
    real_join = os.path.join
    monkeypatch.setattr(gen_tables.os.path, "join", lambda *a: str(out) if a[-1] == "vm_tables.h" else real_join(*a))
    gen_tables.main()
    with open(os.path.join(ENGINE, "vm_tables.h"), encoding="utf-8") as f:
        assert out.read_text(encoding="utf-8") == f.read()   # text mode: CRLF checkouts read the same


# ---- regenerate ------------------------------------------------------------------------
def regenerate():
    exe = harness.native_runner()
    assert exe, "a C compiler is needed to regenerate the goldens"
    os.makedirs(GOLDEN, exist_ok=True)
    pack = pack_of(EXAMPLE)
    rec = os.path.join(GOLDEN, "night_harbour_bot.inputs")
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "m.pack")
        with open(p, "wb") as f:
            f.write(pack)
        subprocess.run(exe + [p, "--bot", "--record", rec, "--quiet"], check=True, capture_output=True)
    runs = {
        "night_harbour_bot": {"doc": "pinball_decryptor/core/video_mode/examples/night_harbour.json",
                              "inputs": "night_harbour_bot.inputs", "seed": 1, "level": 0, "max": 200000},
        "night_harbour_random": {"doc": "pinball_decryptor/core/video_mode/examples/night_harbour.json",
                                 "inputs": "random:1657:40000", "seed": 9, "level": 2, "max": 40000},
        "desk_300_random": {"doc": "tests/data/video_mode/desk_300.json",
                            "inputs": "random:300:6000", "seed": 4, "level": 0, "max": 6000},
    }
    for name, spec in runs.items():
        pk, args = run_args(spec)
        end = end_of(run(exe, pk, *(args + ["--quiet"])).stdout)
        spec.update(hash=end["hash"], steps=int(end["steps"]), outcome=int(end["outcome"]), score=int(end["score"]))
        print(name, end)
    with open(os.path.join(GOLDEN, "golden.json"), "w", newline="\n") as f:
        json.dump({"about": "PAD-1657 golden replays: document + inputs -> draw list hash. "
                            "Regenerate: python tests/test_video_mode_engine.py --regenerate",
                   "runs": runs}, f, indent=2)
        f.write("\n")


if __name__ == "__main__" and "--regenerate" in sys.argv:
    regenerate()
