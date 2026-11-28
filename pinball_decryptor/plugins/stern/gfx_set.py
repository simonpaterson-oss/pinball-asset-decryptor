"""A mode's picture set for moving pictures on the glass (PAD-1655): one ``.padgfx`` file.

A mode draws its own pictures over the game's display with ``pm_gfx_*`` (pad_mode.h, "moving pictures"): the
runtime loads a set, sends its pictures to the GPU over a few frames and draws quads of them every frame. This
module writes and reads that file. Every picture is straight-alpha RGBA, rows top first, at most ``MAX_SIDE`` a
side (atlases of frames are the way to many small ones: a quad takes a part of a picture). Pictures are drawn premultiplied (the backend contract, video_mode_maker.md section 4); a set
may store them straight (this writer's default) or premultiplied (``premultiplied=True``), and says which. A FONT is
one picture,
its atlas, plus a glyph table; :func:`card_font` makes one from the card's own font as an extract holds it
(fontrender's glyph slices and metrics, laid out by the same rule the Scenes preview uses), :func:`ttf_font` from a
desktop font for a title that has none to offer.

The file, little-endian::

    0   "PADGFX1\\0"
    8   u32 pictures, u32 fonts, u32 glyphs (all fonts'), u32 0
    24  pictures x 40: name[24] (NUL-padded), u16 w, u16 h, u32 offset of its pixels, u32 flags (bit 0: its
                       colours are premultiplied by its alpha), u32 0
        fonts x 40:    name[24], u16 picture (index in this file), u16 size (px), u16 line height, i16 ascent,
                       u32 first glyph, u32 glyphs
        glyphs x 16:   u16 code point, u16 x, y, w, h (in the font's picture), i16 x offset from the pen,
                       i16 y offset from the baseline to the glyph's top, i16 advance - the last three in 1/8 px,
                       sorted by code point within each font
        pixels, each picture's w*h*4 bytes at its offset (4-aligned)

The runtime (pad_mode_runtime.c, "moving pictures") refuses a file that does not hold together, so this writer and
:func:`read` are the format's two ends; tests/test_pad1655_gfx_set.py keeps them in step.
"""

import math
import os
import struct

MAGIC = b"PADGFX1\0"
MAX_SIDE = 2048            # every Spike 2 GPU takes this (the runtime reads the real limit and logs a larger picture)
MAX_PICTURES = 256
MAX_FONTS = 32
MAX_GLYPHS = 8192
STAGE = (1360, 768)        # the stage pm_gfx_* coordinates are on unless the mode says otherwise
DEFAULT_CHARS = "".join(chr(c) for c in range(32, 127))


def _pil():
    from PIL import Image
    return Image


def _name(n):
    b = str(n).encode("utf-8")[:23]
    return b + b"\0" * (24 - len(b))


def pack(pictures, fonts=(), premultiplied=False):
    """The file's bytes. *pictures*: ``[(name, PIL image)]``; *fonts*: font specs from :func:`card_font` /
    :func:`ttf_font` (each adds its atlas as a picture named after the font). *premultiplied*: store every picture's
    colours multiplied by its alpha (and say so in its flags)."""
    pics = [(str(n), im.convert("RGBA")) for n, im in pictures]
    fonts = list(fonts)
    if len(pics) + len(fonts) > MAX_PICTURES:
        raise ValueError("a set holds at most %d pictures (fonts' atlases count)" % MAX_PICTURES)
    if len(fonts) > MAX_FONTS:
        raise ValueError("a set holds at most %d fonts" % MAX_FONTS)
    font_rows, glyph_rows = [], []
    for f in fonts:
        pic = len(pics)
        pics.append((f["name"], f["image"].convert("RGBA")))
        gl = sorted(f["glyphs"], key=lambda g: g[0])
        font_rows.append((f["name"], pic, f["size"], f["line_h"], f["ascent"], len(glyph_rows), len(gl)))
        glyph_rows += gl
    if len(glyph_rows) > MAX_GLYPHS:
        raise ValueError("a set's fonts hold at most %d glyphs" % MAX_GLYPHS)
    for n, im in pics:
        if max(im.size) > MAX_SIDE or min(im.size) < 1:
            raise ValueError("picture %s is %dx%d - 1 to %d a side" % (n, im.size[0], im.size[1], MAX_SIDE))
    head = 24 + 40 * (len(pics) + len(font_rows)) + 16 * len(glyph_rows)
    out = bytearray(MAGIC + struct.pack("<4I", len(pics), len(font_rows), len(glyph_rows), 0))
    off = head
    for n, im in pics:
        out += _name(n) + struct.pack("<HHIII", im.size[0], im.size[1], off, 1 if premultiplied else 0, 0)
        off += im.size[0] * im.size[1] * 4
    for n, pic, size, line_h, asc, first, count in font_rows:
        out += _name(n) + struct.pack("<HHHhII", pic, int(round(size)), int(round(line_h)), int(round(asc)), first,
                                      count)
    for cp, x, y, w, h, ox, oy, adv in glyph_rows:
        out += struct.pack("<HHHHHhhh", cp, x, y, w, h, _eighths(ox), _eighths(oy), _eighths(adv))
    assert len(out) == head
    for _n, im in pics:
        out += _premultiply(im.tobytes()) if premultiplied else im.tobytes()
    return bytes(out)


