// The video mode editor's HUD and feel (PAD-1666): the HUD parts' palette, their list, their inspector, and the
// Look and feel panel (the style presets, every effect's switch with its cost against the machine's budget, the
// transitions, the bursts and the particle editor). Held to the plan's design language (section 6), as the rest
// of the editor.
//
// Every part and effect is the engine's own (vm_engine.c draw_hud, text_fx, particles): the stage shows them because
// the engine draws them, with sample numbers in the editor's still, and a particle's preview is the engine bursting
// it over the stage (vm_edit_burst). Nothing here draws a HUD of its own.

import { html, useState, Button, Select, Icon, Check, tip, cx } from "../core/ui.js";

export const PARTS = [
  ["health", "Health", "Health as pips, hearts, a bar or a ring, turning the danger color when low"],
  ["meter", "Meter", "A value of the mode's as a bar, with danger zones"],
  ["score", "Score", "The mode's score, rolling up to each new number"],
  ["combo", "Combo", "Kills close together; shown from 2 up"],
  ["multiplier", "Multiplier", "What the combo multiplies points by; shown from x2 up"],
  ["timer", "Timer", "The phase's time left, as a number or a ring"],
  ["lives", "Tries", "The tries left at this phase"],
  ["progress", "Progress", "How far through the phase (a boss: its weak points)"],
  ["prompts", "Button prompts", "What each button does now, in the buttons' places"],
  ["callout", "Callout", "The big words: the phase's title, CLEAR!, TRY AGAIN"],
  ["counter", "Counter", "A counter of the mode's, in words: CRATES {n}"],
  ["text", "Words", "Words of your own"],
  ["popup", "Pop-up words", "+500 or PERFECT rising from where it happened"],
];
const PART_NAME = Object.fromEntries(PARTS.map(([k, l]) => [k, l]));
const LOOKS = {
  health: [["pips", "Pips"], ["hearts", "Hearts"], ["bar", "Bar"], ["ring", "Ring"], ["number", "Number"]],
  lives: [["pips", "Pips"], ["hearts", "Hearts"], ["bar", "Bar"], ["ring", "Ring"], ["number", "Number"]],
  meter: [["bar", "Bar"], ["pips", "Pips"], ["ring", "Ring"]],
  progress: [["bar", "Bar"], ["ring", "Ring"]],
  timer: [["number", "Number"], ["ring", "Ring and number"], ["bar", "Bar"]],
};
const WORDS = new Set(["score", "combo", "multiplier", "counter", "timer", "text", "callout", "prompts", "popup", "health", "lives"]);
const SIZED = new Set(["health", "lives", "meter", "progress", "timer", "prompts"]);
const DANGER = new Set(["health", "lives", "meter", "timer"]);
const NUMBERS = new Set(["score", "counter"]);
const POPS = new Set(["score", "counter", "combo", "multiplier", "timer", "health", "lives"]);
const HAPPENINGS = [["kill", "A kill"], ["pickup", "A pick-up"], ["hit", "A hit that did not kill"], ["hurt", "The player hurt"],
  ["fire", "A shot fired"], ["prompt_perfect", "A perfect press"], ["prompt_good", "A good press"], ["prompt_miss", "A missed press"]];
const BURSTS = [["kill", "A kill"], ["hit", "A hit"], ["hurt", "The player hurt"], ["pickup", "A pick-up"], ["fire", "A shot fired"],
  ["boss", "A boss going down"]];
const TRANSITIONS = [["cut", "Cut"], ["fade", "Fade through black"], ["white_flash", "White flash"], ["wipe", "Wipe"], ["iris", "Iris"]];
const PRESET_PARTICLES = ["spark", "smoke", "debris", "glow"];
const DEFAULT_BURSTS = { kill: "spark", hurt: "debris", pickup: "glow", hit: "spark", fire: "none", boss: "smoke" };

