/* vm_cli.c - vmrun, the native runner for tests and the text harness (PAD-1657).
 * Not part of the engine: it has stdio, a clock and an allocator.
 *
 *   vmrun PACK [--inputs FILE | --bot] [--record FILE] [--seed N] [--level N] [--max N]
 *              [--dump N] [--quiet] [--clip N] [--card N] [--fuzz N] [--bench N]
 *   vmrun PACK --seek PHASE --at S1,S2,... [--endless]   (PAD-1664: the editor's scrub; "D step ..." per step)
 *
 * Prints one line per event ("E step type a b c") and sound cue ("C step sound op duck"),
 * the draw list every N steps with --dump ("D step w0 w1 ..." in hex), and last
 * "END steps=.. hash=.. outcome=.. score=..". vm_run.mjs prints the same from WebAssembly.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "vm_engine.h"
#include "vm_bot.h"

static vm_engine E;
static unsigned char *pb, *ib;   /* the pack and the inputs, kept for the run (globals: no leak to report) */
static int32_t words[VM_MAX_ENTRIES * 12 + 16];

static unsigned char *slurp(const char *path, long *len)
{
    FILE *f = fopen(path, "rb");
    unsigned char *b;
    if (!f) { fprintf(stderr, "vmrun: cannot open %s\n", path); exit(2); }
    fseek(f, 0, SEEK_END); *len = ftell(f); fseek(f, 0, SEEK_SET);
    b = malloc(*len ? *len : 1);
    if (*len && fread(b, 1, *len, f) != (size_t)*len) { fprintf(stderr, "vmrun: short read %s\n", path); exit(2); }
    fclose(f);
    return b;
}

static double now_us(void) { return (double)clock() * 1e6 / CLOCKS_PER_SEC; }

