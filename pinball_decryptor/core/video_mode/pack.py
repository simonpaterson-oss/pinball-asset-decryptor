"""Packing a video mode's pictures for a machine, and what it costs (PAD-1658).

:func:`pack` reads every picture of a video mode and every font it names, and

1. **trims** each frame to what it shows (a frame's empty edges cost memory and draw
   nothing), keeping where it sat, so the anchor still lands in the same place;
2. **folds** frames that are pixel for pixel the same into one;
3. **packs** them into atlases no larger than the machine's largest (MaxRects, best short
   side fit, largest first; the smallest power-of-two square that holds them, else
   pages of the largest), each frame with 2 texels of extruded edge so bilinear
   sampling never bleeds (wrapped, not clamped, for a picture a phase tiles);
4. **premultiplies** (docs/plans/video_mode_maker.md section 4: ``texel * T``);
5. **costs** it against the machine's budgets (:mod:`.budgets`): memory, the largest
   atlas, card space; and names the sprites to shrink when something is over.

:func:`write` writes the result in the format the machine's backend loads (below), and
:func:`for_card` is the only way a pack reaches a card: it refuses, naming the sprites,
when the mode is over a budget.

Backend formats (``atlas.json`` beside the atlases in each):

* ``webgl`` (the app): ``atlas_<n>.png``, RGBA8, already premultiplied.
* ``spike2``, ``spike3``, ``jjp``, ``spooky``, ``dots``: ``atlas_<n>.pmat``, a 16-byte
  header (``PMAT``, u16 version 1, u16 texel format 1 = RGBA8 premultiplied, u16 width,
  u16 height, u16 flags: bit 0 nearest sampling, bit 1 zlib, u16 0) then the texels,
  rows top to bottom, zlib-compressed. A loader in plain C needs only zlib, and a
  texture upload takes the inflated bytes as they are.

``atlas.json`` holds, for each picture, one entry per frame: ``atlas``, the source box
``sx, sy, sw, sh`` in texels, the anchor inside that box ``ax, ay`` in 16.16 (what the
draw list's ``pm_vm_quad`` carries; it can fall outside 0..1 when trimming cut past the
anchor), and the frame's own size ``fw, fh`` with the trim offset ``ox, oy``. Fonts are
glyph frames in the same atlases, with each glyph's advance and offsets.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import struct
import time
import zlib
from dataclasses import dataclass, field

from . import art as ART
from . import budgets as B

EXTRUDE = 2
MIN_ATLAS = 64
GLYPHS = "".join(chr(c) for c in range(32, 127))
BACKENDS = ("webgl", "spike2", "spike3", "jjp", "spooky", "dots")
PMAT_MAGIC = b"PMAT"
PMAT_RGBA8_PREMUL = 1
FLAG_NEAREST, FLAG_ZLIB = 1, 2
OUT_DIR = "build"


class OverBudget(ValueError):
    """A pack that may not go to a card; ``.problems`` names what to shrink."""

    def __init__(self, problems, report=None):
        self.problems = list(problems)
        self.report = report
        super().__init__("\n".join(self.problems))


@dataclass
class Item:
    owner: str                 # picture id, or "font:<id>"
    index: int                 # frame index, or the glyph's code point
    img: object                # trimmed RGBA (PIL), straight alpha
    ox: int = 0
    oy: int = 0
    fw: int = 0
    fh: int = 0
    anchor: tuple = (0.0, 0.0)
    wrap: bool = False         # a tiled background: extrude by wrapping
    key: str = ""              # pixel hash; same key = same texels
    place: tuple = None        # (atlas, x, y) of the item's box, extrude included


@dataclass
class Pack:
    machine: dict
    atlases: list = field(default_factory=list)       # [(w, h)]
    items: list = field(default_factory=list)         # every frame and glyph, folded ones too
    texels: list = field(default_factory=list)        # numpy uint8 (h, w, 4) premultiplied, per atlas
    fonts: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)
    seconds: float = 0.0
    report: dict = None


# ---- reading the mode --------------------------------------------------------------------
def tiled_pictures(doc):
    out = set()
    for ph in doc.get("phases") or []:
        for lay in ph.get("background") or []:
            if lay.get("tile"):
                out.add(lay.get("picture"))
    return out


def _trim(img):
    """(trimmed image, ox, oy); an empty frame trims to one see-through texel."""
    b = img.getchannel("A").getbbox()
    if b is None:
        return img.crop((0, 0, 1, 1)), 0, 0
    return img.crop(b), b[0], b[1]


def _scaled(img, k):
    """``img`` at ``k`` of its size (box filter in linear-ish space: Pillow's on premultiplied
    pixels, so see-through edges do not darken), at least 1x1."""
    if k == 1:
        return img
    from PIL import Image
    w, h = max(1, int(round(img.width * k))), max(1, int(round(img.height * k)))
    return img.convert("RGBa").resize((w, h), Image.Resampling.BOX).convert("RGBA")


def collect(mode_dir, doc, trim=True, scale=1.0):
    """Every frame of every picture as an :class:`Item` (at ``scale`` of its size), and the
    problems met. ``ox, oy, fw, fh`` are in packed texels."""
    items, problems = [], []
    tiled = tiled_pictures(doc)
    for p in (doc.get("assets") or {}).get("pictures") or []:
        pid = p.get("id")
        try:
            frames = ART.load_frames(mode_dir, p)
        except ART.ArtError as e:
            problems.append("Picture \"%s\": %s" % (pid, e))
            continue
        anchor = tuple(p.get("anchor") or (0.5, 0.5))
        wrap = pid in tiled
        for i, f in enumerate(frames):
            f = _scaled(f, scale)
            fw, fh = f.size
            if trim and not wrap:
                t, ox, oy = _trim(f)
            else:
                t, ox, oy = f, 0, 0
            items.append(Item(pid, i, t, ox, oy, fw, fh, anchor, wrap))
    return items, problems


def _font_file(mode_dir, font, resolve):
    if font.get("file"):
        return ART.picture_path(mode_dir, font)
    face = str(font.get("face") or "")
    if resolve:
        got = resolve(face)
        if got:
            return got
    return None


def bake_fonts(mode_dir, doc, resolve=None, scale=1.0):
    """Each font of the document as glyph items and its metrics. ``resolve(face)`` gives a
    font file for a ``card:<name>`` face; with none, a stand-in face of the same size is
    baked and the font says ``stand_in`` (its cost is the real one's to within the
    glyph shapes)."""
    from PIL import Image, ImageDraw, ImageFont
    items, fonts, problems = [], {}, []
    for f in (doc.get("assets") or {}).get("fonts") or []:
        fid, size = f.get("id"), max(4, int(round(float(f.get("size") or 24) * scale)))
        path = _font_file(mode_dir, f, resolve)
        stand_in = False
        try:
            font = ImageFont.truetype(path, size) if path else None
        except OSError:
            problems.append("Font \"%s\": %s is not a font file this app can read." % (fid, os.path.basename(path)))
            font = None
        if font is None:
            font, stand_in = ImageFont.load_default(size), True
        ascent, descent = font.getmetrics()
        glyphs = {}
        for ch in GLYPHS:
            l, t, r, b = font.getbbox(ch)
            adv = font.getlength(ch)
            glyphs[ord(ch)] = {"adv": round(adv, 2), "x": l, "y": t}
            if r <= l or b <= t:
                continue
            img = Image.new("RGBA", (r - l, b - t), (255, 255, 255, 0))
            ImageDraw.Draw(img).text((-l, -t), ch, font=font, fill=(255, 255, 255, 255))
            items.append(Item("font:%s" % fid, ord(ch), img, 0, 0, r - l, b - t, (0.0, 0.0)))
        fonts[fid] = {"size": size, "ascent": ascent, "descent": descent, "line": ascent + descent,
                      "stand_in": stand_in, "glyphs": glyphs}
    return items, fonts, problems


# ---- packing -----------------------------------------------------------------------------
class MaxRects:
    """One bin; ``insert`` returns (x, y) or None (best short side fit)."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.free = [(0, 0, w, h)]

    def insert(self, w, h):
        best, score = None, None
        for fx, fy, fw, fh in self.free:
            if w <= fw and h <= fh:
                s = (min(fw - w, fh - h), max(fw - w, fh - h), fy, fx)
                if score is None or s < score:
                    best, score = (fx, fy), s
        if best is None:
            return None
        self._place(best[0], best[1], w, h)
        return best

    def _place(self, x, y, w, h):
        out = []
        for f in self.free:
            fx, fy, fw, fh = f
            if x >= fx + fw or x + w <= fx or y >= fy + fh or y + h <= fy:
                out.append(f)
                continue
            if x > fx:
                out.append((fx, fy, x - fx, fh))
            if x + w < fx + fw:
                out.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy:
                out.append((fx, fy, fw, y - fy))
            if y + h < fy + fh:
                out.append((fx, y + h, fw, fy + fh - y - h))
        # drop free boxes inside another
        out.sort(key=lambda r: -r[2] * r[3])
        keep = []
        for r in out:
            if not any(r[0] >= k[0] and r[1] >= k[1] and r[0] + r[2] <= k[0] + k[2] and r[1] + r[3] <= k[1] + k[3]
                       for k in keep):
                keep.append(r)
        self.free = keep


