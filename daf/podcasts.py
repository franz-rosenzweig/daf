"""The Podcasts tab: the shows you follow and their episodes, filtered and sorted; a search of your own
episodes (titles, show notes, and transcripts where Daf has them) and of Apple's podcast directory;
and Follow.

Subscriptions are gpodder.py's (gp_subs): the list AntennaPod syncs with Daf. Following a show here
adds it there with today's time; AntennaPod asks Daf what changed since its last sync
(GET /api/2/subscriptions/…?since=) each time it syncs, so the show turns up in AntennaPod at its next
sync, and one unfollowed here goes from AntennaPod the same way. AntennaPod's own changes come the
other way when it uploads them.

What a show or an episode is comes from its feed (episodes.read_feed), read when it's followed or
opened and once a day after (gpodder.refresh_feeds). Where you are in an episode is the last play
action from anywhere (AntennaPod's or Daf's).
"""
import json
import re
import time
import urllib.parse
import urllib.request

from . import episodes

ITUNES = "https://itunes.apple.com/search"
UA = episodes.UA
DONE_LEFT = 60                    # an episode with less than a minute left is played


# ---- where you are in each episode ------------------------------------------------------------

def _states(conn, urls=None):
    """{audio: (position, total)} from each episode's latest play action."""
    q = ("SELECT episode, position, total, MAX(timestamp) FROM gp_actions WHERE action = 'play' AND position IS NOT NULL" +
         (f" AND episode IN ({','.join('?' * len(urls))})" if urls is not None else "") + " GROUP BY episode")
    return {r[0]: (r[1], r[2]) for r in conn.execute(q, list(urls or []))}


def _clips(conn):
    return {r[0]: r[1] for r in conn.execute(
        "SELECT d.enclosure, COUNT(*) FROM highlights h JOIN docs d ON d.id = h.book_id "
        "WHERE d.kind = 'podcast' AND h.deleted = 0 AND d.enclosure IS NOT NULL GROUP BY d.enclosure")}


def _docs(conn, urls):
    if not urls:
        return {}
    out = {}
    for r in conn.execute(f"SELECT enclosure, id, where_ FROM docs WHERE kind = 'podcast' AND status != 'deleted' "
                          f"AND enclosure IN ({','.join('?' * len(urls))}) ORDER BY CASE where_ WHEN 'library' THEN 0 WHEN 'feed' THEN 1 ELSE 2 END",
                          list(urls)):
        out.setdefault(r[0], r[1])
    return out


def _row(r, st, have, clips, docs):
    """An episode as the tab shows it."""
    pos, total = st.get(r["url"], (None, None))
    dur = r["duration"] or total or None
    done = bool(pos is not None and dur and pos >= dur - DONE_LEFT)
    return {"audio": r["url"], "title": r["title"] or "", "published": r["published"], "duration": dur, "feed": r["podcast"],
            "show": r["podcast_title"] or "", "image": r["image"], "at": pos, "played": pos, "done": done,
            "started": bool(pos and pos > 15 and not done), "transcript": r["url"] in have, "clips": clips.get(r["url"], 0),
            "doc": docs.get(r["url"]), "notes": _plain(r["notes"])[:280] if "notes" in r.keys() else ""}


def _plain(s):
    import html
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


# ---- the shows and their episodes -----------------------------------------------------------

def feed_info(conn, feed_url):
    r = conn.execute("SELECT v FROM kv WHERE k = ?", ("podfeed:" + feed_url,)).fetchone()
    try:
        return json.loads(r[0]) if r else {}
    except ValueError:
        return {}


def shows(conn):
    """The shows you follow, with how many episodes each has, how many you haven't played, and its newest."""
    subs = conn.execute("SELECT url, title, added FROM gp_subs WHERE removed IS NULL").fetchall()
    st = _states(conn)
    out = []
    for s in subs:
        eps = conn.execute("SELECT url, duration, published FROM gp_episodes WHERE podcast = ?", (s["url"],)).fetchall()
        played = sum(1 for e in eps if e["url"] in st)
        info = feed_info(conn, s["url"])
        out.append({"feed": s["url"], "title": s["title"] or info.get("title") or s["url"], "image": info.get("image"),
                    "author": info.get("author") or "", "count": len(eps), "unplayed": len(eps) - played,
                    "newest": max([e["published"] or 0 for e in eps] or [0]) or None, "added": s["added"]})
    return out


