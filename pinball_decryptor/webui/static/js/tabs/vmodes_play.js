// The video mode player (PAD-1659): "sample it on the computer". The machine's own engine (PAD-1657), built for the
// browser (core/video_mode/engine/vm_engine.wasm, loaded through its vm_engine.js), plays the mode 60 steps a
// second, and this file is its WebGL backend: it draws the engine's draw list the way the plan's section 4 says
// every backend must (list order, premultiplied pictures, normal and add blending, shake, flash), on the 1360x768
// stage fitted crisply to the pane. Nothing here decides anything about the game: what plays is the engine's.
//
// Buttons: Left Shift / Right Shift are the flipper buttons, Space is Action, Enter is Start (a gamepad's shoulder
// buttons, A and Start do the same; the on-screen buttons take the mouse). The play bar: pause, step one frame,
// restart, slow motion, the machine's frame rate (60, or the about 29 a real Spike 2 draws), recording the buttons
// and replaying them (the replay must end on the recorded draw list hash, the same hash the native build gives),
// hit boxes, and what a step and a frame cost against the machine's budgets. Sounds play through Web Audio,
// muted until turned on. Python half: webui/tabs/vmodes.py play_open / play_save / play_recording.

import { html, useEffect, useRef, useState, Button, Seg, Chip, Check, Note, Icon, Spinner, tip, call, cx,
         mediaUrl } from "../core/ui.js";

const IN = { LEFT: 1, RIGHT: 2, ACTION: 4, CLIP_DONE: 8 };
const STEP_MS = 1000 / 60;
const MAX_STEPS_A_FRAME = 4;          // the plan's cadence rule: beyond this the game slows rather than skips
const MACHINE_FPS = 29;               // what a real Spike 2 draws, about (video_mode_spike2_drawing.md)
const NO_FILE_CLIP_STEPS = 120;       // a clip with no file yet stands as a card this long, then ends
const FX = 65536;
const EV = ["", "clip_start", "clip_stop", "phase_start", "phase_won", "phase_lost", "score", "kill", "pickup", "hurt",
            "fire", "hit", "finished", "prompt_good", "prompt_perfect", "prompt_miss"];
// a team's hue on the hit box overlay (plan section 6): player, enemy, enemy shot, player shot, pickup, health, scenery
const TEAM_VAR = ["--info", "--err", "--warn", "--warn", "--ok", "--ok", "--ink-3"];
const TEAM_HEX = { player: "#5b9bd5", enemy: "#d9534f", enemy_shot: "#e0a030", player_shot: "#e0a030",
                   pickup: "#4caf50", health: "#4caf50", scenery: "#888888" };

// ---- the engine module, loaded once ---------------------------------------------------------------------------
let engineLoad = null;
async function newEngine(jsPath, wasmPath) {
  if (!engineLoad) {
    engineLoad = (async () => {
      const mod = await import(mediaUrl(jsPath));
      const r = await fetch(mediaUrl(wasmPath));
      if (!r.ok) throw new Error("the engine file did not load (" + r.status + ")");
      return { mod, bytes: await r.arrayBuffer() };
    })();
    engineLoad.catch(() => { engineLoad = null; });
  }
  const { mod, bytes } = await engineLoad;
  return mod.VideoModeEngine.create(bytes);
}

// ---- the WebGL backend ----------------------------------------------------------------------------------------
const VS = `attribute vec2 a_pos; attribute vec2 a_uv; attribute vec4 a_col;
uniform vec2 u_stage; varying vec2 v_uv; varying vec4 v_col;
void main() { vec2 p = a_pos / u_stage * 2.0 - 1.0; gl_Position = vec4(p.x, -p.y, 0.0, 1.0); v_uv = a_uv; v_col = a_col; }`;
const FS = `precision mediump float; uniform sampler2D u_tex; varying vec2 v_uv; varying vec4 v_col;
void main() { gl_FragColor = texture2D(u_tex, v_uv) * v_col; }`;
const FLOATS = 8;                     // x, y, u, v, r, g, b, a
const MAX_ENTRIES = 3072 + 2;

function rgba(c) {                    // 0xRRGGBBAA, straight alpha -> premultiplied floats
  const a = (c & 255) / 255;
  return [((c >>> 24) & 255) / 255 * a, ((c >>> 16) & 255) / 255 * a, ((c >>> 8) & 255) / 255 * a, a];
}

export class GLStage {
  constructor(canvas, W, H) {
    const opts = { alpha: false, premultipliedAlpha: true, antialias: false, preserveDrawingBuffer: true };
    const gl = canvas.getContext("webgl2", opts) || canvas.getContext("webgl", opts);
    if (!gl) throw new Error("this browser has no WebGL");
    this.gl = gl; this.W = W; this.H = H; this.canvas = canvas;
    const sh = (type, src) => {
      const s = gl.createShader(type);
      gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      return s;
    };
    const p = gl.createProgram();
    gl.attachShader(p, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    gl.useProgram(p);
    this.verts = new Float32Array(MAX_ENTRIES * 6 * FLOATS);
    this.buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
    gl.bufferData(gl.ARRAY_BUFFER, this.verts.byteLength, gl.DYNAMIC_DRAW);
    const at = (name, n, off) => {
      const l = gl.getAttribLocation(p, name);
      gl.enableVertexAttribArray(l);
      gl.vertexAttribPointer(l, n, gl.FLOAT, false, FLOATS * 4, off * 4);
    };
    at("a_pos", 2, 0); at("a_uv", 2, 2); at("a_col", 4, 4);
    gl.uniform2f(gl.getUniformLocation(p, "u_stage"), W, H);
    gl.uniform1i(gl.getUniformLocation(p, "u_tex"), 0);
    gl.enable(gl.BLEND);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);      // atlases are premultiplied (plan rule 3)
    this.tex = new Map();
    this.sheets = new Map();          // atlas -> {fw, fh, cols}: a quad's frame, from its source box
    this.machine = null;              // atlas -> [the machine's atlas per frame] (PAD-1658's pack), when known
    this.white = this.upload(Object.assign(document.createElement("canvas"), { width: 1, height: 1 }), true);
    this.runs = [];
  }

