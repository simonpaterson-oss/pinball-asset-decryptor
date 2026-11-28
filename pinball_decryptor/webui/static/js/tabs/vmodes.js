// Video modes tab (PAD-1658): a video mode's pictures. Art comes in from a picture, a numbered run of PNGs, a GIF,
// a sprite sheet (by grid or at its empty gutters) or a stretch of video (cut out with a key colour or the video's
// own alpha); each is a sprite with frames, a frame rate, loop or once, an anchor point and a hit box, both dragged
// on the frame here. Backgrounds are a phase's layers (still, tiled, scrolling, each at its own speed), previewed
// moving. Pack for the machine trims, packs and premultiplies them and says what the mode costs before anything
// is written. Play (PAD-1659) plays the mode in the app: vmodes_play.js. Python half: webui/tabs/vmodes.py; the rules:
// core/video_mode/art.py and pack.py.

import { html, useEffect, useMemo, useRef, useState, PageHead, Card, Button, Field, Select, Seg, Chip, Note, Icon,
         Empty, Spinner, Modal, tip, call, cx, mediaUrl, fmtBytes } from "../core/ui.js";
import { useNs } from "../core/store.js";
import { PixelEditor } from "./pixel_edit.js";
import { VideoModePlayer } from "./vmodes_play.js";

export const css = true;

const STAGE_W = 1360, STAGE_H = 768;
const FRAME_API = { open: "vmodes.frame_open", save: "vmodes.frame_save", bytes: null, label: "The frame", leds: false };

const T = {
  add: "Bring in a picture, a numbered run of PNGs, a GIF, a sprite sheet or a stretch of video. Each becomes one "
    + "sprite with its frames.",
  anchor: "The anchor: the point of the frame that sits where the thing is placed on the stage. Drag the cross.",
  hitbox: "What collides: drag inside it to move it, drag its corner handle to size it. Relative to the anchor.",
  fps: "How many frames a second the animation plays (1 to 60; the machine steps 60 times a second).",
  touch: "Open this frame in the pixel editor to touch it up. Frames up to 512 pixels a side.",
  layers: "A phase's background, back to front. Still: drawn once. Tiled: repeated across the stage. Scrolling: "
    + "tiled and moving at its own speed (minus is to the left); layers at different speeds give depth.",
  check: "Trim, pack and premultiply every picture as the machine would load it, and say what it costs. Nothing is "
    + "written.",
  write: "Pack and write the atlases the machine loads into the mode's build folder. Refused, naming the sprites "
    + "to shrink, when the mode is over a budget.",
  memory: "Every packed atlas as the machine holds it in memory: 4 bytes a texel (RGBA, premultiplied).",
  card: "The packed atlases as the machine's card holds them (on Spike 2 as they sit in memory, since its runtime maps them straight in; compressed elsewhere), plus the mode's sounds and clips as they are.",
  kind: {
    picture: "One picture: one frame.",
    numbered: "Every file of the run this one belongs to (boom_0001.png, boom_0002.png …), in number order.",
    gif: "An animated GIF, APNG or WebP, with its own frame times and loop.",
    grid: "A sheet cut into frames of one size, left to right, top to bottom.",
    auto: "A sheet cut where its empty gutters are: the rows, then the columns, holding nothing but its background.",
    video: "Seconds of a video as frames, cut out by a key colour (a green or blue screen) or by its own alpha.",
  },
};

// ---- drawing a sheet's frames ---------------------------------------------------------------------------------
function useImage(src) {
  const [img, setImg] = useState(null);
  useEffect(() => {
    if (!src) { setImg(null); return undefined; }
    let live = true;
    const im = new Image();
    im.onload = () => { if (live) setImg(im); };
    im.src = src;
    return () => { live = false; };
  }, [src]);
  return img;
}

const srcOf = (path, v) => (path ? mediaUrl(path) + "&v=" + (v || 0) : null);

function checker(g, w, h, k = 8) {
  const cs = getComputedStyle(document.documentElement);
  const a = cs.getPropertyValue("--panel").trim() || "#22262b", b = cs.getPropertyValue("--panel-2").trim() || "#2a2f35";
  for (let y = 0; y < h; y += k) for (let x = 0; x < w; x += k) {
    g.fillStyle = ((x / k + y / k) & 1) ? a : b; g.fillRect(x, y, k, k);
  }
}

// The frame to show at time t: loop, or once with a short hold on the last frame before it plays again.
function frameAt(seq, fps, loop, t) {
  const n = seq.length;
  if (n <= 1) return seq[0] || 0;
  const i = Math.floor(t * fps);
  if (loop) return seq[i % n];
  const cyc = n + Math.round(fps * 0.8);
  const k = i % cyc;
  return seq[Math.min(k, n - 1)];
}

