"""Writes stage_300.json beside this file (PAD-1661): the 300-thing desk's pictures and things, with one custom phase
whose stage holds 300 placed things at their first step (a mixed grid, scaled and turned), for the editor's
"a 300-thing stage stays at 60 fps while dragging". Deterministic: run it again and the file does not change.

    python tests/data/video_mode/make_stage_300.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    with open(os.path.join(HERE, "desk_300.json"), encoding="utf-8") as f:
        doc = json.load(f)
    doc["id"] = "stage-300"
    doc["title"] = "Stage 300"
    doc["notes"] = "300 things placed on one stage, for the editor's frame rate (PAD-1661). Made by make_stage_300.py."
    kinds = ["drone", "mine", "crate", "gold_crate", "sight", "shell", "swarm_orbit", "swarm_path"]
    place = []
    for i in range(300):
        col, row = i % 20, i // 20
        p = {"thing": kinds[i % len(kinds)], "x": 40 + col * 67, "y": 40 + row * 46}
        if i % 3 == 1:
            p["scale"] = 0.6
        if i % 5 == 2:
            p["turn"] = (i * 37) % 360 - 180
        place.append(p)
    doc["phases"] = [{"id": "stage", "kind": "custom", "title": "Stage", "settings": {}, "place": place,
                      "win": [{"when": "survive_s", "value": 30}], "lose": [{"when": "time_up"}]}]
    doc["flow"] = {"start": "c_stage", "cards": [
        {"id": "c_stage", "card": "phase", "phase": "stage", "won": "e_won", "lost": "e_lost"},
        {"id": "e_won", "card": "end", "outcome": "won"}, {"id": "e_lost", "card": "end", "outcome": "lost"}]}
    for k in ("hud", "cues"):
        doc.pop(k, None)
    with open(os.path.join(HERE, "stage_300.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(doc, indent=2) + "\n")


if __name__ == "__main__":
    main()