def episode_list(conn, feed=None, flt="", sort="newest", limit=60, offset=0, q=""):
    """Episodes of the shows you follow (or of one show): flt is "" (all), "unplayed", "progress",
    "played", "transcribed" or "clipped"; sort is "newest", "oldest" or "longest"."""
    if feed:
        rows = conn.execute("SELECT * FROM gp_episodes WHERE podcast = ?", (feed,)).fetchall()
    else:
        rows = conn.execute("SELECT e.* FROM gp_episodes e JOIN gp_subs s ON s.url = e.podcast WHERE s.removed IS NULL").fetchall()
    st = _states(conn)
    have = {r[0] for r in conn.execute("SELECT audio FROM episode_text")}
    clips = _clips(conn)
    eps = [_row(r, st, have, clips, {}) for r in rows]
    keep = {"unplayed": lambda e: e["at"] is None, "progress": lambda e: e["started"], "played": lambda e: e["done"],
            "transcribed": lambda e: e["transcript"], "clipped": lambda e: e["clips"] > 0}.get(flt)
    if keep:
        eps = [e for e in eps if keep(e)]
    if q:
        eps = [e for e in eps if _has(q, e["title"], e["show"], e["notes"])]
    key = {"oldest": lambda e: (e["published"] or 0), "longest": lambda e: -(e["duration"] or 0)}.get(sort, lambda e: -(e["published"] or 0))
    eps.sort(key=key)
    page = eps[offset:offset + limit]
    docs = _docs(conn, [e["audio"] for e in page])
    for e in page:
        e["doc"] = docs.get(e["audio"])
    return {"total": len(eps), "episodes": page}


def _has(q, *texts):
    hay = " ".join(t or "" for t in texts).lower()
    return all(w in hay for w in q.lower().split())


def show(conn, feed_url, read=True):
    """A show's page: what the feed says about it, whether you follow it, and every episode in it.
    read: read the feed first if it's older than six hours (a feed read before Daf kept a show's
    description, at once); without it, what Daf already knows, at once."""
    if read:
        episodes.read_feed(conn, feed_url, max_age=episodes.FEED_MAX_AGE if "description" in feed_info(conn, feed_url) else 0)
    info = feed_info(conn, feed_url)
    sub = conn.execute("SELECT title, removed FROM gp_subs WHERE url = ?", (feed_url,)).fetchone()
    eps = episode_list(conn, feed_url, limit=1000)
    title = (sub["title"] if sub and sub["title"] else None) or info.get("title") or feed_url
    newest = max([e["published"] or 0 for e in eps["episodes"]] or [0]) or None
    return {"feed": feed_url, "title": title, "image": info.get("image"), "author": info.get("author") or "",
            "description": _plain(info.get("description") or ""), "link": info.get("link") or "", "updated": newest,
            "count": eps["total"], "following": bool(sub and sub["removed"] is None), "error": info.get("error"),
            "episodes": eps["episodes"]}


def follow(conn, feed_url, on=True):
    """Follow a show (into the subscriptions AntennaPod syncs), or stop following it."""
    now = int(time.time())
    if on:
        conn.execute("INSERT INTO gp_subs (url, added, removed) VALUES (?, ?, NULL) ON CONFLICT(url) DO UPDATE SET added = excluded.added, removed = NULL",
                     (feed_url, now))
        conn.commit()                                  # not holding the write lock while the feed comes
        title = episodes.read_feed(conn, feed_url, max_age=3600)
        if title:
            conn.execute("UPDATE gp_subs SET title = ?, checked = ? WHERE url = ?", (title, now, feed_url))
    else:
        conn.execute("UPDATE gp_subs SET removed = ? WHERE url = ?", (now, feed_url))
    return {"following": on}