function SheetPlayer({ src, cols, fw, fh, seq, fps, loop, playing = true, box = [96, 96], frame, onFrame, overlay,
                       zoomMax = 8, cls = "" }) {
  const cv = useRef(null);
  const img = useImage(src);
  const scale = Math.min(zoomMax, box[0] / Math.max(1, fw), box[1] / Math.max(1, fh));
  const W = Math.max(1, Math.round(fw * scale)), H = Math.max(1, Math.round(fh * scale));
  const shown = useRef(0);
  useEffect(() => {
    const c = cv.current;
    if (!c || !img) return undefined;
    const g = c.getContext("2d");
    let raf = 0;
    const t0 = performance.now();
    const draw = (f) => {
      g.imageSmoothingEnabled = scale < 2;
      g.clearRect(0, 0, W, H);
      checker(g, W, H, 8);
      g.drawImage(img, (f % cols) * fw, Math.floor(f / cols) * fh, fw, fh, 0, 0, W, H);
      if (overlay) overlay(g, scale);
    };
    if (!playing) { draw(frame || 0); return undefined; }
    const tick = (now) => {
      const f = frameAt(seq, fps, loop, (now - t0) / 1000);
      if (f !== shown.current && onFrame) onFrame(f);
      shown.current = f;
      draw(f);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [img, playing, frame, fps, loop, seq, cols, fw, fh, W, H, overlay]);
  return html`<canvas ref=${cv} class=${cx("vm-player", cls)} width=${W} height=${H}
    style=${{ width: W + "px", height: H + "px" }} />`;
}

// ---- the list of video modes ----------------------------------------------------------------------------------
function NewMode() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  if (!open) return html`<${Button} icon="plus" onClick=${() => setOpen(true)}>New video mode<//>`;
  const go = () => { call("vmodes.new_mode", name); setOpen(false); setName(""); };
  return html`<div class="row" style="gap:6px">
    <${Field} sm value=${name} placeholder="Its name" autoFocus width="180px" onChange=${setName}
      onCommit=${(v) => { setName(v); }} maxLength=${40} />
    <${Button} size="sm" kind="primary" onClick=${go}>Make it<//>
    <${Button} size="sm" kind="ghost" onClick=${() => setOpen(false)}>Cancel<//>
  </div>`;
}

// ---- one sprite's card in the grid ----------------------------------------------------------------------------
function SpriteCard({ p, on, onPick }) {
  const seq = useMemo(() => (p.anim_frames && p.anim_frames.length ? p.anim_frames : [0]), [p.anim_frames]);
  return html`<button type="button" class=${cx("vm-sprite", on && "on", p.missing && "bad")} onClick=${onPick}>
    <div class="vm-thumb">
      ${p.missing ? html`<span class="err small">file missing</span>`
        : html`<${SheetPlayer} src=${srcOf(p.path, p.v)} cols=${p.cols} fw=${p.fw} fh=${p.fh} seq=${seq} fps=${p.fps}
            loop=${p.loop} box=${[112, 84]} />`}
    </div>
    <div class="vm-sprite-name ellip">${p.id}</div>
    <div class="vm-sprite-meta small muted mono">
      ${p.frames > 1 ? `${p.frames} fr · ${p.fps} fps` : "still"} · ${p.fw}×${p.fh}
    </div>
    ${p.uses.length ? html`<span class="vm-used" ...${tip({ head: "Used by", lines: p.uses })}><${Icon} name="link" /></span>` : null}
  </button>`;
}

// ---- the picked sprite: frame, anchor, hit box ----------------------------------------------------------------
function SpriteInspector({ p, running }) {
  const [playing, setPlaying] = useState(p.frames > 1);
  const [frame, setFrame] = useState(0);
  const [anchor, setAnchor] = useState(p.anchor);
  const [hb, setHb] = useState(p.hitbox);
  const [touch, setTouch] = useState(null);
  const drag = useRef(null);
  const live = useRef({ anchor: p.anchor, hb: p.hitbox });
  useEffect(() => { setAnchor(p.anchor); setHb(p.hitbox); live.current = { anchor: p.anchor, hb: p.hitbox }; },
    [p.id, JSON.stringify(p.anchor), JSON.stringify(p.hitbox)]);
  useEffect(() => { setFrame(0); setPlaying(p.frames > 1); }, [p.id]);
  const seq = useMemo(() => (p.anim_frames && p.anim_frames.length ? p.anim_frames : [0]), [p.anim_frames]);
  const box = [520, 340];
  const scale = Math.min(8, box[0] / p.fw, box[1] / p.fh);
  const cs = getComputedStyle(document.documentElement);
  const accent = cs.getPropertyValue("--accent").trim() || "#e8a33d", info = cs.getPropertyValue("--info").trim() || "#7fb0e6";

  const overlay = useMemo(() => (g, s) => {
    const ax = anchor[0] * p.fw * s, ay = anchor[1] * p.fh * s;
    if (hb) {
      g.strokeStyle = info; g.lineWidth = 1; g.fillStyle = info + "33";
      if (hb.shape === "circle") {
        g.beginPath(); g.arc(ax + hb.x * s, ay + hb.y * s, hb.r * s, 0, Math.PI * 2); g.fill(); g.stroke();
        const hx = ax + (hb.x + hb.r) * s, hy = ay + hb.y * s;
        g.fillStyle = info; g.fillRect(hx - 4, hy - 4, 8, 8);
      } else {
        const x = ax + hb.x * s, y = ay + hb.y * s, w = hb.w * s, h = hb.h * s;
        g.fillRect(x, y, w, h); g.strokeRect(Math.round(x) + 0.5, Math.round(y) + 0.5, Math.round(w), Math.round(h));
        g.fillStyle = info; g.fillRect(x + w - 4, y + h - 4, 8, 8);
      }
    }
    g.strokeStyle = accent; g.lineWidth = 1.5;
    g.beginPath(); g.moveTo(ax - 9, ay); g.lineTo(ax + 9, ay); g.moveTo(ax, ay - 9); g.lineTo(ax, ay + 9); g.stroke();
    g.beginPath(); g.arc(ax, ay, 3.5, 0, Math.PI * 2); g.stroke();
  }, [anchor, hb, p.fw, p.fh, accent, info]);

  // dragging: the anchor cross, the hit box's handle, or inside the hit box
  const at = (e) => { const r = e.currentTarget.getBoundingClientRect(); return [(e.clientX - r.left) / scale, (e.clientY - r.top) / scale]; };
  const down = (e) => {
    if (running) return;
    const [fx, fy] = at(e);
    const ax = anchor[0] * p.fw, ay = anchor[1] * p.fh, near = 8 / scale;
    let what = null;
    if (hb) {
      if (hb.shape === "circle") {
        if (Math.abs(fx - (ax + hb.x + hb.r)) < near && Math.abs(fy - (ay + hb.y)) < near) what = "size";
        else if (Math.hypot(fx - (ax + hb.x), fy - (ay + hb.y)) < hb.r) what = "move";
      } else {
        if (Math.abs(fx - (ax + hb.x + hb.w)) < near && Math.abs(fy - (ay + hb.y + hb.h)) < near) what = "size";
        else if (fx > ax + hb.x && fx < ax + hb.x + hb.w && fy > ay + hb.y && fy < ay + hb.y + hb.h) what = "move";
      }
    }
    if (Math.hypot(fx - ax, fy - ay) < near * 1.5) what = "anchor";
    if (!what) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { what, fx, fy, hb: hb && { ...hb }, anchor: [...anchor] };
    setPlaying(false);
  };
  const move = (e) => {
    const d = drag.current;
    if (!d) return;
    const [fx, fy] = at(e);
    const dx = Math.round(fx - d.fx), dy = Math.round(fy - d.fy);
    if (d.what === "anchor") {
      const nx = Math.min(1, Math.max(0, (d.anchor[0] * p.fw + dx) / p.fw));
      const ny = Math.min(1, Math.max(0, (d.anchor[1] * p.fh + dy) / p.fh));
      // the hit box stays where it is on the frame: it is kept relative to the anchor
      const ddx = (nx - d.anchor[0]) * p.fw, ddy = (ny - d.anchor[1]) * p.fh;
      const nhb = d.hb && { ...d.hb, x: Math.round(d.hb.x - ddx), y: Math.round(d.hb.y - ddy) };
      setAnchor([nx, ny]); if (nhb) setHb(nhb);
      live.current = { anchor: [nx, ny], hb: nhb || live.current.hb };
    } else if (d.what === "move") {
      const n = { ...d.hb, x: d.hb.x + dx, y: d.hb.y + dy };
      setHb(n); live.current = { ...live.current, hb: n };
    } else {
      const n = d.hb.shape === "circle" ? { ...d.hb, r: Math.max(1, d.hb.r + dx) }
        : { ...d.hb, w: Math.max(1, d.hb.w + dx), h: Math.max(1, d.hb.h + dy) };
      setHb(n); live.current = { ...live.current, hb: n };
    }
  };
  const up = () => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    call("vmodes.set_picture", p.id, d.what === "anchor" ? { anchor: live.current.anchor, hitbox: live.current.hb }
      : { hitbox: live.current.hb });
  };
  const setShape = (shape) => {
    if (shape === "none") { call("vmodes.set_picture", p.id, { hitbox: null }); return; }
    const ax = anchor[0] * p.fw, ay = anchor[1] * p.fh;
    const n = shape === "circle"
      ? { shape, x: Math.round(p.fw / 2 - ax), y: Math.round(p.fh / 2 - ay), r: Math.round(Math.min(p.fw, p.fh) * 0.4) }
      : { shape, x: Math.round(-ax + p.fw * 0.1), y: Math.round(-ay + p.fh * 0.1), w: Math.round(p.fw * 0.8), h: Math.round(p.fh * 0.8) };
    call("vmodes.set_picture", p.id, { hitbox: n });
  };
  const k = Math.min(1, 44 / Math.max(p.fw, p.fh));
  const shown = playing ? null : frame;
  return html`<${Card} title=${p.id} sub=${`${p.frames > 1 ? `${p.frames} frames` : "A still"} · ${p.fw} × ${p.fh} px · ${p.file}`}
      cls="vm-insp" extra=${html`<${Button} size="sm" kind="ghost" icon="trash" disabled=${running}
        title=${p.uses.length ? `Used by ${p.uses.join(", ")}: take it off there first` : "Take this picture out of the mode"}
        onClick=${() => call("vmodes.remove_picture", p.id)} />`}>
    <div class="vm-insp-body">
      <div class="vm-frame-wrap" onPointerDown=${down} onPointerMove=${move} onPointerUp=${up} ...${tip(T.hitbox)}>
        ${p.missing ? html`<${Empty} title="The picture's file is missing">${p.file}<//>`
          : html`<${SheetPlayer} src=${srcOf(p.path, p.v)} cols=${p.cols} fw=${p.fw} fh=${p.fh} seq=${seq} fps=${p.fps}
              loop=${p.loop} playing=${playing} frame=${shown} onFrame=${setFrame} box=${box} overlay=${overlay}
              cls="vm-big" />`}
      </div>
      <div class="vm-fields">
        <label class="vm-lbl">Name</label>
        <${Field} sm value=${p.id} mono maxLength=${40} disabled=${running}
          onCommit=${(v) => v && v !== p.id && call("vmodes.set_picture", p.id, { id: v })} />
        ${p.frames > 1 ? html`
          <label class="vm-lbl" ...${tip(T.fps)}>Frame rate</label>
          <div class="row" style="gap:6px"><${Field} sm type="number" min=${1} max=${60} step=${1} width="72px"
            value=${String(p.fps)} disabled=${running} onCommit=${(v) => call("vmodes.set_picture", p.id, { fps: v })} />
            <span class="small muted">a second · ${(p.frames / p.fps).toFixed(2)} s</span></div>
          <label class="vm-lbl">Plays</label>
          <${Seg} value=${p.loop ? "loop" : "once"} disabled=${running}
            options=${[{ value: "loop", label: "Loop" }, { value: "once", label: "Once" }]}
            onChange=${(v) => call("vmodes.set_picture", p.id, { loop: v === "loop" })} />` : null}
        <label class="vm-lbl" ...${tip(T.anchor)}>Anchor</label>
        <span class="mono small">${Math.round(anchor[0] * p.fw)}, ${Math.round(anchor[1] * p.fh)} px
          <span class="muted"> (${anchor[0].toFixed(2)}, ${anchor[1].toFixed(2)})</span></span>
        <label class="vm-lbl" ...${tip(T.hitbox)}>Hit box</label>
        <${Seg} value=${hb ? hb.shape : "none"} disabled=${running}
          options=${[{ value: "box", label: "Box" }, { value: "circle", label: "Circle" }, { value: "none", label: "None" }]}
          onChange=${setShape} />
        ${hb ? html`<span></span><span class="mono small muted">${hb.shape === "circle" ? `at ${hb.x}, ${hb.y} · r ${hb.r}`
          : `${hb.x}, ${hb.y} · ${hb.w} × ${hb.h}`}</span>` : null}
      </div>
    </div>
    ${p.frames > 1 ? html`<div class="vm-strip-row">
      <${Button} size="sm" kind="ghost" icon=${playing ? "pause" : "play"} title=${playing ? "Pause" : "Play"}
        onClick=${() => setPlaying(!playing)} />
      <span class="small mono vm-fno">${(shown ?? frame) + 1} / ${p.frames}</span>
      <div class="vm-strip">
        ${Array.from({ length: Math.min(p.frames, 240) }, (_, i) => html`<button type="button"
          class=${cx("vm-cell", !playing && frame === i && "on")} title=${`Frame ${i + 1}`}
          onClick=${() => { setPlaying(false); setFrame(i); }}
          style=${{ width: Math.round(p.fw * k) + "px", height: Math.round(p.fh * k) + "px",
            backgroundImage: `url("${srcOf(p.path, p.v)}")`,
            backgroundSize: `${Math.round(p.sheet_w * k)}px ${Math.round(p.sheet_h * k)}px`,
            backgroundPosition: `-${Math.round((i % p.cols) * p.fw * k)}px -${Math.round(Math.floor(i / p.cols) * p.fh * k)}px` }}></button>`)}
      </div>
    </div>` : null}
    <div class="row" style="gap:8px;margin-top:10px">
      <${Button} size="sm" icon="brush" disabled=${running || p.missing || Math.max(p.fw, p.fh) > 512} title=${T.touch}
        onClick=${() => { setPlaying(false); setTouch(`${p.id}#${playing ? 0 : frame}`); }}>Touch up frame ${(playing ? 0 : frame) + 1}<//>
    </div>
    ${touch ? html`<${PixelEditor} rel=${touch} api=${FRAME_API} onClose=${() => setTouch(null)} />` : null}
  <//>`;
}

