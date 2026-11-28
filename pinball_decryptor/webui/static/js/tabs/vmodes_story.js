// The video mode storyboard (PAD-1664): the flow of the whole mode as a board of cards (clips, phases and ends)
// wired won / lost / then, held to the plan's design language (docs/plans/video_mode_maker.md, section 6; the
// mock-up is docs/plans/video_mode_maker/phases.html).
//
// It cannot be wired wrong: every wire the page offers is checked first by the same rules the document's checker
// applies to a flow (core/video_mode/document.py, reference_problems: every card reachable from the start, an end
// reachable from every card, an end for a win, no clip leading to itself), so a target that would break them is
// dimmed and says why, and a drop on it does nothing. Every change is one ed.commit (checked again and saved by
// Python as one undo step). Add a phase asks Python for a playable phase of the kind picked (vmodes.phase_template)
// and wires it in, all as one change.

import { html, useEffect, useLayoutEffect, useMemo, useRef, useState, Button, Select, Icon, Empty, tip, call, cx,
         openMenu } from "../core/ui.js";

const CSS = "/static/css/tabs/vmodes_story.css";
if (typeof document !== "undefined" && !document.querySelector(`link[href="${CSS}"]`)) {
  const l = document.createElement("link");
  l.rel = "stylesheet";
  l.href = CSS;
  document.head.appendChild(l);
}

const CW = 208, CH = 132, EW = 112, EH = 40, GX = 72, GY = 56, PAD = 48;
const clone = (o) => JSON.parse(JSON.stringify(o));
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const typing = (el) => !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);

// the kinds as the mock-up groups them; the icon paths are the mock-up's own
export const KIND_ICON = {
  chase: '<path d="M3 17h18M6 17l2-5h8l2 5M12 12V4"/>',
  thrust: '<path d="M4 18c4-1 6-6 8-10s4-5 8-5M8 20l-2 2M12 10l3 3"/>',
  aim: '<circle cx="12" cy="12" r="7"/><path d="M12 2v5M12 17v5M2 12h5M17 12h5"/>',
  boss: '<path d="M3 15h18l-2 4H5zM6 15l2-6h8l2 6"/><circle cx="12" cy="12" r="1.5"/>',
  defend: '<path d="M12 4v16M4 12h4M16 12h4M6 9l-3 3 3 3M18 9l3 3-3 3"/>',
  catch: '<path d="M5 14h14l-2 5H7zM12 3v6M9 6l3 3 3-3"/>',
  runner: '<circle cx="14" cy="4.5" r="2"/><path d="M8 21l3-6 3 2v4M11 15l1-6 4 3 3-1M7 10l4-1"/>',
  lander: '<path d="M8 13h8l-1-5H9zM9 13l-3 5M15 13l3 5M3 20h6M15 20h6M12 13v3"/>',
  route: '<path d="M12 21v-7M12 14l-6-6M12 14l6-6M6 8V3M18 8V3"/>',
  mash: '<circle cx="12" cy="12" r="5"/><path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3"/>',
  alternate: '<path d="M4 12l5-5v10zM20 12l-5-5v10z"/>',
  tug: '<path d="M2 12h20M7 8l-4 4 4 4M17 8l4 4-4 4"/><path d="M12 9v6"/>',
  rhythm: '<path d="M9 18V5l10-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/>',
  sequence: '<rect x="2" y="9" width="5" height="6" rx="1"/><rect x="9.5" y="9" width="5" height="6" rx="1"/><rect x="17" y="9" width="5" height="6" rx="1"/>',
  timing: '<rect x="2" y="9" width="20" height="6" rx="2"/><path d="M14 7v10M11 9v6"/>',
  dodge: '<path d="M4 12h12M12 6l6 6-6 6"/><path d="M4 6v12"/>',
  shield: '<path d="M12 3l8 3v6c0 5-4 8-8 9-4-1-8-4-8-9V6z"/>',
  pick: '<rect x="3" y="5" width="5" height="14" rx="1"/><rect x="9.5" y="5" width="5" height="14" rx="1"/><rect x="16" y="5" width="5" height="14" rx="1"/><path d="M12 10v2"/>',
  custom: '<path d="M4 6h16M4 12h10M4 18h7M17 15l3 3-3 3"/>',
  clip: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9l5 3-5 3z"/>',
};
export const KIND_GROUPS = [
  ["Move and shoot", [
    ["chase", "Chase", "Steer lanes, fire, dodge, grab pickups", ["◄", "●", "►"]],
    ["thrust", "Thrust flight", "Hold to rise, fly the gaps, fire", ["●", "►"]],
    ["aim", "Aim and fire", "Sweep or steer a sight; ammo or heat", ["◄", "●", "►"]],
    ["boss", "Boss", "Hit weak points as they open", ["●"]],
    ["defend", "Defend", "Each flipper strikes its own side", ["◄", "►"]],
    ["catch", "Catch", "Move to catch what falls", ["◄", "►"]],
    ["runner", "Runner", "Short jump, long jump with both", ["◄", "►"]],
    ["lander", "Lander", "Side thrusters; land on a pad", ["◄", "●", "►"]],
    ["route", "Route", "Pick the way at each fork", ["◄", "►"]],
  ]],
  ["Button skill", [
    ["mash", "Mash", "Fill a meter, or race a rival", ["●"]],
    ["alternate", "Alternate", "Left, right, left, right", ["◄", "►"]],
    ["tug", "Tug of war", "Hold one flipper, mash Action", ["◄", "●", "►"]],
    ["rhythm", "Rhythm", "Hit prompts on the beat", ["◄", "●", "►"]],
    ["sequence", "Button sequence", "Enter a run, shown or remembered", ["◄", "●", "►"]],
    ["timing", "Timing", "Press or release in the window", ["●"]],
    ["dodge", "Quick dodge", "Press the way the tell shows", ["◄", "►"]],
    ["shield", "Hold shield", "Hold until the danger passes", ["●"]],
  ]],
  ["Choice and freedom", [
    ["pick", "Pick", "Doors, cards, double or nothing", ["◄", "●", "►"]],
    ["custom", "Empty phase", "Things and rule cards only", []],
  ]],
];
const KIND_NAME = Object.fromEntries(KIND_GROUPS.flatMap(([, ks]) => ks.map((k) => [k[0], k[1]])));
const kicon = (k, cls = "") => html`<span class=${cx("vms-kicon", cls)}><svg viewBox="0 0 24 24" dangerouslySetInnerHTML=${{ __html: KIND_ICON[k] || KIND_ICON.custom }}></svg></span>`;

