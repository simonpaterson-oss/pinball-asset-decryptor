"""Video modes tab (PAD-1658): a video mode's pictures, brought in and packed for the machine.

The first page of the video mode maker (docs/plans/video_mode_maker.md): the project's video modes
(``<project>/modes/<slug>/video_mode.json``), and for the one picked its **pictures**: art brought in from a
picture, a numbered run of PNGs, a GIF, a sprite sheet (sliced by a grid or at its empty gutters) or a stretch of
video (cut out with a colour key or the video's own alpha), each a named sprite with frames, a frame rate, loop or
once, an anchor point and a hit box; its phases' **backgrounds** (still, tiled and scrolling layers, each with its
own speed); a frame opened in the pixel editor for touch-up; and **Pack for the machine**, which trims, packs and
premultiplies the pictures into atlases and reports what the mode costs against the machine's budgets before
anything is written. The editor proper (stage, layers, inspector) is PAD-1661's.

**Play** (PAD-1659) opens the player (static/js/tabs/vmodes_play.js): the machine's own engine, built for the browser
(core/video_mode/engine/vm_engine.wasm), plays the mode at 60 steps a second and WebGL draws its draw list. This
side compiles the document (:meth:`play_open`) and keeps the input recordings (``<mode>/replays/``).

The rules live in :mod:`...core.video_mode.art` and :mod:`...core.video_mode.pack`; this is the page.
"""

import base64
import copy
import json
import os
import re
import shutil
import threading
import time

from .. import compat
from .base import TabService, rpc
from ...core.video_mode import sound as SND

INTRO = ("Small games played on the screen with the flipper buttons and Action while the ball is held. Bring in "
         "their pictures here and see what they cost on the machine.")
#: PAD-1667: the sound files a video mode takes (Web Audio plays them in the app; the build makes the machine's WAVs)
SOUND_TYPES = [("Sounds", "*.wav *.ogg *.mp3 *.flac *.m4a *.aac *.opus"), ("All files", "*.*")]
#: a sound longer than this comes in as music, a shorter one as an effect
MUSIC_FROM_S = 8.0
ART_TYPES = [("Pictures, GIFs and videos", "*.png *.jpg *.jpeg *.bmp *.gif *.apng *.webp *.tif *.tiff *.mp4 *.mov "
              "*.m4v *.mkv *.avi *.webm *.wmv *.mpg *.mpeg"), ("All files", "*.*")]
