"""A hash of a whole card file, for every maker.

Simon (DragonRR), 2026-11-28, on the Select card tab's "Existing extraction" box: "we need
to cover all cards... if possible".  A folder's own record names its card by file name and
size, and every card built for one machine is the same size; only Stern Spike 2 could check
a card's files against a project.  So every Extract now keeps a sha256 of the card file it
read (``card_sha256`` in the project's ``.extract_source.json``), and the box hashes the
picked card and compares: the same hash is the same card file, whoever made it.

sha256 runs at about 1.7 GB/s here (Simon's 8 GB Godzilla card: ~5 s from Windows' cache,
longer from a cold disk), so a card's hash is kept per file stamp (size and modified time)
in :data:`HASH_CACHE` and a card is read again only once it changed.
"""

import hashlib
import json
import os
import time

from . import config

#: ``{card key: {"size", "mtime_ns", "sha256", "seen"}}`` beside settings.json.
HASH_CACHE = os.path.join(os.path.dirname(config.SETTINGS_FILE), "card_hashes.json")
#: Newest entries kept.
_MAX_CACHED = 200
_CHUNK = 4 << 20


def _key(path):
    return os.path.normcase(os.path.abspath(str(path)))


def _stamp(path):
    try:
        st = os.stat(path)
    except (OSError, ValueError, TypeError):
        return None
    return st.st_size, st.st_mtime_ns


def _load():
    try:
        with open(HASH_CACHE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data):
    if len(data) > _MAX_CACHED:
        keep = sorted(data, key=lambda k: data[k].get("seen", 0))[-_MAX_CACHED:]
        data = {k: data[k] for k in keep}
    try:
        os.makedirs(os.path.dirname(HASH_CACHE), exist_ok=True)
        tmp = HASH_CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        os.replace(tmp, HASH_CACHE)
    except OSError:
        pass


def cached(path):
    """The card's hash from the cache while its size and modified time are unchanged, else
    ``None`` (nothing read)."""
    stamp = _stamp(path)
    if stamp is None:
        return None
    hit = _load().get(_key(path))
    if hit and (hit.get("size"), hit.get("mtime_ns")) == tuple(stamp) and hit.get("sha256"):
        return hit["sha256"]
    return None


def card_sha256(path, progress=None):
    """The sha256 of the whole file at *path* (hex), from the cache when the file is
    unchanged; ``None`` when it is not a readable regular file.  *progress(done, total)*
    is called as it reads.  Reads the whole file: call off the UI thread."""
    if not path or not os.path.isfile(path):
        return None
    got = cached(path)
    if got:
        return got
    stamp = _stamp(path)
    h = hashlib.sha256()
    done = 0
    try:
        with open(path, "rb") as f:
            while True:
                block = f.read(_CHUNK)
                if not block:
                    break
                h.update(block)
                done += len(block)
                if progress is not None:
                    try:
                        progress(done, stamp[0])
                    except Exception:                   # noqa: BLE001
                        pass
    except OSError:
        return None
    digest = h.hexdigest()
    if _stamp(path) == stamp:                           # not changed while it was read
        data = _load()
        data[_key(path)] = {"size": stamp[0], "mtime_ns": stamp[1], "sha256": digest,
                            "seen": time.time()}
        _save(data)
    return digest
