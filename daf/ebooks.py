"""Books from the Calibre library, read in Daf.

The browser does the rendering (foliate-js, vendored in web/vendor/foliate-js); Daf serves
the file, keeps the reading position (an EPUB CFI and a fraction) so the phone and the
desktop pick up where the other left off, and keeps highlights made here (source 'epub',
anchored by CFI). Those join the daily review and go into the book's vault note, like
paper pages. Time with a book open counts as "Books in Daf".
"""
import hashlib
import html
import json
import re
import time
from datetime import datetime

from . import config, today as T, vaultnotes
from .db import read_only

FORMATS = ["EPUB", "KEPUB", "AZW3", "MOBI", "FB2", "CBZ"]
MIME = {"EPUB": "application/epub+zip", "KEPUB": "application/epub+zip", "AZW3": "application/vnd.amazon.ebook",
        "MOBI": "application/x-mobipocket-ebook", "FB2": "application/x-fictionbook+xml", "CBZ": "application/vnd.comicbook+zip"}


def _calibre(conn, book_id):
    b = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if not b or not b["calibre_id"]:
        return None, None
    return b, config.CALIBRE_DBS[0]


def book_file(conn, book_id):
    """(path, format) of the best readable file for a book, or (None, None)."""
    b, db = _calibre(conn, book_id)
    if not b:
        return None, None
    c = read_only(db)
    try:
        bp = c.execute("SELECT path FROM books WHERE id = ?", (b["calibre_id"],)).fetchone()
        files = {r[1].upper(): r[0] for r in c.execute("SELECT name, format FROM data WHERE book = ?", (b["calibre_id"],))}
    finally:
        c.close()
    if not bp:
        return None, None
    for fmt in FORMATS:
        if fmt in files:
            ext = "kepub" if fmt == "KEPUB" else fmt.lower()
            p = db.parent / bp[0] / f"{files[fmt]}.{ext}"
            if p.exists():
                return p, fmt
    return None, None


def readable_ids(conn):
    """Daf book ids that have a file the reader can open."""
    db = config.CALIBRE_DBS[0]
    c = read_only(db)
    try:
        cal = {r[0] for r in c.execute(f"SELECT DISTINCT book FROM data WHERE upper(format) IN ({','.join('?' * len(FORMATS))})", FORMATS)}
    finally:
        c.close()
    return {r[0] for r in conn.execute("SELECT id, calibre_id FROM books WHERE calibre_id IS NOT NULL") if r[1] in cal}


def _calibre_details(db, cid):
    c = read_only(db)
    try:
        com = c.execute("SELECT text FROM comments WHERE book = ?", (cid,)).fetchone()
        lang = c.execute("SELECT l.lang_code FROM books_languages_link bl JOIN languages l ON l.id = bl.lang_code "
                         "WHERE bl.book = ? ORDER BY bl.item_order LIMIT 1", (cid,)).fetchone()
        pub = c.execute("SELECT pubdate FROM books WHERE id = ?", (cid,)).fetchone()
    finally:
        c.close()
    desc = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", com[0]))).strip() if com and com[0] else ""
    year = pub[0][:4] if pub and pub[0] and not pub[0].startswith("0101") else None
    return {"description": desc, "language": lang[0] if lang else None, "year": year}


def series(conn, db, cid):
    """The book's series in Calibre, and the next book in it that Calibre has."""
    c = read_only(db)
    try:
        r = c.execute("SELECT s.id, s.name, b.series_index FROM books_series_link l JOIN series s ON s.id = l.series "
                      "JOIN books b ON b.id = l.book WHERE l.book = ?", (cid,)).fetchone()
        if not r:
            return None
        nxt = c.execute("SELECT b.id, b.title, b.series_index FROM books_series_link l JOIN books b ON b.id = l.book "
                        "WHERE l.series = ? AND b.series_index > ? ORDER BY b.series_index LIMIT 1", (r[0], r[2])).fetchone()
    finally:
        c.close()
    out = {"name": r[1], "index": r[2], "next": None}
    if nxt and conn.execute("SELECT 1 FROM books WHERE id = ?", (f"cal:{nxt[0]}",)).fetchone():
        out["next"] = {"id": f"cal:{nxt[0]}", "title": nxt[1], "index": nxt[2]}
    return out


