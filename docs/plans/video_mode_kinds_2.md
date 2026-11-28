# Video mode game kinds 2: the button kinds (PAD-1663)

Epic: the video mode maker (plan: `video_mode_maker.md`, PAD-1654). Kinds 1 is PAD-1662 (`video_mode_kinds_1.md`).

## What plays

All seven kinds are played by the engine, in `core/video_mode/engine/vm_kinds2.c` (included by `vm_engine.c`, so the
machine, the app and the tests run the same C). Settings words per kind are listed at the top of that file; the
compiler writes them (`compiler.py` `button_kind`).

| Kind | Play | Ends |
|---|---|---|
| `mash` | each press of its button adds; the meter drains; an optional rival fills its own bar | goal, or the rival or the clock first |
| `alternate` | a left then a right (or right then left) adds a pair | goal, or the clock |
| `tug` | Action pulls only while the named flipper is held (`shown`: it changes sides every `switch_every_s`); the other side pulls back; every `shake_every_s` a grab takes hold: Action does nothing and it pulls back twice as hard until `shake_pairs` left-right pairs shake it off | the meter full (won) or empty (lost), or the clock |
| `rhythm` | notes travel down three lanes (left, Action, right: where the buttons sit) to a hit line on the music's beat grid; a press is perfect within `perfect_ms`, good within `good_ms`, early or late within twice that (counted, the combo broken), else a miss; a held note must be held to its end | when the chart is over: `accuracy` (good presses out of all notes), or `misses` on the way |
| `sequence` | a run of buttons, shown (or flashed for `flash_s`, then entered from memory) against `per_press_s` a press; a random run grows a button a round | `rounds` runs right; a wrong button or a slow one is a miss and the run is shown again |
| `dodge` | a gap, a warning glowing in from the side it comes from (the button named), then a `window_s` window; a press during the warning is too early, a wrong button or no press is a hit | after `count` attacks; `misses` on the way |
| `shield` | a warning, then hold the button through the attack (`hold_s`; it may come down up to 0.15 s into it) | after `count` attacks; `misses` on the way |

A miss hurts the player when the phase has one with health, else it shakes and flashes red. `accuracy` is judged once
a rhythm, sequence, dodge or shield run is over; on other kinds the compiler says it never ends the phase. When such
a run is over and no win condition was met, the phase is lost.

## Prompts: the cabinet's buttons

`draw_button` draws a button as the cabinet has it: the left flipper button left of the middle, Action in the middle,
the right flipper button right of it, round, from boxes (no art, the same cost on every machine), in the prompts
HUD part's `colour` (flippers) and `accent` (Action). Looks: dim, lit, pushed in (for 8 steps after every press, and
while held), a fill bar under it (a hold), a ring thrown out on each press (mash), a bob (next in turn). Mash,
alternate and tug draw theirs standing on the prompts part's bottom edge, their words above (or at the stage's foot
when there is no prompts part); rhythm, sequence, dodge and shield draw their own, with a judgement word (PERFECT,
GOOD, EARLY, LATE, MISS, DODGED, BLOCKED) that pops and fades.

## Rhythm and time

A note's time is fixed in the music from the start (`offset + beat x 60000 / tempo`, worked out by the compiler, in
ms); the engine reads the music's position as `song_steps x 1000 / 60`, counted from the step that cued the music.
Nothing is timed from the note before, so nothing builds up: a three-minute chart at 128 bpm (notes between steps)
is perfect to its last note (`test_rhythm_three_minutes_stays_on_the_beat`).

What can put a rhythm phase out of time is the host: its steps against the sound it plays.

- **The calibration.** `vm_set_audio_offset(e, ms)`: the host's sound is heard `ms` after the step that cued it.
  The engine judges presses, and draws its notes, against `song_ms - offset`. It is kept across `vm_start`; a
  replay must use the same one (saved replays keep `audio_offset`).
