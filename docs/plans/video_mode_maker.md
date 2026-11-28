# Video mode maker: the plan (PAD-1654, umbrella of the epic)

David's ask (2026-11-28): an epic for a video mode maker, Stern first and then the
other makers, with a WYSIWYG editor, a way to sample a mode on the computer, and a
"very high end, professional" look and feel. The reference is a video of custom code
on a Spike 2 machine, 3:27 to 10:30.

A **video mode** is a small game on the machine's screen, played with the left flipper
button, the right flipper button and the Action button while the ball is held. It is a
chain of short **phases** with **clips** between them, and it ends in a win or a loss
that pays into the pinball game.

This file is the plan the rest of the epic is held to: what the reference does, the
document format, the contract between the engine and each screen, the budgets, the
editor's design language, and the ticket map. It is kept current as the tickets land.

Never name a tester or the reference video's maker in anything public.

Contents: [1 The reference](#1-the-reference-taken-apart) ·
[2 Game kinds](#2-game-kinds-and-where-each-was-seen) ·
[3 The document](#3-the-document-video_modejson-format-1) ·
[4 Draw list](#4-the-draw-list-and-the-backend-contract) ·
[5 Budgets](#5-budgets-per-machine) ·
[6 Design language](#6-the-editors-design-language) ·
[7 Ticket map](#7-the-ticket-map) ·
[8 Decisions](#8-decisions)

---

## 1 The reference, taken apart

Taken from the video itself: a frame every 3 seconds from 3:27 to 10:30, cropped to the
machine's screen (141 frames), plus enlarged key frames. Timestamps are the video's.
What could not be read in a 3-second frame is marked *(from the record)*: David's own
account of the video in the epic tickets.

The video shows **three video modes**, one after another. Each opens with a clip and a
title card ("OBJECTIVE ... GET READY"), runs phases separated by comic-panel clips, and
ends on a win clip.

### What every phase shares (the HUD anatomy)

Seen in every playable frame, so it is the default HUD of every game kind:

| Place | What | Seen |
|---|---|---|
| Top left | Health as 6 green pips; turns orange/amber when low | 3:42 onwards |
| Top centre | A thin white progress bar: how far through the phase | 3:42, 6:03, 9:18 |
| Top right | Combo ("COMBO 8 x2", "COMBO 17 x5") and the score | 4:12, 5:00 |
| Centre | Callouts in big yellow outlined capitals: "PHASE 1 - ITS WEAK SPOTS!", "DODGE RIGHT!", "BANK LEFT!" | 4:18, 5:00, 7:27 |
| Centre | A **tell**: a large button glyph inside a ring that runs down like a clock | 5:00, 6:48, 9:36 |
| Upper centre | Result marks: X for a miss, star for a hit, "1/4" style counters, "HITS 0/2" | 5:00, 6:48, 9:36, 10:03 |
| Bottom | The **prompt bar**: three slots that mirror the three buttons, left glyph + word, Action glyph + word, right glyph + word ("LANE · SHOOT · LANE", "FLY · · FLY", "HOLD · MASH", "CLIMB · · CLIMB") | every playable frame |
| Edge | A yellow frame around the whole screen flashes on danger or a hit | 4:24, 6:15, 6:18 |
| Bottom strip | An instruction line in small capitals: "ACTION AS THE SIGHT CROSSES EACH ONE", "HOLD LEFT FLIPPER + MASH ACTION" | 4:24, 7:21 |

Transitions are white flashes (5:21, 7:00) and cuts to comic-panel clips. Hits throw
sparks and burst light (5:15, 5:18).

### Mode 1: the boat chase (3:27 to about 5:25)

| Time | Phase | What the player does | On screen | How it ends |
|---|---|---|---|---|
| 3:27-4:09 | **Chase** | Flippers move the boat between three lanes; Action fires straight up the screen (a tracer line) | Boat at the bottom on a scrolling sea; planes and drones fly in from the horizon; a ring locks on an enemy (3:45, 3:54); prompt bar LANE · SHOOT · LANE; score climbs per kill | Reaches the warship (cut to a clip of it, 4:09) |
| 3:36 | Quick shot | A single overhead plane; FIRE prompt only | Plane crossing a still sea | One shot or it passes |
| 4:15-4:36 | **Boss: weak spots** | Action when the sweeping sight crosses a weak spot | The ship head-on, 3 to 5 red-ringed weak spots, "PHASE 1 - ITS WEAK SPOTS!", then "PHASE 2"; prompt bar FIRE only | All weak spots of both phases hit (4:36 shows the row of rings) |
| 4:45 | **Mash** | "TURBO - ACTION!": hit Action fast | A big ring around the Action glyph over a hero close-up | Meter filled |
| 4:57-5:09 | **Boss 2: dodge then hit** | Dodge the way the tell shows ("DODGE RIGHT!"); then *(from the record)* hold Action and steer a sight without overheating ("HOLD + CHARGE", 5:06) | A flying boss; "DODGE 4/6 - THEN HER LIGHTNING", "HITS 0/2"; prompt bar FLY · · FLY; a crosshair and a charge ring | Six dodges then two hits |
| 5:12 | **Alternate** | "LEFT - RIGHT - LEFT - RIGHT!" to charge | A horizontal meter with arrows either side | Meter full |
| 5:15 | **Release** | "UNLEASH - THE TORNADO!": one Action press | The Action glyph in a ring | Press lands; explosion, white flash, win clip (5:18-5:24) |

### Mode 2: the space flight (5:27 to about 8:27)

| Time | Phase | What the player does | On screen | How it ends |
|---|---|---|---|---|
| 5:27-6:03 | Clips, title card | - | Comic clips, a neon title sign; "OBJECTIVE / REACH THE WARSHIP / GET READY" | Card times out |
| 6:06-6:33 | **Thrust flight** | *(from the record)* hold Action to rise, let go to fall; the right flipper fires | The ship on the left over a scrolling field; columns of fire from top and bottom leave gaps; enemies and pickups drift in; the yellow edge flashes on a hit | Reaches the warship |
| 6:36-6:57 | **Boss: engines** | "ITS ENGINES - ONE AT A TIME!": aim and fire at each engine in turn | A big warship at the right, a reticle with button glyphs on the engine | Every engine down |
| 6:48 | **Quick dodge** | "LASER VOLLEY - DODGE RIGHT!" | A big arrow in a countdown ring; X and star marks for misses and hits | The window closes |
| 7:21-8:24 | **Tug of war** | "BANK LEFT!" / "BANK RIGHT!": hold the named flipper and mash Action; at intervals "LEFT - RIGHT!": alternate the flippers to shake an enemy off; "THROW IT! - ACTION": one press | A tug meter across the top with a sun icon; HOLD · MASH prompt bar; a second bar ("strength") for the shake-off | The pull reaches the end |
| 8:27 | **Final mash** | "MASH ACTION" against a count-down from 8 | A big number and a meter with threshold marks | Time up; the mark reached sets the result |
| 8:30-9:15 | Clips | - | Win clips; the third mode's intro panels | - |

### Mode 3: the rooftop fight (9:15 to 10:30)

| Time | Phase | What the player does | On screen | How it ends |
|---|---|---|---|---|
| 9:18 | Title card | - | "OBJECTIVE / CLIMB TO THE ROOF" | - |
| 9:21-9:45 | **Climb** (alternate) | Alternate the flippers to climb; quick presses on "NOW!" | Prompt bar CLIMB · · CLIMB; an orange vertical meter at the left; the progress bar is the height | The roof |
| 9:36 | **Button sequence** | "DODGE THE SHOTS!": enter the shown run of glyphs (left, right, right...) in time | A row of glyphs with a cursor, "1/4", a timing bar under it, "NEXT!" in the corners | All entered or the bar runs out |
| 9:54-10:09 | **Rhythm / sequence** | "SLASH THE ROBOT!": hit each coloured glyph as it reaches the mark | Glyphs travelling along a track, "1/2", X marks at the top | The run ends |
| 10:12-10:27 | Fight | *(from the record)* fast dodges and **hold a shield** | Health turns amber; X marks fill | Health or misses |

### What winning and losing pay *(from the record)*

Winning or losing plays a different clip and pays into the pinball game: multipliers,
add-a-balls, an extra ball, a jackpot bonus. The video does not show the playfield side
legibly; PAD-1668 owns it.

## 2 Game kinds and where each was seen

The `kind` of a phase. Every kind traces back to something in section 1.

| Kind | What it is | Seen at |
|---|---|---|
| `chase` | Steer between lanes or freely with the flippers, Action fires; things to shoot, dodge and pick up arrive on a timeline; the world scrolls in layers | 3:27-4:09 |
| `thrust` | Hold a button to rise, let go to fall; another button fires; gaps, enemies and pickups scroll in | 6:06-6:33 |
| `aim` | A sight sweeps or is steered; Action fires or is held; an overheat meter punishes holding | 4:15 (sweeping sight), 5:06 (hold and steer) |
| `boss` | A big thing with weak points that open on a pattern, attacks to dodge, a health bar, stages | 4:15-4:36, 6:36-6:57 |
| `mash` | Hit Action fast to fill a meter against a drain | 4:45, 8:27 |
| `alternate` | Left, right, left, right to fill a meter | 5:12, 9:21 |
| `tug` | Hold the named flipper and mash Action, while a second threat needs alternating | 7:21-8:24 |
| `rhythm` | Prompts travel to a hit line in time with the music; early, good and perfect windows | 9:54-10:09 |
| `sequence` | A shown or hidden run of buttons to enter in time | 9:36 |
| `dodge` | A tell, then a short window to press the named button | 4:57, 6:48 |
| `shield` | A tell, then hold a button for a time | *(from the record)* 10:12 on |
| `custom` | Starts empty; built from things and rule cards only (PAD-1665) | - (freedom past the reference) |

A single press after a charge ("UNLEASH", "THROW IT") is a `sequence` of one button;
title cards are part of every phase (its `title` and `objective`).

## 3 The document: video_mode.json, format 1

One file per video mode: `<project>/modes/<slug>/video_mode.json`, beside the mode's art,
sound and clip files. The schema is
`pinball_decryptor/core/video_mode/video_mode.schema.json` (JSON Schema 2020-12); the
app reads a file only through `pinball_decryptor/core/video_mode/document.py`
(`load`, `migrate`, `check`), and `tests/test_video_mode_schema.py` loads the same schema.
The web UI gets it from the app over RPC when the editor lands (PAD-1661); there is no
second copy.

**Units.** Places and sizes are stage pixels on the 1360x768 stage, origin top left,
y down. Times are seconds (the compiler turns them into steps). Turns are degrees,
clockwise. Colours are `#rrggbb` or `#rrggbbaa`. Speeds are pixels a second.

**Ids.** Lower case, `[a-z][a-z0-9_]*`, up to 40 characters, unique within their own
list; things and values share one namespace (a win condition's `of` may name either).
A picture and the thing drawn with it may share a name. The mode's own `id` is its slug.

**Files** are paths inside the mode folder, never absolute, never climbing out with `..`.

### Versions: how a later PAD reads an older file

- `format` is a whole number, 1 today. **Any** change to what a file may hold bumps it,
  even an added optional field: the schema refuses unknown keys, so an older PAD would
  refuse such a file anyway, and a plain refusal beats a field dropped in silence.
- A newer PAD reads an older file by running `MIGRATIONS[n]` for each step n to n+1, in
  turn: pure functions in `document.py` that never touch the disk. The file on disk is
  rewritten in the new format only when the user saves.
- Each format gets a frozen fixture, `tests/data/video_mode/format_<n>.json`, kept for
  good; the test loads every one through the migrations.
- An older PAD refuses a newer file in plain words ("saved by a newer PAD (format 2; this
  PAD reads up to 1). Update PAD to open it.") and never writes it.
- `editor` is the one free-form object: the editor's own state, kept and written back,
  never read by the engine, so editor-only changes do not need a format bump.

### Top level

| Field | Meaning |
|---|---|
| `format` | 1 |
| `kind` | Always `"pad-video-mode"`, so a stray JSON file is refused |
| `id` | The mode's slug, its folder name |
| `title` | Shown in the modes list and on the card (40 characters) |
| `notes` | The author's own notes |
| `seed` | The random seed; the same seed and the same inputs play the same game |
| `stage` | The stage (below) |
| `assets` | `pictures`, `sounds`, `fonts`, `clips` |
| `values` | Meters and counters of the mode's own |
| `things` | What can be on the stage: one entry per kind of thing, placed or spawned by phases |
| `phases` | The playable parts |
| `flow` | The storyboard: clips, phases and ends wired together |
| `hud` | Health, meters, score, prompts, callouts |
| `cues` | Sounds on events |
| `style` | The look and the feel switches |
| `pays` | What it pays into the pinball game |
| `editor` | The editor's own state |

### `stage`

| Field | Meaning |
|---|---|
| `width`, `height` | 1360 and 768: the one stage every mode is designed on |
| `steps_per_second` | 60: the engine's fixed step |
| `background` | The colour behind everything |
| `safe` | A box (`x`, `y`, `w`, `h`) the editor shows as the safe area: inside every machine's visible glass |
| `dots` | Dot-matrix screens: `band_top`, the top of the 1360x340 band of the stage they show (section 4) |

### `assets`

`pictures`: each has `id`, `file` (a PNG, or a sheet), and for a sheet `frame_w`,
`frame_h` and `frames` (count, read left to right, top to bottom); `anchor` (0..1 of the
frame, the point that sits at a thing's x, y); a default `hitbox`; and `animations`, each
with `id`, `frames` (indexes into the sheet), `fps` and `loop`.
A `hitbox` has a `shape` (`box` with `x`, `y`, `w`, `h`, or `circle` with `x`, `y`, `r`),
relative to the anchor.

`sounds`: `id`, `file`, `role` (`music`, `effect` or `callout`), `volume` (0..1), `loop`,
`loop_start_s` (where a looping music bed loops back to).

`fonts`: `id`, `face` (the card's own font, written `card:<name>`, or a font file in the
mode folder named in `file`), `size` in stage pixels. The app draws the same face.

`clips`: `id`, `file` (made with the existing clip tools and film_cut.py), `skippable`.

### `values`

Meters and counters the phases, HUD and rules read and change: `id`, `type` (`meter` or
`counter`), `start`, `min`, `max`, `drain_per_s` (a meter that empties by itself).

### `things`

One entry per kind of thing: `id`, `picture`, `animation` (one of the picture's),
`scale`, `team` (`player`, `enemy`, `enemy_shot`, `player_shot`, `pickup`, `health`,
`scenery`; collisions are by team), `health`, `points` (score when destroyed), `hitbox`
(overrides the picture's), `blend` (`normal` or `add`), `depth` (higher draws in front),
and `mover`.

A `mover` has a `type`: `none`, `straight` (`speed` along `direction`), `lanes` and
`free` (steered by the player), `thrust` (rise and fall), `path` (`path` points,
`easing`, `loop`), `home` (on a `target`, turning at `turn_per_s`), `scroll` (with the
world), `orbit` (`radius`). `easing` is one of `linear`, `in`, `out`, `in_out`,
`back_out`, `bounce_out`, `elastic_out`, `step`.

### `phases`

| Field | Meaning |
|---|---|
| `id` | The phase's id |
| `kind` | One of the game kinds of section 2 |
| `title`, `objective` | The title card: "Chase" / "Reach the warship" |
| `length_s` | How long it runs; 0 or absent: until a win or lose condition |
| `music` | A sound whose role is music |
| `background` | Layers: `picture`, `speed` (scroll, pixels a second), `y`, `tile`, `alpha` |
| `settings` | The kind's own settings (below); the schema checks them against the kind |
| `place` | Things on the stage at the first step: `thing`, `x`, `y`, `scale`, `turn`, `depth`, `hidden`, `locked` (editor only: cannot be dragged) |
| `spawns` | Things that arrive: `thing`, `at_s`, `every_s`, `count`, `x`, `y`, `spread` (random spread from the seed), `lane`, `mover` (overrides the thing's) |
| `rules` | When-this-then-that cards (PAD-1665): `when` (`event`, `a`, `b`, `button`, `value`) and `then`, a list of (`do`, `target`, `value`) |
| `win`, `lose` | Conditions, any one of which ends the phase: `when` (`time_up`, `survive_s`, `score`, `kills`, `pickups`, `goal`, `health_gone`, `misses`, `boss_down`, `hits`, `accuracy`), `value`, `of` (a thing or a value) |

Rule events: `touch`, `value_crosses`, `timer_ends`, `pressed`, `held`, `mashed`,
`released`, `leaves_screen`, `phase_starts`. Rule actions: `add_health`, `score`,
`spawn`, `remove`, `animate`, `sound`, `shake`, `flash`, `change_value`, `set_value`,
`go_to`, `win`, `lose`. PAD-1665 may reshape the cards; that is a format bump.

### The settings of each kind

Buttons are `left`, `right` and `action` everywhere.

- `chase`: `player` (a thing), `steer` (`lanes` or `free`), `lanes` (2 to 7),
  `steer_speed`, `fire` (`action` or `none`), `shot` (the thing fired), `fire_per_s`,
  `scroll_speed`, `health`, `hurt_blink_s`.
- `thrust`: `player`, `thrust_button`, `fire_button` (or `none`), `shot`, `gravity`,
  `thrust`, `max_fall`, `scroll_speed`, `health`.
- `aim`: `sight` (a thing), `move` (`sweep` along `sweep_path` over `sweep_s`, or
  `steer` at `steer_speed`), `fire` (`press` or `hold`), `heat` (a meter), `heat_per_s`,
  `cool_per_s`, `overheat_lock_s`.
- `boss`: `boss` (a thing), `hit_with` (`sight` or `shots`), `sight`, `weak_points`
  (`x`, `y` relative to the boss, `r`, `hits`, and the open pattern `open_s`,
  `closed_s`, `offset_s`), `attacks` (`thing`, `every_s`, `aim`: `player` or
  `straight`), `stages`.
- `mash`: `meter`, `button`, `per_press`, `drain_per_s`, `goal`.
- `alternate`: `meter`, `per_pair`, `drain_per_s`, `start_side` (`left`, `right`,
  `either`), `goal`.
- `tug`: `meter`, `hold` (`left`, `right`, or `shown`: the screen names it and it
  changes every `switch_every_s`), `per_press`, `pull_back_per_s`, and the second threat
  `shake_every_s` / `shake_pairs` (alternations to shake it off), `goal`.
- `rhythm`: `music`, `tempo_bpm`, `offset_ms`, `travel_beats` (how early a prompt
  appears), `chart` (`beat`, `button`, `hold_beats`), `perfect_ms`, `good_ms`.
- `sequence`: `buttons` (a fixed run) or `length` (random from the seed), `shown`,
  `per_press_s`, `rounds`.
- `dodge`: `buttons` (the ones a tell may name), `tell_s`, `window_s`, `count`.
- `shield`: `button`, `tell_s`, `hold_s`, `count`.
- `custom`: no settings; things and rules only.

### `flow`

`start` names the first card; `cards` lists them. A card has an `id` and a `card` type:

- `clip`: plays `clip`, `then` goes on.
- `phase`: plays `phase`; goes to `won` or `lost`; `tries` lets a lost phase restart
  before taking `lost`.
- `end`: the video mode is over with an `outcome`, `won` or `lost`.

The checker refuses a flow that cannot be played: a card that names nothing, a card that
cannot be reached from `start`, a card from which no end can be reached (an endless
loop), no end at all, or no end for a win.

### `hud`

Each part: `id`, `part` (`health`, `meter`, `score`, `combo`, `timer`, `lives`,
`progress`, `prompts`, `callout`, `counter`, `text`), `x`, `y`, `w`, `h`, `value` (the
meter or counter it shows), `look` (`bar`, `pips`, `hearts`, `ring`, `number`,
`glyphs`), `font`, `colour`, `accent` (danger zone, outline), `text` (`{n}` is the
number), `phases` (shown only in these; absent: all).

### `cues`

`on` (`fire`, `hit`, `kill`, `pickup`, `hurt`, `prompt_good`, `prompt_perfect`,
`prompt_miss`, `phase_start`, `phase_won`, `phase_lost`, `won`, `lost`), `sound`,
`duck_music` (lower the music under it).

### `style`

`preset` (`clean`, `arcade`, `comic`, `retro_pixel`), and switches for each effect:
`shake`, `flash`, `particles`, `hit_stop`, `crt`; `transition` between phases (`cut`,
`fade`, `white_flash`, `wipe`, `iris`).

### `pays`

`multiplier_in` (a multiplier earned before the mode scales its score) and `awards`:
`when` (`won`, `lost`, `phase_won` with `phase`, `each_kill`, `pickups_reach` with `at`),
`award` (`score`, `add_a_ball`, `extra_ball`, `light_jackpot`, `multiplier`,
`saved_value` with `name`), `amount`.

### The worked example: Night Harbour

`pinball_decryptor/core/video_mode/examples/night_harbour.json`, an original boat chase
shaped like the reference's first mode, with placeholder art paths (PAD-1670 makes the
art). It checks clean and is the frozen format 1 fixture. In short:

```
flow:   c_intro (clip "intro")
          -> c_chase  phase "chase"     won -> c_boss    lost -> c_lost
          -> c_boss   phase "boss"      won -> c_charge  lost -> c_lost   (2 tries)
          -> c_charge phase "charge"    won -> c_won     lost -> c_won    (pays less)
        c_won  (clip "won_clip")  -> e_won  (end, won)
        c_lost (clip "lost_clip") -> e_lost (end, lost)
```

- `"chase"`: kind `chase`. The boat (`player_boat`, 6 health, pips top left) steers
  between 3 lanes at the bottom; Action fires `player_bolt` 6 times a second straight up.
  Ten `drone`s fly a curved path from the right every 3 s; `mine`s scroll in lane 1
  every 2.5 s; four `crate`s (pickups, counted in `crates`) in lane 2. Sea and skyline
  scroll at different speeds. Won after 45 s or 10 drones down; lost if health is gone.
- `"boss"`: kind `boss`. The `warship` bobs in an orbit with three weak points that open
  2 s and close 1.5 s, staggered; the `sight` sweeps and Action hits whatever open weak
  point it is over; each needs 2 hits. A homing `shell` every 3 s. Won when the boss is
  down; lost at 40 s or no health. Two tries.
- `"charge"`: kind `alternate`. Left-right pairs add 9 to `charge` against a drain of 12
  a second; the bar is shown only in this phase. Won at 100 within 10 s.
- HUD: health pips, progress bar, combo, score, the crates counter, the prompt bar, the
  callout line. Style: `comic`, white flash between phases.
- Pays: 500 a kill; an add-a-ball for the boss; a lit jackpot for the charge; an extra
  ball at 4 crates; a saved value on a win.

```json
{
  "format": 1, "kind": "pad-video-mode", "id": "night-harbour", "title": "Night Harbour",
  "stage": {"width": 1360, "height": 768, "steps_per_second": 60, "background": "#05080f"},
  "phases": [{
    "id": "boss", "kind": "boss", "title": "Warship", "objective": "Hit the weak spots",
    "length_s": 40, "music": "boss_music",
    "settings": {"boss": "warship", "hit_with": "sight", "sight": "sight",
      "weak_points": [{"x": -180, "y": -20, "r": 34, "hits": 2, "open_s": 2.0, "closed_s": 1.5, "offset_s": 0}],
      "attacks": [{"thing": "shell", "every_s": 3, "aim": "player"}]},
    "place": [{"thing": "warship", "x": 680, "y": 330}, {"thing": "sight", "x": 400, "y": 300}],
    "win": [{"when": "boss_down"}],
    "lose": [{"when": "time_up"}, {"when": "health_gone"}]
  }]
}
```
(An excerpt; the file is the whole of it.)

## 4 The draw list and the backend contract

The engine (PAD-1657) never draws. Each step it fills a **draw list**; a thin backend per
place draws it: WebGL in the app (PAD-1659), the game's GL frame on Spike 2 (PAD-1655)
and Spike 3 (PAD-1673), the Allegro draw hook on JJP (PAD-1674), each Spooky runtime's
own (PAD-1675), a dots renderer on CGC and Spike 1 dot-matrix titles (PAD-1676/1677).

### Determinism

The engine keeps its state in fixed point (signed 16.16) and integer steps; no floats
in the rules. The same document, seed and inputs give a bit-identical draw list on x86,
ARM and WebAssembly, so a draw list hash is the match check (PAD-1669). The draw list
itself carries fixed-point numbers; a backend converts to its own floats at the last
moment.

### The entries

```c
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
```

The list is a header (`pm_vm_frame`) then entries in **draw order**, each tagged quad or
box. **Words are quads**: the packer (PAD-1658) bakes each font of the document into a
glyph atlas from the same face (the card's font on the machine, the same file in the
app), and the engine lays text out into glyph quads with the font's own metrics. So
every backend draws only quads and boxes, text measures the same everywhere, and
outline, shadow and gradient are glyph-atlas variants, not backend features.

### What each backend must do

1. **Order.** Draw entries in list order (painter's algorithm), no reordering and no
   depth buffer. The engine has already sorted by depth, then by the order things were
   made (stable).
2. **Clear.** Fill the stage with `clear` first when `cover_game` is 1; when it is 0
   the stage is drawn over the game's own display (a HUD over the game).
3. **Premultiplied pictures.** Atlases are premultiplied at pack time. The colour a
   quad writes is `texel * T`, where `T = (tint.rgb * a, a)` and
   `a = tint.a * alpha / 255`.
4. **Blending.** `normal`: `out = src + dst * (1 - src.a)` (GL `ONE, ONE_MINUS_SRC_ALPHA`).
   `add`: `out = src + dst` (GL `ONE, ONE`). Boxes use the same, with their colour
   premultiplied by the backend.
5. **Sampling.** Bilinear, clamped; atlases carry 2 texels of extruded edge so nothing
   bleeds. Integer-scale pixel art may ask for nearest (a per-atlas flag).
6. **Shake and flash.** Offset every entry by `shake_*`; draw `flash` last over the
   whole stage with normal blending.
7. **State.** Restore every piece of GPU state it touched before handing the frame back
   to the game (PAD-1655), and free its textures when the mode ends.
8. **Cadence.** The engine steps a fixed 60 times a second. A backend draws when its
   screen wants a frame (about 29 a second on a real Spike 2, 60 in the app) and, before
   drawing, runs as many steps as wall time has passed, at most 4 (beyond that the game
   slows rather than skips). It draws the newest list; there is no blending between two
   steps, so the frame at step N is the same picture everywhere.

### The stage on other screens

Every mode is made on the 1360x768 stage. A screen of `W` x `H` shows it at a uniform
scale `s = min(W / 1360, H / 768)`, centred: a stage point `(x, y)` lands at
`(x * s + (W - 1360 s) / 2, y * s + (H - 768 s) / 2)`. Bars left over are filled with
`clear`. Never stretched.

- Spike 2 is 1360x768: `s = 1`, no bars.
- A 1920x1080 screen: `s = 1.4118`. The packer may offer sharper art at the screen's
  scale (PAD-1673); the stage stays the same.
- A screen the game turns (portrait glass): the backend rotates the whole stage; the
  document does not change.
- Titles whose screen differs (PAD-1672, 1674) get their own `W`, `H` in that ticket's
  verdict table.

**Dot-matrix screens** (128x32: CGC remakes, Spike 1 dot-matrix titles, PAD-1676/1677).
They show a 4:1 band of the stage: 1360x340 from `stage.dots.band_top` (default 214,
the middle). 1360/340 = 128/32, so the scale is uniform: each dot averages a 10.625-px
square (box filter in linear light), then is quantised to the panel's levels (16
shades of the dot colour on a mono panel, the remake's palette on a colour one). Words
are not shrunk: the dots renderer draws them with a dot font at dot size, laid out on
the same anchor. The editor shows the band and a "dots" preview (PAD-1676) so a maker
can keep the action inside it.

## 5 Budgets per machine

**All numbers are placeholders** until PAD-1655 measures Spike 2 and each platform ticket
measures its own; those tickets replace this table with what they find, and PAD-1658's
cost report and PAD-1669's budget meter read it from here.

| Budget | Spike 2 | Spike 3 | JJP | Spooky | Dots (CGC, Spike 1) | Placeholder until |
|---|---|---|---|---|---|---|
| Pictures in memory (packed atlases, after premultiply) | 48 MB | 128 MB | 96 MB | 96 MB | 4 MB | PAD-1655 / 1673 / 1674 / 1675 / 1676 |
| Largest atlas | 2048 x 2048 | 4096 x 4096 | 4096 x 4096 | 4096 x 4096 | 512 x 512 | same |
| Things alive at once | 300 | 500 | 400 | 400 | 100 | PAD-1657 (desk) then each platform |
| Quads drawn a frame (things + glyphs + particles) | 1500 | 3000 | 2000 | 2000 | 400 | same |
| Draw calls a frame (one per atlas and blend run) | 16 | 32 | 24 | 24 | n/a | same |
| Engine step on the machine's CPU | 2 ms | 1 ms | 2 ms | 2 ms | 2 ms | same |
| Card space for one video mode (pictures, sounds, clips) | 128 MB | 256 MB | 256 MB | 256 MB | 16 MB | PAD-1658 / each platform |
| Sounds | 16 sounds, 6 music beds (today's mode cap) | as Spike 2 | per runtime | per runtime | per runtime | PAD-1667 |

The engine itself is fixed-size (no malloc): its tables are sized from the largest
column above at compile time.

## 6 The editor's design language

The bar every editor ticket (PAD-1659, 1661-1667, 1669-1671) is held to. It uses the
app's own tokens (`app.css`) and parts (`ui.js`), so the editor looks like the rest of
PAD, not like a different program in a frame. The four mock-ups in
`docs/plans/video_mode_maker/` (shot for the gate) are the reference for it.

### Layout

```
+-------------------------------------------------------------------------------+
| toolbar 44px: mode name · phase picker · undo/redo · zoom · Play · Try on machine|
+--------------+-------------------------------------------------+--------------+
| Layers       |                                                 | Inspector    |
| 240px        |       THE STAGE (1360x768, fitted, centred)     | 300px        |
| (resizable   |       on --bg, with the safe area and bezel     | (resizable   |
|  200-360)    |                                                 |  260-420)    |
|              |                                                 |              |
+--------------+-------------------------------------------------+--------------+
| Timeline 200px (resizable 120-50%): tracks, playhead, keyframes, markers       |
+-------------------------------------------------------------------------------+
| play bar 36px: play/pause · step · restart · time · speed · frame cost · budget |
+-------------------------------------------------------------------------------+
```

- The stage is always in the middle and always the biggest thing. Docks collapse to a
  28px rail (their icon) and remember their size per user.
- Nothing jumps: panels have fixed widths while their content changes, lists keep their
  scroll on a refresh, numbers use tabular figures, and loading states hold the size of
  what will appear.
- Storyboard (phase picker) is a full-width board above the stage when opened, or a
  strip of cards in the toolbar's phase picker.

### Type

The app's faces only: `--sans` (IBM Plex Sans) for words, `--cond` (Plex Sans
Condensed) for panel headings and labels in tight places, `--mono` (Plex Mono) for
numbers in fields, the timeline's time and the frame cost. Sizes: 11px labels (upper
case, +0.06em tracking, `--ink-3`), 12px field text and lists, 13px body, 15px panel
titles, 20px empty-state headings. Weights 400, 500 and 600, nothing else.

### Spacing

A 4px grid. Panel padding 12px; between fields 8px; between groups 16px with an 11px
label above. Rows in Layers 28px; inspector fields 28px high; toolbar buttons 28px.
Radii: 6px for controls and cards (the app's most common), 10px for panels that float
(menus, the command palette), 999px for chips.

### Colour

- Surfaces: `--bg` behind the stage, `--bg-2` docks, `--panel` cards and fields,
  `--panel-2` hover, `--panel-3` pressed; `--line` / `--line-2` borders.
- Ink: `--ink` text, `--ink-2` secondary, `--ink-3` labels and hints.
- **`--accent` (amber) means "selected or active"** and nothing else: the selection, the
  playhead, the active tool, the primary button. Never decoration.
- `--ok`, `--warn`, `--err` only for budgets and checks (the budget meter goes
  `--ok` then `--warn` then `--err`); `--info` for hints and guides.
- Teams carry fixed hues on the stage overlay (hit boxes, layer dots): player `--info`,
  enemies `--err`, shots `--warn`, pickups `--ok`, scenery `--ink-3`.
- The stage itself shows the mode's own colours untouched: the editor never tints art.
- Light theme comes free from `:root.light`; every mock-up and screen is checked in both.

### Motion

Fast and quiet. 120ms for hovers and presses, 180ms for panels opening and docks
resizing, 240ms for the storyboard board; easing `cubic-bezier(.2,.75,.25,1)` (the
app's own). Nothing animates while the user drags. The stage and the player render at
60 fps on canvas; panels never re-render on a stage drag frame. `prefers-reduced-motion`
turns the panel motion off.

### Selection and handles

- A selected thing: a 1px `--accent` box at its bounds, eight 8px square handles
  (`--panel` fill, 1px `--accent` border), a round turn handle 24px above the top edge,
  the anchor as a small `--accent` cross. Multi-select: one box around all, each item
  dashed.
- Hover: a 1px `--accent-line` box, no handles.
- Snapping: guides in `--info`, 1px, with the distance in a small `--mono` chip.
- Hit boxes (toggle H): team colour, 1px, 20% fill.
- Locked things show a lock on hover and do not take a drag.

### Empty states

Every empty place says what goes there and offers the first step: an empty stage shows
"Drop pictures here, or pick a game kind" with the phase picker; empty Layers shows
"Nothing on the stage yet"; an empty timeline shows "Add a spawn wave" and "Add a
keyframe". The `Empty` part of ui.js, one sentence, one button, no illustration.

### Shortcuts

| Keys | Does |
|---|---|
| Space | Play / pause (in the editor); held while dragging: pan |
| `.` / `,` | Step one frame forward / back |
| Home | Back to the phase's first step |
| Ctrl+Z / Ctrl+Shift+Z | Undo / redo (unlimited, survives a reload) |
| Ctrl+C / Ctrl+V / Ctrl+D | Copy / paste / duplicate |
| Delete | Remove the selection |
| Arrows / Shift+arrows | Nudge 1px / 10px |
| Ctrl+G / Ctrl+Shift+G | Group / ungroup |
| Ctrl+A | Select everything on the stage |
| Ctrl+0 / Ctrl+1 / Ctrl+wheel | Zoom to fit / 100% / zoom at the pointer |
| H | Show hit boxes |
| K | Add a keyframe at the playhead |
| Ctrl+P | Phase picker |
| Ctrl+K | Command palette |
| F5 | Play from the start; Shift+F5 from this phase |
| ? | The shortcut sheet |
| Left Shift / Right Shift / Space / Enter | While playing: left flipper / right flipper / Action / Start |

### The mock-ups

Static HTML in `docs/plans/video_mode_maker/`, linking the real `app.css` so the tokens
and fonts are the app's own, with original placeholder art drawn in SVG:

- `stage.html`: the editor with Night Harbour's chase phase selected on the stage.
- `phases.html`: the storyboard and the game kind picker.
- `timeline.html`: the boss phase with its timeline open, keyframes and spawn waves.
- `play.html`: the mode playing in the app, with the play bar and the budget meter.

`scripts/shot_pad1654.py` shoots them in dark and light.

## 7 The ticket map

Merge order runs in waves; a ticket may start when everything it waits on is on main.
Status is kept current here as tickets land.

| Wave | Ticket | What | Waits on | Status |
|---|---|---|---|---|
| 0 | PAD-1654 | This plan, the format and its schema, the design language and mock-ups | - | this branch |
| 1 | PAD-1655 | Spike 2: a mode draws moving pictures on the glass every frame (the risk of the epic; measures the Spike 2 budgets) | - | queued |
| 1 | PAD-1656 | Mode SDK: held buttons, mash and alternate rates; screen-game state | - | queued |
| 1 | PAD-1657 | The engine: one C core, native and WebAssembly; the compiler from this format | PAD-1654 | queued |
| 1 | PAD-1658 | Pictures: sprite sheets, animations, backgrounds, atlases, the cost report | PAD-1654 | queued |
| 2 | PAD-1659 | In the app: play it at 60 fps with keyboard or gamepad | PAD-1657, 1658 | queued |
| 2 | PAD-1660 | Spike 2: a video mode plays inside a real game | PAD-1655, 1656, 1657, 1658 | queued |
| 3 | PAD-1661 | Editor: the stage, the layers and the inspector | PAD-1659 | queued |
| 3 | PAD-1667 | Sound: music per phase, effects on events | PAD-1659 | queued |
| 3 | PAD-1668 | In the pinball game: how it starts, what it pays | PAD-1660 | queued |
| 3 | PAD-1669 | Try it on the emulator; the app-machine match check | PAD-1659, 1660 | queued |
| 3 | PAD-1672 | Every Spike 2 title | PAD-1660 | queued |
| 3 | PAD-1673 | Spike 3 | PAD-1660 | queued |
| 3 | PAD-1674 | JJP | PAD-1660 | queued |
| 3 | PAD-1675 | Spooky | PAD-1660 | queued |
| 3 | PAD-1676 | Chicago Gaming remakes (dots) | PAD-1660 | queued |
| 3 | PAD-1677 | Spike 1, American, Dutch, Pinball Brothers, Barrels of Fun | PAD-1660 | queued |
| 4 | PAD-1662 | Game kinds 1: chase, thrust, aim, boss | PAD-1661 | queued |
| 4 | PAD-1663 | Game kinds 2: mash, alternate, tug, rhythm, sequence, dodge, shield | PAD-1661 | queued |
| 4 | PAD-1664 | Editor: storyboard, cutscenes, timeline with keyframes | PAD-1661 | queued |
| 4 | PAD-1666 | HUD and feel | PAD-1661 | queued |
| 5 | PAD-1665 | Rule cards | PAD-1662, 1663 | queued |
| 5 | PAD-1670 | Starter games, guide page, limits page | PAD-1662, 1663, 1664, 1666, 1667, 1668 | queued |
| 6 | PAD-1671 | The professional finish pass | PAD-1665, 1669, 1670 | queued |

Format changes: a ticket that needs a field this format lacks adds it in its own
branch with a format bump, a migration, a frozen fixture and its rows in section 3, in
that order; two tickets that bump at once take numbers in merge order.

## 8 Decisions

- **One schema file, loaded by the app and the tests**, with a small validator in the
  app for the keywords it uses (the app ships its own Python, without jsonschema). The
  test proves the schema uses no keyword the validator does not understand, and, where
  jsonschema is installed, that both agree (checked by hand on this branch: 21 of 21
  broken documents judged the same).
- **Any change bumps the format**, with a migration and a frozen fixture per step,
  rather than "unknown fields ignored": a silently dropped field is worse than a plain
  refusal.
- **Ids unique per list**, things and values sharing one namespace, rather than unique
  across the whole document: a picture and its thing naturally share a name.
- **Fixed-point engine state** for bit-identical draw lists on x86, ARM and WebAssembly.
- **Words are glyph quads** baked from the document's fonts, so backends draw only quads
  and boxes and text measures the same everywhere.
- **No blending between steps**: the frame at step N is the same picture on every
  screen, which the match check needs.
- **Dot-matrix screens show a 4:1 band** of the stage rather than a squashed whole.