def _premultiply(rgba):
    out = bytearray(rgba)
    for i in range(0, len(out), 4):
        a = out[i + 3]
        if a != 255:
            out[i] = (out[i] * a + 127) // 255
            out[i + 1] = (out[i + 1] * a + 127) // 255
            out[i + 2] = (out[i + 2] * a + 127) // 255
    return bytes(out)


def _eighths(v):
    return max(-32768, min(32767, int(round(v * 8))))


def write(path, pictures, fonts=(), premultiplied=False):
    data = pack(pictures, fonts, premultiplied)
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def read(data):
    """``{"pictures": [{name, w, h, premultiplied, rgba}], "fonts": [{name, picture, size, line_h, ascent, glyphs: {cp: (x, y, w, h,
    ox, oy, adv)}}]}`` - offsets and advance back in px. Raises ValueError on a file the runtime would refuse."""
    if len(data) < 24 or data[:8] != MAGIC:
        raise ValueError("not a picture set (PADGFX1)")
    n_p, n_f, n_g, _z = struct.unpack_from("<4I", data, 8)
    if n_p > MAX_PICTURES or n_f > MAX_FONTS or n_g > MAX_GLYPHS or 24 + 40 * (n_p + n_f) + 16 * n_g > len(data):
        raise ValueError("its tables are too big for it")
    pics, fonts = [], []
    for i in range(n_p):
        e = 24 + 40 * i
        name = data[e:e + 24].split(b"\0")[0].decode("utf-8", "replace")
        w, h, off, flags = struct.unpack_from("<HHII", data, e + 24)
        if not w or not h or off % 4 or off + w * h * 4 > len(data):
            raise ValueError("picture %s: its size or place is wrong" % name)
        pics.append({"name": name, "w": w, "h": h, "premultiplied": bool(flags & 1),
                     "rgba": data[off:off + w * h * 4]})
    g0 = 24 + 40 * (n_p + n_f)
    for i in range(n_f):
        e = 24 + 40 * (n_p + i)
        name = data[e:e + 24].split(b"\0")[0].decode("utf-8", "replace")
        pic, size, line_h, asc, first, count = struct.unpack_from("<HHHhII", data, e + 24)
        if pic >= n_p or first + count > n_g:
            raise ValueError("font %s: its table is wrong" % name)
        glyphs = {}
        for k in range(first, first + count):
            cp, x, y, w, h, ox, oy, adv = struct.unpack_from("<HHHHHhhh", data, g0 + 16 * k)
            glyphs[cp] = (x, y, w, h, ox / 8, oy / 8, adv / 8)
        fonts.append({"name": name, "picture": pic, "size": size, "line_h": line_h, "ascent": asc, "glyphs": glyphs})
    return {"pictures": pics, "fonts": fonts}


# ---- fonts -----------------------------------------------------------------------------------------------------
def _atlas(cells, pad=1, width=512):
    """Shelf-pack ``[(key, image)]``; ``(atlas, {key: (x, y)})``. Grows the width up to MAX_SIDE when it must."""
    Image = _pil()
    cells = [(k, im) for k, im in cells if im is not None and im.size[0] and im.size[1]]
    order = sorted(cells, key=lambda c: -c[1].size[1])
    while True:
        x = y = shelf = 0
        at = {}
        for k, im in order:
            w, h = im.size
            if x + w + pad > width:
                x, y, shelf = 0, y + shelf + pad, 0
            at[k] = (x + pad, y + pad)
            x += w + pad
            shelf = max(shelf, h)
        height = y + shelf + 2 * pad
        if height <= MAX_SIDE or width >= MAX_SIDE:
            break
        width *= 2
    if height > MAX_SIDE:
        raise ValueError("the font's glyphs do not fit one %d px atlas" % MAX_SIDE)
    atlas = Image.new("RGBA", (width, max(1, height)), (0, 0, 0, 0))
    for k, im in cells:
        atlas.paste(im, at[k])
    return atlas, at