const WHEN_WORDS = {
  time_up: (c) => "time up", survive_s: (c) => "survive " + c.value + " s", score: (c) => c.value + " points",
  kills: (c) => c.value + " down", pickups: (c) => c.value + " picked up", goal: (c) => "meter full",
  health_gone: () => "no health", misses: (c) => c.value + " missed", boss_down: () => "boss down",
  hits: (c) => c.value + " hits", accuracy: (c) => c.value + "% hit", ammo_out: () => "out of ammo",
  landed: () => "landed", crashed: () => "crashed", cashed_out: () => "cashed out", busted: () => "busted",
};
const whenText = (c) => (WHEN_WORDS[c.when] || (() => c.when))(c);
const PORT_OF = { clip: ["then"], phase: ["won", "lost"], end: [] };
const PORT_WORD = { then: "then", won: "won", lost: "lost" };

// ---- the flow's rules: document.py reference_problems' flow part, in the page ----------------------------------
export function cardName(doc, c) {
  if (!c) return "a card";
  if (c.card === "end") return (c.outcome === "won" ? "the Won end" : "the Lost end");
  if (c.card === "clip") return "the clip " + (c.clip || c.id);
  const ph = (doc.phases || []).find((p) => p.id === c.phase);
  return "the phase " + ((ph && (ph.title || ph.id)) || c.phase || c.id);
}
// a card's own name, for labels and lists: the phase's title, the clip's id, Won / Lost
export function cardLabel(doc, c) {
  if (!c) return "";
  if (c.card === "end") return c.outcome === "won" ? "Won end" : "Lost end";
  if (c.card === "clip") return "Clip " + (c.clip || c.id);
  const ph = (doc.phases || []).find((p) => p.id === c.phase);
  return (ph && (ph.title || ph.id)) || c.phase || c.id;
}
export function flowProblems(doc, flow = doc.flow) {
  const out = [], cards = ((flow && flow.cards) || []).filter((c) => c && typeof c === "object");
  const byId = new Map(cards.map((c) => [c.id, c]));
  if (!byId.has(flow.start)) return ["the start card is not there"];
  for (const c of cards) {
    for (const k of ["then", "won", "lost"]) {
      if (c[k] == null) continue;
      if (!byId.has(c[k])) out.push(cardName(doc, c) + " leads to a card that is not there");
      if (c[k] === c.id && c.card === "clip") out.push(cardName(doc, c) + " would lead to itself, and a clip cannot");
    }
  }
  if (out.length) return out;
  const nexts = new Map(cards.map((c) => [c.id, ["then", "won", "lost"].map((k) => c[k]).filter((x) => byId.has(x))]));
  const seen = new Set(), todo = [flow.start];
  while (todo.length) { const c = todo.pop(); if (!seen.has(c)) { seen.add(c); todo.push(...(nexts.get(c) || [])); } }
  for (const c of cards) if (!seen.has(c.id)) out.push(cardName(doc, c) + " could not be reached from the start");
  const ends = cards.filter((c) => c.card === "end").map((c) => c.id);
  if (!ends.length) out.push("there is no end card, so the mode could never finish");
  else {
    const good = new Set(ends);
    for (let changed = true; changed;) {
      changed = false;
      for (const [c, nx] of nexts) if (!good.has(c) && nx.some((x) => good.has(x))) { good.add(c); changed = true; }
    }
    for (const c of cards) if (seen.has(c.id) && !good.has(c.id)) out.push(cardName(doc, c) + " would loop for ever: nothing after it reaches an end");
  }
  if (!cards.some((c) => c.card === "end" && c.outcome === "won")) out.push("there would be no end for a win");
  return out;
}
// the flow with one wire moved, and why it would not do ("" = it would)
function wireWhy(doc, from, port, to) {
  const f = (doc.flow.cards || []).find((c) => c.id === from);
  if (!f || !PORT_OF[f.card].includes(port)) return "that card has no " + port + " way out";
  if (from === to && f.card === "clip") return "a clip cannot lead to itself";
  if (f[port] === to) return "it already leads there";
  const flow = clone(doc.flow);
  flow.cards.find((c) => c.id === from)[port] = to;
  const p = flowProblems(doc, flow);
  return p.length ? p[0] : "";
}
function uniqueCardId(doc, base) {
  const taken = new Set((doc.flow.cards || []).map((c) => c.id));
  base = ("c_" + String(base).replace(/[^a-z0-9_]/g, "_")).slice(0, 36);
  let id = base, n = 1;
  while (taken.has(id)) id = base + "_" + (++n);
  return id;
}

// ---- the layout: columns by the longest way from the start, ends on a row of their own ------------------------
export function layoutFlow(doc) {
  const cards = ((doc.flow || {}).cards || []).filter((c) => c && c.id);
  const byId = new Map(cards.map((c) => [c.id, c]));
  const order = new Map(cards.map((c, i) => [c.id, i]));
  const col = new Map();
  const succ = (c) => PORT_OF[c.card] ? PORT_OF[c.card].map((k) => c[k]).filter((x) => byId.has(x)) : [];
  // longest path over the graph with the edges that close a loop left out (a depth-first walk's back edges)
  const state = new Map(), topo = [];
  const visit = (id) => {
    state.set(id, 1);
    for (const n of succ(byId.get(id))) if (!state.has(n)) visit(n);
    state.set(id, 2); topo.push(id);
  };
  if (byId.has(doc.flow.start)) visit(doc.flow.start);
  for (const c of cards) if (!state.has(c.id)) visit(c.id);
  topo.reverse();
  const pos = new Map(topo.map((id, i) => [id, i]));
  for (const id of topo) if (!col.has(id)) col.set(id, 0);
  for (const id of topo) {
    for (const n of succ(byId.get(id))) {
      if (pos.get(n) > pos.get(id) && byId.get(n).card !== "end") col.set(n, Math.max(col.get(n) || 0, col.get(id) + 1));
    }
  }
  const boxes = new Map(), rows = new Map();
  let maxRow = 0, maxCol = 0;
  const main = topo.filter((id) => byId.get(id).card !== "end").sort((a, b) => col.get(a) - col.get(b) || order.get(a) - order.get(b));
  for (const id of main) {
    const c = col.get(id), r = rows.get(c) || 0;
    rows.set(c, r + 1);
    maxRow = Math.max(maxRow, r); maxCol = Math.max(maxCol, c);
    boxes.set(id, { id, x: PAD + c * (CW + GX), y: PAD + r * (CH + GY), w: CW, h: CH, col: c, row: r });
  }
  // the ends: under what leads to them, on a row below everything
  const endY = PAD + (maxRow + 1) * (CH + GY) + 8;
  const used = [];
  for (const id of topo.filter((i) => byId.get(i).card === "end").sort((a, b) => order.get(a) - order.get(b))) {
    const from = cards.filter((c) => succ(c).includes(id) && boxes.has(c.id)).map((c) => boxes.get(c.id));
    let cx = from.length ? from.reduce((s, b) => s + b.x + b.w / 2, 0) / from.length : PAD + EW / 2;
    while (used.some((u) => Math.abs(u - cx) < EW + 24)) cx += EW + 24;
    used.push(cx);
    boxes.set(id, { id, x: cx - EW / 2, y: endY, w: EW, h: EH, end: true });
  }
  let W = 0, H = 0;
  for (const b of boxes.values()) { W = Math.max(W, b.x + b.w); H = Math.max(H, b.y + b.h); }
  return { boxes, W: W + PAD, H: H + PAD + 24, maxCol };
}

