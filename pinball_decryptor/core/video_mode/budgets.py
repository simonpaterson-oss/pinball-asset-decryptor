"""What each machine takes, for a video mode (docs/plans/video_mode_maker.md section 5).

The plan's table is the source; this is the same table in code, and
tests/test_video_mode_pack.py reads the plan's rows and proves the two agree, so a
platform ticket that measures its machine (PAD-1655 Spike 2, 1673 Spike 3, 1674 JJP,
1675 Spooky, 1676 dots) changes both in one branch or the test says which row moved.
The numbers are placeholders until those tickets measure them.

``texel_bytes`` is what one texel of a packed atlas costs in the machine's memory:
4 for RGBA8, the format every backend loads today (docs/plans/video_mode_maker.md
section 4, "Premultiplied pictures"). No mipmaps: the stage is drawn at scale 1 or
larger.

``art_scale`` is the size art is packed at against the stage: 1 for a screen that shows
the stage at its own size or larger; 1/8 for dot-matrix screens, which show the stage at
1/10.625 (128 dots for 1360 px, section 4), so a packed texel still covers less than a
dot. atlas.json says it as ``texel_scale`` (stage px per texel) for the backend.
"""

MB = 1024 * 1024

#: key -> what the machine takes
MACHINES = {
    "spike2": {"label": "Stern Spike 2", "memory": 48 * MB, "atlas": 2048, "card": 128 * MB, "texel_bytes": 4,
               "backend": "spike2"},
    "spike3": {"label": "Stern Spike 3", "memory": 128 * MB, "atlas": 4096, "card": 256 * MB, "texel_bytes": 4,
               "backend": "spike3"},
    "jjp": {"label": "Jersey Jack", "memory": 96 * MB, "atlas": 4096, "card": 256 * MB, "texel_bytes": 4,
            "backend": "jjp"},
    "spooky": {"label": "Spooky", "memory": 96 * MB, "atlas": 4096, "card": 256 * MB, "texel_bytes": 4,
               "backend": "spooky"},
    "dots": {"label": "Dot-matrix screens (CGC, Spike 1)", "memory": 4 * MB, "atlas": 512, "card": 16 * MB,
             "texel_bytes": 4, "backend": "dots", "art_scale": 0.125},
}
ORDER = ("spike2", "spike3", "jjp", "spooky", "dots")
DEFAULT = "spike2"

#: The plan's column heading for each machine, so the test can find it.
PLAN_COLUMN = {"spike2": "Spike 2", "spike3": "Spike 3", "jjp": "JJP", "spooky": "Spooky",
               "dots": "Dots (CGC, Spike 1)"}


def machine(key):
    m = MACHINES.get(key or DEFAULT)
    if m is None:
        raise ValueError("No budgets for %r; the machines are %s." % (key, ", ".join(ORDER)))
    return dict({"art_scale": 1.0}, **m, key=key or DEFAULT)
