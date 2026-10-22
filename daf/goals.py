"""Reading goals: what you aim for, and how you're doing, judged honestly.

settings.json "goals" holds one goal per kind, for example
  {"id": "minutes", "kind": "minutes", "period": "day", "target": 60, "on": true, "main": true,
   "history": [{"from": "2000-01-01", "period": "day", "target": 60, "on": true}]}
A change takes effect today and is added to the history, so earlier days, streaks and the
Year 30 grid are judged by the goal each day had. The main goal drives the ring on Today,
the widget, the menu bar and the Kindle screen. The daily minutes target (from the minutes
goal, whether or not it's on) is what "at the goal" means for a day.
"""
import json
import re
import statistics
from collections import defaultdict
from datetime import date, datetime, time as dtime, timedelta

from . import config, today as T

YEAR35_START = config.YEAR30_START.replace(year=config.YEAR30_START.year + 5)   # "by 35" means before it
BEGINNING = "2000-01-01"           # history entries from before Daf: the goal you started with

# kind: label, unit (one, many), periods, default target per period, (min, max, step) per period
KINDS = {
    "minutes": {"label": "Reading time", "unit": ("minute", "minutes"), "periods": ["day", "week", "month"],
                "default": {"day": 60, "week": 420, "month": 1800},
                "range": {"day": (5, 300, 5), "week": (30, 2100, 15), "month": (60, 9000, 60)}},
    "pages": {"label": "Pages", "unit": ("page", "pages"), "periods": ["day", "week"],
              "default": {"day": 30, "week": 200}, "range": {"day": (5, 400, 5), "week": (20, 2500, 10)}},
    "books": {"label": "Books", "unit": ("book", "books"), "periods": ["y30", "year", "by35"],
              "default": {"y30": 24, "year": 24, "by35": 120}, "range": {"y30": (1, 150, 1), "year": (1, 150, 1), "by35": (5, 600, 5)}},
    "days": {"label": "Days with reading", "unit": ("day", "days"), "periods": ["week"],
             "default": {"week": 5}, "range": {"week": (1, 7, 1)}},
    "streak": {"label": "A streak at the goal", "unit": ("day in a row", "days in a row"), "periods": ["run"],
               "default": {"run": 30}, "range": {"run": (3, 365, 1)}},
    "highlights": {"label": "Highlights", "unit": ("highlight", "highlights"), "periods": ["week"],
                   "default": {"week": 10}, "range": {"week": (1, 300, 1)}},
    "reviews": {"label": "The daily review", "unit": ("day", "days"), "periods": ["week"],
                "default": {"week": 5}, "range": {"week": (1, 7, 1)}},
}
ORDER = list(KINDS)
# A manga or comic volume: "Kaguya-sama - Love Is War v12", "Naruto Vol. 3". The books goal counts
# them only if you say so.
VOLUME = re.compile(r"\bv(?:ol\.?)?\s?\d{1,3}\b", re.I)

DEFAULTS = [
    {"id": "minutes", "period": "day", "target": 60, "on": True, "main": True},
    {"id": "pages", "period": "week", "target": 200, "on": False},
    {"id": "books", "period": "y30", "target": 24, "on": False, "manga": False},
    {"id": "days", "period": "week", "target": 5, "on": False},
    {"id": "streak", "period": "run", "target": 30, "on": False},
    {"id": "highlights", "period": "week", "target": 10, "on": False},
    {"id": "reviews", "period": "week", "target": 5, "on": False},
]

PRESETS = {
    "gentle": {"label": "Gentle", "text": "Half an hour a day, five days a week.",
               "goals": {"minutes": {"period": "day", "target": 30, "on": True}, "days": {"period": "week", "target": 5, "on": True}}},
    "year30": {"label": "Year 30", "text": "An hour a day, and two books a month.",
               "goals": {"minutes": {"period": "day", "target": 60, "on": True}, "books": {"period": "y30", "target": 24, "on": True}}},
    "deep": {"label": "Deep", "text": "An hour and a half a day, three books a month.",
             "goals": {"minutes": {"period": "day", "target": 90, "on": True}, "books": {"period": "y30", "target": 36, "on": True}}},
}


# ---- the goals and their history --------------------------------------------------

def _clean_target(kind, period, v):
    lo, hi, step = KINDS[kind]["range"][period]
    try:
        v = float(v)
    except (TypeError, ValueError):
        return KINDS[kind]["default"][period]
    v = max(lo, min(hi, v))
    return int(round(v / step) * step) if step >= 1 else v


