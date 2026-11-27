"""Lay the machine's card out for a multi-boot image over the network, so a Send can then fill it.

Simon (2026-11-27): "Whenever PAD writes an image - unless the PAD user decides NOT to have network access, whatever
they write it must be possible to change it to anything else" - and "don't do anything that assumes they will have a
big card": most cards are 32-64 GB.

A multi-boot image keeps its other games on partition 7 (mkmulticard's multi and store layouts); a one-game card or a
test card has none, and a Send changes files, never partitions.  So when the user agrees, before the Send:

1. Over the network (this module, on the running machine): a start-up script, its tools (PAD's own e2fsck and
   resize2fs, as the grow's) and the new partition table go onto the system partition, and the machine restarts.
   /data and /dump are saved there too when they have to move.
2. At the first start-up, before the card's partitions are checked or mounted (``S02zz_padlayout``), only while the
   kernel still shows the OLD table: p3's file system is checked and, when p3 is to be smaller, shrunk to its new
   size (its files stay); then the new table is written and the machine restarts at once.
3. At the next start-up, only when the kernel shows exactly the NEW table: p3 is checked and enlarged to fill its
   partition (nothing to do when it was shrunk to it), p7 gets an empty file system, /data and /dump get theirs back
   when they moved, and the script removes itself.

Then the Send fills p7 (and p3, p2) with the image's files, as for any multi-boot card.

THE NEW LAYOUT.  p1, p2 and where p3 starts stay as they are.  /data (p5) and /dump (p6) keep their own sizes at the
very end of the SD card (where a test card grown by :mod:`.testcard_grow` already has them: they are left alone
there).  Between them, p3 and p7 each get what the image needs - p3 at least what its files already use - and any
room left over is split between the two, so later builds can grow.  When the two don't fit the SD card PAD says so
and changes nothing.  p7 is the third logical partition in the chain (the kernel numbers them by the chain), placed
right after p3 at the front of the extended partition; p5 and p6 are not moved for it.

Going the other way (a multi-boot card replaced by one game or a test card), partition 7 is left on the card unused
(Simon: "leave partition 7 unused"): the Send leaves partitions it doesn't need alone.
"""

import contextlib
import os
import struct
import time

from . import remote_send as rs
from . import testcard_grow as tg

SECTOR = tg.SECTOR
ALIGN = tg.ALIGN
LAYOUT_DIR = "/usr/local/padlayout"
BOOT_SCRIPT_PATH = "/etc/rcS.d/S02zz_padlayout"
LOG_ON_DATA = "/data/pad/padlayout.log"
#: p3's room above what its files use, so the shrink never leaves it full (and resize2fs its own metadata)
P3_MARGIN = 512 << 20
#: how long the machine may take to come back: two restarts, a check and a shrink of p3 (a 230 GB /games with a
#: few files is minutes on the machine's SD card)
BACK_WITHIN = 1800


class LayoutError(rs.SendError):
    pass


