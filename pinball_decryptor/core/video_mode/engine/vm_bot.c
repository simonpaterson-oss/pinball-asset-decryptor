/* vm_bot.c - see vm_bot.h. */
#include "vm_bot.h"

#define ONE 65536

static int32_t absi(int32_t v) { return v < 0 ? -v : v; }

void vm_bot_init(vm_bot *b, int32_t clip_steps)
{
    int32_t i;
    b->last = 0; b->clip_steps = clip_steps; b->tick = 0;
    for (i = 0; i < VM_MAX_THINGS; i++) { b->px[i] = 0; b->serial[i] = -1; }
}

/* fire when a shot let go now meets an enemy as it crosses the player's column */
static int aimed(const vm_bot *b, const vm_engine *e, int32_t shot_kind)
{
    const vm_thing *pl = &e->th[e->player];
    int32_t speed, i, any = 0;
    if (shot_kind < 0 || e->doc.kind[shot_kind].mover < 0) return 1;
    speed = e->doc.mover[e->doc.kind[shot_kind].mover].speed;
    if (speed <= 0) return 1;
    for (i = 0; i < VM_MAX_THINGS; i++) {
        const vm_thing *t = &e->th[i];
        int32_t vx, arrive, flight;
        if (!t->alive || t->team != VM_TEAM_ENEMY || b->serial[i] != t->serial || t->y > pl->y) continue;
        any = 1;
        vx = t->x - b->px[i];
        if (vx == 0) continue;
        arrive = (pl->x - t->x) / vx;                    /* steps until it is over the player */
        flight = (pl->y - 24 * ONE - t->y) / speed;      /* steps a shot takes to climb to it */
        if (arrive >= 0 && absi(arrive - flight) <= 1) return 1;
    }
    return !any;
}


/* a press is an edge: let go first if it is held already */
static uint32_t tap(const vm_bot *b, uint32_t bit) { return (b->last & bit) ? 0 : bit; }

static uint32_t chase(vm_bot *b, const vm_engine *e)
{
    const int32_t *s = e->doc.settings[e->doc.phase[e->phase].settings];
    const vm_thing *pl;
    int32_t danger[VM_LANES_MAX], i, best, l;
    uint32_t in = 0;
    if (e->player < 0 || e->nlanes <= 0) return s[4] == 1 ? VM_IN_ACTION : 0;
    pl = &e->th[e->player];
    if (s[4] == 1 && aimed(b, e, s[5])) in |= VM_IN_ACTION;
    for (l = 0; l < e->nlanes; l++) danger[l] = 0;
    for (i = 0; i < VM_MAX_THINGS; i++) {
        const vm_thing *t = &e->th[i];
        int32_t dx, near = 0, nd = 0x7fffffff;
        if (!t->alive || i == e->player) continue;
        if (t->team != VM_TEAM_ENEMY && t->team != VM_TEAM_ENEMY_SHOT && t->team != VM_TEAM_PICKUP && t->team != VM_TEAM_HEALTH) continue;
        dx = t->x - pl->x;
        if (dx < -120 * ONE || dx > 700 * ONE) continue;
        for (l = 0; l < e->nlanes; l++) if (absi(e->lane_y[l] - t->y) < nd) { nd = absi(e->lane_y[l] - t->y); near = l; }
        if (nd > 70 * ONE) continue;
        if (t->team == VM_TEAM_PICKUP || t->team == VM_TEAM_HEALTH) danger[near] -= 3;
        else danger[near] += dx < 260 * ONE ? 40 : 10;
    }
    best = e->lane;
    for (l = 0; l < e->nlanes; l++)
        if (danger[l] < danger[best] || (danger[l] == danger[best] && absi(l - e->lane) < absi(best - e->lane))) best = l;
    if (s[1] == 0) {
        if (best < e->lane) in |= tap(b, VM_IN_LEFT);
        else if (best > e->lane) in |= tap(b, VM_IN_RIGHT);
    } else if (s[1] == 2) {
        if (best == 0) in |= VM_IN_LEFT; else if (best == e->nlanes - 1) in |= VM_IN_RIGHT;
    } else {
        if (e->lane_y[best] < pl->y - 8 * ONE) in |= VM_IN_LEFT;
        else if (e->lane_y[best] > pl->y + 8 * ONE) in |= VM_IN_RIGHT;
    }
    return in;
}

