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
EXPORT(vmw_bot_init) void vmw_bot_init(int32_t clip_steps) { vm_bot_init(&B, clip_steps); }
EXPORT(vmw_bot_input) uint32_t vmw_bot_input(void) { return vm_bot_input(&B, &E); }
