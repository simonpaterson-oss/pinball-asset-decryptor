"""PAD-1655: moving pictures on the glass - the picture set file and the runtime's drawing section.

The runtime's whole "moving pictures" section is compiled on the host, verbatim, against a FAKE GL that keeps the
state a real one would and records every draw: a set written by gfx_set.py loads, its pictures go to GL a budget a
frame and their memory is let go, quads come out sorted by depth with their turn, scale, tint and alpha, words are laid
out from the card font's metrics, the cover goes under everything, and - the point of the route - every piece of GL
state the game had at its swap is exactly as it was after ours. When the mode stops running its list comes off and its
textures are deleted. The rig half (Godzilla, Uncanny X-Men Pro and LE for five minutes) is in
docs/plans/video_mode_maker.md.
"""

import math
import pathlib
import re
import struct

import pytest

from pinball_decryptor.plugins.stern import gfx_set as G

REPO = pathlib.Path(__file__).resolve().parents[1]
SDK = REPO / "tools" / "spike2_emu" / "modes" / "sdk"
RUNTIME = SDK / "pad_mode_runtime.c"


def _font():
    """A small font spec with known metrics: 'A' 10x12, 'B' 8x12, space; ascent 10, size 14."""
    from PIL import Image
    atlas = Image.new("RGBA", (32, 16), (255, 255, 255, 0))
    atlas.paste((255, 255, 255, 255), (1, 1, 11, 13))
    atlas.paste((255, 255, 255, 128), (13, 1, 21, 13))
    return {"name": "TestFont", "image": atlas, "size": 14, "line_h": 16, "ascent": 10,
            "glyphs": [(65, 1, 1, 10, 12, 0.5, -9.0, 11.25), (66, 13, 1, 8, 12, 1.0, -9.0, 9.5), (32, 0, 0, 0, 0, 0, 0, 4.0)]}


def _pictures():
    return [p for p in G.placeholder_pictures() if p[0] != "sky"]


def test_a_set_reads_back_as_written():
    data = G.pack(_pictures(), [_font()])
    s = G.read(data)
    names = [p["name"] for p in s["pictures"]]
    assert names == ["orb", "star", "ring", "ship", "sheet", "TestFont"]
    assert (s["pictures"][4]["w"], s["pictures"][4]["h"]) == (256, 128)
    f = s["fonts"][0]
    assert f["picture"] == 5 and (f["size"], f["line_h"], f["ascent"]) == (14, 16, 10)
    assert f["glyphs"][65] == (1, 1, 10, 12, 0.5, -9.0, 11.25) and f["glyphs"][32][-1] == 4.0
    assert list(f["glyphs"]) == sorted(f["glyphs"])                     # sorted: the runtime looks glyphs up by halves
    orb = dict(_pictures())["orb"].convert("RGBA").tobytes()
    assert s["pictures"][0]["rgba"] == orb                              # straight alpha, rows top first
    assert not s["pictures"][0]["premultiplied"]
    pm = G.read(G.pack(_pictures()[:1], premultiplied=True))["pictures"][0]
    assert pm["premultiplied"] and pm["rgba"][3::4] == orb[3::4]
    i = next(k for k in range(0, len(orb), 4) if 0 < orb[k + 3] < 255)  # a soft edge: its colour times its alpha
    assert pm["rgba"][i] == (orb[i] * orb[i + 3] + 127) // 255


def test_a_set_refuses_what_the_runtime_would():
    from PIL import Image
    with pytest.raises(ValueError):
        G.pack([("big", Image.new("RGBA", (G.MAX_SIDE + 1, 4)))])
    data = bytearray(G.pack(_pictures()))
    with pytest.raises(ValueError):
        G.read(bytes(data[:100]))
    data[0] = ord("X")
    with pytest.raises(ValueError):
        G.read(bytes(data))


