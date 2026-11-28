"""Bringing art into a video mode (PAD-1658): every kind of file becomes a sprite.

A **sprite** is a named picture with frames: a still has one, an animation many. Every
import gives a :class:`Sprite` (its frames as RGBA images of one size, a frame rate, loop
or once), and :func:`save_sprite` writes it into the mode folder as a sheet PNG
(``art/<id>.png``, frames left to right, top to bottom) with its entry in
``assets.pictures`` (``frame_w``, ``frame_h``, ``frames``, ``anchor``, ``hitbox`` and a
``play`` animation), the shape docs/plans/video_mode_maker.md section 3 gives a picture.

The kinds (:data:`KINDS`):

* ``picture``  one PNG, JPEG, BMP, WebP or TIFF.
* ``numbered`` a numbered run (``boom_0001.png``, ``boom_0002.png`` ...): any file of the
  run brings the whole run, in number order.
* ``gif``      an animated GIF, APNG or WebP, with its own frame times and loop.
* ``grid``     a sprite sheet sliced by a grid (frame size, margin, spacing, count).
* ``auto``     a sprite sheet sliced by finding its empty gutters: the rows, then the
  columns in each row, that hold nothing but the sheet's background.
* ``video``    a stretch of a video, cut out with a colour key or with the video's own
  alpha (WebM VP8/VP9, ProRes 4444, PNG or QuickTime Animation in a MOV). The cut goes
  through film_cut.py, the clip cutter the Modes tab already uses.

Frames of different sizes (a numbered run, auto-sliced cells) are centred on the largest.
Backgrounds are pictures too; a phase's ``background`` layers (still, tiled, scrolling,
each with its own speed) name them (:func:`set_backgrounds`).
"""

from __future__ import annotations

import io
import math
import os
import re
from dataclasses import dataclass, field

KINDS = ("picture", "numbered", "gif", "grid", "auto", "video")
KIND_LABELS = {
    "picture": "A picture", "numbered": "A numbered run of PNGs", "gif": "An animated GIF",
    "grid": "A sprite sheet, sliced by a grid", "auto": "A sprite sheet, sliced at its empty gutters",
    "video": "A stretch of video",
}
PICTURE_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff")
ANIM_EXT = (".gif", ".apng")
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".wmv", ".mpg", ".mpeg")

MAX_FRAMES = 1024          # the schema's picture.frames maximum
MAX_SIDE = 4096            # the schema's frame_w / frame_h maximum
MAX_SHEET = 16384          # a sheet PNG's widest side (Pillow and every browser read it)
MAX_VIDEO_SECONDS = 30.0
DEFAULT_FPS = 12.0
ART_DIR = "art"


class ArtError(ValueError):
    """Art that cannot be brought in, said in plain words."""


@dataclass
class Sprite:
    frames: list                       # PIL "RGBA" images, all one size
    fps: float = DEFAULT_FPS
    loop: bool = True
    source: str = ""                   # what it came from, for the page
    notes: list = field(default_factory=list)

    @property
    def size(self):
        return self.frames[0].size if self.frames else (0, 0)


def _pil():
    from PIL import Image
    return Image


def _name(path):
    return os.path.basename(path or "") or "(no file)"


def _open(path):
    if not path or not os.path.isfile(path):
        raise ArtError("There is no file at %s." % (path or "(no file chosen)"))
    Image = _pil()
    try:
        img = Image.open(path)
        img.load()
    except Exception as e:                       # noqa: BLE001 - any decode failure is the file's
        raise ArtError("%s is not a picture this app can read (%s)." % (_name(path), e)) from None
    return img


def _rgba(img):
    return img if img.mode == "RGBA" else img.convert("RGBA")


def _check_frames(frames, what):
    if not frames:
        raise ArtError("%s has no frames in it." % what)
    if len(frames) > MAX_FRAMES:
        raise ArtError("%s has %d frames; a sprite holds up to %d. Bring in a shorter stretch."
                       % (what, len(frames), MAX_FRAMES))
    w, h = frames[0].size
    if w > MAX_SIDE or h > MAX_SIDE:
        raise ArtError("%s is %dx%d; a sprite's frame is at most %dx%d." % (what, w, h, MAX_SIDE, MAX_SIDE))


