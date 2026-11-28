// vm_run.mjs - vmrun's twin on WebAssembly (PAD-1657): same arguments, same lines out,
// so a test can hold the two side by side.
//   node vm_run.mjs WASM PACK [--inputs FILE | --bot] [--record FILE] [--seed N] [--level N] [--max N] [--dump N] [--quiet] [--clip N] [--card N]
//   node vm_run.mjs WASM PACK --seek PHASE --at S1,S2,... [--endless]   (PAD-1664: the editor's scrub, through its snapshots)
import { readFileSync, writeFileSync } from "node:fs";
import { VideoModeEngine } from "./vm_engine.js";

const argv = process.argv.slice(2);
const opt = { seed: 1, level: 0, max: 200000, dump: 0, clip: 120, bot: false, quiet: false };
const pos = [];
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === "--bot") opt.bot = true;
  else if (a === "--quiet") opt.quiet = true;
  else if (a === "--endless") opt.endless = true;
  else if (a === "--time") opt.time = true;
  else if (["--inputs", "--record", "--seed", "--level", "--max", "--dump", "--clip", "--card", "--seek", "--at"].includes(a)) opt[a.slice(2)] = argv[++i];
  else pos.push(a);
}
const vm = await VideoModeEngine.create(readFileSync(pos[0]));
const err = vm.load(readFileSync(pos[1]));
if (err) { console.log(`LOADERR ${err} at=${vm.errAt()}`); process.exit(3); }
if (opt.seek !== undefined) {
  const lines = [], ms = [];
  for (const s of String(opt.at || "0").split(",")) {
    const t0 = performance.now();
    if (vm.seek(Number(opt.seek), Number(s), opt.endless ? 2 : 0) < 0) { console.log("LOADERR 5 at=phase"); process.exit(3); }
    const w = vm.drawWords();
    ms.push(performance.now() - t0);
    if (!opt.time) lines.push(`D ${Number(s)} ` + Array.from(w, (v) => (v >>> 0).toString(16)).join(" "));
  }
  // --time: how long each seek took with its draw list read, first (the snapshots made) and the rest
  if (opt.time) lines.push(`SEEKTIME n=${ms.length} first_ms=${ms[0].toFixed(2)} rest_avg_ms=${(ms.slice(1).reduce((a, b) => a + b, 0) / Math.max(1, ms.length - 1)).toFixed(3)} rest_max_ms=${Math.max(0, ...ms.slice(1)).toFixed(3)}`);
  process.stdout.write(lines.join("\n") + "\n");
  process.exit(0);
}
if (opt.card !== undefined) {
  if (!vm.startAt(Number(opt.seed), Number(opt.level), Number(opt.card))) { console.log("LOADERR 5 at=card"); process.exit(3); }
} else vm.start(Number(opt.seed), Number(opt.level));
vm.botInit(Number(opt.clip));
const inputs = opt.inputs ? readFileSync(opt.inputs) : new Uint8Array(0);
const rec = [];
let out = [];
let step = 0, running = true;
const max = Number(opt.max), dump = Number(opt.dump);
while (running && step < max) {
  const input = opt.bot ? vm.botInput() : step < inputs.length ? inputs[step] : 0;
  rec.push(input);
  running = vm.step(input);
  if (!opt.quiet) {
    for (const e of vm.events()) out.push(`E ${step} ${e.type} ${e.a} ${e.b} ${e.c}`);
    for (const c of vm.cues()) out.push(`C ${step} ${c.sound} ${c.op} ${c.duck}`);
  }
  if (dump && (step % dump === 0 || !running)) {
    const w = vm.drawWords();
    out.push(`D ${step} ` + Array.from(w, (v) => (v >>> 0).toString(16)).join(" "));
  }
  step++;
  if (out.length > 4096) { process.stdout.write(out.join("\n") + "\n"); out = []; }
}
if (opt.record) writeFileSync(opt.record, Uint8Array.from(rec));
out.push(`END steps=${step} hash=${vm.hash()} outcome=${vm.outcome()} score=${vm.score()}`);
process.stdout.write(out.join("\n") + "\n");