// a wire's path: out of the port's side, into the side of the target that faces it
function wirePath(a, port, b) {
  let x1, y1, d1;
  if (port === "lost") { x1 = a.x + a.w * 0.72; y1 = a.y + a.h; d1 = [0, 1]; }
  else if (port === "then" && b.y > a.y + a.h && b.x + b.w / 2 < a.x + a.w) { x1 = a.x + a.w / 2; y1 = a.y + a.h; d1 = [0, 1]; }
  else { x1 = a.x + a.w; y1 = a.y + a.h * (port === "won" ? 0.42 : 0.5); d1 = [1, 0]; }
  let x2, y2, d2;
  if (b.y >= a.y + a.h - 1 && !(b.x > a.x + a.w + 8 && Math.abs(b.y - a.y) < 4)) { x2 = b.x + b.w / 2; y2 = b.y; d2 = [0, -1]; }
  else if (b.x > a.x + a.w) { x2 = b.x; y2 = b.y + Math.min(b.h / 2, 50); d2 = [-1, 0]; }
  else { x2 = b.x + b.w / 2; y2 = b.y; d2 = [0, -1]; }
  if (b === a) {                       // a phase that loses to itself
    return { d: `M${x1} ${y1} C ${x1} ${y1 + 50}, ${a.x - 40} ${a.y + a.h + 40}, ${a.x - 20} ${a.y + a.h / 2}`, mx: a.x - 30, my: a.y + a.h + 24 };
  }
  const k = Math.max(40, Math.min(140, Math.hypot(x2 - x1, y2 - y1) / 2.4));
  const c1 = [x1 + d1[0] * k, y1 + d1[1] * k], c2 = [x2 + d2[0] * k, y2 + d2[1] * k];
  const t = 0.5, m = 1 - t;
  const mx = m * m * m * x1 + 3 * m * m * t * c1[0] + 3 * m * t * t * c2[0] + t * t * t * x2;
  const my = m * m * m * y1 + 3 * m * m * t * c1[1] + 3 * m * t * t * c2[1] + t * t * t * y2;
  return { d: `M${x1} ${y1} C ${c1[0]} ${c1[1]}, ${c2[0]} ${c2[1]}, ${x2} ${y2}`, mx, my, x1, y1 };
}
const portPoint = (b, port) => (port === "lost" ? [b.x + b.w * 0.72, b.y + b.h] : [b.x + b.w, b.y + b.h * (port === "won" ? 0.42 : 0.5)]);

// ---- small fields ------------------------------------------------------------------------------------------------
function TextIn({ value, onCommit, placeholder, max = 60, label }) {
  const [t, setT] = useState(null);
  const done = () => { if (t != null && t !== (value || "")) onCommit(t.slice(0, max)); setT(null); };
  return html`<div class="field sm vms-field"><input value=${t == null ? value || "" : t} placeholder=${placeholder} aria-label=${label}
    onInput=${(e) => setT(e.target.value)} onBlur=${done}
    onKeyDown=${(e) => { if (e.key === "Enter") { e.preventDefault(); done(); e.target.blur(); } if (e.key === "Escape") { setT(null); e.target.blur(); } e.stopPropagation(); }} /></div>`;
}
function Stepper({ value, min, max, onCommit, label }) {
  return html`<div class="vms-stepper" role="group" aria-label=${label}>
    <button type="button" class="btn ghost icon xs" disabled=${value <= min} onClick=${() => onCommit(value - 1)} ...${tip("One fewer")}><${Icon} name="minus" /></button>
    <span class="mono">${value}</span>
    <button type="button" class="btn ghost icon xs" disabled=${value >= max} onClick=${() => onCommit(value + 1)} ...${tip("One more")}><${Icon} name="plus" /></button>
  </div>`;
}