static uint32_t boss(vm_bot *b, const vm_engine *e)
{
    const int32_t *s = e->doc.settings[e->doc.phase[e->phase].settings];
    uint32_t in = 0;
    int32_t i;
    if (e->player >= 0) {     /* keep clear of whatever is coming */
        const vm_thing *pl = &e->th[e->player];
        int32_t nearest = -1, nd = 0x7fffffff;
        for (i = 0; i < VM_MAX_THINGS; i++) {
            const vm_thing *t = &e->th[i];
            int32_t d;
            if (!t->alive || t->team != VM_TEAM_ENEMY_SHOT) continue;
            d = absi(t->x - pl->x) + absi(t->y - pl->y);
            if (d < nd) { nd = d; nearest = i; }
        }
        if (nearest >= 0 && nd < 420 * ONE) in |= e->th[nearest].x > pl->x ? VM_IN_LEFT : VM_IN_RIGHT;
        else if (pl->x < (e->doc.stage_w / 2 - 200) * ONE) in |= VM_IN_RIGHT;
        else if (pl->x > (e->doc.stage_w / 2 + 200) * ONE) in |= VM_IN_LEFT;
        /* pinned against a wall with a shell closing in: run the other way under it */
        if (nearest >= 0 && (pl->x <= 40 * ONE || pl->x >= (e->doc.stage_w - 40) * ONE)) in ^= VM_IN_LEFT | VM_IN_RIGHT;
    }
    if (s[1] == 1) return in | VM_IN_ACTION;
    if (e->boss >= 0 && e->sight >= 0) {
        const vm_thing *bo = &e->th[e->boss], *si = &e->th[e->sight];
        for (i = 0; i < s[4]; i++) {
            const vm_weakpt *w = &e->doc.weak[s[3] + i];
            int64_t dx = (int64_t)(si->x - (bo->x + w->x)), dy = (int64_t)(si->y - (bo->y + w->y)), r = w->r - 6 * ONE;
            if (e->weak_hits[s[3] + i] > 0 && vm_weak_open(e, s[3] + i) && dx * dx + dy * dy <= r * r) { in |= tap(b, VM_IN_ACTION); break; }
        }
    }
    return in;
}

/* the button kinds (PAD-1663): a good player, not a perfect one where the kind has no timing to it */
static uint32_t bit(int32_t btn) { return btn == VM_BTN_LEFT ? VM_IN_LEFT : btn == VM_BTN_RIGHT ? VM_IN_RIGHT : VM_IN_ACTION; }
static uint32_t tug(vm_bot *b, const vm_engine *e)
{
    if (e->bk_grab) return (b->tick % 8) == 0 ? VM_IN_LEFT : (b->tick % 8) == 4 ? VM_IN_RIGHT : 0;
    return bit(e->bk_side) | ((b->tick % 8) == 0 ? tap(b, VM_IN_ACTION) : 0);   /* a person mashes about 7 a second */
}
static uint32_t rhythm(vm_bot *b, const vm_engine *e)
{
    const int32_t *s = e->doc.settings[e->doc.phase[e->phase].settings];
    int32_t next = (int32_t)(((int64_t)(e->song_steps + 1) * 1000) / e->doc.sps) - e->audio_offset_ms, i;
    uint32_t in = 0, want = 0;
    for (i = e->note_next; i < s[2]; i++) {
        const vm_note *n = &e->doc.note[s[1] + i];
        int32_t st = e->note_st[s[1] + i];
        if (n->at - next > 40) break;
        if (st == VM_NOTE_HOLDING) in |= bit(n->button);
        else if (st == VM_NOTE_WAIT && n->at - next <= 8 && n->at - next > -9) want |= bit(n->button);
    }
    /* a press is an edge: a button still held from the last note is let go a step first */
    return in | (want & ~b->last);
}
static uint32_t sequence(vm_bot *b, const vm_engine *e)
{
    if (e->bk_state != VM_BK_ENTER || e->bk_i >= e->bk_len) return 0;
    return (b->tick % 6) == 0 ? tap(b, bit(e->seq[e->bk_i])) : 0;
}
static uint32_t dodge(vm_bot *b, const vm_engine *e)
{
    const int32_t *s = e->doc.settings[e->doc.phase[e->phase].settings];
    if (e->bk_state != VM_BK_WINDOW || s[2] - e->bk_t < 2) return 0;
    return tap(b, bit(e->bk_btn));
}
static uint32_t shield(const vm_engine *e)
{
    const int32_t *s = e->doc.settings[e->doc.phase[e->phase].settings];
    return e->bk_state == VM_BK_TELL || e->bk_state == VM_BK_WINDOW ? bit(s[0]) : 0;
}
uint32_t vm_bot_input(vm_bot *b, const vm_engine *e)
{
    uint32_t in = 0;
    int32_t i;
    b->tick++;
    switch (e->state) {
    case VM_ST_CLIP:
        if (e->state_t >= b->clip_steps) in = VM_IN_CLIP_DONE;
        break;
    case VM_ST_PLAY:
        switch (e->doc.phase[e->phase].kind) {
        case VM_K_CHASE: in = chase(b, e); break;
        case VM_K_BOSS: in = boss(b, e); break;
        case VM_K_ALTERNATE: in = (b->tick % 8) == 0 ? VM_IN_LEFT : (b->tick % 8) == 4 ? VM_IN_RIGHT : 0; break;
        case VM_K_MASH: in = (b->tick % 4) == 0 ? VM_IN_ACTION : 0; break;
        case VM_K_THRUST:
            if (e->player >= 0 && e->th[e->player].y > (e->doc.stage_h / 2) * ONE) in = VM_IN_ACTION;
            in |= (b->tick & 1) ? VM_IN_RIGHT : 0;
            break;
        case VM_K_TUG: in = tug(b, e); break;
        case VM_K_RHYTHM: in = rhythm(b, e); break;
        case VM_K_SEQUENCE: in = sequence(b, e); break;
        case VM_K_DODGE: in = dodge(b, e); break;
        case VM_K_SHIELD: in = shield(e); break;
        default: in = (b->tick % 6) == 0 ? VM_IN_ACTION : 0; break;
        }
        break;
    default: break;
    }
    for (i = 0; i < VM_MAX_THINGS; i++) { b->px[i] = e->th[i].x; b->serial[i] = e->th[i].alive ? e->th[i].serial : -1; }
    b->last = in;
    return in;
}
