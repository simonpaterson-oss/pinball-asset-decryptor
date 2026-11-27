"""CO-OP PLAY back in the service menu, as ALTERNATIVE MODES 0 Off / 1 On / 2 Enhanced.

Simon (2026-11-27, agreed with daveyvandy): "PAD - Item for coop play in service menu OFF/ON. SERVICE MENU - if set to
have the item on will be able to turn coop off/on.. thats it." PAD-1443 had taken the row away (co-op games always on
the start menu). The row comes back unticked on the Service menu tab, so a project that does not tick it is exactly
PAD-1443's card; ticked, the operator gets CO-OP PLAY Off / On, On being the card with no row.

Simon (2026-11-27, with Nathan Hestley, who made the styles): "So the COOP menu in service should be called ALT MODES or
ALTERNATIVE MODES. Then: OFF, ON, ENHANCED" - On the co-op and team games regular only (no version step, no
characters; TEAMS keeps its team step), Enhanced everything (the card with no row). Only checks in front of the chooser:
"As long as the code doesn't change anything - just basically "IF service menu item = this then.."".
"""
import json
import os

from pinball_decryptor.plugins.stern import coop_play as CP
from pinball_decryptor.plugins.stern import engine as E

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME = os.path.join(REPO, "tools", "spike2_emu", "modes", "sdk", "pad_mode_runtime.c")


def _src():
    with open(RUNTIME, encoding="utf-8") as f:
        return f.read()


