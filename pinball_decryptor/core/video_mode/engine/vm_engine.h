/* vm_engine.h - the video mode engine (PAD-1657, epic PAD-1654).
 *
 * One plain C core plays a compiled video_mode.json. It is built three ways from the
 * same files: native (tests, the text harness), WebAssembly (the app's player) and as an
 * object the machine's mode runtime links. So what plays in the editor is the machine's
 * own code.
 *
 * The rules it is built under are mode.so's (tools/spike2_emu/modes/sdk/MODE_SDK.md):
 * no malloc, no stdio, no threads, no floats in the rules. Every table is a fixed size
 * (below), all state is 16.16 fixed point and whole steps, and the only things it may
 * need from a libc are memset and memcpy (which a compiler emits by itself).
 *
 * Use:
 *     static vm_engine e;                       (about 0.6 MB: keep it static)
 *     vm_load(&e, pack, pack_len);              the packed form compiler.py writes
 *     vm_start(&e, play_seed, level);
 *     every 1/60 s: vm_step(&e, input);         input = VM_IN_* bits held this step
 *         e.list (the draw list), e.events[], e.cues[] are this step's output
 *
 * The engine never draws: e.list is the draw list of docs/plans/video_mode_maker.md
 * section 4, and a backend per place draws it.
 */
#ifndef VM_ENGINE_H
#define VM_ENGINE_H

#include <stddef.h>
#include <stdint.h>

#define VM_PACK_MAGIC   0x31504D56u   /* "VMP1" little end first */
#define VM_PACK_VERSION 2   /* 2 (PAD-1667): phases carry their music's fade, cues their fade */

/* ---- limits: sized from the largest column of the plan's budgets (section 5) ---- */
#define VM_MAX_THINGS     512   /* alive at once (the desk budget is 300) */
#define VM_MAX_KINDS      96    /* the document's things */
#define VM_MAX_PICTURES   96
#define VM_MAX_ANIMS      192
#define VM_MAX_FRAMES     2048
#define VM_MAX_VALUES     48
#define VM_MAX_MOVERS     192
#define VM_MAX_PATHPTS    1024
#define VM_MAX_PHASES     32
#define VM_MAX_LAYERS     128
#define VM_MAX_PLACES     1024
#define VM_MAX_SPAWNS     256
#define VM_MAX_CONDS      256
#define VM_MAX_SETTINGS   32    /* one record per phase */
#define VM_SETTING_WORDS  32
#define VM_MAX_WEAKPTS    64
#define VM_MAX_ATTACKS    64
#define VM_MAX_CARDS      96
#define VM_MAX_HUD        64
#define VM_MAX_CUES       64
#define VM_MAX_FONTS      8
#define VM_GLYPHS         95    /* ' ' .. '~' */
#define VM_MAX_STRBYTES   8192
#define VM_MAX_STRINGS    256
#define VM_MAX_SOUNDS     64
#define VM_MAX_CLIPS      32
#define VM_MAX_PARTICLES  256
#define VM_MAX_ENTRIES    3072  /* quads + boxes in one draw list */
#define VM_MAX_EVENTS     64    /* a step */
#define VM_MAX_SNDCUES    16    /* a step */
#define VM_LANES_MAX      7
/* PAD-1664, the timeline: keyframed motion of placed things, and sounds at set times */
#define VM_MAX_TRACKS     256
#define VM_MAX_KEYS       4096
#define VM_MAX_CURVES     128
#define VM_CURVE_PTS      33    /* an easing curve baked to 33 heights at even steps across */
#define VM_MAX_TSOUNDS    256

/* ---- input: one word a step ---- */
#define VM_IN_LEFT      0x01u   /* left flipper button held */
#define VM_IN_RIGHT     0x02u   /* right flipper button held */
#define VM_IN_ACTION    0x04u   /* Action button held */
#define VM_IN_CLIP_DONE 0x08u   /* the host: the clip it was asked to play has ended */

