# Spike 2: moving pictures on the glass (PAD-1655)

The risk of the video mode maker epic (umbrella PAD-1654, `docs/plans/video_mode_maker.md` on its
branch): before this ticket a Spike 2 mode could show, hide and re-word nodes baked into the hud
scene, or play a clip, and nothing moved. A video mode needs a few hundred textured quads placed
freely every frame, with alpha, scale, turn and tint, over the game's own display, at the machine's
frame rate. This is the route, the proof, and the budgets measured.

## The route: draw at the game's own `eglSwapBuffers`

Every frame the game builds ends with `eglSwapBuffers` on the thread that owns its GL context,
called through the game program's own import slot. The mode runtime re-points that slot the first
time a mode loads a picture set (`pm_gfx_load`). In the wrapper, just before the frame goes out:

1. pictures still waiting are sent to GL (6 MB a frame at most, so a big set never stalls one frame),
   then their copy in memory is unmapped;
2. the newest draw list the mode finished on its tick is drawn with a program of the runtime's own,
   in a vertex array object of its own, premultiplied (`ONE, ONE_MINUS_SRC_ALPHA`, or `ONE, ONE` for
   an added quad), the game's destination alpha left as it was;
3. every piece of GL state touched is put back: program, array buffer, framebuffer, viewport, vertex
   array, active texture unit and its 2D binding, blend functions and equations, blend / cull / depth /
   scissor / stencil / alpha-to-coverage / sample-coverage, colour mask;
4. the real `eglSwapBuffers` (or whatever was in the slot before: the picture settings' hook, the image
   sets', padmenu's) is called.

Threads: the tick builds, the renderer draws. Three lists handed over by one atomic exchange each
way: the tick never waits for the renderer, the renderer never waits for the tick, and only the
renderer thread calls GL. A frame with no new list draws the last one again.

Lifetime: a set belongs to the mode that loaded it. When the mode stops running (its `pm_end`, its
ball, the game's end) its list comes off the glass at the next frame, the cover with it, and its
textures are deleted from GL and its memory unmapped. The display is then the game's, exactly as it was.

**The magnet hazard is excluded by construction.** Nothing of the game waits on a mode's drawing:
the game's frame is built exactly as before, the game's renderer is never handed anything (PAD-301's
lesson: a picture handed to the renderer from the tick stopped the game building frames), and the
wrapper does bounded work and calls on. A slow GPU would lower the frame rate the budget line shows,
never hold a game process.

### Why the others lost

- **Radium node transforms on a pool of baked Sprite nodes (b).** Only pictures already baked into the
  card's hud scene can move; the pool is per scene and per title (a site per port and a scene
  grammar per title to find the Sprites); every move goes through the game's own scene update on
  the game's CPU budget; and alpha/tint/turn per node depend on which Radium properties each scene
  exposes. A video mode's art is its own, so this cannot carry it.
- **Drawing at the game's frame hand-over (`frame_end` / `frame_kick`, PAD-301) (a, as first worded).**
  It needs a site pair per port, and a draw there is a request in the game's own render list: the
  machine's renderer, needing about two refreshes a frame, refused the tick's draws while the last
  frame still held the player. The swap is later than any of that: the frame is finished, the
  context is ours for a moment, nothing queues.
- **Sampling threads first (c).** The thread that calls the swap was found from the program's import
  table, not from game code: `gfx_import_slot` reads the program's `PT_DYNAMIC` (its `R_ARM_JUMP_SLOT`
  for `eglSwapBuffers`) at run time; the picture settings (PAD-537/575) and image sets (PAD-1390) had
  already proven that slot is called once a frame, on the GL thread, on every Spike 2 build.

### Generic or per title

**Generic (this ticket, every Spike 2 build):** the slot (from the program's relocations; no `site`
line), the GL calls (looked up by name in the game's own `libGLESv2.so.2` / `libEGL.so.1`), the
draw list, the stage scaling, the set file, the fonts. Godzilla Premium and LE 1.16 and Uncanny
X-Men Pro and LE 0.98 ran the same object with no port change.

**Per title (the rollout tickets of the epic):** where a video mode's ball waits while it plays (a
scoop, a lock, the end of a ball: today's holds stop at 10 s), which cabinet buttons it reads and
keeps from the game (PAD-1403/1656), and anything a title's screen does differently (its size, a
turned glass). None of those touch the drawing.

