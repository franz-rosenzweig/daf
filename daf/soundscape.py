"""Sound: a quiet bed of recorded sound under the book, that follows the scene you're in.

The model reads a part of the book once (a chapter, or a long one's half) and says where its scenes
change and what each would sound like, in Daf's own sounds (SOUNDS): rain on the moor, a fire in a
hall, the sea from a ship's deck, a crowd in an inn, or for a book of essays or prayer, some quiet
music. Daf keeps what it said (table soundscapes) and, wherever you are, gives the scene you're in,
so the reader (web/soundscape.js) can fade from one bed into the next.

Where you are comes as the reader's place (its CFI, fraction and the words on the page) or the
Kindle's (the plugin's page, POST /api/kindle/where): audiomap.py finds it in the book's text, the
same way it finds the audiobook's place. A part is read when you first get to it, and the next one
while you read on, so most of the time it's there already.

The sounds are the recordings Chataltul plays, all Creative Commons 0 (public domain): seamless
loops with half a second of their own end before them and of their start after them (PAD in
soundscape.js), at one loudness. Daf keeps a copy in STATE/sounds, fetched the first time one is
needed from DAF_SOUNDS_URL.
"""
import bisect
import functools
import json
import logging
import os
import re
import threading
import time
import urllib.request
import zipfile

from lxml import etree

from . import ai, audiomap, config, db, ebooks

log = logging.getLogger("daf.soundscape")

# id: (file, what it sounds like and where it fits: the model chooses by this)
SOUNDS = {
    "rain": ("rain-1", "steady rain"),
    "drizzle": ("lightrain-1", "soft rain over open country"),
    "downpour": ("heavyrain-1", "a heavy downpour"),
    "thunderstorm": ("thunder-1", "rain with rolling thunder"),
    "far-storm": ("farstorm-1", "a summer night with thunder far off, crickets close"),
    "gale": ("wind-1", "wind howling round a house: a winter storm, a blizzard, a gale"),
    "empty-wind": ("hollowwind-1", "a thin, distant wind: open moor, tundra, a ruin, desolation"),
    "hearth": ("hearth-1", "a fire in a fireplace, indoors"),
    "campfire": ("crackle-1", "a crackling fire with snaps and pops: a camp, a forge, a burning"),
    "stove": ("sauna-1", "a wood stove burning steady: a small warm room, a cabin, a kitchen"),
    "great-hall": ("bigroom-1", "a big fire in a large room that rings: a hall, a castle, a church"),
    "surf": ("waves-1", "slow surf on a beach"),
    "rough-sea": ("bigwaves-1", "big waves hitting the shore: a storm at sea, cliffs"),
    "ocean": ("ocean-1", "breakers coming in: by the sea, a harbour, a ship's deck"),
    "stream": ("stream-1", "a brook or a river"),
    "forest": ("birds-1", "dawn chorus in a pine forest: woods, morning"),
    "garden": ("springbirds-1", "birds in spring: a garden, a village, the countryside by day"),
    "meadow": ("birdsong-1", "birdsong on a warm day: fields, a road, a park"),
    "jungle": ("rainforest-1", "drops on leaves in a rainforest, a shower now and then"),
    "night": ("night-1", "crickets and cicadas on a warm night outdoors"),
    "crickets": ("crickets-1", "just crickets: a still night, a porch, a field"),
    "crowd": ("cafeteria-1", "a busy crowd indoors: a tavern, a feast, a market hall, a school"),
    "murmur": ("cafe-1", "quiet talk and the odd cup: a café, an inn, a restaurant"),
    "chatter": ("copenhagen-1", "people chatting outdoors: a street, a square, a terrace"),
    "city-night": ("city-1", "a quiet city street at night, the odd car"),
    "calm": ("wandering-1", "music: slow, calm synths (reflection, peace, an essay)"),
    "vast": ("dunes-1", "music: wide and spacey (deserts, the sky, space, awe)"),
    "sacred": ("angelic-1", "music: soft drifting chords (prayer, the holy, wonder)"),
    "meditative": ("bowls-1", "music: singing bowls, waves and a bird (meditation, healing)"),
    "gong": ("tibetan-1", "music: a singing bowl and a gong (stillness, ritual)"),
}
SOURCE = os.environ.get("DAF_SOUNDS_URL") or "https://stuffs.tiresia.xyz/kavana/audio/"
DIR = config.STATE / "sounds"
PART_MIN, PART_MAX = 3000, 45000         # characters: a part shorter joins the next; a longer one is cut at a paragraph
RETRY = 600                              # seconds before a part the model failed on is tried again
LEAF = ("p", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "dd", "dt", "figcaption", "pre", "div", "td")

# ---- the sounds -------------------------------------------------------------------------------

