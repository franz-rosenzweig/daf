"""Stats: streaks, totals and a Year 30 projection, when you read, books in progress and
the ones that have stalled, highlights per week, and highlights from this day in other years.
Private books count in the totals but are never named here."""
from collections import defaultdict
from datetime import date, datetime, timedelta

from . import config, ebooks, today as T


def _streak(vals, test, today_index):
    """Consecutive days ending today (or yesterday, if today isn't there yet) that pass `test`."""
    i = today_index
    if i is None:
        return 0
    if not test(vals[i]):
        i -= 1
    n = 0
    while i >= 0 and test(vals[i]):
        n += 1
        i -= 1
    return n


def _best(vals, test):
    best = cur = 0
    for v in vals:
        cur = cur + 1 if test(v) else 0
        best = max(best, cur)
    return best


def streaks(conn, settings):
    t = T.today(settings)
    g = T.grid(conn, t - timedelta(days=399), settings, days=400)
    vals, ti = g["days"], g["today_index"]
    met = [v >= tg for v, tg in zip(vals, g["targets"])]      # each day judged by the goal it had
    return {"goal": _streak(met, bool, ti), "any": _streak(vals, lambda v: v >= 1, ti),
            "best_goal": _best(met, bool), "best_any": _best(vals, lambda v: v >= 1), "vals": vals, "today_index": ti}


def stats(conn, settings):
    tz = T.tz_of(settings)
    t = T.today(settings)
    from . import goals
    goal = goals.minutes_day(settings, t)
    st = streaks(conn, settings)
    vals, ti = st["vals"], st["today_index"]
    last = lambda n: vals[ti - n + 1: ti + 1]
    y30 = T.grid(conn, config.YEAR30_START, settings)
    days_left = max(0, 365 - y30["elapsed"])
    avg30 = sum(last(30)) / 30
    out = {
        "streak": {k: st[k] for k in ("goal", "any", "best_goal", "best_any")},
        "days14": [{"date": (t - timedelta(days=13 - i)).isoformat(), "minutes": v} for i, v in enumerate(last(14))],
        "totals": {"today": vals[ti], "week": round(sum(last(7))), "month": round(sum(last(30))), "avg30": round(avg30, 1),
                   "year30_hours": y30["total_hours"], "year30_days_goal": y30["days_goal"], "year30_days_read": y30["days_read"],
                   "year30_elapsed": y30["elapsed"],
                   "projection_hours": round(y30["total_hours"] + avg30 * days_left / 60),
                   "goal_hours": round(sum(y30["targets"]) / 60)},
        "goal": goal,
    }

    # Sources and times of day, last 90 days.
    since = int(datetime.combine(t - timedelta(days=89), datetime.min.time(), tz).timestamp())
    by_source, by_hour, by_wday = defaultdict(float), [0.0] * 24, [0.0] * 7
    for r in conn.execute("SELECT source, start, seconds FROM sessions WHERE start >= ?", (since,)):
        m = r["seconds"] / 60
        by_source[r["source"]] += m
        if settings["count"].get(r["source"]):
            dt = datetime.fromtimestamp(r["start"], tz)
            by_hour[dt.hour] += m
            by_wday[(dt.weekday() + 1) % 7] += m          # Sunday first
    out["sources"] = [{"source": s, "label": config.SOURCE_LABELS.get(s, s), "minutes": round(by_source.get(s, 0)),
                       "counted": bool(settings["count"].get(s))} for s in config.SOURCES if by_source.get(s)]
    out["hours"] = [round(h) for h in by_hour]
    out["weekdays"] = [round(w / 13) for w in by_wday]    # average per weekday over ~13 weeks

    # Books: in progress, stalled, finished.
    now = int(datetime.now(tz).timestamp())
    readable = ebooks.readable_ids(conn)
    inprog, stalled, finished = [], [], []
    for b in conn.execute("SELECT id, title, author, progress, progress_note, last_read, calibre_path FROM books "
                          "WHERE kind = 'book' AND private = 0 AND last_read IS NOT NULL ORDER BY last_read DESC"):
        p = b["progress"] or 0
        card = {"id": b["id"], "title": b["title"], "author": b["author"], "progress": p, "note": b["progress_note"],
                "last_read": b["last_read"], "days_ago": (now - b["last_read"]) // 86400, "has_cover": bool(b["calibre_path"]),
                "readable": b["id"] in readable}
        if p >= 97:
            finished.append(card)
        elif p >= 2:
            (stalled if card["days_ago"] >= 14 else inprog).append(card)
    out["in_progress"] = inprog[:12]
    out["stalled"] = sorted(stalled, key=lambda c: c["days_ago"])[:12]
    y30_start = int(datetime.combine(config.YEAR30_START, datetime.min.time(), tz).timestamp())
    out["finished"] = [c for c in finished if c["last_read"] >= y30_start - 365 * 86400][:24]

    # Highlights per week, last 12 weeks (Sunday weeks).
    sun = t - timedelta(days=(t.weekday() + 1) % 7)
    weeks = []
    for i in range(11, -1, -1):
        a = sun - timedelta(weeks=i)
        lo = int(datetime.combine(a, datetime.min.time(), tz).timestamp())
        n = conn.execute("SELECT COUNT(*) FROM highlights h LEFT JOIN books b ON b.id = h.book_id WHERE h.deleted = 0 "
                         "AND COALESCE(b.private, 0) = 0 AND h.created >= ? AND h.created < ?", (lo, lo + 7 * 86400)).fetchone()[0]
        weeks.append({"week": a.isoformat(), "n": n})
    out["highlight_weeks"] = weeks
    from . import jump
    out["on_this_day"] = jump.add(conn, on_this_day(conn, settings))
    return out


def on_this_day(conn, settings, limit=6):
    """Highlights made on this date in earlier years."""
    tz = T.tz_of(settings)
    t = T.today(settings)
    out = []
    for r in conn.execute(
            "SELECT h.id, h.text, h.created, h.book_id, b.title, b.author FROM highlights h JOIN books b ON b.id = h.book_id "
            "WHERE h.deleted = 0 AND b.private = 0 AND h.created IS NOT NULL AND length(h.text) >= 30 ORDER BY h.created DESC"):
        d = datetime.fromtimestamp(r["created"], tz).date()
        if d.month == t.month and d.day == t.day and d.year < t.year:
            out.append({"id": r["id"], "text": r["text"], "title": r["title"], "author": r["author"], "year": d.year,
                        "years_ago": t.year - d.year, "book_id": r["book_id"]})
    return out[:limit]
