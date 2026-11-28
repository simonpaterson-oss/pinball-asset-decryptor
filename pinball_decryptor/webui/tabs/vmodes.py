"""Video modes tab (PAD-1658): a video mode's pictures, brought in and packed for the machine.

The first page of the video mode maker (docs/plans/video_mode_maker.md): the project's video modes
(``<project>/modes/<slug>/video_mode.json``), and for the one picked its **pictures**: art brought in from a
picture, a numbered run of PNGs, a GIF, a sprite sheet (sliced by a grid or at its empty gutters) or a stretch of
video (cut out with a colour key or the video's own alpha), each a named sprite with frames, a frame rate, loop or
once, an anchor point and a hit box; its phases' **backgrounds** (still, tiled and scrolling layers, each with its
own speed); a frame opened in the pixel editor for touch-up; and **Pack for the machine**, which trims, packs and
premultiplies the pictures into atlases and reports what the mode costs against the machine's budgets before
anything is written. The editor proper (stage, layers, inspector) is PAD-1661's.

The rules live in :mod:`...core.video_mode.art` and :mod:`...core.video_mode.pack`; this is the page.
"""

import os
import shutil
import threading

from .. import compat
from .base import TabService, rpc

INTRO = ("Small games played on the screen with the flipper buttons and Action while the ball is held. Bring in "
         "their pictures here and see what they cost on the machine.")
ART_TYPES = [("Pictures, GIFs and videos", "*.png *.jpg *.jpeg *.bmp *.gif *.apng *.webp *.tif *.tiff *.mp4 *.mov "
              "*.m4v *.mkv *.avi *.webm *.wmv *.mpg *.mpeg"), ("All files", "*.*")]
TOUCH_MAX = 512          # the pixel editor's canvas: a frame up to this a side


def _mods():
    from ...core.video_mode import art as A, budgets as B, document as D, pack as P
    return A, B, D, P


