/* vm_kinds2.c - the button kinds of the video mode engine (PAD-1663): tug of war, rhythm, button sequence,
 * quick dodge and hold shield, the prompts of mash and alternate, and the on-screen button glyphs every one of
 * them draws. Included by vm_engine.c (it is part of the engine, under the same rules: no malloc, no floats, no
 * libc); never compiled by itself.
 *
 * The glyphs are the cabinet's own three buttons, always where they sit on it: the left flipper button on the
 * left, Action in the middle, the right flipper button on the right. Each is a round button drawn from boxes, so
 * it needs no art and costs the same on every machine; its looks are idle, lit, pressed in, held (a fill under
 * it), mashed (a ring thrown out on every press) and next-in-turn (it bobs).
 *
 * Settings words (compiler.py writes them; check_kinds2 holds a pack to them):
 *   tug:      0 meter, 1 hold (0 left, 1 right, 2 shown), 2 switch steps, 3 per press, 4 pull back a step,
 *             5 grab every steps, 6 pairs to shake it off, 7 goal
 *   rhythm:   0 music, 1 first note, 2 notes, 3 perfect ms, 4 good ms, 5 travel ms, 6 beat us, 7 first beat ms,
 *             8 end ms, 9 beats a bar
 *   sequence: 0 first note (fixed run), 1 its length (0: random), 2 random length, 3 shown, 4 flash steps,
 *             5 steps a press, 6 rounds
 *   dodge:    0 button mask, 1 tell steps, 2 window steps, 3 count
 *   shield:   0 button, 1 tell steps, 2 hold steps, 3 count
 */

#define BK_RESULT_STEPS 36
#define BK_GRACE        9      /* shield: steps into the attack the button may still come down */
#define BK_JUDGE_STEPS  30

static int bk_kind(int32_t k)
{
    return k == VM_K_MASH || k == VM_K_ALTERNATE || k == VM_K_TUG || k == VM_K_RHYTHM || k == VM_K_SEQUENCE
        || k == VM_K_DODGE || k == VM_K_SHIELD;
}

static int check_kinds2(const vm_doc *d, int32_t kind, const int32_t *s)
{
    int32_t i;
    switch (kind) {
    case VM_K_TUG:
        return !IDX(s[0], d->nvalue) || !RANGE(s[1], 0, 2) || s[2] < 0 || s[5] < 0 || !RANGE(s[6], 0, 50);
    case VM_K_RHYTHM:
        if (!OPT(s[0], d->nsounds) || s[1] < 0 || s[2] < 1 || s[1] + s[2] > d->nnote || s[3] < 0 || s[4] < s[3]
            || s[5] < 1 || s[6] < 1 || s[9] < 1) return 1;
        for (i = 0; i < s[2]; i++) if (!RANGE(d->note[s[1] + i].button, 0, 2) || d->note[s[1] + i].hold < 0) return 1;
        return 0;
    case VM_K_SEQUENCE:
        if (s[1] < 0 || s[1] > VM_MAX_SEQ || s[0] < 0 || s[0] + s[1] > d->nnote || !RANGE(s[2], 0, VM_MAX_SEQ)
            || (s[1] == 0 && s[2] < 1) || s[4] < 0 || s[5] < 1 || s[6] < 1) return 1;
        for (i = 0; i < s[1]; i++) if (!RANGE(d->note[s[0] + i].button, 0, 2)) return 1;
        return 0;
    case VM_K_DODGE:
        return !RANGE(s[0], 1, 7) || s[1] < 0 || s[2] < 1 || s[3] < 1;
    case VM_K_SHIELD:
        return !RANGE(s[0], 0, 2) || s[1] < 0 || s[2] < 1 || s[3] < 1;
    default: return 0;
    }
}