def all_goals(settings):
    """Every goal, defaults filled in, each with a history. Exactly one is main."""
    saved = {g.get("id"): g for g in (settings.get("goals") or []) if isinstance(g, dict)}
    out = []
    for d in DEFAULTS:
        g = dict(d)
        s = saved.get(d["id"]) or {}
        kind = d["id"]
        if s.get("period") in KINDS[kind]["periods"]:
            g["period"] = s["period"]
        if "target" in s:
            g["target"] = _clean_target(kind, g["period"], s["target"])
        if isinstance(s.get("on"), bool):
            g["on"] = s["on"]
        if kind == "books":
            g["manga"] = bool(s.get("manga"))
        g["main"] = bool(s.get("main")) if saved else bool(d.get("main"))
        hist = [h for h in (s.get("history") or []) if isinstance(h, dict) and isinstance(h.get("from"), str)
                and h.get("period") in KINDS[kind]["periods"]]
        g["history"] = sorted(hist, key=lambda h: h["from"]) or [
            {"from": BEGINNING, "period": g["period"], "target": g["target"], "on": g["on"]}]
        g["kind"] = kind
        out.append(g)
    mains = [g for g in out if g["main"] and g["on"]]
    for g in out:
        g["main"] = False
    (mains[0] if mains else next((g for g in out if g["on"]), out[0]))["main"] = True
    return out


def goal(settings, gid):
    return next(g for g in all_goals(settings) if g["id"] == gid)


def effective(g, d):
    """The goal as it was on day d: the last history entry from on or before d."""
    iso = d.isoformat()
    cur = g["history"][0]
    for h in g["history"]:
        if h["from"] <= iso:
            cur = h
    return cur


def _per_day(e):
    t = float(e["target"])
    return round(t if e["period"] == "day" else t / 7 if e["period"] == "week" else t / 30, 1)


def minutes_day(settings, d=None):
    """Minutes a day that count as "at the goal" on day d (today if None)."""
    d = d or T.today(settings)
    return _per_day(effective(goal(settings, "minutes"), d))


def daily_targets(settings, start, days):
    """The daily minutes target for each of `days` days from `start`."""
    g = goal(settings, "minutes")
    return [_per_day(effective(g, start + timedelta(days=i))) for i in range(days)]


def save(settings, incoming, day):
    """Apply changes from the page: [{id, period?, target?, on?, main?}]. Returns the new list."""
    cur = {g["id"]: g for g in all_goals(settings)}
    by_id = {x.get("id"): x for x in incoming if isinstance(x, dict) and x.get("id") in cur}
    if any(x.get("main") for x in by_id.values()):
        for g in cur.values():
            g["main"] = False
    iso = day.isoformat()
    for gid, x in by_id.items():
        g, kind = cur[gid], gid
        if x.get("period") in KINDS[kind]["periods"] and x["period"] != g["period"]:
            g["period"] = x["period"]
            if "target" not in x:
                g["target"] = KINDS[kind]["default"][g["period"]]
        if "target" in x:
            g["target"] = _clean_target(kind, g["period"], x["target"])
        if isinstance(x.get("on"), bool):
            g["on"] = x["on"]
        if gid == "books" and isinstance(x.get("manga"), bool):
            g["manga"] = x["manga"]
        if x.get("main"):
            g["main"], g["on"] = True, True
    for g in cur.values():
        last = g["history"][-1]
        now = {"from": iso, "period": g["period"], "target": g["target"], "on": g["on"]}
        if (last["period"], last["target"], last["on"]) != (g["period"], g["target"], g["on"]):
            if last["from"] == iso and len(g["history"]) > 1:
                g["history"][-1] = now
            elif last["from"] == iso:
                g["history"][-1] = dict(now, **{"from": last["from"]})
            else:
                g["history"].append(now)
    out = [{k: g[k] for k in ("id", "period", "target", "on", "main", "history", "manga") if k in g} for g in cur.values()]
    s = dict(settings, goals=out)
    return all_goals(s), out


# ---- what counts ------------------------------------------------------------------

def _ystart(d):
    b = date(d.year, config.YEAR30_START.month, config.YEAR30_START.day)
    return b if d >= b else date(d.year - 1, b.month, b.day)