// ---- the kind picker: Add a phase ---------------------------------------------------------------------------------
function KindSheet({ where, onPick, onClose }) {
  const [q, setQ] = useState("");
  const [at, setAt] = useState(0);
  const inp = useRef(null);
  useEffect(() => { if (inp.current) inp.current.focus(); }, []);
  const words = q.trim().toLowerCase();
  const groups = KIND_GROUPS.map(([g, ks]) => [g, ks.filter((k) => !words || (k[0] + " " + k[1] + " " + k[2]).toLowerCase().includes(words))])
    .filter(([, ks]) => ks.length);
  const flat = groups.flatMap(([, ks]) => ks);
  const cur = flat[clamp(at, 0, Math.max(0, flat.length - 1))];
  const key = (e) => {
    e.stopPropagation();
    if (e.key === "Escape") { e.preventDefault(); onClose(); }
    else if (e.key === "ArrowDown" || e.key === "ArrowRight") { e.preventDefault(); setAt((a) => Math.min(flat.length - 1, a + (e.key === "ArrowDown" ? 2 : 1))); }
    else if (e.key === "ArrowUp" || e.key === "ArrowLeft") { e.preventDefault(); setAt((a) => Math.max(0, a - (e.key === "ArrowUp" ? 2 : 1))); }
    else if (e.key === "Enter" && cur) { e.preventDefault(); onPick(cur[0]); }
  };
  return html`<div class="vms-sheet" role="dialog" aria-label="Add a phase" onKeyDown=${key}>
    <div class="vms-sheet-h"><span class="t">Add a phase</span>${where ? html`<span class="chip acc sm">${where}</span>` : null}<span class="sp"></span>
      <${Button} kind="ghost" size="xs" icon="x" title="Close (Esc)" onClick=${onClose} /></div>
    <div class="vms-sheet-find"><div class="field sm"><${Icon} name="search" /><input ref=${inp} value=${q} placeholder="Find a game kind: boss, rhythm, hold…"
      aria-label="Find a game kind" onInput=${(e) => { setQ(e.target.value); setAt(0); }} /></div></div>
    <div class="vms-kinds">
      ${groups.map(([g, ks]) => html`<div class="vms-grp-h">${g}<span>${ks.length}</span></div>
        ${ks.map((k) => html`<button type="button" class=${cx("vms-kind", cur && cur[0] === k[0] && "on")} onClick=${() => onPick(k[0])}
            onMouseEnter=${() => setAt(flat.indexOf(k))} ...${tip({ head: k[1], lines: [k[2], "Opens playable, with placeholder art to swap."] })}>
          <span class="kt">${kicon(k[0])}<span class="nm">${k[1]}</span><span class="kb">${k[3].map((g2) => html`<span class=${cx("vms-glyph", g2 === "●" && "a")}>${g2}</span>`)}</span></span>
          <span class="kd">${k[2]}</span></button>`)}`)}
      ${flat.length ? null : html`<div class="vms-none">No game kind by that name</div>`}
    </div>
    <div class="vms-sheet-f"><span class="muted">Opens playable, with placeholder art to swap.</span><span class="sp"></span>
      <${Button} size="sm" onClick=${onClose}>Cancel<//>
      <${Button} kind="primary" size="sm" disabled=${!cur} onClick=${() => cur && onPick(cur[0])}>${cur ? "Add " + cur[1] : "Add"}<//></div>
  </div>`;
}

