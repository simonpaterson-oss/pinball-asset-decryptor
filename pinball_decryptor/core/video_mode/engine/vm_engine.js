// vm_engine.js - the video mode engine in WebAssembly (PAD-1657), for the app's player
// (PAD-1659) and for tests under Node. The same C as the machine runs.
//
//   const vm = await VideoModeEngine.create(wasmBytes);
//   vm.load(packBytes); vm.start(seed, level);
//   while (vm.step(buttons)) { vm.drawWords(); vm.events(); vm.cues(); }
//
// buttons: 1 left, 2 right, 4 action, 8 the clip the engine asked for has ended.
export const IN = { LEFT: 1, RIGHT: 2, ACTION: 4, CLIP_DONE: 8 };

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
    const n = this.x.vmw_ncues(), v = new Int32Array(this.mem(), this.x.vmw_cues(), n * 3), out = [];
    for (let i = 0; i < n; i++) out.push({ sound: v[i * 3], op: v[i * 3 + 1], duck: v[i * 3 + 2] });
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
}
