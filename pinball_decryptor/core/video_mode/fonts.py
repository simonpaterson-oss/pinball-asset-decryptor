"""A video mode's fonts, baked once for the app and the machine alike (PAD-1666).

A document font is ``{"id", "face", "size", "outline"?, "file"?}``: ``face`` is ``card:<name>``, the game's own
font (its glyph table in the extracted project, ``images/scene_textures/glyph_images.txt``, read by the Stern
plugin's fontrender), or a font file in the mode folder named in ``file``. ``card:default`` is the card's largest
named font. With neither there, a stand-in face of the same size is baked and the font says ``stand_in``.

Each glyph is baked three ways, all white so the engine tints them: its **fill**, its **outline** (the fill's
alpha grown by a disc of ``outline`` px) and its **ramp** (the fill's alpha times how far down the line it is, 0
at the line's top to 1 at its foot, so a two-colour gradient runs evenly across a whole word). The engine draws a
styled word from those three (vm_engine.c text_fx), so outline, shadow and gradient are glyph variants, not
backend features (plan section 4).

    baked = bake(mode_dir, doc)                      # {font id: Baked}
    sheets(mode_dir, doc, out_dir)                   # the app: one PNG a font, and the compiler's metrics for it
    items(baked)                                     # the machine: every glyph as a packer item (pack.py)
    compiled_from_atlas(baked, placed, atlas_of)     # the compiler's metrics from where the packer put them
"""
import hashlib
import json
import os

ONE = 65536
GLYPHS = "".join(chr(c) for c in range(32, 127))
FONT_ATLAS_BASE = 1000
VARIANT_OUTLINE = 1000          # a packer item's index: the code point, + 1000 outline, + 2000 ramp
VARIANT_RAMP = 2000
STAND_IN_FACE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "webui", "static",
                             "fonts", "ibm-plex-sans-condensed-latin-600-normal.woff2")


class Baked:
    """One font, baked: ``glyphs`` {code: {"adv", "x", "y", "fill", "outline", "ramp"}} (PIL images or None;
    x, y where the fill's box sits from the pen at the line's top), ``line`` (px), ``ow`` (outline px), ``size``,
    ``stand_in``, ``source`` (what it was baked from)."""

    def __init__(self, fid, size, line, ow, glyphs, stand_in, source):
        self.id, self.size, self.line, self.ow = fid, size, line, ow
        self.glyphs, self.stand_in, self.source = glyphs, stand_in, source


def outline_px(font):
    o = font.get("outline")
    if isinstance(o, (int, float)):
        return max(0, min(12, int(round(o))))
    return max(2, int(round(float(font.get("size") or 24) / 12.0)))


# ---- where a face comes from -------------------------------------------------------------------------------------
def project_of(mode_dir):
    """The project a mode folder sits in (<project>/modes/<slug>)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(mode_dir))) if mode_dir else ""


def card_fonts(project):
    """The game's own fonts in an extracted project (fontrender's font dicts), [] when there are none."""
    if not project:
        return []
    try:
        from ...plugins.stern import fontrender
    except Exception:          # noqa: BLE001 - another maker's app has no Stern plugin: no card fonts
        return []
    try:
        return [f for f in fontrender.load_fonts(project) if f.get("glyphs")]
    except (OSError, ValueError):
        return []


def _px(f):
    try:
        return float(f.get("px") or 0) or float(f.get("ascent", 0) + f.get("descent", 0)) or 32.0
    except (TypeError, ValueError):
        return 32.0


def find_card_font(fonts, name):
    """``name`` by the game's font name or table key; ``default``: the largest named font that has the letters."""
    if name and name != "default":
        for f in fonts:
            if f.get("name") == name or f.get("key") == name:
                return f
        return None
    good = [f for f in fonts if f.get("name") and all(ord(c) in f["glyphs"] for c in "AEOS05")]
    good = good or [f for f in fonts if f.get("name")] or list(fonts)
    return max(good, key=lambda f: (_px(f), len(f["glyphs"]))) if good else None


def resolver(mode_dir):
    """face -> a font file path, a card font dict, or None (bake a stand-in)."""
    cache = {}

    def resolve(face):
        face = str(face or "")
        if not face.startswith("card:"):
            return None
        if "fonts" not in cache:
            cache["fonts"] = card_fonts(project_of(mode_dir))
        return find_card_font(cache["fonts"], face[5:])
    return resolve


