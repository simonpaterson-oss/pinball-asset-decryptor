/* vm_engine.c - the video mode engine (PAD-1657). See vm_engine.h for the rules it keeps.
 *
 * One step, in order: the input's edges; the kind's own play (steering, firing, meters,
 * the boss's weak points); spawns; movers; collisions by team; meters draining; the win
 * and lose conditions; then the draw list, built from scratch. Everything is whole
 * numbers: 16.16 fixed point for places, speeds and meters, steps for time.
 */
#include "vm_engine.h"
#include "vm_tables.h"

struct vm_engine;
static int check_kinds2(const vm_doc *d, int32_t kind, const int32_t *s);   /* vm_kinds2.c (PAD-1663) */
static void bk_begin(struct vm_engine *e);
static void bk_tick(struct vm_engine *e);
static void play_kinds2(struct vm_engine *e);
static void draw_kinds2(struct vm_engine *e);
static void bk_prompts(struct vm_engine *e, int32_t cx, int32_t y);
static int bk_kind(int32_t k);

#define ONE      65536
#define NONE     ((int32_t)0x80000000)
#define DEG(n)   ((int32_t)(n) * ONE)
#define MARGIN   DEG(256)         /* how far off the stage a moving thing may go */
#define TITLE_STEPS   90          /* the title card: 1.5 s */
#define OUTRO_STEPS   60          /* CLEAR / FAILED: 1 s */
#define TRANS_STEPS   18          /* the phase's opening transition */
#define COMBO_STEPS   90          /* kills this close chain into a combo */
#define HOME_LIFE     600         /* a homer gives up after 10 s */
#define FREE_STEER    (ONE * 15)  /* 900 px/s: a player thing a kind does not steer itself */

/* ---- fixed point ---------------------------------------------------------------- */
int32_t vm_fxmul(int32_t a, int32_t b) { return (int32_t)(((int64_t)a * b) / ONE); }
static int32_t fxdiv(int32_t a, int32_t b)
{
    int64_t q;
    if (b == 0) return 0;
    q = ((int64_t)a * ONE) / b;
    if (q > 0x7fffffff) return 0x7fffffff;
    if (q < -0x7fffffff) return -0x7fffffff;
    return (int32_t)q;
}
static int32_t clampi(int32_t v, int32_t lo, int32_t hi) { return v < lo ? lo : v > hi ? hi : v; }
static int32_t absi(int32_t v) { return v < 0 ? -v : v; }

static int32_t sin_quarter(int32_t r)   /* r: 0..90 degrees, 16.16 */
{
    int64_t p = ((int64_t)r * VM_SIN_STEPS) / 90;   /* the table index, 16.16 */
    int32_t i = (int32_t)(p >> 16), f = (int32_t)(p & 0xffff);
    if (i >= VM_SIN_STEPS) return vm_sin_q[VM_SIN_STEPS];
    return vm_sin_q[i] + (int32_t)(((int64_t)(vm_sin_q[i + 1] - vm_sin_q[i]) * f) >> 16);
}
static int32_t norm360(int32_t d)
{
    int32_t full = DEG(360);
    d %= full;
    if (d < 0) d += full;
    return d;
}
int32_t vm_sin(int32_t deg)
{
    int32_t d = norm360(deg), q = d / DEG(90), r = d % DEG(90);
    switch (q) {
    case 0: return sin_quarter(r);
    case 1: return sin_quarter(DEG(90) - r);
    case 2: return -sin_quarter(r);
    default: return -sin_quarter(DEG(90) - r);
    }
}
int32_t vm_cos(int32_t deg) { return vm_sin(deg + DEG(90)); }
static int32_t atan_unit(int32_t r)     /* r: 0..1 in 16.16 -> degrees 16.16 */
{
    int64_t p = (int64_t)r * VM_ATAN_STEPS;
    int32_t i = (int32_t)(p >> 16), f = (int32_t)(p & 0xffff);
    if (i >= VM_ATAN_STEPS) return vm_atan_t[VM_ATAN_STEPS];
    return vm_atan_t[i] + (int32_t)(((int64_t)(vm_atan_t[i + 1] - vm_atan_t[i]) * f) >> 16);
}
int32_t vm_atan2(int32_t y, int32_t x)  /* degrees clockwise from +x on a y-down stage */
{
    int32_t ax = absi(x), ay = absi(y), a;
    if (ax == 0 && ay == 0) return 0;
    if (ax >= ay) a = atan_unit(fxdiv(ay, ax));
    else a = DEG(90) - atan_unit(fxdiv(ax, ay));
    if (x < 0) a = DEG(180) - a;
    if (y < 0) a = -a;
    return a;
}
static int32_t exp2_neg(int32_t x)      /* 2^-x for x >= 0 in 16.16 */
{
    int32_t whole = x >> 16, frac64 = (x & 0xffff) >> 10;
    if (whole >= 16) return 0;
    return vm_exp2_neg[frac64] >> whole;
}
int32_t vm_ease(int32_t kind, int32_t t)
{
    int32_t u;
    t = clampi(t, 0, ONE);
    switch (kind) {
    case VM_EASE_IN: return vm_fxmul(t, t);
    case VM_EASE_OUT: u = ONE - t; return ONE - vm_fxmul(u, u);
    case VM_EASE_IN_OUT:
        if (t < ONE / 2) return 2 * vm_fxmul(t, t);
        u = ONE - t; return ONE - 2 * vm_fxmul(u, u);
    case VM_EASE_BACK_OUT: {
        int32_t c1 = 111514, c3 = c1 + ONE;   /* 1.70158, 2.70158 */
        u = t - ONE;
        return ONE + vm_fxmul(c3, vm_fxmul(u, vm_fxmul(u, u))) + vm_fxmul(c1, vm_fxmul(u, u));
    }
    case VM_EASE_BOUNCE_OUT: {
        int32_t n1 = 495616, d1 = 180224;     /* 7.5625, 2.75 */
        if (t < fxdiv(ONE, d1)) return vm_fxmul(n1, vm_fxmul(t, t));
        if (t < fxdiv(2 * ONE, d1)) { u = t - fxdiv(98304, d1); return vm_fxmul(n1, vm_fxmul(u, u)) + 49152; }
        if (t < fxdiv(163840, d1)) { u = t - fxdiv(147456, d1); return vm_fxmul(n1, vm_fxmul(u, u)) + 61440; }
        u = t - fxdiv(172032, d1); return vm_fxmul(n1, vm_fxmul(u, u)) + 64512;
    }
    case VM_EASE_ELASTIC_OUT:
        if (t == 0 || t == ONE) return t;
        /* 2^(-10t) * sin((10t - 0.75) * 120 degrees) + 1 */
        return vm_fxmul(exp2_neg(10 * t), vm_sin(vm_fxmul(10 * t - 49152, DEG(120)))) + ONE;
    case VM_EASE_STEP: return t < ONE ? 0 : ONE;
    default: return t;
    }
}

static uint32_t rnd(vm_engine *e)
{
    uint32_t x = e->rng;
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    e->rng = x ? x : 0x9e3779b9u;
    return e->rng;
}
static int32_t rnd_range(vm_engine *e, int32_t lo, int32_t hi)   /* lo..hi inclusive */
{
    uint32_t span;
    if (hi <= lo) return lo;
    span = (uint32_t)((int64_t)hi - lo) + 1u;
    return lo + (int32_t)(span ? rnd(e) % span : rnd(e));
}

/* ---- loading ------------------------------------------------------------------- */
typedef struct { const uint8_t *p; uint32_t len, at; int err; } rd;
static int32_t word(rd *r)
{
    const uint8_t *b;
    if (r->err) return 0;
    if (r->at + 4 > r->len) { r->err = VM_ERR_SHORT; return 0; }
    b = r->p + r->at;
    r->at += 4;
    return (int32_t)((uint32_t)b[0] | ((uint32_t)b[1] << 8) | ((uint32_t)b[2] << 16) | ((uint32_t)b[3] << 24));
}
static int32_t table(rd *r, void *dst, int32_t max, int32_t words_each)
{
    int32_t n = word(r), i;
    int32_t *out = (int32_t *)dst;
    if (r->err) return 0;
    if (n < 0 || n > max) { r->err = VM_ERR_LIMIT; return 0; }
    for (i = 0; i < n * words_each; i++) out[i] = word(r);
    return n;
}
#define IDX(v, n)  ((v) >= 0 && (v) < (n))
#define OPT(v, n)  ((v) == -1 || IDX(v, n))
#define RANGE(v, a, b) ((v) >= (a) && (v) <= (b))

