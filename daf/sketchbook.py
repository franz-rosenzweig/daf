"""The Sketchbook: pages to write, draw and type on beside whatever is open (web/sketchbook.js),
kept here, in the vault (sketchvault.py: a note of its own, in Obsidian's Ink plugin's format) and,
for a book, on the Kindle.

What it's beside is its item: "book:<book id>" (a book, EPUB or PDF), "doc:<doc id>" (an article,
a video, a reel, a podcast episode, a PDF document) or "manga:<Komga series id>". An item has tabs,
a page each: a book a tab per chapter, a manga series a tab per volume, and every item the General
one ("").

A page is blocks one under another, as the note in the vault has them: typed text, handwriting
(an Ink writing block: INK_W units across, ruled every LINE), a drawing (an Ink drawing block, in
its own units), and pictures (a manga page or a PDF page, whole or a part of it), which can be
written on too. Each block has its place (ord); each stroke the block it's in (blk), its points in
that block's units. Every block and stroke has the id the page made for it, so what's written
offline and sent twice is kept once and undo takes it away by its id; the same id sent again
replaces it (typed text edited, a block moved).

A book's pages go to the Kindle as KOReader bookmarks at the chapter's start, their text (typed,
and the handwriting as read) as the bookmark's note; the Daf plugin asks for them with
/api/kindle/book and says which it has.
"""
import base64
import hashlib
import json
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from . import config

INK_W, LINE = 2000, 150                      # an Ink writing block's width and ruled lines (its WRITING_PAGE_WIDTH, WRITING_LINE_HEIGHT)
ITEM = re.compile(r"^(book|doc|manga):[^\s/]{1,200}$")
TAB = re.compile(r"^(|c:[^\n]{1,400}|v:[A-Za-z0-9_-]{1,64})$")
MARK_ID = re.compile(r"^[ktib][0-9a-z]{8,40}$")
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
TOOLS = ("fountain", "calligraphy", "pen", "pencil", "brush", "marker", "highlighter")
HL_COLORS = ("yellow", "green", "blue", "pink", "purple")
MAX_POINTS = 4000
IMAGES = config.STATE / "sketchbook"          # the pictures on its pages, by their hash
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
KINDLE_MARK = "Sketchbook"                    # a page on the Kindle is a bookmark whose text starts with this
DRAWN = "[Drawing in Daf]"                    # and says so when there's handwriting on it nobody could read


def _num(v, lo, hi):
    v = float(v)
    if v != v:                                  # NaN
        raise ValueError("Not a number")
    return max(lo, min(hi, v))


def _r1(v):
    return round(v, 1)


def _color(c, highlighter=False):
    if highlighter:
        return c if c in HL_COLORS else "yellow"
    return c if c == "ink" or COLOR.match(str(c or "")) else "ink"


def _clean(m):
    """A block or a stroke as the page sent it, checked: (id, kind, data). ValueError if it isn't one."""
    if not isinstance(m, dict) or not MARK_ID.match(str(m.get("id") or "")):
        raise ValueError("Bad mark id")
    kind = m.get("kind")
    if kind == "stroke":
        if not MARK_ID.match(str(m.get("blk") or "")):
            raise ValueError("A stroke needs its block")
        pts = m.get("pts")
        if not isinstance(pts, list) or not pts or len(pts) > MAX_POINTS:
            raise ValueError("Bad points")
        clean = []
        for p in pts:
            if not isinstance(p, (list, tuple)) or len(p) < 2:
                raise ValueError("Bad point")
            clean.append([_r1(_num(p[0], -100000, 100000)), _r1(_num(p[1], -100000, 400000)),
                          round(_num(p[2] if len(p) > 2 else 0.5, 0, 1), 2)])
        tool = m.get("tool") if m.get("tool") in TOOLS else "pen"
        d = {"blk": m["blk"], "tool": tool, "color": _color(m.get("color"), tool == "highlighter"), "size": _r1(_num(m.get("size") or 6, 0.3, 600)),
             "o": round(_num(m.get("o") if m.get("o") is not None else 1, 0.05, 1), 2), "pts": clean}
        if m.get("sh"):
            d["sh"] = 1
        return m["id"], kind, d
    d = {"ord": round(_num(m.get("ord") if m.get("ord") is not None else 0, -1e9, 1e9), 6)}
    if m.get("t") is not None:                    # a video's or an episode's time, in seconds
        d["t"] = _r1(_num(m["t"], 0, 10 ** 6))
    if kind == "text":
        d["text"] = str(m.get("text") or "").replace("\r\n", "\n").rstrip()[:20000]
        if not d["text"] and "t" not in d:
            raise ValueError("No text")
    elif kind == "ink":
        d["type"] = "drawing" if m.get("type") == "drawing" else "writing"
        vb = m.get("vb")
        if d["type"] == "drawing" and isinstance(vb, list) and len(vb) == 4:
            d["vb"] = [_r1(_num(vb[0], -1e5, 1e5)), _r1(_num(vb[1], -1e5, 1e5)), _r1(_num(vb[2], 1, 1e5)), _r1(_num(vb[3], 1, 1e5))]
        if m.get("transcript"):
            d["transcript"] = str(m["transcript"]).strip()[:20000]
    elif kind == "image":
        d.update(w=INK_W, h=_r1(_num(m.get("h") or INK_W, 20, INK_W * 20)), file=_picture(m), cap=str(m.get("cap") or "")[:200])
    else:
        raise ValueError("Bad mark")
    return m["id"], kind, d