def test_the_placeholder_art_is_original_and_tintable():
    """PAD ships no game content: the proof set is shapes drawn here, white so a tint colours them."""
    pics = dict(G.placeholder_pictures())
    assert set(pics) == {"orb", "star", "ring", "ship", "sheet", "sky"}
    assert pics["sky"].size == G.STAGE
    r, g, b, a = pics["star"].convert("RGBA").getpixel((32, 32))
    assert (r, g, b, a) == (255, 255, 255, 255)


def test_the_placeholder_atlas_holds_each_shape_where_the_proof_mode_reads_it():
    """gfx_test_mode.c draws from the "shapes" atlas by fixed boxes: they are gfx_set.PLACEHOLDER_BOXES, in order,
    and each box holds that shape's pixels."""
    src = (SDK / "gfx_test_mode.c").read_text(encoding="utf-8")
    body = src[src.index("static const float BOX[12][4] = {"):]
    body = body[:body.index("};")]
    boxes = [tuple(int(v) for v in m.split(",")) for m in re.findall(r"\{\s*([\d,\s]+?)\s*\}", body)]
    names = ["orb", "star", "ring", "ship"] + ["frame%d" % f for f in range(8)]
    assert boxes == [G.PLACEHOLDER_BOXES[n] for n in names]
    name, atlas = G.placeholder_atlas()
    pics = dict(G.placeholder_pictures())
    assert name == "shapes" and atlas.size == (256, 256)
    x, y, w, h = G.PLACEHOLDER_BOXES["star"]
    assert atlas.crop((x, y, x + w, y + h)).tobytes() == pics["star"].convert("RGBA").tobytes()
    for a, b in ((n, m) for n in names for m in names if n < m):         # nothing overlaps
        ax, ay, aw, ah = G.PLACEHOLDER_BOXES[a]
        bx, by, bw, bh = G.PLACEHOLDER_BOXES[b]
        assert ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay, (a, b)


def test_a_card_font_is_baked_by_the_scenes_rule(tmp_path, monkeypatch):
    """card_font places each glyph where fontrender.render_text draws it (bearing x, baseline - bearing y) and keeps
    the advance, so a mode's words are the game's letters, spaced as the game spaces them."""
    from PIL import Image
    from pinball_decryptor.plugins.stern import fontrender as FR
    glyph = {"char": 65, "rel": "", "atlas_rel": "", "fmt": 5, "abs": "", "x": 0, "y": 0, "w": 9, "h": 11,
             "rot": False, "lw": 9.0, "lh": 11.0, "bx": 1.5, "by": 10.0, "adv": 12.0, "kern": {}}
    font = {"key": "k", "name": "GameFont", "glyphs": {65: glyph}, "ascent": 10, "descent": 2, "px": 12,
            "cell_pad": 0.0, "cell_scale": None, "sizes": {}}
    monkeypatch.setattr(FR, "load_fonts", lambda d: [font])
    monkeypatch.setattr(FR, "load_slice", lambda g: Image.new("RGBA", (9, 11), (255, 255, 255, 255)))
    spec = G.card_font(str(tmp_path))
    rows = {g[0]: g for g in spec["glyphs"]}
    assert spec["name"] == "GameFont" and spec["ascent"] == 10 and spec["size"] == 12
    cp, x, y, w, h, ox, oy, adv = rows[65]
    assert (w, h, ox, oy, adv) == (9, 11, 1.5, -10.0, 12.0)
    assert rows[32][-1] == FR._space_advance(font)                      # a space the font has no slice for