/* ---- play ---------------------------------------------------------------------------- */
static void bk_judge(vm_engine *e, int32_t word, int32_t btn, uint32_t colour)
{
    e->judge_word = word; e->judge_t = BK_JUDGE_STEPS; e->judge_col = (int32_t)colour;
    e->judge_x = btn == VM_BTN_LEFT ? -1 : btn == VM_BTN_RIGHT ? 1 : 0;
}
static void bk_good(vm_engine *e, int32_t btn, int32_t perfect, int32_t points)
{
    e->hits++;
    e->combo = e->combo_t > 0 || e->combo > 0 ? e->combo + 1 : 1; e->combo_t = 1 << 20;   /* a run of good presses lasts until a miss */
    emit(e, perfect ? VM_EV_PROMPT_PERFECT : VM_EV_PROMPT_GOOD, btn, e->combo, 0);
    add_score(e, points);
}
static void bk_miss(vm_engine *e, int32_t btn, int32_t word)
{
    e->misses++; e->combo = 0; e->combo_t = 0; e->flawless = 0;
    emit(e, VM_EV_PROMPT_MISS, btn, e->misses, 0);
    if (e->health_max > 0 && e->player >= 0) hurt(e);
    else { shake(e, 8); if (e->doc.style & 2) { e->flash_col = (int32_t)0xd8342cffu; e->flash_a = 90; } }
    if (word >= 0) bk_judge(e, word, btn, 0xff5a4cffu);
}
static int32_t song_ms(const vm_engine *e)
{
    return (int32_t)(((int64_t)e->song_steps * 1000) / e->doc.sps) - e->audio_offset_ms;
}
static void bk_new_run(vm_engine *e)
{
    const int32_t *s = S(e);
    int32_t i;
    if (s[1] > 0) {
        e->bk_len = s[1];
        for (i = 0; i < e->bk_len; i++) e->seq[i] = e->doc.note[s[0] + i].button;
    } else {
        e->bk_len = clampi(s[2] + e->bk_round, 1, VM_MAX_SEQ);    /* a random run grows a button a round */
        for (i = 0; i < e->bk_len; i++) e->seq[i] = rnd_range(e, 0, 2);
    }
}
static void bk_pick_button(vm_engine *e)
{
    int32_t mask = S(e)[0], n = 0, b, pick;
    for (b = 0; b < 3; b++) if (mask & (1 << b)) n++;
    pick = n > 1 ? rnd_range(e, 0, n - 1) : 0;
    for (b = 0; b < 3; b++) if (mask & (1 << b)) { if (pick-- == 0) break; }
    e->bk_btn = b > 2 ? 2 : b;
}

static void bk_begin(vm_engine *e)
{
    const vm_phase *p = &e->doc.phase[e->phase];
    const int32_t *s = S(e);
    int32_t i;
    e->kind_won = e->kind_lost = 0;
    e->bk_state = VM_BK_GAP; e->bk_t = 0; e->bk_n = 0; e->bk_btn = 0; e->bk_i = 0; e->bk_round = 0;
    e->bk_len = 0; e->bk_pairs = 0; e->bk_last = -1; e->bk_side = 0; e->bk_grab = 0; e->bk_done = 0;
    e->judge_word = -1; e->judge_t = 0; e->note_next = 0;
    for (i = 0; i < 3; i++) e->press_t[i] = 1000;
    for (i = 0; i < VM_MAX_NOTES; i++) e->note_st[i] = VM_NOTE_WAIT;
    switch (p->kind) {
    case VM_K_TUG:
        e->values[s[0]] = e->doc.value[s[0]].start;
        e->bk_side = s[1] == 2 ? rnd_range(e, 0, 1) : s[1];
        e->bk_t = s[2];                 /* steps to the next switch of the named side */
        e->bk_n = s[5];                 /* steps to the next grab */
        break;
    case VM_K_SEQUENCE:
        bk_new_run(e);
        e->bk_state = VM_BK_SHOW; e->bk_t = s[4] > 0 ? s[4] : 45;
        break;
    case VM_K_DODGE: case VM_K_SHIELD:
        e->bk_state = VM_BK_GAP; e->bk_t = 45;
        break;
    default: break;
    }
}

static void play_tug(vm_engine *e, const int32_t *s)
{
    int32_t *m = &e->values[s[0]];
    const vm_value *v = &e->doc.value[s[0]];
    if (s[1] == 2 && s[2] > 0 && --e->bk_t <= 0) {            /* the screen names the other side */
        e->bk_side = 1 - e->bk_side; e->bk_t = s[2];
        e->press_t[e->bk_side] = 1000;
    }
    if (!e->bk_grab) {
        if (s[5] > 0 && s[6] > 0 && --e->bk_n <= 0) {          /* the second threat takes hold */
            e->bk_grab = 1; e->bk_pairs = 0; e->bk_last = -1; e->bk_i = 0;
            shake(e, 6);
        } else if (pressed(e, VM_BTN_ACTION) && held(e, e->bk_side)) *m += s[3];
        *m -= s[4];
    } else {
        int32_t side = pressed(e, VM_BTN_LEFT) ? 0 : pressed(e, VM_BTN_RIGHT) ? 1 : -1;
        if (side >= 0 && side != e->bk_last) {
            if (e->bk_last >= 0 && ++e->bk_i >= 2) { e->bk_i = 0; e->bk_pairs++; }
            e->bk_last = side;
        }
        if (e->bk_pairs >= s[6]) {
            e->bk_grab = 0; e->bk_n = s[5];
            bk_good(e, VM_BTN_ACTION, 0, 0);
            bk_judge(e, VM_S_SHAKE, VM_BTN_ACTION, 0x7ee08affu);
        }
        *m -= 2 * s[4];                                        /* it drags you back while it holds on */
    }
    *m = clampi(*m, v->min, v->max);
    if (*m >= s[7]) { e->goal_hit = 1; e->kind_won = 1; }
    else if (*m <= v->min && e->t > 1) e->kind_lost = 1;
}