int main(int argc, char **argv)
{
    long seek = -1;
    const char *at = 0;
    int endless = 0;
    const char *pack = 0, *inputs = 0, *record = 0;
    long plen = 0, ilen = 0, i;
    unsigned long seed = 1, max = 200000, dump = 0, fuzz = 0, bench = 0;
    long level = 0, clip = 120, card = -1;
    int bot = 0, quiet = 0, err, running = 1;
    unsigned long step = 0;
    FILE *rec = 0;
    vm_bot B;
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--inputs") && i + 1 < argc) inputs = argv[++i];
        else if (!strcmp(argv[i], "--bot")) bot = 1;
        else if (!strcmp(argv[i], "--record") && i + 1 < argc) record = argv[++i];
        else if (!strcmp(argv[i], "--seed") && i + 1 < argc) seed = strtoul(argv[++i], 0, 0);
        else if (!strcmp(argv[i], "--level") && i + 1 < argc) level = strtol(argv[++i], 0, 0);
        else if (!strcmp(argv[i], "--max") && i + 1 < argc) max = strtoul(argv[++i], 0, 0);
        else if (!strcmp(argv[i], "--dump") && i + 1 < argc) dump = strtoul(argv[++i], 0, 0);
        else if (!strcmp(argv[i], "--clip") && i + 1 < argc) clip = strtol(argv[++i], 0, 0);
        else if (!strcmp(argv[i], "--fuzz") && i + 1 < argc) fuzz = strtoul(argv[++i], 0, 0);
        else if (!strcmp(argv[i], "--bench") && i + 1 < argc) bench = strtoul(argv[++i], 0, 0);
        else if (!strcmp(argv[i], "--card") && i + 1 < argc) card = strtol(argv[++i], 0, 0);
        else if (!strcmp(argv[i], "--quiet")) quiet = 1;
        else if (!strcmp(argv[i], "--seek") && i + 1 < argc) seek = strtol(argv[++i], 0, 0);
        else if (!strcmp(argv[i], "--at") && i + 1 < argc) at = argv[++i];
        else if (!strcmp(argv[i], "--endless")) endless = 1;
        else if (!pack) pack = argv[i];
        else { fprintf(stderr, "vmrun: what is %s?\n", argv[i]); return 2; }
    }
    if (!pack) { fprintf(stderr, "usage: vmrun PACK [--inputs FILE | --bot] ...\n"); return 2; }
    pb = slurp(pack, &plen);
    if (inputs) ib = slurp(inputs, &ilen);
    err = vm_load(&E, pb, (uint32_t)plen);
    if (err) { printf("LOADERR %d at=%d\n", err, E.err_at); return 3; }
    if (seek >= 0) {   /* PAD-1664: the phase at each play step asked, played from its start with nothing pressed */
        unsigned long want, have = 0;
        const char *p = at ? at : "0";
        if (!vm_edit_seek_begin(&E, (int32_t)seek, endless ? VM_SEEK_ENDLESS : 0)) { printf("LOADERR %d at=phase\n", VM_ERR_INDEX); return 3; }
        while (*p) {
            uint32_t n, w;
            want = strtoul(p, (char **)&p, 10);
            if (*p == ',') p++;
            if (want < have) { vm_edit_seek_begin(&E, (int32_t)seek, endless ? VM_SEEK_ENDLESS : 0); have = 0; }
            for (; have < want; have++) vm_edit_seek_step(&E);
            vm_edit_seek_draw(&E);
            n = vm_list_words(&E, words, sizeof(words) / sizeof(words[0]));
            printf("D %lu", want);
            for (w = 0; w < n; w++) printf(" %x", (unsigned)words[w]);
            printf("\n");
        }
        return 0;
    }
    if (card >= 0) {   /* start at another card (the app's "Start here", PAD-1659) */
        if (card >= E.doc.ncard) { printf("LOADERR %d at=card\n", VM_ERR_INDEX); return 3; }
        E.doc.start_card = (int32_t)card;
    }
    vm_start(&E, (uint32_t)seed, (int32_t)level);
    vm_bot_init(&B, (int32_t)clip);

    if (fuzz) {   /* random buttons for N steps; a new play each time one ends */
        uint32_t r = (uint32_t)seed * 2654435761u + 1u;
        unsigned long plays = 1, won = 0, maxthings = 0;
        uint32_t reached = 0;
        for (step = 0; step < fuzz; step++) {
            uint32_t in;
            int c;
            r ^= r << 13; r ^= r >> 17; r ^= r << 5;
            /* odd plays: buttons at random; even plays: the bot with one step in four random,
               so every phase is reached and played badly too */
            in = (plays & 1) || (r >> 20) % 4 == 0 ? r & 7u : vm_bot_input(&B, &E);
            if ((r >> 8) % 97 == 0) in |= VM_IN_CLIP_DONE;
            if (!vm_step(&E, in)) {
                if (E.outcome == 1) won++;
                plays++;
                vm_start(&E, (uint32_t)(seed + plays), (int32_t)(plays % 6));
                vm_bot_init(&B, (int32_t)clip);
            }
            c = vm_check(&E);
            if (c) { printf("FUZZFAIL step=%lu check=%d state=%d phase=%d\n", step, c, E.state, E.phase); return 1; }
            if ((unsigned long)E.nthings > maxthings) maxthings = (unsigned long)E.nthings;
            if (E.state == VM_ST_PLAY) reached |= 1u << (E.phase & 31);
        }
        printf("FUZZ steps=%lu plays=%lu won=%lu phases_reached=%u max_things=%lu ok\n", fuzz, plays, won, (unsigned)reached, maxthings);
        return 0;
    }
    if (bench) {  /* the bot plays, restarting each time; time per step and the most things alive */
        unsigned long maxthings = 0, at300 = 0;
        double t0 = now_us(), t300 = 0;
        for (step = 0; step < bench; step++) {
            double a = now_us(), d;
            if (!vm_step(&E, vm_bot_input(&B, &E))) { vm_start(&E, (uint32_t)(seed + step), 0); vm_bot_init(&B, (int32_t)clip); }
            d = now_us() - a;
            if ((unsigned long)E.nthings > maxthings) maxthings = (unsigned long)E.nthings;
            if (E.nthings >= 300) { at300++; t300 += d; }
        }
        printf("BENCH steps=%lu us_per_step=%.2f max_things=%lu steps_at_300=%lu us_per_step_at_300=%.2f\n",
               bench, (now_us() - t0) / bench, maxthings, at300, at300 ? t300 / at300 : 0.0);
        return 0;
    }
    if (record) rec = fopen(record, "wb");
    while (running && step < max) {
        uint32_t in;
        int k;
        if (bot) in = vm_bot_input(&B, &E);
        else in = (long)step < ilen ? ib[step] : 0;
        if (rec) fputc((int)in, rec);
        running = vm_step(&E, in);
        if (!quiet) {
            for (k = 0; k < E.nevents; k++)
                printf("E %lu %d %d %d %d\n", step, E.events[k].type, E.events[k].a, E.events[k].b, E.events[k].c);
            for (k = 0; k < E.ncues; k++)
                printf("C %lu %d %d %d\n", step, E.cues[k].sound, E.cues[k].op, E.cues[k].duck);
        }
        if (dump && (step % dump == 0 || !running)) {
            uint32_t n = vm_list_words(&E, words, sizeof(words) / sizeof(words[0])), w;
            printf("D %lu", step);
            for (w = 0; w < n; w++) printf(" %x", (unsigned)words[w]);
            printf("\n");
        }
        step++;
    }
    if (rec) fclose(rec);
    printf("END steps=%lu hash=%016llx outcome=%d score=%d\n", step, (unsigned long long)E.hash, E.outcome, E.score);
    return 0;
}
