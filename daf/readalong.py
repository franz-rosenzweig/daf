"""Reading along with the real audiobook: the whole recording matched to the book, once.

audiomap.py finds one place at a time: it hears 24 seconds and finds those words in the EPUB. This
does the same for the whole recording, in the background (media.py's "bookmap" job), and keeps what
it found, so the reader can mark the sentence being read and turn the page with the narrator:

1. Is it this text at all? Five places in the recording are heard (40 seconds each) and looked for
   in the whole book. None found: it's another translation or another book, and nothing more is done.
2. The recording goes through faster-whisper (base.en) ten minutes at a time, at low priority. Each
   thing said (a segment, three or four seconds) is looked for near where the last one ended, with
   audiomap's _find_words, and where it starts is kept as a point: (second, character in the text).
   Measured on this server: about seven minutes of work for an hour of audio, a point every four
   seconds, and a sentence's start within half a second (0.3 s in the middle, 0.6 s for nine in ten).
3. What isn't found near there (credits, music, a foreword the EPUB doesn't have) leaves no point.
   After forty such words they're looked for in the whole book: an abridged recording has skipped
   ahead, and the matching goes on from where it is now.

The points live in kv "readalong-pts:<book>" ({"t": [...], "c": [...]}), and what's known about them
in kv "readalong:<book>" (the audiobook, the file they were made for, how far the work is, and where
the matching is, so a restart goes on from the last ten minutes done). audiomap.py uses them when
they're there (the audiobook from here, and the place offered on opening, need no hearing then).

Where the points stop (a stretch that isn't in the book), the chapter guess of audiomap.py stands.
"""
import bisect
import json
import logging
import os
import time

from . import audiomap, db

log = logging.getLogger("daf.readalong")

MODEL = "base.en"
CHUNK = 600           # seconds of audio heard at a time: what a restart can lose
SPAN = 6000           # characters either side of where the next thing said should be (six minutes' reading)
MINW = 4              # words a thing said needs, to be found by its three-word runs
COVER = 0.3           # of its three-word runs, in the book at one place
WIDE = 40             # words not found near, before the whole book is asked
PACE = 15.0           # characters a second, as a narrator reads
FAST = 40.0           # no one reads faster: further on than that is a place to be sure of first
ENOUGH = 0.3          # of what's said, found: the recording is this text


# ---- matching what's said to the book ---------------------------------------------------------

def fresh():
    """Where the matching is, at the start: nowhere yet."""
    return {"t": 0.0, "c": None, "pc": -1, "lost": [], "end": None, "said": 0.0, "found": 0.0}


def _n(text):
    return len(audiomap._norm_words(text))


def _place(B, st, seg, free=False):
    """One thing said, found near where the matching is: the characters it starts and ends at, or None.
    free: the whole book has just said where it is, so it may be anywhere near that."""
    a, _, text = seg
    n = _n(text)
    if n < MINW or st["c"] is None:
        return None
    dt = max(0.0, a - st["t"])
    f = audiomap._find_words(B, text, near=st["c"] + min(PACE * dt, SPAN / 2), span=SPAN)
    if not f or len({i for i, _ in f}) < COVER * (n - 2):
        return None
    starts = B["starts"]
    i, j = f[0]
    c = starts[max(0, j - i)]
    if not free and not st["c"] - 200 <= c <= st["c"] + FAST * dt + 600:
        return None                                   # back, or too far on: not said here
    i, j = f[-1]
    return c, starts[min(len(starts) - 1, j + n - i)]


def _wide(B, st, lost):
    """What's been said and not found, looked for further off, then in the whole book: the character
    it starts at, or None when it isn't in this text."""
    text = " ".join(x[2] for x in lost)
    need = 0.5 * (_n(text) - 2)
    for near in ([st["c"]] if st["c"] is not None else []) + [None]:
        f = audiomap._find_words(B, text, near=near, span=10 * SPAN if near is not None else None)
        if f and len({i for i, _ in f}) >= need:
            i, j = f[0]
            return B["starts"][max(0, j - i)]
    return None


