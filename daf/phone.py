"""The phone: the evening nudge (asked for by Tasker when a feed app opens), the
home-screen widget's numbers, and things shared to Daf from the share menu.

The nudge never blocks anything. It offers one highlight and the minutes left,
at most once every 25 minutes, and only while the hour isn't done. Every nudge is
logged, so Daf can say whether reading followed within 30 minutes.
"""
import random
import time

from . import config, library, reader, review, today as T

NUDGE_GAP = 25 * 60
FOLLOW_WINDOW = 30 * 60


def clip(text, n=220):
    t = (text or "").strip().strip("\u201c\u201d\"")
    if len(t) <= n:
        return t
    return t[:n].rsplit(" ", 1)[0].rstrip(",;:.") + "\u2026"


def _counted_today(conn, settings):
    return T.day_summary(conn, T.today(settings), settings)["counted"]


def _pick_highlight(conn, settings):
    items = [i for i in review.day_items(conn, settings)["items"] if not i["action"]]
    if items:
        return items[0]
    kept = [dict(r) for r in conn.execute(
        "SELECT h.id, h.text, b.title FROM highlights h JOIN books b ON b.id = h.book_id "
        "JOIN review_state s ON s.hl_id = h.id WHERE s.status = 'kept' AND h.deleted = 0 AND b.private = 0 "
        "AND length(h.text) BETWEEN 30 AND 400")]
    return random.choice(kept) if kept else None


def nudge(conn, settings, app=None, force=False):
    now = int(time.time())
    from . import goals
    counted = _counted_today(conn, settings)
    target = goals.minutes_day(settings)
    left = max(0, target - counted)
    last = conn.execute("SELECT MAX(at) FROM nudges WHERE shown = 1").fetchone()[0]
    reason = None
    if left <= 0 and not force:
        reason = "hour done"
    elif last and now - last < NUDGE_GAP and not force:
        reason = "too soon"
    shown = reason is None
    conn.execute("INSERT INTO nudges (at, app, shown, reason, minutes_left) VALUES (?, ?, ?, ?, ?)",
                 (now, (app or "")[:40], int(shown), reason, round(left)))
    if not shown:
        return {"show": False, "reason": reason, "minutes_left": round(left)}
    h = _pick_highlight(conn, settings)
    cur = library.current_kindle_book(conn)
    book = cur["book"] if cur and cur["book"] and not cur["book"]["private"] else None
    title = f"{round(left)} minutes left today" if counted > 0 else (
        "An hour of reading, not yet started" if target == 60 else f"{round(target)} minutes of reading, not yet started")
    where = f" The Kindle is on page {cur['page']} of {book['title'].split(':')[0]}." if book and cur.get("page") else ""
    text = (f"“{clip(reader.plain(h['text']))}” — {(h.get('title') or '').split(':')[0]}." if h else "") + where
    return {"show": True, "title": title, "text": text.strip(), "minutes_left": round(left),
            "url": config.public_url(settings) + "/"}


def nudge_stats(conn, days=7):
    since = int(time.time()) - days * 86400
    shown = [r[0] for r in conn.execute("SELECT at FROM nudges WHERE shown = 1 AND at > ?", (since,))]
    # Followed = any counted reading began within the window: the Kindle, audiobooks, articles,
    # books in Daf, videos if counted. Not paper: its minutes are logged after the fact.
    counted = config.load_settings()["count"]
    srcs = [x for x in config.SOURCES if counted.get(x) and x != "paper"] or ["kindle"]
    starts = [r[0] for r in conn.execute(
        f"SELECT start FROM sessions WHERE start > ? AND source IN ({','.join('?' * len(srcs))})", (since, *srcs))]
    followed = sum(1 for a in shown if any(a <= s <= a + FOLLOW_WINDOW for s in starts))
    asked = conn.execute("SELECT COUNT(*) FROM nudges WHERE at > ?", (since,)).fetchone()[0]
    return {"days": days, "asked": asked, "shown": len(shown), "followed": followed}


