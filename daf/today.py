"""Days, totals and the year grids, all in the home time zone."""
from collections import defaultdict
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from . import config


def tz_of(settings):
    try:
        return ZoneInfo(settings.get("home_tz") or "America/Phoenix")
    except Exception:  # noqa: BLE001 - a bad name in settings must not break the page
        return ZoneInfo("America/Phoenix")


def today(settings):
    return datetime.now(tz_of(settings)).date()


def beat_start(at, seconds, settings):
    """Where a day's session starts, from its first beat: `seconds` before `at`, but never before
    that day's midnight. A beat just after midnight would otherwise start the session yesterday,
    and every beat added to it that day would count for yesterday too."""
    tz = tz_of(settings)
    midnight = int(datetime.combine(datetime.fromtimestamp(at, tz).date(), dtime.min, tz).timestamp())
    return max(at - seconds, midnight)


def _bounds(d0, d1, tz):
    """Epoch range covering local days d0..d1 inclusive."""
    a = datetime.combine(d0, dtime.min, tz).timestamp()
    b = datetime.combine(d1 + timedelta(days=1), dtime.min, tz).timestamp()
    return int(a), int(b)


def _rows(conn, d0, d1, tz):
    a, b = _bounds(d0, d1, tz)
    return conn.execute(
        "SELECT * FROM sessions WHERE (start >= ? AND start < ?) OR (start IS NULL AND day BETWEEN ? AND ?)",
        (a, b, d0.isoformat(), d1.isoformat())).fetchall()


def _day_of(row, tz):
    if row["start"] is None:
        return date.fromisoformat(row["day"])
    return datetime.fromtimestamp(row["start"], tz).date()


def counted(minutes_by_source, settings):
    return sum(m for s, m in minutes_by_source.items() if settings["count"].get(s))


def day_summary(conn, d, settings):
    tz = tz_of(settings)
    by_source = defaultdict(float)
    items = []
    for r in _rows(conn, d, d, tz):
        if _day_of(r, tz) != d:
            continue
        mins = r["seconds"] / 60
        by_source[r["source"]] += mins
        start = datetime.fromtimestamp(r["start"], tz).strftime("%H:%M") if r["start"] else None
        items.append({
            "source": r["source"],
            "label": config.SOURCE_LABELS.get(r["source"], r["source"]),
            "title": ("Private listening" if r["source"] == "podcast" else "Private reading") if r["private"] else (r["title"] or ""),
            "author": None if r["private"] else r["author"],
            "minutes": round(mins, 1),
            "start": start,
            "note": None if r["private"] else r["note"],
            "counted": bool(settings["count"].get(r["source"])),
            "private": bool(r["private"]),
        })
    items.sort(key=lambda x: (x["start"] or "99:99"))
    minutes = {s: round(by_source.get(s, 0.0), 1) for s in config.SOURCES}
    from . import goals
    return {"date": d.isoformat(), "minutes": minutes, "counted": round(counted(minutes, settings), 1),
            "goal": goals.minutes_day(settings, d), "sessions": items}


def grid(conn, start, settings, days=365):
    """Counted minutes per day for `days` days from `start`, plus totals."""
    tz = tz_of(settings)
    end = start + timedelta(days=days - 1)
    per = defaultdict(float)
    for r in _rows(conn, start, end, tz):
        if settings["count"].get(r["source"]):
            per[_day_of(r, tz)] += r["seconds"] / 60
    vals = [round(per.get(start + timedelta(days=i), 0.0), 1) for i in range(days)]
    from . import goals
    targets = goals.daily_targets(settings, start, days)    # each day judged by the goal it had
    t = today(settings)
    elapsed = max(0, min(days, (t - start).days + 1))
    return {
        "start": start.isoformat(),
        "weekday": start.weekday(),          # Monday = 0
        "days": vals,
        "elapsed": elapsed,
        "today_index": (t - start).days if 0 <= (t - start).days < days else None,
        "total_hours": round(sum(vals) / 60, 1),
        "days_read": sum(1 for v in vals if v >= 1),
        "days_goal": sum(1 for v, g in zip(vals, targets) if v >= g),
        "targets": targets,
    }


def week(conn, settings):
    t = today(settings)
    start = t - timedelta(days=6)
    g = grid(conn, start, settings, days=7)
    return [{"date": (start + timedelta(days=i)).isoformat(), "minutes": g["days"][i], "target": g["targets"][i]} for i in range(7)]


def is_shabbat_window(settings):
    """Friday afternoon through Saturday, local time: the page mentions paper."""
    now = datetime.now(tz_of(settings))
    return (now.weekday() == 4 and now.hour >= 12) or now.weekday() == 5


def last_shabbat(settings):
    t = today(settings)
    back = (t.weekday() - 5) % 7      # Saturday = 5
    return t - timedelta(days=back)
