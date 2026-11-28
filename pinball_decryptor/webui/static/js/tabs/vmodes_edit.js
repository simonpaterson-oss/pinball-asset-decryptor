// The video mode editor (PAD-1661): the stage, the layers and the inspector, held to the plan's design language
// (docs/plans/video_mode_maker.md, section 6).
//
// The stage IS the engine: the machine's own engine (vm_engine.wasm, the same C the machine runs) takes a still of
// the phase (vm_edit_still: its first step, past the opening transition) and the player's WebGL backend draws it.
// A drag rewrites the places it moves in the engine's loaded tables (vmw_place_set) and takes the still again, every
// frame, so what the editor shows while dragging is what the engine draws; selection boxes come from the engine's
// own geometry (vmw_place_boxes). Panels never re-render on a drag frame: the drag lives in this controller and is
// committed when the pointer lets go.
//
// Every change is the whole document sent to vmodes.edit_commit: checked, saved (no save button) and kept as one
// step of an undo history that has no limit and survives a reload (core/video_mode/history.py). Groups and guides
// are the editor's own state, in the document's free-form `editor` object.

import { html, useEffect, useLayoutEffect, useMemo, useRef, useState, Button, Select, Icon, Empty, tip, call, cx,
         mediaUrl } from "../core/ui.js";
import { GLStage, TEAM_HEX, newEngine, loadImage, placeholderSheet, glyphSheet, b64bytes } from "./vmodes_play.js";

const TEAMS = ["player", "enemy", "enemy_shot", "player_shot", "pickup", "health", "scenery"];
const TEAM_LABEL = { player: "Player", enemy: "Enemy", enemy_shot: "Enemy shot", player_shot: "Player shot",
                     pickup: "Pickup", health: "Health", scenery: "Scenery" };
const TEAM_TOKEN = { player: "--info", enemy: "--err", enemy_shot: "--warn", player_shot: "--warn", pickup: "--ok",
                     health: "--ok", scenery: "--ink-3" };
const MOVERS = [["none", "Stays put"], ["straight", "Straight"], ["lanes", "In lanes (the player steers)"],
                ["free", "Free (the player steers)"], ["thrust", "Thrust (rise and fall)"], ["path", "Along a path"],
                ["home", "Homes on a target"], ["scroll", "Scrolls with the world"], ["orbit", "Orbits"]];
const EASINGS = ["linear", "in", "out", "in_out", "back_out", "bounce_out", "elastic_out", "step"];
const HANDLE = 8, TURN_GAP = 24, SNAP_PX = 6, RULER = 20, NUDGE_BIG = 10, PASTE_OFF = 16;
const DOCKS = { left: [240, 200, 360], right: [300, 260, 420] };

const T = {
  done: "Back to the mode's pictures and backgrounds",
  undo: (l) => (l ? "Undo: " + l + " (Ctrl Z)" : "Nothing to undo"),
  redo: (l) => (l ? "Redo: " + l + " (Ctrl Shift Z)" : "Nothing to redo"),
  play: "Play this phase in the app's player (F5)",
  saved: "Every change is saved as you make it, and every change is a step you can undo, even after a reload",
  grid: "Show the grid; things snap to it while Snap is on",
  snap: "Snap to the grid, the guides, the stage, the safe area and to other things, with the distance shown. Hold Ctrl while dragging to place freely",
  hits: "Show the hit boxes, in the team's color (H)",
  safe: "Show the safe area: inside every machine's visible glass",
  bezel: "Show the machine's glass around the stage: the dot-matrix band, or the frame of a screen",
  title: "Show the phase's title card on the stage, as the game opens the phase",
  fit: "Zoom to fit (Ctrl 0)", one: "100% (Ctrl 1)",
  palette: "Every command, by name (Ctrl K)",
  keys: "The shortcuts (?)",
  scrub: "Drag the label sideways to change it (Shift: 10 times as fast, Alt: a tenth); or type a number",
  shared: (n) => (n > 1 ? "Shared by the " + n + " placed things of this kind, in every phase" : "This kind of thing's own settings"),
};

// ---- small helpers ---------------------------------------------------------------------------------------------
const clone = (o) => JSON.parse(JSON.stringify(o));
const r2 = (v) => Math.round(v * 100) / 100;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const typing = (el) => !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
const thingOf = (doc, id) => (doc.things || []).find((t) => t.id === id);
const pictureOf = (doc, id) => ((doc.assets || {}).pictures || []).find((p) => p.id === id);
function uniqueId(taken, base) {
  base = String(base || "thing").toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^[^a-z]+/, "") || "thing";
  base = base.slice(0, 36);
  if (!taken.has(base)) return base;
  for (let n = 2; ; n++) if (!taken.has(base + "_" + n)) return base + "_" + n;
}
function idsInUse(doc) {
  return new Set([...(doc.things || []).map((t) => t.id), ...(doc.values || []).map((v) => v.id)]);
}
function effDepth(doc, pl) {
  if (pl.depth != null) return pl.depth;
  const t = thingOf(doc, pl.thing);
  return t && t.depth != null ? t.depth : 0;
}
// back to front, as the engine draws them: by depth, then in place order
function drawOrder(doc, ph) {
  const pls = ph.place || [];
  return pls.map((_, i) => i).sort((a, b) => effDepth(doc, pls[a]) - effDepth(doc, pls[b]) || a - b);
}
function groupsOf(doc, ph) {
  const g = (doc.editor && doc.editor.groups) || {};
  return (g[ph.id] || []).filter((m) => Array.isArray(m) && m.length > 1);
}
function setGroups(doc, ph, list) {
  doc.editor = doc.editor || {};
  const g = Object.assign({}, doc.editor.groups || {});
  const keep = list.filter((m) => m.length > 1);
  if (keep.length) g[ph.id] = keep; else delete g[ph.id];
  if (Object.keys(g).length) doc.editor.groups = g; else delete doc.editor.groups;
}
// places renumbered: map[old] = new index or -1 (gone); groups follow
function remapGroups(doc, ph, map) {
  setGroups(doc, ph, groupsOf(doc, ph).map((m) => m.map((i) => map[i]).filter((i) => i != null && i >= 0)));
}
function guidesOf(doc) { const g = (doc.editor && doc.editor.guides) || {}; return { x: g.x || [], y: g.y || [] }; }
function setGuides(doc, gd) {
  doc.editor = doc.editor || {};
  if (gd.x.length || gd.y.length) doc.editor.guides = { x: gd.x.map(r2), y: gd.y.map(r2) };
  else delete doc.editor.guides;
}
function cleanPlace(pl) {
  for (const k of ["hidden", "locked"]) if (!pl[k]) delete pl[k];
  if (pl.scale === 1) delete pl.scale;
  if (!pl.turn) delete pl.turn;
  pl.x = r2(pl.x); pl.y = r2(pl.y);
  if (pl.scale != null) pl.scale = Math.round(pl.scale * 1000) / 1000;
  if (pl.turn != null) pl.turn = r2(((pl.turn + 540) % 360) - 180);
  return pl;
}
function polyOf(b) {
  const r = (b.turn || 0) * Math.PI / 180, c = Math.cos(r), s = Math.sin(r);
  return [[b.x0, b.y0], [b.x1, b.y0], [b.x1, b.y1], [b.x0, b.y1]].map(([lx, ly]) => [b.x + lx * c - ly * s, b.y + lx * s + ly * c]);
}
function aabbOf(b) {
  const p = polyOf(b);
  const xs = p.map((q) => q[0]), ys = p.map((q) => q[1]);
  return { l: Math.min(...xs), t: Math.min(...ys), r: Math.max(...xs), b: Math.max(...ys) };
}
function unite(list) {
  if (!list.length) return null;
  return list.reduce((a, b) => ({ l: Math.min(a.l, b.l), t: Math.min(a.t, b.t), r: Math.max(a.r, b.r), b: Math.max(a.b, b.b) }));
}
function inside(b, x, y) {
  const r = -(b.turn || 0) * Math.PI / 180, c = Math.cos(r), s = Math.sin(r), dx = x - b.x, dy = y - b.y;
  const lx = dx * c - dy * s, ly = dx * s + dy * c;
  return lx >= Math.min(b.x0, b.x1) && lx <= Math.max(b.x0, b.x1) && ly >= Math.min(b.y0, b.y1) && ly <= Math.max(b.y0, b.y1);
}
function loadDocks() {
  try { return Object.assign({ left: 240, right: 300, leftOpen: true, rightOpen: true }, JSON.parse(localStorage.getItem("vme.docks") || "{}")); }
  catch (e) { return { left: 240, right: 300, leftOpen: true, rightOpen: true }; }
}
function loadOpts() {
  const d = { grid: true, snap: true, hits: false, safe: true, bezel: false, title: false };
  try { return Object.assign(d, JSON.parse(localStorage.getItem("vme.view") || "{}")); } catch (e) { return d; }
}
let clipboard = null;            // the editor's own copy and paste: {things, places, from}

// ---- the controller: the engine's still, the overlay and every interaction on the stage ------------------------
class Ed {
  constructor(info, eng, gl, els, notify) {
    this.info = info; this.e = eng; this.gl = gl; this.els = els; this.notify = notify;
    this.doc = info.doc; this.ph = 0; this.sel = []; this.hover = -1; this.hoverLocked = -1;
    this.place0 = info.place0 || []; this.packOk = !!info.pack; this.packCounts = this.counts(this.doc);
    this.hist = info.history || {}; this.status = { kind: "ok", text: "Saved" };
    this.opts = loadOpts(); this.view = { k: 1, ox: 0, oy: 0, fit: true };
    this.boxes = []; this.hitList = null; this.preview = null; this.drag = null; this.snaps = [];
    this.space = false; this.queue = Promise.resolve(); this.dirtyFlag = false; this.raf = 0; this.needSync = true;
    this.cursor = null; this.perfReset();
    this.colours();
  }
  counts(doc) { return (doc.phases || []).map((p) => (p.place || []).length); }
  phase() { return this.doc.phases[this.ph]; }
  places() { return this.phase().place || []; }
  colours() {
    const c = (n) => cssVar(n) || "#888";
    this.c = { accent: c("--accent"), accentLine: c("--accent-line") || c("--accent"), info: c("--info"), panel: c("--panel"),
               line: c("--line"), ink: c("--ink"), ink3: c("--ink-3"), bg: c("--bg"), err: c("--err"), warn: c("--warn"), ok: c("--ok"),
               mono: (cssVar("--mono") || "monospace") };
    const m = /#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i.exec(this.c.bg) || [0, "10", "10", "10"];
    this.bgRGB = [parseInt(m[1], 16) / 255, parseInt(m[2], 16) / 255, parseInt(m[3], 16) / 255];
  }
  teamColour(team) { return cssVar(TEAM_TOKEN[team] || "--ink-3") || TEAM_HEX[team] || "#888"; }

  // -- view ------------------------------------------------------------------------------------------------------
  size() { const r = this.els.view.getBoundingClientRect(); return { w: Math.max(1, r.width), h: Math.max(1, r.height) }; }
  fit() {
    const { w, h } = this.size(), W = this.info.stage[0], H = this.info.stage[1], pad = 28;
    const k = Math.max(0.05, Math.min((w - 2 * pad) / W, (h - 2 * pad) / H));
    this.view = { k, ox: (w - W * k) / 2, oy: (h - H * k) / 2, fit: true };
    this.dirty(true);
  }
  zoomAt(k, cx, cy) {
    k = clamp(k, 0.05, 16);
    const v = this.view, sx = (cx - v.ox) / v.k, sy = (cy - v.oy) / v.k;
    this.view = { k, ox: cx - sx * k, oy: cy - sy * k, fit: false };
    this.dirty(true);
  }
  zoomTo(k) { const { w, h } = this.size(); this.zoomAt(k, w / 2, h / 2); }
  toStage(cx, cy) { const v = this.view; return [(cx - v.ox) / v.k, (cy - v.oy) / v.k]; }
  toView(x, y) { const v = this.view; return [x * v.k + v.ox, y * v.k + v.oy]; }
  local(e) { const r = this.els.view.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }

