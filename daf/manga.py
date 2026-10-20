"""Manga, read in Daf, with Komga as the library.

Komga (port 25600, /srv/media/manga read-only) already scans the series, serves the pages and
keeps reading progress, and the Kindle (KOReader's kosync) and the hourly AniList bridge
(/srv/docker/manga-import/manga-track.py) both work through it. So Daf doesn't copy any of
that: it asks Komga for the series, volumes and pages, and writes progress back to it, so a
volume read in Daf is read on the Kindle and on AniList too.

- Accounts: Komga keeps progress per user. The Kindle reads as `kindle@tiresia.xyz`, and Kahon
  or the web UI may read as the admin. Daf reads both and takes the furthest, and writes as the
  Kindle's account, so the Kindle and Daf share one place. The keys are manga-track's
  (`komga.json`, mode 600), never copied anywhere.
- Pages are shrunk to the screen (WebP, in steps so the cache is shared) and kept on disk
  under STATE/manga-cache, the oldest dropped past CACHE_MAX.
- Minutes read here are sessions of source "manga", one per series per day.
"""
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from . import config
from . import today as T

CONF = Path(os.environ.get("DAF_KOMGA_CONF", "/srv/docker/manga-import/komga.json"))
ROOT = Path(os.environ.get("DAF_MANGA_ROOT", "/srv/media/manga"))       # what Komga has as /data/manga
SERIES_MAP = Path(os.environ.get("DAF_MANGA_SERIES_MAP", "/srv/docker/manga-import/series-map.json"))
WRITER = "kindle@tiresia.xyz"
CACHE = config.STATE / "cache" / "manga"           # rebuilt from Komga at will: borg-backup.sh skips */cache/*
CACHE_MAX = 3 * 1024 ** 3
SIZES = (400, 900, 1300, 1800, 2400)       # long side of a page as stored, in pixels (400: the thumbnail grid)
UA = "Daf (personal reading app)"


class MangaError(Exception):
    pass


