"""Simon (2026-11-27): "Whenever PAD writes an image - unless the PAD user decides NOT to have network access, whatever
they write it must be possible to change it to anything else" - and "don't do anything that assumes they will have a
big card": most cards are 32-64 GB.

core/card_relayout.py lays the machine's card out for a multi-boot image (adds partition 7, p3 made smaller or bigger,
/data and /dump at the end) through a start-up script, then the Send fills it.  remote_send asks before a Send that
changes what kind of card the machine runs, and leaves a multi-boot card's partition 7 unused when one game or a test
card replaces it ("leave partition 7 unused")."""

import io
import types

import pytest

from pinball_decryptor.core import card_relayout as cr
from pinball_decryptor.core import remote_send as rs
from pinball_decryptor.core import testcard_grow as tg
from pinball_decryptor.plugins.stern import spike3

GB = 1 << 30
S = 512
# the network test card built from the stock Godzilla 1.16 card (tests/test_testcard_grow.py)
TESTCARD = {1: (8192, 16384), 2: (24576, 688128), 3: (712704, 4194304), 4: (4907008, 2), 5: (4909056, 262144),
            6: (5173248, 262144)}
# a multi-boot image of Heisei (p3) and the stock 1.16 (p7): what it needs on the machine
NEED3, NEED7 = 13 * GB // S, 6 * GB // S


def _mbr(layout):
    m = bytearray(512)
    m[:4] = b"BOOT"
    p1, p2, p3, p5, p6 = (layout[n] for n in (1, 2, 3, 5, 6))
    ext = p3[0] + p3[1]
    m[0x1BE:0x1FE] = (tg._entry(0x0C, *p1[:2]) + tg._entry(0x83, *p2[:2]) + tg._entry(0x83, *p3[:2])
                      + tg._entry(0x0F, ext, p6[0] + p6[1] - ext))
    m[510:512] = b"\x55\xaa"
    return bytes(m)


def _grown(card):
    """A test card grown to fill an SD card of *card* sectors (as Simon's machine runs one)."""
    g = tg.plan(TESTCARD, card, _mbr(TESTCARD))
    return {**TESTCARD, **g.expect}


class _Disk(io.RawIOBase):
    """A card as a file, only the written sectors held (no 32 GB file on the test machine)."""

    def __init__(self, sectors):
        self.data, self.pos = dict(sectors), 0

    def seek(self, pos, whence=0):
        self.pos = pos if whence == 0 else self.pos + pos
        return self.pos

    def read(self, n=-1):
        out = bytearray()
        while len(out) < n:
            lba, off = divmod(self.pos, S)
            chunk = self.data.get(lba, bytes(S))[off:off + n - len(out)]
            out += chunk
            self.pos += len(chunk)
        return bytes(out)


def _read_back(p):
    parts = spike3.parse_partitions(_Disk(p.sectors))
    return {r["index"]: (r["start_lba"], r["sectors"]) for r in parts}


@pytest.mark.parametrize("card_gb", [32, 64, 256])
def test_a_grown_test_card_gets_partition_7(card_gb):
    card = card_gb * 10 ** 9 // S                       # an SD card's size is in decimal gigabytes
    old = _grown(card)
    p = cr.plan(old, card, _mbr(old), NEED3, NEED7, used3=200 << 20)
    assert not p.move, "/data and /dump are at the end already (the grow put them there): left where they are"
    e = p.expect
    assert e[5] == old[5][:2] and e[6] == old[6][:2]
    assert e[3][0] == old[3][0], "p3 starts where it did"
    assert e[3][1] >= NEED3 and e[7][1] >= NEED7
    assert e[3][1] < old[3][1] and p.shrink_kb == e[3][1] * S // 1024
    assert e[3][0] + e[3][1] <= e[7][0] and e[7][0] + e[7][1] <= e[5][0], "p3, then p7, then /data and /dump"
    # the room left over is split between p3 and p7, so later builds can grow
    spare3, spare7 = e[3][1] - NEED3, e[7][1] - NEED7
    assert abs(spare3 - spare7) < 4 * tg.ALIGN
    # the kernel reads the new table as planned: p7 is the chain's third logical partition
    got = _read_back(p)
    assert {n: got[n] for n in (1, 2, 3, 5, 6, 7)} == {1: old[1][:2], 2: old[2][:2], **e}
    assert all(s % tg.ALIGN == 0 for s, _c in got.values() if _c > 2)
    assert [lba for lba, _d in p.sectors][-1] == 0, "the MBR - the switch - last"


