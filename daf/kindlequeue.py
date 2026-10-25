"""What's waiting for the Kindle: books sent from Daf (a book's page → Put it on the Kindle, or Add a
book with its file) and Send to Kindle's articles.

Syncthing is off on the Kindle, so nothing reaches it by itself any more: the Daf plugin asks for
this list on its Wi-Fi sync (GET /api/kindle/inbox), downloads each file into its shelf in the
Kindle's home folder (Libros/<shelf>), and says so (POST …/done). The plugin also tells Daf which
shelves the Kindle has (POST /api/kindle/shelves), so the shelf menu in Daf is the Kindle's own.
A book still waiting for its file (sent to Calibre-Web, not in Calibre yet) is queued by `follow_up`
once Calibre has it.
"""
import json
import re
import time
from pathlib import Path

from . import config

DEFAULT_SHELF = "Books"


def _safe(s, n=110):
    s = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", s or "").strip().strip(".")
    return re.sub(r"\s+", " ", s)[:n] or "Book"


def shelves(conn):
    """The Kindle's shelves (folders in its home folder), as its plugin last reported them."""
    row = conn.execute("SELECT v FROM kv WHERE k = 'kindle_shelves'").fetchone()
    names = json.loads(row[0]).get("shelves", []) if row and row[0] else []
    return names or [DEFAULT_SHELF, "Nightstand"]


def set_shelves(conn, names):
    names = [_safe(str(n), 60) for n in names if isinstance(n, str) and n.strip() and not n.startswith(".")][:60]
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('kindle_shelves', ?)", (json.dumps({"shelves": names, "at": int(time.time())}),))
    return names


def _shelf(name):
    name = _safe(name or DEFAULT_SHELF, 60)
    return name if name and name not in (".", "..") else DEFAULT_SHELF


def queue_book(conn, book_id, shelf=None):
    """The book's Calibre file to the Kindle. Raises LookupError when Daf has no file for it yet."""
    from . import ebooks
    path, fmt = ebooks.book_file(conn, book_id)
    if not path:
        raise LookupError("Daf doesn't have this book's file yet")
    b = conn.execute("SELECT title, author, calibre_id FROM books WHERE id = ?", (book_id,)).fetchone()
    # as the Kindle's books have been named: "Title - Author (<Calibre id>).epub"
    name = _safe(f"{b['title']} - {b['author']}" if b["author"] else b["title"]) + f" ({b['calibre_id']})" + Path(path).suffix.lower()
    conn.execute("INSERT OR REPLACE INTO kindle_queue (id, kind, ref, name, shelf, path, size, requested, delivered, error) "
                 "VALUES (?, 'book', ?, ?, ?, ?, ?, ?, NULL, NULL)",
                 (f"book:{book_id}", book_id, name, _shelf(shelf), str(path), Path(path).stat().st_size, int(time.time())))
    return state(conn, book_id)


def queue_file(conn, path, shelf="Daf"):
    """A file Daf made (Send to Kindle's EPUB of articles)."""
    p = Path(path)
    conn.execute("INSERT OR REPLACE INTO kindle_queue (id, kind, ref, name, shelf, path, size, requested, delivered, error) "
                 "VALUES (?, 'file', ?, ?, ?, ?, ?, ?, NULL, NULL)",
                 (f"file:{p.name}", p.name, p.name, _shelf(shelf), str(p), p.stat().st_size, int(time.time())))


def cancel(conn, book_id):
    conn.execute("DELETE FROM kindle_queue WHERE id = ? AND (delivered IS NULL OR error IS NOT NULL)", (f"book:{book_id}",))


def state(conn, book_id):
    r = conn.execute("SELECT shelf, requested, delivered, error, name FROM kindle_queue WHERE id = ?", (f"book:{book_id}",)).fetchone()
    return dict(r) if r else None


def inbox(conn):
    """For the plugin: what to download, oldest first. One the plugin turned down (a different file by
    that name on the Kindle, too big, no room) isn't offered again until it's sent again from Daf: a
    download that failed on the way never reaches /done, so an error here is always a refusal."""
    out = []
    for r in conn.execute("SELECT * FROM kindle_queue WHERE delivered IS NULL AND error IS NULL ORDER BY requested").fetchall():
        if not Path(r["path"]).exists():
            conn.execute("UPDATE kindle_queue SET error = ? WHERE id = ?", ("The file isn't on the server any more", r["id"]))
            continue
        out.append({"id": r["id"], "name": r["name"], "shelf": r["shelf"], "size": r["size"]})
    return out


def file_for(conn, qid):
    r = conn.execute("SELECT path, name FROM kindle_queue WHERE id = ?", (qid,)).fetchone()
    return (Path(r["path"]), r["name"]) if r and Path(r["path"]).exists() else (None, None)


def done(conn, qid, where=None, error=None):
    if error:
        conn.execute("UPDATE kindle_queue SET error = ? WHERE id = ?", (str(error)[:300], qid))
    else:
        conn.execute("UPDATE kindle_queue SET delivered = ?, error = NULL, path = path WHERE id = ?", (int(time.time()), qid))
    return conn.execute("SELECT changes()").fetchone()[0] > 0


def follow_up(conn):
    """Books that were to go to the Kindle once their file arrived (Add a book, a file sent from Daf)."""
    want = {}
    for r in conn.execute("SELECT b.id, f.kindle_shelf FROM book_files f JOIN books b ON b.calibre_id = f.cal_id "
                          "WHERE f.kindle_shelf IS NOT NULL AND f.cal_id IS NOT NULL"):
        want[r["id"]] = r["kindle_shelf"]
    for r in conn.execute("SELECT b.id, a.kindle_shelf FROM book_adds a JOIN books b ON b.hc_id = a.hc_id "
                          "WHERE a.kindle_shelf IS NOT NULL AND b.calibre_id IS NOT NULL"):
        want.setdefault(r["id"], r["kindle_shelf"])
    for book_id, shelf in want.items():
        if conn.execute("SELECT 1 FROM kindle_queue WHERE id = ?", (f"book:{book_id}",)).fetchone():
            continue
        try:
            queue_book(conn, book_id, shelf)
        except (LookupError, OSError):
            pass                                # not converted yet: the next sync looks again