  upload(src, white = false) {
    const gl = this.gl, t = gl.createTexture();
    if (white) { const g = src.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, 1, 1); }
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, src);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);     // bilinear, clamped (plan rule 5)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return { t, w: src.width || src.naturalWidth || 1, h: src.height || src.naturalHeight || 1 };
  }
  setSheet(atlas, fw, fh, cols) { this.sheets.set(atlas, { fw: Math.max(1, fw), fh: Math.max(1, fh), cols: Math.max(1, cols) }); }
  setMachine(map) { this.machine = map || null; }
  setTexture(atlas, src) {
    const old = this.tex.get(atlas);
    if (old) this.gl.deleteTexture(old.t);
    this.tex.set(atlas, this.upload(src));
  }
  resize(w, h) {
    if (this.canvas.width !== w || this.canvas.height !== h) { this.canvas.width = w; this.canvas.height = h; }
    this.gl.viewport(0, 0, w, h);
  }
  dispose() {
    const gl = this.gl;
    for (const v of this.tex.values()) gl.deleteTexture(v.t);
    gl.deleteTexture(this.white.t);
    gl.deleteBuffer(this.buf);
    this.tex.clear();
  }

  // draw one list of canonical words (vm_engine.c list_words): header 8, quad 12, box 6. Returns what it drew.
  draw(w) {
    const gl = this.gl, V = this.verts;
    const n = w[2], shx = w[3] / FX, shy = w[4] / FX, flash = w[5] >>> 0, clear = w[6] >>> 0;
    const runs = this.runs; runs.length = 0;
    let v = 0, i = 8, quads = 0, boxes = 0, cur = null, curBlend = -1, mcalls = 0, mkey = null, mblend = -1;
    const M = this.machine;
    const mrun = (key, blend) => { if (key !== mkey || blend !== mblend) { mcalls++; mkey = key; mblend = blend; } };
    const put = (x, y, u, vv, c) => {
      V[v++] = x; V[v++] = y; V[v++] = u; V[v++] = vv; V[v++] = c[0]; V[v++] = c[1]; V[v++] = c[2]; V[v++] = c[3];
    };
    const run = (tex, blend) => {
      if (tex !== cur || blend !== curBlend) { runs.push({ tex, blend, first: v / FLOATS, count: 0 }); cur = tex; curBlend = blend; }
      runs[runs.length - 1].count += 6;
    };
    const rect = (x0, y0, x1, y1, c, tex, blend) => {
      run(tex, blend);
      put(x0, y0, 0.5, 0.5, c); put(x1, y0, 0.5, 0.5, c); put(x0, y1, 0.5, 0.5, c);
      put(x1, y0, 0.5, 0.5, c); put(x1, y1, 0.5, 0.5, c); put(x0, y1, 0.5, 0.5, c);
    };
    for (let k = 0; k < n && v < V.length - 6 * FLOATS * 2; k++) {
      const t = w[i], tag = t & 255, blend = (t >>> 8) & 255;
      if (tag === 1) {
        const alpha = (t >>> 16) & 255, atlas = w[i + 1] & 0xffff;
        const sx = w[i + 2] & 0xffff, sy = w[i + 2] >>> 16, sw = w[i + 3] & 0xffff, sh = w[i + 3] >>> 16;
        const x = w[i + 4] / FX + shx, y = w[i + 5] / FX + shy, ax = w[i + 6] / FX, ay = w[i + 7] / FX;
        const kx = w[i + 8] / FX, ky = w[i + 9] / FX, turn = w[i + 10] / FX, tint = w[i + 11] >>> 0;
        i += 12;
        const tex = this.tex.get(atlas) || this.white;
        const a = ((tint & 255) / 255) * (alpha / 255);
        const c = [((tint >>> 24) & 255) / 255 * a, ((tint >>> 16) & 255) / 255 * a, ((tint >>> 8) & 255) / 255 * a, a];
        const x0 = -ax * sw * kx, x1 = (1 - ax) * sw * kx, y0 = -ay * sh * ky, y1 = (1 - ay) * sh * ky;
        const u0 = sx / tex.w, u1 = (sx + sw) / tex.w, v0 = sy / tex.h, v1 = (sy + sh) / tex.h;
        let p;
        if (turn) {
          const r = turn * Math.PI / 180, cs = Math.cos(r), sn = Math.sin(r);
          p = (lx, ly) => [x + lx * cs - ly * sn, y + lx * sn + ly * cs];
        } else p = (lx, ly) => [x + lx, y + ly];
        const A = p(x0, y0), B = p(x1, y0), C = p(x0, y1), D = p(x1, y1);
        run(tex, blend);
        if (M) {                       // the draw call the machine makes for it: its frame's atlas there
          const f = M[atlas], fs = this.sheets.get(atlas);
          const fi = fs ? Math.floor(sy / fs.fh) * fs.cols + Math.floor(sx / fs.fw) : 0;
          mrun(f ? "m" + (f[fi] != null ? f[fi] : f[0]) : "a" + atlas, blend);
        }
        put(A[0], A[1], u0, v0, c); put(B[0], B[1], u1, v0, c); put(C[0], C[1], u0, v1, c);
        put(B[0], B[1], u1, v0, c); put(D[0], D[1], u1, v1, c); put(C[0], C[1], u0, v1, c);
        quads++;
      } else if (tag === 2) {
        const x = w[i + 1] / FX + shx, y = w[i + 2] / FX + shy, bw = w[i + 3] / FX, bh = w[i + 4] / FX;
        const col = w[i + 5] >>> 0;
        i += 6;
        rect(x, y, x + bw, y + bh, rgba(col), this.white, blend);
        if (M) mrun("box", blend);
        boxes++;
      } else break;                                  // a word this backend does not know: stop, never guess
    }
    if (flash & 255) rect(0, 0, this.W, this.H, rgba(flash), this.white, 0);       // flash last (rule 6)
    const cc = rgba(clear | 255);
    gl.clearColor(cc[0], cc[1], cc[2], 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, V.subarray(0, v));
    for (const r of runs) {
      gl.bindTexture(gl.TEXTURE_2D, r.tex.t);
      if (r.blend === 1) gl.blendFunc(gl.ONE, gl.ONE); else gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.drawArrays(gl.TRIANGLES, r.first, r.count);
    }
    return { quads, boxes, calls: M ? mcalls : runs.length, appCalls: runs.length, machineCalls: !!M, shx, shy };
  }
}