# ---- baking ------------------------------------------------------------------------------------------------------
def _white(alpha):
    from PIL import Image
    img = Image.new("RGBA", alpha.size, (255, 255, 255, 0))
    img.putalpha(alpha)
    return img


def _dilate(alpha, r):
    """``alpha`` grown by a disc of radius r (the outline): the brightest of every shift inside the disc."""
    from PIL import Image, ImageChops
    w, h = alpha.size
    out = Image.new("L", (w + 2 * r, h + 2 * r), 0)
    big = Image.new("L", out.size, 0)
    big.paste(alpha, (r, r))
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r + r:
                out = ImageChops.lighter(out, ImageChops.offset(big, dx, dy))
    return out


def _variants(alpha, top, line, ow):
    """fill, outline and ramp of one glyph whose box starts ``top`` px below the line's top."""
    from PIL import Image
    fill = _white(alpha)
    outline = _white(_dilate(alpha, ow)) if ow > 0 else None
    w, h = alpha.size
    grad = Image.new("L", (1, h))
    for y in range(h):
        grad.putpixel((0, y), max(0, min(255, int(round(255.0 * (top + y + 0.5) / max(1.0, line))))))
    from PIL import ImageChops
    ramp = _white(ImageChops.multiply(alpha, grad.resize((w, h))))
    return fill, outline, ramp


def _bake_ttf(path_or_none, size, ow):
    from PIL import Image, ImageDraw, ImageFont
    stand_in = path_or_none is None
    font = None
    if path_or_none:
        try:
            font = ImageFont.truetype(path_or_none, size)
        except OSError:
            font, stand_in = None, True
    if font is None:
        try:      # the stand-in: the app's own condensed face, bold enough for a HUD (Pillow reads its WOFF2)
            font = ImageFont.truetype(STAND_IN_FACE, size)
        except OSError:
            font = ImageFont.load_default(size)
    ascent, descent = font.getmetrics()
    line = ascent + descent
    glyphs = {}
    for ch in GLYPHS:
        l, t, r, b = font.getbbox(ch)
        adv = float(font.getlength(ch))
        g = {"adv": adv, "x": float(l), "y": float(t), "fill": None, "outline": None, "ramp": None}
        if r > l and b > t and ch != " ":
            img = Image.new("L", (r - l, b - t), 0)
            ImageDraw.Draw(img).text((-l, -t), ch, font=font, fill=255)
            if img.getbbox():
                g["fill"], g["outline"], g["ramp"] = _variants(img, t, line, ow)
        glyphs[ord(ch)] = g
    return glyphs, line, stand_in


def _bake_card(cf, size, ow):
    """A card font at ``size`` px a line: each glyph's bitmap placed by the game's own bearings and advance."""
    from ...plugins.stern import fontrender as FR
    from PIL import Image
    asc, desc = float(cf.get("ascent") or 0), float(cf.get("descent") or 0)
    if asc + desc <= 0:
        asc, desc = _px(cf) * 0.8, _px(cf) * 0.2
    ms = float(size) / (asc + desc)
    line = int(round((asc + desc) * ms))
    sp = FR._space_advance(cf) * ms
    glyphs = {}
    for ch in GLYPHS:
        gd = cf["glyphs"].get(ord(ch))
        if gd is None:
            if ch.isalpha() and ord(ch.upper()) in cf["glyphs"]:      # a capitals-only face: the capital
                gd = cf["glyphs"][ord(ch.upper())]
            elif ch.isalpha() and ord(ch.lower()) in cf["glyphs"]:
                gd = cf["glyphs"][ord(ch.lower())]
        if gd is None or gd.get("lh", 0) <= 1:
            glyphs[ord(ch)] = {"adv": (gd["adv"] * ms) if gd else sp, "x": 0.0, "y": 0.0,
                               "fill": None, "outline": None, "ramp": None}
            continue
        try:
            img = FR.load_slice(gd)
        except Exception:          # noqa: BLE001 - a slice missing on disk: a gap, as the game's preview shows it
            glyphs[ord(ch)] = {"adv": gd["adv"] * ms, "x": 0.0, "y": 0.0, "fill": None, "outline": None, "ramp": None}
            continue
        pad, cscale = cf.get("cell_pad", 0.0), cf.get("cell_scale")
        if cscale:
            k = cscale * ms
            tw, th = max(1, int(round(img.size[0] * k))), max(1, int(round(img.size[1] * k)))
            img = img.resize((tw, th), Image.LANCZOS)
            x, y = gd["bx"] * ms - pad * k, asc * ms - gd["by"] * ms - pad * k
        else:
            img = FR._fit_to_metrics(img, gd, ms)
            x, y = gd["bx"] * ms, asc * ms - gd["by"] * ms
        alpha = img.split()[3]
        # the game's ink can carry its own colour; the HUD tints it, so its shape is its alpha (times its lightness)
        lum = img.convert("L")
        from PIL import ImageChops
        alpha = ImageChops.multiply(alpha, lum.point(lambda v: min(255, int(v * 1.25))))
        box = alpha.getbbox()
        g = {"adv": gd["adv"] * ms, "x": x, "y": y, "fill": None, "outline": None, "ramp": None}
        if box:
            alpha = alpha.crop(box)
            g["x"], g["y"] = x + box[0], y + box[1]
            g["fill"], g["outline"], g["ramp"] = _variants(alpha, g["y"], line, ow)
        glyphs[ord(ch)] = g
    return glyphs, line