/* ---- codes shared with compiler.py (keep the two in step) ---- */
enum { VM_TEAM_PLAYER, VM_TEAM_ENEMY, VM_TEAM_ENEMY_SHOT, VM_TEAM_PLAYER_SHOT,
       VM_TEAM_PICKUP, VM_TEAM_HEALTH, VM_TEAM_SCENERY };
enum { VM_MV_NONE, VM_MV_STRAIGHT, VM_MV_LANES, VM_MV_FREE, VM_MV_THRUST, VM_MV_PATH,
       VM_MV_HOME, VM_MV_SCROLL, VM_MV_ORBIT };
enum { VM_EASE_LINEAR, VM_EASE_IN, VM_EASE_OUT, VM_EASE_IN_OUT, VM_EASE_BACK_OUT,
       VM_EASE_BOUNCE_OUT, VM_EASE_ELASTIC_OUT, VM_EASE_STEP };
enum { VM_K_CHASE, VM_K_THRUST, VM_K_AIM, VM_K_BOSS, VM_K_MASH, VM_K_ALTERNATE, VM_K_TUG,
       VM_K_RHYTHM, VM_K_SEQUENCE, VM_K_DODGE, VM_K_SHIELD, VM_K_TIMING, VM_K_DEFEND,
       VM_K_CATCH, VM_K_RUNNER, VM_K_LANDER, VM_K_ROUTE, VM_K_PICK, VM_K_CUSTOM };
enum { VM_W_TIME_UP, VM_W_SURVIVE, VM_W_SCORE, VM_W_KILLS, VM_W_PICKUPS, VM_W_GOAL,
       VM_W_HEALTH_GONE, VM_W_MISSES, VM_W_BOSS_DOWN, VM_W_HITS, VM_W_ACCURACY,
       VM_W_AMMO_OUT, VM_W_LANDED, VM_W_CRASHED, VM_W_CASHED_OUT, VM_W_BUSTED };
enum { VM_CARD_CLIP, VM_CARD_PHASE, VM_CARD_END };
enum { VM_TK_MOTION, VM_TK_SCALE, VM_TK_TURN, VM_TK_ALPHA, VM_TK_TINT };
enum { VM_HUD_HEALTH, VM_HUD_METER, VM_HUD_SCORE, VM_HUD_COMBO, VM_HUD_TIMER, VM_HUD_LIVES,
       VM_HUD_PROGRESS, VM_HUD_PROMPTS, VM_HUD_CALLOUT, VM_HUD_COUNTER, VM_HUD_TEXT };
enum { VM_LOOK_DEFAULT, VM_LOOK_BAR, VM_LOOK_PIPS, VM_LOOK_HEARTS, VM_LOOK_RING,
       VM_LOOK_NUMBER, VM_LOOK_GLYPHS };
enum { VM_TR_CUT, VM_TR_FADE, VM_TR_WHITE_FLASH, VM_TR_WIPE, VM_TR_IRIS };
enum { VM_BTN_LEFT, VM_BTN_RIGHT, VM_BTN_ACTION };
/* fixed strings the compiler puts first in the string table */
enum { VM_S_CLEAR, VM_S_FAILED, VM_S_TRY_AGAIN, VM_S_STEER, VM_S_FIRE, VM_S_LEFT,
       VM_S_RIGHT, VM_S_ACTION, VM_S_MASH, VM_S_BOSS_DOWN, VM_S_HOLD, VM_S_COUNT };