def _conf():
    try:
        c = json.loads(CONF.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise MangaError(f"Komga isn't set up for Daf ({CONF}): {e}")
    accts = {a["label"]: a["apiKey"] for a in c.get("accounts") or [] if a.get("apiKey")}
    if not accts:
        raise MangaError("No Komga accounts in " + str(CONF))
    return c["url"].rstrip("/"), accts


def _req(path, who=None, method="GET", body=None, raw=False, timeout=30):
    base, accts = _conf()
    key = accts.get(who or WRITER) or next(iter(accts.values()))
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"X-API-Key": key, "User-Agent": UA, **({"Content-Type": "application/json"} if data else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = r.read()
            return (out, r.headers.get("Content-Type")) if raw else (json.loads(out) if out else None)
    except urllib.error.HTTPError as e:
        raise MangaError(f"Komga said {e.code} for {path.split('?')[0]}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise MangaError(f"Komga didn't answer: {e}") from e


def _all(path, who=None):
    out, page = [], 0
    sep = "&" if "?" in path else "?"
    while True:
        d = _req(f"{path}{sep}size=1000&page={page}", who)
        out += d.get("content") or []
        if d.get("last", True):
            return out
        page += 1


# ---- the library, with everyone's progress ----------------------------------------------

_lib = {"at": 0, "data": None}
_lib_lock = threading.Lock()


def _progress(b):
    p = b.get("readProgress") or {}
    return {"page": p.get("page") or 0, "completed": bool(p.get("completed")), "at": p.get("lastModified") or p.get("readDate")}


def library(force=False, max_age=60):
    """{series: {id: {...}}, books: {id: {...}}}: Komga's, with the furthest progress of any account."""
    with _lib_lock:
        if _lib["data"] and not force and time.time() - _lib["at"] < max_age:
            return _lib["data"]
        _, accts = _conf()
        series = {s["id"]: {"id": s["id"], "name": display(s["metadata"].get("title") or s["name"]), "folder": s["name"],
                            "count": s["booksCount"], "direction": s["metadata"].get("readingDirection") or "",
                            "status": s["metadata"].get("status"), "summary": s["metadata"].get("summary") or ""}
                  for s in _all("/api/v1/series")}
        books = {}
        for who in [WRITER] + [a for a in accts if a != WRITER]:
            if who not in accts:
                continue
            try:
                rows = _all("/api/v1/books", who)
            except MangaError:
                continue
            for b in rows:
                p = _progress(b)
                cur = books.get(b["id"])
                if cur is None:
                    books[b["id"]] = {"id": b["id"], "series": b["seriesId"], "name": b["metadata"].get("title") or b["name"],
                                      "file": b["name"], "number": b["metadata"].get("numberSort") or b.get("number") or 0,
                                      "pages": (b.get("media") or {}).get("pagesCount") or 0, "size": b.get("sizeBytes"),
                                      "ok": (b.get("media") or {}).get("status") == "READY", **p}
                elif (p["completed"], p["page"]) > (cur["completed"], cur["page"]):
                    cur.update(p)
                elif p["at"] and (not cur["at"] or p["at"] > cur["at"]) and (p["completed"], p["page"]) == (cur["completed"], cur["page"]):
                    cur["at"] = p["at"]
        _lib.update(at=time.time(), data={"series": series, "books": books})
        return _lib["data"]


def display(name):
    """'Naruto (2003-2015) (Digital) (AnHeroGold-Empire) (Edited)' -> 'Naruto': no release tags or years."""
    t = re.sub(r"\s*[\(\[][^)\]]*[\)\]]", "", name or "").strip(" -")
    return t or (name or "")


def _ts(iso):
    try:
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()) if iso else 0
    except ValueError:
        return 0


def _series_books(lib, sid):
    return sorted((b for b in lib["books"].values() if b["series"] == sid), key=lambda b: (float(b["number"] or 0), b["file"]))


def _summary(lib, s):
    """A series card: how far, and the volume to go on with."""
    bs = _series_books(lib, s["id"])
    done = sum(1 for b in bs if b["completed"])
    last = max((_ts(b["at"]) for b in bs if b["at"] and (b["page"] or b["completed"])), default=0)
    nxt = next((b for b in bs if not b["completed"] and b["page"]), None)                     # one under way
    if not nxt:
        after = max((i for i, b in enumerate(bs) if b["completed"]), default=-1)
        nxt = bs[after + 1] if after + 1 < len(bs) else None
    return {"id": s["id"], "name": s["name"], "count": len(bs), "read": done, "last": last, "status": s["status"],
            "next": {"id": nxt["id"], "name": nxt["name"], "page": nxt["page"], "pages": nxt["pages"]} if nxt else None,
            "cover": bs[0]["id"] if bs else None}


def shelf():
    lib = library()
    cards = [_summary(lib, s) for s in lib["series"].values()]
    going = sorted([c for c in cards if c["last"] and c["next"]], key=lambda c: -c["last"])
    return {"continue": going[:12], "series": sorted(cards, key=lambda c: c["name"].lower())}


def series(sid):
    lib = library()
    s = lib["series"].get(sid)
    if not s:
        raise KeyError(sid)
    return {**_summary(lib, s), "summary": s["summary"], "direction": s["direction"],
            "books": [{"id": b["id"], "name": b["name"], "pages": b["pages"], "page": b["page"], "completed": b["completed"],
                       "at": _ts(b["at"]), "ok": b["ok"]} for b in _series_books(lib, sid)]}


def book(bid):
    lib = library()
    b = lib["books"].get(bid)
    if not b:
        lib = library(force=True)
        b = lib["books"].get(bid)
        if not b:
            raise KeyError(bid)
    s = lib["series"].get(b["series"]) or {}
    bs = _series_books(lib, b["series"])
    i = next((k for k, x in enumerate(bs) if x["id"] == bid), 0)
    pages = _req(f"/api/v1/books/{bid}/pages")
    return {"id": bid, "name": b["name"], "series": {"id": b["series"], "name": s.get("name"), "direction": s.get("direction")},
            "page": b["page"], "completed": b["completed"],
            "pages": [{"w": p.get("width") or 0, "h": p.get("height") or 0} for p in pages],
            "prev": bs[i - 1]["id"] if i > 0 else None, "prev_name": bs[i - 1]["name"] if i > 0 else None,
            "next": bs[i + 1]["id"] if i + 1 < len(bs) else None,
            "next_name": bs[i + 1]["name"] if i + 1 < len(bs) else None}


def set_progress(bid, page, completed=False, at=None):
    """Progress to Komga as the Kindle's account: the Kindle opens where Daf left off, and
    manga-track takes a finished volume to AniList. `at` (epoch seconds) is when the page was
    read: progress saved offline and sent later loses to anything Komga heard since (the Kindle
    may have gone further meanwhile). Returns False when it was too old to send."""
    if at:
        try:
            cur = (_req(f"/api/v1/books/{bid}") or {}).get("readProgress") or {}
        except MangaError:
            cur = {}
        if cur and _ts(cur.get("lastModified")) > int(at):
            return False
    _req(f"/api/v1/books/{bid}/read-progress", method="PATCH", body={"page": max(1, int(page)), "completed": bool(completed)})
    lib = _lib["data"]
    if lib and bid in lib["books"]:
        b = lib["books"][bid]
        if (bool(completed), int(page)) >= (b["completed"], b["page"]) or not completed:
            b.update(page=int(page), completed=bool(completed) or b["completed"], at=datetime.utcnow().isoformat() + "Z")
    return True


# ---- pages, shrunk to the screen and kept -------------------------------------------------

def _bucket(want):
    for s in SIZES:
        if want <= s:
            return s
    return SIZES[-1]


def _crop_borders(im):
    """The page without its blank margins: the border colour is taken from the corners, and a
    margin goes only if what's left is still most of the page (a full-bleed page stays as it is)."""
    from PIL import ImageChops
    g = im.convert("L")
    w, h = g.size
    corners = sorted(g.getpixel(c) for c in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)))
    bg = corners[1] if corners[2] - corners[1] < 24 else None        # two or more corners agree
    if bg is None or 40 < bg < 215:                                  # only a white or a black margin
        return im
    mask = ImageChops.difference(g, g.point(lambda _: bg)).point(lambda v: 255 if v > 28 else 0)
    box = mask.getbbox()
    if not box:
        return im
    pad = max(4, round(min(w, h) * 0.01))
    box = (max(0, box[0] - pad), max(0, box[1] - pad), min(w, box[2] + pad), min(h, box[3] + pad))
    if (box[2] - box[0]) * (box[3] - box[1]) < 0.55 * w * h:
        return im
    return im.crop(box)