def bake(mode_dir, doc, resolve=None, scale=1.0):
    """{font id: Baked} for every font of the document; ``scale`` bakes at another size (dot-matrix packs)."""
    resolve = resolve if resolve is not None else resolver(mode_dir)
    out = {}
    for f in (doc.get("assets") or {}).get("fonts") or []:
        fid = f.get("id")
        size = max(4, int(round(float(f.get("size") or 24) * scale)))
        ow = max(0, int(round(outline_px(f) * scale))) if outline_px(f) else 0
        source, stand_in = "stand-in", True
        if f.get("file") and mode_dir:
            path = os.path.join(mode_dir, *str(f["file"]).split("/"))
            glyphs, line, stand_in = _bake_ttf(path if os.path.isfile(path) else None, size, ow)
            source = f["file"] if not stand_in else "stand-in"
        else:
            got = resolve(f.get("face"))
            if isinstance(got, dict):
                glyphs, line = _bake_card(got, size, ow)
                stand_in, source = False, "card:%s" % (got.get("name") or got.get("key"))
            else:
                glyphs, line, stand_in = _bake_ttf(got if isinstance(got, str) else None, size, ow)
                if not stand_in:
                    source = os.path.basename(got)
        out[fid] = Baked(fid, size, line, ow, glyphs, stand_in, source)
    return out


# ---- the machine's packer ------------------------------------------------------------------------------------------
def items(baked):
    """(owner, index, image) for every glyph image: index is the code point (+1000 outline, +2000 ramp)."""
    out = []
    for fid, b in baked.items():
        for code, g in sorted(b.glyphs.items()):
            for off, key in ((0, "fill"), (VARIANT_OUTLINE, "outline"), (VARIANT_RAMP, "ramp")):
                if g[key] is not None:
                    out.append(("font:%s" % fid, code + off, g[key]))
    return out


def compiled(b, atlas, place, texel=1.0):
    """The compiler's font (compiler.py build_fonts): glyph rows (adv, x, y, sx, sy, sw, sh, osx, osy, osw, osh, rsx,
    rsy) in the engine's units. ``place(code_with_variant)`` gives (sx, sy, sw, sh) in the atlas, or None."""
    def fx(v):
        return int(round(float(v) * texel * ONE))
    rows = []
    for c in range(32, 127):
        g = b.glyphs.get(c) or {"adv": b.size * 0.5, "x": 0, "y": 0, "fill": None}
        fp = place(c) if g.get("fill") is not None else None
        op = place(c + VARIANT_OUTLINE) if g.get("fill") is not None else None
        rp = place(c + VARIANT_RAMP) if g.get("fill") is not None else None
        sx, sy, sw, sh = fp if fp else (0, 0, 0, 0)
        osx, osy, osw, osh = op if op else (-1, -1, 0, 0)
        rsx, rsy = (rp[0], rp[1]) if rp else (-1, -1)
        rows.append((fx(g["adv"]), fx(g["x"]), fx(g["y"]), sx, sy, sw, sh, osx, osy, osw, osh, rsx, rsy))
    return {"size": b.size, "line_h": fx(b.line), "atlas": atlas, "texel": int(round(texel * ONE)), "ow": fx(b.ow),
            "glyphs": rows}