// ---- the board ------------------------------------------------------------------------------------------------------
export function Storyboard({ ed, onOpen, onPlay, onClose }) {
  const doc = ed.doc, flow = doc.flow || { cards: [] };
  const [sel, setSel] = useState(() => {
    const c = (flow.cards || []).find((k) => k.card === "phase" && (doc.phases[ed.ph] || {}).id === k.phase);
    return c ? c.id : flow.start;
  });
  const [view, setView] = useState(null);         // {k, ox, oy}; null until fitted
  const [wire, setWire] = useState(null);         // {from, port, x, y, over, keys: [ids], at}
  const [sheet, setSheet] = useState(null);       // {from, port, to}
  const [, setTick] = useState(0);
  const root = useRef(null), area = useRef(null), side = useRef(null);
  const lay = useMemo(() => layoutFlow(doc), [JSON.stringify(flow), (doc.phases || []).length]);
  const cards = (flow.cards || []).filter((c) => c && c.id);
  const byId = new Map(cards.map((c) => [c.id, c]));
  const problems = flowProblems(doc);
  const phaseOf = (c) => (doc.phases || []).find((p) => p.id === c.phase);
  const clipOf = (c) => (((doc.assets || {}).clips) || []).find((k) => k.id === c.clip);
  const sc = byId.get(sel);

  const fit = () => {
    const el = area.current; if (!el) return;
    const r = el.getBoundingClientRect();
    const k = clamp(Math.min((r.width - 32) / lay.W, (r.height - 32) / lay.H), 0.3, 1.25);
    if (r.width < 40 || r.height < 40) return;
    setView({ k, ox: (r.width - lay.W * k) / 2, oy: Math.max(8, (r.height - lay.H * k) / 2), auto: true });
  };
  const fitRef = useRef(fit);
  fitRef.current = fit;
  const autoRef = useRef(true);
  autoRef.current = !view || !!view.auto;
  useEffect(() => {       // the board stays fitted as its area settles and resizes, until the user pans or zooms it
    if (!area.current) return undefined;
    const ro = new ResizeObserver(() => { if (autoRef.current) fitRef.current(); });
    ro.observe(area.current);
    return () => ro.disconnect();
  }, []);
  useLayoutEffect(() => { if (!view) fit(); }, [view]);
  useLayoutEffect(() => { if (view) fit(); }, [lay.boxes.size]);      // a card added or taken away: the whole board in view
  useEffect(() => { if (root.current) root.current.focus(); }, []);
  const v = view || { k: 1, ox: 0, oy: 0 };
  const toWorld = (cx2, cy2) => { const r = area.current.getBoundingClientRect(); return [(cx2 - r.left - v.ox) / v.k, (cy2 - r.top - v.oy) / v.k]; };
  const hit = (x, y) => { for (const b of lay.boxes.values()) if (x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h) return b.id; return null; };

  // -- changes: each one ed.commit ---------------------------------------------------------------------------------
  const commit = (d, label) => { ed.commit(d, label); setTick((t) => t + 1); };
  const doWire = (from, port, to) => {
    if (wireWhy(doc, from, port, to)) return false;
    const d = clone(doc);
    d.flow.cards.find((c) => c.id === from)[port] = to;
    commit(d, "Wire " + cardName(doc, byId.get(from)) + " " + PORT_WORD[port] + " to " + cardName(doc, byId.get(to)));
    return true;
  };
  const lostEnd = (d) => {
    let e = d.flow.cards.find((c) => c.card === "end" && c.outcome === "lost");
    if (!e) { e = { id: uniqueCardId(d, "lost"), card: "end", outcome: "lost" }; d.flow.cards.push(e); }
    return e.id;
  };
  const insertPhase = async (from, port, kind) => {
    const to = (byId.get(from) || {})[port];
    let r;
    try { r = await call("vmodes.phase_template", doc, kind); } catch (err) { r = { ok: false, problems: [String(err && err.message || err)] }; }
    if (!r || !r.ok) { ed.status = { kind: "err", text: "Not kept", why: (r && r.problems) || [] }; ed.notify.panels(); return null; }
    const d = r.doc;
    const id = uniqueCardId(d, r.phase);
    // a loss goes where the card before it sends its own (the lost clip, as a rule); else to the lost end
    const fromCard = d.flow.cards.find((c) => c.id === from) || {};
    const inherit = fromCard.card === "phase" && fromCard.lost && fromCard.lost !== from ? fromCard.lost : null;
    const card = { id, card: "phase", phase: r.phase, won: to, lost: inherit || lostEnd(d) };
    d.flow.cards.splice(d.flow.cards.findIndex((c) => c.id === from) + 1, 0, card);
    d.flow.cards.find((c) => c.id === from)[port] = id;
    const kn = (KIND_NAME[kind] || kind).toLowerCase();
    commit(d, "Add " + (/^[aeiou]/.test(kn) ? "an " : "a ") + kn + " phase");
    setSel(id); setSheet(null);
    return id;
  };
  const insertClip = (from, port, clip) => {
    const to = (byId.get(from) || {})[port];
    const d = clone(doc);
    const id = uniqueCardId(d, clip);
    d.flow.cards.splice(d.flow.cards.findIndex((c) => c.id === from) + 1, 0, { id, card: "clip", clip, then: to });
    d.flow.cards.find((c) => c.id === from)[port] = id;
    commit(d, "Add the clip " + clip);
    setSel(id);
    return id;
  };
  // what deleting a card would leave, or why it cannot go
  const removal = (id) => {
    const c = byId.get(id);
    if (!c) return { why: "there is no such card" };
    const d = clone(doc), cs = d.flow.cards;
    let to = c.card === "clip" ? c.then : c.card === "phase" ? c.won : null;
    if (c.card === "end") {
      const other = cs.find((k) => k.card === "end" && k.id !== id && k.outcome === c.outcome);
      if (!other) return { why: "it is the only " + (c.outcome === "won" ? "Won" : "Lost") + " end; the mode needs it to finish" };
      to = other.id;
    }
    if (to === id) return { why: "it leads only to itself" };
    for (const k of cs) for (const p of ["then", "won", "lost"]) if (k[p] === id) k[p] = to;
    if (d.flow.start === id) d.flow.start = to;
    d.flow.cards = cs.filter((k) => k.id !== id);
    if (c.card === "phase" && !d.flow.cards.some((k) => k.card === "phase" && k.phase === c.phase)) {
      if (d.phases.length <= 1) return { why: "it plays the mode's only phase" };
      d.phases = d.phases.filter((p) => p.id !== c.phase);
      d.hud = (d.hud || []).map((h) => (h.phases ? Object.assign({}, h, { phases: h.phases.filter((p) => p !== c.phase) }) : h))
        .filter((h) => !h.phases || h.phases.length);
      if (d.pays && d.pays.awards) d.pays.awards = d.pays.awards.filter((a) => a.phase !== c.phase);
      if (d.editor && d.editor.markers) delete d.editor.markers[c.phase];
    }
    const p = flowProblems(d);
    if (p.length) return { why: p[0] };
    return { doc: d, to };
  };
  const remove = (id) => {
    const r = removal(id);
    if (!r.doc) return false;
    commit(r.doc, "Delete " + cardName(doc, byId.get(id)));
    setSel(r.to && r.doc.flow.cards.some((k) => k.id === r.to) ? r.to : r.doc.flow.start);
    return true;
  };
  const setCard = (id, patch, label) => {
    const d = clone(doc);
    Object.assign(d.flow.cards.find((c) => c.id === id), patch);
    for (const [k, val] of Object.entries(patch)) if (val == null) delete d.flow.cards.find((c) => c.id === id)[k];
    if (flowProblems(d).length) return;
    commit(d, label);
  };
  const setPhase = (pid, patch, label) => {
    const d = clone(doc);
    Object.assign(d.phases.find((p) => p.id === pid), patch);
    commit(d, label);
  };
  const setStart = (id) => { const d = clone(doc); d.flow.start = id; if (!flowProblems(d).length) commit(d, "Start with " + cardName(doc, byId.get(id))); };

  // -- the plus on a wire --------------------------------------------------------------------------------------------
  const plusMenu = (e, from, port, to) => {
    const clips = ((doc.assets || {}).clips) || [];
    openMenu(e.currentTarget, [
      { header: "Between " + cardName(doc, byId.get(from)) + " and " + cardName(doc, byId.get(to)) },
      { label: "Phase…", icon: "plus", onClick: () => setSheet({ from, port, to }), title: "Pick a game kind; it opens playable" },
      clips.length ? { label: "Clip", icon: "film", submenu: clips.map((k) => ({ label: k.id, onClick: () => insertClip(from, port, k.id), title: k.file })) }
        : { label: "Clip (none yet)", icon: "film", onClick: () => setSheet({ noClips: true }), title: "Clips are made with the tab's clip tools" },
    ]);
  };

  // -- pointer: pan the board, or draw a wire from a port --------------------------------------------------------------
  const down = (e) => {
    if (e.button !== 0 && e.button !== 1) return;
    const port = e.target.closest && e.target.closest("[data-port]");
    if (port) {
      e.preventDefault(); e.stopPropagation();
      const [x, y] = toWorld(e.clientX, e.clientY);
      setWire({ from: port.dataset.card, port: port.dataset.port, x, y, over: null });
      const mv = (ev) => { const [a, b] = toWorld(ev.clientX, ev.clientY); setWire((w) => w && Object.assign({}, w, { x: a, y: b, over: hit(a, b) })); };
      const up = (ev) => {
        window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up);
        const [a, b] = toWorld(ev.clientX, ev.clientY), to = hit(a, b);
        setWire(null);
        if (to) doWire(port.dataset.card, port.dataset.port, to);
      };
      window.addEventListener("pointermove", mv); window.addEventListener("pointerup", up);
      return;
    }
    if (e.target.closest && e.target.closest(".vms-card, .vms-end, .vms-plus, button")) return;
    const x0 = e.clientX, y0 = e.clientY, v0 = v;
    area.current.classList.add("panning");
    const mv = (ev) => setView({ k: v0.k, ox: v0.ox + ev.clientX - x0, oy: v0.oy + ev.clientY - y0 });
    const up = () => { area.current && area.current.classList.remove("panning"); window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", mv); window.addEventListener("pointerup", up);
  };
  const wheel = (e) => {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) {
      const r = area.current.getBoundingClientRect(), cx2 = e.clientX - r.left, cy2 = e.clientY - r.top;
      const k = clamp(v.k * Math.pow(1.0015, -e.deltaY), 0.25, 2);
      setView({ k, ox: cx2 - (cx2 - v.ox) * k / v.k, oy: cy2 - (cy2 - v.oy) * k / v.k });
    } else setView({ k: v.k, ox: v.ox - e.deltaX, oy: v.oy - e.deltaY });
  };

  // -- the keyboard ------------------------------------------------------------------------------------------------------
  const near = (from, dx, dy, among) => {
    const a = lay.boxes.get(from);
    if (!a) return among[0] || null;
    let best = null, bd = 1e9;
    for (const id of among) {
      if (id === from) continue;
      const b = lay.boxes.get(id);
      const vx = (b.x + b.w / 2) - (a.x + a.w / 2), vy = (b.y + b.h / 2) - (a.y + a.h / 2);
      const along = vx * dx + vy * dy, across = Math.abs(vx * dy - vy * dx);
      if (along <= 0) continue;
      const d = along + across * 2;
      if (d < bd) { bd = d; best = id; }
    }
    return best;
  };
  const validFor = (from, port) => cards.map((c) => c.id).filter((id) => !wireWhy(doc, from, port, id));
  const key = (e) => {
    if (sheet || typing(e.target)) return;
    const k = e.key, arrows = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    if (wire && wire.keys) {
      if (arrows[k]) {
        e.preventDefault();
        const n = near(wire.over || wire.from, arrows[k][0], arrows[k][1], wire.keys) || wire.over;
        setWire(Object.assign({}, wire, { over: n }));
      } else if (k === "Enter") { e.preventDefault(); if (wire.over) doWire(wire.from, wire.port, wire.over); setWire(null); }
      else if (k === "Escape") { e.preventDefault(); setWire(null); }
      return;
    }
    if (arrows[k]) { e.preventDefault(); const n = near(sel, arrows[k][0], arrows[k][1], [...lay.boxes.keys()]); if (n) setSel(n); return; }
    if (k === "Enter" && sc) {
      e.preventDefault();
      if (sc.card === "phase") onOpen(doc.phases.findIndex((p) => p.id === sc.phase));
      else { const f = side.current && side.current.querySelector("input, select, button"); if (f) f.focus(); }
      return;
    }
    if (k === " " && sc) { e.preventDefault(); const f = side.current && side.current.querySelector("input, select, button"); if (f) f.focus(); return; }
    if ((k === "Delete" || k === "Backspace") && sc) { e.preventDefault(); remove(sc.id); return; }
    if ((k === "w" || k === "W" || k === "l" || k === "L") && sc && !e.ctrlKey && !e.metaKey) {
      const port = (k === "l" || k === "L") ? "lost" : sc.card === "clip" ? "then" : "won";
      if (!PORT_OF[sc.card].includes(port)) return;
      e.preventDefault();
      const keys = validFor(sc.id, port), b = lay.boxes.get(sc.id), [x, y] = portPoint(b, port);
      setWire({ from: sc.id, port, x, y, over: keys[0] || null, keys });
      return;
    }
    if ((k === "f" || k === "F") && !e.ctrlKey) { e.preventDefault(); fit(); return; }
    if (k === "Escape") { e.preventDefault(); onClose(); }
  };

  // the shot rig's handle
  useEffect(() => {
    window.__vmStory = {
      ready: true,
      cards: () => [...lay.boxes.values()].map((b) => ({ id: b.id, x: b.x, y: b.y, w: b.w, h: b.h })),
      select: (id) => setSel(id),
      wire: (from, port, to) => doWire(from, port, to),
      why: (from, port, to) => wireWhy(doc, from, port, to),
      insertPhase: (from, port, kind) => insertPhase(from, port, kind),
      insertClip: (from, port, clip) => insertClip(from, port, clip),
      remove: (id) => remove(id),
      problems: () => flowProblems(doc),
      toPage: (x, y) => { const r = area.current.getBoundingClientRect(); return [r.left + v.ox + x * v.k, r.top + v.oy + y * v.k]; },
    };
  });
  useEffect(() => () => { window.__vmStory = null; }, []);

  // -- drawing ---------------------------------------------------------------------------------------------------------
  const wireDraw = [], labels = [], pluses = [];
  const valid = wire ? new Set(wire.keys || validFor(wire.from, wire.port)) : null;
  for (const c of cards) {
    const a = lay.boxes.get(c.id);
    if (!a) continue;
    for (const port of PORT_OF[c.card] || []) {
      const b = lay.boxes.get(c[port]);
      if (!b) continue;
      const p = wirePath(a, port, b), cls = port === "won" ? "won" : port === "lost" ? "lost" : "then";
      wireDraw.push(html`<path class=${cx("vms-wire", cls, wire && wire.from === c.id && wire.port === port && "moving")} d=${p.d} marker-end=${`url(#vms-ar-${cls})`} />`);
      if (port !== "then") labels.push(html`<span class=${cx("vms-wl", cls)} style=${`left:${p.mx + 10}px;top:${p.my - 22}px`}>${port === "won" ? "WON" : "LOST"}</span>`);
      if (b !== a) pluses.push(html`<button type="button" class="vms-plus" style=${`left:${p.mx - 11}px;top:${p.my - 11}px`}
        onClick=${(e) => plusMenu(e, c.id, port, c[port])} ...${tip("Put a clip or a phase in here")} aria-label="Insert between">+</button>`);
    }
    if (c.card === "phase" && (c.tries || 1) > 1) {
      wireDraw.push(html`<path class="vms-wire retry" d=${`M${a.x + a.w * 0.3} ${a.y} C ${a.x + a.w * 0.3} ${a.y - 34}, ${a.x + a.w * 0.7} ${a.y - 34}, ${a.x + a.w * 0.7} ${a.y - 3}`} marker-end="url(#vms-ar-retry)" />`);
      labels.push(html`<span class="vms-wl retry" style=${`left:${a.x + a.w * 0.5 - 40}px;top:${a.y - 46}px`}>${c.tries} TRIES</span>`);
    }
  }
  if (wire) {
    const a = lay.boxes.get(wire.from), [x1, y1] = portPoint(a, wire.port);
    const tb = wire.over && lay.boxes.get(wire.over);
    const x2 = tb ? tb.x + tb.w / 2 : wire.x, y2 = tb ? tb.y + tb.h / 2 : wire.y;
    wireDraw.push(html`<path class=${cx("vms-wire drawing", wire.port)} d=${`M${x1} ${y1} C ${x1 + (wire.port === "lost" ? 0 : 80)} ${y1 + (wire.port === "lost" ? 80 : 0)}, ${x2 - 60} ${y2}, ${x2} ${y2}`} />`);
  }
  const marker = (n) => html`<marker id=${"vms-ar-" + n} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" class=${"vms-arh " + n} /></marker>`;

  const startBox = lay.boxes.get(flow.start);
  const nPhases = new Set(cards.filter((c) => c.card === "phase").map((c) => c.phase)).size, nClips = cards.filter((c) => c.card === "clip").length;
  const st = ed.status || {};
  const cardView = (c) => {
    const b = lay.boxes.get(c.id);
    if (!b) return null;
    const isSel = sel === c.id, onStage = c.card === "phase" && (doc.phases[ed.ph] || {}).id === c.phase;
    const target = wire && wire.from !== c.id ? (valid.has(c.id) ? "ok" : "no") : wire && wire.from === c.id && c.card !== "clip" && valid.has(c.id) ? "ok" : wire ? "no" : "";
    const why = target === "no" && wire ? (wireWhy(doc, wire.from, wire.port, c.id) || "") : "";
    const common = {
      "data-card": c.id,
      style: `left:${b.x}px;top:${b.y}px;width:${b.w}px;height:${b.h}px`,
      onPointerDown: (e) => { if (!e.target.closest("[data-port]")) e.stopPropagation(); },
    };
    if (c.card === "end") {
      return html`<div ...${common} class=${cx("vms-end", c.outcome, isSel && "on", target === "ok" && "drop-ok", target === "no" && "drop-no", wire && wire.over === c.id && "over")}
          onClick=${() => setSel(c.id)} ...${tip(why ? { head: "Cannot wire here", lines: [why] } : (c.outcome === "won" ? "The mode is won here" : "The mode is lost here"))}>
        ${c.outcome === "won" ? "Won" : "Lost"}</div>`;
    }
    const ph = c.card === "phase" ? phaseOf(c) : null, clip = c.card === "clip" ? clipOf(c) : null;
    const kind = ph ? ph.kind : "clip";
    const ports = (PORT_OF[c.card] || []).map((p) => html`<span class=${cx("vms-port", p)} data-port=${p} data-card=${c.id}
        ...${tip({ head: "Drag to wire " + (p === "then" ? "where it goes next" : "where it goes when " + p), lines: [p === "lost" ? "or press L" : "or press W"] })}></span>`);
    return html`<div ...${common} class=${cx("vms-card", c.card, isSel && "on", onStage && "stage", target === "ok" && "drop-ok", target === "no" && "drop-no", wire && wire.over === c.id && "over")}
        role="button" aria-label=${cardName(doc, c)}
        onClick=${() => { setSel(c.id); if (c.card === "phase" && !wire) onOpen(doc.phases.findIndex((p) => p.id === c.phase)); }}
        ...${tip(why ? { head: "Cannot wire here", lines: [why] } : c.card === "phase" ? { head: (ph && ph.title) || c.phase, lines: ["Click: open it on the stage", "Arrows then Space: its settings"] } : { head: "Clip " + c.clip, lines: [(clip && clip.file) || "no file named"] })}>
      <div class="vms-band">${kicon(kind)}<span class="kn">${c.card === "clip" ? "Clip" : KIND_NAME[kind] || kind}</span>
        ${flow.start === c.id ? html`<span class="chip sm acc vms-startchip">Start</span>` : null}
        <span class="sp"></span>
        ${c.card === "phase" ? html`<button type="button" class="btn ghost icon xs vms-gear" onClick=${(e) => { e.stopPropagation(); setSel(c.id); }} ...${tip("Its settings: title, objective, tries, wires")}><${Icon} name="gear" /></button>` : null}
      </div>
      <div class="vms-body">
        ${c.card === "phase" ? html`
          <div class="tt">${(ph && ph.title) || c.phase}</div>
          <div class="ob">${(ph && ph.objective) || ""}${ph && ph.length_s ? html`<span class="mono"> · ${ph.length_s} s</span>` : null}</div>
          <div class="res">${((ph && ph.win) || []).slice(0, 2).map((w) => html`<span class="chip sm ok">${whenText(w)}</span>`)}</div>`
        : html`
          <div class="tt">${c.clip}</div>
          <div class="ob mono">${(clip && clip.file) || "missing"}</div>
          <div class="res">${clip && clip.skippable !== false ? html`<span class="chip sm">skippable</span>` : html`<span class="chip sm">plays through</span>`}</div>`}
      </div>
      ${ports}
    </div>`;
  };

  // -- the side panel -------------------------------------------------------------------------------------------------
  const wireSelect = (c, port) => {
    const opts = cards.filter((k) => k.id === c[port] || !wireWhy(doc, c.id, port, k.id))
      .map((k) => ({ value: k.id, label: cardLabel(doc, k) }));
    return html`<div class="vms-row"><span class="lab">${port === "then" ? "Then" : port === "won" ? "When won" : "When lost"}</span>
      <${Select} sm value=${c[port] || ""} options=${opts} title="Only the cards that keep every card reachable and every way out ending"
        onChange=${(to) => doWire(c.id, port, to)} /></div>`;
  };
  const panel = () => {
    if (!sc) return html`<div class="vms-side-empty"><${Empty} icon="list" title="Pick a card">Click a clip or an end, or use the arrows; a phase opens on the stage.<//></div>`;
    const rm = removal(sc.id);
    const isStart = flow.start === sc.id;
    const startWhy = isStart ? "it is the start already" : (() => { const d = clone(doc); d.flow.start = sc.id; const p = flowProblems(d); return p.length ? p[0] : ""; })();
    const foot = html`<div class="vms-side-f">
      <${Button} size="sm" icon="flag" disabled=${!!startWhy} title=${startWhy ? { head: "Cannot start here", lines: [startWhy] } : "The mode starts with this card"} onClick=${() => setStart(sc.id)}>Make this the start<//>
      <${Button} size="sm" kind="ghost" icon="trash" disabled=${!rm.doc} title=${rm.doc ? "Delete this card (Delete); what led to it leads on" : { head: "Cannot delete it", lines: [rm.why] }} onClick=${() => remove(sc.id)}>Delete<//>
    </div>`;
    if (sc.card === "end") {
      const other = sc.outcome === "won" ? "lost" : "won";
      const flip = (() => { const d = clone(doc); d.flow.cards.find((k) => k.id === sc.id).outcome = other; const p = flowProblems(d); return p.length ? p[0] : ""; })();
      return html`<div class="vms-group"><span class="lab">End</span>
        <div class="seg sm" role="group" aria-label="Outcome">
          ${["won", "lost"].map((o) => html`<button type="button" class=${cx(sc.outcome === o && "on")} disabled=${sc.outcome !== o && !!flip}
            onClick=${() => sc.outcome !== o && setCard(sc.id, { outcome: o }, "The end is " + o)} ...${tip(sc.outcome !== o && flip ? { head: "Cannot", lines: [flip] } : o === "won" ? "The mode is won here" : "The mode is lost here")}>${o === "won" ? "Won" : "Lost"}</button>`)}
        </div></div>${foot}`;
    }
    if (sc.card === "clip") {
      const clips = ((doc.assets || {}).clips) || [];
      const clip = clipOf(sc);
      return html`<div class="vms-group"><span class="lab">Clip</span>
          ${clips.length ? html`<${Select} sm value=${sc.clip} options=${clips.map((k) => ({ value: k.id, label: k.id + " · " + k.file }))}
            title="The clips made with the tab's clip tools" onChange=${(id) => setCard(sc.id, { clip: id }, "Play the clip " + id)} />`
            : html`<div class="muted small">No clips yet: they are made with the tab's clip tools.</div>`}
          <div class="vms-row"><span class="lab">Skip</span><span class="small">${clip && clip.skippable !== false ? "The player may skip it" : "It plays through"}</span></div>
        </div>
        <div class="vms-group"><span class="lab">Wires</span>${wireSelect(sc, "then")}</div>${foot}`;
    }
    const ph = phaseOf(sc) || {};
    const pi = doc.phases.findIndex((p) => p.id === sc.phase);
    return html`<div class="vms-group"><span class="lab">Phase</span>
        <div class="vms-row"><span class="lab">Title</span><${TextIn} label="Title" value=${ph.title} max=${40} placeholder=${ph.id} onCommit=${(t) => setPhase(ph.id, { title: t }, "Rename the phase " + ph.id)} /></div>
        <div class="vms-row"><span class="lab">Objective</span><${TextIn} label="Objective" value=${ph.objective} placeholder="What to do" onCommit=${(t) => setPhase(ph.id, { objective: t }, "Change the objective")} /></div>
        <div class="vms-row"><span class="lab">Tries</span><${Stepper} label="Tries" value=${sc.tries || 1} min=${1} max=${9}
          onCommit=${(n) => setCard(sc.id, { tries: n > 1 ? n : null }, n > 1 ? n + " tries at " + (ph.title || ph.id) : "One try at " + (ph.title || ph.id))} /></div>
        <${Button} size="sm" kind="primary" icon="edit" onClick=${() => onOpen(pi)}>Open on the stage<//>
      </div>
      <div class="vms-group"><span class="lab">Wires</span>${wireSelect(sc, "won")}${wireSelect(sc, "lost")}</div>${foot}`;
  };

  return html`<div class="vms" ref=${root} tabindex="0" onKeyDown=${key} aria-label="Storyboard">
    <div class="vms-head">
      <span class="t">Storyboard</span>
      <span class="mono muted">${nPhases} phase${nPhases === 1 ? "" : "s"} · ${nClips} clip${nClips === 1 ? "" : "s"}</span>
      ${problems.length ? html`<span class="chip sm err" ...${tip({ head: "The flow cannot be played", lines: problems })}>${problems[0]}</span>`
        : html`<span class="chip sm ok">Every card leads to an end</span>`}
      ${st.kind === "err" ? html`<span class="chip sm err" ...${tip({ head: "That change was not kept", lines: st.why || [] })}>Not kept</span>` : null}
      <span class="sp"></span>
      <span class="muted small vms-hint">Drag from a card's edge to wire it · <span class="kbd">W</span><span class="kbd">L</span> wire from the keyboard</span>
      <${Button} kind="ghost" size="sm" icon="fit" title="Fit the board (F)" onClick=${fit}>Fit<//>
      <${Button} kind="primary" size="sm" icon="play" title="Play the whole mode from its start card" onClick=${() => onPlay(null)}>Play from the start<//>
      <${Button} kind="ghost" size="sm" icon="x" title="Back to the stage (Esc)" onClick=${onClose} />
    </div>
    <div class="vms-area" ref=${area} onPointerDown=${down} onWheel=${wheel}>
      <div class="vms-world" style=${`transform:translate(${v.ox}px,${v.oy}px) scale(${v.k});width:${lay.W}px;height:${lay.H}px`}>
        <svg class="vms-wires" width=${lay.W} height=${lay.H} viewBox=${`0 0 ${lay.W} ${lay.H}`}>
          <defs>${["won", "lost", "then", "retry"].map(marker)}</defs>
          ${startBox ? html`<path class="vms-wire then" d=${`M${startBox.x - 34} ${startBox.y + startBox.h / 2} H${startBox.x - 3}`} marker-end="url(#vms-ar-then)" />` : null}
          ${wireDraw}
        </svg>
        ${labels}
        ${cards.map(cardView)}
        ${wire ? null : pluses}
      </div>
      ${cards.length ? null : html`<div class="vms-empty"><${Empty} icon="list" title="No storyboard yet">This mode has no flow cards.<//></div>`}
    </div>
    <div class="vms-side" ref=${side}>
      <div class="vms-side-h">${sc ? html`${kicon(sc.card === "phase" ? (phaseOf(sc) || {}).kind : sc.card === "clip" ? "clip" : "custom")}<span class="t">${cardLabel(doc, sc)}</span>` : html`<span class="t">Card</span>`}</div>
      <div class="vms-side-b">${panel()}</div>
    </div>
    ${sheet && !sheet.noClips ? html`<div class="vms-scrim" onPointerDown=${(e) => { if (e.target === e.currentTarget) setSheet(null); }}>
      <${KindSheet} where=${"after " + cardLabel(doc, byId.get(sheet.from)) + (sheet.port === "then" ? "" : ", when " + sheet.port)}
        onClose=${() => { setSheet(null); root.current && root.current.focus(); }} onPick=${(k) => insertPhase(sheet.from, sheet.port, k)} /></div>` : null}
    ${sheet && sheet.noClips ? html`<div class="vms-scrim" onPointerDown=${(e) => { if (e.target === e.currentTarget) setSheet(null); }}>
      <div class="vms-sheet small-sheet" role="dialog" aria-label="No clips yet">
        <${Empty} icon="film" title="No clips yet" action=${html`<div class="row" style="gap:8px;justify-content:center">
            <${Button} onClick=${() => setSheet(null)}>Not now<//><${Button} kind="primary" onClick=${onClose}>Close the storyboard<//></div>`}>
          Clips are cut on the Video modes tab with its clip tools; once a mode has one, it can go anywhere on the board.<//>
      </div></div>` : null}
  </div>`;
}