def uniform(frames):
    """Frames of different sizes, each centred on a canvas the size of the largest."""
    frames = [_rgba(f) for f in frames]
    w = max(f.width for f in frames)
    h = max(f.height for f in frames)
    if all(f.size == (w, h) for f in frames):
        return frames
    Image = _pil()
    out = []
    for f in frames:
        c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        c.paste(f, ((w - f.width) // 2, (h - f.height) // 2))
        out.append(c)
    return out


# ---- a picture ---------------------------------------------------------------------------
def from_picture(path):
    img = _rgba(_open(path))
    s = Sprite([img], fps=DEFAULT_FPS, loop=False, source=_name(path))
    _check_frames(s.frames, _name(path))
    return s


# ---- a numbered run ----------------------------------------------------------------------
_NUM = re.compile(r"^(.*?)(\d+)(\.[A-Za-z0-9]+)$")


def numbered_run(path):
    """Every file of the run ``path`` belongs to, in number order: same folder, same words
    before the number, same extension (``boom_1.png`` .. ``boom_12.png`` and
    ``boom_0001.png`` both work). A file with no number is a run of one."""
    folder, base = os.path.split(os.path.abspath(path))
    m = _NUM.match(base)
    if not m:
        return [path]
    pre, ext = m.group(1), m.group(3).lower()
    rx = re.compile(r"^%s(\d+)%s$" % (re.escape(pre), re.escape(ext)), re.IGNORECASE)
    run = []
    for n in os.listdir(folder):
        mm = rx.match(n)
        if mm:
            run.append((int(mm.group(1)), n))
    run.sort()
    return [os.path.join(folder, n) for _, n in run]


def from_numbered(path, fps=DEFAULT_FPS, loop=True):
    files = numbered_run(path)
    frames = [_rgba(_open(f)) for f in files[:MAX_FRAMES + 1]]
    what = "The run %s" % _name(files[0])
    _check_frames(frames, what)
    s = Sprite(uniform(frames), fps=float(fps), loop=bool(loop),
               source="%s .. %s (%d files)" % (_name(files[0]), _name(files[-1]), len(files)))
    if len({f.size for f in frames}) > 1:
        s.notes.append("The files are not all one size; each is centred on the largest.")
    return s


# ---- an animated GIF / APNG / WebP -------------------------------------------------------
def from_gif(path):
    img = _open(path)
    n = getattr(img, "n_frames", 1)
    if n > MAX_FRAMES:
        raise ArtError("%s has %d frames; a sprite holds up to %d." % (_name(path), n, MAX_FRAMES))
    frames, times = [], []
    for i in range(n):
        img.seek(i)
        frames.append(img.convert("RGBA").copy())   # Pillow composites each frame over the last
        times.append(int(img.info.get("duration") or 100))
    # GIF: "loop" present = the NETSCAPE loop block (0 = for ever); absent = play once.
    loop = "loop" in img.info
    times.sort()
    mid = times[len(times) // 2] or 100
    fps = max(1.0, min(60.0, round(1000.0 / mid, 2)))
    _check_frames(frames, _name(path))
    s = Sprite(frames, fps=fps, loop=loop, source=_name(path))
    if len(set(times)) > 1:
        s.notes.append("Its frames have different times; it plays at the usual one, %g a second." % fps)
    return s


# ---- a sprite sheet by grid --------------------------------------------------------------
def grid_boxes(size, frame_w, frame_h, margin=0, spacing=0, count=None):
    W, H = size
    fw, fh, m, sp = int(frame_w), int(frame_h), int(margin), int(spacing)
    if fw < 1 or fh < 1:
        raise ArtError("A frame is at least 1x1.")
    if fw > W - 2 * m or fh > H - 2 * m:
        raise ArtError("A %dx%d frame does not fit in a %dx%d sheet." % (fw, fh, W, H))
    cols = (W - 2 * m + sp) // (fw + sp)
    rows = (H - 2 * m + sp) // (fh + sp)
    boxes = [(m + c * (fw + sp), m + r * (fh + sp), fw, fh) for r in range(rows) for c in range(cols)]
    if count:
        if int(count) > len(boxes):
            raise ArtError("That grid holds %d frames, not %d." % (len(boxes), int(count)))
        boxes = boxes[:int(count)]
    return boxes


def _crop(img, boxes):
    return [img.crop((x, y, x + w, y + h)) for x, y, w, h in boxes]


def from_sheet_grid(path, frame_w, frame_h, margin=0, spacing=0, count=None, fps=DEFAULT_FPS, loop=True,
                    drop_empty=True):
    img = _rgba(_open(path))
    boxes = grid_boxes(img.size, frame_w, frame_h, margin, spacing, count)
    frames = _crop(img, boxes)
    if drop_empty and not count:
        # a sheet's last row is often part full: its empty cells are not frames
        while len(frames) > 1 and frames[-1].getbbox() is None:
            frames.pop()
    _check_frames(frames, _name(path))
    return Sprite(frames, fps=float(fps), loop=bool(loop), source="%s, %dx%d grid" % (_name(path), int(frame_w),
                                                                                      int(frame_h)))


# ---- a sprite sheet by its gutters -------------------------------------------------------
def _empty_mask(img, tolerance=8):
    """True where a pixel is the sheet's background: see-through, or (a sheet with no
    see-through pixels) the colour of its top left corner."""
    import numpy as np
    a = np.asarray(img, dtype=np.uint8)
    alpha = a[..., 3]
    if (alpha < 255).any():
        return alpha < 8
    bg = a[0, 0, :3].astype(np.int16)
    return (np.abs(a[..., :3].astype(np.int16) - bg).max(axis=2) <= tolerance)


def _runs(full):
    """[(start, end)) of the False runs in a 1-D bool array (False = has something)."""
    out, start = [], None
    for i, e in enumerate(list(full) + [True]):
        if not e and start is None:
            start = i
        elif e and start is not None:
            out.append((start, i))
            start = None
    return out


def find_cells(img, tolerance=8, min_gap=1):
    """The frames of a sheet laid out with empty gutters: bands of rows that hold
    something, then in each band the columns that do; each cell cut to what it holds.
    Gaps narrower than ``min_gap`` do not split. Reading order: top to bottom, left to
    right."""
    empty = _empty_mask(_rgba(img), tolerance)
    def merge(runs):
        out = []
        for r in runs:
            if out and r[0] - out[-1][1] < min_gap:
                out[-1] = (out[-1][0], r[1])
            else:
                out.append(r)
        return out
    boxes = []
    for y0, y1 in merge(_runs(empty.all(axis=1))):
        band = empty[y0:y1]
        for x0, x1 in merge(_runs(band.all(axis=0))):
            cell = band[:, x0:x1]
            rows = _runs(cell.all(axis=1))
            yy0, yy1 = rows[0][0], rows[-1][1]
            boxes.append((x0, y0 + yy0, x1 - x0, yy1 - yy0))
    return boxes


def from_sheet_auto(path, tolerance=8, min_gap=1, fps=DEFAULT_FPS, loop=True):
    img = _rgba(_open(path))
    boxes = find_cells(img, tolerance, min_gap)
    if not boxes:
        raise ArtError("%s holds nothing but its background." % _name(path))
    frames = _crop(img, boxes)
    mask = _empty_mask(img, tolerance)
    if not (img.getchannel("A").getextrema()[0] < 255):
        # an opaque sheet: its background colour becomes see-through in the frames
        import numpy as np
        Image = _pil()
        a = np.array(img)
        a[mask, 3] = 0
        frames = _crop(Image.fromarray(a, "RGBA"), boxes)
    _check_frames(frames, _name(path))
    s = Sprite(uniform(frames), fps=float(fps), loop=bool(loop),
               source="%s, %d frames found at its gutters" % (_name(path), len(boxes)))
    if len({(w, h) for _, _, w, h in boxes}) > 1:
        s.notes.append("The frames found are not all one size; each is centred on the largest.")
    return s


# ---- a stretch of video ------------------------------------------------------------------
def parse_colour(text):
    t = (text or "").strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", t):
        raise ArtError("A key colour is written #rrggbb, not %r." % (text,))
    return tuple(int(t[i:i + 2], 16) for i in (0, 2, 4))


def key_out(rgba, key, tolerance=0.18, softness=0.10, despill=True):
    """See-through where a pixel is near ``key`` (an (r, g, b)): fully at a distance under
    ``tolerance`` (0..1 of the colour cube's diagonal), fading back in over ``softness``.
    ``despill`` takes the key colour's tint off what remains: the key's strongest channel
    is held down to the larger of the other two wherever it stands above both (a video's
    colour is stored at half size, so the screen bleeds into pixels the key keeps)."""
    import numpy as np
    a = np.array(rgba, dtype=np.float32)
    k = np.asarray(key, dtype=np.float32)
    d = np.sqrt(((a[..., :3] - k) ** 2).sum(axis=2)) / (255.0 * math.sqrt(3))
    lo, hi = float(tolerance), float(tolerance) + max(1e-6, float(softness))
    keep = np.clip((d - lo) / (hi - lo), 0.0, 1.0)
    if despill:
        c = int(np.argmax(k))
        others = [i for i in range(3) if i != c]
        cap = np.maximum(a[..., others[0]], a[..., others[1]])
        a[..., c] = np.minimum(a[..., c], cap)
    a[..., 3] = a[..., 3] * keep
    return np.clip(a + 0.5, 0, 255).astype(np.uint8)


def split_pngs(data):
    """The PNGs in an ffmpeg image2pipe stream, each ending at its IEND chunk."""
    out, i = [], 0
    end = b"IEND\xaeB`\x82"
    while i < len(data):
        j = data.find(end, i)
        if j < 0:
            break
        out.append(data[i:j + len(end)])
        i = j + len(end)
    return out


def _video_codec(path):
    """The first video stream's codec name, from ffprobe (or "")."""
    import json
    import subprocess
    from ...core import audio as _audio
    ff = _audio.find_ffmpeg()
    probe = None
    if ff:
        d = os.path.dirname(ff)
        for n in ("ffprobe.exe", "ffprobe"):
            if os.path.isfile(os.path.join(d, n)):
                probe = os.path.join(d, n)
    if not probe:
        return ""
    try:
        r = subprocess.run([probe, "-v", "quiet", "-print_format", "json", "-show_streams", "-select_streams",
                            "V:0", path], capture_output=True, timeout=60, stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        s = (json.loads(r.stdout or b"{}").get("streams") or [{}])[0]
        return str(s.get("codec_name") or "")
    except Exception:                            # noqa: BLE001 - unknown codec = the default decoder
        return ""


def from_video(path, start=0.0, length=2.0, fps=DEFAULT_FPS, cut="key", key="#00ff00", tolerance=0.18,
               softness=0.10, width=None, loop=True, ffmpeg=None):
    """A stretch of video as frames. ``cut``: ``key`` (``key`` colour made see-through),
    ``alpha`` (the video's own see-through), or ``none``. ``width`` scales the frames
    (default: the video's own, up to the stage's 1360)."""
    from ...plugins.stern import film_cut as FC
    if not path or not os.path.isfile(path):
        raise ArtError("There is no video at %s." % (path or "(no file chosen)"))
    start = FC.parse_time(start) if isinstance(start, str) else float(start)
    length = FC.parse_time(length) if isinstance(length, str) else float(length)
    if length <= 0 or length > MAX_VIDEO_SECONDS:
        raise ArtError("A stretch of video for a sprite is up to %d seconds." % MAX_VIDEO_SECONDS)
    fps = float(fps)
    if not (1 <= fps <= 60):
        raise ArtError("A sprite plays 1 to 60 frames a second.")
    if math.ceil(length * fps) > MAX_FRAMES:
        raise ArtError("%g seconds at %g a second is more than %d frames." % (length, fps, MAX_FRAMES))
    if cut not in ("key", "alpha", "none"):
        raise ArtError("A video is cut out by a key colour, by its own alpha, or not at all.")
    keyrgb = parse_colour(key) if cut == "key" else None
    try:
        ff = FC._ffmpeg(ffmpeg)
    except FC.FilmCutError as e:
        raise ArtError(str(e)) from None
    pre = []
    if cut == "alpha":
        # ffmpeg's own VP8/VP9 decoders drop the alpha a WebM carries; libvpx keeps it
        codec = _video_codec(path)
        if codec in ("vp8", "vp9"):
            pre = ["-c:v", "libvpx-vp9" if codec == "vp9" else "libvpx"]
    vf = "fps=%g" % fps
    w = int(width) if width else 0
    if w:
        vf += ",scale=%d:-2:flags=lanczos" % w
    else:
        vf += ",scale='min(iw,%d)':-2:flags=lanczos" % 1360
    vf += ",format=rgba"
    cmd = [ff, "-v", "error", "-nostdin", "-ss", FC._secs(start)] + pre + [
        "-t", FC._secs(length), "-i", path, "-map", "0:V:0", "-an", "-sn", "-dn", "-vf", vf,
        "-frames:v", str(MAX_FRAMES), "-c:v", "png", "-f", "image2pipe", "-"]
    try:
        data = FC._run(cmd, "take frames from", path)
    except FC.FilmCutError as e:
        raise ArtError(str(e)) from None
    Image = _pil()
    frames = [Image.open(io.BytesIO(b)).convert("RGBA") for b in split_pngs(data)]
    if not frames:
        raise ArtError("There are no frames in %s from %s." % (_name(path), FC.format_time(start)))
    notes = []
    if cut == "key":
        frames = [Image.fromarray(key_out(f, keyrgb, tolerance, softness), "RGBA") for f in frames]
    elif cut == "alpha" and all(f.getchannel("A").getextrema()[0] == 255 for f in frames):
        notes.append("This video carries no see-through parts; try a key colour instead.")
    _check_frames(frames, _name(path))
    s = Sprite(frames, fps=fps, loop=bool(loop),
               source="%s, %s for %gs" % (_name(path), FC.format_time(start), length), notes=notes)
    return s


# ---- one call for every kind -------------------------------------------------------------
def guess_kind(path):
    ext = os.path.splitext(path or "")[1].lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in ANIM_EXT:
        return "gif"
    if ext in (".png", ".webp"):
        try:
            img = _open(path)
            if getattr(img, "n_frames", 1) > 1:
                return "gif"
        except ArtError:
            pass
    if ext in PICTURE_EXT and len(numbered_run(path)) > 1:
        return "numbered"
    return "picture"


def import_art(kind, path, **opts):
    """A :class:`Sprite` from ``path`` read as ``kind`` (:data:`KINDS`), with that kind's
    options (frame sizes for ``grid``, start and length and the cut for ``video``...)."""
    if kind == "picture":
        return from_picture(path)
    if kind == "numbered":
        return from_numbered(path, **_pick(opts, "fps", "loop"))
    if kind == "gif":
        return from_gif(path)
    if kind == "grid":
        return from_sheet_grid(path, **_pick(opts, "frame_w", "frame_h", "margin", "spacing", "count", "fps",
                                             "loop"))
    if kind == "auto":
        return from_sheet_auto(path, **_pick(opts, "tolerance", "min_gap", "fps", "loop"))
    if kind == "video":
        return from_video(path, **_pick(opts, "start", "length", "fps", "cut", "key", "tolerance", "softness",
                                        "width", "loop"))
    raise ArtError("Art comes in as one of: %s." % ", ".join(KINDS))


def _pick(opts, *names):
    return {k: opts[k] for k in names if k in opts and opts[k] not in (None, "")}


# ---- into the mode -----------------------------------------------------------------------
def sheet_layout(n, fw, fh):
    """Columns and rows of a sheet of ``n`` frames: as square as it goes, no side over
    :data:`MAX_SHEET`."""
    cols = max(1, min(n, MAX_SHEET // fw, int(math.ceil(math.sqrt(n * fh / float(fw))))))
    rows = int(math.ceil(n / float(cols)))
    if rows * fh > MAX_SHEET:
        raise ArtError("%d frames of %dx%d do not fit in one sheet; bring in fewer or smaller frames."
                       % (n, fw, fh))
    return cols, rows


def make_sheet(frames):
    Image = _pil()
    fw, fh = frames[0].size
    cols, rows = sheet_layout(len(frames), fw, fh)
    sheet = Image.new("RGBA", (cols * fw, rows * fh), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        sheet.paste(f, ((i % cols) * fw, (i // cols) * fh))
    return sheet


def content_box(frames):
    """The box (x, y, w, h) every frame's visible pixels sit in, or the whole frame."""
    box = None
    for f in frames:
        b = f.getchannel("A").getbbox()
        if b:
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    fw, fh = frames[0].size
    if box is None:
        return (0, 0, fw, fh)
    return (box[0], box[1], box[2] - box[0], box[3] - box[1])


def default_hitbox(frames, anchor):
    """A box round what the frames show, relative to the anchor point."""
    fw, fh = frames[0].size
    x, y, w, h = content_box(frames)
    ax, ay = anchor[0] * fw, anchor[1] * fh
    return {"shape": "box", "x": round(x - ax, 1), "y": round(y - ay, 1), "w": max(1, w), "h": max(1, h)}


def picture_entry(sid, sprite, anchor=None, hitbox=None, file=None):
    fw, fh = sprite.size
    anchor = list(anchor) if anchor else [0.5, 0.5]
    p = {"id": sid, "file": file or "%s/%s.png" % (ART_DIR, sid)}
    n = len(sprite.frames)
    if n > 1:
        p.update(frame_w=fw, frame_h=fh, frames=n)
    p["anchor"] = [round(float(anchor[0]), 4), round(float(anchor[1]), 4)]
    p["hitbox"] = hitbox or default_hitbox(sprite.frames, p["anchor"])
    if n > 1:
        p["animations"] = [{"id": "play", "frames": list(range(n)), "fps": round(float(sprite.fps), 3),
                            "loop": bool(sprite.loop)}]
    return p


def valid_id(text):
    """A picture id from a file name: lower case, ``[a-z][a-z0-9_]*``, up to 40."""
    t = re.sub(r"[^a-z0-9_]+", "_", (text or "").lower()).strip("_")
    t = re.sub(r"_+", "_", t)
    if not t or not t[0].isalpha():
        t = "art_" + t if t else "art"
    return t[:40].rstrip("_")


def free_id(doc, want):
    taken = {p.get("id") for p in (doc.get("assets") or {}).get("pictures") or []}
    sid = valid_id(want)
    if sid not in taken:
        return sid
    n = 2
    while ("%s_%d" % (sid[:36], n)) in taken:
        n += 1
    return "%s_%d" % (sid[:36], n)


def save_sprite(mode_dir, doc, sid, sprite, anchor=None, hitbox=None):
    """Write ``sprite`` as ``art/<sid>.png`` in ``mode_dir`` and put its picture entry in
    ``doc`` (replacing one of that id, keeping its anchor, hit box and animations' other
    settings when the frame size is unchanged). Returns the entry. The document itself
    is not written; the caller saves it."""
    sid = valid_id(sid)
    pics = doc.setdefault("assets", {}).setdefault("pictures", [])
    old = next((p for p in pics if p.get("id") == sid), None)
    if old is not None and anchor is None and _frame_size(old, mode_dir) == sprite.size:
        anchor, hitbox = old.get("anchor"), hitbox or old.get("hitbox")
    entry = picture_entry(sid, sprite, anchor, hitbox)
    path = os.path.join(mode_dir, *entry["file"].split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet = make_sheet(sprite.frames)
    tmp = path + ".part"
    sheet.save(tmp, format="PNG", optimize=False, compress_level=6)
    os.replace(tmp, path)
    if old is not None:
        pics[pics.index(old)] = entry
    else:
        pics.append(entry)
    return entry


def _frame_size(p, mode_dir):
    if p.get("frame_w") and p.get("frame_h"):
        return (int(p["frame_w"]), int(p["frame_h"]))
    try:
        return _open(picture_path(mode_dir, p)).size
    except ArtError:
        return None


def picture_path(mode_dir, picture):
    return os.path.join(mode_dir, *str(picture.get("file") or "").split("/"))


def frame_boxes(picture, sheet_size):
    """The (x, y, w, h) of each frame of ``picture`` in its sheet of ``sheet_size``."""
    W, H = sheet_size
    fw, fh = int(picture.get("frame_w") or W), int(picture.get("frame_h") or H)
    n = int(picture.get("frames") or 1)
    cols = max(1, W // fw)
    boxes = [((i % cols) * fw, (i // cols) * fh, fw, fh) for i in range(n)]
    for i, (x, y, w, h) in enumerate(boxes):
        if x + w > W or y + h > H:
            raise ArtError("Picture \"%s\": frame %d is outside its %dx%d sheet." % (picture.get("id"), i, W, H))
    return boxes


def load_frames(mode_dir, picture):
    """The frames of a picture entry, read from its sheet."""
    img = _rgba(_open(picture_path(mode_dir, picture)))
    return _crop(img, frame_boxes(picture, img.size))


def replace_frame(mode_dir, picture, index, frame):
    """Write one frame back into a picture's sheet (a touch-up)."""
    path = picture_path(mode_dir, picture)
    img = _rgba(_open(path)).copy()
    boxes = frame_boxes(picture, img.size)
    if not (0 <= index < len(boxes)):
        raise ArtError("Picture \"%s\" has no frame %d." % (picture.get("id"), index + 1))
    x, y, w, h = boxes[index]
    frame = _rgba(frame)
    if frame.size != (w, h):
        raise ArtError("A touched-up frame stays %dx%d." % (w, h))
    img.paste(frame, (x, y))
    tmp = path + ".part"
    img.save(tmp, format="PNG")
    os.replace(tmp, path)


# ---- backgrounds -------------------------------------------------------------------------
BACKGROUND_KINDS = ("still", "tiled", "scrolling")


def layer(picture, kind="still", speed=0.0, y=0.0, alpha=None):
    """One background layer: ``still`` (drawn once, not moving), ``tiled`` (repeated across
    the stage, not moving), ``scrolling`` (tiled and moving at ``speed`` px a second;
    minus is to the left). Several layers, each at its own speed, give depth."""
    if kind not in BACKGROUND_KINDS:
        raise ArtError("A background is still, tiled or scrolling.")
    out = {"picture": picture, "speed": float(speed) if kind == "scrolling" else 0.0, "y": float(y)}
    if kind != "still":
        out["tile"] = True
    if alpha is not None and float(alpha) < 1:
        out["alpha"] = round(float(alpha), 3)
    return out


def layer_kind(lay):
    if not lay.get("tile"):
        return "still"
    return "scrolling" if float(lay.get("speed") or 0) else "tiled"


def set_backgrounds(doc, phase_id, layers):
    """Set a phase's background layers, back to front (up to 8)."""
    ph = next((p for p in doc.get("phases") or [] if p.get("id") == phase_id), None)
    if ph is None:
        raise ArtError("There is no phase \"%s\"." % phase_id)
    if len(layers) > 8:
        raise ArtError("A phase has up to 8 background layers.")
    if layers:
        ph["background"] = list(layers)
    else:
        ph.pop("background", None)
    return ph