def listening(conn):
    """Episodes started and not finished, newest play first; and new episodes of the shows you follow."""
    st = conn.execute("SELECT episode, position, total, MAX(timestamp) AS at FROM gp_actions WHERE action = 'play' AND position IS NOT NULL "
                      "GROUP BY episode ORDER BY at DESC LIMIT 200").fetchall()
    urls = [r["episode"] for r in st]
    meta = {r["url"]: r for r in conn.execute(f"SELECT * FROM gp_episodes WHERE url IN ({','.join('?' * len(urls))})", urls)} if urls else {}
    have = {r[0] for r in conn.execute("SELECT audio FROM episode_text")}
    clips = _clips(conn)
    states = {r["episode"]: (r["position"], r["total"]) for r in st}
    going = []
    for r in st:
        m = meta.get(r["episode"])
        if not m:
            continue
        e = _row(m, states, have, clips, {})
        if e["started"]:
            e["last"] = r["at"]
            going.append(e)
    fresh = conn.execute("SELECT e.* FROM gp_episodes e JOIN gp_subs s ON s.url = e.podcast WHERE s.removed IS NULL AND e.published > ? "
                         "ORDER BY e.published DESC LIMIT 60", (int(time.time()) - 21 * 86400,)).fetchall()
    allst = _states(conn, [r["url"] for r in fresh])
    new = [_row(r, allst, have, clips, {}) for r in fresh]
    new = [e for e in new if e["at"] is None][:24]
    docs = _docs(conn, [e["audio"] for e in going[:20] + new])
    for e in going[:20] + new:
        e["doc"] = docs.get(e["audio"])
    return {"going": going[:20], "new": new}


# ---- search: your own, and the directory -------------------------------------------------------

def search_mine(conn, q):
    """Your shows and episodes whose title or show notes have every word, and episodes whose transcript
    has them (docs_fts holds a transcript beside its show notes, episodes.index)."""
    from .reader import fts_match
    words = [w for w in q.lower().split() if w]
    if not words:
        return {"shows": [], "episodes": []}
    sh = [s for s in shows(conn) if _has(q, s["title"], s["author"], feed_info(conn, s["feed"]).get("description"))]
    like = " AND ".join("(lower(e.title) LIKE ? OR lower(e.podcast_title) LIKE ? OR lower(COALESCE(e.notes, '')) LIKE ?)" for _ in words)
    args = [x for w in words for x in (f"%{w}%",) * 3]
    rows = conn.execute("SELECT e.*, (s.removed IS NULL AND s.url IS NOT NULL) AS mine FROM gp_episodes e LEFT JOIN gp_subs s ON s.url = e.podcast "
                        f"WHERE {like} ORDER BY e.published DESC LIMIT 400", args).fetchall()
    # The likeliest first: the words together in the title, then each a whole word in it, then in the
    # show notes the same way; a word only inside another ("big" in "biggest") last.
    phrase = re.compile(r"\b" + r"\W+".join(re.escape(w) for w in words) + r"\b", re.I)
    whole = [re.compile(r"\b" + re.escape(w) + r"\b", re.I) for w in words]
    def rank(r):
        t, n = (r["title"] or "") + " " + (r["podcast_title"] or ""), _plain(r["notes"])
        return (3 if phrase.search(t) else 2 if all(x.search(t) for x in whole) else 1.5 if phrase.search(n) else
                1 if all(x.search(t + " " + n) for x in whole) else 0, r["mine"] or 0, r["published"] or 0)
    rows = sorted(rows, key=rank, reverse=True)[:40]
    st = _states(conn, [r["url"] for r in rows])
    have = {r[0] for r in conn.execute("SELECT audio FROM episode_text")}
    clips = _clips(conn)
    eps = []
    for r in rows:
        e = _row(r, st, have, clips, {})
        e["why"] = "title" if _has(q, e["title"], e["show"]) else "notes"
        e["snip"] = _snip(_plain(r["notes"]), words) if e["why"] == "notes" else ""
        eps.append(e)
    seen = {e["audio"] for e in eps}
    match = fts_match(q)
    if match:
        for r in conn.execute("SELECT d.enclosure, snippet(docs_fts, 2, char(2), char(3), '…', 14) AS snip FROM docs_fts f "
                              "JOIN docs d ON d.id = f.id WHERE docs_fts MATCH ? AND d.kind = 'podcast' AND d.status != 'deleted' "
                              "ORDER BY bm25(docs_fts) LIMIT 40", (match,)).fetchall():
            if r["enclosure"] in seen or r["enclosure"] not in have:
                continue
            m = episodes.meta(conn, r["enclosure"])
            if not m:
                continue
            seen.add(r["enclosure"])
            e = _row(m, _states(conn, [r["enclosure"]]), have, clips, {})
            e["why"], e["snip"] = "transcript", r["snip"]
            eps.append(e)
    docs = _docs(conn, [e["audio"] for e in eps])
    for e in eps:
        e["doc"] = docs.get(e["audio"])
    return {"shows": sh, "episodes": eps}