static int check_doc(const vm_doc *d)
{
    int32_t i, j;
    if (d->sps != 60 || d->stage_w < 16 || d->stage_w > 8192 || d->stage_h < 16 || d->stage_h > 8192) return 1;
    if (!IDX(d->start_card, d->ncard)) return 1;
    if (d->nsounds < 0 || d->nsounds > VM_MAX_SOUNDS || d->nclips < 0 || d->nclips > VM_MAX_CLIPS) return 1;
    if (!OPT(d->callout_font, d->nfont) || !OPT(d->title_font, d->nfont)) return 1;
    if (d->nstr < VM_S_COUNT) return 1;
    for (i = 0; i < d->nfont; i++) {
        const vm_font *f = &d->font[i];
        if (f->size <= 0 || f->size > 1024 || f->texel <= 0) return 1;
        for (j = 0; j < VM_GLYPHS; j++)
            if (f->g[j].adv < 0 || f->g[j].adv > DEG(1024) || !RANGE(f->g[j].sw, 0, 4096) || !RANGE(f->g[j].sh, 0, 4096)
                || !RANGE(f->g[j].sx, 0, 65535) || !RANGE(f->g[j].sy, 0, 65535)) return 1;
    }
    for (i = 0; i < d->npic; i++) {
        const vm_picture *p = &d->pic[i];
        if (!RANGE(p->atlas, 0, 65535) || !RANGE(p->w, 1, 8192) || !RANGE(p->h, 1, 8192) || !RANGE(p->cols, 1, 1024)
            || !RANGE(p->frames, 1, 4096) || !RANGE(p->sx0, 0, 65535) || !RANGE(p->sy0, 0, 65535) || p->texel <= 0
            || !RANGE(p->hit.shape, -1, 1)) return 1;
    }
    for (i = 0; i < d->nanim; i++) {
        const vm_anim *a = &d->anim[i];
        if (a->fps < 0 || a->count < 1 || a->first < 0 || a->first + a->count > d->nframe) return 1;
    }
    for (i = 0; i < d->nframe; i++) if (d->frame[i] < 0 || d->frame[i] > 4095) return 1;
    for (i = 0; i < d->nvalue; i++) if (d->value[i].max < d->value[i].min || !RANGE(d->value[i].type, 0, 1)) return 1;
    for (i = 0; i < d->nkind; i++) {
        const vm_kind *k = &d->kind[i];
        if (!IDX(k->picture, d->npic) || !OPT(k->anim, d->nanim) || !RANGE(k->team, 0, 6) || !OPT(k->mover, d->nmover)
            || !OPT(k->counter, d->nvalue) || !RANGE(k->blend, 0, 1) || !RANGE(k->depth, -30000, 30000)
            || !RANGE(k->hit.shape, -1, 1) || k->health < 0 || k->scale <= 0) return 1;
    }
    for (i = 0; i < d->nmover; i++) {
        const vm_mover *m = &d->mover[i];
        if (!RANGE(m->type, 0, 8) || !RANGE(m->easing, 0, 7) || !OPT(m->target, d->nkind) || m->npath < 0
            || m->path0 < 0 || m->path0 + m->npath > d->npath) return 1;
        if (m->type == VM_MV_PATH && m->npath < 2) return 1;
    }
    for (i = 1; i < d->npath; i++) if (d->path[i].cum < 0) return 1;
    for (i = 0; i < d->nphase; i++) {
        const vm_phase *p = &d->phase[i];
        if (!RANGE(p->kind, 0, VM_K_CUSTOM) || !IDX(p->title, d->nstr) || !IDX(p->objective, d->nstr) || p->length < 0
            || !OPT(p->music, d->nsounds) || !IDX(p->settings, d->nsettings) || !RANGE(p->music_fade, 0, 600)) return 1;
        if (p->bg0 < 0 || p->nbg < 0 || p->bg0 + p->nbg > d->nlayer) return 1;
        if (p->place0 < 0 || p->nplace < 0 || p->place0 + p->nplace > d->nplace) return 1;
        if (p->spawn0 < 0 || p->nspawn < 0 || p->spawn0 + p->nspawn > d->nspawn) return 1;
        if (p->win0 < 0 || p->nwin < 0 || p->win0 + p->nwin > d->ncond) return 1;
        if (p->lose0 < 0 || p->nlose < 0 || p->lose0 + p->nlose > d->ncond) return 1;
        if (p->ramp_from <= 0 || p->ramp_to <= 0 || p->ramp_from > DEG(16) || p->ramp_to > DEG(16)) return 1;
    }
    for (i = 0; i < d->nlayer; i++) if (!IDX(d->layer[i].picture, d->npic) || !RANGE(d->layer[i].alpha, 0, 255)) return 1;
    for (i = 0; i < d->nplace; i++) if (!IDX(d->place[i].kind, d->nkind) || d->place[i].scale <= 0) return 1;
    for (i = 0; i < d->nspawn; i++) {
        const vm_spawn *s = &d->spawn[i];
        if (!IDX(s->kind, d->nkind) || s->at < 0 || s->every < 0 || s->count < 0 || s->spread < 0
            || !RANGE(s->lane, -1, VM_LANES_MAX - 1) || !OPT(s->mover, d->nmover)) return 1;
    }
    for (i = 0; i < d->ncond; i++)
        if (!RANGE(d->cond[i].when, 0, VM_W_BUSTED) || !OPT(d->cond[i].of_kind, d->nkind) || !OPT(d->cond[i].of_value, d->nvalue)) return 1;
    for (i = 0; i < d->nweak; i++) if (d->weak[i].hits < 0 || d->weak[i].open < 0 || d->weak[i].closed < 0 || d->weak[i].r < 0) return 1;
    for (i = 0; i < d->natk; i++) if (!IDX(d->atk[i].kind, d->nkind) || d->atk[i].every < 0) return 1;
    for (i = 0; i < d->ncard; i++) {
        const vm_card *c = &d->card[i];
        if (c->type == VM_CARD_CLIP) { if (!IDX(c->a, d->nclips) || !IDX(c->next, d->ncard)) return 1; }
        else if (c->type == VM_CARD_PHASE) { if (!IDX(c->a, d->nphase) || !IDX(c->next, d->ncard) || !IDX(c->lost, d->ncard) || c->tries < 1) return 1; }
        else if (c->type == VM_CARD_END) { if (!RANGE(c->a, 0, 1)) return 1; }
        else return 1;
    }
    for (i = 0; i < d->nhud; i++) {
        const vm_hud *h = &d->hud[i];
        if (!RANGE(h->part, 0, VM_HUD_TEXT) || !OPT(h->value, d->nvalue) || !OPT(h->font, d->nfont) || !OPT(h->text, d->nstr)
            || !RANGE(h->look, 0, VM_LOOK_GLYPHS)) return 1;
    }
    for (i = 0; i < d->ncue; i++) if (!RANGE(d->cue[i].on, 0, VM_ON_LOST) || !IDX(d->cue[i].sound, d->nsounds)) return 1;
    /* the kinds' settings: every index a kind reads */
    for (i = 0; i < d->nphase; i++) {
        const int32_t *s = d->settings[d->phase[i].settings];
        switch (d->phase[i].kind) {
        case VM_K_CHASE:
            if (!OPT(s[0], d->nkind) || !RANGE(s[1], 0, 2) || !RANGE(s[2], 1, VM_LANES_MAX) || !OPT(s[5], d->nkind)
                || s[6] < 1 || s[7] < 0 || !RANGE(s[8], 1, 5) || !RANGE(s[9], -1, 2) || s[11] < 0 || s[12] < 0) return 1;
            break;
        case VM_K_THRUST:
            if (!OPT(s[0], d->nkind) || !RANGE(s[1], 0, 2) || !RANGE(s[2], -1, 2) || !OPT(s[3], d->nkind) || s[4] < 0
                || s[10] < 1 || s[9] < 0 || s[12] < 0) return 1;
            break;
        case VM_K_BOSS:
            if (!OPT(s[0], d->nkind) || !RANGE(s[1], 0, 1) || !OPT(s[2], d->nkind) || s[3] < 0 || s[4] < 0
                || s[3] + s[4] > d->nweak || s[5] < 0 || s[6] < 0 || s[5] + s[6] > d->natk || s[7] < 1
                || !OPT(s[9], d->nkind) || s[10] < 1) return 1;
            break;
        case VM_K_MASH:
            if (!IDX(s[0], d->nvalue) || !RANGE(s[1], 0, 2)) return 1;
            break;
        case VM_K_ALTERNATE:
            if (!IDX(s[0], d->nvalue) || !RANGE(s[3], 0, 2)) return 1;
            break;
        default: break;
        }
        if (check_kinds2(d, d->phase[i].kind, s)) return 1;
    }
    return 0;
}

int vm_load(vm_engine *e, const uint8_t *pack, uint32_t len)
{
    rd r;
    vm_doc *d = &e->doc;
    int32_t i, nwords, at = 0;
    uint8_t *z = (uint8_t *)e;
    for (i = 0; i < (int32_t)sizeof(*e); i++) z[i] = 0;
    r.p = pack; r.len = len; r.at = 0; r.err = 0;
    if ((uint32_t)word(&r) != VM_PACK_MAGIC) { e->err = VM_ERR_MAGIC; return e->err; }
    if (word(&r) != VM_PACK_VERSION) { e->err = VM_ERR_VERSION; return e->err; }
    nwords = word(&r);
    if (nwords < 0 || (uint32_t)nwords * 4u != len) { e->err = VM_ERR_SHORT; return e->err; }
    d->sps = word(&r); d->stage_w = word(&r); d->stage_h = word(&r); d->background = word(&r);
    d->seed = word(&r); d->style = word(&r); d->transition = word(&r); d->skip_clips = word(&r);
    d->speed_step_pct = word(&r); d->start_card = word(&r); d->nsounds = word(&r); d->nclips = word(&r);
    d->callout_font = word(&r); d->title_font = word(&r);
    /* strings: a length, then its bytes in whole words */
    d->nstr = word(&r);
    if (!r.err && (d->nstr < 0 || d->nstr > VM_MAX_STRINGS)) r.err = VM_ERR_LIMIT;
    for (i = 0; i < d->nstr && !r.err; i++) {
        int32_t n = word(&r), k;
        if (n < 0 || n > 1024 || at + n > VM_MAX_STRBYTES) { r.err = VM_ERR_LIMIT; break; }
        d->str[i].off = at; d->str[i].len = n;
        for (k = 0; k < (n + 3) / 4; k++) {
            uint32_t w = (uint32_t)word(&r);
            int32_t b;
            for (b = 0; b < 4 && k * 4 + b < n; b++) d->strbytes[at + k * 4 + b] = (char)((w >> (8 * b)) & 0xff);
        }
        at += n;
    }
    d->nfont = table(&r, d->font, VM_MAX_FONTS, 4 + VM_GLYPHS * 5);
    d->npic = table(&r, d->pic, VM_MAX_PICTURES, 15);
    d->nanim = table(&r, d->anim, VM_MAX_ANIMS, 4);
    d->nframe = table(&r, d->frame, VM_MAX_FRAMES, 1);
    d->nvalue = table(&r, d->value, VM_MAX_VALUES, 5);
    d->nkind = table(&r, d->kind, VM_MAX_KINDS, 15);
    d->nmover = table(&r, d->mover, VM_MAX_MOVERS, 10);
    d->npath = table(&r, d->path, VM_MAX_PATHPTS, 3);
    d->nphase = table(&r, d->phase, VM_MAX_PHASES, 20);
    d->nlayer = table(&r, d->layer, VM_MAX_LAYERS, 5);
    d->nplace = table(&r, d->place, VM_MAX_PLACES, 7);
    d->nspawn = table(&r, d->spawn, VM_MAX_SPAWNS, 9);
    d->ncond = table(&r, d->cond, VM_MAX_CONDS, 4);
    d->nsettings = table(&r, d->settings, VM_MAX_SETTINGS, VM_SETTING_WORDS);
    d->nweak = table(&r, d->weak, VM_MAX_WEAKPTS, 7);
    d->natk = table(&r, d->atk, VM_MAX_ATTACKS, 3);
    d->ncard = table(&r, d->card, VM_MAX_CARDS, 6);
    d->nhud = table(&r, d->hud, VM_MAX_HUD, 12);
    d->ncue = table(&r, d->cue, VM_MAX_CUES, 3);
    d->nnote = table(&r, d->note, VM_MAX_NOTES, 3);
    if (!r.err && (uint32_t)word(&r) != 0x21444e45u) r.err = VM_ERR_SHORT;   /* "END!" */
    if (!r.err && r.at != len) r.err = VM_ERR_SHORT;
    if (!r.err && check_doc(d)) r.err = VM_ERR_INDEX;
    e->err = r.err;
    e->err_at = (int32_t)(r.at / 4);
    e->loaded = !r.err;
    return e->err;
}

