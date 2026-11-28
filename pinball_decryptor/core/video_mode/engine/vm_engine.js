// vm_engine.js - the video mode engine in WebAssembly (PAD-1657), for the app's player
// (PAD-1659) and for tests under Node. The same C as the machine runs.
//
//   const vm = await VideoModeEngine.create(wasmBytes);
//   vm.load(packBytes); vm.start(seed, level);
//   while (vm.step(buttons)) { vm.drawWords(); vm.events(); vm.cues(); }
//
// buttons: 1 left, 2 right, 4 action, 8 the clip the engine asked for has ended.
export const IN = { LEFT: 1, RIGHT: 2, ACTION: 4, CLIP_DONE: 8 };
const NONE = -0x7fffffff - 1;     // vm_engine.h NONE: a place's depth left to its thing

export class VideoModeEngine {
  static async create(wasmBytes) {
    const { instance } = await WebAssembly.instantiate(wasmBytes, {});
    return new VideoModeEngine(instance.exports);
  }
  constructor(x) { this.x = x; }
  mem() { return this.x.memory.buffer; }
  load(bytes) {
    if (bytes.length > this.x.vmw_pack_max()) return 3;
    new Uint8Array(this.mem(), this.x.vmw_pack_buf(), bytes.length).set(bytes);
    return this.x.vmw_load(bytes.length);
  }
  errAt() { return this.x.vmw_err_at(); }
  start(seed, level = 0) { this.x.vmw_start(seed >>> 0, level | 0); }
  // PAD-1659: start at another card (the player's "Start here"); false when there is no such card
  startAt(seed, level, card) { return this.x.vmw_start_at(seed >>> 0, level | 0, card | 0) !== 0; }
  // the sound calibration (PAD-1663): ms this place's sound is heard after the step that cued it. Kept across start.
  audioOffset(ms) { this.x.vmw_audio_offset(ms | 0); }
  // ms of the phase's music played so far by the engine's clock, and the phase's kind (7: rhythm)
  songMs() { return this.x.vmw_song_ms(); }
  songSteps() { return this.x.vmw_song_steps(); }
  kind() { return this.x.vmw_kind(); }
  card() { return this.x.vmw_card(); }
  phase() { return this.x.vmw_phase(); }
  phaseT() { return this.x.vmw_phase_t(); }
  phaseLen() { return this.x.vmw_phase_len(); }
  stepNo() { return this.x.vmw_step_no() >>> 0; }
  dropped() { return this.x.vmw_dropped() >>> 0; }
  health() { return this.x.vmw_health(); }
  things() { return this.x.vmw_things(); }
  // every live thing's hit box: [team, shape (0 box, 1 circle), x, y, w, h] * n, stage px 16.16 (a copy)
  hitBoxes() {
    const n = this.x.vmw_hits();
    return new Int32Array(this.mem(), this.x.vmw_hits_buf(), n * 6).slice();
  }
  step(input) { return this.x.vmw_step(input >>> 0) !== 0; }
  // the draw list's canonical words (header 8, quad 12, box 6): a copy
  drawWords() {
    const n = this.x.vmw_words();
    return new Int32Array(this.mem(), this.x.vmw_words_buf(), n).slice();
  }
  events() {
    const n = this.x.vmw_nevents(), v = new Int32Array(this.mem(), this.x.vmw_events(), n * 4), out = [];
    for (let i = 0; i < n; i++) out.push({ type: v[i * 4], a: v[i * 4 + 1], b: v[i * 4 + 2], c: v[i * 4 + 3] });
    return out;
  }
  cues() {
    const n = this.x.vmw_ncues(), v = new Int32Array(this.mem(), this.x.vmw_cues(), n * 4), out = [];
    for (let i = 0; i < n; i++) out.push({ sound: v[i * 4], op: v[i * 4 + 1], duck: v[i * 4 + 2], fade: v[i * 4 + 3] });
    return out;
  }
  hash() {
    return (this.x.vmw_hash_hi() >>> 0).toString(16).padStart(8, "0") + (this.x.vmw_hash_lo() >>> 0).toString(16).padStart(8, "0");
  }
  state() { return this.x.vmw_state(); }
  outcome() { return this.x.vmw_outcome(); }
  score() { return this.x.vmw_score(); }
  check() { return this.x.vmw_check(); }
  botInit(clipSteps) { this.x.vmw_bot_init(clipSteps); }
  botInput() { return this.x.vmw_bot_input() >>> 0; }
  // PAD-1661, the editor: a phase's still (its first step, past the opening transition; flags 1 = the title card
  // too), a place rewritten in the loaded tables (i over every phase in order; x, y, turn in px / degrees), and
  // each placed thing of the still as drawn: {alive, hidden, x, y, turn, x0, y0, x1, y1} (stage px)
  editStill(phase, flags = 0) { return this.x.vmw_edit_still(phase | 0, flags | 0) !== 0; }
  placeCount() { return this.x.vmw_place_count(); }
  placeSet(i, x, y, scale, turn, depth, hidden) {
    const f = (v) => Math.round(v * 65536) | 0;
    return this.x.vmw_place_set(i | 0, f(x), f(y), f(scale), f(turn), depth == null ? NONE : depth | 0, hidden ? 1 : 0) !== 0;
  }
  placeBoxes() {
    const n = this.x.vmw_place_boxes(), v = new Int32Array(this.mem(), this.x.vmw_place_boxes_buf(), n * 9), out = [];
    for (let i = 0; i < n; i++) {
      const o = i * 9;
      out.push(v[o] ? { alive: true, hidden: !!v[o + 1], x: v[o + 2] / 65536, y: v[o + 3] / 65536, turn: v[o + 4] / 65536,
        x0: v[o + 5] / 65536, y0: v[o + 6] / 65536, x1: v[o + 7] / 65536, y1: v[o + 8] / 65536 } : { alive: false });
    }
    return out;
  }
}
