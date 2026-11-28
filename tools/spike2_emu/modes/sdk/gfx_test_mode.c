/* gfx_test_mode.c - PAD-1655's proof of moving pictures on the glass (pm_gfx_*).
 *
 * /dump/gfx_test.start (a game running): the mode begins and loads /dump/gfx_test.padgfx (gfx_set.py's
 * placeholder set: original shapes and a font of the card's), then runs a timeline:
 *
 *     0 .. BASE s           nothing drawn: the game's frame rate with the swap hook armed (the baseline)
 *     BASE .. BASE+OVER s   300 quads moving over the game's display: Lissajous paths, alpha, turn, tint, depth,
 *                           a sprite sheet's frames, one in seven added light, and words in the card's font - all
 *                           from one atlas ("shapes"), as the engine's packed art draws: a few draw calls a frame
 *     .. +COVER s           the same with the game's display covered (pm_gfx_cover) and a full-stage backdrop
 *     then                  pm_end: the pictures come off the glass, the display is the game's
 *
 * Each phase's start is logged ("gfx_test: phase ...") so a rig job can take its shots and read the budget lines.
 * /dump/gfx_test.secs holds "BASE OVER COVER [QUADS]" to change the times (and the 300 quads, up to 2000); /dump/gfx_test.stop ends it at once. */
#include "pad_mode.h"

#define GFX_MAX 2000

static int set, pic_orb, pic_star, pic_ring, pic_ship, pic_sheet, pic_sky, pic_shapes, font;
/* gfx_set.PLACEHOLDER_BOXES: where each shape sits in the "shapes" atlas (orb, star, ring, ship, then 8 frames) */
static const float BOX[12][4] = {
    { 2, 2, 64, 64 }, { 70, 2, 64, 64 }, { 138, 2, 96, 96 }, { 2, 70, 80, 48 },
    { 2, 130, 60, 60 }, { 66, 130, 60, 60 }, { 130, 130, 60, 60 }, { 194, 130, 60, 60 },
    { 2, 194, 60, 60 }, { 66, 194, 60, 60 }, { 130, 194, 60, 60 }, { 194, 194, 60, 60 },
};
static int on, phase;
static unsigned long t0, last_check;
static unsigned base_s = 60, over_s = 150, cover_s = 150, n_quads = 300, frames;

static float tri(float x)                            /* a smooth wave from -1 to 1, period 1, no libm */
{
    float f = x - (float)(long)x;
    if (f < 0) f += 1;
    f = f < 0.5f ? f * 4 - 1 : 3 - f * 4;
    return f * (1.5f - 0.5f * f * f);
}

static void say_phase(const char *what)
{
    pm_log("gfx_test: phase %d - %s (at %lu ms)", phase, what, pm_ms() - t0);
}

static void stop(const char *why)
{
    pm_log("gfx_test: ends - %s; %u list(s) built", why, frames);
    on = 0;
    pm_end();
}

static void draw(float t, int cover)
{
    char words[96];
    int i;
    if (!pm_gfx_begin()) return;
    if (cover) {
        struct pm_quad sky = { 0 };
        sky.pic = pic_sky; sky.alpha = 1; sky.depth = -10;   /* its top left at the stage's */
        pm_gfx_quad(&sky);
    }
    for (i = 0; i < (int)n_quads; i++) {
        struct pm_quad q = { 0 };
        float fi = (float)i, sp = 0.03f + (float)(i % 17) * 0.004f;
        const float *b = BOX[i % 10 == 9 ? 4 + ((unsigned)(t * 12) + (unsigned)i) % 8 : (unsigned)i % 4];
        q.pic = pic_shapes;                          /* a shape, or one of the sheet's frames at 12 a second */
        q.sx = b[0]; q.sy = b[1]; q.sw = b[2]; q.sh = b[3];
        q.ax = q.ay = 0.5f;                          /* turned and scaled about its centre */
        q.blend = i % 7 == 3 ? PM_GFX_ADD : PM_GFX_NORMAL;
        q.x = 680 + 620 * tri(t * sp + fi * 0.137f);
        q.y = 384 + 330 * tri(t * sp * 1.31f + fi * 0.071f);
        q.scale_x = q.scale_y = 0.5f + 0.4f * (tri(t * 0.2f + fi * 0.05f) + 1);
        q.turn = t * (40 + (float)(i % 7) * 25) + fi * 11;
        q.alpha = 0.35f + 0.32f * (tri(t * 0.25f + fi * 0.03f) + 1);
        q.tint = PM_RGB(128 + 127 * tri(t * 0.1f + fi * 0.01f), 128 + 127 * tri(t * 0.13f + fi * 0.02f + 0.3f),
                        128 + 127 * tri(t * 0.17f + fi * 0.015f + 0.6f));
        q.depth = q.blend == PM_GFX_ADD ? 5 : (float)(i % 5);   /* added light over the rest, in one run */
        pm_gfx_quad(&q);
    }
    pm_snprintf(words, sizeof words, "MOVING PICTURES  %u QUADS  %s", n_quads, cover ? "COVERED" : "OVER THE GAME");
    pm_gfx_box(380, 18, 600, 64, PM_RGB(0, 0, 0), 0.55f, 9);
    pm_gfx_text(font, words, 680, 26, 40, PM_ALIGN_CENTER, PM_RGB(255, 220, 90), 1, 10);
    pm_snprintf(words, sizeof words, "T %lu.%lu", (unsigned long)t, (unsigned long)(t * 10) % 10);
    pm_gfx_text(font, words, 1340, 712, 36, PM_ALIGN_RIGHT, PM_RGB(255, 255, 255), 1, 10);
    pm_gfx_end();
    frames++;
}

