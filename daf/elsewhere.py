"""What you read, watch and listen to outside Daf's Feed, for the Edition's taste (edition.taste).

- Books you read on the Kindle and in Daf's reader, by the hours in them, with Calibre's tags and
  description; audiobooks from Audiobookshelf, with its genres, tags and description; and your
  Hardcover shelves (reading, read and its rating, want to read), from Daf's copy (hardcover.fetch).
- Manga from Daf's manga reader and volumes read on the Kindle, one series at a time, with Komga's
  genres, tags and summary, or AniList's when Komga has none (the series' AniList id from manga-track's
  map, DAF_MANGA_TRACK_MAP; looked up once and kept in kv).
- Films and shows you watched on Jellyfin (a show once, however many episodes), with the genres, tags
  and overview of the film or the show (not each episode's plot), and what you asked Seerr for, with
  its genres, keywords and overview.

A title alone says little about which articles you'd want, so each thing comes with what it's about.
Fiction on a screen counts lightly, and by its genres and keywords only (a thriller's plot is all police
and agents, which are news words): a documentary or a lecture says more about what you'd read. Each source is optional: one that isn't there or fails is left out (and logged), and
the rest still count. A private book (Daf's private flag, a private session, a private Hardcover entry)
and any title library.is_private matches never go in. Jellyfin and Seerr are asked at most every
CACHE seconds, since the Taste page asks for the taste each time it opens.

Keys are read where they already live (secrets.env()): DAF_JELLYFIN_URL/JELLYFIN_URL,
DAF_JELLYFIN_KEY/JELLYFIN_API_KEY, DAF_JELLYFIN_USER/JELLYFIN_USER (your account, and the Seerr
accounts that are yours), DAF_SEERR_URL, DAF_SEERR_KEY/SEERR_API_KEY.
"""
import html
import json
import logging
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime

from . import config, secrets
from .db import read_only

log = logging.getLogger("daf.elsewhere")

DAYS = 180                  # how far back sessions, plays and requests are read (the taste's half-life fades them too)
CACHE = 3 * 3600            # Jellyfin and Seerr at most this often (a failure is asked again after RETRY)
RETRY = 600
PEEK = 600                  # seconds in a book: less is a look, not reading
SEERR_LOOKUPS = 40          # requests looked up for what they're about, newest first, per refresh
TIMEOUT = 10
LATELY_DAYS = 45            # what counts as "lately" for the model and the why lines
SKIP_LIBRARIES = {"music", "musicvideos", "playlists", "books", "photos", "livetv", "boxsets"}

# what the thing is to you, in a why line ("Goes with Middlemarch, which you're reading")
VERBS = {"reading": "which you're reading", "read": "which you read", "listening to": "which you're listening to",
         "listened to": "which you listened to",
         "watching": "which you're watching", "watched": "which you watched", "asked for": "which you asked for"}

_lock = threading.Lock()
_remote = {"at": 0.0, "data": None}
_about = {}                 # ("movie" | "tv", tmdb id) -> (title, text, fiction): what a request is about doesn't change


def clean(text, most=500):
    """Text from HTML (a Calibre description), on one line, at most `most` characters."""
    t = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", t).strip()[:most]


def norm(title):
    """A title to match on: lower case, letters and digits, without a subtitle or a bracket."""
    t = re.sub(r"[\(\[][^)\]]*[\)\]]", " ", (title or "").lower()).split(":")[0]
    return re.sub(r"[^\w]+", " ", t).strip()


def key(title):
    """One name per work, so "Some Series 01 - The Title" and "The Title" are the same book."""
    return norm(short_title(title))