/* ---- events for the pinball side, and the triggers sounds are cued on ---- */
enum {
    VM_EV_CLIP_START = 1,  /* a: clip, b: 1 = skippable. The host plays it, then sets VM_IN_CLIP_DONE */
    VM_EV_CLIP_STOP,       /* a: clip, b: 1 = skipped by the player */
    VM_EV_PHASE_START,     /* a: phase, b: try (0 = first) */
    VM_EV_PHASE_WON,       /* a: phase, b: steps left on its clock, c: health left */
    VM_EV_PHASE_LOST,      /* a: phase, b: tries left */
    VM_EV_SCORE,           /* a: points added, b: the mode's total */
    VM_EV_KILL,            /* a: thing kind, b: points */
    VM_EV_PICKUP,          /* a: thing kind, b: pickups of it so far in the mode */
    VM_EV_HURT,            /* a: health left */
    VM_EV_FIRE,            /* a: shot kind */
    VM_EV_HIT,             /* a: weak point (boss) or thing kind, b: hits left */
    VM_EV_FINISHED,        /* a: 1 won / 0 lost, b: the mode's score, c: 1 = no hit taken */
    VM_EV_PROMPT_GOOD,
    VM_EV_PROMPT_PERFECT,
    VM_EV_PROMPT_MISS,
    VM_EV__COUNT
};
/* a cue's "on" is one of: */
enum { VM_ON_FIRE, VM_ON_HIT, VM_ON_KILL, VM_ON_PICKUP, VM_ON_HURT, VM_ON_PROMPT_GOOD,
       VM_ON_PROMPT_PERFECT, VM_ON_PROMPT_MISS, VM_ON_PHASE_START, VM_ON_PHASE_WON,
       VM_ON_PHASE_LOST, VM_ON_WON, VM_ON_LOST };
/* a sound cue's op (PAD-1667): PLAY a sound once; MUSIC: this bed is the music now (the one before, if any,
 * fades out over `fade` steps as this one fades in - a music change happens only when the bed changes, so a phase
 * tried again, or one with the same music, plays on); MUSIC_STOP: the music fades out over `fade` steps (a
 * cutscene, a phase without music, the end). `duck`: the music goes down under this sound. */
enum { VM_SND_PLAY, VM_SND_MUSIC, VM_SND_MUSIC_STOP };

typedef struct { int32_t type, a, b, c; } vm_event;
typedef struct { int32_t sound, op, duck, fade; } vm_sndcue;

/* ---- the draw list (plan section 4) ---- */
enum { PM_BLEND_NORMAL, PM_BLEND_ADD };
typedef struct {            /* one quad: everything on the stage is one of these */
    uint16_t atlas;         /* which packed atlas (PAD-1658) */
    uint16_t blend;         /* PM_BLEND_NORMAL or PM_BLEND_ADD */
    uint16_t sx, sy, sw, sh;/* source box in the atlas, texels */
    int32_t  x, y;          /* where the anchor lands, stage px, 16.16 */
    int32_t  ax, ay;        /* the anchor inside the source box, 0..1 in 16.16 */
    int32_t  scale_x, scale_y; /* 16.16; negative flips */
    int32_t  turn;          /* degrees clockwise, 16.16 */
    uint32_t tint;          /* 0xRRGGBBAA, straight alpha; 0xFFFFFFFF = none */
    uint8_t  alpha;         /* 0..255, multiplies the tint's alpha */
    int16_t  depth;         /* already applied to the order; kept for debugging */
} pm_vm_quad;
typedef struct {            /* a filled box: bars, meters, flashes, letterbox */
    int32_t x, y, w, h;     /* stage px, 16.16 */
    uint32_t colour;        /* 0xRRGGBBAA, straight alpha */
    uint16_t blend;
} pm_vm_box;
typedef struct {            /* once per list */
    int32_t shake_x, shake_y;   /* camera offset this step, stage px 16.16 */
    uint32_t flash;             /* a full-stage colour over everything, 0 = none */
    uint32_t clear;             /* the stage background */
    uint16_t cover_game;        /* 1 = hide the game's own display (PAD-1655) */
} pm_vm_frame;
enum { PM_VM_QUAD = 1, PM_VM_BOX = 2 };
typedef struct {
    uint16_t tag;               /* PM_VM_QUAD or PM_VM_BOX */
    union { pm_vm_quad q; pm_vm_box b; } u;
} pm_vm_entry;
typedef struct {
    pm_vm_frame frame;
    uint32_t step;              /* the engine step this list is */
    uint32_t n;                 /* entries in draw order */
    uint32_t dropped;           /* entries that did not fit (VM_MAX_ENTRIES) */
    pm_vm_entry e[VM_MAX_ENTRIES];
} pm_vm_list;

