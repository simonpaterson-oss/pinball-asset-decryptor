// The video mode editor's timeline (PAD-1664): the motion inside a phase, over its seconds.
//
// Tracks for each placed thing's keyframed motion (position on a bezier path, scale, turn, fade, tint), for the
// spawn waves and for sounds at set times, with markers and a loop region. Scrubbing IS replaying: the stage shows
// the machine's own engine played from the phase's start to the playhead with nothing pressed (vmw_seek), made
// instant by the engine keeping a snapshot every second. A drag on a key moves it in the engine's loaded tables
// (vmw_key_set / vmw_key_at / vmw_key_insert) and the stage follows every frame; it is committed, as one undo step,
// when the pointer lets go, like every other change in the editor.
//
// The document side (format 2): docs/plans/video_mode_maker.md section 3, "tracks and sound_track". Markers live in
// doc.editor.markers[phase id]; the loop region and the snap are the user's own, kept in the browser.

import { html, useEffect, useRef, useState, Button, Icon, Empty, tip, cx } from "../core/ui.js";
import { Scrub, Group } from "./vmodes_edit.js";

for (const href of ["/static/css/tabs/vmodes_timeline.css"]) {
  if (!document.querySelector(`link[href="${href}"]`)) {
    const l = document.createElement("link"); l.rel = "stylesheet"; l.href = href; document.head.appendChild(l);
  }
}

export const SPS = 60;
export const PROPS = [["motion", "Position"], ["scale", "Scale"], ["turn", "Turn"], ["alpha", "Fade"], ["tint", "Tint"]];
const PROP_LABEL = Object.fromEntries(PROPS);
export const EASES = ["linear", "in", "out", "in_out", "back_out", "bounce_out", "elastic_out", "step"];
const EASE_LABEL = { linear: "Linear", in: "Ease in", out: "Ease out", in_out: "Ease in and out", back_out: "Overshoot",
                     bounce_out: "Bounce", elastic_out: "Spring", step: "Hold, then jump" };
const EASE_ICON = { linear: "M3 27 L37 3", in: "M3 27 C 20 27, 30 20, 37 3", out: "M3 27 C 10 10, 20 3, 37 3",
                    in_out: "M3 27 C 20 27, 20 3, 37 3", back_out: "M3 27 C 14 -6, 24 0, 37 3",
                    bounce_out: "M3 27 L20 3 L26 11 L31 3 L34 6 L37 3", elastic_out: "M3 27 L14 0 L19 8 L24 1 L29 5 L37 3",
                    step: "M3 27 H20 V3 H37" };
const ROW = 24, NAMES_W = 196, SNAP_PX = 6;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const clone = (o) => JSON.parse(JSON.stringify(o));
const r3 = (v) => Math.round(v * 1000) / 1000;
const stepOf = (s) => Math.round((Number(s) || 0) * SPS);
const secOf = (step) => r3(step / SPS);
export const fmtTime = (step) => {
  const s = Math.max(0, step) / SPS, m = Math.floor(s / 60);
  return String(m).padStart(2, "0") + ":" + (s - m * 60).toFixed(2).padStart(5, "0");
};

// ---- the model: the same maths as the engine, in floats, for what the page draws itself ---------------------
export function phaseSteps(ph) { return stepOf(ph && ph.length_s > 0 ? ph.length_s : 60); }
export function trackFor(ph, place, prop) { return (ph.tracks || []).findIndex((t) => t.place === place && t.prop === prop); }
/** where track tr of phase pi begins in the engine's track table, and its keys in the key table (compiler order) */
export function engineIndex(doc, pi, tr) {
  let t = 0, k = 0;
  doc.phases.forEach((ph, i) => {
    (ph.tracks || []).forEach((x, j) => {
      if (i < pi || (i === pi && j < tr)) { t++; k += (x.keys || []).length; }
    });
  });
  return { track: t, key0: k };
}
export function easeF(kind, t) {
  t = clamp(t, 0, 1);
  switch (kind) {
    case "in": return t * t;
    case "out": return 1 - (1 - t) * (1 - t);
    case "in_out": return t < 0.5 ? 2 * t * t : 1 - 2 * (1 - t) * (1 - t);
    case "back_out": { const u = t - 1; return 1 + 2.70158 * u * u * u + 1.70158 * u * u; }
    case "bounce_out": {
      const n = 7.5625, d = 2.75;
      if (t < 1 / d) return n * t * t;
      if (t < 2 / d) { t -= 1.5 / d; return n * t * t + 0.75; }
      if (t < 2.5 / d) { t -= 2.25 / d; return n * t * t + 0.9375; }
      t -= 2.625 / d; return n * t * t + 0.984375;
    }
    case "elastic_out": return t === 0 || t === 1 ? t : Math.pow(2, -10 * t) * Math.sin((10 * t - 0.75) * 2 * Math.PI / 3) + 1;
    case "step": return t < 1 ? 0 : 1;
    default: return t;
  }
}
/** a CSS cubic-bezier's height at u (0..1 across) */
export function curveAt(c, u) {
  const bz = (a, b, t) => { const m = 1 - t; return 3 * m * m * t * a + 3 * m * t * t * b + t * t * t; };
  let lo = 0, hi = 1;
  for (let i = 0; i < 40; i++) { const mid = (lo + hi) / 2; if (bz(c[0], c[2], mid) < u) lo = mid; else hi = mid; }
  return bz(c[1], c[3], (lo + hi) / 2);
}
const keyEase = (k, u) => (k.curve ? curveAt(k.curve, u) : easeF(k.ease || "linear", u));
const tintOf = (s) => { const h = ((s || "#ffffff") + "ff").slice(1, 9); return [0, 2, 4, 6].map((i) => parseInt(h.slice(i, i + 2), 16)); };
const tintHex = (c) => "#" + c.map((v) => clamp(Math.round(v), 0, 255).toString(16).padStart(2, "0")).join("");
/** a segment's two control handles as the engine takes them: a missing one is a third of the way along the line */
export function handles(k0, k1) {
  const dx = k1.x - k0.x, dy = k1.y - k0.y, o = k0.out || [0, 0], i = k1.in || [0, 0];
  return [o[0] || o[1] ? o : [dx / 3, dy / 3], i[0] || i[1] ? i : [-dx / 3, -dy / 3]];
}
export function bez(p0, p1, p2, p3, w) { const m = 1 - w; return m * m * m * p0 + 3 * m * m * w * p1 + 3 * m * w * w * p2 + w * w * w * p3; }
/** a track's value at a play step: [x, y] for motion, [r, g, b, a] for tint, a number for the rest */
export function evalTrack(tr, step) {
  const ks = tr.keys || [];
  if (!ks.length) return null;
  const at = ks.map((k) => stepOf(k.at_s));
  let s = 0, w = 0;
  if (step >= at[at.length - 1]) s = ks.length - 1;
  else if (step > at[0]) {
    while (s < ks.length - 2 && at[s + 1] <= step) s++;
    w = keyEase(ks[s], (step - at[s]) / (at[s + 1] - at[s]));
  }
  const k0 = ks[s], k1 = ks[s + 1];
  if (tr.prop === "motion") {
    if (!k1 || w === 0) return [k0.x, k0.y];
    const [o, i] = handles(k0, k1);
    return [bez(k0.x, k0.x + o[0], k1.x + i[0], k1.x, w), bez(k0.y, k0.y + o[1], k1.y + i[1], k1.y, w)];
  }
  if (tr.prop === "tint") {
    const a = tintOf(k0.tint);
    if (!k1 || w === 0) return a;
    const b = tintOf(k1.tint);
    return a.map((v, n) => v + (b[n] - v) * w);
  }
  if (!k1 || w === 0) return k0.v;
  return k0.v + (k1.v - k0.v) * w;
}
/** the value a new key on `prop` takes at `step`: the track's own there, else the place's */
function valueAt(ph, place, prop, step, drawn) {
  const ti = trackFor(ph, place, prop);
  if (ti >= 0) return evalTrack(ph.tracks[ti], step);
  const pl = ph.place[place];
  if (prop === "motion") return drawn ? [drawn.x, drawn.y] : [pl.x, pl.y];
  if (prop === "scale") return pl.scale == null ? 1 : pl.scale;
  if (prop === "turn") return pl.turn || 0;
  if (prop === "alpha") return 1;
  return [255, 255, 255, 255];
}
function keyFrom(prop, at, val, ease = "linear") {
  const k = { at_s: secOf(at) };
  if (prop === "motion") { k.x = r3(val[0]); k.y = r3(val[1]); }
  else if (prop === "tint") k.tint = tintHex(val);
  else k.v = r3(val);
  if (ease !== "linear") k.ease = ease;
  return k;
}
/** a place list changed (removed things): drop their tracks and renumber the rest. map: old index -> new, or -1 */
export function remapTracks(ph, map) {
  if (!ph.tracks) return;
  ph.tracks = ph.tracks.filter((t) => map[t.place] != null && map[t.place] >= 0).map((t) => Object.assign(t, { place: map[t.place] }));
  if (!ph.tracks.length) delete ph.tracks;
}
export function markersOf(doc, ph) { return ((doc.editor && doc.editor.markers) || {})[ph.id] || []; }
function setMarkers(doc, ph, list) {
  doc.editor = Object.assign({}, doc.editor || {});
  const m = Object.assign({}, doc.editor.markers || {});
  if (list.length) m[ph.id] = list.sort((a, b) => a.at_s - b.at_s); else delete m[ph.id];
  if (Object.keys(m).length) doc.editor.markers = m; else delete doc.editor.markers;
}
function musicOf(doc, ph) { return ((doc.assets || {}).sounds || []).find((s) => s.id === ph.music) || null; }