class VideoModesTab(TabService):
    ns = "vmodes"
    key = "Video Modes"
    label = "Video modes"
    group = "Make"
    icon = "play"

    def __init__(self, window):
        super().__init__(window)
        self._project = ""
        self._slug = ""
        self._doc = None
        self._draft = None            # (path, kind, opts, Sprite)
        self._draft_id = 0
        self._pack_id = 0
        self._tmp = None
        self.set(project="", available=False, why="", intro=INTRO, modes=[], slug="", title="", problems=[],
                 pictures=[], phases=[], draft=None, machine="spike2", machines=[], report=None, packing=False,
                 written="", kinds=[], bg_kinds=[], running=False, stage_bg="#000000")

    # -- the project -------------------------------------------------------------------------------------------
    def _folder(self):
        var = getattr(self.window, "write_assets_var", None) or getattr(self.window, "extract_output_var", None)
        return ((var.get() if var is not None else "") or "").strip()

    def on_project(self, folder):
        if self.shown():
            self.refresh()

    def on_running(self, running, mode):
        self.set(running=bool(running))

    def on_show(self):
        if self._folder() != self._project or self._doc is None:
            self.refresh()

    def _modes_dir(self):
        return os.path.join(self._project, "modes")

    def _mode_dir(self, slug=None):
        return os.path.join(self._modes_dir(), slug or self._slug)

    def _doc_path(self, slug=None):
        _, _, D, _ = _mods()
        return os.path.join(self._mode_dir(slug), D.FILE_NAME)

    def _tmpdir(self):
        if not self._tmp or not os.path.isdir(self._tmp):
            from ...core import pad_temp
            self._tmp = pad_temp.mkdtemp(prefix="pad_vmodes_")
        return self._tmp

    @rpc
    def refresh(self):
        A, B, D, _ = _mods()
        folder = self._folder()
        self._project = folder
        self.set(kinds=[{"key": k, "label": A.KIND_LABELS[k]} for k in A.KINDS],
                 bg_kinds=list(A.BACKGROUND_KINDS),
                 machines=[{"key": k, "label": B.MACHINES[k]["label"]} for k in B.ORDER])
        if not folder or not os.path.isdir(folder):
            self._doc = None
            self.set(project="", available=False, modes=[], pictures=[], phases=[], slug="",
                     why="Set the project folder on the Extract tab first: these games are kept in the project.")
            return False
        modes = []
        try:
            names = sorted(os.listdir(self._modes_dir()))
        except OSError:
            names = []
        for slug in names:
            p = os.path.join(self._modes_dir(), slug, D.FILE_NAME)
            if not os.path.isfile(p):
                continue
            try:
                doc = D.load(p)
                modes.append({"slug": slug, "title": doc.get("title") or slug,
                              "pictures": len((doc.get("assets") or {}).get("pictures") or []), "broken": ""})
            except (OSError, ValueError) as e:
                modes.append({"slug": slug, "title": slug, "pictures": 0, "broken": str(e)[:300]})
        self.set(project=folder, available=True, why="", modes=modes)
        slug = self._slug if any(m["slug"] == self._slug for m in modes) else (modes[0]["slug"] if modes else "")
        self._open(slug)
        return True

    def _open(self, slug):
        _, _, D, _ = _mods()
        self._slug = slug
        self._doc = None
        problems = []
        if slug:
            try:
                self._doc = D.load(self._doc_path())
            except (OSError, ValueError) as e:
                problems = list(getattr(e, "problems", None) or [str(e)])
        self.set(slug=slug, title=(self._doc or {}).get("title", ""), problems=problems, report=None, written="")
        self._paint()

    @rpc
    def select(self, slug):
        self._draft = None
        self.set(draft=None)
        self._open(str(slug or ""))
        return True

    @rpc
    def new_mode(self, title):
        _, _, D, _ = _mods()
        import re
        title = (title or "").strip() or "My video mode"
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "video-mode"
        if not slug[0].isalnum():
            slug = "vm-" + slug
        base, n = slug, 2
        while os.path.exists(self._mode_dir(slug)):
            slug = "%s-%d" % (base[:44], n)
            n += 1
        os.makedirs(self._mode_dir(slug), exist_ok=True)
        D.save(self._doc_path(slug), D.new(slug, title))
        self._slug = slug
        self.refresh()
        return slug

    # -- the document ------------------------------------------------------------------------------------------
    def _save(self, what=""):
        _, _, D, _ = _mods()
        try:
            D.save(self._doc_path(), self._doc)
        except ValueError as e:
            # the change is not kept: read the file back as it is on disk
            self._open(self._slug)
            compat.messagebox.showerror("Video modes", "Not saved: %s" % e)
            return False
        self.set(report=None, written="")
        self._paint()
        return True

    def _picture(self, pid):
        for p in (self._doc or {}).get("assets", {}).get("pictures") or []:
            if p.get("id") == pid:
                return p
        return None

    def _uses(self, pid):
        out = []
        for t in self._doc.get("things") or []:
            if t.get("picture") == pid:
                out.append('thing "%s"' % t.get("id"))
        for ph in self._doc.get("phases") or []:
            if any(lay.get("picture") == pid for lay in ph.get("background") or []):
                out.append('phase "%s" background' % ph.get("id"))
        return out

    def _paint(self):
        A, _, _, _ = _mods()
        doc = self._doc
        if doc is None:
            self.set(pictures=[], phases=[])
            return
        md = self._mode_dir()
        pics = []
        for p in (doc.get("assets") or {}).get("pictures") or []:
            path = A.picture_path(md, p)
            sw = sh = 0
            try:
                from PIL import Image
                with Image.open(path) as im:
                    sw, sh = im.size
                missing = False
                mtime = int(os.path.getmtime(path))
            except OSError:
                missing, mtime = True, 0
            fw, fh = int(p.get("frame_w") or sw), int(p.get("frame_h") or sh)
            anim = (p.get("animations") or [{}])[0]
            pics.append({"id": p["id"], "path": path, "v": mtime, "missing": missing, "sheet_w": sw, "sheet_h": sh,
                         "fw": fw, "fh": fh, "cols": max(1, sw // fw) if fw else 1, "frames": int(p.get("frames") or 1),
                         "fps": anim.get("fps", A.DEFAULT_FPS), "loop": anim.get("loop", True),
                         "anim": anim.get("id", ""), "anim_frames": anim.get("frames") or [0],
                         "anchor": p.get("anchor") or [0.5, 0.5], "hitbox": p.get("hitbox"),
                         "uses": self._uses(p["id"]), "file": p.get("file")})
        phases = []
        for ph in doc.get("phases") or []:
            phases.append({"id": ph["id"], "title": ph.get("title") or ph["id"], "kind": ph.get("kind"),
                           "layers": [dict(lay, kind=A.layer_kind(lay)) for lay in ph.get("background") or []]})
        self.set(pictures=pics, phases=phases, title=doc.get("title", ""),
                 stage_bg=(doc.get("stage") or {}).get("background") or "#000000")

    # -- bringing art in ---------------------------------------------------------------------------------------
    @rpc
    def pick(self):
        """Choose a file; it opens as a draft with its kind guessed and a preview."""
        A, _, _, _ = _mods()
        if self._doc is None:
            return False
        start = self.window.last_browse_dir("vmodes") if hasattr(self.window, "last_browse_dir") else ""
        got = compat.filedialog.askopenfilename(title="Bring art into the video mode", filetypes=ART_TYPES,
                                                initialdir=start if start and os.path.isdir(start) else "")
        path = got[0] if isinstance(got, (list, tuple)) and got else got
        if not path:
            return False
        path = os.path.normpath(path)
        if hasattr(self.window, "remember_browse_dir"):
            self.window.remember_browse_dir("vmodes", os.path.dirname(path))
        return self.draft(path, A.guess_kind(path), {})

    @rpc
    def draft(self, path, kind, opts=None):
        """(Re)read ``path`` as ``kind`` with ``opts``; the preview lands in ``draft`` (a worker: a video takes a
        moment)."""
        A, _, _, _ = _mods()
        opts = dict(opts or {})
        self._draft_id += 1
        did = self._draft_id
        name = os.path.splitext(os.path.basename(path))[0]
        if A.numbered_run(path)[1:] and kind == "numbered":
            import re
            name = re.sub(r"[_\-. ]*\d+$", "", name) or name
        base = {"path": path, "name": os.path.basename(path), "kind": kind, "opts": opts, "busy": True, "error": "",
                "id": opts.pop("_id", None) or A.free_id(self._doc or {}, name)}
        if kind == "video":
            base["opts"] = dict({"start": "0:00", "length": "2", "fps": 12, "cut": "key", "key": "#00ff00",
                                 "tolerance": 0.18}, **opts)
        elif kind == "grid":
            base["opts"] = dict({"frame_w": 64, "frame_h": 64, "margin": 0, "spacing": 0}, **opts)
        self.set(draft=base)
        tmp = self._tmpdir()

        def work():
            out = dict(base)
            try:
                sp = A.import_art(kind, path, **self._num_opts(base["opts"]))
                sheet = A.make_sheet(sp.frames)
                f = os.path.join(tmp, "draft_%d.png" % did)
                sheet.save(f, format="PNG", compress_level=1)
                fw, fh = sp.size
                out.update(busy=False, sheet=f, sheet_w=sheet.width, sheet_h=sheet.height, fw=fw, fh=fh,
                           cols=sheet.width // fw, frames=len(sp.frames), fps=sp.fps, loop=sp.loop,
                           source=sp.source, notes=sp.notes)
                if kind == "grid" or kind == "auto":
                    from PIL import Image
                    with Image.open(path) as im:
                        out.update(src_w=im.width, src_h=im.height)
                draft = (path, kind, base["opts"], sp)
            except Exception as e:                       # noqa: BLE001 - said in the dialog
                out.update(busy=False, error=str(e))
                draft = None
            self.ctx.loop.post(lambda: self._draft_done(did, out, draft))
        threading.Thread(target=work, daemon=True, name="vmodes-draft").start()
        return True

    @staticmethod
    def _num_opts(opts):
        out = {}
        for k, v in opts.items():
            if k in ("frame_w", "frame_h", "margin", "spacing", "count", "min_gap", "width"):
                out[k] = int(float(v)) if str(v).strip() else None
            elif k in ("fps", "tolerance", "softness"):
                out[k] = float(v)
            elif k == "loop":
                out[k] = bool(v)
            else:
                out[k] = v
        return out

    def _draft_done(self, did, out, draft):
        if did != self._draft_id:
            return
        self._draft = draft
        self.set(draft=out)

    @rpc
    def draft_close(self):
        self._draft_id += 1
        self._draft = None
        self.set(draft=None)
        return True

    @rpc
    def add(self, pid, fps=None, loop=None):
        """The draft into the mode as picture ``pid`` (a new id, or one it replaces)."""
        A, _, _, _ = _mods()
        if not self._draft or self._doc is None:
            return False
        _, _, _, sp = self._draft
        if fps is not None:
            sp.fps = float(fps)
        if loop is not None:
            sp.loop = bool(loop)
        pid = A.valid_id(pid)
        try:
            A.save_sprite(self._mode_dir(), self._doc, pid, sp)
        except A.ArtError as e:
            compat.messagebox.showerror("Video modes", str(e))
            return False
        if self._save():
            self._draft = None
            self.set(draft=None)
            return pid
        return False

    # -- a picture's settings ----------------------------------------------------------------------------------
    @rpc
    def set_picture(self, pid, changes):
        A, _, _, _ = _mods()
        p = self._picture(pid)
        if p is None:
            return False
        ch = dict(changes or {})
        if "anchor" in ch:
            ax, ay = (float(v) for v in ch["anchor"])
            p["anchor"] = [round(min(1, max(0, ax)), 4), round(min(1, max(0, ay)), 4)]
        if "hitbox" in ch:
            hb = ch["hitbox"]
            if hb is None:
                p.pop("hitbox", None)
            elif hb.get("shape") == "circle":
                p["hitbox"] = {"shape": "circle", "x": round(float(hb.get("x", 0)), 1),
                               "y": round(float(hb.get("y", 0)), 1), "r": max(1, round(float(hb.get("r", 1)), 1))}
            else:
                p["hitbox"] = {"shape": "box", "x": round(float(hb.get("x", 0)), 1),
                               "y": round(float(hb.get("y", 0)), 1), "w": max(1, round(float(hb.get("w", 1)), 1)),
                               "h": max(1, round(float(hb.get("h", 1)), 1))}
        if ("fps" in ch or "loop" in ch) and p.get("animations"):
            a = p["animations"][0]
            if "fps" in ch:
                a["fps"] = round(min(60.0, max(0.1, float(ch["fps"]))), 3)
            if "loop" in ch:
                a["loop"] = bool(ch["loop"])
        if "id" in ch and ch["id"] != pid:
            new = A.valid_id(ch["id"])
            if self._picture(new) is not None:
                compat.messagebox.showerror("Video modes", 'There is a picture "%s" already.' % new)
                return False
            for t in self._doc.get("things") or []:
                if t.get("picture") == pid:
                    t["picture"] = new
            for ph in self._doc.get("phases") or []:
                for lay in ph.get("background") or []:
                    if lay.get("picture") == pid:
                        lay["picture"] = new
            p["id"] = new
        return self._save()

    @rpc
    def remove_picture(self, pid):
        p = self._picture(pid)
        if p is None:
            return False
        uses = self._uses(pid)
        if uses:
            compat.messagebox.showerror("Video modes", 'Picture "%s" is used by %s; take it off there first.'
                                        % (pid, ", ".join(uses)))
            return False
        self._doc["assets"]["pictures"].remove(p)
        return self._save()

    # -- backgrounds -------------------------------------------------------------------------------------------
    @rpc
    def set_layers(self, phase_id, layers):
        """A phase's background layers, back to front: [{picture, kind, speed, y, alpha}]."""
        A, _, _, _ = _mods()
        if self._doc is None:
            return False
        try:
            out = [A.layer(lay["picture"], lay.get("kind", "still"), float(lay.get("speed") or 0),
                           float(lay.get("y") or 0), lay.get("alpha")) for lay in layers or []]
            A.set_backgrounds(self._doc, phase_id, out)
        except (A.ArtError, KeyError, ValueError) as e:
            compat.messagebox.showerror("Video modes", str(e))
            return False
        return self._save()

    # -- touch-up in the pixel editor --------------------------------------------------------------------------
    def _frame_ref(self, rel):
        pid, _, idx = str(rel).rpartition("#")
        return self._picture(pid), pid, int(idx or 0)

    @rpc
    def frame_open(self, rel):
        A, _, _, _ = _mods()
        import base64
        p, pid, idx = self._frame_ref(rel)
        if p is None:
            return None
        frames = A.load_frames(self._mode_dir(), p)
        f = frames[idx]
        if max(f.size) > TOUCH_MAX:
            compat.messagebox.showinfo("Video modes", "The pixel editor opens frames up to %d pixels a side; "
                                       "this one is %dx%d." % (TOUCH_MAX, f.width, f.height))
            return None
        d = os.path.join(self._tmpdir(), "touch_%s" % pid)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        listed = []
        for i, fr in enumerate(frames[:600]):
            fp = os.path.join(d, "%04d.png" % i)
            fr.save(fp, compress_level=1)
            listed.append({"rel": "%s#%d" % (pid, i), "name": "Frame %d" % (i + 1), "path": fp})
        data = base64.b64encode(f.tobytes()).decode("ascii")
        return {"rel": rel, "name": '%s, frame %d' % (pid, idx + 1), "w": f.width, "h": f.height, "data": data,
                "orig": data, "edited": False, "budget": None, "cell": None, "ring": False, "ringmap": None,
                "frames": listed if len(listed) > 1 else [], "index": idx}

    @rpc
    def frame_save(self, rel, w, h, data):
        A, _, _, _ = _mods()
        from .pixel_edit import decode_rgba
        p, pid, idx = self._frame_ref(rel)
        if p is None:
            return {"ok": False, "msg": "That picture is gone."}
        try:
            A.replace_frame(self._mode_dir(), p, idx, decode_rgba(int(w), int(h), data))
        except (A.ArtError, ValueError) as e:
            return {"ok": False, "msg": str(e)}
        self.set(report=None, written="")
        self._paint()
        return {"ok": True, "same": False, "msg": "Frame %d of %s saved." % (idx + 1, pid), "path": ""}

    # -- packing -----------------------------------------------------------------------------------------------
    @rpc
    def set_machine(self, key):
        _, B, _, _ = _mods()
        if key in B.MACHINES:
            self.set(machine=key, report=None, written="")
        return True

    @rpc
    def pack(self, write=False):
        """Pack for the machine picked and report the cost; ``write``: also write it for the card (refused over
        budget, naming the sprites to shrink)."""
        _, _, _, P = _mods()
        if self._doc is None:
            return False
        self._pack_id += 1
        pid = self._pack_id
        machine = self.get("machine") or "spike2"
        md, doc = self._mode_dir(), self._doc
        self.set(packing=True, written="")

        def work():
            written, report = "", None
            try:
                if write:
                    try:
                        pk = P.for_card(md, doc, machine)
                        report = pk.report
                        written = "Packed into %s." % os.path.join("build", pk.machine["backend"])
                    except P.OverBudget as e:
                        report = e.report
                        written = "Not written: the mode is over what the machine takes."
                else:
                    report = P.pack(md, doc, machine).report
            except Exception as e:                       # noqa: BLE001 - said on the page
                report = {"ok": False, "problems": ["The pack failed: %s" % e], "sprites": [], "atlases": []}
            self.ctx.loop.post(lambda: self._pack_done(pid, report, written))
        threading.Thread(target=work, daemon=True, name="vmodes-pack").start()
        return True

    def _pack_done(self, pid, report, written):
        if pid != self._pack_id:
            return
        self.set(packing=False, report=report, written=written)


TAB = VideoModesTab
