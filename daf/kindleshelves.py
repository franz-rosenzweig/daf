"""The Kindle's shelves in Daf, both ways.

The Kindle's shelves are the folders in its home folder (the Daf plugin's Shelves screen). On each
Wi-Fi sync the plugin reports them, and every book in them: its path from the home folder and its
KOReader fingerprint (the partial MD5 Daf already knows a Kindle book by, book_keys). Each folder
is a shelf in Daf (shelves.kindle = the folder) holding the Daf books found in it, so Daf's Books
has the Kindle's shelves as they are. A folder gone from the Kindle takes its shelf with it.

The other way: a book put on a Kindle shelf in Daf moves there on the Kindle at its next sync (the
plugin moves it with KOReader's own bookkeeping, so its notes, history and collections go with
it), or is sent there when it isn't on the Kindle yet (kindlequeue). One taken off a Kindle shelf
goes to the Kindle's home folder. A book on the Kindle is on one shelf, as a file is in one
folder. Until the plugin has made a move, or brought a book in, the report doesn't undo it.

Shelves are made, renamed and removed on the Kindle; Daf's own shelves stay Daf's.
"""
import hashlib
import re
import time

from . import library

CAL_ID = re.compile(r"\((\d+)\)\.[A-Za-z0-9]+$")


def _folder(p):
    return p.rsplit("/", 1)[0] if "/" in p else ""


def _ok_path(p):
    return isinstance(p, str) and 0 < len(p) < 500 and not p.startswith("/") and ".." not in p.split("/") and "\x00" not in p


def _book_for(conn, path, md5):
    """The Daf book a Kindle file is: by its fingerprint, else by the Calibre id Daf names files with
    ("Title - Author (342).epub"), when the title agrees."""
    bid = library.book_for_md5(conn, md5) if md5 else None
    if bid:
        return bid
    m = CAL_ID.search(path)
    if m:
        b = conn.execute("SELECT id, title FROM books WHERE id = ?", (f"cal:{m.group(1)}",)).fetchone()
        name = library.norm(path.rsplit("/", 1)[-1])
        if b and library.norm(b["title"])[:12] and library.norm(b["title"])[:12] in name:
            return b["id"]
    return None


def shelf_name(folder):
    return folder.replace("/", " › ")


def _pending(conn):
    """What Daf has asked of the Kindle and it hasn't done yet: {book_id: folder}, moves and books on their way."""
    out = {}
    for r in conn.execute("SELECT book_id, dest FROM kindle_moves WHERE done IS NULL ORDER BY id"):
        if r["book_id"]:
            out[r["book_id"]] = r["dest"]
    for r in conn.execute("SELECT ref, shelf FROM kindle_queue WHERE kind = 'book' AND delivered IS NULL AND error IS NULL"):
        if r["ref"]:
            out.setdefault(r["ref"], r["shelf"])
    return out


def report(conn, folders, files):
    """The plugin's report: the folders, and every book in them ([{path, md5}]). Brings Daf's Kindle
    shelves in line with it. Returns the moves the plugin is to make: [{id, path, dest}]."""
    now = int(time.time())
    rows = []
    for f in files or []:
        if not isinstance(f, dict) or not _ok_path(f.get("path")):
            continue
        path, md5 = f["path"], str(f.get("md5") or "")[:40] or None
        rows.append((path, md5, _book_for(conn, path, md5), _folder(path), now))
    conn.execute("DELETE FROM kindle_files")
    conn.executemany("INSERT OR REPLACE INTO kindle_files (path, md5, book_id, shelf, seen) VALUES (?, ?, ?, ?, ?)", rows)
    # a move whose book isn't where Daf asked to move it from any more: the Kindle has moved on
    for mv in conn.execute("SELECT id, path FROM kindle_moves WHERE done IS NULL").fetchall():
        if not conn.execute("SELECT 1 FROM kindle_files WHERE path = ?", (mv["path"],)).fetchone():
            conn.execute("UPDATE kindle_moves SET done = ?, error = 'gone' WHERE id = ?", (now, mv["id"]))

    names = {n.strip("/") for n in folders or [] if isinstance(n, str) and _ok_path(n.strip("/"))}
    names |= {r[3] for r in rows if r[3]}
    pending = _pending(conn)
    names |= {d for d in pending.values() if d}
    # where each Daf book is: on the Kindle, unless Daf has asked for it somewhere else
    at = {r[2]: r[3] for r in rows if r[2]}
    at.update(pending)

    have = {r["kindle"]: r["id"] for r in conn.execute("SELECT id, kindle FROM shelves WHERE kindle IS NOT NULL")}
    for folder, sid in have.items():
        if folder not in names:                   # gone from the Kindle
            conn.execute("DELETE FROM shelf_books WHERE shelf_id = ?", (sid,))
            conn.execute("DELETE FROM shelves WHERE id = ?", (sid,))
    for folder in sorted(names):
        sid = have.get(folder) or _make_shelf(conn, folder, now)
        want = {b for b, f in at.items() if f == folder}
        on = {r[0] for r in conn.execute("SELECT book_id FROM shelf_books WHERE shelf_id = ?", (sid,))}
        for b in on - want:
            conn.execute("DELETE FROM shelf_books WHERE shelf_id = ? AND book_id = ?", (sid, b))
        conn.executemany("INSERT OR IGNORE INTO shelf_books (shelf_id, book_id, added) VALUES (?, ?, ?)", [(sid, b, now) for b in want - on])
    return moves(conn)


