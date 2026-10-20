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