HARNESS = r"""
#include "pad_mode.h"
#include <stdio.h>
#include <string.h>
#define O_RDONLY 0
#define CLOCK_MONOTONIC 1
#define PIC_RTLD_NOW 2
#define PIC_RTLD_NOLOAD 4
#define MAP_R 1u
#define MAP_X 2u
#define MAP_GAME 4u
extern int open(const char *, int, ...);
extern long read(int, void *, __SIZE_TYPE__);
extern int close(int);
extern int clock_gettime(int, void *);
extern int mprotect(void *, __SIZE_TYPE__, int);
extern void *dlopen(const char *, int);
extern void *dlsym(void *, const char *);
static const struct pm_mode *current;
static int running_ok = 1;
static unsigned long fake_ms;
static int runs_now(const struct pm_mode *m) { return m && running_ok; }
static const char *mode_name(const struct pm_mode *m, const char *none) { return m && m->name ? m->name : none; }
static void say(const char *fmt, ...) { va_list ap; va_start(ap, fmt); printf("say "); vprintf(fmt, ap); printf("\n"); va_end(ap); }
void pm_log(const char *fmt, ...) { va_list ap; va_start(ap, fmt); printf("log "); vprintf(fmt, ap); printf("\n"); va_end(ap); }
int pm_snprintf(char *o, unsigned long c, const char *f, ...) { va_list ap; int n; va_start(ap, f); n = vsnprintf(o, c, f, ap); va_end(ap); return n; }
unsigned long pm_ms(void) { return fake_ms; }
long pm_read_file(const char *p, char *b, unsigned long c) { (void)p; (void)b; (void)c; return -1; }
static int maps_has(unsigned long a, unsigned long l, unsigned how) { (void)a; (void)l; (void)how; return 0; }
@SECTION@

/* ---- a fake GL: the state a real one keeps, every draw recorded ---- */
static struct { int prog, abuf, fb, vp[4], vao, unit, tex[16], bf[4], eq[2]; unsigned char caps[8], mask[4]; } S;
static const unsigned CAPS[8] = { GX_BLEND, GX_CULL_FACE, GX_DEPTH_TEST, GX_SCISSOR_TEST, GX_STENCIL_TEST,
                                  GX_ALPHA_TO_COVERAGE, GX_SAMPLE_COVERAGE, 0 };
static unsigned next_name = 100, live_tex, bad;
static float xf[4], pm_now = -1;
static int capix(unsigned c) { int i; for (i = 0; i < 7; i++) if (CAPS[i] == c) return i; printf("bad cap 0x%x\n", c); bad++; return 7; }
static void f_GetIntegerv(unsigned p, int *v)
{
    switch (p) {
    case GX_CURRENT_PROGRAM: *v = S.prog; break;
    case GX_ARRAY_BUFFER_BINDING: *v = S.abuf; break;
    case GX_FRAMEBUFFER_BINDING: *v = S.fb; break;
    case GX_VIEWPORT: memcpy(v, S.vp, sizeof S.vp); break;
    case GX_VERTEX_ARRAY_BINDING: *v = S.vao; break;
    case GX_ACTIVE_TEXTURE: *v = S.unit; break;
    case GX_TEXTURE_BINDING_2D: *v = S.tex[S.unit - GX_TEXTURE0]; break;
    case GX_BLEND_SRC_RGB: *v = S.bf[0]; break;
    case GX_BLEND_DST_RGB: *v = S.bf[1]; break;
    case GX_BLEND_SRC_ALPHA: *v = S.bf[2]; break;
    case GX_BLEND_DST_ALPHA: *v = S.bf[3]; break;
    case GX_BLEND_EQUATION_RGB: *v = S.eq[0]; break;
    case GX_BLEND_EQUATION_ALPHA: *v = S.eq[1]; break;
    case 0x0D33: *v = 4096; break;
    default: printf("bad query 0x%x\n", p); bad++;
    }
}
static unsigned char f_IsEnabled(unsigned c) { return S.caps[capix(c)]; }
static void f_Enable(unsigned c) { S.caps[capix(c)] = 1; }
static void f_Disable(unsigned c) { S.caps[capix(c)] = 0; }
static void f_BlendFuncSeparate(unsigned a, unsigned b, unsigned c, unsigned d) { S.bf[0] = a; S.bf[1] = b; S.bf[2] = c; S.bf[3] = d; }
static void f_BlendEquationSeparate(unsigned a, unsigned b) { S.eq[0] = a; S.eq[1] = b; }
static void f_Viewport(int x, int y, int w, int h) { S.vp[0] = x; S.vp[1] = y; S.vp[2] = w; S.vp[3] = h; }
static void f_UseProgram(unsigned p) { S.prog = p; }
static void f_BindBuffer(unsigned t, unsigned b) { if (t == GX_ARRAY_BUFFER) S.abuf = b; }
static void f_Gen(int n, unsigned *o) { int i; for (i = 0; i < n; i++) o[i] = next_name++; }
static void f_GenTextures(int n, unsigned *o) { f_Gen(n, o); live_tex += n; }
static void f_BufferData(unsigned t, long n, const void *d, unsigned u) { printf("bufdata %ld\n", n); }
static void f_BindFramebuffer(unsigned t, unsigned f) { S.fb = f; }
static void f_VAP(unsigned i, int n, unsigned t, unsigned char nm, int st, const void *p)
{ if (S.vao != (int)gx_vao) { printf("attrib on the game's VAO\n"); bad++; } }
static void f_EVAA(unsigned i) { if (S.vao != (int)gx_vao) { printf("attrib on the game's VAO\n"); bad++; } }
static void f_DrawArrays(unsigned m, int first, int n)
{
    printf("draw tex=%d first=%d n=%d pm=%g ours=%d blend=%d,%d,%d,%d on=%d vp=%d,%d\n", S.tex[S.unit - GX_TEXTURE0],
           first, n, pm_now,
           S.prog == (int)gx_prog && S.vao == (int)gx_vao && S.abuf == (int)gx_buf && S.fb == 0, S.bf[0], S.bf[1],
           S.bf[2], S.bf[3], S.caps[0] && !S.caps[1] && !S.caps[2] && !S.caps[3] && !S.caps[4], S.vp[2], S.vp[3]);
}
static unsigned f_CreateShader(unsigned k) { return next_name++; }
static void f_ShaderSource(unsigned s, int n, const char *const *src, const int *l) { }
static void f_CompileShader(unsigned s) { }
static void f_GetShaderiv(unsigned s, unsigned p, int *v) { *v = 1; }
static unsigned f_CreateProgram(void) { return next_name++; }
static void f_AttachShader(unsigned p, unsigned s) { }
static void f_BindAttribLocation(unsigned p, unsigned i, const char *n) { }
static void f_LinkProgram(unsigned p) { }
static void f_GetProgramiv(unsigned p, unsigned q, int *v) { *v = 1; }
static int f_GetUniformLocation(unsigned p, const char *n) { return n[2] == 'x' ? 1 : 2; }
static void f_Uniform4f(int l, float a, float b, float c, float d) { xf[0] = a; xf[1] = b; xf[2] = c; xf[3] = d; }
static void f_Uniform1i(int l, int v) { }
static void f_Uniform1f(int l, float v) { pm_now = v; }
static void f_DeleteTextures(int n, const unsigned *t) { int i; for (i = 0; i < n; i++) printf("deltex %u\n", t[i]); live_tex -= n; }
static void f_BindTexture(unsigned t, unsigned x) { S.tex[S.unit - GX_TEXTURE0] = x; }
static void f_ActiveTexture(unsigned u) { S.unit = u; }
static void f_TexImage2D(unsigned t, int l, int f, int w, int h, int b, unsigned fm, unsigned ty, const void *px)
{ printf("upload tex=%d %dx%d px0=%d\n", S.tex[S.unit - GX_TEXTURE0], w, h, px ? ((const unsigned char *)px)[3] : -1); }
static void f_TexParameteri(unsigned t, unsigned p, int v) { }
static void f_BindVertexArray(unsigned v) { S.vao = v; }
static void f_GetBooleanv(unsigned p, unsigned char *v) { memcpy(v, S.mask, 4); }
static void f_ColorMask(unsigned char a, unsigned char b, unsigned char c, unsigned char d) { S.mask[0] = a; S.mask[1] = b; S.mask[2] = c; S.mask[3] = d; }
static unsigned swaps_on;
static unsigned f_next(void *d, void *s) { swaps_on++; return 1; }

static void swap(const char *tag)
{
    char before[sizeof S];
    memcpy(before, &S, sizeof S);
    gfx_swap(0, 0);
    printf("swap %s restored=%d\n", tag, !memcmp(before, &S, sizeof S));
}

static void list_out(void)
{
    struct gfx_list *L = &gfx_list[gfx_ready & 3u];
    unsigned b, i;
    printf("list n_v=%u n_b=%u quads=%u cover=%u\n", L->n_v, L->n_b, L->quads, L->cover);
    for (b = 0; b < L->n_b; b++) printf("batch %u pic=%u first=%u n=%u\n", b, L->b_pic[b], L->b_first[b], L->b_n[b]);
    for (i = 6; i < L->n_v; i++)
        printf("v %u %.3f %.3f %.4f %.4f %u %u %u %u\n", i, L->v[i].x, L->v[i].y, L->v[i].u, L->v[i].v, L->v[i].c[0],
               L->v[i].c[1], L->v[i].c[2], L->v[i].c[3]);
}

static const struct pm_mode mode = { .name = "T" };
int main(int argc, char **argv)
{
    int set, orb, sheet, font, k;
    struct pm_quad q = { 0 };
    gx.GetIntegerv = f_GetIntegerv; gx.IsEnabled = f_IsEnabled; gx.Enable = f_Enable; gx.Disable = f_Disable;
    gx.BlendFuncSeparate = f_BlendFuncSeparate; gx.BlendEquationSeparate = f_BlendEquationSeparate;
    gx.Viewport = f_Viewport; gx.UseProgram = f_UseProgram; gx.BindBuffer = f_BindBuffer; gx.GenBuffers = f_Gen;
    gx.BufferData = f_BufferData; gx.BindFramebuffer = f_BindFramebuffer; gx.VertexAttribPointer = f_VAP;
    gx.EnableVertexAttribArray = f_EVAA; gx.DrawArrays = f_DrawArrays; gx.CreateShader = f_CreateShader;
    gx.ShaderSource = f_ShaderSource; gx.CompileShader = f_CompileShader; gx.GetShaderiv = f_GetShaderiv;
    gx.CreateProgram = f_CreateProgram; gx.AttachShader = f_AttachShader; gx.BindAttribLocation = f_BindAttribLocation;
    gx.LinkProgram = f_LinkProgram; gx.GetProgramiv = f_GetProgramiv; gx.GetUniformLocation = f_GetUniformLocation;
    gx.Uniform4f = f_Uniform4f; gx.Uniform1i = f_Uniform1i; gx.Uniform1f = f_Uniform1f; gx.GenTextures = f_GenTextures;
    gx.DeleteTextures = f_DeleteTextures; gx.BindTexture = f_BindTexture; gx.ActiveTexture = f_ActiveTexture;
    gx.TexImage2D = f_TexImage2D; gx.TexParameteri = f_TexParameteri; gx.GenVertexArrays = f_Gen;
    gx.BindVertexArray = f_BindVertexArray; gx.GetBooleanv = f_GetBooleanv; gx.ColorMask = f_ColorMask;
    gfx_next = f_next;
    gfx_armed = 1;
    /* the game's state at its swap: none of it ours */
    S.prog = 7; S.abuf = 3; S.fb = 0; S.vp[2] = 1360; S.vp[3] = 768; S.vao = 5; S.unit = GX_TEXTURE0 + 2;
    S.tex[0] = 11; S.tex[2] = 12; S.bf[0] = 1; S.bf[1] = GX_ONE_MINUS_SRC_ALPHA; S.bf[2] = 1; S.bf[3] = GX_ONE_MINUS_SRC_ALPHA;
    S.eq[0] = S.eq[1] = GX_FUNC_ADD; S.caps[0] = S.caps[2] = S.caps[3] = 1; S.mask[0] = S.mask[1] = S.mask[2] = S.mask[3] = 1;
    current = &mode;
    printf("bad_load %d\n", pm_gfx_load(argv[2]));
    set = pm_gfx_load(argv[1]);
    orb = pm_gfx_picture(set, "orb"); sheet = pm_gfx_picture(set, "sheet"); font = pm_gfx_font(set, "");
    printf("set %d orb %d sheet %d font %d nope %d\n", set, orb, sheet, font, pm_gfx_picture(set, "nope"));
    swap("idle");                                     /* the set goes to GL */
    printf("ready %d mapped %d\n", pm_gfx_ready(set), gfx_set[set - 1].map != 0);
    pm_gfx_begin();
    q.pic = orb; q.x = 100; q.y = 200; q.ax = q.ay = 0.5f; q.scale_x = 2; q.scale_y = 0.5f; q.turn = 90; q.alpha = 0.5f;
    q.tint = PM_RGB(255, 0, 128); q.depth = 5;
    pm_gfx_quad(&q);
    memset(&q, 0, sizeof q);
    q.pic = sheet; q.sx = 64; q.sy = 64; q.sw = 64; q.sh = 64; q.x = 300; q.y = 300; q.alpha = 1; q.depth = 5;
    pm_gfx_quad(&q);
    q.blend = PM_GFX_ADD;                            /* the same picture added: a batch of its own */
    pm_gfx_quad(&q);
    q.blend = PM_GFX_NORMAL;
    pm_gfx_box(10, 20, 30, 40, PM_RGB(0, 0, 0), 1, 1);
    printf("width %.4f\n", pm_gfx_text(font, "AB A", 400, 50, 28, PM_ALIGN_LEFT, 0, 1, 3));
    q.alpha = 0;                                     /* nothing to draw: not even a batch */
    pm_gfx_quad(&q);
    pm_gfx_end();
    list_out();
    swap("draw");
    printf("xf %.6f %.6f %.6f %.6f\n", xf[0], xf[1], xf[2], xf[3]);
    pm_gfx_cover(1, PM_RGB(1, 2, 3));
    pm_gfx_begin(); pm_gfx_box(0, 0, 10, 10, PM_RGB(255, 255, 255), 1, 0); pm_gfx_end();
    swap("cover");
    printf("cover rgb %u %u %u %u\n", gfx_list[gfx_front].v[0].c[0], gfx_list[gfx_front].v[0].c[1],
           gfx_list[gfx_front].v[0].c[2], gfx_list[gfx_front].v[0].c[3]);
    for (k = 0; k < 2000; k++) { pm_gfx_begin(); pm_gfx_box(0, 0, 1, 1, 1, 1, 0); }   /* a list never ended stays off */
    for (k = 0; k < PM_GFX_MAX_QUADS + 5; k++) pm_gfx_box((float)k, 0, 1, 1, 1, 1, 0);
    pm_gfx_end();
    printf("full quads %u\n", gfx_list[gfx_ready & 3u].quads);
    fake_ms = 61000;
    running_ok = 0;                                   /* the mode ends */
    gfx_tick();
    printf("dropped %d\n", gfx_set[set - 1].state == GFX_DROP);
    swap("ended");
    printf("freed %d live %u\n", gfx_set[set - 1].state == GFX_FREE, live_tex);
    running_ok = 1;
    printf("again %d\n", pm_gfx_load(argv[1]));
    printf("bad %u swaps %u\n", bad, swaps_on);
    return 0;
}
"""