/* ---- output -------------------------------------------------------------------- */
static int32_t on_code(int32_t ev, int32_t a)
{
    switch (ev) {
    case VM_EV_FIRE: return VM_ON_FIRE;
    case VM_EV_HIT: return VM_ON_HIT;
    case VM_EV_KILL: return VM_ON_KILL;
    case VM_EV_PICKUP: return VM_ON_PICKUP;
    case VM_EV_HURT: return VM_ON_HURT;
    case VM_EV_PROMPT_GOOD: return VM_ON_PROMPT_GOOD;
    case VM_EV_PROMPT_PERFECT: return VM_ON_PROMPT_PERFECT;
    case VM_EV_PROMPT_MISS: return VM_ON_PROMPT_MISS;
    case VM_EV_PHASE_START: return VM_ON_PHASE_START;
    case VM_EV_PHASE_WON: return VM_ON_PHASE_WON;
    case VM_EV_PHASE_LOST: return VM_ON_PHASE_LOST;
    case VM_EV_FINISHED: return a ? VM_ON_WON : VM_ON_LOST;
    default: return -1;
    }
}
static void sound(vm_engine *e, int32_t snd, int32_t op, int32_t duck, int32_t fade)
{
    if (e->ncues >= VM_MAX_SNDCUES) return;
    e->cues[e->ncues].sound = snd; e->cues[e->ncues].op = op; e->cues[e->ncues].duck = duck;
    e->cues[e->ncues].fade = fade;
    e->ncues++;
}
/* PAD-1667: the music is `snd` from now (-1: none). Only a change is cued: the music plays on through a phase's
 * result card, a phase tried again and a next phase with the same bed; a new bed fades in over its own fade as
 * the old one fades out, and a stop fades the playing one out over its fade. */
static void music_to(vm_engine *e, int32_t snd, int32_t fade)
{
    if (snd == e->music) return;
    if (snd >= 0) sound(e, snd, VM_SND_MUSIC, 0, fade);
    else sound(e, e->music, VM_SND_MUSIC_STOP, 0, e->music_fade);
    e->music = snd;
    e->music_fade = snd >= 0 ? fade : 0;
}
static void emit(vm_engine *e, int32_t type, int32_t a, int32_t b, int32_t c)
{
    int32_t on = on_code(type, a), i;
    if (e->nevents < VM_MAX_EVENTS) {
        vm_event *v = &e->events[e->nevents++];
        v->type = type; v->a = a; v->b = b; v->c = c;
    } else e->events_dropped++;
    if (on < 0) return;
    for (i = 0; i < e->doc.ncue; i++)
        if (e->doc.cue[i].on == on) sound(e, e->doc.cue[i].sound, VM_SND_PLAY, e->doc.cue[i].duck, 0);
}

/* ---- things -------------------------------------------------------------------- */
static const int32_t *S(const vm_engine *e) { return e->doc.settings[e->doc.phase[e->phase].settings]; }
static int32_t find_kind(const vm_engine *e, int32_t kind)
{
    int32_t i;
    if (kind < 0) return -1;
    for (i = 0; i < VM_MAX_THINGS; i++) if (e->th[i].alive && e->th[i].kind == kind) return i;
    return -1;
}
static int32_t spawn(vm_engine *e, int32_t kind, int32_t x, int32_t y, int32_t mover)
{
    const vm_kind *k = &e->doc.kind[kind];
    vm_thing *t;
    int32_t i;
    for (i = 0; i < VM_MAX_THINGS; i++) if (!e->th[i].alive) break;
    if (i == VM_MAX_THINGS) return -1;
    t = &e->th[i];
    t->alive = 1; t->kind = kind; t->team = k->team; t->serial = e->serial++;
    t->vx = t->vy = 0; t->scale = k->scale; t->turn = 0; t->depth = k->depth; t->hidden = 0;
    t->health = k->health > 0 ? k->health : 1; t->age = 0; t->blink = 0; t->role = VM_ROLE_NONE;
    t->mover = mover >= 0 ? mover : k->mover;
    t->heading = t->mover >= 0 ? e->doc.mover[t->mover].dir : 0;
    t->target = -1;
    if (t->mover >= 0) {
        const vm_mover *m = &e->doc.mover[t->mover];
        if (m->type == VM_MV_PATH) {
            const vm_pathpt *p0 = &e->doc.path[m->path0];
            if (x == NONE) x = p0->x;
            if (y == NONE) y = p0->y;
        }
        if (m->target >= 0) {
            t->target = (e->player >= 0 && e->th[e->player].kind == m->target) ? e->player : find_kind(e, m->target);
            if (t->target >= 0) t->heading = vm_atan2(e->th[t->target].y - y, e->th[t->target].x - x);
        }
    }
    if (x == NONE) x = DEG(e->doc.stage_w / 2);
    if (y == NONE) y = DEG(e->doc.stage_h / 2);
    t->x = t->ox = x; t->y = t->oy = y;
    if (t->mover >= 0 && e->doc.mover[t->mover].type == VM_MV_PATH) {
        const vm_pathpt *p0 = &e->doc.path[e->doc.mover[t->mover].path0];
        t->ox = x - p0->x; t->oy = y - p0->y;
    }
    if (e->nthings < VM_MAX_THINGS) e->order[e->nthings++] = i;
    return i;
}
static void hitbox(const vm_engine *e, const vm_thing *t, vm_hitbox *out)
{
    const vm_kind *k = &e->doc.kind[t->kind];
    const vm_picture *p = &e->doc.pic[k->picture];
    vm_hitbox h = k->hit.shape >= 0 ? k->hit : p->hit;
    if (h.shape < 0) {   /* the frame itself, about its anchor */
        int32_t w = p->w * p->texel, hh = p->h * p->texel;
        h.shape = 0; h.x = -vm_fxmul(p->ax, w); h.y = -vm_fxmul(p->ay, hh); h.w = w; h.h = hh;
    }
    out->shape = h.shape;
    out->x = t->x + vm_fxmul(h.x, t->scale); out->y = t->y + vm_fxmul(h.y, t->scale);
    out->w = vm_fxmul(h.w, t->scale); out->h = vm_fxmul(h.h, t->scale);
}
static int overlap(const vm_hitbox *a, const vm_hitbox *b)
{
    if (a->shape == 0 && b->shape == 0)
        return a->x < b->x + b->w && b->x < a->x + a->w && a->y < b->y + b->h && b->y < a->y + a->h;
    if (a->shape == 1 && b->shape == 1) {
        int64_t dx = (int64_t)(a->x - b->x), dy = (int64_t)(a->y - b->y), r = (int64_t)a->w + b->w;
        return dx * dx + dy * dy < r * r;
    } else {
        const vm_hitbox *c = a->shape == 1 ? a : b, *bx = a->shape == 1 ? b : a;
        int64_t nx = clampi(c->x, bx->x, bx->x + bx->w), ny = clampi(c->y, bx->y, bx->y + bx->h);
        int64_t dx = c->x - nx, dy = c->y - ny;
        return dx * dx + dy * dy < (int64_t)c->w * c->w;
    }
}
static void burst(vm_engine *e, int32_t x, int32_t y, int32_t colour)
{
    int32_t n = 0, i;
    if (!(e->doc.style & 4)) return;
    for (i = 0; i < VM_MAX_PARTICLES && n < 12; i++) {
        vm_particle *p = &e->pt[i];
        int32_t a, s;
        if (p->alive) continue;
        a = rnd_range(e, 0, DEG(360) - 1); s = rnd_range(e, DEG(2), DEG(7));
        p->alive = 1; p->x = x; p->y = y; p->vx = vm_fxmul(s, vm_cos(a)); p->vy = vm_fxmul(s, vm_sin(a));
        p->life = 30; p->colour = colour;
        n++;
    }
}
static void add_score(vm_engine *e, int32_t n)
{
    if (n <= 0) return;
    e->score += n; e->phase_score += n;
    emit(e, VM_EV_SCORE, n, e->score, 0);
}
static void shake(vm_engine *e, int32_t px) { if ((e->doc.style & 1) && px > e->shake) e->shake = px; }
static void kill(vm_engine *e, int32_t i, int32_t scored)
{
    vm_thing *t = &e->th[i];
    int32_t pts = scored ? e->doc.kind[t->kind].points : 0;
    t->alive = 0;
    burst(e, t->x, t->y, (int32_t)0xf2c14effu);
    if (!scored) return;
    e->kills[t->kind]++; e->kills_all++;
    e->combo = e->combo_t > 0 ? e->combo + 1 : 1; e->combo_t = COMBO_STEPS;
    emit(e, VM_EV_KILL, t->kind, pts, 0);
    add_score(e, pts);
    if (e->doc.style & 8) e->hitstop = 3;
    shake(e, 4);
}
static void hurt(vm_engine *e)
{
    if (e->player < 0 || e->th[e->player].blink > 0 || e->health <= 0) return;
    e->health--; e->flawless = 0;
    e->th[e->player].blink = e->blink_steps;
    emit(e, VM_EV_HURT, e->health, 0, 0);
    shake(e, 10);
}
static void collect(vm_engine *e, int32_t i)
{
    vm_thing *t = &e->th[i];
    const vm_kind *k = &e->doc.kind[t->kind];
    t->alive = 0;
    if (t->team == VM_TEAM_HEALTH) { if (e->health < e->health_max) e->health++; return; }
    e->pickups[t->kind]++; e->pickups_total[t->kind]++; e->pickups_all++;
    if (k->counter >= 0) {
        const vm_value *v = &e->doc.value[k->counter];
        e->values[k->counter] = clampi(e->values[k->counter] + ONE, v->min, v->max);
    }
    emit(e, VM_EV_PICKUP, t->kind, e->pickups_total[t->kind], 0);
    add_score(e, k->points);
}

/* ---- the phase ------------------------------------------------------------------- */
static int32_t world_speed(const vm_engine *e)    /* the ramp and the level, 16.16 */
{
    const vm_phase *p = &e->doc.phase[e->phase];
    int32_t r = p->ramp_from;
    if (p->length > 0) r = p->ramp_from + (int32_t)(((int64_t)(p->ramp_to - p->ramp_from) * clampi(e->t, 0, p->length)) / p->length);
    r = (int32_t)(((int64_t)r * e->speed_pct) / 100);
    if (p->kind == VM_K_CHASE && e->gear > 1) r = (int32_t)(((int64_t)r * (100 + 25 * (e->gear - 1))) / 100);
    return r;
}
static int32_t settings_health(const vm_engine *e)
{
    const vm_phase *p = &e->doc.phase[e->phase];
    if (p->kind == VM_K_CHASE) return S(e)[11];
    if (p->kind == VM_K_THRUST) return S(e)[9];
    return 0;
}
static int32_t weak_open(const vm_engine *e, int32_t i)
{
    const vm_weakpt *w = &e->doc.weak[i];
    int32_t t = e->t - w->offset, cyc = w->open + w->closed;
    if (t < 0 || cyc <= 0) return 0;
    return (t % cyc) < w->open;
}
int vm_weak_open(const vm_engine *e, int32_t i) { return IDX(i, e->doc.nweak) ? weak_open(e, i) : 0; }