def match(B, segs, st):
    """A stretch of the recording, [(start, end, text)] in its seconds and in order, found in the book:
    [(second, character)], going on from st (where the matching is; kept from one stretch to the next)."""
    pts = []

    def put(t, c):
        if c > st["pc"] and (not pts or t > pts[-1][0]):
            pts.append((round(t, 2), int(c)))
            st["pc"] = c

    def found(seg, got):
        c, c_end = got
        put(seg[0], c)
        st.update(t=seg[1], c=c_end, end=[seg[1], c_end])
        st["found"] += seg[1] - seg[0]

    for seg in segs:
        a, b, text = seg
        end, st["end"] = st["end"], None
        if end and a - end[0] >= 1.0 and end[1] > st["pc"]:    # a silence after the last one found: it ended there
            pts.append((round(end[0], 2), int(end[1])))
            st["pc"] = end[1] - 1                              # (the next may start right there, not before)
        if _n(text) < MINW:
            if st["lost"]:
                st["lost"].append([a, b, text])                # "Yes." is no place, but it's words for the whole book
            continue
        st["said"] += b - a
        got = _place(B, st, seg)
        if got:
            st["lost"] = []
            found(seg, got)
            continue
        lost = st["lost"]
        lost.append([a, b, text])
        if sum(_n(x[2]) for x in lost) < WIDE:
            continue
        at = _wide(B, st, lost)
        if at is None:
            st["lost"] = lost[len(lost) // 2:]                 # not in the book; the newer half is asked again with what comes
            continue
        st.update(t=lost[0][0], c=at, pc=-1, lost=[])          # it's there: the ones not found are found from there
        free = True
        for x in lost:
            got = _place(B, st, x, free=free)
            if got:
                found(x, got)
                free = False
    return pts


# ---- kept: the points, and what's known about them -----------------------------------------------

def _key(book_id):
    return "readalong:" + book_id


def _file_key(path):
    st = os.stat(path)
    return f"{st.st_size}:{st.st_mtime_ns}"


def _get(conn, k):
    r = conn.execute("SELECT v FROM kv WHERE k = ?", (k,)).fetchone()
    try:
        return json.loads(r[0]) if r else None
    except ValueError:
        return None


def _put(conn, k, v):
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (k, json.dumps(v, separators=(",", ":"))))


def _pair(conn, book_id):
    """(the audiobook, the EPUB's path) of a book that has both, else (None, None)."""
    from . import absapi, ebooks
    item = absapi.for_book(conn, book_id)
    if not item:
        return None, None
    path, fmt = ebooks.book_file(conn, book_id)
    return (item, path) if path and fmt in ("EPUB", "KEPUB") else (None, None)


def meta(conn, book_id, item=None, path=None):
    """What's kept for this book, if it was made for this audiobook and this file."""
    m = _get(conn, _key(book_id))
    if not m or m.get("v") != 1:
        return None
    if item is None:
        item, path = _pair(conn, book_id)
    try:
        return m if item and m.get("item") == item and m.get("file") == _file_key(path) else None
    except OSError:
        return None


def status(conn, book_id):
    """For the book's page: None (no audiobook beside an EPUB), else {"state", "done"}: "none", "queued",
    "going" (done: how far, 0 to 1), "ready", "other" (the recording isn't this text) or "failed"."""
    from . import media
    item, path = _pair(conn, book_id)
    if not item:
        return None
    m = meta(conn, book_id, item, path)
    if m and m.get("state") in ("ready", "other"):
        return {"state": m["state"], "done": 1.0}
    done = round(min(1.0, m["done"] / m["dur"]), 3) if m and m.get("dur") else 0.0
    j = media.job_status(conn, "bookmap", book_id)
    if j and j["status"] in ("queued", "running"):
        return {"state": "going" if j["status"] == "running" else "queued", "done": done}
    if j and j["status"] == "failed":
        return {"state": "failed", "done": done, "error": j["error"]}
    return {"state": "none", "done": done}


def points(conn, book_id):
    """The points of a book whose audiobook is ready: ([seconds], [characters]), else None."""
    m = meta(conn, book_id)
    if not m or m.get("state") != "ready":
        return None
    p = _get(conn, _key(book_id).replace("readalong:", "readalong-pts:", 1)) or {}
    return (p["t"], p["c"]) if p.get("t") and len(p["t"]) == len(p.get("c") or ()) else None


def for_reader(conn, book_id):
    """What the reader follows by: the points as words, not characters (the page counts its own words
    the same way; characters differ with how a browser reads the file): {"item", "duration", "secs":
    [[the section's first word, its words], ...] for each spine section, "t": [...], "w": [...]}."""
    p = points(conn, book_id)
    if not p:
        return None
    item, path = _pair(conn, book_id)
    B = audiomap.book(path)
    starts = B["starts"]
    word = lambda c: bisect.bisect_left(starts, c)
    secs = []
    for s in B["secs"]:
        w0 = word(s["start"])
        secs.append([w0, word(s["start"] + s["len"]) - w0])
    m = meta(conn, book_id, item, path)
    return {"item": item, "duration": m.get("dur"), "secs": secs, "t": [round(t, 1) for t in p[0]], "w": [min(word(c), len(starts) - 1) for c in p[1]]}


# ---- a place in one, in the other (for audiomap.py) ---------------------------------------------

def time_at(p, c):
    """The second a character is read at, or None where the points don't reach it."""
    T, C = p
    order = sorted(range(len(C)), key=C.__getitem__) if any(a > b for a, b in zip(C, C[1:])) else None
    k = bisect.bisect_right([C[i] for i in order] if order else C, c) - 1
    if k < 0:
        return None
    k = order[k] if order else k
    if k + 1 < len(C) and C[k + 1] > c and T[k + 1] - T[k] < 60:
        return T[k] + (c - C[k]) / max(1, C[k + 1] - C[k]) * (T[k + 1] - T[k])
    return T[k] + (c - C[k]) / PACE if c - C[k] < 600 else None