/* ---- the packed document, as read (fields are the engine's own) ---- */
typedef struct { int32_t shape, x, y, w, h; } vm_hitbox;  /* shape -1 none, 0 box, 1 circle (w = r) */
typedef struct { int32_t atlas, w, h, cols, frames, sx0, sy0, ax, ay, texel; vm_hitbox hit; } vm_picture;
typedef struct { int32_t fps, loop, first, count; } vm_anim;
typedef struct { int32_t type, start, min, max, drain; } vm_value;
typedef struct { int32_t picture, anim, scale, team, health, points, blend, depth, mover, counter; vm_hitbox hit; } vm_kind;
typedef struct { int32_t type, speed, dir, path0, npath, easing, loop, target, turn, radius; } vm_mover;
typedef struct { int32_t x, y, cum; } vm_pathpt;
typedef struct { int32_t kind, title, objective, length, music, bg0, nbg, place0, nplace,
                 spawn0, nspawn, win0, nwin, lose0, nlose, layout, ramp_from, ramp_to, settings,
                 music_fade,            /* steps its music fades in (and out) over */
                 track0, ntrack, tsnd0, ntsnd; } vm_phase;
/* PAD-1664: a track drives one property of one placed thing (place: its index among the phase's places) through
 * its keys. A key holds its time (steps into the phase's play), its value (a: x, scale, turn, alpha 0..1 or the tint
 * 0xRRGGBBAA; b: y), the easing into the next key (a preset, or curve >= 0: a baked curve), and for motion the
 * bezier handles about it, out (ox, oy) towards the next key and in (ix, iy) from the one before. */
typedef struct { int32_t place, prop, key0, nkey; } vm_track;
typedef struct { int32_t at, a, b, ease, curve, ox, oy, ix, iy; } vm_key;
typedef struct { int32_t y[VM_CURVE_PTS]; } vm_curve;
typedef struct { int32_t at, sound; } vm_tsound;
typedef struct { int32_t picture, speed, y, tile, alpha; } vm_layer;
typedef struct { int32_t kind, x, y, scale, turn, depth, hidden; } vm_place;
typedef struct { int32_t kind, at, every, count, x, y, spread, lane, mover; } vm_spawn;
typedef struct { int32_t when, value, of_kind, of_value; } vm_cond;
typedef struct { int32_t x, y, r, hits, open, closed, offset; } vm_weakpt;
typedef struct { int32_t kind, every, aim; } vm_attack;
typedef struct { int32_t type, a, next, lost, tries, skippable; } vm_card;
typedef struct { int32_t part, x, y, w, h, value, look, font, colour, accent, text, phases; } vm_hud;
typedef struct { int32_t on, sound, duck; } vm_cue;
typedef struct { int32_t adv, sx, sy, sw, sh; } vm_glyph;
typedef struct { int32_t size, line_h, atlas, texel; vm_glyph g[VM_GLYPHS]; } vm_font;
typedef struct { int32_t off, len; } vm_str;