def _section():
    src = RUNTIME.read_text(encoding="utf-8")
    return src[src.index("/* ---- moving pictures on the glass (PAD-1655)"):]


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    from tests import test_spike2_mode_roster as R
    tmp = tmp_path_factory.mktemp("gfx")
    good = tmp / "t.padgfx"
    G.write(str(good), _pictures(), [_font()])
    (tmp / "bad.padgfx").write_bytes(b"PADGFX1\0" + struct.pack("<4I", 300, 0, 0, 0))
    out = R._host_run(tmp, HARNESS.replace("@SECTION@", _section()), flags=("-I" + str(SDK), "-no-pie"),
                      args=(str(good), str(tmp / "bad.padgfx")))
    return out.splitlines()


def _get(out, prefix):
    return [l for l in out if l.startswith(prefix)]


def test_a_set_loads_and_goes_to_gl_then_its_memory_goes(run):
    assert _get(run, "bad_load ") == ["bad_load 0"]                     # a table bigger than the file: refused
    assert any("not loaded" in l for l in _get(run, "log "))
    assert _get(run, "set ") == ["set 1 orb 1 sheet 5 font 1 nope 0"]
    ups = _get(run, "upload ")
    assert len(ups) == 1 + 6                                            # the white texel, then 5 pictures + the atlas
    assert ups[0].endswith("1x1 px0=255") and "256x128" in ups[5]
    assert _get(run, "ready ") == ["ready 1 mapped 0"]                  # GL holds them; our copy is unmapped


