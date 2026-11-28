"""A video mode's undo history (PAD-1661): every change to video_mode.json is one step, undo and redo are
unlimited, and the history survives a reload.

A step is the difference between the document before and after, as operations on JSON paths:

    {"p": path, "a": old, "b": new}              a value set ("a" absent: it was added; "b" absent: removed)
    {"p": path, "i": i, "a": [...], "b": [...]}  a list spliced at i: the items "a" there became the items "b"

so a moved thing costs a few numbers and a thing added to a 300-thing phase costs that thing, not the list.
Undo applies a step's operations backwards (in reverse order, "b" back to "a"); redo forwards.

On disk it is ``<mode>/.video_mode_history.jsonl``: a header line, then one line a step ({"label", "ops", "sha"})
or a move of the cursor ({"pos", "sha"}), appended as they happen; the file is rewritten only when a new step
throws away the redo branch or the cursor lines pile up. ``sha`` is the document's fingerprint at that point: when
the file on disk does not match the history's (the document was changed by something else), the history starts
again from the document as it is, rather than undoing into something that never was.
"""
import copy
import hashlib
import json
import os

FILE_NAME = ".video_mode_history.jsonl"
VERSION = 1
COMPACT_AFTER = 4000          # cursor lines before the file is written afresh


def fingerprint(doc):
    return hashlib.sha1(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                        .encode("utf-8")).hexdigest()


# ---- the difference ---------------------------------------------------------------------------------------------
def diff(a, b, path=None):
    """The operations that turn ``a`` into ``b``."""
    path = list(path or [])
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in a:
            if k not in b:
                out.append({"p": path + [k], "a": copy.deepcopy(a[k])})
            else:
                out += diff(a[k], b[k], path + [k])
        for k in b:
            if k not in a:
                out.append({"p": path + [k], "b": copy.deepcopy(b[k])})
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) == len(b):
            out = []
            for i, (x, y) in enumerate(zip(a, b)):
                out += diff(x, y, path + [i])
            return out
        lo = 0
        while lo < len(a) and lo < len(b) and _same(a[lo], b[lo]):
            lo += 1
        ea, eb = len(a), len(b)
        while ea > lo and eb > lo and _same(a[ea - 1], b[eb - 1]):
            ea -= 1
            eb -= 1
        return [{"p": path, "i": lo, "a": copy.deepcopy(a[lo:ea]), "b": copy.deepcopy(b[lo:eb])}]
    if _same(a, b):
        return []
    return [{"p": path, "a": copy.deepcopy(a), "b": copy.deepcopy(b)}]


def _same(x, y):
    """Strictly the same value: 1, 1.0 and True are three different things in a document (== says they are not)."""
    if type(x) is not type(y):
        return False
    if isinstance(x, dict):
        return list(x) == list(y) and all(_same(x[k], y[k]) for k in x)
    if isinstance(x, list):
        return len(x) == len(y) and all(_same(a, b) for a, b in zip(x, y))
    return x == y


def _parent(doc, path):
    node = doc
    for k in path[:-1]:
        node = node[k]
    return node


def apply(doc, ops, forward=True):
    """Apply ``ops`` to ``doc`` in place: forward ("a" to "b") or back. Returns doc."""
    src, dst = ("a", "b") if forward else ("b", "a")
    seq = ops if forward else list(reversed(ops))
    for op in seq:
        p = op["p"]
        if "i" in op:
            lst = _parent(doc, p)[p[-1]] if p else doc
            i = op["i"]
            lst[i:i + len(op[src])] = copy.deepcopy(op[dst])
            continue
        if not p:
            raise ValueError("a step cannot replace the whole document")
        par = _parent(doc, p)
        if dst in op:
            par[p[-1]] = copy.deepcopy(op[dst])
        else:
            del par[p[-1]]
    return doc