static void play_rhythm(vm_engine *e, const int32_t *s)
{
    const vm_note *chart = &e->doc.note[s[1]];
    int32_t now = song_ms(e), i, b, early = 2 * s[4], left = 0;
    uint8_t *st = &e->note_st[s[1]];
    for (b = 0; b < 3; b++) {
        int32_t best = -1, bd = 0x7fffffff;
        if (!pressed(e, b)) continue;
        for (i = e->note_next; i < s[2]; i++) {
            int32_t d = now - chart[i].at;
            if (chart[i].at - now > early) break;              /* the chart is in time order */
            if (st[i] != VM_NOTE_WAIT || chart[i].button != b || d > early) continue;
            if (absi(d) < bd) { bd = absi(d); best = i; }
        }
        if (best < 0) continue;
        {
            int32_t d = now - chart[best].at;
            st[best] = chart[best].hold > 0 ? VM_NOTE_HOLDING : VM_NOTE_HIT;
            if (absi(d) <= s[3]) { bk_good(e, b, 1, 300); bk_judge(e, VM_S_PERFECT, b, 0xffd84aff); }
            else if (absi(d) <= s[4]) { bk_good(e, b, 0, 100); bk_judge(e, VM_S_GOOD, b, 0x7ee08aff); }
            else {                                             /* early or late: it counts, the combo does not */
                e->hits++; e->combo = 0;
                emit(e, VM_EV_PROMPT_GOOD, b, 0, d < 0 ? 1 : 2);
                add_score(e, 30);
                bk_judge(e, d < 0 ? VM_S_EARLY : VM_S_LATE, b, 0x8fb8ffff);
            }
        }
    }
    for (i = e->note_next; i < s[2]; i++) {
        if (chart[i].at - now > early) break;
        if (st[i] == VM_NOTE_WAIT && now - chart[i].at > early) { st[i] = VM_NOTE_MISSED; bk_miss(e, chart[i].button, VM_S_MISS); }
        else if (st[i] == VM_NOTE_HOLDING) {
            if (now >= chart[i].at + chart[i].hold) { st[i] = VM_NOTE_HIT; add_score(e, 100); }
            else if (!held(e, chart[i].button) && now < chart[i].at + chart[i].hold - s[4]) {
                st[i] = VM_NOTE_MISSED; bk_miss(e, chart[i].button, VM_S_MISS);
            }
        }
    }
    while (e->note_next < s[2] && (st[e->note_next] == VM_NOTE_HIT || st[e->note_next] == VM_NOTE_MISSED)) e->note_next++;
    for (i = e->note_next; i < s[2]; i++) if (st[i] != VM_NOTE_HIT && st[i] != VM_NOTE_MISSED) left++;
    if (!left && now >= s[8] && !e->bk_done) { e->bk_done = 1; e->goal_hit = 1; }
}

static void play_sequence(vm_engine *e, const int32_t *s)
{
    int32_t b;
    if (--e->bk_t > 0 && e->bk_state != VM_BK_ENTER) return;
    switch (e->bk_state) {
    case VM_BK_SHOW:
        e->bk_state = VM_BK_ENTER; e->bk_i = 0; e->bk_t = s[5];
        break;
    case VM_BK_RESULT:
        if (e->bk_round >= s[6]) { e->goal_hit = 1; e->bk_done = 1; break; }
        e->bk_state = VM_BK_SHOW; e->bk_t = s[4] > 0 ? s[4] : 45;
        break;
    case VM_BK_ENTER:
        if (e->bk_t <= 0) {                                    /* too slow */
            bk_miss(e, e->seq[e->bk_i], VM_S_MISS);
            e->bk_state = VM_BK_RESULT; e->bk_t = BK_RESULT_STEPS;
            break;
        }
        for (b = 0; b < 3; b++) {
            if (!pressed(e, b)) continue;
            if (b != e->seq[e->bk_i]) {
                bk_miss(e, b, VM_S_MISS);
                e->bk_state = VM_BK_RESULT; e->bk_t = BK_RESULT_STEPS;
                return;
            }
            e->bk_i++; e->bk_t = s[5];
            emit(e, VM_EV_PROMPT_GOOD, b, e->bk_i, 0);
            add_score(e, 50);
            if (e->bk_i >= e->bk_len) {
                e->bk_round++;
                bk_good(e, b, 1, 250 * e->bk_round);
                bk_judge(e, VM_S_PERFECT, VM_BTN_ACTION, 0xffd84aff);
                e->bk_state = VM_BK_RESULT; e->bk_t = BK_RESULT_STEPS;
                if (e->bk_round < s[6]) bk_new_run(e);
            }
            return;
        }
        break;
    default: break;
    }
}