// ---- the controller: lives on the editor (ed.tlc), owns the playhead, the live drags and the stage's path overlay ----
export class TimelineCtl {
  constructor(ed) {
    this.ed = ed; this.step = 0; this.key = null; this.playing = false; this.raf = 0; this.live = null;
    this.paintFns = new Set();
    let v = {};
    try { v = JSON.parse(localStorage.getItem("vme.tl") || "{}") || {}; } catch (e) { v = {}; }
    this.snap = v.snap || "q"; this.loops = v.loops || {}; this.zoom = null;
    this.pick = null;                       // {kind: "marker"|"sound"|"wave", i} picked on the timeline
  }
  save() { try { localStorage.setItem("vme.tl", JSON.stringify({ snap: this.snap, loops: this.loops })); } catch (e) { /* private mode */ } }
  ph() { return this.ed.phase(); }
  len() { return phaseSteps(this.ph()); }
  loop() { const l = this.loops[this.ph().id]; return l && l.on ? l : null; }
  onPaint(fn) { this.paintFns.add(fn); return () => this.paintFns.delete(fn); }
  paint() { for (const f of this.paintFns) f(); }
  phaseChanged() { this.stop(); this.step = 0; this.key = null; this.pick = null; this.zoom = null; this.ed.dirty(); this.paint(); }
  seek(step) {
    const s = clamp(Math.round(step), 0, Math.max(this.len(), 1) * 4);
    if (s === this.step) return;
    this.step = s; this.ed.dirty(); this.paint();
  }
  stepBy(n) { this.stop(); this.seek(this.step + n); }
  home() { this.stop(); const l = this.loop(); this.seek(l ? l.a : 0); }
  stop() { if (this.playing) { this.playing = false; cancelAnimationFrame(this.raf); this.ed.notify.panels(); } }
  toggle() {
    if (this.playing) { this.stop(); return; }
    this.playing = true;
    const l0 = this.loop();
    if (l0 && (this.step < l0.a || this.step >= l0.b)) this.seek(l0.a);
    else if (!l0 && this.step >= this.len()) this.seek(0);
    let last = performance.now(), acc = 0;
    const tick = (t) => {
      if (!this.playing) return;
      acc += Math.min(100, t - last) * SPS / 1000; last = t;
      const n = Math.floor(acc); acc -= n;
      if (n) {
        let s = this.step + n;
        const l = this.loop();
        if (l && s >= l.b) s = l.a + ((s - l.a) % Math.max(1, l.b - l.a));
        else if (!l && s >= this.len()) { s = this.len(); this.seek(s); this.stop(); return; }
        this.seek(s);
      }
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
    this.ed.notify.panels();
  }
  // -- snapping ------------------------------------------------------------------------------------------------------
  grid() {
    if (this.snap === "q") return 15;
    if (this.snap === "beat") { const m = musicOf(this.ed.doc, this.ph()); if (m && m.tempo_bpm) return SPS * 60 / m.tempo_bpm; }
    return 0;
  }
  snapStep(step, pxPerStep, skip) {
    let best = Math.round(step), bestD = SNAP_PX / Math.max(pxPerStep, 1e-6);
    const near = (s) => { const d = Math.abs(s - step); if (d < bestD) { bestD = d; best = Math.round(s); } };
    const ph = this.ph();
    near(this.step);
    markersOf(this.ed.doc, ph).forEach((m) => near(stepOf(m.at_s)));
    (ph.tracks || []).forEach((t, ti) => t.keys.forEach((k, ki) => { if (!skip || skip[0] !== ti || skip[1] !== ki) near(stepOf(k.at_s)); }));
    const g = this.grid();
    if (g > 0 && bestD >= SNAP_PX / Math.max(pxPerStep, 1e-6)) {
      const m = musicOf(this.ed.doc, ph), off = this.snap === "beat" && m ? stepOf(m.beat_offset_s || 0) : 0;
      best = Math.round(Math.round((step - off) / g) * g + off);
    }
    return Math.max(0, best);
  }
  // -- the stage: what the engine draws at the playhead, with any live drag put into its tables first ------------------
  draw() {
    const ed = this.ed, e = ed.e;
    if (this.live && this.live.apply) this.live.apply(e);
    if (this.step > 0) e.seek(ed.ph, this.step, 2);
    else e.editStill(ed.ph, ed.opts.title ? 1 : 0);
  }
  // -- keys --------------------------------------------------------------------------------------------------------------
  /** add keys at the playhead for the picked things: each of their tracks, or a position key when they have none */
  addKeys(props) {
    const ed = this.ed, sel = ed.sel.slice();
    if (!sel.length) { ed.notify.flash && ed.notify.flash("Pick a thing on the stage first"); return; }
    const at = this.step, drawn = ed.boxes;
    let added = null;
    ed.edit(sel.length > 1 ? "Add keyframes" : "Add a keyframe", (doc, ph) => {
      ph.tracks = ph.tracks || [];
      for (const i of sel) {
        const want = props || (ph.tracks.some((t) => t.place === i) ? ph.tracks.filter((t) => t.place === i).map((t) => t.prop) : ["motion"]);
        for (const prop of want) {
          let ti = trackFor(ph, i, prop);
          const val = valueAt(ph, i, prop, at, drawn[i] && drawn[i].alive ? drawn[i] : null);
          if (ti < 0) { ph.tracks.push({ place: i, prop, keys: [] }); ti = ph.tracks.length - 1; }
          const ks = ph.tracks[ti].keys, k = ks.findIndex((x) => stepOf(x.at_s) === at);
          if (k >= 0) continue;
          ks.push(keyFrom(prop, at, val, prop === "motion" ? "in_out" : "linear"));
          ks.sort((a, b) => a.at_s - b.at_s);
          added = [ti, ks.findIndex((x) => stepOf(x.at_s) === at)];
        }
      }
    });
    if (added) { this.key = { tr: added[0], k: added[1] }; this.pick = null; }
    ed.notify.panels();
  }
  removeKey() {
    const k = this.key; if (!k) return false;
    this.key = null;
    this.ed.edit("Remove a keyframe", (doc, ph) => {
      const tr = ph.tracks[k.tr]; if (!tr) return false;
      tr.keys.splice(k.k, 1);
      if (!tr.keys.length) ph.tracks.splice(k.tr, 1);
      if (!ph.tracks.length) delete ph.tracks;
    });
    return true;
  }
  setKey(label, patch, tr = this.key && this.key.tr, k = this.key && this.key.k) {
    if (tr == null) return;
    this.ed.edit(label, (doc, ph) => {
      const key = ph.tracks && ph.tracks[tr] && ph.tracks[tr].keys[k];
      if (!key) return false;
      patch(key, ph.tracks[tr]);
      for (const f of ["in", "out"]) if (key[f] && !key[f][0] && !key[f][1]) delete key[f];
    });
  }
  /** a key's values live in the engine while a field or handle is dragged (no commit) */
  liveKey(tr, k, key) {
    const ed = this.ed, ph = ed.phase(), t = ph.tracks[tr];
    const gi = engineIndex(ed.doc, ed.ph, tr).key0 + k, prop = t.prop;
    const prev = k > 0 ? stepOf(t.keys[k - 1].at_s) : 0;
    this.live = { apply: (e) => {
      if (prop === "motion") e.keySet(gi, key.x, key.y, (key.out || [0, 0])[0], (key.out || [0, 0])[1], (key.in || [0, 0])[0], (key.in || [0, 0])[1]);
      else if (prop === "tint") { const c = tintOf(key.tint); e.keySet(gi, ((c[0] << 24) | (c[1] << 16) | (c[2] << 8) | c[3]) | 0, 0, 0, 0, 0, 0, true); }
      else e.keySet(gi, key.v);
      e.seekDirty(prev);
    } };
    ed.dirty();
  }
  endLive() { this.live = null; }
  // -- the stage overlay: the picked things' motion paths, their keys and handles -----------------------------------------
  paths() {
    const ed = this.ed, ph = ed.phase(), out = [];
    (ph.tracks || []).forEach((t, ti) => { if (t.prop === "motion" && (ed.sel.includes(t.place) || (this.key && this.key.tr === ti))) out.push(ti); });
    return out;
  }
  overlay(g, P, c) {
    const ph = this.ed.phase(), lv = this.live && this.live.track;
    for (const ti of this.paths()) {
      const t = lv && lv.ti === ti ? lv.t : ph.tracks[ti], ks = t.keys;
      g.save();
      g.strokeStyle = c.info; g.lineWidth = 2; g.setLineDash([7, 6]);
      g.beginPath();
      ks.forEach((k0, i) => {
        const a = P(k0.x, k0.y);
        if (i === 0) g.moveTo(a[0], a[1]);
        const k1 = ks[i + 1]; if (!k1) return;
        const [o, n] = handles(k0, k1), b = P(k0.x + o[0], k0.y + o[1]), d = P(k1.x + n[0], k1.y + n[1]), e = P(k1.x, k1.y);
        g.bezierCurveTo(b[0], b[1], d[0], d[1], e[0], e[1]);
      });
      g.stroke(); g.setLineDash([]);
      // the handles of the picked key and its neighbours
      ks.forEach((k0, i) => {
        const picked = this.key && this.key.tr === ti && this.key.k === i;
        if (!picked) return;
        for (const [f, ok] of [["in", i > 0], ["out", i < ks.length - 1]]) {
          if (!ok) continue;
          const h = k0[f] || [0, 0], a = P(k0.x, k0.y), b = P(k0.x + h[0], k0.y + h[1]);
          g.strokeStyle = c.ink3; g.lineWidth = 1; g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke();
          g.fillStyle = c.panel; g.strokeStyle = c.accent; g.lineWidth = 2; g.beginPath(); g.arc(b[0], b[1], 5, 0, Math.PI * 2); g.fill(); g.stroke();
        }
      });
      ks.forEach((k0, i) => {
        const a = P(k0.x, k0.y), picked = this.key && this.key.tr === ti && this.key.k === i;
        g.save(); g.translate(a[0], a[1]); g.rotate(Math.PI / 4);
        g.fillStyle = picked ? c.accent : c.panel; g.strokeStyle = picked ? c.accent : c.info; g.lineWidth = 2;
        g.fillRect(-5, -5, 10, 10); g.strokeRect(-5, -5, 10, 10); g.restore();
      });
      // where the thing is at the playhead
      const now = evalTrack(t, this.step), q = P(now[0], now[1]);
      g.fillStyle = c.accent; g.beginPath(); g.arc(q[0], q[1], 3.5, 0, Math.PI * 2); g.fill();
      g.restore();
    }
  }
  /** what of a path is under the pointer: {ti, k, part: "key"|"in"|"out"} */
  hitPath(cx, cy) {
    const ed = this.ed, ph = ed.phase(), P = (x, y) => ed.toView(x, y);
    let best = null, bd = 9;
    for (const ti of this.paths()) {
      const ks = ph.tracks[ti].keys;
      ks.forEach((k0, i) => {
        const cand = [["key", k0.x, k0.y]];
        if (this.key && this.key.tr === ti && this.key.k === i) {
          if (i > 0) cand.push(["in", k0.x + (k0.in || [0, 0])[0], k0.y + (k0.in || [0, 0])[1]]);
          if (i < ks.length - 1) cand.push(["out", k0.x + (k0.out || [0, 0])[0], k0.y + (k0.out || [0, 0])[1]]);
        }
        for (const [part, x, y] of cand) {
          const [a, b] = P(x, y), d = Math.hypot(a - cx, b - cy);
          if (d < bd || (d === bd && part !== "key")) { bd = d; best = { ti, k: i, part }; }
        }
      });
    }
    return best;
  }
  /** a drag on a path's key or handle: live in the engine, one step when let go. Alt: the handles move apart. */
  pathDown(hit, x, y) {
    const ed = this.ed, ph = ed.phase();
    this.key = { tr: hit.ti, k: hit.k }; this.pick = null;
    const t = clone(ph.tracks[hit.ti]);
    this.live = { track: { ti: hit.ti, t }, x0: x, y0: y, orig: clone(t.keys[hit.k]), hit, moved: false };
    ed.notify.panels();
    ed.dirty();
  }
  pathMove(x, y, alt, shift) {
    const L = this.live; if (!L || !L.track) return;
    let dx = x - L.x0, dy = y - L.y0;
    if (shift) { if (Math.abs(dx) > Math.abs(dy)) dy = 0; else dx = 0; }
    const k = L.track.t.keys[L.hit.k], o = L.orig;
    if (L.hit.part === "key") { k.x = r3(o.x + dx); k.y = r3(o.y + dy); }
    else {
      const f = L.hit.part, other = f === "in" ? "out" : "in", h = o[f] || [0, 0];
      k[f] = [r3(h[0] + dx), r3(h[1] + dy)];
      const len = Math.hypot(...(o[other] || [0, 0]));
      if (!alt && L.track.t.keys[L.hit.k + (other === "out" ? 1 : -1)]) {   // smooth: the other handle keeps the line
        const n = Math.hypot(...k[f]) || 1;
        k[other] = [r3(-k[f][0] / n * (len || n)), r3(-k[f][1] / n * (len || n))];
      }
    }
    L.moved = true;
    const gi = engineIndex(this.ed.doc, this.ed.ph, L.hit.ti).key0 + L.hit.k, prev = L.hit.k > 0 ? stepOf(L.track.t.keys[L.hit.k - 1].at_s) : 0;
    L.apply = (e) => { e.keySet(gi, k.x, k.y, (k.out || [0, 0])[0], (k.out || [0, 0])[1], (k.in || [0, 0])[0], (k.in || [0, 0])[1]); e.seekDirty(prev); };
    this.ed.dirty();
  }
  pathUp() {
    const L = this.live; this.live = null;
    if (!L || !L.track || !L.moved) { this.ed.dirty(); return; }
    const k = L.track.t.keys[L.hit.k];
    this.setKey(L.hit.part === "key" ? "Move a keyframe" : "Shape the path", (key) => {
      key.x = k.x; key.y = k.y;
      for (const f of ["in", "out"]) { if (k[f]) key[f] = k[f]; else delete key[f]; }
    }, L.hit.ti, L.hit.k);
  }
  /** a move of picked things on the stage: the ones with a position track get a key at the playhead (made live in the
   * engine if there is none yet), the rest move as before. Returns the places it took over. */
  keyedMoveStart(sel) {
    const ed = this.ed, ph = ed.phase(), took = new Map();
    for (const i of sel) {
      const ti = trackFor(ph, i, "motion");
      if (ti < 0) continue;
      const t = ph.tracks[ti], at = this.step, ks = t.keys;
      let k = ks.findIndex((x) => stepOf(x.at_s) === at);
      const base = evalTrack(t, at);
      const eng = engineIndex(ed.doc, ed.ph, ti);
      took.set(i, { ti, k, base, at, eng, made: k < 0, pos: k < 0 ? ks.filter((x) => stepOf(x.at_s) < at).length : k });
    }
    if (took.size) {
      // the keys a drag makes go into the engine now, last first so the earlier indexes hold
      const made = [...took.values()].filter((m) => m.made).sort((a, b) => b.eng.track - a.eng.track);
      for (const m of made) ed.e.keyInsert(m.eng.track, m.pos, m.at, m.base[0], m.base[1], 3);
      // where each one's key now sits in the engine's key table
      let shift = 0;
      const order = [...took.values()].sort((a, b) => a.eng.track - b.eng.track);
      for (const m of order) { m.gi = m.eng.key0 + shift + m.pos; if (m.made) shift++; }
      this.keyed = took;
    }
    return took;
  }
  keyedMove(dx, dy) {
    if (!this.keyed) return;
    const took = this.keyed;
    let from = Infinity;
    for (const m of took.values()) {
      const ks = this.ed.phase().tracks[m.ti].keys, prevKey = ks.filter((x) => stepOf(x.at_s) < m.at).pop();
      from = Math.min(from, prevKey ? stepOf(prevKey.at_s) : 0);
    }
    this.live = { apply: (e) => {
      for (const m of took.values()) {
        const ks = this.ed.phase().tracks[m.ti].keys, old = m.made ? null : ks[m.k];
        const o = old ? (old.out || [0, 0]) : [0, 0], n = old ? (old.in || [0, 0]) : [0, 0];
        e.keySet(m.gi, m.base[0] + dx, m.base[1] + dy, o[0], o[1], n[0], n[1]);
      }
      e.seekDirty(from);
    } };
  }
  keyedCommit(doc, ph, dx, dy) {
    const took = this.keyed; this.keyed = null; this.live = null;
    if (!took) return new Set();
    for (const [, m] of took) {
      const ks = ph.tracks[m.ti].keys;
      if (m.made) {
        ks.push(keyFrom("motion", m.at, [m.base[0] + dx, m.base[1] + dy], "in_out"));
        ks.sort((a, b) => a.at_s - b.at_s);
      } else { ks[m.k].x = r3(m.base[0] + dx); ks[m.k].y = r3(m.base[1] + dy); }
    }
    return new Set(took.keys());
  }
  /** a nudge of place i: when it has a position track, its key at the playhead moves (made there if there is none).
   * Returns false for a thing without one (its place moves). */
  nudgeKeyed(ph, i, dx, dy) {
    const ti = trackFor(ph, i, "motion");
    if (ti < 0) return false;
    const ks = ph.tracks[ti].keys, at = this.step, k = ks.findIndex((x) => stepOf(x.at_s) === at);
    if (k >= 0) { ks[k].x = r3(ks[k].x + dx); ks[k].y = r3(ks[k].y + dy); return true; }
    const v = evalTrack(ph.tracks[ti], at);
    ks.push(keyFrom("motion", at, [v[0] + dx, v[1] + dy], "in_out"));
    ks.sort((a, b) => a.at_s - b.at_s);
    return true;
  }
  /** Alt + arrows: the playhead to the picked things' last / next key, and that key picked */
  hopKey(dir) {
    const ed = this.ed, ph = ed.phase(), cands = [];
    (ph.tracks || []).forEach((t, ti) => {
      if (ed.sel.length && !ed.sel.includes(t.place)) return;
      t.keys.forEach((k, ki) => cands.push({ at: stepOf(k.at_s), ti, ki }));
    });
    const next = dir > 0 ? cands.filter((c) => c.at > this.step).sort((a, b) => a.at - b.at || a.ti - b.ti)[0]
      : cands.filter((c) => c.at < this.step).sort((a, b) => b.at - a.at || a.ti - b.ti)[0];
    if (!next) return;
    this.stop(); this.key = { tr: next.ti, k: next.ki }; this.pick = null;
    this.seek(next.at); ed.notify.panels();
  }
  keyedCancel() {
    if (this.keyed && [...this.keyed.values()].some((m) => m.made)) this.ed.reloadPack();
    this.keyed = null; this.live = null;
  }
}

// ---- the timeline dock -----------------------------------------------------------------------------------------------
function rowsOf(ed, ph) {
  const rows = [{ kind: "markers" }], doc = ed.doc, tracks = ph.tracks || [];
  const places = new Set(tracks.map((t) => t.place));
  if (ed.sel.length === 1) places.add(ed.sel[0]);
  [...places].sort((a, b) => a - b).forEach((i) => {
    if (!ph.place[i]) return;
    rows.push({ kind: "thing", place: i });
    PROPS.forEach(([prop]) => { const ti = trackFor(ph, i, prop); if (ti >= 0) rows.push({ kind: "track", ti, prop, place: i }); });
    if (ed.sel.includes(i)) rows.push({ kind: "addkeys", place: i });
  });
  const things = [];
  (ph.spawns || []).forEach((s) => { if (!things.includes(s.thing)) things.push(s.thing); });
  const pickedThing = ed.sel.length === 1 && ph.place[ed.sel[0]] ? ph.place[ed.sel[0]].thing : null;
  if (pickedThing && !things.includes(pickedThing)) things.push(pickedThing);
  things.forEach((thing) => rows.push({ kind: "spawns", thing }));
  rows.push({ kind: "sounds" });
  void doc;
  return rows;
}

function EaseIcon({ name, on }) {
  return html`<svg viewBox="0 0 40 30" class="vtl-ease-ic"><path d=${EASE_ICON[name]} fill="none" stroke=${on ? "var(--accent)" : "var(--ink-2)"} stroke-width="2" /></svg>`;
}

export function Timeline({ ed }) {
  const tlc = ed.tlc, ph = ed.phase(), doc = ed.doc;
  const area = useRef(null), head = useRef(null), timeEl = useRef(null), [, setV] = useState(0);
  const [w, setW] = useState(800);
  const [menu, setMenu] = useState(null);           // {kind: "add-sound" | "add-wave", x, y}
  const [rename, setRename] = useState(null);        // marker index being renamed
  const len = tlc.len(), span = tlc.zoom ? tlc.zoom[1] - tlc.zoom[0] : len, t0 = tlc.zoom ? tlc.zoom[0] : 0;
  const pps = Math.max(1, w - 16) / Math.max(1, span);       // px a step
  const X = (step) => 8 + (step - t0) * pps;
  const S = (px) => t0 + (px - 8) / pps;
  useEffect(() => {
    if (!area.current) return undefined;
    const ro = new ResizeObserver(() => setW(area.current ? area.current.clientWidth : 800));
    ro.observe(area.current);
    return () => ro.disconnect();
  }, []);
  // the playhead and the clock move without a re-render of the panel
  useEffect(() => tlc.onPaint(() => {
    if (head.current) head.current.style.transform = `translateX(${X(tlc.step)}px)`;
    if (timeEl.current) timeEl.current.textContent = fmtTime(tlc.step);
  }), [w, t0, span, ph.id]);
  useEffect(() => { tlc.paint(); });

  const rows = rowsOf(ed, ph), markers = markersOf(doc, ph);
  const loopRaw = tlc.loops[ph.id];
  const music = musicOf(doc, ph);
  const sounds = ((doc.assets || {}).sounds || []).filter((s) => s.role !== "music");
  const thingTeam = (id) => ((doc.things || []).find((t) => t.id === id) || {}).team;
  const local = (e) => { const r = area.current.getBoundingClientRect(); return e.clientX - r.left; };
  const rerender = () => setV((v) => v + 1);

  // one drag on the timeline: fn(stepUnderPointer, e) every move, done(e, moved) when let go
  const drag = (e, fn, done) => {
    e.preventDefault(); e.stopPropagation();
    const el = e.currentTarget, x0 = e.clientX;
    let moved = false;
    try { el.setPointerCapture(e.pointerId); } catch (err) { /* not capturable */ }
    const mv = (ev) => { if (!moved && Math.abs(ev.clientX - x0) < 3) return; moved = true; fn(S(local(ev)), ev); };
    const up = (ev) => { el.removeEventListener("pointermove", mv); el.removeEventListener("pointerup", up); done && done(ev, moved); };
    el.addEventListener("pointermove", mv); el.addEventListener("pointerup", up);
  };
  const scrub = (e) => {
    if (e.shiftKey) {             // Shift drag on the ruler: the loop region
      const a = tlc.snapStep(S(local(e)), pps);
      tlc.loops[ph.id] = { a, b: a + 1, on: true };
      drag(e, (s) => { const b = tlc.snapStep(s, pps); tlc.loops[ph.id] = { a: Math.min(a, b), b: Math.max(a, b, Math.min(a, b) + 1), on: true }; rerender(); },
        () => { tlc.save(); rerender(); });
      return;
    }
    tlc.stop();
    tlc.seek(tlc.snapStep(S(local(e)), pps));
    drag(e, (s, ev) => tlc.seek(ev.ctrlKey ? Math.round(s) : tlc.snapStep(s, pps)));
  };
  const keyDown = (e, ti, k) => {
    tlc.key = { tr: ti, k }; tlc.pick = null; ed.notify.panels();
    const t = ph.tracks[ti], key = t.keys[k], at0 = stepOf(key.at_s);
    const lo = k > 0 ? stepOf(t.keys[k - 1].at_s) + 1 : 0, hi = k < t.keys.length - 1 ? stepOf(t.keys[k + 1].at_s) - 1 : 1e9;
    const gi = engineIndex(doc, ed.ph, ti).key0 + k;
    let now = at0;
    drag(e, (s, ev) => {
      now = clamp(ev.ctrlKey ? Math.round(s) : tlc.snapStep(s, pps, [ti, k]), lo, hi);
      tlc.live = { apply: (eng) => { eng.keyAt(gi, now); eng.seekDirty(Math.max(0, Math.min(lo - 1, now))); }, at: { ti, k, now } };
      ed.dirty(); rerender();
    }, (ev, moved) => {
      if (!moved || now === at0) { tlc.live = null; tlc.seek(at0); return; }
      tlc.setKey("Move a keyframe in time", (kk) => { kk.at_s = secOf(now); }, ti, k);
      tlc.live = null;
    });
  };
  const keyAtOf = (ti, k) => (tlc.live && tlc.live.at && tlc.live.at.ti === ti && tlc.live.at.k === k ? tlc.live.at.now : stepOf(ph.tracks[ti].keys[k].at_s));
  const addKeyOnRow = (e, row) => {
    const at = tlc.snapStep(S(local(e)), pps);
    tlc.seek(at);
    ed.setSel([row.place]);
    tlc.addKeys([row.prop]);
  };
  const waveDown = (e, si, part) => {
    tlc.pick = { kind: "wave", i: si }; tlc.key = null; ed.notify.panels();
    const sp = ph.spawns[si], at0 = stepOf(sp.at_s), every = stepOf(sp.every_s || 0), n0 = sp.count || 1;
    let at = at0, n = n0;
    drag(e, (s) => {
      if (part === "end" && every > 0) n = clamp(Math.round((s - at0) / every) + 1, 1, 999);
      else at = Math.max(0, tlc.snapStep(s - (S(local(e)) - at0), pps));
      tlc.live = { wave: { si, at, n } }; rerender();
    }, (ev, moved) => {
      tlc.live = null;
      if (!moved) { rerender(); return; }
      ed.edit(part === "end" ? "Change a spawn wave's size" : "Move a spawn wave", (d, p) => {
        p.spawns[si].at_s = secOf(at);
        if (part === "end") p.spawns[si].count = n;
      });
    });
  };
  const paintWave = (e, thing) => {
    const a = tlc.snapStep(S(local(e)), pps);
    const same = (ph.spawns || []).filter((s) => s.thing === thing && s.every_s);
    const every = stepOf(same.length ? same[same.length - 1].every_s : 1) || SPS;
    let b = a;
    tlc.live = { paint: { thing, a, b, every } }; rerender();
    drag(e, (s) => { b = Math.max(a, tlc.snapStep(s, pps)); tlc.live = { paint: { thing, a, b, every } }; rerender(); }, (ev) => {
      tlc.live = null;
      const count = Math.max(1, Math.floor((b - a) / every) + 1);
      const tmpl = (ph.spawns || []).filter((s) => s.thing === thing).pop();
      ed.edit("Paint a spawn wave", (d, p) => {
        p.spawns = p.spawns || [];
        const sp = Object.assign(tmpl ? clone(tmpl) : { thing }, { at_s: secOf(a), count });
        if (count > 1) sp.every_s = r3(every / SPS); else delete sp.every_s;
        if (!tmpl && ed.sel.length === 1 && p.place[ed.sel[0]]) { sp.x = p.place[ed.sel[0]].x; sp.y = p.place[ed.sel[0]].y; }
        p.spawns.push(sp);
        tlc.pick = { kind: "wave", i: p.spawns.length - 1 };
      });
    });
  };
  const itemDrag = (e, kind, i) => {
    tlc.pick = { kind, i }; tlc.key = null; ed.notify.panels();
    const list = kind === "marker" ? markers : (ph.sound_track || []);
    const at0 = stepOf(list[i].at_s);
    let at = at0;
    const off = S(local(e)) - at0;
    drag(e, (s) => { at = Math.max(0, tlc.snapStep(s - off, pps)); tlc.live = { item: { kind, i, at } }; rerender(); }, (ev, moved) => {
      tlc.live = null;
      if (!moved || at === at0) { tlc.seek(at0); rerender(); return; }
      ed.edit(kind === "marker" ? "Move a marker" : "Move a sound", (d, p) => {
        if (kind === "marker") { const m = clone(markersOf(d, p)); m[i].at_s = secOf(at); setMarkers(d, p, m); }
        else p.sound_track[i].at_s = secOf(at);
      });
    });
  };
  const addMarker = () => {
    const at = tlc.step;
    ed.edit("Add a marker", (d, p) => { const m = clone(markersOf(d, p)); m.push({ at_s: secOf(at), label: "Marker " + (m.length + 1) }); setMarkers(d, p, m); });
  };
  const addSound = (id) => {
    const at = tlc.step;
    ed.edit("Add a sound at " + fmtTime(at), (d, p) => { p.sound_track = p.sound_track || []; p.sound_track.push({ at_s: secOf(at), sound: id }); p.sound_track.sort((a, b) => a.at_s - b.at_s); });
    setMenu(null);
  };
  const addWave = (thing) => {
    const at = tlc.step;
    const tmpl = (ph.spawns || []).filter((s) => s.thing === thing).pop();
    ed.edit("Add a spawn wave", (d, p) => {
      p.spawns = p.spawns || [];
      const sp = Object.assign(tmpl ? clone(tmpl) : { thing, every_s: 1 }, { at_s: secOf(at), count: (tmpl && tmpl.count) || 5 });
      if (!tmpl && ed.sel.length === 1 && p.place[ed.sel[0]]) { sp.x = p.place[ed.sel[0]].x; sp.y = p.place[ed.sel[0]].y; }
      p.spawns.push(sp);
      tlc.pick = { kind: "wave", i: p.spawns.length - 1 };
    });
    setMenu(null);
  };
  const wheel = (e) => {
    if (!(e.ctrlKey || e.metaKey) && !tlc.zoom) return;
    e.preventDefault();
    const at = S(local(e));
    let a = t0, b = t0 + span;
    if (e.ctrlKey || e.metaKey) {
      const k = Math.exp(e.deltaY * 0.002), ns = clamp(span * k, 30, len * 4);
      a = at - (at - a) * ns / span; b = a + ns;
    } else { const d = (e.deltaX || e.deltaY) / pps; a += d; b += d; }
    if (a < 0) { b -= a; a = 0; }
    tlc.zoom = b - a >= len - 1 && a <= 0 ? null : [a, b];
    rerender();
  };

  // the ruler's ticks: whole seconds, a label every 1, 2, 5 or 10 s as room allows
  const secPx = pps * SPS, every = [1, 2, 5, 10, 30].find((n) => n * secPx >= 46) || 60;
  const ticks = [];
  for (let s = Math.ceil(t0 / SPS); s * SPS <= t0 + span; s++) ticks.push(s);
  const L = tlc.live || {};
  const waveOf = (sp, si) => {
    const at = L.wave && L.wave.si === si ? L.wave.at : stepOf(sp.at_s), n = L.wave && L.wave.si === si ? L.wave.n : (sp.count || 1);
    const ev = stepOf(sp.every_s || 0);
    return { at, n, ev, end: at + (n > 1 && ev > 0 ? (n - 1) * ev : 0) };
  };
  const curvePath = (t) => {
    if (t.prop === "motion" || t.prop === "tint") return null;
    const ks = t.keys, lo = Math.min(...ks.map((k) => k.v)), hi = Math.max(...ks.map((k) => k.v));
    if (hi - lo < 1e-9) return null;
    let d = "";
    const n = Math.max(24, Math.min(240, Math.round(w / 4)));
    for (let j = 0; j <= n; j++) {
      const st = t0 + span * j / n, v = evalTrack(t, st);
      d += (j ? " L" : "M") + X(st).toFixed(1) + " " + (ROW - 4 - (v - lo) / (hi - lo) * (ROW - 8)).toFixed(1);
    }
    return d;
  };
  const sel1 = ed.sel.length === 1 ? ed.sel[0] : -1;

  const rowEl = (row, ri) => {
    if (row.kind === "markers") return html`<div class="vtl-row vtl-markers" key="m">
      ${markers.map((m, i) => { const at = L.item && L.item.kind === "marker" && L.item.i === i ? L.item.at : stepOf(m.at_s);
        return html`<span class=${cx("vtl-marker", tlc.pick && tlc.pick.kind === "marker" && tlc.pick.i === i && "on")} style=${{ left: X(at) + "px" }}
          onPointerDown=${(e) => itemDrag(e, "marker", i)} onDblClick=${() => setRename(i)} ...${tip({ head: m.label, lines: [fmtTime(at) + " · drag to move, double-click to rename, Delete removes it"] })}>
          ${rename === i ? html`<input class="vtl-rename" value=${m.label} autofocus onPointerDown=${(e) => e.stopPropagation()}
              onKeyDown=${(e) => { if (e.key === "Enter") e.currentTarget.blur(); if (e.key === "Escape") { setRename(null); } e.stopPropagation(); }}
              onBlur=${(e) => { const v = e.currentTarget.value.trim().slice(0, 40); setRename(null);
                if (v && v !== m.label) ed.edit("Rename a marker", (d, p) => { const mm = clone(markersOf(d, p)); mm[i].label = v; setMarkers(d, p, mm); }); }} />` : m.label}</span>`; })}
    </div>`;
    if (row.kind === "thing") return html`<div class="vtl-row vtl-thing" key=${"t" + row.place}></div>`;
    if (row.kind === "addkeys") return html`<div class="vtl-row vtl-addkeys" key=${"a" + row.place}></div>`;
    if (row.kind === "track") {
      const t = ph.tracks[row.ti], d = curvePath(t);
      return html`<div class=${cx("vtl-row", tlc.key && tlc.key.tr === row.ti && "on")} key=${"k" + row.ti}
          onDblClick=${(e) => { if (e.target === e.currentTarget || e.target.tagName === "svg" || e.target.tagName === "path") addKeyOnRow(e, row); }}
          ...${tip("Double-click to add a " + PROP_LABEL[t.prop].toLowerCase() + " key here")}>
        ${t.keys.map((k, i) => i < t.keys.length - 1 ? html`<span class="vtl-span" style=${{ left: X(keyAtOf(row.ti, i)) + "px", width: Math.max(0, X(keyAtOf(row.ti, i + 1)) - X(keyAtOf(row.ti, i))) + "px" }}></span>` : null)}
        ${d ? html`<svg class="vtl-curve"><path d=${d} /></svg>` : null}
        ${t.keys.map((k, i) => html`<span class=${cx("vtl-kf", tlc.key && tlc.key.tr === row.ti && tlc.key.k === i && "on", t.prop)}
            style=${{ left: X(keyAtOf(row.ti, i)) + "px" }} onPointerDown=${(e) => keyDown(e, row.ti, i)}
            ...${tip({ head: PROP_LABEL[t.prop] + " key · " + fmtTime(keyAtOf(row.ti, i)), lines: [k.curve ? "A curve of its own" : EASE_LABEL[k.ease || "linear"], "Drag to move it in time (Ctrl: by single steps)"] })}></span>`)}
      </div>`;
    }
    if (row.kind === "spawns") {
      const list = (ph.spawns || []).map((sp, si) => [sp, si]).filter(([sp]) => sp.thing === row.thing);
      const P = L.paint && L.paint.thing === row.thing ? L.paint : null;
      return html`<div class="vtl-row vtl-spawns" key=${"s" + row.thing} onPointerDown=${(e) => { if (e.target === e.currentTarget) paintWave(e, row.thing); }}
          ...${tip("Drag across an empty stretch to paint a wave of " + row.thing)}>
        ${list.map(([sp, si]) => { const v = waveOf(sp, si), on = tlc.pick && tlc.pick.kind === "wave" && tlc.pick.i === si;
          return html`<span class=${cx("vtl-wave", on && "on")} style=${{ left: X(v.at) + "px", width: Math.max(8, X(v.end) - X(v.at) + 8) + "px" }}
              onPointerDown=${(e) => waveDown(e, si, "body")}
              ...${tip({ head: row.thing + " · " + v.n + (v.n === 1 ? " spawn" : " spawns"), lines: [fmtTime(v.at) + (v.ev ? " · one every " + (v.ev / SPS) + " s" : ""), "Drag to move; drag its right end to change how many"] })}>
            ${v.ev > 0 ? Array.from({ length: Math.min(v.n, 200) }, (_, j) => html`<i style=${{ left: (j * v.ev * pps) + "px" }}></i>`) : html`<i style=${{ left: "0px" }}></i>`}
            ${v.ev > 0 ? html`<b class="vtl-wave-end" onPointerDown=${(e) => waveDown(e, si, "end")}></b>` : null}
          </span>`; })}
        ${P ? html`<span class="vtl-wave paint" style=${{ left: X(P.a) + "px", width: Math.max(8, X(P.b) - X(P.a) + 8) + "px" }}>
            ${Array.from({ length: Math.floor((P.b - P.a) / P.every) + 1 }, (_, j) => html`<i style=${{ left: (j * P.every * pps) + "px" }}></i>`)}</span>` : null}
      </div>`;
    }
    return html`<div class="vtl-row vtl-sounds" key="snd">
      ${(ph.sound_track || []).map((sn, i) => { const at = L.item && L.item.kind === "sound" && L.item.i === i ? L.item.at : stepOf(sn.at_s);
        return html`<span class=${cx("vtl-snd", tlc.pick && tlc.pick.kind === "sound" && tlc.pick.i === i && "on")} style=${{ left: X(at) + "px" }}
          onPointerDown=${(e) => itemDrag(e, "sound", i)} ...${tip({ head: sn.sound, lines: [fmtTime(at) + " · drag to move, Delete removes it"] })}><${Icon} name="music" />${sn.sound}</span>`; })}
    </div>`;
  };
  const nameEl = (row) => {
    if (row.kind === "markers") return html`<div class="vtl-name grp">Markers</div>`;
    if (row.kind === "thing") {
      const pl = ph.place[row.place];
      return html`<div class=${cx("vtl-name thing", ed.sel.includes(row.place) && "on")} onClick=${() => ed.setSel([row.place])}
        ...${tip("Pick it on the stage")}><span class="team" style=${{ background: ed.teamColour(thingTeam(pl.thing)) }}></span>${pl.thing}<span class="dim">#${row.place + 1}</span></div>`;
    }
    if (row.kind === "track") return html`<div class=${cx("vtl-name sub", tlc.key && tlc.key.tr === row.ti && "on")}>${PROP_LABEL[row.prop]}
      <button type="button" class="btn ghost icon xs vtl-rm" onClick=${() => ed.edit("Remove the " + PROP_LABEL[row.prop].toLowerCase() + " keys", (d, p) => {
        p.tracks.splice(row.ti, 1); if (!p.tracks.length) delete p.tracks; tlc.key = null; })} ...${tip("Remove this track and its keys")}><${Icon} name="x" /></button></div>`;
    if (row.kind === "addkeys") {
      const have = new Set((ph.tracks || []).filter((t) => t.place === row.place).map((t) => t.prop));
      return html`<div class="vtl-name sub add">${PROPS.filter(([p]) => !have.has(p)).map(([p, l]) => html`<button type="button" class="chip sm vtl-addprop"
        onClick=${() => tlc.addKeys([p])} ...${tip("Add a " + l.toLowerCase() + " key at the playhead")}>+ ${l}</button>`)}</div>`;
    }
    if (row.kind === "spawns") {
      const n = (ph.spawns || []).filter((s) => s.thing === row.thing).length;
      return html`<div class="vtl-name"><span class="team" style=${{ background: ed.teamColour(thingTeam(row.thing)) }}></span>${row.thing}<span class="dim">${n ? n + (n === 1 ? " wave" : " waves") : "spawns"}</span></div>`;
    }
    return html`<div class="vtl-name grp">Sounds</div>`;
  };

  const lp = loopRaw && loopRaw.on ? loopRaw : null;
  const empty = !(ph.tracks || []).length && !(ph.spawns || []).length && !(ph.sound_track || []).length && !markers.length && ed.sel.length !== 1;
  return html`<div class="vtl" onWheel=${wheel}>
    <div class="vtl-h">
      <span class="t">Timeline</span>
      <span class="chip sm mono">${(ph.title || ph.id)} · ${ph.length_s > 0 ? ph.length_s + " s" : "until won or lost"}</span>
      <span class="vme-vsep"></span>
      <button type="button" class="btn ghost icon sm" onClick=${() => tlc.home()} ...${tip({ head: "Back to the start", lines: ["Home"] })}><${Icon} name="prev" /></button>
      <button type="button" class="btn ghost icon sm" onClick=${() => tlc.stepBy(-1)} ...${tip({ head: "One step back", lines: [", (comma)"] })}>‹</button>
      <button type="button" class=${cx("btn icon sm", tlc.playing ? "primary" : "ghost")} onClick=${() => tlc.toggle()} ...${tip({ head: tlc.playing ? "Pause" : "Play the phase here", lines: ["Space · plays it with nothing pressed, as the scrub shows it"] })}><${Icon} name=${tlc.playing ? "pause" : "play"} /></button>
      <button type="button" class="btn ghost icon sm" onClick=${() => tlc.stepBy(1)} ...${tip({ head: "One step on", lines: [". (full stop)"] })}>›</button>
      <span class="mono vtl-time" ref=${timeEl}>${fmtTime(tlc.step)}</span><span class="mono dim">/ ${fmtTime(len)}</span>
      ${lp ? html`<span class="chip sm info vtl-loopchip">Loop ${fmtTime(lp.a)} – ${fmtTime(lp.b)}
          <button type="button" class="btn ghost icon xs" onClick=${() => { delete tlc.loops[ph.id]; tlc.save(); rerender(); }} ...${tip("Stop looping (L)")}><${Icon} name="x" /></button></span>`
        : html`<span class="dim vtl-hint">Shift drag the ruler to loop a stretch</span>`}
      <span class="sp"></span>
      <div class="seg sm">
        ${[["off", "Snap off"], ["q", "0.25 s"], ["beat", "Beats"]].map(([k, l]) => html`<button type="button" class=${cx(tlc.snap === k && "on")}
          disabled=${k === "beat" && !(music && music.tempo_bpm)} onClick=${() => { tlc.snap = k; tlc.save(); rerender(); }}
          ...${tip(k === "beat" ? (music && music.tempo_bpm ? "Snap to the beats of " + music.id : "Beats come from the phase's music, once it has a tempo") : k === "off" ? "Keys snap only to markers, other keys and the playhead" : "Snap to quarter seconds")}>${l}</button>`)}
      </div>
      <span class="vme-vsep"></span>
      <button type="button" class="btn ghost xs" onClick=${(e) => setMenu({ kind: "add-wave", x: e.currentTarget.getBoundingClientRect().left })} ...${tip("Add a spawn wave at the playhead")}><${Icon} name="plus" />Spawn wave</button>
      <button type="button" class="btn ghost xs" disabled=${!ed.sel.length} onClick=${() => tlc.addKeys()} ...${tip({ head: "Add a keyframe at the playhead", lines: ["K · for the picked things: each of their tracks, or their position"] })}><${Icon} name="plus" />Keyframe <span class="kbd">K</span></button>
      <button type="button" class="btn ghost xs" onClick=${addMarker} ...${tip("Add a marker at the playhead")}><${Icon} name="flag" />Marker</button>
      <button type="button" class="btn ghost xs" disabled=${!sounds.length} onClick=${(e) => setMenu({ kind: "add-sound", x: e.currentTarget.getBoundingClientRect().left })} ...${tip(sounds.length ? "Play a sound at the playhead" : "The mode has no sounds yet")}><${Icon} name="music" />Sound</button>
    </div>
    <div class="vtl-b">
      <div class="vtl-names">
        <div class="vtl-name ruler"></div>
        ${rows.map((r) => nameEl(r))}
      </div>
      <div class="vtl-area" ref=${area}>
        <div class="vtl-ruler" onPointerDown=${scrub} ...${tip({ head: "Drag to scrub", lines: ["The stage replays the phase to here with nothing pressed", "Shift drag: loop a stretch"] })}>
          ${ticks.map((s) => html`<span class=${cx("vtl-tick", s % every === 0 && "big")} style=${{ left: X(s * SPS) + "px" }}>${s % every === 0 ? s + "s" : ""}</span>`)}
          ${lp ? html`<div class="vtl-loop" style=${{ left: X(lp.a) + "px", width: Math.max(2, X(lp.b) - X(lp.a)) + "px" }}></div>` : null}
          ${len > 0 ? html`<div class="vtl-end" style=${{ left: X(len) + "px" }}></div>` : null}
        </div>
        ${rows.map((r, i) => rowEl(r, i))}
        ${lp ? html`<div class="vtl-loopband" style=${{ left: X(lp.a) + "px", width: Math.max(2, X(lp.b) - X(lp.a)) + "px" }}></div>` : null}
        ${markers.map((m) => html`<div class="vtl-markline" style=${{ left: X(stepOf(m.at_s)) + "px" }}></div>`)}
        <div class="vtl-head" ref=${head} style=${{ transform: `translateX(${X(tlc.step)}px)` }} onPointerDown=${scrub}></div>
        ${empty ? html`<div class="vtl-empty"><${Empty} icon="clock" title="Nothing on the timeline yet"
            action=${html`<div class="row" style="gap:8px;justify-content:center">
              <${Button} size="sm" icon="plus" onClick=${(e) => setMenu({ kind: "add-wave", x: e.currentTarget.getBoundingClientRect().left })}>Add a spawn wave<//>
              <${Button} size="sm" icon="plus" disabled=${!ph.place.length} onClick=${() => { if (!ed.sel.length && ph.place.length) ed.setSel([0]); tlc.addKeys(); }}>Add a keyframe<//></div>`}>
            Pick a thing on the stage and add keyframes to move it, or paint spawn waves.<//></div>` : null}
      </div>
    </div>
    ${menu ? html`<div class="vme-scrim vtl-scrim" onPointerDown=${(e) => { if (e.target === e.currentTarget) setMenu(null); }}>
      <div class="vtl-menu" style=${{ left: Math.max(8, menu.x - 40) + "px" }} role="menu">
        ${menu.kind === "add-sound" ? sounds.map((s) => html`<button type="button" role="menuitem" class="vtl-menu-i" onClick=${() => addSound(s.id)}><${Icon} name="music" />${s.id}<span class="dim">${s.role}</span></button>`)
          : (doc.things || []).filter((t) => t.team !== "player").map((t) => html`<button type="button" role="menuitem" class="vtl-menu-i" onClick=${() => addWave(t.id)}>
              <span class="team" style=${{ background: ed.teamColour(t.team) }}></span>${t.id}<span class="dim">${t.team}</span></button>`)}
      </div></div>` : null}
  </div>`;
}

// ---- the keyframe inspector (the right dock, while a key is picked) ---------------------------------------------------
function CurveEditor({ value, onCommit }) {
  const [c, setC] = useState(value);
  useEffect(() => setC(value), [String(value)]);
  const W = 268, H = 132, pad = 18, bx = (x) => pad + x * (W - 2 * pad), by = (y) => H - pad - y * (H - 2 * pad) * 0.62 - (H - 2 * pad) * 0.19;
  const svg = useRef(null);
  const down = (n) => (e) => {
    e.preventDefault();
    const el = e.currentTarget; el.setPointerCapture(e.pointerId);
    let cur = c.slice();
    const mv = (ev) => {
      const r = svg.current.getBoundingClientRect(), px = (ev.clientX - r.left) * W / r.width, py = (ev.clientY - r.top) * H / r.height;
      const x = clamp((px - pad) / (W - 2 * pad), 0, 1), y = clamp(((H - pad - py) - (H - 2 * pad) * 0.19) / ((H - 2 * pad) * 0.62), -1, 2);
      cur = c.slice(); cur[n * 2] = r3(x); cur[n * 2 + 1] = r3(y); setC(cur);
    };
    const up = () => { el.removeEventListener("pointermove", mv); el.removeEventListener("pointerup", up); onCommit(cur); };
    el.addEventListener("pointermove", mv); el.addEventListener("pointerup", up);
  };
  let d = "";
  for (let i = 0; i <= 48; i++) { const u = i / 48; d += (i ? " L" : "M") + bx(u).toFixed(1) + " " + by(curveAt(c, u)).toFixed(1); }
  return html`<div class="vtl-curved"><svg ref=${svg} viewBox=${"0 0 " + W + " " + H} preserveAspectRatio="none">
      <path d=${`M${bx(0)} ${by(0)}H${bx(1)}M${bx(0)} ${by(1)}H${bx(1)}M${bx(0.5)} ${by(-0.25)}V${by(1.25)}`} stroke="var(--line)" stroke-width="1" fill="none" />
      <line x1=${bx(0)} y1=${by(0)} x2=${bx(c[0])} y2=${by(c[1])} stroke="var(--ink-3)" stroke-width="1" />
      <line x1=${bx(1)} y1=${by(1)} x2=${bx(c[2])} y2=${by(c[3])} stroke="var(--ink-3)" stroke-width="1" />
      <path d=${d} fill="none" stroke="var(--accent)" stroke-width="2.5" />
      <circle cx=${bx(0)} cy=${by(0)} r="4" fill="var(--accent)" /><circle cx=${bx(1)} cy=${by(1)} r="4" fill="var(--accent)" />
      <circle class="vtl-ch" cx=${bx(c[0])} cy=${by(c[1])} r="6" onPointerDown=${down(0)} />
      <circle class="vtl-ch" cx=${bx(c[2])} cy=${by(c[3])} r="6" onPointerDown=${down(1)} />
    </svg>
    <div class="vme-two mono vtl-curvenums"><span>In ${c[0].toFixed(2)}, ${c[1].toFixed(2)}</span><span>Out ${c[2].toFixed(2)}, ${c[3].toFixed(2)}</span></div></div>`;
}

export function KeyInspector({ ed }) {
  const tlc = ed.tlc, ph = ed.phase(), sel = tlc.key;
  const t = sel && ph.tracks && ph.tracks[sel.tr], key = t && t.keys[sel.k];
  if (!key) return null;
  const last = sel.k === t.keys.length - 1, prop = t.prop;
  const pl = ph.place[t.place];
  const live = (patch) => (v) => { const k = clone(key); patch(k, v); tlc.liveKey(sel.tr, sel.k, k); };
  const commit = (label, patch) => (v) => { tlc.endLive(); tlc.setKey(label, (k) => patch(k, v)); };
  const presets = html`<div class="vtl-presets">${EASES.map((n) => html`<button type="button" class=${cx("vtl-preset", !key.curve && (key.ease || "linear") === n && "on")}
      onClick=${() => tlc.setKey("Ease: " + EASE_LABEL[n], (k) => { delete k.curve; if (n === "linear") delete k.ease; else k.ease = n; })}
      ...${tip(EASE_LABEL[n])}><${EaseIcon} name=${n} on=${!key.curve && (key.ease || "linear") === n} /></button>`)}
      <button type="button" class=${cx("vtl-preset txt", key.curve && "on")} onClick=${() => tlc.setKey("Ease: a curve of its own", (k) => { delete k.ease; k.curve = k.curve || [0.25, 0, 0.55, 1.1]; })}
      ...${tip("A curve of its own: drag its two handles")}>Curve</button></div>`;
  const tint = prop === "tint" ? tintOf(key.tint) : null;
  return html`<div class="vtl-kins">
    <${Group} label="Value">
      ${prop === "motion" ? html`<div class="vme-two">
          <${Scrub} label="X" unit="px" value=${key.x} onLive=${live((k, v) => { k.x = v; })} onCommit=${commit("Move a keyframe", (k, v) => { k.x = v; })} />
          <${Scrub} label="Y" unit="px" value=${key.y} onLive=${live((k, v) => { k.y = v; })} onCommit=${commit("Move a keyframe", (k, v) => { k.y = v; })} /></div>`
        : prop === "tint" ? html`<div class="vme-two"><label class="field sm vtl-colour"><input type="color" value=${tintHex(tint).slice(0, 7)}
            onInput=${(e) => live((k) => { k.tint = e.currentTarget.value + tintHex(tint).slice(7); })()}
            onChange=${(e) => commit("Tint a keyframe", (k) => { k.tint = e.currentTarget.value + tintHex(tint).slice(7); })()} /></label>
            <${Scrub} label="A" value=${r3(tint[3] / 255)} step=${0.01} min=${0} max=${1} onLive=${live((k, v) => { const c = tintOf(k.tint); c[3] = v * 255; k.tint = tintHex(c); })}
              onCommit=${commit("Tint a keyframe", (k, v) => { const c = tintOf(k.tint); c[3] = v * 255; k.tint = tintHex(c); })} /></div>`
        : html`<${Scrub} label=${PROP_LABEL[prop]} unit=${prop === "turn" ? "°" : prop === "scale" ? "×" : ""} value=${key.v}
            step=${prop === "turn" ? 1 : 0.01} min=${prop === "turn" ? -3600 : prop === "scale" ? 0.01 : 0} max=${prop === "turn" ? 3600 : prop === "scale" ? 16 : 1}
            onLive=${live((k, v) => { k.v = v; })} onCommit=${commit("Change a keyframe", (k, v) => { k.v = v; })} />`}
      <${Scrub} label="At" unit="s" value=${key.at_s} step=${1 / SPS} min=${0} max=${600}
        onCommit=${(v) => {
          const s = stepOf(v), lo = sel.k > 0 ? stepOf(t.keys[sel.k - 1].at_s) + 1 : 0, hi = last ? 1e9 : stepOf(t.keys[sel.k + 1].at_s) - 1;
          tlc.setKey("Move a keyframe in time", (k) => { k.at_s = secOf(clamp(s, lo, hi)); });
        }} />
    <//>
    ${prop === "motion" && !(sel.k === 0 && last) ? html`<${Group} label="Path handles" extra=${html`<span class="dim">Alt drag on the stage: apart</span>`}>
        ${sel.k > 0 ? html`<div class="vme-two">
          <${Scrub} label="In x" unit="px" value=${(key.in || [0, 0])[0]} onCommit=${commit("Shape the path", (k, v) => { k.in = [v, (k.in || [0, 0])[1]]; })} />
          <${Scrub} label="In y" unit="px" value=${(key.in || [0, 0])[1]} onCommit=${commit("Shape the path", (k, v) => { k.in = [(k.in || [0, 0])[0], v]; })} /></div>` : null}
        ${!last ? html`<div class="vme-two">
          <${Scrub} label="Out x" unit="px" value=${(key.out || [0, 0])[0]} onCommit=${commit("Shape the path", (k, v) => { k.out = [v, (k.out || [0, 0])[1]]; })} />
          <${Scrub} label="Out y" unit="px" value=${(key.out || [0, 0])[1]} onCommit=${commit("Shape the path", (k, v) => { k.out = [(k.out || [0, 0])[0], v]; })} /></div>` : null}
        <div class="vme-two">
          <${Button} size="sm" onClick=${() => tlc.setKey("Smooth the path", (k) => {
              const a = t.keys[sel.k - 1], b = t.keys[sel.k + 1];
              if (a && b) { const dx = (b.x - a.x) / 6, dy = (b.y - a.y) / 6; k.out = [r3(dx), r3(dy)]; k.in = [r3(-dx), r3(-dy)]; }
              else if (b) k.out = [r3((b.x - k.x) / 3), r3((b.y - k.y) / 3)];
              else if (a) k.in = [r3((a.x - k.x) / 3), r3((a.y - k.y) / 3)];
            })} ...${tip("Handles along the line through its neighbours: a smooth curve")}>Smooth<//>
          <${Button} size="sm" onClick=${() => tlc.setKey("Straighten the path", (k) => { delete k.in; delete k.out; })} ...${tip("No handles: straight lines to its neighbours")}>Straight<//>
        </div>
      <//>` : null}
    <${Group} label=${last ? "Easing (the last key holds)" : "Easing into the next key"}>
      ${last ? html`<div class="dim vtl-note">After its last key ${pl ? pl.thing : "the thing"} stays as this key leaves it.</div>` : html`${presets}
        ${key.curve ? html`<${CurveEditor} value=${key.curve} onCommit=${(c) => tlc.setKey("Shape the easing curve", (k) => { k.curve = c; delete k.ease; })} />` : null}`}
    <//>
    <div class="vtl-kfoot">
      <${Button} size="sm" icon="trash" onClick=${() => tlc.removeKey()} ...${tip({ head: "Remove this keyframe", lines: ["Delete"] })}>Remove<//>
      <span class="sp"></span>
      <${Button} kind="ghost" size="sm" onClick=${() => { tlc.key = null; ed.notify.panels(); }} ...${tip("Back to the thing's settings (Esc)")}>Done<//>
    </div>
  </div>`;
}

/** the right dock's title while a key is picked */
export function keyTitle(ed) {
  const tlc = ed.tlc, ph = ed.phase(), sel = tlc.key, t = sel && ph.tracks && ph.tracks[sel.tr], k = t && t.keys[sel.k];
  if (!k) return null;
  return { thing: (ph.place[t.place] || {}).thing, prop: PROP_LABEL[t.prop], at: fmtTime(stepOf(k.at_s)) };
}
/** the picked marker, sound or wave goes (Delete on the timeline); true when there was one */
export function removePicked(ed) {
  const tlc = ed.tlc, p = tlc.pick;
  if (tlc.key) return tlc.removeKey();
  if (!p) return false;
  tlc.pick = null;
  if (p.kind === "marker") ed.edit("Remove a marker", (d, ph) => { const m = clone(markersOf(d, ph)); m.splice(p.i, 1); setMarkers(d, ph, m); });
  else if (p.kind === "sound") ed.edit("Remove a sound", (d, ph) => { ph.sound_track.splice(p.i, 1); if (!ph.sound_track.length) delete ph.sound_track; });
  else if (p.kind === "wave") ed.edit("Remove a spawn wave", (d, ph) => { ph.spawns.splice(p.i, 1); if (!ph.spawns.length) delete ph.spawns; });
  return true;
}