_fetch = threading.Lock()


def sound_file(name):
    """The path of a sound's recording, fetched from SOURCE the first time; None for no such sound."""
    s = SOUNDS.get(name)
    if not s:
        return None
    p = DIR / f"{s[0]}.mp3"
    if p.exists():
        return p
    with _fetch:
        if p.exists():
            return p
        DIR.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(SOURCE.rstrip("/") + f"/{s[0]}.mp3", headers={"User-Agent": "Daf"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        if len(data) < 10000:
            raise RuntimeError("The sound didn't come")
        tmp = p.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(p)
    return p


# ---- the book in parts, and its paragraphs ---------------------------------------------------

def _book(conn, book_id):
    """(audiomap's book, its file's key) or (None, why)."""
    path, fmt = ebooks.book_file(conn, book_id)
    if not path:
        return None, "Daf has no file for this book"
    if fmt not in ("EPUB", "KEPUB"):
        return None, "Sound needs the book as an EPUB"
    st = path.stat()
    return audiomap.book(path), f"{st.st_size}:{st.st_mtime_ns}"


@functools.lru_cache(maxsize=4)
def _paras(path, key):
    """[(start, text)]: every paragraph in the book's text stream (audiomap's), in order."""
    B = audiomap.book(path)
    out = []
    with zipfile.ZipFile(path) as z:
        for s in B["secs"]:
            if not s["linear"] or not s["len"]:
                continue
            try:
                d = audiomap._section(z.read(s["href"]))
            except (KeyError, etree.XMLSyntaxError, ValueError):
                continue
            for el, at in d["el"].items():
                if not isinstance(el.tag, str) or etree.QName(el).localname not in LEAF:
                    continue
                if any(isinstance(k.tag, str) and etree.QName(k).localname in LEAF for k in el.iterdescendants()):
                    continue                     # only the innermost blocks
                text = " ".join("".join(el.itertext()).split())
                if len(text) > 1:
                    out.append((s["start"] + at, text))
    out.sort()
    return out


def parts(B, paras):
    """The book in the parts the model reads one at a time: [{start, end, title}]. Its chapters (the
    contents), a short one joined to the next, a long one cut at a paragraph."""
    total = B["total"]
    marks = sorted({0} | {e["pos"] for e in B["toc"] if 0 <= e["pos"] < total})
    out = []
    for i, a in enumerate(marks):
        b = marks[i + 1] if i + 1 < len(marks) else total
        if b > a:
            out.append({"start": a, "end": b, "title": audiomap.chapter_at(B, a) or ""})
    joined = []
    for p in out:
        if joined and joined[-1]["end"] - joined[-1]["start"] < PART_MIN:
            joined[-1]["end"] = p["end"]
            joined[-1]["title"] = joined[-1]["title"] or p["title"]
        else:
            joined.append(dict(p))
    starts = [s for s, _ in paras]
    cut = []
    for p in joined:
        a = p["start"]
        while p["end"] - a > PART_MAX:
            want = a + (p["end"] - a) // -(-(p["end"] - a) // PART_MAX)  # even pieces, each under PART_MAX
            k = bisect.bisect_left(starts, want)
            b = starts[k] if k < len(starts) and a < starts[k] < p["end"] else want
            cut.append({"start": a, "end": b, "title": p["title"]})
            a = b
        cut.append({"start": a, "end": p["end"], "title": p["title"]})
    return cut


def _part_at(P, c):
    for i, p in enumerate(P):
        if p["start"] <= c < p["end"]:
            return i
    return len(P) - 1 if P else None


# ---- the model reads a part -------------------------------------------------------------------

PROMPT = """You're the sound designer for someone reading a book. Under the page plays a quiet bed of
recorded background sound, and you choose it, scene by scene. Below is part of "{title}"{by}{where}.
Each paragraph starts with its number in brackets.

Split it into scenes by where it takes place and what can be heard there, and give each scene up to
three of these sounds (nothing else):
{sounds}

- Start a new scene only when the place, the weather or what a listener would hear really changes. A
  chapter usually has one to four; a long run of talk in one room is one.
- Each sound gets a level from 0.2 (just there) to 1 (full). It sits under reading, so keep it gentle;
  a storm the story is about can be loud.
- This is the ground under the scene, not effects: don't follow one door, one shot or one bell.
- The music sounds are for when no place can be heard: an essay, a reflection, a letter, a prayer, a
  memory. A book that is all argument or instruction can have one calm bed throughout, or nothing.
- Nothing fits, or anything would distract: give the scene no sounds.

Answer with JSON only, a list, the first scene at the first paragraph:
[{{"from": 1, "scene": "A few words, e.g. Rain on the moor", "sounds": {{"empty-wind": 0.6, "drizzle": 0.5}}}}]

{text}
"""


def _ask(meta, part, ps):
    by = f' by {meta["author"]}' if meta.get("author") else ""
    where = f', from "{part["title"]}"' if part.get("title") else ""
    sounds = "\n".join(f"{k}: {v[1]}" for k, v in SOUNDS.items())
    text = "\n".join(f"[{i + 1}] {t}" for i, (_, t) in enumerate(ps))
    out = ai.run(PROMPT.format(title=meta.get("title") or "a book", by=by, where=where, sounds=sounds, text=text), timeout=300)
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        raise RuntimeError("The model's answer had no scenes")
    raw = json.loads(m.group(0))
    scenes = []
    for x in raw if isinstance(raw, list) else []:
        if not isinstance(x, dict):
            continue
        try:
            n = int(x.get("from"))
        except (TypeError, ValueError):
            continue
        if not 1 <= n <= len(ps):
            continue
        snd = {}
        for k, v in (x.get("sounds") or {}).items() if isinstance(x.get("sounds"), dict) else ():
            if k in SOUNDS:
                try:
                    snd[k] = round(min(1.0, max(0.1, float(v))), 2)
                except (TypeError, ValueError):
                    pass
        snd = dict(sorted(snd.items(), key=lambda kv: -kv[1])[:3])
        scenes.append({"start": ps[n - 1][0], "scene": " ".join(str(x.get("scene") or "").split())[:60], "sounds": snd})
    scenes.sort(key=lambda s: s["start"])
    if not scenes:
        raise RuntimeError("The model's answer had no scenes")
    scenes[0]["start"] = part["start"]               # the first scene holds from the part's start
    keep = []
    for s in scenes:
        if keep and s["start"] == keep[-1]["start"]:
            keep[-1] = s
        elif not keep or s["sounds"] != keep[-1]["sounds"]:
            keep.append(s)
    return keep


_busy = set()
_lock = threading.Lock()


def _make(book_id, path, key, part, meta, then=None):
    """Reads one part in its own thread and keeps the scenes (or the error); then the next, if asked."""
    c = db.connect()
    try:
        ps = [p for p in _paras(str(path), key) if part["start"] <= p[0] < part["end"]]
        try:
            scenes = _ask(meta, part, ps) if ps else [{"start": part["start"], "scene": "", "sounds": {}}]
            err = None
        except Exception as e:                        # noqa: BLE001 - kept, shown, tried again later
            log.warning("soundscape %s @%s: %s", book_id, part["start"], e)
            scenes, err = [], str(e)[:300]
        c.execute("INSERT OR REPLACE INTO soundscapes (book_id, file, start, end, scenes, made, model, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (book_id, key, part["start"], part["end"], json.dumps(scenes), int(time.time()), ai.model(), err))
        c.commit()
    finally:
        c.close()
        with _lock:
            _busy.discard((book_id, part["start"]))
    if then and not err:
        ensure(book_id, path, key, then, meta)


def _row(conn, book_id, key, start):
    return conn.execute("SELECT scenes, error, made FROM soundscapes WHERE book_id = ? AND file = ? AND start = ?",
                        (book_id, key, start)).fetchone()


def ensure(book_id, path, key, part, meta, then=None, conn=None):
    """Starts reading a part unless it's read, being read, or failed lately. True when it's being read."""
    c = conn or db.connect()
    try:
        r = _row(c, book_id, key, part["start"])
    finally:
        if conn is None:
            c.close()
    if r and (not r["error"] or time.time() - r["made"] < RETRY):
        return False
    with _lock:
        if (book_id, part["start"]) in _busy:
            return True
        _busy.add((book_id, part["start"]))
    threading.Thread(target=_make, args=(book_id, path, key, part, meta, then), daemon=True, name="soundscape").start()
    return True


# ---- where you are → the scene -----------------------------------------------------------------

def at(conn, book_id, place):
    """The scene at a place in a book: {state: "ready" | "reading" | "failed" | "none", scene, sounds,
    part, why}. "reading": the model is on it, ask again in a few seconds."""
    B, key = _book(conn, book_id)
    if B is None:
        return {"state": "none", "why": key}
    path = B["path"]
    paras = _paras(str(path), key)
    P = parts(B, paras)
    if not P:
        return {"state": "none", "why": "This book has no text to go by"}
    c = audiomap.char_of(B, place or {})
    i = _part_at(P, c)
    part = P[i]
    nxt = P[i + 1] if i + 1 < len(P) else None
    b = conn.execute("SELECT title, author FROM books WHERE id = ?", (book_id,)).fetchone()
    meta = {"title": b["title"] if b else None, "author": b["author"] if b else None}
    r = _row(conn, book_id, key, part["start"])
    out = {"book_id": book_id, "title": meta["title"], "part": part["title"], "at": c}
    if not r or (r["error"] and time.time() - r["made"] >= RETRY):
        ensure(book_id, path, key, part, meta, then=nxt, conn=conn)
        return {**out, "state": "reading"}
    if r["error"]:
        return {**out, "state": "failed", "why": r["error"]}
    if nxt and c > part["start"] + 0.5 * (part["end"] - part["start"]):
        ensure(book_id, path, key, nxt, meta, conn=conn)   # read on ahead
    scenes = json.loads(r["scenes"])
    s = scenes[0] if scenes else {"scene": "", "sounds": {}}
    for x in scenes:
        if x["start"] <= c:
            s = x
    return {**out, "state": "ready", "scene": s["scene"], "sounds": s["sounds"]}


def forget(conn, book_id):
    """The scenes kept for a book go, so it's read again (the model, or the book, changed)."""
    conn.execute("DELETE FROM soundscapes WHERE book_id = ?", (book_id,))


# ---- the Kindle: the page the plugin last said it was on ----------------------------------------

def kindle_where(conn, book_id, text, fraction):
    w = {"book_id": book_id, "text": (text or "")[:600], "fraction": fraction, "at": time.time()}
    conn.execute("INSERT INTO kv (k, v) VALUES ('kindle_where', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (json.dumps(w),))
    return w


def kindle_now(conn):
    r = conn.execute("SELECT v FROM kv WHERE k = 'kindle_where'").fetchone()
    return json.loads(r[0]) if r else None


def kindle_scene(conn):
    w = kindle_now(conn)
    if not w:
        return {"state": "none", "why": "", "at": 0}
    place = {"text": w.get("text") or None, "fraction": w.get("fraction")}
    r = at(conn, w["book_id"], {k: v for k, v in place.items() if v is not None})
    return {**r, "seen": w["at"]}


# ---- the routes ---------------------------------------------------------------------------------

def router():
    import asyncio

    from fastapi import APIRouter, Depends, HTTPException
    from fastapi.responses import FileResponse
    from starlette.concurrency import run_in_threadpool

    from . import library
    from .app import conn, device, json_body, user, user_or_device

    r = APIRouter()

    @r.get("/api/sounds/{name}.mp3", dependencies=[Depends(user_or_device)])
    async def get_sound(name: str):
        """One of SOUNDS' recordings (a seamless loop, PAD seconds either side)."""
        if name not in SOUNDS:
            raise HTTPException(404, "No such sound")
        try:
            p = await run_in_threadpool(sound_file, name)
        except Exception as e:                    # noqa: BLE001
            raise HTTPException(502, f"The sound didn't come: {e}") from e
        return FileResponse(p, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"})

    @r.post("/api/ebooks/{book_id}/sound", dependencies=[Depends(user)])
    async def post_book_sound(book_id: str, b=Depends(json_body), c=Depends(conn)):
        """{cfi, fraction, text}: the reader's place → the scene there and its sounds (at)."""
        place = {k: b.get(k) for k in ("cfi", "fraction", "text") if b.get(k) is not None}
        return await run_in_threadpool(at, c, book_id, place)

    @r.post("/api/kindle/where")
    def post_kindle_where(b=Depends(json_body), name=Depends(device), c=Depends(conn)):
        """{md5, text, fraction}: the page the Kindle is on, from the plugin when Sound is on there."""
        md5 = str(b.get("md5") or "").strip().lower()
        bid = library.book_for_md5(c, md5) if re.fullmatch(r"[0-9a-f]{32}", md5) else None
        if not bid:
            return {"ok": False}
        try:
            f = float(b.get("fraction")) if b.get("fraction") is not None else None
        except (TypeError, ValueError):
            f = None
        kindle_where(c, bid, str(b.get("text") or ""), f)
        return {"ok": True}

    @r.get("/api/sound/kindle", dependencies=[Depends(user)])
    async def get_kindle_sound(after: float = 0, wait: int = 0):
        """The scene on the Kindle's page. With `after`, waits (up to `wait` seconds, at most 25) for a
        page newer than that, so a page can listen without a timer."""
        end = time.time() + min(max(wait, 0), 25)
        while True:
            c = db.connect()
            try:
                w = kindle_now(c)
                if not after or (w and w["at"] > after) or time.time() >= end:
                    return await run_in_threadpool(kindle_scene, c)
            finally:
                c.close()
            await asyncio.sleep(1)

    @r.get("/api/sound/sounds", dependencies=[Depends(user)])
    def get_sounds():
        return {"sounds": [{"id": k, "about": v[1]} for k, v in SOUNDS.items()]}

    return r