/* dodge and shield share a beat: a gap, the tell, the window (or the attack), what came of it */
static void bk_next_attack(vm_engine *e, int32_t count)
{
    e->bk_n++;
    e->bk_state = VM_BK_RESULT; e->bk_t = BK_RESULT_STEPS + rnd_range(e, 0, 30);   /* a pause that cannot be learned */
    if (e->bk_n >= count) { e->goal_hit = 1; e->bk_done = 1; }
}
static void play_dodge(vm_engine *e, const int32_t *s)
{
    int32_t b, any = -1;
    for (b = 0; b < 3; b++) if (pressed(e, b)) { any = b; break; }
    switch (e->bk_state) {
    case VM_BK_GAP: case VM_BK_RESULT:
        if (--e->bk_t <= 0) { bk_pick_button(e); e->bk_state = VM_BK_TELL; e->bk_t = s[1]; }
        break;
    case VM_BK_TELL:
        if (any >= 0) { bk_miss(e, any, VM_S_TOO_EARLY); bk_next_attack(e, s[3]); break; }
        if (--e->bk_t <= 0) { e->bk_state = VM_BK_WINDOW; e->bk_t = s[2]; }
        break;
    case VM_BK_WINDOW:
        if (any >= 0) {
            if (any == e->bk_btn) {
                int32_t perfect = s[2] - e->bk_t < (s[2] + 2) / 3;
                bk_good(e, any, perfect, perfect ? 200 : 100);
                bk_judge(e, VM_S_DODGED, any, perfect ? 0xffd84aff : 0x7ee08aff);
            } else bk_miss(e, any, VM_S_HIT);
            bk_next_attack(e, s[3]);
        } else if (--e->bk_t <= 0) { bk_miss(e, e->bk_btn, VM_S_HIT); bk_next_attack(e, s[3]); }
        break;
    default: break;
    }
}
static void play_shield(vm_engine *e, const int32_t *s)
{
    e->bk_btn = s[0];
    switch (e->bk_state) {
    case VM_BK_GAP: case VM_BK_RESULT:
        if (--e->bk_t <= 0) { e->bk_state = VM_BK_TELL; e->bk_t = s[1]; }
        break;
    case VM_BK_TELL:
        if (--e->bk_t <= 0) { e->bk_state = VM_BK_WINDOW; e->bk_t = s[2]; e->bk_i = 0; }
        break;
    case VM_BK_WINDOW:
        e->bk_i++;
        if (!held(e, s[0]) && e->bk_i > BK_GRACE) { bk_miss(e, s[0], VM_S_HIT); bk_next_attack(e, s[3]); break; }
        if (--e->bk_t <= 0) {
            bk_good(e, s[0], 1, 150);
            bk_judge(e, VM_S_BLOCKED, s[0], 0x7ee08aff);
            shake(e, 4);
            bk_next_attack(e, s[3]);
        }
        break;
    default: break;
    }
}

/* every step of the play, before the kind's own switch */
static void bk_tick(vm_engine *e)
{
    int32_t b;
    for (b = 0; b < 3; b++) {
        if (pressed(e, b)) e->press_t[b] = 0;
        else if (e->press_t[b] < 1000) e->press_t[b]++;
    }
    if (e->judge_t > 0) e->judge_t--;
}
static void play_kinds2(vm_engine *e)
{
    const int32_t *s = S(e);
    switch (e->doc.phase[e->phase].kind) {
    case VM_K_TUG: play_tug(e, s); break;
    case VM_K_RHYTHM: play_rhythm(e, s); break;
    case VM_K_SEQUENCE: play_sequence(e, s); break;
    case VM_K_DODGE: play_dodge(e, s); break;
    case VM_K_SHIELD: play_shield(e, s); break;
    default: break;
    }
}

void vm_set_audio_offset(vm_engine *e, int32_t ms) { e->audio_offset_ms = clampi(ms, -2000, 2000); }