def period_range(period, t):
    """(first day, last day) of the period that contains t."""
    if period == "day":
        return t, t
    if period == "week":                                   # Sunday weeks, like the rest of Daf
        a = t - timedelta(days=(t.weekday() + 1) % 7)
        return a, a + timedelta(days=6)
    if period == "month":
        a = t.replace(day=1)
        return a, (a + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    if period == "year":
        return date(t.year, 1, 1), date(t.year, 12, 31)
    if period == "y30":
        a = _ystart(t)
        return a, date(a.year + 1, a.month, a.day) - timedelta(days=1)
    if period == "by35":
        return config.YEAR30_START, YEAR35_START - timedelta(days=1)
    return t, t


def period_words(period, t):
    """(how the goal reads, how the progress reads): ("a week", "this week")."""
    if period == "y30":
        n = 30 + (_ystart(t).year - config.YEAR30_START.year)
        return f"in Year {n}", f"in Year {n}"
    return {"day": ("a day", "today"), "week": ("a week", "this week"), "month": ("a month", "this month"),
            "year": ("a year", f"in {t.year}"), "by35": ("by 35", "since 30"), "run": ("in a row", "now")}[period]


def _epoch(d, tz):
    return int(datetime.combine(d, dtime.min, tz).timestamp())


def pages_by_day(conn, settings, a, b):
    """Pages read per local day, a..b: Kindle pages shown for 5 seconds or more (each page once a
    day), pages in Daf's book reader, and paper pages logged with their minutes."""
    tz = T.tz_of(settings)
    out = defaultdict(int)
    seen = set()
    for md5, page, start in conn.execute("SELECT md5, page, start FROM pages WHERE duration >= 5 AND start >= ? AND start < ?",
                                         (_epoch(a, tz), _epoch(b + timedelta(days=1), tz))):
        d = datetime.fromtimestamp(start, tz).date()
        if (md5, page, d) not in seen:
            seen.add((md5, page, d))
            out[d] += 1
    for day, n in conn.execute("SELECT day, COUNT(*) FROM ebook_pages WHERE day BETWEEN ? AND ? GROUP BY day",
                               (a.isoformat(), b.isoformat())):
        out[date.fromisoformat(day)] += n
    for day, n in conn.execute("SELECT day, SUM(pages) FROM sessions WHERE source = 'paper' AND pages IS NOT NULL "
                               "AND day BETWEEN ? AND ? GROUP BY day", (a.isoformat(), b.isoformat())):
        out[date.fromisoformat(day)] += int(n or 0)
    return out


def finished_books(conn, a, b, manga=False):
    """Books finished between a and b: {key: day}. Hardcover's read dates, and books Daf saw
    reach the end (97% or more) whose last reading falls in the range; one book counts once.
    Manga and comic volumes only if `manga`."""
    out = {}
    row = conn.execute("SELECT v FROM kv WHERE k = 'hardcover'").fetchone()
    if row:
        for ub in json.loads(row[0]).get("books") or []:
            if not manga and VOLUME.search((ub.get("book") or {}).get("title") or ""):
                continue
            for rd in ub.get("user_book_reads") or []:
                f = (rd.get("finished_at") or "")[:10]
                if f and a.isoformat() <= f <= b.isoformat():
                    out[("hc", ub.get("book_id"))] = f
    hm = conn.execute("SELECT v FROM kv WHERE k = 'hc_map'").fetchone()
    hcmap = json.loads(hm[0]) if hm else {}
    tz = T.tz_of(config.load_settings())          # the home time zone, not the server's
    lo, hi = _epoch(a, tz), _epoch(b + timedelta(days=1), tz)
    mangas = {r[0] for r in conn.execute("SELECT book_id FROM manga_books")}
    for bid, last, title in conn.execute("SELECT id, last_read, title FROM books WHERE kind = 'book' AND progress >= 97 "
                                         "AND last_read >= ? AND last_read < ?", (lo, hi)):
        # A volume from the manga library, or a scene-style "v01" title; "Vol. 1" alone may be a light novel.
        if not manga and (bid in mangas or re.search(r"\bv\d{1,3}\b", title or "", re.I)):
            continue
        hid = hcmap.get(bid)
        key = ("hc", hid) if hid else ("daf", bid)
        out.setdefault(key, datetime.fromtimestamp(last, tz).date().isoformat())
    return out


def review_days(conn, a, b):
    """Days between a and b on which the daily review was finished."""
    out = set()
    for day, ids, done in conn.execute("SELECT day, ids, done FROM review_days WHERE day BETWEEN ? AND ?", (a.isoformat(), b.isoformat())):
        ids, done = json.loads(ids), json.loads(done or "{}")
        if ids and all(i in done for i in ids):
            out.add(day)
    return out


def at_goal_days(conn, settings, start, days):
    """Counted minutes per day from `start`, and whether each day met its own daily target."""
    g = T.grid(conn, start, settings, days=days)
    return g, [v >= t for v, t in zip(g["days"], g["targets"])]


def streak_now(conn, settings):
    from . import stats
    return stats.streaks(conn, settings)


def _unit(kind, n):
    one, many = KINDS[kind]["unit"]
    return one if n == 1 else many


def progress(conn, settings, g, t=None, cache=None):
    """How the goal stands in the period containing t: done, target, met, and a line of text."""
    t = t or T.today(settings)
    cache = cache if cache is not None else {}
    kind, period, target = g["kind"], g["period"], g["target"]
    a, b = period_range(period, t)
    upto = min(b, t)
    if kind == "minutes":
        grid = T.grid(conn, a, settings, days=(upto - a).days + 1)
        done = round(sum(grid["days"]))
    elif kind == "pages":
        done = sum(pages_by_day(conn, settings, a, upto).values())
    elif kind == "books":
        done = len(finished_books(conn, a, upto, g.get("manga")))
    elif kind == "days":
        grid = T.grid(conn, a, settings, days=(upto - a).days + 1)
        done = sum(1 for v in grid["days"] if v >= 1)
    elif kind == "streak":
        st = cache.get("streaks") or streak_now(conn, settings)
        cache["streaks"] = st
        done = st["goal"]
    elif kind == "highlights":
        tz = T.tz_of(settings)
        done = conn.execute("SELECT COUNT(*) FROM highlights WHERE deleted = 0 AND created >= ? AND created < ?",
                            (_epoch(a, tz), _epoch(upto + timedelta(days=1), tz))).fetchone()[0]
    elif kind == "reviews":
        done = len(review_days(conn, a, upto))
    else:
        done = 0
    goal_words, now_words = period_words(period, t)
    unit = _unit(kind, target)
    met = done >= target
    if kind == "streak":
        text = f"{done} of {target} days in a row at the goal"
        label = f"{target} days in a row at the goal"
    elif kind == "reviews":
        text = f"The review on {done} of {target} days {now_words}"
        label = f"The review {target} {_unit(kind, target)} {goal_words}"
    elif kind == "days":
        text = f"Reading on {done} of {target} days {now_words}"
        label = f"Reading {target} {unit} {goal_words}"
    else:
        text = f"{done} of {target} {unit} {now_words}"
        label = f"{target} {unit} {goal_words}"
    return {"id": g["id"], "kind": kind, "label": label, "unit": KINDS[kind]["unit"][1], "done": done, "target": target,
            "period": period, "period_label": now_words, "met": met, "main": g["main"], "on": g["on"],
            "pct": round(min(1.0, done / target) * 100) if target else 0, "text": text,
            "key": f"{g['id']}:{a.isoformat()}:{target}", "from": a.isoformat(), "to": b.isoformat()}


def summary(conn, settings, t=None):
    """The goals that are on (and the main one): what /api/today, the widget and the Kindle get."""
    cache = {}
    out = [progress(conn, settings, g, t, cache) for g in all_goals(settings) if g["on"] or g["main"]]
    return out


def main_of(goals_list):
    return next((g for g in goals_list if g["main"]), goals_list[0] if goals_list else None)


# ---- pace, for the live previews ---------------------------------------------------

def pace(conn, settings):
    t = T.today(settings)
    tz = T.tz_of(settings)
    g = T.grid(conn, t - timedelta(days=59), settings, days=60)
    vals = g["days"]
    avg30 = sum(vals[-30:]) / 30
    # Kindle pages per minute, last 60 days.
    rows = conn.execute("SELECT md5, page, start, duration FROM pages WHERE duration >= 5 AND start >= ?",
                        (_epoch(t - timedelta(days=59), tz),)).fetchall()
    secs = sum(r[3] for r in rows)
    pages = len({(r[0], r[1], datetime.fromtimestamp(r[2], tz).date()) for r in rows})
    ppm = round(pages / (secs / 60), 2) if secs >= 1800 else 0.8
    # Minutes per book: prose read on the Kindle at least halfway (40 seconds a page or more, so
    # not manga), scaled up to the whole book. Too few of those, and it's a typical 9-hour book.
    est = []
    digests = {r[0] for r in conn.execute("SELECT md5 FROM kindle_epubs")}
    for md5, s, n, total in conn.execute("SELECT md5, SUM(duration), COUNT(DISTINCT page), MAX(total) FROM pages "
                                          "WHERE duration >= 5 GROUP BY md5"):
        if md5 not in digests and total and total >= 80 and n / total >= 0.5 and s / n >= 40:
            est.append(s / 60 * total / n)
    mpb = round(statistics.median(est)) if len(est) >= 3 else 540
    from . import library
    stand = library.nightstand(conn, settings) or library.suggest_nightstand(conn)
    left = sum(max(0, 100 - (b["progress"] or 0)) / 100 * mpb for b in stand)
    # Days read a week, highlights a week, review days a week (last four and eight weeks).
    sun = t - timedelta(days=(t.weekday() + 1) % 7)
    wk = [sum(1 for v in vals[i:i + 7] if v >= 1) for i in range(len(vals) - 7 - ((t - sun).days + 1), -1, -7)][:4]
    days_week = round(sum(wk) / len(wk), 1) if wk else 0
    since = _epoch(sun - timedelta(weeks=8), tz)
    hl = conn.execute("SELECT COUNT(*) FROM highlights WHERE deleted = 0 AND created >= ? AND created < ?",
                      (since, _epoch(sun, tz))).fetchone()[0]
    rv = len(review_days(conn, sun - timedelta(weeks=4), sun - timedelta(days=1)))
    st = streak_now(conn, settings)
    y30a, _ = period_range("y30", t)
    manga = goal(settings, "books").get("manga")
    return {"avg_day": round(avg30, 1), "week": round(sum(vals[-7:])), "pages_per_minute": ppm, "minutes_per_book": mpb,
            "nightstand_left": round(left), "nightstand_books": len(stand), "days_week": days_week,
            "highlights_week": round(hl / 8, 1), "reviews_week": round(rv / 4, 1),
            "streak": st["goal"], "best_streak": st["best_goal"],
            "books_y30": len(finished_books(conn, y30a, t, manga)), "books_since30": len(finished_books(conn, config.YEAR30_START, t, manga)),
            "book_basis": "your Kindle books" if len(est) >= 3 else "a typical book of about nine hours",
            "today": t.isoformat(), "y30_days_left": (period_range("y30", t)[1] - t).days + 1,
            "days_to_35": (YEAR35_START - t).days}


# ---- milestones ---------------------------------------------------------------------

def milestones(conn, settings):
    """Year 30's milestones: hours, books, streaks at the goal, review days. Each with the
    day it was reached, if it was."""
    t = T.today(settings)
    start = config.YEAR30_START
    if t < start:
        return []
    n = (t - start).days + 1
    g, met = at_goal_days(conn, settings, start, n)
    out = []
    run = 0
    cum = 0.0
    reached_h = {}
    reached_s = {}
    for i, (v, ok) in enumerate(zip(g["days"], met)):
        cum += v
        for h in (10, 50, 100, 200, 365):
            if h not in reached_h and cum / 60 >= h:
                reached_h[h] = (start + timedelta(days=i)).isoformat()
        run = run + 1 if ok else 0
        for s in (7, 30, 100, 365):
            if s not in reached_s and run >= s:
                reached_s[s] = (start + timedelta(days=i)).isoformat()
    hours = round(cum / 60, 1)
    for h in (10, 50, 100, 200, 365):
        out.append({"id": f"hours{h}", "label": f"{h} hours in Year 30", "reached": reached_h.get(h),
                    "done": min(hours, h), "target": h, "family": "hours"})
    fin = sorted(finished_books(conn, start, t, goal(settings, "books").get("manga")).values())
    for b in (1, 10, 25, 50):
        out.append({"id": f"books{b}", "label": "The first book finished in Year 30" if b == 1 else f"{b} books in Year 30",
                    "reached": fin[b - 1] if len(fin) >= b else None, "done": min(len(fin), b), "target": b, "family": "books"})
    best = 0
    run = 0
    for ok in met:
        run = run + 1 if ok else 0
        best = max(best, run)
    for s in (7, 30, 100, 365):
        out.append({"id": f"streak{s}", "label": f"{s} days in a row at the goal", "reached": reached_s.get(s),
                    "done": min(best, s), "target": s, "family": "streak"})
    rd = sorted(review_days(conn, start, t))
    for r in (30, 100):
        out.append({"id": f"review{r}", "label": f"The daily review on {r} days", "reached": rd[r - 1] if len(rd) >= r else None,
                    "done": min(len(rd), r), "target": r, "family": "review"})
    return out
