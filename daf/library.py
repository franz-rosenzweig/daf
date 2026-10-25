"""Book identity: every Kindle copy, the audiobook and the vault note of one work
become one row in `books`, keyed by Calibre id when Calibre has it.

Matching is by Hardcover's book id first, where both sides have one (Calibre keeps it as the
`hardcover-book` identifier, a vault note as `hardcoverBookId`), then by normalized title
(subtitles, articles and punctuation dropped), checked against the author's surname when several
books share a title. A book added from Daf (book_adds) is a row of its own, `hc:<id>`, until its
note or its file arrives. When a book's id changes that way (hc: → vault: → cal:), everything that
pointed at the old id moves to the new one (rekey).
"""
import json
import re
import unicodedata
from pathlib import Path

from . import config
from .db import read_only
from .sources import lua

ARTICLES = re.compile(r"^(the|a|an)\s+")


def norm(title):
    t = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode().lower()
    t = re.split(r"[:(\[]| - ", t)[0]
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = ARTICLES.sub("", re.sub(r"\s+", " ", t).strip())
    if t:
        return t
    # A title in another script (Hebrew) keeps its own letters, or every such title would be "".
    r = re.split(r"[:(\[]| - ", unicodedata.normalize("NFKC", title or "").lower())[0]
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]+", " ", r)).strip()


def slug(title):
    """A vault book's id: its normalized title in a-z0-9, or a hash of it for one in another script."""
    import hashlib
    n = norm(title)
    return re.sub(r"[^a-z0-9]+", "-", n).strip("-") or "t" + hashlib.sha1(n.encode()).hexdigest()[:10]


def surname(author):
    a = unicodedata.normalize("NFKD", (author or "").split(",")[0].split("&")[0]).encode("ascii", "ignore").decode().lower()
    parts = re.findall(r"[a-z]+", a)
    return parts[-1] if parts else ""


def _frontmatter(text):
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    out = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


def calibre_books():
    db = config.CALIBRE_DBS[0]
    c = read_only(db)
    try:
        rows = c.execute(
            "SELECT b.id, b.title, b.path, b.has_cover, group_concat(a.name, ' & ') FROM books b "
            "LEFT JOIN books_authors_link l ON l.book = b.id LEFT JOIN authors a ON a.id = l.author GROUP BY b.id").fetchall()
        hc, isbn = {}, {}
        for book, typ, val in c.execute("SELECT book, type, val FROM identifiers WHERE type IN ('hardcover-book', 'isbn', 'isbn13', 'isbn10')"):
            if typ == "hardcover-book" and str(val).isdigit():
                hc[book] = int(val)
            elif typ != "hardcover-book":
                isbn.setdefault(book, []).append(re.sub(r"[^0-9Xx]", "", str(val)))
    finally:
        c.close()
    return [{"id": r[0], "title": r[1], "path": str(db.parent / r[2]) if r[3] else None, "author": r[4] or "",
             "hc": hc.get(r[0]), "isbn": isbn.get(r[0], [])} for r in rows]


def vault_books():
    out = []
    for p in (config.VAULT / "Reference" / "books").glob("*.md"):
        if ".sync-conflict-" in p.name:
            continue
        try:
            fm = _frontmatter(p.read_text(encoding="utf-8")[:4000])
        except (OSError, UnicodeDecodeError):
            continue
        if fm.get("type") != "book":
            continue
        hcid = str(fm.get("hardcoverBookId") or "").strip()
        out.append({"title": fm.get("title") or p.stem, "author": fm.get("author", ""), "status": fm.get("status", ""),
                    "path": str(p.relative_to(config.VAULT)), "hc": int(hcid) if hcid.isdigit() else None})
    return out