def page_image(bid, n, want=1800, crop=False):
    """(bytes, media type) of page n, its long side at most the size step above `want`, its blank
    margins trimmed when `crop`."""
    size = _bucket(int(want or 1800))
    p = CACHE / bid / f"{int(n)}-{size}{'-c' if crop else ''}.webp"
    if p.exists():
        os.utime(p)
        return p.read_bytes(), "image/webp"
    data, ctype = _req(f"/api/v1/books/{bid}/pages/{int(n)}", raw=True, timeout=60)
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:  # noqa: BLE001 - something Pillow can't read: hand it over as it is
        return data, ctype or "application/octet-stream"
    if crop:
        im = _crop_borders(im)
    if max(im.size) > size:
        k = size / max(im.size)
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    out = io.BytesIO()
    im.convert("RGB" if im.mode not in ("RGB", "L") else im.mode).save(out, "WEBP", quality=82, method=4)
    body = out.getvalue()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(body)
    tmp.replace(p)
    return body, "image/webp"


def thumb(kind, kid):
    """A series' or a volume's cover, as Komga makes it."""
    p = CACHE / "thumbs" / f"{kind}-{kid}.jpg"
    if p.exists() and time.time() - p.stat().st_mtime < 7 * 86400:
        return p.read_bytes(), "image/jpeg"
    data, ctype = _req(f"/api/v1/{'series' if kind == 's' else 'books'}/{kid}/thumbnail", raw=True)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return data, ctype or "image/jpeg"


