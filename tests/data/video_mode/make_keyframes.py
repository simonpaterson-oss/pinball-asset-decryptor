"""PAD-1664: writes keyframes.json (the timeline's test document) and format_3.json (the frozen format 3 fixture)
from the worked example, Night Harbour.

    python tests/data/video_mode/make_keyframes.py

keyframes.json keeps Night Harbour's art, things, HUD and sounds, and starts with a 20 s "parade" phase (a custom
phase: nothing to play, only the timeline) whose placed things use every kind of track and every easing: a drone
flown on a bezier path through four keys, a mine scaled with bounce_out, a crate turned with a curve of its own, a
gold crate faded out and back, a shell tinted red to clear, and sounds at set times. The boss phase follows with its
warship bobbing on keys while the game plays (the sight sweeping, the shells homing), then the ends.
"""
import copy
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXAMPLE = os.path.join(ROOT, "pinball_decryptor", "core", "video_mode", "examples", "night_harbour.json")

PARADE = {
    "id": "parade", "kind": "custom", "title": "Parade", "objective": "Watch the keys", "length_s": 20,
    "background": [{"picture": "skyline", "speed": 0, "y": 0}],
    "settings": {},
    "place": [
        {"thing": "drone", "x": 120, "y": 200},
        {"thing": "mine", "x": 680, "y": 420},
        {"thing": "crate", "x": 300, "y": 600},
        {"thing": "gold_crate", "x": 1060, "y": 600},
        {"thing": "shell", "x": 680, "y": 160},
        {"thing": "warship", "x": 680, "y": 560, "depth": -5},
    ],
    "tracks": [
        {"place": 0, "prop": "motion", "keys": [
            {"at_s": 0, "x": 120, "y": 200, "out": [220, -120], "ease": "in_out"},
            {"at_s": 4, "x": 680, "y": 180, "in": [-200, 0], "out": [200, 0], "ease": "out"},
            {"at_s": 9.5, "x": 1240, "y": 300, "in": [0, -160], "out": [-60, 260], "curve": [0.25, 0, 0.55, 1.1]},
            {"at_s": 15, "x": 400, "y": 360, "in": [300, 120], "ease": "back_out"},
            {"at_s": 18, "x": 120, "y": 200}]},
        {"place": 0, "prop": "turn", "keys": [{"at_s": 0, "v": 0, "ease": "linear"}, {"at_s": 18, "v": 720}]},
        {"place": 1, "prop": "scale", "keys": [
            {"at_s": 1, "v": 0.4, "ease": "bounce_out"}, {"at_s": 3, "v": 2.0, "ease": "elastic_out"},
            {"at_s": 8, "v": 1.0, "ease": "step"}, {"at_s": 12, "v": 0.6}]},
        {"place": 2, "prop": "turn", "keys": [
            {"at_s": 2, "v": -30, "curve": [0.7, -0.6, 0.3, 1.6]}, {"at_s": 6, "v": 30, "ease": "in"}, {"at_s": 10, "v": -30}]},
        {"place": 2, "prop": "motion", "keys": [
            {"at_s": 0, "x": 300, "y": 600, "ease": "linear"}, {"at_s": 20, "x": 1000, "y": 600}]},
        {"place": 3, "prop": "alpha", "keys": [
            {"at_s": 2, "v": 1, "ease": "in"}, {"at_s": 5, "v": 0, "ease": "out"}, {"at_s": 8, "v": 1}]},
        {"place": 4, "prop": "tint", "keys": [
            {"at_s": 0, "tint": "#ff3030ff", "ease": "in_out"}, {"at_s": 6, "tint": "#ffffff40", "ease": "linear"},
            {"at_s": 12, "tint": "#40c0ffff"}]},
        {"place": 5, "prop": "motion", "keys": [
            {"at_s": 0, "x": -300, "y": 560, "ease": "out"}, {"at_s": 5, "x": 680, "y": 560, "ease": "in"},
            {"at_s": 19, "x": 1700, "y": 560}]},
        # the mine, the gold crate and the shell scroll or home by themselves: one key each holds them in place
        {"place": 1, "prop": "motion", "keys": [{"at_s": 0, "x": 680, "y": 420}]},
        {"place": 3, "prop": "motion", "keys": [{"at_s": 0, "x": 1060, "y": 600}]},
        {"place": 4, "prop": "motion", "keys": [{"at_s": 0, "x": 680, "y": 160}]},
    ],
    "sound_track": [{"at_s": 0.5, "sound": "go_now"}, {"at_s": 4, "sound": "zap"}, {"at_s": 9.5, "sound": "boom"},
                    {"at_s": 15, "sound": "chime"}],
    "win": [{"when": "time_up"}],
    "lose": [],
}


def keyframes_doc():
    d = json.load(open(EXAMPLE, encoding="utf-8"))
    d["id"] = "keyframes"
    d["title"] = "Keyframes"
    boss = copy.deepcopy(next(p for p in d["phases"] if p["id"] == "boss"))
    boss["tracks"] = [
        {"place": 0, "prop": "motion", "keys": [
            {"at_s": 0, "x": 680, "y": 330, "out": [0, -40], "ease": "in_out"},
            {"at_s": 3, "x": 560, "y": 300, "in": [-60, 0], "out": [60, 0], "ease": "in_out"},
            {"at_s": 6, "x": 800, "y": 300, "in": [60, 0], "out": [-60, 0], "ease": "in_out"},
            {"at_s": 9, "x": 680, "y": 330}]},
        {"place": 0, "prop": "turn", "keys": [{"at_s": 0, "v": -4, "ease": "in_out"}, {"at_s": 4.5, "v": 4, "ease": "in_out"},
                                              {"at_s": 9, "v": -4}]},
    ]
    boss["sound_track"] = [{"at_s": 2, "sound": "go_now"}]
    d["phases"] = [PARADE, boss]
    d["flow"] = {"start": "c_parade", "cards": [
        {"id": "c_parade", "card": "phase", "phase": "parade", "won": "c_boss", "lost": "c_boss"},
        {"id": "c_boss", "card": "phase", "phase": "boss", "won": "e_won", "lost": "e_lost"},
        {"id": "e_won", "card": "end", "outcome": "won"},
        {"id": "e_lost", "card": "end", "outcome": "lost"}]}
    d["hud"] = [h for h in d.get("hud", []) if not h.get("phases") or set(h["phases"]) & {"parade", "boss"}]
    for h in d["hud"]:
        if h.get("phases"):
            h["phases"] = [p for p in h["phases"] if p in ("parade", "boss")]
    awards = (d.get("pays") or {}).get("awards") or []
    d.setdefault("pays", {})["awards"] = [a for a in awards if a.get("phase") in (None, "parade", "boss")]
    return d


def main():
    d = keyframes_doc()
    with open(os.path.join(HERE, "keyframes.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    fixture = json.load(open(EXAMPLE, encoding="utf-8"))
    fixture["phases"][1]["tracks"] = copy.deepcopy(d["phases"][1]["tracks"])
    fixture["phases"][1]["sound_track"] = [{"at_s": 2, "sound": "go_now"}]
    fixture["editor"] = {"markers": {"boss": [{"at_s": 3, "label": "Bob left"}]}}
    with open(os.path.join(HERE, "format_3.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
