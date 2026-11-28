"""ALTERNATIVE MODES and ONLINE CO-OP in the service menu.

Simon (2026-11-27, with Nathan Hestley, who made the co-op styles): "So the COOP menu in service should be called ALT
MODES or ALTERNATIVE MODES. Then: OFF, ON, ENHANCED" - On the co-op and team games regular only (no version step, no
characters; TEAMS keeps its team step), Enhanced everything (the card with no row). Only checks in front of the chooser:
"As long as the code doesn't change anything - just basically "IF service menu item = this then.."".
David (2026-11-28): give users the most options we can - so it is a fourth place for the co-op style on the Modes tab
("Alternative Modes"), beside v1.635.0's start menu / service menu / both, which are unchanged.
Simon (2026-11-27): "Can we have online coop "OFF" as a seperate service menu item?" - ONLINE CO-OP Off / On.
"""
import inspect
import json
import os

from pinball_decryptor.plugins.stern import coop_play as CP
from pinball_decryptor.plugins.stern import engine as E
from pinball_decryptor.plugins.stern import menu_settings as MS

_GZ_HEAD = b"\x7fELF\x01\x01" + bytes(58)
_SRC = os.path.join(os.path.dirname(__file__), "..", "tools", "spike2_emu", "modes", "sdk", "pad_mode_runtime.c")


def _src():
    return open(_SRC, encoding="utf-8").read()