def prune():
    """Keep the page cache under CACHE_MAX, the pages looked at longest ago going first."""
    if not CACHE.is_dir():
        return 0
    files = [(f.stat().st_mtime, f.stat().st_size, f) for f in CACHE.rglob("*.webp")]
    total, n = sum(s for _, s, _ in files), 0
    for _, s, f in sorted(files):
        if total <= CACHE_MAX:
            break
        f.unlink(missing_ok=True)
        total -= s
        n += 1
    return n


# ---- minutes -------------------------------------------------------------------------

def beat(conn, settings, bid, seconds, at=None):
    """Reading manga in Daf, in short beats: one session per series per day."""
    seconds = max(0, min(90, int(seconds)))
    lib = _lib["data"] or library()
    b = lib["books"].get(bid)
    if not seconds or not b:
        return
    s = lib["series"].get(b["series"]) or {}
    now = int(time.time())
    try:
        at = int(at) if at is not None else now
    except (TypeError, ValueError):
        at = now
    if not (now - 7 * 86400 <= at <= now + 60):
        at = now
    day = datetime.fromtimestamp(at, T.tz_of(settings)).date().isoformat()
    sid = f"manga:{b['series']}:{day}"
    # One statement, so two first beats at once can't both try to make the session.
    conn.execute("INSERT INTO sessions (id, source, origin, item, title, author, start, seconds, day, private, note) "
                 "VALUES (?, 'manga', 'daf-read', ?, ?, NULL, ?, ?, NULL, 0, ?) "
                 "ON CONFLICT(id) DO UPDATE SET seconds = seconds + excluded.seconds, note = excluded.note",
                 (sid, b["series"], s.get("name") or b["name"], T.beat_start(at, seconds, settings), seconds, b["name"]))


# ---- which of Daf's books are manga volumes ------------------------------------------------
# A volume read on the Kindle came from Komga, so its KOReader md5 is the md5 of a file in the
# manga library. Those books leave the Books page (they're on the Manga page, by series), and
# their Kindle time is titled by series. A file the Kindle got some other way is matched by its
# name instead.

FILES = (".cbz", ".cbr", ".cb7", ".zip", ".pdf", ".epub")
JUNK = re.compile(r"\s*[\(\[][^)\]]*[\)\]]|\.(cbz|cbr|cb7|zip|pdf|epub)$", re.I)


def _norm(t):
    return re.sub(r"[^a-z0-9]+", " ", JUNK.sub("", (t or "").lower())).strip()


def refresh_index():
    """Hash new or changed files (outside any transaction: the first run reads 1,000 files),
    then match Daf's books. Returns (files hashed, books matched)."""
    from . import db, kindlesend
    if not ROOT.is_dir():
        return 0, 0
    with db.session() as conn:
        known = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT path, size, mtime FROM manga_files")}
    found, fresh = set(), []
    for f in ROOT.rglob("*"):
        if f.suffix.lower() not in FILES or not f.is_file() or ".sync-conflict-" in f.name:
            continue
        rel = str(f.relative_to(ROOT))
        found.add(rel)
        st = f.stat()
        if known.get(rel) != (st.st_size, int(st.st_mtime)):
            try:
                fresh.append((rel, st.st_size, int(st.st_mtime), kindlesend.partial_md5(f)))
            except OSError:
                continue
    with db.session() as conn:
        conn.executemany("INSERT OR REPLACE INTO manga_files (path, size, mtime, md5) VALUES (?, ?, ?, ?)", fresh)
        gone = [p for p in known if p not in found]
        conn.executemany("DELETE FROM manga_files WHERE path = ?", [(p,) for p in gone])
        n = map_books(conn)
    return len(fresh), n


