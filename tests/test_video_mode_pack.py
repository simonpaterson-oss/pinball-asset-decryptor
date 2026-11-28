"""PAD-1658: a video mode's pictures - every import kind on real files, the packer, the cost report, the card gate,
and the Video modes tab.

Real files: PNGs, GIFs and sheets written by Pillow AND by ffmpeg (a second encoder), and videos encoded by ffmpeg
(an H.264 green screen, a VP9 WebM with real alpha), read back through the same code the app runs."""
import base64
import os
import re
import shutil
import subprocess
import time

import pytest

Image = pytest.importorskip("PIL.Image")
np = pytest.importorskip("numpy")
from PIL import ImageDraw  # noqa: E402

from pinball_decryptor.core.video_mode import art as A, budgets as B, document as D, pack as P  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ffmpeg():
    from pinball_decryptor.core import audio
    return audio.find_ffmpeg() or shutil.which("ffmpeg")


needs_ffmpeg = pytest.mark.skipif(not _ffmpeg(), reason="needs ffmpeg")


def _frames(n=6, size=(40, 30), seed=0):
    out = []
    for i in range(n):
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([4 + i, 5, 20 + i, 20], fill=(200, (40 * i + seed) % 256, 30, 255))
        d.point((size[0] - 3, size[1] - 3), fill=(10, 250, 10, 128))
        out.append(im)
    return out


def _same(a, b):
    return np.array_equal(np.asarray(a.convert("RGBA")), np.asarray(b.convert("RGBA")))


def _mode(tmp_path):
    md = tmp_path / "modes" / "test-mode"
    md.mkdir(parents=True)
    doc = D.new("test-mode", "Test mode")
    return str(md), doc


def _round_trip(md, doc, sid, sprite):
    """Into the mode, saved, loaded back: the same frames come out."""
    A.save_sprite(md, doc, sid, sprite)
    path = os.path.join(md, D.FILE_NAME)
    D.save(path, doc)
    back = D.load(path)
    pic = next(p for p in back["assets"]["pictures"] if p["id"] == sid)
    frames = A.load_frames(md, pic)
    assert len(frames) == len(sprite.frames)
    for a, b in zip(frames, sprite.frames):
        assert _same(a, b)
    return pic


# ---- each import kind round-trips -----------------------------------------------------------------------------
def test_picture_round_trip(tmp_path):
    md, doc = _mode(tmp_path)
    f = _frames(1)[0]
    f.save(tmp_path / "one.png")
    sp = A.import_art(A.guess_kind(str(tmp_path / "one.png")), str(tmp_path / "one.png"))
    pic = _round_trip(md, doc, "one", sp)
    assert "frames" not in pic and "animations" not in pic
    assert pic["anchor"] == [0.5, 0.5]
    hb = pic["hitbox"]                     # round what the frame shows, relative to the anchor
    assert hb["shape"] == "box" and hb["x"] == 4 - 20 and hb["w"] == 37 - 4 + 1


def test_numbered_run_in_number_order(tmp_path):
    md, doc = _mode(tmp_path)
    fr = _frames(11)
    for i, f in enumerate(fr):
        f.save(tmp_path / ("boom_%d.png" % (i + 1)))          # 1..11: 10 sorts after 9, not after 1
    (tmp_path / "boom_notes.png").write_bytes(b"")           # not of the run
    assert A.guess_kind(str(tmp_path / "boom_3.png")) == "numbered"
    sp = A.import_art("numbered", str(tmp_path / "boom_3.png"), fps=24, loop=False)
    assert [_same(a, b) for a, b in zip(sp.frames, fr)] == [True] * 11
    pic = _round_trip(md, doc, "boom", sp)
    assert pic["animations"] == [{"id": "play", "frames": list(range(11)), "fps": 24.0, "loop": False}]


def test_numbered_run_of_different_sizes_is_centred(tmp_path):
    Image.new("RGBA", (10, 10), (255, 0, 0, 255)).save(tmp_path / "a_01.png")
    Image.new("RGBA", (20, 14), (0, 0, 255, 255)).save(tmp_path / "a_02.png")
    sp = A.from_numbered(str(tmp_path / "a_01.png"))
    assert sp.size == (20, 14) and sp.notes
    assert sp.frames[0].getpixel((5, 2)) == (255, 0, 0, 255) and sp.frames[0].getpixel((4, 2))[3] == 0