// ---- pictures and glyphs as the engine names them -------------------------------------------------------------
function loadImage(src) {
  return new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = rej; im.src = src; });
}
// a picture with no file yet: its frames as team-coloured boxes (the compiler's placeholder size), so play goes on
function placeholderSheet(p) {
  const c = document.createElement("canvas");
  c.width = Math.max(1, p.w); c.height = Math.max(1, p.h);
  const g = c.getContext("2d"), col = TEAM_HEX[p.team] || TEAM_HEX.scenery;
  const fh = p.fh || p.h, n = p.frames || 1;
  for (let k = 0; k < n; k++) {
    g.globalAlpha = 0.55; g.fillStyle = col; g.fillRect(1, k * fh + 1, c.width - 2, fh - 2);
    g.globalAlpha = 1; g.strokeStyle = col; g.lineWidth = 2; g.strokeRect(1, k * fh + 1, c.width - 2, fh - 2);
    g.fillStyle = "#fff"; g.font = "600 " + Math.max(9, Math.min(16, fh / 4)) + "px sans-serif";
    g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(p.id, c.width / 2, k * fh + fh / 2, c.width - 4);
  }
  return c;
}
// the compiler's placeholder font (compiler.py placeholder_font): glyph i of ' '..'~' in a 16-wide grid of
// cell_w x size cells, white, so the quad's tint colours it
function glyphSheet(f) {
  const c = document.createElement("canvas");
  c.width = 16 * f.cell_w; c.height = 6 * f.size;
  const g = c.getContext("2d");
  g.fillStyle = "#fff"; g.textAlign = "center"; g.textBaseline = "middle";
  g.font = "700 " + Math.round(f.size * 0.92) + "px 'IBM Plex Mono', ui-monospace, Consolas, monospace";
  for (let i = 1; i < 95; i++) {
    g.fillText(String.fromCharCode(32 + i), (i % 16) * f.cell_w + f.cell_w / 2, Math.floor(i / 16) * f.size + f.size * 0.55, f.cell_w);
  }
  return c;
}

// ---- sound: Web Audio, muted until turned on ----------------------------------------------------------------------
class Sounds {
  constructor(list) { this.list = list || []; this.on = false; this.ctx = null; this.bufs = new Map(); this.music = -1; this.src = null; this.played = 0; this.musicPlayed = 0; }
  buffer(i) {
    const s = this.list[i];
    if (!s || !s.path || !this.ctx) return Promise.resolve(null);
    if (!this.bufs.has(i)) {
      this.bufs.set(i, fetch(mediaUrl(s.path)).then((r) => r.arrayBuffer()).then((b) => this.ctx.decodeAudioData(b))
        .catch(() => null));
    }
    return this.bufs.get(i);
  }
  setOn(on) {
    this.on = on;
    if (on && !this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      this.ctx = new AC();
      this.master = this.ctx.createGain(); this.master.connect(this.ctx.destination);
      this.musicGain = this.ctx.createGain(); this.musicGain.connect(this.master);
    }
    if (!this.ctx) return;
    if (on) { this.ctx.resume(); if (this.music >= 0 && !this.src) this.startMusic(this.music); }
    else { this.stopMusicSource(); this.ctx.suspend(); }
  }
  stopMusicSource() { if (this.src) { try { this.src.stop(); } catch (e) { /* already stopped */ } this.src = null; } }
  async startMusic(i) {
    this.stopMusicSource();
    const s = this.list[i], b = await this.buffer(i);
    if (!b || !this.on || this.music !== i) return;
    const src = this.ctx.createBufferSource();
    src.buffer = b; src.loop = s.loop !== false;
    if (s.loop_start_s) { src.loopStart = s.loop_start_s; src.loopEnd = b.duration; }
    const g = this.ctx.createGain(); g.gain.value = s.volume == null ? 1 : s.volume;
    src.connect(g); g.connect(this.musicGain);
    src.start();
    this.src = src; this.musicPlayed++;
  }
  async cue(c) {
    if (c.op === 1) { this.music = c.sound; if (this.on) this.startMusic(c.sound); return; }
    if (c.op === 2) { this.music = -1; this.stopMusicSource(); return; }
    if (!this.on || !this.ctx) return;
    const b = await this.buffer(c.sound);
    if (!b) return;
    const s = this.list[c.sound] || {};
    const src = this.ctx.createBufferSource(), g = this.ctx.createGain();
    src.buffer = b; g.gain.value = s.volume == null ? 1 : s.volume;
    src.connect(g); g.connect(this.master); src.start(); this.played++;
    if (c.duck) {                                    // duck_music: the music dips under it
      const t = this.ctx.currentTime, mg = this.musicGain.gain;
      mg.cancelScheduledValues(t); mg.setTargetAtTime(0.35, t, 0.03); mg.setTargetAtTime(1, t + b.duration, 0.15);
    }
  }
  reset() { this.music = -1; this.stopMusicSource(); }
  close() { this.reset(); if (this.ctx) this.ctx.close(); this.ctx = null; }
}

// ---- the run: engine, clock, buttons, clips, recording --------------------------------------------------------------
function b64bytes(s) { const b = atob(s); const u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; }
function bytesB64(u) { let s = ""; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); }