def details(conn, book_id):
    b, db = _calibre(conn, book_id)
    if not b:
        return None
    path, fmt = book_file(conn, book_id)
    out = {"id": b["id"], "title": b["title"], "author": b["author"], "private": bool(b["private"]), "format": fmt,
           "size": path.stat().st_size if path else None, "has_cover": bool(b["calibre_path"]),
           "vault_path": b["vault_path"], **_calibre_details(db, b["calibre_id"]),
           "series": series(conn, db, b["calibre_id"])}
    pos = conn.execute("SELECT cfi, fraction, chapter, updated FROM book_positions WHERE book_id = ?", (book_id,)).fetchone()
    out["position"] = dict(pos) if pos else None
    out["highlights"] = [dict(r) | {"pos": json.loads(r["pos"]) if r["pos"] else {}} for r in conn.execute(
        "SELECT h.id, h.text, h.chapter, h.pos, h.created, h.color, h.source, s.user_note, s.tags, s.fav FROM highlights h "
        "LEFT JOIN review_state s ON s.hl_id = h.id WHERE h.book_id = ? AND h.source = 'epub' AND h.deleted = 0 ORDER BY h.created", (book_id,))]
    out["other_highlights"] = [dict(r) for r in conn.execute(
        "SELECT h.id, h.text, h.note, h.chapter, h.page, h.source, h.created, h.pos, h.color, s.user_note, s.tags, s.fav FROM highlights h "
        "LEFT JOIN review_state s ON s.hl_id = h.id WHERE h.book_id = ? AND h.source != 'epub' AND h.deleted = 0 "
        "ORDER BY COALESCE(h.page, 0), h.created", (book_id,))]
    for h in out["highlights"] + out["other_highlights"]:
        h["tags"] = json.loads(h["tags"]) if h.get("tags") else []
        h["fav"] = bool(h.get("fav"))
    for h in out["other_highlights"]:
        p = h.pop("pos", None)
        if p and p.startswith("{"):
            try:
                h["t"] = json.loads(p).get("t")
            except ValueError:
                pass
        elif p:
            h["xp"] = p
    out["bookmarks"] = [dict(r) for r in conn.execute(
        "SELECT id, cfi, fraction, chapter, excerpt, created FROM book_marks WHERE book_id = ? ORDER BY fraction", (book_id,))]
    md5s = [k[4:] for (k,) in conn.execute("SELECT key FROM book_keys WHERE book_id = ? AND key LIKE 'md5:%'", (book_id,))]
    k = conn.execute(f"SELECT page, total, start FROM pages WHERE md5 IN ({','.join('?' * len(md5s))}) ORDER BY start DESC LIMIT 1",
                     md5s).fetchone() if md5s else None
    out["kindle"] = {"page": k["page"], "total": k["total"], "fraction": round(k["page"] / k["total"], 4) if k["total"] else None,
                     "at": k["start"]} if k else None
    secs = conn.execute("SELECT COALESCE(SUM(seconds), 0) FROM sessions WHERE source = 'ebook' AND item = ?", (book_id,)).fetchone()[0]
    out["minutes_here"] = round(secs / 60)
    return out


def when(at):
    """When something was done: `at` from a device that was offline (its outbox sends it later),
    within the past week; otherwise now."""
    now = int(time.time())
    try:
        at = int(at)
    except (TypeError, ValueError):
        return now
    return at if now - 7 * 86400 <= at <= now + 60 else now