## The SDK calls (`pad_mode.h`, "moving pictures")

`pm_gfx_load / ready / free`, `pm_gfx_picture / picture_size / font`, `pm_gfx_stage`,
`pm_gfx_begin / quad / box / text / text_width / end / clear`, `pm_gfx_cover`. A `struct pm_quad`
is the backend side of the epic's draw list contract (`video_mode_maker.md` section 4): picture and
source box, anchor (0..1) and where it lands on the 1360x768 stage, scale x/y (negative flips),
turn (degrees clockwise) about the anchor, alpha, tint, depth (lowest first, stable), blend normal or
add; boxes are quads of the white texel; words are glyph quads laid out from the font's metrics;
`pm_gfx_cover(1, rgb)` fills the whole surface with the stage's `clear` under everything. What the
engine (PAD-1657) adds on top is its own: fixed point to float at the last moment, shake as an
offset on every entry, flash as a last full-stage box.

The set file, `.padgfx` (`pinball_decryptor/plugins/stern/gfx_set.py`): pictures (straight or
premultiplied, a flag each), fonts (an atlas and a glyph table each, code points sorted, offsets and
advances in 1/8 px). `gfx_set.card_font` bakes the card's own font from an extract the way the
Scenes preview lays it out (cell scale or metric fit, bearings, advances; kerning not carried), so
the words are the game's letters: the proof drew Godzilla's `GameFont_Primary`.

## The proof (emulator, 2026-11-28)

`gfx_test_mode.c` on each build, a real game started with its ball waiting in the shooter lane, the
rig at the machine's cadence (`--fps 30`) and real time: 60 s loaded and armed with nothing drawn
(the baseline), 150 s of 300 quads moving over the game's display (Lissajous paths, alpha, turn,
tint, depth, sprite sheet frames, one in seven added, words in the card's font), 150 s the same with
the game's display covered and a full-stage backdrop, then `pm_end`. Five minutes of quads.

Every build passed, on the final object (run 4), a minute at a time from the runtime's own budget
line (frames that went to the glass in that minute, how many carried the list, draw calls, the
runtime's part of each frame on the GL thread, and the list's build on the tick):

| Build | baseline (armed, nothing drawn) | 5 min of 300 quads (338 with the words) | draw calls a frame | our part of a frame, average (worst) | list build on the tick | coil drives while drawing |
|---|---|---|---|---|---|---|
| Godzilla Premium 1.16 | 30.0 a second | 30.0 every minute, list on every frame | 4 to 6 | 85 to 102 us (7.5 ms) | 121 to 155 us | none (26 before, 26 after) |
| Godzilla LE 1.16 | 29.8 | 29.9 to 30.0 | 4 to 6 | 74 to 102 us (7.9 ms) | 113 to 146 us | none (47, 47) |
| Uncanny X-Men LE 0.98 | 29.5 | 30.0 | 4 to 6 | 75 to 91 us (3.4 ms) | 116 to 142 us | none (24, 24) |
| Uncanny X-Men Pro 0.98 | 29.9 | 30.0 | 4 to 6 | 74 to 85 us (5.4 ms) | 111 to 140 us | rig 2's trough eject, below |

| Build, 1500 quads (1540 with the words) | baseline | 5 min of quads | draw calls | our part of a frame | list build |
|---|---|---|---|---|---|
| Godzilla Premium 1.16 | 30.0 | 29.8 to 30.0 | 4 to 6 | 104 to 313 us (32.9 ms) | 548 to 727 us |
| Uncanny X-Men LE 0.98 | 29.9 | 29.9 to 30.0 | 4 to 6 | 112 to 297 us (47.3 ms) | 592 to 743 us |

The worst single frames are the rig host's scheduling (four rigs on ten cores at once, the batch
warned so); the averages are the cost. Ball search and Tech Alerts stayed quiet: the game was on,
its ball waiting in the shooter lane, and with hwshim's coil probe on no coil fired from the first
mark before the drawing to the last after it, on the three rigs with a ball feed. Rig 2 (X-Men Pro,
and the X-Men LE 1500 run) has had its ball feed switched off since 2026-10-27, and there the game
retries its trough eject (node 8 coil 1) every 5.78 s from 44 s after boot, in attract, at the same
rate before, during and after the drawing: the rig's, not the drawing's. The magnet hazard: nothing
holds the game (above).