def _sizes(limit):
    """Power-of-two atlas sizes (w, h) up to ``limit`` a side, smallest area first, and the
    squarer of two of one area first (2048x1024 before 4096x512)."""
    sides, s = [], MIN_ATLAS
    while s < limit:
        sides.append(s)
        s *= 2
    sides.append(limit)
    out = [(w, h) for w in sides for h in sides if w >= h]
    out.sort(key=lambda wh: (wh[0] * wh[1], wh[0] - wh[1]))
    return out


def _try(boxes, size):
    """Every box into one bin of ``size`` (w, h), or None."""
    b = MaxRects(size[0], size[1])
    out = []
    for w, h in boxes:
        got = b.insert(w, h)
        if got is None:
            return None
        out.append(got)
    return out


def _could(boxes, area, size):
    W, H = size
    return W * H >= area and all(w <= W and h <= H for w, h in boxes)


def place_boxes(boxes, limit):
    """[(atlas, x, y)] for ``boxes`` [(w, h)] (already sorted), and [(side, side)] per atlas."""
    if not boxes:
        return [], []
    area = sum(w * h for w, h in boxes)
    for size in _sizes(limit):
        if not _could(boxes, area, size):
            continue
        got = _try(boxes, size)
        if got is not None:
            return [(0, x, y) for x, y in got], [size]
    # pages of the largest; the last one shrunk to the smallest that holds what is on it
    pages, where = [], [None] * len(boxes)
    for i, (w, h) in enumerate(boxes):
        for n, pg in enumerate(pages):
            got = pg[0].insert(w, h)
            if got is not None:
                pg[1].append(i)
                where[i] = (n, got[0], got[1])
                break
        else:
            pg = (MaxRects(limit, limit), [i])
            got = pg[0].insert(w, h)
            pages.append(pg)
            where[i] = (len(pages) - 1, got[0], got[1])
    sizes = [(limit, limit)] * len(pages)
    last = pages[-1][1]
    lb = [boxes[i] for i in last]
    la = sum(w * h for w, h in lb)
    for size in _sizes(limit):
        if not _could(lb, la, size):
            continue
        got = _try(lb, size)
        if got is not None:
            for i, (x, y) in zip(last, got):
                where[i] = (len(pages) - 1, x, y)
            sizes[-1] = size
            break
    return where, sizes