static void on_tick(void)
{
    unsigned long now = pm_ms();
    float t;
    if (now - last_check >= 500) {
        char buf[64];
        last_check = now;
        if (!on && pm_trigger("gfx_test.start")) {
            if (pm_trigger_text("gfx_test.secs", buf, sizeof buf) > 0) {
                unsigned v[4] = { 0, 0, 0, 0 }, k = 0;
                const char *p;
                for (p = buf; *p && k < 4; p++) {
                    if (*p >= '0' && *p <= '9') v[k] = v[k] * 10 + (unsigned)(*p - '0');
                    else if (v[k]) k++;
                }
                if (v[0]) base_s = v[0];
                if (v[1]) over_s = v[1];
                if (v[2]) cover_s = v[2];
                if (v[3]) n_quads = v[3] > GFX_MAX ? GFX_MAX : v[3];
            }
            if (!pm_begin()) { pm_log("gfx_test: the game would not let the mode begin"); return; }
            set = pm_gfx_load("gfx_test.padgfx");
            if (!set) { stop("the picture set did not load"); return; }
            pic_orb = pm_gfx_picture(set, "orb"); pic_star = pm_gfx_picture(set, "star");
            pic_ring = pm_gfx_picture(set, "ring"); pic_ship = pm_gfx_picture(set, "ship");
            pic_sheet = pm_gfx_picture(set, "sheet"); pic_sky = pm_gfx_picture(set, "sky");
            pic_shapes = pm_gfx_picture(set, "shapes");
            if (!pic_shapes) { stop("the set has no \"shapes\" atlas (gfx_set.py --placeholder)"); return; }
            font = pm_gfx_font(set, "");
            pm_log("gfx_test: set %d - pictures %d %d %d %d %d %d, font %d; %u s, %u s, %u s; %u quads", set, pic_orb,
                   pic_star, pic_ring, pic_ship, pic_sheet, pic_sky, font, base_s, over_s, cover_s, n_quads);
            on = 1;
            phase = 0;
            frames = 0;
            t0 = now;
            say_phase("baseline: loaded, nothing drawn");
        }
        if (on && pm_trigger("gfx_test.stop")) { stop("gfx_test.stop"); return; }
    }
    if (!on) return;
    if (!pm_running()) { on = 0; pm_log("gfx_test: the mode was ended by the game"); return; }
    t = (float)(now - t0) / 1000.0f;
    if (phase == 0 && t >= (float)base_s) {
        phase = 1;
        say_phase(pm_gfx_ready(set) ? "quads over the game's display (the set is on GL)" : "quads over the game's display "
                  "(the set is NOT all on GL yet)");
    }
    if (phase == 1 && t >= (float)(base_s + over_s)) {
        phase = 2;
        pm_gfx_cover(1, PM_RGB(8, 10, 24));
        say_phase("quads with the game's display covered");
    }
    if (phase == 2 && t >= (float)(base_s + over_s + cover_s)) { stop("its time is up"); return; }
    if (phase >= 1) draw(t - (float)base_s, phase == 2);
}

static const struct pm_mode gfx_test = { .name = "GFX TEST", .tick = on_tick };
PM_REGISTER(gfx_test);