def _picture(m):
    """A picture's file: one already kept (file), or one sent as a data: address, kept now."""
    f = str(m.get("file") or "")
    if re.fullmatch(r"[0-9a-f]{40}\.(jpg|png|webp)", f) and (IMAGES / f).exists():
        return f
    src = str(m.get("src") or "")
    mt = re.match(r"^data:(image/(?:jpeg|png|webp));base64,", src)
    if not mt:
        raise ValueError("Bad picture")
    data = base64.b64decode(src[mt.end():], validate=False)
    if not data or len(data) > 6 * 1024 * 1024:
        raise ValueError("That picture is too big")
    name = hashlib.sha1(data).hexdigest() + IMAGE_TYPES[mt.group(1)]
    IMAGES.mkdir(parents=True, exist_ok=True)
    p = IMAGES / name
    if not p.exists():
        tmp = p.with_name("." + name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)
    return name


def item_ok(item):
    return bool(ITEM.match(item or ""))


def tabs(conn, item):
    """The item's tabs with something on them, in reading order (General first)."""
    rows = conn.execute(
        "SELECT t.tab, t.title, t.pos, t.updated, COUNT(m.id) AS n FROM sketch_tabs t "
        "JOIN sketch_marks m ON m.item = t.item AND m.tab = t.tab AND m.kind != 'stroke' WHERE t.item = ? GROUP BY t.tab", (item,)).fetchall()
    out = [dict(r) for r in rows]
    out.sort(key=lambda r: (r["tab"] != "", r["pos"] if r["pos"] is not None else 2, r["title"] or ""))
    return out


def marks(conn, item, tab):
    out = []
    for r in conn.execute("SELECT id, kind, data, updated FROM sketch_marks WHERE item = ? AND tab = ? ORDER BY created, rowid", (item, tab)):
        try:
            d = json.loads(r["data"])
        except ValueError:
            continue
        out.append({"id": r["id"], "kind": r["kind"], "updated": r["updated"], **d})
    return out


def has(conn, item):
    return conn.execute("SELECT 1 FROM sketch_marks WHERE item = ? LIMIT 1", (item,)).fetchone() is not None