def _premultiply(img):
    import numpy as np
    a = np.asarray(img, dtype=np.uint16)
    out = np.empty(a.shape, dtype=np.uint8)
    al = a[..., 3:4]
    out[..., :3] = ((a[..., :3] * al + 127) // 255).astype(np.uint8)
    out[..., 3] = a[..., 3]
    return out


def pack(mode_dir, doc, machine=B.DEFAULT, fonts=True, resolve_font=None, trim=True):
    """Pack the mode's pictures (and fonts) for ``machine`` (:data:`.budgets.MACHINES`).
    Nothing is written; the :class:`Pack` carries the atlases, the places and the cost
    report (``.report``)."""
    import numpy as np
    t0 = time.perf_counter()
    m = B.machine(machine)
    limit = int(m["atlas"])
    items, problems = collect(mode_dir, doc, trim, float(m["art_scale"]))
    font_meta = {}
    if fonts:
        fi, font_meta, fp = bake_fonts(mode_dir, doc, resolve_font, float(m["art_scale"]))
        items += fi
        problems += fp
    # fold same pixels
    first = {}
    unique = []
    for it in items:
        h = hashlib.blake2b(it.img.tobytes(), digest_size=16)
        h.update(struct.pack("<II?", it.img.width, it.img.height, it.wrap))
        it.key = h.hexdigest()
        if it.key not in first:
            first[it.key] = it
            unique.append(it)
    too_big = []
    fit = []
    for it in unique:
        w, h = it.img.width + 2 * EXTRUDE, it.img.height + 2 * EXTRUDE
        if w > limit or h > limit:
            too_big.append(it)
        else:
            fit.append(it)
    seen_big = set()
    for it in too_big:
        if it.owner in seen_big:
            continue
        seen_big.add(it.owner)
        problems.append("%s: a frame is %dx%d (with its edge), larger than the largest picture %s takes, "
                        "%dx%d. Make it smaller or cut it in parts."
                        % (_label(it.owner), it.img.width + 2 * EXTRUDE, it.img.height + 2 * EXTRUDE,
                           m["label"], limit, limit))
    fit.sort(key=lambda it: (-max(it.img.width, it.img.height), -it.img.width * it.img.height, it.owner,
                             it.index))
    where, sizes = place_boxes([(it.img.width + 2 * EXTRUDE, it.img.height + 2 * EXTRUDE) for it in fit], limit)
    canvases = [np.zeros((h, w, 4), dtype=np.uint8) for w, h in sizes]
    for it, (n, x, y) in zip(fit, where):
        it.place = (n, x, y)
        px = _premultiply(it.img)
        px = np.pad(px, ((EXTRUDE, EXTRUDE), (EXTRUDE, EXTRUDE), (0, 0)), mode="wrap" if it.wrap else "edge")
        canvases[n][y:y + px.shape[0], x:x + px.shape[1]] = px
    for it in items:
        if it.place is None and it.key in first and first[it.key] is not it:
            it.place = first[it.key].place
    pk = Pack(machine=m, atlases=sizes, items=items, texels=canvases, fonts=font_meta, problems=problems)
    pk.seconds = time.perf_counter() - t0
    pk.report = cost(pk, mode_dir, doc)
    return pk


def _label(owner):
    return 'Font "%s"' % owner[5:] if owner.startswith("font:") else 'Sprite "%s"' % owner


# ---- the cost ----------------------------------------------------------------------------
def _file_size(mode_dir, rel):
    try:
        return os.path.getsize(ART.picture_path(mode_dir, {"file": rel}))
    except (OSError, TypeError):
        return 0


def _atlas_bytes(arr):
    return len(zlib.compress(arr.tobytes(), 6)) + 16


def cost(pk, mode_dir, doc):
    """What the mode costs on ``pk.machine``: memory (every atlas, texel for texel), card
    space (the packed atlases compressed, as :func:`write` writes them for the machine,
    plus the sounds, clips and font files as they are in the mode folder), each sprite's
    share, and the problems, each naming what to shrink."""
    m = pk.machine
    tb = int(m["texel_bytes"])
    memory = sum(w * h * tb for w, h in pk.atlases)
    atlas_card = [_atlas_bytes(a) for a in pk.texels]
    pics_card = sum(atlas_card)
    # each sprite's share: the texels its own (unfolded) boxes take, and that share of the card bytes
    own = {}
    frames = {}
    seen = set()
    for it in pk.items:
        frames.setdefault(it.owner, [0, 0])
        frames[it.owner][0] += 1
        if it.place is None or it.key in seen:
            continue
        seen.add(it.key)
        frames[it.owner][1] += 1
        area = (it.img.width + 2 * EXTRUDE) * (it.img.height + 2 * EXTRUDE)
        own[it.owner] = own.get(it.owner, 0) + area
    used = sum(own.values())
    total_area = sum(w * h for w, h in pk.atlases) or 1
    sprites = []
    for owner, (n, u) in frames.items():
        a = own.get(owner, 0)
        sprites.append({"id": owner, "label": _label(owner), "font": owner.startswith("font:"), "frames": n,
                        "unique": u, "texels": a, "memory": a * tb,
                        "card": int(round(pics_card * a / float(used))) if used else 0,
                        "pct": round(100.0 * a / total_area, 1)})
    sprites.sort(key=lambda s: (-s["memory"], s["id"]))
    others = []
    a = doc.get("assets") or {}
    for kind in ("sounds", "clips"):
        for s in a.get(kind) or []:
            others.append({"id": s.get("id"), "kind": kind[:-1], "file": s.get("file"),
                           "card": _file_size(mode_dir, s.get("file"))})
    for f in a.get("fonts") or []:
        if f.get("file"):
            others.append({"id": f.get("id"), "kind": "font file", "file": f.get("file"),
                           "card": _file_size(mode_dir, f.get("file"))})
    card = pics_card + sum(o["card"] for o in others)
    problems = list(pk.problems)
    if memory > m["memory"]:
        problems.append(_over("Pictures need %s of memory; %s has room for %s." % (
            fmt_bytes(memory), m["label"], fmt_bytes(m["memory"])), memory - m["memory"],
            [(s["label"], s["memory"]) for s in sprites], memory))
    if card > m["card"]:
        problems.append(_over("The mode needs %s of card space; %s gives a video mode %s." % (
            fmt_bytes(card), m["label"], fmt_bytes(m["card"])), card - m["card"],
            [(s["label"], s["card"]) for s in sprites]
            + [('%s "%s"' % (o["kind"].capitalize(), o["id"]), o["card"]) for o in others], card))
    return {
        "machine": m["key"], "label": m["label"],
        "budget": {"memory": m["memory"], "card": m["card"], "atlas": m["atlas"]},
        "memory": memory, "card": card, "card_pictures": pics_card,
        "atlases": [{"w": w, "h": h, "memory": w * h * tb, "card": atlas_card[i],
                     "used_pct": round(100.0 * _used_on(pk, i) / float(w * h), 1)}
                    for i, (w, h) in enumerate(pk.atlases)],
        "frames": len(pk.items), "unique": len(seen), "trimmed_away": _trimmed_away(pk),
        "sprites": sprites, "others": others, "fonts": {k: {"size": v["size"], "stand_in": v["stand_in"]}
                                                       for k, v in pk.fonts.items()},
        "problems": problems, "ok": not problems, "seconds": round(pk.seconds, 3),
    }


def _used_on(pk, n):
    seen, area = set(), 0
    for it in pk.items:
        if it.place and it.place[0] == n and it.key not in seen:
            seen.add(it.key)
            area += (it.img.width + 2 * EXTRUDE) * (it.img.height + 2 * EXTRUDE)
    return area


def _trimmed_away(pk):
    """Texels the trim and the folding saved, against packing every frame whole."""
    whole = sum(it.fw * it.fh for it in pk.items)
    kept, seen = 0, set()
    for it in pk.items:
        if it.key not in seen:
            seen.add(it.key)
            kept += it.img.width * it.img.height
    return max(0, whole - kept)


def _over(head, excess, parts, total):
    """``head`` and the biggest parts, enough of them to cover ``excess``; a part under 2% of
    the whole is never named (shrinking it would not help: the rest is atlas room)."""
    parts = sorted((p for p in parts if p[1] > 0), key=lambda p: -p[1])
    parts = parts[:1] + [p for p in parts[1:] if p[1] >= 0.02 * total]
    names, got = [], 0
    for label, b in parts:
        names.append("%s (%s, %d%%)" % (label, fmt_bytes(b), round(100.0 * b / total)) if total else label)
        got += b
        if got >= excess or len(names) >= 5:
            break
    return "%s Shrink %s: fewer frames, smaller frames, or fewer pictures." % (head, _and(names)) if names else head


def _and(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def fmt_bytes(n):
    n = float(n)
    if n >= B.MB:
        return "%.1f MB" % (n / B.MB)
    if n >= 1024:
        return "%.0f KB" % (n / 1024)
    return "%d bytes" % n


# ---- writing -----------------------------------------------------------------------------
def _fx(v):
    return int(round(v * 65536))


def manifest(pk, backend, files):
    pics = {}
    for it in pk.items:
        if it.owner.startswith("font:") or it.place is None:
            continue
        n, x, y = it.place
        sw, sh = it.img.width, it.img.height
        ax = (it.anchor[0] * it.fw - it.ox) / float(sw)
        ay = (it.anchor[1] * it.fh - it.oy) / float(sh)
        pics.setdefault(it.owner, []).append({
            "frame": it.index, "atlas": n, "sx": x + EXTRUDE, "sy": y + EXTRUDE, "sw": sw, "sh": sh,
            "ax": _fx(ax), "ay": _fx(ay), "fw": it.fw, "fh": it.fh, "ox": it.ox, "oy": it.oy})
    for v in pics.values():
        v.sort(key=lambda e: e["frame"])
    fonts = {}
    for fid, meta in pk.fonts.items():
        g = {}
        for it in pk.items:
            if it.owner == "font:%s" % fid and it.place is not None:
                n, x, y = it.place
                g[it.index] = {"atlas": n, "sx": x + EXTRUDE, "sy": y + EXTRUDE, "sw": it.img.width,
                               "sh": it.img.height}
        glyphs = {}
        for cp, gm in meta["glyphs"].items():
            glyphs[str(cp)] = dict(gm, **g.get(cp, {}))
        fonts[fid] = dict(meta, glyphs=glyphs)
    return {"format": 1, "backend": backend, "machine": pk.machine["key"], "extrude": EXTRUDE,
            "premultiplied": True, "texel_scale": round(1.0 / float(pk.machine["art_scale"]), 6),
            "atlases": [{"file": f, "w": w, "h": h, "texel": "rgba8_premultiplied", "filter": "linear"}
                        for f, (w, h) in zip(files, pk.atlases)],
            "pictures": pics, "fonts": fonts}


def pmat_bytes(arr, nearest=False):
    h, w = arr.shape[:2]
    flags = FLAG_ZLIB | (FLAG_NEAREST if nearest else 0)
    return PMAT_MAGIC + struct.pack("<HHHHHH", 1, PMAT_RGBA8_PREMUL, w, h, flags, 0) + zlib.compress(arr.tobytes(), 6)


def read_pmat(blob):
    """(width, height, flags, RGBA8 bytes) of a .pmat file."""
    if blob[:4] != PMAT_MAGIC:
        raise ValueError("not a PMAT atlas")
    ver, fmt, w, h, flags, _ = struct.unpack("<HHHHHH", blob[4:16])
    if ver != 1 or fmt != PMAT_RGBA8_PREMUL:
        raise ValueError("PMAT version %d format %d is not read here" % (ver, fmt))
    data = blob[16:]
    if flags & FLAG_ZLIB:
        data = zlib.decompress(data)
    if len(data) != w * h * 4:
        raise ValueError("PMAT holds %d bytes, not %d" % (len(data), w * h * 4))
    return w, h, flags, data


def write(pk, out_dir, backend=None):
    """Write ``pk`` for ``backend`` (default: the machine's own) into ``out_dir``: the
    atlases and atlas.json. Returns atlas.json's path."""
    from PIL import Image
    backend = backend or pk.machine["backend"]
    if backend not in BACKENDS:
        raise ValueError("No backend %r; they are %s." % (backend, ", ".join(BACKENDS)))
    os.makedirs(out_dir, exist_ok=True)
    for n in os.listdir(out_dir):
        if n.startswith("atlas_") and (n.endswith(".png") or n.endswith(".pmat")):
            os.remove(os.path.join(out_dir, n))
    files = []
    for i, arr in enumerate(pk.texels):
        if backend == "webgl":
            name = "atlas_%d.png" % i
            buf = io.BytesIO()
            Image.fromarray(arr, "RGBA").save(buf, format="PNG", compress_level=1)
            data = buf.getvalue()
        else:
            name = "atlas_%d.pmat" % i
            data = pmat_bytes(arr)
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(data)
        files.append(name)
    path = os.path.join(out_dir, "atlas.json")
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest(pk, backend, files), f, indent=1, sort_keys=True)
    os.replace(tmp, path)
    return path


def for_card(mode_dir, doc, machine, out_dir=None, resolve_font=None):
    """Pack and write the mode for a card. Over any budget: nothing is written and
    :class:`OverBudget` names the sprites to shrink. Every path that puts a video mode
    on a card goes through here."""
    pk = pack(mode_dir, doc, machine, resolve_font=resolve_font)
    if not pk.report["ok"]:
        raise OverBudget(pk.report["problems"], pk.report)
    out = out_dir or os.path.join(mode_dir, OUT_DIR, pk.machine["backend"])
    write(pk, out)
    return pk