def short_title(title):
    """A title as a why line names it: "Some Series 01 - The Title" -> "The Title", no "(Unabridged)",
    no subtitle, at most 40 characters."""
    t = re.sub(r"\s*[\(\[][^)\]]*[\)\]]", "", title or "").strip()
    m = re.match(r"^.+?\s\d+(\.\d+)?\s+-\s+(.+)$", t)
    if m:
        t = m.group(2)
    t = t.split(": ")[0].strip()
    return (t if len(t) <= 40 else t[:39].rsplit(" ", 1)[0] + "…") or (title or "")[:40]


def _ts(iso):
    if not iso:
        return 0
    try:
        return int(datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


def _hours(secs, base=0.4, per=0.3):
    """Weight by time spent: a book you spent five hours in counts most, a short sitting least."""
    return round(base + per * min(5.0, (secs or 0) / 3600), 3)


def _private(title, settings):
    from . import library
    return library.is_private(title, settings)


def _chunks(seq, n=400):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _join(*parts):
    return " ".join(p for p in parts if p)


# ---- books -----------------------------------------------------------------------------------------

def _calibre(ids):
    """{calibre id: (tags, description)} for these books."""
    out = {}
    ids = [i for i in set(ids) if i]
    db = config.CALIBRE_DBS[0]
    if not ids or not db.exists():
        return out
    c = read_only(db)
    try:
        for chunk in _chunks(ids):
            for bid, tags, desc in c.execute(
                    "SELECT b.id, (SELECT group_concat(t.name, ', ') FROM books_tags_link l JOIN tags t ON t.id = l.tag WHERE l.book = b.id), "
                    f"(SELECT text FROM comments WHERE book = b.id) FROM books b WHERE b.id IN ({','.join('?' * len(chunk))})", chunk):
                out[bid] = (tags or "", clean(desc))
    finally:
        c.close()
    return out


def _calibre_titles():
    db = config.CALIBRE_DBS[0]
    if not db.exists():
        return {}
    c = read_only(db)
    try:
        return {norm(t): i for i, t in c.execute("SELECT id, title FROM books")}
    finally:
        c.close()


def books(conn, now, settings):
    """Books read on the Kindle or in Daf's reader in the last DAYS days, one thing per book."""
    since = now - DAYS * 86400
    manga = {r[0][4:] for r in conn.execute("SELECT book_id FROM manga_books WHERE book_id LIKE 'md5:%'")}
    rows = [r for r in conn.execute(
        "SELECT source, item, title, author, seconds, start, private FROM sessions "
        "WHERE source IN ('kindle', 'ebook') AND start > ? AND item IS NOT NULL", (since,))
        if not (r[0] == "kindle" and r[1] in manga)]
    keys = {("md5:" + r[1]) if r[0] == "kindle" else r[1] for r in rows}
    found = {}                     # session key -> (Daf book id, calibre id, private, title, author)
    for chunk in _chunks(keys):
        q = ",".join("?" * len(chunk))
        for k, bid, cal, priv, t, a in conn.execute(
                f"SELECT k.key, b.id, b.calibre_id, b.private, b.title, b.author FROM book_keys k JOIN books b ON b.id = k.book_id WHERE k.key IN ({q})", chunk):
            found[k] = (bid, cal, priv, t, a)
        for bid, cal, priv, t, a in conn.execute(
                f"SELECT id, calibre_id, private, title, author FROM books WHERE id IN ({q})", chunk):
            found.setdefault(bid, (bid, cal, priv, t, a))
    per = {}
    for source, item, title, author, secs, start, priv in rows:
        k = ("md5:" + item) if source == "kindle" else item
        bid, cal, bpriv, btitle, bauthor = found.get(k, (k, None, 0, None, None))
        p = per.setdefault(bid, {"title": btitle or title or "", "author": bauthor or author or "", "cal": cal,
                                 "secs": 0, "last": 0, "private": False})
        p["secs"] += secs or 0
        p["last"] = max(p["last"], start or 0)
        p["private"] = p["private"] or bool(priv) or bool(bpriv)
    about = _calibre(p["cal"] for p in per.values())
    out = []
    for p in per.values():
        if p["private"] or p["secs"] < PEEK or not p["title"] or _private(p["title"], settings):
            continue
        tags, desc = about.get(p["cal"], ("", ""))
        out.append({"kind": "book", "title": p["title"], "when": p["last"], "w": _hours(p["secs"]), "by": p["author"] or "",
                    "text": _join(p["title"], (p["author"] or "").replace("|", ","), tags, desc),
                    "verb": "reading" if now - p["last"] < 14 * 86400 else "read"})
    return out


def audiobooks(conn, now, settings):
    """Audiobooks played in Audiobookshelf in the last DAYS days, with its genres, tags and description."""
    since = now - DAYS * 86400
    rows = conn.execute("SELECT item, MAX(title), MAX(author), SUM(seconds), MAX(start), MAX(private) FROM sessions "
                        "WHERE source = 'audio' AND origin = 'audiobookshelf' AND start > ? AND item IS NOT NULL GROUP BY item",
                        (since,)).fetchall()
    about = {}
    if rows and config.ABS_DB.exists():
        a = read_only(config.ABS_DB)
        try:
            for chunk in _chunks(r[0] for r in rows):
                for bid, desc, genres, tags in a.execute(
                        f"SELECT id, description, genres, tags FROM books WHERE id IN ({','.join('?' * len(chunk))})", chunk):
                    words_ = []
                    for j in (genres, tags):
                        try:
                            words_ += [str(x) for x in json.loads(j or "[]")]
                        except ValueError:
                            pass
                    about[bid] = (", ".join(words_), clean(desc))
        except sqlite3.Error as ex:
            log.warning("taste from audiobookshelf: %s", ex)
        finally:
            a.close()
    out = []
    for item, title, author, secs, last, priv in rows:
        if priv or (secs or 0) < PEEK or not title or _private(title, settings):
            continue
        tags, desc = about.get(item, ("", ""))
        out.append({"kind": "audiobook", "title": title, "when": last or 0, "w": _hours(secs), "by": author or "",
                    "text": _join(title, author, tags, desc),
                    "verb": "listening to" if now - (last or 0) < 14 * 86400 else "listened to"})
    return out


def shelves(conn, now, settings, have):
    """Your Hardcover shelves (the copy hardcover.fetch keeps), for books read away from Daf and the ones you
    mean to read. `have`: titles (norm) already counted from the time spent in them."""
    row = conn.execute("SELECT v FROM kv WHERE k = 'hardcover'").fetchone()
    if not row:
        return []
    try:
        shelf = json.loads(row[0]).get("books") or []
    except ValueError:
        return []
    private = {r[0] for r in conn.execute(
        "SELECT hc_id FROM books WHERE private = 1 AND hc_id IS NOT NULL UNION "
        "SELECT l.hc_book_id FROM hc_links l JOIN books b ON b.id = l.book_id WHERE b.private = 1")}
    titles = _calibre_titles()
    picked = []
    for ub in shelf:
        b = ub.get("book") or {}
        title, st = b.get("title") or "", ub.get("status_id")
        w = {1: 0.2, 2: 0.6, 3: 0.3}.get(st)              # want to read, reading, read
        if not title or w is None or ub.get("privacy_setting_id") == 3 or ub.get("book_id") in private:
            continue
        if key(title) in have or _private(title, settings):
            continue
        r = ub.get("rating")
        if r:
            w += 0.6 if r >= 4.5 else 0.3 if r >= 4 else -0.9 if r <= 2 else 0
        authors = [c["author"].get("name") for c in (b.get("cached_contributors") or [])
                   if isinstance(c, dict) and isinstance(c.get("author"), dict)]
        picked.append((ub, title, round(w, 2), ", ".join(a for a in authors[:2] if a), titles.get(norm(title))))
    about = _calibre(p[4] for p in picked)
    out = []
    for ub, title, w, authors, cal in picked:
        tags, desc = about.get(cal, ("", ""))
        out.append({"kind": "book", "title": title, "when": _ts(ub.get("updated_at")) or int(now - 90 * 86400), "w": w, "by": authors,
                    "text": _join(title, authors, tags, desc), "shelf": True,
                    "verb": {1: "want to read", 2: "reading", 3: "read"}[ub["status_id"]]})
    return out


# ---- manga -----------------------------------------------------------------------------------------

TRACK_MAP = config.setting("DAF_MANGA_TRACK_MAP", "/srv/docker/manga-import/track-map.json")
_anilist = {}


def _anilist_about(conn, aid):
    """(genres and tags, description) of an AniList manga, asked once and kept in kv ("anilist:<id>")."""
    if not aid:
        return None
    if aid in _anilist:
        return _anilist[aid]
    row = conn.execute("SELECT v FROM kv WHERE k = ?", (f"anilist:{aid}",)).fetchone()
    if row:
        _anilist[aid] = tuple(json.loads(row[0]))
        return _anilist[aid]
    from . import anilist
    q = "query($id:Int){ Media(id:$id, type:MANGA){ genres tags { name rank isMediaSpoiler } description(asHtml:false) } }"
    req = urllib.request.Request(anilist.API, data=json.dumps({"query": q, "variables": {"id": int(aid)}}).encode(),
                                 headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": anilist.UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        m = (json.load(r).get("data") or {}).get("Media") or {}
    tags = [t["name"] for t in m.get("tags") or [] if not t.get("isMediaSpoiler") and (t.get("rank") or 0) >= 60]
    got = (", ".join((m.get("genres") or []) + tags[:12]), clean(m.get("description"), 400))
    _anilist[aid] = got
    try:
        conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (f"anilist:{aid}", json.dumps(got)))
    except sqlite3.Error:
        pass                                   # a read-only connection: it's kept in memory till the next start
    return got


def _track_map():
    try:
        with open(TRACK_MAP, encoding="utf-8") as f:
            return {k: (v or {}).get("anilistId") for k, v in json.load(f).items() if isinstance(v, dict)}
    except (OSError, ValueError):
        return {}

def manga(conn, now, settings):
    """Manga series read in Daf or on the Kindle in the last DAYS days, with Komga's genres, tags and summary."""
    since = now - DAYS * 86400
    kindle = {r[0][4:]: r[1] for r in conn.execute("SELECT book_id, series FROM manga_books WHERE book_id LIKE 'md5:%'")}
    rows = conn.execute("SELECT source, item, title, seconds, start, private FROM sessions WHERE start > ? AND item IS NOT NULL "
                        "AND (source = 'manga' OR source = 'kindle')", (since,)).fetchall()
    rows = [r for r in rows if r[0] == "manga" or r[1] in kindle]
    if not rows:
        return []
    lib = {"series": {}, "books": {}}
    try:
        from . import manga as komga
        lib = komga.library(max_age=CACHE)
    except Exception as ex:  # noqa: BLE001 - no Komga: the series still count by name
        log.warning("taste from komga: %s", ex)
    per = {}
    for source, item, title, secs, start, priv in rows:
        sid = kindle.get(item) if source == "kindle" else (lib["books"].get(item) or {}).get("series")
        s = lib["series"].get(sid) or {}
        name = s.get("name") or title or ""
        p = per.setdefault(sid or name, {"title": name, "series": s, "secs": 0, "last": 0, "private": False})
        p["secs"] += secs or 0
        p["last"] = max(p["last"], start or 0)
        p["private"] = p["private"] or bool(priv)
    ids = _track_map()
    out = []
    for p in per.values():
        if p["private"] or p["secs"] < PEEK / 2 or not p["title"] or _private(p["title"], settings):
            continue
        s = p["series"]
        tags, summary = ", ".join((s.get("genres") or []) + (s.get("tags") or [])), clean(s.get("summary"), 400)
        if not tags and s.get("folder") in ids:
            try:
                tags, summary = _anilist_about(conn, ids[s["folder"]]) or (tags, summary)
            except Exception as ex:  # noqa: BLE001 - AniList away: the title still counts
                log.info("taste from anilist, %s: %s", p["title"], ex)
        out.append({"kind": "manga", "title": p["title"], "when": p["last"], "w": _hours(p["secs"], 0.3, 0.2),
                    "text": _join(p["title"], tags, summary), "verb": "reading" if now - p["last"] < 14 * 86400 else "read"})
    return out


# ---- Jellyfin and Seerr ----------------------------------------------------------------------------

def _get(url, headers):
    req = urllib.request.Request(url, headers=dict(headers, Accept="application/json"))
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def _me():
    e = secrets.env()
    return e.get("DAF_JELLYFIN_USER") or e.get("JELLYFIN_USER") or ""


def screen(now, settings):
    """Films and shows you watched on Jellyfin in the last DAYS days. A documentary, a docuseries or a home
    video (a lecture) counts fully; fiction lightly. A show is one thing, weighed by its episodes."""
    e = secrets.env()
    key = e.get("DAF_JELLYFIN_KEY") or e.get("JELLYFIN_API_KEY") or e.get("HOMEPAGE_VAR_JELLYFIN_KEY")
    if not key:
        return []
    base = (e.get("DAF_JELLYFIN_URL") or e.get("JELLYFIN_URL") or "http://127.0.0.1:8096").rstrip("/")
    hdr = {"Authorization": f'MediaBrowser Token="{key}"'}
    users = _get(base + "/Users", hdr)
    me = _me()
    uid = next((u["Id"] for u in users if u.get("Name") == me), None) if me else (users[0]["Id"] if len(users) == 1 else None)
    if not uid:
        log.warning("taste from jellyfin: no account named in DAF_JELLYFIN_USER / JELLYFIN_USER")
        return []
    since = now - DAYS * 86400
    out, shows = [], {}
    for lib in _get(f"{base}/Users/{uid}/Views", hdr).get("Items") or []:
        kind = lib.get("CollectionType") or ""
        if kind in SKIP_LIBRARIES:
            continue
        q = urllib.parse.urlencode({"ParentId": lib["Id"], "Recursive": "true", "Filters": "IsPlayed",
                                    "IncludeItemTypes": "Movie,Episode,Video", "SortBy": "DatePlayed", "SortOrder": "Descending",
                                    "Limit": 300, "Fields": "Genres,Tags,Overview", "EnableImages": "false"})
        for it in _get(f"{base}/Users/{uid}/Items?{q}", hdr).get("Items") or []:
            when = _ts((it.get("UserData") or {}).get("LastPlayedDate"))
            if when < since:
                continue
            lecture = kind == "homevideos"
            if it.get("Type") == "Episode" and it.get("SeriesId"):
                s = shows.setdefault(it["SeriesId"], {"eps": 0, "when": 0, "title": it.get("SeriesName") or "", "lecture": lecture})
                s["eps"] += 1
                s["when"] = max(s["when"], when)
                continue
            genres, title = it.get("Genres") or [], it.get("Name") or ""
            if not title or _private(title, settings):
                continue
            fiction = not lecture and "Documentary" not in genres
            out.append({"kind": "screen", "title": title, "when": when, "w": 0.4 if fiction else 1.2,
                        "text": _join(title, ", ".join(genres + (it.get("Tags") or [])), "" if fiction else clean(it.get("Overview"), 400)),
                        "verb": "watched"})
    for sid, s in sorted(shows.items(), key=lambda kv: -kv[1]["when"])[:40]:
        try:
            d = _get(f"{base}/Users/{uid}/Items/{sid}", hdr)
        except Exception as ex:  # noqa: BLE001 - one show that won't answer
            log.info("taste from jellyfin, show %s: %s", sid, ex)
            d = {}
        title, genres = d.get("Name") or s["title"], d.get("Genres") or []
        if not title or _private(title, settings):
            continue
        fiction = not s["lecture"] and "Documentary" not in genres
        w = max(0.15, min(0.8, 0.1 * s["eps"]) if fiction else min(2.4, 0.4 * s["eps"]))
        out.append({"kind": "screen", "title": title, "when": s["when"], "w": round(w, 3),
                    "text": _join(title, ", ".join(genres + (d.get("Tags") or [])), "" if fiction else clean(d.get("Overview"), 400)),
                    "verb": "watching" if now - s["when"] < 21 * 86400 else "watched"})
    return out


def requested(now, settings):
    """What you asked Seerr for in the last DAYS days (your own accounts only: the ones named like your Jellyfin
    account, else the key's owner), with the film's or show's genres, keywords and overview."""
    e = secrets.env()
    key = e.get("DAF_SEERR_KEY") or e.get("SEERR_API_KEY") or e.get("HOMEPAGE_VAR_JELLYSEERR_KEY")
    if not key:
        return []
    base = (e.get("DAF_SEERR_URL") or "http://127.0.0.1:5055").rstrip("/") + "/api/v1"
    hdr = {"X-Api-Key": key}
    me = _me()
    mine = {u["id"] for u in _get(base + "/user?take=100", hdr).get("results") or []
            if me and me in (u.get("jellyfinUsername"), u.get("username"), u.get("displayName"))}
    if not mine:
        mine = {_get(base + "/auth/me", hdr).get("id")}
    reqs = []
    for skip in range(0, 500, 100):
        page = _get(f"{base}/request?take=100&skip={skip}&filter=all&sort=added", hdr).get("results") or []
        reqs += page
        if len(page) < 100 or _ts(page[-1].get("createdAt")) < now - DAYS * 86400:
            break
    out, seen, looked = [], set(), 0
    for r in reqs:
        when = _ts(r.get("createdAt"))
        tid = (r.get("media") or {}).get("tmdbId")
        kind = "movie" if r.get("type") == "movie" else "tv"
        if (r.get("requestedBy") or {}).get("id") not in mine or when < now - DAYS * 86400 or not tid or (kind, tid) in seen:
            continue
        seen.add((kind, tid))
        if (kind, tid) not in _about:
            if looked >= SEERR_LOOKUPS:
                continue
            looked += 1
            try:
                d = _get(f"{base}/{kind}/{tid}", hdr)
            except Exception as ex:  # noqa: BLE001 - one request that won't answer
                log.info("taste from seerr, %s %s: %s", kind, tid, ex)
                continue
            genres = [g.get("name") or "" for g in d.get("genres") or []]
            kws = [k.get("name") or "" for k in (d.get("keywords") or [])[:15]]
            title = d.get("title") or d.get("name") or ""
            fiction = "Documentary" not in genres
            _about[(kind, tid)] = (title, _join(title, ", ".join(genres + kws), "" if fiction else clean(d.get("overview"), 400)), fiction)
        title, text, fiction = _about[(kind, tid)]
        if title and not _private(title, settings):
            out.append({"kind": "requested", "title": title, "when": when, "w": 0.35 if fiction else 1.0, "text": text, "verb": "asked for"})
    return out


def _from_servers(settings):
    """Jellyfin's and Seerr's, kept CACHE seconds (RETRY after a failure)."""
    with _lock:
        t = time.time()
        if _remote["data"] is not None and t < _remote["at"]:
            return _remote["data"]
        data, failed = [], False
        for name, fn in (("jellyfin", screen), ("seerr", requested)):
            try:
                data += fn(t, settings)
            except Exception as ex:  # noqa: BLE001 - a server that's down leaves its part out
                log.warning("taste from %s: %s", name, ex)
                failed = True
        _remote.update(at=t + (RETRY if failed else CACHE), data=data)
        return data


# ---- all of it ---------------------------------------------------------------------------------------

def things(conn, now=None, settings=None, servers=True):
    """Everything above: [{kind, title, when, w, text, verb}], kind book | audiobook | manga | screen | requested."""
    now = now or time.time()
    settings = settings if settings is not None else config.load_settings()
    out = []
    for name, fn in (("books", books), ("audiobooks", audiobooks), ("manga", manga)):
        try:
            out += fn(conn, now, settings)
        except Exception as ex:  # noqa: BLE001
            log.warning("taste from %s: %s", name, ex)
    out = _one_each(out)
    have = {key(t["title"]) for t in out if t["kind"] in ("book", "audiobook")}
    try:
        out += shelves(conn, now, settings, have)
    except Exception as ex:  # noqa: BLE001
        log.warning("taste from hardcover: %s", ex)
    if servers:
        out += _from_servers(settings)
    return [t for t in out if t["text"] and t["when"]]


def _one_each(found):
    """A book counted twice (the Kindle's copy and Daf's under two names) once: the stronger, at the later time."""
    best = {}
    for t in found:
        k = (t["kind"], key(t["title"]))
        b = best.get(k)
        if b is None or t["w"] > b["w"]:
            best[k] = dict(t, when=max(t["when"], b["when"]) if b else t["when"])
        else:
            b["when"] = max(b["when"], t["when"])
    return list(best.values())


def lately(found, now, most=10):
    """What you're in the middle of or just finished (the last LATELY_DAYS days), strongest first, for the model
    and the why lines, each with the names a piece would know it by (its title, and a book's author). A
    want-to-read or long-read Hardcover entry isn't lately."""
    recent = [t for t in found if t["w"] > 0 and now - t["when"] < LATELY_DAYS * 86400
              and not (t.get("shelf") and t["verb"] != "reading")]
    recent.sort(key=lambda t: -t["w"] * 0.5 ** ((now - t["when"]) / (14 * 86400)))
    out, seen = [], set()
    for t in recent:
        k = key(t["title"])
        if k in seen:
            continue
        seen.add(k)
        short = short_title(t["title"])
        names = [short] + ([t["title"]] if t["title"] != short and len(t["title"]) <= 60 else [])
        by = re.sub(r"\s+", " ", (t.get("by") or "").split("|")[0].split(",")[0]).strip()
        if 2 <= len(by.split()) <= 4 and min(len(w) for w in by.split()) >= 2 and re.fullmatch(r"[^\W\d_][\w.'\- ]+", by):
            names.append(by)
        out.append({"title": short, "kind": t["kind"], "verb": t["verb"], "names": names})
        if len(out) >= most:
            break
    return out


COMMON = 3      # a name in this many of the day's candidates is an ordinary phrase there ("Harbour"), not the show


def matchers(lately_, cands):
    """[(thing, pattern)]: each name of what you're into lately, as written (capitals and all) and whole, for
    knowing a candidate that names it. Word overlap was tried first and tied a film about a war veteran to
    news about veterans, so a piece has to name the book, the show or the author."""
    texts = [f'{c.get("title") or ""} {(c.get("summary") or "")[:300]}'.lower() for c in cands]
    out = []
    for t in lately_:
        for name in t.get("names") or []:
            if len(name) < 6 or sum(1 for x in texts if name.lower() in x) >= COMMON:
                continue
            out.append((t, re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)")))
    return out


def near(c, ms):
    """The thing you're into lately that a candidate names, or None."""
    text = f'{c.get("title") or ""} {(c.get("summary") or "")[:300]}'
    for t, rx in ms:
        if rx.search(text):
            return {"title": t["title"], "verb": t["verb"]}
    return None


def near_line(n):
    return f"Goes with {n['title']}, {VERBS.get(n['verb'], 'from your shelf')}"