typedef struct {
    int32_t sps, stage_w, stage_h, background, seed, style, transition, skip_clips,
            speed_step_pct, start_card, nsounds, nclips, callout_font, title_font;
    int32_t nstr, nfont, npic, nanim, nframe, nvalue, nkind, nmover, npath, nphase, nlayer,
            nplace, nspawn, ncond, nsettings, nweak, natk, ncard, nhud, ncue, ntrack, nkey, ncurve, ntsnd;
    char strbytes[VM_MAX_STRBYTES];
    vm_str str[VM_MAX_STRINGS];
    vm_font font[VM_MAX_FONTS];
    vm_picture pic[VM_MAX_PICTURES];
    vm_anim anim[VM_MAX_ANIMS];
    int32_t frame[VM_MAX_FRAMES];
    vm_value value[VM_MAX_VALUES];
    vm_kind kind[VM_MAX_KINDS];
    vm_mover mover[VM_MAX_MOVERS];
    vm_pathpt path[VM_MAX_PATHPTS];
    vm_phase phase[VM_MAX_PHASES];
    vm_layer layer[VM_MAX_LAYERS];
    vm_place place[VM_MAX_PLACES];
    vm_spawn spawn[VM_MAX_SPAWNS];
    vm_cond cond[VM_MAX_CONDS];
    int32_t settings[VM_MAX_SETTINGS][VM_SETTING_WORDS];
    vm_weakpt weak[VM_MAX_WEAKPTS];
    vm_attack atk[VM_MAX_ATTACKS];
    vm_card card[VM_MAX_CARDS];
    vm_hud hud[VM_MAX_HUD];
    vm_cue cue[VM_MAX_CUES];
    vm_track track[VM_MAX_TRACKS];
    vm_key key[VM_MAX_KEYS];
    vm_curve curve[VM_MAX_CURVES];
    vm_tsound tsnd[VM_MAX_TSOUNDS];
} vm_doc;

/* ---- the running game ---- */
typedef struct {
    int32_t alive, kind, team, serial;
    int32_t x, y, vx, vy;        /* 16.16 px, px a step */
    int32_t ox, oy;              /* where it started: path offset, orbit centre */
    int32_t scale, turn, depth, hidden;
    int32_t health, age, blink;
    int32_t mover;               /* index into doc.mover, or -1 */
    int32_t heading;             /* 16.16 degrees: straight and home movers */
    int32_t target;              /* thing slot a homer chases, -1 none */
    int32_t role;                /* 0, or VM_ROLE_* */
    int32_t place;               /* PAD-1664: the phase's place it was put on the stage from, or -1 (spawned) */
    int32_t alpha;               /* 0..255, its tracks' own */
    int32_t tint;                /* 0xRRGGBBAA, its tracks' own; -1 (0xFFFFFFFF) none */
    int32_t keyed;               /* 1: a motion track places it, and it is not lost off the stage */
} vm_thing;
enum { VM_ROLE_NONE, VM_ROLE_PLAYER, VM_ROLE_BOSS, VM_ROLE_SIGHT };
typedef struct { int32_t alive, x, y, vx, vy, life, colour; } vm_particle;

enum { VM_ST_IDLE, VM_ST_CLIP, VM_ST_TITLE, VM_ST_PLAY, VM_ST_OUTRO, VM_ST_DONE };

typedef struct vm_engine {
    vm_doc doc;
    int32_t err, err_at;             /* vm_load's verdict and the word it stopped at */
    int32_t loaded;
    /* the play */
    uint32_t rng, play_seed;
    int32_t level, speed_pct;
    int32_t state, state_t, card, phase, try_no, outcome, flawless;
    int32_t t;                       /* steps into the phase's play */
    uint32_t step_no;
    uint32_t in, in_prev, pressed, released;
    int32_t score, phase_score;
    int32_t health, health_max, blink_steps;
    int32_t player, boss, sight;     /* thing slots, -1 none */
    int32_t fire_cd, ammo, ammo_max, gear;
    int32_t lane, nlanes, lane_y[VM_LANES_MAX];
    int32_t values[VM_MAX_VALUES];   /* 16.16 */
    int32_t kills[VM_MAX_KINDS], pickups[VM_MAX_KINDS], pickups_total[VM_MAX_KINDS];
    int32_t kills_all, pickups_all, hits, misses, shots, boss_down, goal_hit, crashed, phase_result;
    int32_t weak_hits[VM_MAX_WEAKPTS], stage_no;
    int32_t alt_last, alt_half, rival;
    int32_t combo, combo_t, hitstop, shake, shake_x, shake_y, flash_a, flash_col;
    int32_t callout, callout_t;      /* a string shown big, steps left */
    int32_t music, music_fade;       /* the music bed playing (-1 none) and the steps it fades out over */
    int32_t spawned[VM_MAX_SPAWNS];
    int32_t place_th[VM_MAX_PLACES]; /* PAD-1664: the thing slot each of the phase's places went to, -1 none */
    int32_t edit_flags;              /* PAD-1664: the editor's seek (VM_SEEK_*); 0 in a game */
    int32_t serial;
    int32_t nthings;
    vm_thing th[VM_MAX_THINGS];
    vm_particle pt[VM_MAX_PARTICLES];
    int32_t order[VM_MAX_THINGS];
    /* this step's output */
    pm_vm_list list;
    vm_event events[VM_MAX_EVENTS];
    int32_t nevents, events_dropped;
    int32_t held_events;             /* vm_start's own events, handed out with the first step */
    vm_sndcue cues[VM_MAX_SNDCUES];
    int32_t ncues;
    uint64_t hash;                   /* FNV-1a over every step's draw list words and events */
} vm_engine;