def _make_shelf(conn, folder, now):
    name = shelf_name(folder)
    if conn.execute("SELECT 1 FROM shelves WHERE lower(name) = lower(?)", (name,)).fetchone():
        name += " (Kindle)"                        # one of Daf's own shelves has the name
    sid = "kindle-" + (re.sub(r"[^a-z0-9]+", "-", folder.lower()).strip("-")[:30] or hashlib.sha1(folder.encode()).hexdigest()[:8])
    while conn.execute("SELECT 1 FROM shelves WHERE id = ?", (sid,)).fetchone():
        sid += "-" + hashlib.sha1(f"{folder}{time.time()}".encode()).hexdigest()[:4]
    conn.execute("INSERT INTO shelves (id, name, created, kindle) VALUES (?, ?, ?, ?)", (sid, name, now, folder))
    return sid


def moves(conn):
    return [{"id": r["id"], "path": r["path"], "dest": r["dest"]}
            for r in conn.execute("SELECT id, path, dest FROM kindle_moves WHERE done IS NULL ORDER BY id")]


def on_kindle(conn, book_id):
    r = conn.execute("SELECT path, shelf FROM kindle_files WHERE book_id = ? ORDER BY path LIMIT 1", (book_id,)).fetchone()
    return dict(r) if r else None


def put(conn, shelf_id, folder, book_id):
    """The book onto a Kindle shelf: moved there on the Kindle, or sent there. Returns what happens:
    "moves", "sent" or "there"."""
    from . import kindlequeue
    now = int(time.time())
    f = on_kindle(conn, book_id)
    if f and f["shelf"] == folder and not _pending(conn).get(book_id):
        how = "there"
    elif f:
        conn.execute("UPDATE kindle_moves SET done = ?, error = 'replaced' WHERE book_id = ? AND done IS NULL", (now, book_id))
        conn.execute("INSERT INTO kindle_moves (path, dest, book_id, requested) VALUES (?, ?, ?, ?)", (f["path"], folder, book_id, now))
        how = "moves"
    else:
        kindlequeue.queue_book(conn, book_id, folder)      # LookupError when Daf has no file for it
        how = "sent"
    # one shelf on the Kindle: off the others
    conn.execute("DELETE FROM shelf_books WHERE book_id = ? AND shelf_id IN (SELECT id FROM shelves WHERE kindle IS NOT NULL AND id != ?)", (book_id, shelf_id))
    conn.execute("INSERT OR IGNORE INTO shelf_books (shelf_id, book_id, added) VALUES (?, ?, ?)", (shelf_id, book_id, now))
    return how


def take_off(conn, shelf_id, book_id):
    """Off a Kindle shelf: to the Kindle's home folder (or, on its way, not sent after all)."""
    now = int(time.time())
    f = on_kindle(conn, book_id)
    conn.execute("UPDATE kindle_moves SET done = ?, error = 'replaced' WHERE book_id = ? AND done IS NULL", (now, book_id))
    if f and f["shelf"]:
        conn.execute("INSERT INTO kindle_moves (path, dest, book_id, requested) VALUES (?, '', ?, ?)", (f["path"], book_id, now))
    conn.execute("DELETE FROM kindle_queue WHERE id = ? AND delivered IS NULL", (f"book:{book_id}",))
    conn.execute("DELETE FROM shelf_books WHERE shelf_id = ? AND book_id = ?", (shelf_id, book_id))


def done(conn, move_id, error=None, path=None):
    """The plugin made a move (path: where the book is now), or couldn't (error)."""
    mv = conn.execute("SELECT * FROM kindle_moves WHERE id = ?", (move_id,)).fetchone()
    if not mv:
        return False
    conn.execute("UPDATE kindle_moves SET done = ?, error = ? WHERE id = ?", (int(time.time()), (str(error)[:300] if error else None), move_id))
    if not error and _ok_path(path):
        conn.execute("UPDATE kindle_files SET path = ?, shelf = ? WHERE path = ?", (path, _folder(path), mv["path"]))
    elif error and mv["book_id"]:
        # it stays where it was: back on that shelf in Daf
        f = conn.execute("SELECT shelf FROM kindle_files WHERE path = ?", (mv["path"],)).fetchone()
        conn.execute("DELETE FROM shelf_books WHERE book_id = ? AND shelf_id IN (SELECT id FROM shelves WHERE kindle IS NOT NULL)", (mv["book_id"],))
        if f and f["shelf"]:
            sid = conn.execute("SELECT id FROM shelves WHERE kindle = ?", (f["shelf"],)).fetchone()
            if sid:
                conn.execute("INSERT OR IGNORE INTO shelf_books (shelf_id, book_id, added) VALUES (?, ?, ?)", (sid[0], mv["book_id"], int(time.time())))
    return True