static void phase_begin(vm_engine *e)
{
    const vm_phase *p = &e->doc.phase[e->phase];
    const int32_t *s = S(e);
    int32_t i, n;
    for (i = 0; i < VM_MAX_THINGS; i++) e->th[i].alive = 0;
    for (i = 0; i < VM_MAX_PARTICLES; i++) e->pt[i].alive = 0;
    e->nthings = 0;
    for (i = 0; i < VM_MAX_KINDS; i++) { e->kills[i] = 0; e->pickups[i] = 0; }
    for (i = 0; i < VM_MAX_SPAWNS; i++) e->spawned[i] = 0;
    for (i = 0; i < VM_MAX_WEAKPTS; i++) e->weak_hits[i] = i < e->doc.nweak ? e->doc.weak[i].hits : 0;
    e->kills_all = e->pickups_all = e->hits = e->misses = e->shots = 0;
    e->boss_down = e->goal_hit = e->crashed = e->stage_no = 0;
    e->t = 0; e->phase_score = 0; e->fire_cd = 0; e->gear = 1;
    e->alt_last = -1; e->alt_half = 0; e->rival = 0; e->combo = e->combo_t = 0; e->hitstop = 0;
    e->player = e->boss = e->sight = -1;
    /* a fixed layout plays the same every time; a per-play one draws from the play's seed */
    e->rng = (uint32_t)e->doc.seed * 2654435761u ^ (uint32_t)(e->phase + 1) * 40503u ^ (p->layout ? 0u : e->play_seed);
    if (!e->rng) e->rng = 1;
    for (i = 0; i < e->doc.nvalue; i++) if (e->doc.value[i].type == 0) e->values[i] = e->doc.value[i].start;
    for (i = 0; i < p->nplace; i++) {
        const vm_place *pl = &e->doc.place[p->place0 + i];
        int32_t k = spawn(e, pl->kind, pl->x, pl->y, -1);
        if (k < 0) continue;
        e->th[k].scale = vm_fxmul(e->th[k].scale, pl->scale);
        e->th[k].turn = pl->turn; e->th[k].hidden = pl->hidden;
        if (pl->depth != NONE) e->th[k].depth = pl->depth;
    }
    /* who is who */
    if (p->kind == VM_K_CHASE || p->kind == VM_K_THRUST) e->player = find_kind(e, s[0]);
    if (p->kind == VM_K_BOSS) { e->boss = find_kind(e, s[0]); e->sight = find_kind(e, s[2]); }
    if (e->player < 0)
        for (i = 0; i < VM_MAX_THINGS; i++) if (e->th[i].alive && e->th[i].team == VM_TEAM_PLAYER) { e->player = i; break; }
    if (e->player < 0 && (p->kind == VM_K_CHASE || p->kind == VM_K_THRUST) && s[0] >= 0)
        e->player = spawn(e, s[0], DEG(e->doc.stage_w / 4), DEG(e->doc.stage_h / 2), -1);
    if (e->player >= 0) e->th[e->player].role = VM_ROLE_PLAYER;
    if (e->boss >= 0) e->th[e->boss].role = VM_ROLE_BOSS;
    if (e->sight >= 0) e->th[e->sight].role = VM_ROLE_SIGHT;
    e->health_max = 0;
    if (e->player >= 0) {
        n = settings_health(e);
        e->health_max = n > 0 ? n : (e->doc.kind[e->th[e->player].kind].health > 0 ? e->doc.kind[e->th[e->player].kind].health : 3);
        e->th[e->player].mover = -1;
    }
    e->health = e->health_max;
    e->blink_steps = p->kind == VM_K_CHASE ? s[12] : p->kind == VM_K_THRUST ? s[12] : 60;
    if (e->blink_steps <= 0) e->blink_steps = 60;
    e->ammo_max = p->kind == VM_K_CHASE ? s[7] : p->kind == VM_K_THRUST ? s[4] : 0;
    e->ammo = e->ammo_max;
    e->nlanes = 0;
    if (p->kind == VM_K_CHASE) {
        int32_t top = s[13], bot = s[14], best = 0, bestd = 0x7fffffff;
        e->nlanes = clampi(s[2], 1, VM_LANES_MAX);
        for (i = 0; i < e->nlanes; i++) e->lane_y[i] = top + (int32_t)(((int64_t)(bot - top) * (2 * i + 1)) / (2 * e->nlanes));
        if (e->player >= 0)
            for (i = 0; i < e->nlanes; i++) {
                int32_t dd = absi(e->lane_y[i] - e->th[e->player].y);
                if (dd < bestd) { bestd = dd; best = i; }
            }
        e->lane = best;
    }
    if (p->kind == VM_K_MASH || p->kind == VM_K_ALTERNATE) e->values[s[0]] = e->doc.value[s[0]].start;
    bk_begin(e);
}
static void go_card(vm_engine *e, int32_t c);
static void phase_start(vm_engine *e, int32_t phase, int32_t try_no)
{
    const vm_phase *p;
    e->phase = phase; e->try_no = try_no;
    p = &e->doc.phase[phase];
    phase_begin(e);
    e->state = VM_ST_TITLE; e->state_t = 0;
    e->callout = p->title; e->callout_t = TITLE_STEPS;
    if (p->kind == VM_K_RHYTHM && e->music >= 0) {   /* a rhythm's music starts from its top, now: its chart is timed from it */
        sound(e, e->music, VM_SND_MUSIC_STOP, 0, 0);
        e->music = -1;
    }
    music_to(e, p->music, p->kind == VM_K_RHYTHM ? 0 : p->music_fade);   /* the bed first: a phase_start callout ducks the new one */
    e->song_steps = 0;
    emit(e, VM_EV_PHASE_START, phase, try_no, 0);
}
static void phase_end(vm_engine *e, int won)
{
    const vm_phase *p = &e->doc.phase[e->phase];
    const vm_card *c = &e->doc.card[e->card];
    e->phase_result = won;
    e->state = VM_ST_OUTRO; e->state_t = 0;
    if (won) {
        emit(e, VM_EV_PHASE_WON, e->phase, p->length > 0 ? clampi(p->length - e->t, 0, p->length) : 0, e->health);
        e->callout = e->boss_down ? VM_S_BOSS_DOWN : VM_S_CLEAR;
    } else {
        int32_t left = c->tries - 1 - e->try_no;
        emit(e, VM_EV_PHASE_LOST, e->phase, left > 0 ? left : 0, 0);
        e->callout = left > 0 ? VM_S_TRY_AGAIN : VM_S_FAILED;
    }
    e->callout_t = OUTRO_STEPS;
}
static void go_card(vm_engine *e, int32_t c)
{
    const vm_card *k = &e->doc.card[c];
    e->card = c;
    if (k->type == VM_CARD_CLIP) {
        e->state = VM_ST_CLIP; e->state_t = 0;
        music_to(e, -1, 0);                      /* a cutscene has its own sound */
        emit(e, VM_EV_CLIP_START, k->a, k->skippable, 0);
    } else if (k->type == VM_CARD_PHASE) {
        phase_start(e, k->a, 0);
    } else {
        e->state = VM_ST_DONE; e->outcome = k->a;
        music_to(e, -1, 0);
        emit(e, VM_EV_FINISHED, k->a, e->score, e->flawless);
    }
}

void vm_start(vm_engine *e, uint32_t play_seed, int32_t level)
{
    int32_t i;
    if (!e->loaded) return;
    e->play_seed = play_seed; e->level = level < 0 ? 0 : level;
    e->speed_pct = 100 + e->doc.speed_step_pct * e->level;
    e->score = 0; e->flawless = 1; e->outcome = -1; e->step_no = 0;
    e->in = e->in_prev = e->pressed = e->released = 0;
    e->hash = 0xcbf29ce484222325ull;
    e->shake = e->shake_x = e->shake_y = 0; e->flash_a = 0; e->flash_col = 0;
    e->callout = -1; e->callout_t = 0; e->serial = 0;
    e->music = -1; e->music_fade = 0;
    e->phase = 0; e->player = e->boss = e->sight = -1; e->nthings = 0;
    for (i = 0; i < VM_MAX_THINGS; i++) e->th[i].alive = 0;
    for (i = 0; i < VM_MAX_KINDS; i++) e->pickups_total[i] = 0;
    for (i = 0; i < e->doc.nvalue; i++) e->values[i] = e->doc.value[i].start;
    e->nevents = 0; e->ncues = 0; e->events_dropped = 0;
    go_card(e, e->doc.start_card);
    e->held_events = 1;   /* the first clip or phase's events go out with step 0 */
}