  // -- drawing ---------------------------------------------------------------------------------------------------
  dirty(rulers = false) {
    if (rulers) this.rulersDirty = true;
    if (this.raf) return;
    this.raf = requestAnimationFrame((t) => { this.raf = 0; this.render(t); });
  }
  sync() {
    // the document's places into the engine's tables (a change not yet in the pack: a move, a hide, a depth)
    const doc = this.doc;
    const same = this.counts(doc).every((n, i) => n === this.packCounts[i]) && this.counts(doc).length === this.packCounts.length;
    this.syncOk = same;
    if (!same || !this.packOk) return;
    doc.phases.forEach((ph, pi) => (ph.place || []).forEach((pl, i) => {
      this.e.placeSet(this.place0[pi] + i, pl.x, pl.y, pl.scale == null ? 1 : pl.scale, pl.turn || 0,
        pl.depth == null ? null : pl.depth, !!pl.hidden);
    }));
  }
  render(t) {
    const t0 = performance.now();
    const { w, h } = this.size(), dpr = window.devicePixelRatio || 1;
    const cw = Math.round(w * dpr), ch = Math.round(h * dpr);
    const gl = this.gl, ov = this.els.over;
    gl.resize(cw, ch);
    if (ov.width !== cw || ov.height !== ch) { ov.width = cw; ov.height = ch; }
    if (this.view.fit && (this.lastW !== w || this.lastH !== h)) { this.lastW = w; this.lastH = h; this.fit(); }
    const v = this.view;
    gl.setView(v.k * dpr, v.ox * dpr, v.oy * dpr, cw, ch, this.bgRGB);
    if (this.needSync) { this.sync(); this.needSync = false; }
    if (this.packOk) {          // a newer pack on its way: the last one stays drawn meanwhile, never a blank stage
      if (this.preview && this.syncOk) {
        for (const [i, pl] of this.preview) {
          this.e.placeSet(this.place0[this.ph] + i, pl.x, pl.y, pl.scale == null ? 1 : pl.scale, pl.turn || 0,
            pl.depth == null ? null : pl.depth, !!pl.hidden);
        }
      }
      this.e.editStill(this.ph, this.opts.title ? 1 : 0);
      this.drawn = gl.draw(this.e.drawWords());
      this.boxes = this.e.placeBoxes();
      this.hitList = this.opts.hits ? this.e.hitBoxes() : null;
    } else {
      gl.draw(new Int32Array([0, 0, 0, 0, 0, 0, parseInt((this.doc.stage.background || "#000000").slice(1, 7), 16) * 256 + 255, 0]));
      if (!this.packOk) this.boxes = [];
    }
    this.overlay(dpr);
    if (this.rulersDirty || this.drag) { this.rulers(dpr); this.rulersDirty = false; }
    const t1 = performance.now();
    if (this.drag && this.drag.moved) {
      if (this.lastFrame) this.pf.gaps.push(t1 - this.lastFrame);
      this.pf.work.push(t1 - t0);
    }
    this.lastFrame = this.drag ? t1 : 0;
  }
  perfReset() { this.pf = { gaps: [], work: [] }; }
  perf() {
    const g = this.pf.gaps.slice().sort((a, b) => a - b), wk = this.pf.work.slice().sort((a, b) => a - b);
    const avg = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);
    const pct = (a, p) => (a.length ? a[Math.min(a.length - 1, Math.floor(a.length * p))] : 0);
    return { frames: g.length, fps: g.length ? 1000 / avg(g) : 0, gap_avg_ms: avg(g), gap_p95_ms: pct(g, 0.95),
             gap_worst_ms: g.length ? g[g.length - 1] : 0, work_avg_ms: avg(wk), work_p95_ms: pct(wk, 0.95),
             things: this.places().length };
  }
  shape(i) {
    const b = this.boxes[i];
    return b && b.alive ? b : null;
  }
  selBounds(list = this.sel) {
    return unite(list.map((i) => this.shape(i)).filter(Boolean).map(aabbOf));
  }
  handles() {
    // the selection's frame: one thing turned with it, several as their bounds
    if (!this.sel.length) return null;
    if (this.sel.length === 1) {
      const b = this.shape(this.sel[0]);
      if (!b) return null;
      return { poly: polyOf(b), turn: b.turn || 0, single: b };
    }
    const u = this.selBounds();
    if (!u) return null;
    return { poly: [[u.l, u.t], [u.r, u.t], [u.r, u.b], [u.l, u.b]], turn: 0 };
  }
  handlePoints(hd) {
    // 0..7: nw, n, ne, e, se, s, sw, w (stage px); 8: the turn handle
    const [a, b, c, d] = hd.poly, mid = (p, q) => [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
    const pts = [a, mid(a, b), b, mid(b, c), c, mid(c, d), d, mid(d, a)];
    const top = pts[1], r = hd.turn * Math.PI / 180, gap = TURN_GAP / this.view.k;
    pts.push([top[0] + Math.sin(r) * gap, top[1] - Math.cos(r) * gap]);
    return pts;
  }
  overlay(dpr) {
    const g = this.els.over.getContext("2d"), v = this.view, c = this.c, W = this.info.stage[0], H = this.info.stage[1];
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, this.els.over.width, this.els.over.height);
    const P = (x, y) => [x * v.k + v.ox, y * v.k + v.oy];
    const line = (x0, y0, x1, y1) => { g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke(); };
    const poly = (pts) => { g.beginPath(); pts.forEach((p, i) => { const q = P(p[0], p[1]); if (i) g.lineTo(q[0] + 0.5, q[1] + 0.5); else g.moveTo(q[0] + 0.5, q[1] + 0.5); }); g.closePath(); };
    const [sx0, sy0] = P(0, 0), [sx1, sy1] = P(W, H);
    // the grid
    const grid = this.grid();
    if (this.opts.grid && grid * v.k >= 6) {
      g.strokeStyle = c.ink; g.globalAlpha = 0.07; g.lineWidth = 1;
      g.beginPath();
      for (let x = 0; x <= W; x += grid) { const q = Math.round(x * v.k + v.ox) + 0.5; g.moveTo(q, sy0); g.lineTo(q, sy1); }
      for (let y = 0; y <= H; y += grid) { const q = Math.round(y * v.k + v.oy) + 0.5; g.moveTo(sx0, q); g.lineTo(sx1, q); }
      g.stroke(); g.globalAlpha = 1;
    }
    // the stage's edge
    g.strokeStyle = c.line; g.lineWidth = 1; g.strokeRect(Math.round(sx0) - 0.5, Math.round(sy0) - 0.5, Math.round(sx1 - sx0) + 1, Math.round(sy1 - sy0) + 1);
    // the machine's glass
    if (this.opts.bezel) this.bezel(g, P, W, H);
    // the safe area
    const safe = this.doc.stage.safe;
    if (this.opts.safe && safe) {
      const [a, b] = P(safe.x, safe.y);
      g.strokeStyle = c.info; g.globalAlpha = 0.7; g.setLineDash([6, 5]);
      g.strokeRect(Math.round(a) + 0.5, Math.round(b) + 0.5, Math.round(safe.w * v.k), Math.round(safe.h * v.k));
      g.setLineDash([]); g.globalAlpha = 1;
    }
    // guides
    const gd = this.guideView();
    g.lineWidth = 1;
    for (const ax of ["x", "y"]) gd[ax].forEach((val, i) => {
      const on = this.drag && this.drag.type === "guide" && this.drag.axis === ax && this.drag.i === i;
      g.strokeStyle = on ? c.accent : c.info; g.globalAlpha = on ? 1 : 0.8;
      if (ax === "x") { const q = Math.round(val * v.k + v.ox) + 0.5; line(q, 0, q, 99999); }
      else { const q = Math.round(val * v.k + v.oy) + 0.5; line(0, q, 99999, q); }
      g.globalAlpha = 1;
    });
    // hit boxes, in their team's colours (H)
    if (this.hitList) {
      for (let i = 0; i < this.hitList.length; i += 6) {
        const col = this.teamColour(TEAMS[this.hitList[i]] || "scenery");
        const x = this.hitList[i + 2] / 65536, y = this.hitList[i + 3] / 65536, w = this.hitList[i + 4] / 65536, h = this.hitList[i + 5] / 65536;
        g.strokeStyle = col; g.fillStyle = col; g.lineWidth = 1;
        g.beginPath();
        if (this.hitList[i + 1] === 1) { const [cx, cy] = P(x, y); g.arc(cx, cy, w * v.k, 0, Math.PI * 2); }
        else { const [a, b] = P(x, y); g.rect(a + 0.5, b + 0.5, w * v.k, h * v.k); }
        g.globalAlpha = 0.2; g.fill(); g.globalAlpha = 1; g.stroke();
      }
    }
    // things left behind by a duplicating drag
    if (this.drag && this.drag.dup && this.drag.moved) {
      g.strokeStyle = c.accent; g.setLineDash([4, 4]); g.globalAlpha = 0.7;
      for (const pts of this.drag.ghosts) { poly(pts); g.stroke(); }
      g.setLineDash([]); g.globalAlpha = 1;
    }
    // hover
    if (this.hover >= 0 && !this.sel.includes(this.hover) && !this.drag) {
      const b = this.shape(this.hover);
      if (b) { g.strokeStyle = c.accentLine; g.lineWidth = 1; poly(polyOf(b)); g.stroke(); }
    }
    if (this.hoverLocked >= 0 && !this.drag) {
      const b = this.shape(this.hoverLocked);
      if (b) {
        const u = aabbOf(b), [x, y] = P(u.r, u.t);
        g.fillStyle = c.panel; g.strokeStyle = c.line; g.beginPath(); g.roundRect(x - 22, y + 4, 18, 18, 4); g.fill(); g.stroke();
        g.strokeStyle = c.ink; g.lineWidth = 1.4;
        g.strokeRect(x - 17.5, y + 12.5, 9, 6); g.beginPath(); g.arc(x - 13, y + 12, 3, Math.PI, 0); g.stroke();
      }
    }
    // the selection
    const hd = this.handles();
    if (hd) {
      g.strokeStyle = c.accent; g.lineWidth = 1;
      if (this.sel.length > 1) {
        g.setLineDash([3, 3]);
        for (const i of this.sel) { const b = this.shape(i); if (b) { poly(polyOf(b)); g.stroke(); } }
        g.setLineDash([]);
      }
      poly(hd.poly); g.stroke();
      const locked = this.sel.every((i) => (this.places()[i] || {}).locked);
      if (!locked && !(this.drag && this.drag.moved && this.drag.type === "move")) {
        const pts = this.handlePoints(hd);
        const [tx, ty] = P(pts[8][0], pts[8][1]), [mx, my] = P(pts[1][0], pts[1][1]);
        line(mx + 0.5, my + 0.5, tx + 0.5, ty + 0.5);
        g.fillStyle = c.panel;
        g.beginPath(); g.arc(tx + 0.5, ty + 0.5, 5, 0, Math.PI * 2); g.fill(); g.stroke();
        for (let k = 0; k < 8; k++) {
          const [x, y] = P(pts[k][0], pts[k][1]);
          g.fillRect(Math.round(x - HANDLE / 2) + 0.5, Math.round(y - HANDLE / 2) + 0.5, HANDLE, HANDLE);
          g.strokeRect(Math.round(x - HANDLE / 2) + 0.5, Math.round(y - HANDLE / 2) + 0.5, HANDLE, HANDLE);
        }
      }
      if (hd.single) {                              // the anchor: a small cross
        const [x, y] = P(hd.single.x, hd.single.y);
        g.strokeStyle = c.accent; line(x - 5, y + 0.5, x + 6, y + 0.5); line(x + 0.5, y - 5, x + 0.5, y + 6);
      }
    }
    // snap guides and their distances
    if (this.snaps.length) {
      g.strokeStyle = c.info; g.lineWidth = 1;
      g.font = "500 11px " + c.mono; g.textBaseline = "middle"; g.textAlign = "center";
      for (const s of this.snaps) {
        const [a0, b0] = P(s.x0, s.y0), [a1, b1] = P(s.x1, s.y1);
        line(Math.round(a0) + 0.5, Math.round(b0) + 0.5, Math.round(a1) + 0.5, Math.round(b1) + 0.5);
        if (s.label) {
          const [lx, ly] = P(s.lx, s.ly), tw = g.measureText(s.label).width + 10;
          g.fillStyle = c.panel; g.beginPath(); g.roundRect(lx - tw / 2, ly - 9, tw, 18, 4); g.fill(); g.stroke();
          g.fillStyle = c.info; g.fillText(s.label, lx, ly + 0.5);
        }
      }
    }
    // the marquee
    if (this.drag && this.drag.type === "marquee" && this.drag.moved) {
      const [a, b] = P(Math.min(this.drag.x0, this.drag.x1), Math.min(this.drag.y0, this.drag.y1));
      const w = Math.abs(this.drag.x1 - this.drag.x0) * v.k, h = Math.abs(this.drag.y1 - this.drag.y0) * v.k;
      g.fillStyle = c.accent; g.globalAlpha = 0.08; g.fillRect(a, b, w, h); g.globalAlpha = 1;
      g.strokeStyle = c.accent; g.strokeRect(Math.round(a) + 0.5, Math.round(b) + 0.5, Math.round(w), Math.round(h));
    }
  }
  bezel(g, P, W, H) {
    const [x0, y0] = P(0, 0), [x1, y1] = P(W, H);
    g.save();
    if (this.info.machine === "dots") {
      const top = ((this.doc.stage.dots || {}).band_top != null ? this.doc.stage.dots.band_top : 214);
      const [, a] = P(0, top), [, b] = P(0, top + 340);
      g.fillStyle = "#000"; g.globalAlpha = 0.62;
      g.fillRect(x0, y0, x1 - x0, a - y0); g.fillRect(x0, b, x1 - x0, y1 - b);
      g.globalAlpha = 1; g.strokeStyle = "#ff8a1e"; g.lineWidth = 2; g.strokeRect(x0 - 1, a - 1, x1 - x0 + 2, b - a + 2);
    } else {
      const k = this.view.k, t = Math.max(6, 26 * k);
      g.strokeStyle = "#0b0b0c"; g.lineWidth = t;
      g.beginPath(); g.roundRect(x0 - t / 2, y0 - t / 2, x1 - x0 + t, y1 - y0 + t, t * 0.6); g.stroke();
      g.strokeStyle = "rgba(255,255,255,.12)"; g.lineWidth = 1;
      g.beginPath(); g.roundRect(x0 - t, y0 - t, x1 - x0 + 2 * t, y1 - y0 + 2 * t, t); g.stroke();
    }
    g.restore();
  }
  rulers(dpr) {
    const v = this.view, c = this.c;
    for (const ax of ["x", "y"]) {
      const cv = this.els["ruler" + ax.toUpperCase()];
      if (!cv) continue;
      const r = cv.getBoundingClientRect(), w = Math.max(1, Math.round(r.width * dpr)), h = Math.max(1, Math.round(r.height * dpr));
      if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
      const g = cv.getContext("2d");
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, r.width, r.height);
      const len = ax === "x" ? r.width : r.height, off = ax === "x" ? v.ox : v.oy;
      // the selection's extent, faintly
      const u = this.selBounds();
      if (u) {
        g.fillStyle = c.accent; g.globalAlpha = 0.16;
        const a = (ax === "x" ? u.l : u.t) * v.k + off, b = (ax === "x" ? u.r : u.b) * v.k + off;
        if (ax === "x") g.fillRect(a, 0, b - a, r.height); else g.fillRect(0, a, r.width, b - a);
        g.globalAlpha = 1;
      }
      let step = 10;
      for (const s of [10, 20, 50, 100, 200, 500, 1000]) { step = s; if (s * v.k >= 56) break; }
      const minor = step / 5;
      g.strokeStyle = c.ink3; g.fillStyle = c.ink3; g.lineWidth = 1;
      g.font = "10px " + c.mono; g.textBaseline = "top"; g.textAlign = "left";
      const first = Math.floor(-off / v.k / minor) * minor, last = (len - off) / v.k;
      g.beginPath();
      for (let s = first; s <= last; s += minor) {
        const q = Math.round(s * v.k + off) + 0.5, major = Math.abs(s / step - Math.round(s / step)) < 1e-6;
        const tl = major ? RULER : 5;
        if (ax === "x") { g.moveTo(q, RULER - tl); g.lineTo(q, RULER); } else { g.moveTo(RULER - tl, q); g.lineTo(RULER, q); }
      }
      g.stroke();
      for (let s = Math.ceil(first / step) * step; s <= last; s += step) {
        const q = Math.round(s * v.k + off);
        if (ax === "x") g.fillText(String(Math.round(s)), q + 3, 2);
        else { g.save(); g.translate(2, q + 3); g.rotate(Math.PI / 2); g.fillText(String(Math.round(s)), 0, -8); g.restore(); }
      }
      if (this.cursor) {
        const q = Math.round((ax === "x" ? this.cursor[0] : this.cursor[1]) * v.k + off) + 0.5;
        g.strokeStyle = c.accent; g.beginPath();
        if (ax === "x") { g.moveTo(q, 0); g.lineTo(q, RULER); } else { g.moveTo(0, q); g.lineTo(RULER, q); }
        g.stroke();
      }
    }
  }
  grid() { const e = this.doc.editor || {}; return clamp(Number(e.grid) || 8, 2, 256); }
  guideView() {
    const gd = guidesOf(this.doc);
    if (this.drag && this.drag.type === "guide") {
      const out = { x: gd.x.slice(), y: gd.y.slice() };
      if (this.drag.i < 0) out[this.drag.axis].push(this.drag.val);
      else out[this.drag.axis][this.drag.i] = this.drag.val;
      return out;
    }
    return gd;
  }

  // -- hit testing -----------------------------------------------------------------------------------------------
  hitTest(x, y, withLocked = false) {
    const order = drawOrder(this.doc, this.phase()), pls = this.places();
    for (let k = order.length - 1; k >= 0; k--) {
      const i = order[k], b = this.shape(i), pl = pls[i];
      if (!b || pl.hidden || (pl.locked && !withLocked)) continue;
      if (inside(b, x, y)) return i;
    }
    return -1;
  }
  groupOf(i) {
    const g = groupsOf(this.doc, this.phase()).find((m) => m.includes(i));
    return g ? g.slice() : [i];
  }
  handleAt(cx, cy) {
    const hd = this.handles();
    if (!hd || this.sel.every((i) => (this.places()[i] || {}).locked)) return -1;
    const pts = this.handlePoints(hd);
    for (let k = 8; k >= 0; k--) {
      const [x, y] = this.toView(pts[k][0], pts[k][1]);
      if (Math.abs(cx - x) <= HANDLE && Math.abs(cy - y) <= HANDLE) return k;
    }
    return -1;
  }
  guideAt(cx, cy) {
    const gd = guidesOf(this.doc);
    for (const ax of ["x", "y"]) for (let i = 0; i < gd[ax].length; i++) {
      const q = ax === "x" ? gd.x[i] * this.view.k + this.view.ox : gd.y[i] * this.view.k + this.view.oy;
      if (Math.abs((ax === "x" ? cx : cy) - q) <= 3) return { axis: ax, i };
    }
    return null;
  }

  // -- snapping --------------------------------------------------------------------------------------------------
  snapTargets(skip) {
    const W = this.info.stage[0], H = this.info.stage[1], xs = [], ys = [];
    const add = (arr, v, kind, box) => arr.push({ v, kind, box });
    for (const v of [0, W / 2, W]) add(xs, v, "stage");
    for (const v of [0, H / 2, H]) add(ys, v, "stage");
    const safe = this.doc.stage.safe;
    if (safe && this.opts.safe) { add(xs, safe.x, "safe"); add(xs, safe.x + safe.w, "safe"); add(ys, safe.y, "safe"); add(ys, safe.y + safe.h, "safe"); }
    const gd = guidesOf(this.doc);
    gd.x.forEach((v) => add(xs, v, "guide")); gd.y.forEach((v) => add(ys, v, "guide"));
    this.places().forEach((pl, i) => {
      if (skip.has(i) || pl.hidden) return;
      const b = this.shape(i);
      if (!b) return;
      const u = aabbOf(b);
      add(xs, u.l, "thing", u); add(xs, (u.l + u.r) / 2, "thing", u); add(xs, u.r, "thing", u);
      add(ys, u.t, "thing", u); add(ys, (u.t + u.b) / 2, "thing", u); add(ys, u.b, "thing", u);
    });
    return { xs, ys };
  }
  // the selection's bounds u moved by (dx, dy): the snapped move and the lines that show it
  snapMove(u, dx, dy, targets, free) {
    this.snaps = [];
    if (free || !this.opts.snap) return [dx, dy];
    const thr = SNAP_PX / this.view.k, grid = this.grid();
    const pick = (edges, list, gridOn) => {
      let best = null;
      for (const e of edges) for (const t of list) {
        const d = t.v - e;
        if (Math.abs(d) <= thr && (!best || Math.abs(d) < Math.abs(best.d))) best = { d, t, e };
      }
      if (!best && gridOn && this.opts.grid) {
        const d = Math.round(edges[0] / grid) * grid - edges[0];
        if (Math.abs(d) <= thr) best = { d, t: null, e: edges[0] };
      }
      return best;
    };
    const L = u.l + dx, R = u.r + dx, Tp = u.t + dy, B = u.b + dy;
    const bx = pick([L, (L + R) / 2, R], targets.xs, true), by = pick([Tp, (Tp + B) / 2, B], targets.ys, true);
    if (bx) dx += bx.d;
    if (by) dy += by.d;
    const nu = { l: u.l + dx, r: u.r + dx, t: u.t + dy, b: u.b + dy };
    const H = this.info.stage[1], W = this.info.stage[0];
    const lineFor = (best, axis) => {
      if (!best || !best.t) return;
      const v = best.t.v;
      if (best.t.kind === "thing") {
        const o = best.t.box;
        if (axis === "x") {
          const y0 = Math.min(nu.t, o.t), y1 = Math.max(nu.b, o.b);
          const s = { x0: v, y0, x1: v, y1 };
          const gap = nu.t > o.b ? nu.t - o.b : o.t > nu.b ? o.t - nu.b : 0;
          if (gap > 0) { s.label = Math.round(gap) + " px"; s.lx = v; s.ly = nu.t > o.b ? (o.b + nu.t) / 2 : (nu.b + o.t) / 2; }
          this.snaps.push(s);
        } else {
          const x0 = Math.min(nu.l, o.l), x1 = Math.max(nu.r, o.r);
          const s = { x0, y0: v, x1, y1: v };
          const gap = nu.l > o.r ? nu.l - o.r : o.l > nu.r ? o.l - nu.r : 0;
          if (gap > 0) { s.label = Math.round(gap) + " px"; s.ly = v; s.lx = nu.l > o.r ? (o.r + nu.l) / 2 : (nu.r + o.l) / 2; }
          this.snaps.push(s);
        }
      } else if (axis === "x") this.snaps.push({ x0: v, y0: 0, x1: v, y1: H });
      else this.snaps.push({ x0: 0, y0: v, x1: W, y1: v });
    };
    lineFor(bx, "x"); lineFor(by, "y");
    return [dx, dy];
  }

  // -- pointer -----------------------------------------------------------------------------------------------------
  down(e) {
    if (e.button === 2) return;
    this.els.view.focus({ preventScroll: true });
    const [cx, cy] = this.local(e), [x, y] = this.toStage(cx, cy);
    this.els.view.setPointerCapture(e.pointerId);
    if (this.space || e.button === 1) { this.drag = { type: "pan", cx, cy, ox: this.view.ox, oy: this.view.oy }; this.els.view.style.cursor = "grabbing"; return; }
    const hk = this.handleAt(cx, cy);
    if (hk >= 0) { this.startTransform(hk === 8 ? "turn" : "scale", hk, x, y); return; }
    const gi = this.guideAt(cx, cy);
    const i = this.hitTest(x, y);
    if (gi && i < 0) {
      const gd = guidesOf(this.doc);
      this.drag = { type: "guide", axis: gi.axis, i: gi.i, val: gd[gi.axis][gi.i], start: gd[gi.axis][gi.i] };
      return;
    }
    if (i >= 0) {
      const grp = this.groupOf(i);
      if (e.shiftKey) {
        const has = grp.every((k) => this.sel.includes(k));
        this.setSel(has ? this.sel.filter((k) => !grp.includes(k)) : [...new Set([...this.sel, ...grp])]);
        if (has) return;
      } else if (!this.sel.includes(i)) this.setSel(grp);
      this.startMove(x, y, e.altKey, i);
      return;
    }
    if (!e.shiftKey && this.sel.length) this.setSel([]);
    this.drag = { type: "marquee", x0: x, y0: y, x1: x, y1: y, base: e.shiftKey ? this.sel.slice() : [] };
  }
  startMove(x, y, dup, clicked) {
    const pls = this.places(), sel = this.sel.filter((k) => !pls[k].locked);
    if (!sel.length) return;
    const u = this.selBounds(sel);
    this.drag = { type: "move", x0: x, y0: y, sel, orig: new Map(sel.map((k) => [k, Object.assign({}, pls[k])])), u,
                  targets: this.snapTargets(new Set(sel)), dup, clicked,
                  ghosts: sel.map((k) => this.shape(k)).filter(Boolean).map(polyOf) };
  }
  startTransform(type, hk, x, y) {
    const pls = this.places(), sel = this.sel.filter((k) => !pls[k].locked);
    if (!sel.length) return;
    const hd = this.handles(), pts = this.handlePoints(hd);
    const opp = [4, 5, 6, 7, 0, 1, 2, 3][hk] ?? 0;
    const u = this.selBounds(sel);
    const centre = hd.single ? [hd.single.x, hd.single.y] : [(u.l + u.r) / 2, (u.t + u.b) / 2];
    this.drag = { type, hk, x0: x, y0: y, sel, orig: new Map(sel.map((k) => [k, Object.assign({}, pls[k])])),
                  fixed: pts[opp], grab: pts[hk], centre, a0: Math.atan2(y - centre[1], x - centre[0]), turn: hd.turn };
  }
  move(e) {
    const [cx, cy] = this.local(e), [x, y] = this.toStage(cx, cy);
    this.cursor = [x, y];
    this.notify.cursor(x, y);
    const d = this.drag;
    if (!d) {
      const hk = this.handleAt(cx, cy);
      const i = hk < 0 ? this.hitTest(x, y) : -1;
      const li = hk < 0 && i < 0 ? this.hitTest(x, y, true) : -1;
      const gi = hk < 0 && i < 0 ? this.guideAt(cx, cy) : null;
      this.els.view.style.cursor = this.space ? "grab" : hk === 8 ? "alias" : hk >= 0 ? (["nwse-resize", "ns-resize", "nesw-resize", "ew-resize"][hk % 4])
        : i >= 0 ? "move" : li >= 0 ? "not-allowed" : gi ? (gi.axis === "x" ? "ew-resize" : "ns-resize") : "default";
      if (i !== this.hover || li !== this.hoverLocked) { this.hover = i; this.hoverLocked = li; }
      this.dirty(true);
      return;
    }
    if (d.type === "pan") {
      this.view = { k: this.view.k, ox: d.ox + cx - d.cx, oy: d.oy + cy - d.cy, fit: false };
      this.dirty(true); return;
    }
    if (d.type === "guide") { d.val = r2(d.axis === "x" ? x : y); d.moved = true; this.dirty(true); return; }
    if (d.type === "marquee") {
      d.x1 = x; d.y1 = y; d.moved = d.moved || Math.abs(x - d.x0) * this.view.k > 3 || Math.abs(y - d.y0) * this.view.k > 3;
      if (d.moved) {
        const r = { l: Math.min(d.x0, x), r: Math.max(d.x0, x), t: Math.min(d.y0, y), b: Math.max(d.y0, y) };
        const pls = this.places(), hit = new Set(d.base);
        pls.forEach((pl, i) => {
          const b = this.shape(i);
          if (!b || pl.locked || pl.hidden) return;
          const a = aabbOf(b);
          if (a.r >= r.l && a.l <= r.r && a.b >= r.t && a.t <= r.b) for (const k of this.groupOf(i)) hit.add(k);
        });
        this.setSel([...hit], true);
      }
      this.dirty(); return;
    }
    let dx = x - d.x0, dy = y - d.y0;
    if (!d.moved && Math.hypot(dx, dy) * this.view.k < 3) return;
    d.moved = true;
    const prev = new Map();
    if (d.type === "move") {
      if (e.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) dy = 0; else dx = 0; }
      if (d.u) [dx, dy] = this.snapMove(d.u, dx, dy, d.targets, e.ctrlKey || e.metaKey);
      for (const [k, o] of d.orig) prev.set(k, Object.assign({}, o, { x: o.x + dx, y: o.y + dy }));
      d.dx = dx; d.dy = dy;
    } else if (d.type === "scale") {
      const f = d.fixed, g0 = d.grab;
      const v0 = [g0[0] - f[0], g0[1] - f[1]], v1 = [x - f[0], y - f[1]];
      const len = v0[0] * v0[0] + v0[1] * v0[1];
      let s = len > 0 ? (v1[0] * v0[0] + v1[1] * v0[1]) / len : 1;
      s = clamp(s, 0.02, 64);
      if (e.shiftKey) s = Math.max(0.05, Math.round(s * 20) / 20);
      for (const [k, o] of d.orig) {
        const sc = clamp((o.scale == null ? 1 : o.scale) * s, 0.01, 16);
        const real = sc / (o.scale == null ? 1 : o.scale);
        prev.set(k, Object.assign({}, o, { x: f[0] + (o.x - f[0]) * real, y: f[1] + (o.y - f[1]) * real, scale: sc }));
      }
      d.s = s;
      this.snaps = [];
    } else if (d.type === "turn") {
      let da = (Math.atan2(y - d.centre[1], x - d.centre[0]) - d.a0) * 180 / Math.PI;
      if (e.shiftKey) da = Math.round((d.turn + da) / 15) * 15 - d.turn;
      const r = da * Math.PI / 180, cs = Math.cos(r), sn = Math.sin(r), [cxs, cys] = d.centre;
      for (const [k, o] of d.orig) {
        const ox = o.x - cxs, oy = o.y - cys;
        prev.set(k, Object.assign({}, o, { x: cxs + ox * cs - oy * sn, y: cys + ox * sn + oy * cs, turn: (o.turn || 0) + da }));
      }
      d.da = da;
      this.snaps = [{ x0: d.centre[0], y0: d.centre[1], x1: x, y1: y, label: Math.round(((d.turn + da) % 360 + 540) % 360 - 180) + "°", lx: x, ly: y - 24 / this.view.k }];
    }
    this.preview = prev;
    this.dirty();
  }
  up(e) {
    const d = this.drag;
    this.drag = null; this.snaps = []; this.els.view.style.cursor = this.space ? "grab" : "default";
    try { this.els.view.releasePointerCapture(e.pointerId); } catch (err) { /* already gone */ }
    if (!d) return;
    if (d.type === "pan") { this.dirty(true); return; }
    if (d.type === "guide") {
      const doc = clone(this.doc), gd = guidesOf(doc);
      const [cx, cy] = this.local(e);
      const off = d.axis === "x" ? cx < 0 : cy < 0;           // dragged back onto its ruler: gone
      if (d.i < 0) { if (!off && d.moved !== false) gd[d.axis].push(d.val); }
      else if (off) gd[d.axis].splice(d.i, 1);
      else gd[d.axis][d.i] = d.val;
      setGuides(doc, gd);
      this.commit(doc, d.i < 0 ? "Add a guide" : off ? "Remove a guide" : "Move a guide");
      return;
    }
    if (d.type === "marquee") { this.dirty(); this.notify.panels(); return; }
    const prev = this.preview;
    if (!d.moved || !prev) {
      this.preview = null;
      if (d.type === "move" && d.clicked != null && !e.shiftKey && this.sel.length > 1) this.setSel(this.groupOf(d.clicked));
      this.dirty(); return;
    }
    const doc = clone(this.doc), ph = doc.phases[this.ph], pls = ph.place;
    let label = d.type === "move" ? (d.sel.length > 1 ? "Move " + d.sel.length + " things" : "Move " + pls[d.sel[0]].thing)
      : d.type === "scale" ? "Scale" : "Turn";
    if (d.dup && d.type === "move") {
      const added = [];
      for (const [k, p] of prev) { pls.push(cleanPlace(Object.assign({}, p))); added.push(pls.length - 1); }
      const grpMap = {};
      for (const m of groupsOf(doc, ph)) if (m.every((k) => d.sel.includes(k))) {
        const g2 = m.map((k) => added[d.sel.indexOf(k)]);
        grpMap[m.join(",")] = g2;
      }
      setGroups(doc, ph, [...groupsOf(doc, ph), ...Object.values(grpMap)]);
      label = "Duplicate";
      this.preview = null;
      this.commit(doc, label, added);
      return;
    }
    for (const [k, p] of prev) pls[k] = cleanPlace(Object.assign({}, p));
    this.commit(doc, label);
  }
  wheel(e) {
    e.preventDefault();
    const [cx, cy] = this.local(e);
    if (e.ctrlKey || e.metaKey) { this.zoomAt(this.view.k * Math.exp(-e.deltaY * 0.0022), cx, cy); return; }
    const dx = e.shiftKey ? e.deltaY : e.deltaX, dy = e.shiftKey ? 0 : e.deltaY;
    this.view = { k: this.view.k, ox: this.view.ox - dx, oy: this.view.oy - dy, fit: false };
    this.dirty(true);
  }
  rulerDown(e, axis) {
    // drag out of a ruler: a new guide (the top ruler makes a level one)
    e.preventDefault();
    const gaxis = axis === "x" ? "y" : "x";
    this.drag = { type: "guide", axis: gaxis, i: -1, val: -1, moved: false };
    const mv = (ev) => {
      const [cx, cy] = this.local(ev), [x, y] = this.toStage(cx, cy);
      this.drag.val = r2(gaxis === "x" ? x : y); this.drag.moved = true; this.dirty();
    };
    const upf = (ev) => {
      window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", upf);
      this.up(ev);
    };
    window.addEventListener("pointermove", mv); window.addEventListener("pointerup", upf);
  }

  // -- selection ---------------------------------------------------------------------------------------------------
  setSel(list, quiet = false) {
    const n = this.places().length;
    this.sel = [...new Set(list)].filter((i) => i >= 0 && i < n);
    this.dirty(true);
    if (!quiet) this.notify.panels();
  }
  cycle(back) {
    const order = drawOrder(this.doc, this.phase()).reverse().filter((i) => !this.places()[i].hidden);
    if (!order.length) return;
    const cur = this.sel.length ? order.indexOf(this.sel[0]) : -1;
    const nx = cur < 0 ? (back ? order.length - 1 : 0) : (cur + (back ? -1 : 1) + order.length) % order.length;
    this.setSel([order[nx]]);
  }

  // -- the document ------------------------------------------------------------------------------------------------
  setDoc(doc, sel) {
    this.doc = doc;
    if (this.ph >= doc.phases.length) this.ph = 0;
    this.sel = (sel || this.sel).filter((i) => i < this.places().length);
    this.preview = null;
    this.needSync = true;
    this.dirty(true);
    this.notify.panels();
  }
  // one change: shown at once, then checked and saved by Python as one undo step; refused: put back
  // Changes are saved one after another. A nudge made while the last nudge is still waiting its turn joins it: a
  // run of arrow presses is one step, as in other editors, and never a queue of dozens.
  commit(doc, label, sel) {
    const before = this.doc;
    this.setDoc(doc, sel);
    const tail = this.tail;
    if (label === "Nudge" && tail && !tail.started && tail.label === "Nudge") { tail.doc = doc; return this.queue; }
    const job = { doc, label, started: false };
    this.tail = job;
    this.pending = (this.pending || 0) + 1;
    this.status = { kind: "busy", text: "Saving…" }; this.notify.panels();
    this.queue = this.queue.then(async () => {
      job.started = true;
      let r;
      try { r = await call("vmodes.edit_commit", job.doc, job.label); } catch (err) { r = { ok: false, problems: [String(err && err.message || err)] }; }
      if (!r || !r.ok) {
        this.failed = { why: (r && r.problems) || [] };
        if (this.doc === job.doc) this.setDoc(r && r.doc ? r.doc : before);
        return;
      }
      await this.applyReply(r, job.doc);
    }).catch((err) => {
      // a fault here must never stop the changes after it from being saved: say so and carry on
      this.errors = (this.errors || []).concat(String(err && err.stack || err)).slice(-5);
      this.failed = { why: [String(err && err.message || err)] };
      this.needSync = true;
    }).then(() => {
      // "Saved" only once every change made has been saved; a refusal stays on show until the next change
      this.pending--;
      if (this.failed) { this.status = { kind: "err", text: "Not kept", why: this.failed.why }; if (!this.pending) this.failed = null; }
      else if (!this.pending) this.status = { kind: "ok", text: "Saved" };
      this.dirty(true); this.notify.panels();
    });
    return this.queue;
  }
  async applyReply(r, committed) {
    if (r.history) this.hist = r.history;
    if (r.pack) {
      const v = this.e.load(b64bytes(r.pack));
      this.packOk = !v;
      this.packErr = v ? "The engine refused the compiled mode (" + v + " at word " + this.e.errAt() + ")." : "";
      this.place0 = r.place0 || this.place0;
      this.packCounts = this.counts(r.doc || committed || this.doc);
      if (r.pictures) await this.notify.textures(r);
    } else if (r.problems && r.problems.length) { this.packOk = false; this.packErr = r.problems.join("\n"); }
    this.needSync = true;
    this.dirty(true);
    this.notify.panels();
  }
  async undoRedo(which) {
    await this.queue;
    const r = await call(which === "undo" ? "vmodes.edit_undo" : "vmodes.edit_redo");
    if (!r || !r.ok) { if (r && r.problems) { this.status = { kind: "err", text: "Not kept", why: r.problems }; this.notify.panels(); } return; }
    this.status = { kind: "ok", text: (which === "undo" ? "Undid: " : "Redid: ") + (r.label || "a change") };
    this.doc = r.doc;
    await this.applyReply(r, r.doc);
    this.setDoc(r.doc);
  }
  edit(label, fn, sel) {
    const doc = clone(this.doc), ph = doc.phases[this.ph];
    ph.place = ph.place || [];
    const out = fn(doc, ph);
    if (out === false) return null;
    return this.commit(doc, label, Array.isArray(out) ? out : sel);
  }
  setPhase(i) {
    this.ph = clamp(i, 0, this.doc.phases.length - 1);
    this.sel = []; this.preview = null; this.hover = -1;
    this.dirty(true); this.notify.panels();
  }

  // -- the commands --------------------------------------------------------------------------------------------------
  thingFor(doc, assetKind, id) {
    if (assetKind === "thing") return id;
    const have = (doc.things || []).find((t) => t.id === id && t.picture === id) || (doc.things || []).find((t) => t.picture === id);
    if (have) return have.id;
    const tid = uniqueId(idsInUse(doc), id);
    doc.things = doc.things || [];
    doc.things.push({ id: tid, picture: id, team: "scenery" });
    return tid;
  }
  add(assetKind, id, x, y) {
    if (x == null) {
      // the middle of the stage, stepped aside from anything already there, so a run of adds fans out
      x = this.info.stage[0] / 2; y = this.info.stage[1] / 2;
      const taken = (px, py) => this.places().some((p) => Math.abs(p.x - px) < 4 && Math.abs(p.y - py) < 4);
      for (let n = 0; n < 40 && taken(x, y); n++) { x += 32; y += 24; }
    }
    if (this.opts.snap && this.opts.grid) { const g = this.grid(); x = Math.round(x / g) * g; y = Math.round(y / g) * g; }
    return this.edit("Add " + id, (doc, ph) => {
      const tid = this.thingFor(doc, assetKind, id);
      ph.place.push(cleanPlace({ thing: tid, x, y }));
      return [ph.place.length - 1];
    });
  }
  remove() {
    if (!this.sel.length) return;
    const gone = new Set(this.sel);
    this.edit(gone.size > 1 ? "Remove " + gone.size + " things" : "Remove " + this.places()[this.sel[0]].thing, (doc, ph) => {
      const map = {}; let n = 0;
      ph.place.forEach((_, i) => { map[i] = gone.has(i) ? -1 : n++; });
      ph.place = ph.place.filter((_, i) => !gone.has(i));
      remapGroups(doc, ph, map);
      return [];
    });
  }
  nudge(dx, dy) {
    const sel = this.sel.filter((i) => !this.places()[i].locked);
    if (!sel.length) return;
    this.edit("Nudge", (doc, ph) => { for (const i of sel) { ph.place[i].x = r2(ph.place[i].x + dx); ph.place[i].y = r2(ph.place[i].y + dy); } });
  }
  setPlaces(label, patch, sel = this.sel) {
    if (!sel.length) return null;
    return this.edit(label, (doc, ph) => { for (const i of sel) ph.place[i] = cleanPlace(Object.assign({}, ph.place[i], patch(ph.place[i], i))); });
  }
  setThing(label, id, patch) {
    return this.edit(label, (doc) => {
      const t = thingOf(doc, id);
      if (!t) return false;
      patch(t, doc);
    });
  }
  copy() {
    if (!this.sel.length) return;
    const pls = this.sel.slice().sort((a, b) => a - b).map((i) => clone(this.places()[i]));
    const things = [...new Set(pls.map((p) => p.thing))].map((id) => clone(thingOf(this.doc, id)));
    clipboard = { things, places: pls, from: this.phase().id };
    try { localStorage.setItem("vme.clip", JSON.stringify(clipboard)); } catch (e) { /* too big: the module's copy stays */ }
    this.status = { kind: "ok", text: "Copied " + pls.length };
    this.notify.panels();
  }
  paste(off = true) {
    let clip = clipboard;
    try { if (!clip) clip = JSON.parse(localStorage.getItem("vme.clip") || "null"); } catch (e) { clip = null; }
    if (!clip || !clip.places.length) return;
    this.edit("Paste " + clip.places.length, (doc, ph) => {
      const added = [];
      for (const t of clip.things) {
        if (!thingOf(doc, t.id) && pictureOf(doc, t.picture)) { doc.things = doc.things || []; doc.things.push(clone(t)); }
      }
      const shift = off && clip.from === ph.id ? PASTE_OFF : 0;
      for (const p of clip.places) {
        if (!thingOf(doc, p.thing)) continue;
        ph.place.push(cleanPlace(Object.assign(clone(p), { x: p.x + shift, y: p.y + shift })));
        added.push(ph.place.length - 1);
      }
      clipboard = { things: clip.things, places: clip.places.map((p) => Object.assign({}, p, { x: p.x + shift, y: p.y + shift })), from: ph.id };
      return added.length ? added : false;
    });
  }
  duplicate() {
    if (!this.sel.length) return;
    const sel = this.sel.slice().sort((a, b) => a - b);
    this.edit("Duplicate", (doc, ph) => {
      const added = sel.map((i) => { ph.place.push(cleanPlace(Object.assign(clone(ph.place[i]), { x: ph.place[i].x + PASTE_OFF, y: ph.place[i].y + PASTE_OFF }))); return ph.place.length - 1; });
      const extra = groupsOf(doc, ph).filter((m) => m.every((k) => sel.includes(k))).map((m) => m.map((k) => added[sel.indexOf(k)]));
      setGroups(doc, ph, [...groupsOf(doc, ph), ...extra]);
      return added;
    });
  }
  group() {
    if (this.sel.length < 2) return;
    const sel = this.sel.slice().sort((a, b) => a - b);
    this.edit("Group " + sel.length, (doc, ph) => {
      setGroups(doc, ph, [...groupsOf(doc, ph).map((m) => m.filter((k) => !sel.includes(k))), sel]);
      return sel;
    });
  }
  ungroup() {
    const sel = this.sel;
    if (!groupsOf(this.doc, this.phase()).some((m) => m.some((k) => sel.includes(k)))) return;
    this.edit("Ungroup", (doc, ph) => { setGroups(doc, ph, groupsOf(doc, ph).filter((m) => !m.some((k) => sel.includes(k)))); return sel; });
  }
  toggle(key) {
    if (!this.sel.length) return;
    const on = !this.sel.every((i) => this.places()[i][key]);
    this.setPlaces((on ? (key === "hidden" ? "Hide" : "Lock") : (key === "hidden" ? "Show" : "Unlock")), () => ({ [key]: on }));
  }
  align(how) {
    const sel = this.sel.filter((i) => !this.places()[i].locked && this.shape(i));
    if (!sel.length) return;
    const W = this.info.stage[0], H = this.info.stage[1];
    const boxes = new Map(sel.map((i) => [i, aabbOf(this.shape(i))]));
    const all = sel.length > 1 ? unite([...boxes.values()]) : { l: 0, t: 0, r: W, b: H };
    if (how === "dist_x" || how === "dist_y") {
      if (sel.length < 3) return;
      const ax = how === "dist_x", lo = ax ? "l" : "t", hi = ax ? "r" : "b";
      const order = sel.slice().sort((a, b) => boxes.get(a)[lo] - boxes.get(b)[lo]);
      const span = all[hi] - all[lo], sizes = order.reduce((s, i) => s + boxes.get(i)[hi] - boxes.get(i)[lo], 0);
      const gap = (span - sizes) / (order.length - 1);
      let at = all[lo];
      const moves = new Map();
      for (const i of order) { moves.set(i, at - boxes.get(i)[lo]); at += boxes.get(i)[hi] - boxes.get(i)[lo] + gap; }
      this.setPlaces(ax ? "Distribute across" : "Distribute down", (p, i) => (ax ? { x: p.x + moves.get(i) } : { y: p.y + moves.get(i) }), sel);
      return;
    }
    const d = (i) => {
      const b = boxes.get(i);
      switch (how) {
        case "left": return [all.l - b.l, 0];
        case "centre": return [(all.l + all.r) / 2 - (b.l + b.r) / 2, 0];
        case "right": return [all.r - b.r, 0];
        case "top": return [0, all.t - b.t];
        case "middle": return [0, (all.t + all.b) / 2 - (b.t + b.b) / 2];
        default: return [0, all.b - b.b];
      }
    };
    const names = { left: "Align left", centre: "Align centers", right: "Align right", top: "Align tops", middle: "Align middles", bottom: "Align bottoms" };
    this.setPlaces(names[how] || "Align", (p, i) => { const [dx, dy] = d(i); return { x: p.x + dx, y: p.y + dy }; }, sel);
  }
  // the layers' order, front first: one change. The things that moved take a depth between their new neighbours'
  // (their own when it already fits); the rest keep theirs unless the order cannot hold otherwise.
  reorder(frontFirst, label = "Reorder", movedIdx = null) {
    const movedSet = new Set(movedIdx || []);
    return this.edit(label, (doc, ph) => {
      const backFirst = frontFirst.slice().reverse(), old = ph.place;
      const list = backFirst.map((i) => clone(old[i])), n = list.length;
      for (let k = 0; k < n; k++) {
        if (movedSet.size && !movedSet.has(backFirst[k])) continue;
        const own = effDepth(doc, list[k]);
        const lo = k ? effDepth(doc, list[k - 1]) : -Infinity, hi = k + 1 < n ? effDepth(doc, list[k + 1]) : Infinity;
        if (own < lo || own > hi) list[k].depth = k ? lo : hi;
      }
      for (let k = 1; k < n; k++) if (effDepth(doc, list[k]) < effDepth(doc, list[k - 1])) list[k].depth = effDepth(doc, list[k - 1]);
      for (const pl of list) {
        const t = thingOf(doc, pl.thing), def = t && t.depth != null ? t.depth : 0;
        if (pl.depth != null && pl.depth === def) delete pl.depth;
      }
      const map = {};
      backFirst.forEach((oldI, newI) => { map[oldI] = newI; });
      ph.place = list;
      remapGroups(doc, ph, map);
      return this.sel.map((i) => map[i]);
    });
  }
  arrange(how) {
    if (!this.sel.length) return;
    let order = drawOrder(this.doc, this.phase()).reverse();       // front first
    const sel = this.sel, rest = order.filter((i) => !sel.includes(i)), mine = order.filter((i) => sel.includes(i));
    if (how === "front") order = [...mine, ...rest];
    else if (how === "back") order = [...rest, ...mine];
    else {
      const step = how === "forward" ? -1 : 1;
      for (const i of (step < 0 ? mine : mine.slice().reverse())) {
        const k = order.indexOf(i), j = k + step;
        if (j < 0 || j >= order.length || sel.includes(order[j])) continue;
        [order[k], order[j]] = [order[j], order[k]];
      }
    }
    this.reorder(order, { front: "Bring to front", back: "Send to back", forward: "Bring forward", backward: "Send backward" }[how], sel);
  }
}