def test_a_card_too_small_for_the_image_is_refused_with_the_sizes():
    card = 16 * 10 ** 9 // S
    old = _grown(card)
    with pytest.raises(cr.LayoutError, match=r"too small .* 13.0 GB on partition 3 and 6.0 GB on partition 7"):
        cr.plan(old, card, _mbr(old), NEED3, NEED7)


def test_p3_keeps_room_for_the_files_it_has():
    card = 32 * 10 ** 9 // S
    old = _grown(card)
    p = cr.plan(old, card, _mbr(old), 1 * GB // S, NEED7, used3=20 * GB)
    assert p.expect[3][1] * S >= 20 * GB + cr.P3_MARGIN


def test_a_stock_one_game_card_on_a_32_gb_card_moves_data_and_dump():
    # Stern's 8 GB layout written to a 32 GB card: /data and /dump sit at 8 GB, the rest of the card unused
    stock = {1: (8192, 16384), 2: (24576, 2097152), 3: (2121728, 11534336), 4: (13656064, 2),
             5: (13658112, 1048576), 6: (14708736, 524288)}
    card = 32 * 10 ** 9 // S
    p = cr.plan(stock, card, _mbr(stock), NEED3, NEED7)
    assert p.move, "/data and /dump go to the end of the card"
    assert p.expect[6][0] + p.expect[6][1] <= card and card - (p.expect[6][0] + p.expect[6][1]) < tg.ALIGN
    assert p.expect[3][1] > stock[3][1] and p.shrink_kb == 0, "p3 grows: nothing to shrink first"
    assert _read_back(p)[7] == p.expect[7]
    assert "MOVE=1" in p.conf()


def test_only_a_card_of_six_partitions_is_laid_out():
    card = 32 * 10 ** 9 // S
    old = _grown(card)
    with pytest.raises(cr.LayoutError, match="partitions 1, 2, 3, 4, 5, 6, 7"):
        cr.plan({**old, 7: (1, 2)}, card, _mbr(old), NEED3, NEED7)
    with pytest.raises(cr.LayoutError, match="no partition table"):
        cr.plan(old, card, bytes(512), NEED3, NEED7)


def test_the_startup_script_changes_only_the_table_it_expects():
    s = cr.startup_script()
    assert s.startswith("#!/bin/sh") and cr.LAYOUT_DIR in s and cr.LOG_ON_DATA in s
    i_old, i_new = s.index("if is_old; then"), s.index("if ! is_new; then")
    assert i_old < i_new
    step1 = s[i_old:i_new]
    # step 1, under the old table: p3 checked and shrunk BEFORE the table is written, then a restart
    assert step1.index("e2fsck -fy") < step1.index("resize2fs /dev/mmcblk0p3 ${SHRINK_KB}K") < step1.index("dd if=")
    assert step1.rstrip().endswith("reboot -f\n    exit 0\nfi") or "reboot -f" in step1
    # a failure in step 1 changes nothing and lets PAD try again
    assert step1.count("mv $D/layout.conf $D/layout.failed") == 2
    step2 = s[i_new:]
    assert "mke2fs -q -F -t ext4 -L $LABEL /dev/mmcblk0p7" in step2
    assert 'if [ "$MOVE" = 1 ]; then' in step2
    assert cr.BOOT_SCRIPT_PATH.startswith("/etc/rcS.d/S02zz_") and not cr.BOOT_SCRIPT_PATH.endswith(".sh")


def test_the_conf_names_both_tables():
    card = 32 * 10 ** 9 // S
    old = _grown(card)
    p = cr.plan(old, card, _mbr(old), NEED3, NEED7, label="padwork")
    c = p.conf()
    assert "OLD_P3_START=%d\nOLD_P3_SIZE=%d\n" % old[3][:2] in c
    assert "P7_START=%d\nP7_SIZE=%d\n" % p.expect[7] in c and "LABEL=padwork" in c
    assert "LBAS='%s'" % " ".join(str(lba) for lba, _d in p.sectors) in c
    assert len(p.table()) == S * len(p.sectors)
    assert cr.plan(old, card, _mbr(old), NEED3, NEED7, label="bad label;rm").label == "multi"


# ---- the Send --------------------------------------------------------------------------------------------------
def _target(layout, menu=False, testcard=False):
    t = types.SimpleNamespace(platform="stern-spike2", layout=layout, parts={3: "/games", 2: "/"}, raw={1: 1})
    return t, menu, testcard


def _check(monkeypatch, layout, machine, menu=False, testcard=False, replace_ok=False):
    t = types.SimpleNamespace(platform="stern-spike2", layout=layout, parts={"/": 2, "/games": 3}, raw={1})
    monkeypatch.setattr(rs, "_has_boot_menu", lambda target: menu)
    monkeypatch.setattr(rs, "is_test_card", lambda target: testcard)
    rs.check_layout(t, machine, replace_ok)


MENU_CARD = {1: (8192, 16384, 0x0C), 2: (24576, 688128, 0x83), 3: (712704, 4194304, 0x83), 4: (4907008, 2, 0x0F),
             5: (4909056, 262144, 0x83), 6: (5173248, 262144, 0x83), 7: (5437440, 8388608, 0x83)}


def test_one_game_replacing_a_multi_boot_card_leaves_partition_7_unused(monkeypatch):
    image = {n: v for n, v in MENU_CARD.items() if n != 7}
    machine = {n: v[:2] for n, v in MENU_CARD.items()}
    with pytest.raises(rs.SendError, match="can't replace one of its games"):
        _check(monkeypatch, image, machine)
    _check(monkeypatch, image, machine, replace_ok=True)                          # asked: p7 left alone
    _check(monkeypatch, image, machine, testcard=True, replace_ok=True)


def test_a_multi_boot_image_still_needs_partition_7_without_the_layout_change(monkeypatch):
    machine = {n: v[:2] for n, v in MENU_CARD.items() if n != 7}
    with pytest.raises(rs.SendError, match="partition 7 is missing"):
        _check(monkeypatch, MENU_CARD, machine, menu=True, replace_ok=True)


def test_a_test_card_may_replace_a_one_game_card_once_asked(monkeypatch):
    m = types.SimpleNamespace(sh=lambda *a, **k: (0, ""))                        # a one-game card
    monkeypatch.setattr(rs, "is_test_card", lambda target: True)
    with pytest.raises(rs.SendError, match="isn't running one"):
        rs.check_test_card_target(object(), m)
    rs.check_test_card_target(object(), m, replace_menu_card=True)


def test_the_send_lays_the_card_out_first_when_asked():
    src = open(rs.__file__, encoding="utf-8").read()
    run = src[src.index("class SendPipeline"):]
    i = run.index("card_relayout.has_p7(self.image) and 7 not in machine.layout()")
    assert run.index("if self.replace_menu_card and not") < i < run.index('machine.widen(self._log)')
    assert "check_layout(target, machine.layout(), replace_menu_card)" in src


def test_the_tabs_ask_before_a_send_that_changes_the_card():
    import pinball_decryptor.webui.tabs.network as net
    import pinball_decryptor.webui.tabs.testcard as tct
    n = open(net.__file__, encoding="utf-8").read()
    assert "remote_send.replace_question(path, machine)" in n
    assert "fn(path, address, replace_menu_card=True)" in n
    t = open(tct.__file__, encoding="utf-8").read()
    assert "raise RpcError(rs.TESTCARD_ONLY)" not in t, "a one-game card is asked about now, not refused"
    assert 'self._replace_menu_card = kind in ("menu", "game")' in t