// ---- bringing art in -------------------------------------------------------------------------------------------
function OptField({ label, k, d, opts, width = "72px", type = "number", title, min, max, step }) {
  return html`<label class="vm-lbl" ...${tip(title)}>${label}</label>
    <${Field} sm type=${type} width=${width} value=${String(opts[k] ?? "")} min=${min} max=${max} step=${step}
      onCommit=${(v) => call("vmodes.draft", d.path, d.kind, { ...opts, [k]: v, _id: d.id })} />`;
}

function ImportDialog({ d, kinds }) {
  const [id, setId] = useState(d.id);
  const [fps, setFps] = useState(d.fps);
  const [loop, setLoop] = useState(d.loop);
  useEffect(() => { setFps(d.fps); setLoop(d.loop); }, [d.sheet]);
  useEffect(() => { setId(d.id); }, [d.path]);
  const o = d.opts || {};
  const redo = (kind, extra = {}) => call("vmodes.draft", d.path, kind, { ...(kind === d.kind ? o : {}), ...extra, _id: id });
  const seq = useMemo(() => Array.from({ length: d.frames || 1 }, (_, i) => i), [d.frames]);
  const footer = html`
    <label class="small muted">Name</label>
    <${Field} sm mono value=${id} width="180px" maxLength=${40} onChange=${setId} />
    <span class="grow"></span>
    <${Button} kind="ghost" onClick=${() => call("vmodes.draft_close")}>Cancel<//>
    <${Button} kind="primary" icon="plus" disabled=${d.busy || !!d.error || !d.frames}
      onClick=${() => call("vmodes.add", id, fps, loop)}>Add to the mode<//>`;
  return html`<${Modal} title="Bring art in" icon="image" wide onClose=${() => call("vmodes.draft_close")} footer=${footer}>
    <div class="vm-imp">
      <div class="vm-imp-opts">
        <label class="vm-lbl">File</label>
        <span class="mono small ellip" title=${d.path}>${d.name}</span>
        <label class="vm-lbl">Read it as</label>
        <${Select} sm value=${d.kind} options=${kinds.map((k) => ({ value: k.key, label: k.label }))}
          onChange=${(v) => redo(v)} />
        <span></span><span class="small muted">${T.kind[d.kind]}</span>
        ${d.kind === "grid" ? html`
          <${OptField} label="Frame width" k="frame_w" d=${d} opts=${o} min=${1} />
          <${OptField} label="Frame height" k="frame_h" d=${d} opts=${o} min=${1} />
          <${OptField} label="Margin" k="margin" d=${d} opts=${o} min=${0} title="Empty pixels round the sheet's edge" />
          <${OptField} label="Spacing" k="spacing" d=${d} opts=${o} min=${0} title="Empty pixels between frames" />
          <${OptField} label="Frames" k="count" d=${d} opts=${o} min=${1} title="How many to take (empty: every full cell)" />
          ${d.src_w ? html`<span></span><span class="small muted mono">sheet ${d.src_w} × ${d.src_h}</span>` : null}` : null}
        ${d.kind === "auto" ? html`
          <${OptField} label="Tolerance" k="tolerance" d=${d} opts=${o} min=${0} max=${64}
            title="How far from the background colour still counts as empty (a sheet with no see-through pixels)" />
          <${OptField} label="Smallest gap" k="min_gap" d=${d} opts=${o} min=${1}
            title="Gutters narrower than this (pixels) do not split frames" />` : null}
        ${d.kind === "video" ? html`
          <${OptField} label="Start" k="start" d=${d} opts=${o} type="text" width="90px" title="m:ss or seconds" />
          <${OptField} label="Length" k="length" d=${d} opts=${o} type="text" width="90px" title="Seconds, up to 30" />
          <${OptField} label="Frames a second" k="fps" d=${d} opts=${o} min=${1} max=${60} />
          <${OptField} label="Width" k="width" d=${d} opts=${o} min=${8} max=${1360} title="Scale the frames to this width (empty: the video's own, up to 1360)" />
          <label class="vm-lbl">Cut out by</label>
          <${Seg} value=${o.cut || "key"} onChange=${(v) => redo("video", { cut: v })}
            options=${[{ value: "key", label: "Key colour" }, { value: "alpha", label: "Alpha" }, { value: "none", label: "None" }]} />
          ${(o.cut || "key") === "key" ? html`
            <label class="vm-lbl">Key colour</label>
            <div class="row" style="gap:6px">
              <input type="color" class="vm-swatch" value=${o.key || "#00ff00"}
                onChange=${(e) => redo("video", { key: e.target.value })} />
              <span class="mono small">${o.key || "#00ff00"}</span></div>
            <${OptField} label="Tolerance" k="tolerance" d=${d} opts=${o} min=${0} max=${1} step=${0.01}
              title="0 to 1: how near the key colour a pixel must be to go see-through" />` : null}` : null}
        ${d.frames > 1 ? html`
          <label class="vm-lbl" ...${tip(T.fps)}>Frame rate</label>
          <${Field} sm type="number" width="72px" min=${1} max=${60} value=${String(fps)} onChange=${(v) => setFps(Number(v) || fps)} />
          <label class="vm-lbl">Plays</label>
          <${Seg} value=${loop ? "loop" : "once"} onChange=${(v) => setLoop(v === "loop")}
            options=${[{ value: "loop", label: "Loop" }, { value: "once", label: "Once" }]} />` : null}
      </div>
      <div class="vm-imp-prev">
        ${d.busy ? html`<div class="vm-imp-busy"><${Spinner} /><span class="muted">Reading ${d.name}…</span></div>`
          : d.error ? html`<${Note} kind="err">${d.error}<//>`
          : html`<${SheetPlayer} src=${srcOf(d.sheet)} cols=${d.cols} fw=${d.fw} fh=${d.fh} seq=${seq} fps=${fps}
              loop=${loop} box=${[400, 300]} />
            <div class="small mono muted">${d.frames} frame${d.frames === 1 ? "" : "s"} · ${d.fw} × ${d.fh} px</div>
            <div class="small muted ellip">${d.source}</div>
            ${(d.notes || []).map((n) => html`<${Note} kind="warn">${n}<//>`)}`}
      </div>
    </div>
  <//>`;
}