def add_bookmark(conn, book_id, cfi, fraction=None, chapter=None, excerpt=None, at=None):
    if not cfi:
        raise ValueError("No place to mark")
    bid = "m" + hashlib.sha1(f"{book_id}|{cfi}".encode()).hexdigest()[:15]
    conn.execute("INSERT OR REPLACE INTO book_marks (id, book_id, cfi, fraction, chapter, excerpt, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (bid, book_id, cfi, fraction, (chapter or "")[:200] or None, (excerpt or "").strip()[:200] or None, when(at)))
    return bid


def save_position(conn, book_id, cfi, fraction, chapter=None, at=None):
    """A device's place in the book. One sent late (made offline) doesn't replace a newer one,
    from the Kindle or another device. Returns whether it was kept."""
    t = when(at)
    cur = conn.execute("INSERT INTO book_positions (book_id, cfi, fraction, chapter, updated) VALUES (?, ?, ?, ?, ?) "
                       "ON CONFLICT(book_id) DO UPDATE SET cfi = excluded.cfi, fraction = excluded.fraction, "
                       "chapter = excluded.chapter, updated = excluded.updated WHERE excluded.updated >= book_positions.updated",
                       (book_id, cfi, max(0.0, min(1.0, float(fraction or 0))), (chapter or "")[:200] or None, t))
    return cur.rowcount > 0


def add_highlight(conn, settings, book_id, cfi, text, chapter=None, fraction=None, note=None, color=None, replaces=None, at=None):
    text = (text or "").strip()
    if not text or not cfi:
        raise ValueError("Nothing selected")
    hid = "e" + hashlib.sha1(f"{book_id}|{cfi}".encode()).hexdigest()[:16]
    from .reader import COLORS
    conn.execute("INSERT OR REPLACE INTO highlights (id, book_id, source, text, note, chapter, page, created, pos, seen, deleted, color) "
                 "VALUES (?, ?, 'epub', ?, NULL, ?, NULL, ?, ?, ?, 0, ?)",
                 (hid, book_id, text, (chapter or "")[:200] or None, when(at),
                  json.dumps({"cfi": cfi, "fraction": fraction}), int(time.time()), color if color in COLORS else None))
    from . import review
    review.carry(conn, hid, replaces, own=("epub",))
    if note:
        review.set_note(conn, hid, note)
    vaultnotes.write_book(conn, settings, book_id, create=True)
    return hid


def beat(conn, settings, book_id, seconds, at=None):
    """Reading time with a book open in Daf: one session per book per day."""
    seconds = max(0, min(90, int(seconds)))
    b = conn.execute("SELECT title, author, private FROM books WHERE id = ?", (book_id,)).fetchone()
    if not seconds or not b:
        return
    now = int(time.time())
    try:
        at = int(at) if at is not None else now
    except (TypeError, ValueError):
        at = now
    if not (now - 7 * 86400 <= at <= now + 60):
        at = now
    day = datetime.fromtimestamp(at, T.tz_of(settings)).date().isoformat()
    sid = f"ebk:{book_id}:{day}"
    # One statement, so two first beats at once can't both try to make the session.
    conn.execute("INSERT INTO sessions (id, source, origin, item, title, author, start, seconds, day, private, note) "
                 "VALUES (?, 'ebook', 'daf-read', ?, ?, ?, ?, ?, NULL, ?, NULL) "
                 "ON CONFLICT(id) DO UPDATE SET seconds = seconds + excluded.seconds",
                 (sid, book_id, b["title"], b["author"], T.beat_start(at, seconds, settings), seconds, int(b["private"] or 0)))


def ask(conn, book_id, question, quote=None, context=None):
    from . import ai
    b = conn.execute("SELECT title, author FROM books WHERE id = ?", (book_id,)).fetchone()
    if not b:
        raise KeyError(book_id)
    prompt = (f"I'm reading {b['title']}" + (f" by {b['author']}" if b["author"] else "") + ".\n\n"
              + (f"Around where I am:\n\"\"\"\n{(context or '')[:6000]}\n\"\"\"\n\n" if context else "")
              + (f"The passage I selected:\n\"\"\"\n{quote[:2000]}\n\"\"\"\n\n" if quote else "")
              + f"{question}\n\n" + ai.prompt("ask_book"))
    a = ai.run(prompt, timeout=120)
    conn.execute("INSERT INTO asks (doc_id, q, quote, a, at) VALUES (?, ?, ?, ?, ?)", (book_id, question, quote, a, int(time.time())))
    return a