def test_every_piece_of_the_games_gl_state_is_put_back(run):
    swaps = _get(run, "swap ")
    assert swaps == ["swap idle restored=1", "swap draw restored=1", "swap cover restored=1", "swap ended restored=1"]
    assert _get(run, "bad ") == ["bad 0 swaps 4"]                       # every swap called on; no stray state touched
    assert not _get(run, "attrib on the game's VAO")


def test_quads_come_out_by_depth_turned_scaled_and_tinted(run):
    batches = [l.split()[2] for l in _get(run, "batch ")]
    # first list: the box (depth 1) on the white texel, the words (3) on the font's atlas, then the two depth-5 quads
    # in call order; the alpha 0 quad never makes a batch
    assert batches[:5] == ["pic=0", "pic=6", "pic=1", "pic=5", "pic=5"]
    v = {int(l.split()[1]): [float(x) for x in l.split()[2:]] for l in _get(run, "v ")}
    lst = _get(run, "list ")[0]
    assert lst.startswith("list n_v=48 n_b=5 quads=7")                  # box, 3 letters, orb, sheet frame twice
    first = {int(l.split()[3].split("=")[1]): l for l in _get(run, "batch ")[:5]}
    orb0 = [int(l.split()[3].split("=")[1]) for l in _get(run, "batch ")[:5] if "pic=1 " in l][0]
    # the orb: 64x64 scaled 2 x 0.5 = 128 x 32, turned 90 clockwise about (100, 200): corner (-64, -16) -> (116, 136)
    x, y, u, vv, r, g, b, a = v[orb0]
    assert (round(x, 2), round(y, 2)) == (116.0, 136.0) and (u, vv) == (0.0, 0.0)
    assert (r, g, b, a) == (128, 0, 64, 128)                            # premultiplied: tint x alpha, alpha
    # the sheet's frame (64, 64)-(128, 128) of 256x128: u 0.25..0.5, v 0.5..1
    sh0 = [int(l.split()[3].split("=")[1]) for l in _get(run, "batch ")[:5] if "pic=5 " in l][0]
    us = sorted(set(v[i][2] for i in range(sh0, sh0 + 6)))
    vs = sorted(set(v[i][3] for i in range(sh0, sh0 + 6)))
    assert us == [0.25, 0.5] and vs == [0.5, 1.0]
    assert first