class Run {
  constructor(info, eng, stage, overlay, clipEl, onTick) {
    this.info = info; this.e = eng; this.stage = stage; this.overlay = overlay; this.clipEl = clipEl; this.onTick = onTick;
    this.sounds = new Sounds(info.sounds);
    this.keys = 0; this.mouse = 0; this.pad = 0; this.padStart = false; this.padName = "";
    this.paused = false; this.speed = 1; this.fps = 60; this.hits = false;
    this.acc = 0; this.last = 0; this.lastDraw = 0; this.nextDraw = 0; this.raf = 0;
    this.perfReset();
    this.restart(null);
  }
  cardIndex(id) { return this.info.cards.findIndex((c) => c.id === id); }
  // a new play: from the flow's start (card null) or from a card; replay: a recording to feed instead of the buttons
  restart(card, replay = null) {
    const seed = replay ? (replay.seed || this.info.seed) : this.info.seed;
    const c = replay ? (replay.card == null || replay.card < 0 ? null : replay.card) : card;
    if (c == null) this.e.start(seed, 0); else this.e.startAt(seed, 0, c);
    this.seed = seed; this.card = c; this.replay = replay; this.rec = new Uint8Array(1 << 14); this.nrec = 0;
    this.alive = true; this.done = null; this.log = []; this.score = 0; this.kills = 0; this.pickups = 0;
    this.clip = null; this.clipDone = false; this.verdict = null; this.lastList = null; this.lastDrawn = null;
    this.sounds.reset(); this.showClip(null);
    this.step(true);
  }
  input() {
    let v = this.keys | this.mouse | this.pad;
    if (this.clipDone) { v |= IN.CLIP_DONE; this.clipDone = false; }
    return v & 15;
  }
  // one engine step (60 a second). first: the step a play opens with (vm_start's own events come out with it)
  step() {
    if (!this.alive) return false;
    let input;
    if (this.replay) {
      if (this.nrec >= this.replay.data.length) { this.endReplay(); return false; }
      input = this.replay.data[this.nrec];
    } else input = this.input();
    if (this.nrec >= this.rec.length) { const r = new Uint8Array(this.rec.length * 2); r.set(this.rec); this.rec = r; }
    this.rec[this.nrec++] = input;
    const t0 = performance.now();
    const more = this.e.step(input);
    const words = this.e.drawWords();
    this.pf.stepMs += performance.now() - t0; this.pf.steps++;
    this.lastList = words;
    for (const ev of this.e.events()) this.event(ev);
    for (const c of this.e.cues()) this.sounds.cue(c);
    if (this.clip && !this.clip.file && !this.replay && this.e.stepNo() - this.clip.at >= NO_FILE_CLIP_STEPS) this.clipDone = true;
    if (!more) {
      this.alive = false;
      this.done = { outcome: this.e.outcome(), score: this.e.score(), hash: this.e.hash(), steps: this.nrec };
      this.showClip(null);
      if (this.replay) this.endReplay();
    }
    return more;
  }
  endReplay() {
    if (!this.replay || this.verdict) return;
    const r = this.replay, hash = this.e.hash();
    this.alive = false;
    this.verdict = { hash, want: r.hash, steps: this.nrec, wantSteps: r.steps, same: hash === r.hash && this.nrec === r.steps };
  }
  word(kind, i) { const t = this.info[kind] || []; return t[i] != null ? (t[i].id || t[i]) : "#" + i; }
  event(ev) {
    const s = this.e.stepNo(), name = EV[ev.type] || "event " + ev.type;
    let say = name;
    if (ev.type === 1) { say = "clip " + this.word("clips", ev.a) + (ev.b ? " (can be skipped)" : ""); this.showClip(ev.a, !!ev.b); }
    else if (ev.type === 2) { say = "clip " + this.word("clips", ev.a) + (ev.b ? " skipped" : " ended"); this.showClip(null); }
    else if (ev.type === 3) { say = "phase " + this.word("phases", ev.a) + " starts" + (ev.b ? " (try " + (ev.b + 1) + ")" : ""); this.showClip(null); }
    else if (ev.type === 4) say = "phase " + this.word("phases", ev.a) + " won";
    else if (ev.type === 5) say = "phase " + this.word("phases", ev.a) + " lost · " + ev.b + " tries left";
    else if (ev.type === 6) { this.score = ev.b; if (this.log.length && this.log[0].kind === "score" && this.log[0].s === s) return; say = "+" + ev.a.toLocaleString() + " · " + ev.b.toLocaleString(); }
    else if (ev.type === 7) { this.kills++; say = "hit " + this.word("things", ev.a) + (ev.b ? " +" + ev.b : ""); }
    else if (ev.type === 8) { this.pickups++; say = "pickup " + this.word("things", ev.a) + " · " + ev.b; }
    else if (ev.type === 9) say = "hurt · health " + ev.a;
    else if (ev.type === 10) return;                 // fire: too many to list
    else if (ev.type === 11) say = "weak point " + ev.a + " hit · " + ev.b + " left";
    else if (ev.type === 12) say = (ev.a ? "WON" : "LOST") + " · " + ev.b.toLocaleString() + (ev.c ? " · no hit taken" : "");
    this.log.unshift({ s, say, kind: name });
    if (this.log.length > 80) this.log.length = 80;
  }
  showClip(i, skippable = false) {
    const el = this.clipEl;
    if (i == null) {
      this.clip = null;
      if (el) { const v = el.querySelector("video"); if (v) { v.pause(); v.removeAttribute("src"); v.load(); } el.hidden = true; }
      return;
    }
    const c = (this.info.clips || [])[i] || {};
    this.clip = { i, file: !!c.path, at: this.e.stepNo(), skippable, id: c.id || "#" + i };
    if (!el) return;
    el.hidden = false;
    const v = el.querySelector("video"), w = el.querySelector(".vmp-clip-card");
    if (c.path) {
      w.hidden = true; v.hidden = false;
      v.muted = !this.sounds.on; v.src = mediaUrl(c.path);
      v.onended = () => { if (!this.replay && this.clip && this.clip.i === i) this.clipDone = true; };
      v.play().catch(() => {});
    } else {
      v.hidden = true; w.hidden = false;
      w.querySelector("b").textContent = c.id || "clip";
      w.querySelector("span").textContent = c.file ? "No file at " + c.file + " yet: it stands here 2 s, as the clip would play." : "No file for this clip yet.";
    }
  }
  startPressed() {                    // Enter / the pad's Start: begin again when it is over, or end a clip that plays
    if (!this.alive && !this.replay) { this.restart(this.card); return; }
    if (this.clip && !this.replay) this.clipDone = true;
  }
  pollPad() {
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    let v = 0, start = false, name = "";
    for (const p of pads) {
      if (!p || !p.connected) continue;
      name = name || p.id;
      const b = (k) => p.buttons[k] && (p.buttons[k].pressed || p.buttons[k].value > 0.5);
      if (b(4) || b(6)) v |= IN.LEFT;            // LB (or the left trigger)
      if (b(5) || b(7)) v |= IN.RIGHT;           // RB
      if (b(0)) v |= IN.ACTION;                  // A
      if (b(9)) start = true;                    // Start
    }
    if (start && !this.padStart) this.startPressed();
    this.padStart = start; this.pad = v; this.padName = name;
  }
  // the frame: run as many steps as wall time has passed (at most 4), draw the newest list
  frame(now) {
    this.pollPad();
    const dt = this.last ? Math.min(250, now - this.last) : 0;
    this.last = now;
    if (this.fps !== 60) {          // the machine's rate: draw on a running schedule, steps keep wall time between
      const period = 1000 / this.fps;
      if (now < this.nextDraw - 8) { this.acc += this.paused ? 0 : dt * this.speed; return; }
      this.nextDraw = this.nextDraw + period < now - period ? now + period : this.nextDraw + period;
    }
    if (!this.paused && this.alive) {
      this.acc += dt * this.speed;
      let n = Math.floor(this.acc / STEP_MS);
      if (n > MAX_STEPS_A_FRAME) { n = MAX_STEPS_A_FRAME; this.acc = 0; } else this.acc -= n * STEP_MS;
      for (let k = 0; k < n && this.step(); k++);
    } else this.acc = 0;
    this.draw(now);
  }
  draw(now) {
    if (!this.lastList) return;
    const t0 = performance.now();
    const d = this.stage.draw(this.lastList);
    this.drawOverlay(d);
    const ms = performance.now() - t0;
    const pf = this.pf;
    if (this.lastDraw && now) { const gap = now - this.lastDraw; pf.gaps.push(gap); if (pf.gaps.length > 600) pf.gaps.shift(); }
    this.lastDraw = now || performance.now();
    pf.drawMs += ms; pf.draws++; pf.quads = d.quads; pf.calls = d.calls; pf.appCalls = d.appCalls; pf.machineCalls = d.machineCalls; pf.boxes = d.boxes;
    pf.things = this.e.things(); pf.maxThings = Math.max(pf.maxThings, pf.things); pf.maxQuads = Math.max(pf.maxQuads, d.quads);
    this.lastDrawn = d;
  }
  drawOverlay(d) {
    const cv = this.overlay;
    if (!cv) return;
    const g = cv.getContext("2d");
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.clearRect(0, 0, cv.width, cv.height);
    if (!this.hits) return;
    const k = cv.width / this.info.stage[0];
    g.setTransform(k, 0, 0, k, d.shx * k, d.shy * k);
    const cs = getComputedStyle(cv);
    const col = TEAM_VAR.map((v) => cs.getPropertyValue(v).trim() || "#888");
    const h = this.e.hitBoxes();
    g.lineWidth = 1 / k * Math.max(1, window.devicePixelRatio || 1);
    for (let i = 0; i < h.length; i += 6) {
      const c = col[h[i]] || col[6], x = h[i + 2] / FX, y = h[i + 3] / FX, w = h[i + 4] / FX, hh = h[i + 5] / FX;
      g.beginPath();
      if (h[i + 1] === 1) g.arc(x, y, w, 0, Math.PI * 2); else g.rect(x, y, w, hh);
      g.globalAlpha = 0.2; g.fillStyle = c; g.fill();
      g.globalAlpha = 1; g.strokeStyle = c; g.stroke();
    }
  }
  perfReset() { this.pf = { stepMs: 0, steps: 0, drawMs: 0, draws: 0, gaps: [], quads: 0, calls: 0, boxes: 0, things: 0, maxThings: 0, maxQuads: 0, t0: performance.now() }; }
  perf() {
    const pf = this.pf, g = pf.gaps.slice().sort((a, b) => a - b);
    const secs = (performance.now() - pf.t0) / 1000;
    return { seconds: +secs.toFixed(2), frames: pf.draws, fps: +(pf.draws / Math.max(0.001, secs)).toFixed(1),
             steps_per_s: +(pf.steps / Math.max(0.001, secs)).toFixed(1),
             frame_gap_ms_mean: g.length ? +(g.reduce((a, b) => a + b, 0) / g.length).toFixed(2) : 0,
             frame_gap_ms_p95: g.length ? +g[Math.floor(g.length * 0.95)].toFixed(2) : 0,
             frame_gap_ms_max: g.length ? +g[g.length - 1].toFixed(2) : 0,
             step_ms: pf.steps ? +(pf.stepMs / pf.steps).toFixed(4) : 0, draw_ms: pf.draws ? +(pf.drawMs / pf.draws).toFixed(4) : 0,
             things: pf.things, max_things: pf.maxThings, quads: pf.quads, max_quads: pf.maxQuads, draw_calls: pf.calls,
             app_draw_calls: pf.appCalls || 0, draw_calls_as_machine: !!pf.machineCalls };
  }
  recording() {
    return { data: this.rec.slice(0, this.nrec), seed: this.seed, level: 0, card: this.card == null ? -1 : this.card,
             card_id: this.card == null ? this.info.start : (this.info.cards[this.card] || {}).id,
             steps: this.nrec, hash: this.e.hash(), outcome: this.done ? this.done.outcome : -1, score: this.e.score() };
  }
  setSound(on) {
    this.sounds.setOn(on);
    const v = this.clipEl && this.clipEl.querySelector("video");
    if (v) v.muted = !on;
  }
  setPaused(p) {
    this.paused = p;
    const v = this.clipEl && this.clipEl.querySelector("video");
    if (v && !v.hidden && v.getAttribute("src")) { if (p) v.pause(); else v.play().catch(() => {}); }
  }
  close() { cancelAnimationFrame(this.raf); this.sounds.close(); this.showClip(null); }
}