/* vm_load's verdicts */
enum { VM_OK = 0, VM_ERR_MAGIC, VM_ERR_VERSION, VM_ERR_SHORT, VM_ERR_LIMIT, VM_ERR_INDEX,
       VM_ERR_VALUE };

int vm_load(vm_engine *e, const uint8_t *pack, uint32_t len);
void vm_start(vm_engine *e, uint32_t play_seed, int32_t level);
int vm_step(vm_engine *e, uint32_t input);           /* 1 while the mode runs, 0 when done */
/* The canonical byte form of this step's draw list (32-bit words, little end first):
 * what the WebAssembly side hands to JavaScript, and what the match check hashes.
 * Returns the words written (or needed, if over cap). */
uint32_t vm_list_words(const vm_engine *e, int32_t *out, uint32_t cap);
/* 0 when every thing, count and index is inside its bounds (the fuzz run's check) */
int vm_check(const vm_engine *e);
/* 1 when boss weak point i is open this step */
int vm_weak_open(const vm_engine *e, int32_t i);
/* the editor's still (PAD-1661): phase `phase` as its first step leaves it, past the opening transition, with
 * the title card when flags & 1. Builds the draw list and steps nothing; play state is the phase's start.
 * Never called on a machine. 0 when there is no such phase. */
int vm_edit_still(vm_engine *e, int32_t phase, int32_t flags);
/* the editor's timeline (PAD-1664): scrubbing is replaying. vm_edit_seek_begin puts phase `phase` at the first step
 * of its play exactly as starting on its card and pressing nothing for the title card's 90 steps leaves it;
 * vm_edit_seek_step plays one step of it with no button held (and, with VM_SEEK_ENDLESS, never ends the phase, so
 * the whole of its timeline can be seen); vm_edit_seek_draw builds the draw list of where it is. Between them they
 * draw what the game draws at that step with nothing pressed. Never called on a machine. */
#define VM_SEEK_ENDLESS 2
int vm_edit_seek_begin(vm_engine *e, int32_t phase, int32_t flags);
void vm_edit_seek_step(vm_engine *e);
void vm_edit_seek_draw(vm_engine *e);
/* where the play state lives in the engine (for the editor's snapshots): from `err` up to the draw list */
#define VM_STATE_FIRST(e) ((uint8_t *)&(e)->err)
#define VM_STATE_BYTES    (offsetof(vm_engine, list) - offsetof(vm_engine, err))

/* fixed point helpers, shared with the bot and the harness */
#define VM_FX(n) ((int32_t)((n) * 65536))
int32_t vm_fxmul(int32_t a, int32_t b);
int32_t vm_sin(int32_t deg);
int32_t vm_cos(int32_t deg);
int32_t vm_atan2(int32_t y, int32_t x);
int32_t vm_ease(int32_t kind, int32_t t);

#endif