def sidecars(conn=None):
    """KOReader sidecars: (path, parsed table). The Daf plugin sends each book's own (kindle_sidecars,
    since 2026-10-20); a copy synced to the server by Syncthing is used for a book the plugin hasn't sent.
    Conflict copies skipped."""
    sent = {}
    if conn is not None:
        for md5, file, data in conn.execute("SELECT md5, file, data FROM kindle_sidecars"):
            try:
                sent[md5] = (Path("plugin:" + (file or md5)), json.loads(data))
            except ValueError:
                continue
    root = Path("/srv/koreader/Libros")
    for p in root.rglob("metadata.*.lua"):
        if "sync-conflict" in p.name or not p.parent.name.endswith(".sdr"):
            continue
        try:
            t = lua.load(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001 - one unreadable sidecar must not stop the rest
            continue
        if t.get("partial_md5_checksum") in sent:
            continue                     # the plugin's copy is the Kindle's own, and newer
        yield p, t
    yield from sent.values()


def abs_books():
    c = read_only(config.ABS_DB)
    try:
        user = c.execute("SELECT id FROM users WHERE username = ?", (config.ABS_USER,)).fetchone()
        rows = c.execute(
            "SELECT li.id, b.id, b.title, (SELECT group_concat(au.name, ' & ') FROM bookAuthors ba JOIN authors au ON au.id = ba.authorId WHERE ba.bookId = b.id) "
            "FROM libraryItems li JOIN books b ON b.id = li.mediaId WHERE li.mediaType = 'book'").fetchall()
        prog = {r[0]: (r[1], r[2], r[3]) for r in c.execute(
            "SELECT mediaItemId, currentTime, duration, isFinished FROM mediaProgresses WHERE userId = ? AND mediaItemType = 'book'",
            (user[0] if user else "",))}
    finally:
        c.close()
    out = []
    for item_id, book_id, title, author in rows:
        cur, dur, fin = prog.get(book_id, (None, None, None))
        out.append({"item": item_id, "media": book_id, "title": title, "author": author or "",
                    "pct": (100.0 if fin else round(100 * cur / dur, 1)) if cur and dur else None,
                    "pos": cur, "len": dur})
    return out


class Matcher:
    def __init__(self, cal, vault):
        self.cal, self.cal_hc = {}, {}
        for b in cal:
            self.cal.setdefault(norm(b["title"]), []).append(b)
            if b.get("hc"):
                self.cal_hc.setdefault(b["hc"], b)
        self.vault, self.vault_hc = {}, {}
        for v in vault:
            self.vault.setdefault(norm(v["title"]), []).append(v)
            if v.get("hc"):
                self.vault_hc.setdefault(v["hc"], v)

    @staticmethod
    def _pick(cands, author):
        if len(cands) == 1 or not author:
            return cands[0]
        s = surname(author)
        for c in cands:
            if s and s in c["author"].lower():
                return c
        return cands[0]

    def calibre(self, title, author, hc=None):
        if hc and hc in self.cal_hc:
            return self.cal_hc[hc]
        c = self.cal.get(norm(title))
        return self._pick(c, author) if c else None

    def vault_note(self, title, author, hc=None):
        if hc and hc in self.vault_hc:
            return self.vault_hc[hc]
        v = self.vault.get(norm(title))
        return self._pick(v, author) if v else None


def private_patterns(settings):
    return [p.lower() for p in settings.get("private_titles", [])]


def is_private(title, settings):
    t = (title or "").lower()
    return any(p in t for p in private_patterns(settings))


# Where a book's id is kept: (table, column, keyed by it). A keyed row that the new id already has
# is the new id's, and the old one goes.
BOOK_REFS = [("highlights", "book_id", False), ("shelf_books", "book_id", True), ("book_review", "book_id", True),
             ("ebook_pages", "book_id", True), ("reading_notes", "book_id", False), ("audio_bookmarks", "book_id", False),
             ("hc_links", "book_id", True), ("book_marks", "book_id", False), ("book_positions", "book_id", True),
             ("paper_pages", "book_id", False), ("book_files", "book_id", False)]


def rekey(conn, settings, old, new):
    """Everything that pointed at book `old` points at `new`: a want-to-read book that got its note, a
    note that got its Calibre file."""
    import logging
    for table, col, keyed in BOOK_REFS:
        if keyed:
            conn.execute(f"UPDATE OR IGNORE {table} SET {col} = ? WHERE {col} = ?", (new, old))
            conn.execute(f"DELETE FROM {table} WHERE {col} = ?", (old,))
        else:
            conn.execute(f"UPDATE {table} SET {col} = ? WHERE {col} = ?", (new, old))
    conn.execute("UPDATE sessions SET item = ? WHERE item = ? AND source IN ('ebook', 'paper')", (new, old))
    conn.execute("UPDATE OR IGNORE kindle_queue SET id = ?, ref = ? WHERE id = ?", (f"book:{new}", new, f"book:{old}"))
    ns = settings.get("nightstand") or []
    if old in ns:
        s = config.load_settings()
        s["nightstand"] = [new if i == old else i for i in s.get("nightstand", [])]
        s["nightstand"] = list(dict.fromkeys(s["nightstand"]))[:3]
        config.save_settings(s)
        settings["nightstand"] = s["nightstand"]
    logging.getLogger("daf.library").info("book %s is now %s", old, new)


def rebuild(conn, settings):
    """Recompute books and book_keys from Calibre, the vault, the Kindle and Audiobookshelf."""
    from . import bookfiles
    try:
        bookfiles.settle(conn)                  # files sent from Daf: which Calibre book each became
    except Exception:  # noqa: BLE001 - the books still build
        import logging
        logging.getLogger("daf.library").exception("bookfiles.settle")
    cal, vault = calibre_books(), vault_books()
    ov = bookfiles.overrides(conn)
    for c in cal:
        if c["id"] in ov:
            c["hc"] = ov[c["id"]]
    m = Matcher(cal, vault)
    books, keys = {}, {}

    def ensure(bid, kind, title, author, cal_row=None, hc=None):
        b = books.get(bid)
        if not b:
            hc = hc or (cal_row or {}).get("hc")
            b = books[bid] = {"id": bid, "kind": kind, "title": title, "author": author or None,
                              "calibre_id": cal_row["id"] if cal_row else None,
                              "calibre_path": cal_row["path"] if cal_row else None, "vault_path": None, "status": None,
                              "progress": None, "progress_note": None, "last_read": None, "audio_pct": None,
                              "audio_note": None, "url": None, "private": 0, "hc_id": hc}
            v = m.vault_note(title, author, hc)
            if v:
                b["vault_path"], b["status"] = v["path"], v["status"]
                b["hc_id"] = b["hc_id"] or v.get("hc")
        return b

    def resolve(title, author):
        c = m.calibre(title, author)
        if c:
            return ensure(f"cal:{c['id']}", "book", c["title"], c["author"], c)
        v = m.vault_note(title, author)
        if v:
            return ensure(f"vault:{slug(v['title'])}", "book", v["title"], v["author"], hc=v.get("hc"))
        return None

    # The Kindle: titles from KoInsight/plugin and from the sidecars.
    kindle_titles = {r["md5"]: (r["title"], r["authors"]) for r in conn.execute("SELECT md5, title, authors FROM kindle_books")}
    for _p, t in sidecars(conn):
        md5 = t.get("partial_md5_checksum")
        dp = t.get("doc_props") or {}
        if md5 and dp.get("title"):
            kindle_titles.setdefault(md5, (dp.get("title"), dp.get("authors")))
    from . import kindlesend
    daf_epubs = kindlesend.epubs(conn)          # Send to Kindle's articles, not books
    for md5, (title, authors) in kindle_titles.items():
        if not title or md5 in daf_epubs:
            continue
        b = resolve(title, None if authors in (None, "N/A") else authors) or ensure(f"md5:{md5}", "book", title, authors if authors != "N/A" else None)
        keys[f"md5:{md5}"] = b["id"]

    # Audiobookshelf.
    try:
        for a in abs_books():
            b = resolve(a["title"], a["author"]) or ensure(f"abs:{a['item']}", "book", a["title"], a["author"])
            keys[f"abs:{a['item']}"] = b["id"]
            keys[f"absmedia:{a['media']}"] = b["id"]
            if a["pct"] is not None:
                b["audio_pct"] = a["pct"]
                b["audio_note"] = f"{int(a['pos'] // 3600)}h {int(a['pos'] % 3600 // 60)}m of {int(a['len'] // 3600)}h {int(a['len'] % 3600 // 60)}m"
    except Exception:  # noqa: BLE001
        pass

    # Every vault book note is a book even if nothing has been read on a device.
    for v in vault:
        c = m.calibre(v["title"], v["author"], v.get("hc"))
        if not c:
            if not any(b.get("vault_path") == v["path"] for b in books.values()):
                ensure(f"vault:{slug(v['title'])}", "book", v["title"], v["author"], hc=v.get("hc"))
        else:
            ensure(f"cal:{c['id']}", "book", c["title"], c["author"], c)

    # And every book in Calibre, so the whole library can be opened in Daf's reader.
    for c in cal:
        ensure(f"cal:{c['id']}", "book", c["title"], c["author"], c)

    # Books added from Daf (Add a book) that no note and no Calibre book has yet.
    have_hc = {b["hc_id"] for b in books.values() if b.get("hc_id")}
    for a in conn.execute("SELECT * FROM book_adds").fetchall():
        if a["hc_id"] in have_hc:
            continue
        b = ensure(f"hc:{a['hc_id']}", "book", a["title"], a["author"], hc=a["hc_id"])
        b["status"] = b["status"] or {1: "want-to-read", 2: "reading"}.get(a["status"])

    # Kindle progress: the newest page turn in any copy of the book.
    latest = conn.execute(
        "SELECT p.md5, p.start, p.page, p.total FROM pages p JOIN "
        "(SELECT md5, MAX(start) AS m FROM pages GROUP BY md5) x ON x.md5 = p.md5 AND x.m = p.start").fetchall()
    for r in latest:
        bid = keys.get(f"md5:{r['md5']}")
        b = books.get(bid)
        if not b or (b["last_read"] and b["last_read"] >= r["start"]):
            continue
        b["last_read"] = r["start"]
        if r["page"] and r["total"]:
            b["progress"] = round(100 * r["page"] / r["total"], 1)
            b["progress_note"] = f"page {r['page']} of {r['total']}"

    # Reading in Daf counts as reading the book: a newer position there wins.
    for r in conn.execute("SELECT book_id, fraction, updated FROM book_positions").fetchall():
        b = books.get(r["book_id"])
        if b and r["updated"] and (not b["last_read"] or r["updated"] > b["last_read"]):
            b["last_read"] = r["updated"]
            b["progress"] = round(100 * (r["fraction"] or 0), 1)
            b["progress_note"] = f"{b['progress']:.0f}% in Daf"

    for b in books.values():
        b["private"] = 1 if is_private(b["title"], settings) else 0

    # A book whose id changed (its note or its file arrived): its shelves, place, notes and the rest follow.
    moved = {}
    for old in conn.execute("SELECT id, hc_id, vault_path, calibre_id FROM books WHERE kind = 'book'").fetchall():
        if old["id"] in books:
            continue
        new = next((b["id"] for b in books.values() if
                    (old["hc_id"] and b.get("hc_id") == old["hc_id"]) or
                    (old["vault_path"] and b.get("vault_path") == old["vault_path"]) or
                    (old["calibre_id"] and b.get("calibre_id") == old["calibre_id"])), None)
        if new:
            moved[old["id"]] = new
    for old, new in moved.items():
        rekey(conn, settings, old, new)

    conn.execute("DELETE FROM books WHERE kind = 'book'")
    conn.execute("DELETE FROM book_keys WHERE key NOT LIKE 'kk:%'")
    cols = ["id", "kind", "title", "author", "calibre_id", "calibre_path", "vault_path", "status", "progress",
            "progress_note", "last_read", "audio_pct", "audio_note", "url", "private", "hc_id"]
    conn.executemany(f"INSERT OR REPLACE INTO books ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                     [tuple(b[c] for c in cols) for b in books.values()])
    conn.executemany("INSERT OR REPLACE INTO book_keys (key, book_id) VALUES (?, ?)", list(keys.items()))
    try:
        from . import kindlequeue
        kindlequeue.follow_up(conn)             # books that were to go to the Kindle once their file came
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger("daf.library").exception("kindlequeue.follow_up")
    return len(books)


def add_paper_book(conn, title, author=None):
    """A book that exists only on paper: a vault note (so rebuild keeps it) and a books row."""
    from . import vaultnotes
    title, author = title.strip(), (author or "").strip() or None
    if not norm(title):
        raise ValueError("A title, please")
    bid = f"vault:{slug(title)}"
    row = conn.execute("SELECT * FROM books WHERE id = ?", (bid,)).fetchone()
    if not row:
        conn.execute("INSERT INTO books (id, kind, title, author, private) VALUES (?, 'book', ?, ?, 0)", (bid, title, author))
        row = conn.execute("SELECT * FROM books WHERE id = ?", (bid,)).fetchone()
    if not row["vault_path"]:
        vaultnotes.new_book_note(conn, row)
    return bid


def book_for_md5(conn, md5):
    r = conn.execute("SELECT book_id FROM book_keys WHERE key = ?", (f"md5:{md5}",)).fetchone()
    return r[0] if r else None


def current_kindle_book(conn):
    """The book and page of the newest Kindle page turn: (book row, page, total, when)."""
    r = conn.execute("SELECT md5, start, page, total FROM pages ORDER BY start DESC LIMIT 1").fetchone()
    if not r:
        return None
    bid = book_for_md5(conn, r["md5"])
    b = conn.execute("SELECT * FROM books WHERE id = ?", (bid,)).fetchone() if bid else None
    return {"book": dict(b) if b else None, "page": r["page"], "total": r["total"], "when": r["start"]}


def nightstand(conn, settings):
    ids = [i for i in settings.get("nightstand", []) if isinstance(i, str)][:3]
    rows = {r["id"]: dict(r) for r in conn.execute(
        f"SELECT * FROM books WHERE id IN ({','.join('?' * len(ids))})", ids)} if ids else {}
    return [rows[i] for i in ids if i in rows]


def suggest_nightstand(conn):
    """Until you pick, the three books most recently read on the Kindle."""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM books WHERE kind = 'book' AND last_read IS NOT NULL AND private = 0 "
        "AND id NOT IN (SELECT book_id FROM manga_books) ORDER BY last_read DESC LIMIT 3")]


def cover_path(conn, book_id):
    r = conn.execute("SELECT calibre_path FROM books WHERE id = ?", (book_id,)).fetchone()
    if r and r[0]:
        p = Path(r[0]) / "cover.jpg"
        if p.exists():
            return p
    return None


def to_json(row):
    return json.loads(json.dumps(dict(row)))
