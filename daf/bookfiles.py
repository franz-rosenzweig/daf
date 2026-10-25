"""A book's file, from Daf into Calibre (Books → a book → Add the file, or Add a book with its file).

Calibre stays read-only to Daf: the file goes into Calibre-Web-Automated's import folder
(config.CWA_INGEST), which adds it to the library, converts it to EPUB and fetches its metadata
(Hardcover first). Before it goes, an EPUB gets the book's Hardcover id and ISBN written into its
own metadata, so the import finds the right book; and book_files remembers which Daf book (and
Hardcover book) it was for. Once Calibre has it, `settle` ties the new Calibre book to that
Hardcover book even if Calibre-Web gave it another title, and the Daf book (hc: or vault:) becomes
the Calibre one (library.rekey moves its shelves, place and notes).
"""
import io
import re
import time
import zipfile
from datetime import datetime, timezone

from . import config
from .db import read_only

FORMATS = {"epub", "kepub", "mobi", "azw3", "fb2", "cbz", "pdf"}
MAX_BYTES = 200 * 1024 * 1024
FAILED_DIR = config.STATE.parent / "cwa" / "processed_books" / "failed"


class Exists(Exception):
    def __init__(self, msg, book_id=None):
        super().__init__(msg)
        self.book_id = book_id


def _safe(s):
    s = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", s or "").strip().strip(".")
    return re.sub(r"\s+", " ", s)[:120] or "Book"


def in_calibre(conn, hc_id=None, isbn=None, title=None, author=None):
    """The Calibre book that is this one already, if any: by Hardcover id, then ISBN, then title."""
    from . import library
    isbn = re.sub(r"[^0-9Xx]", "", isbn or "")
    for c in library.calibre_books():
        if hc_id and c.get("hc") == int(hc_id):
            return c
        if isbn and isbn in c.get("isbn", []):
            return c
    if title:
        m = library.Matcher(library.calibre_books(), [])
        c = m.calibre(title, author)
        if c and (not author or library.surname(author) in (c["author"] or "").lower()):
            return c
    return None


def _epub_with_ids(raw, title, author, isbn, hc_id):
    """The EPUB with dc:identifier entries for the ISBN and the Hardcover book (and a title and author
    if it has none). Anything that goes wrong: the file as it came."""
    try:
        zin = zipfile.ZipFile(io.BytesIO(raw))
        container = zin.read("META-INF/container.xml").decode("utf-8", "replace")
        opf_path = re.search(r'full-path="([^"]+)"', container).group(1)
        opf = zin.read(opf_path).decode("utf-8")
        v3 = bool(re.search(r'<package[^>]*\sversion="3', opf))
        add = []
        if isbn and isbn not in opf:
            add.append(f"<dc:identifier>urn:isbn:{isbn}</dc:identifier>" if v3 else f'<dc:identifier opf:scheme="ISBN">{isbn}</dc:identifier>')
        if hc_id and f"hardcover-book:{hc_id}" not in opf:
            add.append(f"<dc:identifier>hardcover-book:{hc_id}</dc:identifier>" if v3
                       else f'<dc:identifier opf:scheme="hardcover-book">{hc_id}</dc:identifier>')
        if title and not re.search(r"<dc:title[^>]*>\s*[^<\s]", opf):
            opf = re.sub(r"<dc:title[^>]*>\s*</dc:title>|<dc:title[^>]*/>", "", opf)       # an empty one gives way
            add.append(f"<dc:title>{_xml(title)}</dc:title>")
        if author and not re.search(r"<dc:creator[^>]*>\s*[^<\s]", opf):
            add.append(f"<dc:creator>{_xml(author)}</dc:creator>")
        if not add or "</metadata>" not in opf and "</opf:metadata>" not in opf:
            return raw
        if not v3 and 'xmlns:opf=' not in opf:
            add = [a.replace(' opf:scheme=', ' scheme=') for a in add]
        end = "</opf:metadata>" if "</opf:metadata>" in opf else "</metadata>"
        opf = opf.replace(end, "\n    " + "\n    ".join(add) + "\n  " + end, 1)
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as zout:
            for info in zin.infolist():
                data = opf.encode("utf-8") if info.filename == opf_path else zin.read(info.filename)
                zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
        return out.getvalue()
    except Exception:  # noqa: BLE001 - Calibre-Web reads it as it is
        return raw