/* the kinds' own play */
static int held(const vm_engine *e, int32_t btn) { return btn >= 0 && (e->in & (1u << btn)); }
static int pressed(const vm_engine *e, int32_t btn) { return btn >= 0 && (e->pressed & (1u << btn)); }
static void fire(vm_engine *e, int32_t shot, int32_t interval)
{
    vm_thing *pl;
    int32_t k;
    if (e->player < 0 || shot < 0 || e->fire_cd > 0) return;
    if (e->ammo_max > 0 && e->ammo <= 0) return;
    pl = &e->th[e->player];
    k = spawn(e, shot, pl->x, pl->y - DEG(24), -1);
    if (k < 0) return;
    e->fire_cd = interval; e->shots++;
    if (e->ammo_max > 0) e->ammo--;
    emit(e, VM_EV_FIRE, shot, 0, 0);
}
static void steer_x(vm_engine *e, int32_t speed)
{
    vm_thing *pl;
    int32_t dir;
    if (e->player < 0) return;
    pl = &e->th[e->player];
    dir = (held(e, VM_BTN_RIGHT) ? 1 : 0) - (held(e, VM_BTN_LEFT) ? 1 : 0);
    pl->x = clampi(pl->x + dir * speed, DEG(32), DEG(e->doc.stage_w - 32));
}
static void play_kind(vm_engine *e)
{
    const vm_phase *p = &e->doc.phase[e->phase];
    const int32_t *s = S(e);
    vm_thing *pl = e->player >= 0 ? &e->th[e->player] : 0;
    int32_t i;
    if (e->fire_cd > 0) e->fire_cd--;
    bk_tick(e);
    switch (p->kind) {
    case VM_K_CHASE: {
        int32_t target;
        if (s[8] > 1 && pressed(e, s[9])) e->gear = e->gear % s[8] + 1;
        if (!pl) break;
        if (s[1] == 0) {          /* lanes: a press moves one lane; left is toward lane 0 (up) */
            if (pressed(e, VM_BTN_LEFT) && e->lane > 0) e->lane--;
            if (pressed(e, VM_BTN_RIGHT) && e->lane < e->nlanes - 1) e->lane++;
        } else if (s[1] == 2) {   /* hold: the held side's lane, the middle when let go */
            e->lane = held(e, VM_BTN_LEFT) ? 0 : held(e, VM_BTN_RIGHT) ? e->nlanes - 1 : e->nlanes / 2;
        }
        if (s[1] == 1) {
            int32_t dir = (held(e, VM_BTN_RIGHT) ? 1 : 0) - (held(e, VM_BTN_LEFT) ? 1 : 0);
            pl->y = clampi(pl->y + dir * s[3], s[13], s[14]);
        } else {
            target = e->lane_y[e->lane];
            if (pl->y < target) pl->y = pl->y + s[3] > target ? target : pl->y + s[3];
            else if (pl->y > target) pl->y = pl->y - s[3] < target ? target : pl->y - s[3];
        }
        if (s[4] == 1 && held(e, VM_BTN_ACTION)) fire(e, s[5], s[6]);
        break;
    }
    case VM_K_THRUST:
        if (!pl) break;
        if (held(e, s[1])) pl->vy -= s[6]; else pl->vy += s[5];
        if (s[7] > 0) pl->vy = clampi(pl->vy, -s[7], s[7]);
        pl->y += pl->vy;
        if (pl->y < 0 || pl->y > DEG(e->doc.stage_h)) {
            pl->y = clampi(pl->y, 0, DEG(e->doc.stage_h)); pl->vy = 0;
            if (!e->crashed) { e->crashed = 1; hurt(e); }
        } else e->crashed = 0;
        if (s[2] >= 0 && held(e, s[2])) fire(e, s[3], s[10]);
        break;
    case VM_K_BOSS: {
        vm_thing *b = e->boss >= 0 ? &e->th[e->boss] : 0;
        steer_x(e, s[8] > 0 ? s[8] : FREE_STEER);
        if (b && e->sight >= 0 && s[1] == 0 && s[4] > 0) {   /* the sight sweeps across the weak points */
            int32_t lo = 0x7fffffff, hi = -0x7fffffff, my = 0, per = 144, ph, span;
            for (i = 0; i < s[4]; i++) {
                const vm_weakpt *w = &e->doc.weak[s[3] + i];
                if (w->x < lo) lo = w->x;
                if (w->x > hi) hi = w->x;
                my += w->y / s[4];
            }
            lo -= DEG(60); hi += DEG(60); span = hi - lo;
            ph = e->t % (2 * per);
            ph = ph < per ? ph : 2 * per - ph;
            e->th[e->sight].x = b->x + lo + (int32_t)(((int64_t)span * vm_ease(VM_EASE_IN_OUT, (ph * ONE) / per)) >> 16);
            e->th[e->sight].y = b->y + my;
        }
        if (b && s[1] == 0 && e->sight >= 0 && pressed(e, VM_BTN_ACTION)) {
            int32_t hit = 0;
            for (i = 0; i < s[4]; i++) {
                const vm_weakpt *w = &e->doc.weak[s[3] + i];
                int64_t dx = (int64_t)(e->th[e->sight].x - (b->x + w->x)), dy = (int64_t)(e->th[e->sight].y - (b->y + w->y));
                if (e->weak_hits[s[3] + i] > 0 && weak_open(e, s[3] + i) && dx * dx + dy * dy <= (int64_t)w->r * w->r) {
                    e->weak_hits[s[3] + i]--; e->hits++; hit = 1;
                    emit(e, VM_EV_HIT, i, e->weak_hits[s[3] + i], 0);
                    shake(e, 6);
                    if (e->weak_hits[s[3] + i] == 0) burst(e, b->x + w->x, b->y + w->y, (int32_t)0xf0705fffu);
                    break;
                }
            }
            e->shots++;
            if (!hit) e->misses++;
        }
        if (b && s[1] == 1 && held(e, VM_BTN_ACTION)) fire(e, s[9], s[10]);
        if (b) {
            int32_t left = 0;
            for (i = 0; i < s[4]; i++) left += e->weak_hits[s[3] + i];
            if (left == 0 && s[4] > 0) {
                e->stage_no++;
                if (e->stage_no >= s[7]) { e->boss_down = 1; kill(e, e->boss, 1); e->boss = -1; }
                else for (i = 0; i < s[4]; i++) e->weak_hits[s[3] + i] = e->doc.weak[s[3] + i].hits;
            }
        }
        if (e->boss >= 0)
            for (i = 0; i < s[6]; i++) {
                const vm_attack *a = &e->doc.atk[s[5] + i];
                if (a->every > 0 && e->t > 0 && e->t % a->every == 0) {
                    int32_t k = spawn(e, a->kind, e->th[e->boss].x, e->th[e->boss].y, -1);
                    if (k >= 0) {
                        if (a->aim == 0 && pl) e->th[k].heading = vm_atan2(pl->y - e->th[k].y, pl->x - e->th[k].x);
                        else if (a->aim != 0) e->th[k].heading = DEG(90);
                    }
                }
            }
        break;
    }
    case VM_K_MASH:
        if (pressed(e, s[1])) e->values[s[0]] += s[2];
        e->values[s[0]] -= s[3];
        e->rival += s[5];
        e->values[s[0]] = clampi(e->values[s[0]], e->doc.value[s[0]].min, e->doc.value[s[0]].max);
        if (e->values[s[0]] >= s[4]) e->goal_hit = 1;
        break;
    case VM_K_ALTERNATE: {
        int32_t side = pressed(e, VM_BTN_LEFT) ? 0 : pressed(e, VM_BTN_RIGHT) ? 1 : -1;
        if (side >= 0) {
            if (e->alt_last < 0) {
                if (s[3] == 2 || s[3] == side) { e->alt_last = side; e->alt_half = 1; }
            } else if (side != e->alt_last) {
                e->alt_last = side;
                if (++e->alt_half >= 2) { e->values[s[0]] += s[1]; e->alt_half = 0; }
            }
        }
        e->values[s[0]] -= s[2];
        e->values[s[0]] = clampi(e->values[s[0]], e->doc.value[s[0]].min, e->doc.value[s[0]].max);
        if (e->values[s[0]] >= s[4]) e->goal_hit = 1;
        break;
    }
    case VM_K_TUG: case VM_K_RHYTHM: case VM_K_SEQUENCE: case VM_K_DODGE: case VM_K_SHIELD:
        play_kinds2(e);
        break;
    default:
        steer_x(e, FREE_STEER);
        break;
    }
}

static void spawns(vm_engine *e)
{
    const vm_phase *p = &e->doc.phase[e->phase];
    int32_t i;
    for (i = 0; i < p->nspawn; i++) {
        const vm_spawn *s = &e->doc.spawn[p->spawn0 + i];
        int32_t n = e->spawned[p->spawn0 + i], due, x, y, k;
        if (s->count > 0 && n >= s->count) continue;
        due = s->at + (s->every > 0 ? n * s->every : 0);
        if (s->every <= 0 && n > 0) continue;
        if (e->t - 1 != due) continue;   /* t counts this step; due is the time before it */
        e->spawned[p->spawn0 + i] = n + 1;
        x = s->x; y = s->y;
        if (s->lane >= 0 && e->nlanes > 0) y = e->lane_y[s->lane < e->nlanes ? s->lane : e->nlanes - 1];
        if (s->spread > 0) {
            int32_t d = rnd_range(e, -s->spread, s->spread);
            if (y == NONE) y = DEG(e->doc.stage_h / 2);
            y += d;
        }
        k = spawn(e, s->kind, x, y, s->mover);
        (void)k;
    }
}

static void move_things(vm_engine *e)
{
    int32_t i, ws = world_speed(e), scroll = 0;
    const vm_phase *p = &e->doc.phase[e->phase];
    if (p->kind == VM_K_CHASE) scroll = S(e)[10];
    else if (p->kind == VM_K_THRUST) scroll = S(e)[8];
    for (i = 0; i < VM_MAX_THINGS; i++) {
        vm_thing *t = &e->th[i];
        const vm_mover *m;
        if (!t->alive) continue;
        t->age++;
        if (t->blink > 0) t->blink--;
        if (t->mover < 0) continue;
        m = &e->doc.mover[t->mover];
        switch (m->type) {
        case VM_MV_STRAIGHT:
            t->x += vm_fxmul(m->speed, vm_cos(t->heading)); t->y += vm_fxmul(m->speed, vm_sin(t->heading));
            break;
        case VM_MV_SCROLL:
            t->x -= vm_fxmul(m->speed > 0 ? m->speed : scroll, ws);
            break;
        case VM_MV_PATH: {
            const vm_pathpt *pp = &e->doc.path[m->path0];
            int32_t L = pp[m->npath - 1].cum, u, d, s;
            int64_t raw;
            if (L <= 0 || m->speed <= 0) break;
            raw = ((int64_t)t->age * m->speed * ONE) / L;
            if (raw >= ONE) {
                if (!m->loop) { t->alive = 0; if (t->team == VM_TEAM_PICKUP) e->misses++; break; }
                raw %= ONE;
            }
            u = (int32_t)raw;
            d = clampi(vm_fxmul(vm_ease(m->easing, u), L), 0, L);
            for (s = 0; s < m->npath - 2 && pp[s + 1].cum <= d; s++) {}
            {
                int32_t seg = pp[s + 1].cum - pp[s].cum, f = seg > 0 ? fxdiv(d - pp[s].cum, seg) : 0;
                f = clampi(f, 0, ONE);
                t->x = t->ox + pp[s].x + vm_fxmul(pp[s + 1].x - pp[s].x, f);
                t->y = t->oy + pp[s].y + vm_fxmul(pp[s + 1].y - pp[s].y, f);
            }
            break;
        }
        case VM_MV_HOME:
            if (t->target >= 0 && e->th[t->target].alive) {
                int32_t want = vm_atan2(e->th[t->target].y - t->y, e->th[t->target].x - t->x);
                int32_t diff = norm360(want - t->heading + DEG(180)) - DEG(180);
                t->heading = norm360(t->heading + clampi(diff, -m->turn, m->turn));
            }
            t->x += vm_fxmul(m->speed, vm_cos(t->heading)); t->y += vm_fxmul(m->speed, vm_sin(t->heading));
            if (t->age > HOME_LIFE) t->alive = 0;
            break;
        case VM_MV_ORBIT: {
            int32_t a = norm360(t->heading + (int32_t)(((int64_t)m->turn * t->age) % DEG(360)));
            t->x = t->ox + vm_fxmul(m->radius, vm_cos(a)); t->y = t->oy + vm_fxmul(m->radius, vm_sin(a));
            break;
        }
        default: break;
        }
        if (t->alive && t->role == VM_ROLE_NONE
            && (t->x < -MARGIN || t->x > DEG(e->doc.stage_w) + MARGIN || t->y < -MARGIN || t->y > DEG(e->doc.stage_h) + MARGIN)) {
            if (t->team == VM_TEAM_PICKUP) e->misses++;
            t->alive = 0;
        }
    }
    for (i = 0; i < VM_MAX_PARTICLES; i++) {
        vm_particle *q = &e->pt[i];
        if (!q->alive) continue;
        q->x += q->vx; q->y += q->vy; q->vy += ONE / 8;
        if (--q->life <= 0) q->alive = 0;
    }
}

