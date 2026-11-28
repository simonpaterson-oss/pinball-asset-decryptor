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
[1b The industry](#1b-video-modes-the-industry-made) ·
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

## 1b Video modes the industry made

David asked (2026-11-28) for a survey of real machines' video modes before the plan
was settled, so the kinds cover what pinball has done, not only the reference. About
60 machines from 1991 to 2025 were checked against their rule sheets
(pinballrulesheets.com, the old Tilt Forums sheets; ipdb and the funet / lysator rule
archives; bmigaming.com; pinballprimer.github.io), with Pinside and Kineticist where
they could be read. Values are the rule sheets'; a few sheets disagree with each other.

### The catalog

| Machine | Mode | Buttons | What you do | Ends / pays |
|---|---|---|---|---|
| Terminator 2 (Williams 1991) | the first DMD video mode | flippers move a crosshair; it fires by itself | shoot terminators, a plane, a falling extra-ball box | 3 hits on you or all killed; about 8-10M |
| Fish Tales (Williams 1992) | boat shoot | rod button or flippers fire torpedoes | boats cross at three depths; lead the shot | 20 s, 20 torpedoes; far boats pay more, 20/20 pays 20M, extra ball |
| The Getaway (Williams 1992) | lane race | hold a flipper to steer; gearshift picks speed | dodge cars in 3 lanes, pseudo-3D | higher gear pays more (about 16M in 4th, 27M in 5th); ranked the best 90s mode |
| Doctor Who (Bally 1992) | Dalek escape | one flipper short jump, both long jump | a runner jumping hazards in waves; fixed or random on hard | each wave relights it; extra ball on waves 2-3 |
| Black Rose (Bally 1992) | three micro-games | Fire button | knife throw (time it), walk the plank (mash), rigging swing (time it) | prize shown first |
| Guns N' Roses (DE 1994), Harley-Davidson (Sega 1999) | Gilby Rolls | flippers steer | a motorbike in 3 lanes; pass cars, hit pedestrians | a car ends it; fixed course, can be learned |
| Indiana Jones (Williams 1993) | Escape in the Cart | flippers pick the way at each fork | a mine cart speeding up; 25 right choices | 5M + 1M a turn, 30M to finish |
| ST:TNG (Williams 1993) | Shuttle Simulation | flippers left, right, centre | a tunnel of 10 caverns with forks; same layout every time | 1M a cavern, 50M artifact, extra ball for perfect; **declinable for 25M** |
| Dracula (Williams 1993) | werewolf hunt | flippers fire left and right | werewolves from both sides; 5 spare bullets | one reaches you: no bonus; pays per bullet left |
| Tales from the Crypt (DE 1993) | Door Prize | flippers pick a door, button opens | points or a victim behind each of 3 doors | the victim ends it; 3 rounds may give an extra ball |
| Jurassic Park (DE 1993) | skill shot, shoot out | trigger or left flipper | fire when the dinosaur is in the sights | timing, never takes the ball |
| The Shadow (Bally 1994) | Duel of Wills | trigger clears the screen once | dodge falling daggers | points rise per dodge; one is an extra ball |
| Corvette (Bally 1994), Viper (Sega 1998), Baywatch (Sega 1995) | drag race / beach run | mash (Corvette: left accelerates, right shifts) | race a computer opponent | win starts a multiball (Corvette); losing pays by progress (Viper) |
| Batman Forever (Sega 1995) | Rooftop Chase | hold a flipper to be in that lane, release drifts back | dodge in two sections, collect in two | fixed course; 100-150M |
| Apollo 13 (Sega 1995) | lunar landing | a flipper is a side thruster, both thrust up | land on a pad | 50/75/100M by pad, a crash still pays by time |
| Attack from Mars (Bally 1995) | Saucer Attack | flippers aim an auto-firing cannon; launch button is a smart bomb, once | Space Invaders style; at 50 saucers a mothership boss | a landed saucer ends it; 635M for all |
| Congo (Williams 1995), Indy 500 (Bally 1995), No Fear (Williams 1995) | boat, caution lap, motorbike | flippers steer (Congo: speeds up the longer you hold) | dodge waves; No Fear has 3 tracks so it cannot be memorised | finish bonus |
| Johnny Mnemonic (Williams 1995) | SNARF | four buttons move in 2D | collect dots before time runs out | a worst-of-the-90s pick |
| Theatre of Magic (Bally 1995) | Digital Pinball | flippers work tiny on-screen flippers | clear targets in 20 s | 40M or an extra ball; a worst-of-the-90s pick |
| Space Jam (Sega 1996) | hoop catch | flippers move the hoop | catch 16 shots | 50K each, 200K for all |
| Medieval Madness (Williams 1997) | Save the Children | flippers move, a button clears | defend three babies from buzzards | 30 kills wins; one baby taken loses |
| Starship Troopers (Sega 1997), X-Files (Sega 1998), Lost World (Sega 1997) | psychic test, trivia, vine swing | left cycles / right locks; flippers pick an answer; one press | guess a card; pick an answer; time one press | flat prize; tiny |
| Revenge from Mars (Williams 1999) | Pinball 2000 video on the playfield | action buttons aim / choose | mini-games while the ball plays (one holds the ball) | "Flawless" bonus on every mode |
| Terminator 3 (Stern 2003) | T2's mode with tanks | flippers aim, trigger fires | 3 hits and you lose | flawless bonus |
| Ghostbusters (Stern 2016) | Don't Cross the Streams; ESP cards | each flipper sweeps its stream; pick a card or cash out | catch 15 ghosts; double-or-nothing up to 64M | 60-80M; pays so much it became the only choice |
| Houdini (American 2017) | King of Cards | hold a flipper to set the throw, release to throw | throw cards through hoops that speed up | 45 s (operator 40-60 s); extra ball |
| Star Wars (Stern 2017) | asteroid flight | flippers steer, centre button boosts | dodge asteroids | per dodge, big no-hit bonus; levels stack |
| Pirates of the Caribbean (JJP 2018) | Liar's Dice | pick a stake, or walk away | double or nothing on points, gold or tilt warnings | walk away any time; rules screen |
| Oktoberfest (American 2019) | Tap-It! | flippers move, hold the button to fill | serve 20 customers, 4 misses allowed | 2-4K each |
| Elvira's House of Horrors (Stern 2019), Sonic (JJP 2024), Labyrinth | wheel stop, spin dash, the duel | one button in a window | stop a moving marker on the target | nothing if not stopped in 6 s |
| Godzilla (Stern 2021) | Fight or Flee | left fights, right flees | a decision on the two flippers | flee banks jackpot + time left |
| Venom (Stern 2023) | Scream | each flipper strikes its side | infected come from both sides | 10M just for starting, 10M for clearing |
| Jaws (Stern 2024) | Shark Hunter | flippers fire harpoons | shoot sharks, spare divers; harpoon pickups | 3000 x the video score; also playable from a menu |
| Harry Potter (JJP 2025) | spell training | flippers and Action | memorise a spell sequence, then enter it | +1x multiball scoring per spell |
| Munsters, Jurassic Park (Stern) | pizza eating, T-Rex pummel | Action mash | 6-10 s mash | per press |
| Evil Dead (Spooky 2024), Beetlejuice (Spooky 2022) | 80s-style video mode; shooting gallery | flippers move, Action shoots | zombies and a final beast | small pay: flavour |

Most modern titles have none at all (Stern's Batman 66, Deadpool, Black Knight, Iron
Maiden, Mandalorian, Foo Fighters, King Kong, TMNT, James Bond; JJP's Wonka, Toy Story,
Avatar; Spooky's Halloween, Ultraman; and more), and what modern games do have is often
a screen decision or a timing meter rather than a game. Pinside is split on video modes
(a poll had 62% wanting them back; others call them "not pinball"), which is a reason
for the maker's lessons below, not against the feature.

### What the survey teaches the maker

These are now rules of the format and the editor:

1. **Short, and the operator can change it.** Real ones run 6 to 60 s (Houdini 45 s,
   adjustable 40-60 s). Phases default to 20-45 s; `operator` lets the owner shorten or
   lengthen every phase by a percentage, or switch the mode off.
2. **Pay must not outweigh the playfield.** Ghostbusters' 60-80M video mode became the
   only thing anyone played and its skill-shot route had to be removed. The cost report
   (PAD-1658) and the pinball side (PAD-1668) warn when a mode's best pay is more than a
   set share of a good ball's score.
3. **Failing still pays something.** A floor (Venom pays 10M just for starting), a
   crash that still pays by time (Apollo 13), pay by progress (Viper): `pays.start_score`
   and `pays.floor`.
4. **Let the player say no.** ST:TNG offers 25M instead; Godzilla, Pirates and
   Ghostbusters let you cash out or walk away; Hot Wheels skips its film on a double
   flip: `entry.declinable`, `entry.decline_score`, `entry.skip_clips`, the `pick` kind's
   `cash_out`.
5. **Learnable or fresh, by choice.** Harley-Davidson, Batman Forever and ST:TNG are the
   same every time and players learn routes; No Fear has three tracks and Doctor Who's
   hard setting is random so nobody can: a phase's `layout` is `fixed` or `per_play`.
6. **One hidden extra ball.** Nearly every 90s mode slips an extra-ball item into the
   stream (T2, Getaway, Fish Tales, The Shadow, Attack from Mars, Doctor Who): an award
   `when` `collected` `of` a thing.
7. **Perfect and leftovers pay.** Flawless bonuses (Revenge from Mars, T3, Star Wars),
   bullets left (Dracula), time left (Godzilla): `when` `flawless`, and `per` on an award.
8. **The Action button is a special.** Smart bomb once per mode (Attack from Mars, The
   Shadow): a phase's `bomb`. Boost (Star Wars). Limited `ammo` (Fish Tales 20
   torpedoes, Houdini's cards). Auto-fire with aiming only (T2, Attack from Mars).
9. **Risk for reward.** The Getaway's gears: faster pays more (`gears`, `gear_button`).
10. **It gets harder.** Carts and saucers speed up within a phase (`ramp`), and a mode
    played again starts a level higher and pays more (Star Wars, Game of Thrones, Junk
    Yard): `levels`.
11. **Playable on its own.** Stern's challenge menus and Jaws' Shark Hunter play a video
    mode outside a game: `entry.from_attract`.
12. **Video score is its own scale.** Jaws pays 3000 x the video score: `pays.score_scale`.

Left out, with reasons: pinball inside pinball (Theatre of Magic, and one of the worst
rated) needs a ball physics engine for one example; free 2D movement (Johnny Mnemonic)
needed four buttons and is also rated among the worst; both stay possible as a
`custom` phase with rule cards.

## 2 Game kinds and where each was seen

The `kind` of a phase. Every kind traces back to the reference (section 1) or to real
machines (section 1b).

| Kind | What it is | In the reference | On real machines |
|---|---|---|---|
| `chase` | Steer between lanes, freely, or hold to sit in a side lane; Action fires; things to shoot, dodge and pick up arrive on a timeline; the world scrolls in layers | 3:27-4:09 | Getaway, Gilby Rolls / Harley, Batman Forever, Congo, Indy 500, No Fear, Star Wars (2017) |
| `thrust` | Hold a button to rise, let go to fall; another button fires; gaps, enemies and pickups scroll in | 6:06-6:33 | - |
| `aim` | A sight sweeps, is steered or fires by itself; Action fires or is held; ammo or an overheat meter limit it | 4:15, 5:06 | Terminator 2 and 3, Fish Tales, Attack from Mars, Jaws, Beetlejuice, Jurassic Park |
| `boss` | A big thing with weak points that open on a pattern, attacks to dodge, a health bar, stages | 4:15-4:36, 6:36-6:57 | Attack from Mars' mothership, Evil Dead's beast |
| `mash` | Hit a button fast to fill a meter against a drain, or race a rival | 4:45, 8:27 | Corvette, Viper, Baywatch, Munsters, Jurassic Park (Stern), X-Files |
| `alternate` | Left, right, left, right to fill a meter | 5:12, 9:21 | - |
| `tug` | Hold the named flipper and mash Action, while a second threat needs alternating | 7:21-8:24 | - |
| `rhythm` | Prompts travel to a hit line in time with the music; early, good and perfect windows | 9:54-10:09 | - |
| `sequence` | A shown, hidden or memorised run of buttons to enter in time | 9:36 | Harry Potter (memorise, then enter) |
| `dodge` | A tell, then a short window to press the named button | 4:57, 6:48 | The Shadow, Godzilla (Fight or Flee as a choice) |
| `shield` | A tell, then hold a button for a time | *(from the record)* | - |
| `timing` | A marker sweeps a bar; press, or hold and release, inside the window | 5:15 ("UNLEASH") | Black Rose, Lost World, Elvira's wheel, Sonic, Labyrinth, Houdini, Hot Wheels |
| `defend` | Enemies come from the sides or the top; the flipper on that side strikes; a few may get through | - | Venom, Dracula, Medieval Madness, Ghostbusters' streams |
| `catch` | Move a catcher between lanes or freely to catch falling things | - | Space Jam, Oktoberfest |
| `runner` | A runner jumps hazards: one flipper a short jump, both a long one | - | Doctor Who |
| `lander` | Side thrusters on the flippers, both (or Action) thrust up; land on a pad with fuel left | - | Apollo 13 |
| `route` | The way forks; pick left or right in time as it speeds up; learnable when fixed | - | Indiana Jones mine cart, ST:TNG shuttle |
| `pick` | Choose a door, card or answer with the buttons; prizes, doubles and a bust; cash out any time | - | Tales from the Crypt, Ghostbusters ESP, Pirates' Liar's Dice, Starship Troopers, X-Files trivia, Jack*Bot |
| `custom` | Starts empty; built from things and rule cards only (PAD-1665) | - | anything else (Tap-It, digital pinball, 2D chases) |

A single press after a charge ("UNLEASH", "THROW IT") is a `timing` phase with a wide
window; title cards are part of every phase (its `title` and `objective`).

## 3 The document: video_mode.json, format 3

Format 3 (PAD-1666) added the HUD's looks and text styles, `multiplier` and `popup` parts, `particles`, a
thing's `trail`, the style's new switches and amounts, `combo`, and a font's `outline`; a format 2 file
migrates unchanged but for its number (no multiplier, the old bursts as presets).

Format 2 (PAD-1667) added the music's `fade_s` and beat grid (`tempo_bpm`, `beat_offset_s`,
`beats_per_bar`) to `sounds` and let a `rhythm` phase take its tempo from its music; a format 1
file migrates unchanged but for its number.

One file per video mode: `<project>/modes/<slug>/video_mode.json`, beside the mode's art,
sound and clip files. The schema is
`pinball_decryptor/core/video_mode/video_mode.schema.json` (JSON Schema 2020-12); the
app reads a file only through `pinball_decryptor/core/video_mode/document.py`
(`load`, `migrate`, `check`), and `tests/test_video_mode_schema.py` loads the same schema.
The web UI gets it from the app over RPC (the editor, PAD-1661: `vmodes.edit_open` and `edit_commit`); there is no
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
| `format` | 3 |
| `kind` | Always `"pad-video-mode"`, so a stray JSON file is refused |
| `id` | The mode's slug, its folder name |
| `title` | Shown in the modes list and on the card (40 characters) |
| `notes` | The author's own notes |
| `seed` | The random seed; the same seed and the same inputs play the same game |
| `stage` | The stage (below) |
| `assets` | `pictures`, `sounds`, `fonts`, `clips`, `particles` |
| `values` | Meters and counters of the mode's own |
| `things` | What can be on the stage: one entry per kind of thing, placed or spawned by phases |
| `phases` | The playable parts |
| `flow` | The storyboard: clips, phases and ends wired together |
| `hud` | Health, meters, score, prompts, callouts |
| `cues` | Sounds on events |
| `style` | The look and the feel switches |
| `combo` | Kills close together chain a combo and a multiplier: `window_s`, `every` (kills a step of the multiplier; 0 none), `max` |
| `pays` | What it pays into the pinball game |
| `entry` | How it may be entered: `declinable` (offer a choice, paying `decline_score` instead), `skip_clips` (`none`, `double_flip`, `action`), `from_attract` (also playable on its own from attract mode) |
| `levels` | A mode played again gets harder and pays more: `carry` (`none`, per `player`, or for the whole `game`), `max_level`, `speed_step_pct`, `pay_step_pct` |
| `operator` | The owner's setting on the mode's row: `can_turn_off`, and the range `length_pct_min` to `length_pct_max` every phase's length may be scaled by |
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
`loop_start_s` (where a looping music bed loops back to). Music only (format 2): `fade_s`
(how long the bed fades in when it takes over, and out when it stops; absent 1 s), and its
beat grid: `tempo_bpm`, `beat_offset_s` (where the first beat falls in the file) and
`beats_per_bar` (absent 4), which a `rhythm` phase on that music and the timeline read.

`fonts`: `id`, `face` (the card's own font, written `card:<name>`, or a font file in the
mode folder named in `file`), `size` in stage pixels, `outline` (px of outline baked round each
glyph; absent a twelfth of the size, at least 2). The app draws the same face: the packer bakes each
font's glyphs three ways from it (fill, outline, and a ramp for gradients), see section 4 "HUD and feel".

`particles` (format 3): a burst or a trail, `id`, a `preset` (`spark`, `smoke`, `debris`, `glow`) and what
it changes: `count`, `speed` ([low, high] px/s), `direction` and `spread` (degrees, the whole fan),
`life_s`, `size` and `size_end` (px), `gravity` (px/s/s, down is +), `drag` (the share of speed kept
after a second), `colour` and `colour_end`, `blend`, `glow` (1 to 3 nested boxes, a soft edge),
`streak` (a streak along its speed), `picture` (drawn instead of a box).

`clips`: `id`, `file` (made with the existing clip tools and film_cut.py), `skippable`.

### `values`

Meters and counters the phases, HUD and rules read and change: `id`, `type` (`meter` or
`counter`), `start`, `min`, `max`, `drain_per_s` (a meter that empties by itself).

### `things`

One entry per kind of thing: `id`, `picture`, `animation` (one of the picture's),
`scale`, `team` (`player`, `enemy`, `enemy_shot`, `player_shot`, `pickup`, `health`,
`scenery`; collisions are by team), `health`, `points` (score when destroyed), `hitbox`
(overrides the picture's), `blend` (`normal` or `add`), `depth` (higher draws in front),
`mover`, and `trail` (format 3): `particles` (a particle's id or a preset) left behind every
`every_s`.

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
| `win`, `lose` | Conditions, any one of which ends the phase: `when` (`time_up`, `survive_s`, `score`, `kills`, `pickups`, `goal`, `health_gone`, `misses`, `boss_down`, `hits`, `accuracy`, `ammo_out`, `landed`, `crashed`, `cashed_out`, `busted`), `value`, `of` (a thing or a value) |
| `layout` | `per_play` (spawns, forks and picks drawn from a new seed each play) or `fixed` (the same every time, so it can be learned) |
| `ramp` | Speed over the phase: `speed_from` at the start to `speed_to` at the end (1 = as set) |
| `bomb` | A once-or-few-times screen clear: `button` and `uses` |

Rule events: `touch`, `value_crosses`, `timer_ends`, `pressed`, `held`, `mashed`,
`released`, `leaves_screen`, `phase_starts`. Rule actions: `add_health`, `score`,
`spawn`, `remove`, `animate`, `sound`, `shake`, `flash`, `change_value`, `set_value`,
`go_to`, `win`, `lose`. PAD-1665 may reshape the cards; that is a format bump.

### The settings of each kind

Buttons are `left`, `right` and `action` everywhere.

- `chase`: `player` (a thing), `steer` (`lanes`, `free`, or `hold`: held flipper puts
  it in that side's lane, release drifts back), `lanes` (2 to 7), `steer_speed`, `fire`
  (`action` or `none`), `shot` (the thing fired), `fire_per_s`, `ammo` (0 or absent:
  unlimited), `gears` (1 to 5 speeds, each faster and paying more) shifted with
  `gear_button`, `scroll_speed`, `health`, `hurt_blink_s`.
- `thrust`: `player`, `thrust_button`, `fire_button` (or `none`), `shot`, `ammo`,
  `gravity`, `thrust`, `max_fall`, `scroll_speed`, `health`.
- `aim`: `sight` (a thing), `move` (`sweep` along `sweep_path` over `sweep_s`, or
  `steer` at `steer_speed`), `fire` (`press`, `hold`, or `auto`: it fires by itself and
  the player only aims), `ammo`, `heat` (a meter), `heat_per_s`, `cool_per_s`,
  `overheat_lock_s`.
- `boss`: `boss` (a thing), `hit_with` (`sight` or `shots`), `sight`, `weak_points`
  (`x`, `y` relative to the boss, `r`, `hits`, and the open pattern `open_s`,
  `closed_s`, `offset_s`), `attacks` (`thing`, `every_s`, `aim`: `player` or
  `straight`), `stages`.
- `mash`: `meter`, `button`, `per_press`, `drain_per_s`, `goal`, `rival_per_s` (a
  computer rival filling its own bar: a drag race; first to the goal wins).
- `alternate`: `meter`, `per_pair`, `drain_per_s`, `start_side` (`left`, `right`,
  `either`), `goal`.
- `tug`: `meter`, `hold` (`left`, `right`, or `shown`: the screen names it and it
  changes every `switch_every_s`), `per_press`, `pull_back_per_s`, and the second threat
  `shake_every_s` / `shake_pairs` (alternations to shake it off), `goal`.
- `rhythm`: `music`, `tempo_bpm`, `offset_ms` (both absent: the music's own beat grid,
  format 2), `travel_beats` (how early a prompt appears), `chart` (`beat`, `button`,
  `hold_beats`), `perfect_ms`, `good_ms`.
- `sequence`: `buttons` (a fixed run) or `length` (random from the seed), `shown`,
  `flash_s` (shown this long, then hidden: enter it from memory), `per_press_s`,
  `rounds`.
- `dodge`: `buttons` (the ones a tell may name), `tell_s`, `window_s`, `count`.
- `shield`: `button`, `tell_s`, `hold_s`, `count`.
- `timing`: `input` (`press`, or `hold_release`: hold to charge, let go in the window),
  `button`, `sweep_s` (one crossing of the bar), `window_from` and `window_to` (0..1 of
  the bar), `shrink_pct` (the window narrows each round), `rounds`.
- `defend`: `enemy` (a thing), `from` (`sides`: the flipper on that side strikes, or
  `top`), `speed`, `every_s`, `count`, `reach` (how far a strike lands), `let_through`
  (how many may pass before it is lost).
- `catch`: `catcher` (a thing), `move` (`lanes` or `free`), `lanes`, `speed`,
  `misses_allowed`; what falls comes from the phase's `spawns`.
- `runner`: `runner` (a thing), `jump` (a button), `long_jump` (`both_flippers`, a
  button, or `none`), `jump_px`, `long_jump_px`, `scroll_speed`, `waves`.
- `lander`: `ship` (a thing), `gravity`, `side_thrust` (the flippers push it sideways),
  `up` (`action` or `both_flippers`), `up_thrust`, `fuel_s`, `max_land_speed`, and
  `pads` (`x`, `w`, `points`).
- `route`: `vehicle` (a thing), `forks` (the right side at each fork, `left` or
  `right`) or `fork_count` (drawn from the seed), `speed`, `speed_up_pct` (per fork).
- `pick`: `choices` (2: the flippers, or 3: left, Action, right), `outcomes` (`label`,
  `weight`, `result` `prize` / `double` / `bust`, `amount`), `bank_start`, `cash_out`
  (the button that banks and ends it, or `none`), `rounds`. With `layout` `fixed` the
  draws are the same every play, which tournament settings need.
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
`progress`, `prompts`, `callout`, `counter`, `text`, and in format 3 `multiplier` and `popup`), `x`, `y`,
`w`, `h`, `value` (the meter or counter it shows), `look` (`bar`, `pips`, `hearts`, `ring`, `number`,
`glyphs`), `font`, `colour`, `accent` (a bar's frame; the prompts' colour for a held button), `text` (`{n}`
is the number), `phases` (shown only in these; absent: all).

Format 3: words take `align` (`auto`, `left`, `centre`, `right`), `outline`, `shadow` and `gradient`
(colours; the gradient runs from `colour` at the top to it at the bottom). `danger` is the colour a
health, lives, timer or meter part turns, pulsing, at or under `low` (a share of full, absent 0.34);
`zones` (up to 4, `from`, `to`, `colour`) are a meter's danger zones, where its fill takes the zone's
colour and pulses. `count_up` (seconds) rolls a score or counter up to a new number; `pop` grows a number
that went up for a moment. `picture` draws pips, hearts and lives from a picture (frame 0 full, frame 1
empty). A `popup` part is pop-up words: on each happening in `on` (`kill`, `pickup`, `hit`, `hurt`,
`fire`, `prompt_good`, `prompt_perfect`, `prompt_miss`; absent `kill`) its `text` (absent `+{n}`, the
points) rises `rise` px from where it happened over `life_s`; a happening with no place (a prompt) uses
the part's own `x`, `y`.

### `cues`

`on` (`fire`, `hit`, `kill`, `pickup`, `hurt`, `prompt_good`, `prompt_perfect`,
`prompt_miss`, `phase_start`, `phase_won`, `phase_lost`, `won`, `lost`), `sound`,
`duck_music` (lower the music under it).

### `style`

`preset` (`clean`, `arcade`, `comic`, `retro_pixel`), and switches for each effect:
`shake`, `flash`, `particles`, `hit_stop`, `crt`; `transition` between phases (`cut`,
`fade`, `white_flash`, `wipe`, `iris`).

Format 3: every effect has its switch, so each can be turned off per mode: `shake`, `flash`, `particles`,
`trails`, `hit_stop`, `squash`, `blink`, `popups`, `count_up`, `pulse`, `crt` (absent: on, except
`hit_stop` and `crt`). Their amounts: `shake_amount` (1 as designed), `hit_stop_frames`, `transition_s`
(the way out of a phase and the way into the next), `crt_strength`. `bursts` names the particle each
happening throws (`kill`, `hurt`, `pickup`, `hit`, `fire`, `boss`): a particle's id, a preset, or `none`
(absent: spark, debris, glow, spark, none, smoke). A preset is a starting point applied once
(`core/video_mode/feel.py` `apply_preset`); the maker's changes after it are kept.

### `pays`

`multiplier_in` (a multiplier earned before the mode scales its score), `start_score`
(paid just for starting), `floor` (the least a finished mode pays, won or lost),
`score_scale` (pinball points per video point; Jaws pays 3000), and `awards`: `when`
(`won`, `lost`, `phase_won` with `phase`, `each_kill`, `pickups_reach` with `at`,
`start`, `flawless` (no hit taken), `collected` `of` a thing: the hidden extra ball),
`award` (`score`, `add_a_ball`, `extra_ball`, `light_jackpot`, `multiplier`,
`saved_value` with `name`), `amount`, and `per` (multiply the amount by what is left at
the end: `time_left_s`, `health_left`, `ammo_left`, or a value's id).

### The worked example: Night Harbour

`pinball_decryptor/core/video_mode/examples/night_harbour.json`, an original boat chase
shaped like the reference's first mode, with placeholder art paths (PAD-1670 makes the
art). It checks clean, in format 3 (`tests/data/video_mode/format_1.json`, `format_2.json` and
`format_3.json` are the frozen fixtures), with the comic style preset applied. In short:

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
  "format": 2, "kind": "pad-video-mode", "id": "night-harbour", "title": "Night Harbour",
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

### Packed pictures (PAD-1658)

`core/video_mode/pack.py` is what a backend loads. Per machine it writes `atlas.json` and
the atlases into `<mode>/build/<backend>/`, only through `for_card`, which refuses
(naming the sprites to shrink) when the mode is over a budget of section 5.

- Every frame is trimmed to its visible pixels (a tiled background is not, and its edge
  extrudes by wrapping), frames that are the same texel for texel are kept once, and all
  are packed (MaxRects, largest first) into the smallest power-of-two atlas that holds
  them, else pages of the machine's largest. 2 texels of extruded edge round each.
- `webgl`: `atlas_<n>.png`. Every machine: `atlas_<n>.pmat`, a 16-byte header (`PMAT`,
  u16 version 1, u16 format 1 = RGBA8 premultiplied, u16 width, u16 height, u16 flags:
  bit 0 nearest, bit 1 zlib, u16 0) and the texels, rows top down, zlib-compressed.
- `atlas.json`: per picture, per frame, `atlas`, `sx sy sw sh` (texels), `ax ay` (the
  anchor inside the source box, 16.16, exactly what `pm_vm_quad` carries), `fw fh ox oy`
  (the frame before the trim); per font, its glyphs the same way with `adv`, `x`, `y`.
  `texel_scale` is stage px per texel: 1, or 8 on dot-matrix screens, whose art is packed
  at 1/8 (they show the stage at 1/10.625).
- Memory is every atlas at 4 bytes a texel; card space is the written atlases plus the
  mode's sounds, clips and font files as they are.

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

### The engine (PAD-1657)

`pinball_decryptor/core/video_mode/engine/`: `vm_engine.h` / `vm_engine.c` are the whole
engine; `vm_tables.h` (made by `gen_tables.py`) holds its sine, arctangent and power
tables, so no float is used at run time. `vm_bot.c` (a test player), `vm_cli.c` (vmrun,
the native runner) and `vm_wasm.c` (the WebAssembly exports) are never in the machine's
object. `vm_engine.js` is the module the app's player loads; `vm_run.mjs` is vmrun's twin
on WebAssembly. `build.py` builds all three ways: `wasm` (committed as `vm_engine.wasm`,
with the source hash in `vm_engine.wasm.sha`, since a user's PC has no compiler),
`native`, and `arm` (mode.so's own flags; it refuses the object if it calls anything the
mode rules ban; it needs only libgcc's division helpers and `memset`). The mode runtime
links it by passing `vm_engine.c` to `build_mode.sh` beside the mode (PAD-1660).

The compiler is `compiler.py` (`compile_doc`, `compile_file`): ids become indexes, seconds
become steps, pixels a second become 16.16 a step, and the lanes and path lengths are
worked out there, so the C side never parses JSON. It reports every problem as "place:
what" (the checker's, then its own, such as a spawn lane past the chase's lanes or a
document bigger than the engine's tables) and keeps a list of notes for what plays
differently today (placeholder art, kinds and conditions still to come). `harness.py` is
the text harness: `python -m pinball_decryptor.core.video_mode.harness MODE.json --bot`
plays a mode in a terminal, events in words and the stage drawn in letters.

**Interface.** `vm_load` (the pack; every index is checked, a broken pack is refused),
`vm_start(seed, level)`, then `vm_step(input)` 60 times a second. The input is one word a
step: bit 0 left flipper held, bit 1 right, bit 2 Action, bit 3 the host saying the clip it
was asked for has ended. Out of each step come `e.list` (the draw list above; its
canonical words, `vm_list_words`, are what WebAssembly hands to JavaScript), `e.events`
and `e.cues`, and the run's hash (FNV-1a over every step's draw list words, events and
cues).

**Events** for the pinball side: `CLIP_START` (clip, skippable), `CLIP_STOP` (clip,
skipped), `PHASE_START` (phase, try), `PHASE_WON` (phase, steps left, health),
`PHASE_LOST` (phase, tries left), `SCORE` (added, total), `KILL` (thing, points),
`PICKUP` (thing, so far), `HURT` (health left), `FIRE`, `HIT` (weak point, hits left),
`FINISHED` (won, score, no hit taken). What `pays` makes of them is PAD-1668's. **Sound
cues** (`sound`, `op`, `duck`, `fade`): play a sound (from `cues`); the music is this bed from
now, fading in over `fade` steps as the one before fades out; the music stops, fading out
(PAD-1667: only a change is cued, so the music plays on through a result card, a phase tried
again and a next phase with the same bed; a cutscene, a phase without music and the end stop
it).

**A step**: the input's edges; the kind's own play; spawns; movers; collisions by team;
meters draining; the win conditions, then the lose ones (so a boss downed on the step the
last health goes is a win); then the draw list, built from scratch. A phase opens with
its title card (1.5 s, the opening transition in its first 0.3 s) and closes on CLEAR!,
BOSS DOWN!, TRY AGAIN or FAILED (1 s); a clip card waits for the host's bit (or the skip
`entry.skip_clips` names, when the clip is skippable).

**How the kinds play today.** `chase`: the lanes are rows, spread evenly from the top of
the phase's lowest background layer (the sea) to the stage's foot; a left press moves one
lane up, a right press one lane down (`hold`: the held side's lane, the middle when let
go; `free`: steer up and down); Action held fires `shot` at `fire_per_s`; a spawn's
`lane` puts it in that row; gears shift on `gear_button`. `boss`: the sight sweeps across
the weak points by itself and an Action press hits the open one it is over (`hit_with:
shots`: the player's shots must strike an open one); the flippers move the player along
the bottom; attacks leave the boss on their beat, aimed at the player. `alternate`: a left
then a right (or the other way) adds `per_pair`. `mash`: each press adds `per_press`,
against a rival bar when `rival_per_s` is set. `thrust`: hold to rise, let go to fall,
leaving the screen is a crash. Every other kind plays its things, spawns and conditions
for now, its own play coming with PAD-1662 and PAD-1663, and the compiler says so. A
pickup counts into the counter named after it (`crate` into `crates`) until rule cards
(PAD-1665) name the link. A homer gives up after 10 s; anything moving more than 256 px
off the stage is gone.

**Proved by** `tests/test_video_mode_engine.py`: golden replays (the bot's winning run of
Night Harbour, a random-button run, a random run on the 300-thing desk) give the
recorded hash on native and on WebAssembly, and the two print the same events, cues and
draw lists line for line; the same hash on Windows (zig), Linux (gcc) and 32-bit ARM
(the Spike 2 cross compiler, under qemu); Night Harbour plays start to finish in the text
harness; a million steps of random buttons (and the bot with one step in four random,
so every phase is reached) never leave bounds, under the address and undefined-behaviour
sanitizers on Linux; 120 broken packs are refused or played safely, never crash.

### The player in the app (PAD-1659)

**Play** on the Video modes tab opens the player (`webui/static/js/tabs/vmodes_play.js`; its Python half is
`vmodes.py` `play_open` / `play_save` / `play_recording`). `play_open` compiles the document and hands the page the
pack, the engine's two files (`vm_engine.js` is imported and `vm_engine.wasm` fetched through the app's own file
route), and each picture, font, sound and clip by the index the engine names it. The page is the WebGL backend of
section 4: it draws the draw list in order into one vertex buffer per frame, one draw call per run of the same
texture and blend, premultiplied (`UNPACK_PREMULTIPLY_ALPHA_WEBGL`), shake and flash as the rules say, on the stage
fitted to the pane at the screen's own pixels. Until PAD-1658's atlases are loaded by the app, a quad's `atlas` is
the picture's index and its source box is in the picture's sheet, so each sheet is its own texture; a picture with
no file yet is a team-coloured placeholder of the compiler's size, and the placeholder font's glyph grid is drawn
by the page. The cadence is rule 8: steps as wall time passes, at most 4 a frame, the newest list drawn; the
**machine rate** draws on a 29-a-second schedule while the engine keeps its 60 steps.

Buttons: Left Shift / Right Shift / Space / Enter, a gamepad's LB / RB / A / Start (triggers too), and on-screen
buttons. Start begins again when the play is over, or ends a clip (the host's `VM_IN_CLIP_DONE`); a clip with a
file plays as video over the stage, one without stands 2 s as a card. Sounds go through Web Audio, off until turned
on, by the machine's rules (section "Sound" below).

Every play keeps its input word a step. **Replay** plays them again from the same card and seed and must end on the
same draw list hash; **Save** keeps them as `<mode>/replays/<time>.inputs` with a `.json` (seed, card, steps, hash).
**Start here** starts the engine at any card of the flow: `vmw_start_at` in `vm_wasm.c` and `--card` in `vmrun` and
`vm_run.mjs`, which set the start card for that one `vm_start` (the engine's own C is unchanged). **Hit boxes** (H)
come from `vmw_hits`, the collisions' own boxes. The budgets panel meters quads, things and picture memory against
the machine picked, and counts draw calls as the machine makes them, from where PAD-1658's packer puts each frame.

**Proved by** `tests/test_video_mode_player.py` (every card of Night Harbour started natively and on WebAssembly
gives the same lines; the player's calls on `vm_engine.js` and a recorded play give the native hash; 300 things
with their hit boxes; the tab's calls; the Modes tab's video rows and wizard) and `scripts/shot_pad1659.py` in Edge
on David's PC (WebGL2 on the RTX 5090): a 283-step play from the chase, its replay in the player and the native
build on the same buttons all ended on one hash; the intro clip played and 13 effects and the chase music played
through Web Audio (Edge muted); the machine rate drew 29 frames a second at 60 steps; the 300-thing desk took
0.044 ms a step and 0.16 ms to draw a frame (about 1% of a 60 fps frame).

The Modes tab lists video modes with the rest (a Video pill; picking one opens it on the Video modes tab), and the
New mode wizard has a fourth way, **Video mode**, that needs a project but no card.

### The editor in the app (PAD-1661)

**Edit** on the Video modes tab opens the editor (`webui/static/js/tabs/vmodes_edit.js`; its Python half is
`vmodes.py` `edit_open` / `edit_commit` / `edit_undo` / `edit_redo`; the undo history is
`core/video_mode/history.py`), laid out as section 6 draws it: the toolbar, Layers and Assets on the left, the stage
with its rulers in the middle, the inspector on the right and a status line under them.

**The stage is the engine.** The engine takes a still of the phase, `vm_edit_still` (its first step as `phase_start`
leaves it, past the opening transition; the title card only when **Title** is on), and the player's WebGL backend
draws its draw list under a zoom and pan (`GLStage.setView`). A drag rewrites the places it moves in the engine's
loaded tables (`vmw_place_set`, editor only, never in the machine's object) and takes the still again on every
frame, so what the editor shows while dragging is what the engine draws, not a second drawing of it. The selection
boxes, handles, hit testing and snapping use the engine's own geometry of each placed thing (`vmw_place_boxes`:
place j is live thing j, since a phase's places spawn first, in order). A change that adds or removes things waits
for the pack the compiler makes of it (milliseconds). The engine and compiler hold 1024 placed things (they held
256; a phase may place 300).

**What it does.** Things and pictures dragged from Assets onto the stage (a picture becomes a thing of its own, team
scenery); move, scale (from the opposite handle) and turn (the round handle) with handles, Shift for steps; snapping
to the grid, the guides, the stage, the safe area and other things' edges and centres, with the gap to the thing
snapped to shown in px (Ctrl places freely); zoom at the pointer (Ctrl wheel), pan (wheel, Space drag, middle drag),
Fit and 100%; rulers with the cursor and the selection marked, guides dragged out of them and back to remove them;
the safe area and the machine's glass as overlays (the dot-matrix band, or a screen's frame); hit boxes (H) from the
engine's collisions; multi-select (Shift, a box), group and ungroup, align and distribute (one thing: to the stage),
copy and paste (between phases too), duplicate (Ctrl D, or Alt drag leaving the original), nudges, lock and hide;
Layers in draw order with their depth, dragged to reorder (the moved rows take a depth between their new neighbours',
the rest keep theirs); the inspector for the phase (title, objective, length, stage colour, safe area), for one
thing (place, size in px, scale, turn, depth, picture, animation, team, health, points, blend, hit box, how it moves)
and for several (align bar, place, arrange). Number fields scrub on drag and take typed numbers and arrows. A command
palette (Ctrl K) names every command, which with Tab, the arrows and F6 makes the editor whole from the keyboard;
`?` shows the shortcut sheet. **Play** (F5) opens the player on the phase's card, and Back to editing returns.

**Every change is one step.** The page sends the whole document after a change to `edit_commit`, which checks it,
compiles it and saves it (there is no save button), or refuses it whole with every reason and the page puts its copy
back. The history keeps each step as a diff (`{"p", "a", "b"}` a value set, `{"p", "i", "a", "b"}` a list spliced),
appended to `<mode>/.video_mode_history.jsonl` with the document's fingerprint, so undo and redo have no limit and
survive a reload; a file changed by something else starts a new history. The tab's own changes (bring art in, a
picture's settings, backgrounds) are steps too. Groups and guides live in the document's `editor` object; the view
(zoom, the overlays, the docks' widths) is the user's own, kept in the browser.

**Proved by** `tests/test_video_mode_editor.py` (300 random documents through a step and back, exactly; 500 mixed
edits through the tab's calls with the app closed and opened half-way, undone one by one to the empty document and
redone; a refused change saves nothing; a file changed outside starts afresh; the still of Night Harbour's boss
phase is where the game's own first 18 steps leave its things, a rewritten place moves in it, and
`tests/data/video_mode/stage_300.json`'s 300 placed things take a still in well under a frame; 1024 places compile,
1200 do not) and `scripts/shot_pad1661.py` in Edge: a 3 s drag on the 300-thing stage drew about 76 frames a second
at about 0.5 ms of work a frame; a phase laid out from nothing with the mouse only (dragged from Assets, a box drawn,
aligned and distributed) and with the keyboard only (the palette, Tab, arrows, Ctrl D, align), and the keyboard one
undone, after a reload of the page, back to an empty stage.

### Sound (PAD-1667)

**One set of rules, written once** in `core/video_mode/sound.py` and followed by the player (Web Audio) and the
machine (`pad_mode_assets.h`), so what the editor plays is what the machine plays:

- **One music voice.** The machine's music is one carrier playing one bed at a time, so a music change is the
  bed playing fading out over the new bed's `fade_s`, then the new one fading in over the same; a stop fades
  the playing bed out over its own; from quiet a bed fades in. The engine cues only a change (music plays on
  through result cards, retries and a next phase on the same bed); a cutscene, a phase without music and the
  end stop it. A looping bed goes back to `loop_start_s`.
- **Ducking.** A sound ducks the music wherever it plays when it is a `callout` or any cue of it says
  `duck_music` (the machine ducks per call, not per event): 28 volume steps of 1/3 dB (about 9.3 dB), down over
  150 ms, back over 400 ms, the machine's own dip.
- **One voice for effects and callouts**, as a mode's calls share the voice bus: a new one fades the one still
  sounding (30 ms) and starts once it is gone (167 ms, the emulator's median); an effect (a priority 3 call) whose previous play still sounds is
  skipped; a callout (priority 4) played again starts over. `sound.cue_log` is this rule in step time, and
  the player's log and the rig's are held to it.
- **Volumes** are each sound's `volume`; on the machine it is baked into the sound's file.

**The Sound card** on the Video modes tab: each sound with its waveform (`sound.peaks`, made off the page's thread;
the timeline's sound track is the same `<Wave>`), its loop point dragged on it, a music bed's fade shaded and its
beat grid drawn (bars strong); its role, volume, loop, fade, tempo, first beat and beats a bar; **Find the beat**
(`sound.find_beat`: onsets matched against themselves a beat later, 60 to 200 a minute, then the first beat's
phase; within 0.25 a minute and 12 ms on the test beds); music per phase; sounds on events; and the count against
the machine picked (`sound.machine_plan`), with what is left. A sound with no file yet plays a placeholder the app
makes (`sound.placeholder_wav`: a blip, a two-note chime, or bars of bass and click on the bed's own grid), as a
picture without one is a placeholder. Each sound change is one named step in the editor's undo history
(PAD-1661), undone from the tab's head or the editor alike (Ctrl+Z, Ctrl+Y).

**On the machine** (Spike 2; Spike 3 has the same mode runtime): `sound.machine_plan` puts the first music a phase
plays on the mode's own music, every other bed on a further bed by name (`pa_music_bed`'s), and each effect and
callout a cue plays on a call of the mode's own; a sound nothing plays is left off. The route carries **16 calls and
the mode's own music plus 6 more beds**; Night Harbour uses 5 and 2. No cap was raised: a mode that needs more is
told so (cue fewer sounds, let phases share music) - one sound can serve several events. `sound.machine_files`
writes the machine's 48 kHz WAVs and the code mode's `assets.json` sound fields; because the machine loops a record
from its start, each bed is baked: the whole file once, then its loop body again and again until it outlasts every
phase that plays it, each try with its cards (`sound.bed_seconds`, 150 s at most, the build's own cap on a bed). `engine/vm_sound.h` plays each
step's cues: `pa_call` for a sound, `pa_music_change` for the music. `pad_mode_assets.h` gained `pa_music_change`
(fade out, then the new bed in; or quiet without giving the game's music back, which `pa_end` does) and a call line's
`noduck` (the build writes it for a sound that does not duck; every other call ducks the music, as before).
Jersey Jack, Spooky and the dot-matrix machines count the sounds with no cap until their tickets set one.

**Proved by** `tests/test_video_mode_sound.py` (format 2 and its checks; the engine's music cues by phase, retries
and cutscenes; ducking per sound; the plan, its names and its over-the-cap words; baked beds; the machine's files;
`noduck` in the .assets file; `pa_music_change` and `noduck` on the desk against stand-ins of the runtime; the
placeholder and the beat finder; the player's Sounds class against `cue_log`; the tab's edits, undo and redo),
`scripts/shot_pad1667.py` (the shots, and the bot's winning run replayed in the app's player with sound on in Edge,
muted at the process: its 55 cues the native build's, step for step, 52 sounds and 2 beds played through Web Audio)
and `scripts/proof_pad1667_rig.py` (the same run on James Bond LE 1.06 in the emulator, muted: see the ticket).

### HUD and feel (PAD-1666)

**All of it is the engine's.** The HUD's looks, its words' styles and every effect are drawn by `vm_engine.c` into
the same draw list of quads and boxes, so the machine shows what the app shows and no backend gained a feature:

- **Words** are glyph quads from fonts baked once (`core/video_mode/fonts.py`) from the game's own glyph table
  (`card:<name>` in the extracted project; `card:default` is its largest named face) or the font file a font names;
  a stand-in is the app's own condensed face. Each glyph is baked three ways, white so the quad's tint colours it:
  its fill, its outline (the fill's alpha grown by a disc of the font's `outline` px) and a ramp (the fill's alpha
  times how far down the line it is). A styled word is up to four passes: the shadow (outline glyph, offset), the
  outline, the fill, and the ramp tinted the gradient's foot colour over it, so a two-colour gradient runs evenly
  across a whole word. The app's player and editor load one sheet a font and compile with its metrics; the machine's
  pack carries the same glyphs (item index the code point, +1000 outline, +2000 ramp, named in `atlas.json`).
- **The HUD's looks**: pips, hearts (seven boxes a heart), bars with a sheen and danger zones (a tinted band and a
  foot strip; the fill takes a zone's colour and pulses), rings of 24 dots, numbers. A part at or under `low` turns
  its `danger` colour and pulses. Scores and counters roll up to a new number over `count_up`; a number that went
  up pops for 10 steps. The prompts put each button's word in its place (left flipper, Action, right flipper) and
  light the held one; PAD-1663's round buttons draw for its own kinds. The combo multiplies kill points by
  `1 + (combo - 1) / every`, up to `max`.
- **Pop-up words** rise from where a kill, pick-up, hit, hurt or shot happened (24 alive at once; the oldest makes
  room), and a prompt's judgement from the part's own place.
- **Particles**: an emitter table of the document's particles then the four presets (spark, smoke, debris, glow),
  512 alive; a burst per happening (`style.bursts`) and a thing's `trail`. Each particle is a box (1 to 3 nested
  for a glow, stretched along its speed for a streak) or the particle's picture, growing and changing colour as it
  ages, full strength for 60% of its life then fading. Drag and gravity in 16.16 a step.
- **The feel**: shake (scaled by `shake_amount`), a red flash on a hurt and a white one when a boss goes down,
  hit-stop (`hit_stop_frames` on a kill or hit, two more on a hurt, three times on a boss), squash and stretch on a
  hit thing and a hurt player, the damage blink, transitions out of a phase as well as into the next
  (`transition_s`), and a CRT look (192 scan-line boxes and a 16-box edge).
- **Every effect has a switch** (`style`: VM_FX_* bits), so each can be turned off per mode; the editor shows what
  each costs, and `feel.costs` reports each effect's draw list entries at its worst against the machine's "Quads
  drawn a frame" row.
- **Style presets** (`feel.STYLE_PRESETS`: arcade, comic, clean, retro pixel) set the whole feel and every HUD part's
  look, colours and text style at once, adding pop-up words when there are none; places, sizes, fonts and values
  stay the maker's. Applied once as one undo step; the worked example carries the comic preset.

**In the editor** the still is taken with every HUD part showing sample numbers (`vm_edit_still` flag 2: a score,
a combo and its multiplier, the prompts, each pop-up at its own place), and the engine works out each part's box
from the entries it drew (`vmw_hud_boxes`). Parts are picked over things (the HUD is drawn on top), dragged with the
same snapping (`vmw_hud_set` moves them live), nudged, removed, listed under HUD in Layers and added from the HUD
palette under Assets (drag onto the stage or Enter). The HUD inspector covers place and size, look, what it shows,
colour and frame, words (text with `{n}`, font, align, outline, shadow, gradient, count-up, pop), danger colour and
low point, danger zones, a pop-up's happenings, rise and life, and its phases. **Style** opens the look and feel:
the presets, the cost against the machine's budget, each effect's switch with its cost and amount, the transition,
the bursts, the combo, and the particle editor (preset, count, speed, aim, spread, life, sizes, gravity, drag,
streak, glow, colours, blend) whose preview is the engine bursting the particle over the stage (`vm_edit_burst`,
editor only).

**Proved by** `tests/test_video_mode_feel.py`: format 2 reads on as 3; every preset checks, compiles, keeps the
maker's places and fits Spike 2's budget; a run shows shake, flashes, squash, blink, CRT, particles, pop-ups and the
count-up, and with every switch off (and each alone) shows none of it; hit-stop lengthens a run; the combo
multiplies; every preset gives the same hash natively and in WebAssembly; the busiest frame of glow bursts stays
under 1500 entries; a card's glyph table bakes fill, outline and ramp at the asked size into the sheet and the
pack; the editor's HUD boxes come from the engine and move where they are put; the tab gives the presets, switches
and costs and applies a preset as one undo step. On 32-bit ARM (the Spike 2 cross compiler, mode.so's rules, run
under qemu) the bot's winning run gives the golden hash, and a deliberately heavy setup (glow bursts on every
happening, smoke trails on every enemy and shot, CRT on) took 159 us a step against the 2 ms budget, its busiest
frame 1,374 entries of 1,500. In the app (Edge, `scripts/shot_pad1666.py`) the bot's run played at 55 to 57 frames
a second with 0.04 ms a step and 0.06 ms a frame of drawing. The same run on a real game's display in the emulator is
PAD-1669's match check, once PAD-1660 plays a video mode inside a game.

## 5 Budgets per machine

**Spike 2 is measured** (PAD-1655 in the emulator, `video_mode_spike2_drawing.md`; checked
against the cost report by PAD-1679): its runtime sends every picture to GL as RGBA8, and its
"KB of pictures on GL" line read 12,039 KB for a set whose atlases are exactly that at 4 bytes a
texel; its set file (`.padgfx`) holds the texels raw, so a Spike 2 atlas costs the card what it
costs memory. It kept 48 MB and 2048 x 2048. PAD-1679 packed the worked example (Night
Harbour) in the Video modes tab, wrote its atlas as a `.padgfx` with PAD-1655's writer and loaded
it on Godzilla Premium 1.16 in the emulator: the report said 8,388,608 bytes of memory and the
runtime "8192 KB of pictures on GL" (0% apart); the report's card bytes were the file's 8,388,672
plus the font tables the file will carry (0.04%). PAD-1655's frame costs are here too (time on
the game's GL thread, the list build on the tick, pictures sent a frame, sets at once); "things
alive" and "engine step" are the engine's own (PAD-1657 on the desk, PAD-1660 on Spike 2), and what the emulator cannot see
is the real GPU's fill (PAD-575): 1500 quads draw about 6.8 screens of pixels a frame, so the
runtime's budget line ("frames went to the glass") is the meter on a real machine. **The other
columns are placeholders** until each
platform ticket measures its own and replaces its column; PAD-1658's cost report and PAD-1669's
budget meter read this table through `budgets.py`, and `tests/test_video_mode_pack.py` keeps the
two in step (memory, largest atlas, card space, texel format, how the card holds an atlas).

| Budget | Spike 2 | Spike 3 | JJP | Spooky | Dots (CGC, Spike 1) | Placeholder until |
|---|---|---|---|---|---|---|
| Pictures in memory (packed atlases, after premultiply) | 48 MB | 128 MB | 96 MB | 96 MB | 4 MB | Spike 2 measured (12 MB run, 48 MB kept); PAD-1673 / 1674 / 1675 / 1676 |
| Texel format in memory | RGBA8, 4 bytes | RGBA8, 4 bytes | RGBA8, 4 bytes | RGBA8, 4 bytes | RGBA8, 4 bytes | Spike 2 measured; same |
| Atlases on the card | raw (`.padgfx`, mapped in) | compressed | compressed | compressed | compressed | Spike 2 measured; same |
| Largest atlas | 2048 x 2048 | 4096 x 4096 | 4096 x 4096 | 4096 x 4096 | 512 x 512 | Spike 2 measured (the emulator's GL takes 4096); same |
| Things alive at once | 300 | 500 | 400 | 400 | 100 | desk measured (PAD-1657: 306 alive, ~33 us a step on x86); then each platform |
| Quads drawn a frame (things + glyphs + particles) | 1500 | 3000 | 2000 | 2000 | 400 | Spike 2 measured (1500 at 30 a second); same |
| Draw calls a frame (one per atlas and blend run) | 16 | 32 | 24 | 24 | n/a | Spike 2 measured (4 to 6 for packed art, 512 still held); same |
| Drawing's part of a frame (the game's GL thread, average) | 0.3 ms | to measure | to measure | to measure | to measure | Spike 2 measured (0.1 ms at 300 quads, 0.1 to 0.3 at 1500); PAD-1673 / 1674 / 1675 / 1676 |
| Draw list build on the tick | 0.75 ms | to measure | to measure | to measure | to measure | Spike 2 measured (0.12 to 0.15 ms at 300 quads, 0.55 to 0.75 at 1500); same |
| Pictures sent to the GPU a frame (a set loads over several) | 6 MB | to measure | to measure | to measure | to measure | Spike 2 measured (a 12 MB set took 2 frames, the worst 22 ms); same |
| Picture sets loaded at once | 8, up to 96 MB a set | to measure | to measure | to measure | to measure | Spike 2: the runtime's own limits (PAD-1655); same |
| Engine step on the machine's CPU | 2 ms | 1 ms | 2 ms | 2 ms | 2 ms | PAD-1660 on Spike 2 (desk: ~300 us on emulated ARM); then each platform |
| Card space for one video mode (pictures, sounds, clips) | 128 MB | 256 MB | 256 MB | 256 MB | 16 MB | PAD-1658 / each platform |
| Sounds | 16 calls, its own music and 6 more beds (the mode sound route; not raised) | as Spike 2 | per runtime | per runtime | per runtime | PAD-1667 |

The engine itself is fixed-size (no malloc): its tables are sized from the largest
column above at compile time (`VM_MAX_*` in `vm_engine.h`: 512 things alive, 1024 placed things, 3072 draw
list entries, 96 kinds of thing, 32 phases; about 0.6 MB, kept static).

**Measured on the desk (PAD-1657)**, `tests/data/video_mode/desk_300.json` (306 things
alive: 150 orbiting, 150 on looping paths, mines, crates and shots, all colliding): a step
costs about 33 us on a desktop x86 (Windows and Linux alike), about 54 us in WebAssembly
under Node (the draw list copied out to JavaScript included), and about 300 us on 32-bit
ARM emulated under qemu, which is slower than the real chip. The Spike 2 figure is
PAD-1660's to measure, with a video mode inside a real game.

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
- `phases.html`: the storyboard and the game kind picker (all 18 kinds and the empty phase, grouped).
- `timeline.html`: the boss phase with its timeline open, keyframes and spawn waves.
- `play.html`: the mode playing in the app, with the play bar and the budget meter.

`scripts/shot_pad1654.py` shoots them in dark and light.

## 7 The ticket map

Merge order runs in waves; a ticket may start when everything it waits on is on main.
Status is kept current here as tickets land.

| Wave | Ticket | What | Waits on | Status |
|---|---|---|---|---|
| 0 | PAD-1654 | This plan, the format and its schema, the design language and mock-ups | - | released (v1.641.0) |
| 1 | PAD-1655 | Spike 2: a mode draws moving pictures on the glass every frame (the risk of the epic; measures the Spike 2 budgets) | - | released (v1.645.0; its budgets are in section 5) |
| 1 | PAD-1656 | Mode SDK: held buttons, mash and alternate rates; screen-game state | - | queued |
| 1 | PAD-1657 | The engine: one C core, native and WebAssembly; the compiler from this format | PAD-1654 | released (v1.646.0) |
| 1 | PAD-1658 | Pictures: sprite sheets, animations, backgrounds, atlases, the cost report | PAD-1654 | released (v1.643.0; Spike 2 card cost checked by PAD-1679, v1.644.0) |
| 2 | PAD-1659 | In the app: play it at 60 fps with keyboard or gamepad | PAD-1657, 1658 | released (v1.647.0) |
| 2 | PAD-1660 | Spike 2: a video mode plays inside a real game | PAD-1655, 1656, 1657, 1658 | queued |
| 3 | PAD-1661 | Editor: the stage, the layers and the inspector | PAD-1659 | released (v1.648.0) |
| 3 | PAD-1667 | Sound: music per phase, effects on events | PAD-1659 | on its branch |
| 3 | PAD-1668 | In the pinball game: how it starts, what it pays | PAD-1660 | queued |
| 3 | PAD-1669 | Try it on the emulator; the app-machine match check | PAD-1659, 1660 | queued |
| 3 | PAD-1672 | Every Spike 2 title | PAD-1660 | queued |
| 3 | PAD-1673 | Spike 3 | PAD-1660 | queued |
| 3 | PAD-1674 | JJP | PAD-1660 | queued |
| 3 | PAD-1675 | Spooky | PAD-1660 | queued |
| 3 | PAD-1676 | Chicago Gaming remakes (dots) | PAD-1660 | queued |
| 3 | PAD-1677 | Spike 1, American, Dutch, Pinball Brothers, Barrels of Fun | PAD-1660 | queued |
| 4 | PAD-1662 | Game kinds 1: chase, thrust, aim, boss; and from the survey defend, catch, runner, lander, route | PAD-1661 | queued |
| 4 | PAD-1663 | Game kinds 2: mash, alternate, tug, rhythm, sequence, dodge, shield; and from the survey timing, pick | PAD-1661 | queued |
| 4 | PAD-1664 | Editor: storyboard, cutscenes, timeline with keyframes | PAD-1661 | queued |
| 4 | PAD-1666 | HUD and feel | PAD-1661 | done, waiting to ship |
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
- **Seven kinds added from the survey** of real machines (`timing`, `defend`, `catch`,
  `runner`, `lander`, `route`, `pick`), split between PAD-1662 and PAD-1663, rather than
  leaving them to rule cards: each is used by several shipped games.
- **Not kinds:** pinball inside pinball and free 2D movement, each from one poorly rated
  90s game; a `custom` phase can still build them.
- **The survey's lessons are format fields**, not editor advice: short adjustable
  length, a pay floor, decline and cash-out, fixed or per-play layouts, levels, the
  hidden extra ball, flawless and leftover pay.
- **The engine's input is one word a step** (three buttons held, and the host's "the
  clip ended"), so a recorded run is one byte a step and replays anywhere; the engine
  finds presses and releases itself, and PAD-1656's rates come from the same edges.
- **A chase's lanes are rows** across the lowest background layer, with left up and right
  down: the document's things scroll in from the right along the sea, so rows are what a
  spawn's `lane` can mean. A top-down chase would want columns: that is a field to add
  (with a format bump) when a kind needs it.
- **Win before lose on the same step**, and a clock that runs out with no condition met
  loses the phase.
- **Outline, shadow and gradient are baked glyph variants** (PAD-1666): an outline glyph and a ramp glyph per letter,
  tinted, rather than offset copies of the fill or a backend shader: two to four quads a styled letter, any colours,
  the same on every backend.
- **A preset is applied once**, not kept live: it writes the looks into the document, so the maker's changes after it
  stay and a later preset is a new step, not a theme that overrides.
- **The HUD and its effects are on the engine's list, inside the machine's quad budget**, each switchable and costed,
  rather than a second layer a backend draws.
- **Pictures without a file yet are drawn as placeholders** the size of their hitbox, and
  fonts use monospace placeholder metrics, until PAD-1658 packs the real atlases and
  glyphs; the compiler takes both as inputs, so nothing in the engine changes then.
