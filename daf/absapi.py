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


def progress():
    """Where you are in everything: {"<item>" or "<item>:<episode>": mediaProgress}. /api/me also
    carries the user's token, which is dropped here."""
    def fetch():
        me = get("/api/me")
        return {p["libraryItemId"] + (":" + p["episodeId"] if p.get("episodeId") else ""): {
            k: p.get(k) for k in ("currentTime", "duration", "progress", "isFinished", "lastUpdate", "hideFromContinueListening")}
            for p in me.get("mediaProgress") or [] if p.get("libraryItemId")}
    return _kept("progress", fetch, keep=30)


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
                        "narrator": md.get("narratorName") or "", "duration": med.get("duration") or 0,
                        "at": (p or {}).get("currentTime"), "pct": _pct(p, med.get("duration")), "done": bool(p and p.get("isFinished")),
                        "last": _ms((p or {}).get("lastUpdate")) or _ms(it.get("addedAt")), "added": _ms(it.get("addedAt")),
                        "book": bid, "readable": bid in readable, "chapters": med.get("numChapters") or 0})
    return out


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