// ---- number fields that scrub on drag ------------------------------------------------------------------------
function Scrub({ label, value, unit, step = 1, min = -1e9, max = 1e9, digits = 2, onLive, onCommit, title, mixed, disabled }) {
  const [text, setText] = useState(null);
  const shown = mixed ? "" : value == null ? "" : String(r2(Number(value) * 10 ** (digits - 2)) / 10 ** (digits - 2));
  const down = (e) => {
    if (disabled || e.button !== 0) return;
    e.preventDefault();
    const x0 = e.clientX, v0 = Number(value) || 0;
    let last = v0, moved = false;
    const mv = (ev) => {
      const f = ev.shiftKey ? 10 : ev.altKey ? 0.1 : 1, dx = ev.clientX - x0;
      if (Math.abs(dx) > 2) moved = true;
      last = clamp(Math.round((v0 + dx * step * f) / (step * (ev.altKey ? 0.1 : 1))) * (step * (ev.altKey ? 0.1 : 1)), min, max);
      if (onLive) onLive(last);
    };
    const upf = () => {
      window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", upf);
      document.body.classList.remove("vme-scrubbing");
      if (moved && last !== v0) onCommit(last); else if (onLive) onLive(null);
    };
    document.body.classList.add("vme-scrubbing");
    window.addEventListener("pointermove", mv); window.addEventListener("pointerup", upf);
  };
  const commit = () => {
    if (text == null) return;
    const v = Number(text);
    setText(null);
    if (text.trim() !== "" && Number.isFinite(v) && v !== Number(value)) onCommit(clamp(v, min, max));
  };
  return html`<label class=${cx("vme-nf", disabled && "disabled")} ...${tip(title || T.scrub)}>
    <span class="l" onPointerDown=${down}>${label}</span>
    <input class="mono" inputmode="decimal" disabled=${disabled} value=${text != null ? text : shown} placeholder=${mixed ? "mixed" : ""}
      onFocus=${(e) => { setText(shown); e.target.select(); }} onInput=${(e) => setText(e.target.value)} onBlur=${commit}
      onKeyDown=${(e) => {
        if (e.key === "Enter") { e.preventDefault(); commit(); e.target.blur(); }
        else if (e.key === "Escape") { setText(null); e.target.blur(); }
        else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
          e.preventDefault();
          const v = clamp((Number(text != null ? text : value) || 0) + (e.key === "ArrowUp" ? 1 : -1) * step * (e.shiftKey ? 10 : 1), min, max);
          setText(null); onCommit(r2(v));
        }
      }} />
    ${unit ? html`<span class="u">${unit}</span>` : null}
  </label>`;
}

