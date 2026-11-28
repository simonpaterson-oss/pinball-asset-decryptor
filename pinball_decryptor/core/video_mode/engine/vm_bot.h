/* vm_bot.h - a player for tests and the text harness (PAD-1657). Never linked into the
 * machine's mode runtime: it reads the engine's own state and answers with the buttons a
 * decent player would hold this step, so a golden run can be recorded once and replayed. */
#ifndef VM_BOT_H
#define VM_BOT_H
#include "vm_engine.h"
typedef struct {
    uint32_t last; int32_t clip_steps; int32_t tick;
    int32_t px[VM_MAX_THINGS], serial[VM_MAX_THINGS];   /* last step's x of each thing: its speed */
} vm_bot;
void vm_bot_init(vm_bot *b, int32_t clip_steps);   /* clip_steps: how long a clip "plays" */
uint32_t vm_bot_input(vm_bot *b, const vm_engine *e);
#endif