/* ---- the glyphs ----------------------------------------------------------------------- */
enum { GL_DIM = 1, GL_LIT = 2, GL_DOWN = 4, GL_NOLABEL = 8 };
/* the half-width of a circle's strip k of n, 16.16 of the radius: sqrt(1 - y*y) at the strip's middle */
static const int32_t STRIP9[9] = { 30016, 48824, 58720, 63898, 65536, 63898, 58720, 48824, 30016 };
static const int32_t STRIP5[5] = { 39321, 60030, 65536, 60030, 39321 };
static void disc(vm_engine *e, int32_t cx, int32_t cy, int32_t r, uint32_t colour, uint16_t blend, int32_t fine)
{
    int32_t n = fine ? 9 : 5, k, h = (2 * r) / n;
    const int32_t *w = fine ? STRIP9 : STRIP5;
    if (r <= 0) return;
    for (k = 0; k < n; k++) {
        int32_t hw = vm_fxmul(r, w[k]);
        box(e, cx - hw, cy - r + k * h, 2 * hw, h + (k == n - 1 ? 2 * r - n * h : 0), colour, blend);
    }
}
static uint32_t shade(uint32_t c, int32_t pct)    /* pct of the colour, alpha kept */
{
    uint32_t r = (c >> 24) & 0xff, g = (c >> 16) & 0xff, b = (c >> 8) & 0xff;
    r = (uint32_t)clampi((int32_t)(r * (uint32_t)pct / 100), 0, 255);
    g = (uint32_t)clampi((int32_t)(g * (uint32_t)pct / 100), 0, 255);
    b = (uint32_t)clampi((int32_t)(b * (uint32_t)pct / 100), 0, 255);
    return (r << 24) | (g << 16) | (b << 8) | (c & 0xff);
}
static uint32_t lighten(uint32_t c, int32_t pct)  /* pct of the way to white */
{
    uint32_t r = (c >> 24) & 0xff, g = (c >> 16) & 0xff, b = (c >> 8) & 0xff;
    r += (255 - r) * (uint32_t)pct / 100; g += (255 - g) * (uint32_t)pct / 100; b += (255 - b) * (uint32_t)pct / 100;
    return (r << 24) | (g << 16) | (b << 8) | (c & 0xff);
}
typedef struct { uint32_t flip, action; int32_t font; } bk_look;
static bk_look look_of(const vm_engine *e)
{
    bk_look l;
    int32_t i;
    l.flip = 0xe8edf4ffu; l.action = 0xe5483bffu; l.font = e->doc.title_font;
    for (i = 0; i < e->doc.nhud; i++) {
        const vm_hud *h = &e->doc.hud[i];
        if (h->part != VM_HUD_PROMPTS) continue;
        if (h->colour) l.flip = (uint32_t)h->colour;
        if (h->accent) l.action = (uint32_t)h->accent;
        if (h->font >= 0) l.font = h->font;
        break;
    }
    return l;
}
/* one cabinet button at (cx, cy), radius r. progress >= 0 draws a fill bar under it (a hold) */
static void draw_button(vm_engine *e, int32_t btn, int32_t cx, int32_t cy, int32_t r, int32_t flags, int32_t progress, int32_t alpha)
{
    bk_look l = look_of(e);
    uint32_t c = btn == VM_BTN_ACTION ? l.action : l.flip;
    int32_t fine = r >= DEG(22), down = (flags & GL_DOWN) != 0, pt = btn >= 0 && btn < 3 ? e->press_t[btn] : 1000;
    if (alpha <= 0) return;
    if (pt < 8 && !(flags & GL_DIM)) down = 1;                      /* a press pushes it in for a moment */
    if (flags & GL_DIM) { c = shade(c, 45); alpha = alpha * 3 / 4; }
    else if (flags & GL_LIT) c = lighten(c, 25);
    disc(e, cx, cy + DEG(4), r + DEG(3), with_alpha(0x000000a0u, alpha), PM_BLEND_NORMAL, fine);   /* its shadow */
    disc(e, cx, cy, r + DEG(3), with_alpha(shade(c, 35), alpha), PM_BLEND_NORMAL, fine);              /* the bezel */
    {
        int32_t rr = down ? r * 7 / 8 : r, dy = down ? DEG(2) : 0;
        disc(e, cx, cy + dy, rr, with_alpha(down ? shade(c, 80) : c, alpha), PM_BLEND_NORMAL, fine);
        if (!down) disc(e, cx - rr / 5, cy - rr / 3, rr / 3, with_alpha(0xffffff60u, alpha), PM_BLEND_ADD, 0);  /* the shine */
        if (!(flags & GL_NOLABEL)) {
            int32_t f = l.font >= 0 && l.font < e->doc.nfont ? l.font : 0, sc;
            int32_t lh = e->doc.nfont ? e->doc.font[f].line_h : DEG(32);
            sc = lh > 0 ? fxdiv(rr, lh) : ONE;
            text_str(e, f, btn == VM_BTN_LEFT ? VM_S_GLYPH_L : btn == VM_BTN_RIGHT ? VM_S_GLYPH_R : VM_S_GLYPH_A,
                     cx, cy + dy - vm_fxmul(lh, sc) / 2, 0, with_alpha(btn == VM_BTN_ACTION ? 0xffffffffu : 0x1d2230ffu, alpha), alpha, sc);
        }
    }
    if (progress >= 0) {
        int32_t w = 2 * r + DEG(8), x = cx - w / 2, y = cy + r + DEG(10);
        box(e, x, y, w, DEG(8), with_alpha(0x00000090u, alpha), PM_BLEND_NORMAL);
        box(e, x + DEG(1), y + DEG(1), vm_fxmul(w - DEG(2), clampi(progress, 0, ONE)), DEG(6), with_alpha(lighten(c, 30), alpha), PM_BLEND_NORMAL);
    }
}
/* the mash look: a ring thrown out by each press, fading as it grows */
static void mash_ring(vm_engine *e, int32_t btn, int32_t cx, int32_t cy, int32_t r)
{
    int32_t pt = e->press_t[btn];
    bk_look l = look_of(e);
    if (pt >= 14) return;
    disc(e, cx, cy, r + DEG(4 + pt * 2), with_alpha(btn == VM_BTN_ACTION ? l.action : l.flip, 110 - pt * 7), PM_BLEND_ADD, 1);
}
static int32_t btn_x(const vm_engine *e, int32_t btn, int32_t cx, int32_t gap)
{
    (void)e;
    return btn == VM_BTN_LEFT ? cx - gap : btn == VM_BTN_RIGHT ? cx + gap : cx;
}
static int32_t bob(const vm_engine *e) { return vm_fxmul(DEG(6), vm_sin(DEG((e->step_no * 12) % 360))); }
static void caption(vm_engine *e, int32_t sid, int32_t x, int32_t y, uint32_t colour, int32_t alpha)
{
    bk_look l = look_of(e);
    text_str(e, l.font, sid, x, y, 0, colour, alpha, ONE);
}