def _project(tmp_path, data):
    p = str(tmp_path / "proj")
    os.makedirs(p, exist_ok=True)
    with open(os.path.join(p, ".staged_changes.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)
    return p


def test_the_row_is_off_on_enhanced_and_enhanced_to_start_with():
    from pinball_decryptor.plugins.stern import menu_settings as MS
    key, values, names, opts = E._CoopMenu(lambda *a: None).wanted()
    assert key == "coop_play" and values == 3 and names == ()
    assert opts == {"default": CP.MENU_DEFAULT, "help_text": CP.MENU_HELP, "from_zero": True}
    assert CP.MENU_DEFAULT == 3                                     # counted from 1: 3 is 2, Enhanced
    assert CP.MENU_HELP == "0 Off. 1 On: co-op and teams, regular. 2 Enhanced: all"
    assert len(CP.MENU_HELP) <= 63                                  # the spare help lines' room
    assert MS.SETTINGS["coop_play"][1:3] == ("ALTERNATIVE MODES", "Alternative Modes")


def test_the_card_says_switch_only_with_a_spike2_row():
    """coop.cfg's `switch` tells the runtime the row is Off / On (coop_row_styles); no row, no line."""
    import inspect
    body = inspect.getsource(CP.cfg_text)
    assert '("switch\\n" if setting and not wide else "")' in body
    assert body.index('"switch') < body.index('"only')


def test_the_runtime_reads_an_off_on_row_as_the_card_with_no_row():
    from tests import test_spike2_mode_roster as R
    src = _src()
    assert "return coop.setting && !coop.onoff;" in R._lift(src, "static int coop_row_styles(void)\n{")
    assert 'if (str_starts(s, "switch")) coop.onoff = 1;' in src
    # On: the start menu's own style step and default style, CO-OP PLAY with no pick, no ENHANCED STANDARD entry
    assert "!coop_row_styles()" in R._lift(src, "static int sty_wanted(void)\n{")
    assert "if (!coop_row_styles()) return coop.style == 2u;" in R._lift(src, "static int coop_classic(void)\n{")
    assert "if (!coop.style_default || coop_row_styles()) return;" in R._lift(src, "static void coop_style_held(void)\n{")
    assert "coop.plain = kind == 1u && !coop_row_styles();" in src
    assert "if (coop_row_styles() && !coop_classic()) kinds[n++] = 2u;" in src
    # Off: the row's value still switches co-op off as it always did (no start menu games, Start a competing player)
    assert "coop_row_mode(*(volatile const unsigned *)(unsigned long)coop.setting) != 0u" in R._lift(
        src, "static int coop_switched_on(void)\n{")
    # Insider Connected: an Off / On card keeps PAD-1443's per-game gate (Off: no game is one of ours, all report)
    wanted = R._lift(src, "static pm_addr coop_setting_wanted(void)\n{")
    assert "return only && v && !sw ? setting_addr(v) : 0;" in wanted


def test_an_older_cards_three_value_row_keeps_its_meaning():
    """A card written before PAD-1443 (no `switch` line) still reads 0 Off, 1 Classic, 2 Enhanced."""
    from tests import test_spike2_mode_roster as R
    src = _src()
    assert "return v <= 2u ? v : v == 3u ? 2u : v <= 6u ? 1u : 0u;" in R._lift(
        src, "static unsigned coop_row_mode(unsigned v)\n{")
    assert "return coop_row_mode(*(volatile const unsigned *)(unsigned long)coop.setting) == 1u;" in R._lift(
        src, "static int coop_classic(void)\n{")


def test_the_prebuilt_runtimes_are_built_from_these_sources():
    import hashlib
    sdk = os.path.dirname(RUNTIME)
    for pin in ("SOURCES.sha256", "SOURCES64.sha256"):
        with open(os.path.join(sdk, "prebuilt", pin), encoding="utf-8") as f:
            lines = [l.split() for l in f if l.strip() and not l.startswith(("#", "compiler"))]
        got = dict((name, digest) for digest, name in lines)
        with open(RUNTIME, "rb") as f:
            assert got["pad_mode_runtime.c"] == hashlib.sha256(f.read().replace(b"\r", b"")).hexdigest()


def test_the_write_asks_for_the_row_only_when_ticked(tmp_path):
    from pinball_decryptor.plugins.stern import service_menu as SM
    p = _project(tmp_path, {"coop_play": {"on": True}})
    assert "coop_play" not in [r[0] for r in SM.wanted(p)]           # unticked: PAD-1443's card, no row
    CP.save(p, True, menu=True)
    assert "coop_play" in [r[0] for r in SM.wanted(p)]
    CP.save(p, True, menu=False)
    assert "coop_play" not in [r[0] for r in SM.wanted(p)]


def test_the_tab_ticks_co_op_on_and_off_again(tmp_path, monkeypatch):
    """Ticked on a project with no co-op play, the row switches co-op play on too, and unticking it switches it off
    again; co-op play switched on at the Modes tab stays on when the row is unticked."""
    import pytest
    from tests.webui_harness import web_app
    from pinball_decryptor.webui.tabs import svcmenu
    monkeypatch.setattr(svcmenu, "_coop_refusal", lambda _cp, _p: "")    # a blank project names no game
    p = _project(tmp_path, {})
    with web_app(tmp_path / "app") as w:
        modes = w.window.service("modes")
        var = modes._project_var() if modes is not None else None
        if var is None:
            pytest.skip("no project folder variable in this window")
        w.run(lambda: var.set(p))
        w.drain()
        w.call("ui.select_tab", "svcmenu")
        w.drain()
        row = next(r for r in w.state("svcmenu")["settings"] if r["key"] == "coop_play")
        assert row["can"] and not row["on"] and row["note"] == "Not on the card: tick to add its row (and co-op play)."
        modes.set_coop = lambda on: CP.save(p, bool(on)) is not None    # the title check needs a real card
        w.call("svcmenu.set_row", "coop_play", True)
        w.drain()
        assert CP.load(p) and CP.menu_asked(p)
        w.call("svcmenu.set_row", "coop_play", False)
        w.drain()
        assert not CP.load(p) and not CP.menu_asked(p)


SWITCH_MAIN = r"""
@FNS@
static void kinds(const char *tag)
{
    unsigned k[6], n = team_menu_kinds(k), i;
    printf(" %s:", tag);
    for (i = 0; i < n; i++) printf("%u", k[i]);
}
int main(void)
{
    coop.setting = 0;                                   /* no row: PAD-1443's start menu */
    kinds("none");
    printf(",%d", coop_classic());
    coop.setting = (unsigned)(unsigned long)&row;       /* an Off / On row (coop.cfg `switch`) */
    coop.onoff = 1;
    row = 0;
    kinds("off");
    printf(",%d", coop_switched_on());
    row = 1;
    kinds("on");
    printf(",%d%d", coop_switched_on(), coop_classic());
    coop.style = 2u;                                    /* the start menu's CHARACTERS pick, as with no row */
    printf(",%d", coop_classic());
    row = 2;                                            /* Enhanced: the card with no row */
    kinds("enh");
    printf(",%d%d", coop_regular_only(), coop_alt_off());
    row = 1;
    printf(",%d%d", coop_regular_only(), coop_alt_off());
    coop.teams_always = 3;                              /* a card of coop.cfg `teams 2v1` */
    kinds("t1");
    row = 0;                                            /* Off: no team game either */
    kinds("t0");
    printf("\n");
    return 0;
}
"""


def test_an_off_on_row_gives_the_start_menu_of_a_card_with_no_row(tmp_path):
    """Compiled from the runtime itself: On offers exactly what a card with no row offers (no ENHANCED STANDARD
    entry, the style the start menu's own pick), Off offers nothing."""
    from tests import test_pad1073_coop_row_three as T
    from tests import test_spike2_mode_roster as R
    R._cc()                                             # skips with no ELF toolchain (Windows, macOS)
    main = T.PRELUDE + SWITCH_MAIN.replace("@FNS@", T._fns(_src(), *T.ROW_FNS))
    out = R._host_run(tmp_path, main, flags=("-no-pie",)).strip()
    # Simon: 1 On and 2 Enhanced offer the same games (On plays them regular); 0 Off nothing - a `teams` card too
    assert out == "none:1435,0 off:,0 on:1435,10,1 enh:1435,00,10 t1:3 t0:"


def test_on_adds_only_checks_in_front_of_the_chooser():
    """Simon, with Nathan: "IF service menu item = this then.." - each gate is a line before the chooser's own code."""
    from tests import test_spike2_mode_roster as R
    src = _src()
    kind = R._lift(src, "static unsigned sty_menu_kind(void)\n{")
    assert kind.index("if (!sty_wanted()) return 0u;") < kind.index("coop_regular_only()") < kind.index("if (tm.pending)")
    frame = R._lift(src, "static void sty_menu_frame(unsigned c, int teams, int ours, unsigned std_msg, unsigned index)\n{")
    assert frame.index("if (act && coop_regular_only() && smn.open && smn.shaping)") < frame.index("if (act) switch")
    assert "if (coop_regular_only()) smn.go_style = 1;" in R._lift(src, "static void sty_menu_go(void)\n{")
    begin = R._lift(src, "static void sty_begin(unsigned kind)\n{")
    assert begin.index("if (coop_regular_only()) sty.preset = 1;") < begin.index("if (sty_default_normal(")
    held = R._lift(src, "static void coop_style_held(void)\n{")
    assert held.index("if (coop_regular_only())") < held.index("if (!coop.style_default || coop_row_styles()) return;")


def test_the_online_coop_row(tmp_path):
    """Simon: "Can we have online coop OFF as a seperate service menu item?" - ONLINE CO-OP Off / On, its word in
    scorefeed.cfg; Off, a report carries no online fields."""
    import inspect
    from tests import test_spike2_mode_roster as R
    from pinball_decryptor.plugins.stern import menu_settings as MS, mode_write as MW, online_coop as OC
    from pinball_decryptor.plugins.stern import service_menu as SM
    key, values, names, opts = E._OnlineCoopMenu(lambda *a: None).wanted()
    assert (key, values, names) == ("online_coop", 2, ())
    assert opts == {"default": 2, "help_text": OC.MENU_HELP, "onoff": True} and len(OC.MENU_HELP) <= 63
    assert MS.SETTINGS["online_coop"][1:3] == ("ONLINE CO-OP", "Online Co-op")
    assert "online_coop" in SM.TICK_KEYS
    p = _project(tmp_path, {})
    SM.save(p, {"on": ["online_coop"]})
    assert "online_coop" not in [r[0] for r in SM.wanted(p)]        # ticked, but online co-op is not set up
    src = _src()
    assert 'str_starts(raw + i, "online_row ")' in src
    into = R._lift(src, "static void feed_online_into(struct feed_report *r)\n{")
    assert into.index("feed.online_row") < into.index("for (k = 0; k < sizeof r->campaign; k++)")
    assert 'text += "online_row 0x%08x\\n" % online_setting' in inspect.getsource(MW.feed_into)