- **The app.** While a rhythm phase plays with sound on, the player steps by the music's audio clock, not the
  wall's: the steps due are the music's position in steps less the steps run since the cue (at most 8 a frame;
  none while the music is still being fetched and decoded, up to 1.5 s). Each play's offset is the browser's
  reported output latency plus the player's own: **Calibrate** (twelve clicks at 100 a minute; Space on the last
  eight, each timed against the click as heard by the audio clock's output timestamp; the middle difference),
  kept in the app's storage (`pad.vmode.audio_offset_ms`).
- **The machine.** The mode runtime steps the engine once a tick, 60 a second, whatever the screen draws (a Spike 2
  draws about 29 frames a second). Its offset is `VM_SOUND_AUDIO_OFFSET_MS` in `vm_sound.h`, 14 ms as measured on the
  emulator, applied by `vm_sound_calibrate(&E)` before `vm_start` (PAD-1660's runtime glue calls it); a build that
  measures its machine otherwise passes `-DVM_SOUND_AUDIO_OFFSET_MS=<ms>`. What the emulator cannot show is the
  real machine's output buffer after the sound worker takes a request; the app's Calibrate covers a computer, and
  the define a machine.

## The catalog

`core/video_mode/kinds_buttons.py`: `KINDS2` under `GROUP2` ("Buttons and timing"), in the shape of PAD-1662's
`kinds.py`, which takes them in (`KINDS.update(KINDS2)`). Each starter makes its kind playable at once: a meter and
its bar for mash, alternate and tug; the rhythm starter an original drum loop (`beat_wav`, written by `make_files`)
and a 24-bar chart that grows busier. `new_doc(kind)` is a one-phase mode of a kind.

## Merging with the epic's other branches

- PAD-1662 (kinds 1) and PAD-1666 (HUD) each took a pack version and appended fixed strings after `VM_S_HOLD`; the
  branch merged second takes the next pack version, puts its table after the other's, and its strings after theirs.
- PAD-1666's pop-up HUD part: `draw_kinds2` skips the judgement word when a `popup` part's `on` lists
  `prompt_good`, `prompt_perfect` or `prompt_miss`, so a maker's own pop-up replaces it.
- `e->kind_won` / `e->kind_lost` mean the same on PAD-1662's branch; keep one copy.
- Golden replays: the branch merged second re-records them.

## Proved by

- `tests/test_video_mode_kinds2.py`: every starter won by the bot and lost with no buttons, golden on native and
  WebAssembly; rhythm's windows to the step, its calibration, held notes and the three-minute chart; tug needs the
  named flipper and its grab is shaken off by alternating; a wrong sequence button, a too-early dodge and a held
  shield; the glyphs in their cabinet places; the catalog against the schema; random buttons for 200,000 steps a kind.
- `scripts/shot_pad1663.py` in Edge on David's PC (sound on, Edge muted at the process): each starter in the app's
  player, its winning buttons replayed to a win on the native build's hash and a play with no buttons to a loss, all
  seven. rhythm-3min (384 notes at 128 bpm on its own three-minute drum track) played by a player in the page that
  presses each note when its beat is heard by the audio clock: at 60 fps 384 of 384 perfect, the engine at most 17 ms
  (one step) from its music, 7 ms on average, over 184 s; at the machine's 29 fps 383 perfect and 1 good, at most
  27 ms, 8 ms on average. Blocking the page 150 ms, it is back on its music within a frame.
- The first three-minute run found two faults, both fixed: a tap that came and went within a frame that ran no step
  never reached the engine (the player now latches a press until a step has seen it; the page player missed runs of
  notes without it), and the music drift readout was taken before the frame's steps.
- `scripts/proof_pad1663_rig.py --slot N` on James Bond LE 1.06 (hidden, muted): rhythm-3min as a C code mode, the
  engine stepped once a tick on the bot's buttons for 10,982 steps (183 s) while the screen drew at its own rate:
  every logged step within 6 ms of the machine's 60 a second clock, none off it; the music's request taken by the
  game's sound worker 13 ms after its cue's step and its bed started at 14 ms; 384 of 384 notes perfect, outcome
  won, the same hash as the native build. Hence the 14 ms machine calibration.
