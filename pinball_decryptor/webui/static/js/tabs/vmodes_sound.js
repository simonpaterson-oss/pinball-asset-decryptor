// Video modes tab, the Sound card (PAD-1667): a video mode's music and sounds. Each sound shows its waveform (its
// loop point and, for music, its beat grid drawn on it), its role, volume, loop and fade, and what plays it; music is
// picked per phase and effects and callouts are tied to events; the top says how they go on the machine picked and
// what is left of what its mode sound route carries. The rules every place plays them by: core/video_mode/sound.py.
// Python half: webui/tabs/vmodes.py (_paint_sounds and the sound RPCs). <Wave> is the timeline's sound track too.

import { html, useEffect, useRef, useState, Card, Button, Field, Select, Seg, Chip, Note, Icon, Check, tip, call, cx,
         mediaUrl } from "../core/ui.js";

const ON_LABEL = {
  fire: "Fire", hit: "Hit a weak point", kill: "Kill", pickup: "Pickup", hurt: "Hurt", prompt_good: "Prompt: good",
  prompt_perfect: "Prompt: perfect", prompt_miss: "Prompt: missed", phase_start: "Phase starts", phase_won: "Phase won",
  phase_lost: "Phase lost", won: "Won", lost: "Lost",
};
const ROLE_ICON = { music: "music", effect: "star", callout: "text" };
const T = {
  add: "Bring a sound file in: it is copied into the mode's sound folder. A long one comes in as music.",
  role: "Music plays under a phase and loops; an effect plays on an event; a callout is speech: it ducks the music while it plays",
  volume: "How loud this sound plays, 0 to 100%",
  loop: "Music: start again at the loop point when it reaches the end",
  loopFrom: "Where the music goes back to when it loops, in seconds (drag the line on the waveform)",
  fade: "When this music takes over from another, the one before fades out over this many seconds, then this one fades in over the same (the machine plays one music bed at a time). It also fades out over this when it stops.",
  tempo: "Beats a minute: the beat grid a rhythm phase on this music plays to, drawn on the waveform",
  find: "Listen for the beat in the file and set the tempo and the first beat from it",
  first: "Where the first beat falls in the file, in seconds",
  bar: "Beats a bar: every bar's first beat is drawn stronger",
  preview: "Play this sound here",
  stop: "Stop",
  remove: "Take this sound out of the mode (only when nothing plays it)",
  duck: "The music goes down (about 9 dB) while this sound plays, as the machine ducks it",
  placeholder: "No file yet: a placeholder sound made by the app plays here and in the player, as pictures without a file show as placeholders",
  machine: "Its name on the machine, and its priority on the voice bus (3: a sound that repeats, skipped while it still sounds; 4: a callout, which starts over)",
  sounds: "Effects and callouts the cues play, against how many calls one mode carries on this machine",
  beds: "Music beds the phases play (the mode's own and its further beds), against how many one mode carries",
  oneVoice: "On the machine a mode's effects and callouts share one voice: a new one fades out the one still sounding (the newest event speaks), and an effect that still sounds is skipped. The player plays them the same way.",
};

const fmtS = (v) => (v == null || v === "" ? "" : String(Math.round(Number(v) * 1000) / 1000));