# ---- the app: one sheet a font ------------------------------------------------------------------------------------
def _shelf(imgs, width=1024):
    """Shelf-pack [(key, image)] with 1 px of air: ({key: (x, y, w, h)}, (w, h))."""
    at, x, y, row = {}, 1, 1, 0
    for key, im in sorted(imgs, key=lambda kv: -kv[1].size[1]):
        w, h = im.size
        if x + w + 1 > width:
            x, y, row = 1, y + row + 1, 0
        at[key] = (x, y, w, h)
        x += w + 1
        row = max(row, h)
    return at, (width, y + row + 1)


def fingerprint(mode_dir, doc):
    """What a font sheet depends on: the fonts' rows, their files' times, and the project's glyph table's time."""
    fonts = (doc.get("assets") or {}).get("fonts") or []
    bits = [json.dumps(fonts, sort_keys=True), "v3"]
    for f in fonts:
        if f.get("file") and mode_dir:
            p = os.path.join(mode_dir, *str(f["file"]).split("/"))
            bits.append(str(os.path.getmtime(p)) if os.path.isfile(p) else "-")
    man = os.path.join(project_of(mode_dir), "images", "scene_textures", "glyph_images.txt") if mode_dir else ""
    bits.append(str(os.path.getmtime(man)) if man and os.path.isfile(man) else "-")
    return hashlib.sha1("\n".join(bits).encode("utf-8")).hexdigest()[:16]


def sheets(mode_dir, doc, out_dir, resolve=None):
    """Each font of the document as one PNG in ``out_dir`` (made once per fingerprint) and its compiled metrics:
    ({font id: {"path", "atlas", "stand_in", "source"}}, {font id: compiler font}). The atlas index is the
    compiler's FONT_ATLAS_BASE + the font's place in the list, as the player names its texture."""
    from PIL import Image
    fp = fingerprint(mode_dir, doc)
    files, metrics = {}, {}
    fonts = (doc.get("assets") or {}).get("fonts") or []
    baked = None
    for i, f in enumerate(fonts):
        fid = f.get("id")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(fid))[:32]
        png = os.path.join(out_dir, "font_%s_%s.png" % (safe, fp))
        meta = png[:-4] + ".json"
        if os.path.isfile(png) and os.path.isfile(meta):
            try:
                with open(meta, encoding="utf-8") as fh:
                    m = json.load(fh)
                m["font"]["glyphs"] = [tuple(r) for r in m["font"]["glyphs"]]
                files[fid] = {"path": png, "atlas": FONT_ATLAS_BASE + i, "stand_in": m["stand_in"], "source": m["source"]}
                metrics[fid] = m["font"]
                continue
            except (OSError, ValueError, KeyError):
                pass
        if baked is None:
            baked = bake(mode_dir, doc, resolve)
        b = baked[fid]
        imgs = [((c, key), g[key]) for c, g in b.glyphs.items() for key in ("fill", "outline", "ramp")
                if g[key] is not None]
        at, (w, h) = _shelf(imgs)
        sheet = Image.new("RGBA", (w, max(1, h)), (255, 255, 255, 0))
        for k, im in imgs:
            sheet.paste(im, at[k][:2])
        os.makedirs(out_dir, exist_ok=True)
        sheet.save(png + ".part.png")
        os.replace(png + ".part.png", png)

        def place(code, at=at):
            key = "ramp" if code >= VARIANT_RAMP else "outline" if code >= VARIANT_OUTLINE else "fill"
            return at.get((code % 1000, key))
        m = compiled(b, FONT_ATLAS_BASE + i, place)
        with open(meta + ".part", "w", encoding="utf-8") as fh:
            json.dump({"font": m, "stand_in": b.stand_in, "source": b.source}, fh)
        os.replace(meta + ".part", meta)
        files[fid] = {"path": png, "atlas": FONT_ATLAS_BASE + i, "stand_in": b.stand_in, "source": b.source}
        metrics[fid] = m
    return files, metrics