static void collide(vm_engine *e)
{
    static int32_t shots[VM_MAX_THINGS], foes[VM_MAX_THINGS];
    int32_t ns = 0, nf = 0, i, j;
    const int32_t *s = S(e);
    vm_hitbox ph, a, b;
    int have_player = e->player >= 0 && e->th[e->player].alive;
    if (have_player) hitbox(e, &e->th[e->player], &ph);
    for (i = 0; i < VM_MAX_THINGS; i++) {
        vm_thing *t = &e->th[i];
        if (!t->alive || t->hidden) continue;
        if (t->team == VM_TEAM_PLAYER_SHOT) shots[ns++] = i;
        else if (t->team == VM_TEAM_ENEMY) foes[nf++] = i;
        if (!have_player || i == e->player) continue;
        if (t->team == VM_TEAM_ENEMY || t->team == VM_TEAM_ENEMY_SHOT || t->team == VM_TEAM_PICKUP || t->team == VM_TEAM_HEALTH) {
            hitbox(e, t, &a);
            if (!overlap(&a, &ph)) continue;
            if (t->team == VM_TEAM_PICKUP || t->team == VM_TEAM_HEALTH) collect(e, i);
            else {
                hurt(e);
                if (t->role != VM_ROLE_BOSS) { kill(e, i, 0); if (t->team == VM_TEAM_ENEMY) nf--; }
            }
        }
    }
    for (i = 0; i < ns; i++) {
        vm_thing *sh = &e->th[shots[i]];
        if (!sh->alive) continue;
        hitbox(e, sh, &a);
        /* a boss hit with shots takes them on its open weak points only */
        if (e->doc.phase[e->phase].kind == VM_K_BOSS && s[1] == 1 && e->boss >= 0) {
            vm_thing *bo = &e->th[e->boss];
            for (j = 0; j < s[4]; j++) {
                const vm_weakpt *w = &e->doc.weak[s[3] + j];
                vm_hitbox c;
                c.shape = 1; c.x = bo->x + w->x; c.y = bo->y + w->y; c.w = w->r; c.h = 0;
                if (e->weak_hits[s[3] + j] > 0 && weak_open(e, s[3] + j) && overlap(&a, &c)) {
                    e->weak_hits[s[3] + j]--; e->hits++; sh->alive = 0;
                    emit(e, VM_EV_HIT, j, e->weak_hits[s[3] + j], 0);
                    shake(e, 6);
                    break;
                }
            }
            if (!sh->alive) continue;
        }
        for (j = 0; j < nf; j++) {
            vm_thing *f = &e->th[foes[j]];
            if (!f->alive) continue;
            hitbox(e, f, &b);
            if (!overlap(&a, &b)) continue;
            sh->alive = 0;
            if (f->role == VM_ROLE_BOSS) break;   /* the hull soaks it up */
            e->hits++;
            if (--f->health <= 0) kill(e, foes[j], 1);
            else emit(e, VM_EV_HIT, f->kind, f->health, 0);
            break;
        }
    }
}

static int cond_met(const vm_engine *e, const vm_cond *c)
{
    const vm_phase *p = &e->doc.phase[e->phase];
    int32_t i, n;
    switch (c->when) {
    case VM_W_TIME_UP: return p->length > 0 && e->t >= p->length;
    case VM_W_SURVIVE: return e->t >= c->value;
    case VM_W_SCORE: return e->phase_score >= c->value;
    case VM_W_KILLS: return (c->of_kind >= 0 ? e->kills[c->of_kind] : e->kills_all) >= c->value;
    case VM_W_PICKUPS:
        if (c->of_value >= 0) return e->values[c->of_value] >= c->value * ONE;
        return (c->of_kind >= 0 ? e->pickups[c->of_kind] : e->pickups_all) >= c->value;
    case VM_W_GOAL: return e->goal_hit;
    case VM_W_HEALTH_GONE: return e->health_max > 0 && e->health <= 0;
    case VM_W_MISSES: return e->misses >= c->value;
    case VM_W_BOSS_DOWN: return e->boss_down;
    case VM_W_HITS: return e->hits >= c->value;
    case VM_W_AMMO_OUT:
        if (e->ammo_max <= 0 || e->ammo > 0) return 0;
        for (i = 0, n = 0; i < VM_MAX_THINGS; i++) if (e->th[i].alive && e->th[i].team == VM_TEAM_PLAYER_SHOT) n++;
        return n == 0;
    case VM_W_CRASHED: return e->crashed;
    case VM_W_ACCURACY:   /* judged once the kind's run is over: good presses out of all it asked for */
        return e->bk_done && e->hits + e->misses > 0 && (int64_t)e->hits * 100 >= (int64_t)c->value * (e->hits + e->misses);
    default: return 0;    /* landed, cashed_out, busted: their kinds come with PAD-1662 */
    }
}
static void judge(vm_engine *e)
{
    const vm_phase *p = &e->doc.phase[e->phase];
    int32_t i;
    for (i = 0; i < p->nwin; i++) if (cond_met(e, &e->doc.cond[p->win0 + i])) { phase_end(e, 1); return; }
    if (e->kind_won) { phase_end(e, 1); return; }
    if (e->kind_lost || e->bk_done) { phase_end(e, 0); return; }   /* a button kind's run is over and nothing asked of it was met */
    if (p->kind == VM_K_MASH && S(e)[5] > 0 && e->rival >= S(e)[4]) { phase_end(e, 0); return; }
    for (i = 0; i < p->nlose; i++) if (cond_met(e, &e->doc.cond[p->lose0 + i])) { phase_end(e, 0); return; }
    if (p->length > 0 && e->t >= p->length) phase_end(e, 0);   /* the clock ran out: nothing was won */
}

/* ---- the draw list ------------------------------------------------------------------ */
static pm_vm_entry *entry(vm_engine *e, uint16_t tag)
{
    pm_vm_entry *x;
    if (e->list.n >= VM_MAX_ENTRIES) { e->list.dropped++; return 0; }
    x = &e->list.e[e->list.n++];
    x->tag = tag;
    return x;
}
static void box(vm_engine *e, int32_t x, int32_t y, int32_t w, int32_t h, uint32_t colour, uint16_t blend)
{
    pm_vm_entry *b;
    if ((colour & 0xff) == 0 || w <= 0 || h <= 0) return;
    b = entry(e, PM_VM_BOX);
    if (!b) return;
    b->u.b.x = x; b->u.b.y = y; b->u.b.w = w; b->u.b.h = h; b->u.b.colour = colour; b->u.b.blend = blend;
}
static void quad(vm_engine *e, int32_t atlas, int32_t blend, int32_t sx, int32_t sy, int32_t sw, int32_t sh,
                 int32_t x, int32_t y, int32_t ax, int32_t ay, int32_t scale, int32_t turn, uint32_t tint,
                 int32_t alpha, int32_t depth)
{
    pm_vm_entry *q = entry(e, PM_VM_QUAD);
    if (!q) return;
    q->u.q.atlas = (uint16_t)atlas; q->u.q.blend = (uint16_t)blend;
    q->u.q.sx = (uint16_t)sx; q->u.q.sy = (uint16_t)sy; q->u.q.sw = (uint16_t)sw; q->u.q.sh = (uint16_t)sh;
    q->u.q.x = x; q->u.q.y = y; q->u.q.ax = ax; q->u.q.ay = ay;
    q->u.q.scale_x = scale; q->u.q.scale_y = scale; q->u.q.turn = turn;
    q->u.q.tint = tint; q->u.q.alpha = (uint8_t)clampi(alpha, 0, 255); q->u.q.depth = (int16_t)clampi(depth, -32768, 32767);
}
static uint32_t with_alpha(uint32_t c, int32_t a) { return (c & 0xffffff00u) | (uint32_t)clampi((int32_t)(((c & 0xff) * (uint32_t)clampi(a, 0, 255)) / 255), 0, 255); }

/* words: glyph quads laid out with the font's own advances. align -1 left, 0 centre, 1 right */
static int32_t text_width(const vm_font *f, const char *s, int32_t n, int32_t scale)
{
    int32_t w = 0, i;
    for (i = 0; i < n; i++) {
        int32_t c = (unsigned char)s[i];
        if (c < 32 || c > 126) c = '?';
        w += f->g[c - 32].adv;
    }
    return vm_fxmul(w, scale);
}
static void text(vm_engine *e, int32_t font, const char *s, int32_t n, int32_t x, int32_t y, int32_t align,
                 uint32_t colour, int32_t alpha, int32_t scale)
{
    const vm_font *f;
    int32_t i, w;
    if (font < 0) font = 0;
    if (font >= e->doc.nfont) return;
    f = &e->doc.font[font];
    w = text_width(f, s, n, scale);
    if (align == 0) x -= w / 2; else if (align > 0) x -= w;
    for (i = 0; i < n; i++) {
        int32_t c = (unsigned char)s[i];
        const vm_glyph *g;
        if (c < 32 || c > 126) c = '?';
        g = &f->g[c - 32];
        if (c != ' ' && g->sw > 0)
            quad(e, f->atlas, PM_BLEND_NORMAL, g->sx, g->sy, g->sw, g->sh, x, y, 0, 0, vm_fxmul(f->texel, scale), 0, colour, alpha, 30000);
        x += vm_fxmul(g->adv, scale);
    }
}
static void text_str(vm_engine *e, int32_t font, int32_t sid, int32_t x, int32_t y, int32_t align, uint32_t colour, int32_t alpha, int32_t scale)
{
    if (!IDX(sid, e->doc.nstr)) return;
    text(e, font, e->doc.strbytes + e->doc.str[sid].off, e->doc.str[sid].len, x, y, align, colour, alpha, scale);
}
static int32_t number(char *out, int32_t v, int commas)   /* no stdio: digits by hand */
{
    char rev[24];
    int32_t n = 0, k = 0, neg = v < 0, digits = 0;
    uint32_t u = neg ? (uint32_t)(-(int64_t)v) : (uint32_t)v;
    do {
        if (commas && digits && digits % 3 == 0) rev[n++] = ',';
        rev[n++] = (char)('0' + u % 10); u /= 10; digits++;
    } while (u && n < 22);
    if (neg) out[k++] = '-';
    while (n) out[k++] = rev[--n];
    return k;
}
static int32_t align_of(const vm_engine *e, int32_t x)
{
    if (x >= DEG(e->doc.stage_w) * 3 / 4) return 1;
    if (x <= DEG(e->doc.stage_w) / 4) return -1;
    return 0;
}
static int32_t font_line(const vm_engine *e, int32_t font)
{
    if (font < 0) font = 0;
    return font < e->doc.nfont ? e->doc.font[font].line_h : DEG(32);
}

#include "vm_kinds2.c"

