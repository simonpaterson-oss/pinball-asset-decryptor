/* vm_wasm.c - the WebAssembly face of the engine (PAD-1657): one engine, a buffer the
 * host copies the pack into, and the step's output as plain memory JavaScript reads
 * (vm_engine.js). Built --target=wasm32-freestanding with no libc, so the calls a
 * compiler emits by itself are here. */
#include "vm_engine.h"
#include "vm_bot.h"

#define EXPORT(name) __attribute__((export_name(#name)))

void *memset(void *d, int c, unsigned long n) { unsigned char *p = d; while (n--) *p++ = (unsigned char)c; return d; }
void *memcpy(void *d, const void *s, unsigned long n) { unsigned char *p = d; const unsigned char *q = s; while (n--) *p++ = *q++; return d; }
void *memmove(void *d, const void *s, unsigned long n)
{
    unsigned char *p = d; const unsigned char *q = s;
    if (p < q) while (n--) *p++ = *q++;
    else { p += n; q += n; while (n--) *--p = *--q; }
    return d;
}

#define PACK_MAX (1024 * 1024)
static vm_engine E;
static vm_bot B;
static uint8_t pack[PACK_MAX];
static int32_t words[VM_MAX_ENTRIES * 12 + 16];

EXPORT(vmw_pack_buf) uint8_t *vmw_pack_buf(void) { return pack; }
EXPORT(vmw_pack_max) int32_t vmw_pack_max(void) { return PACK_MAX; }
EXPORT(vmw_load) int32_t vmw_load(int32_t len) { return len < 0 || len > PACK_MAX ? VM_ERR_SHORT : vm_load(&E, pack, (uint32_t)len); }
EXPORT(vmw_err_at) int32_t vmw_err_at(void) { return E.err_at; }
EXPORT(vmw_start) void vmw_start(uint32_t seed, int32_t level) { vm_start(&E, seed, level); }
EXPORT(vmw_step) int32_t vmw_step(uint32_t input) { return vm_step(&E, input); }
EXPORT(vmw_words) int32_t vmw_words(void) { return (int32_t)vm_list_words(&E, words, sizeof(words) / sizeof(words[0])); }
EXPORT(vmw_words_buf) int32_t *vmw_words_buf(void) { return words; }
EXPORT(vmw_events) vm_event *vmw_events(void) { return E.events; }
EXPORT(vmw_nevents) int32_t vmw_nevents(void) { return E.nevents; }
EXPORT(vmw_cues) vm_sndcue *vmw_cues(void) { return E.cues; }
EXPORT(vmw_ncues) int32_t vmw_ncues(void) { return E.ncues; }
EXPORT(vmw_hash_lo) uint32_t vmw_hash_lo(void) { return (uint32_t)E.hash; }
EXPORT(vmw_hash_hi) uint32_t vmw_hash_hi(void) { return (uint32_t)(E.hash >> 32); }
EXPORT(vmw_state) int32_t vmw_state(void) { return E.state; }
EXPORT(vmw_outcome) int32_t vmw_outcome(void) { return E.outcome; }
EXPORT(vmw_score) int32_t vmw_score(void) { return E.score; }
EXPORT(vmw_check) int32_t vmw_check(void) { return vm_check(&E); }
/* PAD-1659, the app's player: start at any card ("Start here"), and what it shows beside the stage. None of
 * this is in the machine's object; the engine itself is untouched. */
EXPORT(vmw_start_at) int32_t vmw_start_at(uint32_t seed, int32_t level, int32_t card)
{
    int32_t keep = E.doc.start_card;
    if (!E.loaded || card < 0 || card >= E.doc.ncard) return 0;
    E.doc.start_card = card;
    vm_start(&E, seed, level);
    E.doc.start_card = keep;
    return 1;
}
EXPORT(vmw_card) int32_t vmw_card(void) { return E.card; }
EXPORT(vmw_phase) int32_t vmw_phase(void) { return E.phase; }
EXPORT(vmw_phase_t) int32_t vmw_phase_t(void) { return E.t; }
EXPORT(vmw_phase_len) int32_t vmw_phase_len(void) { return E.doc.nphase ? E.doc.phase[E.phase].length : 0; }
EXPORT(vmw_step_no) uint32_t vmw_step_no(void) { return E.step_no; }
EXPORT(vmw_dropped) uint32_t vmw_dropped(void) { return E.list.dropped; }
EXPORT(vmw_health) int32_t vmw_health(void) { return E.health; }
EXPORT(vmw_things) int32_t vmw_things(void)
{
    int32_t i, n = 0;
    for (i = 0; i < VM_MAX_THINGS; i++) n += E.th[i].alive != 0;
    return n;
}
/* every live thing's hit box as the collisions see it (vm_engine.c hitbox()): team, shape (0 box, 1 circle),
 * x, y, w, h in stage px 16.16 (a circle: x, y its centre, w its radius) */
static int32_t hits[VM_MAX_THINGS * 6];
EXPORT(vmw_hits_buf) int32_t *vmw_hits_buf(void) { return hits; }
EXPORT(vmw_hits) int32_t vmw_hits(void)
{
    int32_t i, n = 0;
    for (i = 0; i < VM_MAX_THINGS; i++) {
        const vm_thing *t = &E.th[i];
        const vm_kind *k;
        const vm_picture *p;
        vm_hitbox h;
        if (!t->alive || t->hidden) continue;
        k = &E.doc.kind[t->kind];
        p = &E.doc.pic[k->picture];
        h = k->hit.shape >= 0 ? k->hit : p->hit;
        if (h.shape < 0) {
            int32_t w = p->w * p->texel, hh = p->h * p->texel;
            h.shape = 0; h.x = -vm_fxmul(p->ax, w); h.y = -vm_fxmul(p->ay, hh); h.w = w; h.h = hh;
        }
        hits[n * 6] = t->team; hits[n * 6 + 1] = h.shape;
        hits[n * 6 + 2] = t->x + vm_fxmul(h.x, t->scale); hits[n * 6 + 3] = t->y + vm_fxmul(h.y, t->scale);
        hits[n * 6 + 4] = vm_fxmul(h.w, t->scale); hits[n * 6 + 5] = vm_fxmul(h.h, t->scale);
        n++;
    }
    return n;
}
EXPORT(vmw_bot_init) void vmw_bot_init(int32_t clip_steps) { vm_bot_init(&B, clip_steps); }
EXPORT(vmw_bot_input) uint32_t vmw_bot_input(void) { return vm_bot_input(&B, &E); }