function TextIn({ value, onCommit, placeholder, max = 60 }) {
  const [t, setT] = useState(null);
  const done = () => { if (t != null && t !== (value || "")) onCommit(t.slice(0, max)); setT(null); };
  return html`<div class="field sm"><input value=${t != null ? t : value || ""} placeholder=${placeholder} maxlength=${max}
    onInput=${(e) => setT(e.target.value)} onBlur=${done} onKeyDown=${(e) => { if (e.key === "Enter") e.target.blur(); if (e.key === "Escape") { setT(null); e.target.blur(); } }} /></div>`;
}

const Group = ({ label, children, extra }) => html`<div class="vme-group">
  <div class="vme-lab"><span>${label}</span>${extra || null}</div>${children}</div>`;

// ---- the inspector -------------------------------------------------------------------------------------------
function Inspector({ ed, pics }) {
  const doc = ed.doc, ph = ed.phase(), pls = ph.place || [], sel = ed.sel;
  const live = (i, patch) => (v) => {
    if (v == null) { ed.preview = null; ed.dirty(); return; }
    ed.preview = new Map(i.map((k) => [k, Object.assign({}, pls[k], patch(pls[k], v))]));
    ed.dirty();
  };
  if (!sel.length) {
    const st = doc.stage || {};
    return html`<div class="vme-dock-b">
      <${Group} label="Phase">
        <div class="vme-row"><span class="vme-k">Title</span><${TextIn} value=${ph.title} max=${40} placeholder=${ph.id}
          onCommit=${(v) => ed.edit("Name the phase", (d, p) => { if (v) p.title = v; else delete p.title; })} /></div>
        <div class="vme-row"><span class="vme-k">Objective</span><${TextIn} value=${ph.objective} placeholder="What the player does"
          onCommit=${(v) => ed.edit("Change the objective", (d, p) => { if (v) p.objective = v; else delete p.objective; })} /></div>
        <div class="vme-two">
          <${Scrub} label="Length" unit="s" value=${ph.length_s || 0} step=${0.5} min=${0} max=${600}
            title="How long the phase runs; 0: until it is won or lost"
            onCommit=${(v) => ed.edit("Change the length", (d, p) => { if (v > 0) p.length_s = v; else delete p.length_s; })} />
          <div class="vme-kind"><span class="chip sm">${ph.kind}</span></div>
        </div>
      <//>
      <${Group} label="Stage">
        <div class="vme-row"><span class="vme-k">Background</span>
          <input type="color" class="vme-colour" value=${(st.background || "#000000").slice(0, 7)}
            onChange=${(e) => ed.edit("Change the background color", (d) => { d.stage.background = e.target.value; })} /></div>
        ${st.safe ? html`<div class="vme-two">
          <${Scrub} label="Safe X" value=${st.safe.x} min=${0} max=${1360} onCommit=${(v) => ed.edit("Change the safe area", (d) => { d.stage.safe.x = v; })} />
          <${Scrub} label="Y" value=${st.safe.y} min=${0} max=${768} onCommit=${(v) => ed.edit("Change the safe area", (d) => { d.stage.safe.y = v; })} />
          <${Scrub} label="W" value=${st.safe.w} min=${1} max=${1360} onCommit=${(v) => ed.edit("Change the safe area", (d) => { d.stage.safe.w = v; })} />
          <${Scrub} label="H" value=${st.safe.h} min=${1} max=${768} onCommit=${(v) => ed.edit("Change the safe area", (d) => { d.stage.safe.h = v; })} />
        </div>` : html`<${Button} size="sm" icon="plus" title="Mark the part of the stage every machine's glass shows"
            onClick=${() => ed.edit("Add a safe area", (d) => { d.stage.safe = { x: 40, y: 24, w: 1280, h: 720 }; })}>Safe area<//>`}
      <//>
      <div class="vme-hint">${pls.length ? "Click a thing on the stage or in Layers to change it. Tab picks the next one." : "Drag a thing or a picture from Assets onto the stage, or press Ctrl K and type its name."}</div>
    </div>`;
  }
  const one = sel.length === 1 ? pls[sel[0]] : null;
  const b = ed.selBounds();
  if (!one) {
    const same = (k, d) => { const v = pls[sel[0]][k] ?? d; return sel.every((i) => (pls[i][k] ?? d) === v) ? v : null; };
    const grouped = groupsOf(doc, ph).some((m) => m.some((k) => sel.includes(k)));
    return html`<div class="vme-dock-b">
      <${Group} label="Align and distribute">
        <${AlignBar} ed=${ed} />
      <//>
      <${Group} label="Place">
        <div class="vme-two">
          <${Scrub} label="X" unit="px" disabled=${!b} value=${b ? r2(b.l) : 0} onLive=${live(sel, (p, v) => ({ x: p.x + v - b.l }))}
            onCommit=${(v) => ed.setPlaces("Move " + sel.length + " things", (p) => ({ x: p.x + v - b.l }))} />
          <${Scrub} label="Y" unit="px" disabled=${!b} value=${b ? r2(b.t) : 0} onLive=${live(sel, (p, v) => ({ y: p.y + v - b.t }))}
            onCommit=${(v) => ed.setPlaces("Move " + sel.length + " things", (p) => ({ y: p.y + v - b.t }))} />
          <${Scrub} label="Scale" unit="×" step=${0.01} min=${0.01} max=${16} value=${same("scale", 1)} mixed=${same("scale", 1) == null}
            onLive=${live(sel, (p, v) => ({ scale: v }))} onCommit=${(v) => ed.setPlaces("Scale", () => ({ scale: v }))} />
          <${Scrub} label="Turn" unit="°" min=${-360} max=${360} value=${same("turn", 0)} mixed=${same("turn", 0) == null}
            onLive=${live(sel, (p, v) => ({ turn: v }))} onCommit=${(v) => ed.setPlaces("Turn", () => ({ turn: v }))} />
        </div>
        <div class="vme-chip-row"><span class="chip sm mono">${b ? Math.round(b.r - b.l) + " × " + Math.round(b.b - b.t) + " px" : ""}</span></div>
      <//>
      <${Group} label="Arrange">
        <div class="vme-btns">
          <${Button} size="sm" onClick=${() => (grouped ? ed.ungroup() : ed.group())} title=${grouped ? "Ungroup (Ctrl Shift G)" : "Group: they select and move together (Ctrl G)"}>${grouped ? "Ungroup" : "Group"}<//>
          <${Button} size="sm" icon="copy" onClick=${() => ed.duplicate()} title="Duplicate (Ctrl D)">Duplicate<//>
          <${Button} size="sm" icon=${sel.every((i) => pls[i].locked) ? "unlock" : "lock"} onClick=${() => ed.toggle("locked")}>${sel.every((i) => pls[i].locked) ? "Unlock" : "Lock"}<//>
          <${Button} size="sm" icon="eye" onClick=${() => ed.toggle("hidden")}>${sel.every((i) => pls[i].hidden) ? "Show" : "Hide"}<//>
          <${Button} size="sm" icon="trash" onClick=${() => ed.remove()} title="Remove (Delete)">Remove<//>
        </div>
      <//>
    </div>`;
  }
  const i0 = sel[0], th = thingOf(doc, one.thing) || {}, pic = pictureOf(doc, th.picture) || {};
  const pinfo = pics.find((p) => p.id === th.picture) || {};
  const uses = doc.phases.reduce((n, p) => n + (p.place || []).filter((q) => q.thing === one.thing).length, 0);
  const fw = pinfo.fw || pic.frame_w || 64, fh = pinfo.fh || pic.frame_h || 64;
  const tscale = th.scale == null ? 1 : th.scale, pscale = one.scale == null ? 1 : one.scale;
  const hb = th.hitbox, mv = th.mover || { type: "none" };
  const setMover = (patch) => ed.setThing("Change how " + th.id + " moves", th.id, (t) => {
    const m = Object.assign({}, t.mover || { type: "none" }, patch);
    for (const k of Object.keys(m)) if (m[k] == null) delete m[k];
    if (m.type === "none" && Object.keys(m).length === 1) delete t.mover; else t.mover = m;
  });
  return html`<div class="vme-dock-b">
    <${Group} label="Place">
      <div class="vme-two">
        <${Scrub} label="X" unit="px" value=${one.x} onLive=${live([i0], (p, v) => ({ x: v }))} onCommit=${(v) => ed.setPlaces("Move " + one.thing, () => ({ x: v }))} />
        <${Scrub} label="Y" unit="px" value=${one.y} onLive=${live([i0], (p, v) => ({ y: v }))} onCommit=${(v) => ed.setPlaces("Move " + one.thing, () => ({ y: v }))} />
        <${Scrub} label="Scale" unit="×" step=${0.01} min=${0.01} max=${16} value=${pscale} digits=${3}
          onLive=${live([i0], (p, v) => ({ scale: v }))} onCommit=${(v) => ed.setPlaces("Scale " + one.thing, () => ({ scale: v }))} />
        <${Scrub} label="Turn" unit="°" min=${-360} max=${360} value=${one.turn || 0}
          onLive=${live([i0], (p, v) => ({ turn: v }))} onCommit=${(v) => ed.setPlaces("Turn " + one.thing, () => ({ turn: v }))} />
        <${Scrub} label="W" unit="px" min=${1} max=${8192} value=${Math.round(fw * tscale * pscale)} title="Its width on the stage: sets the scale, keeping its shape"
          onLive=${live([i0], (p, v) => ({ scale: clamp(v / (fw * tscale), 0.01, 16) }))} onCommit=${(v) => ed.setPlaces("Size " + one.thing, () => ({ scale: clamp(v / (fw * tscale), 0.01, 16) }))} />
        <${Scrub} label="H" unit="px" min=${1} max=${8192} value=${Math.round(fh * tscale * pscale)} title="Its height on the stage: sets the scale, keeping its shape"
          onLive=${live([i0], (p, v) => ({ scale: clamp(v / (fh * tscale), 0.01, 16) }))} onCommit=${(v) => ed.setPlaces("Size " + one.thing, () => ({ scale: clamp(v / (fh * tscale), 0.01, 16) }))} />
        <${Scrub} label="Depth" min=${-1000} max=${1000} value=${effDepth(doc, one)} title="Higher draws in front; Layers' order sets it too"
          onCommit=${(v) => ed.setPlaces("Change depth", () => ({ depth: Math.round(v) }))} />
        <div class="vme-btns tight">
          <button type="button" class=${cx("btn ghost icon sm", one.hidden && "on")} onClick=${() => ed.toggle("hidden")} ...${tip(one.hidden ? "Hidden: show it" : "Hide it")}><${Icon} name="eye" /></button>
          <button type="button" class=${cx("btn ghost icon sm", one.locked && "on")} onClick=${() => ed.toggle("locked")} ...${tip(one.locked ? "Locked: unlock it" : "Lock it: it cannot be dragged")}><${Icon} name=${one.locked ? "lock" : "unlock"} /></button>
          <button type="button" class="btn ghost icon sm" onClick=${() => ed.duplicate()} ...${tip("Duplicate (Ctrl D)")}><${Icon} name="copy" /></button>
          <button type="button" class="btn ghost icon sm" onClick=${() => ed.remove()} ...${tip("Remove (Delete)")}><${Icon} name="trash" /></button>
        </div>
      </div>
    <//>
    <${Group} label="Picture" extra=${html`<span class="vme-shared" ...${tip(T.shared(uses))}>${uses > 1 ? "× " + uses : ""}</span>`}>
      <div class="vme-pic">
        <${Thumb} p=${pinfo} />
        <div class="stack" style="gap:6px;flex:1;min-width:0">
          <${Select} sm value=${th.picture} options=${((doc.assets || {}).pictures || []).map((p) => ({ value: p.id, label: p.id + (p.frames > 1 ? " · " + p.frames + " frames" : "") }))}
            onChange=${(v) => ed.setThing("Change " + th.id + "'s picture", th.id, (t, d) => {
              t.picture = v; const np = pictureOf(d, v) || {};
              if (t.animation && !(np.animations || []).some((a) => a.id === t.animation)) delete t.animation;
            })} />
          <${Select} sm value=${th.animation || ""} disabled=${!(pic.animations || []).length}
            options=${[{ value: "", label: (pic.animations || []).length ? "No animation: frame 1" : "No animations" },
                       ...(pic.animations || []).map((a) => ({ value: a.id, label: a.id + " · " + a.fps + " fps" + (a.loop === false ? "" : " · loop") }))]}
            onChange=${(v) => ed.setThing("Change " + th.id + "'s animation", th.id, (t) => { if (v) t.animation = v; else delete t.animation; })} />
        </div>
      </div>
    <//>
    <${Group} label="Team, health and points">
      <${Select} sm value=${th.team} options=${TEAMS.map((t) => ({ value: t, label: TEAM_LABEL[t] }))}
        onChange=${(v) => ed.setThing("Change " + th.id + "'s team", th.id, (t) => { t.team = v; })} />
      <div class="vme-two">
        <${Scrub} label="Health" min=${1} max=${999} value=${th.health || 1} onCommit=${(v) => ed.setThing("Change health", th.id, (t) => { t.health = Math.round(v); })} />
        <${Scrub} label="Points" min=${0} max=${1000000} step=${10} value=${th.points || 0}
          onCommit=${(v) => ed.setThing("Change points", th.id, (t) => { if (v > 0) t.points = Math.round(v); else delete t.points; })} />
        <${Scrub} label="Size" unit="×" step=${0.01} min=${0.01} max=${16} value=${tscale} digits=${3} title="Every one of this kind, placed or spawned"
          onCommit=${(v) => ed.setThing("Scale every " + th.id, th.id, (t) => { if (v === 1) delete t.scale; else t.scale = v; })} />
        <${Select} sm value=${th.blend || "normal"} options=${[{ value: "normal", label: "Normal" }, { value: "add", label: "Glow (add)" }]}
          onChange=${(v) => ed.setThing("Change blend", th.id, (t) => { if (v === "normal") delete t.blend; else t.blend = v; })} />
      </div>
    <//>
    <${Group} label="Hit box">
      <${Select} sm value=${hb ? hb.shape : ""} options=${[{ value: "", label: "The picture's own" }, { value: "box", label: "A box" }, { value: "circle", label: "A circle" }]}
        onChange=${(v) => ed.setThing("Change the hit box", th.id, (t) => {
          const ax = (pic.anchor || [0.5, 0.5]);
          if (!v) delete t.hitbox;
          else if (v === "box") t.hitbox = { shape: "box", x: r2(-ax[0] * fw), y: r2(-ax[1] * fh), w: fw, h: fh };
          else t.hitbox = { shape: "circle", x: r2((0.5 - ax[0]) * fw), y: r2((0.5 - ax[1]) * fh), r: r2(Math.min(fw, fh) / 2) };
        })} />
      ${hb ? html`<div class="vme-two">
        <${Scrub} label="X" value=${hb.x || 0} onCommit=${(v) => ed.setThing("Change the hit box", th.id, (t) => { t.hitbox.x = v; })} />
        <${Scrub} label="Y" value=${hb.y || 0} onCommit=${(v) => ed.setThing("Change the hit box", th.id, (t) => { t.hitbox.y = v; })} />
        ${hb.shape === "box" ? html`
          <${Scrub} label="W" min=${0.5} max=${4096} value=${hb.w} onCommit=${(v) => ed.setThing("Change the hit box", th.id, (t) => { t.hitbox.w = v; })} />
          <${Scrub} label="H" min=${0.5} max=${4096} value=${hb.h} onCommit=${(v) => ed.setThing("Change the hit box", th.id, (t) => { t.hitbox.h = v; })} />`
        : html`<${Scrub} label="R" min=${0.5} max=${4096} value=${hb.r} onCommit=${(v) => ed.setThing("Change the hit box", th.id, (t) => { t.hitbox.r = v; })} />`}
      </div>` : null}
    <//>
    <${Group} label="How it moves">
      <${Select} sm value=${mv.type} options=${MOVERS.map(([v, l]) => ({ value: v, label: l }))}
        onChange=${(v) => setMover(v === "path" ? { type: v, path: mv.path || [[0, 0], [240, 0]], speed: mv.speed || 200 }
          : v === "home" ? { type: v, target: mv.target || (doc.things.find((t) => t.team === "player") || doc.things[0]).id, path: null }
          : v === "orbit" ? { type: v, radius: mv.radius || 80, speed: mv.speed || 160, path: null, target: null }
          : { type: v, path: null, target: null, easing: null, loop: null, radius: null, turn_per_s: null })} />
      ${mv.type !== "none" && mv.type !== "lanes" && mv.type !== "free" && mv.type !== "thrust" ? html`<div class="vme-two">
        <${Scrub} label="Speed" unit="px/s" min=${0} max=${8000} step=${5} value=${mv.speed || 0} onCommit=${(v) => setMover({ speed: v })} />
        ${mv.type === "straight" ? html`<${Scrub} label="Heading" unit="°" min=${-360} max=${360} value=${mv.direction || 0} onCommit=${(v) => setMover({ direction: v })} />` : null}
        ${mv.type === "orbit" ? html`<${Scrub} label="Radius" unit="px" min=${1} max=${4096} value=${mv.radius || 80} onCommit=${(v) => setMover({ radius: v })} />` : null}
        ${mv.type === "home" ? html`<${Scrub} label="Turns" unit="°/s" min=${0} max=${3600} value=${mv.turn_per_s ?? 90} onCommit=${(v) => setMover({ turn_per_s: v })} />` : null}
      </div>` : null}
      ${mv.type === "path" ? html`<div class="vme-two">
        <${Select} sm value=${mv.easing || "linear"} options=${EASINGS.map((x) => ({ value: x, label: "Ease: " + x.replace("_", " ") }))} onChange=${(v) => setMover({ easing: v === "linear" ? null : v })} />
        <label class="vme-chk"><input type="checkbox" checked=${!!mv.loop} onChange=${(e) => setMover({ loop: e.target.checked || null })} /> Loop the path</label>
      </div><div class="vme-hint">${(mv.path || []).length} points, from where it starts.</div>` : null}
      ${mv.type === "home" ? html`<${Select} sm value=${mv.target} options=${doc.things.map((t) => ({ value: t.id, label: "Homes on " + t.id }))} onChange=${(v) => setMover({ target: v })} />` : null}
    <//>
  </div>`;
}

const ALIGN_SVG = {
  left: "M2 1v14M5 4h9v3H5zM5 9h6v3H5z", centre: "M8 1v14M3 4h10v3H3zM5 9h6v3H5z", right: "M14 1v14M2 4h9v3H2zM5 9h6v3H5z",
  top: "M1 2h14M4 5v9h3V5zM9 5v6h3V5z", middle: "M1 8h14M4 3v10h3V3zM9 5v6h3V5z", bottom: "M1 14h14M4 2v9h3V2zM9 5v6h3V5z",
  dist_x: "M1 1v14M15 1v14M5 4h2v8H5zM9 4h2v8H9z", dist_y: "M1 1h14M1 15h14M4 5v2h8V5zM4 9v2h8V9z",
};
function AlignBar({ ed }) {
  const n = ed.sel.length;
  const b = (act, icon, label, need = 1) => html`<button type="button" class="btn ghost icon sm" data-act=${act} disabled=${n < need}
    onClick=${() => ed.align(act)} ...${tip(label + (n === 1 ? " (to the stage)" : ""))}>
    <svg class="vme-al" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d=${ALIGN_SVG[act]} /></svg></button>`;
  return html`<div class="vme-align">
    ${b("left", "", "Align left edges")}${b("centre", "", "Align centers across")}${b("right", "", "Align right edges")}
    <span class="vme-vsep"></span>
    ${b("top", "", "Align top edges")}${b("middle", "", "Align middles")}${b("bottom", "", "Align bottom edges")}
    <span class="vme-vsep"></span>
    ${b("dist_x", "", "Space evenly across (three or more)", 3)}${b("dist_y", "", "Space evenly down (three or more)", 3)}
  </div>`;
}

function Thumb({ p, size = 44 }) {
  if (!p || !p.path) {
    const col = TEAM_HEX[(p && p.team) || "scenery"] || "#888";
    return html`<span class="vme-thumb ph" style=${{ width: size + "px", height: size + "px", borderColor: col }}>${p && p.id ? p.id.slice(0, 2) : "?"}</span>`;
  }
  const cols = p.cols || 1, rows = Math.max(1, Math.round(p.h / (p.fh || p.h)));
  const k = Math.min(size / (p.fw || p.w), size / (p.fh || p.h));
  return html`<span class="vme-thumb" style=${{ width: size + "px", height: size + "px" }}><i style=${{
    width: Math.max(1, (p.fw || p.w) * k) + "px", height: Math.max(1, (p.fh || p.h) * k) + "px",
    backgroundImage: "url(" + mediaUrl(p.path) + "&v=" + (p.v || 0) + ")", backgroundSize: cols * 100 + "% " + rows * 100 + "%" }}></i></span>`;
}

// ---- the layers ---------------------------------------------------------------------------------------------------
function Layers({ ed }) {
  const doc = ed.doc, ph = ed.phase(), pls = ph.place || [];
  const [dragging, setDragging] = useState(null);
  const [over, setOver] = useState(null);
  const listRef = useRef(null);
  const order = drawOrder(doc, ph).reverse();           // front first
  const groups = groupsOf(doc, ph);
  const count = {}, nth = {};
  for (let i = 0; i < pls.length; i++) { const t = pls[i].thing; count[t] = (count[t] || 0) + 1; nth[i] = count[t]; }
  const rows = [], seen = new Set();
  for (const i of order) {
    const gi = groups.findIndex((m) => m.includes(i));
    if (gi >= 0 && !seen.has("g" + gi)) {
      seen.add("g" + gi);
      rows.push({ group: gi, members: groups[gi] });
      for (const k of order) if (groups[gi].includes(k)) rows.push({ i: k, child: true });
    } else if (gi < 0) rows.push({ i });
  }
  const overRef = useRef(null);
  overRef.current = over;
  useEffect(() => {
    // keep the selected row in view without moving the list otherwise
    const el = listRef.current && listRef.current.querySelector(".vme-lay.on");
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
  }, [ed.sel.join(",")]);
  if (!pls.length) return html`<div class="vme-empty-s">Nothing on the stage yet</div>`;
  const pick = (e, list) => {
    if (e.shiftKey || e.ctrlKey || e.metaKey) {
      const has = list.every((k) => ed.sel.includes(k));
      ed.setSel(has ? ed.sel.filter((k) => !list.includes(k)) : [...ed.sel, ...list]);
    } else ed.setSel(list);
  };
  // pointer reordering: drop between rows; the row moves (with its group) to that place in the order
  const startDrag = (e, list) => {
    if (e.button !== 0) return;
    const y0 = e.clientY;
    let on = false;
    const mv = (ev) => {
      if (!on && Math.abs(ev.clientY - y0) < 4) return;
      on = true; setDragging(list);
      const els = [...listRef.current.querySelectorAll(".vme-lay[data-i]")];
      let at = els.length;
      for (let k = 0; k < els.length; k++) { const r = els[k].getBoundingClientRect(); if (ev.clientY < r.top + r.height / 2) { at = k; break; } }
      setOver(at);
    };
    const upf = () => {
      window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", upf);
      if (on) {
        const els = [...listRef.current.querySelectorAll(".vme-lay[data-i]")];
        setDragging(null); setOver(null);
        const ids = els.map((el) => Number(el.dataset.i));
        const atEl = ids[overRef.current] ?? null;
        const rest = order.filter((k) => !list.includes(k));
        let pos = atEl == null ? rest.length : rest.indexOf(atEl);
        if (pos < 0) pos = rest.length;
        const mine = order.filter((k) => list.includes(k));
        const next = [...rest.slice(0, pos), ...mine, ...rest.slice(pos)];
        if (next.join() !== order.join()) ed.reorder(next, list.length > 1 ? "Reorder " + list.length + " things" : "Reorder " + pls[list[0]].thing, list);
      }
    };
    window.addEventListener("pointermove", mv); window.addEventListener("pointerup", upf);
  };
  let rowNo = -1;
  return html`<div class="vme-layers" ref=${listRef} role="listbox" aria-multiselectable="true">
    ${rows.map((r) => {
      if (r.group != null) {
        const on = r.members.every((k) => ed.sel.includes(k));
        return html`<div class=${cx("vme-lay grp", on && "on")} onPointerDown=${(e) => startDrag(e, r.members)} onClick=${(e) => pick(e, r.members)}>
          <span class="ic"><${Icon} name="down" /></span><span class="nm">Group ${r.group + 1}</span><span class="d mono">${r.members.length}</span></div>`;
      }
      const i = r.i, pl = pls[i], th = thingOf(doc, pl.thing) || {}, on = ed.sel.includes(i);
      rowNo++;
      const k = rowNo;
      return html`<div class=${cx("vme-lay", r.child && "child", on && "on", pl.hidden && "dim", dragging && dragging.includes(i) && "drag",
          over === k && "drop-before")} data-i=${i} role="option" aria-selected=${on}
        onPointerDown=${(e) => { if (!e.target.closest("button")) startDrag(e, r.child ? [i] : ed.groupOf(i)); }}
        onClick=${(e) => { if (!e.target.closest("button")) pick(e, r.child || e.altKey ? [i] : ed.groupOf(i)); }}
        onMouseEnter=${() => { ed.hover = i; ed.dirty(); }} onMouseLeave=${() => { ed.hover = -1; ed.dirty(); }}>
        <span class="team" style=${{ background: ed.teamColour(th.team) }}></span>
        <span class="nm">${pl.thing}${count[pl.thing] > 1 ? html` <span class="muted">· ${nth[i]}</span>` : null}</span>
        <span class="d mono" ...${tip("Depth: higher draws in front")}>${effDepth(doc, pl)}</span>
        <button type="button" class=${cx("vme-ic", pl.hidden && "off")} onClick=${() => ed.setPlaces(pl.hidden ? "Show" : "Hide", () => ({ hidden: !pl.hidden }), [i])}
          ...${tip(pl.hidden ? "Hidden: show it" : "Hide it")}><${Icon} name="eye" /></button>
        <button type="button" class=${cx("vme-ic", !pl.locked && "faint")} onClick=${() => ed.setPlaces(pl.locked ? "Unlock" : "Lock", () => ({ locked: !pl.locked }), [i])}
          ...${tip(pl.locked ? "Locked: unlock it" : "Lock it: it cannot be dragged")}><${Icon} name=${pl.locked ? "lock" : "unlock"} /></button>
      </div>`;
    })}
    ${over === rows.filter((r) => r.group == null).length ? html`<div class="vme-drop-end"></div>` : null}
  </div>`;
}

// ---- the assets: things and pictures to drag onto the stage ------------------------------------------------------
function Assets({ ed, pics }) {
  const doc = ed.doc, things = doc.things || [];
  const loose = ((doc.assets || {}).pictures || []).filter((p) => !things.some((t) => t.picture === p.id && t.id === p.id));
  const startDrag = (e, kind, id) => {
    if (e.button !== 0) return;
    const x0 = e.clientX, y0 = e.clientY, tgt = e.currentTarget;
    let ghost = null;
    const mv = (ev) => {
      if (!ghost && Math.hypot(ev.clientX - x0, ev.clientY - y0) < 4) return;
      if (!ghost) {
        ghost = tgt.cloneNode(true); ghost.classList.add("vme-ghost"); document.body.appendChild(ghost);
      }
      ghost.style.left = ev.clientX - 22 + "px"; ghost.style.top = ev.clientY - 22 + "px";
    };
    const upf = (ev) => {
      window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", upf);
      if (!ghost) return;
      ghost.remove();
      const r = ed.els.view.getBoundingClientRect();
      if (ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom) {
        const [x, y] = ed.toStage(ev.clientX - r.left, ev.clientY - r.top);
        ed.add(kind, id, x, y);
      }
    };
    window.addEventListener("pointermove", mv); window.addEventListener("pointerup", upf);
  };
  const tile = (kind, id, p, team, label) => html`<button type="button" class="vme-asset" data-id=${id} data-kind=${kind}
      onPointerDown=${(e) => startDrag(e, kind, id)} onDblClick=${() => ed.add(kind, id)}
      onKeyDown=${(e) => { if (e.key === "Enter") { e.preventDefault(); ed.add(kind, id); } }}
      ...${tip({ head: label, lines: [kind === "thing" ? TEAM_LABEL[team] + " · drag it onto the stage, or press Enter to put one in the middle" : "A picture: dragged onto the stage it becomes a thing of its own"] })}>
    <${Thumb} p=${Object.assign({}, p, { team })} size=${40} />
    <span class="nm">${id}</span>
    ${kind === "thing" ? html`<span class="team" style=${{ background: ed.teamColour(team) }}></span>` : null}
  </button>`;
  if (!things.length && !loose.length) {
    return html`<div class="vme-empty-s">No pictures yet. <${Button} size="sm" kind="ghost" icon="plus" onClick=${() => call("vmodes.pick")}>Bring art in…<//></div>`;
  }
  return html`<div class="vme-assets">
    ${things.length ? html`<div class="vme-lab"><span>Things</span></div><div class="vme-asset-grid">
      ${things.map((t) => tile("thing", t.id, pics.find((p) => p.id === t.picture), t.team, t.id))}</div>` : null}
    ${loose.length ? html`<div class="vme-lab"><span>Pictures</span></div><div class="vme-asset-grid">
      ${loose.map((p) => tile("picture", p.id, pics.find((q) => q.id === p.id), "scenery", p.id))}</div>` : null}
  </div>`;
}