def test_words_are_laid_out_by_the_fonts_metrics(run):
    v = {int(l.split()[1]): [float(x) for x in l.split()[2:]] for l in _get(run, "v ")}
    t0 = [int(l.split()[3].split("=")[1]) for l in _get(run, "batch ")[:5] if "pic=6 " in l][0]
    k = 28 / 14                                                          # size 28 of a font baked at 14
    # 'A' at the pen (400): left = 400 + 0.5 k, top = 50 + (ascent 10 - 9) k, 10x12 scaled by k
    xs = [v[i][0] for i in range(t0, t0 + 6)]
    ys = [v[i][1] for i in range(t0, t0 + 6)]
    assert (min(xs), max(xs)) == (400 + 0.5 * k, 400 + 0.5 * k + 10 * k)
    assert (min(ys), max(ys)) == (50 + 1 * k, 50 + 1 * k + 12 * k)
    # 'B' after A's advance 11.25 k
    xs = [v[i][0] for i in range(t0 + 6, t0 + 12)]
    assert min(xs) == pytest.approx(400 + 11.25 * k + 1.0 * k)
    # the second 'A' after B and the space: 11.25 + 9.5 + 4
    xs = [v[i][0] for i in range(t0 + 12, t0 + 18)]
    assert min(xs) == pytest.approx(400 + (11.25 + 9.5 + 4) * k + 0.5 * k)
    assert _get(run, "width ") == ["width %.4f" % ((11.25 + 9.5 + 4 + 11.25) * k)]