static void draw_bar(vm_engine *e, const vm_hud *h, int32_t frac, uint32_t colour)
{
    int32_t w = h->w > 0 ? h->w : DEG(200), hh = h->h > 0 ? h->h : DEG(12);
    box(e, h->x, h->y, w, hh, with_alpha(colour, 0x40), PM_BLEND_NORMAL);
    box(e, h->x, h->y, vm_fxmul(w, clampi(frac, 0, ONE)), hh, colour, PM_BLEND_NORMAL);
    if (h->accent) {
        uint32_t a = (uint32_t)h->accent;
        box(e, h->x - DEG(2), h->y - DEG(2), w + DEG(4), DEG(2), a, PM_BLEND_NORMAL);
        box(e, h->x - DEG(2), h->y + hh, w + DEG(4), DEG(2), a, PM_BLEND_NORMAL);
        box(e, h->x - DEG(2), h->y, DEG(2), hh, a, PM_BLEND_NORMAL);
        box(e, h->x + w, h->y, DEG(2), hh, a, PM_BLEND_NORMAL);
    }
}
static void draw_pips(vm_engine *e, const vm_hud *h, int32_t have, int32_t of, uint32_t colour)
{
    int32_t gap = DEG(4), w = h->w > 0 ? h->w : DEG(24) * of, pw, i;
    if (of <= 0) return;
    pw = (w - gap * (of - 1)) / of;
    for (i = 0; i < of && i < 32; i++)
        box(e, h->x + i * (pw + gap), h->y, pw, h->h > 0 ? h->h : DEG(16), i < have ? colour : with_alpha(colour, 0x40), PM_BLEND_NORMAL);
}
static void draw_hud(vm_engine *e)
{
    const vm_phase *p = &e->doc.phase[e->phase];
    char buf[96];
    int32_t i, n;
    for (i = 0; i < e->doc.nhud; i++) {
        const vm_hud *h = &e->doc.hud[i];
        uint32_t col = h->colour ? (uint32_t)h->colour : 0xffffffffu;
        if (h->phases && !(h->phases & (1 << (e->phase & 31)))) continue;
        switch (h->part) {
        case VM_HUD_HEALTH:
            if (e->health_max <= 0) break;
            if (h->look == VM_LOOK_BAR) draw_bar(e, h, fxdiv(e->health, e->health_max), col);
            else if (h->look == VM_LOOK_NUMBER) { n = number(buf, e->health, 0); text(e, h->font, buf, n, h->x, h->y, align_of(e, h->x), col, 255, ONE); }
            else draw_pips(e, h, e->health, e->health_max, col);
            break;
        case VM_HUD_PROGRESS: {
            int32_t frac = 0;
            if (p->kind == VM_K_BOSS && S(e)[4] > 0) {
                int32_t tot = 0, left = 0, k;
                for (k = 0; k < S(e)[4]; k++) { tot += e->doc.weak[S(e)[3] + k].hits; left += e->weak_hits[S(e)[3] + k]; }
                frac = tot ? fxdiv(tot - left, tot) : 0;
            } else if (p->length > 0) frac = fxdiv(e->t, p->length);
            draw_bar(e, h, frac, col);
            break;
        }
        case VM_HUD_COMBO:
            if (e->combo < 2 || e->combo_t <= 0) break;
            buf[0] = 'x'; n = 1 + number(buf + 1, e->combo, 0);
            text(e, h->font, buf, n, h->x, h->y, align_of(e, h->x), col, 255, ONE);
            break;
        case VM_HUD_SCORE:
            n = number(buf, e->score, 1);
            text(e, h->font, buf, n, h->x, h->y, align_of(e, h->x), col, 255, ONE);
            break;
        case VM_HUD_TIMER:
            if (p->length <= 0) break;
            n = number(buf, (clampi(p->length - e->t, 0, p->length) + e->doc.sps - 1) / e->doc.sps, 0);
            text(e, h->font, buf, n, h->x, h->y, align_of(e, h->x), col, 255, ONE);
            break;
        case VM_HUD_LIVES:
            draw_pips(e, h, e->doc.card[e->card].tries - e->try_no, e->doc.card[e->card].tries, col);
            break;
        case VM_HUD_METER:
            if (h->value >= 0) {
                const vm_value *v = &e->doc.value[h->value];
                draw_bar(e, h, fxdiv(e->values[h->value] - v->min, v->max - v->min), col);
                if (p->kind == VM_K_MASH && S(e)[0] == h->value && S(e)[5] > 0) {
                    vm_hud r = *h;
                    r.y = h->y + (h->h > 0 ? h->h : DEG(12)) + DEG(6); r.h = DEG(6); r.accent = 0;
                    draw_bar(e, &r, fxdiv(e->rival, S(e)[4]), h->accent ? (uint32_t)h->accent : 0xf0705fffu);
                }
            }
            break;
        case VM_HUD_COUNTER: {
            int32_t v = h->value >= 0 ? e->values[h->value] >> 16 : e->pickups_all, k = 0, j;
            if (IDX(h->text, e->doc.nstr)) {
                const char *s = e->doc.strbytes + e->doc.str[h->text].off;
                for (j = 0; j < e->doc.str[h->text].len && k < 80; j++) {
                    if (s[j] == '{' && j + 2 < e->doc.str[h->text].len && s[j + 1] == 'n' && s[j + 2] == '}') { k += number(buf + k, v, 1); j += 2; }
                    else buf[k++] = s[j];
                }
            } else k = number(buf, v, 1);
            text(e, h->font, buf, k, h->x, h->y, align_of(e, h->x), col, 255, ONE);
            break;
        }
        case VM_HUD_TEXT:
            text_str(e, h->font, h->text, h->x, h->y, align_of(e, h->x), col, 255, ONE);
            break;
        case VM_HUD_PROMPTS: {
            int32_t cx = h->x + (h->w > 0 ? h->w : DEG(e->doc.stage_w)) / 2, y = h->y + DEG(4), gapx = DEG(160);
            if (e->state != VM_ST_PLAY) break;
            if (bk_kind(p->kind)) bk_prompts(e, cx, h->y + (h->h > 0 ? h->h : DEG(40)));
            else if (p->kind == VM_K_ALTERNATE) {
                int32_t next = e->alt_last < 0 ? -1 : 1 - e->alt_last;
                text_str(e, h->font, VM_S_LEFT, cx - gapx, y, 0, col, next == 1 ? 90 : 255, ONE);
                text_str(e, h->font, VM_S_RIGHT, cx + gapx, y, 0, col, next == 0 ? 90 : 255, ONE);
            } else if (p->kind == VM_K_MASH) text_str(e, h->font, VM_S_MASH, cx, y, 0, col, 255, ONE);
            else if (p->kind == VM_K_CHASE) {
                text_str(e, h->font, VM_S_STEER, cx - gapx, y, 0, col, 255, ONE);
                if (S(e)[4] == 1) text_str(e, h->font, VM_S_FIRE, cx + gapx, y, 0, col, 255, ONE);
            } else if (p->kind == VM_K_THRUST) text_str(e, h->font, VM_S_HOLD, cx, y, 0, col, 255, ONE);
            else text_str(e, h->font, VM_S_FIRE, cx, y, 0, col, 255, ONE);
            break;
        }
        default: break;   /* the callout is drawn by draw_callout */
        }
    }
}
static void draw_callout(vm_engine *e)
{
    const vm_hud *h = 0;
    int32_t i, x, y, a, sc, font;
    uint32_t col = 0xffffffffu;
    if (e->callout < 0 || e->callout_t <= 0) return;
    for (i = 0; i < e->doc.nhud; i++) if (e->doc.hud[i].part == VM_HUD_CALLOUT) { h = &e->doc.hud[i]; break; }
    x = h ? h->x : DEG(e->doc.stage_w / 2);
    y = h ? h->y : DEG(e->doc.stage_h / 3);
    if (h && h->colour) col = (uint32_t)h->colour;
    font = h && h->font >= 0 ? h->font : e->doc.callout_font;
    /* in: back_out pop over 12 steps; out: fade over the last 12 */
    {
        int32_t total = e->state == VM_ST_TITLE ? TITLE_STEPS : OUTRO_STEPS, age = total - e->callout_t;
        sc = age < 12 ? vm_ease(VM_EASE_BACK_OUT, (age * ONE) / 12) : ONE;
        a = e->callout_t < 12 ? (e->callout_t * 255) / 12 : 255;
        if (sc < ONE / 8) sc = ONE / 8;
    }
    if (h && h->accent) text_str(e, font, e->callout, x + DEG(4), y + DEG(4), 0, (uint32_t)h->accent, a, sc);
    text_str(e, font, e->callout, x, y, 0, col, a, sc);
    if (e->state == VM_ST_TITLE)
        text_str(e, e->doc.title_font, e->doc.phase[e->phase].objective, x, y + font_line(e, font), 0, 0xffffffffu, a, ONE);
}
static void sort_things(vm_engine *e)
{
    int32_t i, j, n = 0;
    for (i = 0; i < e->nthings; i++) if (e->th[e->order[i]].alive) e->order[n++] = e->order[i];
    e->nthings = n;
    for (i = 1; i < n; i++) {   /* insertion: the order is nearly sorted from the last step */
        int32_t k = e->order[i], dk = e->th[k].depth, sk = e->th[k].serial;
        for (j = i - 1; j >= 0; j--) {
            const vm_thing *o = &e->th[e->order[j]];
            if (o->depth < dk || (o->depth == dk && o->serial < sk)) break;
            e->order[j + 1] = e->order[j];
        }
        e->order[j + 1] = k;
    }
}
static void build_list(vm_engine *e)
{
    const vm_doc *d = &e->doc;
    int32_t i;
    e->list.n = 0; e->list.dropped = 0; e->list.step = e->step_no;
    e->list.frame.clear = (uint32_t)d->background;
    e->list.frame.cover_game = 1;
    e->list.frame.shake_x = e->shake_x; e->list.frame.shake_y = e->shake_y;
    e->list.frame.flash = e->flash_a > 0 ? with_alpha((uint32_t)e->flash_col, e->flash_a) : 0;
    sort_things(e);
    if (e->state != VM_ST_TITLE && e->state != VM_ST_PLAY && e->state != VM_ST_OUTRO) return;
    {
        const vm_phase *p = &d->phase[e->phase];
        int32_t ws = world_speed(e);
        for (i = 0; i < p->nbg; i++) {
            const vm_layer *l = &d->layer[p->bg0 + i];
            const vm_picture *pic = &d->pic[l->picture];
            int32_t w = pic->w * pic->texel, x;
            int64_t off = (int64_t)vm_fxmul(l->speed, ws) * e->t;
            if (l->tile && w > 0) {
                x = (int32_t)(off % w);
                if (x > 0) x -= w;
                for (; x < DEG(d->stage_w); x += w)
                    quad(e, pic->atlas, PM_BLEND_NORMAL, pic->sx0, pic->sy0, pic->w, pic->h, x, l->y, 0, 0, pic->texel, 0, 0xffffffffu, l->alpha, -30000 + i);
            } else {
                x = (int32_t)clampi((int32_t)(off > 0x3fffffff ? 0x3fffffff : off < -0x3fffffff ? -0x3fffffff : off), -0x3fffffff, 0x3fffffff);
                quad(e, pic->atlas, PM_BLEND_NORMAL, pic->sx0, pic->sy0, pic->w, pic->h, x, l->y, 0, 0, pic->texel, 0, 0xffffffffu, l->alpha, -30000 + i);
            }
        }
    }
    for (i = 0; i < e->nthings; i++) {
        const vm_thing *t = &e->th[e->order[i]];
        const vm_kind *k = &d->kind[t->kind];
        const vm_picture *p = &d->pic[k->picture];
        int32_t f = 0, alpha = 255;
        if (t->hidden) continue;
        if (k->anim >= 0) {
            const vm_anim *a = &d->anim[k->anim];
            int32_t no = (int32_t)(((int64_t)t->age * a->fps) / ((int64_t)d->sps * ONE));
            no = a->loop ? no % a->count : (no < a->count ? no : a->count - 1);
            f = d->frame[a->first + no];
        }
        if (f >= p->frames) f = p->frames - 1;
        if (t->blink > 0 && ((t->blink >> 2) & 1)) alpha = 70;
        quad(e, p->atlas, k->blend, p->sx0 + (f % p->cols) * p->w, p->sy0 + (f / p->cols) * p->h, p->w, p->h,
             t->x, t->y, p->ax, p->ay, vm_fxmul(t->scale, p->texel), t->turn, 0xffffffffu, alpha, t->depth);
    }
    if (d->phase[e->phase].kind == VM_K_BOSS && e->boss >= 0) {
        const int32_t *s = S(e);
        for (i = 0; i < s[4]; i++) {
            const vm_weakpt *w = &d->weak[s[3] + i];
            if (e->weak_hits[s[3] + i] <= 0 || !weak_open(e, s[3] + i)) continue;
            box(e, e->th[e->boss].x + w->x - w->r / 2, e->th[e->boss].y + w->y - w->r / 2, w->r, w->r, 0xf0705f90u, PM_BLEND_ADD);
        }
    }
    for (i = 0; i < VM_MAX_PARTICLES; i++) {
        const vm_particle *q = &e->pt[i];
        if (q->alive) box(e, q->x - DEG(3), q->y - DEG(3), DEG(6), DEG(6), with_alpha((uint32_t)q->colour, (q->life * 255) / 30), PM_BLEND_ADD);
    }
    draw_kinds2(e);
    draw_hud(e);
    draw_callout(e);
    if (e->state == VM_ST_TITLE && e->state_t < TRANS_STEPS) {   /* the phase's opening transition */
        int32_t left = TRANS_STEPS - e->state_t, W = DEG(d->stage_w), H = DEG(d->stage_h);
        int32_t f = (left * ONE) / TRANS_STEPS;
        switch (d->transition) {
        case VM_TR_FADE: box(e, 0, 0, W, H, with_alpha(0x000000ffu, (left * 255) / TRANS_STEPS), PM_BLEND_NORMAL); break;
        case VM_TR_WIPE: box(e, W - vm_fxmul(W, f), 0, vm_fxmul(W, f), H, 0x000000ffu, PM_BLEND_NORMAL); break;
        case VM_TR_IRIS: {
            int32_t r = vm_fxmul(W / 2, ONE - f), cx = W / 2, cy = H / 2;
            box(e, 0, 0, W, cy - r > 0 ? cy - r : 0, 0x000000ffu, PM_BLEND_NORMAL);
            box(e, 0, cy + r, W, H - (cy + r), 0x000000ffu, PM_BLEND_NORMAL);
            box(e, 0, cy - r, cx - r > 0 ? cx - r : 0, 2 * r, 0x000000ffu, PM_BLEND_NORMAL);
            box(e, cx + r, cy - r, W - (cx + r), 2 * r, 0x000000ffu, PM_BLEND_NORMAL);
            break;
        }
        default: break;
        }
    }
}