// ---- the command palette and the shortcut sheet ---------------------------------------------------------------
function commands(ed, ctx) {
  const doc = ed.doc, out = [], has = ed.sel.length > 0;
  const add = (label, run, keys, ok = true) => { if (ok) out.push({ label, run, keys }); };
  for (const t of doc.things || []) add("Add " + t.id, () => ed.add("thing", t.id));
  for (const p of ((doc.assets || {}).pictures || [])) if (!(doc.things || []).some((t) => t.id === p.id)) add("Add " + p.id + " (picture)", () => ed.add("picture", p.id));
  doc.phases.forEach((p, i) => add("Phase: " + (p.title || p.id) + " · " + p.kind, () => ed.setPhase(i), "", i !== ed.ph));
  add("Select everything", () => ed.setSel(ed.places().map((_, i) => i)), "Ctrl A");
  add("Undo" + (ed.hist.undo_label ? ": " + ed.hist.undo_label : ""), () => ed.undoRedo("undo"), "Ctrl Z", ed.hist.can_undo);
  add("Redo" + (ed.hist.redo_label ? ": " + ed.hist.redo_label : ""), () => ed.undoRedo("redo"), "Ctrl Shift Z", ed.hist.can_redo);
  for (const [k, l] of [["left", "Align left"], ["centre", "Align centers"], ["right", "Align right"], ["top", "Align top"], ["middle", "Align middles"], ["bottom", "Align bottom"]])
    add(l, () => ed.align(k), "", has);
  add("Distribute across", () => ed.align("dist_x"), "", ed.sel.length > 2);
  add("Distribute down", () => ed.align("dist_y"), "", ed.sel.length > 2);
  add("Group", () => ed.group(), "Ctrl G", ed.sel.length > 1);
  add("Ungroup", () => ed.ungroup(), "Ctrl Shift G", has);
  add("Duplicate", () => ed.duplicate(), "Ctrl D", has);
  add("Copy", () => ed.copy(), "Ctrl C", has);
  add("Paste", () => ed.paste(), "Ctrl V");
  add("Remove", () => ed.remove(), "Delete", has);
  add("Lock or unlock", () => ed.toggle("locked"), "", has);
  add("Hide or show", () => ed.toggle("hidden"), "", has);
  add("Bring to front", () => ed.arrange("front"), "Ctrl Shift ]", has);
  add("Bring forward", () => ed.arrange("forward"), "Ctrl ]", has);
  add("Send backward", () => ed.arrange("backward"), "Ctrl [", has);
  add("Send to back", () => ed.arrange("back"), "Ctrl Shift [", has);
  add("Zoom to fit", () => ed.fit(), "Ctrl 0");
  add("Zoom to 100%", () => ed.zoomTo(1), "Ctrl 1");
  for (const [k, l] of [["grid", "grid"], ["snap", "snapping"], ["hits", "hit boxes"], ["safe", "safe area"], ["bezel", "machine's glass"], ["title", "title card"]])
    add((ed.opts[k] ? "Hide the " : "Show the ") + l, () => ctx.toggleOpt(k), k === "hits" ? "H" : "");
  for (const m of ctx.machines || []) add("Glass of " + m.label, () => ctx.setMachine(m.key), "", m.key !== ed.info.machine || !ed.opts.bezel);
  for (const g of [4, 8, 16, 32]) add("Grid of " + g + " px", () => ed.edit("Grid " + g, (d) => { d.editor = Object.assign({}, d.editor || {}, { grid: g }); }), "", ed.grid() !== g);
  add("Play this phase", () => ctx.play(), "F5");
  add("Shortcuts", () => ctx.keys(), "?");
  return out;
}