// ---- the page ---------------------------------------------------------------------------------------------------
const KEYS = { ShiftLeft: IN.LEFT, ShiftRight: IN.RIGHT, Space: IN.ACTION };
const fmtTime = (steps) => { const s = Math.max(0, steps) / 60; return String(Math.floor(s / 60)).padStart(2, "0") + ":" + (s % 60).toFixed(2).padStart(5, "0"); };

function Meter({ label, used, budget, fmt = (v) => v.toLocaleString(), title }) {
  const pct = budget ? Math.min(100, (100 * used) / budget) : 0;
  const tone = !budget ? "var(--ink-3)" : pct > 100 * 0.999 ? "var(--err)" : pct > 75 ? "var(--warn)" : "var(--ok)";
  return html`<div class="vmp-bud" ...${tip(title)}><span>${label}</span>
    <span class="bar"><i style=${`width:${pct}%;background:${tone}`}></i></span>
    <b>${fmt(used)}${budget ? " / " + fmt(budget) : ""}</b></div>`;
}

const T = {
  back: "Back to the pictures and backgrounds. The play stops.",
  pause: "Pause, or carry on (P)",
  step: "One engine step, a sixtieth of a second, while paused (.)",
  restart: "Play again from where this play started (Home)",
  speed: "Slow motion: the engine still takes its 60 steps a second of game time, just fewer of them a second of yours.",
  fps: "How often the screen is drawn. The engine always steps 60 times a second; a real Spike 2 draws about 29 frames a second, so the same steps are shown about every other one.",
  rec: "Every play keeps the buttons it was given, step by step. Save keeps this one beside the mode (its replays folder) with the run's draw list hash.",
  replay: "Play the buttons of this play (or the recording picked) again from the same start. It must end on the same draw list hash: the engine is the same code as the machine's, so the native build gives that hash too.",
  hits: "Show what collides: each thing's hit box in its team's colour (H)",
  sound: "Sounds play through this computer's speakers. Off until you turn them on.",
  step_cost: "What one engine step costs on this computer, and drawing a frame. The machine's own step budget is in the plan's budgets.",
};