// ---- the waveform: peaks, a loop point, a beat grid, a playhead ----------------------------------------------------
export function Wave({ peaks, seconds, loopStart, grid, fade, at, height = 54, onLoopStart, title }) {
  const ref = useRef(null);
  const drag = useRef(false);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1, w = c.clientWidth || 300, h = height;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
    const g = c.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const css = getComputedStyle(c);
    const ink = css.getPropertyValue("--ink-3").trim() || "#888", acc = css.getPropertyValue("--accent").trim() || "#4af";
    const line = css.getPropertyValue("--line-2").trim() || "#444", warn = css.getPropertyValue("--warn").trim() || "#fa0";
    const x = (t) => (seconds > 0 ? (t / seconds) * w : 0);
    if (fade > 0 && seconds > 0) {                      // the fade in, shaded
      g.fillStyle = line; g.globalAlpha = 0.35; g.fillRect(0, 0, x(Math.min(fade, seconds)), h); g.globalAlpha = 1;
    }
    if (grid && grid.bpm > 0 && seconds > 0) {          // the beat grid: bars strong, beats faint
      const beat = 60 / grid.bpm;
      for (let k = 0, t = grid.offset_s; t <= seconds && k < 4000; k++, t += beat) {
        const bar = k % (grid.per_bar || 4) === 0;
        g.fillStyle = bar ? acc : line; g.globalAlpha = bar ? 0.55 : 0.6;
        g.fillRect(Math.round(x(t)), 0, 1, h);
      }
      g.globalAlpha = 1;
    }
    const n = (peaks || []).length;
    if (n) {
      g.fillStyle = ink;
      const mid = h / 2, bw = w / n;
      for (let i = 0; i < n; i++) {
        const [lo, hi] = peaks[i];
        const y0 = mid - Math.max(0.5, hi * mid * 0.92), y1 = mid - Math.min(-0.5, lo * mid * 0.92);
        g.fillRect(i * bw, y0, Math.max(1, bw - 0.25), y1 - y0);
      }
    } else {
      g.fillStyle = line; g.fillRect(0, h / 2, w, 1);
    }
    if (loopStart != null && seconds > 0) {             // the loop point
      g.fillStyle = warn; g.fillRect(Math.round(x(loopStart)) - 1, 0, 2, h);
      g.beginPath(); g.moveTo(x(loopStart) - 5, 0); g.lineTo(x(loopStart) + 5, 0); g.lineTo(x(loopStart), 6); g.fill();
    }
    if (at != null && seconds > 0) { g.fillStyle = acc; g.fillRect(Math.round(x(at)), 0, 2, h); }
  });
  const toS = (e) => {
    const r = ref.current.getBoundingClientRect();
    return Math.max(0, Math.min(seconds, ((e.clientX - r.left) / r.width) * seconds));
  };
  const down = (e) => { if (!onLoopStart || !(seconds > 0)) return; drag.current = true; e.currentTarget.setPointerCapture(e.pointerId); };
  const up = (e) => { if (!drag.current) return; drag.current = false; onLoopStart(Math.round(toS(e) * 100) / 100); };
  return html`<canvas ref=${ref} class=${cx("vm-wave", onLoopStart && "drag")} style=${{ height: height + "px" }}
    onPointerDown=${down} onPointerUp=${up} ...${tip(title)} />`;
}

function CountMeter({ label, used, max, title }) {
  const pct = max ? (100 * used) / max : 0;
  const kind = max == null ? "ok" : pct > 100 ? "err" : pct > 80 ? "warn" : "ok";
  return html`<div class="vm-meter" ...${tip(title)}>
    <div class="row small"><span class="vm-lbl">${label}</span><span class="sp"></span>
      <span class=${cx("mono", kind)}>${used}</span>${max != null ? html`<span class="mono muted"> of ${max}</span>` : null}</div>
    <div class="vm-bar"><span class=${kind} style=${{ width: (max ? Math.min(100, pct) : 0).toFixed(1) + "%" }}></span></div>
  </div>`;
}

// one preview at a time, through an <audio> element (the player has the machine's rules; this is the file itself)
let previewing = null;
function usePreview(row) {
  const [at, setAt] = useState(null);
  const el = useRef(null);
  useEffect(() => () => { if (el.current) el.current.pause(); }, []);
  const stop = () => { if (el.current) { el.current.pause(); el.current = null; } setAt(null); if (previewing && previewing.row === row.id) previewing = null; };
  const play = () => {
    if (previewing) previewing.stop();
    const a = new Audio(mediaUrl(row.path) + "&v=" + (row.v || 0));
    a.volume = Math.max(0, Math.min(1, row.volume));
    a.loop = !!row.loop;
    if (row.loop && row.loop_start_s) a.addEventListener("timeupdate", () => { if (a.duration && a.currentTime >= a.duration - 0.05) a.currentTime = row.loop_start_s; });
    el.current = a; previewing = { row: row.id, stop };
    let raf = 0;
    const tick = () => { if (el.current !== a) return; setAt(a.currentTime); raf = requestAnimationFrame(tick); };
    a.addEventListener("ended", () => { cancelAnimationFrame(raf); stop(); });
    a.play().then(() => { raf = requestAnimationFrame(tick); }).catch(() => stop());
  };
  return { at, playing: at != null, play, stop };
}

