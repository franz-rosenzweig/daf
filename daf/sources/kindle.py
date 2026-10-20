"""Kindle reading time.

Page turns arrive two ways and land in the same `pages` table, keyed by
(book md5, start), so the same turn counted by both is stored once:

- KoInsight's database (history, and whatever its KOReader plugin last synced);
- the Daf KOReader plugin, which posts new turns when the Kindle goes to sleep.

Sessions are rebuilt from pages on every sync: consecutive turns in one book
with less than SESSION_GAP_SECONDS between them are one sitting.
"""
from .. import config
from ..db import read_only

ORIGIN_KOINSIGHT = "koinsight"
ORIGIN_PLUGIN = "plugin"


def import_koinsight(conn):
    """Copy KoInsight's page turns and book titles. Returns (rows seen, newest start)."""
    if not config.KOINSIGHT_DB.exists():
        raise FileNotFoundError(config.KOINSIGHT_DB)
    src = read_only(config.KOINSIGHT_DB)
    try:
        books = src.execute("SELECT md5, title, authors FROM book WHERE md5 IS NOT NULL").fetchall()
        pages = src.execute("SELECT book_md5, start_time, duration, page, total_pages FROM page_stat").fetchall()
    finally:
        src.close()
    conn.executemany(
        "INSERT INTO kindle_books (md5, title, authors) VALUES (?, ?, ?) "
        "ON CONFLICT(md5) DO UPDATE SET title = excluded.title, authors = excluded.authors",
        [(m, t, a) for m, t, a in books])
    conn.executemany(
        "INSERT OR IGNORE INTO pages (md5, start, duration, page, total, origin) VALUES (?, ?, ?, ?, ?, ?)",
        [(m, s, d, p, t, ORIGIN_KOINSIGHT) for m, s, d, p, t in pages if m and s and d])
    newest = max((p[1] for p in pages), default=None)
    return len(pages), newest


def ingest_plugin(conn, books, pages):
    """Store what the Daf KOReader plugin sent. Returns how many turns were new."""
    for b in books or []:
        md5 = (b.get("md5") or "").strip()
        if not md5:
            continue
        conn.execute(
            "INSERT INTO kindle_books (md5, title, authors) VALUES (?, ?, ?) "
            "ON CONFLICT(md5) DO UPDATE SET title = COALESCE(excluded.title, title), "
            "authors = COALESCE(excluded.authors, authors)",
            (md5, b.get("title"), b.get("authors")))
    before = conn.total_changes
    rows = []
    for p in pages or []:
        try:
            md5, start, dur = str(p["md5"]), int(p["start"]), int(p["duration"])
        except (KeyError, TypeError, ValueError):
            continue
        if md5 and start > 0 and 0 < dur <= 3600:
            rows.append((md5, start, dur, p.get("page"), p.get("total"), ORIGIN_PLUGIN))
    conn.executemany(
        "INSERT OR IGNORE INTO pages (md5, start, duration, page, total, origin) VALUES (?, ?, ?, ?, ?, ?)", rows)
    return conn.total_changes - before


def rebuild_sessions(conn):
    """Turn page turns into sittings. Returns the number of sessions written.

    An EPUB from Send to Kindle is split by article: its sittings are article reading (each
    titled by its article), and how far the pages went sets each article's progress."""
    from .. import kindlesend, library
    titles = {r["md5"]: (r["title"], r["authors"]) for r in conn.execute("SELECT md5, title, authors FROM kindle_books")}
    private = {r[0][4:] for r in conn.execute(
        "SELECT k.key FROM book_keys k JOIN books b ON b.id = k.book_id WHERE k.key LIKE 'md5:%' AND b.private = 1")}
    daf_epubs = kindlesend.epubs(conn)
    manga_series = {k[4:]: n for k, n in conn.execute(
        "SELECT k.key, m.series_name FROM manga_books m JOIN book_keys k ON k.book_id = m.book_id WHERE k.key LIKE 'md5:%' AND m.series_name != ''")}
    rows = conn.execute("SELECT md5, start, duration, page, total FROM pages ORDER BY md5, start").fetchall()
    sessions, cur, reached = [], None, {}
    for r in rows:
        doc = None
        if r["md5"] in daf_epubs:
            at = kindlesend.part_at(daf_epubs[r["md5"]], r["page"], r["total"])
            if not at:
                continue
            doc = at[0]
            prev = reached.get(doc)
            reached[doc] = (max(prev[0], at[1]) if prev else at[1], min(prev[1], r["start"]) if prev else r["start"])
        if cur and r["md5"] == cur["md5"] and doc == cur["doc"] and r["start"] - cur["end"] <= config.SESSION_GAP_SECONDS:
            cur["seconds"] += r["duration"]
            cur["end"] = max(cur["end"], r["start"] + r["duration"])
            cur["last_page"], cur["total"] = r["page"], r["total"]
            continue
        if cur:
            sessions.append(cur)
        cur = {"md5": r["md5"], "doc": doc, "start": r["start"], "end": r["start"] + r["duration"],
               "seconds": r["duration"], "last_page": r["page"], "total": r["total"]}
    if cur:
        sessions.append(cur)
    conn.execute("DELETE FROM sessions WHERE origin = 'kindle'")
    docs = {}
    if reached:
        ids = list(reached)
        for i in range(0, len(ids), 400):
            chunk = ids[i:i + 400]
            docs.update({d["id"]: d for d in conn.execute(
                f"SELECT id, title, source, category FROM docs WHERE id IN ({','.join('?' * len(chunk))})", chunk)})
    settings = config.load_settings()
    out = []
    for s in sessions:
        if s["doc"]:
            d = docs.get(s["doc"])
            if not d:
                continue
            hidden = library.is_private(f"{d['title']} {d['source'] or ''} {d['category'] or ''}", settings)
            out.append((f"kindle:{s['md5']}:{s['start']}", "article", "kindle", s["doc"], d["title"], d["source"],
                        s["start"], s["seconds"], None, 1 if hidden else 0, "on the Kindle"))
            continue
        title, authors = titles.get(s["md5"], (None, None))
        where = f"page {s['last_page']} of {s['total']}" if s["last_page"] and s["total"] else None
        if s["md5"] in manga_series:              # a manga volume: the series, with the volume in the note
            vol, title, authors = title, manga_series[s["md5"]], None
            where = " · ".join(x for x in (vol, where) if x)
        out.append((f"kindle:{s['md5']}:{s['start']}", "kindle", "kindle", s["md5"], title or "Unknown book",
                    None if authors in (None, "N/A") else authors, s["start"], s["seconds"], None,
                    1 if s["md5"] in private else 0, where))
    conn.executemany(
        "INSERT INTO sessions (id, source, origin, item, title, author, start, seconds, day, private, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", out)
    # An article read on the Kindle is opened, and as far along as its last page there.
    for doc, (frac, first) in reached.items():
        if doc in docs:
            conn.execute("UPDATE docs SET opened = COALESCE(opened, ?), progress = MAX(COALESCE(progress, 0), ?) WHERE id = ?",
                         (first, round(100 * frac, 1), doc))
    return len(out)


def newest_by_origin(conn):
    return {r["origin"]: r["m"] for r in conn.execute("SELECT origin, MAX(start) AS m FROM pages GROUP BY origin")}