export function VideoModePlayer({ s, onClose }) {
  const [info, setInfo] = useState(null);
  const [err, setErr] = useState("");
  const [ui, setUi] = useState({});
  const [sound, setSound] = useState(false);
  const [paused, setPaused] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [fps, setFps] = useState(60);
  const [hits, setHits] = useState(false);
  const [saved, setSaved] = useState("");
  const [recs, setRecs] = useState([]);
  const wrap = useRef(null), canvas = useRef(null), over = useRef(null), clipEl = useRef(null), run = useRef(null);

  // open: compile, load the engine and the pictures, start
  useEffect(() => {
    let live = true, stage = null;
    (async () => {
      try {
        const inf = await call("vmodes.play_open");
        if (!live) return;
        if (!inf || (inf.problems || []).length) { setErr((inf && inf.problems || ["It did not compile."]).join("\n")); return; }
        const eng = await newEngine(inf.engine_js, inf.engine_wasm);
        const verdict = eng.load(b64bytes(inf.pack));
        if (verdict) { setErr("The engine refused the compiled mode (" + verdict + " at word " + eng.errAt() + ")."); return; }
        stage = new GLStage(canvas.current, inf.stage[0], inf.stage[1]);
        await Promise.all(inf.pictures.map(async (p, i) => {
          let src;
          try { src = p.path ? await loadImage(mediaUrl(p.path) + "&v=" + (p.v || 0)) : placeholderSheet(p); }
          catch (e) { src = placeholderSheet(Object.assign({}, p, { fh: p.h, frames: 1 })); }
          stage.setTexture(i, src);
          stage.setSheet(i, p.fw || p.w, p.fh || p.h, p.cols || 1);
        }));
        try { await document.fonts.load("700 32px 'IBM Plex Mono'"); } catch (e) { /* the fallback face draws */ }
        inf.fonts.forEach((f) => stage.setTexture(f.atlas, glyphSheet(f)));
        if (!live) { stage.dispose(); return; }
        setInfo(inf); setRecs(inf.recordings || []);
        const r = new Run(inf, eng, stage, over.current, clipEl.current, null);
        run.current = r;
        const loop = (t) => { r.frame(t); r.raf = requestAnimationFrame(loop); };
        r.raf = requestAnimationFrame(loop);
        window.__vmPlayer = {
          ready: true, run: r,
          startAt: (id) => { const i = r.cardIndex(id); r.restart(i < 0 ? null : i); },
          perf: () => r.perf(), perfReset: () => r.perfReset(), recording: () => { const x = r.recording(); return Object.assign(x, { data: bytesB64(x.data) }); },
          replay: (rec) => r.restart(null, Object.assign({}, rec, { data: typeof rec.data === "string" ? b64bytes(rec.data) : rec.data })),
          verdict: () => r.verdict, done: () => r.done, hash: () => eng.hash(),
          sound: () => ({ on: r.sounds.on, state: r.sounds.ctx ? r.sounds.ctx.state : "none", played: r.sounds.played, music: r.sounds.musicPlayed }),
          clip: () => { const v = clipEl.current && clipEl.current.querySelector("video"); return { clip: r.clip, playing: !!(v && !v.hidden && v.currentTime > 0 && !v.paused), t: v ? v.currentTime : 0 }; },
        };
      } catch (e) { if (live) setErr(String(e && e.message || e)); }
    })();
    return () => {
      live = false;
      if (run.current) run.current.close();
      run.current = null;
      if (stage) stage.dispose();
      if (window.__vmPlayer) window.__vmPlayer = null;
    };
  }, [s.slug]);

  // the machine's atlases, once PAD-1658's pack has placed every frame (vmodes.py play_open's thread)
  const atlasMap = s.play_mem && s.play_mem.atlas;
  useEffect(() => { if (run.current) run.current.stage.setMachine(atlasMap || null); }, [atlasMap, info]);

  // the readouts: a few times a second, never per frame
  useEffect(() => {
    const id = setInterval(() => {
      const r = run.current;
      if (!r) return;
      const pf = r.perf();
      setUi({ step: r.e.stepNo(), card: r.e.card(), phase: r.e.phase(), t: r.e.phaseT(), len: r.e.phaseLen(),
              state: r.e.state(), alive: r.alive, done: r.done, verdict: r.verdict, replay: !!r.replay, nrec: r.nrec,
              log: r.log.slice(0, 14), score: r.e.score(), kills: r.kills, pickups: r.pickups, pad: r.padName,
              hash: r.e.hash(), pf, clip: r.clip });
    }, 200);
    return () => clearInterval(id);
  }, []);

  // keys: the flipper buttons, Action and Start while the player is open; the play bar's shortcuts
  useEffect(() => {
    const typing = (e) => /^(INPUT|TEXTAREA|SELECT)$/.test((e.target && e.target.tagName) || "");
    const down = (e) => {
      const r = run.current;
      if (!r || typing(e)) return;
      if (KEYS[e.code]) { r.keys |= KEYS[e.code]; e.preventDefault(); return; }
      if (e.code === "Enter" || e.code === "NumpadEnter") { if (!e.repeat) r.startPressed(); e.preventDefault(); return; }
      if (e.repeat) return;
      if (e.key === "p" || e.key === "P") { setPaused((p) => { r.setPaused(!p); return !p; }); e.preventDefault(); }
      else if (e.key === "." && r.paused) { r.step(); r.draw(performance.now()); e.preventDefault(); }
      else if (e.key === "Home") { r.restart(r.card); e.preventDefault(); }
      else if (e.key === "h" || e.key === "H") { r.hits = !r.hits; setHits(r.hits); e.preventDefault(); }
      else if (e.key === "Escape") { onClose(); e.preventDefault(); }
    };
    const up = (e) => { const r = run.current; if (r && KEYS[e.code]) { r.keys &= ~KEYS[e.code]; e.preventDefault(); } };
    const blur = () => { if (run.current) { run.current.keys = 0; run.current.mouse = 0; } };
    window.addEventListener("keydown", down, true); window.addEventListener("keyup", up, true); window.addEventListener("blur", blur);
    return () => { window.removeEventListener("keydown", down, true); window.removeEventListener("keyup", up, true); window.removeEventListener("blur", blur); };
  }, [onClose]);

  // the stage fitted to the pane, drawn at the screen's own pixels (crisp at any size)
  useEffect(() => {
    if (!info || !wrap.current) return undefined;
    const fit = () => {
      const el = wrap.current, r = run.current;
      if (!el || !r) return;
      const [W, H] = info.stage, bw = el.clientWidth, bh = el.clientHeight;
      const cw = Math.max(64, Math.floor(Math.min(bw, (bh * W) / H))), ch = Math.round((cw * H) / W);
      const dpr = window.devicePixelRatio || 1;
      for (const c of [canvas.current, over.current, clipEl.current]) { c.style.width = cw + "px"; c.style.height = ch + "px"; }
      r.stage.resize(Math.round(cw * dpr), Math.round(ch * dpr));
      over.current.width = Math.round(cw * dpr); over.current.height = Math.round(ch * dpr);
      r.draw(0);
    };
    const ro = new ResizeObserver(fit);
    ro.observe(wrap.current);
    fit();
    return () => ro.disconnect();
  }, [info]);

  const r = run.current;
  const set = {
    paused: (p) => { setPaused(p); if (r) r.setPaused(p); },
    speed: (v) => { setSpeed(v); if (r) r.speed = v; },
    fps: (v) => { setFps(v); if (r) r.fps = v; },
    hits: (v) => { setHits(v); if (r) r.hits = v; },
    sound: (v) => { setSound(v); if (r) r.setSound(v); },
  };
  const save = async () => {
    if (!r || !r.nrec) return;
    const x = r.recording();
    const name = await call("vmodes.play_save", bytesB64(x.data), x);
    if (name) { setSaved(name); setRecs([Object.assign({}, x, { name, data: undefined })].concat(recs.filter((q) => q.name !== name)).slice(0, 20)); }
  };
  const replayThis = () => { if (r && r.nrec) { const x = r.recording(); setSaved(""); r.restart(null, x); } };
  const replaySaved = async (name) => {
    const x = await call("vmodes.play_recording", name);
    if (x && r) r.restart(null, Object.assign({}, x, { data: b64bytes(x.data) }));
  };
  const hold = (bit) => ({
    onPointerDown: (e) => { if (r) r.mouse |= bit; e.currentTarget.setPointerCapture(e.pointerId); },
    onPointerUp: () => { if (r) r.mouse &= ~bit; }, onPointerCancel: () => { if (r) r.mouse &= ~bit; },
  });

  const m = (info && info.machine) || {};
  const pf = ui.pf || {};
  const cards = (info && info.cards) || [];
  const cur = cards[ui.card] || {};
  const top = html`<div class="vmp-top">
    <${Button} kind="ghost" icon="left" title=${T.back} onClick=${onClose}>Back to editing<//>
    <span class="vsep"></span>
    <span class="vmp-name">${(info && info.title) || s.title || s.slug}</span>
    <span class="vmp-crumb">playing in the app · the machine's engine, built for the browser</span>
    <span class="grow"></span>
    <${Chip} sm title="Left Shift, Right Shift, Space and Enter">Keyboard<//>
    ${ui.pad ? html`<${Chip} sm kind="ok" title=${ui.pad}>Gamepad found<//>` : html`<${Chip} sm title="Plug in a gamepad: LB and RB are the flipper buttons, A is Action, Start is Start">No gamepad<//>`}
    <span class="vsep"></span>
    <${Button} kind="ghost" icon=${sound ? "audio" : "ban"} title=${T.sound} onClick=${() => set.sound(!sound)}>${sound ? "Sound on" : "Sound off"}<//>
  </div>`;
  if (err) {
    return html`<div class="vmp">${top}<div class="vmp-err"><${Note} kind="err"><div class="stack" style="gap:4px">
      <b>This video mode can't play yet:</b>${err.split("\n").map((l) => html`<div>${l}</div>`)}</div><//></div></div>`;
  }
  const status = !info ? "Loading…" : ui.verdict ? (ui.verdict.same ? "Replay matched" : "Replay differs")
    : ui.replay ? "Replaying" : ui.done ? (ui.done.outcome === 1 ? "Won" : ui.done.outcome === 0 ? "Lost" : "Over") : paused ? "Paused" : "Playing";
  const memMB = (v) => (v / (1024 * 1024)).toFixed(1);
  return html`<div class="vmp">
    ${top}
    <div class="vmp-main">
      <div class="vmp-col">
        <div class="vmp-stage" ref=${wrap}>
          <canvas ref=${canvas} class="vmp-gl"></canvas>
          <canvas ref=${over} class="vmp-over"></canvas>
          <div ref=${clipEl} class="vmp-clip" hidden>
            <video playsinline muted></video>
            <div class="vmp-clip-card" hidden><${Icon} name="film" /><b></b><span></span></div>
          </div>
          ${!info ? html`<div class="vmp-loading"><${Spinner} /> Building the mode for the browser…</div>` : null}
          ${ui.done && !ui.replay ? html`<div class="vmp-done">
            <div class="vmp-done-t">${ui.done.outcome === 1 ? "Won" : "Lost"} · ${ui.done.score.toLocaleString()}</div>
            <div class="small">Press Enter (or Start) to play again.</div></div>` : null}
        </div>
        <div class="vmp-pads">
          <button type="button" class="vmp-pad" ...${hold(IN.LEFT)} ...${tip("Left flipper button (Left Shift, LB)")}><span class="kbd">L Shift</span>Left flipper</button>
          <button type="button" class="vmp-pad act" ...${hold(IN.ACTION)} ...${tip("Action (Space, A)")}><span class="kbd">Space</span>Action</button>
          <button type="button" class="vmp-pad" ...${hold(IN.RIGHT)} ...${tip("Right flipper button (Right Shift, RB)")}><span class="kbd">R Shift</span>Right flipper</button>
          <button type="button" class="vmp-pad start" onClick=${() => r && r.startPressed()} ...${tip("Start (Enter): play again when it is over, or end a clip")}><span class="kbd">Enter</span>Start</button>
        </div>
      </div>
      <aside class="vmp-dock">
        <div class="vmp-group"><span class="lab">Phases</span>
          <div class="vmp-phases">
            ${cards.filter((c) => c.card !== "end").map((c) => { const i = cards.indexOf(c), on = ui.card === i && ui.alive; return html`<div class=${cx("vmp-ph", on && "on")} key=${c.id}>
              <span class=${cx("chip sm", c.kind !== "clip" && "info")}>${c.kind}</span><span class="ellip">${c.label}</span>
              <span class="st">${on && c.card === "phase" ? html`<span class="mono">${(ui.t / 60).toFixed(1)}${ui.len > 0 ? " / " + (ui.len / 60).toFixed(0) : ""} s</span>`
                : html`<${Button} size="xs" title=${"Play from " + c.label + " (the engine starts at this card)"} onClick=${() => { setSaved(""); r && r.restart(i); }}>Start here<//>`}</span></div>`; })}
          </div>
        </div>
        <div class="vmp-group"><span class="lab">Budgets · ${m.label || ""}</span>
          <div class="vmp-budgets">
            <${Meter} label="Quads" used=${pf.quads || 0} budget=${m.quads} title=${"Quads drawn this frame, against what " + (m.label || "the machine") + " draws a frame"} />
            <${Meter} label="Draws" used=${pf.draw_calls || 0} budget=${m.draw_calls} title=${pf.draw_calls_as_machine
              ? "Draw calls this frame as " + (m.label || "the machine") + " makes them: one per run of the same packed atlas and blend (this computer made " + (pf.app_draw_calls || 0) + ")"
              : "Draw calls this frame on this computer, until the pictures are packed as " + (m.label || "the machine") + " packs them"} />
            <${Meter} label="Things" used=${pf.things || 0} budget=${m.things} title=${"Things alive now, against what " + (m.label || "the machine") + " keeps alive"} />
            <${Meter} label="Pictures" used=${s.play_mem ? s.play_mem.used : 0} budget=${m.memory} fmt=${(v) => memMB(v) + " MB"} title=${s.play_mem ? "The pictures packed as " + (m.label || "the machine") + " holds them in memory" : "Working out what the pictures cost…"} />
          </div>
        </div>
        <div class="vmp-group"><span class="lab">What happened</span>
          <div class="vmp-log">${(ui.log || []).map((l, i) => html`<div key=${i}><span class="s">${l.s}</span>${l.say}</div>`)}
            ${!(ui.log || []).length ? html`<div class="muted">Nothing yet.</div>` : null}</div>
        </div>
        <div class="vmp-group"><span class="lab">Pays so far</span>
          <div class="vmp-kv"><span>Score</span><b class="mono">${(ui.score || 0).toLocaleString()}</b>
            <span>Hits</span><b class="mono">${ui.kills || 0}</b><span>Pickups</span><b class="mono">${ui.pickups || 0}</b>
            <span>Now</span><b>${status}${cur.label && ui.alive ? " · " + cur.label : ""}</b></div>
        </div>
        <div class="vmp-group"><span class="lab">Recordings</span>
          ${ui.verdict ? html`<div class=${cx("vmp-verdict", ui.verdict.same ? "ok" : "bad")}>
            <${Icon} name=${ui.verdict.same ? "check" : "warn"} />
            <span>${ui.verdict.same ? "Same draw list hash after " + ui.verdict.steps + " steps" : "Different: " + ui.verdict.steps + " steps, hash " + ui.verdict.hash + ", recorded " + ui.verdict.wantSteps + " steps, " + ui.verdict.want}</span></div>` : null}
          <div class="vmp-kv" ...${tip("The run's draw list hash: every step's draw list, events and sounds so far. A replay of the same buttons ends on the same one, here and on the machine.")}>
            <span>Hash</span><b class="mono vmp-hash">${ui.hash || ""}</b></div>
          ${saved ? html`<div class="small muted">Kept as replays/${saved}.inputs</div>` : null}
          <div class="vmp-recs">${recs.length ? recs.slice(0, 6).map((x) => html`<button type="button" class="li" key=${x.name} onClick=${() => replaySaved(x.name)}
              ...${tip("Replay it: " + x.steps + " steps from " + (x.card_id || "the start") + ", hash " + x.hash)}>
              <${Icon} name="play" /><span class="ellip">${x.name}</span><span class="r mono small">${fmtTime(x.steps)}</span></button>`)
            : html`<div class="small muted">None kept yet.</div>`}</div>
        </div>
        ${(info && info.notes || []).length ? html`<div class="vmp-group"><span class="lab">Plays differently for now</span>
          <div class="small muted vmp-notes">${info.notes.slice(0, 6).map((n) => html`<div>${n}</div>`)}</div></div>` : null}
      </aside>
    </div>
    <div class="vmp-bar">
      <${Button} kind="ghost" icon=${paused ? "play" : "pause"} title=${T.pause} onClick=${() => set.paused(!paused)} />
      <${Button} kind="ghost" icon="next" title=${T.step} disabled=${!paused} onClick=${() => { if (r) { r.step(); r.draw(performance.now()); } }} />
      <${Button} kind="ghost" icon="prev" title=${T.restart} onClick=${() => { setSaved(""); r && r.restart(r.card); }} />
      <span class="vmp-time mono">${fmtTime(ui.step || 0)}</span>
      <span class="vsep"></span>
      <span ...${tip(T.speed)}><${Seg} value=${speed} onChange=${set.speed} options=${[{ value: 0.25, label: "¼×" }, { value: 0.5, label: "½×" }, { value: 1, label: "1×" }]} /></span>
      <span ...${tip(T.fps)}><${Seg} value=${fps} onChange=${set.fps} options=${[{ value: 60, label: "60 fps" }, { value: MACHINE_FPS, label: "Machine · " + MACHINE_FPS + " fps" }]} /></span>
      <span class="vsep"></span>
      ${ui.verdict ? html`<span class=${cx("vmp-rec", ui.verdict.same ? "ok" : "bad")} ...${tip(ui.verdict.same ? "The replay ended on the recorded draw list hash, " + ui.verdict.hash : "Recorded " + ui.verdict.wantSteps + " steps, hash " + ui.verdict.want + "; the replay " + ui.verdict.steps + " steps, hash " + ui.verdict.hash)}>
          <${Icon} name=${ui.verdict.same ? "check" : "warn"} />${ui.verdict.same ? "Replay matched" : "Replay differs"} · <span class="mono">${ui.verdict.steps}</span> steps</span>`
        : html`<span class="vmp-rec" ...${tip(T.rec)}><span class=${cx("dot", !ui.replay && ui.alive && "on")}></span>${ui.replay ? "Replaying" : "Recording"} · <span class="mono">${ui.nrec || 0}</span> steps</span>`}
      <${Button} kind="ghost" icon="save" title=${T.rec} disabled=${!ui.nrec || ui.replay} onClick=${save}>Save<//>
      <${Button} kind="ghost" icon="refresh" title=${T.replay} disabled=${!ui.nrec || ui.replay} onClick=${replayThis}>Replay<//>
      <${Check} checked=${hits} onChange=${set.hits} title=${T.hits} label=${html`Hit boxes <span class="kbd">H</span>`} />
      <span class="grow"></span>
      <span class="vmp-meter" ...${tip(T.step_cost)}>Step <b>${(pf.step_ms || 0).toFixed(3)}</b> Draw <b>${(pf.draw_ms || 0).toFixed(2)} ms</b></span>
      <span class="vmp-meter" ...${tip("Frames drawn a second on this screen")}><b>${Math.round(pf.fps || 0)}</b> fps</span>
    </div>
  </div>`;
}