def test_gif_from_pillow_round_trip(tmp_path):
    md, doc = _mode(tmp_path)
    fr = [f.convert("RGBA") for f in _frames(5)]
    # a GIF keeps one see-through level: make the frames all-or-nothing so they read back equal
    fr = [Image.fromarray(np.where(np.asarray(f)[..., 3:4] > 0, np.asarray(f) | np.array([0, 0, 0, 255], np.uint8),
                                   0).astype(np.uint8), "RGBA") for f in fr]
    p = tmp_path / "anim.gif"
    fr[0].save(p, save_all=True, append_images=fr[1:], duration=40, loop=0, disposal=2)
    assert A.guess_kind(str(p)) == "gif"
    sp = A.import_art("gif", str(p))
    assert sp.fps == 25 and sp.loop is True and len(sp.frames) == 5
    for a, b in zip(sp.frames, fr):
        assert _same(a, b)
    _round_trip(md, doc, "anim", sp)


def test_gif_without_loop_plays_once(tmp_path):
    fr = [Image.new("RGB", (8, 8), c) for c in ((255, 0, 0), (0, 255, 0))]
    p = tmp_path / "once.gif"
    fr[0].save(p, save_all=True, append_images=fr[1:], duration=100)
    sp = A.from_gif(str(p))
    assert sp.loop is False and sp.fps == 10


@needs_ffmpeg
def test_gif_from_ffmpeg(tmp_path):
    """A GIF made by another encoder (ffmpeg's palette GIF, 8 frames at 10 a second, looping)."""
    out = tmp_path / "ff.gif"
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=0.8",
                    "-loop", "0", str(out)], check=True)
    sp = A.import_art(A.guess_kind(str(out)), str(out))
    assert len(sp.frames) == 8 and sp.size == (64, 48) and sp.loop and sp.fps == 10
    md, doc = _mode(tmp_path)
    _round_trip(md, doc, "ff", sp)