def card_font(assets_dir, name=None, chars=None, size_id=0):
    """A font spec from the card's own font in an extract (fontrender's glyph slices + metrics). *name*: the font's
    name or table key (None: the extract's largest named font); *chars*: the characters to carry (None: all it has).
    Each glyph is baked exactly as fontrender.render_text draws it at size 1.0 (cell scale or metric fit, bearings),
    so the words a mode draws are the game's letters; kerning is not carried."""
    from . import fontrender as FR
    fonts = FR.load_fonts(assets_dir)
    if not fonts:
        raise ValueError("%s holds no fonts (images/scene_textures/glyph_images.txt)" % assets_dir)
    if name:
        pick = [f for f in fonts if f["name"] == name or f["key"] == name]
        if not pick:
            raise ValueError("no font %r in %s" % (name, assets_dir))
        font = pick[0]
    else:
        font = max((f for f in fonts if f["name"]), key=lambda f: (f["px"], len(f["glyphs"])), default=fonts[0])
    font = FR.font_at_size(font, size_id)
    want = set(ord(c) for c in chars) if chars else None
    asc, desc = font["ascent"], font["descent"]
    cells, rows = [], {}
    for cp, g in sorted(font["glyphs"].items()):
        if cp > 0xffff or (want is not None and cp not in want):
            continue
        if g["lh"] <= 1:
            rows[cp] = (0, 0, g["adv"])
            continue
        try:
            img = FR.load_slice(g)
        except (OSError, FR.FontError):
            continue
        pad, cscale = font.get("cell_pad", 0.0), font.get("cell_scale")
        if cscale:
            cw, ch = img.size
            tw, th = max(1, int(round(cw * cscale))), max(1, int(round(ch * cscale)))
            if (tw, th) != img.size:
                img = img.resize((tw, th), _pil().LANCZOS)
            ox, oy = g["bx"] - pad * cscale, -g["by"] - pad * cscale
        else:
            img = FR._fit_to_metrics(img, g, 1.0)
            ox, oy = g["bx"], -g["by"]
        cells.append((cp, img))
        rows[cp] = (ox, oy, g["adv"])
    if 32 not in rows and (want is None or 32 in want):
        rows[32] = (0, 0, FR._space_advance(font))
    atlas, at = _atlas(cells)
    sizes = dict((cp, im.size) for cp, im in cells)
    glyphs = []
    for cp, (ox, oy, adv) in rows.items():
        x, y = at.get(cp, (0, 0))
        w, h = sizes.get(cp, (0, 0))
        glyphs.append((cp, x, y, w, h, ox, oy, adv))
    return {"name": (font["name"] or font["key"])[:23], "image": atlas, "size": asc + desc,
            "line_h": asc + desc + FR.LINE_GAP, "ascent": asc, "glyphs": glyphs}


def ttf_font(path, size, chars=DEFAULT_CHARS, name=None):
    """A font spec from a TTF/OTF at *size* px (white letters, straight alpha)."""
    from PIL import ImageFont, ImageDraw
    Image = _pil()
    f = ImageFont.truetype(path, size)
    asc, desc = f.getmetrics()
    cells, rows = [], {}
    for ch in chars:
        cp = ord(ch)
        adv = f.getlength(ch)
        box = f.getbbox(ch)
        if ch.isspace() or box[2] <= box[0] or box[3] <= box[1]:
            rows[cp] = (0, 0, adv)
            continue
        w, h = box[2] - box[0] + 2, box[3] - box[1] + 2
        im = Image.new("RGBA", (w, h), (255, 255, 255, 0))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).text((1 - box[0], 1 - box[1]), ch, font=f, fill=255)
        im.putalpha(mask)
        cells.append((cp, im))
        rows[cp] = (box[0] - 1, box[1] - 1 - asc, adv)
    atlas, at = _atlas(cells)
    sizes = dict((cp, im.size) for cp, im in cells)
    glyphs = [(cp, at.get(cp, (0, 0))[0], at.get(cp, (0, 0))[1], sizes.get(cp, (0, 0))[0], sizes.get(cp, (0, 0))[1],
               ox, oy, adv) for cp, (ox, oy, adv) in rows.items()]
    return {"name": (name or os.path.splitext(os.path.basename(path))[0])[:23], "image": atlas, "size": asc + desc,
            "line_h": asc + desc + 2, "ascent": asc, "glyphs": glyphs}