function Palette({ ed, ctx, onClose, start = "" }) {
  const [q, setQ] = useState(start);
  const inRef = useRef(null);
  useLayoutEffect(() => { const el = inRef.current; if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } }, []);
  const [at, setAt] = useState(0);
  const list = useMemo(() => commands(ed, ctx), [ed.doc, ed.sel.join(","), ed.hist]);
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  const hits = list.filter((c) => words.every((w) => c.label.toLowerCase().includes(w))).slice(0, 12);
  const run = (c) => { onClose(); if (c) setTimeout(() => c.run(), 0); };
  return html`<div class="vme-scrim" onPointerDown=${(e) => { if (e.target === e.currentTarget) onClose(); }}>
    <div class="vme-palette" role="dialog" aria-label="Commands">
      <input autofocus class="vme-pal-in" placeholder="Type a command: add drone, align top, zoom…" value=${q}
        ref=${inRef}
        onInput=${(e) => { setQ(e.target.value); setAt(0); }}
        onKeyDown=${(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setAt((a) => Math.min(hits.length - 1, a + 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setAt((a) => Math.max(0, a - 1)); }
          else if (e.key === "Enter") { e.preventDefault(); run(hits[at]); }
          else if (e.key === "Escape") { e.preventDefault(); onClose(); }
          e.stopPropagation();
        }} />
      <div class="vme-pal-list">
        ${hits.length ? hits.map((c, k) => html`<div class=${cx("vme-pal-row", k === at && "on")} onPointerDown=${() => run(c)} onMouseEnter=${() => setAt(k)}>
          <span>${c.label}</span>${c.keys ? html`<span class="kbd">${c.keys}</span>` : null}</div>`)
          : html`<div class="vme-pal-none">No command by that name</div>`}
      </div>
    </div>
  </div>`;
}