An earlier run (run 3) drew 1500 quads from five separate pictures interleaved, so each quad was its
own draw call: 512 calls a frame (the batch table's old size, which then dropped the rest; it now
holds one batch per quad, so a list is never cut short) and still 30.0 frames a second, our part of
a frame 476 to 542 us. Packed art (one atlas, the engine's way) is 4 to 6 calls.

The set (12.0 MB: the placeholder shapes, their atlas, a 1360x768 backdrop, Godzilla's
`GameFont_Primary`) went to GL in the baseline minute, 6 MB a frame; the frames that carried it are
the baseline's worst (12 to 22 ms). Pictures on GL: 12,039 KB while the mode ran, 0 KB after.

**Memory is flat for the drawing.** The emulated game's process grows about 95 MB a minute on these
rigs whether or not a mode draws: run 2 put a drawing rig and a never-armed rig of the same build side
by side for seven minutes (resident memory sampled from outside every 10 s):

| Build | never armed: start, end | drawing: start, end |
|---|---|---|
| Godzilla Premium 1.16 | 1017 MB, 1911 MB | 1018 MB, 1918 MB |
| Uncanny X-Men LE 0.98 | 687 MB, 1591 MB | 676 MB, 1555 MB |

The difference is within the rigs' noise; the pictures on GL go from 11.8 MB to 0 when the mode ends.

**The display comes back exactly.** The host harness (`tests/test_pad1655_gfx.py`) compiles this
section of the runtime against a fake GL that keeps a real one's state: after every swap (uploading,
drawing, covered, freeing) the state is byte-for-byte what the game had. On the rigs the shot after
the mode's end is the game's own screen (the pairs at the gate).

## Budgets for Spike 2 (measured in the emulator)

These are the Spike 2 column of `video_mode_maker.md` section 5, the epic's budget table
(copied in by PAD-1679 and PAD-1680); `budgets.py` carries the ones the cost report reads.

| Budget | Spike 2, measured | How |
|---|---|---|
| Quads drawn a frame | **1500** at the game's 30 a second (things, glyphs, boxes; 2048 is a list's cap) | run 4, Godzilla Premium and X-Men LE, 5 min each |
| Draw calls a frame | **16** keeps the margin; 4 to 6 measured for packed art, and 512 still held 30 a second | runs 3 and 4 |
| The runtime's part of a frame (GL thread) | 0.1 ms at 300 quads, 0.1 to 0.3 ms at 1500, on average | the budget line, every minute |
| A list's build on the tick | 0.12 to 0.15 ms at 300, 0.55 to 0.75 ms at 1500 | the budget line |
| Pictures sent to the GPU | 6 MB a frame (a 12 MB set: 2 frames, the worst 22 ms) | run 4's baseline |
| Pictures in memory | 12 MB proven, freed to 0 at the end; a set up to 96 MB, 8 sets at once (the runtime's limits); keep the epic's **48 MB** until a set that size is run | run 4; run 2 for memory |
| Largest picture | **2048 x 2048** (the packer's limit; the runtime reads the GPU's own and logs a larger one) | the emulator's GL says 4096 |
| Things alive, engine step | not this ticket's: the engine (PAD-1657) measures its own step on the tick | |
| Memory | flat: a drawing rig and a never-armed rig grow alike (run 2) | |

What the emulator cannot see is the machine's GPU fill (PAD-575: a step on every pixel of every
layer dropped a real Godzilla to 7 to 9 frames a second in busy scenes while the emulator showed
nothing). The
proof's 300 quads draw about 1.4 screens of pixels a frame over the game, the covered phase 3.4
(the backdrop and the cover are a screen each; the game goes on drawing under the cover); 1500 quads
draw about 6.8. The runtime's budget line (`gfx: in the last 60 s ... frames went to the glass`)
is the meter on a real machine: it counts the frames that actually went to the glass.