def _xml(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def attach(conn, book_id, filename, raw, kindle_shelf=None, force=False):
    """Sends a book's file to Calibre-Web's import folder for the Daf book book_id. Returns the name it
    went under. Raises Exists when Calibre has the book already (force sends it anyway)."""
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext not in FORMATS:
        raise ValueError("Calibre takes EPUB, KEPUB, MOBI, AZW3, FB2, CBZ or PDF")
    if len(raw) > MAX_BYTES:
        raise ValueError("That file is over 200 MB")
    b = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if not b:
        raise KeyError(book_id)
    add = conn.execute("SELECT * FROM book_adds WHERE hc_id = ?", (b["hc_id"],)).fetchone() if b["hc_id"] else None
    isbn = add["isbn"] if add else None
    if not force:
        if b["calibre_id"]:
            raise Exists("Calibre has this book already", f"cal:{b['calibre_id']}")
        c = in_calibre(conn, b["hc_id"], isbn, b["title"], b["author"])
        if c:
            raise Exists(f"Calibre has it already: {c['title']}", f"cal:{c['id']}")
    if ext == "epub":
        raw = _epub_with_ids(raw, b["title"], b["author"], isbn, b["hc_id"])
    config.CWA_INGEST.mkdir(parents=True, exist_ok=True)
    stem = _safe(f"{b['title']} - {b['author']}" if b["author"] else b["title"])
    name, n = f"{stem}.{ext}", 2
    while (config.CWA_INGEST / name).exists() or conn.execute("SELECT 1 FROM book_files WHERE name = ?", (name,)).fetchone():
        name, n = f"{stem} ({n}).{ext}", n + 1
    part = config.CWA_INGEST / ("." + name + ".part")          # hidden until whole: the import skips it
    part.write_bytes(raw)
    part.replace(config.CWA_INGEST / name)
    conn.execute("INSERT INTO book_files (name, hc_id, book_id, title, author, created, kindle_shelf) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (name, b["hc_id"], book_id, b["title"], b["author"], int(time.time()), kindle_shelf))
    return name


def _calibre_added_since(ts):
    """Calibre books added since ts (epoch seconds): [{id, title, author, hc, isbn}]."""
    from . import library
    db = config.CALIBRE_DBS[0]
    c = read_only(db)
    try:
        since = datetime.fromtimestamp(ts - 120, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        ids = {r[0] for r in c.execute("SELECT id FROM books WHERE timestamp >= ?", (since,))}
    finally:
        c.close()
    return [b for b in library.calibre_books() if b["id"] in ids]


def settle(conn):
    """Files sent to Calibre-Web: which Calibre book each became (by its Hardcover id, ISBN or
    title among the books added since), or why not. Called before every library rebuild."""
    from . import library
    for f in conn.execute("SELECT * FROM book_files WHERE cal_id IS NULL AND error IS NULL").fetchall():
        add = conn.execute("SELECT isbn FROM book_adds WHERE hc_id = ?", (f["hc_id"],)).fetchone() if f["hc_id"] else None
        isbn = re.sub(r"[^0-9Xx]", "", (add["isbn"] if add else "") or "")
        hit = None
        for c in _calibre_added_since(f["created"]):
            if (f["hc_id"] and c.get("hc") == f["hc_id"]) or (isbn and isbn in c.get("isbn", [])):
                hit = c
                break
            if library.norm(c["title"]) == library.norm(f["title"] or "") and (
                    not f["author"] or library.surname(f["author"]) in (c["author"] or "").lower()):
                hit = hit or c
        if hit:
            conn.execute("UPDATE book_files SET cal_id = ? WHERE name = ?", (hit["id"], f["name"]))
            if f["hc_id"]:
                conn.execute("INSERT OR REPLACE INTO hc_links (book_id, hc_book_id, linked) VALUES (?, ?, ?)",
                             (f"cal:{hit['id']}", f["hc_id"], int(time.time())))
            continue
        stem = f["name"].rsplit(".", 1)[0]
        if FAILED_DIR.exists() and any(p.name.startswith(stem) for p in FAILED_DIR.iterdir()):
            conn.execute("UPDATE book_files SET error = ? WHERE name = ?", ("Calibre-Web couldn't import it (it's in its failed folder)", f["name"]))
        elif time.time() - f["created"] > 6 * 3600:
            conn.execute("UPDATE book_files SET error = ? WHERE name = ?", ("Calibre hasn't got it after six hours", f["name"]))


def overrides(conn):
    """Calibre id -> Hardcover id for files sent from Daf: the book chosen in Daf wins over the one
    Calibre-Web's metadata fetch picked."""
    return {r[0]: r[1] for r in conn.execute("SELECT cal_id, hc_id FROM book_files WHERE cal_id IS NOT NULL AND hc_id IS NOT NULL")}


def pending(conn, book_id):
    r = conn.execute("SELECT name, created, cal_id, error FROM book_files WHERE book_id = ? ORDER BY created DESC LIMIT 1", (book_id,)).fetchone()
    return dict(r) if r else None
