"""Audiobookshelf in Daf’s player: its audiobooks, and its podcast libraries (recordings added by hand,
not RSS shows, so they stay a category of their own beside AntennaPod's).

sources/audiobookshelf.py reads ABS's database for listening time; this talks to ABS's API the way
its own apps do:
- reading: the libraries, an item with its audio files and chapters, and where you are in each
  (/api/me's mediaProgress). Kept a few minutes, so the Podcasts tab doesn't ask on every draw.
- the audio and the covers, through Daf: a file from the disk where ABS's folders are mounted here
  (media.ABS_MOUNTS), else from ABS with the key. The key never reaches the browser, and Range
  requests pass, so it seeks.
- where you are, back to ABS (played): a playback session, opened as ABS's apps open one (POST
  /api/items/<id>/play[/<episode>]) and synced as you listen (/api/session/<id>/sync, then close).
  ABS keeps your place and its listening time; Daf reads that time back as sessions, so it isn't
  counted twice (audiobooks count toward the hour, the podcast libraries are private and don't).

Every write goes through write(), which the sandbox stands in for.
"""
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import config, secrets

log = logging.getLogger("daf.abs")
DEVICE = {"clientName": "Daf", "clientVersion": "1.0", "deviceId": "daf", "manufacturer": "Daf", "model": "Daf"}
KEEP = 300                       # seconds a library or an item is kept before asking ABS again
_memo, _lock = {}, threading.Lock()


class Unavailable(RuntimeError):
    """ABS didn't answer, or there's no key."""