def char_at(p, t):
    """The character being read at a second, or None where the points don't reach it."""
    T, C = p
    k = bisect.bisect_right(T, t) - 1
    if k < 0:
        return None
    if k + 1 < len(T) and T[k + 1] - T[k] < 60 and C[k + 1] > C[k]:
        return int(C[k] + (t - T[k]) / max(1e-3, T[k + 1] - T[k]) * (C[k + 1] - C[k]))
    return int(C[k] + (t - T[k]) * PACE) if t - T[k] < 40 else None


# ---- the job ------------------------------------------------------------------------------------

def _hear(path, local, duration, off):
    """`duration` seconds of an audio file from `local`, as [(start, end, text)] in the audiobook's seconds."""
    from . import media
    res = media.whisper(path, start=local, duration=duration, model=MODEL, timeout=3600, low=True)
    return [(off + float(s["start"]), off + float(s.get("end") or s["start"]), s.get("text") or "") for s in res.get("segments") or []]


def _files(item_id):
    """The audiobook's files on this disk, in order: [(path, the second it starts at, its seconds)]."""
    from . import absapi
    from .media import ABS_MOUNTS
    med = absapi.item(item_id).get("media") or {}
    out, off = [], 0.0
    for f in sorted([f for f in med.get("audioFiles") or [] if not f.get("exclude")], key=lambda f: f.get("index") or 0):
        path = (f.get("metadata") or {}).get("path") or ""
        for k, v in ABS_MOUNTS.items():
            if path.startswith(k + "/"):
                path = v + path[len(k):]
        dur = float(f.get("duration") or 0)
        out.append((path, off, dur))
        off += dur
    return out


def is_it(B, files, hear=None):
    """Is the recording this text? Five places in it, 40 seconds each, looked for in the whole book:
    False only when something was said at two of them or more and none of it is in the book."""
    hear = hear or _hear
    total = sum(d for _, _, d in files)
    said = hits = 0
    for frac in (0.15, 0.3, 0.5, 0.7, 0.85):
        t = total * frac
        path, off, dur = next((f for f in files if f[1] + f[2] > t), files[-1])
        text = " ".join(x[2] for x in hear(path, max(0.0, min(t - off, dur - 40)), 40, off))
        n = _n(text)
        if n < 30:
            continue                                  # music, a pause
        said += 1
        f = audiomap._find_words(B, text)
        hits += len({i for i, _ in f}) >= 0.4 * (n - 2)
    return hits > 0 or said < 2


def build(book_id, hear=None, files=None):
    """The job: hear the audiobook ten minutes at a time and keep where each thing said is in the book.
    It goes on from where it stopped (a restart, or Prepare pressed again after a failure).
    hear and files: the tests' own, in place of whisper and the audiobook's files."""
    hear = hear or _hear
    with db.session() as conn:
        item, path = _pair(conn, book_id)
        if not item:
            raise RuntimeError("No audiobook and EPUB for this book")
        m = meta(conn, book_id, item, path)
        pk = _key(book_id).replace("readalong:", "readalong-pts:", 1)
        p = _get(conn, pk) if m else None
    if m and m.get("state") in ("ready", "other"):
        return m
    B = audiomap.book(path)
    if files is None:
        files = _files(item)
        if not files or not all(os.path.isfile(f[0]) for f in files):
            raise RuntimeError("The audiobook's files aren't on this disk")
    total = sum(d for _, _, d in files)
    if not m:
        m = {"v": 1, "item": item, "file": _file_key(path), "dur": round(total, 2), "done": 0.0, "state": "going", "st": fresh(), "made": int(time.time())}
        p = {"t": [], "c": []}
        if not is_it(B, files, hear):
            m.update(state="other", st=None)
    p = p or {"t": [], "c": []}

    def keep():
        with db.session() as conn:
            _put(conn, _key(book_id), m)
            _put(conn, pk, p)

    keep()
    if m["state"] == "other":
        return m
    st = m["st"]
    for fpath, off, dur in files:
        local = 0.0
        while local < dur - 0.5:
            upto = min(off + local + CHUNK, off + dur)
            if upto > m["done"] + 0.5:                         # (what's already done is skipped)
                for t, c in match(B, hear(fpath, local, min(CHUNK, dur - local), off), st):
                    if not p["t"] or t > p["t"][-1]:
                        p["t"].append(t)
                        p["c"].append(c)
                m["done"] = round(upto, 2)
                keep()
            local += CHUNK
    if st["end"] and st["end"][1] >= st["pc"] and (not p["t"] or st["end"][0] > p["t"][-1]):
        p["t"].append(round(st["end"][0], 2))
        p["c"].append(int(st["end"][1]))
    m.update(state="ready" if st["found"] >= ENOUGH * max(1.0, st["said"]) else "other", said=round(st["said"]), found=round(st["found"]), st=None)
    keep()
    log.info("readalong %s: %s, %d points, %d of %d seconds found", book_id, m["state"], len(p["t"]), m["found"], m["said"])
    return m
