"""What each machine takes, for a video mode (docs/plans/video_mode_maker.md section 5).

The plan's table is the source; this is the same table in code, and
tests/test_video_mode_pack.py reads the plan's rows and proves the two agree, so a
platform ticket that measures its machine (PAD-1655 Spike 2, 1673 Spike 3, 1674 JJP,
1675 Spooky, 1676 dots) changes both in one branch or the test says which row moved.
Spike 2 is measured (PAD-1655, docs/plans/video_mode_spike2_drawing.md): its runtime sends every
picture to GL as RGBA8, w x h x 4 bytes, and its "KB of pictures on GL" line read 12,039 KB for a
set whose atlases sum to exactly that; the 48 MB and 2048 x 2048 budgets were kept. The other
machines' numbers are placeholders until their tickets measure them (``measured`` False).

``card_atlas`` is how the machine's card holds a packed atlas: ``"raw"`` when the runtime maps the
texels straight in (Spike 2's ``.padgfx`` set file: w x h x 4 bytes a picture plus its tables, so
the card costs what memory does), ``"zlib"`` when it is written compressed and unpacked on load.

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
               "backend": "spike2", "card_atlas": "raw", "measured": True},
    "spike3": {"label": "Stern Spike 3", "memory": 128 * MB, "atlas": 4096, "card": 256 * MB, "texel_bytes": 4,
               "backend": "spike3"},
    "jjp": {"label": "Jersey Jack", "memory": 96 * MB, "atlas": 4096, "card": 256 * MB, "texel_bytes": 4,
            "backend": "jjp"},
    "spooky": {"label": "Spooky", "memory": 96 * MB, "atlas": 4096, "card": 256 * MB, "texel_bytes": 4,
               "backend": "spooky"},
    "dots": {"label": "Dot-matrix screens (CGC, Spike 1)", "memory": 4 * MB, "atlas": 512, "card": 16 * MB,
             "texel_bytes": 4, "backend": "dots", "art_scale": 0.125},
}
#: What the screen draws each frame and the engine keeps alive (the plan's "Things alive at once", "Quads drawn a
#: frame" and "Draw calls a frame" rows; 0 = not limited there). The app's player (PAD-1659) meters against them.
PLAY = {
    "spike2": {"things": 300, "quads": 1500, "draw_calls": 16},
    "spike3": {"things": 500, "quads": 3000, "draw_calls": 32},
    "jjp": {"things": 400, "quads": 2000, "draw_calls": 24},
    "spooky": {"things": 400, "quads": 2000, "draw_calls": 24},
    "dots": {"things": 100, "quads": 400, "draw_calls": 0},
}
for _k, _v in PLAY.items():
    MACHINES[_k].update(_v)
del _k, _v

ORDER = ("spike2", "spike3", "jjp", "spooky", "dots")
DEFAULT = "spike2"

#: The plan's column heading for each machine, so the test can find it.
PLAN_COLUMN = {"spike2": "Spike 2", "spike3": "Spike 3", "jjp": "JJP", "spooky": "Spooky",
               "dots": "Dots (CGC, Spike 1)"}

#: Spike 2's set file (``.padgfx``, pinball_decryptor/plugins/stern/gfx_set.py from PAD-1655): a 24-byte header,
#: 40 bytes a picture and a font, 16 a glyph, then each picture's texels, 4-aligned.
PADGFX = {"header": 24, "picture": 40, "font": 40, "glyph": 16}


def machine(key):
    m = MACHINES.get(key or DEFAULT)
    if m is None:
        raise ValueError("No budgets for %r; the machines are %s." % (key, ", ".join(ORDER)))
    return dict({"art_scale": 1.0, "card_atlas": "zlib", "measured": False}, **m, key=key or DEFAULT)
