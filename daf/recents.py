"""Recents (web/recents.js): what was read, watched, listened to or opened, newest first, a day at a
time in the home time zone.

A day's rows come from its sittings (sessions: one row an item a day, from every source) and from
what was opened in Daf without a sitting (docs.opened, books.last_read: both only the last time).
Each item shows once a day, at the last time it was touched. A private sitting keeps Today's words
("Private reading") and no link."""
from datetime import date, datetime, timedelta

from . import config
from .today import _bounds, tz_of, today

KINDS = {"kindle": "Kindle", "ebook": "Book", "manga": "Manga", "audio": "Audiobook", "article": "Article",
         "paper": "Paper", "podcast": "Podcast", "video": "Video"}


def _doc(conn, doc_id):
    return conn.execute("SELECT id, kind, title, author, source, thumb FROM docs WHERE id = ?", (doc_id,)).fetchone()


def _book_pic(conn, book_id):
    b = conn.execute("SELECT calibre_path FROM books WHERE id = ?", (book_id,)).fetchone()
    return f"/api/cover/{book_id}" if b and b["calibre_path"] else None


def _where(conn, src, item):
    """Where a sitting's item opens in Daf, and its picture: (go, pic)."""
    if not item:
        return ("paper", None) if src == "paper" else (None, None)
    if src in ("article", "video"):
        d = _doc(conn, item)
        return "read/" + item, d["thumb"] if d else None
    if src == "ebook":
        return "book/" + item, _book_pic(conn, item)
    if src == "kindle":
        k = conn.execute("SELECT book_id FROM book_keys WHERE key = ?", ("md5:" + item,)).fetchone()
        return ("book/" + k["book_id"], _book_pic(conn, k["book_id"])) if k else (None, None)
    if src == "manga":
        return "mread/" + item, None
    if src == "podcast":
        d = conn.execute("SELECT id, thumb FROM docs WHERE id = ? OR enclosure = ? LIMIT 1", (item, item)).fetchone()
        return ("read/" + d["id"], d["thumb"]) if d else ("podcasts", None)
    if src == "audio":
        return "podcasts/audiobooks", None
    return None, None


def days(conn, settings, before=None, n=7):
    """Up to n days with something in them, newest first, before the day `before` (ISO; default:
    after today). → {"days": [{"date", "items": [...]}], "next": ISO day to ask with, or None}."""
    tz = tz_of(settings)
    end = date.fromisoformat(before) - timedelta(days=1) if before else today(settings)
    start = end - timedelta(days=n - 1)
    a, b = _bounds(start, end, tz)
    rows = {}            # (day, key) -> row; the last touch wins

    def put(day, key, row):
        old = rows.get((day, key))
        if old is None or row["at"] > old["at"]:
            if old and old.get("minutes") and not row.get("minutes"):
                row["minutes"] = old["minutes"]
            rows[(day, key)] = row
        elif row.get("minutes") and not old.get("minutes"):
            old["minutes"] = row["minutes"]

    for r in conn.execute("SELECT * FROM sessions WHERE start >= ? AND start < ?", (a, b)):
        at = int(r["start"] + (r["seconds"] or 0))
        day = datetime.fromtimestamp(r["start"], tz).date().isoformat()
        private = bool(r["private"])
        go, pic = (None, None) if private else _where(conn, r["source"], r["item"])
        key = go or f"{r['source']}:{r['item'] or r['id']}"
        put(day, key, {
            "at": at, "kind": KINDS.get(r["source"], config.SOURCE_LABELS.get(r["source"], r["source"])),
            "title": ("Private listening" if r["source"] == "podcast" else "Private reading") if private else (r["title"] or ""),
            "author": None if private else r["author"], "minutes": round((r["seconds"] or 0) / 60),
            "go": go, "pic": pic, "private": private})

    from . import reader
    for d in conn.execute("SELECT id, kind, title, author, source, thumb, opened, where_, url FROM docs "
                          "WHERE opened >= ? AND opened < ? AND (deleted IS NULL OR deleted = 0)", (a, b)):
        if reader.library_copy(conn, d):          # a saved Feed item opens its Library copy: that one's listed
            continue
        day = datetime.fromtimestamp(d["opened"], tz).date().isoformat()
        kind = "Podcast" if d["id"].startswith("ep:") else KINDS.get(d["kind"], (d["kind"] or "").title() or "Article")
        put(day, "read/" + d["id"], {"at": int(d["opened"]), "kind": kind, "title": d["title"] or "",
                                     "author": d["author"] or d["source"], "minutes": 0, "go": "read/" + d["id"],
                                     "pic": d["thumb"], "private": False})

    for bk in conn.execute("SELECT id, title, author, calibre_path, private, last_read FROM books "
                           "WHERE last_read >= ? AND last_read < ?", (a, b)):
        if bk["private"]:
            continue
        day = datetime.fromtimestamp(bk["last_read"], tz).date().isoformat()
        put(day, "book/" + bk["id"], {"at": int(bk["last_read"]), "kind": "Book", "title": bk["title"] or "",
                                      "author": bk["author"], "minutes": 0, "go": "book/" + bk["id"],
                                      "pic": f"/api/cover/{bk['id']}" if bk["calibre_path"] else None, "private": False})

    out = {}
    for (day, _), row in rows.items():
        row["time"] = datetime.fromtimestamp(row["at"], tz).strftime("%H:%M")
        out.setdefault(day, []).append(row)
    listed = [{"date": d, "items": sorted(out[d], key=lambda x: -x["at"])} for d in sorted(out, reverse=True)]
    older = conn.execute("SELECT 1 FROM sessions WHERE start < ? LIMIT 1", (a,)).fetchone() or \
        conn.execute("SELECT 1 FROM docs WHERE opened < ? LIMIT 1", (a,)).fetchone()
    return {"days": listed, "next": start.isoformat() if older else None}