function SoundRow({ r, peaks, busy, disabled }) {
  const pv = usePreview(r);
  const set = (ch) => call("vmodes.set_sound", r.id, ch);
  const pk = peaks || {};
  const secs = pk.seconds || 0;
  const music = r.role === "music";
  const uses = [...r.phases.map((p) => "plays in " + p), ...r.cues.map((c) => "on " + (ON_LABEL[c] || c).toLowerCase())];
  return html`<div class=${cx("vm-snd", music && "music")}>
    <div class="vm-snd-head row">
      <span class="vm-snd-ico"><${Icon} name=${ROLE_ICON[r.role] || "audio"} /></span>
      <${Field} sm mono width="150px" value=${r.id} disabled=${disabled} title="Its name in the mode"
        onCommit=${(v) => v && v !== r.id && set({ id: v })} />
      ${r.missing ? html`<${Chip} sm kind="warn" title=${T.placeholder}>placeholder<//>`
        : html`<span class="small muted mono ellip" ...${tip(r.file)}>${r.file}</span>`}
      <span class="sp"></span>
      <${Seg} value=${r.role} disabled=${disabled} onChange=${(v) => set({ role: v })}
        options=${[{ value: "music", label: "Music", title: T.role }, { value: "effect", label: "Effect", title: T.role },
                   { value: "callout", label: "Callout", title: T.role }]} />
      <${Field} sm type="number" width="84px" min="0" max="100" step="5" suffix="%" title=${T.volume} disabled=${disabled}
        value=${String(Math.round(r.volume * 100))} onCommit=${(v) => set({ volume: Number(v) / 100 })} />
      <${Button} kind="ghost" icon=${pv.playing ? "stop" : "play"} title=${pv.playing ? T.stop : T.preview}
        disabled=${!r.path} onClick=${() => (pv.playing ? pv.stop() : pv.play())} />
      <${Button} kind="ghost" icon="trash" title=${T.remove} disabled=${disabled || uses.length > 0}
        onClick=${() => call("vmodes.remove_sound", r.id)} />
    </div>
    <${Wave} peaks=${pk.peaks} seconds=${secs} loopStart=${music && r.loop ? r.loop_start_s || 0 : null}
      grid=${music ? r.grid : null} fade=${music ? r.fade_s : 0} at=${pv.at}
      onLoopStart=${music && r.loop && !disabled ? (v) => set({ loop_start_s: v }) : null}
      title=${music ? (r.loop ? "Drag to move the loop point" : null) : null} />
    ${music ? html`<div class="vm-snd-opts row">
      <${Check} checked=${r.loop} disabled=${disabled} label="Loop" title=${T.loop} onChange=${(v) => set({ loop: v })} />
      <label class="vm-lbl" ...${tip(T.loopFrom)}>From</label>
      <${Field} sm type="number" width="80px" min="0" step="0.1" suffix="s" disabled=${disabled || !r.loop}
        value=${fmtS(r.loop_start_s || 0)} onCommit=${(v) => set({ loop_start_s: v })} />
      <label class="vm-lbl" ...${tip(T.fade)}>Fade</label>
      <${Field} sm type="number" width="80px" min="0" max="10" step="0.1" suffix="s" disabled=${disabled}
        value=${fmtS(r.fade_s)} onCommit=${(v) => set({ fade_s: v })} />
      <span class="vm-snd-gap"></span>
      <label class="vm-lbl" ...${tip(T.tempo)}>Tempo</label>
      <${Field} sm type="number" width="118px" min="30" max="300" step="0.5" suffix="bpm" disabled=${disabled}
        value=${fmtS(r.tempo_bpm)} placeholder="none" onCommit=${(v) => set({ tempo_bpm: v === "" ? null : v })} />
      <label class="vm-lbl" ...${tip(T.first)}>First beat</label>
      <${Field} sm type="number" width="94px" min="0" step="0.01" suffix="s" disabled=${disabled || !r.tempo_bpm}
        value=${fmtS(r.beat_offset_s || 0)} onCommit=${(v) => set({ beat_offset_s: v })} />
      <label class="vm-lbl" ...${tip(T.bar)}>A bar</label>
      <${Field} sm type="number" width="60px" min="1" max="16" step="1" disabled=${disabled || !r.tempo_bpm}
        value=${String(r.beats_per_bar || 4)} onCommit=${(v) => set({ beats_per_bar: v })} />
      <${Button} size="sm" icon="search" busy=${busy} disabled=${disabled || busy || !r.path} title=${T.find}
        onClick=${() => call("vmodes.find_beat", r.id)}>Find the beat<//>
    </div>` : null}
    <div class="vm-snd-foot row small">
      <span class="muted">${uses.length ? uses.join(" · ") : "Nothing plays it yet"}</span>
      ${secs ? html`<span class="mono muted">${secs.toFixed(2)} s</span>` : null}
      <span class="sp"></span>
      ${r.duck ? html`<${Chip} sm title=${T.duck}>ducks the music<//>` : null}
      ${r.machine ? html`<${Chip} sm title=${T.machine}><span class="mono">${r.machine}</span>${r.priority ? " · priority " + r.priority : ""}<//>` : null}
    </div>
  </div>`;
}

function Cues({ s, disabled }) {
  const cues = s.cues || [];
  const others = (s.sounds || []).filter((r) => r.role !== "music");
  const put = (list) => call("vmodes.set_cues", list);
  const ons = (s.cue_on || []).map((o) => ({ value: o, label: ON_LABEL[o] || o }));
  const snds = others.map((r) => ({ value: r.id, label: r.id + (r.role === "callout" ? " (callout)" : "") }));
  const free = (s.cue_on || []).find((o) => !cues.some((c) => c.on === o)) || "fire";
  return html`<div class="vm-cues">
    <div class="row"><span class="vm-lbl">Sounds on events</span><span class="sp"></span>
      <${Button} size="sm" icon="plus" disabled=${disabled || !others.length}
        title=${others.length ? "Play a sound on an event" : "Bring an effect or callout in first"}
        onClick=${() => put([...cues, { on: free, sound: others[0].id, duck_music: false }])}>Add<//></div>
    ${cues.length ? html`<table class="vm-cost vm-cue-t"><thead><tr><th>When</th><th>Sound</th><th>Duck the music</th><th></th></tr></thead>
      <tbody>${cues.map((c, i) => {
        const ch = (k, v) => put(cues.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
        const callout = (others.find((r) => r.id === c.sound) || {}).role === "callout";
        return html`<tr>
          <td><${Select} sm value=${c.on} options=${ons} disabled=${disabled} onChange=${(v) => ch("on", v)} /></td>
          <td><${Select} sm value=${c.sound} options=${snds} disabled=${disabled} onChange=${(v) => ch("sound", v)} /></td>
          <td><${Check} checked=${c.duck_music || callout} disabled=${disabled || callout}
            title=${callout ? "A callout always ducks the music" : T.duck} onChange=${(v) => ch("duck_music", v)} /></td>
          <td class="n"><${Button} kind="ghost" size="sm" icon="x" title="Take this cue off" disabled=${disabled}
            onClick=${() => put(cues.filter((_, j) => j !== i))} /></td></tr>`;
      })}</tbody></table>`
      : html`<div class="small muted vm-none">No sounds on events yet.</div>`}
  </div>`;
}

function PhaseMusic({ s, disabled }) {
  const music = (s.sounds || []).filter((r) => r.role === "music");
  const opts = [{ value: "", label: "No music" }, ...music.map((r) => ({ value: r.id, label: r.id }))];
  return html`<div class="vm-cues">
    <div class="row"><span class="vm-lbl">Music for each phase</span></div>
    <table class="vm-cost"><thead><tr><th>Phase</th><th>Kind</th><th>Music</th></tr></thead>
      <tbody>${(s.music_phases || []).map((p) => html`<tr>
        <td class="ellip">${p.title}</td><td class="muted">${p.kind}</td>
        <td><${Select} sm value=${p.music} disabled=${disabled}
          options=${p.kind === "rhythm" ? opts.slice(1) : opts} onChange=${(v) => call("vmodes.set_phase_music", p.id, v)}
          title=${p.kind === "rhythm" ? "A rhythm phase plays to its music and reads its beat grid" : "The music under this phase. The next phase's music takes over with a fade; the same music plays on."} /></td>
      </tr>`)}</tbody></table>
  </div>`;
}

export function SoundCard({ s }) {
  const rows = s.sounds || [];
  const plan = s.sound_plan;
  const busy = new Set(s.beat_busy || []);
  const disabled = !!s.running;
  const c = plan ? plan.count : null;
  return html`<${Card} title="Sound" sub="Music for each phase, sounds on events, and what the machine carries" cls="vm-sound"
    extra=${html`<${Button} kind="primary" icon="plus" disabled=${disabled} title=${T.add} onClick=${() => call("vmodes.add_sound")}>Bring a sound in…<//>`}>
    ${plan ? html`<div class="vm-meters">
      <${CountMeter} label="Sounds" used=${c.calls} max=${c.calls_max} title=${T.sounds} />
      <${CountMeter} label="Music beds" used=${(plan.music ? 1 : 0) + c.beds} max=${c.beds_max == null ? null : c.beds_max + 1} title=${T.beds} />
    </div>
    <div class="row small" style="gap:6px"><span class="muted" ...${tip(T.oneVoice)}>${plan.words}</span></div>
    ${(plan.problems || []).length ? html`<${Note} kind="err"><div class="stack" style="gap:4px">${plan.problems.map((p) => html`<div>${p}</div>`)}</div><//>` : null}` : null}
    ${rows.length ? html`<div class="vm-snds">${rows.map((r) => html`<${SoundRow} key=${r.id} r=${r} peaks=${(s.peaks || {})[r.peaks_key]}
      busy=${busy.has(r.id)} disabled=${disabled} />`)}</div>`
      : html`<div class="small muted vm-none">No sounds yet. Bring in music for the phases and effects for the events.</div>`}
    ${rows.length ? html`<div class="vm-snd-cols"><${PhaseMusic} s=${s} disabled=${disabled} /><${Cues} s=${s} disabled=${disabled} /></div>` : null}
  <//>`;
}