int vm_edit_still(vm_engine *e, int32_t phase, int32_t flags)
{
    if (!e->loaded || phase < 0 || phase >= e->doc.nphase) return 0;
    e->score = 0; e->flawless = 1; e->outcome = -1; e->step_no = 0; e->level = 0; e->speed_pct = 100;
    e->in = e->in_prev = e->pressed = e->released = 0;
    e->shake = e->shake_x = e->shake_y = 0; e->flash_a = 0; e->flash_col = 0;
    e->serial = 0; e->card = 0; e->play_seed = 1;
    phase_start(e, phase, 0);
    e->state_t = TRANS_STEPS;
    if (!(flags & 1)) { e->callout = -1; e->callout_t = 0; }
    build_list(e);
    e->nevents = 0; e->ncues = 0;
    return 1;
}

/* the canonical words of the draw list: header 8, quad 12, box 6 */
typedef struct { int32_t *out; uint32_t cap, n; uint64_t *h; } wr;
static void put(wr *w, int32_t v)
{
    if (w->out && w->n < w->cap) w->out[w->n] = v;
    w->n++;
    if (w->h) {
        uint32_t u = (uint32_t)v;
        int b;
        for (b = 0; b < 4; b++) { *w->h ^= (u >> (8 * b)) & 0xff; *w->h *= 0x100000001b3ull; }
    }
}
static void list_words(const vm_engine *e, wr *w)
{
    const pm_vm_list *l = &e->list;
    uint32_t i;
    put(w, 0x314c4456); put(w, (int32_t)l->step); put(w, (int32_t)l->n);
    put(w, l->frame.shake_x); put(w, l->frame.shake_y); put(w, (int32_t)l->frame.flash);
    put(w, (int32_t)l->frame.clear); put(w, l->frame.cover_game);
    for (i = 0; i < l->n; i++) {
        const pm_vm_entry *x = &l->e[i];
        if (x->tag == PM_VM_QUAD) {
            const pm_vm_quad *q = &x->u.q;
            put(w, PM_VM_QUAD | (q->blend << 8) | (q->alpha << 16));
            put(w, q->atlas | ((uint32_t)(uint16_t)q->depth << 16));
            put(w, q->sx | ((uint32_t)q->sy << 16)); put(w, q->sw | ((uint32_t)q->sh << 16));
            put(w, q->x); put(w, q->y); put(w, q->ax); put(w, q->ay);
            put(w, q->scale_x); put(w, q->scale_y); put(w, q->turn); put(w, (int32_t)q->tint);
        } else {
            const pm_vm_box *b = &x->u.b;
            put(w, PM_VM_BOX | (b->blend << 8));
            put(w, b->x); put(w, b->y); put(w, b->w); put(w, b->h); put(w, (int32_t)b->colour);
        }
    }
}
uint32_t vm_list_words(const vm_engine *e, int32_t *out, uint32_t cap)
{
    wr w;
    w.out = out; w.cap = cap; w.n = 0; w.h = 0;
    list_words(e, &w);
    return w.n;
}

/* ---- one step ---------------------------------------------------------------------- */
int vm_step(vm_engine *e, uint32_t input)
{
    int32_t i;
    if (!e->loaded) return 0;
    if (!e->held_events) { e->nevents = 0; e->ncues = 0; e->events_dropped = 0; e->song_steps++; }
    e->held_events = 0;
    e->in_prev = e->in; e->in = input;
    e->pressed = e->in & ~e->in_prev; e->released = e->in_prev & ~e->in;
    e->state_t++;
    switch (e->state) {
    case VM_ST_CLIP: {
        const vm_card *c = &e->doc.card[e->card];
        int skip = 0;
        if (c->skippable && e->doc.skip_clips == 1)
            skip = (e->in & 3u) == 3u && (e->pressed & 3u);
        else if (c->skippable && e->doc.skip_clips == 2)
            skip = (e->pressed & VM_IN_ACTION) != 0;
        if ((e->in & VM_IN_CLIP_DONE) || skip) {
            emit(e, VM_EV_CLIP_STOP, c->a, skip && !(e->in & VM_IN_CLIP_DONE), 0);
            go_card(e, c->next);
        }
        break;
    }
    case VM_ST_TITLE:
        if (e->callout_t > 0) e->callout_t--;
        if (e->state_t >= TITLE_STEPS) { e->state = VM_ST_PLAY; e->state_t = 0; e->callout = -1; }
        break;
    case VM_ST_PLAY:
        if (e->hitstop > 0) { e->hitstop--; break; }
        e->t++;
        play_kind(e);
        spawns(e);
        move_things(e);
        collide(e);
        for (i = 0; i < e->doc.nvalue; i++) {   /* meters drain by themselves, but not one a kind drives */
            const vm_value *v = &e->doc.value[i];
            int driven = (e->doc.phase[e->phase].kind == VM_K_MASH || e->doc.phase[e->phase].kind == VM_K_ALTERNATE
                          || e->doc.phase[e->phase].kind == VM_K_TUG) && S(e)[0] == i;
            if (v->type == 0 && v->drain > 0 && !driven) e->values[i] = clampi(e->values[i] - v->drain, v->min, v->max);
        }
        if (e->combo_t > 0 && --e->combo_t == 0) e->combo = 0;
        if (e->callout_t > 0) e->callout_t--;
        judge(e);
        break;
    case VM_ST_OUTRO:
        if (e->callout_t > 0) e->callout_t--;
        move_things(e);   /* the world keeps drifting under the result */
        if (e->state_t >= OUTRO_STEPS) {
            const vm_card *c = &e->doc.card[e->card];
            if (e->phase_result) go_card(e, c->next);
            else if (e->try_no + 1 < c->tries) phase_start(e, e->phase, e->try_no + 1);
            else go_card(e, c->lost);
        }
        break;
    default: break;
    }
    if (e->state == VM_ST_TITLE && e->state_t == 1 && e->doc.transition == VM_TR_WHITE_FLASH && (e->doc.style & 2)) {
        e->flash_col = (int32_t)0xffffffffu; e->flash_a = 255;
    }
    /* the camera */
    if (e->shake > 0) {
        int32_t s = e->shake;
        e->shake_x = rnd_range(e, -DEG(s), DEG(s)); e->shake_y = rnd_range(e, -DEG(s), DEG(s));
        if ((e->step_no & 1) == 0) e->shake--;
    } else e->shake_x = e->shake_y = 0;
    if (e->flash_a > 0) e->flash_a = e->flash_a > 255 / TRANS_STEPS ? e->flash_a - 255 / TRANS_STEPS : 0;
    build_list(e);
    {
        wr w;
        w.out = 0; w.cap = 0; w.n = 0; w.h = &e->hash;
        list_words(e, &w);
        for (i = 0; i < e->nevents; i++) { put(&w, e->events[i].type); put(&w, e->events[i].a); put(&w, e->events[i].b); put(&w, e->events[i].c); }
        for (i = 0; i < e->ncues; i++) { put(&w, e->cues[i].sound); put(&w, e->cues[i].op); put(&w, e->cues[i].duck); put(&w, e->cues[i].fade); }
    }
    e->step_no++;
    return e->state != VM_ST_DONE;
}

int vm_check(const vm_engine *e)
{
    int32_t i, n = 0;
    const vm_doc *d = &e->doc;
    if (!e->loaded) return 1;
    if (e->state < VM_ST_IDLE || e->state > VM_ST_DONE) return 2;
    if (!IDX(e->card, d->ncard) || !IDX(e->phase, d->nphase)) return 3;
    if (e->nthings < 0 || e->nthings > VM_MAX_THINGS) return 4;
    if (e->list.n > VM_MAX_ENTRIES || e->nevents > VM_MAX_EVENTS || e->ncues > VM_MAX_SNDCUES) return 5;
    if (e->health < 0 || e->health > e->health_max) return 6;
    if (e->nlanes < 0 || e->nlanes > VM_LANES_MAX || (e->nlanes && !IDX(e->lane, e->nlanes))) return 7;
    for (i = 0; i < VM_MAX_THINGS; i++) {
        const vm_thing *t = &e->th[i];
        if (!t->alive) continue;
        n++;
        if (!IDX(t->kind, d->nkind) || !OPT(t->mover, d->nmover) || !OPT(t->target, VM_MAX_THINGS)) return 8;
        if (t->x < -2 * MARGIN - DEG(d->stage_w) || t->x > DEG(2 * d->stage_w) + 2 * MARGIN
            || t->y < -2 * MARGIN - DEG(d->stage_h) || t->y > DEG(2 * d->stage_h) + 2 * MARGIN) return 9;
    }
    if (n > e->nthings + VM_MAX_THINGS) return 10;
    for (i = 0; i < d->nvalue; i++) if (e->values[i] < d->value[i].min || e->values[i] > d->value[i].max) return 11;
    if (e->score < 0) return 12;
    return 0;
}