const SHORTCUTS = [
  ["Drag", "Move; Shift keeps to one direction; Ctrl places freely; Alt leaves a copy behind"],
  ["Handles", "Scale from the opposite side (Shift: in steps); the round one turns (Shift: 15°)"],
  ["Shift click / drag a box", "Add to the selection"],
  ["Tab / Shift Tab", "The next / the last thing on the stage"],
  ["Arrows / Shift arrows", "Nudge 1 px / 10 px"],
  ["Ctrl Z / Ctrl Shift Z", "Undo / redo, without limit, even after a reload"],
  ["Ctrl C / Ctrl V / Ctrl D", "Copy / paste / duplicate"],
  ["Delete", "Remove the selection"],
  ["Ctrl G / Ctrl Shift G", "Group / ungroup"],
  ["Ctrl ] / Ctrl [", "Forward / backward; with Shift: to the front / back"],
  ["Ctrl A", "Select everything on the stage"],
  ["Space drag, middle drag, wheel", "Pan"],
  ["Ctrl wheel / Ctrl 0 / Ctrl 1", "Zoom at the pointer / to fit / to 100%"],
  ["Drag out of a ruler", "A guide; drag it back to remove it"],
  ["H", "Show hit boxes"],
  ["Ctrl K / Ctrl P", "Commands / phases"],
  ["F6", "The next panel: stage, inspector, layers"],
  ["F5", "Play this phase"],
  ["Escape", "Clear the selection"],
];

function KeySheet({ onClose }) {
  return html`<div class="vme-scrim" onPointerDown=${(e) => { if (e.target === e.currentTarget) onClose(); }}>
    <div class="vme-palette vme-keys" role="dialog" aria-label="Shortcuts">
      <div class="vme-keys-h"><b>Shortcuts</b><span class="sp"></span><${Button} kind="ghost" size="sm" icon="x" title="Close (Escape)" onClick=${onClose} /></div>
      <div class="vme-keys-b">${SHORTCUTS.map(([k, d]) => html`<div class="vme-key-row"><span class="kbd">${k}</span><span>${d}</span></div>`)}</div>
    </div>
  </div>`;
}