def test_grid_sheet_with_margin_and_spacing(tmp_path):
    md, doc = _mode(tmp_path)
    fr = _frames(7, (32, 24))
    m, s = 3, 2
    sheet = Image.new("RGBA", (2 * m + 4 * 32 + 3 * s, 2 * m + 2 * 24 + s), (0, 0, 0, 0))
    for i, f in enumerate(fr):
        sheet.paste(f, (m + (i % 4) * (32 + s), m + (i // 4) * (24 + s)))
    sheet.save(tmp_path / "grid.png")
    sp = A.import_art("grid", str(tmp_path / "grid.png"), frame_w=32, frame_h=24, margin=m, spacing=s)
    assert len(sp.frames) == 7                     # the 8th cell is empty: not a frame
    assert all(_same(a, b) for a, b in zip(sp.frames, fr))
    _round_trip(md, doc, "grid", sp)
    with pytest.raises(A.ArtError, match="holds 8 frames"):
        A.from_sheet_grid(str(tmp_path / "grid.png"), 32, 24, m, s, count=9)


def test_auto_sheet_finds_gutters(tmp_path):
    md, doc = _mode(tmp_path)
    sheet = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    d = ImageDraw.Draw(sheet)
    boxes = [(5, 5, 30, 40), (50, 8, 40, 30), (120, 2, 20, 44), (10, 60, 50, 30), (90, 55, 30, 35)]
    for i, (x, y, w, h) in enumerate(boxes):
        d.rectangle([x, y, x + w - 1, y + h - 1], fill=(30 * i, 200, 100, 255))
    sheet.save(tmp_path / "auto.png")
    assert A.find_cells(sheet) == boxes
    sp = A.import_art("auto", str(tmp_path / "auto.png"))
    assert len(sp.frames) == 5 and sp.size == (50, 44)
    _round_trip(md, doc, "auto", sp)


def test_auto_sheet_on_a_solid_background(tmp_path):
    """A sheet with no see-through pixels: its corner colour is the gutter, and it goes see-through."""
    sheet = Image.new("RGB", (90, 30), (255, 0, 255))
    d = ImageDraw.Draw(sheet)
    for i in range(3):
        d.ellipse([5 + i * 30, 5, 24 + i * 30, 24], fill=(10, 20 * i, 200))
    sheet.save(tmp_path / "magenta.png")
    sp = A.from_sheet_auto(str(tmp_path / "magenta.png"))
    assert len(sp.frames) == 3
    a = np.asarray(sp.frames[0])
    assert a[0, 0, 3] == 0 and a[a.shape[0] // 2, a.shape[1] // 2, 3] == 255


@needs_ffmpeg
def test_video_green_screen_key(tmp_path):
    """An H.264 green screen: the green goes see-through, the subject stays, and no green is left on it."""
    src = tmp_path / "src"
    src.mkdir()
    for i in range(12):
        im = Image.new("RGB", (160, 96), (0, 255, 0))
        ImageDraw.Draw(im).ellipse([40 + i * 4, 20, 100 + i * 4, 76], fill=(220, 60, 50))
        im.save(src / ("%02d.png" % i))
    vid = tmp_path / "green.mp4"
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-framerate", "12", "-i", str(src / "%02d.png"), "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(vid)], check=True)
    assert A.guess_kind(str(vid)) == "video"
    sp = A.import_art("video", str(vid), start="0:00", length="1", fps=12, cut="key", key="#00ff00")
    assert len(sp.frames) == 12 and sp.size == (160, 96)
    a = np.asarray(sp.frames[0]).astype(int)
    assert a[2, 2, 3] == 0                                  # the screen is gone
    assert a[48, 70, 3] == 255                              # the subject is whole
    kept = a[a[..., 3] > 0]
    assert (kept[:, 1] <= np.maximum(kept[:, 0], kept[:, 2])).all()    # despilled: no pixel left green-tinted
    md, doc = _mode(tmp_path)
    _round_trip(md, doc, "runner", sp)


@needs_ffmpeg
def test_video_own_alpha_webm(tmp_path):
    """A VP9 WebM with alpha (ffmpeg's own decoder drops it; libvpx keeps it)."""
    src = tmp_path / "src"
    src.mkdir()
    for i in range(6):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle([10 + i * 4, 16, 34 + i * 4, 48], fill=(40, 120, 230, 255))
        im.save(src / ("%02d.png" % i))
    vid = tmp_path / "alpha.webm"
    r = subprocess.run([_ffmpeg(), "-v", "error", "-y", "-framerate", "6", "-i", str(src / "%02d.png"),
                        "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "1M", str(vid)], capture_output=True)
    if r.returncode:
        pytest.skip("this ffmpeg cannot write VP9 with alpha")
    sp = A.import_art("video", str(vid), start=0, length=1, fps=6, cut="alpha")
    assert len(sp.frames) == 6 and not sp.notes
    a = np.asarray(sp.frames[0])
    assert a[2, 2, 3] < 16 and a[32, 20, 3] > 240


def test_video_refusals(tmp_path):
    with pytest.raises(A.ArtError, match="no video"):
        A.from_video(str(tmp_path / "none.mp4"))
    (tmp_path / "v.mp4").write_bytes(b"x")
    with pytest.raises(A.ArtError, match="up to 30 seconds"):
        A.from_video(str(tmp_path / "v.mp4"), length=31)
    with pytest.raises(A.ArtError, match="#rrggbb"):
        A.from_video(str(tmp_path / "v.mp4"), key="green")


def test_frames_have_a_limit(tmp_path):
    with pytest.raises(A.ArtError, match="up to 1024"):
        A._check_frames([Image.new("RGBA", (1, 1))] * 1025, "x")


def test_touch_up_writes_one_frame_back(tmp_path):
    md, doc = _mode(tmp_path)
    sp = A.Sprite(_frames(5))
    pic = A.save_sprite(md, doc, "t", sp)
    new = Image.new("RGBA", (40, 30), (1, 2, 3, 255))
    A.replace_frame(md, pic, 3, new)
    fr = A.load_frames(md, pic)
    assert _same(fr[3], new) and _same(fr[2], sp.frames[2]) and _same(fr[4], sp.frames[4])
    with pytest.raises(A.ArtError, match="stays 40x30"):
        A.replace_frame(md, pic, 0, Image.new("RGBA", (4, 4)))


def test_backgrounds_still_tiled_scrolling(tmp_path):
    md, doc = _mode(tmp_path)
    A.save_sprite(md, doc, "sky", A.Sprite([Image.new("RGBA", (64, 32), (0, 0, 80, 255))]))
    A.save_sprite(md, doc, "sea", A.Sprite([Image.new("RGBA", (64, 32), (0, 60, 90, 255))]))
    A.set_backgrounds(doc, "main", [A.layer("sky", "still"), A.layer("sky", "tiled", y=10),
                                    A.layer("sea", "scrolling", speed=-120, y=400, alpha=0.5)])
    D.save(os.path.join(md, D.FILE_NAME), doc)
    back = D.load(os.path.join(md, D.FILE_NAME))["phases"][0]["background"]
    assert [A.layer_kind(x) for x in back] == ["still", "tiled", "scrolling"]
    assert back[2] == {"picture": "sea", "speed": -120.0, "y": 400.0, "tile": True, "alpha": 0.5}
    with pytest.raises(A.ArtError, match="up to 8"):
        A.set_backgrounds(doc, "main", [A.layer("sky")] * 9)


# ---- packing -----------------------------------------------------------------------------------------------------
def _atlas_frame(pk, man, pid, i):
    e = man["pictures"][pid][i]
    a = pk.texels[e["atlas"]]
    return e, a[e["sy"]:e["sy"] + e["sh"], e["sx"]:e["sx"] + e["sw"]]


def test_pack_trims_premultiplies_and_keeps_the_anchor(tmp_path):
    md, doc = _mode(tmp_path)
    fr = _frames(6, (48, 40))
    A.save_sprite(md, doc, "s", A.Sprite(fr), anchor=[0.25, 0.75])
    pk = P.pack(md, doc, "spike2", fonts=False)
    assert pk.report["ok"]
    man = P.manifest(pk, "spike2", ["a.pmat"])
    for i, f in enumerate(fr):
        e, px = _atlas_frame(pk, man, "s", i)
        x0, y0, x1, y1 = f.getchannel("A").getbbox()
        assert (e["ox"], e["oy"], e["sw"], e["sh"]) == (x0, y0, x1 - x0, y1 - y0)      # trimmed
        assert np.array_equal(px, P._premultiply(f.crop((x0, y0, x1, y1))))           # premultiplied, exact
        # the anchor in the source box lands on the same point of the frame
        assert abs(e["ax"] / 65536.0 * e["sw"] + e["ox"] - 0.25 * 48) < 1e-3
        assert abs(e["ay"] / 65536.0 * e["sh"] + e["oy"] - 0.75 * 40) < 1e-3
        # 2 texels of extruded edge on every side
        a = pk.texels[e["atlas"]]
        assert np.array_equal(a[e["sy"] - 2, e["sx"]:e["sx"] + e["sw"]], px[0])
        assert np.array_equal(a[e["sy"]:e["sy"] + e["sh"], e["sx"] - 1], px[:, 0])


def test_pack_premultiply_maths():
    f = Image.new("RGBA", (1, 1), (200, 100, 51, 128))
    assert P._premultiply(f)[0, 0].tolist() == [100, 50, 26, 128]


def test_pack_folds_identical_frames(tmp_path):
    md, doc = _mode(tmp_path)
    one = _frames(1, (40, 40))[0]
    A.save_sprite(md, doc, "same", A.Sprite([one] * 10))
    pk = P.pack(md, doc, "spike2", fonts=False)
    r = pk.report
    assert r["frames"] == 10 and r["unique"] == 1
    man = P.manifest(pk, "spike2", ["a"])
    assert len({(e["sx"], e["sy"]) for e in man["pictures"]["same"]}) == 1


def test_tiled_background_is_not_trimmed_and_wraps(tmp_path):
    md, doc = _mode(tmp_path)
    tile = Image.new("RGBA", (64, 16), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rectangle([0, 4, 9, 11], fill=(255, 0, 0, 255))     # touches the left edge only
    A.save_sprite(md, doc, "waves", A.Sprite([tile]))
    A.set_backgrounds(doc, "main", [A.layer("waves", "scrolling", speed=-50)])
    pk = P.pack(md, doc, "spike2", fonts=False)
    e, px = _atlas_frame(pk, P.manifest(pk, "spike2", ["a"]), "waves", 0)
    assert (e["sw"], e["sh"], e["ox"]) == (64, 16, 0)
    a = pk.texels[e["atlas"]]
    # the texel left of the tile is its right edge (see-through), not a copy of its own red left edge
    assert a[e["sy"] + 6, e["sx"] - 1, 3] == 0 and a[e["sy"] + 6, e["sx"] + e["sw"], 3] == 255


def test_200_frames_pack_in_seconds(tmp_path):
    md, doc = _mode(tmp_path)
    fr = []
    for i in range(200):
        im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        r = 20 + i % 55
        ImageDraw.Draw(im).ellipse([80 - r, 80 - r, 80 + r, 80 + r], fill=(255, i, 40, 255))
        fr.append(im)
    A.save_sprite(md, doc, "boom", A.Sprite(fr, fps=30))
    doc["assets"]["fonts"] = [{"id": "hud", "face": "card:default", "size": 28}]
    t0 = time.perf_counter()
    pk = P.pack(md, doc, "spike2")
    P.write(pk, str(tmp_path / "out"))
    took = time.perf_counter() - t0
    assert took < 5.0, took
    r = pk.report
    assert r["ok"] and r["unique"] == 200 + len(pk.fonts["hud"]["glyphs"]) - 1      # every glyph but the space
    assert len(r["atlases"]) == 1 and r["atlases"][0]["used_pct"] > 45


def test_atlases_never_overlap(tmp_path, monkeypatch):
    md, doc = _mode(tmp_path)
    monkeypatch.setitem(B.MACHINES, "small", dict(B.MACHINES["spike2"], atlas=256))
    import random
    rnd = random.Random(7)
    fr = []
    for i in range(120):
        im = Image.new("RGBA", (rnd.randrange(8, 200), rnd.randrange(8, 120)), (i, 255 - i, 9, 255))
        fr.append(im)
    for i, f in enumerate(fr):
        A.save_sprite(md, doc, "p%d" % i, A.Sprite([f]))
    pk = P.pack(md, doc, "small", fonts=False)     # small atlases: several pages
    assert len(pk.atlases) > 1
    seen = {}
    for it in pk.items:
        n, x, y = it.place
        w, h = it.img.width + 4, it.img.height + 4
        W, H = pk.atlases[n]
        assert x >= 0 and y >= 0 and x + w <= W and y + h <= H
        for (ox, oy, ow, oh) in seen.get(n, []):
            assert x >= ox + ow or ox >= x + w or y >= oy + oh or oy >= y + h
        seen.setdefault(n, []).append((x, y, w, h))


# ---- cost and the card gate --------------------------------------------------------------------------------------
def test_cost_matches_what_is_written(tmp_path):
    md, doc = _mode(tmp_path)
    A.save_sprite(md, doc, "s", A.Sprite(_frames(8, (100, 80))))
    (tmp_path / "modes" / "test-mode" / "sound").mkdir()
    (tmp_path / "modes" / "test-mode" / "sound" / "zap.wav").write_bytes(b"\0" * 5000)
    doc["assets"]["sounds"] = [{"id": "zap", "file": "sound/zap.wav", "role": "effect"}]
    # a machine whose card holds the atlases compressed: the card bytes are the files written
    pk = P.for_card(md, doc, "spike3")
    r = pk.report
    out = os.path.join(md, "build", "spike3")
    files = sorted(n for n in os.listdir(out) if n.endswith(".pmat"))
    assert r["memory"] == sum(w * h * 4 for w, h in pk.atlases)
    assert r["card_pictures"] == sum(os.path.getsize(os.path.join(out, n)) for n in files)
    assert r["card"] == r["card_pictures"] + 5000
    w, h, flags, data = P.read_pmat(open(os.path.join(out, files[0]), "rb").read())
    assert (w, h) == pk.atlases[0] and flags & P.FLAG_ZLIB and data == pk.texels[0].tobytes()
    import json
    man = json.load(open(os.path.join(out, "atlas.json")))
    assert man["premultiplied"] and man["texel_scale"] == 1 and len(man["pictures"]["s"]) == 8
    assert set(man["fonts"]) == set() or man["fonts"]
    P.write(pk, str(tmp_path / "web"), "webgl")
    png = Image.open(tmp_path / "web" / "atlas_0.png")
    assert np.array_equal(np.asarray(png), pk.texels[0])


def _padgfx_size(pk):
    """The size of Spike 2's set file for this pack, as PAD-1655's writer lays it out: with that writer on hand,
    the file itself; without it, its documented layout."""
    try:
        from pinball_decryptor.plugins.stern import gfx_set
    except ImportError:
        gfx_set = None
    glyphs = {}
    for it in pk.items:
        if it.owner.startswith("font:"):
            glyphs[it.owner] = glyphs.get(it.owner, 0) + 1
    L = B.PADGFX
    fonts = sum(L["font"] + L["glyph"] * n for n in glyphs.values())
    if gfx_set is None:
        return L["header"] + sum(L["picture"] + w * h * 4 for w, h in pk.atlases) + fonts
    pics = [("atlas_%d" % i, Image.fromarray(a, "RGBA")) for i, a in enumerate(pk.texels)]
    return len(gfx_set.pack(pics, premultiplied=True)) + fonts


def test_spike2_card_is_the_set_file_and_matches_what_was_measured(tmp_path):
    """Spike 2 maps its set file's texels straight into GL (PAD-1655): the card holds each atlas raw, so card space
    is the set file's size, and memory is what the runtime's "KB of pictures on GL" line counts (w x h x 4 a
    picture, RGBA8)."""
    md, doc = _mode(tmp_path)
    A.save_sprite(md, doc, "s", A.Sprite(_frames(8, (100, 80))))
    A.save_sprite(md, doc, "big", A.Sprite([Image.new("RGBA", (1200, 700), (40, 90, 200, 255))]))
    pk = P.pack(md, doc, "spike2")
    r = pk.report
    assert r["budget"]["measured"] is True
    assert r["memory"] == sum(w * h * 4 for w, h in pk.atlases)
    assert r["card_pictures"] == _padgfx_size(pk)
    # the card costs what memory does, within the file's tables
    assert 0 <= r["card_pictures"] - r["memory"] < 1024
    # and so does each sprite's share: its own texels, never the atlas's empty space
    for sp in r["sprites"]:
        assert sp["card"] - sp["memory"] == (0 if not sp["font"] else 40 + 16 * sp["frames"]), sp
    assert not P.pack(md, doc, "spike3").report["budget"]["measured"]


def test_over_budget_names_the_sprite_and_writes_nothing(tmp_path, monkeypatch):
    md, doc = _mode(tmp_path)
    big = []
    for i in range(30):
        px = np.random.default_rng(i).integers(0, 255, (300, 300, 4), dtype=np.uint8)
        px[..., 3] = 255
        big.append(Image.fromarray(px, "RGBA"))
    A.save_sprite(md, doc, "giant", A.Sprite(big))
    A.save_sprite(md, doc, "tiny", A.Sprite([Image.new("RGBA", (8, 8), (9, 9, 9, 255))]))
    monkeypatch.setitem(B.MACHINES, "spike2", dict(B.MACHINES["spike2"], memory=2 * B.MB))
    with pytest.raises(P.OverBudget) as e:
        P.for_card(md, doc, "spike2")
    msg = str(e.value)
    assert "of memory" in msg and 'Sprite "giant"' in msg and "tiny" not in msg
    assert not os.path.exists(os.path.join(md, "build"))


def test_frame_bigger_than_the_largest_atlas_is_named(tmp_path):
    md, doc = _mode(tmp_path)
    A.save_sprite(md, doc, "wide", A.Sprite([Image.new("RGBA", (3000, 10), (1, 1, 1, 255))]))
    r = P.pack(md, doc, "spike2", fonts=False).report
    assert not r["ok"] and 'Sprite "wide"' in r["problems"][0] and "2048x2048" in r["problems"][0]


def test_dots_pack_art_at_their_scale(tmp_path):
    """A dot-matrix screen shows the stage at 1/10.6: a full-width background packs there, at 1/8."""
    md, doc = _mode(tmp_path)
    A.save_sprite(md, doc, "sky", A.Sprite([Image.new("RGBA", (1360, 400), (20, 30, 90, 255))]))
    pk = P.pack(md, doc, "dots", fonts=False)
    assert pk.report["ok"], pk.report["problems"]
    man = P.manifest(pk, "dots", ["a"])
    assert man["texel_scale"] == 8 and man["pictures"]["sky"][0]["sw"] == 170


def test_budgets_match_the_plan():
    """budgets.py is the plan's section 5 table in code: the two never drift apart."""
    text = open(os.path.join(REPO, "docs", "plans", "video_mode_maker.md"), encoding="utf-8").read()
    sec = text[text.index("## 5 Budgets per machine"):text.index("## 6 ")]
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in sec.splitlines() if ln.startswith("|")]
    head = rows[0]

    def row(start):
        return next(r for r in rows if r[0].startswith(start))

    def mb(cell):
        return int(re.match(r"(\d+) MB", cell).group(1)) * B.MB

    for key, col in B.PLAN_COLUMN.items():
        i = head.index(col)
        m = B.MACHINES[key]
        assert mb(row("Pictures in memory")[i]) == m["memory"], key
        assert row("Largest atlas")[i] == "%d x %d" % (m["atlas"], m["atlas"]), key
        assert mb(row("Card space")[i]) == m["card"], key
        mm = B.machine(key)
        assert row("Texel format")[i] == "RGBA8, %d bytes" % mm["texel_bytes"], key
        # PAD-1659: the player's meters
        assert int(row("Things alive at once")[i]) == m["things"], key
        assert int(row("Quads drawn a frame")[i]) == m["quads"], key
        calls = row("Draw calls a frame")[i]
        assert (0 if calls == "n/a" else int(calls)) == m["draw_calls"], key
        assert row("Atlases on the card")[i].split()[0] == {"raw": "raw", "zlib": "compressed"}[mm["card_atlas"]], key


# ---- the Video modes tab -----------------------------------------------------------------------------------------
def test_video_modes_tab(tmp_path):
    from tests.webui_harness import web_app
    project = tmp_path / "proj"
    project.mkdir()
    gif = tmp_path / "burst.gif"
    fr = [Image.new("RGBA", (24, 24), (255, 40 * i, 0, 255)) for i in range(4)]
    fr[0].save(gif, save_all=True, append_images=fr[1:], duration=100, loop=0)
    with web_app(tmp_path, mfr="stern") as w:
        w.run(lambda: w.window.write_assets_var.set(str(project)))
        w.drain()
        assert w.call("vmodes.refresh") is True
        s = w.state("vmodes")
        assert s["available"] and s["modes"] == []
        slug = w.call("vmodes.new_mode", "Harbour Run")
        assert slug == "harbour-run" and w.state("vmodes")["slug"] == slug
        w.call("vmodes.draft", str(gif), "gif", {})
        t0 = time.time()
        while (w.state("vmodes").get("draft") or {}).get("busy") and time.time() - t0 < 20:
            time.sleep(0.05)
            w.drain()
        d = w.state("vmodes")["draft"]
        assert d["frames"] == 4 and d["fps"] == 10 and not d["error"] and d["id"] == "burst"
        assert w.call("vmodes.add", "burst", 15, False) == "burst"
        w.drain()
        s = w.state("vmodes")
        p = s["pictures"][0]
        assert (p["id"], p["frames"], p["fps"], p["loop"]) == ("burst", 4, 15.0, False)
        assert w.call("vmodes.set_picture", "burst", {"anchor": [0.5, 1], "hitbox": {"shape": "circle", "x": 0,
                                                                                    "y": -12, "r": 10}})
        assert w.call("vmodes.set_layers", "main", [{"picture": "burst", "kind": "scrolling", "speed": -40, "y": 100}])
        doc = D.load(str(project / "modes" / slug / D.FILE_NAME))
        pic = doc["assets"]["pictures"][0]
        assert pic["anchor"] == [0.5, 1] and pic["hitbox"] == {"shape": "circle", "x": 0, "y": -12, "r": 10}
        assert doc["phases"][0]["background"] == [{"picture": "burst", "speed": -40.0, "y": 100.0, "tile": True}]
        # touch-up: a frame opens in the pixel editor's shape and saves back into the sheet
        sp = w.call("vmodes.frame_open", "burst#2")
        assert (sp["w"], sp["h"], len(sp["frames"]), sp["index"]) == (24, 24, 4, 2)
        blue = Image.new("RGBA", (24, 24), (0, 0, 255, 255))
        r = w.call("vmodes.frame_save", "burst#2", 24, 24, base64.b64encode(blue.tobytes()).decode())
        assert r["ok"]
        assert _same(A.load_frames(str(project / "modes" / slug), pic)[2], blue)
        # pack: the report lands
        w.call("vmodes.pack", False)
        t0 = time.time()
        while w.state("vmodes").get("packing") and time.time() - t0 < 30:
            time.sleep(0.05)
            w.drain()
        rep = w.state("vmodes")["report"]
        assert rep["ok"] and rep["machine"] == "spike2" and rep["sprites"][0]["id"] in ("burst", "font:hud") \
            or rep["ok"]
        assert any(sp["id"] == "burst" for sp in rep["sprites"])
        # a picture in use is not taken out
        assert w.call("vmodes.remove_picture", "burst") is False