# ---- PAD's own placeholder art (no game content: original shapes drawn here) ------------------------------------
def placeholder_pictures():
    """``[(name, image)]``: orb, star, ring, ship (white, so a tint colours them), sheet (eight numbered 64x64
    frames in a 256x128 sprite sheet) and sky (a full-stage backdrop)."""
    from PIL import ImageDraw
    Image = _pil()

    def canvas(w, h):
        return Image.new("RGBA", (w, h), (255, 255, 255, 0))

    orb = canvas(64, 64)
    px = orb.load()
    for y in range(64):
        for x in range(64):
            d = math.hypot(x - 31.5, y - 31.5) / 31.5
            if d < 1:
                px[x, y] = (255, 255, 255, int(255 * min(1.0, (1 - d) * 3)))
    star = canvas(64, 64)
    pts = []
    for i in range(10):
        r = 31 if i % 2 == 0 else 13
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((32 + r * math.cos(a), 32 + r * math.sin(a)))
    ImageDraw.Draw(star).polygon(pts, fill=(255, 255, 255, 255))
    ring = canvas(96, 96)
    ImageDraw.Draw(ring).ellipse((4, 4, 91, 91), outline=(255, 255, 255, 255), width=10)
    ship = canvas(80, 48)
    ImageDraw.Draw(ship).polygon([(78, 24), (6, 2), (22, 24), (6, 46)], fill=(255, 255, 255, 255))
    ImageDraw.Draw(ship).polygon([(30, 18), (52, 24), (30, 30)], fill=(90, 200, 255, 255))
    sheet = canvas(256, 128)
    d = ImageDraw.Draw(sheet)
    for f in range(8):
        x0, y0 = f % 4 * 64, f // 4 * 64
        d.rounded_rectangle((x0 + 4, y0 + 4, x0 + 59, y0 + 59), radius=12, fill=(255, 255, 255, 200))
        a = f * math.pi / 4
        d.line((x0 + 32, y0 + 32, x0 + 32 + 22 * math.cos(a), y0 + 32 + 22 * math.sin(a)), fill=(30, 30, 60, 255),
               width=6)
    sky = Image.new("RGBA", STAGE, (0, 0, 0, 255))
    sp = sky.load()
    for y in range(STAGE[1]):
        t = y / (STAGE[1] - 1)
        row = (int(20 + 40 * t), int(16 + 30 * t), int(60 + 90 * (1 - t)), 255)
        for x in range(STAGE[0]):
            sp[x, y] = row
    return [("orb", orb), ("star", star), ("ring", ring), ("ship", ship), ("sheet", sheet), ("sky", sky)]


#: Where each shape sits in :func:`placeholder_atlas`'s "shapes" picture: (x, y, w, h). gfx_test_mode.c draws from
#: these boxes (tests/test_pad1655_gfx.py keeps the two in step); frame0..frame7 are the sprite sheet's frames.
PLACEHOLDER_BOXES = {
    "orb": (2, 2, 64, 64), "star": (70, 2, 64, 64), "ring": (138, 2, 96, 96), "ship": (2, 70, 80, 48),
    **{"frame%d" % f: (2 + f % 4 * 64, 130 + f // 4 * 64, 60, 60) for f in range(8)},
}


def placeholder_atlas():
    """``("shapes", image)``: the placeholder shapes and the sheet's eight frames packed in one 256x256 picture
    (2 px apart, so bilinear sampling never bleeds), as an engine's packed art is: one texture, so a list of many
    of them is a few draw calls, not one a quad."""
    Image = _pil()
    pics = dict(placeholder_pictures())
    atlas = Image.new("RGBA", (256, 256), (255, 255, 255, 0))
    for name in ("orb", "star", "ring", "ship"):
        x, y, _w, _h = PLACEHOLDER_BOXES[name]
        atlas.paste(pics[name], (x, y))
    for f in range(8):
        x, y, w, h = PLACEHOLDER_BOXES["frame%d" % f]
        cell = pics["sheet"].crop((f % 4 * 64 + 2, f // 4 * 64 + 2, f % 4 * 64 + 2 + w, f // 4 * 64 + 2 + h))
        atlas.paste(cell, (x, y))
    return "shapes", atlas


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Write a mode's picture set (.padgfx)")
    ap.add_argument("out")
    ap.add_argument("--png", nargs="*", default=[], help="PNG files; each picture is named after its file")
    ap.add_argument("--placeholder", action="store_true",
                    help="PAD's own placeholder shapes (each alone, and packed in the 'shapes' atlas)")
    ap.add_argument("--card-font", metavar="EXTRACT", help="an extract folder: the card's own font")
    ap.add_argument("--font-name", help="which of the extract's fonts (its name or table key)")
    ap.add_argument("--ttf", nargs=2, metavar=("FILE", "PX"), help="a desktop font instead")
    a = ap.parse_args(argv)
    Image = _pil()
    pics = placeholder_pictures() + [placeholder_atlas()] if a.placeholder else []
    pics += [(os.path.splitext(os.path.basename(p))[0], Image.open(p)) for p in a.png]
    fonts = []
    if a.card_font:
        fonts.append(card_font(a.card_font, a.font_name))
    if a.ttf:
        fonts.append(ttf_font(a.ttf[0], int(a.ttf[1])))
    n = write(a.out, pics, fonts)
    print("%s: %d picture(s), %d font(s), %d KB" % (a.out, len(pics) + len(fonts), len(fonts), n // 1024))


if __name__ == "__main__":
    main()