def test_the_stage_fills_the_surface_and_the_cover_goes_under_everything(run):
    xf = [float(x) for x in _get(run, "xf ")[0].split()[1:]]
    assert xf == pytest.approx([2 / 1360, -2 / 768, -1, 1], abs=1e-6)              # 1360x768 stage on a 1360x768 surface
    draws = _get(run, "draw ")
    assert all("ours=1" in d and "on=1" in d for d in draws)            # our program/VAO/buffer, blend on, tests off
    normal = [d for d in draws if "blend=1,771,0,1" in d]               # premultiplied over; the game's alpha kept
    added = [d for d in draws if "blend=1,1,0,1" in d]                  # the PM_GFX_ADD batch: light added
    assert len(normal) + len(added) == len(draws) and len(added) == 1
    pics = [d for d in draws if " pm=0 " in d]                          # straight pictures: the shader multiplies
    assert len(pics) >= 4 and all(" pm=1 " in d for d in draws if d not in pics)   # the white texel: as it is
    cover = [d for d in draws if "first=0 n=6" in d]
    white = _get(run, "upload ")[0].split()[1]
    assert len(cover) == 1 and cover[0].startswith("draw %s " % white)  # the white texel, the first draw of its frame
    assert _get(run, "cover rgb") == ["cover rgb 1 2 3 255"]


