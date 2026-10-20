"""Listening time from Audiobookshelf, read the same way audiobookshelf-sync.py reads it:
the SQLite file, read-only.

Audiobooks count toward the hour. The Podcasts library is speaker talks, so those
sessions are stored as private, never named on any screen, and never counted.
"""
from datetime import datetime, timezone

from .. import config
from ..db import read_only


def _epoch(ts):
    # ABS writes "2026-09-13 15:24:40.858 +00:00"
    return int(datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())


def import_sessions(conn):
    if not config.ABS_DB.exists():
        raise FileNotFoundError(config.ABS_DB)
    src = read_only(config.ABS_DB)
    try:
        user = src.execute("SELECT id FROM users WHERE username = ?", (config.ABS_USER,)).fetchone()
        if not user:
            raise LookupError(f"no Audiobookshelf user {config.ABS_USER}")
        rows = src.execute(
            "SELECT id, mediaItemType, mediaItemId, displayTitle, displayAuthor, timeListening, createdAt, currentTime "
            "FROM playbackSessions WHERE userId = ? AND timeListening > 0", (user[0],)).fetchall()
    finally:
        src.close()
    conn.execute("DELETE FROM sessions WHERE origin = 'audiobookshelf'")
    out, newest = [], None
    for sid, kind, item, title, author, secs, created, pos in rows:
        try:
            start = _epoch(created)
        except (TypeError, ValueError):
            continue
        newest = max(newest or 0, start)
        is_book = kind == "book"
        out.append((f"abs:{sid}", "audio" if is_book else "podcast", "audiobookshelf", item,
                    title if is_book else None, author if is_book else None,
                    start, int(secs), None, 0 if is_book else 1, None))
    conn.executemany(
        "INSERT INTO sessions (id, source, origin, item, title, author, start, seconds, day, private, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", out)
    return len(out), newest