def change(conn, item, tab, add=(), remove=(), title=None, pos=None, at=None):
    """Marks written or changed (add) and taken away (remove, by id) on one tab, in one go: the
    removals first, so a mark sent as both (an edit undone) ends as added. Returns (added, removed,
    {a picture's id: the name its file is kept under}, for one sent as a data: address)."""
    now = int(time.time())
    when = at if isinstance(at, int) and now - 30 * 86400 < at <= now + 60 else now
    ids = [str(i) for i in list(remove)[:2000] if MARK_ID.match(str(i))]
    removed = 0
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        removed += conn.execute(f"DELETE FROM sketch_marks WHERE item = ? AND tab = ? AND id IN ({','.join('?' * len(part))})",
                                (item, tab, *part)).rowcount
        # a block taken away takes its strokes (undo sends them again with it)
        conn.execute(f"DELETE FROM sketch_marks WHERE item = ? AND tab = ? AND kind = 'stroke' AND json_extract(data, '$.blk') IN ({','.join('?' * len(part))})",
                     (item, tab, *part))
    added, files = 0, {}
    for m in list(add)[:500]:
        mid, kind, d = _clean(m)
        if kind == "image" and m.get("src"):
            files[mid] = d["file"]
        old = conn.execute("SELECT created FROM sketch_marks WHERE id = ?", (mid,)).fetchone()
        conn.execute("INSERT OR REPLACE INTO sketch_marks (id, item, tab, kind, data, created, updated) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (mid, item, tab, kind, json.dumps(d, separators=(",", ":"), ensure_ascii=False), old["created"] if old else when, when))
        added += 1
    title = str(title)[:300] if title else None
    pos = _num(pos, 0, 1) if isinstance(pos, (int, float)) else None
    conn.execute("INSERT INTO sketch_tabs (item, tab, title, pos, updated) VALUES (?, ?, ?, ?, ?) "
                 "ON CONFLICT(item, tab) DO UPDATE SET title = COALESCE(excluded.title, title), pos = COALESCE(excluded.pos, pos), updated = excluded.updated",
                 (item, tab, title, pos, now))
    return added, removed, files


# ---- text, as it reads ---------------------------------------------------------------------------

def _stamp(t):
    t = int(t or 0)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def blocks(ms):
    """A page's blocks in order, each with its strokes (the strokes of a block that's gone are left out)."""
    out = sorted((dict(m) for m in ms if m["kind"] != "stroke"), key=lambda m: (m.get("ord", 0), m.get("updated", 0), m["id"]))
    by = {b["id"]: b for b in out}
    for b in out:
        b["strokes"] = []
    for m in ms:
        if m["kind"] == "stroke" and m.get("blk") in by:
            by[m["blk"]]["strokes"].append(m)
    return out


def plain(ms):
    """A page's words, for the Kindle (and anything else that only takes words): the typed text and
    the handwriting as read, in order; a drawing nobody could read is said to be there."""
    out, drawn = [], False
    for b in blocks(ms):
        line = ""
        if b["kind"] == "text":
            line = (b.get("text") or "").strip()
        elif b["kind"] == "ink":
            line = (b.get("transcript") or "").strip()
            drawn = drawn or (not line and bool(b["strokes"]))
        elif b["strokes"]:
            drawn = True
        if b.get("t") is not None and line:
            line = _stamp(b["t"]) + " " + line
        if line:
            out.append(line)
    if drawn:
        out.append(DRAWN)
    return "\n\n".join(out)


# ---- the Kindle -----------------------------------------------------------------------------------

def _h(text):
    return hashlib.sha1((text or "").encode()).hexdigest()[:16]


def for_kindle(conn, book_id):
    """A book's pages the Kindle doesn't have as they are now: [{id, chapter, fraction, text, hash}],
    and {id, remove: true} for one emptied since. The plugin makes each a bookmark at the chapter's
    start (General: the book's), with the text as its note, and says so (kindle_ack)."""
    item = "book:" + book_id
    out, have = [], {}
    for t in tabs(conn, item):
        text = plain(marks(conn, item, t["tab"]))
        if not text:
            continue
        tid = item + "|" + t["tab"]
        have[tid] = True
        h = _h(text)
        sent = conn.execute("SELECT hash FROM sketch_kindle WHERE id = ?", (tid,)).fetchone()
        if sent and sent["hash"] == h:
            continue
        out.append({"id": tid, "chapter": t["title"] if t["tab"] else None, "fraction": t["pos"] if t["tab"] else 0,
                    "label": KINDLE_MARK + " · " + (t["title"] or "General" if t["tab"] else "General"), "text": text, "hash": h})
    for r in conn.execute("SELECT id FROM sketch_kindle WHERE id LIKE ? ESCAPE '\\'", (_like(item) + "|%",)):
        if r["id"] not in have:
            out.append({"id": r["id"], "remove": True})
    return out


def _like(s):
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def kindle_ack(conn, items):
    n = 0
    for x in items or []:
        if not isinstance(x, dict) or not str(x.get("id") or "").startswith("book:"):
            continue
        if x.get("remove"):
            conn.execute("DELETE FROM sketch_kindle WHERE id = ?", (x["id"],))
        elif x.get("hash"):
            conn.execute("INSERT OR REPLACE INTO sketch_kindle (id, hash, at) VALUES (?, ?, ?)", (x["id"], str(x["hash"])[:40], int(time.time())))
        n += 1
    return n


def kindle_echo(conn, text, note):
    """Is this a bookmark the Kindle has from the Sketchbook (sent back with its notes file)? Then it
    isn't a highlight of its own (sources/highlights.py): by its text, or its note as Daf sent it."""
    if (text or "").startswith(KINDLE_MARK + " · "):
        return True
    return bool(note) and conn.execute("SELECT 1 FROM sketch_kindle WHERE hash = ? LIMIT 1", (_h(note.strip()),)).fetchone() is not None


# ---- the API ----------------------------------------------------------------------------------------

def router():
    """The routes, for app.py to include at its end (they use its conn, device, json_body and user)."""
    from .app import conn, device, json_body, user
    r = APIRouter(prefix="/api/sketchbook")

    @r.get("/img/{name}", dependencies=[Depends(user)])
    def get_image(name: str):
        """A picture on a page (cached for good: its name is its hash)."""
        if not re.fullmatch(r"[0-9a-f]{40}\.(jpg|png|webp)", name) or not (IMAGES / name).exists():
            raise HTTPException(404, "Not found")
        return FileResponse(IMAGES / name, headers={"Cache-Control": "private, max-age=31536000, immutable"})

    @r.post("/dictate", dependencies=[Depends(user)])
    async def dictate(request: Request):
        """What was said, as text: the recording (the request's body, as the browser made it) through
        faster-whisper on the server (media.whisper), in the language it hears."""
        data = await request.body()
        if not data:
            raise HTTPException(400, "Nothing was recorded")
        if len(data) > 40 * 1024 * 1024:
            raise HTTPException(413, "That's too long to write down in one go")
        ctype = request.headers.get("content-type", "")
        ext = ".mp4" if "mp4" in ctype or "aac" in ctype else ".ogg" if "ogg" in ctype else ".wav" if "wav" in ctype else ".mp3" if "mpeg" in ctype else ".webm"
        return await run_in_threadpool(_dictate, data, ext)

    @r.post("/kindle/ack")
    def kindle_ack_route(b=Depends(json_body), name=Depends(device), c=Depends(conn)):
        """The Kindle's plugin has these pages as bookmarks now (or took away the ones emptied)."""
        return {"ok": True, "acked": kindle_ack(c, b.get("items") if isinstance(b, dict) else None)}

    @r.get("/{item}", dependencies=[Depends(user)])
    def get_item(item: str, tab: str = "", c=Depends(conn)):
        """The item's tabs, and what's on one of them (General unless asked)."""
        if not item_ok(item) or not TAB.match(tab):
            raise HTTPException(400, "Bad item")
        from . import sketchvault
        sketchvault.pull_soon(c, config.load_settings(), item)        # text edited in Obsidian comes back first
        return {"item": item, "tab": tab, "ink_w": INK_W, "line": LINE, "tabs": [{k: t[k] for k in ("tab", "title", "pos", "n", "updated")} for t in tabs(c, item)],
                "marks": marks(c, item, tab), "vault": sketchvault.sketch_of(c, item)}

    @r.post("/{item}", dependencies=[Depends(user)])
    def post_item(item: str, b=Depends(json_body), c=Depends(conn)):
        """{tab, title?, pos?, add: [marks], remove: [ids]}: one tab's changes, in one go (web/sketchbook.js)."""
        if not item_ok(item) or not isinstance(b, dict) or not TAB.match(str(b.get("tab") or "")):
            raise HTTPException(400, "Bad item")
        try:
            added, removed, files = change(c, item, str(b.get("tab") or ""), b.get("add") or [], b.get("remove") or [],
                                           b.get("title"), b.get("pos"), b.get("at"))
        except (ValueError, TypeError) as e:
            raise HTTPException(400, str(e) or "Bad mark")
        from . import sketchvault
        sketchvault.later(item)
        return {"added": added, "removed": removed, "files": files}

    return r


def _dictate(data, ext):
    from . import media
    tmp = config.STATE / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    p = tmp / f"dictation-{hashlib.sha1(data).hexdigest()[:12]}{ext}"
    p.write_bytes(data)
    try:
        out = media.whisper(str(p))
    except Exception as e:  # noqa: BLE001 - said to the page
        raise HTTPException(502, f"It couldn't be written down: {e}")
    finally:
        p.unlink(missing_ok=True)
    text = " ".join(s["text"].strip() for s in out.get("segments") or [] if s.get("text", "").strip())
    return {"text": text, "language": out.get("language")}


def image_path(name):
    return IMAGES / name
