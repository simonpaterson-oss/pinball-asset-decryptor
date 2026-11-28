/* vm_sound.h - a video mode's sound on the machine (PAD-1667): the engine's sound cues played through the mode's
 * own sound route, tools/spike2_emu/modes/sdk/pad_mode_assets.h, by the rules core/video_mode/sound.py writes down
 * (the app's player follows the same ones):
 *
 *   VM_SND_PLAY        pa_call(own, <its name>): a call of the mode's own on the voice bus. An effect is a
 *                      priority-3 call (skipped while its previous play still sounds), a callout priority 4 (starts
 *                      over); the newest call fades the one still sounding. A call ducks the music unless its
 *                      .assets line says noduck (the build writes noduck for a sound that does not duck).
 *   VM_SND_MUSIC       pa_music_change(own, <its bed>, fade): the bed playing fades out over the fade, then this one
 *                      starts and fades in over the same (one carrier, one bed at a time).
 *   VM_SND_MUSIC_STOP  pa_music_change(own, NULL, fade): the music fades out and stays quiet; the game's music
 *                      comes back only at the end (vm_sound_end).
 *
 * The build names each of the document's sounds on the machine (sound.machine_plan): "music" for the mode's own
 * first bed, its bed name for a further one, its call name for an effect or callout, "" for one nothing plays.
 *
 *     static struct pa_assets own = { .folder = "my_video_mode" };
 *     static const char *const names[] = { "music", "boss_music", "zap", ... };   indexed as the engine's sounds
 *     static struct vm_sound snd = { &own, names, 7 };
 *     load:     vm_sound_calibrate(&E);          the machine's sound offset (below), before vm_start
 *     start:    vm_sound_start(&snd);            the game's music fades; the mode's begins quiet
 *     a step:   vm_step(&E, in); vm_sound_cues(&snd, &E);
 *     tick:     pa_tick(&own);                   every tick, running or not
 *     end:      vm_sound_end(&snd);              its music fades, the game's comes back
 *
 * Nothing here allocates or blocks; everything is static (the mode rules).
 */
#ifndef VM_SOUND_H
#define VM_SOUND_H

#include "pad_mode_assets.h"
#include "vm_engine.h"

struct vm_sound {
    struct pa_assets *own;
    const char *const *names;   /* the machine name of each of the engine's sounds ("" = none) */
    int nnames;
    int on;                     /* between vm_sound_start and vm_sound_end */
    unsigned long cues, played, music_changes;
};

static PA_UNUSED const char *vm_sound_name(const struct vm_sound *s, int32_t snd)
{
    return snd >= 0 && snd < s->nnames && s->names[snd] ? s->names[snd] : "";
}

/* The machine's sound calibration (PAD-1663): how long after the step that cues it the mode's music is heard. A
 * rhythm phase judges presses and draws its notes against the music as heard (vm_set_audio_offset). Measured on
 * the emulator (James Bond LE 1.06, scripts/proof_pad1663_rig.py): the game's sound worker takes a bed's request
 * 13 ms after its cue's step and the mode sees it start at 14 ms; 3 minutes of steps stay within 6 ms of the
 * machine's 60 a second clock. A build that measures its machine otherwise sets -DVM_SOUND_AUDIO_OFFSET_MS=<ms>. */
#ifndef VM_SOUND_AUDIO_OFFSET_MS
#define VM_SOUND_AUDIO_OFFSET_MS 14
#endif
static PA_UNUSED void vm_sound_calibrate(vm_engine *e) { vm_set_audio_offset(e, VM_SOUND_AUDIO_OFFSET_MS); }

static PA_UNUSED void vm_sound_start(struct vm_sound *s)
{
    pa_start(s->own);
    pa_music_change(s->own, 0, 0);      /* quiet until the engine's first music cue: a bed fades in from quiet */
    s->on = 1;
}

/* fade steps (60 a second) to ms */
static PA_UNUSED unsigned vm_sound_ms(int32_t steps) { return steps > 0 ? (unsigned)steps * 1000u / 60u : 0u; }

/* Play this step's cues. `step` is the engine's step number the cues came out of (for the log). */
static PA_UNUSED void vm_sound_cues(struct vm_sound *s, const vm_engine *e, unsigned long step)
{
    int32_t i;
    if (!s->on) return;
    for (i = 0; i < e->ncues; i++) {
        const vm_sndcue *c = &e->cues[i];
        const char *name = vm_sound_name(s, c->sound);
        int ok = 0;
        s->cues++;
        if (c->op == VM_SND_PLAY) {
            ok = name[0] ? pa_call(s->own, name) : 0;
            s->played += ok ? 1 : 0;
        } else if (c->op == VM_SND_MUSIC) {
            ok = name[0] ? pa_music_change(s->own, name, vm_sound_ms(c->fade)) : 0;
            s->music_changes++;
        } else if (c->op == VM_SND_MUSIC_STOP) {
            ok = pa_music_change(s->own, 0, vm_sound_ms(c->fade));
            s->music_changes++;
        }
        pm_log("vm sound: step %lu at %lu ms: cue %d %s op %d duck %d fade %d -> %s", step, pm_ms(), (int)c->sound,
               name[0] ? name : "(none)", (int)c->op, (int)c->duck, (int)c->fade, ok ? "sent" : "NOT on this card");
    }
}

static PA_UNUSED void vm_sound_end(struct vm_sound *s)
{
    if (!s->on) return;
    s->on = 0;
    pa_end(s->own);
    pm_log("vm sound: end: %lu cues, %lu calls played, %lu music changes", s->cues, s->played, s->music_changes);
}

#endif