// ---- the page ---------------------------------------------------------------------------------------------------
export function VideoModeEditor({ s, onClose, onPlay }) {
  const [err, setErr] = useState("");
  const [, setVer] = useState(0);
  const [pal, setPal] = useState(null);
  const [keys, setKeys] = useState(false);
  const [docks, setDocks] = useState(loadDocks);
  const [pics, setPics] = useState([]);
  const edRef = useRef(null);
  const root = useRef(null), view = useRef(null), canvas = useRef(null), over = useRef(null), rx = useRef(null), ry = useRef(null), coords = useRef(null);
  const ed = edRef.current;
  const bump = () => setVer((v) => v + 1);

  useEffect(() => {
    let live = true, gl = null;
    (async () => {
      try {
        const inf = await call("vmodes.edit_open");
        if (!live) return;
        if (!inf || !inf.doc) { setErr(((inf && inf.problems) || ["The editor did not open."]).join("\n")); return; }
        const eng = await newEngine(inf.engine_js || s.engine_js, inf.engine_wasm || s.engine_wasm);
        gl = new GLStage(canvas.current, inf.stage[0], inf.stage[1]);
        const textures = async (r) => {
          await Promise.all((r.pictures || []).map(async (p, i) => {
            let src;
            try { src = p.path ? await loadImage(mediaUrl(p.path) + "&v=" + (p.v || 0)) : placeholderSheet(p); }
            catch (e) { src = placeholderSheet(Object.assign({}, p, { fh: p.h, frames: 1 })); }
            gl.setTexture(i, src);
            gl.setSheet(i, p.fw || p.w, p.fh || p.h, p.cols || 1);
          }));
          try { await document.fonts.load("700 32px 'IBM Plex Mono'"); } catch (e) { /* the fallback face draws */ }
          (r.fonts || []).forEach((f) => gl.setTexture(f.atlas, glyphSheet(f)));
          if (live) setPics(r.pictures || []);
        };
        if (inf.pack) {
          const v = eng.load(b64bytes(inf.pack));
          if (v) inf.pack = null;
        }
        await textures(inf);
        if (!live) { gl.dispose(); return; }
        const e = new Ed(inf, eng, gl, { view: view.current, over: over.current, rulerX: rx.current, rulerY: ry.current },
          { panels: bump, textures, cursor: (x, y) => { if (coords.current) coords.current.textContent = "x " + Math.round(x) + " · y " + Math.round(y); } });
        if (!inf.pack) { e.packOk = false; e.packErr = (inf.problems || []).join("\n"); }
        const first = (s.vm_phase && inf.doc.phases.findIndex((p) => p.id === s.vm_phase)) || 0;
        e.ph = Math.max(0, first);
        edRef.current = e;
        e.fit();
        bump();
        window.__vmEditor = {
          ready: true, ed: e,
          doc: () => e.doc,
          phase: (id) => e.setPhase(Math.max(0, e.doc.phases.findIndex((p) => p.id === id))),
          selectIndex: (i) => e.setSel(Array.isArray(i) ? i : [i]),
          centreOf: (i) => { const b = e.shape(i); if (!b) return null; const u = aabbOf(b); return [(u.l + u.r) / 2, (u.t + u.b) / 2]; },
          toPage: (x, y) => { const r = e.els.view.getBoundingClientRect(), [a, b] = e.toView(x, y); return [r.left + a, r.top + b]; },
          perf: () => e.perf(), perfReset: () => e.perfReset(),
          canUndo: () => !!e.hist.can_undo, settled: () => e.queue.then(() => true),
        };
      } catch (x) { if (live) setErr(String(x && x.message || x)); }
    })();
    return () => {
      live = false;
      if (edRef.current && edRef.current.raf) cancelAnimationFrame(edRef.current.raf);
      edRef.current = null;
      if (gl) gl.dispose();
      window.__vmEditor = null;
    };
  }, [s.slug]);

  // the view's size follows the window and the docks
  useEffect(() => {
    if (!view.current) return undefined;
    const ro = new ResizeObserver(() => { const e = edRef.current; if (e) e.dirty(true); });
    ro.observe(view.current);
    return () => ro.disconnect();
  }, []);
  // the theme: overlay colours follow it
  useEffect(() => {
    const mo = new MutationObserver(() => { const e = edRef.current; if (e) { e.colours(); e.dirty(true); } });
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style"] });
    return () => mo.disconnect();
  }, []);
  useEffect(() => { try { localStorage.setItem("vme.docks", JSON.stringify(docks)); } catch (e) { /* private mode */ } }, [docks]);
  useEffect(() => { const e = edRef.current; if (e) e.dirty(true); }, [docks]);

  const toggleOpt = (k) => {
    const e = edRef.current; if (!e) return;
    e.opts = Object.assign({}, e.opts, { [k]: !e.opts[k] });
    try { localStorage.setItem("vme.view", JSON.stringify(e.opts)); } catch (x) { /* private mode */ }
    e.dirty(true); bump();
  };
  const cardFor = () => {
    const e = edRef.current;
    const c = ((e.doc.flow || {}).cards || []).find((k) => k.card === "phase" && k.phase === e.phase().id);
    return c ? c.id : null;
  };
  const play = () => { const e = edRef.current; if (e) e.queue.then(() => onPlay(cardFor())); };
  const setMachine = (key) => {
    // the glass shown follows the machine picked on the tab (Pack for the machine uses the same one)
    const e = edRef.current; if (!e) return;
    call("vmodes.set_machine", key);
    e.info.machine = key;
    if (!e.opts.bezel) toggleOpt("bezel"); else { e.dirty(); bump(); }
  };
  const ctx = { toggleOpt, play, keys: () => setKeys(true), machines: s.machines || [], setMachine };

  // the keyboard: the editor's shortcuts, not while typing in a field
  useEffect(() => {
    const kd = (ev) => {
      const e = edRef.current;
      if (keys) { if (ev.key === "Escape" || ev.key === "?") { ev.preventDefault(); setKeys(false); } return; }
      if (!e || pal) return;
      if (!root.current || !document.body.contains(root.current)) return;
      const mod = ev.ctrlKey || ev.metaKey, k = ev.key, inField = typing(ev.target);
      if (mod && (k === "k" || k === "K")) { ev.preventDefault(); setPal({ start: "" }); return; }
      if (mod && (k === "p" || k === "P")) { ev.preventDefault(); setPal({ start: "phase " }); return; }
      if (k === "F5") { ev.preventDefault(); play(); return; }
      if (k === "F6") {
        ev.preventDefault();
        const spots = [view.current, root.current.querySelector(".vme-dock.right .vme-dock-b input, .vme-dock.right .vme-dock-b button, .vme-dock.right select"),
                       root.current.querySelector(".vme-layers .vme-lay, .vme-asset")].filter(Boolean);
        const cur = spots.findIndex((el) => el.contains(document.activeElement) || el === document.activeElement || (el.closest(".vme-dock") || el).contains(document.activeElement));
        spots[(cur + (ev.shiftKey ? spots.length - 1 : 1)) % spots.length].focus();
        return;
      }
      if (inField) return;
      if (mod && !ev.shiftKey && (k === "z" || k === "Z")) { ev.preventDefault(); e.undoRedo("undo"); return; }
      if (mod && ((ev.shiftKey && (k === "z" || k === "Z")) || k === "y" || k === "Y")) { ev.preventDefault(); e.undoRedo("redo"); return; }
      const onStage = document.activeElement === view.current || document.activeElement === document.body || root.current.contains(document.activeElement);
      if (!onStage) return;
      if (k === " " && !ev.repeat) { ev.preventDefault(); e.space = true; view.current.style.cursor = "grab"; return; }
      if (k === "?" ) { ev.preventDefault(); setKeys(true); return; }
      if (mod && (k === "a" || k === "A")) { ev.preventDefault(); e.setSel(e.places().map((_, i) => i)); return; }
      if (mod && (k === "c" || k === "C")) { ev.preventDefault(); e.copy(); return; }
      if (mod && (k === "x" || k === "X")) { ev.preventDefault(); e.copy(); e.remove(); return; }
      if (mod && (k === "v" || k === "V")) { ev.preventDefault(); e.paste(); return; }
      if (mod && (k === "d" || k === "D")) { ev.preventDefault(); e.duplicate(); return; }
      if (mod && (k === "g" || k === "G")) { ev.preventDefault(); if (ev.shiftKey) e.ungroup(); else e.group(); return; }
      if (mod && k === "0") { ev.preventDefault(); e.fit(); return; }
      if (mod && k === "1") { ev.preventDefault(); e.zoomTo(1); return; }
      if (mod && (k === "=" || k === "+")) { ev.preventDefault(); e.zoomTo(e.view.k * 1.25); return; }
      if (mod && k === "-") { ev.preventDefault(); e.zoomTo(e.view.k / 1.25); return; }
      if (mod && (k === "]" || k === "}")) { ev.preventDefault(); e.arrange(ev.shiftKey ? "front" : "forward"); return; }
      if (mod && (k === "[" || k === "{")) { ev.preventDefault(); e.arrange(ev.shiftKey ? "back" : "backward"); return; }
      if (k === "Delete" || k === "Backspace") { ev.preventDefault(); e.remove(); return; }
      if (k === "Escape") { if (e.sel.length) { ev.preventDefault(); e.setSel([]); } return; }
      if (k === "Tab" && document.activeElement === view.current) { ev.preventDefault(); e.cycle(ev.shiftKey); return; }
      if ((k === "h" || k === "H") && !mod) { ev.preventDefault(); toggleOpt("hits"); return; }
      const arrows = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
      if (arrows[k] && e.sel.length) {
        ev.preventDefault();
        const f = ev.shiftKey ? NUDGE_BIG : 1;
        e.nudge(arrows[k][0] * f, arrows[k][1] * f);
      }
    };
    const ku = (ev) => { const e = edRef.current; if (e && ev.key === " ") { e.space = false; if (view.current) view.current.style.cursor = "default"; } };
    window.addEventListener("keydown", kd); window.addEventListener("keyup", ku);
    return () => { window.removeEventListener("keydown", kd); window.removeEventListener("keyup", ku); };
  }, [pal, keys]);

  const resize = (side) => (e) => {
    e.preventDefault();
    const x0 = e.clientX, w0 = docks[side], [, lo, hi] = DOCKS[side];
    const mv = (ev) => setDocks((d) => Object.assign({}, d, { [side]: clamp(w0 + (side === "left" ? 1 : -1) * (ev.clientX - x0), lo, hi) }));
    const upf = () => { window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", upf); document.body.classList.remove("vme-resizing"); };
    document.body.classList.add("vme-resizing");
    window.addEventListener("pointermove", mv); window.addEventListener("pointerup", upf);
  };
  const dockOpen = (side, open) => setDocks((d) => Object.assign({}, d, { [side + "Open"]: open }));

  const doc = ed && ed.doc, ph = ed && ed.phase(), pls = (ph && ph.place) || [];
  const st = ed ? ed.status : { kind: "busy", text: "Opening…" };
  const sel1 = ed && ed.sel.length === 1 ? pls[ed.sel[0]] : null;
  const selThing = sel1 && thingOf(doc, sel1.thing);
  const empty = ed && !pls.length && !(ph.background || []).length;
  const optBtn = (k, icon, label, title) => html`<button type="button" class=${cx("btn ghost sm vme-opt", ed && ed.opts[k] && "on")}
    onClick=${() => toggleOpt(k)} aria-pressed=${!!(ed && ed.opts[k])} ...${tip(title)}>${icon ? html`<${Icon} name=${icon} />` : null}${label}</button>`;
  const zoomPct = ed ? Math.round(ed.view.k * 100) : 100;
  return html`<div class="vme" ref=${root} style=${{ "--vme-left": (docks.leftOpen ? docks.left : 28) + "px", "--vme-right": (docks.rightOpen ? docks.right : 28) + "px" }}>
    <div class="vme-top">
      <${Button} kind="ghost" size="sm" icon="left" title=${T.done} onClick=${() => { const e = edRef.current; (e ? e.queue : Promise.resolve()).then(onClose); }}>Done<//>
      <span class="vme-name">${(doc && doc.title) || s.title || s.slug}</span><span class="vme-crumb">video mode</span>
      <span class="vme-vsep"></span>
      ${ed ? html`<${Select} sm cls="vme-phase-pick" value=${String(ed.ph)} title="The phase on the stage (Ctrl P)"
        options=${doc.phases.map((p, i) => ({ value: String(i), label: (i + 1) + " · " + (p.title || p.id) + " · " + p.kind }))}
        onChange=${(v) => ed.setPhase(Number(v))} />` : null}
      <span class="vme-vsep"></span>
      <${Button} kind="ghost" size="sm" icon="undo" disabled=${!ed || !ed.hist.can_undo} title=${T.undo(ed && ed.hist.undo_label)} onClick=${() => ed.undoRedo("undo")} />
      <${Button} kind="ghost" size="sm" icon="redo" disabled=${!ed || !ed.hist.can_redo} title=${T.redo(ed && ed.hist.redo_label)} onClick=${() => ed.undoRedo("redo")} />
      <span class="sp"></span>
      <span class=${cx("chip sm vme-status", st.kind === "ok" ? "ok" : st.kind === "err" ? "err" : "")}
        ...${tip(st.kind === "err" ? { head: "That change was not kept", lines: st.why || [] } : T.saved)}>${st.text}</span>
      <span class="vme-vsep"></span>
      ${optBtn("grid", "", "Grid", T.grid)}${optBtn("snap", "", "Snap", T.snap)}${optBtn("safe", "", "Safe area", T.safe)}${optBtn("bezel", "", "Glass", T.bezel)}${optBtn("hits", "", "Hit boxes", T.hits)}${optBtn("title", "", "Title", T.title)}
      <span class="vme-vsep"></span>
      <div class="seg sm vme-zoom">
        <button type="button" class=${cx(ed && ed.view.fit && "on")} onClick=${() => ed && ed.fit()} ...${tip(T.fit)}>Fit</button>
        <button type="button" class=${cx(ed && !ed.view.fit && "on", "mono")} onClick=${() => ed && ed.zoomTo(ed.view.k * 1.25)} ...${tip("Zoom in (Ctrl +); Ctrl wheel zooms at the pointer")}>${zoomPct}%</button>
        <button type="button" class=${cx(zoomPct === 100 && "on")} onClick=${() => ed && ed.zoomTo(1)} ...${tip(T.one)}>100%</button>
      </div>
      <${Button} kind="ghost" size="sm" icon="search" title=${T.palette} onClick=${() => setPal({ start: "" })} />
      <${Button} kind="ghost" size="sm" icon="question" title=${T.keys} onClick=${() => setKeys(true)} />
      <${Button} kind="primary" size="sm" icon="play" title=${T.play} disabled=${!ed || !ed.packOk} onClick=${play}>Play<//>
    </div>
    <div class=${cx("vme-dock left", !docks.leftOpen && "shut")}>
      ${docks.leftOpen ? html`
        <div class="vme-dock-h"><span class="t">Layers</span><span class="sp"></span><span class="chip sm mono">${pls.length}</span>
          <button type="button" class="btn ghost icon xs" onClick=${() => dockOpen("left", false)} ...${tip("Fold the layers away")}><${Icon} name="left" /></button></div>
        <div class="vme-dock-scroll">${ed ? html`<${Layers} ed=${ed} />` : null}</div>
        <div class="vme-dock-h sub"><span class="t">Assets</span></div>
        <div class="vme-dock-scroll assets">${ed ? html`<${Assets} ed=${ed} pics=${pics} />` : null}</div>
        <div class="vme-split" onPointerDown=${resize("left")}></div>`
      : html`<button type="button" class="vme-rail" onClick=${() => dockOpen("left", true)} ...${tip("Layers and assets")}><${Icon} name="list" /></button>`}
    </div>
    <div class="vme-centre">
      <div class="vme-corner"></div>
      <canvas class="vme-ruler x" ref=${rx} onPointerDown=${(e) => ed && ed.rulerDown(e, "x")} ...${tip("Drag down from here for a guide")}></canvas>
      <canvas class="vme-ruler y" ref=${ry} onPointerDown=${(e) => ed && ed.rulerDown(e, "y")} ...${tip("Drag across from here for a guide")}></canvas>
      <div class="vme-stage" ref=${view} tabindex="0" aria-label="The stage"
        onPointerDown=${(e) => ed && ed.down(e)} onPointerMove=${(e) => ed && ed.move(e)} onPointerUp=${(e) => ed && ed.up(e)}
        onPointerLeave=${() => { if (ed && !ed.drag) { ed.hover = -1; ed.hoverLocked = -1; ed.cursor = null; ed.dirty(true); } }}
        onWheel=${(e) => ed && ed.wheel(e)} onDblClick=${(e) => {
          if (!ed) return;
          const [cx2, cy2] = ed.local(e), [x, y] = ed.toStage(cx2, cy2), i = ed.hitTest(x, y);
          if (i >= 0) ed.setSel([i]);                  // into a group: just the one
        }} onContextMenu=${(e) => e.preventDefault()}>
        <canvas class="vme-gl" ref=${canvas}></canvas>
        <canvas class="vme-over" ref=${over}></canvas>
        ${empty ? html`<div class="vme-empty"><${Empty} icon="image" title="Drop pictures here, or pick a game kind"
            action=${html`<div class="row" style="gap:8px;justify-content:center">
              <${Button} kind="primary" icon="plus" onClick=${() => setPal({ start: "add " })}>Add a thing<//>
              <${Button} icon="list" onClick=${() => setPal({ start: "phase " })}>Pick a phase<//></div>`}>
            Drag a thing or a picture from Assets onto the stage. Game kinds are picked for a phase on the storyboard.<//></div>` : null}
        ${ed && !ed.packOk ? html`<div class="vme-stage-note"><${Icon} name="warn" /><span>${ed.packErr || "This phase cannot be drawn yet."}</span></div>` : null}
        ${err ? html`<div class="vme-stage-note"><${Icon} name="error" /><span>${err}</span></div>` : null}
      </div>
    </div>
    <div class=${cx("vme-dock right", !docks.rightOpen && "shut")}>
      ${docks.rightOpen ? html`
        <div class="vme-split" onPointerDown=${resize("right")}></div>
        <div class="vme-dock-h">
          ${sel1 ? html`<span class="team" style=${{ background: ed.teamColour((selThing || {}).team) }}></span><span class="t">${sel1.thing}</span>`
            : ed && ed.sel.length > 1 ? html`<span class="t">${ed.sel.length} things</span>` : html`<span class="t">${ph ? (ph.title || ph.id) : "Inspector"}</span>`}
          <span class="sp"></span>
          <button type="button" class="btn ghost icon xs" onClick=${() => dockOpen("right", false)} ...${tip("Fold the inspector away")}><${Icon} name="right" /></button>
        </div>
        <div class="vme-dock-scroll">${ed ? html`<${Inspector} ed=${ed} pics=${pics} />` : null}</div>`
      : html`<button type="button" class="vme-rail" onClick=${() => dockOpen("right", true)} ...${tip("The inspector")}><${Icon} name="edit" /></button>`}
    </div>
    <div class="vme-bar">
      <span class="mono vme-xy" ref=${coords}></span>
      <span class="vme-vsep"></span>
      <span class="mono">${ed && ed.sel.length ? (() => { const b = ed.selBounds(); return b ? ed.sel.length + " picked · " + Math.round(b.r - b.l) + " × " + Math.round(b.b - b.t) + " px" : ""; })() : "Nothing picked"}</span>
      <span class="sp"></span>
      <span class="mono muted">${doc ? doc.stage.width + " × " + doc.stage.height : ""}</span>
      <span class="vme-vsep"></span>
      <span class="mono muted" ...${tip("Things on the stage when the phase starts")}>${pls.length} on the stage</span>
      <span class="vme-vsep"></span>
      <span class="muted">Grid ${ed ? ed.grid() : 8}</span>
    </div>
    ${pal && ed ? html`<${Palette} ed=${ed} ctx=${ctx} start=${pal.start} onClose=${() => { setPal(null); if (view.current) view.current.focus(); }} />` : null}
    ${keys ? html`<${KeySheet} onClose=${() => setKeys(false)} />` : null}
  </div>`;
}