def widget(conn, settings):
    s = T.day_summary(conn, T.today(settings), settings)
    y = T.grid(conn, config.YEAR30_START, settings)
    h = _pick_highlight(conn, settings)
    stand = library.nightstand(conn, settings) or library.suggest_nightstand(conn)
    from . import goals
    gl = goals.summary(conn, settings)
    return {"date": s["date"], "minutes": round(s["counted"]), "goal": s["goal"],
            "goals": gl, "main": goals.main_of(gl),
            "year_day": (y["today_index"] or 0) + 1, "year_hours": y["total_hours"],
            "highlight": {"text": reader.plain(h["text"]), "title": (h.get("title") or "").split(":")[0]} if h else None,
            # A private book can be on the nightstand; outside Daf's own pages it isn't named.
            "nightstand": [{"id": b["id"], "title": "A private book" if b.get("private") else b["title"].split(":")[0], "progress": b["progress"]} for b in stand]}


def save_shared(conn, url, title, text):
    now = int(time.time())
    url = (url or "").strip()
    if not url:
        # Some apps put the link inside the text.
        import re
        m = re.search(r"https?://\S+", text or "")
        url = m.group(0) if m else ""
    conn.execute("INSERT INTO inbox (url, title, text, created, status) VALUES (?, ?, ?, ?, 'new')",
                 (url, (title or "").strip()[:300], (text or "").strip()[:2000], now))
    return url


# ---- the home-screen widgets (android/…/widgets): one answer for all of them ----------------------
# Keep reading, the Edition, Spotlight, a highlight, Listen and the Feed list's sources come in one
# answer (/api/phone/widgets); a Feed widget's own headlines come from widget_feed. Pictures are
# Daf's own addresses (/api/cover/…, /api/thumb/…, which take the phone's token) or a page's picture
# on the web. A private book is never named outside Daf's own pages, and has no cover here.

def _short(title):
    return (title or "").split(":")[0].strip()


def _book(b, readable):
    priv = bool(b.get("private"))
    route = ("#ebook/" if b["id"] in readable else "#book/") + b["id"]
    return {"id": b["id"], "title": "A private book" if priv else _short(b["title"]),
            "author": "" if priv else (b.get("author") or ""),
            "progress": b.get("progress"), "note": b.get("progress_note") or "",
            "audio": b.get("audio_pct"), "audio_note": b.get("audio_note") or "",
            "cover": None if priv or not b.get("calibre_path") else "/api/cover/" + b["id"],
            "route": route}


def _reading(conn, settings, n=6):
    """The nightstand first (or what Daf suggests for it), then the other books read lately."""
    from . import ebooks
    try:
        readable = ebooks.readable_ids(conn)
    except Exception:  # noqa: BLE001 - Calibre's database away: the book's page instead of the reader
        readable = set()
    stand = library.nightstand(conn, settings) or library.suggest_nightstand(conn)
    ids = {b["id"] for b in stand}
    more = [dict(r) for r in conn.execute(
        "SELECT * FROM books WHERE kind = 'book' AND private = 0 AND (last_read IS NOT NULL OR audio_pct IS NOT NULL) "
        "AND id NOT IN (SELECT book_id FROM manga_books) ORDER BY COALESCE(last_read, 0) DESC LIMIT ?", (n + 3,))]
    books = stand + [b for b in more if b["id"] not in ids]
    return [_book(b, readable) for b in books[:n]]


def _piece(it, label=None):
    return {"id": it["id"], "title": it.get("title") or "", "source": it.get("publication") or it.get("source") or "",
            "kind": it.get("kind") or "article", "minutes": it.get("minutes") or it.get("mins"),
            "thumb": it.get("thumb") or None, "label": label,
            "route": "#read/" + it["id"] if it.get("exists", True) else "#edition"}


def _edition(conn, settings):
    from . import edition
    e = edition.public(conn, T.today(settings)).get("edition")
    if not e:
        return None
    items = [_piece(it) | {"done": bool(it.get("done") or it.get("opened"))} for it in e["items"]]
    return {"day": e["day"], "number": e.get("number"), "done": e.get("done", 0), "total": len(items), "items": items}