def _request(method, path, body=None, timeout=20, headers=None):
    key = secrets.abs_key()
    if not key:
        raise Unavailable("No Audiobookshelf key (AUDIOBOOKSHELF_API_KEY)")
    h = {"Authorization": "Bearer " + key, "Accept": "application/json", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    return urllib.request.urlopen(urllib.request.Request(config.ABS_URL + path, data=data, method=method, headers=h), timeout=timeout)


def get(path, timeout=20):
    try:
        with _request("GET", path, timeout=timeout) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError:
        raise
    except OSError as e:
        raise Unavailable(f"Audiobookshelf didn't answer: {e}") from e


def write(method, path, body=None):
    """Everything Daf tells ABS (sessions and where you are) goes through here."""
    with _request(method, path, body, timeout=20) as r:
        raw = r.read()
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def stream(path, headers=None):
    """A file or a cover from ABS, for Daf to pass on (app.py)."""
    return _request("GET", path, timeout=30, headers=headers)


def _kept(key, fetch, keep=KEEP):
    with _lock:
        hit = _memo.get(key)
    if hit and time.time() - hit[0] < keep:
        return hit[1]
    val = fetch()
    with _lock:
        _memo[key] = (time.time(), val)
    return val


def forget(*keys):
    with _lock:
        for k in keys or list(_memo):
            _memo.pop(k, None)


# ---- reading ---------------------------------------------------------------------------

def libraries():
    return _kept("libs", lambda: [{"id": l["id"], "name": l.get("name") or "", "kind": l.get("mediaType")}
                                   for l in get("/api/libraries").get("libraries", [])])


def items(lib_id):
    """A library's items, minified (their files and episodes come with item())."""
    return _kept("items:" + lib_id, lambda: get(f"/api/libraries/{lib_id}/items?minified=1&limit=1000").get("results", []))


def item(item_id):
    """One item, expanded: its audio files, chapters, and a podcast's episodes."""
    return _kept("item:" + item_id, lambda: get(f"/api/items/{urllib.parse.quote(item_id)}?expanded=1"))


def _me():
    """/api/me, without the user's token (which it also carries): where you are in everything, and your bookmarks."""
    def fetch():
        me = get("/api/me")
        return {"progress": {p["libraryItemId"] + (":" + p["episodeId"] if p.get("episodeId") else ""): {
                    k: p.get(k) for k in ("currentTime", "duration", "progress", "isFinished", "lastUpdate", "hideFromContinueListening")}
                    for p in me.get("mediaProgress") or [] if p.get("libraryItemId")},
                "bookmarks": [{k: b.get(k) for k in ("libraryItemId", "time", "title", "createdAt")} for b in me.get("bookmarks") or []]}
    return _kept("progress", fetch, keep=30)


def progress():
    """Where you are in everything: {"<item>" or "<item>:<episode>": mediaProgress}."""
    return _me()["progress"]


def where(item_id, episode=None):
    return progress().get(item_id + (":" + episode if episode else ""))


def _ms(v):
    return int(v / 1000) if v else None


def _pct(p, dur):
    if not p:
        return None
    if p.get("isFinished"):
        return 100.0
    d = p.get("duration") or dur
    return round(100 * (p.get("currentTime") or 0) / d, 1) if d else None


# ---- the lists the Podcasts tab shows ----------------------------------------------------

def audiobooks(conn):
    """Every audiobook, with where you are and the Daf book it's matched to (library.py's book_keys)."""
    books = {r[0][4:]: r[1] for r in conn.execute("SELECT key, book_id FROM book_keys WHERE key LIKE 'abs:%'")}
    from . import ebooks
    readable = ebooks.readable_ids(conn)
    out = []
    for lib in libraries():
        if lib["kind"] != "book":
            continue
        for it in items(lib["id"]):
            md, med = (it.get("media") or {}).get("metadata") or {}, it.get("media") or {}
            if not med.get("numAudioFiles") and not med.get("duration"):
                continue                                   # an ebook alone: nothing to hear
            p = where(it["id"])
            bid = books.get(it["id"])
            out.append({"item": it["id"], "title": md.get("title") or "", "author": md.get("authorName") or "",
                        "narrator": md.get("narratorName") or "", "duration": med.get("duration") or 0, "library": lib["id"],
                        "series": series_of(md.get("seriesName")), "authors": _names(md.get("authorName")), "narrators": _names(md.get("narratorName")),
                        "at": (p or {}).get("currentTime"), "pct": _pct(p, med.get("duration")), "done": bool(p and p.get("isFinished")),
                        "last": _ms((p or {}).get("lastUpdate")) or _ms(it.get("addedAt")), "added": _ms(it.get("addedAt")),
                        "book": bid, "readable": bid in readable, "chapters": med.get("numChapters") or 0})
    return out


def _names(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def series_of(s):
    """ABS's minified seriesName ("Asian Saga #1, Another #2") as [{name, seq}]."""
    out = []
    for part in (s or "").split(", "):
        name, _, seq = part.strip().rpartition(" #")
        if not name:
            name, seq = part.strip(), ""
        if name:
            out.append({"name": name, "seq": seq})
    return out


def collections():
    """Your collections in the audiobook libraries: [{id, library, name, books: [item, ...]}]."""
    def fetch():
        out = []
        for lib in libraries():
            if lib["kind"] != "book":
                continue
            for c in get(f"/api/libraries/{lib['id']}/collections?limit=1000").get("results") or []:
                out.append({"id": c["id"], "library": lib["id"], "name": c.get("name") or "",
                            "books": [b.get("id") for b in c.get("books") or [] if b.get("id")]})
        return out
    return _kept("collections", fetch)


def recordings():
    """The podcast libraries, each its own category: [{id, name, shows: [...]}]."""
    out = []
    prog = progress()
    for lib in libraries():
        if lib["kind"] != "podcast":
            continue
        shows = []
        for it in items(lib["id"]):
            md, med = (it.get("media") or {}).get("metadata") or {}, it.get("media") or {}
            mine = [v for k, v in prog.items() if k.startswith(it["id"] + ":")]
            shows.append({"item": it["id"], "title": md.get("title") or "", "author": md.get("author") or "",
                          "count": med.get("numEpisodes") or 0, "played": sum(1 for p in mine if p.get("isFinished")),
                          "started": sum(1 for p in mine if not p.get("isFinished") and (p.get("currentTime") or 0) > 0),
                          "last": max([_ms(p.get("lastUpdate")) or 0 for p in mine] or [0]) or None, "added": _ms(it.get("addedAt")),
                          "genres": md.get("genres") or [], "description": md.get("description") or ""})
        out.append({"id": lib["id"], "name": lib["name"], "shows": shows})
    return out


def going(limit=12):
    """What you've started in ABS and not finished, the last played first: recordings and audiobooks."""
    out = []
    kinds = {lib["id"]: lib["kind"] for lib in libraries()}
    for key, p in sorted(progress().items(), key=lambda kv: -(kv[1].get("lastUpdate") or 0)):
        if p.get("isFinished") or p.get("hideFromContinueListening") or (p.get("currentTime") or 0) < 15:
            continue
        item_id, _, ep = key.partition(":")
        try:
            it = item(item_id)
        except Exception:  # noqa: BLE001 - an item since removed from ABS
            continue
        med = it.get("media") or {}
        md = med.get("metadata") or {}
        if ep:
            e = next((x for x in med.get("episodes") or [] if x["id"] == ep), None)
            if not e:
                continue
            out.append({"kind": "recording", "item": item_id, "id": ep, "title": e.get("title") or "", "show": md.get("title") or "",
                        "duration": e.get("duration") or p.get("duration") or 0, "at": p.get("currentTime"), "last": _ms(p.get("lastUpdate")),
                        "published": _published(e)})
        elif kinds.get(it.get("libraryId")) == "book":
            out.append({"kind": "audiobook", "item": item_id, "title": md.get("title") or "", "show": md.get("authorName") or "",
                        "duration": med.get("duration") or p.get("duration") or 0, "at": p.get("currentTime"), "last": _ms(p.get("lastUpdate"))})
        if len(out) >= limit:
            break
    return out


def search(q):
    """ABS's own search in every library: audiobooks, recordings (a podcast library's items) and their
    episodes whose title, author or tag has the words."""
    out = {"audiobooks": [], "recordings": [], "episodes": []}
    if len(q) < 2:
        return out
    prog = progress()
    for lib in libraries():
        r = get(f"/api/libraries/{lib['id']}/search?q={urllib.parse.quote(q)}&limit=12")
        for x in r.get("book") or []:
            it = x.get("libraryItem") or {}
            md, med = (it.get("media") or {}).get("metadata") or {}, it.get("media") or {}
            if med.get("audioFiles") or med.get("duration"):
                p = prog.get(it["id"])
                out["audiobooks"].append({"item": it["id"], "title": md.get("title") or "", "author": md.get("authorName") or "",
                                          "duration": med.get("duration") or 0, "pct": _pct(p, med.get("duration")), "done": bool(p and p.get("isFinished"))})
        for x in r.get("podcast") or []:
            it = x.get("libraryItem") or {}
            md = (it.get("media") or {}).get("metadata") or {}
            out["recordings"].append({"item": it["id"], "title": md.get("title") or "", "author": md.get("author") or "",
                                      "count": (it.get("media") or {}).get("numEpisodes") or len((it.get("media") or {}).get("episodes") or [])})
        for x in r.get("episodes") or []:
            it = x.get("libraryItem") or {}
            e = it.get("recentEpisode") or {}
            if not e.get("id"):
                continue
            p = prog.get(it["id"] + ":" + e["id"])
            md = (it.get("media") or {}).get("metadata") or {}
            out["episodes"].append({"item": it["id"], "id": e["id"], "title": e.get("title") or "", "show": md.get("title") or "",
                                    "published": _published(e), "duration": e.get("duration") or (e.get("audioFile") or {}).get("duration") or 0,
                                    "at": (p or {}).get("currentTime"), "done": bool(p and p.get("isFinished"))})
    return out


def _published(e):
    try:
        return int(e["publishedAt"] / 1000) if e.get("publishedAt") else None
    except (TypeError, ValueError):
        return None


def show(item_id):
    """A recording's item (a "show") and its episodes, with where you are in each."""
    it = item(item_id)
    md, med = (it.get("media") or {}).get("metadata") or {}, it.get("media") or {}
    eps = []
    for e in med.get("episodes") or []:
        p = where(item_id, e["id"])
        dur = e.get("duration") or ((e.get("audioFile") or {}).get("duration")) or 0
        eps.append({"id": e["id"], "title": e.get("title") or "", "published": _published(e), "added": _ms(e.get("addedAt")),
                    "duration": dur, "at": (p or {}).get("currentTime"), "done": bool(p and p.get("isFinished")),
                    "last": _ms((p or {}).get("lastUpdate")), "description": _plain(e.get("description") or e.get("subtitle") or "")[:600],
                    "number": e.get("episode") or "", "season": e.get("season") or ""})
    return {"item": item_id, "library": it.get("libraryId"), "title": md.get("title") or "", "author": md.get("author") or "",
            "description": _plain(md.get("description") or ""), "genres": md.get("genres") or [], "episodes": eps}


def _plain(s):
    import html
    import re
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


# ---- one item, the way the player takes it -----------------------------------------------

def playable(item_id, episode=None):
    """What the player needs: the files as one track (each through Daf), chapters, and where you were."""
    it = item(item_id)
    med = it.get("media") or {}
    md = med.get("metadata") or {}
    q = urllib.parse.quote
    if episode:
        e = next((x for x in med.get("episodes") or [] if x["id"] == episode), None)
        if not e:
            raise KeyError(episode)
        af = e.get("audioFile") or {}
        dur = e.get("duration") or af.get("duration") or 0
        tracks = [{"url": f"/api/abs/audio/{q(item_id)}/{q(str(af.get('ino')))}", "start": 0, "dur": dur}]
        chapters = [{"t": float(c.get("start") or 0), "title": c.get("title") or ""} for c in e.get("chapters") or []]
        title, sub = e.get("title") or "", md.get("title") or ""
    else:
        files = sorted([f for f in med.get("audioFiles") or [] if not f.get("exclude")], key=lambda f: f.get("index") or 0)
        tracks, t = [], 0.0
        for f in files:
            tracks.append({"url": f"/api/abs/audio/{q(item_id)}/{q(str(f['ino']))}", "start": round(t, 3), "dur": f.get("duration") or 0})
            t += f.get("duration") or 0
        dur = med.get("duration") or t
        chapters = [{"t": float(c.get("start") or 0), "title": c.get("title") or ""} for c in med.get("chapters") or []]
        title, sub = md.get("title") or "", md.get("authorName") or ""
    p = where(item_id, episode)
    at = (p or {}).get("currentTime") or 0
    if p and p.get("isFinished"):
        at = 0
    return {"item": item_id, "episode": episode, "kind": "recording" if episode else "audiobook", "title": title, "sub": sub,
            "art": f"/api/abs/cover/{q(item_id)}", "tracks": tracks, "duration": dur, "chapters": [c for c in chapters if c["title"]],
            "at": at, "done": bool(p and p.get("isFinished")), "last": _ms((p or {}).get("lastUpdate"))}


def audio_file(item_id, ino):
    """(path on this disk or None, ABS's path for it, its type) for one of an item's audio files."""
    from .media import ABS_MOUNTS
    it = item(item_id)
    med = it.get("media") or {}
    files = list(med.get("audioFiles") or []) + [e.get("audioFile") or {} for e in med.get("episodes") or []]
    f = next((f for f in files if str(f.get("ino")) == str(ino)), None)
    if not f:
        raise KeyError(ino)
    path = (f.get("metadata") or {}).get("path") or ""
    local = None
    for k, v in ABS_MOUNTS.items():
        if path.startswith(k + "/"):
            p = Path(v + path[len(k):])
            if p.is_file():
                local = p
    return local, f"/api/items/{urllib.parse.quote(item_id)}/file/{urllib.parse.quote(str(ino))}", f.get("mimeType") or "audio/mpeg"


def file_at(item_id, t):
    """The audio file a book's time t falls in, on this disk, and the time within it (for whisper)."""
    from .media import ABS_MOUNTS
    med = item(item_id).get("media") or {}
    files = sorted([f for f in med.get("audioFiles") or [] if not f.get("exclude")], key=lambda f: f.get("index") or 0)
    off = 0.0
    for f in files:
        dur = float(f.get("duration") or 0)
        if off + dur > t or f is files[-1]:
            path = (f.get("metadata") or {}).get("path") or ""
            for k, v in ABS_MOUNTS.items():
                if path.startswith(k + "/"):
                    path = v + path[len(k):]
            return path, max(0.0, t - off), dur
        off += dur
    raise KeyError(t)


def for_book(conn, book_id):
    """The audiobook matched to a Daf book (library.py: book_keys "abs:<item>"), or None."""
    r = conn.execute("SELECT key FROM book_keys WHERE book_id = ? AND key LIKE 'abs:%' ORDER BY key LIMIT 1", (book_id,)).fetchone()
    return r[0][4:] if r else None


# ---- where you are, back to ABS ----------------------------------------------------------

_open = {}                        # (item, episode) → the ABS playback session Daf has open for it


def played(item_id, episode, at, listened, duration, end=False):
    """A stretch heard in Daf: ABS's session for it is synced (and closed at the end), so ABS has your
    place and its listening time. ABS closes a device's other sessions when one opens, and forgets
    them all when it restarts: a session it no longer knows is opened again."""
    key = (item_id, episode or "")
    body = {"currentTime": round(max(0.0, float(at)), 2), "timeListened": round(max(0.0, min(float(listened or 0), 3600.0)), 2),
            "duration": float(duration or 0) or None}
    for _ in range(2):
        sid = _open.get(key)
        if not sid:
            s = write("POST", f"/api/items/{urllib.parse.quote(item_id)}/play" + (f"/{urllib.parse.quote(episode)}" if episode else ""),
                      {"deviceInfo": DEVICE, "forceDirectPlay": True, "mediaPlayer": "html5",
                       "supportedMimeTypes": ["audio/mpeg", "audio/mp4", "audio/aac", "audio/ogg", "audio/flac", "audio/wav"]})
            sid = s.get("id")
            if not sid:
                raise Unavailable("Audiobookshelf didn't open a session")
            _open.clear()                     # ABS has just closed this device's others
            _open[key] = sid
        try:
            write("POST", f"/api/session/{sid}/" + ("close" if end else "sync"), body)
            break
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            _open.pop(key, None)              # ABS restarted, or another session took its place
    if end:
        _open.pop(key, None)
    forget("progress")


# ---- an audiobook's page: what ABS knows of it, and what you keep there --------------------

def book_page(conn, item_id):
    """An audiobook's page: its details, chapters, your bookmarks in it, its files, the collections it's
    in (and the others there are), and how long you listened to it on each of the last seven days."""
    it = item(item_id)
    med = it.get("media") or {}
    md = med.get("metadata") or {}
    if it.get("mediaType") not in (None, "book"):
        raise KeyError(item_id)
    p = where(item_id)
    chs = med.get("chapters") or []
    marks = book_page_marks(item_id)
    files = [{"ino": f.get("ino"), "name": (f.get("metadata") or {}).get("filename") or "", "size": (f.get("metadata") or {}).get("size") or 0,
              "kind": f.get("fileType") or ""} for f in it.get("libraryFiles") or []]
    cols = [{"id": c["id"], "name": c["name"], "on": item_id in c["books"]} for c in collections() if c["library"] == it.get("libraryId")]
    bid = for_book(conn, item_id)
    from . import ebooks
    return {"item": item_id, "library": it.get("libraryId"), "title": md.get("title") or "", "subtitle": md.get("subtitle") or "",
            "authors": [a.get("name") for a in md.get("authors") or [] if a.get("name")] or _names(md.get("authorName")),
            "narrators": md.get("narrators") or _names(md.get("narratorName")),
            "series": [{"name": x.get("name") or "", "seq": x.get("sequence") or ""} for x in md.get("series") or []] or series_of(md.get("seriesName")),
            "genres": md.get("genres") or [], "year": md.get("publishedYear") or "", "publisher": md.get("publisher") or "",
            "isbn": md.get("isbn") or "", "asin": md.get("asin") or "", "language": md.get("language") or "",
            "description": _plain(md.get("description") or ""), "duration": med.get("duration") or 0, "size": it.get("size") or 0,
            "chapters": [{"t": float(c.get("start") or 0), "end": float(c.get("end") or 0), "title": c.get("title") or ""} for c in chs],
            "at": (p or {}).get("currentTime") or 0, "done": bool(p and p.get("isFinished")), "pct": _pct(p, med.get("duration")),
            "bookmarks": marks, "files": files, "collections": cols, "week": week(item_id),
            "book": bid, "readable": bool(bid and bid in ebooks.readable_ids(conn))}


def book_page_marks(item_id):
    return sorted([{"t": b.get("time") or 0, "title": b.get("title") or "", "created": _ms(b.get("createdAt"))}
                   for b in _me()["bookmarks"] if b.get("libraryItemId") == item_id], key=lambda b: b["t"])


def week(item_id, days=7):
    """[{day: "YYYY-MM-DD", secs}] for the last `days` days, today last: ABS's listening sessions for the item."""
    from datetime import date, timedelta
    today = date.today()
    out = {(today - timedelta(days=i)).isoformat(): 0 for i in range(days - 1, -1, -1)}
    try:
        r = get(f"/api/me/item/listening-sessions/{urllib.parse.quote(item_id)}?itemsPerPage=200&page=0")
    except Exception:  # noqa: BLE001 - an older ABS without it: an empty week
        return [{"day": d, "secs": 0} for d in out]
    for x in r.get("sessions") or []:
        d = x.get("date") or ""
        if d in out:
            out[d] += int(x.get("timeListening") or 0)
    return [{"day": d, "secs": v} for d, v in out.items()]


# ---- what you keep in ABS: bookmarks, collections, finished, details found ----------------
# Each is one call to ABS's own API (write()), the one its apps make; what's kept here is forgotten after.

def bookmark_add(item_id, t, title):
    write("POST", f"/api/me/item/{urllib.parse.quote(item_id)}/bookmark", {"time": int(max(0, t)), "title": title or ""})
    forget("progress")


def bookmark_edit(item_id, t, title):
    write("PATCH", f"/api/me/item/{urllib.parse.quote(item_id)}/bookmark", {"time": int(t), "title": title or ""})
    forget("progress")


def bookmark_drop(item_id, t):
    write("DELETE", f"/api/me/item/{urllib.parse.quote(item_id)}/bookmark/{int(t)}")
    forget("progress")


def collection_set(item_id, coll_id, on):
    q = urllib.parse.quote
    if on:
        write("POST", f"/api/collections/{q(coll_id)}/book", {"id": item_id})
    else:
        write("DELETE", f"/api/collections/{q(coll_id)}/book/{q(item_id)}")
    forget("collections")


def collection_new(item_id, name):
    lib = item(item_id).get("libraryId")
    c = write("POST", "/api/collections", {"libraryId": lib, "name": name, "books": [item_id]})
    forget("collections")
    return {"id": c.get("id"), "name": c.get("name") or name}


def finished(item_id, on):
    write("PATCH", f"/api/me/progress/{urllib.parse.quote(item_id)}", {"isFinished": bool(on)})
    forget("progress")


BOOK_PROVIDERS = [{"value": "audible", "text": "Audible.com"}, {"value": "google", "text": "Google Books"},
                  {"value": "openlibrary", "text": "Open Library"}, {"value": "itunes", "text": "iTunes"}]


def providers():
    """Where ABS can find a book's details (its own match providers)."""
    def fetch():
        try:
            return get("/api/search/providers").get("providers", {}).get("books") or BOOK_PROVIDERS
        except urllib.error.HTTPError:
            return BOOK_PROVIDERS                    # an ABS older than the list: the usual ones
    return _kept("providers", fetch, keep=86400)


def find_details(item_id, provider, title=None, author=None):
    """Candidates for an audiobook's details from one of ABS's providers, as ABS's Match finds them."""
    md = ((item(item_id).get("media") or {}).get("metadata") or {})
    q = urllib.parse.urlencode({"title": title or md.get("title") or "", "author": author if author is not None else md.get("authorName") or "",
                                "provider": provider, "id": item_id})
    res = get("/api/search/books?" + q, timeout=40) or []
    out = []
    for x in res if isinstance(res, list) else []:
        if not isinstance(x, dict) or x.get("errorCode") or x.get("errorMsg") or not x.get("title"):
            continue                                 # a provider's own error, given as a result (Open Library does)
        ser = x.get("series") or []
        out.append({"title": x.get("title") or "", "subtitle": x.get("subtitle") or "", "author": x.get("author") or "",
                    "narrator": x.get("narrator") or "", "publisher": x.get("publisher") or "", "year": str(x.get("publishedYear") or ""),
                    "description": _plain(x.get("description") or "")[:2000], "cover": x.get("cover") or "", "isbn": x.get("isbn") or "",
                    "asin": x.get("asin") or "", "genres": [g for g in x.get("genres") or [] if isinstance(g, str)],
                    "series": [{"name": s.get("series") or "", "seq": str(s.get("sequence") or "")} for s in ser if isinstance(s, dict) and s.get("series")],
                    "language": x.get("language") or "", "duration": x.get("duration") or 0})
    return out[:12]


def use_details(item_id, c):
    """Use: a candidate's details (the ones it has) become the audiobook's in ABS, its cover too."""
    q = urllib.parse.quote
    md = {}
    for k, v in (("title", c.get("title")), ("subtitle", c.get("subtitle")), ("publisher", c.get("publisher")),
                 ("publishedYear", c.get("year")), ("description", c.get("description")), ("isbn", c.get("isbn")),
                 ("asin", c.get("asin")), ("language", c.get("language"))):
        if isinstance(v, str) and v.strip():
            md[k] = v.strip()
    if c.get("author"):
        md["authors"] = [{"name": n} for n in _names(c["author"])]
    if c.get("narrator"):
        md["narrators"] = _names(c["narrator"])
    if c.get("genres"):
        md["genres"] = [g for g in c["genres"] if isinstance(g, str)]
    if c.get("series"):
        md["series"] = [{"name": s["name"], "sequence": s.get("seq") or None} for s in c["series"] if s.get("name")]
    if not md:
        raise ValueError("Nothing to use")
    write("PATCH", f"/api/items/{q(item_id)}/media", {"metadata": md})
    if isinstance(c.get("cover"), str) and c["cover"].startswith("http"):
        try:
            write("POST", f"/api/items/{q(item_id)}/cover", {"url": c["cover"]})
        except urllib.error.HTTPError as e:            # the details are in; a cover that won't come isn't worth failing for
            log.info("cover for %s: %s", item_id, e)
    lib = item(item_id).get("libraryId") or ""
    forget("item:" + item_id, "items:" + lib)
    return sorted(md)