def map_books(conn):
    from . import goals
    try:
        lib = library()
    except MangaError:
        lib = {"series": {}, "books": {}}
    by_file = {}                                          # (series folder, file stem) -> (komga book, series)
    for b in lib["books"].values():
        s = lib["series"].get(b["series"]) or {}
        by_file[(s.get("folder") or "", b["file"])] = (b["id"], b["series"], s.get("name") or "")
    by_name = {_norm(stem): v for (_, stem), v in by_file.items()}
    by_vol, folders = {}, {}
    series_of = {s.get("folder") or "": (None, sid, s.get("name") or "") for sid, s in lib["series"].items()}
    for (folder, stem), v in by_file.items():
        n = re.search(r"\bv(\d{1,3})\b", stem, re.I)
        if n:
            by_vol[(folder, int(n.group(1)))] = v
        folders[_norm(folder)] = folder
    try:                                                  # the importer's own title -> folder overrides
        smap = json.loads(SERIES_MAP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        smap = {}
    files = {r[0]: r[1] for r in conn.execute("SELECT md5, path FROM manga_files")}
    rows = []
    for bid, title in conn.execute("SELECT id, title FROM books WHERE kind = 'book'").fetchall():
        md5s = [k[4:] for (k,) in conn.execute("SELECT key FROM book_keys WHERE book_id = ? AND key LIKE 'md5:%'", (bid,))]
        hit = None
        for m in md5s:
            if m in files:
                folder, _, name = files[m].partition("/")
                stem = name.rsplit(".", 1)[0]
                hit = by_file.get((folder, stem)) or (None, None, folder)
                break
        if not hit and re.search(r"\bv\d{1,3}\b", title or "", re.I) and goals.VOLUME.search(title or ""):
            hit = by_name.get(_norm(title)) or _by_series_and_volume(title, by_vol, folders, smap, series_of)
        if hit:
            rows.append((bid, hit[0], hit[1], hit[2]))
    conn.execute("DELETE FROM manga_books")
    conn.executemany("INSERT INTO manga_books (book_id, komga_book, series, series_name) VALUES (?, ?, ?, ?)", rows)
    return len(rows)


def _by_series_and_volume(title, by_vol, folders, smap, series_of):
    """'Kaoru Hana wa Rin to Saku v13' -> the folder its series is filed under (by name, or the
    importer's series-map.json), and volume 13 in it."""
    t = re.sub(r"^unknown author\s*-\s*", "", JUNK.sub("", title or ""), flags=re.I)
    m = re.match(r"^(.*?)\s*\bv(\d{1,3})\b", t, re.I)
    if not m:
        return None
    key = _norm(m.group(1))
    folder = smap.get(key) or folders.get(key)
    if not folder:
        return None
    # The volume itself may be gone from the library (some series are kept as chapters now): the series still holds.
    return by_vol.get((folder, int(m.group(2)))) or series_of.get(folder)


def is_manga(conn):
    return {r[0] for r in conn.execute("SELECT book_id FROM manga_books")}


# ---- the reader's settings, kept on morten so every device reads the same way -------------
# {"defaults": {...}, "series": {series id: {...}}}: how pages are laid out is kept per series
# (the reader decides which keys), everything else once.

def prefs(conn):
    r = conn.execute("SELECT v FROM kv WHERE k = 'manga_prefs'").fetchone()
    try:
        d = json.loads(r[0]) if r else {}
    except ValueError:
        d = {}
    return {"defaults": d.get("defaults") or {}, "series": d.get("series") or {}}


def set_prefs(conn, defaults=None, series=None):
    d = prefs(conn)
    if isinstance(defaults, dict):
        d["defaults"].update({k: v for k, v in defaults.items() if isinstance(k, str) and len(k) < 40})
    if isinstance(series, dict):
        for sid, v in series.items():
            if isinstance(v, dict) and re.fullmatch(r"[0-9A-Za-z]{6,40}", sid or ""):
                if v.get("_clear"):
                    d["series"].pop(sid, None)
                else:
                    d["series"].setdefault(sid, {}).update({k: x for k, x in v.items() if isinstance(k, str) and len(k) < 40})
    blob = json.dumps(d)
    if len(blob) > 200_000:
        raise MangaError("Too many reader settings")
    conn.execute("INSERT INTO kv (k, v) VALUES ('manga_prefs', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (blob,))
    return d