def _snip(text, words, width=160):
    low = text.lower()
    m = re.search(r"\b" + r"\W+".join(re.escape(w) for w in words) + r"\b", low) or re.search(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", low)
    i = m.start() if m else min([low.find(w) for w in words if low.find(w) >= 0] or [0])
    a = max(0, i - width // 3)
    s = text[a:a + width]
    for w in sorted(set(words), key=len, reverse=True):
        s = re.sub(r"\b(" + re.escape(w) + r")\b", "\u0002\\1\u0003", s, flags=re.I)
    return ("…" if a else "") + s + ("…" if a + width < len(text) else "")


_dir = {}


def directory(q, kind="shows", limit=25):
    """Apple's podcast directory (the iTunes Search API, which needs no key): shows, or episodes."""
    q = q.strip()
    k = (q.lower(), kind)
    hit = _dir.get(k)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    p = {"term": q, "media": "podcast", "limit": limit}
    if kind == "episodes":
        p["entity"] = "podcastEpisode"
    req = urllib.request.Request(ITUNES + "?" + urllib.parse.urlencode(p), headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read()).get("results", [])
    out = []
    for x in res:
        if kind == "episodes":
            if not x.get("episodeUrl") or not x.get("feedUrl"):
                continue
            out.append({"audio": x["episodeUrl"], "title": x.get("trackName") or "", "show": x.get("collectionName") or "",
                        "feed": x["feedUrl"], "image": x.get("artworkUrl600") or x.get("artworkUrl160") or "",
                        "published": _iso(x.get("releaseDate")), "duration": int((x.get("trackTimeMillis") or 0) / 1000) or None,
                        "notes": _plain(x.get("description") or x.get("shortDescription") or "")[:400], "guid": x.get("episodeGuid")})
        else:
            if not x.get("feedUrl"):
                continue
            out.append({"feed": x["feedUrl"], "title": x.get("collectionName") or "", "author": x.get("artistName") or "",
                        "image": x.get("artworkUrl600") or x.get("artworkUrl100") or "", "count": x.get("trackCount"),
                        "updated": _iso(x.get("releaseDate")), "genre": x.get("primaryGenreName") or ""})
    _dir[k] = (time.time(), out)
    if len(_dir) > 200:
        _dir.clear()
    return out


def _iso(s):
    from datetime import datetime
    try:
        return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError):
        return None


def found(conn, e):
    """An episode found in the directory, remembered as its feed would have it, so it opens and plays
    like one of yours (its page, its transcript, where you stop going to AntennaPod)."""
    audio, feed = str(e.get("audio") or ""), str(e.get("feed") or "")
    if not re.match(r"^https?://", audio) or (feed and not re.match(r"^https?://", feed)):
        raise ValueError("An episode's audio address")
    if episodes.meta(conn, audio):
        return
    episodes.remember(conn, feed or None, str(e.get("show") or ""), [{
        "url": audio, "link": "", "title": str(e.get("title") or "")[:500], "guid": e.get("guid") or None,
        "published": int(e["published"]) if str(e.get("published") or "").isdigit() else None,
        "duration": int(e["duration"]) if str(e.get("duration") or "").isdigit() else None,
        "image": str(e.get("image") or "") or None, "author": str(e.get("show") or "") or None,
        "notes": str(e.get("notes") or "") or None, "transcript_url": None, "transcript_type": None, "chapters_url": None}])
    # Not "checked": the episode's page reads its feed once for the rest (episodes.ensure_meta).
    conn.execute("UPDATE gp_episodes SET checked = NULL WHERE url = ?", (audio,))