const r2 = (v) => Math.round(v * 100) / 100;
const hex6 = (c, d = "#ffffff") => (typeof c === "string" && /^#[0-9a-f]{6}/i.test(c) ? c.slice(0, 7) : d);
const withHex = (old, v) => (typeof old === "string" && old.length === 9 ? v + old.slice(7) : v);

// a new part, at the place it was dropped
export function newPart(doc, part, x, y) {
  const fonts = ((doc.assets || {}).fonts || []).slice().sort((a, b) => (a.size || 0) - (b.size || 0));
  const small = fonts[0] && fonts[0].id, big = fonts.length ? fonts[fonts.length - 1].id : undefined;
  const meter = (doc.values || []).find((v) => v.type === "meter"), counter = (doc.values || []).find((v) => v.type === "counter");
  const ids = new Set((doc.hud || []).map((h) => h.id));
  let id = part, n = 2;
  while (ids.has(id)) id = part + "_" + n++;
  const at = { id, part, x: Math.round(x), y: Math.round(y) };
  const base = {
    health: { w: 180, h: 22, look: "pips", colour: "#5ee07a", danger: "#ff4b3a" },
    meter: Object.assign({ w: 300, h: 18, look: "bar", colour: "#f2c14e" }, meter ? { value: meter.id } : {}),
    score: { font: small, colour: "#ffffff", count_up: 0.5, pop: true },
    combo: { font: small, colour: "#ffd23f", pop: true },
    multiplier: { font: small, colour: "#ffd23f", text: "x{n}", pop: true },
    timer: { w: 64, h: 64, look: "ring", font: small, colour: "#ffffff", danger: "#ff4b3a" },
    lives: { w: 120, h: 18, look: "pips", colour: "#ffffff" },
    progress: { w: 600, h: 6, colour: "#e9eae7" },
    prompts: { x: 0, w: 1360, h: 40, font: small, colour: "#ffffff", accent: "#ffd23f" },
    callout: { font: big, colour: "#ffd23f", outline: "#101214" },
    counter: Object.assign({ font: small, text: "x {n}", colour: "#ffffff" }, counter ? { value: counter.id } : {}),
    text: { font: small, text: "WORDS", colour: "#ffffff" },
    popup: { font: small, text: "+{n}", on: ["kill"], colour: "#ffd23f", outline: "#101214", rise: 60, life_s: 0.8 },
  }[part] || {};
  const out = Object.assign(at, base);
  for (const k of Object.keys(out)) if (out[k] === undefined) delete out[k];
  return out;
}

// ---- the palette: parts to drag onto the stage ----------------------------------------------------------------
export function HudPalette({ ed }) {
  const startDrag = (e, part) => {
    if (e.button !== 0) return;
    const x0 = e.clientX, y0 = e.clientY, tgt = e.currentTarget;
    let ghost = null;
    const mv = (ev) => {
      if (!ghost && Math.hypot(ev.clientX - x0, ev.clientY - y0) < 4) return;
      if (!ghost) { ghost = tgt.cloneNode(true); ghost.classList.add("vme-ghost"); document.body.appendChild(ghost); }
      ghost.style.left = ev.clientX - 22 + "px"; ghost.style.top = ev.clientY - 14 + "px";
    };
    const upf = (ev) => {
      window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", upf);
      if (!ghost) return;
      ghost.remove();
      const r = ed.els.view.getBoundingClientRect();
      if (ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom) {
        const [x, y] = ed.toStage(ev.clientX - r.left, ev.clientY - r.top);
        ed.addHud(part, x, y);
      }
    };
    window.addEventListener("pointermove", mv); window.addEventListener("pointerup", upf);
  };
  return html`<div class="vme-hud-grid">
    ${PARTS.map(([k, label, about]) => html`<button type="button" class="vme-hud-tile" data-part=${k}
        onPointerDown=${(e) => startDrag(e, k)} onDblClick=${() => ed.addHud(k)}
        onKeyDown=${(e) => { if (e.key === "Enter") { e.preventDefault(); ed.addHud(k); } }}
        ...${tip({ head: label, lines: [about, "Drag it onto the stage, or press Enter to put one in the middle"] })}>${label}</button>`)}
  </div>`;
}

// ---- the HUD in Layers ------------------------------------------------------------------------------------------
export function HudLayers({ ed }) {
  const hud = ed.doc.hud || [], phid = ed.phase().id;
  if (!hud.length) return html`<div class="vme-empty-s">No HUD yet: drag a part from HUD below</div>`;
  return html`<div class="vme-layers">${hud.map((h, i) => {
    const here = !h.phases || !h.phases.length || h.phases.includes(phid);
    return html`<div class=${cx("vme-lay", ed.hudSel === i && "on", !here && "dim")} role="option" aria-selected=${ed.hudSel === i}
        onClick=${() => ed.setHud(i)} onMouseEnter=${() => { ed.hudHover = i; ed.dirty(); }} onMouseLeave=${() => { ed.hudHover = -1; ed.dirty(); }}
        ...${tip(here ? PART_NAME[h.part] : PART_NAME[h.part] + ": not shown in this phase")}>
      <span class="team hud"></span><span class="nm">${h.id}</span><span class="d">${PART_NAME[h.part] || h.part}</span></div>`;
  })}</div>`;
}

// ---- small fields -----------------------------------------------------------------------------------------------
function ColourField({ label, value, optional, onCommit, title }) {
  return html`<div class="vme-row" ...${tip(title || "")}><span class="vme-k">${label}</span>
    <div class="vme-col-pair">
      ${value || !optional ? html`<input type="color" class="vme-colour" value=${hex6(value)}
          onChange=${(e) => onCommit(withHex(value, e.target.value))} />` : html`<span class="vme-none">None</span>`}
      ${optional ? (value
        ? html`<button type="button" class="btn ghost icon xs" onClick=${() => onCommit(null)} ...${tip("Take it off")}><${Icon} name="x" /></button>`
        : html`<button type="button" class="btn ghost icon xs" onClick=${() => onCommit("#101214")} ...${tip("Add one")}><${Icon} name="plus" /></button>`) : null}
    </div></div>`;
}

// ---- the HUD part inspector ------------------------------------------------------------------------------------
export function HudInspector({ ed, ui }) {
  const { Scrub, TextIn, Group } = ui;
  const doc = ed.doc, i = ed.hudSel, h = (doc.hud || [])[i];
  if (!h) return null;
  const set = (label, patch) => ed.setHudPart(label, patch);
  const fonts = (doc.assets || {}).fonts || [];
  const vals = (doc.values || []).filter((v) => (h.part === "meter" ? v.type === "meter" : v.type === "counter"));
  const zones = h.zones || [];
  const box = ed.hudBox(i);
  const live = (k) => (v) => {
    if (v == null) { ed.hudPrev = null; ed.dirty(); return; }
    ed.hudPrev = Object.assign({ i }, h, { [k]: v }); ed.dirty();
  };
  return html`<div class="vme-dock-b">
    <${Group} label=${PART_NAME[h.part] || h.part} extra=${html`<span class="chip sm mono">${h.id}</span>`}>
      <div class="vme-two">
        <${Scrub} label="X" unit="px" value=${h.x} min=${-2000} max=${4000} onLive=${live("x")} onCommit=${(v) => set("Move " + h.id, { x: r2(v) })} />
        <${Scrub} label="Y" unit="px" value=${h.y} min=${-2000} max=${4000} onLive=${live("y")} onCommit=${(v) => set("Move " + h.id, { y: r2(v) })} />
        ${SIZED.has(h.part) ? html`
          <${Scrub} label="W" unit="px" value=${h.w || 0} min=${0} max=${4000} onLive=${live("w")} onCommit=${(v) => set("Size " + h.id, { w: r2(v) })} />
          <${Scrub} label="H" unit="px" value=${h.h || 0} min=${0} max=${2000} onLive=${live("h")} onCommit=${(v) => set("Size " + h.id, { h: r2(v) })} />` : null}
      </div>
      <div class="vme-chip-row"><span class="chip sm mono">${box ? Math.round(box.x1 - box.x0) + " × " + Math.round(box.y1 - box.y0) + " px drawn" : "not drawn in this phase"}</span></div>
      ${LOOKS[h.part] ? html`<div class="vme-row"><span class="vme-k">Look</span>
        <${Select} sm value=${h.look || LOOKS[h.part][0][0]} options=${LOOKS[h.part].map(([v, l]) => ({ value: v, label: l }))}
          onChange=${(v) => set("Look of " + h.id, { look: v })} /></div>` : null}
      ${h.part === "meter" || h.part === "counter" ? html`<div class="vme-row"><span class="vme-k">Shows</span>
        <${Select} sm value=${h.value || ""} options=${[{ value: "", label: h.part === "counter" ? "Pick-ups" : "Pick a meter" },
          ...vals.map((v) => ({ value: v.id, label: v.id }))]} onChange=${(v) => set("What " + h.id + " shows", { value: v || null })} /></div>` : null}
      ${(h.look === "pips" || h.look === "hearts" || (!h.look && (h.part === "health" || h.part === "lives"))) ? html`<div class="vme-row"
          ...${tip("A picture for each pip: its frame 1 full, frame 2 empty; none: drawn")}><span class="vme-k">Picture</span>
        <${Select} sm value=${h.picture || ""} options=${[{ value: "", label: "Drawn" }, ...((doc.assets || {}).pictures || []).map((p) => ({ value: p.id, label: p.id }))]}
          onChange=${(v) => set("Picture of " + h.id, { picture: v || null })} /></div>` : null}
      <${ColourField} label="Color" value=${h.colour || "#ffffff"} onCommit=${(v) => set("Color of " + h.id, { colour: v })} />
      ${h.part !== "popup" && h.part !== "text" ? html`<${ColourField} label=${h.part === "prompts" ? "Held" : "Frame"} optional value=${h.accent}
        title=${h.part === "prompts" ? "The word of a button held down lights in this" : "A frame round a bar"}
        onCommit=${(v) => set("Accent of " + h.id, { accent: v })} />` : null}
    <//>
    ${WORDS.has(h.part) && (h.part !== "health" && h.part !== "lives" || h.look === "number") ? html`<${Group} label="Words">
      ${h.part !== "prompts" && h.part !== "callout" ? html`<div class="vme-row" ...${tip("{n} is the number")}><span class="vme-k">Text</span>
        <${TextIn} value=${h.text} placeholder=${h.part === "popup" ? "+{n}" : h.part === "combo" || h.part === "multiplier" ? "x{n}" : "{n}"}
          onCommit=${(v) => set("Words of " + h.id, { text: v || null })} /></div>` : null}
      <div class="vme-row"><span class="vme-k">Font</span>
        <${Select} sm value=${h.font || ""} options=${[{ value: "", label: "The first font" }, ...fonts.map((f) => ({ value: f.id, label: f.id + " · " + f.size + " px" }))]}
          onChange=${(v) => set("Font of " + h.id, { font: v || null })} /></div>
      ${h.part !== "prompts" && h.part !== "popup" && h.part !== "callout" ? html`<div class="vme-row"><span class="vme-k">Align</span>
        <${Select} sm value=${h.align || "auto"} options=${[{ value: "auto", label: "By its place" }, { value: "left", label: "Left" },
          { value: "centre", label: "Center" }, { value: "right", label: "Right" }]} onChange=${(v) => set("Align " + h.id, { align: v === "auto" ? null : v })} /></div>` : null}
      <${ColourField} label="Outline" optional value=${h.outline} title="An outline round each letter, from the font's own outline glyphs"
        onCommit=${(v) => set("Outline of " + h.id, { outline: v })} />
      <${ColourField} label="Shadow" optional value=${h.shadow} title="A drop shadow" onCommit=${(v) => set("Shadow of " + h.id, { shadow: v })} />
      <${ColourField} label="Gradient" optional value=${h.gradient} title="The letters run from the color at the top to this at the foot"
        onCommit=${(v) => set("Gradient of " + h.id, { gradient: v })} />
      ${NUMBERS.has(h.part) ? html`<${Scrub} label="Count-up" unit="s" step=${0.05} min=${0} max=${10} value=${h.count_up || 0}
        title="How long the number takes to roll up to a new one; 0: at once" onCommit=${(v) => set("Count-up of " + h.id, { count_up: v || null })} />` : null}
      ${POPS.has(h.part) ? html`<${Check} label="Pop when it goes up" checked=${!!h.pop} onChange=${(v) => set("Pop of " + h.id, { pop: v || null })} />` : null}
    <//>` : null}
    ${DANGER.has(h.part) ? html`<${Group} label="Danger">
      <${ColourField} label="Color" optional value=${h.danger} title="The color it turns, pulsing, when it is low"
        onCommit=${(v) => set("Danger color of " + h.id, { danger: v })} />
      ${h.danger ? html`<${Scrub} label="Low at" unit="%" step=${1} min=${0} max=${100} digits=${2} value=${Math.round((h.low == null ? 0.34 : h.low) * 100)}
        title="It is in danger from this share of full down" onCommit=${(v) => set("Danger of " + h.id, { low: r2(v / 100) })} />` : null}
    <//>` : null}
    ${h.part === "meter" || h.part === "progress" ? html`<${Group} label="Danger zones" extra=${zones.length < 4 ? html`<button type="button" class="btn ghost icon xs"
        onClick=${() => set("Add a danger zone", { zones: [...zones, { from: 0.8, to: 1, colour: "#f0705f" }] })} ...${tip("Add a zone")}><${Icon} name="plus" /></button>` : null}>
      ${zones.length ? zones.map((z, k) => html`<div class="vme-zone">
        <${Scrub} label="From" unit="%" min=${0} max=${100} value=${Math.round(z.from * 100)}
          onCommit=${(v) => set("Danger zone", { zones: zones.map((q, j) => (j === k ? Object.assign({}, q, { from: r2(v / 100) }) : q)) })} />
        <${Scrub} label="To" unit="%" min=${0} max=${100} value=${Math.round(z.to * 100)}
          onCommit=${(v) => set("Danger zone", { zones: zones.map((q, j) => (j === k ? Object.assign({}, q, { to: r2(v / 100) }) : q)) })} />
        <input type="color" class="vme-colour sm" value=${hex6(z.colour, "#f0705f")}
          onChange=${(e) => set("Danger zone color", { zones: zones.map((q, j) => (j === k ? Object.assign({}, q, { colour: e.target.value }) : q)) })} />
        <button type="button" class="btn ghost icon xs" onClick=${() => set("Remove a danger zone", { zones: zones.filter((_, j) => j !== k) })} ...${tip("Remove the zone")}><${Icon} name="trash" /></button>
      </div>`) : html`<div class="vme-hint">A zone is a band of the bar: the fill takes its color and pulses inside it (overheating, too low).</div>`}
    <//>` : null}
    ${h.part === "popup" ? html`<${Group} label="When">
      <div class="vme-checks">${HAPPENINGS.map(([k, l]) => html`<${Check} label=${l} checked=${(h.on || ["kill"]).includes(k)}
        onChange=${(v) => { const on = new Set(h.on || ["kill"]); if (v) on.add(k); else on.delete(k); set("When " + h.id + " pops up", { on: HAPPENINGS.map(([q]) => q).filter((q) => on.has(q)) }); }} />`)}</div>
      <div class="vme-two">
        <${Scrub} label="Rise" unit="px" min=${-1000} max=${1000} value=${h.rise == null ? 60 : h.rise} onCommit=${(v) => set("Rise of " + h.id, { rise: v })} />
        <${Scrub} label="Lasts" unit="s" step=${0.05} min=${0.1} max=${10} value=${h.life_s == null ? 0.8 : h.life_s} onCommit=${(v) => set("How long " + h.id + " lasts", { life_s: v })} />
      </div>
      <div class="vme-hint">The sample on the stage stands at the part's own place; in play the words rise from where it happened.</div>
    <//>` : null}
    <${Group} label="Phases">
      <div class="vme-checks">
        <${Check} label="Every phase" checked=${!h.phases || !h.phases.length} onChange=${(v) => set("Phases of " + h.id, { phases: v ? null : [ed.phase().id] })} />
        ${h.phases && h.phases.length ? doc.phases.map((p) => html`<${Check} label=${p.title || p.id} checked=${h.phases.includes(p.id)}
          onChange=${(v) => { const s = new Set(h.phases); if (v) s.add(p.id); else s.delete(p.id); set("Phases of " + h.id, { phases: doc.phases.map((q) => q.id).filter((q) => s.has(q)) }); }} />`) : null}
      </div>
    <//>
    <div class="vme-btns"><${Button} size="sm" icon="trash" onClick=${() => ed.removeHud()} title="Remove (Delete)">Remove<//></div>
  </div>`;
}

// ---- the look and feel ------------------------------------------------------------------------------------------
function costOf(feel, key) {
  return ((feel && feel.rows) || []).find((r) => r.key === key);
}
function CostChip({ row }) {
  if (!row) return null;
  return html`<span class=${cx("chip sm mono vme-cost", row.share >= 25 ? "warn" : "")}
    ...${tip({ head: row.label, lines: [row.entries + " quads and boxes a frame at its worst", row.share + "% of the machine's " + "budget a frame"] })}>${row.entries} · ${row.share}%</span>`;
}

const PFIELDS = [
  ["count", "Count", "", 1, 0, 128], ["life_s", "Life", "s", 0.05, 0.02, 10], ["size", "Size", "px", 1, 0, 512],
  ["size_end", "End size", "px", 1, 0, 512], ["direction", "Aim", "°", 5, -360, 360], ["spread", "Spread", "°", 5, 0, 360],
  ["gravity", "Gravity", "px/s²", 10, -5000, 5000], ["drag", "Drag", "", 0.05, 0, 1], ["streak", "Streak", "", 0.25, 0, 16],
  ["glow", "Glow", "", 1, 1, 3],
];

function ParticleEditor({ ed, ui, id, presets }) {
  const { Scrub, Group } = ui;
  const list = ((ed.doc.assets || {}).particles || []);
  const p = list.find((q) => q.id === id);
  if (!p) return null;
  const full = Object.assign({}, presets[p.preset || "spark"] || {}, p);
  const set = (label, patch) => ed.editDoc(label, (d) => {
    const q = d.assets.particles.find((x) => x.id === id);
    for (const [k, v] of Object.entries(patch)) { if (v == null) delete q[k]; else q[k] = v; }
  });
  const sp = Array.isArray(full.speed) ? full.speed : [full.speed, full.speed];
  return html`<${Group} label=${"Particle · " + id} extra=${html`<span class="vme-btns tight">
      <button type="button" class="btn ghost icon xs" onClick=${() => ed.previewBurst(id)} ...${tip("Burst it in the middle of the stage, as the engine plays it")}><${Icon} name="play" /></button>
      <button type="button" class="btn ghost icon xs" onClick=${() => ed.editDoc("Remove the particle " + id, (d) => { d.assets.particles = d.assets.particles.filter((x) => x.id !== id); if (!d.assets.particles.length) delete d.assets.particles; })}
        ...${tip("Remove it (bursts and trails that name it go back to their preset)")}><${Icon} name="trash" /></button></span>`}>
    <div class="vme-row"><span class="vme-k">Preset</span>
      <${Select} sm value=${p.preset || "spark"} options=${PRESET_PARTICLES.map((k) => ({ value: k, label: k }))}
        onChange=${(v) => set("Preset of " + id, { preset: v })} /></div>
    <div class="vme-two">
      <${Scrub} label="Speed" unit="px/s" step=${10} min=${0} max=${12000} value=${sp[0]} onCommit=${(v) => set("Speed of " + id, { speed: [v, Math.max(v, sp[1])] })} />
      <${Scrub} label="to" unit="px/s" step=${10} min=${0} max=${12000} value=${sp[1]} onCommit=${(v) => set("Speed of " + id, { speed: [Math.min(v, sp[0]), v] })} />
      ${PFIELDS.map(([k, l, u, st, lo, hi]) => html`<${Scrub} label=${l} unit=${u} step=${st} min=${lo} max=${hi} value=${full[k]}
        onCommit=${(v) => set(l + " of " + id, { [k]: k === "count" || k === "glow" ? Math.round(v) : v })} />`)}
    </div>
    <${ColourField} label="Color" value=${full.colour} onCommit=${(v) => set("Color of " + id, { colour: v })} />
    <${ColourField} label="Fades to" value=${full.colour_end} onCommit=${(v) => set("End color of " + id, { colour_end: v })} />
    <div class="vme-row"><span class="vme-k">Blend</span>
      <${Select} sm value=${full.blend || "normal"} options=${[{ value: "normal", label: "Over" }, { value: "add", label: "Add (light)" }]}
        onChange=${(v) => set("Blend of " + id, { blend: v })} /></div>
  <//>`;
}

export function StylePanel({ ed, ui }) {
  const { Scrub, Group } = ui;
  const [pick, setPick] = useState(null);
  const doc = ed.doc, st = doc.style || {}, feel = ed.feel || {}, info = ed.info || {};
  const presets = info.particle_presets || {};
  const parts = (doc.assets || {}).particles || [];
  const setStyle = (label, patch) => ed.editDoc(label, (d) => {
    d.style = Object.assign({}, d.style || {});
    for (const [k, v] of Object.entries(patch)) { if (v == null) delete d.style[k]; else d.style[k] = v; }
  });
  const bursts = Object.assign({}, DEFAULT_BURSTS, st.bursts || {});
  const burstOpts = [{ value: "none", label: "None" }, ...PRESET_PARTICLES.map((k) => ({ value: k, label: k + " (preset)" })),
    ...parts.map((p) => ({ value: p.id, label: p.id }))];
  const total = feel.total || 0, budget = feel.budget || 1, share = feel.share || 0;
  const meter = share >= 100 ? "err" : share >= 60 ? "warn" : "ok";
  const combo = doc.combo || {};
  const newParticle = (preset) => ed.editDoc("Add a particle", (d) => {
    d.assets = d.assets || {};
    const have = new Set((d.assets.particles || []).map((q) => q.id));
    let id = preset, n = 2;
    while (have.has(id) || PRESET_PARTICLES.includes(id)) id = preset + "_" + n++;
    d.assets.particles = [...(d.assets.particles || []), { id, preset }];
    setPick(id);
  });
  return html`<div class="vme-dock-b">
    <${Group} label="Style presets">
      <div class="vme-presets">${(info.presets || []).map((p) => html`<button type="button" class=${cx("vme-preset", st.preset === p.key && "on")}
          onClick=${() => ed.preset(p.key)} ...${tip({ head: p.label, lines: [p.about, "Sets the whole HUD's looks and every effect; your changes after it are kept"] })}>
        <span class="t">${p.label}</span>${st.preset === p.key ? html`<span class="chip sm">Applied</span>` : null}</button>`)}</div>
    <//>
    <${Group} label="Cost" extra=${html`<span class="mono vme-k">${feel.label || ""}</span>`}>
      <div class=${cx("vme-budget", meter)} ...${tip({ head: "What the HUD and effects draw a frame at their worst", lines: [total + " of the machine's " + budget + " quads and boxes a frame (" + share + "%)", "The things on the stage draw on top of this"] })}>
        <i style=${{ width: Math.min(100, share) + "%" }}></i></div>
      <div class="vme-chip-row"><span class="mono">${total} / ${budget} a frame · ${share}%</span></div>
    <//>
    <${Group} label="Effects">
      ${(info.switches || []).map((s) => {
        const on = st[s.key] == null ? s.on : !!st[s.key];
        const row = costOf(feel, s.key);
        return html`<div class="vme-fx">
          <${Check} label=${s.label} title=${s.about} checked=${on} onChange=${(v) => setStyle((v ? "Turn on " : "Turn off ") + s.label.toLowerCase(), { [s.key]: v })} />
          <${CostChip} row=${row} />
          ${s.key === "shake" && on ? html`<${Scrub} label="Amount" unit="×" step=${0.1} min=${0} max=${4} value=${st.shake_amount == null ? 1 : st.shake_amount}
              onCommit=${(v) => setStyle("Shake amount", { shake_amount: v })} />` : null}
          ${s.key === "hit_stop" && on ? html`<${Scrub} label="Frames" step=${1} min=${0} max=${30} value=${st.hit_stop_frames == null ? 3 : st.hit_stop_frames}
              onCommit=${(v) => setStyle("Hit-stop frames", { hit_stop_frames: Math.round(v) })} />` : null}
          ${s.key === "crt" && on ? html`<${Scrub} label="Strength" unit="%" step=${1} min=${0} max=${100} value=${Math.round((st.crt_strength == null ? 0.35 : st.crt_strength) * 100)}
              onCommit=${(v) => setStyle("CRT strength", { crt_strength: r2(v / 100) })} />` : null}
        </div>`;
      })}
      <div class="vme-fx"><span class="vme-k">Words and bars</span><${CostChip} row=${costOf(feel, "text")} /><${CostChip} row=${costOf(feel, "bars")} /></div>
    <//>
    <${Group} label="Between phases">
      <div class="vme-row"><span class="vme-k">Transition</span>
        <${Select} sm value=${st.transition || "cut"} options=${TRANSITIONS.map(([v, l]) => ({ value: v, label: l }))}
          onChange=${(v) => setStyle("Transition", { transition: v })} /></div>
      ${(st.transition || "cut") !== "cut" ? html`<${Scrub} label="Length" unit="s" step=${0.05} min=${0.05} max=${4} value=${st.transition_s == null ? 0.3 : st.transition_s}
        title="The way out of a phase, and the way into the next" onCommit=${(v) => setStyle("Transition length", { transition_s: v })} />` : null}
    <//>
    <${Group} label="Bursts">
      ${BURSTS.map(([k, l]) => html`<div class="vme-row"><span class="vme-k">${l}</span>
        <${Select} sm value=${bursts[k] || "none"} options=${burstOpts}
          onChange=${(v) => setStyle("Burst on " + l.toLowerCase(), { bursts: Object.assign({}, st.bursts || {}, { [k]: v }) })} /></div>`)}
    <//>
    <${Group} label="Combo and multiplier">
      <div class="vme-two">
        <${Scrub} label="Within" unit="s" step=${0.1} min=${0.1} max=${100} value=${combo.window_s == null ? 1.5 : combo.window_s}
          title="Kills this close together chain a combo" onCommit=${(v) => ed.editDoc("Combo window", (d) => { d.combo = Object.assign({}, d.combo || {}, { window_s: v }); })} />
        <${Scrub} label="Every" step=${1} min=${0} max=${1000} value=${combo.every || 0}
          title="Every this many kills in a combo adds 1 to the multiplier; 0: no multiplier" onCommit=${(v) => ed.editDoc("Combo steps", (d) => { d.combo = Object.assign({}, d.combo || {}, { every: Math.round(v) }); })} />
        <${Scrub} label="Up to" unit="×" step=${1} min=${1} max=${100} value=${combo.max || 5}
          onCommit=${(v) => ed.editDoc("Most multiplier", (d) => { d.combo = Object.assign({}, d.combo || {}, { max: Math.round(v) }); })} />
      </div>
    <//>
    <${Group} label="Particles" extra=${html`<${Select} sm value="" options=${[{ value: "", label: "New from…" }, ...PRESET_PARTICLES.map((k) => ({ value: k, label: k }))]}
        onChange=${(v) => v && newParticle(v)} />`}>
      <div class="vme-btns">
        ${PRESET_PARTICLES.map((k) => html`<${Button} size="sm" kind="ghost" icon="play" title=${"Burst the " + k + " preset in the middle of the stage"} onClick=${() => ed.previewBurst(k)}>${k}<//>`)}
      </div>
      ${parts.length ? html`<div class="vme-btns">${parts.map((p) => html`<button type="button" class=${cx("chip sm vme-pchip", (pick || parts[0].id) === p.id && "on")}
          onClick=${() => setPick(p.id)}>${p.id}</button>`)}</div>` : html`<div class="vme-hint">The bursts use the presets; make one of your own to change its count, speed, colors or glow.</div>`}
    <//>
    ${parts.length ? html`<${ParticleEditor} ed=${ed} ui=${ui} id=${pick && parts.some((p) => p.id === pick) ? pick : parts[0].id} presets=${presets} />` : null}
  </div>`;
}