/* the prompts of a kind, centred on cx and standing on `bottom`: the HUD's prompts part, or the stage's foot
 * when it has none. Their words sit above the buttons, so a thin strip at the stage's foot holds them. */
static void bk_prompts(vm_engine *e, int32_t cx, int32_t bottom)
{
    const int32_t *s = S(e);
    int32_t gap = DEG(150), r = DEG(30), cy = bottom - r - DEG(10), below = cy - r - DEG(44);
    switch (e->doc.phase[e->phase].kind) {
    case VM_K_MASH: {
        int32_t b = s[1], x = btn_x(e, b, cx, gap);
        mash_ring(e, b, x, cy, r);
        draw_button(e, b, x, cy, r, GL_LIT, -1, 255);
        caption(e, VM_S_MASH, x, below, 0xffffffffu, 160 + (e->press_t[b] < 10 ? 95 : 0));
        break;
    }
    case VM_K_ALTERNATE: {
        int32_t next = e->alt_last < 0 ? -1 : 1 - e->alt_last, b;
        for (b = 0; b < 2; b++) {
            int32_t on = next < 0 || next == b;
            draw_button(e, b, btn_x(e, b, cx, gap), cy - (on && next >= 0 ? bob(e) : 0), r, on ? GL_LIT : GL_DIM, -1, 255);
        }
        caption(e, VM_S_ALTERNATE, cx, below, 0xffffffffu, 230);
        break;
    }
    case VM_K_TUG:
        if (e->bk_grab) {
            int32_t b;
            for (b = 0; b < 2; b++) {
                int32_t on = e->bk_last < 0 || e->bk_last != b;
                draw_button(e, b, btn_x(e, b, cx, gap), cy - (on ? bob(e) : 0), r, on ? GL_LIT : GL_DIM, -1, 255);
            }
            draw_button(e, VM_BTN_ACTION, cx, cy, r, GL_DIM, -1, 200);
            caption(e, VM_S_SHAKE, cx, below, 0xff8a5cffu, ((e->step_no >> 3) & 1) ? 255 : 150);
        } else {
            int32_t side = e->bk_side, hx = btn_x(e, side, cx, gap);
            draw_button(e, side, hx, cy, r, held(e, side) ? GL_DOWN | GL_LIT : GL_LIT, -1, 255);
            caption(e, VM_S_HOLD, hx, below, 0xffffffffu, held(e, side) ? 160 : ((e->step_no >> 4) & 1) ? 255 : 120);
            draw_button(e, 1 - side, btn_x(e, 1 - side, cx, gap), cy, r * 3 / 4, GL_DIM | GL_NOLABEL, -1, 140);
            mash_ring(e, VM_BTN_ACTION, cx, cy, r);
            draw_button(e, VM_BTN_ACTION, cx, cy, r, held(e, side) ? GL_LIT : GL_DIM, -1, 255);
            caption(e, VM_S_PULL, cx, below, 0xffffffffu, held(e, side) ? 255 : 110);
        }
        break;
    default: break;
    }
}