def _up(x):
    return -(-x // ALIGN) * ALIGN


class Plan(object):
    """The new layout: ``sectors`` = [(LBA, 512 bytes)] to write (the EBRs first, the MBR last), ``expect`` =
    {partition: (start, sectors)} the machine shows after it, ``old`` the machine's layout now."""

    def __init__(self, old, card, expect, ext, move, label, sectors):
        self.old, self.card, self.expect, self.ext, self.move, self.label = old, card, expect, ext, move, label
        self.sectors = sectors

    @property
    def shrink_kb(self):
        """p3's new size in KiB when it is to be smaller (0: it keeps its size or grows)."""
        new = self.expect[3][1]
        return new * SECTOR // 1024 if new < self.old[3][1] else 0

    def conf(self):
        """The start-up script's own checks and steps."""
        e = self.expect
        return ("OLD_P3_START=%d\nOLD_P3_SIZE=%d\nP3_START=%d\nP3_SIZE=%d\nP5_START=%d\nP5_SIZE=%d\n"
                "P6_START=%d\nP6_SIZE=%d\nP7_START=%d\nP7_SIZE=%d\nSHRINK_KB=%d\nMOVE=%d\nLABEL=%s\nLBAS='%s'\n"
                % (self.old[3] + e[3] + e[5] + e[6] + e[7] + (self.shrink_kb, int(self.move), self.label,
                                                               " ".join(str(lba) for lba, _d in self.sectors))))

    def table(self):
        return b"".join(d for _lba, d in self.sectors)

    def words(self):
        """For the question and the log: what happens to each partition."""
        h = lambda n: rs._human(n * SECTOR)
        p3 = self.expect[3][1]
        how = "made smaller" if p3 < self.old[3][1] else "made bigger" if p3 > self.old[3][1] else "kept"
        return ("partition 3 (/games) %s: %s, partition 7 added: %s (the SD card is %s)"
                % (how, h(p3), h(self.expect[7][1]), h(self.card)))


def plan(layout, card_sectors, mbr, need3, need7, used3=0, label="multi"):
    """The new table for a machine whose partitions are *layout* (``{n: (start, sectors)}``) on an SD card of
    *card_sectors*, from its MBR sector *mbr*, for an image whose p3 is *need3* sectors and p7 *need7*; *used3* is
    what /games holds now (bytes); *label* p7's file system label (the image's)."""
    mbr = bytes(mbr)
    if len(mbr) != SECTOR or mbr[510:512] != b"\x55\xaa":
        raise LayoutError("The machine's card has no partition table PAD can read.")
    if sorted(layout) != [1, 2, 3, 4, 5, 6]:
        raise LayoutError("The machine's card isn't laid out as PAD can change over the network (partitions %s)."
                          % ", ".join(map(str, sorted(layout))))
    types = [mbr[0x1BE + 16 * i + 4] for i in range(4)]
    if types[2] != 0x83 or types[3] not in (0x05, 0x0F):
        raise LayoutError("The machine's card isn't laid out as PAD can change over the network.")
    p3s, p3c = layout[3][:2]
    p5s, p5c = layout[5][:2]
    p6s, p6c = layout[6][:2]
    if not (layout[2][0] + layout[2][1] <= p3s and p3s + p3c <= p5s < p6s):
        raise LayoutError("The machine's card isn't laid out as PAD can change over the network.")
    # /data and /dump at the very end: where they are when already there (a grown test card), else moved there
    n6 = tg._down(card_sectors - p6c)
    n5 = tg._down(n6 - ALIGN - p5c)
    move = (p5s, p6s) != (n5, n6)
    if not move:
        n5, n6 = p5s, p6s
    total = n5 - p3s - 2 * ALIGN                       # p3, the EBR at the extended's start, p7's EBR, p7
    want3 = _up(max(need3, (used3 + P3_MARGIN + SECTOR - 1) // SECTOR))
    want7 = _up(need7)
    if want3 + want7 > total:
        h = lambda n: rs._human(n * SECTOR)
        raise LayoutError("The machine's SD card is %s, too small for this multi-boot image: its games need %s on "
                          "partition 3 and %s on partition 7 (%s more than the card has room for)."
                          % (h(card_sectors), h(want3), h(want7), h(want3 + want7 - total)))
    left = total - want3 - want7
    a = tg._down(want3 + left // 2)
    ext = p3s + a
    ebr7 = ext + ALIGN
    p7s = ebr7 + ALIGN
    b = tg._down(n5 - p7s)
    if a < want3 or b < want7:                          # never, with the room checked above
        raise LayoutError("PAD couldn't fit this multi-boot image's partitions on the machine's SD card.")
    ebr6 = n6 - ALIGN
    end = n6 + p6c
    new = bytearray(mbr)
    new[0x1BE + 32:0x1FE] = tg._entry(0x83, p3s, a) + tg._entry(0x0F, ext, end - ext)
    # the chain: the EBR at the extended's start (p5), then p6's, then p7's - the kernel numbers them in that order
    chain = [(ext, n5, p5c), (ebr6, n6, p6c), (ebr7, p7s, b)]
    sectors = []
    for i, (ebr, start, count) in enumerate(chain):
        eb = bytearray(SECTOR)
        eb[0x1BE:0x1CE] = tg._entry(0x83, start - ebr, count, chs_base=ebr)
        if i + 1 < len(chain):
            nebr, nstart, ncount = chain[i + 1]
            eb[0x1CE:0x1DE] = tg._entry(0x05, nebr - ext, nstart + ncount - nebr, chs_base=ext)
        eb[510:512] = b"\x55\xaa"
        sectors.append((ebr, bytes(eb)))
    sectors.append((0, bytes(new)))
    expect = {3: (p3s, a), 5: (n5, p5c), 6: (n6, p6c), 7: (p7s, b)}
    return Plan(dict((n, tuple(v[:2])) for n, v in layout.items()), card_sectors, expect, ext, move,
                label if label and label.replace("_", "").replace("-", "").isalnum() else "multi", sectors)


# ---- the start-up script ---------------------------------------------------------------------------------------
#: Runs as a program (not sourced: the card's rc sources *.sh), early in start-up.  It changes something only when
#: the kernel shows exactly the table it expects; any other start-up changes nothing.
STARTUP = r"""#!/bin/sh
# PAD: laying this card out for a multi-boot image over the network (Simon, 2026-11-27).  Runs before the card's
# partitions are checked and mounted; PAD's Send wrote it.
D=@DIR@
[ -f $D/layout.conf ] || exit 0
. $D/layout.conf
part() { cat /sys/block/mmcblk0/mmcblk0p$1/$2 2>/dev/null; }
say() { echo "padlayout: $*"; echo "$*" >> $D/layout.log; }
dev() {
    if [ ! -b /dev/mmcblk0p$1 ]; then
        mm=$(part $1 dev)
        [ -n "$mm" ] && mknod /dev/mmcblk0p$1 b ${mm%%:*} ${mm##*:}
    fi
}
is_new() {
    [ "$(part 3 start)" = "$P3_START" ] && [ "$(part 3 size)" = "$P3_SIZE" ] && \
    [ "$(part 5 start)" = "$P5_START" ] && [ "$(part 5 size)" = "$P5_SIZE" ] && \
    [ "$(part 6 start)" = "$P6_START" ] && [ "$(part 6 size)" = "$P6_SIZE" ] && \
    [ "$(part 7 start)" = "$P7_START" ] && [ "$(part 7 size)" = "$P7_SIZE" ]
}
is_old() { [ "$(part 3 start)" = "$OLD_P3_START" ] && [ "$(part 3 size)" = "$OLD_P3_SIZE" ] && [ -z "$(part 7 start)" ]; }
mount -o remount,rw / || { echo "padlayout: the system partition can't be written: nothing changed"; exit 0; }
if is_old; then
    # step 1: p3's files kept, made to fit its new size, then the new table and a restart at once
    say "start-up $(date) - the old table: p3 $OLD_P3_SIZE sectors -> $P3_SIZE"
    dev 3
    $D/e2fsck -fy /dev/mmcblk0p3 >> $D/layout.log 2>&1
    rc=$?
    if [ $rc -gt 1 ]; then
        say "p3 /games has errors e2fsck could not fix ($rc): nothing changed"
        mv $D/layout.conf $D/layout.failed; rm -f $0; sync; mount -o remount,ro / 2>/dev/null; exit 0
    fi
    if [ "$SHRINK_KB" != 0 ]; then
        if ! $D/resize2fs /dev/mmcblk0p3 ${SHRINK_KB}K >> $D/layout.log 2>&1; then
            say "p3 /games could not be made smaller: nothing changed"
            mv $D/layout.conf $D/layout.failed; rm -f $0; sync; mount -o remount,ro / 2>/dev/null; exit 0
        fi
        say "p3 /games made smaller"
    fi
    i=0
    for lba in $LBAS; do
        dd if=$D/table.bin of=/dev/mmcblk0 bs=512 skip=$i seek=$lba count=1 2>/dev/null || say "sector $lba not written"
        i=$((i + 1))
    done
    sync
    say "new table written: restarting"
    mount -o remount,ro / 2>/dev/null
    reboot -f
    exit 0
fi
if ! is_new; then
    echo "padlayout: the card's partitions are neither the old nor the new ones: nothing changed"
    mount -o remount,ro / 2>/dev/null
    exit 0
fi
say "start-up $(date) - the new table"
for n in 3 5 6 7; do dev $n || say "no device for p$n"; done
ok=1
$D/e2fsck -fy /dev/mmcblk0p3 >> $D/layout.log 2>&1
rc=$?
if [ $rc -le 1 ] && RESIZE2FS_FORCE_LAZY_ITABLE_INIT=1 $D/resize2fs /dev/mmcblk0p3 >> $D/layout.log 2>&1; then
    say "p3 /games fills its partition"
else
    ok=0
    say "p3 /games not checked (e2fsck $rc)"
fi
if mke2fs -q -F -t ext4 -L $LABEL /dev/mmcblk0p7 >> $D/layout.log 2>&1; then
    say "p7 made ($LABEL)"
else
    ok=0
    say "p7 not made"
fi
if [ "$MOVE" = 1 ]; then
    for p in "5 /data data" "6 /dump dump"; do
        set -- $p
        if mke2fs -q -F -t ext4 -L $3 /dev/mmcblk0p$1 >> $D/layout.log 2>&1 && mount -t ext4 /dev/mmcblk0p$1 $2; then
            tar -xf $D/$3.tar -C $2 >> $D/layout.log 2>&1 && say "$2 back" || { ok=0; say "$2 not restored"; }
            umount $2
        else
            ok=0
            say "p$1 $2 failed"
        fi
    done
fi
if [ $ok = 1 ]; then
    say "done"
    if mount -t ext4 /dev/mmcblk0p5 /data; then
        mkdir -p /data/pad && cp $D/layout.log @LOG@
        umount /data
    fi
    rm -rf $D
    rm -f $0
else
    say "not finished: tried again at the next start-up"
fi
sync
mount -o remount,ro / 2>/dev/null
exit 0
"""


def startup_script():
    return STARTUP.replace("@DIR@", LAYOUT_DIR).replace("@LOG@", LOG_ON_DATA)


# ---- the image and the machine ---------------------------------------------------------------------------------
def image_layout(image):
    """``{n: (start, sectors, type)}`` of a card image's partitions."""
    from ..plugins.stern import spike3
    with open(image, "rb") as f:
        return {p["index"]: (p["start_lba"], p["sectors"], p["ptype"]) for p in spike3.parse_partitions(f)}


def image_p7_label(image, layout):
    """p7's ext4 label in the image ("multi", or the store layout's "padwork"), "multi" when unreadable."""
    p7 = layout.get(7)
    if not p7:
        return "multi"
    try:
        with open(image, "rb") as f:
            f.seek(p7[0] * SECTOR + 1024)
            sb = f.read(256)
        if struct.unpack_from("<H", sb, 0x38)[0] != 0xEF53:
            return "multi"
        return sb[0x78:0x88].split(b"\0")[0].decode("ascii", "replace") or "multi"
    except (OSError, struct.error):
        return "multi"


def has_p7(image):
    """Has the image a partition 7 (a multi-boot image's other games)?  One that can't be read: no (the Send then
    says what is wrong with it)."""
    try:
        return 7 in image_layout(image)
    except OSError:
        return False


def needs(image, machine_layout):
    """Does the image need partitions the machine's card hasn't (a multi-boot image's p7)?"""
    return has_p7(image) and 7 not in machine_layout


def survey(machine, image):
    """-> (plan, bytes the system partition needs, its free bytes).  Changes nothing."""
    # under way only with its start-up script there too: files left by a prepare that stopped part way are a
    # leftover (prepare starts afresh), not a change a restart would finish
    _rc, left = machine.sh("[ -f %s/layout.conf ] && [ -f %s ] && { echo UNFINISHED; tail -n 1 %s/layout.log "
                           "2>/dev/null; }" % (LAYOUT_DIR, BOOT_SCRIPT_PATH, LAYOUT_DIR), check=False)
    if "UNFINISHED" in (left or ""):
        last = [ln for ln in left.splitlines() if ln and ln != "UNFINISHED"]
        raise LayoutError("A change of this card's layout is still under way on the machine (%s): restart the "
                          "machine to let its start-up finish it." % (last[0] if last else "its start-up hasn't run"))
    il = image_layout(image)
    _rc, out = machine.sh("cat /sys/block/mmcblk0/size")
    card = tg._int(out, "the SD card's size")
    _rc, out = machine.sh("df -k %s | tail -n 1 | awk '{print $3}'" % rs.GAMES)
    used3 = tg._int(out, "how much /games holds") * 1024
    p = plan(machine.layout(), card, tg._sectors_hex(machine, [0])[0], il[3][1], il[7][1], used3,
             image_p7_label(image, il))
    need = tg.SPARE + sum(map(len, tg.tools().values())) + len(p.table())
    if p.move:
        _rc, out = machine.sh("du -sk /data /dump | awk '{s += $1} END {print s}'")
        need += tg._int(out, "how much /data and /dump hold") * 1024
    return p, need, machine.free(rs.ROOT)


def prepare(machine, p, log):
    """On the running machine: the start-up script, its tools, the table and (when they move) /data and /dump onto
    the system partition.  Nothing on the card's table changes until the start-up; a failure takes it all off."""
    log("Putting the card's new layout and its start-up script on the machine...", "info")
    kit = tg.tools()
    files = ["%s/layout.conf" % LAYOUT_DIR, "%s/table.bin" % LAYOUT_DIR, BOOT_SCRIPT_PATH] + \
        ["%s/%s" % (LAYOUT_DIR, name) for name in tg.TOOLS]
    try:
        machine.sh("mount -o remount,rw / && rm -rf %s && mkdir -p %s" % (LAYOUT_DIR, LAYOUT_DIR))
        if p.move:
            files += ["%s/data.tar" % LAYOUT_DIR, "%s/dump.tar" % LAYOUT_DIR]
            machine.sh("tar -cf %s/data.tar -C /data . && tar -cf %s/dump.tar -C /dump ." % (LAYOUT_DIR, LAYOUT_DIR),
                       timeout=900)
        machine.sh("cat > %s/table.bin" % LAYOUT_DIR, stdin=p.table())
        machine.sh("cat > %s/layout.conf" % LAYOUT_DIR, stdin=p.conf().encode("ascii"))
        for name in tg.TOOLS:
            machine.sh("cat > %s/%s && chmod 755 %s/%s" % (LAYOUT_DIR, name, LAYOUT_DIR, name), stdin=kit[name],
                       timeout=300)
        machine.sh("cat > %s && chmod 755 %s" % (BOOT_SCRIPT_PATH, BOOT_SCRIPT_PATH),
                   stdin=startup_script().encode("ascii"))
        _rc, out = machine.sh("for f in %s; do [ -s $f ] || echo MISSING $f; done; sync" % " ".join(files))
        if "MISSING" in out:
            raise LayoutError("The machine didn't keep the layout change's files (%s)." % out.strip())
    except BaseException:
        machine.sh("rm -rf %s; rm -f %s; sync" % (LAYOUT_DIR, BOOT_SCRIPT_PATH), check=False)
        raise
    machine.sh("mount -o remount,ro / 2>/dev/null; sync", check=False)


def check(machine, p):
    """After the restarts: the table the machine shows and the start-up's own log."""
    got = machine.layout()
    wrong = [n for n, want in sorted(p.expect.items()) if tuple(got.get(n, ())[:2]) != tuple(want)]
    _rc, why = machine.sh("cat %s/layout.log 2>/dev/null" % LAYOUT_DIR, check=False)
    last = ((why or "").strip().splitlines()[-1:] or ["its start-up script did not run"])[0]
    if wrong:
        raise LayoutError("The machine came back without the new partitions (p%s): %s."
                          % (", p".join(map(str, wrong)), last))
    _rc, done = machine.sh("cat %s 2>/dev/null" % LOG_ON_DATA, check=False)
    if "done" not in (done or "").split():
        raise LayoutError("The machine's start-up didn't finish laying out the card: %s" % last)


def run(machine_fn, image, log, progress, cancelled, sleep=time.sleep, clock=time.monotonic):
    """The whole change, from a connected machine (*machine_fn()* connects): survey, prepare, restart, wait, check.
    Returns a fresh connection to the machine on its new layout (the caller closes it)."""
    machine = machine_fn()
    try:
        p, need, free = survey(machine, image)
        if need > free:
            raise LayoutError("The machine's system partition has %s free, and the layout change needs %s on it."
                              % (rs._human(free), rs._human(need)))
        log("Laying out the machine's card for this multi-boot image: %s." % p.words(), "info")
        machine.pause_game()
        try:
            prepare(machine, p, log)
        except BaseException:
            with contextlib.suppress(Exception):
                machine.screen_stopped(False)
            raise
        machine.screen_changing()
        log("Restarting the machine: its start-up changes the card's layout and restarts it once more (a few "
            "minutes).", "info")
        booted = getattr(machine, "_boot", "")
        machine.reboot()
    finally:
        machine.close()
    sleep(30)
    until = clock() + BACK_WITHIN
    while True:
        if cancelled():
            raise LayoutError("Stopped waiting for the machine; it finishes the layout change as it starts up. Send "
                              "again once it is up.")
        try:
            machine = machine_fn()
            if booted and getattr(machine, "_boot", "") == booted:
                machine.close()
                raise rs.Unreachable("it has not restarted yet")
            break
        except rs.SendError:
            if clock() > until:
                raise LayoutError("The machine didn't come back on the network after its restarts. Check its "
                                  "screen; once it is up, Send again.") from None
            progress(0, 0, "Waiting for the machine to come back")
            sleep(10)
    try:
        check(machine, p)
    except BaseException:
        machine.close()
        raise
    log("The machine's card is laid out for the multi-boot image: %s." % p.words(), "info")
    return machine