REPLAYS = "replays"       # a mode's input recordings (PAD-1659)
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
        self._peaks = {}                  # (path, mtime) -> {"seconds", "peaks"}
        self._beat_busy = set()
        self.set(project="", available=False, why="", intro=INTRO, modes=[], slug="", title="", problems=[],
                 pictures=[], phases=[], draft=None, machine="spike2", machines=[], report=None, packing=False,
                 written="", kinds=[], bg_kinds=[], running=False, stage_bg="#000000", play_mem=None, history=None,
                 sounds=[], cues=[], cue_on=[], sound_plan=None, music_phases=[], peaks={}, beat_busy=[])
        self._play_id = 0
        self._hist = None             # the open mode's undo history (core/video_mode/history.py, PAD-1661)
        self._saved = None            # the document as last written, what the next step is measured from

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
        self._hist_open()
        self._paint()

    # -- the undo history: every change to the document is one step (PAD-1661) --------------------------------
    def _hist_open(self):
        from ...core.video_mode import history as H
        self._hist = H.History(self._mode_dir()).open(self._doc) if self._doc is not None else None
        self._saved = copy.deepcopy(self._doc)
        self._hist_state()

    def _hist_state(self):
        self.set(history=self._hist.state() if self._hist else None)

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
        if self._hist is not None and self._saved is not None:
            self._hist.push(what or "Change", self._saved, self._doc)
        self._saved = copy.deepcopy(self._doc)
        self._hist_state()
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
        self._paint_sounds()

    # -- sounds (PAD-1667) -------------------------------------------------------------------------------------
    def _sound(self, sid):
        for x in (self._doc or {}).get("assets", {}).get("sounds") or []:
            if x.get("id") == sid:
                return x
        return None

    def _paint_sounds(self):
        """The Sounds card: each sound with its settings, what plays it, its file's waveform (made off the page's
        thread, once per file), the cues, the music of each phase, and how it all goes on the machine."""
        from ...core.video_mode import compiler as C
        doc, md = self._doc, self._mode_dir()
        plan = SND.machine_plan(doc, self.get("machine") or SND.DEFAULT)
        on_machine = {r["id"]: r for r in plan["calls"] + plan["beds"] + ([plan["music"]] if plan["music"] else [])}
        duck = SND.ducks(doc)
        rows, want = [], []
        for n, x in enumerate(SND.sounds(doc)):
            path = SND.file_of(md, x)
            missing = not path
            if missing:                                 # its placeholder: heard, and its waveform drawn, as it plays
                path = self._placeholder_sound(x, n)
            mtime = int(os.path.getmtime(path)) if path else 0
            key = "%s|%d" % (path, mtime) if path else ""
            if key and key not in self._peaks:
                want.append((key, path))
            sid = x.get("id")
            phases = [ph.get("title") or ph.get("id") for ph in doc.get("phases") or [] if SND.phase_music(ph) == sid]
            cues = [c.get("on") for c in doc.get("cues") or [] if c.get("sound") == sid]
            m = on_machine.get(sid)
            rows.append({"id": sid, "role": x.get("role"), "file": x.get("file", ""), "path": path, "v": mtime,
                         "missing": missing, "peaks_key": key, "volume": float(x.get("volume", 1.0)),
                         "loop": bool(x.get("loop", False)), "loop_start_s": x.get("loop_start_s"),
                         "fade_s": SND.fade_s(x), "has_fade": "fade_s" in x, "grid": SND.sound_grid(x),
                         "tempo_bpm": x.get("tempo_bpm"), "beat_offset_s": x.get("beat_offset_s"),
                         "beats_per_bar": x.get("beats_per_bar"), "phases": phases, "cues": cues,
                         "duck": bool(duck.get(sid)), "machine": m["name"] if m else "",
                         "priority": m.get("priority") if m else None, "index": n})
        music_phases = [{"id": ph.get("id"), "title": ph.get("title") or ph.get("id"), "kind": ph.get("kind"),
                         "music": SND.phase_music(ph) or "", "from_settings": not ph.get("music") and bool(SND.phase_music(ph))}
                        for ph in doc.get("phases") or []]
        cues = [{"on": c.get("on"), "sound": c.get("sound"), "duck_music": bool(c.get("duck_music"))}
                for c in doc.get("cues") or []]
        self.set(sounds=rows, cues=cues, cue_on=list(C.CUE_ON), sound_plan=plan, music_phases=music_phases)
        if want:
            def work(todo=tuple(want)):
                got = {}
                for key, path in todo:
                    try:
                        got[key] = SND.peaks(path, 600)
                    except (ValueError, OSError, Exception):    # noqa: BLE001 - no waveform, the row says so
                        got[key] = {"seconds": 0.0, "peaks": [], "error": True}

                def done():
                    self._peaks.update(got)
                    self.set(peaks={k: v for k, v in self._peaks.items()})
                self.ctx.loop.post(done)
            for key, _p in want:
                self._peaks.setdefault(key, None)
            threading.Thread(target=work, daemon=True, name="vmodes-peaks").start()

    @rpc
    def add_sound(self):
        """Choose a sound file: it is copied into the mode's sound/ folder and added (music when it is long)."""
        _, _, D, _ = _mods()
        if self._doc is None:
            return False
        start = self.window.last_browse_dir("vmodes_sound") if hasattr(self.window, "last_browse_dir") else ""
        got = compat.filedialog.askopenfilename(title="Bring a sound into the video mode", filetypes=SOUND_TYPES,
                                                initialdir=start if start and os.path.isdir(start) else "")
        path = got[0] if isinstance(got, (list, tuple)) and got else got
        if not path:
            return False
        return self.add_sound_file(os.path.normpath(path))

    @rpc
    def add_sound_file(self, path):
        if self._doc is None or not os.path.isfile(str(path or "")):
            return False
        if hasattr(self.window, "remember_browse_dir"):
            self.window.remember_browse_dir("vmodes_sound", os.path.dirname(path))
        secs = SND.seconds(path)
        if secs <= 0:
            compat.messagebox.showerror("Video modes", "%s does not read as a sound." % os.path.basename(path))
            return False
        base = os.path.basename(path)
        stem = re.sub(r"[^0-9A-Za-z_.-]+", "_", os.path.splitext(base)[0])[:40] or "sound"
        ext = os.path.splitext(base)[1].lower()
        folder = os.path.join(self._mode_dir(), "sound")
        os.makedirs(folder, exist_ok=True)
        name, k = stem + ext, 2
        while os.path.exists(os.path.join(folder, name)):
            name = "%s_%d%s" % (stem, k, ext)
            k += 1
        shutil.copyfile(path, os.path.join(folder, name))
        sounds = self._doc.setdefault("assets", {}).setdefault("sounds", [])
        taken = {x.get("id") for x in sounds}
        sid = re.sub(r"[^a-z0-9_]+", "_", stem.lower()).strip("_") or "sound"
        if not sid[0].isalpha():
            sid = "s_" + sid
        sid, base_id, k = sid[:40], sid[:36], 2
        while sid in taken:
            sid = "%s_%d" % (base_id, k)
            k += 1
        row = {"id": sid, "file": "sound/" + name, "role": "music" if secs >= MUSIC_FROM_S else "effect", "volume": 1.0}
        if row["role"] == "music":
            row["loop"] = True
        sounds.append(row)
        return self._save("Bring a sound in")

    @rpc
    def set_sound(self, sid, changes):
        """A sound's settings: role, volume, loop, loop_start_s, fade_s, tempo_bpm, beat_offset_s, beats_per_bar
        (None takes a field off), or a new id (every use follows)."""
        x = self._sound(sid)
        if x is None:
            return False
        ch = dict(changes or {})

        def num(k, lo, hi, nd=3):
            v = ch[k]
            if v is None or v == "":
                x.pop(k, None)
                return
            x[k] = round(min(hi, max(lo, float(v))), nd)
        if "role" in ch and ch["role"] in ("music", "effect", "callout"):
            x["role"] = ch["role"]
            if x["role"] != "music":
                for k in ("fade_s", "tempo_bpm", "beat_offset_s", "beats_per_bar"):
                    x.pop(k, None)
        try:
            if "volume" in ch:
                num("volume", 0, 1)
            if "loop" in ch:
                x["loop"] = bool(ch["loop"])
            if "loop_start_s" in ch:
                num("loop_start_s", 0, 600)
            for k, lo, hi in (("fade_s", 0, 10), ("tempo_bpm", 30, 300), ("beat_offset_s", 0, 60)):
                if k in ch:
                    num(k, lo, hi)
            if "beats_per_bar" in ch:
                if ch["beats_per_bar"] in (None, ""):
                    x.pop("beats_per_bar", None)
                else:
                    x["beats_per_bar"] = int(min(16, max(1, int(float(ch["beats_per_bar"])))))
        except (TypeError, ValueError):
            return False
        if x.get("role") == "music" and "tempo_bpm" not in x:
            x.pop("beat_offset_s", None)
            x.pop("beats_per_bar", None)
        if "id" in ch and ch["id"] != sid:
            new = re.sub(r"[^a-z0-9_]+", "_", str(ch["id"]).lower()).strip("_")[:40]
            if not new or not new[0].isalpha():
                return False
            if self._sound(new) is not None:
                compat.messagebox.showerror("Video modes", 'There is a sound "%s" already.' % new)
                return False
            for ph in self._doc.get("phases") or []:
                if ph.get("music") == sid:
                    ph["music"] = new
                st = ph.get("settings") or {}
                if ph.get("kind") == "rhythm" and st.get("music") == sid:
                    st["music"] = new
            for c in self._doc.get("cues") or []:
                if c.get("sound") == sid:
                    c["sound"] = new
            x["id"] = new
        return self._save("Change a sound")

    @rpc
    def remove_sound(self, sid):
        x = self._sound(sid)
        if x is None:
            return False
        uses = ['phase "%s"' % ph.get("id") for ph in self._doc.get("phases") or [] if SND.phase_music(ph) == sid]
        uses += ['the cue on %s' % c.get("on") for c in self._doc.get("cues") or [] if c.get("sound") == sid]
        if uses:
            compat.messagebox.showerror("Video modes", 'Sound "%s" is played by %s; take it off there first.'
                                        % (sid, ", ".join(uses)))
            return False
        self._doc["assets"]["sounds"].remove(x)
        return self._save("Remove a sound")

    @rpc
    def find_beat(self, sid):
        """Find a music bed's tempo and first beat from its file (a worker); they are set on it, as one change."""
        x = self._sound(sid)
        path = SND.file_of(self._mode_dir(), x) if x else ""
        if not path or sid in self._beat_busy:
            return False
        self._beat_busy.add(sid)
        self.set(beat_busy=sorted(self._beat_busy))
        slug = self._slug

        def work():
            try:
                got = SND.beat_of(path)
            except (ValueError, OSError, Exception):    # noqa: BLE001
                got = None

            def done():
                self._beat_busy.discard(sid)
                self.set(beat_busy=sorted(self._beat_busy))
                if slug != self._slug:
                    return
                if not got:
                    compat.messagebox.showerror("Video modes", "No steady beat found in %s." % os.path.basename(path))
                    return
                self.set_sound(sid, {"tempo_bpm": got["bpm"], "beat_offset_s": got["offset_s"]})
            self.ctx.loop.post(done)
        threading.Thread(target=work, daemon=True, name="vmodes-beat").start()
        return True

    @rpc
    def set_phase_music(self, phase_id, sid):
        """The music a phase plays ("" = none). A rhythm phase's is its settings.music, which its beat grid reads."""
        for ph in (self._doc or {}).get("phases") or []:
            if ph.get("id") != phase_id:
                continue
            if sid and (self._sound(sid) or {}).get("role") != "music":
                return False
            if ph.get("kind") == "rhythm":
                if not sid:
                    return False                              # a rhythm phase plays to its music
                ph.setdefault("settings", {})["music"] = sid
                ph.pop("music", None)
            elif sid:
                ph["music"] = sid
            else:
                ph.pop("music", None)
            return self._save("Change a phase's music")
        return False

    @rpc
    def set_cues(self, cues):
        """The sounds on events, as a list [{on, sound, duck_music}] (the page edits a copy and hands it back)."""
        from ...core.video_mode import compiler as C
        if self._doc is None:
            return False
        out = []
        for c in cues or []:
            if not isinstance(c, dict) or c.get("on") not in C.CUE_ON or self._sound(c.get("sound")) is None:
                continue
            row = {"on": c["on"], "sound": c["sound"]}
            if c.get("duck_music"):
                row["duck_music"] = True
            out.append(row)
        if out:
            self._doc["cues"] = out
        else:
            self._doc.pop("cues", None)
        return self._save("Change the sounds on events")

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
        if self._save("Bring art in"):
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
        return self._save("Change a picture")

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
        return self._save("Remove a picture")

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
        return self._save("Change the backgrounds")

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
            if self._doc is not None:
                self._paint_sounds()                   # PAD-1667: the sounds count against this machine's route
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

    # -- playing it in the app (PAD-1659) ----------------------------------------------------------------------
    def _replays_dir(self):
        return os.path.join(self._mode_dir(), REPLAYS)

    def _recordings(self):
        out = []
        d = self._replays_dir()
        try:
            names = sorted(os.listdir(d), reverse=True)
        except OSError:
            return out
        for n in names:
            if not n.endswith(".json"):
                continue
            try:
                with open(os.path.join(d, n), encoding="utf-8") as f:
                    meta = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(meta, dict) and os.path.isfile(os.path.join(d, n[:-5] + ".inputs")):
                out.append(dict(meta, name=n[:-5]))
        return out[:20]

    def _play_pictures(self, doc, names):
        """Each picture the engine names by index (its quads' ``atlas``), as the player loads it: the sheet's file
        and size, or a placeholder of the size the compiler gave it (compiler.py build_pictures)."""
        A, _, _, _ = _mods()
        teams = {}
        for t in doc.get("things") or []:
            teams.setdefault(t.get("picture"), t.get("team", "scenery"))
        by_id = {p["id"]: p for p in (doc.get("assets") or {}).get("pictures") or []}
        md = self._mode_dir()
        out = []
        for pid in names.get("pictures") or []:
            p = by_id.get(pid) or {}
            path = A.picture_path(md, p) if p.get("file") else ""
            size = None
            if path and os.path.isfile(path):
                try:
                    from PIL import Image
                    with Image.open(path) as im:
                        size = im.size
                except OSError:
                    size = None
            n = int(p.get("frames") or 1)
            if size:
                fw, fh = int(p.get("frame_w") or size[0]), int(p.get("frame_h") or p.get("frame_w") or size[1])
                out.append({"id": pid, "path": path, "w": size[0], "h": size[1], "team": teams.get(pid, "scenery"),
                            "v": int(os.path.getmtime(path)), "fw": fw, "fh": fh, "frames": n,
                            "cols": max(1, size[0] // max(1, fw))})
                continue
            if p.get("frame_w"):
                fw, fh = int(p["frame_w"]), int(p.get("frame_h", p["frame_w"]))
            else:
                hb = p.get("hitbox") or {}
                if hb.get("shape") == "circle":
                    fw = fh = int(round(2 * hb.get("r", 32)))
                elif hb.get("shape") == "box":
                    fw, fh = int(round(hb.get("w", 64))), int(round(hb.get("h", 64)))
                else:
                    fw = fh = 64
            fw, fh = max(1, fw), max(1, fh)
            out.append({"id": pid, "path": "", "w": fw, "h": fh * n, "fw": fw, "fh": fh, "frames": n, "cols": 1,
                        "team": teams.get(pid, "scenery")})
        return out

    def _placeholder_sound(self, snd, index):
        """The stand-in WAV of a sound whose file is not there yet (core.video_mode.sound.placeholder_wav), made once
        per look of it in the tab's own temp folder. "" when it could not be written."""
        import hashlib
        key = hashlib.sha1(json.dumps([snd, index], sort_keys=True).encode("utf-8")).hexdigest()[:16]
        path = os.path.join(self._tmpdir(), "sounds", "%s_%s.wav" % (re.sub(r"[^0-9A-Za-z_-]", "_", str(snd.get("id", "s")))[:24], key))
        if not os.path.isfile(path):
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path + ".part", "wb") as f:
                    f.write(SND.placeholder_wav(snd, index))
                os.replace(path + ".part", path)
            except OSError:
                return ""
        return path

    @rpc
    def play_open(self):
        """Compile the mode for the player. Returns what it needs to play, or {"problems": [...]}: the pack (base64),
        the engine's files, each picture / font / sound / clip by the index the engine names it, the flow's cards
        (for Start here), the budgets of the machine picked and the recordings kept."""
        from ...core.video_mode import compiler as C
        _, B, _, P = _mods()
        if self._doc is None:
            return {"problems": ["Pick a video mode first."]}
        comp = C.compile_doc(self._doc, self._mode_dir())
        if not comp.ok:
            return {"problems": comp.problems[:20]}
        doc, names, md = self._doc, comp.names, self._mode_dir()
        assets = doc.get("assets") or {}

        def files(kind, ids):
            by_id = {a["id"]: a for a in assets.get(kind) or []}
            out = []
            for n, i in enumerate(ids):
                a = by_id.get(i) or {}
                path = os.path.join(md, *str(a.get("file") or "").split("/")) if a.get("file") else ""
                row = {"id": i, "path": path if path and os.path.isfile(path) else "", "file": a.get("file", ""),
                       "loop": bool(a.get("loop", False)), "volume": float(a.get("volume", 1.0)),
                       "role": a.get("role", ""), "loop_start_s": float(a.get("loop_start_s", 0) or 0)}
                if kind == "sounds":
                    # PAD-1667: a sound without its file yet plays a placeholder made here, as a picture without one is
                    # drawn as a placeholder; and how long each plays (the machine's one voice skips an effect still
                    # sounding, so the player needs it)
                    if not row["path"]:
                        row["path"], row["placeholder"] = self._placeholder_sound(a, n), True
                    row["seconds"] = round(SND.seconds(row["path"]), 4) if row["path"] else 0.0
                    row["duck"] = bool(duck.get(i))
                out.append(row)
            return out
        duck = SND.ducks(doc)
        phases = {ph["id"]: ph for ph in doc.get("phases") or []}
        cards = []
        for c in (doc.get("flow") or {}).get("cards") or []:
            ph = phases.get(c.get("phase")) or {}
            if c.get("card") == "phase":
                label, kind = ph.get("title") or c.get("phase"), ph.get("kind", "")
            elif c.get("card") == "clip":
                label, kind = c.get("clip", ""), "clip"
            else:
                label, kind = "Ends: " + str(c.get("outcome", "")), "end"
            cards.append({"id": c["id"], "card": c.get("card"), "label": label, "kind": kind,
                          "phase": c.get("phase", ""), "length_s": ph.get("length_s")})
        machine = self.get("machine") or B.DEFAULT
        m = B.MACHINES.get(machine) or B.MACHINES[B.DEFAULT]
        eng = os.path.join(os.path.dirname(C.__file__), "engine")
        fonts = [{"atlas": f["atlas"], "size": f["size"], "cell_w": max(1, int(round(f["size"] * 0.6)))}
                 for f in names.get("fonts") or []]
        self._play_id += 1
        pid = self._play_id
        self.set(play_mem=None)

        pic_ix = {pid: i for i, pid in enumerate(names.get("pictures") or [])}
        font_ix = {"font:%s" % f.get("id"): fm["atlas"]
                   for f, fm in zip(assets.get("fonts") or [], names.get("fonts") or [])}

        def work():
            """What the pictures cost the machine, and which of its atlases each frame lands in (so the player counts
            draw calls as the machine makes them: one per atlas and blend run): PAD-1658's pack, off the page's
            thread."""
            try:
                pk = P.pack(md, doc, machine)
                atlas = {}
                for it in pk.items:
                    if it.place is None:
                        continue
                    if it.owner in font_ix:
                        atlas.setdefault(str(font_ix[it.owner]), [it.place[0]])
                    elif it.owner in pic_ix:
                        fr = atlas.setdefault(str(pic_ix[it.owner]), [])
                        while len(fr) <= it.index:
                            fr.append(it.place[0])
                        fr[it.index] = it.place[0]
                mem = {"used": int(pk.report.get("memory") or 0), "budget": int(m["memory"]), "atlas": atlas,
                       "atlases": len(pk.atlases)}
            except Exception:             # noqa: BLE001 - the meters just stay as the app counts
                mem = None
            self.ctx.loop.post(lambda: pid == self._play_id and self.set(play_mem=mem))
        threading.Thread(target=work, daemon=True, name="vmodes-play-cost").start()
        stage = doc.get("stage") or {}
        return {
            "problems": [], "notes": comp.notes[:20], "slug": self._slug, "title": doc.get("title") or self._slug,
            "pack": base64.b64encode(comp.pack).decode("ascii"),
            "engine_js": os.path.join(eng, "vm_engine.js"), "engine_wasm": os.path.join(eng, "vm_engine.wasm"),
            "stage": [int(stage.get("width", 1360)), int(stage.get("height", 768))],
            "seed": 1, "pictures": self._play_pictures(doc, names), "fonts": fonts,
            "sounds": files("sounds", names.get("sounds") or []), "clips": files("clips", names.get("clips") or []),
            "things": names.get("things") or [], "phases": names.get("phases") or [], "cards": cards,
            "start": (doc.get("flow") or {}).get("start", ""),
            "skip_clips": (doc.get("entry") or {}).get("skip_clips", "none"),
            "machine": {"key": machine, "label": m["label"], "things": m.get("things", 0), "quads": m.get("quads", 0),
                        "draw_calls": m.get("draw_calls", 0), "memory": m["memory"]},
            "recordings": self._recordings(),
        }

    @rpc
    def play_save(self, data_b64, meta):
        """Keep a recording of the buttons a play was given (one byte a step, the engine's input word) beside its
        seed, start card, steps and the run's draw list hash, in ``<mode>/replays/``. Returns its name."""
        if self._doc is None:
            return ""
        data = base64.b64decode(data_b64 or "")
        if not data:
            return ""
        d = self._replays_dir()
        os.makedirs(d, exist_ok=True)
        name = time.strftime("%Y%m%d-%H%M%S")
        base, n = name, 2
        while os.path.exists(os.path.join(d, name + ".inputs")):
            name = "%s-%d" % (base, n)
            n += 1
        keep = {k: meta.get(k) for k in ("seed", "level", "card", "card_id", "steps", "hash", "outcome", "score", "audio_offset")
                if isinstance(meta, dict) and k in meta}
        keep["made"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(d, name + ".inputs"), "wb") as f:
            f.write(data)
        with open(os.path.join(d, name + ".json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(keep, f, indent=1, sort_keys=True)
        return name

    @rpc
    def play_recording(self, name):
        """A kept recording: {"data": base64 inputs, ...its meta}, or None."""
        if self._doc is None or not re.fullmatch(r"[0-9A-Za-z_-]{1,64}", str(name or "")):
            return None
        d = self._replays_dir()
        try:
            with open(os.path.join(d, name + ".inputs"), "rb") as f:
                data = f.read()
            with open(os.path.join(d, name + ".json"), encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(meta, dict):
            return None
        return dict(meta, name=name, data=base64.b64encode(data).decode("ascii"))


    # -- the editor (PAD-1661): the stage, the layers and the inspector ----------------------------------------
    def _stage_parts(self, comp, doc):
        """What the page needs to draw a compiled document: the pack, the engine's files, the pictures and fonts by
        the index the engine names them, and where each phase's places start in the engine's place table."""
        from ...core.video_mode import compiler as C
        names = comp.names
        eng = os.path.join(os.path.dirname(C.__file__), "engine")
        stage = doc.get("stage") or {}
        return {
            "pack": base64.b64encode(comp.pack).decode("ascii"),
            "engine_js": os.path.join(eng, "vm_engine.js"), "engine_wasm": os.path.join(eng, "vm_engine.wasm"),
            "stage": [int(stage.get("width", 1360)), int(stage.get("height", 768))],
            "pictures": self._play_pictures(doc, names),
            "fonts": [{"atlas": f["atlas"], "size": f["size"], "cell_w": max(1, int(round(f["size"] * 0.6)))}
                      for f in names.get("fonts") or []],
            "place0": names.get("place0") or [], "phases": names.get("phases") or [],
            "track_keys": names.get("track_keys") or [],          # PAD-1664: each track's first key in the engine
        }

    def _edit_reply(self, doc, with_doc=False, assets_changed=False):
        from ...core.video_mode import compiler as C
        comp = C.compile_doc(doc, self._mode_dir())
        out = {"ok": True, "history": self._hist.state() if self._hist else None, "notes": comp.notes[:20],
               "problems": comp.problems[:20]}
        if comp.ok:
            parts = self._stage_parts(comp, doc)
            if not assets_changed and not with_doc:
                parts.pop("pictures")
                parts.pop("fonts")
            out.update(parts)
        else:
            out["pack"] = None
        if with_doc:
            out["doc"] = doc
        return out

    @rpc
    def edit_open(self):
        """Open the editor on the mode picked: the document, the compiled pack and what draws it, and the history."""
        if self._doc is None:
            return {"ok": False, "problems": ["Pick a video mode first."]}
        _, B, _, _ = _mods()
        out = self._edit_reply(self._doc, with_doc=True)
        out["slug"] = self._slug
        out["machine"] = self.get("machine") or B.DEFAULT
        return out

    @rpc
    def edit_commit(self, doc, label=""):
        """One change made in the editor: the whole document after it. Checked, saved (there is no save button)
        and kept as one undo step. Refused, with every reason, when it does not check or compile; the page then
        puts its copy back."""
        from ...core.video_mode import compiler as C
        _, _, D, _ = _mods()
        if self._doc is None:
            return {"ok": False, "problems": ["Pick a video mode first."]}
        try:
            doc = D.migrate(doc)
        except ValueError as e:
            return {"ok": False, "problems": list(getattr(e, "problems", None) or [str(e)])}
        probs = D.check(doc)
        if not probs:
            comp = C.compile_doc(doc, self._mode_dir())
            probs = [] if comp.ok else comp.problems
        if probs:
            return {"ok": False, "problems": probs[:12], "doc": self._doc}
        assets_changed = (doc.get("assets") or {}) != (self._doc.get("assets") or {})
        self._doc = doc
        if not self._save(str(label or "Change")[:80]):
            return {"ok": False, "problems": ["The change was not saved."], "doc": self._doc}
        return self._edit_reply(self._doc, assets_changed=assets_changed)

    def _edit_move(self, which):
        _, _, D, _ = _mods()
        if self._doc is None or self._hist is None:
            return {"ok": False}
        label = self._hist.undo_label() if which == "undo" else self._hist.redo_label()
        doc = self._hist.undo(self._doc) if which == "undo" else self._hist.redo(self._doc)
        if doc is None:
            return {"ok": False}
        assets_changed = (doc.get("assets") or {}) != (self._doc.get("assets") or {})
        try:
            D.save(self._doc_path(), doc)
        except ValueError as e:
            # a step that no longer leads to a document that checks: step back over it and say so
            if which == "undo":
                self._hist.redo(doc)
            else:
                self._hist.undo(doc)
            return {"ok": False, "problems": list(getattr(e, "problems", None) or [str(e)])}
        self._doc = doc
        self._saved = copy.deepcopy(doc)
        self._hist_state()
        self.set(report=None, written="")
        self._paint()
        out = self._edit_reply(doc, with_doc=True, assets_changed=assets_changed)
        out["label"] = label
        return out

    @rpc
    def edit_undo(self):
        """One step back. Returns the document and its pack, or {"ok": False} at the start of the history."""
        return self._edit_move("undo")

    @rpc
    def edit_redo(self):
        return self._edit_move("redo")

    @rpc
    def phase_template(self, doc, kind):
        """PAD-1664, the storyboard's Add a phase: ``doc`` (the page's copy) with a new playable phase of game kind
        ``kind`` and the placeholder things it needs. Nothing is saved: the page wires the phase into the flow and
        commits the whole change as one step."""
        _, _, D, _ = _mods()
        try:
            new = D.phase_template(D.migrate(doc), str(kind or ""))
        except ValueError as e:
            return {"ok": False, "problems": list(getattr(e, "problems", None) or [str(e)])}
        return {"ok": True, "doc": new, "phase": new["phases"][-1]["id"]}


TAB = VideoModesTab