/* the kinds' own pictures: the rhythm's highway, the run of buttons, the tell, the judgement */
static void draw_rhythm(vm_engine *e, const int32_t *s)
{
    const vm_note *chart = &e->doc.note[s[1]];
    const uint8_t *st = &e->note_st[s[1]];
    int32_t W = DEG(e->doc.stage_w), H = DEG(e->doc.stage_h), cx = W / 2, gap = DEG(150), r = DEG(30);
    int32_t top = DEG(96), hit = H - DEG(150), span = hit - top, now = song_ms(e), i, b, k;
    bk_look l = look_of(e);
    box(e, cx - gap - DEG(70), top, 2 * gap + DEG(140), hit - top + DEG(60), 0x0000006eu, PM_BLEND_NORMAL);
    for (b = 0; b < 3; b++) box(e, btn_x(e, b, cx, gap) - DEG(2), top, DEG(4), span, 0xffffff22u, PM_BLEND_NORMAL);
    /* the beat grid: a line on every beat still to come in the window, the bar's first beat brighter */
    if (s[6] > 0) {
        int64_t beat_us = s[6];
        int64_t first = s[7], from = now, n0 = (from * 1000 - first * 1000) / beat_us;
        if (n0 < 0) n0 = 0;
        for (k = 0; k < 48; k++) {
            int64_t n = n0 + k, at = first + (n * beat_us) / 1000;
            int32_t y;
            if (at < now) continue;
            if (at - now > s[5]) break;
            y = hit - (int32_t)(((int64_t)(at - now) * span) / s[5]);
            box(e, cx - gap - DEG(60), y - DEG(1), 2 * gap + DEG(120), DEG(2), n % s[9] == 0 ? 0xffffff50u : 0xffffff1cu, PM_BLEND_NORMAL);
        }
    }
    box(e, cx - gap - DEG(66), hit - DEG(2), 2 * gap + DEG(132), DEG(4), 0xffffffa0u, PM_BLEND_NORMAL);
    for (b = 0; b < 3; b++) {                                  /* the targets on the hit line: the cabinet's buttons */
        int32_t x = btn_x(e, b, cx, gap);
        if (held(e, b)) disc(e, x, hit, r + DEG(10), with_alpha(b == VM_BTN_ACTION ? l.action : l.flip, 60), PM_BLEND_ADD, 1);
        draw_button(e, b, x, hit, r + DEG(4), held(e, b) ? GL_DOWN : GL_DIM, -1, 255);
    }
    for (i = s[2] - 1; i >= e->note_next; i--) {               /* far notes first, so near ones sit on top */
        int32_t dt = chart[i].at - now, x = btn_x(e, chart[i].button, cx, gap), y, a;
        if (dt > s[5] || st[i] == VM_NOTE_HIT || st[i] == VM_NOTE_MISSED) continue;
        y = hit - (int32_t)(((int64_t)dt * span) / s[5]);
        a = dt > s[5] * 3 / 4 ? clampi((s[5] - dt) * 255 / (s[5] / 4 + 1), 0, 255) : 255;
        if (chart[i].hold > 0) {
            int32_t ty = hit - (int32_t)(((int64_t)(chart[i].at + chart[i].hold - now) * span) / s[5]);
            if (ty < top) ty = top;
            if (st[i] == VM_NOTE_HOLDING) y = hit;
            box(e, x - DEG(10), ty, DEG(20), y - ty, with_alpha(chart[i].button == VM_BTN_ACTION ? l.action : l.flip, a * 2 / 3), PM_BLEND_NORMAL);
        }
        if (y > hit + DEG(40)) continue;
        draw_button(e, chart[i].button, x, y, r, (st[i] == VM_NOTE_HOLDING ? GL_DOWN : GL_LIT) | GL_NOLABEL, -1, a);
    }
}
static void draw_sequence(vm_engine *e, const int32_t *s)
{
    int32_t W = DEG(e->doc.stage_w), H = DEG(e->doc.stage_h), r = DEG(28), step = DEG(80), i;
    int32_t n = e->bk_len, x0 = W / 2 - ((n - 1) * step) / 2, y = H * 11 / 20;
    int32_t showing = e->bk_state == VM_BK_SHOW, visible = showing || (s[3] && s[4] == 0);
    if (n > 14) { step = DEG(56); r = DEG(20); x0 = W / 2 - ((n - 1) * step) / 2; }
    box(e, x0 - step / 2 - DEG(20), y - r - DEG(26), (n - 1) * step + step + DEG(40), 2 * r + DEG(52), 0x00000080u, PM_BLEND_NORMAL);
    for (i = 0; i < n; i++) {
        int32_t x = x0 + i * step, done = e->bk_state != VM_BK_SHOW && i < e->bk_i, next = e->bk_state == VM_BK_ENTER && i == e->bk_i;
        if (done) draw_button(e, e->seq[i], x, y, r, GL_LIT, -1, 255);
        else if (visible || (e->bk_state == VM_BK_RESULT && s[3])) draw_button(e, e->seq[i], x, y - (next ? bob(e) : 0), r, next ? GL_LIT : 0, -1, next || showing ? 255 : 170);
        else {                                                  /* hidden: enter it from memory */
            disc(e, x, y, r + DEG(3), 0x2a2f3dffu, PM_BLEND_NORMAL, 1);
            disc(e, x, y, r, next ? 0x56607aff : 0x3a4152ffu, PM_BLEND_NORMAL, 1);
        }
    }
    if (e->bk_state == VM_BK_ENTER && s[5] > 0)
        box(e, x0 - step / 2, y + r + DEG(14), vm_fxmul((n - 1) * step + step, fxdiv(e->bk_t, s[5])), DEG(5), 0xffd84ac0u, PM_BLEND_NORMAL);
    caption(e, showing ? VM_S_WATCH : e->bk_state == VM_BK_ENTER ? VM_S_GO : -1, W / 2, y - r - DEG(70), 0xffffffffu, 230);
}
static void draw_tell(vm_engine *e, const int32_t *s, int shield)
{
    int32_t W = DEG(e->doc.stage_w), H = DEG(e->doc.stage_h), b = e->bk_btn, r = DEG(44);
    int32_t x = btn_x(e, b, W / 2, W / 3), y = H * 3 / 5;
    if (e->bk_state == VM_BK_TELL) {
        int32_t blink = ((e->bk_t >> 2) & 1) ? 255 : 150;
        int32_t k, sw = W / 40, sh = H / 40;       /* a glow fading in from the side it comes from */
        for (k = 0; k < 5; k++) {
            uint32_t warn = 0xff5a3c00u | (uint32_t)(((5 - k) * blink) / 14);
            if (b == VM_BTN_LEFT) box(e, k * sw, 0, sw, H, warn, PM_BLEND_NORMAL);
            else if (b == VM_BTN_RIGHT) box(e, W - (k + 1) * sw, 0, sw, H, warn, PM_BLEND_NORMAL);
            else box(e, 0, k * sh, W, sh, warn, PM_BLEND_NORMAL);
        }
        draw_button(e, b, x, y, r, shield && held(e, b) ? GL_DOWN | GL_LIT : 0, -1, blink);
        caption(e, shield ? VM_S_HOLD : VM_S_DODGE, x, y - r - DEG(56), 0xffffffffu, blink);
    } else if (e->bk_state == VM_BK_WINDOW) {
        int32_t left = shield ? fxdiv(s[2] - e->bk_t, s[2]) : fxdiv(e->bk_t, s[2]);
        if (!shield) disc(e, x, y, r + DEG(8 + ((e->step_no & 3) * 3)), 0xffd84a50u, PM_BLEND_ADD, 1);
        draw_button(e, b, x, y, r, held(e, b) ? GL_DOWN | GL_LIT : GL_LIT, left, 255);
        caption(e, shield ? VM_S_BLOCK : VM_S_DODGE, x, y - r - DEG(56), 0xffd84aff, 255);
    }
}
static void draw_kinds2(vm_engine *e)
{
    const int32_t *s;
    int32_t i, k = e->doc.phase[e->phase].kind, prompts = 0;
    if (!bk_kind(k)) return;
    s = S(e);
    if (e->state == VM_ST_PLAY || e->state == VM_ST_OUTRO || (e->state == VM_ST_TITLE && k == VM_K_RHYTHM)) {
        switch (k) {
        case VM_K_RHYTHM: draw_rhythm(e, s); break;
        case VM_K_SEQUENCE: if (e->state == VM_ST_PLAY) draw_sequence(e, s); break;
        case VM_K_DODGE: if (e->state == VM_ST_PLAY) draw_tell(e, s, 0); break;
        case VM_K_SHIELD: if (e->state == VM_ST_PLAY) draw_tell(e, s, 1); break;
        default: break;
        }
    }
    for (i = 0; i < e->doc.nhud; i++) if (e->doc.hud[i].part == VM_HUD_PROMPTS) prompts = 1;
    if (!prompts && e->state == VM_ST_PLAY) bk_prompts(e, DEG(e->doc.stage_w) / 2, DEG(e->doc.stage_h) - DEG(20));
    if (e->judge_t > 0 && e->judge_word >= 0 && e->state == VM_ST_PLAY) {
        int32_t W = DEG(e->doc.stage_w), age = BK_JUDGE_STEPS - e->judge_t;
        int32_t x = k == VM_K_RHYTHM ? btn_x(e, e->judge_x == -1 ? 0 : e->judge_x == 1 ? 1 : 2, W / 2, DEG(150)) : W / 2;
        int32_t y = k == VM_K_RHYTHM ? DEG(e->doc.stage_h) - DEG(250) : DEG(e->doc.stage_h) / 3;
        int32_t sc = age < 8 ? vm_ease(VM_EASE_BACK_OUT, (age * ONE) / 8) : ONE;
        if (sc < ONE / 8) sc = ONE / 8;
        text_str(e, e->doc.callout_font, e->judge_word, x, y - age * DEG(1), 0, (uint32_t)e->judge_col, e->judge_t < 10 ? e->judge_t * 25 : 255, sc);
    }
}
