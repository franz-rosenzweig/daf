"""A book's reading stats, the way BookOrbit shows them: time across the Kindle, Daf's reader and
the audiobook, sittings, the last 30 days, pace, and when it'll be done at that pace."""
from collections import defaultdict
from datetime import datetime, timedelta

from . import today as T


def _sessions(conn, book_id):
    """Every session of this book: Kindle copies (md5), Audiobookshelf items, and Daf's reader."""
    keys = [k for (k,) in conn.execute("SELECT key FROM book_keys WHERE book_id = ?", (book_id,))]
    md5s = [k[4:] for k in keys if k.startswith("md5:")]
    abs_ids = [k[4:] for k in keys if k.startswith("abs:")]
    out = []
    for src, items in (("kindle", md5s), ("audio", abs_ids), ("ebook", [book_id])):
        if not items:
            continue
        out += [dict(r) for r in conn.execute(
            f"SELECT source, start, seconds, day FROM sessions WHERE source = ? AND item IN ({','.join('?' * len(items))})",
            (src, *items))]
    return out, md5s


def stats(conn, settings, book_id, progress=None, daf_fraction=None):
    tz = T.tz_of(settings)
    t = T.today(settings)
    rows, md5s = _sessions(conn, book_id)
    if not rows:
        return None
    by_src = defaultdict(float)
    per_day = defaultdict(float)
    starts = []
    for r in rows:
        m = r["seconds"] / 60
        by_src[r["source"]] += m
        d = datetime.fromtimestamp(r["start"], tz).date() if r["start"] else datetime.fromisoformat(r["day"]).date()
        per_day[d] += m
        starts.append(d)
    total = sum(by_src.values())
    last30 = [round(per_day.get(t - timedelta(days=29 - i), 0.0), 1) for i in range(30)]
    out = {"minutes": round(total), "by_source": {k: round(v) for k, v in by_src.items()}, "sittings": len(rows),
           "days": len(per_day), "first": min(starts).isoformat(), "last": max(starts).isoformat(), "last30": last30}
    # Pace on the Kindle: pages an hour, from page turns of five seconds or more.
    if md5s:
        q = f"SELECT page, total, duration FROM pages WHERE md5 IN ({','.join('?' * len(md5s))}) AND duration >= 5"
        pg = conn.execute(q, md5s).fetchall()
        secs = sum(r[2] for r in pg)
        if secs >= 1800:
            out["pages_per_hour"] = round(len({r[0] for r in pg}) / (secs / 3600))
    # Time left: from the share already read and the time it took (reading only, not listening).
    frac = None
    if daf_fraction is not None and daf_fraction > 0.02:
        frac = daf_fraction
    elif progress is not None and progress > 2:
        frac = progress / 100
    read_min = by_src.get("kindle", 0) + by_src.get("ebook", 0)
    if frac and frac < 0.985 and read_min >= 20:
        left = read_min / frac * (1 - frac)
        out["minutes_left"] = round(left)
        recent = sum(last30[-14:]) / 14
        if recent >= 2:
            out["finish"] = (t + timedelta(days=max(1, round(left / recent)))).isoformat()
            out["recent_per_day"] = round(recent)
    return out