def _spotlight(conn, settings, ed, n=10):
    """Pieces with a picture, for the Spotlight: what's left in the Edition, then the Feed's newest."""
    out = [p | {"label": "Edition"} for p in (ed or {}).get("items", []) if p.get("thumb") and not p.get("done")]
    seen = {p["id"] for p in out}
    for d in reader.list_docs(conn, settings, "feed", "unseen", None, None, 60, 0, "new", None, {}, ""):    # the Feed as it shows
        if len(out) >= n:
            break
        if d.get("thumb") and d["id"] not in seen and d.get("title"):
            out.append(_piece(d, d.get("source")))
    return out[:n]


def _highlights(conn, settings, n=20):
    """The day's review first, then highlights kept in Review, shuffled; none from a private book."""
    out, seen = [], set()
    for i in review.day_items(conn, settings)["items"]:
        if i.get("action") or i["id"] in seen or i.get("private"):
            continue
        seen.add(i["id"])
        out.append({"id": i["id"], "text": clip(reader.plain(i["text"]), 400), "title": _short(i.get("title")), "route": "#review"})
    kept = [dict(r) for r in conn.execute(
        "SELECT h.id, h.text, b.title FROM highlights h JOIN books b ON b.id = h.book_id "
        "JOIN review_state s ON s.hl_id = h.id WHERE s.status = 'kept' AND h.deleted = 0 AND b.private = 0 "
        "AND length(h.text) BETWEEN 30 AND 400 ORDER BY RANDOM() LIMIT ?", (n,))]
    for h in kept:
        if len(out) >= n:
            break
        if h["id"] not in seen:
            seen.add(h["id"])
            out.append({"id": h["id"], "text": reader.plain(h["text"]), "title": _short(h["title"]), "route": "#review"})
    return out


def _listen(conn):
    """The episode last played and not finished."""
    from . import podcasts
    try:
        going = podcasts.listening(conn)["going"]
    except Exception:  # noqa: BLE001
        return None
    if not going:
        return None
    e = going[0]
    return {"audio": e["audio"], "title": e["title"], "show": e["show"], "image": e.get("image"),
            "at": e.get("at"), "duration": e.get("duration"), "doc": e.get("doc"),
            "route": "#read/" + e["doc"] if e.get("doc") else "#podcasts"}


def _feed_sources(conn, settings):
    try:
        src = reader.feed_sources(conn, settings)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for f in src.get("folders") or []:
        if f.get("show") == "hidden":
            continue
        if f.get("name"):
            out.append({"key": "folder:" + f["name"], "name": f["name"], "count": f.get("count", 0)})
        for x in f.get("feeds") or []:
            out.append({"key": "feed:" + x["id"], "name": x["title"], "folder": f.get("name") or "", "count": x.get("count", 0)})
    return out


def widgets(conn, settings):
    ed = _edition(conn, settings)
    return {"at": int(time.time()), "reading": _reading(conn, settings), "edition": ed,
            "spotlight": _spotlight(conn, settings, ed), "highlights": _highlights(conn, settings),
            "listen": _listen(conn), "feeds": _feed_sources(conn, settings)}


def widget_feed(conn, settings, src="", limit=20):
    """A Feed widget's headlines: what's unseen in the whole Feed, a folder ("folder:Name") or a feed ("feed:id")."""
    cat = src[7:] if src.startswith("folder:") else None
    feed = src[5:] if src.startswith("feed:") else None
    items = reader.list_docs(conn, settings, "feed", "unseen", None, cat, max(1, min(limit, 40)), 0, "new", feed, {}, "")
    return {"src": src, "items": [{"id": d["id"], "title": d["title"] or "", "source": d.get("source") or "",
                                   "published": d.get("published") or d.get("added"), "thumb": d.get("thumb") or None,
                                   "kind": d.get("kind") or "article", "route": "#read/" + d["id"]} for d in items]}