def test_a_full_list_keeps_its_limit_and_an_ended_mode_lets_everything_go(run):
    cap = int(re.search(r"#define PM_GFX_MAX_QUADS (\d+)", (SDK / "pad_mode.h").read_text()).group(1))
    assert cap == 2048 and _get(run, "full quads ") == ["full quads %d" % cap]
    assert sum("left out" in l for l in _get(run, "log ")) == 1         # said once
    assert _get(run, "dropped ") == ["dropped 1"]
    after = run[run.index("dropped 1"):]
    assert not [l for l in after if l.startswith("draw ")]              # the ended mode's list is off the glass
    assert len([l for l in after if l.startswith("deltex ")]) == 6      # every picture of the set deleted
    assert _get(run, "freed ") == ["freed 1 live 1"]                    # only the white texel stays
    assert _get(run, "again ") == ["again 1"]                           # and the slot loads again
    assert any("ended - its pictures are off the glass" in l for l in _get(run, "say "))
    budget = [l for l in _get(run, "say ") if "in the last 61 s" in l]
    assert budget and "3 frame(s) went to the glass" in budget[0]


def test_the_turn_series_is_accurate():
    """gfx_sincos's series, as written, against math: within 2e-6 over a few turns either way."""
    def sincos(deg):
        r = deg / 90.0
        q = int(r - 0.5) if r < 0 else int(r + 0.5)
        x = (r - q) * 1.5707963268
        x2 = x * x
        sn = x * (1 - x2 / 6 * (1 - x2 / 20 * (1 - x2 / 42 * (1 - x2 / 72))))
        cs = 1 - x2 / 2 * (1 - x2 / 12 * (1 - x2 / 30 * (1 - x2 / 56)))
        return [(sn, cs), (cs, -sn), (-sn, -cs), (-cs, sn)][q & 3]
    src = RUNTIME.read_text(encoding="utf-8")
    assert "sn = x * (1 - x2 / 6 * (1 - x2 / 20 * (1 - x2 / 42 * (1 - x2 / 72))));" in src
    for deg in range(-1080, 1081, 7):
        s, c = sincos(deg)
        assert abs(s - math.sin(math.radians(deg))) < 2e-6 and abs(c - math.cos(math.radians(deg))) < 2e-6