def _project(tmp_path, data):
    p = str(tmp_path)
    os.makedirs(p, exist_ok=True)
    with open(os.path.join(p, ".staged_changes.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)
    return p


def test_alternative_modes_is_a_fourth_place(tmp_path):
    from pinball_decryptor.plugins.stern import service_menu as SM
    assert CP.PLACES == ("start", "service", "both", "alt")                       # v1.635.0's three kept, in order
    assert CP.PLACE_LABELS["alt"] == "Alternative Modes in the service menu"
    p = _project(tmp_path, {"coop_play": {"on": True}})
    CP.save_place(p, "alt")
    assert CP.load_place(p) == "alt" and CP.menu_asked(p)
    assert CP.menu_row(p) == (3, (), 3, "0 Off. 1 On: co-op and teams, regular. 2 Enhanced: all")
    assert (CP.ALT_OFF, CP.ALT_ON, CP.ALT_ENHANCED, CP.ALT_DEFAULT) == (0, 1, 2, 3)   # counted from 1: 3 is 2
    assert len(CP.ALT_HELP) <= 63
    assert CP.place_line(p, _GZ_HEAD) == "styles alt\n"
    assert CP.place_line(p, b"\x7fELF\x02\x01" + bytes(58)) == ""                 # Spike 3 keeps its own row
    key, values, names, opts = E._CoopMenu(lambda *a, **k: None, p).wanted()
    assert (key, values, names) == ("alt_modes", 3, ())
    assert opts == {"default": 3, "help_text": CP.ALT_HELP, "from_zero": True}    # shown as 0 / 1 / 2
    assert MS.SETTINGS["alt_modes"][1:3] == ("ALTERNATIVE MODES", "Alternative Modes")
    assert MS.SETTINGS["coop_play"][1:3] == ("CO-OP PLAY", "Co-op Play")          # the other places' row as it was
    assert "alt_modes" in [r[0] for r in SM.wanted(p)]
    for place in ("start", "service", "both"):                                    # the others unchanged
        CP.save_place(p, place)
        assert E._CoopMenu(lambda *a, **k: None, p).wanted()[0] == "coop_play"
        assert CP.place_line(p, _GZ_HEAD) == ("" if place == "start" else "styles %s\n" % place)


def test_the_card_says_switch_and_styles_alt(tmp_path):
    """The Write's coop.cfg: ``switch`` (cfg_text, as an Off / On row) and ``styles alt`` (place_line)."""
    from pinball_decryptor.plugins.stern import mode_write as MW
    src = inspect.getsource(MW.coop_into)
    assert "text += CP.place_line(project, game_elf)" in src
    assert 'if place == "alt":' in src and "ALTERNATIVE MODES: 0 Off, 1 On" in src
    assert '+ ("switch\\n" if setting and not wide else "")' in inspect.getsource(CP.cfg_text)


def test_the_runtime_reads_styles_alt_only():
    src = _src()
    assert 'if (str_starts(s, "styles alt")) coop.alt = 1;' in src
    from tests import test_spike2_mode_roster as R
    value = R._lift(src, "static int coop_alt_value(void)\n{")
    assert "if (!coop.setting || !coop.onoff || !coop.alt) return -1;" in value   # another place's row: nothing


def test_only_checks_in_front_of_the_chooser():
    """Simon, with Nathan: "IF service menu item = this then.." - each gate is a line before the chooser's own code."""
    from tests import test_spike2_mode_roster as R
    src = _src()
    kind = R._lift(src, "static unsigned sty_menu_kind(void)\n{")
    assert kind.index("if (!sty_wanted()) return 0u;") < kind.index("coop_alt_off()") < kind.index("if (tm.pending)")
    assert kind.index("coop_regular_only()") < kind.index("if (tm.pending)")
    frame = R._lift(src, "static void sty_menu_frame(unsigned c, int teams, int ours, unsigned std_msg, unsigned index)\n{")
    assert frame.index("if (act && coop_regular_only() && smn.open && smn.shaping)") < frame.index("if (act) switch")
    assert "if (coop_regular_only()) smn.go_style = 1;" in R._lift(src, "static void sty_menu_go(void)\n{")
    begin = R._lift(src, "static void sty_begin(unsigned kind)\n{")
    assert begin.index("if (coop_regular_only()) sty.preset = 1;") < begin.index("if (sty_default_normal(")
    held = R._lift(src, "static void coop_style_held(void)\n{")
    assert held.index("if (coop_regular_only())") < held.index("if (!d || coop_row_styles()) return;")
    team = R._lift(src, "static void team_menu_frame(pm_reg *r)\n{")
    assert team.index("if (!nk && coop_alt_off()) sty_alt_off_tidy();") < team.index("if (creg > 12 || breg > 12")
    kinds = R._lift(src, "static unsigned team_menu_kinds(unsigned *kinds)\n{")
    assert kinds.index("if (coop.teams_always && coop_alt_off()) return 0;") < kinds.index("if (coop.teams_always) {")


ALT_MAIN = r"""
@FNS@
static void kinds(const char *tag)
{
    unsigned k[6], n = team_menu_kinds(k), i;
    printf(" %s:", tag);
    for (i = 0; i < n; i++) printf("%u", k[i]);
}
int main(void)
{
    coop.setting = (unsigned)(unsigned long)&row;       /* the row, coop.cfg `switch` */
    coop.onoff = 1;
    row = 0;                                            /* another place's Off / On row at Off: no gate of ours */
    printf("other:%d%d", coop_regular_only(), coop_alt_off());
    coop.alt = 1;                                       /* `styles alt` */
    kinds("off");
    printf(",%d%d%d", coop_switched_on(), coop_regular_only(), coop_alt_off());
    row = 1;
    kinds("on");
    printf(",%d%d%d", coop_switched_on(), coop_regular_only(), coop_alt_off());
    row = 2;                                            /* Enhanced: the card with no row */
    kinds("enh");
    printf(",%d%d%d", coop_switched_on(), coop_regular_only(), coop_alt_off());
    coop.teams_always = 3;                              /* a card of coop.cfg `teams 2v1` */
    kinds("t2");
    row = 0;                                            /* Off: no team game either */
    kinds("t0");
    printf("\n");
    return 0;
}
"""


def test_the_three_values_compiled(tmp_path):
    """Compiled from the runtime itself: 1 On and 2 Enhanced offer the same games (On plays them regular); 0 Off
    nothing, a `teams` card too; another place's row never meets a gate of ours."""
    from tests import test_pad1073_coop_row_three as T
    from tests import test_spike2_mode_roster as R
    R._cc()                                             # skips with no ELF toolchain (Windows, macOS)
    main = T.PRELUDE + ALT_MAIN.replace("@FNS@", T._fns(_src(), *T.ROW_FNS))
    out = R._host_run(tmp_path, main, flags=("-no-pie",)).strip()
    assert out == "other:00 off:,001 on:1435,110 enh:1435,100 t2:3 t0:"


def test_the_online_coop_row(tmp_path):
    """ONLINE CO-OP Off / On, its word in scorefeed.cfg; Off, a report carries no online fields."""
    from tests import test_spike2_mode_roster as R
    from pinball_decryptor.plugins.stern import mode_write as MW, online_coop as OC
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
    assert "if (feed.online_row && !*(volatile const unsigned *)(unsigned long)feed.online_row) return 0;" in \
        R._lift(src, "int pm_online(void)\n{")
    assert 'text += "online_row 0x%08x\\n" % online_setting' in inspect.getsource(MW.feed_into)
    eng = inspect.getsource(E)
    assert "show_menu, timer_menu, online_menu], log)" in eng
    assert "online_setting=online_setting," in eng