// ---- backgrounds ----------------------------------------------------------------------------------------------
function Parallax({ layers, pictures, bg }) {
  const cv = useRef(null);
  const W = 448, s = W / STAGE_W, H = Math.round(STAGE_H * s);
  const byId = useMemo(() => Object.fromEntries(pictures.map((p) => [p.id, p])), [pictures]);
  const imgs = useRef({});
  useEffect(() => {
    const c = cv.current;
    if (!c) return undefined;
    const g = c.getContext("2d");
    for (const l of layers) {
      const p = byId[l.picture];
      if (p && !imgs.current[p.id + p.v]) { const im = new Image(); im.src = srcOf(p.path, p.v); imgs.current[p.id + p.v] = im; }
    }
    let raf = 0;
    const t0 = performance.now();
    const tick = (now) => {
      const t = (now - t0) / 1000;
      g.fillStyle = bg || "#000"; g.fillRect(0, 0, W, H);
      for (const l of layers) {
        const p = byId[l.picture];
        const im = p && imgs.current[p.id + p.v];
        if (!im || !im.complete || !im.naturalWidth) continue;
        g.globalAlpha = l.alpha ?? 1;
        const fw = p.fw * s, fh = p.fh * s, y = (l.y || 0) * s;
        if (!l.tile) g.drawImage(im, 0, 0, p.fw, p.fh, 0, y, fw, fh);
        else {
          let x = (((l.speed || 0) * t * s) % fw);
          if (x > 0) x -= fw;
          for (; x < W; x += fw) g.drawImage(im, 0, 0, p.fw, p.fh, x, y, fw, fh);
        }
        g.globalAlpha = 1;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [layers, byId, bg]);
  return html`<canvas ref=${cv} class="vm-parallax" width=${W} height=${H} />`;
}

function Backgrounds({ s }) {
  const phases = s.phases || [];
  const [pid, setPid] = useState(phases[0] && phases[0].id);
  useEffect(() => { if (!phases.find((p) => p.id === pid)) setPid(phases[0] && phases[0].id); }, [phases]);
  const ph = phases.find((p) => p.id === pid);
  const pics = s.pictures || [];
  if (!ph) return null;
  const layers = ph.layers || [];
  const put = (ls) => call("vmodes.set_layers", ph.id, ls);
  const edit = (i, ch) => put(layers.map((l, j) => (j === i ? { ...l, ...ch } : l)));
  const moveL = (i, d) => { const ls = [...layers]; const [x] = ls.splice(i, 1); ls.splice(i + d, 0, x); put(ls); };
  return html`<${Card} title="Backgrounds" sub=${T.layers} cls="vm-bg"
      extra=${html`<${Select} sm value=${pid} width="200px" options=${phases.map((p) => ({ value: p.id, label: `Phase: ${p.title}` }))} onChange=${setPid} />`}>
    <div class="vm-bg-body">
      <div class="vm-layers">
        ${layers.length ? null : html`<div class="small muted vm-none">No background on this phase: the stage's colour shows.</div>`}
        ${layers.map((l, i) => html`<div class="vm-layer">
          <span class="vm-layer-n mono small muted">${i + 1}</span>
          <${Select} sm value=${l.picture} width="130px" disabled=${s.running}
            options=${pics.map((p) => ({ value: p.id, label: p.id }))} onChange=${(v) => edit(i, { picture: v })} />
          <${Seg} value=${l.kind} disabled=${s.running} onChange=${(v) => edit(i, { kind: v, speed: v === "scrolling" ? (l.speed || -60) : 0 })}
            options=${[{ value: "still", label: "Still" }, { value: "tiled", label: "Tiled" }, { value: "scrolling", label: "Scrolling" }]} />
          ${l.kind === "scrolling" ? html`<${Field} sm type="number" width="112px" value=${String(l.speed)} disabled=${s.running}
            title="Pixels a second; minus is to the left" suffix=${html`<span class="small muted">px/s</span>`}
            onCommit=${(v) => edit(i, { speed: Number(v) || 0 })} />` : null}
          <${Field} sm type="number" width="88px" value=${String(l.y || 0)} disabled=${s.running} title="Its top, on the 1360 × 768 stage"
            prefix=${html`<span class="small muted">y</span>`} onCommit=${(v) => edit(i, { y: Number(v) || 0 })} />
          <span class="sp"></span>
          <${Button} size="sm" kind="ghost" icon="up" title="Further back" disabled=${s.running || i === 0} onClick=${() => moveL(i, -1)} />
          <${Button} size="sm" kind="ghost" icon="down" title="Further forward" disabled=${s.running || i === layers.length - 1} onClick=${() => moveL(i, 1)} />
          <${Button} size="sm" kind="ghost" icon="x" title="Take this layer off" disabled=${s.running} onClick=${() => put(layers.filter((_, j) => j !== i))} />
        </div>`)}
        <div class="row" style="margin-top:6px">
          <${Button} size="sm" icon="plus" disabled=${s.running || !pics.length || layers.length >= 8}
            title=${pics.length ? "Add a layer in front of the others" : "Bring a picture in first"}
            onClick=${() => put([...layers, { picture: pics[0].id, kind: "still", speed: 0, y: 0 }])}>Add a layer<//>
        </div>
      </div>
      <div class="vm-bg-prev">
        <${Parallax} layers=${layers} pictures=${pics} bg=${s.stage_bg} />
        <div class="small muted">The stage, 1360 × 768, moving as it will play</div>
      </div>
    </div>
  <//>`;
}

// ---- pack and cost --------------------------------------------------------------------------------------------
function Meter({ label, used, budget, title }) {
  const pct = budget ? (100 * used) / budget : 0;
  const kind = pct > 100 ? "err" : pct > 80 ? "warn" : "ok";
  return html`<div class="vm-meter" ...${tip(title)}>
    <div class="row small"><span class="vm-lbl">${label}</span><span class="sp"></span>
      <span class=${cx("mono", kind)}>${fmtBytes(used)}</span><span class="mono muted"> of ${fmtBytes(budget)}</span></div>
    <div class="vm-bar"><span class=${kind} style=${{ width: Math.min(100, pct).toFixed(1) + "%" }}></span></div>
  </div>`;
}

function Pack({ s }) {
  const r = s.report;
  return html`<${Card} title="Pack for the machine" sub="Trim the empty edges, pack into atlases, premultiply, and see what it costs" cls="vm-pack">
    <div class="row" style="gap:8px;flex-wrap:wrap">
      <${Seg} value=${s.machine} disabled=${s.packing} onChange=${(v) => call("vmodes.set_machine", v)}
        options=${(s.machines || []).map((m) => ({ value: m.key, label: m.label.replace("Stern ", "").replace(" (CGC, Spike 1)", "") , title: m.label }))} />
      <span class="sp"></span>
      <${Button} icon="search" disabled=${s.packing || !(s.pictures || []).length} busy=${s.packing} title=${T.check}
        onClick=${() => call("vmodes.pack", false)}>Check the cost<//>
      <${Button} kind="primary" icon="save" disabled=${s.packing || !(s.pictures || []).length || s.running} title=${T.write}
        onClick=${() => call("vmodes.pack", true)}>Pack for the card<//>
    </div>
    ${!r ? html`<div class="small muted vm-none">Check the cost to see what the pictures take on ${((s.machines || []).find((m) => m.key === s.machine) || {}).label || "the machine"}.</div>`
      : html`<div class="vm-report">
      ${r.budget ? html`<div class="vm-meters">
        <${Meter} label="Memory" used=${r.memory} budget=${r.budget.memory} title=${T.memory} />
        <${Meter} label="Card space" used=${r.card} budget=${r.budget.card} title=${T.card} />
      </div>
      <div class="row small" style="gap:6px;flex-wrap:wrap">
        ${(r.atlases || []).map((a, i) => html`<${Chip} sm title=${`Atlas ${i + 1}: ${fmtBytes(a.memory)} in memory, ${fmtBytes(a.card)} on the card`}>
          ${a.w} × ${a.h} · ${a.used_pct}% used<//>`)}
        <span class="muted">${r.frames} frames and glyphs, ${r.unique} kept after folding the same ones · packed in ${r.seconds} s
          · largest atlas ${r.budget.atlas} × ${r.budget.atlas} · ${r.budget.measured ? "budgets measured in the emulator" : "budgets are estimates until this machine is measured"}</span>
      </div>` : null}
      ${(r.problems || []).length ? html`<${Note} kind="err"><div class="stack" style="gap:4px">${r.problems.map((p) => html`<div>${p}</div>`)}</div><//>`
        : html`<${Note} kind="ok">Fits on ${r.label}.<//>`}
      ${s.written ? html`<div class=${cx("small", r.ok ? "ok" : "err")}>${s.written}</div>` : null}
      ${(r.sprites || []).length ? html`<table class="vm-cost">
        <thead><tr><th>Sprite</th><th class="n">Frames</th><th class="n">Kept</th><th class="n">Memory</th><th class="n">Card</th><th class="n">Share</th></tr></thead>
        <tbody>${r.sprites.map((sp) => html`<tr class=${cx(sp.font && "muted")}>
          <td class="ellip">${sp.font ? html`<span class="muted">font </span>${sp.id.slice(5)}` : sp.id}</td>
          <td class="n mono">${sp.frames}</td><td class="n mono">${sp.unique}</td>
          <td class="n mono">${fmtBytes(sp.memory)}</td><td class="n mono">${fmtBytes(sp.card)}</td>
          <td class="n"><span class="vm-share"><span style=${{ width: Math.min(100, sp.pct) + "%" }}></span></span><span class="mono small">${sp.pct}%</span></td>
        </tr>`)}</tbody>
      </table>` : null}
    </div>`}
  <//>`;
}

// ---- the page --------------------------------------------------------------------------------------------------
export default function VideoModesTab() {
  const s = useNs("vmodes");
  const [pick, setPick] = useState(null);
  const [playing, setPlaying] = useState(false);
  const pics = s.pictures || [];
  const sel = pics.find((p) => p.id === pick) || pics[0];
  const canPlay = s.available && s.slug && !(s.problems || []).length;
  useEffect(() => { if (!canPlay) setPlaying(false); }, [canPlay, s.slug]);
  if (playing && canPlay) return html`<div class="page vm-page vm-playing"><${VideoModePlayer} s=${s} onClose=${() => setPlaying(false)} /></div>`;
  const head = html`<${PageHead} title="Video modes" sub=${s.intro}>
    ${canPlay ? html`<${Button} kind="primary" icon="play" disabled=${s.running}
      title="Play this video mode here, with the keyboard, a gamepad or the mouse: the machine's own engine, built for the browser"
      onClick=${() => setPlaying(true)}>Play<//>` : null}
    ${s.available ? html`<${NewMode} />` : null}
    <${Button} icon="refresh" onClick=${() => call("vmodes.refresh")}>Read again<//>
  <//>`;
  if (!s.available) {
    return html`<div class="page vm-page">${head}<${Empty} title="Nothing to show here" icon="info">${s.why}<//></div>`;
  }
  const modes = s.modes || [];
  if (!modes.length) {
    return html`<div class="page vm-page">${head}
      <${Empty} title="No video modes yet" icon="play" action=${html`<${NewMode} />`}>
        A video mode is a short game on the screen, played with the flipper buttons and Action while the ball is held.
        Make one, then bring its pictures in.<//></div>`;
  }
  return html`<div class="page vm-page">
    ${head}
    <div class="vm-modes row" style="gap:6px;flex-wrap:wrap">
      ${modes.map((m) => html`<button type="button" class=${cx("vm-mode", m.slug === s.slug && "on", m.broken && "bad")}
        onClick=${() => call("vmodes.select", m.slug)} ...${tip(m.broken ? { head: "This file does not load", lines: [m.broken] } : null)}>
        <${Icon} name="play" /><span>${m.title}</span><span class="muted small mono">${m.pictures}</span></button>`)}
    </div>
    ${(s.problems || []).length ? html`<${Note} kind="err"><div class="stack" style="gap:4px">
      <b>This video mode's file does not load:</b>${s.problems.slice(0, 12).map((p) => html`<div>${p}</div>`)}</div><//>` : null}
    ${s.slug && !(s.problems || []).length ? html`
      <${Card} title="Pictures" sub="Sprites with their frames, and the pictures backgrounds are made of" cls="vm-pics"
        extra=${html`<${Button} kind="primary" icon="plus" disabled=${s.running} title=${T.add} onClick=${() => call("vmodes.pick")}>Bring art in…<//>`}>
        ${pics.length ? html`<div class="vm-grid">
          ${pics.map((p) => html`<${SpriteCard} p=${p} on=${sel && sel.id === p.id} onPick=${() => setPick(p.id)} />`)}
        </div>` : html`<${Empty} title="No pictures yet" icon="image"
            action=${html`<${Button} kind="primary" icon="plus" onClick=${() => call("vmodes.pick")}>Bring art in…<//>`}>
            A picture, a numbered run of PNGs, a GIF, a sprite sheet or a stretch of video.<//>`}
      <//>
      ${sel ? html`<${SpriteInspector} p=${sel} running=${s.running} />` : null}
      <${Backgrounds} s=${s} />
      <${Pack} s=${s} />` : null}
    ${s.draft ? html`<${ImportDialog} d=${s.draft} kinds=${s.kinds || []} />` : null}
  </div>`;
}