# ---- the history ------------------------------------------------------------------------------------------------
class History:
    """The steps of one mode's document, and where the document is among them."""

    def __init__(self, mode_dir):
        self.path = os.path.join(mode_dir, FILE_NAME)
        self.steps = []           # [{"label", "ops", "sha"}]
        self.pos = 0              # steps[:pos] are applied
        self.base = ""            # the fingerprint before steps[0]
        self._cursor_lines = 0

    # -- reading and writing --
    def open(self, doc):
        """Read the history for ``doc`` as it is on disk. Starts afresh when there is none or it does not lead to
        this document."""
        sha = fingerprint(doc)
        steps, pos, base, cursor = [], 0, "", 0
        try:
            with open(self.path, encoding="utf-8") as f:
                head = json.loads(f.readline() or "{}")
                if head.get("v") != VERSION:
                    raise ValueError("not this history's version")
                base = head.get("base", "")
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if "ops" in rec:
                        del steps[pos:]
                        steps.append(rec)
                        pos = len(steps)
                    elif "pos" in rec:
                        pos = max(0, min(len(steps), int(rec["pos"])))
                        cursor += 1
        except (OSError, ValueError, KeyError, TypeError):
            steps, pos, base, cursor = [], 0, "", 0
        here = steps[pos - 1]["sha"] if pos else base
        if here != sha:
            steps, pos, base, cursor = [], 0, sha, 0
            self.steps, self.pos, self.base, self._cursor_lines = steps, pos, base, cursor
            self._rewrite()
            return self
        self.steps, self.pos, self.base, self._cursor_lines = steps, pos, base, cursor
        return self

    def _rewrite(self):
        tmp = self.path + ".part"
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps({"v": VERSION, "base": self.base}) + "\n")
                for s in self.steps:
                    f.write(json.dumps(s, ensure_ascii=False, separators=(",", ":")) + "\n")
                if self.pos != len(self.steps):
                    f.write(json.dumps({"pos": self.pos, "sha": self.here()}) + "\n")
            os.replace(tmp, self.path)
        except OSError:
            pass                   # the history is a convenience: the document itself is already saved
        self._cursor_lines = 0

    def _append(self, rec):
        try:
            with open(self.path, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            pass

    # -- the steps --
    def here(self):
        return self.steps[self.pos - 1]["sha"] if self.pos else self.base

    def push(self, label, before, after):
        """Record the change from ``before`` to ``after`` (both whole documents) as one step. False when nothing
        changed."""
        ops = diff(before, after)
        if not ops:
            return False
        rec = {"label": str(label or "Change")[:80], "ops": ops, "sha": fingerprint(after)}
        if self.pos < len(self.steps):
            del self.steps[self.pos:]
            self.steps.append(rec)
            self.pos = len(self.steps)
            self._rewrite()
        else:
            if not os.path.isfile(self.path):
                self.base = fingerprint(before)
                self._rewrite()
            self.steps.append(rec)
            self.pos = len(self.steps)
            self._append(rec)
        return True

    def can_undo(self):
        return self.pos > 0

    def can_redo(self):
        return self.pos < len(self.steps)

    def undo_label(self):
        return self.steps[self.pos - 1]["label"] if self.pos else ""

    def redo_label(self):
        return self.steps[self.pos]["label"] if self.pos < len(self.steps) else ""

    def _moved(self):
        self._cursor_lines += 1
        if self._cursor_lines > COMPACT_AFTER:
            self._rewrite()
        else:
            self._append({"pos": self.pos, "sha": self.here()})

    def undo(self, doc):
        """The document one step back (a new dict), or None at the start."""
        if not self.pos:
            return None
        out = apply(copy.deepcopy(doc), self.steps[self.pos - 1]["ops"], forward=False)
        self.pos -= 1
        self._moved()
        return out

    def redo(self, doc):
        if self.pos >= len(self.steps):
            return None
        out = apply(copy.deepcopy(doc), self.steps[self.pos]["ops"], forward=True)
        self.pos += 1
        self._moved()
        return out

    def state(self):
        return {"can_undo": self.can_undo(), "can_redo": self.can_redo(), "undo_label": self.undo_label(),
                "redo_label": self.redo_label(), "steps": len(self.steps), "pos": self.pos}
